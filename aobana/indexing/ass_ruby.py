import collections
import re
import unicodedata

from aobana import paths
from aobana.utils import ALPHA_CHARS, RUBY_RE, katakana_to_hiragana, ruby_merge_key, ruby_table

POS = re.compile(r"\\pos\(\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)")
AN = re.compile(r"\\an(\d)")
GAIJI = re.compile(r"\[外:[0-9A-Fa-f]+\]")
SEG = re.compile(r"(\{[^}]*\})|([^{]+)")
SIZE_TAG = re.compile(r"\\(fscx|fsp|fs)(-?[\d.]+)")
KANA = re.compile(r"[\u3041-\u3096\u30a1-\u30fa\u30fc]+")
HIRAGANA = re.compile(r"[ぁ-ゖ]")
KATAKANA_READING = re.compile(r"[\u30a1-\u30fa\u30fc・･\s]+")
HIRAGANA_READING = re.compile(r"[ぁ-ゖー・･\s]+")
KANJI = re.compile(r"[\u4e00-\u9fff\u3005\u30f6]")
BASEISH = re.compile(r"[\u4e00-\u9fff\u3005\u30f60-9\uff10-\uff19]")
ALPHAISH = re.compile(rf"[{ALPHA_CHARS}．]")
LATIN_OR_DIGIT = re.compile(rf"[{ALPHA_CHARS}．\-－]+")
JOINER = re.compile(r"[\-－‐・･]+")
PUNCT = re.compile(r"[「」『』（）()《》［］【】〈〉｛｝、。，,！!？?…―—]+")
SMALL = set("ゃゅょぁぃぅぇぉゎャュョァィゥェォヮ")
K_RANGE = [round(0.5 + 0.025 * i, 3) for i in range(23)]
H_RANGE = [0.45, 0.5, 0.55, 0.6]
NOT_ATTACHED = {"misplaced", "no-kanji-below", "nobase"}
PAIRS_PATH = paths.RUBY_TABLES_PATH

_SUDACHI = {}
_CTX = {}
_POS = {}
_LEX = {}


def sudachi():
    if not _SUDACHI:
        from sudachipy import dictionary, tokenizer
        d = dictionary.Dictionary(dict="core")
        _SUDACHI.update(dict=d, tok=d.create(), mode=tokenizer.Tokenizer.SplitMode.A)
    return _SUDACHI


def fold(s):
    return unicodedata.normalize("NFC", "".join(
        c for c in unicodedata.normalize("NFD", s) if c not in "\u3099\u309a"))


def key_of(reading):
    return fold(ruby_merge_key(reading))


class Evidence:
    sources = ()

    def attests(self, seg, key, source):
        return False

    def whole(self, term):
        return set()

    def readings(self, surface):
        return set()

    def kanji(self, ch):
        return set()

    def bases_of(self, key):
        return set()

    def substitute(self, line, i0, j0, reading):
        return None


class FrozenEvidence(Evidence):
    sources = ("frozen",)

    def __init__(self, path=PAIRS_PATH):
        self.pairs, self.by_base, self.by_key = set(), collections.defaultdict(set), collections.defaultdict(set)
        for _, (base, reading) in ruby_table(path, "ass_pairs"):
            k = key_of(reading)
            self.pairs.add((base, k))
            self.by_base[base].add(k)
            self.by_key[k].add(base)

    def attests(self, seg, key, source):
        return (seg, key) in self.pairs

    def whole(self, term):
        return self.by_base.get(term, set())

    def readings(self, surface):
        return self.by_base.get(surface, set())

    def bases_of(self, key):
        return self.by_key.get(key, set())


def is_half(ch):
    return ord(ch) < 0x2000 or 0xFF61 <= ord(ch) <= 0xFF9F


def styles(content):
    out, fields, sec = {}, None, None
    for line in content.splitlines():
        s = line.strip()
        if s.startswith("["):
            sec = s.lower()
        elif sec in ("[v4+ styles]", "[v4 styles]") and s.lower().startswith("format:"):
            fields = [f.strip().lower() for f in s.split(":", 1)[1].split(",")]
        elif sec in ("[v4+ styles]", "[v4 styles]") and s.lower().startswith("style:") and fields:
            row = dict(zip(fields, [v.strip() for v in s.split(":", 1)[1].split(",")]))
            try:
                out[row["name"].lower()] = (float(row.get("fontsize", 40)), float(row.get("scalex", 100)),
                                            float(row.get("spacing", 0)), int(row.get("alignment", 2)))
            except ValueError:
                pass
    return out


def visible(raw):
    out, fs, fscx, fsp = [], None, None, None
    for tag, text in SEG.findall(raw):
        if tag:
            for name, val in SIZE_TAG.findall(tag):
                v = float(val)
                if name == "fscx":
                    fscx = v
                elif name == "fs":
                    fs = v
                else:
                    fsp = v
            continue
        for part in re.split(r"(\\[Nn])", text):
            if part in ("\\N", "\\n"):
                out.append((None, (fs, fscx, fsp), False))
                continue
            pos = 0
            for m in GAIJI.finditer(part):
                out += [(c, (fs, fscx, fsp), False) for c in part[pos:m.start()].replace("\\h", " ")]
                out.append(("〓", (fs, fscx, fsp), True))
                pos = m.end()
            out += [(c, (fs, fscx, fsp), False) for c in part[pos:].replace("\\h", " ")]
    return out


def layout(ev, st, k=1.0, h=0.5):
    size, scx, spacing, align = st
    m = POS.search(ev["tags"])
    if not m:
        return None
    x = float(m.group(1))
    a = AN.search(ev["tags"])
    align = int(a.group(1)) if a else align
    chars, cur = [], 0.0
    for ch, (fs, fscx, fsp), _ in visible(ev["raw"]):
        if ch is None:
            continue
        fs, fscx, fsp = fs if fs is not None else size, fscx if fscx is not None else scx, fsp if fsp is not None else spacing
        w = k * fs * fscx / 100 * (h if is_half(ch) else 1.0)
        chars.append((ch, cur, cur + w))
        cur += w + fsp
    width = cur
    shift = {1: 0, 4: 0, 7: 0, 2: -width / 2, 5: -width / 2, 8: -width / 2}.get(align, -width)
    return [(c, l + x + shift, r + x + shift) for c, l, r in chars]


def context_readings(line):
    s_ = sudachi()
    out = [None] * len(line)
    for t in s_["tok"].tokenize(line, s_["mode"]):
        s, e = t.begin(), t.end()
        for i in range(s, e):
            out[i] = (s, e, katakana_to_hiragana(t.reading_form()))
    return out


def affix(line, n):
    if line not in _POS:
        if len(_POS) > 20000:
            _POS.clear()
        s_ = sudachi()
        _POS[line] = {t.begin(): t.part_of_speech()[0] for t in s_["tok"].tokenize(line, s_["mode"])
                      if t.end() - t.begin() == 1 and t.part_of_speech()[0] in ("接尾辞", "接頭辞")}
    return _POS[line].get(n)


def ctx_of(line):
    if line not in _CTX:
        if len(_CTX) > 20000:
            _CTX.clear()
        _CTX[line] = context_readings(line)
    return _CTX[line]


def split_token(surface, reading, greedy=False):
    pieces = [(m.start(), m.end(), bool(KANA.fullmatch(m.group())))
              for m in re.finditer(r"[ぁ-ゖァ-ヺー]+|[^ぁ-ゖァ-ヺー]+", surface)]
    if not any(k for _, _, k in pieces) or all(k for _, _, k in pieces):
        return None
    pat = "".join(re.escape(katakana_to_hiragana(surface[s:e])) if k else ("(.+)" if greedy else "(.+?)")
                  for s, e, k in pieces)
    m = re.fullmatch(pat, reading)
    if not m:
        return None
    out, g = {}, 1
    for s, e, k in pieces:
        if k:
            out[(s, e)] = katakana_to_hiragana(surface[s:e])
        else:
            out[(s, e)] = m.group(g)
            g += 1
    return out


def span_reading(line, ctx, a, b):
    parts, i = [], a
    while i < b:
        if not ctx[i]:
            return None
        s, e, r = ctx[i]
        if s >= a and e <= b:
            parts.append(r)
            i = e
            continue
        x, y = max(a, s), min(b, e)
        split = split_token(line[s:e], r)
        if not split:
            return None
        got = [(ps + s, pe + s, pr) for (ps, pe), pr in sorted(split.items()) if x <= ps + s and pe + s <= y]
        if not got or got[0][0] != x or got[-1][1] != y:
            return None
        parts.extend(pr for _, _, pr in got)
        i = y
    return "".join(parts)


def lexicon_readings(surface):
    if surface not in _LEX:
        _LEX[surface] = {katakana_to_hiragana(m.reading_form()) for m in sudachi()["dict"].lookup(surface)
                         if m.surface() == surface}
    return _LEX[surface]


def lexicon_has(line, ctx, a, b, want):
    if want in lexicon_readings(line[a:b]):
        return True
    if not ctx[a] or ctx[a][0] > a or ctx[a][1] < b:
        return False
    s, e, _ = ctx[a]
    for r in lexicon_readings(line[s:e]):
        split = split_token(line[s:e], r)
        if not split:
            continue
        got = [(ps + s, pe + s, pr) for (ps, pe), pr in sorted(split.items()) if a <= ps + s and pe + s <= b]
        if got and got[0][0] == a and got[-1][1] == b and "".join(p for _, _, p in got) == want:
            return True
    return False


def lexicon_near(line, ctx, i0, j0, want):
    for a, b in ((i0 + 1, j0 + 1), (i0, j0)):
        if b - a < 1 or not all(BASEISH.match(c) for c in line[a:b]):
            continue
        if any(fold(r) == fold(want) for r in lexicon_readings(line[a:b])):
            return a, b
    return None


LETTER_NAMES = {
    "A": "エー エイ", "B": "ビー", "C": "シー", "D": "ディー デー", "E": "イー", "F": "エフ", "G": "ジー",
    "H": "エッチ エイチ", "I": "アイ", "J": "ジェー ジェイ", "K": "ケー ケイ", "L": "エル", "M": "エム",
    "N": "エヌ", "O": "オー", "P": "ピー", "Q": "キュー", "R": "アール", "S": "エス", "T": "ティー テー",
    "U": "ユー", "V": "ブイ ヴィー ヴイ", "W": "ダブリュー ダブル", "X": "エックス", "Y": "ワイ",
    "Z": "ゼット ズィー",
    "0": "ゼロ レイ オー", "1": "ワン イチ ファースト", "2": "ツー ニ トゥー セカンド", "3": "スリー サン サード",
    "4": "フォー ヨン フォース", "5": "ファイブ ゴ フィフス", "6": "シックス ロク", "7": "セブン ナナ",
    "8": "エイト ハチ", "9": "ナイン キュウ", "-": "", ".": "",
}
NAMES = {k: {katakana_to_hiragana(n) for n in v.split()} or {""} for k, v in LETTER_NAMES.items()}


def spelled(seg, reading):
    s = unicodedata.normalize("NFKC", seg).upper().replace("−", "-")
    want = katakana_to_hiragana(re.sub(r"[・･\s]", "", reading))
    if not s or any(c not in NAMES for c in s):
        return False
    reach = {0}
    for c in s:
        reach = {k + len(n) for k in reach for n in NAMES[c] if want.startswith(n, k)}
        if not reach:
            return False
    return len(want) in reach


def spelled_span(line, i0, j0, reading):
    best = None
    for a in range(max(0, i0 - 4), min(len(line), i0 + 3)):
        for b in range(max(a + 1, j0 - 1), min(len(line), j0 + 5) + 1):
            if spelled(line[a:b], reading):
                cost = abs(a - i0) + abs(b - 1 - j0)
                if best is None or cost < best[0]:
                    best = (cost, a, b)
    return best


def alpha_run(line, i, j):
    def ok(c):
        return bool(ALPHAISH.match(c))
    while i > 0 and ok(line[i - 1]):
        i -= 1
    while j + 1 < len(line) and ok(line[j + 1]):
        j += 1
    return i, j


def latin_start(line, i0):
    i = i0
    while i > 0 and i0 - i < 16:
        c = line[i - 1]
        if ALPHAISH.match(c) or JOINER.fullmatch(c) or (c in " 　" and i > 1 and ALPHAISH.match(line[i - 2])):
            i -= 1
        else:
            break
    return i


NUMERALS = set("0123456789０１２３４５６７８９一二三四五六七八九十百千万")


def numeral_readings(ch):
    out = {katakana_to_hiragana(r) for r in lexicon_readings(ch)} | NAMES.get(unicodedata.normalize("NFKC", ch), set())
    out |= {r[:-1] + "っ" for r in out if len(r) > 1 and r[-1] in "ちつくう"}
    return out


def strip_numerals(line, i, j, reading):
    want = katakana_to_hiragana(re.sub(r"[・･\s]", "", reading))
    while j > i and line[j] in NUMERALS and not any(r and want.endswith(r) for r in numeral_readings(line[j])):
        j -= 1
    while i < j and line[i] in NUMERALS and not any(r and want.startswith(r) for r in numeral_readings(line[i])):
        i += 1
    return i, j


def attested_span(line, i0, j0, reading, ev, source):
    want = key_of(reading)
    best = None
    for a in range(max(0, i0 - 2), min(len(line), i0 + 3)):
        for b in range(max(a + 1, j0 - 1), min(len(line), j0 + 3) + 1):
            seg = line[a:b]
            if not BASEISH.search(seg) and not ALPHAISH.search(seg) or seg[0] in " 　" or seg[-1] in " 　":
                continue
            if ev.attests(seg, want, source):
                cost = abs(a - i0) + abs(b - 1 - j0)
                if best is None or cost < best[0]:
                    best = (cost, a, b)
    return best


def snap(line, ctx, i0, j0, reading):
    want = katakana_to_hiragana(reading)
    best = None
    for a in range(max(0, i0 - 2), min(len(line), i0 + 3)):
        for b in range(max(a + 1, j0 - 1), min(len(line), j0 + 3) + 1):
            seg = line[a:b]
            if not all(BASEISH.match(c) for c in seg):
                continue
            if span_reading(line, ctx, a, b) == want:
                cost = abs(a - i0) + abs(b - 1 - j0)
                if best is None or cost < best[0]:
                    best = (cost, a, b)
    return best


def suffix_cut(line, ctx, i, j, reading):
    if not HIRAGANA_READING.fullmatch(reading) or j - i < 2 or not ctx[j] or ctx[j][0] != j or ctx[j][1] != j + 1:
        return j
    if not KANJI.fullmatch(line[j]):
        return j
    want = katakana_to_hiragana(reading)
    reads = {ctx[j][2]} | lexicon_readings(line[j])
    if any(r and want.endswith(r) for r in reads):
        return j
    if line[j - 1] in " 　" or affix(line, j) == "接尾辞" or any(r and key_of(want).endswith(r) for r in char_reads(line, ctx, j - 1)):
        return j - 1
    return j


def trim(line, ctx, i0, j0):
    i, j = i0, j0
    if ctx[j] and ctx[j][1] > j + 1 and KANJI.search(line[j + 1:ctx[j][1]]) and ctx[j][0] > i:
        j = ctx[j][0] - 1
    elif ctx[j] and ctx[j][1] > j + 1 and KANJI.fullmatch(line[j + 1]) and ctx[j][0] <= i:
        j = ctx[j][1] - 1
    if ctx[i] and ctx[i][0] < i and KANJI.search(line[ctx[i][0]:i]):
        sp = [n for n in range(i, j + 1) if line[n] in " 　"]
        i = sp[0] + 1 if sp else ctx[i][0]
    while i <= j and not BASEISH.match(line[i]):
        i += 1
    while j >= i and not BASEISH.match(line[j]):
        j -= 1
    return None if (i, j) == (i0, j0) or i > j else (i, j)


def char_reads(line, ctx, n):
    ch = line[n]
    out = set(lexicon_readings(ch))
    if ch in NUMERALS:
        out |= numeral_readings(ch)
    if ctx[n]:
        s, e, r = ctx[n]
        if e - s == 1:
            out.add(r)
        else:
            split = split_token(line[s:e], r)
            if split and (n - s, n - s + 1) in split:
                out.add(split[(n - s, n - s + 1)])
    return {key_of(r) for r in out if r}


def run_edge(line, n, step):
    m = n + step
    return m < 0 or m >= len(line) or not BASEISH.match(line[m])


def edge_keep(line, ctx, i0, j0, i, j, reading):
    want = key_of(reading)
    hira = bool(HIRAGANA_READING.fullmatch(reading))
    if j < j0 and all(BASEISH.match(c) for c in line[j + 1:j0 + 1]):
        if run_edge(line, j0, 1) or hira and any(r and want.endswith(r) for r in char_reads(line, ctx, j0)):
            j = j0
    if i > i0 and all(BASEISH.match(c) for c in line[i0:i]):
        if run_edge(line, i0, -1) or hira and any(r and want.startswith(r) for r in char_reads(line, ctx, i0)):
            i = i0
    if i < i0 and hira and not reads_head(line, ctx, i, i0, want):
        i = i0
    return i, j


def reads_head(line, ctx, a, b, want):
    grown = span_reading(line, ctx, a, b)
    if grown and want.startswith(key_of(grown)):
        return True
    reach = {0}
    for n in range(a, b):
        reach = {k + len(r) for k in reach for r in char_reads(line, ctx, n) if r and want.startswith(r, k)}
        if not reach:
            return False
    return True


def token_complete(line, ctx, i, j, reading):
    if not KATAKANA_READING.fullmatch(reading):
        return i, j
    n = j + 1
    if n < len(line) and KANJI.fullmatch(line[n]):
        in_token = ctx[j] and ctx[j][1] == n + 1 and ctx[j][0] <= j
        ends = run_edge(line, n, 1) and not (n + 1 < len(line) and HIRAGANA.match(line[n + 1]))
        if in_token or ends:
            j = n
    n = i - 1
    if n >= 0 and KANJI.fullmatch(line[n]):
        in_token = ctx[i] and ctx[i][0] == n and ctx[i][1] > i
        if (in_token or run_edge(line, n, -1)) and affix(line, n) != "接頭辞" and KANJI.search(line[i:j + 1]):
            i = n
    return i, j


def compose(line, ctx, a, b, reading, ev, abbrev=False):
    want = key_of(reading)
    words, i = [], a
    while i < b:
        if not ctx[i] or ctx[i][0] < a or ctx[i][1] > b:
            return None
        s, e, r = ctx[i]
        words.append((s, e, r))
        i = e
    wild = abbrev and len(words) > 1 and KATAKANA_READING.fullmatch(reading) and \
        LATIN_OR_DIGIT.fullmatch(line[words[0][0]:words[0][1]]) and words[0][1] - words[0][0] <= 4
    if abbrev and not wild:
        return None
    reach = {0: ([], False)}
    for n, (s, e, r) in enumerate(words):
        surf = line[s:e]
        nxt = {}
        for k, (path, used) in reach.items():
            if PUNCT.fullmatch(surf) or not surf.strip(" 　") or JOINER.fullmatch(surf):
                nxt.setdefault(k, (path + [(s, e, None)], used))
                continue
            ev_opts = set()
            if n == 0 and wild:
                opts = {want[k:k2] for k2 in range(k + 1, len(want))}
            elif KANA.fullmatch(surf):
                opts = {katakana_to_hiragana(surf)}
            elif LATIN_OR_DIGIT.fullmatch(surf):
                ev_opts = {want[k:k2] for k2 in range(k + 1, len(want) + 1)
                           if want[k:k2] in ev.whole(surf) or want[k:k2] in ev.readings(surf)}
                opts = {want[k:k2] for k2 in range(k + 1, len(want) + 1) if spelled(surf, want[k:k2])} | ev_opts
            else:
                ev_opts = ev.readings(surf) | ev.whole(surf) | (ev.kanji(surf) if len(surf) == 1 else set())
                opts = {r} | {katakana_to_hiragana(x) for x in lexicon_readings(surf)} | ev_opts
            for o in opts:
                o = key_of(o)
                if o and want.startswith(o, k):
                    nxt.setdefault(k + len(o), (path + [(s, e, o)], used or o in {key_of(x) for x in ev_opts}))
        reach = nxt
        if not reach:
            return None
    if len(want) not in reach:
        return None
    path, used = reach[len(want)]
    if wild and not used:
        return None
    parts, cur = [], None
    for s, e, o in path:
        if o is None and PUNCT.fullmatch(line[s:e]):
            cur = None
            continue
        if cur is None:
            cur = [s, e, o or ""]
            parts.append(cur)
        else:
            cur[1], cur[2] = e, cur[2] + (o or "")
    return [tuple(p) for p in parts if p[2]]


def composed_span(line, ctx, i0, j0, reading, ev, abbrev=False):
    far = latin_start(line, i0)
    best = None
    for a in range(min(far, max(0, i0 - 2)), min(len(line), i0 + 3)):
        for b in range(max(a + 1, j0 - (3 if abbrev else 1)), min(len(line), j0 + 3) + 1):
            parts = compose(line, ctx, a, b, reading, ev, abbrev)
            if parts:
                cost = abs(a - i0) + abs(b - 1 - j0)
                if best is None or cost < best[0]:
                    best = (cost, parts)
    return best


def known_elsewhere(line, reading, ev):
    bases = ev.bases_of(key_of(reading))
    if not bases:
        return None
    hits = [(line.find(b), line.find(b) + len(b)) for b in bases if b and line.find(b) >= 0]
    if hits:
        return max(hits, key=lambda h: h[1] - h[0])
    return False if all(LATIN_OR_DIGIT.fullmatch(b) for b in bases) else None


def ruby_tasks(events, content):
    st_all = styles(content)
    by_time = collections.defaultdict(list)
    for ev in events:
        by_time[(ev["start"], ev["end"])].append(ev)
    tasks = []
    for group in by_time.values():
        bases = [e for e in group if not e["drop"] and POS.search(e["tags"])]
        for r in group:
            if r["drop"] not in ("ruby-small", "ruby-style") or not POS.search(r["tags"]):
                continue
            ry = float(POS.search(r["tags"]).group(2))
            below = [(float(POS.search(b["tags"]).group(2)) - ry, b) for b in bases
                     if float(POS.search(b["tags"]).group(2)) > ry]
            row = []
            if below:
                dmin = min(d for d, _ in below)
                row = [b for d, b in below if d - dmin < 2]
            tasks.append((r, row, st_all))
    return tasks


def has_half(task):
    return any(is_half(c) and c != " " for b in task[1] for c in b["text"])


def grade(task, k, h=0.5, ev=None):
    ev = ev or Evidence()
    r, row, st_all = task
    st = st_all.get(r["style"].lower()) or st_all.get("default")
    if not st or not row:
        return "nobase", None
    rl = layout(r, st, k, h)
    if not rl:
        return "nobase", None
    r0, r1 = rl[0][1], rl[-1][2]
    mid = (r0 + r1) / 2
    best = None
    for b in row:
        bl = layout(b, st_all.get(b["style"].lower()) or st, k, h)
        if not bl:
            continue
        dist = 0 if bl[0][1] <= mid <= bl[-1][2] else min(abs(mid - bl[0][1]), abs(mid - bl[-1][2]))
        if best is None or dist < best[0]:
            best = (dist, bl, b)
    if not best:
        return "nobase", None
    bl, base_ev = best[1], best[2]
    slack = (bl[0][2] - bl[0][1]) / 2
    under = [i for i, (c, l, rr) in enumerate(bl) if r0 - slack <= (l + rr) / 2 <= r1 + slack]
    idx = [i for i in under if BASEISH.match(bl[i][0])]
    line = "".join(c for c, _, _ in bl)
    reading = r["text"].replace(" ", "").replace("\u3000", "")
    want = katakana_to_hiragana(reading)
    case = {"line": line, "reading": reading, "event": base_ev}
    ctx = ctx_of(line)
    if not idx:
        alpha = [i for i in under if ALPHAISH.match(bl[i][0])]
        if not alpha:
            case.update(i=None, j=None, geo="")
            return "no-kanji-below", case
        a, b = alpha_run(line, alpha[0], alpha[-1])
        for w in re.finditer(r"[^ 　]+", line[a:b + 1]):
            if key_of(reading) in ev.whole(w.group()) or spelled(w.group(), reading):
                a, b = a + w.start(), a + w.end() - 1
                break
        case.update(i=a, j=b, geo=line[alpha[0]:alpha[-1] + 1])
        sp = spelled_span(line, alpha[0], alpha[-1], reading)
        if sp:
            case.update(i=sp[1], j=sp[2] - 1)
            return "spelled", case
        if key_of(reading) in ev.whole(line[a:b + 1]):
            return "alpha-dictionary", case
        for source in ev.sources:
            at = attested_span(line, alpha[0], alpha[-1], reading, ev, source)
            if at:
                case.update(i=at[1], j=at[2] - 1)
                return source, case
        cs = composed_span(line, ctx, a, b, reading, ev)
        if cs and len(cs[1]) == 1:
            case.update(i=cs[1][0][0], j=cs[1][0][1] - 1)
            return "composed", case
        return "alpha-base", case
    i0, j0 = idx[0], idx[-1]
    case.update(i=i0, j=j0, geo=line[i0:j0 + 1])
    if span_reading(line, ctx, i0, j0 + 1) == want:
        return "geometry-exact", case
    s = snap(line, ctx, i0, j0, reading)
    if s:
        case.update(i=s[1], j=s[2] - 1)
        return "snapped", case
    if lexicon_has(line, ctx, i0, j0 + 1, want):
        return "lexicon", case
    sp = spelled_span(line, i0, j0, reading)
    if sp:
        case.update(i=sp[1], j=sp[2] - 1)
        return "spelled", case
    for source in ev.sources:
        at = attested_span(line, i0, j0, reading, ev, source)
        if at:
            case.update(i=at[1], j=at[2] - 1)
            return source, case
    for abbrev in (False, True):
        cs = composed_span(line, ctx, i0, j0, reading, ev, abbrev)
        if cs:
            parts = cs[1]
            case.update(i=parts[0][0], j=parts[-1][1] - 1)
            if len(parts) > 1:
                case["parts"] = [[s, e - 1, r] for s, e, r in parts]
                return "composed-split", case
            return "composed-abbrev" if abbrev else "composed", case
    far = known_elsewhere(line, reading, ev)
    if far:
        case.update(i=far[0], j=far[1] - 1)
        return "corpus-far", case
    if far is False and ctx[j0] and ctx[j0][1] > j0 + 1 and KANA.fullmatch(line[j0 + 1:ctx[j0][1]]):
        return "misplaced", case
    sub = ev.substitute(line, i0, j0, reading)
    if sub:
        case.update(i=sub[0], j=sub[1] - 1)
        return "substitution", case
    ln = lexicon_near(line, ctx, i0, j0, want)
    if ln:
        case.update(i=ln[0], j=ln[1] - 1)
        return "lexicon", case
    j1 = suffix_cut(line, ctx, i0, j0, reading)
    t = trim(line, ctx, i0, j1)
    i, j = t if t else (i0, j1)
    i, j = strip_numerals(line, i, j, reading)
    if (i, j) != (i0, j1):
        i, j = edge_keep(line, ctx, i0, j1, i, j, reading)
    i, j = token_complete(line, ctx, i, j, reading)
    if (i, j) != (i0, j0):
        case.update(i=i, j=j)
        a, b = i, j + 1
        if span_reading(line, ctx, a, b) == want or lexicon_has(line, ctx, a, b, want) or compose(line, ctx, a, b, reading, ev):
            return "trimmed-verified", case
        return "trimmed", case
    return "unverified", case


def fit(tasks, fixed=False, ev=None):
    if fixed:
        return 1.0, 0.5
    probe = tasks[:: max(1, len(tasks) // 60)]
    k = max(K_RANGE, key=lambda kk: (sum(grade(tk, kk)[0] == "geometry-exact" for tk in probe),
                                      -abs(kk - 0.8)))
    half = [tk for tk in tasks if has_half(tk)]
    if not half:
        return k, 0.5
    half = half[:: max(1, len(half) // 60)]
    h = max(H_RANGE, key=lambda hh: (sum(grade(tk, k, hh)[0] == "geometry-exact" for tk in half),
                                      -abs(hh - 0.5)))
    return k, h


def placements(g, case):
    if g in NOT_ATTACHED or not case or case.get("i") is None:
        return []
    reading = case["reading"]
    if not case.get("parts"):
        return [(case["i"], case["j"], reading)]
    out, pos = [], 0
    for s, e, key in case["parts"]:
        start = pos
        while pos < len(reading) and key_of(reading[start:pos]) != key:
            pos += 1
        if key_of(reading[start:pos]) != key:
            return [(case["i"], case["j"], reading)]
        out.append((s, e, reading[start:pos]))
    return out


def ruby_text(base, reading):
    s = f"｜{base}({reading})"
    m = RUBY_RE.fullmatch(s)
    return s if m and m.group(1) == base and m.group(3) == reading else None


def annotate(ev, rubies):
    glyphs = visible(ev["raw"])
    drawn = [n for n, (c, _, _) in enumerate(glyphs) if c is not None]
    starts, attached, skipped = {}, 0, 0
    taken = set()
    for i, j, reading in sorted(rubies):
        if any(n in taken for n in range(i, j + 1)) or j >= len(drawn):
            skipped += 1
            continue
        if any(glyphs[drawn[n]][2] for n in range(i, j + 1)):
            skipped += 1
            continue
        if any(glyphs[m][0] is None for m in range(drawn[i], drawn[j] + 1)):
            skipped += 1
            continue
        base = "".join(glyphs[drawn[n]][0] for n in range(i, j + 1))
        rt = ruby_text(base, reading)
        if not rt:
            skipped += 1
            continue
        starts[drawn[i]] = (drawn[j], rt)
        taken.update(range(i, j + 1))
        attached += 1
    out, n = [], 0
    while n < len(glyphs):
        c, _, gaiji = glyphs[n]
        if n in starts:
            end, rt = starts[n]
            out.append(rt)
            n = end + 1
            continue
        out.append("\n" if c is None else ("" if gaiji else c))
        n += 1
    text = "".join(out)
    text = "\n".join(t.strip() for t in text.split("\n") if t.strip())
    return text, attached, skipped


def attach(events, content, ev=None, stats=None):
    ev = ev or FROZEN()
    tasks = ruby_tasks(events, content)
    if not tasks:
        return
    k, h = fit(tasks)
    per_event = collections.defaultdict(set)
    for tk in tasks:
        g, case = grade(tk, k, h, ev)
        if stats is not None:
            stats["grade:" + g] += 1
        for i, j, reading in placements(g, case):
            per_event[id(case["event"])].add((i, j, reading))
    by_id = {id(e): e for e in events}
    done = {}
    for eid, rubies in per_event.items():
        base = by_id[eid]
        text, a, s = annotate(base, rubies)
        done[(base["start"], base["end"], base["text"], POS.search(base["tags"]).group(0))] = text
        base["text"] = text
        if stats is not None:
            stats["attached"] += a
            stats["skipped"] += s
    for e in events:
        if e["drop"] or not POS.search(e["tags"]):
            continue
        key = (e["start"], e["end"], e["text"], POS.search(e["tags"]).group(0))
        if key in done:
            e["text"] = done[key]


_FROZEN = []


def FROZEN():
    if not _FROZEN:
        _FROZEN.append(FrozenEvidence())
    return _FROZEN[0]
