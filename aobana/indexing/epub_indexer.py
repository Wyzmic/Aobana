import bisect
import collections
import os
import sys
import re
import unicodedata
import sqlite3
import hashlib
import json
import time
import zipfile
import posixpath
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urlsplit
import warnings
from bs4 import BeautifulSoup, NavigableString, CData, Comment, Declaration, XMLParsedAsHTMLWarning
from bs4.builder import HTMLParserTreeBuilder
from bs4.dammit import EncodingDetector


def _page_markup(raw):
    if isinstance(raw, str):
        return raw, None, None, False
    detector = EncodingDetector(raw, is_html=True)
    declared = detector.find_declared_encoding(detector.markup, is_html=True)
    encoding = detector.sniffed_encoding or declared or 'utf-8'
    try:
        text = detector.markup.decode(encoding, errors='replace')
    except LookupError:
        encoding = 'utf-8'
        text = detector.markup.decode(encoding, errors='replace')
    return text, encoding, declared, '\ufffd' in text


class _PageBuilder(HTMLParserTreeBuilder):
    def prepare_markup(self, markup, user_specified_encoding=None,
                       document_declared_encoding=None, exclude_encodings=None):
        yield _page_markup(markup)


def parse_page(raw):
    return BeautifulSoup(raw, builder=_PageBuilder())
warnings.filterwarnings('ignore', category=XMLParsedAsHTMLWarning)

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from sudachipy import tokenizer, dictionary
from datetime import datetime

from aobana import paths
BASE_DIR = paths.BASE_DIR
EPUB_ROOT_DIR = paths.books_dir()
DB_PATH = paths.epub_db()

_TOKENIZER = None
mode = tokenizer.Tokenizer.SplitMode.A
from aobana.utils import SUDACHI_MAX_BYTES, sudachi_pieces as _sudachi_pieces


def get_tokenizer():
    global _TOKENIZER
    if _TOKENIZER is None:
        _TOKENIZER = dictionary.Dictionary(dict="core").create()
    return _TOKENIZER

from aobana.utils import (
    KANA_RE, KANJI_CHARS, KANJI_PATTERN,
    ALPHA_CHARS, ALPHA_PATTERN, RUBY_BASE_RE, BOOK_RUBY_RE, BOOK_BAR_RUBY_RE,
    norm_relpath, INDEX_FORMAT, is_outdated, ensure_format_column, compact_if_worth, stop_requested, write_tokenizer_meta, ruby_index_extras, fold_compat, parallel_map, append_filtered_rows, refresh_auto_filtered,
    held_removals, ALLOW_REMOVAL_FLAG, name_key, start_output, emit, say,
)

TIMESTAMP_SCENE_RE = re.compile(
    r'^\s*[-ー―‐―—\s]*[0-9０-９]+[\s:：][0-9０-９]+(?:[\s:：][0-9０-９]+)?\s*$'
)
ILLUSTRATION_PLACEHOLDER_RE = re.compile(
    r'^\s*[（(［\[【〔〈《「『]*\s*(?:挿絵|挿図|イラスト|口絵|図版|カラー口絵|口絵イラスト|挿画)\s*[）)］\]】〕〉》」』]*\s*$'
)

_EXCLUDED_LOG = []

from aobana.utils import convert_hw_katakana, EPUB_STR_REPLACEMENTS, katakana_to_hiragana, replace_until_fixed
from aobana.utils import normalize_cjk_spacing, book_title_and_author, _BOOK_BRACKET
from aobana.utils import ensure_chapters, chapter_spans, has_chapters, ensure_chapter_folder
from aobana.utils import ensure_line_lengths, has_line_lengths, write_line_lengths, stored_display_length
from aobana.utils import has_token_lengths, token_lengths_blob, write_token_lengths
from aobana.utils import ensure_ruby_lexicon, has_ruby_lexicon, write_ruby_lexicon, drop_ruby_lexicon

_RE_REPLACEMENTS = [
    (re.compile(r'＠ルビ.*?［(.+?)[｜|](.+?)］＠'), r'｜\1(\2)'),
    (re.compile(r'(?<![―—])[―—](?![―—])'), '――'),
    (re.compile(r'[・]{3,}'), '…'),
    (re.compile(r'…{2,}'), '…'),
    (re.compile(r'‥{2,}'), '…'),
    (re.compile(r'~~~'), '～～～'),
    (re.compile(r'~~'),  '～～'),
    (re.compile(r'~'),   '～'),
]

GENERIC_TOC_NAMES = {
    '表紙', '扉', '本文', '目次', 'GUIDE', 'NAVIGATION', 'START', 
    'COVER', 'CONTENTS', 'MAIN', '中扉', 'TABLE OF CONTENTS', 'LANDMARKS'
}

IN_FILE_CHAPTER_RE = re.compile(
    r'^(?:(?:第\s*)?[0-9０-９一二三四五六七八九十百千]+\s*[章話回篇幕首課節]|'
    r'ACT(?:\.|\s+)?(?:[0-9０-９\d]+|[IVXLCDM]+(?!\w))|'
    r'Chapter\s*(?:[0-9０-９\d]+|[IVXLCDM]+(?!\w))|'
    r'プロローグ|エピローグ|序章|終章|序幕|終幕|間奏|幕間|'
    r'Interlude|Prologue|Epilogue|Intro|Outro|'
    r'まえがき|あとがき|はじめに|おわりに|序|序文|跋|跋文|'
    r'解説|解題|凡例|年表|初出一覧|著者紹介|監修者紹介|訳者あとがき|著者あとがき|'
    r'主要参考文献|参考文献|用語集|索引|奥付|附録|付録|補章|追補|特別寄稿)'
    r'(?:.*)?$',
    re.IGNORECASE
)

IN_FILE_PART_RE = re.compile(
    r'^(?:(?:第\s*)?[0-9０-９一二三四五六七八九十百千IVX]+\s*[部巻篇]|'
    r'Part\s*(?:[0-9０-９\d]+|[IVXLCDM]+(?!\w))|PART\s*(?:[0-9０-９\d]+|[IVXLCDM]+(?!\w))|'
    r'上巻|中巻|下巻|前篇|後篇|本篇|別篇)'
    r'(?:.*)?$',
    re.IGNORECASE
)

CONTENTS_LABEL_RE = re.compile(r'目\s*次|もくじ|^(?:table\s+of\s+)?contents$|ＣＯＮＴＥＮＴＳ', re.IGNORECASE)
COLOPHON_LABEL_RE = re.compile(r'奥付|^[本中]?扉$')
COLOPHON_TEXT_RE = re.compile(r'発行所|発行者|発行人|印刷所|初版発行|禁無断|著作権|配信|電子書籍版|ISBN')
JAPANESE_TEXT_RE = re.compile(r'[ぁ-ゖァ-ヺ一-鿿々]')
COLOPHON_PAGE_CHARS = 1500
HTML_MEDIA_TYPES = {'application/xhtml+xml', 'text/html'}
HTML_EXTS = ('.xhtml', '.html', '.htm', '.xml')

STANDALONE_NON_PART_SECTIONS = {
    'まえがき', 'あとがき', 'はじめに', 'おわりに', '序', '序文', '跋', '跋文',
    '解説', '解題', '凡例', '年表', '初出一覧', '著者紹介', '監修者紹介',
    '訳者あとがき', '著者あとがき', '主要参考文献', '参考文献', '用語集', '索引',
    '奥付', '附録', '付録', '補章', '追補', '特別寄稿', 'ビジュアル・ギャラリー'
}

SUB_NUMBERING_RE = re.compile(
    r'^(?:[0-9０-９]+[\.\s　、・\-:：“"\'（\(]|'
    r'[0-9０-９]+\.[0-9０-９]+|'
    r'[一二三四五六七八九十]+[\s　、・\-:：“"\'（\(])'
)

def strip_ruby_markup(text: str) -> str:
    if '(' in text:
        text = BOOK_BAR_RUBY_RE.sub(r'\1', BOOK_RUBY_RE.sub(r'\1\2', text))
    return text.replace('｜', '')


_GLUED_BRACKET_RE = re.compile(r'(?<=[^()\s　])\([^()]*\)')


def heading_test_text(text: str) -> str:
    t = strip_ruby_markup(text)
    while '(' in t:
        t, n = _GLUED_BRACKET_RE.subn('', t)
        if not n:
            break
    return t


def _name_key(text: str) -> str:
    t = re.sub(r'[\s　]+', '', text).replace('（', '(').replace('）', ')')
    return heading_test_text(t)

LABEL_PAREN_RE = re.compile(r'\(([^()]*)\)')


def _label_parens(t: str) -> str:
    def one(m):
        before = t[:m.start()].rstrip(' 　')
        if before and re.match(r'[A-Za-z0-9_)]', before[-1]):
            return m.group(0)
        return f'（{m.group(1)}）'
    return LABEL_PAREN_RE.sub(one, t)


def clean_heading_label(text: str) -> str:
    if '｜' in text or '|' in text:
        parts = [clean_heading_label(p) for p in re.split(r'[｜|]', text)]
        return '｜'.join(p for p in parts if p)
    t = strip_ruby_markup(text.strip())
    t = t.replace('/', '／').replace('\\', '＼')
    t = _label_parens(t)
    t = drawn_gloss_text(t)
    t = t.replace('\u201c', '"').replace('\u201d', '"')
    t = t.replace('\u300e', '"').replace('\u300f', '"')
    t = t.replace('\u301d', '"').replace('\u301e', '"')
    t = t.replace('\u301f', '"')
    t = re.sub(r'[\s　]+', ' ', t)
    m = re.match(r'^((?:第\s*)?[0-9０-９一二三四五六七八九十百千IVX]+\s*[部巻篇章話回幕首課節])(\s*)(.*)$', t)
    if m:
        prefix = re.sub(r'\s+', '', m.group(1))
        rest = m.group(3).strip()
        if not m.group(2) and (rest[:1] == 'の' or (rest[:1] == '目' and prefix[-1] in '回首話')):
            return _tidy_label(prefix + rest)
        return _tidy_label(f"{prefix} {rest}".strip())
    return _tidy_label(normalize_cjk_spacing(t))


def _tidy_label(t: str) -> str:
    return re.sub(r'[ 　]*：[ 　]*', '：', re.sub(r'[ 　]+（', '（', t))


def is_valid_heading_block(tag_name: str, text: str) -> bool:
    if tag_name in ('td', 'th'):
        return False
    clean_t = normalize_cjk_spacing(heading_test_text(text.strip()))
    if not clean_t or len(clean_t) > 40:
        return False
    if TIMESTAMP_SCENE_RE.match(clean_t) or ILLUSTRATION_PLACEHOLDER_RE.match(clean_t):
        return False
    if clean_t.startswith(('「', '『', '（', '【', '※', '・', '…', '―')):
        return False
    if '。' in clean_t or '？' in clean_t or '！' in clean_t:
        return False
    if any(ind in clean_t for ind in ('の第', 'による', 'について', 'から', 'における', '──詩')):
        return False
    return bool(IN_FILE_CHAPTER_RE.match(clean_t) or IN_FILE_PART_RE.match(clean_t))


def format_merged_chapter_name(current_part: str, chapter_title: str) -> str:
    ch_clean = clean_heading_label(chapter_title)
    if not current_part:
        return ch_clean
    if TIMESTAMP_SCENE_RE.match(ch_clean) or ILLUSTRATION_PLACEHOLDER_RE.match(ch_clean):
        return clean_heading_label(current_part)
    part_clean = clean_heading_label(current_part)
    if ch_clean.startswith(part_clean):
        return ch_clean
    if ch_clean in STANDALONE_NON_PART_SECTIONS or any(ch_clean.startswith(s) for s in STANDALONE_NON_PART_SECTIONS):
        return ch_clean
    return f"{part_clean}｜{ch_clean}"

def is_part_divider(label: str) -> bool:
    return bool(IN_FILE_PART_RE.match(normalize_cjk_spacing(heading_test_text(label.strip()))))

def is_main_chapter_heading(label: str) -> bool:
    clean = normalize_cjk_spacing(heading_test_text(label.strip()))
    if TIMESTAMP_SCENE_RE.match(clean) or ILLUSTRATION_PLACEHOLDER_RE.match(clean):
        return False
    return bool(IN_FILE_CHAPTER_RE.match(clean) or IN_FILE_PART_RE.match(clean))

def is_structural_chapter_heading(label: str) -> bool:
    clean = normalize_cjk_spacing(heading_test_text(label.strip()))
    if TIMESTAMP_SCENE_RE.match(clean) or ILLUSTRATION_PLACEHOLDER_RE.match(clean):
        return False
    if clean in STANDALONE_NON_PART_SECTIONS or any(clean.startswith(s) for s in STANDALONE_NON_PART_SECTIONS):
        return False
    return bool(IN_FILE_CHAPTER_RE.match(clean) or IN_FILE_PART_RE.match(clean))


BOOK_INVISIBLE_RE = re.compile('[\u200b\u200e\u200f\u202a-\u202e\u2060\u2066-\u2069\ufeff\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')


BOOK_PUA_RE = re.compile('[\ue000-\uf8ff\U000f0000-\U000ffffd\U00100000-\U0010fffd]+')


def _book_kanji(ch):
    o = ord(ch)
    return 0x3400 <= o <= 0x9FFF or 0xF900 <= o <= 0xFAFF or o == 0x3005 or 0x20000 <= o <= 0x323AF


def _book_letter(ch):
    o = ord(ch)
    return 0x3041 <= o <= 0x3096 or 0x30A1 <= o <= 0x30FA or o == 0x30FC or _book_kanji(ch)


def book_private_use(text):
    def one(m):
        run, i, j = m.group(), m.start(), m.end()
        if len(run) > 1:
            return ' '
        if 0xF020 <= ord(run) <= 0xF0FF or ord(run) > 0xFFFF or i == 0 or text[i - 1].isspace():
            return ''
        if _book_kanji(text[i - 1]) or (j < len(text) and _book_kanji(text[j])):
            return '〓'
        if j < len(text) and _book_letter(text[i - 1]) and _book_letter(text[j]):
            return '〓'
        return ''
    if not BOOK_PUA_RE.search(text):
        return text
    text = ''.join(chr(ord(c) - 0x100000) if 0x100020 <= ord(c) <= 0x10007E else c for c in text)
    return BOOK_PUA_RE.sub(one, text).strip()


def _postprocess_sentence(text: str) -> str:
    text = convert_hw_katakana(book_private_use(BOOK_INVISIBLE_RE.sub('', text)))
    for _ in range(10):
        before = text
        text = replace_until_fixed(text, EPUB_STR_REPLACEMENTS)
        for pattern, dst in _RE_REPLACEMENTS:
            text = pattern.sub(dst, text)
        if text == before:
            break
    return text

GENERIC_EXACT_LOWER = {
    'image', 'img', 'figure', 'fig', 'picture', 'photo', 'illustration',
    'イラスト', '写真', '挿絵', 'ロゴ', 'logo', 'icon', 'spacer', 'dummy', 'cover',
    'comic book images', 'page',
}
GENERIC_ALT_LABEL_RE = re.compile(
    r'(?:画像|ロゴ|^(?:中|裏|文字ナシ)?表紙|^(?:第?[0-9０-９一二三四五六七八九十]+[章部][\s　]*)?大?扉|^挿絵|^イラスト|^代替テキスト)[\s　]*[0-9０-９]*$')
GENERIC_ALT_STEM_RE = re.compile(r'^[A-Za-z]{3,}(?:[_\-][A-Za-z]+)*[_\-]?[0-9]+[a-z]?$')

def _alt_core(alt: str) -> str:
    return re.sub(r'^[（(［\[【〔〈《「『\s]+|[）)］\]】〕〉》」』\s]+$', '', alt.strip().lower())


FONT_OBFUSCATION = ("http://www.idpf.org/2008/embedding", "http://ns.adobe.com/pdf/enc#RC")
CONTENT_EXTS = (".xhtml", ".html", ".htm", ".ncx", ".opf")


def drm_locked(path) -> bool:
    try:
        with zipfile.ZipFile(path) as z:
            if "META-INF/encryption.xml" not in z.namelist():
                return False
            root = ET.fromstring(z.read("META-INF/encryption.xml"))
    except (OSError, zipfile.BadZipFile, ET.ParseError, KeyError):
        return False
    for data in root.iter():
        if not data.tag.endswith("}EncryptedData"):
            continue
        method = next((e.get("Algorithm") for e in data.iter() if e.tag.endswith("}EncryptionMethod")), None)
        uris = [e.get("URI") or "" for e in data.iter() if e.tag.endswith("}CipherReference")]
        if method not in FONT_OBFUSCATION and any(unquote(u).lower().endswith(CONTENT_EXTS) for u in uris):
            return True
    return False


def is_generic_alt(alt: str) -> bool:
    if not alt:
        return True
    a = alt.strip()
    a_low = a.lower()
    a_clean = _alt_core(a)
    
    if a_low in GENERIC_EXACT_LOWER or a_clean in GENERIC_EXACT_LOWER:
        return True
        
    if re.match(r'^(?:fig|figure|image|img|photo|page)[\s_\-\.:\d]', a_low):
        return True
        
    if re.search(r'\.(?:png|jpg|jpeg|gif|webp|svg|bmp)$', a_low):
        return True
        
    if len(a) > 30:
        return True

    if GENERIC_ALT_LABEL_RE.search(a_clean) or GENERIC_ALT_STEM_RE.match(a):
        return True

    return False

GAIJI_MARK = '〓'
SPACER_MAX_BYTES = 512
IMG_BLOCK_TAGS = ['p', 'div', 'li', 'td', 'th', 'dt', 'dd', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                  'blockquote', 'figcaption']

def _has_text_before(img) -> bool:
    block = img.find_parent(IMG_BLOCK_TAGS)
    if block is None:
        return False
    for el in img.previous_elements:
        if el is block:
            return False
        if isinstance(el, str) and el.strip():
            return True
    return False

def clean_html_ruby_and_tags(soup, image_size=None):
    for tag in soup.find_all(['script', 'style', 'svg', 'audio', 'video']):
        tag.decompose()

    for img in soup.find_all('img'):
        alt = img.get('alt', '').strip()
        if alt and GENERIC_ALT_LABEL_RE.search(_alt_core(alt)):
            img.decompose()
            continue
        if is_generic_alt(alt):
            alt = ''

        if alt:
            img.replace_with(alt)
            continue
        size = image_size(img.get('src', '')) if image_size else None
        if size is not None and size <= SPACER_MAX_BYTES:
            img.decompose()
        elif img.find_parent('ruby') or _has_text_before(img):
            img.replace_with(GAIJI_MARK)
        else:
            img.decompose()

    for ruby in soup.find_all('ruby'):
        rt_tags = ruby.find_all('rt')
        furi_text = ''.join(rt.get_text(strip=True) for rt in rt_tags)
        for rt in rt_tags:
            rt.decompose()
        for rp in ruby.find_all('rp'):
            rp.decompose()
        base_text = ruby.get_text(strip=True)
        if furi_text and base_text:
            ruby.replace_with(f'｜{base_text}({furi_text})')
        elif base_text:
            ruby.replace_with(base_text)
        elif furi_text:
            ruby.replace_with(furi_text)
        else:
            ruby.decompose()


KINDLE_TEMPLATE_MARK = 'kindle_inner'
TEMPLATE_PLACEHOLDERS = {'${TITLE}'}


def drop_template_placeholders(soup, raw_xhtml: str):
    if isinstance(raw_xhtml, bytes):
        raw_xhtml = raw_xhtml.decode('ascii', errors='replace')
    if KINDLE_TEMPLATE_MARK not in raw_xhtml or '${' not in raw_xhtml:
        return
    for el in soup.find_all(string=lambda s: s.strip() in TEMPLATE_PLACEHOLDERS):
        el.extract()


_BODY_BLOCK_TAGS = {
    'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'div', 'ul', 'ol', 'blockquote',
    'li', 'dt', 'dd', 'table', 'tr', 'td', 'th', 'section', 'article', 'aside',
    'header', 'footer', 'nav', 'figure', 'figcaption', 'pre', 'hr', 'form',
    'fieldset', 'address', 'main',
}


_HEADS = ('p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6')
_LEAF_TAGS = ('li', 'dt', 'dd', 'blockquote', 'div')
_NESTED_TAGS = ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'div', 'ul', 'ol', 'blockquote', 'li', 'dt', 'dd']
_SECTION_TAGS = ('article', 'section', 'aside')


def _page_block_test(read_tables, skip_tables=(), sections=True):
    leaf = _LEAF_TAGS + (_SECTION_TAGS if sections else ())
    nested = _NESTED_TAGS + (list(_SECTION_TAGS) if sections else [])

    def block(tag):
        return tag.name in _HEADS or (tag.name in leaf and not tag.find(nested))

    def test(tag):
        if tag.name in ('td', 'th'):
            if not read_tables or tag.find(nested + ['table']) or not JAPANESE_TEXT_RE.search(tag.get_text()):
                return False
            table = tag.find_parent('table')
            if table is not None and id(table) in skip_tables:
                return False
            return not any(block(p) for p in tag.parents)
        return block(tag)
    return test


def _wrap_body_inline_runs(soup):
    body = soup.body
    if not body:
        return False
    for sp in list(body.find_all(['span', 'font'])):
        if sp.find('br') is not None:
            sp.unwrap()
    changed = False
    for container in [body] + list(body.find_all(('div',) + _SECTION_TAGS)):
        if container is not body and not container.find(_BODY_BLOCK_TAGS):
            continue
        has_inline_text = any(
            (isinstance(ch, NavigableString) and not isinstance(ch, (Comment, Declaration)) and str(ch).strip())
            or (getattr(ch, 'name', None) not in _BODY_BLOCK_TAGS and getattr(ch, 'name', None) != 'br'
                and hasattr(ch, 'get_text') and ch.get_text(strip=True))
            for ch in container.children
        )
        if not has_inline_text:
            continue
        runs, cur = [], []
        for ch in list(container.children):
            if getattr(ch, 'name', None) in _BODY_BLOCK_TAGS or getattr(ch, 'name', None) == 'br':
                if cur:
                    runs.append((ch, cur))
                    cur = []
            else:
                cur.append(ch)
        if cur:
            runs.append((None, cur))
        for anchor, nodes in runs:
            txt = ''.join(n.get_text() if hasattr(n, 'get_text') else str(n) for n in nodes).strip()
            if not txt:
                continue
            p_tag = soup.new_tag('p')
            if anchor is not None:
                anchor.insert_before(p_tag)
            else:
                container.append(p_tag)
            for n in nodes:
                p_tag.append(n.extract())
            changed = True
    return changed


SPEECH_END = '。！？!?…‥―─'
SPACES_RE = re.compile('[ ' + chr(0x3000) + ']*')


def sentence_pieces(text: str):
    sentences = []
    buf = []
    quote_depth = 0
    speech = False
    bracket_map = {'「': '」', '『': '』', '（': '）', '(': ')'}
    reverse_map = {v: k for k, v in bracket_map.items()}

    def flush(next_speech):
        nonlocal buf, speech
        s = ''.join(buf).strip()
        if s:
            sentences.append((s, speech))
        buf, speech = [], next_speech

    for i, char in enumerate(text):
        buf.append(char)
        if char in bracket_map:
            quote_depth += 1
        elif char in reverse_map:
            if quote_depth > 0:
                quote_depth -= 1
                if quote_depth == 0 and char in '」』' and len(buf) > 1 and buf[-2] in SPEECH_END:
                    j = SPACES_RE.match(text, i + 1).end()
                    if j < len(text) and text[j] in '「『':
                        flush(True)
        elif char in ('。', '！', '？', '!', '?') and quote_depth == 0:
            flush(False)

    flush(False)
    return sentences


def split_japanese_sentences(text: str):
    return [s for s, _ in sentence_pieces(text)]

def _edge_space(run: str) -> str:
    if IDEOGRAPHIC_SPACE in run:
        return IDEOGRAPHIC_SPACE * run.count(IDEOGRAPHIC_SPACE)
    if not run or '\n' in run or '\r' in run:
        return ''
    return ' ' if (' ' in run or '\t' in run) else ''


def _spaced(text: str) -> str:
    core = text.strip()
    if not core:
        return _edge_space(text)
    return _edge_space(text[:len(text) - len(text.lstrip())]) + core + _edge_space(text[len(text.rstrip()):])


def _spaced_join(pieces) -> str:
    out = ''
    for p in pieces:
        if out.endswith(' ') and p.startswith(' '):
            p = p[1:]
        out += p
    return out.strip()


IDEOGRAPHIC_SPACE = chr(0x3000)


def block_text_spaced(block) -> str:
    return _spaced_join(_spaced(el) for el in block.descendants if type(el) in (NavigableString, CData))


def _br_segments(block):
    segs, spaced = [[]], [[]]
    for el in block.descendants:
        if getattr(el, 'name', None) == 'br':
            if el.find_parent('a') is None:
                segs.append([])
                spaced.append([])
        elif type(el) in (NavigableString, CData):
            spaced[-1].append(_spaced(el))
            t = el.strip()
            if t:
                segs[-1].append((t, el.find_parent('a', href=True) is not None))
    return [g for g in segs if g], [_spaced_join(s) for g, s in zip(segs, spaced) if g]


def _is_link_list(segs) -> bool:
    links = sum(1 for g in segs if all(inside for _, inside in g))
    return links >= 3 and links * 2 >= len(segs)


CODE_LINE_START_RE = re.compile(
    r'^\s*(?:#include\b|(?:int|void|double|float|char|bool|string|vector|auto|const|static|constexpr|'
    r'namespace|class|template)\b|(?:std::)?(?:cout|cin)\b)')
CODE_ASCII_SHARE = 0.6
INDEX_MIN_ITEMS = 20
INDEX_MAX_ITEM = 40
INDEX_MAX_MEAN = 16
INDEX_PUNCT_RE = re.compile(r'[。！？!?、,;{}]')
KANA_HEADING_RE = re.compile(r'[ぁ-ゖァ-ヺ](?:[\s　]+[ぁ-ゖァ-ヺ]){0,3}')


def has_kana_heading(soup) -> bool:
    return any(KANA_HEADING_RE.fullmatch(h.get_text(' ', strip=True))
               for h in soup.find_all(('h1', 'h2', 'h3', 'h4', 'h5', 'h6')))


def _code_block(texts) -> bool:
    joined = '\n'.join(texts)
    return (any(CODE_LINE_START_RE.match(t) for t in texts)
            and sum(ord(c) < 128 for c in joined) >= CODE_ASCII_SHARE * len(joined))


def _code_line_ends(prev: str, before: str) -> bool:
    if not (prev.endswith((';', '{', '}')) or prev.startswith('#') or '//' in prev):
        return False
    if '/*' in before or '*/' in before:
        return False
    if '//' in prev:
        before = before[:before.rfind('//')]
    return not (len(re.findall(r'(?<!\\)"', before)) % 2 or len(re.findall(r"(?<!\\)'", before)) % 2)


def _index_block(texts) -> bool:
    return (len(texts) >= INDEX_MIN_ITEMS and max(map(len, texts)) <= INDEX_MAX_ITEM
            and sum(map(len, texts)) <= INDEX_MAX_MEAN * len(texts)
            and not any(INDEX_PUNCT_RE.search(t) for t in texts))


def _br_lines(block, block_text: str, kana_index_page: bool = False):
    spaced_text = block_text_spaced(block)
    if block.find('br') is None:
        return [spaced_text]
    segs, spaced = _br_segments(block)
    if len(segs) < 2:
        return [spaced_text]
    texts = [''.join(t for t, _ in g) for g in segs]
    contents = _is_link_list(segs)
    code = _code_block(texts)
    index = kana_index_page and _index_block(texts)
    pieces, depth, before = [spaced[0]], 0, ''
    for prev, nxt, nxt_spaced in zip(texts, texts[1:], spaced[1:]):
        before += prev
        for ch in prev:
            if ch in '「『（(':
                depth += 1
            elif ch in '」』）)' and depth:
                depth -= 1
        if (contents or (depth == 0 and prev[-1] in '」』' and nxt[0] in '「『')
                or (depth == 0 and code and _code_line_ends(prev.strip(), before))
                or (depth == 0 and index)):
            pieces.append(nxt_spaced)
        else:
            pieces[-1] += nxt_spaced
    return pieces if ''.join(texts) == block_text else [spaced_text]


def get_clean_text_for_mecab(line: str) -> str:
    return BOOK_RUBY_RE.sub(r'\1\2', line)

def analyze_with_sudachi(clean_text: str):
    return analyze_tokens(clean_text)[:2]

def analyze_tokens(clean_text: str):
    base_forms = []
    readings = []
    words = [w for piece in _sudachi_pieces(clean_text) for w in get_tokenizer().tokenize(piece, mode)]
    for word in words:
        base_forms.append(word.normalized_form())
        kana = word.reading_form()
        if kana:
            readings.append(katakana_to_hiragana(kana))
        else:
            readings.append(word.surface())
    return " ".join(base_forms), " ".join(readings), token_lengths_blob(w.surface() for w in words)

def compute_file_hash(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


VOLUME_LABEL_RE = re.compile(r'^(?:(?:第\s*)?[0-9０-９一二三四五六七八九十百千]+\s*[部巻篇]|上巻|中巻|下巻|前篇|後篇)(?:\s|$)')
NAMED_VOLUME_RE = re.compile(r'^(?:上巻|中巻|下巻|前篇|後篇)(?:\s|$)')


def _names_volumes(labels, parent='', book_title='') -> bool:
    name = re.sub(r'[\s　]+', '', strip_ruby_markup(parent or ''))
    title = re.sub(r'[\s　]+', '', strip_ruby_markup(book_title or ''))
    if name in STANDALONE_NON_PART_SECTIONS or name.upper() in GENERIC_TOC_NAMES:
        return False
    if len(name) >= 2 and title.startswith(name):
        return False
    volumes = [v for v in (strip_ruby_markup(l.strip()) for l in labels) if VOLUME_LABEL_RE.match(v)]
    return any(NAMED_VOLUME_RE.match(v) for v in volumes) or len(volumes) >= 2


def _parse_nav_ol(ol, nav_dir, toc_map, depth=0, parent_label=None, has_any_main=True, last_main_label=None, work=False,
                  book_title=''):
    effective_parent = None
    for li in ol.find_all(['li', 'ol'], recursive=False):
        if li.name == 'ol':
            if effective_parent:
                _parse_nav_ol(li, nav_dir, toc_map, depth + 1, effective_parent, has_any_main, last_main_label,
                              _names_volumes((x.get_text() for x in li.find_all('a', recursive=True)),
                                             effective_parent, book_title), book_title)
            continue
        effective_parent = None
        a = li.find('a', recursive=False)
        if not a:
            continue
        raw_text = a.get_text()
        has_leading_space = raw_text.startswith((' ', '　', '\t'))
        href_raw = a.get('href', '').split('#')[0]
        lbl = clean_heading_label(raw_text.strip())
        if not href_raw or not lbl:
            continue
        res_h = posixpath.normpath(posixpath.join(nav_dir, href_raw))

        if TIMESTAMP_SCENE_RE.match(lbl) or ILLUSTRATION_PLACEHOLDER_RE.match(lbl):
            target = parent_label or last_main_label
            if target and res_h not in toc_map:
                toc_map[res_h] = target
            continue

        if depth == 0:
            is_structural = is_structural_chapter_heading(lbl)
            if has_leading_space and last_main_label and last_main_label.upper() not in GENERIC_TOC_NAMES and last_main_label not in STANDALONE_NON_PART_SECTIONS:
                merged = format_merged_chapter_name(last_main_label, lbl)
                if res_h not in toc_map:
                    toc_map[res_h] = merged
                effective_parent = last_main_label
            else:
                is_sub = has_any_main and not is_structural and SUB_NUMBERING_RE.match(lbl)
                if is_sub and last_main_label:
                    merged = format_merged_chapter_name(last_main_label, lbl)
                    if res_h not in toc_map:
                        toc_map[res_h] = merged
                    effective_parent = last_main_label
                else:
                    if res_h not in toc_map or (is_structural and not is_structural_chapter_heading(toc_map.get(res_h, ''))):
                        toc_map[res_h] = lbl
                    effective_parent = lbl
                    if is_structural or (not is_sub and not has_leading_space and lbl.upper() not in GENERIC_TOC_NAMES and lbl not in STANDALONE_NON_PART_SECTIONS):
                        last_main_label = lbl
        else:
            if parent_label and ((has_any_main and is_structural_chapter_heading(parent_label)) or work):
                merged = format_merged_chapter_name(parent_label, lbl)
                if res_h not in toc_map:
                    toc_map[res_h] = merged
                effective_parent = parent_label
            else:
                if res_h not in toc_map:
                    toc_map[res_h] = lbl
                effective_parent = lbl

        nested_ol = li.find('ol', recursive=False)
        if nested_ol:
            _parse_nav_ol(nested_ol, nav_dir, toc_map, depth + 1, effective_parent, has_any_main, last_main_label,
                          _names_volumes((x.get_text() for x in nested_ol.find_all('a', recursive=True)),
                                         effective_parent, book_title), book_title)


def _parse_ncx_navpoints(navpoints, ncx_dir, toc_map, depth=0, parent_label=None, has_any_main=True, work=False,
                         book_title=''):
    for np in navpoints:
        navlabel = np.find('navlabel')
        text_el = navlabel.find('text') if navlabel else np.find('text')
        content_el = np.find('content')
        if not text_el or not content_el:
            continue
        lbl = clean_heading_label(text_el.get_text(strip=True))
        src = content_el.get('src', '').split('#')[0]
        if not src or not lbl:
            continue
        res_h = posixpath.normpath(posixpath.join(ncx_dir, src))

        if TIMESTAMP_SCENE_RE.match(lbl) or ILLUSTRATION_PLACEHOLDER_RE.match(lbl):
            if parent_label and res_h not in toc_map:
                toc_map[res_h] = parent_label
            continue

        if depth == 0:
            is_structural = is_structural_chapter_heading(lbl)
            if res_h not in toc_map or (is_structural and not is_structural_chapter_heading(toc_map.get(res_h, ''))):
                toc_map[res_h] = lbl
            effective_parent = lbl
        else:
            if parent_label and ((has_any_main and is_structural_chapter_heading(parent_label)) or work):
                merged = format_merged_chapter_name(parent_label, lbl)
                if res_h not in toc_map:
                    toc_map[res_h] = merged
                effective_parent = parent_label
            else:
                if res_h not in toc_map:
                    toc_map[res_h] = lbl
                effective_parent = lbl

        child_navpoints = np.find_all('navpoint', recursive=False)
        if child_navpoints:
            _parse_ncx_navpoints(child_navpoints, ncx_dir, toc_map, depth + 1, effective_parent, has_any_main,
                                 _names_volumes((t.get_text() for c in child_navpoints for t in [c.find('text')] if t),
                                                effective_parent, book_title), book_title)


def _apply_split_file_carry(toc_map, zf_namelist):
    SPLIT_RE = re.compile(r'^(.+?)_split_\d+(\.[^.]+)$')
    stem_to_label = {}
    for path, label in toc_map.items():
        stem_to_label[path] = label

    for f in zf_namelist:
        m = SPLIT_RE.match(posixpath.basename(f))
        if not m:
            continue
        stem_file = posixpath.join(posixpath.dirname(f), m.group(1) + m.group(2))
        stem_norm = posixpath.normpath(stem_file)
        if f not in toc_map and stem_norm in toc_map:
            toc_map[f] = toc_map[stem_norm]
        elif f not in toc_map and stem_file in toc_map:
            toc_map[f] = toc_map[stem_file]


def _parse_mokuji_page(zf, mokuji_path, mokuji_dir, toc_map, allowed_targets=None):
    try:
        raw = zf.read(mokuji_path)
        soup = parse_page(raw)
        for a in soup.find_all('a', href=True):
            href_raw = a.get('href', '').split('#')[0]
            if allowed_targets is not None:
                try:
                    target_url = urlsplit(a.get('href', ''))
                except ValueError:
                    continue
                if target_url.scheme or target_url.netloc or target_url.query:
                    continue
                href_raw = unquote(target_url.path)
            if not href_raw:
                continue
            lbl = clean_heading_label(a.get_text(strip=True))
            if not lbl or len(lbl) < 2 or len(lbl) > 50:
                continue
            if TIMESTAMP_SCENE_RE.match(lbl) or ILLUSTRATION_PLACEHOLDER_RE.match(lbl):
                continue
            if re.match(r'^[\d\s　ivxlcdmIVXLCDM]+$', lbl):
                continue
            res_h = posixpath.normpath(posixpath.join(mokuji_dir, href_raw))
            if allowed_targets is not None and res_h not in allowed_targets:
                continue
            if res_h not in toc_map:
                toc_map[res_h] = lbl
                if allowed_targets is not None:
                    continue
                stem_base = posixpath.basename(res_h)
                stem_dir = posixpath.dirname(res_h)
                stem_no_ext = posixpath.splitext(stem_base)[0]
                for candidate in [f for f in zf.namelist()
                                   if posixpath.dirname(f) == stem_dir
                                   and posixpath.basename(f).startswith(stem_no_ext + '_split_')]:
                    if candidate not in toc_map:
                        toc_map[candidate] = lbl
    except Exception as e:
        say(f"Error parsing 目次 page {mokuji_path}: {e}")


def _supplement_spine_contents(zf, opf, content_dir, toc_map):
    manifest = {item.get('id'): item.get('href', '')
                for item in opf.findall('.//{*}manifest/{*}item')}
    spine_paths = [posixpath.normpath(posixpath.join(content_dir, manifest.get(ref.get('idref'), '')))
                   for ref in opf.findall('.//{*}spine/{*}itemref')
                   if manifest.get(ref.get('idref'))]
    allowed = set(spine_paths)
    labels = {'目次', 'もくじ', '目次ページ', 'contents', 'table of contents'}
    for path in spine_paths:
        if clean_heading_label(toc_map.get(path, '')).lower() in labels:
            continue
        if not path.lower().endswith(('.html', '.xhtml', '.htm')):
            continue
        try:
            page_bytes = zf.read(path)
            raw = _page_markup(page_bytes)[0]
        except (zipfile.BadZipFile, EOFError, OSError, RuntimeError, KeyError):
            continue
        if not re.search(r'目次|もくじ|contents|epub:type\s*=\s*["\x27]toc', raw, re.I):
            continue
        soup = parse_page(page_bytes)
        body = soup.body
        if body is None:
            continue
        first = next((s.strip() for s in body.stripped_strings if s.strip()), '')
        semantic = body.find('nav', attrs={'epub:type': 'toc'}) is not None
        if clean_heading_label(first).lower() not in labels and not semantic:
            continue
        links = soup.find_all('a', href=True)
        local_links = []
        for a in links:
            try:
                ref = urlsplit(a['href'])
            except ValueError:
                continue
            if (a.get_text(strip=True) and ref.path and not (ref.scheme or ref.netloc or ref.query)
                    and posixpath.normpath(posixpath.join(posixpath.dirname(path), unquote(ref.path))) in allowed):
                local_links.append(a)
        if len(local_links) < 3:
            continue
        _parse_mokuji_page(zf, path, posixpath.dirname(path), toc_map, allowed_targets=allowed)


def extract_toc_map(zf, opf, content_dir):
    toc_map = {}

    if opf is None:
        nav_candidates = (
            [n for n in zf.namelist() if n.endswith(('navigation-documents.xhtml', 'nav.xhtml'))]
            or [n for n in zf.namelist() if n.endswith(('toc.xhtml', 'toc.ncx'))]
        )
        if nav_candidates:
            nav_full = nav_candidates[0]
            nav_dir = posixpath.dirname(nav_full)
            try:
                soup = parse_page(zf.read(nav_full))
                nav_tag = (soup.find('nav', attrs={'epub:type': 'toc'})
                           or soup.find('nav', id='toc')
                           or soup.find('nav'))
                if nav_tag:
                    root_ol = nav_tag.find('ol')
                    if root_ol:
                        all_labels = [a.get_text(strip=True) for a in nav_tag.find_all('a')]
                        has_any_main = any(is_structural_chapter_heading(l) for l in all_labels)
                        _parse_nav_ol(root_ol, nav_dir, toc_map, depth=0, parent_label=None, has_any_main=has_any_main)
            except Exception as e:
                say(f"Error parsing direct Nav TOC: {e}")
        _apply_split_file_carry(toc_map, zf.namelist())
        return toc_map

    manifest = {item.attrib['id']: item.attrib for item in opf.findall('.//{*}manifest/{*}item')}
    title_elem = opf.find('.//{*}title')
    book_title = (title_elem.text or '') if title_elem is not None else ''

    nav_item = next((item for item in manifest.values()
                     if 'properties' in item and 'nav' in item['properties'].split()), None)
    if nav_item:
        nav_href = nav_item['href']
        nav_full = posixpath.normpath(posixpath.join(content_dir, nav_href)) if content_dir else nav_href
        nav_dir = posixpath.dirname(nav_full)
        try:
            raw_nav = zf.read(nav_full)
            soup = parse_page(raw_nav)
            nav_tag = (soup.find('nav', attrs={'epub:type': 'toc'})
                       or soup.find('nav', id='toc')
                       or soup.find('nav'))
            if nav_tag:
                root_ol = nav_tag.find('ol')
                if root_ol:
                    all_labels = [a.get_text(strip=True) for a in nav_tag.find_all('a')]
                    has_any_main = any(is_structural_chapter_heading(l) for l in all_labels)
                    _parse_nav_ol(root_ol, nav_dir, toc_map, depth=0, parent_label=None, has_any_main=has_any_main,
                                  book_title=book_title)
        except Exception as e:
            say(f"Error parsing Nav TOC {nav_full}: {e}")

    if not toc_map:
        ncx_item = next((item for item in manifest.values()
                         if item.get('media-type') == 'application/x-dtbncx+xml'
                         or item.get('id') == 'ncx'), None)
        if ncx_item:
            ncx_href = ncx_item['href']
            ncx_full = posixpath.normpath(posixpath.join(content_dir, ncx_href)) if content_dir else ncx_href
            ncx_dir = posixpath.dirname(ncx_full)
            try:
                raw_ncx = zf.read(ncx_full)
                soup = parse_page(raw_ncx)
                nav_map = soup.find('navmap')
                if nav_map:
                    top_navpoints = nav_map.find_all('navpoint', recursive=False)
                    all_labels = [np.find('text').get_text(strip=True) for np in nav_map.find_all('navpoint') if np.find('text')]
                    has_any_main = any(is_structural_chapter_heading(l) for l in all_labels)
                    _parse_ncx_navpoints(top_navpoints, ncx_dir, toc_map, depth=0, parent_label=None, has_any_main=has_any_main,
                                         book_title=book_title)
            except Exception as e:
                say(f"Error parsing NCX TOC {ncx_full}: {e}")

    _apply_split_file_carry(toc_map, zf.namelist())

    mokuji_path = None
    mokuji_dir = ""
    for path, label in toc_map.items():
        if label in ('目次', '目次ページ', 'Contents', 'Table of Contents'):
            mokuji_path = path
            mokuji_dir = posixpath.dirname(path)
            break
    if mokuji_path:
        try:
            candidate_paths = [mokuji_path]
            if content_dir and not mokuji_path.startswith(content_dir):
                candidate_paths.append(posixpath.normpath(posixpath.join(content_dir, mokuji_path)))
            for cp in candidate_paths:
                if cp in zf.namelist():
                    _parse_mokuji_page(zf, cp, mokuji_dir or posixpath.dirname(cp), toc_map)
                    break
        except Exception as e:
            say(f"Error in 目次 supplementary parse: {e}")

    _supplement_spine_contents(zf, opf, content_dir, toc_map)
    return toc_map


INDEX_FOLDER_RE = re.compile(r'索引|\bindex\b', re.I)


def _toc_chains(zf, opf, content_dir):
    names = set(zf.namelist())
    if opf is not None:
        items = [i.attrib for i in opf.findall('.//{*}manifest/{*}item')]
        nav = next((i for i in items if 'nav' in i.get('properties', '').split()), None)
        ncx = next((i for i in items if i.get('media-type') == 'application/x-dtbncx+xml'), None)
        nav_path = posixpath.normpath(posixpath.join(content_dir, unquote(nav['href']))) if nav else None
        ncx_path = posixpath.normpath(posixpath.join(content_dir, unquote(ncx['href']))) if ncx else None
    else:
        found = ([n for n in names if n.endswith(('navigation-documents.xhtml', 'nav.xhtml'))]
                 or [n for n in names if n.endswith(('toc.xhtml', 'toc.ncx'))])
        nav_path = found[0] if found and not found[0].endswith('.ncx') else None
        ncx_path = found[0] if found and found[0].endswith('.ncx') else None

    def target(href, directory):
        return posixpath.normpath(posixpath.join(directory, unquote(href.split('#')[0])))

    chains = {}
    if nav_path in names:
        soup = parse_page(zf.read(nav_path))
        toc = soup.find('nav', attrs={'epub:type': 'toc'}) or soup.find('nav')
        ol = toc.find('ol', recursive=False) if toc else None

        def visit(ol, chain):
            previous = None
            for node in ol.find_all(['li', 'ol'], recursive=False):
                if node.name == 'ol':
                    if previous:
                        visit(node, previous)
                    continue
                a = node.find('a', recursive=False)
                previous = None
                if a is None or not a.get('href') or not a.get_text(strip=True):
                    continue
                entry = (a.get_text(strip=True), target(a['href'], posixpath.dirname(nav_path)))
                current = previous = chain + [entry]
                chains.setdefault(entry[1], current)
                sub = node.find('ol', recursive=False)
                if sub:
                    visit(sub, current)
        if ol:
            visit(ol, [])
    if not chains and ncx_path in names:
        nav_map = parse_page(zf.read(ncx_path)).find('navmap')

        def visit_ncx(nodes, chain):
            for node in nodes:
                label = node.find('navlabel', recursive=False)
                content = node.find('content', recursive=False)
                if not label or not content:
                    continue
                entry = (label.get_text(strip=True), target(content.get('src', ''), posixpath.dirname(ncx_path)))
                current = chain + [entry]
                chains.setdefault(entry[1], current)
                visit_ncx(node.find_all('navpoint', recursive=False), current)
        if nav_map:
            visit_ncx(nav_map.find_all('navpoint', recursive=False), [])
    return chains


def index_folders(zf, opf, content_dir, spine_files, title, chapters):
    chains = _toc_chains(zf, opf, content_dir)
    if not chains:
        return [None] * len(chapters)
    pages = [posixpath.normpath(posixpath.join(content_dir, h)) if content_dir else posixpath.normpath(h)
             for h in spine_files]
    title_key = re.sub(r'\s+', '', title)
    keys, labels = [], {}
    for ch in chapters:
        first, last = ch['spine']
        page_chains = [chains.get(pages[j], []) for j in range(first, min(last + 1, len(pages)))]
        chain = page_chains[0] if page_chains else []
        common = []
        for level in range(min((len(c) for c in page_chains), default=0)):
            if all(c[level] == chain[level] for c in page_chains):
                common.append(chain[level])
            else:
                break
        parents = common[:-1] if common and common == chain else common
        node = next((p for p in parents if re.sub(r'\s+', '', p[0]) != title_key
                     and p[0].upper() not in GENERIC_TOC_NAMES and INDEX_FOLDER_RE.search(p[0])), None)
        keys.append(node[1] if node else None)
        if node:
            labels[node[1]] = node[0]
    counts = collections.Counter(k for k in keys if k is not None)
    return [labels[k] if k is not None and counts[k] >= 2 else None for k in keys]


COUNTER_LABEL_RE = re.compile(r'^(?:(?:第|その)?[\s　]*[(（]?[0-9０-９一二三四五六七八九十百千]+[)）]?|[ぁ-ゖァ-ヺ]{1,2})[\s　]*$')
EPISODE_LABEL_RE = re.compile(r'^第[\s　]*[0-9０-９一二三四五六七八九十百千]+[\s　]*[話回]')


def shared_name_parents(zf, opf, content_dir, spine_files, title, chapters):
    names = [ch['chapter_title'] for ch in chapters]
    shared = {n for n, k in collections.Counter(names).items() if k >= 2}
    if not shared:
        return names
    chains = _toc_chains(zf, opf, content_dir)
    if not chains:
        return names
    pages = [posixpath.normpath(posixpath.join(content_dir, h)) if content_dir else posixpath.normpath(h)
             for h in spine_files]
    title_key = re.sub(r'\s+', '', title)
    out = []
    for ch, name in zip(chapters, names):
        first = ch['spine'][0]
        chain = chains.get(pages[first], []) if name in shared and first < len(pages) else []
        leaf = re.sub(r'\s+', '', name.split('｜')[-1])
        parent = None
        for label, _ in reversed(chain):
            key = re.sub(r'\s+', '', label)
            if (key == leaf or key == title_key or label.upper() in GENERIC_TOC_NAMES
                    or COUNTER_LABEL_RE.match(label) or key in re.sub(r'\s+', '', name)
                    or CHAPTER_LEVEL_RE.match(normalize_cjk_spacing(label)) or EPISODE_LABEL_RE.match(label)):
                continue
            parent = label
            break
        out.append(format_merged_chapter_name(parent, name) if parent else name)
    told_apart = {n for n in shared
                  if len({new for old, new in zip(names, out) if old == n}) > 1}
    return [new if old in told_apart else old for old, new in zip(names, out)]


def is_tautological_chapter(ch_title: str, sentences: list) -> bool:
    if len(sentences) == 0:
        return True
    if len(sentences) == 1:
        s = sentences[0]
        s_clean, ch_clean = _name_key(s), _name_key(ch_title)
        sub_ch_clean = ch_clean.split('｜')[-1]
        if s_clean == ch_clean or s_clean == sub_ch_clean or ch_clean.endswith(s_clean) or s_clean.endswith(ch_clean):
            return True
    return False


CHAPTER_LEVEL_RE = re.compile(
    r'^(?:(?:第\s*)?[0-9０-９一二三四五六七八九十百千]+\s*章|Chapter\s*\S+|'
    r'序章|終章|プロローグ|エピローグ|間章|幕間)', re.IGNORECASE)
DIVIDER_MAX_SENTENCES = 5


SECTION_LEVEL_RE = re.compile(r'^(?:第\s*)?[0-9０-９一二三四五六七八九十百千]+\s*節')


def _cut_sections(label: str) -> str:
    segs = (label or '').split('｜')
    cut = next((i for i, s in enumerate(segs) if i and SECTION_LEVEL_RE.match(normalize_cjk_spacing(s))), len(segs))
    return '｜'.join(segs[:cut])


def _without_chapter(label: str) -> str:
    segs = (label or '').split('｜')
    while len(segs) > 1 and CHAPTER_LEVEL_RE.match(normalize_cjk_spacing(segs[-1])):
        segs.pop()
    return '｜'.join(segs) if segs != [''] else ''


def _from_last_chapter(label: str) -> str:
    segs = label.split('｜')
    last = max((i for i, s in enumerate(segs) if CHAPTER_LEVEL_RE.match(normalize_cjk_spacing(s))), default=0)
    return '｜'.join(segs[last:])

SEQ_BOOK_MIN = 1000
SEQ_SHARE = 0.5
SEQ_MIN_GAP = 10
SEQ_MIN_RUN = 4
BACK_MATTER = {'本著作物について', '著者略歴', '著者紹介', '著者プロフィール', '底本', 'クレジット', '電子版奥付',
               '奥付・著者紹介', '著者・訳者紹介', '訳者略歴'}
NOTES_LABEL_RE = re.compile(r'^(?:訳|原|脚|補|後)?[註注](?:釈|記)?$|^notes?$', re.IGNORECASE)
_SEQ_NUM = (r'(?P<num>[0-9０-９]{1,3}|[〇一二三四五六七八九十百廿卅]{1,5}|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫ]'
            r'|(?=[IVX])X{0,3}(?:IX|IV|V?I{0,3}))')
_SEQ_LINE_RE = re.compile(r'^(?P<pre>その|§|[◇◆■□●○◎★☆]|[【［〈〔]第?|第)?' + _SEQ_NUM + r'(?P<rest>.*)$')
_SEQ_SPECIAL_RE = re.compile(r'^(?P<pre>§|[◇◆■□●○◎★☆]|[【［〈〔])?(?:序章|終章|プロローグ|エピローグ|幕間|間章)')
_KANJI_DIGIT = {'〇': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}
_ROMAN = {'Ⅰ': 1, 'Ⅱ': 2, 'Ⅲ': 3, 'Ⅳ': 4, 'Ⅴ': 5, 'Ⅵ': 6, 'Ⅶ': 7, 'Ⅷ': 8, 'Ⅸ': 9, 'Ⅹ': 10, 'Ⅺ': 11, 'Ⅻ': 12}
_SEQ_UNITS = set('年月日時分秒歳才人個本枚回度番号階位円万千百十名点巻代条項話章%％')


def _seq_number(s):
    if s[0] in '0123456789０１２３４５６７８９':
        return int(unicodedata.normalize('NFKC', s))
    if s in _ROMAN:
        return _ROMAN[s]
    if s[0] in 'IVX':
        vals = {'I': 1, 'V': 5, 'X': 10}
        n = sum(vals[c] for c in s)
        return n - 2 * sum(vals[a] for a, b in zip(s, s[1:]) if vals[a] < vals[b])
    if all(c in _KANJI_DIGIT for c in s):
        return int(''.join(str(_KANJI_DIGIT[c]) for c in s))
    total, cur = 0, 0
    for c in s:
        if c in _KANJI_DIGIT:
            cur = _KANJI_DIGIT[c]
        elif c in '十百':
            total += (cur or 1) * (10 if c == '十' else 100)
            cur = 0
        else:
            total += 20 if c == '廿' else 30
            cur = 0
    return total + cur


def _seq_mark(line):
    text = heading_test_text(line.strip())
    if not text or len(text) > 40 or any(c in text for c in '。！？!?'):
        return None
    m = _SEQ_LINE_RE.match(text)
    if m:
        pre, num, rest = m.group('pre') or '', m.group('num'), m.group('rest')
        kind = 'a' if num[0] in '0123456789０１２３４５６７８９' else ('r' if num[0] in 'ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫIVX' else 'k')
        if not rest:
            shape = ''
        elif rest[0] in '章話回幕節':
            shape = rest[0]
        elif rest[0] in ' 　':
            shape = ' '
        elif rest[0] in '.．':
            shape = '.'
        elif rest[0] in '、，,':
            shape = '、'
        elif rest[0] in ':：':
            shape = ':'
        elif rest[0] in '／/':
            shape = '／'
        elif kind == 'a' and rest[0] not in _SEQ_UNITS and unicodedata.category(rest[0]) == 'Lo':
            shape = ' '
        else:
            return None
        if pre[:1] in ('【', '［', '〈', '〔', '第') and shape not in ('章', '話', '回', '幕', '節'):
            return None
        return (pre[:1], kind, shape), _seq_number(num)
    m = _SEQ_SPECIAL_RE.match(text)
    if m:
        return ((m.group('pre') or '')[:1], None, None), None
    return None


def glued_lines(chapter) -> int:
    return len(chapter['sentences']) - len(chapter.get('br_at', ()))


def split_counting_headings(chapters, title):
    total = sum(glued_lines(c) for c in chapters)
    if total < SEQ_BOOK_MIN or not chapters:
        return chapters
    big_i = max(range(len(chapters)), key=lambda i: glued_lines(chapters[i]))
    big = chapters[big_i]
    if glued_lines(big) < SEQ_SHARE * total or NOTES_LABEL_RE.match(big['chapter_title'].split('｜')[-1].strip()):
        return chapters

    br_at = big.get('br_at', [])
    glued = lambda i: i - bisect.bisect_left(br_at, i)
    br_set = set(br_at)
    marks = collections.defaultdict(list)
    specials = collections.defaultdict(list)
    for i, s in enumerate(big['sentences']):
        if i in br_set:
            continue
        mk = _seq_mark(s)
        if mk:
            fam, n = mk
            if n is None:
                specials[fam[0]].append(i)
            else:
                marks[fam].append((i, n))

    best, best_len = None, 0
    for fam, ms in marks.items():
        chains, cur = [], []
        for i, n in ms:
            if cur and n in (cur[-1][1] + 1, cur[-1][1] + 2) and glued(i) - glued(cur[-1][0]) >= SEQ_MIN_GAP:
                cur.append((i, n))
            elif n in (0, 1) and (not cur or glued(i) - glued(cur[-1][0]) >= SEQ_MIN_GAP):
                if cur:
                    chains.append(cur)
                cur = [(i, n)]
        if cur:
            chains.append(cur)
        longest = max((len(c) for c in chains), default=0)
        if longest >= SEQ_MIN_RUN and longest > best_len:
            best, best_len = (fam, [i for c in chains if len(c) >= 2 for i, _ in c]), longest
    if not best:
        return chapters
    fam, points = best
    points = sorted(set(points) | set(specials.get(fam[0], [])))
    kept = []
    for p in points:
        if not kept or glued(p) - glued(kept[-1]) >= SEQ_MIN_GAP:
            kept.append(p)

    parent = big['chapter_title']
    last = parent.split('｜')[-1].strip()
    pure = lambda t: re.sub(r'[\s　]+', '', strip_ruby_markup(t))

    def matter(c):
        n = c['chapter_title'].split('｜')[-1].strip()
        return (c['origin'] == 'contents' or n.upper() in GENERIC_TOC_NAMES or n in BACK_MATTER
                or n in STANDALONE_NON_PART_SECTIONS or any(n.startswith(x) for x in STANDALONE_NON_PART_SECTIONS)
                or glued_lines(c) < SEQ_MIN_GAP)
    generic = (last.upper() in GENERIC_TOC_NAMES or last in ('本編', '本篇', '本文') or big['origin'] == 'title'
               or re.match(r'(?:プロローグ|エピローグ|序章|終章|序幕|終幕|Prologue|Epilogue)', last, re.I)
               or any(last.startswith(x) for x in STANDALONE_NON_PART_SECTIONS)
               or (pure(last) == pure(title) and all(matter(c) for c in chapters if c is not big)))
    pieces = []
    bounds = ([0] if kept[0] > 0 else []) + kept + [len(big['sentences'])]
    for a, b in zip(bounds, bounds[1:]):
        if a in kept:
            label = clean_heading_label(strip_ruby_markup(big['sentences'][a]))
            name = label if generic else format_merged_chapter_name(parent, label)
            origin = 'sequence'
        else:
            name, origin = parent, big['origin']
        sp = big['sp'][a:b]
        pieces.append({'chapter_title': name, 'sentences': big['sentences'][a:b], 'sp': sp,
                       'spine': [sp[0], sp[-1]], 'origin': origin, 'br_at': [i - a for i in br_at if a <= i < b]})
    return chapters[:big_i] + pieces + chapters[big_i + 1:]


def extract_epub_content(epub_path):
    with zipfile.ZipFile(epub_path, 'r') as zf:
        opf = None
        content_dir = ""
        rootfile_path = ""
        try:
            container_xml = zf.read('META-INF/container.xml')
            container = ET.fromstring(container_xml)
            rootfile_path = container.find('.//{*}rootfile').attrib['full-path']
            opf_data = zf.read(rootfile_path)
            opf = ET.fromstring(opf_data)
            content_dir = posixpath.dirname(rootfile_path)
        except Exception:
            opf_files = [n for n in zf.namelist() if n.endswith('.opf')]
            if opf_files:
                rootfile_path = opf_files[0]
                opf_data = zf.read(rootfile_path)
                opf = ET.fromstring(opf_data)
                content_dir = posixpath.dirname(rootfile_path)

        if opf is not None:
            title_elem = opf.find('.//{*}title')
            raw_title = title_elem.text.strip() if (title_elem is not None and title_elem.text) else ""
            creator_elem = opf.find('.//{*}creator')
            raw_author = creator_elem.text.strip() if (creator_elem is not None and creator_elem.text) else ""
            author, title = book_title_and_author(epub_path, raw_title, raw_author)
            manifest = {item.attrib['id']: item.attrib['href'] for item in opf.findall('.//{*}manifest/{*}item')}
            media_types = {item.attrib['href']: item.attrib.get('media-type', '') for item in opf.findall('.//{*}manifest/{*}item')}
            spine = [itemref.attrib['idref'] for itemref in opf.findall('.//{*}spine/{*}itemref')]
            spine_files = [manifest.get(idref) for idref in spine if manifest.get(idref)]
            not_pages = {h for h in spine_files
                         if media_types.get(h, '') not in HTML_MEDIA_TYPES and not h.lower().endswith(HTML_EXTS)}
        else:
            author, title = book_title_and_author(epub_path, "", "")
            not_pages = set()
            spine_files = [n for n in zf.namelist() if n.endswith(('.xhtml', '.html')) and not n.endswith(('navigation-documents.xhtml', 'nav.xhtml', 'toc.xhtml'))]
            def spine_sort_key(p):
                base = posixpath.basename(p).lower()
                if 'cover' in base: return (0, 0)
                if 'title' in base: return (0, 1)
                if 'caution' in base: return (0, 2)
                m = re.search(r'(\d+)', base)
                if m: return (1, int(m.group(1)))
                if 'atogaki' in base or 'afterword' in base: return (2, 0)
                if 'author' in base: return (2, 1)
                if 'colophon' in base: return (2, 2)
                return (1, 999)
            spine_files.sort(key=spine_sort_key)

        zip_names = set(zf.namelist())
        toc_map = extract_toc_map(zf, opf, content_dir)
        has_authoritative_toc = len(toc_map) > 0
        toc_label_files = {}
        for path, label in toc_map.items():
            for lab in {label, label.split('｜')[-1]}:
                key = re.sub(r'[\s　]+', '', clean_heading_label(lab))
                if key:
                    toc_label_files.setdefault(key, set()).add(posixpath.normpath(path))

        def names_toc_chapter_elsewhere(ch_name, here):
            files = toc_label_files.get(re.sub(r'[\s　]+', '', ch_name))
            return bool(files) and here not in files

        pure_title = re.sub(r'[\s　]+', '', strip_ruby_markup(title))
        pure_author = re.sub(r'[\s　]+', '', strip_ruby_markup(author))

        def _read_spine():
            chapters_list = []
            current_part = ""
            section_ctx = None
            current_chapter_title = title
            current_origin = "title"
            divider, divider_from, divider_parent = None, 0, None
            last_toc_label, last_toc_title = None, None
            pass_excluded = []

            def under_divider(label, name, merged):
                nonlocal divider, divider_from, divider_parent
                norm = normalize_cjk_spacing(label)
                if IN_FILE_PART_RE.match(norm) or label in STANDALONE_NON_PART_SECTIONS or any(label.startswith(x) for x in STANDALONE_NON_PART_SECTIONS):
                    divider = divider_parent = None
                elif CHAPTER_LEVEL_RE.match(norm):
                    divider, divider_from, divider_parent = name, len(chapters_list), None
                elif divider and not merged:
                    if divider_parent is None:
                        own = sum(glued_lines(c) for c in chapters_list[divider_from:] if c['chapter_title'] == divider)
                        divider_parent = divider if own <= DIVIDER_MAX_SENTENCES else ''
                    if divider_parent:
                        return format_merged_chapter_name(divider_parent, label)
                return name

            for spine_idx, href in enumerate(spine_files):
                if not href or href in not_pages:
                    continue

                matched_toc_label = None
                here = None
                if href in toc_map:
                    matched_toc_label = toc_map[href]
                    here = posixpath.normpath(href)
                else:
                    full_h = posixpath.join(content_dir, href) if content_dir else href
                    here = posixpath.normpath(full_h)
                    if full_h in toc_map:
                        matched_toc_label = toc_map[full_h]
                    elif here in toc_map:
                        matched_toc_label = toc_map[here]

                if matched_toc_label:
                    current_origin = "toc"
                    section_ctx = None
                    toc_label = clean_heading_label(matched_toc_label)
                    norm_toc = normalize_cjk_spacing(toc_label)
                    if IN_FILE_PART_RE.match(norm_toc):
                        current_part = _cut_sections(toc_label)
                        current_chapter_title = toc_label
                    elif ('｜' in toc_label and not is_structural_chapter_heading(toc_label.split('｜')[0])
                          and VOLUME_LABEL_RE.match(strip_ruby_markup(matched_toc_label.split('｜')[-1].strip()))):
                        current_part = ""
                        current_chapter_title = toc_label
                    else:
                        root = _without_chapter(current_part)
                        standalone = toc_label in STANDALONE_NON_PART_SECTIONS or any(toc_label.startswith(s) for s in STANDALONE_NON_PART_SECTIONS)
                        if root and not standalone and CHAPTER_LEVEL_RE.match(normalize_cjk_spacing(toc_label.split('｜')[0])):
                            chapter = _from_last_chapter(toc_label)
                            current_chapter_title = format_merged_chapter_name(root, chapter)
                            section_ctx = (current_part, f"{root}｜{chapter.split('｜')[0]}")
                        elif current_part and not (toc_label in STANDALONE_NON_PART_SECTIONS or any(toc_label.startswith(s) for s in STANDALONE_NON_PART_SECTIONS)):
                            current_chapter_title = format_merged_chapter_name(current_part, toc_label)
                        else:
                            if toc_label in STANDALONE_NON_PART_SECTIONS or any(toc_label.startswith(s) for s in STANDALONE_NON_PART_SECTIONS):
                                current_part = ""
                            current_chapter_title = toc_label
                    if toc_label != last_toc_label:
                        last_toc_label = toc_label
                        current_chapter_title = under_divider(toc_label, current_chapter_title,
                                                              '｜' in matched_toc_label or bool(current_part))
                        last_toc_title = current_chapter_title
                    else:
                        current_chapter_title = last_toc_title

                full_path = None
                for h in dict.fromkeys((href, unquote(href))):
                    for candidate in (h, posixpath.normpath(posixpath.join(content_dir, h)) if content_dir else h):
                        if full_path is None and candidate in zip_names:
                            full_path = candidate
                if full_path is None:
                    pass_excluded.append((title, "MISSING_PAGE", href))
                    continue
                try:
                    raw_xhtml = zf.read(full_path)
                except (zipfile.BadZipFile, EOFError, OSError, RuntimeError, KeyError) as exc:
                    raise zipfile.BadZipFile(f"Unreadable EPUB chapter {full_path}: {exc}") from exc

                page_dir = posixpath.dirname(full_path)
                def image_size(src, page_dir=page_dir):
                    try:
                        return zf.getinfo(posixpath.normpath(posixpath.join(page_dir, src))).file_size
                    except (KeyError, ValueError):
                        return None
                def page_soup():
                    s = parse_page(raw_xhtml)
                    clean_html_ruby_and_tags(s, image_size)
                    drop_template_placeholders(s, raw_xhtml)
                    return s
                soup = page_soup()
                label_key = re.sub(r'[\s　]+', '', clean_heading_label(matched_toc_label)) if matched_toc_label else ''
                labelled_colophon = bool(label_key and COLOPHON_LABEL_RE.search(label_key))
                wrapped = _wrap_body_inline_runs(soup)

                text_blocks = [b for b in soup.find_all(_page_block_test(False, sections=False)) if b.get_text(strip=True)]
                linked = sum(1 for b in text_blocks
                             if b.find_parent('a', href=True)
                             or sum(len(a.get_text(strip=True)) for a in b.find_all('a', href=True))
                             >= 0.5 * len(b.get_text(strip=True)))
                is_contents_page = bool(
                    (matched_toc_label and CONTENTS_LABEL_RE.search(clean_heading_label(matched_toc_label)))
                    or (len(text_blocks) >= 3 and linked >= 0.5 * len(text_blocks)))
                if wrapped and (is_contents_page or labelled_colophon):
                    soup = page_soup()
                    if not any(b.get_text(strip=True) for b in soup.find_all(_page_block_test(False, sections=False))):
                        _wrap_body_inline_runs(soup)
                page_text = soup.get_text(strip=True)
                read_tables = not (is_contents_page or labelled_colophon
                                   or (len(page_text) < COLOPHON_PAGE_CHARS and COLOPHON_TEXT_RE.search(page_text)))
                skip_tables = set()
                if read_tables:
                    for table in soup.find_all('table'):
                        table_text = table.get_text(strip=True)
                        if len(table_text) < COLOPHON_PAGE_CHARS and COLOPHON_TEXT_RE.search(table_text):
                            skip_tables.add(id(table))
                blocks = soup.find_all(_page_block_test(read_tables, skip_tables))
                kana_index_page = has_kana_heading(soup)
                if is_contents_page and not matched_toc_label:
                    current_part = ""
                    current_chapter_title = '目次'
                    current_origin = "contents"
                lines = [b.get_text(strip=True) for b in blocks if b.get_text(strip=True)]
                unique_lines = list(dict.fromkeys(lines))
                total_chars = sum(len(l) for l in unique_lines)

                if len(unique_lines) == 0:
                    continue

                if len(unique_lines) <= 2 and total_chars <= 50:
                    clean_first = normalize_cjk_spacing(heading_test_text(unique_lines[0]))
                    pure_first = re.sub(r'[\s　]+', '', clean_first)
                    if IN_FILE_PART_RE.match(clean_first):
                        if not (matched_toc_label and '｜' in matched_toc_label
                                and re.sub(r'[\s　]+', '', matched_toc_label.split('｜')[-1]) == pure_first):
                            current_part = clean_heading_label(unique_lines[0])
                        continue
                    if pure_first in (pure_title, pure_author, f'{pure_author}{pure_title}', '表紙', '扉', '目次', 'Cover', 'Guide', 'Navigation', 'Start', 'Contents') or any(kw in clean_first for kw in ['刊行された', '発行所', '禁無断転載', '初出']):
                        continue

                for b in blocks:
                    block_text = b.get_text(strip=True)
                    if not block_text:
                        continue

                    clean_b_text = normalize_cjk_spacing(heading_test_text(block_text))

                    if not is_contents_page and is_valid_heading_block(b.name, block_text):
                        if IN_FILE_PART_RE.match(clean_b_text):
                            if not has_authoritative_toc:
                                current_part = clean_heading_label(block_text)
                            continue
                        elif IN_FILE_CHAPTER_RE.match(clean_b_text):
                            ch_name = clean_heading_label(strip_ruby_markup(block_text))
                            pure_ch = re.sub(r'[\s　]+', '', ch_name)
                            if ch_name.upper() not in GENERIC_TOC_NAMES and pure_ch != pure_title:
                                if has_authoritative_toc and (current_chapter_title == ch_name or current_chapter_title.endswith(f"｜{ch_name}") or current_chapter_title.startswith(ch_name)):
                                    pass
                                elif has_authoritative_toc and names_toc_chapter_elsewhere(ch_name, here):
                                    pass
                                else:
                                    current_origin = "infile"
                                    chapter_level = (CHAPTER_LEVEL_RE.match(normalize_cjk_spacing(ch_name))
                                                     and not (ch_name in STANDALONE_NON_PART_SECTIONS or any(ch_name.startswith(s) for s in STANDALONE_NON_PART_SECTIONS)))
                                    if section_ctx and section_ctx[0] == current_part and SECTION_LEVEL_RE.match(normalize_cjk_spacing(ch_name)):
                                        current_chapter_title = format_merged_chapter_name(section_ctx[1], ch_name)
                                    elif current_part and chapter_level:
                                        section_ctx = None
                                        current_chapter_title = format_merged_chapter_name(_without_chapter(current_part), ch_name)
                                    elif current_part and not (ch_name in STANDALONE_NON_PART_SECTIONS or any(ch_name.startswith(s) for s in STANDALONE_NON_PART_SECTIONS)):
                                        current_chapter_title = format_merged_chapter_name(current_part, ch_name)
                                    else:
                                        if ch_name in STANDALONE_NON_PART_SECTIONS or any(ch_name.startswith(s) for s in STANDALONE_NON_PART_SECTIONS):
                                            current_part = ""
                                        current_chapter_title = ch_name
                                    current_chapter_title = under_divider(ch_name, current_chapter_title, bool(current_part))
                                    continue

                    pieces = _br_lines(b, block_text, kana_index_page)
                    first_own = kana_index_page and len(pieces) > 1 and _index_block(pieces)
                    for s, own_line, repeat in ((s, pi > 0 and si == 0, speech or (si == 0 and (pi > 0 or first_own)))
                                                for pi, piece in enumerate(pieces)
                                                for si, (s, speech) in enumerate(sentence_pieces(piece))):
                        s_clean = _postprocess_sentence(s)
                        if not s_clean:
                            continue

                        if TIMESTAMP_SCENE_RE.match(s_clean):
                            pass_excluded.append((title, "TIMESTAMP_SCENE", s_clean))
                            continue

                        if ILLUSTRATION_PLACEHOLDER_RE.match(s_clean):
                            pass_excluded.append((title, "ILLUSTRATION_PLACEHOLDER", s_clean))
                            continue

                        if not chapters_list or chapters_list[-1]['chapter_title'] != current_chapter_title:
                            chapters_list.append({'chapter_title': current_chapter_title, 'sentences': [], 'sp': [],
                                                  'spine': [spine_idx, spine_idx], 'origin': current_origin})
                        chapter = chapters_list[-1]
                        chapter['spine'][1] = spine_idx
                        s_list = chapter['sentences']

                        if s_list and not repeat:
                            prev_clean = get_clean_text_for_mecab(s_list[-1])
                            curr_clean = get_clean_text_for_mecab(s_clean)
                            if prev_clean == curr_clean:
                                if '｜' in s_clean and '｜' not in s_list[-1]:
                                    s_list[-1] = s_clean
                                continue

                        s_list.append(s_clean)
                        chapter['sp'].append(spine_idx)
                        if own_line:
                            chapter.setdefault('br_at', []).append(len(s_list) - 1)

            chapters_list = split_counting_headings(chapters_list, title)
            kept = []
            for chapter in chapters_list:
                ch_name, s_list = chapter['chapter_title'], chapter['sentences']
                if is_tautological_chapter(ch_name, [''.join(s_list)] if chapter.get('br_at') and glued_lines(chapter) == 1 else s_list):
                    pass_excluded.append((title, "TAUTOLOGICAL_EMPTY_CHAPTER", ch_name))
                    continue
                kept.append(chapter)
            return kept, pass_excluded

        kept, pass_excluded = _read_spine()
        _EXCLUDED_LOG.extend(pass_excluded)
        if kept and kept[0]['origin'] == 'title' and glued_lines(kept[0]) <= 50:
            kept[0]['chapter_title'] = '表紙'
            if len(kept) > 1 and kept[1]['chapter_title'] == '表紙':
                kept[0]['sentences'] += kept[1]['sentences']
                kept[0]['spine'] = [kept[0]['spine'][0], kept[1]['spine'][1]]
                del kept[1]

        chapters_data = []
        valid_idx = 1
        for chapter in kept:
            ch_name, s_list = chapter['chapter_title'], chapter['sentences']
            chapters_data.append({
                'order_idx': valid_idx,
                'chapter_title': ch_name,
                'sentences': s_list,
                'spine': tuple(chapter['spine']),
                'origin': chapter['origin'],
            })
            valid_idx += 1
        try:
            for chapter, name in zip(chapters_data, shared_name_parents(zf, opf, content_dir, spine_files, title, chapters_data)):
                chapter['chapter_title'] = name
        except Exception:
            pass
        try:
            folders = index_folders(zf, opf, content_dir, spine_files, title, chapters_data)
        except Exception:
            folders = [None] * len(chapters_data)
        for chapter, folder in zip(chapters_data, folders):
            chapter['folder'] = folder

        return author, title, chapters_data

def chapter_file(title, ch):
    return f"{title}\\{ch['order_idx']:02d}.{ch['chapter_title']}"


_ASCII_BRACKETS = str.maketrans("()[]", "（）［］")


class _HeldTitles:
    def __init__(self, title_ids, own):
        self.title_ids, self.own = title_ids, own

    def __contains__(self, title):
        return bool(self.title_ids.get(title, set()) - {self.own})


def distinct_book_title(title, relpath, author, taken):
    if not title or title not in taken:
        return title
    stem =os.path.splitext(os.path.basename(relpath))[0]
    plain = re.sub(r"[\s_　]", "", title)
    marks = [b.translate(_ASCII_BRACKETS) for b in re.findall(_BOOK_BRACKET, stem)
             if re.sub(r"[\s_　]", "", b[1:-1]) and re.sub(r"[\s_　]", "", b[1:-1]) not in plain]
    folder = os.path.basename(os.path.dirname(relpath.replace("\\", "/")))
    for extra in ("".join(marks), f"（{author}）" if author else "", f"（{folder}）" if folder else ""):
        if extra and f"{title}{extra}" not in taken:
            return f"{title}{extra}".replace("_", " ")
    n = 2
    while f"{title}（{n}）" in taken:
        n += 1
    return f"{title}（{n}）"


def book_rows(title, chapters_data):
    rows = []
    for ch in chapters_data:
        file_key = chapter_file(title, ch)

        for i, line in enumerate(ch['sentences']):
            if i % 128 == 0:
                control.check_stop()
            clean_text = fold_compat(get_clean_text_for_mecab(line))
            base_forms, readings, lens = analyze_tokens(drawn_gloss_text(clean_text))

            base_forms, readings = ruby_index_extras(line, BOOK_RUBY_RE, base_forms, readings)
            base_forms, readings = ruby_index_extras(drawn_gloss_ruby(clean_text), BOOK_RUBY_RE, base_forms, readings)

            rows.append((file_key, line, clean_text, base_forms, readings, lens))
    return rows


def _drawn_glosses(clean_text):
    if '（' not in clean_text and '(' not in clean_text:
        return []
    from aobana.search import furigana
    out = []
    for m in furigana.display_ruby_re('epub').finditer(clean_text):
        if m.group(2) is None:
            continue
        okuri = furigana._gloss_okuri(m)
        cut = furigana.gloss_span(m.group(2), m.group(3), okuri) or 0
        out.append((m.end(2), m.end(), m.group(2)[cut:], m.group(3)))
    return out


def drawn_gloss_text(clean_text):
    spans = _drawn_glosses(clean_text)
    if not spans:
        return clean_text
    out, at = [], 0
    for start, end, _, _ in spans:
        out.append(clean_text[at:start])
        at = end
    out.append(clean_text[at:])
    return ''.join(out)


def drawn_gloss_ruby(clean_text):
    return ''.join(f'｜{base}({re.sub(r"[ 　]", "", kana)})' for _, _, base, kana in _drawn_glosses(clean_text))


def _prepare(job):
    epub_path, relpath, known_hash = job
    _EXCLUDED_LOG.clear()
    try:
        file_hash = compute_file_hash(epub_path)
        if file_hash == known_hash:
            return ('same', relpath, file_hash, None)
        author, title, chapters_data = extract_epub_content(epub_path)
        rows = [r + (stored_display_length(r[1], "epub"), kanji_table.tokens(r[2]))
                for r in book_rows(title, chapters_data)]
    except Exception as e:
        return ('error', relpath, None, f"{type(e).__name__}: {e}")
    folders = {chapter_file(title, ch): ch['folder'] for ch in chapters_data if ch.get('folder')}
    return ('rows', relpath, file_hash, (title, author, len(chapters_data), rows, list(_EXCLUDED_LOG), folders))


COMMIT_EVERY_BOOKS = 20
COMMIT_EVERY_SECONDS = 20


from aobana.indexing import run_control as control, kanji_table, rebuild as rebuilding
from aobana.indexing.preparation import prepare_changed
from aobana.utils import media_walk

def build_tables(conn, top, db=None):
    db = db or DB_PATH
    if top and not has_chapters(conn):
        emit("phase", "CHAPTERS building the chapter table (once, reads the whole index)...", phase="chapters")
    if ensure_chapters(conn) and top:
        say(f"CHAPTERS {conn.execute('SELECT COUNT(*) FROM chapters').fetchone()[0]} chapters")
    ensure_chapter_folder(conn)
    conn.commit()
    if top and not has_line_lengths(conn):
        emit("phase", "LENGTHS building the display-length table (once, reads the whole index)...", phase="lengths")
    ensure_line_lengths(conn, db, "epubs", "epub", paths.index_workers())
    if stop_requested():
        return
    if top and not has_ruby_lexicon(conn):
        emit("phase", "LEXICON building the ruby lexicon table (once, reads the whole index)...", phase="lexicon")
    ensure_ruby_lexicon(conn, "epubs", "epub", paths.index_workers())
    if stop_requested():
        return
    kanji_table.build(conn, "epubs")


@control.owned(lambda: DB_PATH)
def run_tables():
    say(f"Building the book index's tables ({DB_PATH})...")
    with control.connection(DB_PATH) as conn:
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'epubs'").fetchone() is None:
            say("Tables ready: no book index yet.")
            return
        build_tables(conn, conn.execute("SELECT rowid FROM epubs ORDER BY rowid DESC LIMIT 1").fetchone())
    if stop_requested():
        emit("stopped", "STOPPED")
    else:
        say("Tables ready.")


def _auto_filter_journal():
    return paths.filtered_list() + ".epub-pending"


def _write_auto_filter_journal(rows):
    path = _auto_filter_journal()
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _recover_auto_filter_journal(conn):
    path = _auto_filter_journal()
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as fh:
        rows = json.load(fh)
    if not isinstance(rows, list):
        raise ValueError("Invalid pending EPUB filter journal")
    committed = []
    for row in rows:
        name = row.get("name", "")
        if (row.get("media") != "epub" or row.get("origin") != "auto"
                or conn.execute("SELECT 1 FROM sources WHERE relpath = ?", (name,)).fetchone()):
            continue
        file_path = paths.resolve_media_path('epub', name, paths.index_roots('epub', EPUB_ROOT_DIR))
        if not file_path:
            continue
        try:
            st = os.stat(file_path)
        except OSError:
            continue
        if str(st.st_size) == row.get("size") and str(st.st_mtime_ns) == row.get("mtime"):
            committed.append(row)
    append_filtered_rows(paths.filtered_list(), committed)
    os.remove(path)


@control.owned(lambda: DB_PATH)
def run_epub_indexer(force=False, outdated=False, allow_removal=False, rebuild=False):
    say(f"Starting EPUB indexer on {EPUB_ROOT_DIR} (force={force}, outdated={outdated}, rebuild={rebuild})...")
    roots = paths.index_roots('epub', EPUB_ROOT_DIR, paths.media_roots('epub'))
    _EXCLUDED_LOG.clear()
    if EPUB_ROOT_DIR is None:
        emit("root_not_set", "ROOT_NOT_SET epub", media="epub")
        say("No books folder is set (Library tab). Nothing was changed.")
        return
    if not paths.media_enabled("books"):
        say("Books are off in Settings. Nothing was changed.")
        return
    if any(not os.path.isdir(root) for root in roots):
        missing = next(root for root in roots if not os.path.isdir(root))
        emit("root_missing", f"ROOT_MISSING {missing}", folder=missing)
        say("EPUB indexing aborted: the books folder does not exist. Nothing was changed.")
        return
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    excluded = control.StreamLog(os.path.join(paths.logs_dir(), 'excluded_epub_lines.txt'),
                                 lambda r: f'[{r[0]}] [{r[1]}] {r[2]}')

    db, old_files, failed_keys, result = DB_PATH, {}, [], None
    if rebuild:
        old_files = rebuilding.old_sources(DB_PATH)
        db = rebuilding.path(DB_PATH)
        rebuilding.discard(DB_PATH)
        say(f"REBUILD a new index beside the old one ({len(old_files)} books indexed)")
    with control.connection(db) as conn:
        conn.row_factory = sqlite3.Row

        if force:
            say("Force rebuild requested. Dropping existing tables in epub.db...")
            conn.execute("DROP TABLE IF EXISTS epubs")
            conn.execute("DROP TABLE IF EXISTS sources")
            conn.execute("DROP TABLE IF EXISTS chapters")
            conn.execute("DROP TABLE IF EXISTS line_lengths")
            conn.execute("DROP TABLE IF EXISTS token_lengths")
            conn.execute("DROP TABLE IF EXISTS ruby_lexicon")
            kanji_table.drop(conn, "epubs")
            conn.commit()

        conn.execute('''
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                relpath TEXT UNIQUE NOT NULL,
                file_hash TEXT NOT NULL,
                title TEXT NOT NULL,
                author TEXT NOT NULL,
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.execute('''
            CREATE VIRTUAL TABLE IF NOT EXISTS epubs USING fts5(
                source_id UNINDEXED,
                file UNINDEXED,
                line UNINDEXED,
                clean_text UNINDEXED,
                base_forms,
                readings,
                tokenize = "unicode61"
            )
        ''')
        conn.commit()

        ensure_format_column(conn)
        from aobana.utils import report_outdated
        report_outdated(conn, 'epub')
        conn.commit()
        _recover_auto_filter_journal(conn)
        top = conn.execute("SELECT rowid FROM epubs ORDER BY rowid DESC LIMIT 1").fetchone()
        build_tables(conn, top, db)
        lengths = has_line_lengths(conn)
        tokens = has_token_lengths(conn)
        lexicon = has_ruby_lexicon(conn)
        control.check_stop()
        kanji = kanji_table.ready(conn, "epubs")
        cur = conn.execute("SELECT id, relpath, file_hash, index_format FROM sources")
        existing_files = {name_key(row['relpath']): {'id': row['id'], 'hash': None if outdated and is_outdated('epub', row['relpath'], row['index_format']) else row['file_hash']}
                          for row in cur}
        title_ids = collections.defaultdict(set)
        id_title = {}
        for sid, t in conn.execute("SELECT id, title FROM sources"):
            title_ids[t].add(sid)
            id_title[sid] = t
        conn.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
        row_checked = conn.execute("SELECT v FROM meta WHERE k = 'epub_spine_checked'").fetchone()
        recheck_empty = (row_checked is None or row_checked[0] != '3')
        if recheck_empty:
            empty_ids = {row[0] for row in conn.execute(
                "SELECT id FROM sources EXCEPT SELECT source_id FROM chapters "
                "UNION SELECT source_id FROM chapters GROUP BY source_id "
                "HAVING SUM(last_rowid - first_rowid + 1) <= 200")}
            for old in existing_files.values():
                if old['id'] in empty_ids:
                    old['hash'] = None
        deleted_rows = inserted_rows = 0
        floor = top[0] if top else 0
        next_rowid = floor + 1
        replaced = []
        auto_filtered = []

        def old_spans(source_id):
            spans = conn.execute("SELECT first_rowid, last_rowid FROM chapters WHERE source_id = ?",
                                 (source_id,)).fetchall()
            conn.execute("DELETE FROM chapters WHERE source_id = ?", (source_id,))
            if lexicon:
                drop_ruby_lexicon(conn, [source_id])
            return spans

        def delete_rows(source_id, spans):
            n = 0
            for a, b in spans:
                n += conn.execute("DELETE FROM epubs WHERE rowid BETWEEN ? AND ? AND source_id = ?",
                                  (a, min(b, floor), source_id)).rowcount
                if lengths:
                    conn.execute("DELETE FROM line_lengths WHERE rowid BETWEEN ? AND ?", (a, min(b, floor)))
                if tokens:
                    conn.execute("DELETE FROM token_lengths WHERE rowid BETWEEN ? AND ?", (a, min(b, floor)))
                if kanji:
                    kanji_table.delete_range(conn, "epubs", a, min(b, floor))
            return n

        removed = 0
        def flush():
            nonlocal deleted_rows
            control.check_stop()
            for source_id, spans in replaced:
                deleted_rows += delete_rows(source_id, spans)
            replaced.clear()
            if auto_filtered:
                _write_auto_filter_journal(auto_filtered)
            conn.commit()
            control.committed(new_or_updated, skipped, removed + auto_removed)
            if auto_filtered:
                append_filtered_rows(paths.filtered_list(), auto_filtered)
                os.remove(_auto_filter_journal())
                auto_filtered.clear()

        current_disk_files = set()
        new_or_updated = 0
        skipped = 0
        auto_removed = 0

        epub_files = []
        ignored = 0
        failed = 0
        roots_by_path = {}
        from aobana.utils import media_walk_roots
        for source_root, root, kept, other in media_walk_roots(roots, "epub"):
            control.check_stop()
            epub_files.extend(os.path.join(root, f) for f in kept)
            roots_by_path.update({os.path.join(root, f): source_root for f in kept})
            ignored += other

        say(f"Found {len(epub_files)} .epub file(s) in {EPUB_ROOT_DIR}.")
        if ignored:
            emit("ignored_other", f"IGNORED_OTHER {ignored}", count=ignored)
        emit("total", f"TOTAL {len(epub_files)}", quiet=True, total=len(epub_files))

        epub_by_name = {norm_relpath(p, roots_by_path[p]): p for p in epub_files}
        filtered = {name_key(r["name"]) for r in refresh_auto_filtered(
            paths.filtered_list(), "epub", epub_by_name
        ) if r["media"] == "epub"}
        jobs, n_filtered = [], 0
        for epub_path in epub_files:
            relpath = norm_relpath(epub_path, roots_by_path[epub_path])
            key = name_key(relpath)
            if key in filtered:
                n_filtered += 1
                continue
            current_disk_files.add(key)
            jobs.append((epub_path, relpath, existing_files.get(key, {}).get('hash')))
        if n_filtered:
            emit("filtered", f"FILTERED {n_filtered}", count=n_filtered)

        workers = paths.index_workers() if len(jobs) > 1 else 1
        if workers > 1:
            say(f"Workers: {workers}")
        meta_written = False
        pending, last_commit = 0, time.monotonic()
        stopped = False
        control.phase('preparation', total=len(jobs))
        for n, (kind, relpath, file_hash, payload) in enumerate(
                prepare_changed(_prepare, jobs, workers, compute_file_hash, stop=stop_requested), 1):
            if stop_requested():
                stopped = True
                break
            emit("progress", f"PROGRESS {n}/{len(jobs)} {relpath}", quiet=True, done=n, total=len(jobs), file=relpath)
            if kind == 'same':
                skipped += 1
                continue
            old = existing_files.get(name_key(relpath))
            if kind == 'error':
                if old:
                    conn.execute("UPDATE sources SET file_hash = '' WHERE id = ?", (old['id'],))
                failed += 1
                if rebuilding.transient(payload):
                    failed_keys.append(name_key(relpath))
                emit("failed", f"FAILED {relpath}: {payload}", file=relpath, error=str(payload))
                continue
            control.phase('writing', n-1, len(jobs))
            title, author, n_chapters, rows, book_excluded, folders = payload
            rows = list(rows)
            excluded.extend(book_excluded)
            if not rows:
                if old:
                    deleted_rows += delete_rows(old['id'], old_spans(old['id']))
                    conn.execute("DELETE FROM sources WHERE id = ?", (old['id'],))
                    auto_removed += 1
                try:
                    file_stat = os.stat(epub_by_name[relpath])
                except OSError:
                    file_stat = None
                if file_stat is not None:
                    auto_filtered.append({
                    "media": "epub",
                    "name": relpath,
                    "reason": "drm" if drm_locked(epub_by_name[relpath]) else "image_only",
                    "keep": "",
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "origin": "auto",
                    "size": str(file_stat.st_size),
                    "mtime": str(file_stat.st_mtime_ns),
                    })
                filtered.add(name_key(relpath))
                n_filtered += 1
                say(f"Filtered image-only EPUB (0 sentences): {relpath}")
                emit("filtered", f"FILTERED {n_filtered}", count=n_filtered)
                pending += 1
                if pending >= COMMIT_EVERY_BOOKS or time.monotonic() - last_commit >= COMMIT_EVERY_SECONDS:
                    flush()
                    pending, last_commit = 0, time.monotonic()
                continue
            if not meta_written:
                write_tokenizer_meta(conn, 1)
                meta_written = True
            if old:
                source_id = old['id']
                replaced.append((source_id, old_spans(source_id)))
                conn.execute("UPDATE sources SET relpath = ?, file_hash = ?, indexed_at = ?, index_format = ? WHERE id = ?",
                             (relpath, file_hash, datetime.now().isoformat(' '), INDEX_FORMAT['epub'], source_id))
            else:
                cur = conn.execute("INSERT INTO sources (relpath, file_hash, title, author, index_format) VALUES (?, ?, '', '', ?)",
                                   (relpath, file_hash, INDEX_FORMAT['epub']))
                source_id = cur.lastrowid

            new_or_updated += 1
            held = _HeldTitles(title_ids, source_id)
            distinct = distinct_book_title(title, relpath, author, held)
            if distinct != title:
                cut = len(title)
                rows = [(distinct + r[0][cut:],) + tuple(r[1:]) for r in rows]
                folders = {distinct + k[cut:]: v for k, v in folders.items()}
                title = distinct
            title_ids[id_title.get(source_id)].discard(source_id)
            title_ids[title].add(source_id)
            id_title[source_id] = title
            conn.execute("UPDATE sources SET title = ?, author = ? WHERE id = ?", (title, author, source_id))
            inserted_rows += conn.executemany(
                "INSERT INTO epubs(rowid, source_id, file, line, clean_text, base_forms, readings) VALUES (?, ?, ?, ?, ?, ?, ?);",
                [(next_rowid + i, source_id) + r[:5] for i, r in enumerate(rows)]
            ).rowcount
            conn.executemany("INSERT INTO chapters VALUES (?, ?, ?, ?, ?, ?)",
                             [span + (folders.get(span[1]),) for span in
                              chapter_spans((next_rowid + i, source_id, r[0]) for i, r in enumerate(rows))])
            if lengths:
                write_line_lengths(conn, ((next_rowid + i, r[6]) for i, r in enumerate(rows)), "epub", computed=True)
            write_token_lengths(conn, ((next_rowid + i, r[5]) for i, r in enumerate(rows)))
            if kanji:
                kanji_table.write(conn, "epubs", ((next_rowid + i, r[7]) for i, r in enumerate(rows)), computed=True)
            if lexicon:
                write_ruby_lexicon(conn, "epub", ((source_id, r[0], r[1]) for r in rows))
            next_rowid += len(rows)
            say(f"Indexed EPUB: {title} by {author} ({len(rows)} sentences in {n_chapters} chapters)")
            pending += 1
            if pending >= COMMIT_EVERY_BOOKS or time.monotonic() - last_commit >= COMMIT_EVERY_SECONDS:
                flush()
                pending, last_commit = 0, time.monotonic()
        control.check_stop()
        flush()

        deleted_files, _ = held_removals(len(existing_files), set(existing_files.keys()) - current_disk_files,
                                         filtered, allow_removal)
        control.phase('removals', total=len(deleted_files))
        removal_pending, removal_time = 0, time.monotonic()
        for relpath in sorted(deleted_files):
            control.check_stop()
            source_id = existing_files[relpath]['id']
            deleted_rows += delete_rows(source_id, old_spans(source_id))
            conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
            removed += 1
            removal_pending += 1
            control.CURRENT.publish(phase='removals', phase_done=removed, phase_total=len(deleted_files))
            if removal_pending >= 200 or time.monotonic() - removal_time >= 20:
                flush()
                removal_pending, removal_time = 0, time.monotonic()
            say(f"Removed {'filtered' if relpath in filtered else 'deleted'} EPUB: {relpath}")

        if rebuild and not stopped:
            gone, held = held_removals(len(old_files), set(old_files) - current_disk_files, filtered, allow_removal)
            deleted_files, removed = gone, len(gone)
            why = rebuilding.refused(old_files, failed_keys, held)
            result = 'refused' if why else 'rebuilt'
            if why:
                say(f"REBUILD_REFUSED {why}: the old index is kept and updated instead.")

        for t, n, rels in conn.execute(
                "SELECT title, COUNT(*), group_concat(relpath, ' | ') FROM sources "
                "GROUP BY title HAVING COUNT(*) > 1"):
            say(f"WARNING: {n} books share the title {t}: {rels}")

        ident = write_tokenizer_meta(conn, 0)
        if new_or_updated:
            say(f"Tokenizer: SudachiDict-core {ident['sudachidict_version']} "
                  f"({ident['dictionary_format']}), SudachiPy {ident['sudachipy_version']}, "
                  f"system.dic {ident['system_dic_sha256'][:12]}")

        if recheck_empty and not stopped:
            conn.execute("INSERT OR REPLACE INTO meta (k, v) VALUES ('epub_spine_checked', '3')")
        flush()
        if stopped:
            emit("stopped", "STOPPED")
        else:
            compact_if_worth(conn, "epubs", deleted_rows, inserted_rows)

    excluded.close()

    if rebuild:
        conn.close()
        if result == 'rebuilt':
            open(rebuilding.done_path(DB_PATH), 'w').close()
        else:
            rebuilding.discard(DB_PATH)
        if result == 'refused':
            return result

    emit("summary", f"EPUB Indexing complete! Skipped {skipped} unchanged files. Indexed {new_or_updated} new/updated books. Removed {len(deleted_files) + auto_removed} deleted."
         + (f" Failed {failed}." if failed else ""),
         unchanged=skipped, indexed=new_or_updated, removed=removed + auto_removed, failed=failed)
    return result

if __name__ == "__main__":
    import sys
    from aobana.indexing.process_tree import cli_owner
    cli_owner('aobana.indexing.epub_indexer')
    start_output()
    force_flag = "--force" in sys.argv
    if "--tables" in sys.argv:
        if os.path.exists(DB_PATH):
            run_tables()
        sys.exit(0)
    if rebuilding.FLAG in sys.argv:
        rebuilding.main(run_epub_indexer, DB_PATH, sys.argv, ALLOW_REMOVAL_FLAG in sys.argv)
    else:
        run_epub_indexer(force=force_flag, outdated="--outdated" in sys.argv, allow_removal=ALLOW_REMOVAL_FLAG in sys.argv)
