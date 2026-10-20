import functools
import re
import unicodedata

from aobana import paths
from aobana.utils import BOOK_RUBY_RE, katakana_to_hiragana, ruby_merge_key, ruby_table
from aobana.search.reading import fold_small, kanji_readings
from aobana.search.furigana import _sudachi_reading, tagger

CHUNK_RE = re.compile(r'([ぁ-ゖー、・ 　]*[ぁ-ゖー])([一-龯々]+)')
MARKS = "、・ 　"
_KANA_RE = re.compile(r'[ぁ-ゖ]')


def _unvoice(s):
    return unicodedata.normalize("NFC", unicodedata.normalize("NFD", s).replace("\u3099", "").replace("\u309a", ""))


def g(s):
    return _unvoice(fold_small(ruby_merge_key(s)))


LIST_FOLDS = (("exact", lambda s: s), ("small", fold_small), ("dakuten", lambda s: _unvoice(fold_small(s))))


def list_splits(K, S, f):
    n = 0

    def walk(k, p):
        nonlocal n
        if n > 1:
            return
        if k == len(K):
            n += p == len(S)
            return
        base = K[k - 1] if K[k] == '々' and k else K[k]
        for r in {f(r) for r in kanji_readings(base)}:
            if r and S.startswith(r, p):
                walk(k + 1, p + len(r))
    walk(0, 0)
    return n


@functools.lru_cache(maxsize=1)
def _frozen_words():
    out = {}
    for _, (word, reading, families, trusted) in ruby_table(paths.RUBY_TABLES_PATH, "manga_word_readings"):
        out.setdefault(word, {})[reading] = (int(families), trusted == "1")
    return out


def frozen_word_readings(term):
    return _frozen_words().get(term, {})


@functools.lru_cache(maxsize=1)
def _frozen_f():
    return {(kana, kanji, "" if okuri == "-" else okuri): reading
            for _, (kana, kanji, okuri, reading) in ruby_table(paths.RUBY_TABLES_PATH, "manga_fused_dictionary")}


class Frozen:

    def b(self, K, S, okuri):
        return dict_reading(K, S, okuri, frozen_word_readings)

    def f(self, K, S, okuri):
        return _frozen_f().get((S, K, okuri))


class Live:

    def __init__(self, words):
        self.words = words

    def b(self, K, S, okuri):
        return dict_reading(K, S, okuri, self.words)

    def f(self, K, S, okuri):
        if self.words(S + K) or self.words(S + K + okuri):
            return None
        return dict_reading(K, S, okuri, self.words)


@functools.lru_cache(maxsize=1)
def reviewed():
    return {(kana, kanji): (base, reading)
            for _, (kana, kanji, base, reading) in ruby_table(paths.RUBY_TABLES_PATH, "manga_fused_reviewed")}


@functools.lru_cache(maxsize=1)
def exceptions():
    return frozenset(tuple(cols) for _, cols in ruby_table(paths.RUBY_TABLES_PATH, "manga_fused_exceptions"))


def candidates(text):
    spans = [(m.start(), m.end()) for m in BOOK_RUBY_RE.finditer(text)]
    for m in CHUNK_RE.finditer(text):
        if not any(a < m.end() and m.start() < b for a, b in spans):
            yield m


def _mark(c):
    d = unicodedata.normalize("NFD", c)
    return 2 if "゚" in d else 1 if "゙" in d else 0


def closeness(r, S):
    return sum(2 * (a == b) + (a != b and _mark(a) > 0 and _mark(b) > 0) for a, b in zip(r, S))


def dict_reading(K, S, okuri, words):
    best = None
    for o in ([okuri] if okuri else []) + [""]:
        want = g(S + o)
        rs = words(K + o)
        if any(g(r) != want and g(r).endswith(g(S)) and rs[r][0] > max(
                [rs[x][0] for x in rs if g(x) == want] or [0]) for r in rs):
            continue
        for r, (families, trusted) in rs.items():
            if g(r) != want or not trusted:
                continue
            r = katakana_to_hiragana(r)
            r = r[:len(r) - len(o)] if o and r.endswith(o) else r
            score = (r == S, closeness(r, S), families)
            if best is None or score > best[0]:
                best = (score, r)
        if best:
            return best[1]
    return None


def _is_particle(S):
    with tagger() as (tok, mode):
        toks = list(tok.tokenize(S, mode))
    return len(toks) == 1 and toks[0].part_of_speech()[0] == "助詞"


def _sets(text, m, bounds, dicts):
    H, K = m.group(1), m.group(2)
    pos = [j for j, c in enumerate(H) if c not in MARKS]
    clean = "".join(H[j] for j in pos)
    nxt = text[m.end():m.end() + 1]
    okuri = nxt if _KANA_RE.fullmatch(nxt) else ""
    out = {}
    for i in range(len(clean) - 1):
        hit = reviewed().get((clean[i:], K))
        if hit:
            out["R"] = (m.start() + pos[i], clean[i:], hit[1], hit[0])
            break
    for i in range(len(clean) - 1):
        S = clean[i:]
        fold = next((name for name, f in LIST_FOLDS if list_splits(K, f(S), f) == 1), None)
        if not fold:
            continue
        start = m.start() + pos[i]
        f = dict(LIST_FOLDS)[fold]
        sud_r = None
        for o in {"", okuri}:
            r = katakana_to_hiragana(_sudachi_reading(K + o))
            if f(ruby_merge_key(r)) == f(S + o):
                sud_r = r[:len(r) - len(o)] if o and r.endswith(o) else r
        if sud_r:
            if len(K) >= 2:
                r = (dicts.b(K, S, okuri) if fold != "exact" else None) or sud_r
                out["A" if fold == "exact" else "B"] = (start, S, r, K)
            elif i == 0 and start in bounds and not _is_particle(S):
                out["C"] = (start, S, sud_r, K)
        elif len(K) >= 3 and len(S) >= 6:
            out["REVIEW"] = (start, S, S, K)
        break
    if len(K) >= 2:
        for i in range(len(clean) - 1):
            S = clean[i:]
            start = m.start() + pos[i]
            if start not in bounds:
                continue
            r = dicts.f(K, S, okuri)
            if r:
                out["F"] = (start, S, r, K)
                break
    return {k: v for k, v in out.items() if (v[1], K) not in exceptions()}


FROZEN = Frozen()


def unfuse(text, dicts=FROZEN):
    ms = list(candidates(text))
    if not ms:
        return text, []
    with tagger() as (tok, mode):
        bounds = {t.begin() for t in tok.tokenize(text, mode)}
    found, edits = [], []
    for m in ms:
        got = _sets(text, m, bounds, dicts)
        rule = next((k for k in ("R", "A", "B", "C", "F") if k in got), None)
        if rule:
            start, S, r, base = got[rule]
            new = f"｜{base}({r}){m.group(2)[len(base):]}"
            edits.append((start, m.end(), new))
            found.append((rule, S, m.group(2), new))
        elif "REVIEW" in got:
            found.append(("REVIEW", got["REVIEW"][1], m.group(2), ""))
    for a, b, new in reversed(edits):
        text = text[:a] + new + text[b:]
    return text, found
