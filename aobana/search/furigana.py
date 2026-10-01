
import bisect
import contextlib
import functools
import os
import queue
import re
import sqlite3
import threading

from aobana.utils import (
    ALPHA_CHARS, BOOK_RUBY_RE, DISPLAY_NONWORD_RE, DISPLAY_PUNCT_RE, GlossRuby, KANJI_CHARS,
    RUBY_RE, SPACED_RUBY_PREV_RE, build_ruby_lexicon, has_ruby_lexicon, katakana_to_hiragana,
    load_ruby_decisions, load_ruby_merges, load_ruby_trims, ruby_merge_key, ruby_reading,
    split_spaced_ruby, sudachi_pieces, work_folder,
)
from aobana import paths


_TAGGER_POOL = queue.LifoQueue()
_TAGGER_LOCK = threading.Lock()
_TAGGER_MADE = [0]
_TAGGER_MAX = max(4, min(16, os.cpu_count() or 4))
_TAGGER_DICT = [None]
_TAGGER_HELD = threading.local()


def _take_tagger():
    try:
        return _TAGGER_POOL.get_nowait()
    except queue.Empty:
        pass
    with _TAGGER_LOCK:
        if _TAGGER_MADE[0] < _TAGGER_MAX:
            from sudachipy import tokenizer, dictionary
            if _TAGGER_DICT[0] is None:
                _TAGGER_DICT[0] = dictionary.Dictionary(dict="core")
            _TAGGER_MADE[0] += 1
            return _TAGGER_DICT[0].create(), tokenizer.Tokenizer.SplitMode.A
    return _TAGGER_POOL.get()


@contextlib.contextmanager
def tagger():
    held = getattr(_TAGGER_HELD, 'pair', None)
    if held is not None:
        yield held
        return
    pair = _take_tagger()
    _TAGGER_HELD.pair = pair
    try:
        yield pair
    finally:
        _TAGGER_HELD.pair = None
        _TAGGER_POOL.put(pair)

_RUBY_LEXICON = None
_RUBY_LEXICON_LOCK = threading.Lock()
_LEXICON_GEN = [0]
_LEXICON_LOCAL = threading.local()
_LEXICON_OPEN = {}
_LEXICON_OPEN_LOCK = threading.Lock()
_LEXICON_MEMO_MAX = 50_000
_DB_PATHS = (('subs', paths.subs_db, 'subtitles'), ('epub', paths.epub_db, 'epubs'),
             ('manga', paths.manga_db, 'manga'))


def work_key(media: str, file: str) -> tuple:
    return (media, work_folder(file))


def get_ruby_lexicon():
    global _RUBY_LEXICON
    lexicon = _RUBY_LEXICON
    if lexicon is not None:
        return lexicon
    with _RUBY_LEXICON_LOCK:
        if _RUBY_LEXICON is not None:
            return _RUBY_LEXICON
        gen = _LEXICON_GEN[0]
        rows = []
        for media, db_path, table in _DB_PATHS:
            path = db_path()
            if not os.path.exists(path):
                continue
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            try:
                rows += [(work_key(media, f), line) for f, line in conn.execute(
                    f"SELECT file, line FROM {table} WHERE instr(line, ?) > 0", ('(',))]
            finally:
                conn.close()
        lexicon = build_ruby_lexicon(rows)
        if gen == _LEXICON_GEN[0]:
            _RUBY_LEXICON = lexicon
        return lexicon


def _lexicon_tables():
    local = _LEXICON_LOCAL
    if getattr(local, 'gen', None) != _LEXICON_GEN[0]:
        for conn in (getattr(local, 'conns', None) or {}).values():
            conn.close()
        conns, complete = {}, True
        for media, db_path, _ in _DB_PATHS:
            path = db_path()
            if not os.path.exists(path):
                continue
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
            conns[media] = conn
            complete = complete and has_ruby_lexicon(conn)
        local.conns, local.complete, local.memo, local.gen = conns, complete, {}, _LEXICON_GEN[0]
        thread = threading.current_thread()
        with _LEXICON_OPEN_LOCK:
            _LEXICON_OPEN[thread] = conns
    return local.conns if local.complete else None


def _close_ended_lexicon_tables():
    with _LEXICON_OPEN_LOCK:
        ended = [thread for thread in _LEXICON_OPEN if not thread.is_alive()]
        closing = [_LEXICON_OPEN.pop(thread) for thread in ended]
    for conns in closing:
        for conn in conns.values():
            conn.close()


def release_thread_resources():
    local = _LEXICON_LOCAL
    conns = getattr(local, 'conns', None)
    local.conns, local.complete, local.memo, local.gen = None, False, {}, None
    with _LEXICON_OPEN_LOCK:
        _LEXICON_OPEN.pop(threading.current_thread(), None)
    for conn in (conns or {}).values():
        try:
            conn.close()
        except Exception:
            pass
    _close_ended_lexicon_tables()


def drop_lexicon(close_live=False):
    global _RUBY_LEXICON
    _LEXICON_GEN[0] += 1
    _RUBY_LEXICON = None
    if not close_live:
        _close_ended_lexicon_tables()
        return
    with _LEXICON_OPEN_LOCK:
        closing = list(_LEXICON_OPEN.values())
        _LEXICON_OPEN.clear()
    for conns in closing:
        for conn in conns.values():
            try:
                conn.close()
            except Exception:
                pass


def warm_ruby_lexicon():
    if _lexicon_tables() is None:
        get_ruby_lexicon()


def _lexicon_lookup(conns, media, folder, word):
    memo = _LEXICON_LOCAL.memo
    key = (media, folder, word)
    if key not in memo:
        if len(memo) > _LEXICON_MEMO_MAX:
            memo.clear()
        own = set()
        if media in conns:
            own = {r for (r,) in conns[media].execute(
                "SELECT DISTINCT reading FROM ruby_lexicon WHERE base = ? AND folder = ?", (word, folder))}
        corpus = set()
        for conn in conns.values():
            corpus.update(r for (r,) in conn.execute(
                "SELECT DISTINCT reading FROM ruby_lexicon WHERE base = ?", (word,)))
        memo[key] = (own, corpus)
    return memo[key]


_SUDACHI_READINGS = {}
_SUDACHI_READINGS_MAX = 50_000

def _sudachi_reading(word: str) -> str:
    if word not in _SUDACHI_READINGS:
        if len(_SUDACHI_READINGS) >= _SUDACHI_READINGS_MAX:
            _SUDACHI_READINGS.clear()
        from sudachipy import tokenizer
        with tagger() as (tokenizer_obj, _):
            toks = tokenizer_obj.tokenize(word, tokenizer.Tokenizer.SplitMode.C)
        _SUDACHI_READINGS[word] = katakana_to_hiragana("".join(t.reading_form() for t in toks))
    return _SUDACHI_READINGS[word]


def ruby_evidence(work):
    conns = _lexicon_tables()
    if conns is None:
        by_work, corpus = get_ruby_lexicon()

        def readings(word):
            return by_work.get((work, word), set()), corpus.get(word, set())
    else:
        media, folder = work if work else (None, None)

        def readings(word):
            return _lexicon_lookup(conns, media, folder, word)

    def evidence(word):
        own, anywhere = readings(word)
        for r in sorted(own):
            yield r, 0
        for r in sorted(anywhere - own):
            yield r, 1
        s = _sudachi_reading(word)
        if s and s != word:
            yield s, 2
    return evidence


RUBY_TABLES_PATH = paths.RUBY_TABLES_PATH

_RUBY_DECISIONS = None


def ruby_decisions() -> dict:
    global _RUBY_DECISIONS
    if _RUBY_DECISIONS is None:
        _RUBY_DECISIONS = {**load_ruby_decisions(RUBY_TABLES_PATH, 'gloss_names'),
                           **load_ruby_decisions(RUBY_TABLES_PATH, 'ruby_decisions')}
    return _RUBY_DECISIONS

def spaced_ruby_split(prev, base, furi, work):
    decided = ruby_decisions()
    key = (prev, base, furi)
    if key in decided:
        return decided[key]
    return split_spaced_ruby(prev, base, furi, ruby_evidence(work))


def iter_spaced_ruby_candidates():
    for media, db_path, table in _DB_PATHS:
        path = db_path()
        if not os.path.exists(path):
            continue
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            rows = conn.execute(f"SELECT rowid, file, line FROM {table} WHERE instr(line, ?) > 0 OR instr(line, ?) > 0",
                                ('(', '（' if media == 'epub' else '(')).fetchall()
        finally:
            conn.close()
        for rowid, f, line in rows:
            work, last = work_key(media, f), 0
            for m in display_ruby_re(media).finditer(line):
                gap, last = line[last:m.start()], m.end()
                pm = None if m.group(1) else SPACED_RUBY_PREV_RE.search(gap)
                if pm:
                    prev, base, furi = pm.group(1), m.group(2), ruby_reading(m)
                    yield (media, rowid, work, prev, base, furi, spaced_ruby_split(prev, base, furi, work))

HTML_ESCAPE_MAP = {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#x27;'}

_DISPLAY_PUNCT_RE = DISPLAY_PUNCT_RE
_DISPLAY_NONWORD_RE = DISPLAY_NONWORD_RE

def calculate_display_length(line: str, media: str = 'subs') -> int:
    if not line: return 0
    processed = display_ruby_re(media).sub(r'\1\2', line)
    processed = _DISPLAY_PUNCT_RE.sub('', processed)
    processed = _DISPLAY_NONWORD_RE.sub('', processed)
    return len(processed)

def detect_script(query):
    has_kanji = bool(re.search(rf'[{KANJI_CHARS}]', query))
    has_hiragana = bool(re.search(r'[\u3040-\u309F]', query))
    has_katakana = bool(re.search(r'[\u30A0-\u30FF]', query))
    
    if has_kanji: return 'kanji'
    if has_katakana and not has_hiragana: return 'katakana'
    if has_hiragana: return 'hiragana'
    return 'romaji'

@functools.lru_cache(maxsize=256)
def bound_auxiliary(q):
    if detect_script(q) != 'hiragana':
        return None
    with tagger() as (tokenizer_obj, mode):
        toks = list(tokenizer_obj.tokenize(q, mode))
    if len(toks) != 1 or toks[0].part_of_speech()[0] != '助動詞':
        return None
    kana = toks[0].reading_form()
    return toks[0].normalized_form(), katakana_to_hiragana(kana) if kana else q

RUN_ANCHOR_POS = ('動詞', '形容詞', '形状詞')

RUN_ANCHOR_NOUN_POS2 = '形状詞可能'

RUN_TAIL_POS = ('助動詞', '助詞', '接尾辞')

RUN_TAIL_KEIJOUSHI_POS1 = '助動詞語幹'


TAIL_PARTICLE_WHITELIST = frozenset({'て', 'で', 'ば', 'たり', 'だり',
                                     'ちゃ', 'ながら', 'つつ', 'たって'})

TAIL_REF_POS = ('動詞', '形容詞', '助動詞', '形状詞', '接尾辞')

TAIL_NA_DROP_KATSUYOU = '意志推量形'

TAIL_SUFFIX_NA_POS1 = '形状詞的'

PHONETIC_SKIP_POS = ('助詞', '助動詞', '補助記号', '空白')


def merge_mono_ruby(clean_text: str, spans: list) -> list:
    if len(spans) < 2:
        return spans
    def one_word(a, b):
        base = clean_text[spans[a]['start']:spans[b]['end']]
        furi = ''.join(sp['furi'] for sp in spans[a:b + 1])
        with tagger() as (tokenizer_obj, mode):
            toks = list(tokenizer_obj.tokenize(base, mode))
        return len(toks) == 1 and katakana_to_hiragana(toks[0].reading_form()) == katakana_to_hiragana(furi)

    out, i = [], 0
    while i < len(spans):
        j = i
        while j + 1 < len(spans) and spans[j + 1]['start'] == spans[j]['end']:
            j += 1
        k = next((k for k in range(j, i, -1) if one_word(i, k)), None)
        if k is None:
            out.append(spans[i])
            i += 1
        else:
            out.append({'start': spans[i]['start'], 'end': spans[k]['end'],
                        'furi': ''.join(sp['furi'] for sp in spans[i:k + 1])})
            i = k + 1
    return out


_RUBY_MERGES = None

def merge_dict_ruby(clean_text: str, spans: list) -> list:
    global _RUBY_MERGES
    if _RUBY_MERGES is None:
        _RUBY_MERGES = load_ruby_merges(RUBY_TABLES_PATH, 'ruby_dict_merge')
    if len(spans) < 2 or not _RUBY_MERGES:
        return spans

    def listed(a, b):
        base = clean_text[spans[a]['start']:spans[b]['end']]
        return (base, ruby_merge_key(''.join(sp['furi'] for sp in spans[a:b + 1]))) in _RUBY_MERGES

    out, i = [], 0
    while i < len(spans):
        j = i
        while j + 1 < len(spans) and spans[j + 1]['start'] == spans[j]['end']:
            j += 1
        k = next((k for k in range(j, i, -1) if listed(i, k)), None)
        if k is None:
            out.append(spans[i])
            i += 1
        else:
            out.append({'start': spans[i]['start'], 'end': spans[k]['end'],
                        'furi': ''.join(sp['furi'] for sp in spans[i:k + 1])})
            i = k + 1
    return out


_RUBY_WHOLE = None
_RUBY_TRIMS = None

def ruby_base_trim(base: str, furi: str) -> int:
    global _RUBY_WHOLE, _RUBY_TRIMS
    if _RUBY_TRIMS is None:
        _RUBY_TRIMS = load_ruby_trims(RUBY_TABLES_PATH)
    key = (base, ruby_merge_key(furi))
    if key in _RUBY_TRIMS:
        return _RUBY_TRIMS[key]
    if _RUBY_WHOLE is None:
        _RUBY_WHOLE = load_ruby_merges(RUBY_TABLES_PATH, 'ruby_whole')
    if key in _RUBY_WHOLE:
        return 0
    hfuri = katakana_to_hiragana(furi)
    with tagger() as (tokenizer_obj, mode):
        tokens = list(tokenizer_obj.tokenize(base, mode))
    if len(tokens) > 1:
        tail_reading = ""
        tail_len = 0
        for token in reversed(tokens):
            kana = token.reading_form()
            tail_reading = (katakana_to_hiragana(kana) if kana else token.surface()) + tail_reading
            tail_len += len(token.surface())
            if tail_reading == hfuri:
                return len(base) - tail_len

        last = tokens[-1].surface()
        if len(last) < len(base) and len(furi) <= max(3, len(last) * 3):
            head = katakana_to_hiragana("".join(t.reading_form() or t.surface() for t in tokens[:-1]))
            if not (head and len(hfuri) > len(head) and hfuri.startswith(head)):
                tail = katakana_to_hiragana(tokens[-1].reading_form() or last)
                if len(hfuri) > len(tail) and hfuri.endswith(tail):
                    tail_len, first_long = len(last), None
                    for token in reversed(tokens[:-1]):
                        tail = katakana_to_hiragana(token.reading_form() or token.surface()) + tail
                        tail_len += len(token.surface())
                        if len(tail) >= len(hfuri):
                            if tail[0] == hfuri[0]:
                                return len(base) - tail_len
                            first_long = first_long or tail_len
                    return len(base) - (first_long or tail_len)
                return len(base) - len(last)

    if len(base) > 1 and len(furi) == 1 and '一' <= base[-1] <= '鿿':
        return len(base) - 1

    if detect_script(furi) == 'katakana':
        prefix_match = re.match(r'^(歴代全|歴代|全|元|第[０-９0-9一二三四五六七八九十]+期)', base)
        if prefix_match and len(base) > len(prefix_match.group(1)):
            return len(prefix_match.group(1))
    return 0


def _sudachi_normalized_reading(word: str) -> str:
    with tagger() as (tokenizer_obj, mode):
        toks = tokenizer_obj.tokenize(word, mode)
    norm = "".join(t.normalized_form() for t in toks)
    return _sudachi_reading(norm) if norm != word else ""


def gloss_sudachi_evidence(base: str, gloss: str, okuri: str = ""):
    h = ruby_merge_key(gloss)
    cut = ruby_base_trim(base, gloss)
    spans = [base] + ([base[cut:]] if 0 < cut < len(base) else [])
    for s in spans:
        for k in range(len(okuri) + 1):
            written, reading = s + okuri[:k], h + okuri[:k]
            if (ruby_merge_key(_sudachi_reading(written)) == reading
                    or ruby_merge_key(_sudachi_normalized_reading(written)) == reading):
                return written
    return None


_GLOSS_RUBY = None
_GLOSS_DECIDED = None
_GLOSS_KANA_RE = re.compile(r'[ァ-ヺー・]+(?:[ 　]+[ァ-ヺー・]+)*|[ぁ-ゖー・]+(?:[ 　]+[ぁ-ゖー・]+)*')
_OKURI_RE = re.compile(r'[ぁ-ゖ]{1,4}')


@functools.lru_cache(maxsize=65536)
def gloss_span(base: str, gloss: str, okuri: str = ""):
    global _GLOSS_RUBY, _GLOSS_DECIDED
    if not _GLOSS_KANA_RE.fullmatch(gloss):
        return None
    if _GLOSS_RUBY is None:
        _GLOSS_RUBY = load_ruby_merges(RUBY_TABLES_PATH, 'gloss_ruby')
    if _GLOSS_DECIDED is None:
        _GLOSS_DECIDED = frozenset((b, r) for _, b, r in ruby_decisions())
    key, bare = ruby_merge_key(gloss), re.sub(r'[ 　]', '', gloss)
    cuts = [c for c in range(len(base))
            if (base[c:], key) in _GLOSS_RUBY or (base[c:], bare) in _GLOSS_DECIDED][:1]
    written = gloss_sudachi_evidence(base, gloss, okuri)
    if written:
        cuts += [next(c for c in range(len(base) + 1) if written.startswith(base[c:]))]
    cuts = [c for c in cuts if c < len(base)]
    return min(cuts) if cuts else None


def gloss_is_ruby(base: str, gloss: str, okuri: str = "") -> bool:
    return gloss_span(base, gloss, okuri) is not None


def _gloss_okuri(m) -> str:
    after = _OKURI_RE.match(m.string, m.end())
    return after.group(0) if after else ""


def _accept_gloss(m) -> bool:
    return gloss_is_ruby(m.group(2), m.group(3), _gloss_okuri(m))


_BOOK_DISPLAY_RUBY = GlossRuby(_accept_gloss)


def display_ruby_re(media: str):
    if media == 'epub':
        return _BOOK_DISPLAY_RUBY
    return BOOK_RUBY_RE if media == 'manga' else RUBY_RE


_TOKEN_PAREN_RE = re.compile(r'(?<=.)[（(]')
_PAREN_POS = ('補助記号', '括弧開', '*', '*', '*', '*')


def highlight_and_furigana(text: str, content_bases: list, q: str, mark: bool = True, bold: bool = False, base_groups: list = None, readings: list = None, work: tuple = None) -> str:
    if not text: return text
    tag = "mark" if mark else "b"
    if bold: tag = "b"
    
    ruby_spans = []
    clean_text = ""
    last_idx = 0
    for m in display_ruby_re(work[0] if work else 'subs').finditer(text):
        gap = text[last_idx:m.start()]
        base = m.group(1) or m.group(2)
        furi = ruby_reading(m)

        split = None
        if not m.group(1):
            pm = SPACED_RUBY_PREV_RE.search(gap)
            split = pm and spaced_ruby_split(pm.group(1), base, furi, work)
            if split:
                clean_text += gap[:pm.start()]
                ruby_spans.append({'start': len(clean_text), 'end': len(clean_text) + len(pm.group(1)),
                                   'furi': split[0]})
                clean_text += pm.group(1)
                gap = gap[pm.end(1):]
                furi = split[1]

        clean_text += gap
        base_start = len(clean_text)

        if not m.group(1) and not split:
            if work and work[0] == 'epub':
                cut = gloss_span(base, m.group(3), _gloss_okuri(m))
            else:
                cut = ruby_base_trim(base, furi)
            clean_text += base[:cut]
            base_start = len(clean_text)
            base = base[cut:]

        clean_text += base
        base_end = len(clean_text)
        ruby_spans.append({
            'start': base_start,
            'end': base_end,
            'furi': furi
        })
        last_idx = m.end()

    clean_text += text[last_idx:]
    ruby_spans = merge_mono_ruby(clean_text, ruby_spans)
    ruby_spans = merge_dict_ruby(clean_text, ruby_spans)

    extended_bases = set(content_bases)
    exact_matches = []
    phonetic_matches = []
    furi_matches = []

    if q:
        idx = 0
        while True:
            start = clean_text.find(q, idx)
            if start == -1: break
            exact_matches.append((start, start + len(q)))
            idx = start + 1

    words_data = []
    idx = 0
    with tagger() as (tokenizer_obj, mode):
        pieces = [tokenizer_obj.tokenize(piece, mode) for piece in sudachi_pieces(clean_text)]
    for token in (t for toks in pieces for t in toks):
        surface = token.surface()
        start = clean_text.find(surface, idx)
        if start != -1:
            end = start + len(surface)
            pos_full = token.part_of_speech()
            paren = _TOKEN_PAREN_RE.search(surface)
            bracket = None
            if paren:
                bracket = {'surface': surface[paren.start():], 'lemma': '', 'dict_form': '',
                           'reading': '', 'pos': '補助記号', 'pos_full': _PAREN_POS,
                           'start': start + paren.start(), 'end': end}
                surface = surface[:paren.start()]
            words_data.append({
                'surface': surface,
                'lemma': token.normalized_form(),
                'dict_form': token.dictionary_form(),
                'reading': katakana_to_hiragana(token.reading_form() or ''),
                'pos': pos_full[0],
                'pos_full': pos_full,
                'start': start,
                'end': start + len(surface)
            })
            if bracket:
                words_data.append(bracket)
            idx = end

    if readings and q and not re.search(rf'[{KANJI_CHARS}]', q):
        kana_bases = {katakana_to_hiragana(b) for b in content_bases
                      if b and re.fullmatch(r'[぀-ゟ゠-ヿー]+', b)}
        reading_set = {r for r in set(readings) | kana_bases if r and len(r) >= 2}
        if reading_set:
            for w in words_data:
                if w['pos'] in PHONETIC_SKIP_POS:
                    continue
                if w['reading'] and w['reading'] in reading_set:
                    phonetic_matches.append((w['start'], w['end']))
            for r in ruby_spans:
                if r['furi'] and katakana_to_hiragana(r['furi']) in reading_set:
                    furi_matches.append((r['start'], r['end']))

    word_starts = [w['start'] for w in words_data]
    for m_start, m_end in phonetic_matches + furi_matches:
        for k in range(bisect.bisect_left(word_starts, m_start), len(words_data)):
            w = words_data[k]
            if w['start'] > m_end:
                break
            if w['end'] <= m_end:
                w['reading_match'] = True

    char_hl = ['none'] * len(clean_text)

    def token_base(w):
        base = w['lemma'] if w['lemma'] else w['surface']
        return base.split('-')[0] if '-' in base else base

    if base_groups is None:
        single_bases = extended_bases
        sequences = []
    else:
        single_bases = {b for g in base_groups if len(g) == 1 for b in g}
        sequences = [g for g in base_groups if len(g) > 1]

    bound = bound_auxiliary(q) if q else None
    for w in words_data:
        surface = w['surface']
        base = token_base(w)
        if bound:
            w['is_match'] = base == bound[0] and katakana_to_hiragana(w['reading'] or surface).startswith(bound[1])
        else:
            w['is_match'] = (base in single_bases or surface in single_bases or surface == q
                             or w.get('reading_match', False))
        w['hl'] = "main" if w['is_match'] else "none"

    seq_words = [w for w in words_data if w['pos'] != '空白']
    for seq in sequences:
        n = len(seq)
        for i in range(len(seq_words) - n + 1):
            run = seq_words[i:i + n]
            if all(token_base(w) == b or w['surface'] == b for w, b in zip(run, seq)):
                for w in run:
                    w['is_match'] = True
                    w['hl'] = "main"

    def anchor_kind(w):
        p = w['pos_full']
        if p[0] in RUN_ANCHOR_POS:
            return 'full'
        if p[0] == '名詞' and len(p) > 2 and p[2] == RUN_ANCHOR_NOUN_POS2:
            return 'copula'
        return None

    def is_tail(w):
        p = w['pos_full']
        if p[0] in RUN_TAIL_POS:
            return True
        return p[0] == '形状詞' and len(p) > 1 and p[1] == RUN_TAIL_KEIJOUSHI_POS1

    for idx, w in enumerate(words_data):
        if w['hl'] != "main":
            continue
        kind = anchor_kind(w)
        if kind is None:
            continue
        for next_idx in range(idx + 1, len(words_data)):
            next_w = words_data[next_idx]
            if next_w['hl'] == "main":
                break
            if kind == 'copula' and next_idx == idx + 1 and next_w['pos'] != '助動詞':
                break
            if not is_tail(next_w):
                break
            next_w['hl'] = "tail"

    def is_na_adjective(p):
        if p[0] == '形状詞':
            return True
        if p[0] == '名詞' and len(p) > 2 and p[2] == RUN_ANCHOR_NOUN_POS2:
            return True
        return p[0] == '接尾辞' and len(p) > 1 and p[1] == TAIL_SUFFIX_NA_POS1

    def find_reference(j):
        for k in range(j - 1, -1, -1):
            p = words_data[k]['pos_full']
            if p[0] == '助詞':
                continue
            if p[0] in TAIL_REF_POS or is_na_adjective(p):
                return words_data[k]
            return None
        return None

    def classify_tail(w, ref):
        p = w['pos_full']
        if p[0] == '助詞':
            return "tail" if w['surface'] in TAIL_PARTICLE_WHITELIST else "tail-p"
        if p[0] == '接尾辞':
            return "tail"
        if ref is None:
            return "tail-p"
        if is_na_adjective(ref['pos_full']):
            if p[0] == '助動詞' and len(p) > 5 and p[5] == TAIL_NA_DROP_KATSUYOU:
                return "tail-p"
            return "tail"
        return "tail" if ref['surface'] != ref['dict_form'] else "tail-p"

    dropped = False
    for j, w in enumerate(words_data):
        if w['hl'] == "main":
            dropped = False
        elif w['hl'] == "tail":
            if dropped:
                w['hl'] = "tail-p"
            else:
                w['hl'] = classify_tail(w, find_reference(j))
                dropped = w['hl'] == "tail-p"
        else:
            dropped = False

    for w in words_data:
        w_start = w['start']
        w_end = w['end']
        if w['hl'] != "none":
            for i in range(w_start, w_end):
                char_hl[i] = w['hl']
            
    for start, end in exact_matches + phonetic_matches + furi_matches:
        for i in range(start, end):
            char_hl[i] = "main"
            
    in_hl = False
    for i in range(len(char_hl)):
        if char_hl[i] == 'main':
            in_hl = True
        elif char_hl[i] in ('tail', 'tail-p') and in_hl:
            pass
        else:
            in_hl = False
            char_hl[i] = 'none'

    out = []
    ruby_at = {}
    for r in ruby_spans:
        ruby_at.setdefault(r['start'], r)
    i = 0
    current_hl = "none"
    
    def close_hl():
        if current_hl == "main": return f"</{tag}>"
        if current_hl in ("tail", "tail-p"): return "</span>"
        return ""

    def open_hl(hl):
        if hl == "main": return f"<{tag}>"
        if hl == "tail": return '<span class="hl-tail">'
        if hl == "tail-p": return '<span class="hl-tail-p">'
        return ""
        
    while i < len(clean_text):
        ruby = ruby_at.get(i)
        if ruby:
            out.append(close_hl())
            current_hl = "none"

            base_str = clean_text[ruby['start']:ruby['end']]
            is_alpha = bool(re.search(ALPHA_CHARS, base_str))
            cls = ' class="alpha"' if is_alpha else ''
            out.append(f'<ruby{cls}>')
            for j in range(ruby['start'], ruby['end']):
                hl = char_hl[j]
                if hl != current_hl:
                    out.append(close_hl())
                    out.append(open_hl(hl))
                    current_hl = hl
                c = clean_text[j]
                out.append(HTML_ESCAPE_MAP.get(c, c))
            out.append(close_hl())
            current_hl = "none"

            furi_escaped = "".join(HTML_ESCAPE_MAP.get(c, c) for c in ruby["furi"])
            out.append(f'<rt>{furi_escaped}</rt></ruby>')
            i = ruby['end']
            continue

        hl = char_hl[i]
        if hl != current_hl:
            out.append(close_hl())
            out.append(open_hl(hl))
            current_hl = hl

        c = clean_text[i]
        out.append(HTML_ESCAPE_MAP.get(c, c))
        i += 1

    out.append(close_hl())
    result_html = "".join(out)
    
    if not (work and work[0] == 'epub'):
        result_html = result_html.replace('(', '（').replace(')', '）')
    
    return result_html
