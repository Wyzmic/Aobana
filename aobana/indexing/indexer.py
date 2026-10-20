import os
import re
import sqlite3
import collections
import hashlib
import time
import unicodedata
from sudachipy import tokenizer, dictionary
from datetime import datetime

from aobana import paths
BASE_DIR = paths.BASE_DIR
ROOT_DIR = paths.subs_dir()
DB_PATH = paths.subs_db()

_TOKENIZER = None
mode = tokenizer.Tokenizer.SplitMode.A
from aobana.utils import SUDACHI_MAX_BYTES


def get_tokenizer():
    global _TOKENIZER
    if _TOKENIZER is None:
        _TOKENIZER = dictionary.Dictionary(dict="core").create()
    return _TOKENIZER

from aobana.utils import (
    KANA_RE, KANJI_CHARS, KANJI_PATTERN,
    ALPHA_CHARS, ALPHA_PATTERN, RUBY_BASE_RE, RUBY_RE,
    norm_relpath, INDEX_FORMAT, is_outdated, ensure_format_column, compact_if_worth, stop_requested, sub_relpath, is_appledouble_name, write_tokenizer_meta, ruby_index_extras, fold_compat, parallel_map,
    strip_chinese_chunks, is_chinese_text, filtered_names, held_removals, ALLOW_REMOVAL_FLAG, name_key,
    MEDIA_EXTS, media_walk,
    start_output, emit, say,
    ensure_line_lengths, has_line_lengths, write_line_lengths, drop_orphan_lengths, token_lengths_blob,
    write_token_lengths, stored_display_length,
    ensure_ruby_lexicon, has_ruby_lexicon, write_ruby_lexicon, drop_ruby_lexicon,
)

HTML_TAG_RE = re.compile(r'</?(?:i|b|u|s|font|c(?=[.>])|v(?=[\s.>]))[^>]*>', re.IGNORECASE)
BIDI_MARK_RE = re.compile(r'&(?:lrm|rlm);|[‎‏]')
INVISIBLE_RE = re.compile('[\u202a-\u202e\u2066-\u2069\u200b\ufeff\u00ad\u2009\u3164\ufe0f]')
CONTROL_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
PUA_SPACE = {0xE4C6}
PUA_MARKS = {0xEC00, 0xEC01, 0xE285, 0xE292, 0xE2F9, 0xE2FA, 0xE2FB, 0xE348, 0xE349}


def _is_kanji(ch):
    o = ord(ch)
    return 0x3400 <= o <= 0x9FFF or 0xF900 <= o <= 0xFAFF or o == 0x3005


def private_use(line):
    if not any(0xE000 <= ord(c) <= 0xF8FF for c in line):
        return line
    out = []
    for i, c in enumerate(line):
        o = ord(c)
        if not 0xE000 <= o <= 0xF8FF:
            out.append(c)
        elif 0xF300 <= o <= 0xF6FF and unicodedata.category(chr(0x10000 + o)) == 'So':
            out.append(chr(0x10000 + o))
        elif o in PUA_SPACE:
            if out and out[-1] != ' ':
                out.append(' ')
        elif o in PUA_MARKS:
            pass
        elif i and (_is_kanji(line[i - 1]) or (i + 1 < len(line) and _is_kanji(line[i + 1]))):
            out.append('〓')
    return ''.join(out).strip()


HTML_ENTITIES = (('&lt;', '<'), ('&gt;', '>'), ('&amp;', '&'))
SQUARE_BRACKETS_RE = re.compile(r'\[[^\[\]]*\]')
from aobana.indexing import subtitle_input
from aobana.indexing.subtitle_ruby import dictionary_prefixes, has_native_ruby, normalize_subtitle_ruby, source_readings
from functools import lru_cache
TIMECODE_RE = subtitle_input.TIMECODE_RE

SIMP_CHINESE_RE = re.compile(r'[这吗呢吧啦么谁们从说话样觉视频听欢买卖错让帮确对爱关门图运无计场动时发现经还进长您她啥够钟钱馆帅步舔护见恼变樱联语弃寻伫战龙击两亚丽丝态类优恶办统层头谈论戏极气为复杂转带质压雾辈适厌连隐谓认费愿拥应废东获谢闪诚责过军预给险刚脑测实迟钝虽剑临圣请哪呗尔谅创兰鲁伙开读网电车专乐业产农风飞杀药权树桥决减满卫织续损]')
ZH_KANA_RE = re.compile('[ぁ-ゖァ-ヺ]')
_CJK_CHAR_RE = re.compile('[一-鿿]')
_ZH_SPLIT_RE = re.compile('([\\s　]+)')
ZH_CREDIT_RE = re.compile(r'(?:翻[译譯]|校[对對润潤译]|后期|日听|听写|聽寫|时间轴|时轴|時軸|压制|壓制|繁化|片源|特效|监制|总筹|字幕制作|日字|翻校|时后|校轴)\s*[：:]')
ZH_CREDIT_JA_RE = re.compile(r'(?:後期|時間軸|監製)\s*[：:]')
ZH_NOTE_RE = re.compile(r'(?:^|[\s　]+)[（(【\[]?\s*(?:译者?注|譯者?注|译者|譯者|注释|註釋|注|註|PS)\s*[：:]')


def _zh_chars(text):
    return bool(SIMP_CHINESE_RE.search(text) or CHINESE_RE.search(text) or simplified(text))


def chinese_line(line):
    if not ZH_KANA_RE.search(line):
        return ("", "CHINESE") if SIMP_CHINESE_RE.search(line) or is_chinese_text(line) else (line, None)
    if ZH_CREDIT_RE.search(line) or (ZH_CREDIT_JA_RE.search(line) and _zh_only_count(RUBY_RE.sub('', line))):
        return "", "CHINESE"
    m = ZH_NOTE_RE.search(line)
    if m and _zh_chars(line[m.start():]):
        rest = line[:m.start()].strip()
        return (rest, "CHINESE_NOTE") if ZH_KANA_RE.search(rest) else ("", "CHINESE")
    bare = RUBY_RE.sub('', line)
    n = _zh_only_count(bare)
    if n >= ZH_ONLY_IN_JAPANESE or (n >= 2 and (CHINESE_RE.search(bare) or '，' in bare)):
        return "", "CHINESE"
    if _zh_sentence(line):
        return "", "CHINESE"
    parts = _ZH_SPLIT_RE.split(line)
    kept = [p for p in parts if not _zh_sentence(p, words=True)]
    if len(kept) < len(parts):
        rest = re.sub('([\\s　])[\\s　]+', r'\1', ''.join(kept)).strip()
        return (rest, "CHINESE_PART") if ZH_KANA_RE.search(rest) else ("", "CHINESE")
    return line, None


ZH_ONLY_IN_JAPANESE = 4


_ZH_QUOTED_RE = re.compile('「[^」]*」|『[^』]*』|“[^”]*”|【[^】]*】')


def _zh_sentence(text, words=False):
    outside = _ZH_QUOTED_RE.sub('', RUBY_RE.sub('', text))
    if ZH_KANA_RE.search(outside):
        return False
    if words:
        return bool(SIMP_CHINESE_RE.search(outside) or CHINESE_RE.search(outside))
    return _zh_chars(outside)


def _zh_only_count(text):
    return sum(1 for ch in _CJK_CHAR_RE.findall(text)
               if SIMP_CHINESE_RE.match(ch) or CHINESE_RE.match(ch) or simplified(ch))


PROMO_URL_RE = re.compile(r'(?:https?://|www\.|(?:\.com|\.cc|\.net|\.org)(?:\b|/))', re.IGNORECASE)
JAPANESE_CHARS_RE = re.compile(r'[\u3040-\u30FF\u4E00-\u9FFF\u3400-\u4DBF\uF900-\uFAFF\U00020000-\U000323AF\U0002F800-\U0002FA1F]')

_EXCLUDED_LOG = []
_WAKATI_LOG = []
_NOTES = []

from aobana.utils import convert_hw_katakana, SUBS_STR_REPLACEMENTS, katakana_to_hiragana, ruby_table, replace_until_fixed
from aobana.utils import CHINESE_RE, simplified

_RE_REPLACEMENTS = [
    (re.compile(r'＠ルビ.*?［(.+?)[｜|](.+?)］＠'), r'\1(\2)'),
    (re.compile(r'ルビ[上下右左]?［([^［］｜\n]+)｜([^［］｜\n]+)］'), r'｜\1(\2)'),
    (re.compile(r'＠幅広［(.*?)］＠'), r'\1'),
    (re.compile(r'(?<![―—])[―—](?![―—])'), '――'),
    (re.compile(r'[・]{3,}'), '…'),
    (re.compile(r'~~~'), '～～～'),
    (re.compile(r'~~'),  '～～'),
    (re.compile(r'~'),   '～'),
    (re.compile(r'⇒[\s　]*$'), ''),
]

HW_DOT_RUN_RE = re.compile('･{3,}')

DASH_RUN_RE = re.compile('[―—⸺]+')
_JP_NEIGHBOUR = '\u3041-\u3096\u309d-\u309f\u30a1-\u30fa\u30fd-\u30ff\u31f0-\u31ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u30fc'
NAME_DOT_RE = re.compile(f'(?<=[{_JP_NEIGHBOUR}])[·‧](?=[{_JP_NEIGHBOUR}])')

def finish_caption(text: str) -> str:
    return NAME_DOT_RE.sub('・', DASH_RUN_RE.sub('――', text))

def _postprocess_sentence(text: str) -> str:
    text = convert_hw_katakana(text)
    text = HW_DOT_RUN_RE.sub('…', text)
    for _ in range(10):
        before = text
        text = replace_until_fixed(text, SUBS_STR_REPLACEMENTS)
        for pattern, dst in _RE_REPLACEMENTS:
            text = pattern.sub(dst, text)
        if text == before:
            break
    return close_unclosed_ruby(text)

UNCLOSED_RUBY_RE = re.compile(r'ルビ[上下右左]?［[^［］｜\n]*｜')

def _load_unclosed_ruby():
    rulings = []
    for _, (tag, base, reading) in ruby_table(paths.RUBY_TABLES_PATH, 'unclosed_ruby'):
        ruby = f'｜{base}({reading})'
        if not RUBY_RE.fullmatch(ruby):
            ruby = f'{base}（{reading}）'
        rulings.append((tag, ruby))
    return sorted(rulings, key=lambda r: -len(r[0]))

_UNCLOSED_RUBY = _load_unclosed_ruby()

def close_unclosed_ruby(text: str) -> str:
    if 'ルビ' not in text:
        return text
    for tag, ruby in _UNCLOSED_RUBY:
        text = text.replace(tag, ruby)
    return text

def clean_ruby_match(m) -> str:
    furi = m.group(3)
    return m.group(0)[:-len(furi) - 2] + '(' + re.sub(r'[ 　]', '', furi) + ')'

def is_paren_only_line(line):
    s = line.strip()
    if re.fullmatch(r'（[^）]+）', s): return True
    if re.fullmatch(r'\([^)]*\)', s): return True
    return False

def bar_ruby_plain(text):
    return RUBY_RE.sub(lambda m: m.group(1) if m.group(1) else m.group(0), text)


_LEADING_PAREN_RE = re.compile(r'\(([^()\n]+)\)')


def opening_tag(prev, curr):
    m = _LEADING_PAREN_RE.match(curr)
    if not m or not prev:
        return curr
    joined = prev + curr
    if any(r.start(3) - 1 == len(prev) and r.group(1) is None for r in RUBY_RE.finditer(joined)):
        return '（' + m.group(1) + '）' + curr[m.end():]
    return curr


def smart_join(lines):
    if not lines: return ''
    lines = [lines[0]] + [opening_tag(prev, curr) for prev, curr in zip(lines, lines[1:])]
    result = [lines[0]]
    for prev, curr in zip(lines, lines[1:]):
        last  = prev[-1] if prev else ''
        tail = [m for m in RUBY_RE.finditer(prev) if m.end() == len(prev) and m.group(1)]
        if tail:
            last = tail[-1].group(1)[-1]
        first = curr.lstrip('｜')[:1]
        if (re.match(r'[\u3040-\u30FF\u4E00-\u9FFF\w]', last)
                and re.match(r'[\u3040-\u30FF\u4E00-\u9FFF\w]', first)
                and last  not in '・―…、。！？）」'
                and first not in '・―…、。！？（「'):
            result.append(' ' + curr)
        else:
            result.append(curr)
    return ''.join(result)

@lru_cache(maxsize=4096)
def _native_reading(base):
    return katakana_to_hiragana(''.join(t.reading_form() for t in
        get_tokenizer().tokenize(base, tokenizer.Tokenizer.SplitMode.C)))


@lru_cache(maxsize=4096)
def _native_prefixes(base, tail):
    tok = get_tokenizer()
    return dictionary_prefixes(base, tail, lambda text: tok.tokenize(text, mode))


def clean_line(line, relpath, native_aliases=None):
    folder = re.split(r"[\\/]", relpath)[0]
    line = BIDI_MARK_RE.sub('', line)
    line = INVISIBLE_RE.sub('', line).replace('\u00a0', ' ')
    line = private_use(CONTROL_RE.sub('', line))
    for entity, char in HTML_ENTITIES:
        line = line.replace(entity, char)
    native_notes = []
    line = normalize_subtitle_ruby(line, lookup=_native_reading, aliases=native_aliases,
                                   notes=native_notes, prefixes=_native_prefixes)
    for kind, base, reading in native_notes:
        _NOTES.append(f'NATIVE_RUBY_{kind.upper()} {relpath}: {base} / {reading}')
    line, chinese = strip_chinese_chunks(line)
    for chunk in chinese:
        _EXCLUDED_LOG.append((folder, "CHINESE_PART", chunk))
    kept, why = chinese_line(line)
    if why:
        _EXCLUDED_LOG.append((folder, why, line))
    if not kept:
        return ""
    line = kept
    if PROMO_URL_RE.search(line) and not JAPANESE_CHARS_RE.search(line):
        _EXCLUDED_LOG.append((folder, "URL_PROMO", line))
        return ""
        
    line = HTML_TAG_RE.sub('', line)
    line = SQUARE_BRACKETS_RE.sub('', line)
    line = re.sub(r'^-\s*(?=[（\(])', '', line)
    result = []
    skip = 0
    for char in line:
        if char == '{': skip += 1
        elif char == '}':
            if skip > 0: skip -= 1
        elif skip == 0: result.append(char)
    cleaned_text = _postprocess_sentence(''.join(result).strip()).strip()
    if UNCLOSED_RUBY_RE.search(cleaned_text):
        _NOTES.append(f"UNCLOSED_RUBY {relpath}: {cleaned_text}")
    return cleaned_text

def is_music_only_line(line):
    s = re.sub(r'[\u202A-\u202E\u200B-\u200F\u2066-\u2069  ]', '', line)
    return bool(re.fullmatch(r'[♪♬♫♩🎵〽〜～]+', s))

def is_line_number(line): return line.strip().isdigit()
def is_timecode(line): return bool(TIMECODE_RE.fullmatch(line.strip())) or bool(TIMECODE_RE.search(line))

def is_punctuation_line(line):
    s = line.strip()
    if bool(re.fullmatch(r'[-–—><\s,]+', s)): return True
    if bool(re.fullmatch(r'[-–—]+[A-Za-z\s]+[-–—]+', s)): return True
    return False

def _merge_group(group_texts):
    merged_lines = []
    paren_buffer = ""
    for text in group_texts:
        if is_paren_only_line(text):
            paren_buffer += text
        else:
            if paren_buffer:
                merged_lines.append(paren_buffer + text)
                paren_buffer = ""
            else:
                merged_lines.append(text)
    if paren_buffer:
        merged_lines.append(paren_buffer)
    return smart_join(merged_lines)

def assess_and_clean_wakati(lines, relpath=""):
    total_spaced = 0
    chunk_ratio_sum = 0.0

    for line in lines:
        spaces = line.count(' ')
        if spaces == 0:
            continue
        chars = len(line) - spaces
        total_spaced += 1
        chunk_ratio_sum += chars / (spaces + 1)

    if total_spaced >= 20:
        mean_chunk_chars = chunk_ratio_sum / total_spaced
        if mean_chunk_chars <= 3.0:
            cleaned_lines = [line.replace(' ', '') for line in lines]
            if relpath:
                _WAKATI_LOG.append((relpath, len(lines), mean_chunk_chars))
            return cleaned_lines, True

    return lines, False

WHOLE_BRACKET_RE = re.compile(r'\[([^\[\]]*)\]')


def bracket_wrapped(srt_content):
    total = wrapped = 0
    for raw in srt_content.splitlines():
        s = raw.strip()
        if not s or is_line_number(s) or is_timecode(s) or not JAPANESE_CHARS_RE.search(s):
            continue
        total += 1
        wrapped += bool(WHOLE_BRACKET_RE.fullmatch(s))
    return wrapped >= 20 and wrapped >= 0.8 * total


def _timecode_follows(lines, i):
    for k in range(i + 1, len(lines)):
        if lines[k]:
            return is_timecode(lines[k])
    return False


def extract_lines_grouped_by_timecode(srt_content, relpath):
    native_aliases = source_readings(srt_content)
    unwrap = bracket_wrapped(srt_content)
    lines = []
    group_texts = []
    current_timecode = None

    def flush():
        if current_timecode is not None and group_texts:
            joined = _merge_group(group_texts)
            if not is_music_only_line(joined):
                plain = bar_ruby_plain(joined)
                if lines and bar_ruby_plain(lines[-1]) == plain and (lines[-1] == joined or plain in (lines[-1], joined)):
                    if len(joined) > len(lines[-1]):
                        lines[-1] = joined
                else:
                    lines.append(joined)

    stripped = [raw.strip() for raw in srt_content.splitlines()]
    for i, line in enumerate(stripped):
        if not line: continue
        if is_line_number(line) and _timecode_follows(stripped, i):
            continue
        if is_timecode(line):
            flush()
            current_timecode = line
            group_texts = []
            continue
        
        if is_punctuation_line(line):
            folder = re.split(r"[\\/]", relpath)[0]
            _EXCLUDED_LOG.append((folder, "SYMBOL/JUNK", line))
            continue
        if unwrap:
            m = WHOLE_BRACKET_RE.fullmatch(line)
            if m:
                line = m.group(1).strip()
                if not line:
                    continue

        cleaned = clean_line(line, relpath, native_aliases)
        if cleaned: group_texts.append(cleaned)

    flush()
    cleaned_lines, _ = assess_and_clean_wakati(lines, relpath)
    return cleaned_lines

SUB_EXTS = MEDIA_EXTS["subs"]
ASS_TAG_RE = re.compile(r'\{[^}]*\}')
ASS_GAIJI_RE = re.compile(r'\[外:[0-9A-Fa-f]+\]')
ASS_TIME_RE = re.compile(r'(-?\d+)\s*:\s*(-?\d+)\s*:\s*(-?\d+)\s*[.:]\s*(-?)(\d+)')
ASS_V4_FIELDS = ['layer', 'start', 'end', 'style', 'name', 'marginl', 'marginr', 'marginv', 'effect', 'text']
ASS_RESET_RE = re.compile(r'\\r([^\\}]*)')
ASS_SEG_RE = re.compile(r'(\{[^}]*\})|([^{]+)')
ASS_RUBY_STYLE_RE = re.compile(r'rubi|ruby|furigana', re.IGNORECASE)
ASS_RUBY_STYLE_SHARE = 0.75
ASS_CREDIT_STYLE_RE = re.compile(r'staff|credit|製作|制作|注釋|注释|^cmt', re.IGNORECASE)
KANA_RE_ASS = re.compile(r'[ぁ-ゖァ-ヺー]')
ASS_KANJI_RE = re.compile(r'[一-鿿々]')
KANA_ONLY_RE = re.compile(r'[ぁ-ゖァ-ヺー\s　]+')
ASS_GLOSS_RE = re.compile(r'[ぁ-ゖァ-ヺー一-鿿々〆]{1,20}(?:\[[^\]]*\])?\s*[:：][\s(\-…~.]*[A-Za-z0-9]')
LATIN_RE = re.compile(r'[A-Za-z]')
ASS_KANA_SHARE = 0.2


def read_subtitle_text(path):
    return subtitle_input.read(path)['text']


def _ass_time(s):
    m = ASS_TIME_RE.match(s.strip())
    if not m:
        return None
    h, mi, se, neg, frac = m.groups()
    ms = int(frac.ljust(3, '0')[:3]) * (-1 if neg else 1)
    return ((int(h) * 60 + int(mi)) * 60 + int(se)) * 1000 + ms


def _ass_shown(start, end):
    return end > max(start, 0)


def _srt_time(ms):
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _ass_last_tag(tags, name):
    found = re.findall(r'\\' + name + r'(-?[\d.]+)', tags)
    if not found:
        return None
    try:
        return subtitle_input.number(found[-1])
    except ValueError:
        return None


def _ass_expand_resets(raw, style, style_geom):
    def expand(m):
        geom = style_geom.get((m[1].strip() or style).lower())
        if not geom:
            return m[0]
        size, scx, scy, spacing = geom
        return f"{m[0]}\\fs{size:g}\\fscx{scx:g}\\fscy{scy:g}\\fsp{spacing:g}"
    return ASS_TAG_RE.sub(lambda b: ASS_RESET_RE.sub(expand, b[0]), raw)


def _ass_text_small(raw, base):
    fs = fscy = None
    seen = False
    for tag, text in ASS_SEG_RE.findall(raw):
        if tag:
            fs = _ass_last_tag(tag, 'fs') if _ass_last_tag(tag, 'fs') is not None else fs
            fscy = _ass_last_tag(tag, 'fscy') if _ass_last_tag(tag, 'fscy') is not None else fscy
            continue
        if not re.sub(r'\\[Nnh]|\s', '', text):
            continue
        seen = True
        if not ((fscy is not None and fscy < 100) or (fs is not None and base and fs < base * 0.75)):
            return False
    return seen


def _ass_event_lines(content, stats=None):
    section = None
    for line in content.splitlines():
        s = line.strip()
        if s.startswith('[') and s.endswith(']'):
            section = s.lower()
        if section == '[events]' and s.lower().startswith('format:'):
            header, marker, value = s.partition('Dialogue:')
            if marker:
                fields = [f.strip().lower() for f in header.partition(':')[2].split(',')]
                standard = fields in (ASS_V4_FIELDS, ['marked'] + ASS_V4_FIELDS[1:])
                parts = value.split(',', len(fields) - 1)
                if standard and len(parts) == len(fields):
                    event = dict(zip(fields, parts))
                    start, end = _ass_time(event['start']), _ass_time(event['end'])
                    if start is not None and end is not None and _ass_shown(start, end):
                        if stats is not None:
                            stats['glued-header-repaired'] += 1
                        yield header
                        yield marker + value
                        continue
        yield line


def _gloss_side(text):
    rest = re.split(r'[:：]', text, maxsplit=1)[1]
    return len(LATIN_RE.findall(rest)) > len(JAPANESE_CHARS_RE.findall(rest))


def parse_ass_events(content, stats=None):
    section, fields, style_size, style_geom = None, None, {}, {}
    style_fields = None
    events = []
    for line in _ass_event_lines(content, stats):
        s = line.strip()
        if s.startswith('[') and s.endswith(']'):
            section = s.lower()
            continue
        if ':' not in s:
            continue
        key, _, value = s.partition(':')
        key = key.strip().lower()
        if section in ('[v4+ styles]', '[v4 styles]') and key in ('format', 'style'):
            if key == 'format':
                style_fields = [f.strip().lower() for f in value.split(',')]
            elif style_fields:
                vals = [v.strip() for v in value.split(',')]
                row = dict(zip(style_fields, vals))
                try:
                    name = row.get('name', '').lower()
                    style_size[name] = float(row.get('fontsize', ''))
                    style_geom[name] = (style_size[name], float(row.get('scalex', 100) or 100),
                                        float(row.get('scaley', 100) or 100), float(row.get('spacing', 0) or 0))
                except ValueError:
                    pass
        elif section == '[events]' and key == 'format':
            fields = [f.strip().lower() for f in value.split(',')]
        elif key == 'dialogue' and (section == '[events]' or not fields):
            use = fields or ASS_V4_FIELDS
            parts = value.split(',', len(use) - 1)
            if len(parts) < len(use):
                continue
            ev = dict(zip(use, parts))
            start, end = _ass_time(ev.get('start', '')), _ass_time(ev.get('end', ''))
            if start is None or end is None or end <= 0:
                if stats is not None:
                    stats['bad-time' if start is None or end is None else 'before-start'] += 1
                continue
            if not _ass_shown(start, end):
                if stats is not None:
                    stats['zero-duration'] += 1
                continue
            start = max(start, 0)
            raw = ev.get('text', '')
            if '\\r' in raw:
                raw = _ass_expand_resets(raw, ev.get('style', '').strip(), style_geom)
            tags = ''.join(ASS_TAG_RE.findall(raw))
            text = ASS_TAG_RE.sub('', raw)
            text = text.replace('\\N', '\n').replace('\\n', '\n').replace('\\h', ' ')
            text = ASS_GAIJI_RE.sub('', text)
            text = '\n'.join(t.strip() for t in text.split('\n') if t.strip())
            events.append({'start': start, 'end': end, 'raw': raw, 'tags': tags,
                           'style': ev.get('style', '').strip(), 'text': text, 'drop': None})

    cjk, kana = {}, {}
    for ev in events:
        st = ev['style'].lower()
        if JAPANESE_CHARS_RE.search(ev['text']):
            cjk[st] = cjk.get(st, 0) + 1
            if KANA_RE_ASS.search(ev['text']):
                kana[st] = kana.get(st, 0) + 1
    japanese = {st for st, n in cjk.items() if kana.get(st, 0) / n >= ASS_KANA_SHARE}
    with_kanji = collections.Counter(ev['style'].lower() for ev in events if ASS_KANJI_RE.search(ev['text']))
    main = max((st for st in japanese if st in style_size), key=lambda st: (with_kanji[st], style_size[st]), default=None)
    largest = style_size[main] if main else None

    for ev in events:
        st, text, tags = ev['style'].lower(), ev['text'], ev['tags']
        p = _ass_last_tag(tags, 'p')
        base = style_size.get(st) or style_size.get('*' + st) or style_size.get('default')
        small = _ass_text_small(ev['raw'], base)
        if p:
            ev['drop'] = 'drawing'
        elif not text:
            ev['drop'] = 'empty'
        elif (ASS_RUBY_STYLE_RE.search(st)
              and (largest is None or st not in style_size or style_size[st] < largest * ASS_RUBY_STYLE_SHARE)):
            ev['drop'] = 'ruby-style'
        elif small and KANA_ONLY_RE.fullmatch(text):
            ev['drop'] = 'ruby-small'
        elif ASS_CREDIT_STYLE_RE.search(st):
            ev['drop'] = 'credits'
        elif st not in japanese:
            ev['drop'] = 'not-japanese-style'
        elif not JAPANESE_CHARS_RE.search(text):
            ev['drop'] = 'no-japanese'
        elif ASS_GLOSS_RE.match(text) and _gloss_side(text):
            ev['drop'] = 'gloss'
        if stats is not None:
            stats[ev['drop'] or 'kept'] += 1
    if any(ev['drop'] == 'ruby-style' and ev['raw'].count('\\pos(') > 1 for ev in events):
        from aobana.indexing import ass_ruby
        ass_ruby.split_caption_rows(events, stats)
    return events


def ass_to_srt(content, stats=None, ev=None):
    events = parse_ass_events(content, stats)
    if any(ev['drop'] in ('ruby-small', 'ruby-style') for ev in events):
        from aobana.indexing import ass_ruby
        ass_ruby.attach(events, content, ev=ev, stats=stats)
    groups = {}
    for e in events:
        if e['drop']:
            continue
        texts = groups.setdefault((e['start'], e['end']), [])
        same = [n for n, t in enumerate(texts) if bar_ruby_plain(t) == bar_ruby_plain(e['text'])]
        if not same:
            texts.append(e['text'])
        elif len(e['text']) > len(texts[same[0]]):
            texts[same[0]] = e['text']
    out = []
    for n, ((start, end), texts) in enumerate(sorted(groups.items(), key=lambda kv: kv[0]), 1):
        out.append(f"{n}\n{_srt_time(start)} --> {_srt_time(end)}\n" + '\n'.join(texts) + "\n")
    return '\n'.join(out)

def get_clean_text_for_mecab(line: str) -> str:
    return RUBY_RE.sub(r'\1\2', line)


def analyze_with_sudachi(clean_text: str):
    return analyze_tokens(clean_text)[:2]


def analyze_tokens(clean_text: str):
    base_forms = []
    readings = []
    surfaces = []
    for word in get_tokenizer().tokenize(clean_text, mode):
        base_forms.append(word.normalized_form())
        surfaces.append(word.surface())
        
        kana = word.reading_form()
        if kana:
            readings.append(katakana_to_hiragana(kana))
        else:
            readings.append(word.surface())
            
    return " ".join(base_forms), " ".join(readings), token_lengths_blob(surfaces)

def compute_file_hash(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            control.check_stop()
            h.update(chunk)
    return h.hexdigest()

def kept_lines(path, relpath):
    return parse_subtitle(path, relpath)[0]


def parse_subtitle(path, relpath):
    info = subtitle_input.read(path)
    content = info['text']
    info['native_ruby'] = has_native_ruby(content)
    if info['format'] == 'ass':
        content = ass_to_srt(content)
    note_start = len(_NOTES)
    lines = [finish_caption(line) for line in extract_lines_grouped_by_timecode(content, relpath)]
    info['native_ruby_unresolved'] = sum(note.startswith('NATIVE_RUBY_') and not note.startswith('NATIVE_RUBY_LEFT_RB')
                                         for note in _NOTES[note_start:])
    if not any(JAPANESE_CHARS_RE.search(line) for line in lines):
        lines = []
    info['status'] = 'readable' if lines else 'no_japanese'
    for warning in info['warnings']:
        _NOTES.append(f"WARNING {relpath}: {warning}")
    if not lines:
        _NOTES.append(f"EMPTY {relpath}: no Japanese dialogue")
    return lines, info


def index_rows(flat_lines, relpath):
    rows = []
    for i, line in enumerate(flat_lines):
        if i % 128 == 0:
            control.check_stop()
        clean_text = fold_compat(get_clean_text_for_mecab(line))
        if len(clean_text.encode('utf-8')) > SUDACHI_MAX_BYTES:
            _EXCLUDED_LOG.append((re.split(r"[\\/]", relpath)[0], "TOO_LONG", clean_text[:200]))
            _NOTES.append(f"TOO_LONG {relpath}: {len(clean_text.encode('utf-8'))} bytes")
            continue
        base_forms, readings, lens = analyze_tokens(clean_text)

        extracted_rubies = [m[2] for m in RUBY_RE.findall(line)]
        if extracted_rubies:
            base_forms, readings = ruby_index_extras(line, RUBY_RE, base_forms, readings)
            line = RUBY_RE.sub(clean_ruby_match, line)

        rows.append((line, clean_text, base_forms, readings, lens))
    return rows


def _prepare(job):
    path, relpath, known_hash = job
    _EXCLUDED_LOG.clear()
    _WAKATI_LOG.clear()
    _NOTES.clear()
    try:
        file_hash = compute_file_hash(path)
        if file_hash == known_hash:
            return ('same', relpath, file_hash, None)
        rows = [r + (stored_display_length(r[0], "subs"), kanji_table.tokens(r[1]))
                for r in index_rows(kept_lines(path, relpath), relpath)]
    except Exception as e:
        return ('error', relpath, None, f"{type(e).__name__}: {e}")
    return ('rows', relpath, file_hash, (rows, list(_EXCLUDED_LOG), list(_WAKATI_LOG), list(_NOTES)))


COMMIT_EVERY_FILES = 200
COMMIT_EVERY_SECONDS = 20


from aobana.indexing import run_control as control, source_ranges, kanji_table, rebuild as rebuilding
from aobana.indexing.preparation import prepare_changed

def build_lexicon(conn, top):
    if top and not has_ruby_lexicon(conn):
        emit("phase", "LEXICON building the ruby lexicon table (once, reads the whole index)...", phase="lexicon")
    ensure_ruby_lexicon(conn, "subtitles", "subs", paths.index_workers())


@control.owned(lambda: DB_PATH)
def build_tables():
    say(f"Building the subtitle index's tables ({DB_PATH})...")
    with control.connection(DB_PATH) as conn:
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'subtitles'").fetchone() is None:
            say("Tables ready: no subtitle index yet.")
            return
        control.phase('migration')
        if not source_ranges.ensure(conn, stop_requested, control.CURRENT.publish):
            raise control.Stopped()
        top = conn.execute("SELECT rowid FROM subtitles ORDER BY rowid DESC LIMIT 1").fetchone()
        if top and not has_line_lengths(conn):
            emit("phase", "LENGTHS building the display-length table (once, reads the whole index)...", phase="lengths")
        ensure_line_lengths(conn, DB_PATH, "subtitles", "subs", paths.index_workers())
        if stop_requested():
            emit("stopped", "STOPPED")
            return
        control.check_stop()
        build_lexicon(conn, top)
        control.check_stop()
        kanji_table.build(conn, "subtitles")
        control.check_stop()
    say("Tables ready.")


@control.owned(lambda: DB_PATH)
def run_indexer(force=False, outdated=False, allow_removal=False, rebuild=False):
    say(f"Starting indexer on {ROOT_DIR} (force={force}, outdated={outdated}, rebuild={rebuild})...")
    roots = paths.index_roots('subs', ROOT_DIR, paths.media_roots('subs'))
    _EXCLUDED_LOG.clear()
    _WAKATI_LOG.clear()
    if ROOT_DIR is None:
        emit("root_not_set", "ROOT_NOT_SET subs", media="subs")
        say("No subtitle folder is set (Library tab). Nothing was changed.")
        return
    if not paths.media_enabled("subs"):
        say("Subtitles are off in Settings. Nothing was changed.")
        return
    if any(not os.path.isdir(root) for root in roots):
        missing = next(root for root in roots if not os.path.isdir(root))
        emit("root_missing", f"ROOT_MISSING {missing}", folder=missing)
        say("Indexing aborted: the subtitle folder does not exist. Nothing was changed.")
        return
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    excluded = control.StreamLog(os.path.join(paths.logs_dir(), 'excluded_lines.txt'),
                                 lambda r: f'[{r[0]}] [{r[1]}] {r[2]}')
    wakati = control.StreamLog(os.path.join(paths.logs_dir(), 'wakati_normalized.txt'),
                               lambda r: f'[{r[0]}] {r[1]} lines normalized (mean chunk: {r[2]:.2f} chars)')

    db, old_files, failed_keys, result = DB_PATH, {}, [], None
    if rebuild:
        old_files = rebuilding.old_sources(DB_PATH)
        db = rebuilding.path(DB_PATH)
        rebuilding.discard(DB_PATH)
        say(f"REBUILD a new index beside the old one ({len(old_files)} files indexed)")
    with control.connection(db) as conn:
        conn.row_factory = sqlite3.Row

        forced_pending = None
        if force:
            from aobana.indexing import pending_reindex
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='sources'").fetchone():
                forced_pending = pending_reindex.validated(conn)
        if force:
            say("Force rebuild requested. Dropping existing tables...")
            conn.execute("DROP TABLE IF EXISTS subtitles")
            conn.execute("DROP TABLE IF EXISTS line_lengths")
            conn.execute("DROP TABLE IF EXISTS token_lengths")
            conn.execute("DROP TABLE IF EXISTS ruby_lexicon")
            conn.execute("DROP TABLE IF EXISTS sources")
            conn.execute("DROP TABLE IF EXISTS source_ranges")
            conn.execute("DROP TABLE IF EXISTS _source_range_checkpoint")
            conn.execute("DROP TABLE IF EXISTS _source_ranges_stage")
            conn.execute("DELETE FROM meta WHERE k='source_ranges_version'") if conn.execute("SELECT 1 FROM sqlite_master WHERE name='meta'").fetchone() else None
            kanji_table.drop(conn, "subtitles")
            conn.commit()

        conn.execute('''
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                relpath TEXT UNIQUE NOT NULL,
                file_hash TEXT NOT NULL,
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.execute('''
            CREATE VIRTUAL TABLE IF NOT EXISTS subtitles USING fts5(
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
        report_outdated(conn, 'subs')
        conn.commit()
        cur = conn.execute("SELECT id, relpath, file_hash, index_format FROM sources")
        existing_files = {name_key(row['relpath']): {'id': row['id'], 'name': row['relpath'], 'hash': None if outdated and is_outdated('subs', row['relpath'], row['index_format']) else row['file_hash']}
                          for row in cur}
        pending_doc, pending_jobs = None, []
        if not force and not rebuild:
            from aobana.indexing import pending_reindex
            pending_doc, pending_jobs = pending_reindex.validated(conn)
        elif forced_pending:
            pending_doc, pending_jobs = forced_pending
        deleted_rows = inserted_rows = 0
        control.phase('migration')
        if not source_ranges.ensure(conn, stop_requested, control.CURRENT.publish):
            raise control.Stopped()
        top = conn.execute("SELECT rowid FROM subtitles ORDER BY rowid DESC LIMIT 1").fetchone()
        if top and not has_line_lengths(conn):
            emit("phase", "LENGTHS building the display-length table (once, reads the whole index)...", phase="lengths")
        ensure_line_lengths(conn, db, "subtitles", "subs", paths.index_workers())
        lengths = has_line_lengths(conn)
        control.check_stop()
        build_lexicon(conn, top)
        control.check_stop()
        lexicon = has_ruby_lexicon(conn)
        kanji = kanji_table.build(conn, "subtitles")
        control.check_stop()
        floor = top[0] if top else 0
        next_rowid = floor + 1
        def flush():
            control.check_stop()
            conn.commit()
            if pending_doc and pending_commits:
                pending_reindex.committed(pending_doc,pending_commits)
                pending_commits.clear()
            control.committed(new_or_updated, skipped, removed)

        pending_names = {name_key(job[1]) for job in pending_jobs}
        pending_commits = set()
        removed = 0
        current_disk_files = set()
        new_or_updated = 0
        skipped = 0
        failed = 0

        srt_paths, ignored = [], 0
        control.phase('traversal')
        roots_by_path = {}
        from aobana.utils import media_walk_roots
        for source_root, dirpath, kept, other in media_walk_roots(roots, "subs"):
            control.check_stop()
            ignored += other
            srt_paths.extend((dirpath, fname) for fname in kept)
            roots_by_path.update({os.path.join(dirpath, fname): source_root for fname in kept})
        if ignored:
            emit("ignored_other", f"IGNORED_OTHER {ignored}", count=ignored)
        emit("total", f"TOTAL {len(srt_paths)}", quiet=True, total=len(srt_paths))

        filtered = filtered_names(paths.filtered_list(), "subs")
        jobs, n_filtered = [], 0
        for dirpath, fname in sorted(srt_paths):
            control.check_stop()
            path = os.path.join(dirpath, fname)
            relpath = sub_relpath(path, roots_by_path[path])
            key = name_key(relpath)
            if key in filtered:
                n_filtered += 1
                continue
            if key in current_disk_files:
                emit("skipped_clash", f"SKIPPED_CLASH {fname}", file=fname)
                continue
            current_disk_files.add(key)
            jobs.append((path, relpath, None if key in pending_names else existing_files.get(key, {}).get('hash')))
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
                if old and name_key(relpath) not in pending_names:
                    conn.execute("UPDATE sources SET file_hash = '' WHERE id = ?", (old['id'],))
                failed += 1
                if rebuilding.transient(payload):
                    failed_keys.append(name_key(relpath))
                emit("failed", f"FAILED {relpath}: {payload}", file=relpath, error=str(payload))
                continue
            control.phase('writing', n-1, len(jobs))
            rows, file_excluded, file_wakati, notes = payload
            rows = list(rows)
            excluded.extend(file_excluded)
            wakati.extend(file_wakati)
            for note in notes:
                say(note)
            if not meta_written:
                write_tokenizer_meta(conn, 1)
                meta_written = True
            if old:
                source_id = old['id']
                deleted_rows += source_ranges.delete(conn, source_id)
                if lexicon:
                    drop_ruby_lexicon(conn, [source_id])
                conn.execute("UPDATE sources SET relpath = ?, file_hash = ?, indexed_at = ?, index_format = ? WHERE id = ?",
                             (relpath, file_hash, datetime.now().isoformat(' '), INDEX_FORMAT['subs'], source_id))
            else:
                cur = conn.execute("INSERT INTO sources (relpath, file_hash, index_format) VALUES (?, ?, ?)",
                                   (relpath, file_hash, INDEX_FORMAT['subs']))
                source_id = cur.lastrowid
            new_or_updated += 1
            inserted_rows += conn.executemany(
                "INSERT INTO subtitles(rowid, source_id, file, line, clean_text, base_forms, readings) VALUES (?, ?, ?, ?, ?, ?, ?);",
                ((next_rowid + i, source_id, relpath) + r[:4] for i, r in enumerate(rows))
            ).rowcount
            if lengths:
                write_line_lengths(conn, ((next_rowid + i, r[5]) for i, r in enumerate(rows)), "subs", computed=True)
            write_token_lengths(conn, ((next_rowid + i, r[4]) for i, r in enumerate(rows)))
            if kanji:
                kanji_table.write(conn, "subtitles", ((next_rowid + i, r[6]) for i, r in enumerate(rows)), computed=True)
            if lexicon:
                write_ruby_lexicon(conn, "subs", ((source_id, relpath, r[0]) for r in rows))
            source_ranges.record(conn, source_id, next_rowid, len(rows))
            next_rowid += len(rows)
            say(f"Indexed: {relpath}")
            if name_key(relpath) in pending_names:
                pending_commits.add(relpath)
            pending += 1
            if pending >= COMMIT_EVERY_FILES or time.monotonic() - last_commit >= COMMIT_EVERY_SECONDS:
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
            deleted_rows += source_ranges.delete(conn, source_id)
            conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
            if lexicon:
                drop_ruby_lexicon(conn, [source_id])
            removed += 1
            removal_pending += 1
            control.CURRENT.publish(phase='removals', phase_done=removed, phase_total=len(deleted_files))
            if removal_pending >= COMMIT_EVERY_FILES or time.monotonic() - removal_time >= COMMIT_EVERY_SECONDS:
                flush()
                removal_pending, removal_time = 0, time.monotonic()
            say(f"Removed {'filtered' if relpath in filtered else 'deleted'} file: {relpath}")

        if rebuild and not stopped:
            gone, held = held_removals(len(old_files), set(old_files) - current_disk_files, filtered, allow_removal)
            removed = len(gone)
            why = rebuilding.refused(old_files, failed_keys, held)
            result = 'refused' if why else 'rebuilt'
            if why:
                say(f"REBUILD_REFUSED {why}: the old index is kept and updated instead.")

        if pending_doc:
            pending_commits.update(i['name'] for i in pending_doc['items'] if name_key(i['name']) in filtered)
        flush()

        ident = write_tokenizer_meta(conn, 0)
        if new_or_updated:
            say(f"Tokenizer: SudachiDict-core {ident['sudachidict_version']} "
                  f"({ident['dictionary_format']}), SudachiPy {ident['sudachipy_version']}, "
                  f"system.dic {ident['system_dic_sha256'][:12]}")

        flush()
        if stopped:
            emit("stopped", "STOPPED")
        else:
            compact_if_worth(conn, "subtitles", deleted_rows, inserted_rows)

    excluded.close()
    wakati.close()

    if rebuild:
        conn.close()
        if result == 'rebuilt':
            from aobana.indexing import pending_reindex
            doc = pending_reindex.load()
            pending_reindex.committed(doc, {i['name'] for i in doc['items']})
            open(rebuilding.done_path(DB_PATH), 'w').close()
        else:
            rebuilding.discard(DB_PATH)
        if result == 'refused':
            return result

    emit("summary", f"Indexing complete! Skipped {skipped} unchanged files. Indexed {new_or_updated} new/updated files. Removed {removed} deleted files."
         + (f" Failed {failed}." if failed else ""),
         unchanged=skipped, indexed=new_or_updated, removed=removed, failed=failed)
    return result

if __name__ == "__main__":
    import sys
    from aobana.indexing.process_tree import cli_owner
    cli_owner('aobana.indexing.indexer')
    start_output()
    force_rebuild = "--force" in sys.argv
    if "--tables" in sys.argv:
        if os.path.exists(DB_PATH):
            build_tables()
        sys.exit(0)
    if rebuilding.FLAG in sys.argv:
        rebuilding.main(run_indexer, DB_PATH, sys.argv, ALLOW_REMOVAL_FLAG in sys.argv)
    else:
        run_indexer(force=force_rebuild, outdated="--outdated" in sys.argv, allow_removal=ALLOW_REMOVAL_FLAG in sys.argv)
