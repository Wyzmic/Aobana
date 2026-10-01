import functools
import hashlib
import json
import os
import re
import shutil
import tempfile
import sqlite3
import sys
import unicodedata
from datetime import datetime

_HW_DAKU_MAP = {
    'ｶﾞ': 'ガ', 'ｷﾞ': 'ギ', 'ｸﾞ': 'グ', 'ｹﾞ': 'ゲ', 'ｺﾞ': 'ゴ',
    'ｻﾞ': 'ザ', 'ｼﾞ': 'ジ', 'ｽﾞ': 'ズ', 'ｾﾞ': 'ゼ', 'ｿﾞ': 'ゾ',
    'ﾀﾞ': 'ダ', 'ﾁﾞ': 'ヂ', 'ﾂﾞ': 'ヅ', 'ﾃﾞ': 'デ', 'ﾄﾞ': 'ド',
    'ﾊﾞ': 'バ', 'ﾋﾞ': 'ビ', 'ﾌﾞ': 'ブ', 'ﾍﾞ': 'ベ', 'ﾎﾞ': 'ボ',
    'ﾊﾟ': 'パ', 'ﾋﾟ': 'ピ', 'ﾌﾟ': 'プ', 'ﾍﾟ': 'ペ', 'ﾎﾟ': 'ポ',
    'ｳﾞ': 'ヴ'
}

_HW_MAP = str.maketrans({
    'ｧ': 'ァ', 'ｱ': 'ア', 'ｨ': 'ィ', 'ｲ': 'イ', 'ｩ': 'ゥ', 'ｳ': 'ウ',
    'ｪ': 'ェ', 'ｴ': 'エ', 'ｫ': 'ォ', 'ｵ': 'オ', 'ｶ': 'カ', 'ｷ': 'キ',
    'ｸ': 'ク', 'ｹ': 'ケ', 'ｺ': 'コ', 'ｻ': 'サ', 'ｼ': 'シ', 'ｽ': 'ス',
    'ｾ': 'セ', 'ｿ': 'ソ', 'ﾀ': 'タ', 'ﾁ': 'チ', 'ｯ': 'ッ', 'ﾂ': 'ツ',
    'ﾃ': 'テ', 'ﾄ': 'ト', 'ﾅ': 'ナ', 'ﾆ': 'ニ', 'ﾇ': 'ヌ', 'ﾈ': 'ネ',
    'ﾉ': 'ノ', 'ﾊ': 'ハ', 'ﾋ': 'ヒ', 'ﾌ': 'フ', 'ﾍ': 'ヘ', 'ﾎ': 'ホ',
    'ﾏ': 'マ', 'ﾐ': 'ミ', 'ﾑ': 'ム', 'ﾒ': 'メ', 'ﾓ': 'モ', 'ｬ': 'ャ',
    'ﾔ': 'ヤ', 'ｭ': 'ュ', 'ﾕ': 'ユ', 'ｮ': 'ョ', 'ﾖ': 'ヨ', 'ﾗ': 'ラ',
    'ﾘ': 'リ', 'ﾙ': 'ル', 'ﾚ': 'レ', 'ﾛ': 'ロ', 'ﾜ': 'ワ', 'ｦ': 'ヲ',
    'ﾝ': 'ン', 'ｰ': 'ー', 'ﾞ': '゛', 'ﾟ': '゜'
})

def convert_hw_katakana(text: str) -> str:
    for hw, fw in _HW_DAKU_MAP.items():
        text = text.replace(hw, fw)
    return text.translate(_HW_MAP)

KANA_RE = r'[\u3040-\u309F\u30A0-\u30FF\u31F0-\u31FF\uFF65-\uFF9F\u3031-\u3035\U0001B000-\U0001B16Fa-zA-Z0-9ａ-ｚＡ-Ｚ０-９ー・･ﾞﾟﾞ゛゜.･･\s\-/／＼]+'
KANJI_CHARS = r"\u4E00-\u9FFF\u3400-\u4DBF\uF900-\uFAFF\U00020000-\U000323AF\U0002F800-\U0002FA1F\u3005\U0001B000-\U0001B16F"
KANJI_PATTERN = rf"[{KANJI_CHARS}０-９0-9]+[\u3040-\u309F]*"
ALPHA_CHARS = r"a-zA-Zａ-ｚＡ-Ｚ0-9０-９α-ωΑ-Ω\'\.\u00C0-\u024F\u2160-\u217F"
ALPHA_PATTERN = rf"[{ALPHA_CHARS}]+(?:[ \t\-　]+[{ALPHA_CHARS}]+)*"
RUBY_BASE_RE = rf"(?:{KANJI_PATTERN}|{ALPHA_PATTERN})"
_SPACED_KANJI_BASE = rf"[{KANJI_CHARS}]+(?:[ 　][{KANJI_CHARS}]+)+"
RUBY_RE = re.compile(rf'(?:[｜|]({_SPACED_KANJI_BASE}|[^()\n\r\t 　]+?)|({RUBY_BASE_RE}))\(({KANA_RE})\)')
BOOK_RUBY_RE = re.compile(rf'(?:｜([^()｜\n\r\t]+?)|(?!)({RUBY_BASE_RE}))\(({KANA_RE})\)')


def ruby_re_for(media: str):
    return BOOK_RUBY_RE if media in ('epub', 'manga') else RUBY_RE


MEDIA_NAMES = ('subs', 'epub', 'manga')


def parse_media(value):
    if not value or ',' not in value:
        return value
    names = [m for m in MEDIA_NAMES if m in {p.strip().lower() for p in value.split(',')}]
    if not names:
        return value
    return 'all' if len(names) == len(MEDIA_NAMES) else ','.join(names)


def media_has(media, name):
    return media == 'all' or name in media.split(',')


def media_wanted(media):
    return tuple(m for m in MEDIA_NAMES if media_has(media, m))


BOOK_DISPLAY_RUBY_RE = re.compile(
    rf'(?:｜([^()｜\n\r\t]+?)\(|([{KANJI_CHARS}]+)[（(])({KANA_RE})[）)]')
GLOSS_KANA_RE = re.compile(r'[ぁ-ゖァ-ヺー・]+(?:[ 　]+[ぁ-ゖァ-ヺー・]+)*')


class GlossRuby:

    def __init__(self, accept):
        self.accept = accept

    def ok(self, m) -> bool:
        whole = m.group(0)
        if m.group(1) is not None:
            return whole.endswith(')')
        opened = whole[len(m.group(2))]
        return (whole[-1] == (')' if opened == '(' else '）')
                and not (m.start() and m.string[m.start() - 1] == '｜')
                and GLOSS_KANA_RE.fullmatch(m.group(3)) is not None
                and self.accept(m))

    def finditer(self, text):
        return (m for m in BOOK_DISPLAY_RUBY_RE.finditer(text) if self.ok(m))

    def sub(self, repl, text):
        def one(m):
            if not self.ok(m):
                return m.group(0)
            return m.expand(repl) if isinstance(repl, str) else repl(m)
        return BOOK_DISPLAY_RUBY_RE.sub(one, text)


_KANJI_WORD_RE = re.compile(rf'[{KANJI_CHARS}]{{2,}}')


def ruby_index_extras(line: str, regex, base_forms: str, readings: str):
    matches = [m for m in regex.finditer(line) if len(m.group(3).strip()) >= 2]
    if not matches:
        return base_forms, readings
    normalized = [re.sub(r'[ 　]', '', m.group(3)).replace('･', '・') for m in matches]
    readings = readings + " " + " ".join(katakana_to_hiragana(r) for r in normalized)
    base_forms = base_forms + " " + " ".join(normalized)
    bases = ruby_index_bases(matches, base_forms)
    if bases:
        base_forms = base_forms + " " + " ".join(bases)
    return base_forms, readings


def ruby_index_bases(matches, base_forms: str) -> list:
    tokens = set(base_forms.split())
    bases = []
    for m in matches:
        base = re.sub(r'[ 　]', '', m.group(1) or m.group(2))
        if _KANJI_WORD_RE.fullmatch(base) and base not in tokens:
            tokens.add(base)
            bases.append(base)
    return bases

SUBS_STR_REPLACEMENTS = [
    (">>", " "),
    ("?　", "？"), ("? ",  "？"), ("?",   "？"),
    ("？　", "？"), ("？ ", "？"),
    ("!　", "！"), ("! ",  "！"), ("!",   "！"),
    ("！　", "！"), ("！ ", "！"),
    ("｡", "。"), ("。　", "。"), ("。 ", "。"), (" 。", "。"),
    ("､", "、"), ("、 ", "、"), (" 、", "、"),
    ("……",    "…"), ("...",   "…"), ("････", "…"), ("･･･", "…"), ("･･", "："), ("…　",   "…"),
    ("… ",    "…"), (" …",    "…"), ("　…",   "…"),
    ("➡　", "――"), ("➡ ",  "――"), ("➡",   "――"),
    ("➨　", "――"), ("➨ ",  "――"), ("➨",   "――"),
    (" ―",  "――"), ("　―", "――"), (" —",  "――"), ("　—", "――"),
    ("｢",      "「"), ("｣",     "」"), ("「　",  "「"),
    (" 「",   "「"), ("」　",  "」"), ("」 ",   "」"),
    ("　(", "("), (" ( ", "("), ("( ",  "("), ("(　", "("),
    (" )",  ")"), ("　)", ")"), ("[", "（"), ("]", "）"),
    ("<",    "＜"), (">",    "＞"), ("＞ ",  "＞"), ("＞　", "＞"),
    ("＜ ",  "＜"), ("＜　", "＜"),
    ("）　", "）"), ("） ",  "）"), ("　（", "（"), (" （",  "（"),
    ("~ ",  "~"), (" ~",  "~"),
    ("〜",  "～"),
    (" : ", "："), (":",   "："),
    (" ･ ", "･"), (" ･",  "･"), ("･ ",  "･"), ("･",   "・"),
    (" ・","・"), ("・ ","・"),
    ('"',   '”'), ("→",   ""),
]

EPUB_STR_REPLACEMENTS = [
    ("｢", "「"), ("｣", "」"),
    ("｡", "。"), ("､", "、"),
    ("･", "・"),

    ("〜", "～"),

    ("？　", "？"), ("？ ", "？"),
    ("！　", "！"), ("！ ", "！"),
    ("。　", "。"), ("。 ", "。"), (" 。", "。"),
    ("、　", "、"), ("、 ", "、"), (" 、", "、"),
    ("「　", "「"), (" 「", "「"), ("」　", "」"), ("」 ", "」"),
    ("『　", "『"), (" 『", "『"), ("』　", "』"), ("』 ", "』"),
    ("（　", "（"), (" （", "（"), ("）　", "）"), ("） ", "）"),
    ("　（", "（"), ("　）", "）"),
    ("〈　", "〈"), (" 〈", "〈"), ("〉　", "〉"), ("〉 ", "〉"),
    ("《　", "《"), (" 《", "《"), ("》　", "》"), ("》 ", "》"),
    ("【　", "【"), (" 【", "【"), ("】　", "】"), ("】 ", "】"),
    (" ・", "・"), ("・ ", "・"),
    ("~ ", "~"), (" ~", "~"),

    (" ―", "――"), ("　―", "――"), (" —", "――"), ("　—", "――"),

    ("……", "…"),
    ("...", "…"), ("･･･", "…"),
    ("…　", "…"), ("… ", "…"), (" …", "…"), ("　…", "…"),
]

MANGA_STR_REPLACEMENTS = [
    ("〜", "～"),
]
MANGA_RE_REPLACEMENTS = [
    (re.compile(r'．{2,}'), '…'),
    (re.compile(r'…{2,}'), '…'),
    (re.compile(r'^ー+'), '――'),
]


def normalize_manga_text(text: str) -> str:
    for src, dst in MANGA_STR_REPLACEMENTS:
        text = text.replace(src, dst)
    for pattern, dst in MANGA_RE_REPLACEMENTS:
        text = pattern.sub(dst, text)
    return text


def katakana_to_hiragana(text: str) -> str:
    return text.translate(str.maketrans(
        'ァアィイゥウェエォオカガキギクグケゲコゴサザシジスズセゼソゾタダチヂッツヅテデトドナニヌネノハバパヒビピフブプヘベペホボポマミムメモャヤュユョヨラリルレロヮワヰヱヲンヴヵヶ',
        'ぁあぃいぅうぇえぉおかがきぎくぐけげこごさざしじすずせぜそぞただちぢっつづてでとどなにぬねのはばぱひびぴふぶぷへべぺほぼぽまみむめもゃやゅゆょよらりるれろゎわゐゑをんゔゕゖ'
    ))


def normalize_cjk_spacing(text: str) -> str:
    t = text.strip()
    if not t:
        return ""

    t = re.sub(r'[ \t　]+', ' ', t).strip()
    tokens = t.split(' ')
    if len(tokens) <= 1:
        return t

    cjk_single_re = re.compile(r'^[一-鿿぀-ヿ々゠-ヿ0-9０-９]$')

    new_tokens = []
    buf = []

    for tok in tokens:
        if cjk_single_re.match(tok):
            buf.append(tok)
            buf_str = ''.join(buf)
            if re.match(r'^第[一二三四五六七八九十百0-9０-９]+[部章巻節話篇]$', buf_str):
                new_tokens.append(buf_str)
                buf = []
        else:
            if buf:
                new_tokens.append(''.join(buf))
                buf = []
            new_tokens.append(tok)

    if buf:
        new_tokens.append(''.join(buf))

    return ' '.join(new_tokens).strip()


BOOK_SERIES_PREFIXES = [
    r'^國體詳解双書\s*',
    r'^ＮＨＫ出版\s*学びのきほん\s*',
    r'^NHK出版\s*学びのきほん\s*',
    r'^ＮＨＫ\s*「?１００分ｄｅ名著」?\s*ブックス?\s*',
    r'^NHK\s*「?100分de名著」?\s*ブックス?\s*',
    r'^別冊ＮＨＫ１００分de名著\s*',
    r'^別冊NHK100分de名著\s*',
    r'^岩波少年文庫\s*\d*\s*',
    r'^P[\+＋]D\s*BOOKS\s*',
    r'^古典現代語訳叢書\s*',
    r'^ことば選び辞典\s*',
    r'^古典文学の世界\s*',
    r'^日本語シリーズ\s*',
    r'^桑原岩雄著作復刻選\s*',
]
BOOK_BRACKET_VOL_RE = re.compile(
    r"\s*[\(\（\[\［\【\〔〈《<]\s*"
    r"(上|中|下|前|後|前編|中編|後編|前篇|中篇|後篇|上巻|中巻|下巻|冬上|冬下|春・夏|秋|"
    r"[0-9０-９]{1,3}|[一二三四五六七八九十]{1,3}|"
    r"第?[0-9０-９一二三四五六七八九十百]+(?:巻|話|部|編|篇|章|回|冊|集|幕)|"
    r"(?:Vol|Volume|Part)\.?\s*[0-9０-９IVX]+)"
    r"\s*[\)\）\]\］\】\〕〉》>](?![のにをがはとでやもへ歳才代])",
    re.IGNORECASE,
)
BOOK_PUB_KEYWORDS_RE = re.compile(
    r"文庫|新書|ブックス|BOOKS|ノベル|NOVEL|コミックス|COMIC|出版|書房|書店|選書|叢書|シリーズ|"
    r"コレクション|レーベル|ディスカヴァー|Impress|インプレス|NextPublishing|OnDeck|"
    r"限定|特典|SS|イラスト|書き下ろし|書下ろし|電子|版|付|合本|試し読み|無料|記念",
    re.IGNORECASE,
)
BOOK_ANGLE_JUNK_RE = re.compile(r"\s*[〈《<]([^〉》<>]*)[〉》>]", re.IGNORECASE)
BOOK_ANGLE_PUB_RE = re.compile(
    r"文庫|新書|ブックス|BOOKS|ノベル|NOVELS|限定版|特別版|特典版|新装版|改訂版|増補決定版|オールカラー版|完全版|トークメーカー版|電子",
    re.IGNORECASE,
)
BOOK_TRAILING_IMPRINT_RE = re.compile(
    r"\s*(?:PHP文芸文庫|PHP文庫|徳間文庫|えちかわ文庫|プリンセス文庫|ｅマニア文庫|ステイタス文庫|鹿砦社新書|Forest2545新書|スマートブックス)$"
)
BOOK_DANGLING_EDGE_RE = re.compile(r"(?:\s+-\s*$|\s*[:：]\s*$)")
BOOK_UPLOADER_PLACEHOLDERS = frozenset({"Unknown", "unknown", "Yuri Yuru"})
BOOK_PROMO_BRACKET_RE = re.compile(r"音声|DL|付|対応|記念|限定|特典|無料|改訂|新装|完訳|語録|no[\s_]*name", re.IGNORECASE)
BOOK_SWAPPED_TITLE_AUTHOR_FILES = frozenset({
    "[てんのじ村]_難波利三.epub",
    "[大いなる助走]_筒井康隆.epub",
    "[黒パン俘虜記]_胡桃沢耕史.epub",
})
BOOK_AUTHOR_ROLE_RE = re.compile(
    r"(?:[\(\（](?:編|編集|著|訳|監修|原作|イラスト|漫画)[\)\）]|"
    r"[・\s]+(?:編|著|訳|監修)$|"
    r"(?<=編集部)編$|"
    r"(?<=[゠-ヿ])(?:著|訳|編)$)"
)
BOOK_RAW_FILE_CH_RE = re.compile(
    r"^(?:text\d+|part\d+|item\d+|sec\d+|p-\d+|ch\d+|c\d+|section\d+|page\d+)$|\.x?html$",
    re.IGNORECASE,
)
_BOOK_BRACKET = r"[\(\（\[\［\【\〔][^\(\（\[\［\【\〔\)\）\]\］\】\〕]*[\)\）\]\］\】\〕]"


def _angle_tag(m, whole):
    inner = m.group(1).strip()
    if BOOK_ANGLE_PUB_RE.search(inner):
        return ""
    if not m.group(0).lstrip().startswith("<"):
        return m.group(0)
    rest = BOOK_ANGLE_JUNK_RE.sub("", whole[:m.start()] + whole[m.end():])
    key = re.sub(r"[\s「」『』]|シリーズ$", "", inner)
    if key and key in re.sub(r"\s", "", rest):
        return ""
    return m.group(0)


_NUMERIC_REF_RE = re.compile(r"&#(?:(\d{1,7})|[xX]([0-9a-fA-F]{1,6}));")


def unescape_numeric_refs(s: str) -> str:
    def _ch(m):
        n = int(m.group(1)) if m.group(1) else int(m.group(2), 16)
        if n > 0x10FFFF or 0xD800 <= n <= 0xDFFF or n < 0x20:
            return m.group(0)
        return " " if n == 0xA0 else chr(n)
    return _NUMERIC_REF_RE.sub(_ch, s) if s and "&#" in s else s


def clean_book_title(title: str) -> str:
    if not title:
        return ""
    t = unescape_numeric_refs(title).strip()
    for sp in BOOK_SERIES_PREFIXES:
        t = re.sub(sp, "", t, flags=re.IGNORECASE)
    t_vol = BOOK_BRACKET_VOL_RE.sub(
        lambda m: " " + m.group(1) + (" " if re.match(r"\w", m.string[m.end():m.end() + 1]) else ""), t)

    protected = {}

    def _protect(m):
        whole = m.group(0)
        after = t_vol[m.end():]
        if (m.start() > 0 and after and re.match(r"^[のにをがはとでやもへ歳才代]", after)
                and not BOOK_PUB_KEYWORDS_RE.search(whole[1:-1].strip())):
            key = f"__PROT_BRACKET_{len(protected)}__"
            protected[key] = whole
            return key
        return whole

    t = re.sub(_BOOK_BRACKET, _protect, t_vol)
    for _ in range(3):
        t_next = re.sub(_BOOK_BRACKET, "", t)
        if t_next == t:
            break
        t = t_next
    for k, v in protected.items():
        t = t.replace(k, v)

    t = re.sub(r"\s*ビギナーズ・クラシックス\s*日本の古典.*$", "", t)
    t = re.sub(r"\s*古典現代語訳叢書.*$", "", t)
    t = re.sub(r"^\d+\s*新・古文入門", "新・古文入門", t)
    t = BOOK_ANGLE_JUNK_RE.sub(lambda m: _angle_tag(m, t), t)
    t = t.replace("_", " ")
    t = BOOK_TRAILING_IMPRINT_RE.sub("", t)
    t = BOOK_DANGLING_EDGE_RE.sub("", t)
    t = t.replace("/", "／")
    t = re.sub(r"[ \t　]+", " ", t).strip()
    return normalize_cjk_spacing(t)


def _balanced(x):
    return all(
        sum(x.count(o) for o in op) == sum(x.count(c) for c in cl)
        for op, cl in (("(（", ")）"), ("[［【〔", "]］】〕"), ("〈《<", "〉》>"))
    )


def book_title_and_author(epub_path, opf_title, opf_author):
    fname = os.path.basename(epub_path)
    fname_clean = fname[:-5] if fname.lower().endswith(".epub") else fname

    file_author = file_title = ""
    m_bracket = re.match(r"^\[(.*?)\]\s*(.*)$", fname_clean)
    m_dash = re.match(r"^(.*?)\s*-\s*(.*)$", fname_clean)
    if m_bracket:
        file_author = m_bracket.group(1).strip()
        file_title = m_bracket.group(2).strip().lstrip("_")
    elif m_dash and _balanced(m_dash.group(1)):
        file_author = m_dash.group(1).strip()
        file_title = m_dash.group(2).strip()
        if any(BOOK_PUB_KEYWORDS_RE.search(b) for b in re.findall(_BOOK_BRACKET, file_author)):
            file_author, file_title = file_title, file_author
    else:
        file_title = fname_clean

    author = unescape_numeric_refs(opf_author).strip() if opf_author else ""
    if author in BOOK_UPLOADER_PLACEHOLDERS:
        if file_author and not BOOK_PROMO_BRACKET_RE.search(file_author) and fname not in BOOK_SWAPPED_TITLE_AUTHOR_FILES:
            author = file_author.replace("_", " ")
        elif author.lower() == "unknown":
            author = ""
    elif not author and file_author and not BOOK_PROMO_BRACKET_RE.search(file_author):
        author = file_author
    if author:
        author = BOOK_AUTHOR_ROLE_RE.sub("", author).strip() or author
        author = re.sub(r"\s*([／、])\s*", r"\1", author)

    if not opf_title or re.search(r"^\d{4,}_|申請データ|draft|titlepage", opf_title, re.IGNORECASE):
        raw = file_title
    else:
        raw = opf_title if clean_book_title(opf_title) else file_title
    return normalize_cjk_spacing(author), clean_book_title(raw)


SPACED_RUBY_PREV_RE = re.compile(rf"([{KANJI_CHARS}]+)[ 　]$")
_RUBY_SEP = "・･ 　"


def ruby_reading(m) -> str:
    return re.sub(r'[ 　]', '', m.group(3))


def work_folder(file: str) -> str:
    return file.split('\\', 1)[0]


def lexicon_entries(media: str, line: str):
    for m in ruby_re_for(media).finditer(line):
        yield m.group(1) or m.group(2), ruby_reading(m)


def build_ruby_lexicon(rows):
    by_work, corpus = {}, {}
    for work, line in rows:
        for base, r in lexicon_entries(work[0], line):
            by_work.setdefault((work, base), set()).add(r)
            corpus.setdefault(base, set()).add(r)
    return by_work, corpus


RUBY_LEXICON_VERSION = "1"
RUBY_LEXICON_SCHEMA = (
    "CREATE TABLE ruby_lexicon (source_id INTEGER NOT NULL, folder TEXT NOT NULL, base TEXT NOT NULL, "
    "reading TEXT NOT NULL, PRIMARY KEY (base, folder, reading, source_id)) WITHOUT ROWID",
    "CREATE INDEX ruby_lexicon_source ON ruby_lexicon(source_id)",
)


def has_ruby_lexicon(conn) -> bool:
    try:
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'ruby_lexicon'").fetchone() is None:
            return False
        row = conn.execute("SELECT v FROM meta WHERE k = 'ruby_lexicon_version'").fetchone()
        return row is not None and row[0] == RUBY_LEXICON_VERSION
    except sqlite3.Error:
        return False


def lexicon_rows(media, rows):
    out = set()
    for sid, f, line in rows:
        if '(' in line:
            folder = work_folder(f)
            for base, r in lexicon_entries(media, line):
                out.add((sid, folder, base, r))
    return out


def write_ruby_lexicon(conn, media, rows):
    conn.executemany("INSERT OR IGNORE INTO ruby_lexicon VALUES (?, ?, ?, ?)", lexicon_rows(media, rows))


def drop_ruby_lexicon(conn, source_ids):
    conn.executemany("DELETE FROM ruby_lexicon WHERE source_id = ?", [(s,) for s in source_ids])


MEDIA_TABLES = {"subs": "subtitles", "epub": "epubs", "manga": "manga"}


def missing_tables(conn, media) -> list:
    if conn is None:
        return []
    table = MEDIA_TABLES[media]
    try:
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (table,)).fetchone() is None:
            return []
        out = []
        if media == "epub" and not has_chapters(conn):
            out.append("chapters")
        if not has_line_lengths(conn):
            out.append("line_lengths")
        if not has_ruby_lexicon(conn):
            out.append("ruby_lexicon")
        return out
    except sqlite3.Error:
        return []


def ruby_lexicon_drift(conn, table, media):
    have = set(conn.execute("SELECT source_id, folder, base, reading FROM ruby_lexicon"))
    want = lexicon_rows(media, conn.execute(
        f"SELECT source_id, file, line FROM {table} WHERE instr(line, ?) > 0", ('(',)))
    return len(want - have), len(have - want)


def _table_ranges(top, workers):
    if not top:
        return []
    chunk = min(LENGTHS_CHUNK_ROWS, max(10_000, (top + max(1, workers) - 1) // max(1, workers)))
    return [(lo, min(top, lo + chunk - 1)) for lo in range(1, top + 1, chunk)]


def _ruby_chunk(job):
    db_path, table, media, lo, hi, out_path = job
    src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    out = sqlite3.connect(out_path)
    try:
        out.execute("CREATE TABLE r (source_id INTEGER, folder TEXT, base TEXT, reading TEXT, "
                    "PRIMARY KEY (source_id, folder, base, reading)) WITHOUT ROWID")
        batch = set()
        for sid, file, line in src.execute(
                f"SELECT source_id, file, line FROM {table} WHERE rowid BETWEEN ? AND ? "
                "AND instr(line, ?) > 0", (lo, hi, '(')):
            folder = work_folder(file)
            for base, reading in lexicon_entries(media, line):
                batch.add((sid, folder, base, reading))
            if len(batch) >= 1000:
                out.executemany("INSERT OR IGNORE INTO r VALUES (?, ?, ?, ?)", batch)
                batch.clear()
        if batch:
            out.executemany("INSERT OR IGNORE INTO r VALUES (?, ?, ?, ?)", batch)
        out.commit()
    finally:
        out.close()
        src.close()
    return out_path


def ensure_ruby_lexicon(conn, table, media, workers=1) -> bool:
    conn.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
    conn.commit()
    if has_ruby_lexicon(conn):
        return False
    top = conn.execute(f"SELECT rowid FROM {table} ORDER BY rowid DESC LIMIT 1").fetchone()
    db_path = next((row[2] for row in conn.execute("PRAGMA database_list") if row[1] == "main"), "")
    ranges = _table_ranges(top[0], workers) if top else []
    parallel = bool(db_path and len(ranges) > 1 and workers > 1)
    work = None
    parts = []
    try:
        if parallel:
            work = tempfile.mkdtemp(prefix=f".ruby_lexicon-{table}-",
                                    dir=os.path.dirname(os.path.abspath(db_path)))
            jobs = [(db_path, table, media, lo, hi, os.path.join(work, f"{i:06d}.db"))
                    for i, (lo, hi) in enumerate(ranges)]
            actual = min(workers, len(jobs))
            say(f"LEXICON Workers: {actual}")
            running = parallel_map(_ruby_chunk, jobs, actual, ordered=False, stop=stop_requested)
            try:
                for i, part in enumerate(running, 1):
                    parts.append(part)
                    if stop_requested():
                        return False
                    emit("phase", f"LEXICON {i}/{len(jobs)}", phase="lexicon", done=i, total=len(jobs))
            finally:
                running.close()
        if stop_requested():
            return False
        try:
            conn.execute("BEGIN")
            conn.execute("DROP TABLE IF EXISTS ruby_lexicon")
            for sql in RUBY_LEXICON_SCHEMA:
                conn.execute(sql)
            if parallel:
                for part in parts:
                    if stop_requested():
                        raise InterruptedError
                    src = sqlite3.connect(part)
                    try:
                        conn.executemany("INSERT OR IGNORE INTO ruby_lexicon VALUES (?, ?, ?, ?)",
                                         src.execute("SELECT source_id, folder, base, reading FROM r"))
                    finally:
                        src.close()
            else:
                rows = conn.execute(f"SELECT source_id, file, line FROM {table} WHERE instr(line, ?) > 0", ('(',))
                write_ruby_lexicon(conn, media, rows)
            if stop_requested():
                raise InterruptedError
            conn.execute("INSERT OR REPLACE INTO meta (k, v) VALUES ('ruby_lexicon_version', ?)",
                         (RUBY_LEXICON_VERSION,))
            conn.commit()
            return True
        except InterruptedError:
            conn.rollback()
            return False
        except Exception:
            conn.rollback()
            raise
    finally:
        if work:
            shutil.rmtree(work, ignore_errors=True)


def split_spaced_ruby(prev: str, base: str, reading: str, evidence):
    whole = katakana_to_hiragana(reading)
    base_readings, best = None, None
    for r_prev, rank in evidence(prev):
        head = katakana_to_hiragana(r_prev)
        if len(head) < 2 or len(whole) <= len(head) or not whole.startswith(head):
            continue
        r_base = reading[len(head):].lstrip(_RUBY_SEP)
        if not r_base:
            continue
        if base_readings is None:
            base_readings = {katakana_to_hiragana(r) for r, _ in evidence(base)}
        proven = katakana_to_hiragana(r_base) in base_readings
        if len(prev) < 2 and not proven:
            continue
        key = (proven, -rank, len(head))
        if best is None or key > best[0]:
            best = (key, reading[:len(head)], r_base)
    return (best[1], best[2]) if best else None


RUBY_TABLES = {
    "ruby_decisions": ("prev", "base", "reading", "decision"),
    "gloss_names": ("prev", "base", "reading", "decision"),
    "ruby_dict_merge": ("base", "reading"),
    "ruby_whole": ("base", "reading"),
    "ruby_trim": ("base", "reading", "cut"),
    "gloss_ruby": ("base", "reading"),
    "unclosed_ruby": ("tag", "base", "reading"),
    "ass_pairs": ("base", "reading"),
}


@functools.lru_cache(maxsize=4)
def _ruby_tables(path) -> dict:
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for n, row in enumerate(f, 1):
            if row.strip():
                name, *cols = row.rstrip("\n").split("\t")
                out.setdefault(name, []).append((n, cols))
    for name, rows in out.items():
        n, header = rows[0]
        if tuple(header) != RUBY_TABLES.get(name):
            raise ValueError(f"{path}:{n}: table {name!r} has header {header}, want {RUBY_TABLES.get(name)}")
    return out


def ruby_table(path, name) -> list:
    return _ruby_tables(path).get(name, [])[1:]


def load_ruby_decisions(path, table) -> dict:
    out = {}
    for n, (prev, base, reading, decision) in ruby_table(path, table):
        if decision == "B":
            out[(prev, base, reading)] = None
            continue
        r_prev, sep, r_base = decision.partition("|")
        if (not sep or not r_prev or not r_base or not reading.startswith(r_prev)
                or reading[len(r_prev):].lstrip(_RUBY_SEP) != r_base):
            raise ValueError(f"{path}:{n}: {decision!r} does not split {reading!r}")
        out[(prev, base, reading)] = (r_prev, r_base)
    return out


def ruby_merge_key(furi: str) -> str:
    return katakana_to_hiragana("".join(c for c in furi if c not in _RUBY_SEP))


def load_ruby_merges(path, table) -> frozenset:
    return frozenset((base, ruby_merge_key(reading)) for _, (base, reading) in ruby_table(path, table))


def load_ruby_trims(path, table="ruby_trim") -> dict:
    out = {}
    for n, (base, reading, cut) in ruby_table(path, table):
        cut = int(cut)
        if not 0 <= cut < len(base):
            raise ValueError(f"{path}:{n}: cut {cut} leaves nothing of {base!r} under the ruby")
        out[(base, ruby_merge_key(reading))] = cut
    return out


def norm_relpath(path: str, root: str) -> str:
    return unicodedata.normalize("NFC", os.path.relpath(path, root))


def clean_sub_stem(filename: str) -> str:
    if filename.lower().endswith(('.srt', '.ass', '.ssa')):
        filename = filename[:-4]
    filename = re.sub(r'\.(?:ja|jp|jpn|ja-en|ja-jp|jpn-en|jp-en)$', '', filename, flags=re.IGNORECASE)
    filename = re.sub(r'\s*\[[0-9A-Fa-f]{8}\]', '', filename)
    stripped = re.sub(r'^\s*\[[^\]]*\]\s*', '', filename)
    if stripped and not stripped.startswith('['):
        filename = stripped
    return filename


def sub_relpath(path: str, root: str) -> str:
    rel = norm_relpath(path, root)
    if os.sep in rel or (os.altsep and os.altsep in rel):
        return rel
    show = clean_sub_stem(rel).strip(' ._') or rel
    return os.path.join(show, rel)


FILTER_COLUMNS = ("media", "name", "reason", "keep", "date", "origin", "size", "mtime")


def filtered_rows(path: str) -> list:
    rows = []
    try:
        with open(path, encoding="utf-8-sig") as fh:
            for line in fh:
                parts = line.rstrip("\r\n").split("\t")
                if len(parts) < 2 or not parts[1] or parts[0] == "media":
                    continue
                parts += [""] * (len(FILTER_COLUMNS) - len(parts))
                rows.append(dict(zip(FILTER_COLUMNS, parts)))
    except OSError:
        pass
    return rows


def filtered_names(path: str, media: str) -> set:
    return {r["name"] for r in filtered_rows(path) if r["media"] == media}


JSONL_FLAG = "--jsonl"
_JSONL_ENV = "AOBANA_JSONL"
_PROGRESS = os.environ.get("AOBANA_PROGRESS") == "1"
_OUTPUT_READY = False


def start_output():
    if JSONL_FLAG in sys.argv:
        os.environ[_JSONL_ENV] = "1"
    else:
        os.environ.pop(_JSONL_ENV, None)
    _ready_output()


def _ready_output():
    global _OUTPUT_READY
    _OUTPUT_READY = True
    try:
        sys.stdout.reconfigure(encoding="utf-8" if os.environ.get(_JSONL_ENV) == "1" else None,
                               errors="replace")
    except (AttributeError, ValueError):
        pass


def emit(kind: str, text: str, quiet: bool = False, **fields):
    if not _OUTPUT_READY:
        _ready_output()
    if os.environ.get(_JSONL_ENV) == "1":
        print(json.dumps({"type": kind, "text": text, **fields}, ensure_ascii=False), flush=True)
    elif not quiet or _PROGRESS:
        print(text, flush=True)


def say(text: str):
    emit("log", text)


REMOVAL_HOLD_SHARE = 0.5
ALLOW_REMOVAL_FLAG = "--allow-removal"


def held_removals(indexed: int, gone, filtered, allow: bool):
    gone = list(gone)
    missing = [r for r in gone if r not in filtered]
    if allow or not missing or len(missing) <= indexed * REMOVAL_HOLD_SHARE:
        return gone, []
    emit("removal_held", f"REMOVAL_HELD {len(missing)}/{indexed}", gone=len(missing), indexed=indexed)
    return [r for r in gone if r in filtered], missing


def refresh_auto_filtered(path: str, media: str, disk: dict) -> list:
    rows = filtered_rows(path)
    kept = []
    for row in rows:
        if row["media"] != media or row.get("origin") != "auto":
            kept.append(row)
            continue
        file_path = disk.get(row["name"])
        try:
            st = os.stat(file_path) if file_path else None
        except OSError:
            st = None
        if (st is not None and str(st.st_size) == row.get("size")
                and str(st.st_mtime_ns) == row.get("mtime")):
            kept.append(row)
    if len(kept) != len(rows):
        write_filtered_rows(path, kept)
    return kept


def write_filtered_rows(path: str, rows: list):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\t".join(FILTER_COLUMNS) + "\n")
        for r in rows:
            fh.write("\t".join(str(r.get(c, "")).replace("\t", " ").replace("\n", " ")
                               for c in FILTER_COLUMNS) + "\n")
    os.replace(tmp, path)


def append_filtered_rows(path: str, new_rows: list) -> int:
    if not new_rows:
        return 0
    rows = filtered_rows(path)
    have = {(r["media"], r["name"]) for r in rows}
    added = 0
    for r in new_rows:
        key = (r.get("media", ""), r.get("name", ""))
        if key[0] and key[1] and key not in have:
            rows.append(r)
            have.add(key)
            added += 1
    if added:
        write_filtered_rows(path, rows)
    return added


_KANA = re.compile(r"[ぁ-ゖァ-ヺー]")
_CJK = re.compile(r"[一-鿿]")
_LATIN_WORD = re.compile(r"[A-Za-z]{2,}")
CHINESE_RE = re.compile(r"[们們这说說么麼吗嗎沒谁给哪呢吧啊你妳]")
_CHUNK_SPLIT = re.compile(r"([\s　]+)")


def simplified(text: str) -> int:
    n = 0
    for ch in _CJK.findall(text):
        try:
            ch.encode("cp932")
            continue
        except UnicodeEncodeError:
            pass
        try:
            ch.encode("gb2312")
        except UnicodeEncodeError:
            continue
        try:
            ch.encode("big5")
        except UnicodeEncodeError:
            n += 1
    return n


_SPEAKER_TAG = re.compile(r"[（(][^）)]*[）)]")


def is_chinese_text(text: str) -> bool:
    text = text.strip()
    if not text or _KANA.search(text):
        return False
    text = _SPEAKER_TAG.sub("", text).strip() or text
    if CHINESE_RE.search(text):
        return True
    return bool(simplified(text)) and len(_CJK.findall(text)) >= 3


_chinese_chunk = is_chinese_text


def line_kind(line: str) -> str:
    if _KANA.search(line):
        return "mix" if any(_chinese_chunk(c) for c in re.split(r"[\s　]+", line)) else "ja"
    if len(_CJK.findall(line)) >= 5 and (CHINESE_RE.search(line) or simplified(line)):
        return "zh"
    if not _CJK.search(line) and len(_LATIN_WORD.findall(line)) >= 3:
        return "en"
    return "other"


def strip_chinese_chunks(line: str):
    if not _KANA.search(line):
        return line, []
    parts = _CHUNK_SPLIT.split(line)
    removed = [p for p in parts[::2] if _chinese_chunk(p)]
    if not removed:
        return line, []
    out = []
    for i in range(0, len(parts), 2):
        chunk = parts[i]
        if not chunk or _chinese_chunk(chunk):
            continue
        if out:
            out.append(parts[i - 1])
        out.append(chunk)
    return "".join(out), removed


def system_dic_path() -> str:
    try:
        import sudachidict_core
        return os.path.join(
            os.path.dirname(sudachidict_core.__file__), "resources", "system.dic")
    except Exception:
        return ""


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def tokenizer_identity(with_hash: bool = True) -> dict:
    import importlib.metadata as md

    ident = {}
    for key, dist in (("sudachidict_version", "SudachiDict-core"),
                      ("sudachipy_version", "SudachiPy")):
        try:
            ident[key] = md.version(dist)
        except Exception:
            ident[key] = "unknown"

    requires = ""
    try:
        for r in (md.metadata("SudachiDict-core").get_all("Requires-Dist") or []):
            if "sudachipy" in r.lower():
                requires = r
                break
    except Exception:
        pass
    ident["sudachidict_requires"] = requires
    ident["dictionary_format"] = "v1" if ">=0.7" in requires.replace(" ", "") else "v0"

    if with_hash:
        path = system_dic_path()
        try:
            ident["system_dic_sha256"] = _sha256_file(path)
            ident["system_dic_bytes"] = str(os.path.getsize(path))
        except Exception:
            ident["system_dic_sha256"] = "unknown"
            ident["system_dic_bytes"] = "unknown"
    return ident


INDEX_FORMAT = {"subs": 3, "epub": 2, "manga": 1}
FORMAT_SCOPE = {("subs", 3): (".ass", ".ssa")}


def required_format(media, relpath) -> int:
    for n in range(INDEX_FORMAT[media], 1, -1):
        scope = FORMAT_SCOPE.get((media, n))
        if scope is None or relpath.lower().endswith(scope):
            return n
    return 1


def is_outdated(media, relpath, index_format) -> bool:
    return index_format < required_format(media, relpath)


def ensure_format_column(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(sources)")}
    if "index_format" not in cols:
        conn.execute("ALTER TABLE sources ADD COLUMN index_format INTEGER NOT NULL DEFAULT 1")


def outdated_sources(conn, media) -> int:
    if conn is None:
        return 0
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(sources)")}
        if "index_format" not in cols:
            return conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        return sum(is_outdated(media, relpath, fmt) for relpath, fmt in conn.execute(
            "SELECT relpath, index_format FROM sources WHERE index_format < ?", (INDEX_FORMAT[media],)))
    except Exception:
        return 0


def compact_index(conn, table):
    conn.commit()
    conn.execute(f"INSERT INTO {table}({table}) VALUES('optimize')")
    conn.commit()
    conn.execute("VACUUM")
    say(f"COMPACTED {table}")


CHAPTERS_SCHEMA = (
    "CREATE TABLE chapters (source_id INTEGER NOT NULL, file TEXT NOT NULL, "
    "first_rowid INTEGER NOT NULL, last_rowid INTEGER NOT NULL, lines INTEGER NOT NULL, "
    "PRIMARY KEY (source_id, file))",
    "CREATE INDEX chapters_file ON chapters(file)",
)


def has_chapters(conn) -> bool:
    try:
        return conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'chapters'").fetchone() is not None
    except sqlite3.Error:
        return False


def count_rows(conn, table) -> int:
    if table == "epubs" and has_chapters(conn):
        return conn.execute("SELECT COALESCE(SUM(lines), 0) FROM chapters").fetchone()[0]
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}_docsize").fetchone()[0]
    except sqlite3.Error:
        return conn.execute(f"SELECT COUNT(rowid) FROM {table}").fetchone()[0]


def chapter_spans(rows):
    spans = {}
    for rowid, sid, f in rows:
        s = spans.get((sid, f))
        if s is None:
            spans[(sid, f)] = [rowid, rowid, 1]
        else:
            s[0], s[1], s[2] = min(s[0], rowid), max(s[1], rowid), s[2] + 1
    return [(sid, f, a, b, n) for (sid, f), (a, b, n) in spans.items()]


def ensure_chapters(conn) -> bool:
    if has_chapters(conn):
        return False
    conn.commit()
    conn.execute("BEGIN")
    for sql in CHAPTERS_SCHEMA:
        conn.execute(sql)
    conn.executemany("INSERT INTO chapters VALUES (?, ?, ?, ?, ?)",
                     chapter_spans(conn.execute("SELECT rowid, source_id, file FROM epubs")))
    conn.commit()
    return True


SUDACHI_MAX_BYTES = 49149


def sudachi_pieces(text: str):
    if len(text.encode('utf-8')) <= SUDACHI_MAX_BYTES:
        return [text]
    pieces, buf, size = [], [], 0
    for ch in text:
        n = len(ch.encode('utf-8'))
        if size + n > SUDACHI_MAX_BYTES:
            pieces.append(''.join(buf))
            buf, size = [], 0
        buf.append(ch)
        size += n
    pieces.append(''.join(buf))
    return pieces


LINE_LENGTHS_VERSION = "1"
LINE_LENGTHS_SCHEMA = "CREATE TABLE line_lengths (rowid INTEGER PRIMARY KEY, chars INTEGER NOT NULL)"
DISPLAY_PUNCT_RE = re.compile(r'[ 　。…―～！？”“!?]')
DISPLAY_NONWORD_RE = re.compile(r'[^\w、\.,]')


def stored_display_length(line, media):
    if not line:
        return 0
    if media == "epub":
        if BOOK_DISPLAY_RUBY_RE.search(line):
            return None
        processed = line
    elif media == "manga":
        processed = BOOK_RUBY_RE.sub(r'', line)
    else:
        processed = RUBY_RE.sub(r'\1\2', line)
    return len(DISPLAY_NONWORD_RE.sub('', DISPLAY_PUNCT_RE.sub('', processed)))


def has_line_lengths(conn) -> bool:
    try:
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'line_lengths'").fetchone() is None:
            return False
        row = conn.execute("SELECT v FROM meta WHERE k = 'line_lengths_version'").fetchone()
        return row is not None and row[0] == LINE_LENGTHS_VERSION
    except sqlite3.Error:
        return False


def write_line_lengths(conn, rows, media):
    keep, clear = [], []
    for rowid, line in rows:
        n = stored_display_length(line, media)
        if n is None:
            clear.append((rowid,))
        else:
            keep.append((rowid, n))
    conn.executemany("INSERT OR REPLACE INTO line_lengths VALUES (?, ?)", keep)
    if clear:
        conn.executemany("DELETE FROM line_lengths WHERE rowid = ?", clear)


def _lengths_chunk(job):
    db_path, table, media, lo, hi, out_path = job
    src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    out = sqlite3.connect(out_path)
    out.execute("CREATE TABLE IF NOT EXISTS l (rowid INTEGER PRIMARY KEY, chars INTEGER NOT NULL)")
    rows = []
    for rowid, line in src.execute(f"SELECT rowid, line FROM {table} WHERE rowid BETWEEN ? AND ?", (lo, hi)):
        n = stored_display_length(line, media)
        if n is not None:
            rows.append((rowid, n))
    out.executemany("INSERT INTO l VALUES (?, ?)", rows)
    out.commit()
    out.close()
    src.close()
    return out_path


LENGTHS_CHUNK_ROWS = 250_000


def ensure_line_lengths(conn, db_path, table, media, workers=1) -> bool:
    conn.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
    conn.commit()
    if has_line_lengths(conn):
        return False
    top = conn.execute(f"SELECT rowid FROM {table} ORDER BY rowid DESC LIMIT 1").fetchone()
    work = os.path.join(os.path.dirname(os.path.abspath(db_path)), f".line_lengths-{table}")
    shutil.rmtree(work, ignore_errors=True)
    parts = []
    if top:
        os.makedirs(work, exist_ok=True)
        jobs = [(db_path, table, media, lo, hi, os.path.join(work, f"{i:06d}.db"))
                for i, (lo, hi) in enumerate(_table_ranges(top[0], workers))]
        actual = min(workers, len(jobs))
        say(f"LENGTHS Workers: {actual}")
        for i, part in enumerate(parallel_map(_lengths_chunk, jobs, actual, ordered=False,
                                              stop=stop_requested), 1):
            parts.append(part)
            if stop_requested():
                break
            emit("phase", f"LENGTHS {i}/{len(jobs)}", phase="lengths", done=i, total=len(jobs))
        if stop_requested():
            shutil.rmtree(work, ignore_errors=True)
            return False
    conn.commit()
    conn.execute("BEGIN")
    conn.execute("DROP TABLE IF EXISTS line_lengths")
    conn.execute(LINE_LENGTHS_SCHEMA)
    for part in sorted(parts):
        src = sqlite3.connect(part)
        conn.executemany("INSERT INTO line_lengths VALUES (?, ?)", src.execute("SELECT rowid, chars FROM l ORDER BY rowid"))
        src.close()
    conn.execute("INSERT OR REPLACE INTO meta (k, v) VALUES ('line_lengths_version', ?)", (LINE_LENGTHS_VERSION,))
    conn.commit()
    shutil.rmtree(work, ignore_errors=True)
    return True


def drop_orphan_lengths(conn, table):
    if has_line_lengths(conn):
        conn.execute(f"DELETE FROM line_lengths WHERE rowid NOT IN (SELECT id FROM {table}_docsize)")


def stop_requested():
    path = os.environ.get("AOBANA_STOP_FILE")
    return bool(path) and os.path.exists(path)


COMPACT_SHARE = 0.25


def compact_if_worth(conn, table, deleted, inserted):
    if not deleted:
        return
    conn.commit()
    before = count_rows(conn, table) - inserted + deleted
    if before > 0 and deleted / before >= COMPACT_SHARE:
        compact_index(conn, table)


def write_tokenizer_meta(conn, tokenized_rows: int) -> dict:
    conn.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
    if tokenized_rows <= 0:
        return dict(conn.execute("select k, v from meta").fetchall())

    prior = {k: v for k, v in conn.execute("select k, v from meta")
             if k not in ("line_lengths_version", "ruby_lexicon_version")}
    ident = tokenizer_identity()
    was = prior.get("system_dic_sha256")
    if prior and was != ident["system_dic_sha256"]:
        ident["mixed_with"] = (
            "%s rows predate this run and were tokenized with sudachidict=%s system_dic=%s"
            % ("some", prior.get("sudachidict_version", "?"), was or "unrecorded"))
    ident["tokenized_at"] = datetime.now().isoformat(timespec="seconds")
    conn.executemany(
        "INSERT INTO meta(k, v) VALUES (?, ?) "
        "ON CONFLICT(k) DO UPDATE SET v = excluded.v",
        sorted(ident.items()))
    return ident


def parallel_map(fn, items, workers, chunksize=1, ordered=True, stop=None):
    pool = None
    if workers > 1:
        try:
            import multiprocessing
            pool = multiprocessing.get_context("spawn").Pool(workers)
        except (ImportError, OSError, NotImplementedError) as e:
            say(f"PARALLEL_OFF {type(e).__name__}: {e}")
    if pool is None:
        yield from map(fn, items)
        return
    with pool:
        if stop is None:
            yield from (pool.imap if ordered else pool.imap_unordered)(fn, items, chunksize)
            return
        items = list(items)
        chunks = [items[i:i + chunksize] for i in range(0, len(items), chunksize)]
        it = (pool.imap if ordered else pool.imap_unordered)(functools.partial(_map_chunk, fn), chunks, 1)
        while True:
            try:
                yield from it.next(timeout=0.5)
            except multiprocessing.TimeoutError:
                if stop():
                    return
            except StopIteration:
                return


def _map_chunk(fn, chunk):
    return [fn(x) for x in chunk]
