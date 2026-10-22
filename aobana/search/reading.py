
import bisect
import functools
import re
import unicodedata
from dataclasses import dataclass

from aobana.utils import (
    KANJI_CHARS, _SPACED_EQ_RE, katakana_to_hiragana, load_kanji_readings, ruby_merge_key,
)


_KANJI_RE = re.compile(rf'[{KANJI_CHARS}〆ヵヶ]')
_KANA = 'ぁ-ゖァ-ヴヷ-ヺー'
_KANA_RE = re.compile(rf'[{_KANA}]')
_SIDE_CHARS = rf'{KANJI_CHARS}〆ヵヶ{_KANA}'
_SIDE_RE = re.compile(rf'[{_SIDE_CHARS}]+')
_READING_RE = re.compile(rf'[{_KANA}]+')
_TERM_RE = re.compile(r'^([-－]?)([^=＝]+)[=＝]([^=＝]+)$')
_QUOTES = ('"', '“', '”')

_VOICED = {
    'か': 'が', 'き': 'ぎ', 'く': 'ぐ', 'け': 'げ', 'こ': 'ご', 'さ': 'ざ', 'し': 'じ', 'す': 'ず',
    'せ': 'ぜ', 'そ': 'ぞ', 'た': 'だ', 'ち': 'ぢじ', 'つ': 'づず', 'て': 'で', 'と': 'ど',
    'は': 'ばぱ', 'ひ': 'びぴ', 'ふ': 'ぶぷ', 'へ': 'べぺ', 'ほ': 'ぼぽ',
}
_SOKUON_FROM = 'つくちき'
_ROWS = ('あいうえお', 'かきくけこ', 'がぎぐげご', 'さしすせそ', 'ざじずぜぞ', 'たちつてと', 'だぢづでど',
         'なにぬねの', 'はひふへほ', 'ばびぶべぼ', 'ぱぴぷぺぽ', 'まみむめも', 'やゆよ', 'らりるれろ', 'わを')
_ROW_OF = {c: i for i, row in enumerate(_ROWS) for c in row}
_E_ROW = frozenset('えけげせぜてでねへべぺめれぇ')
_EXTRA_READINGS = {'ヵ': ('か', 'が', 'こ', 'け'), 'ヶ': ('か', 'が', 'こ', 'け'), '〆': ('しめ',)}
_SPLITS_MAX = 256
SEARCH_MIN_FAMILIES = 2


def fold(text: str) -> str:
    return ruby_merge_key(text or '')


_SMALL = str.maketrans('ぁぃぅぇぉっゃゅょゎ', 'あいうえおつやゆよわ')


def fold_small(reading: str) -> str:
    return reading.translate(_SMALL)


def is_kanji(c: str) -> bool:
    return bool(_KANJI_RE.fullmatch(c))


def is_kana(c: str) -> bool:
    return bool(_KANA_RE.fullmatch(c))


def variants(reading: str) -> frozenset:
    out = {reading}
    if reading[0] in _VOICED:
        out |= {v + reading[1:] for v in _VOICED[reading[0]]}
    if len(reading) > 1 and reading[-1] in _SOKUON_FROM:
        out |= {r[:-1] + 'っ' for r in list(out)}
    return frozenset(out)


@functools.lru_cache(maxsize=65536)
def kanji_readings(c: str, min_families: int = SEARCH_MIN_FAMILIES) -> frozenset:
    if c in _EXTRA_READINGS:
        return frozenset(_EXTRA_READINGS[c])
    if '豈' <= c <= '﫿':
        c = unicodedata.normalize('NFC', c)
    out = set()
    for r, families in load_kanji_readings().get(c, {}).items():
        if families >= min_families:
            out |= variants(r)
    return frozenset(out)


@functools.lru_cache(maxsize=65536)
def _splits(base: str, furi: str, min_families: int = SEARCH_MIN_FAMILIES, small: bool = False):
    out = []
    norm = fold_small if small else (lambda r: r)

    def walk(k, p, acc):
        if len(out) > _SPLITS_MAX:
            return
        if k == len(base):
            if p == len(furi):
                out.append(tuple(acc))
            return
        c = base[k]
        if is_kana(c):
            f = norm(fold(c))
            if furi.startswith(f, p):
                walk(k + 1, p + len(f), acc + [f])
            return
        if c == '々':
            options = kanji_readings(base[k - 1], min_families) if k and is_kanji(base[k - 1]) else ()
        else:
            options = kanji_readings(c, min_families)
        for r in {norm(r) for r in options}:
            if furi.startswith(r, p):
                walk(k + 1, p + len(r), acc + [r])

    walk(0, 0, [])
    return None if len(out) > _SPLITS_MAX else tuple(out)


def split_tries(base: str, furi: str, min_families: int = SEARCH_MIN_FAMILIES):
    splits = _splits(base, furi, min_families)
    if splits == ():
        splits = _splits(base, fold_small(furi), min_families, True)
    return splits


def split_reading(base: str, furi: str, i: int, j: int):
    furi = fold(furi)
    splits = None
    for families in (SEARCH_MIN_FAMILIES, 1):
        splits = split_tries(base, furi, families)
        if splits != ():
            break
    if not splits:
        return None
    found = {''.join(s[i:j]) for s in splits}
    return found.pop() if len(found) == 1 else None


def same_reading(found: str, wanted: str, slang: bool = False) -> bool:
    return (_same(found, wanted, slang)
            or _same(fold_small(found or ''), fold_small(wanted or ''), slang))


def _same(found: str, wanted: str, slang: bool) -> bool:
    if found == wanted:
        return True
    if not found or not wanted or len(found) != len(wanted):
        return False
    n = len(wanted)

    def ok_first(f, w):
        return f == w or f in _VOICED.get(w, '')

    def ok_last(f, w):
        return (f == w or (f == 'っ' and w in _SOKUON_FROM)
                or (slang and f in _ROW_OF and _ROW_OF.get(f) == _ROW_OF.get(w)))

    if n == 1:
        f, w = found, wanted
        return ok_first(f, w) or ok_last(f, w)
    return ok_first(found[0], wanted[0]) and ok_last(found[-1], wanted[-1]) and found[1:-1] == wanted[1:-1]


def _skeleton(word: str):
    parts, k = [], 0
    while k < len(word):
        if is_kana(word[k]):
            parts.append(re.escape(fold(word[k])))
            k += 1
        else:
            while k < len(word) and not is_kana(word[k]):
                k += 1
            parts.append('(.+?)')
    return re.compile('^' + ''.join(parts) + '$')


@dataclass(frozen=True)
class ReadingTerm:
    word: str
    reading: str
    stem: str
    conjugates: bool
    i_adj: bool
    lemmas: tuple

    @property
    def kanji(self) -> str:
        return ''.join(c for c in self.word if is_kanji(c))


def _term(word: str, reading: str):
    if not _SIDE_RE.fullmatch(word) or not any(is_kanji(c) for c in word):
        return None
    if not _READING_RE.fullmatch(reading):
        return None
    r = fold(reading)
    if not _skeleton(word).match(r):
        return None
    last = max(k for k, c in enumerate(word) if is_kanji(c))
    tail = fold(word[last + 1:])
    stem = r[:len(r) - len(tail)] if tail else r
    from aobana.search import furigana
    with furigana.tagger() as (tok, mode):
        toks = list(tok.tokenize(word, mode))
        entries = [m for m in furigana._TAGGER_DICT[0].lookup(word) if fold(m.reading_form()) == r]
    if entries:
        lemmas = (frozenset(m.normalized_form().split('-')[0] for m in entries),)
        pos = {m.part_of_speech()[0] for m in entries}
        conjugates = bool(pos & {'動詞', '形容詞', '助動詞'})
        i_adj = '形容詞' in pos and word.endswith('い')
        return ReadingTerm(word, r, stem, conjugates, i_adj, lemmas)
    lemmas = []
    for t in toks:
        pos = t.part_of_speech()[0]
        surface = t.surface()
        is_symbol = pos == '補助記号' and not re.search(rf'[{KANJI_CHARS}぀-ヿ]', surface)
        if pos not in ('助動詞', '助詞') and not is_symbol:
            base = t.normalized_form()
            if surface == 'いい' and base == '言う':
                base = '良い'
            lemmas.append(frozenset((base,)))
    last_pos = toks[-1].part_of_speech()[0] if toks else ''
    content = [t for t in toks if t.part_of_speech()[0] not in ('助動詞', '助詞', '補助記号')]
    i_adj = bool(content) and content[-1].part_of_speech()[0] == '形容詞' and word.endswith('い')
    return ReadingTerm(word, r, stem, last_pos in ('動詞', '形容詞', '助動詞'), i_adj, tuple(lemmas))


def _chunks(q: str):
    out, current, in_quotes = [], '', False
    for ch in q:
        if ch in _QUOTES:
            in_quotes = not in_quotes
            current += ch
        elif not in_quotes and ch.isspace():
            if current:
                out.append(current)
            current = ''
        else:
            current += ch
    if current:
        out.append(current)
    return out


_READING_MARKS = str.maketrans('', '', '↓↑・／＼/\\')


def _is_term_shape(word: str, reading: str) -> bool:
    return bool(_SIDE_RE.fullmatch(word) and any(is_kanji(c) for c in word)
                and _READING_RE.fullmatch(reading))


def _term_dictionary_form(word: str, reading: str):
    from aobana.search import furigana
    last = max(k for k, c in enumerate(word) if is_kanji(c))
    forms = []
    with furigana.tagger():
        lexicon = furigana._TAGGER_DICT[0]
        for end in range(len(word), last, -1):
            head = word[:end]
            for m in lexicon.lookup(head):
                form = m.dictionary_form()
                if (m.surface() == head and m.part_of_speech()[0] in ('動詞', '形容詞')
                        and form != word and form not in forms):
                    forms.append(form)
    for form in forms:
        if _is_term_shape(form, reading):
            term = _term(form, reading)
            if term is not None:
                return term
    return None


def _term_leading_kana(word: str, reading: str):
    lead = 0
    while lead < len(word) and is_kana(word[lead]):
        lead += 1
    head = fold(word[:lead])
    if not head or fold(reading).startswith(head):
        return None
    return _term(word, head + reading)


@functools.lru_cache(maxsize=1024)
def resolve_term(word: str, reading: str):
    reading = reading.translate(_READING_MARKS)
    term = _term(word, reading)
    if term is None and _is_term_shape(word, reading):
        term = _term_dictionary_form(word, reading) or _term_leading_kana(word, reading)
    return term


def _chunk_term(chunk: str):
    m = None if any(c in chunk for c in _QUOTES) else _TERM_RE.match(chunk)
    term = m and resolve_term(m.group(2), m.group(3))
    return (m.group(1), term) if term else None


def _fallback_word(chunk):
    match = None if any(c in chunk for c in _QUOTES) else _TERM_RE.match(chunk)
    if (match and _is_term_shape(match[2], match[3].translate(_READING_MARKS))
            and resolve_term(match[2], match[3]) is None):
        return match[1] + match[2]
    return None


def reading_fallback_words(q):
    return [word.lstrip('-－') for chunk in _chunks(_join_spaced(q))
            if (word := _fallback_word(chunk)) is not None]


def _join_spaced(q: str) -> str:
    parts, current, quoted = [], [], False
    for char in q:
        if char in _QUOTES:
            text = ''.join(current)
            parts.append(text if quoted else _SPACED_EQ_RE.sub(r'\1', text))
            parts.append(char)
            current = []
            quoted = not quoted
        else:
            current.append(char)
    text = ''.join(current)
    parts.append(text if quoted else _SPACED_EQ_RE.sub(r'\1', text))
    return ''.join(parts)


def literal_equal_terms(q):
    return tuple(chunk.strip('"“”') for chunk in _chunks(_join_spaced(q))
                 if not chunk.startswith(('-', '－')) and not _chunk_term(chunk)
                 and re.search(r'[^=＝\s][=＝][^=＝\s]', chunk))


@functools.lru_cache(maxsize=256)
def parse_reading_terms(q: str):
    if not q or ('=' not in q and '＝' not in q):
        return q, (), (), q
    joined = _join_spaced(q)
    plain, rest, terms, neg = [], [], [], []
    for chunk in _chunks(joined):
        found = _chunk_term(chunk)
        if not found:
            chunk = _fallback_word(chunk) or chunk
            plain.append(chunk)
            rest.append(chunk)
            continue
        sign, term = found
        if sign:
            neg.append(term)
        else:
            terms.append(term)
            plain.append(term.word)
    if not terms and not neg:
        if reading_fallback_words(joined):
            return ' '.join(plain), (), (), ' '.join(rest)
        return joined, (), (), joined
    return ' '.join(plain), tuple(terms), tuple(neg), ' '.join(rest)


class Overlaps:

    def __init__(self, items):
        def bounds(x):
            return (x['start'], x['end']) if isinstance(x, dict) else (x[0], x[1])
        self.items = sorted(items, key=lambda x: bounds(x)[0])
        self.bounds = [bounds(x) for x in self.items]
        self.starts = [s for s, _ in self.bounds]
        self.reach, top = [], None
        for _, e in self.bounds:
            top = e if top is None or e > top else top
            self.reach.append(top)

    def over(self, a: int, b: int):
        k = bisect.bisect_right(self.reach, a)
        while k < len(self.items) and self.starts[k] < b:
            if self.bounds[k][1] > a:
                yield self.items[k]
            k += 1

    def any_over(self, a: int, b: int) -> bool:
        return next(self.over(a, b), None) is not None


def _index(analysis, key: str) -> Overlaps:
    cache = analysis.setdefault('_overlaps', {})
    if key not in cache:
        cache[key] = Overlaps(analysis[key])
    return cache[key]


def token_reading(w) -> str:
    reading = fold(w.get('reading') or '')
    cut = w.get('cut')
    if cut:
        inner = fold(cut.strip('（()）'))
        if inner and reading.endswith(inner) and len(reading) > len(inner):
            reading = reading[:-len(inner)]
    return reading


def _align(w):
    if 'align' in w:
        return w['align']
    surface, reading, segs = w['surface'], token_reading(w), None
    if surface and reading and _READING_RE.fullmatch(reading):
        runs, k = [], 0
        while k < len(surface):
            j = k + 1
            if not is_kana(surface[k]):
                while j < len(surface) and not is_kana(surface[j]):
                    j += 1
            runs.append((k, j, not is_kana(surface[k])))
            k = j
        pattern = ''.join('(.+?)' if block else f'({re.escape(fold(surface[a:b]))})' for a, b, block in runs)
        m = re.fullmatch(pattern, reading)
        if m:
            segs = [(w['start'] + a, w['start'] + b, m.group(n + 1), block)
                    for n, (a, b, block) in enumerate(runs)]
    w['align'] = segs
    return segs


def own_work_readings(work, word: str) -> set:
    if not work:
        return set()
    from aobana.search import furigana
    conns = furigana._lexicon_tables()
    if conns is None:
        by_work, _, _ = furigana.get_ruby_lexicon()
        own = by_work.get((work, word), set())
    else:
        own, _ = furigana._lexicon_lookup(conns, work[0], work[1], word)
    return {fold(r) for r in own}


def own_work_alone(work, word: str) -> set:
    if not work:
        return set()
    from aobana.search import furigana
    conns = furigana._lexicon_tables()
    if conns is None:
        _, _, alone = furigana.get_ruby_lexicon()
        own = alone.get((work, word), set())
    else:
        own = furigana._lexicon_alone(conns, work[0], work[1], word)
    return {fold(r) for r in own}


@functools.lru_cache(maxsize=65536)
def dictionary_entries(word: str) -> frozenset:
    from aobana.search import furigana
    with furigana.tagger():
        entries = furigana._TAGGER_DICT[0].lookup(word)
    return frozenset((fold_small(fold(m.reading_form())), m.part_of_speech()[1] == '固有名詞')
                     for m in entries if m.surface() == word)


def dictionary_readings(word: str) -> frozenset:
    return frozenset(r for r, _ in dictionary_entries(word))


_DIGITS_RE = re.compile(r'[0-9０-９]+')


def work_ruby_counts(work, word: str, reading: str) -> bool:
    if _DIGITS_RE.fullmatch(word):
        return False
    if len(word) == 1 and reading not in own_work_alone(work, word):
        return False
    entries = dictionary_entries(word)
    return not entries or (fold_small(reading), True) in entries


def _whole_words(analysis, a: int, b: int) -> bool:
    for w in _index(analysis, 'words').over(a, b):
        if w['start'] < a or w['end'] > b:
            return False
    return True


def span_reading(analysis, a: int, b: int, work=None, why: list = None):
    text = analysis['clean_text']
    if not 0 <= a < b <= len(text):
        return None
    pieces = {}
    covered = [False] * (b - a)

    def put(lo, hi, reading, source):
        pieces[lo] = (hi, reading)
        for k in range(lo, hi):
            covered[k - a] = True
        if why is not None and source not in why:
            why.append(source)

    for sp in _index(analysis, 'ruby_spans').over(a, b):
        s, e = sp['start'], sp['end']
        lo, hi = max(s, a), min(e, b)
        if s >= a and e <= b:
            put(lo, hi, fold(sp['furi']), 'ruby')
            continue
        r = split_reading(text[s:e], sp['furi'], lo - s, hi - s)
        if r is None:
            return None
        put(lo, hi, r, 'ruby split')

    if not pieces and work:
        own = own_work_readings(work, text[a:b])
        if len(own) == 1 and _whole_words(analysis, a, b) \
                and work_ruby_counts(work, text[a:b], next(iter(own))):
            if why is not None:
                why.append('work')
            return next(iter(own))

    for w in _index(analysis, 'words').over(a, b):
        lo, hi = max(w['start'], a), min(w['end'], b)
        if all(covered[k - a] for k in range(lo, hi)):
            continue
        segs = _align(w)
        if segs is None:
            whole = token_reading(w)
            if w['start'] >= a and w['end'] <= b and not any(covered[k - a] for k in range(lo, hi)) \
                    and whole and _READING_RE.fullmatch(whole):
                put(lo, hi, whole, 'sudachi')
                continue
            return None
        for s, e, r, block in segs:
            if not block:
                continue
            k = max(s, a)
            while k < min(e, b):
                if covered[k - a]:
                    k += 1
                    continue
                j = k
                while j < min(e, b) and not covered[j - a]:
                    j += 1
                if k == s and j == e:
                    put(k, j, r, 'sudachi')
                else:
                    part = split_reading(text[s:e], r, k - s, j - s)
                    if part is None:
                        return None
                    put(k, j, part, 'split')
                k = j

    out, k = [], a
    while k < b:
        if k in pieces:
            hi, r = pieces[k]
            out.append(r)
            k = hi
        elif is_kana(text[k]):
            out.append(fold(text[k]))
            k += 1
        else:
            return None
    return ''.join(out)


def _ends_e_row(text: str) -> bool:
    t = fold(text).rstrip('ーっ')
    return bool(t) and t[-1] in _E_ROW


_GUESSED = frozenset(('sudachi', 'split'))

_STEM_ENDS = ('すぎ', 'スギ', '過ぎ')
_STEM_END_WORDS = frozenset(('そう', 'そー', 'ソウ', 'さう', 'み', 'ミ', 'げ', 'ゲ', 'う', 'ウ'))


@functools.lru_cache(maxsize=4096)
def _spells_particle(kana: str) -> bool:
    from aobana.search import furigana
    with furigana.tagger():
        entries = furigana._TAGGER_DICT[0].lookup(kana)
    return any(m.part_of_speech()[0] == '助詞' and m.part_of_speech()[1] != '終助詞' for m in entries)


def _stem_counts(seq, j: int, stem: str) -> bool:
    if j >= len(seq):
        return True
    w = seq[j]
    s = w['surface']
    if w['pos'] == '補助記号' or s[0] in 'っッーｰ～〜ぇいイ' or s.startswith(_STEM_ENDS) or s in _STEM_END_WORDS:
        return True
    if w['pos'] == '接尾辞' and s[0] in 'がガ':
        return True
    if s in ('さ', 'サ') and w['pos'] == '接尾辞':
        after = seq[j + 1]['pos_full'] if j + 1 < len(seq) else None
        return (after is not None and after[0] == '助詞' and after[1] != '終助詞') \
            or not _spells_particle(stem)
    return False


def occurrences(analysis, term: ReadingTerm, work=None, exact=False):
    from aobana.search.furigana import token_base
    text = analysis['clean_text']
    i = text.find(term.word)
    while i != -1:
        why = []
        r = span_reading(analysis, i, i + len(term.word), work, why)
        yield (i, i + len(term.word), r is not None and same_reading(r, term.reading),
               bool(_GUESSED.intersection(why)))
        i = text.find(term.word, i + 1)
    n = 0 if exact else len(term.lemmas)
    if n:
        seq = [w for w in analysis['words'] if w['pos'] != '空白']
        for k in range(len(seq) - n + 1):
            run = seq[k:k + n]
            if any(token_base(w) not in lemmas for w, lemmas in zip(run, term.lemmas)):
                continue
            a, b = run[0]['start'], run[-1]['end']
            run_text = text[a:b]
            kanji = [p for p, c in enumerate(run_text) if is_kanji(c)]
            spelled = ''.join(run_text[p] for p in kanji) if kanji else ''.join(
                c for w in run for c in token_base(w) if is_kanji(c))
            if spelled != term.kanji:
                continue
            why = []
            if kanji:
                last = kanji[-1] + 1
                r = span_reading(analysis, a, a + last, work, why)
                slang = term.i_adj and _ends_e_row(run_text[last:])
                ok = r is not None and same_reading(r, term.stem, slang)
            else:
                r = fold(run_text)
                if (term.i_adj and str(run[-1].get('pos_full', ('',) * 6)[5]).startswith('語幹')
                        and not _stem_counts(seq, k + n, run[-1]['surface'])):
                    continue
                if term.conjugates:
                    slang = term.i_adj and _ends_e_row(run_text)
                    ok = same_reading(r[:len(term.stem)], term.stem, slang)
                else:
                    ok = same_reading(r, term.reading)
            yield (a, b, ok, bool(_GUESSED.intersection(why)))


def matched_spans(analysis, terms, work=None):
    matched, unmatched, guessed = [], [], []
    for term in terms:
        for a, b, ok, guess in occurrences(analysis, term, work):
            (matched if ok else unmatched).append((a, b))
            if ok and guess:
                guessed.append((a, b))
    return matched, unmatched, guessed


def row_matches(analysis, terms, neg_terms, work=None, exact=False, ruby_only=False) -> bool:
    for term in terms:
        if not any(ok and not (ruby_only and guess)
                   for _, _, ok, guess in occurrences(analysis, term, work, exact)):
            return False
    for term in neg_terms:
        if any(ok for _, _, ok, _ in occurrences(analysis, term, work, exact)):
            return False
    return True


def prefilter_keys(term: ReadingTerm) -> tuple:
    s = term.stem
    lasts = {s[-1]}
    if s[-1] in _SOKUON_FROM:
        lasts.add('っ')
    if term.i_adj and s[-1] in _ROW_OF:
        lasts |= set(_ROWS[_ROW_OF[s[-1]]])
    out = set()
    for last in lasts:
        key = s[:-1] + last
        out.add(key)
        out |= {v + key[1:] for v in _VOICED.get(key[0], '')}
    return tuple(sorted(out))
