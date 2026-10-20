import collections
from functools import lru_cache
import hashlib
import json
import os
import re
import threading

POLICY = 'iplusone-1'
# Grammar, not vocabulary: a form one of whose dictionary entries is a particle or an auxiliary
# (は is also a noun and a letter's name in the dictionary, ます a noun), or one that is only symbols.
GRAMMAR_POS = frozenset(('助詞', '助動詞'))
SYMBOL_POS = frozenset(('補助記号', '記号', '空白'))
WORD = re.compile(r'[ぁ-ヿ㐀-鿿豈-﫿A-Za-zＡ-Ｚａ-ｚ]')
# i+1 first under おすすめ: how far apart two groups' scores are; おすすめ's own score is at most 1.5
# (the length's 1, the exact match's 0.5), so a group never reaches into the one before it.
GROUP_STEP = 10.0
# i+1 first: the lines that write the searched word in kana as another of its readings (つらい for
# からい) come after every line that holds it as typed, in groups of their own.
OTHER_READING = 100


def first_score(score, i1, known, total, other_reading=False):
    group = 0 if i1 else max(1, total - known)
    return score - GROUP_STEP * (group + OTHER_READING * other_reading)


_DICT = []


def _dictionary():
    if not _DICT:
        from aobana.search.furigana import tagger, _TAGGER_DICT
        with tagger():
            _DICT.append(_TAGGER_DICT[0])
    return _DICT[0]


@lru_cache(maxsize=200_000)
def is_grammar(form):
    if not WORD.search(form):
        return True
    pos = [m.part_of_speech() for m in _dictionary().lookup(form) if m.normalized_form() == form]
    if any(p[0] in GRAMMAR_POS or p[1] == '助動詞語幹' for p in pos):
        return True
    return bool(pos) and all(p[0] in SYMBOL_POS for p in pos)


_SEEN = set()
_GRAMMAR = set()


def _learn_forms(forms):
    for f in forms:
        if is_grammar(f):
            _GRAMMAR.add(f)
        _SEEN.add(f)


def tokenize(text):
    from aobana.search.furigana import tagger
    from aobana.utils import sudachi_pieces
    with tagger() as (tok, mode):
        pieces = [list(tok.tokenize(p, mode)) for p in sudachi_pieces(text)]
    return tuple(m.normalized_form() for ms in pieces for m in ms if not m.surface().isspace())


def target_units(query):
    from aobana.search.furigana import tagger
    with tagger() as (tok, mode):
        words = [m for m in tok.tokenize(query, mode) if not m.surface().isspace()]
    while len(words) > 1 and words[-1].part_of_speech()[0] in ('助動詞', '助詞'):
        words.pop()
    units = tuple(m.normalized_form() for m in words)
    return units if any(not is_grammar(u) for u in units) else ()


def _katakana(text):
    return ''.join(chr(ord(c) + 0x60) if 'ぁ' <= c <= 'ゖ' else c for c in text)


def entry_units(expression, reading=''):
    units = tokenize(expression)
    if len(units) == 1 and reading:
        want = _katakana(reading)
        forms = {m.normalized_form() for m in _dictionary().lookup(expression) if m.reading_form() == want}
        if len(forms) == 1:
            units = (forms.pop(),)
    return units


_VOICED = str.maketrans('がぎぐげござじずぜぞだぢづでどばびぶべぼぱぴぷぺぽ', 'かきくけこさしすせそたちつてとはひふへほはひふへほ')
KANA = re.compile(r'[ぁ-ゖァ-ヺー]+')
LETTER_OR_DIGIT = re.compile(r'[ぁ-ヿ㐀-鿿豈-﫿A-Za-zＡ-Ｚａ-ｚ0-9０-９]')
SPACE_READING = 'きごう'


def _hiragana(text):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in text)


def fold(reading):
    return _hiragana(reading).translate(_VOICED)


@lru_cache(maxsize=20_000)
def readings_of(form):
    return frozenset(fold(m.reading_form()) for m in _dictionary().lookup(form)
                     if m.normalized_form() == form and m.dictionary_form() == form)


def _common_start(a, b):
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


@lru_cache(maxsize=200_000)
def kana_reading(surface, form):
    found = {fold(m.dictionary_form()) for m in _dictionary().lookup(surface) if m.normalized_form() == form}
    got = found & readings_of(form)
    if not got and found:
        best = sorted(((_common_start(r, fold(surface)), r) for r in readings_of(form)), reverse=True)
        if best and best[0][0] and (len(best) == 1 or best[1][0] < best[0][0]):
            got = {best[0][1]}
    return got.pop() if len(got) == 1 else None


def typed_reading(query, target):
    q = query.strip()
    if len(target) != 1 or not KANA.fullmatch(q) or len(readings_of(target[0])) < 2:
        return None
    from aobana.search.furigana import tagger
    with tagger() as (tok, mode):
        got = {fold(m.dictionary_form()) for m in tok.tokenize(q, mode) if m.normalized_form() == target[0]}
    got &= readings_of(target[0])
    return got.pop() if len(got) == 1 else None


def _aligned(tokens, readings):
    rs = (readings or '').split()
    if len(rs) == len(tokens):
        out = rs
    else:
        out, j = [], 0
        for i, tok in enumerate(tokens):
            while (j < len(rs) and rs[j] == SPACE_READING and len(rs) - j > len(tokens) - i
                   and LETTER_OR_DIGIT.search(tok)):
                j += 1
            if j >= len(rs):
                return None
            out.append(rs[j])
            j += 1
        if j != len(rs):
            return None
    if any(r == SPACE_READING and LETTER_OR_DIGIT.search(tok) for tok, r in zip(tokens, out)):
        return None
    return out


@lru_cache(maxsize=1024)
def _first_kanji(form):
    got = re.search(r'[㐀-鿿豈-﫿々]', form)
    return got.group() if got else ''


def other_reading(tokens, readings, clean_text, form, typed):
    if form not in tokens:
        return False
    where = [i for i, tok in enumerate(tokens) if tok == form]
    kanji = _first_kanji(form)
    if kanji and clean_text.count(kanji) >= len(where):
        return False
    if clean_text.count(typed) >= len(where):
        return False
    rs = _aligned(tokens, readings)
    if rs is None:
        return False
    text = _hiragana(clean_text)
    pieces = collections.Counter(_hiragana(rs[i]) for i in where)
    for r, n in pieces.items():
        if text.count(r) < n or kana_reading(r, form) in (None, typed):
            return False
    return True


GRAMMAR, KNOWN, UNKNOWN = 0, 1, 2


class Vocabulary:

    __slots__ = ('singles', 'phrases', 'fingerprint', 'entries', 'kind', 'longest', 'parts', 'part_forms')

    def __init__(self, singles, phrases, fingerprint, entries):
        self.singles = frozenset(singles)
        self.phrases = {}
        for seq in phrases:
            self.phrases.setdefault(seq[0], []).append(tuple(seq))
        self.longest = max((len(p) for ps in self.phrases.values() for p in ps), default=1)
        self.parts = {}
        for ps in self.phrases.values():
            for p in ps:
                for off, f in enumerate(p):
                    self.parts.setdefault(f, []).append((p, off))
        self.part_forms = frozenset(self.parts)
        self.fingerprint = fingerprint
        self.entries = entries
        self.kind = {}

    def kind_of(self, form):
        k = GRAMMAR if is_grammar(form) else KNOWN if form in self.singles else UNKNOWN
        if len(self.kind) < 500_000:
            self.kind[form] = k
        return k

    def knows(self, unit):
        unit = tuple(unit)
        return (len(unit) == 1 and unit[0] in self.singles) or unit in self.phrases.get(unit[0], ())

    def to_json(self):
        return {'policy': POLICY, 'fingerprint': self.fingerprint, 'entries': self.entries,
                'singles': sorted(self.singles),
                'phrases': sorted(p for ps in self.phrases.values() for p in ps)}


def compile_vocabulary(entries):
    units = set()
    for expression, reading in entries:
        seq = entry_units(expression, reading) if expression else ()
        if seq and any(not is_grammar(u) for u in seq):
            units.add(seq)
    singles = {s[0] for s in units if len(s) == 1}
    phrases = sorted(s for s in units if len(s) > 1)
    digest = hashlib.sha256(json.dumps([POLICY, sorted(units)], ensure_ascii=False).encode('utf-8'))
    return Vocabulary(singles, phrases, digest.hexdigest()[:16], len(units))


def row_units(base_forms, clean_text='', media=''):
    if media == 'custom' and '\u2029' in (clean_text or ''):
        return tokenize(clean_text.split('\u2029', 1)[0])
    return tuple((base_forms or '').split())


def _hits(tokens, target):
    n = len(target)
    if n == 1:
        t = target[0]
        if t not in tokens:
            return ()
        return {i for i, tok in enumerate(tokens) if tok == t}
    return {i + j for i in range(len(tokens) - n + 1) if tuple(tokens[i:i + n]) == target for j in range(n)}


def _covered(tokens, vocab, wanted):
    out = set()
    phrases, longest, n = vocab.phrases, vocab.longest, len(tokens)
    tried = set()
    for p in wanted:
        if p in out:
            continue
        for i in range(max(0, p - longest + 1), p + 1):
            if i in tried:
                continue
            tried.add(i)
            for phrase in phrases.get(tokens[i], ()):
                end = i + len(phrase)
                if end <= n and tuple(tokens[i:end]) == phrase:
                    out.update(q for q in range(i, end) if q in wanted)
    return out


def analyze(tokens, target, vocab, stop_at=None, positional=False, target_known=None):
    kind, kind_of = vocab.kind.get, vocab.kind_of
    if target_known is None:
        target_known = bool(target) and vocab.knows(target)
    if len(target) == 1 and not positional:
        forms = set(tokens)
        t = target[0]
        found = t in forms
        forms.discard(t)
        new = forms - _SEEN
        if new:
            _learn_forms(new)
        content = forms - _GRAMMAR
        others = len(content)
        unknown_forms = content - vocab.singles
        parts = vocab.parts
        suspects = unknown_forms & vocab.part_forms if parts else ()
        unknown = len(unknown_forms) - len(suspects)
        if stop_at is not None and unknown > stop_at:
            return False, 0, 0
        if suspects:
            present = forms | {t} if found else forms
            for tok in suspects:
                near = [(p, off) for p, off in parts[tok] if present.issuperset(p)]
                if not near or any(not any(0 <= i - off and tuple(tokens[i - off:i - off + len(p)]) == p
                                           for p, off in near)
                                   for i, x in enumerate(tokens) if x == tok):
                    unknown += 1
            if stop_at is not None and unknown > stop_at:
                return False, 0, 0
        total = others + found
        if target_known:
            return found and unknown == 1, total - unknown, total
        return found and not unknown, total - unknown - found, total
    hit = _hits(tokens, target) if target else ()
    unknown_at = {}
    others = set()
    for i, tok in enumerate(tokens):
        k = kind(tok)
        if k is None:
            k = kind_of(tok)
        if k == GRAMMAR or (hit and i in hit):
            continue
        others.add(tok)
        if k == UNKNOWN:
            unknown_at[i] = tok
            if stop_at is not None and not vocab.phrases and len(set(unknown_at.values())) > stop_at:
                return False, 0, 0
    if unknown_at and vocab.phrases:
        for i in _covered(tokens, vocab, unknown_at):
            del unknown_at[i]
    unknown = len(set(unknown_at.values()))
    if stop_at is not None and unknown > stop_at:
        return False, 0, 0
    found = bool(hit)
    total = len(others) + found
    if target_known:
        return found and unknown == 1, total - unknown, total
    return found and not unknown, total - unknown - found, total


def classify(tokens, target, vocab, target_known, typed=None, readings='', clean_text='', stop_at=None):
    if typed and other_reading(tokens, readings, clean_text or '', target[0], typed):
        if stop_at is not None:
            return False, 0, 0, True
        return analyze(tokens, (), vocab) + (True,)
    return analyze(tokens, target, vocab, stop_at=stop_at, target_known=target_known) + (False,)


_LOCK = threading.Lock()
_LOADED = {}


def snapshot_path():
    from aobana import paths
    return os.path.join(paths.known_words_dir(), 'snapshot.json')


def save_snapshot(vocab):
    path = snapshot_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as fh:
        json.dump(vocab.to_json(), fh, ensure_ascii=False)
    os.replace(tmp, path)
    with _LOCK:
        _LOADED.pop(path, None)


def drop_snapshot():
    path = snapshot_path()
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    with _LOCK:
        _LOADED.pop(path, None)


def current():
    path = snapshot_path()
    try:
        mtime = os.stat(path).st_mtime_ns
    except OSError:
        return None
    with _LOCK:
        got = _LOADED.get(path)
        if got and got[0] == mtime:
            return got[1]
    try:
        with open(path, encoding='utf-8') as fh:
            data = json.load(fh)
        if data.get('policy') != POLICY:
            return None
        vocab = Vocabulary(data['singles'], data['phrases'], data['fingerprint'], data['entries'])
    except (OSError, ValueError, KeyError):
        return None
    if not vocab.entries:
        return None
    with _LOCK:
        _LOADED[path] = (mtime, vocab)
    return vocab


class StaleVocabulary(Exception):
    pass


def resolve(learn):
    if not learn:
        return None
    mode, _, fp = learn.partition(':')
    vocab = current()
    if vocab is None or vocab.fingerprint != fp:
        raise StaleVocabulary(learn)
    return mode, vocab


def learn_token(mode):
    if mode not in ('first', 'only'):
        return ''
    vocab = current()
    return f'{mode}:{vocab.fingerprint}' if vocab is not None else None
