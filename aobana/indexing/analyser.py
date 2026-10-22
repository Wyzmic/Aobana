import array
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import time
import zlib
import uuid
import threading
from collections import Counter, defaultdict
from pathlib import Path
from contextlib import closing

from aobana import paths
from aobana.utils import norm_relpath, sub_relpath, is_appledouble_name, parallel_map, line_kind, filtered_rows, write_filtered_rows, refresh_auto_filtered, stop_requested
from aobana.utils import start_output, emit, name_key, MEDIA_EXTS, media_walk, fold_compat

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

SUB_EXTS = MEDIA_EXTS["subs"]
VERSION = 14
BOOK_VERSION = 13
CUSTOM_VERSION = 2
CUSTOM_WALL_CHARS = 1200


class _CheckStopped(Exception):
    pass


class _CheckProgress:
    def __init__(self, workers):
        self.started = self.phase_started = time.monotonic()
        self.lock = threading.Lock()
        self.closed = threading.Event()
        self.last_emit = 0
        self.cache = None
        self.state = dict(stage='subs',phase='traversal',done=0,total=None,current='',workers=workers)
        self.thread = threading.Thread(target=self._heartbeat,daemon=True)

    def _heartbeat(self):
        while not self.closed.wait(.5):
            self.publish()

    def publish(self, force=False):
        now = time.monotonic()
        with self.lock:
            if not force and now-self.last_emit < .2:
                return
            self.last_emit = now
            state = dict(self.state)
            elapsed = now-self.phase_started
        total,done = state['total'],state['done']
        remaining = elapsed*(total-done)/done if total and done >= 3 and elapsed >= 1 else None
        emit('check_phase','',quiet=True,**state,elapsed=round(now-self.started,1),
             phase_elapsed=round(elapsed,1),remaining=round(max(0,remaining),1) if remaining is not None else None)

    def begin(self, phase, total=None, stage=None, **extra):
        self.check()
        with self.lock:
            self.phase_started = time.monotonic()
            self.state.update(phase=phase,done=0,total=total,current='',**extra)
            if stage:
                self.state['stage']=stage
        self.publish(True)

    def check(self):
        if stop_requested():
            raise _CheckStopped()

    def tick(self, done=None, total=None, current=None):
        self.check()
        with self.lock:
            if done is not None: self.state['done']=done
            if total is not None: self.state['total']=total
            if current is not None: self.state['current']=current
        self.publish()

    def sql(self):
        return int(stop_requested())

kind = line_kind


MIN_LINES = 50
BILINGUAL_SHARE = 0.02
JAPANESE_SHARE = 0.5
EPUB_JAPANESE_REVIEW_SHARE = 0.3


MOJIBAKE_LINES = 10
GARBLED_MIN_LINES = 20
GARBLED_SHARE = 0.05
_HIGH_BYTES = re.compile(r"[\x80-\xff]")


def mojibake(line):
    if not _HIGH_BYTES.search(line):
        return False
    for wrong in ("cp1252", "latin-1"):
        try:
            raw = line.encode(wrong)
        except UnicodeEncodeError:
            continue
        for right in ("utf-8", "cp932"):
            try:
                if kind(raw.decode(right)) == "ja":
                    return True
            except UnicodeDecodeError:
                pass
    return False


def language(n, ja, zh, mix, utf8, media="subs", en=0, garbled=0):
    if n < MIN_LINES:
        return None
    if media == "epub":
        named = ja + zh + mix + en
        if named < MIN_LINES:
            return None
        share = ja / named
        if share < EPUB_JAPANESE_REVIEW_SHARE:
            return "other_language"
        return "language_review" if share < JAPANESE_SHARE else None
    if garbled >= MOJIBAKE_LINES:
        return "encoding"
    if (zh + mix) / n >= BILINGUAL_SHARE:
        return "bilingual"
    named = ja + zh + mix + en
    if ja / (named if named >= MIN_LINES else n) < JAPANESE_SHARE:
        return "encoding" if utf8 is False else "other_language"
    return None


NORM = re.compile(r"[^ぁ-ゖァ-ヺー一-鿿]")
SUB_KEY_CHARS = 4
BOOK_KEY_CHARS = 8
SKETCH = 256
DUP_SHARE = 0.5
CUSTOM_DUP_SHARE = 0.8
CUSTOM_DUP_MIN_LINES = 5
SUBPLZ_RE = re.compile(r"^(.*)\.(ja|ae|av|as|ak|az|ab|en)\.srt$", re.IGNORECASE)
SUBPLZ_RANK = {s: i for i, s in enumerate(("ja", "ae", "av", "as", "ak", "az", "ab", "en"))}


def line_keys(lines, min_chars):
    keys = set()
    for l in lines:
        n = NORM.sub("", l)
        if len(n) >= min_chars:
            keys.add(zlib.crc32(n.encode("utf-8")))
    return keys


def _pack(keys):
    return array.array("I", sorted(keys)).tobytes()


def _unpack(blob):
    a = array.array("I")
    a.frombytes(blob or b"")
    return a


def _counts(lines):
    c = Counter(kind(l) for l in lines)
    return len(lines), c["ja"], c["zh"], c["mix"], c["en"]


def stored_text_sha(clean_texts):
    h = hashlib.sha256()
    for text in clean_texts:
        h.update(text.encode("utf-8", "surrogatepass") + b"\n")
    return h.hexdigest()


def _measure_sub(job):
    path, relpath = job
    from aobana.indexing import indexer
    indexer._NOTES.clear()
    indexer._EXCLUDED_LOG.clear()
    indexer._WAKATI_LOG.clear()
    raw = b""
    try:
        lines, details = indexer.parse_subtitle(path, relpath)
        sha = details['sha']
        utf8 = details['encoding'].startswith('utf-8') if path.lower().endswith('.srt') else None
    except Exception as e:
        try:
            with open(path, 'rb') as fh: raw = fh.read()
        except OSError:
            pass
        row = dict(sha=hashlib.sha256(raw).hexdigest() if raw else '', n=0, ja=0, zh=0, mix=0, en=0,
                   utf8=None, keys=b'', distinct=0, title='', author='', details={'status':getattr(e,'reason','unreadable')})
        return relpath, row, f"{type(e).__name__}: {e}"
    n, ja, zh, mix, en = _counts(lines)
    details = {k:v for k,v in details.items() if k != "text"}
    details["mojibake"] = sum(1 for l in lines if mojibake(l))
    details["text_sha"] = stored_text_sha(fold_compat(indexer.get_clean_text_for_mecab(l)) for l in lines)
    from aobana.indexing.duplicate_rules import has_author_furigana
    details["author_furigana"] = has_author_furigana(lines)
    return relpath, {"sha": sha, "n": n, "ja": ja, "zh": zh, "mix": mix, "en": en, "utf8": utf8,
                     "keys": _pack(line_keys((indexer.get_clean_text_for_mecab(l) for l in lines), SUB_KEY_CHARS)), "distinct": 0, "details": details,
                     "title": "", "author": ""}, None


def _measure_book(job):
    path, relpath = job
    from aobana.indexing import epub_indexer
    try:
        measured_stat = os.stat(path)
        author, title, chapters = epub_indexer.extract_epub_content(path)
    except Exception as e:
        return relpath, None, f"{type(e).__name__}: {e}"
    lines = [s for ch in chapters for s in ch["sentences"]]
    n, ja, zh, mix, en = _counts(lines)
    keys = line_keys(lines, BOOK_KEY_CHARS)
    details = {"replacement_lines": sum(1 for l in lines if "\ufffd" in l),
               "replacement_chars": sum(l.count("\ufffd") for l in lines), "chars": sum(len(l) for l in lines)}
    if n == 0 and epub_indexer.drm_locked(path):
        details["drm"] = True
    sha = ''
    if language(n, ja, zh, mix, None, 'epub', en):
        from aobana.indexing.repair import digest
        try:
            sha = digest(path)
            current_stat = os.stat(path)
            if (measured_stat.st_size, measured_stat.st_mtime_ns) != (current_stat.st_size, current_stat.st_mtime_ns):
                return relpath, None, 'File changed while its language was measured'
        except OSError as e:
            return relpath, None, f'{type(e).__name__}: {e}'
    return relpath, {"sha": sha, "n": n, "ja": ja, "zh": zh, "mix": mix, "en": en, "utf8": None,
                     "keys": _pack(sorted(keys)[:SKETCH]), "distinct": len(keys),
                     "title": title or "", "author": author or "", "details": details}, None


def _measure_custom(job):
    from aobana.indexing.subtitle_input import decode_bytes
    path, relpath = job
    raw = b''
    details = {}
    try:
        raw = Path(path).read_bytes()
        text, encoding = decode_bytes(raw)
        physical = text.splitlines()
        nonempty = [line for line in physical if line.strip()]
        details.update(encoding=encoding, longest_line=max(map(len, physical), default=0),
                       empty=not text.strip(), wall=len(nonempty) == 1 and len(nonempty[0]) > CUSTOM_WALL_CHARS,
                       mojibake=sum(mojibake(line) or '\ufffd' in line for line in physical),
                       damaged=encoding.endswith('-damaged'),
                       binary=bool(re.search(r'[\x00-\x08\x0b\x0e-\x1f\x7f]', text)))
        canonical = '\n'.join(line.strip(' \t　') for line in physical).strip('\n')
        details['trimmed_sha'] = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
        if relpath.lower().endswith('.md'):
            from aobana.custom_source import clean_path, link_target
            from aobana.indexing.custom_markdown import links, parse
            clean = clean_path(relpath.replace(chr(92), '/'))
            title = os.path.splitext(clean.split('/')[-1])[0]
            stem = os.path.splitext(clean)[0] + '/'
            navigation = {target for _, target, _ in links(text)
                          if (link_target(clean, target) or '').startswith(stem)}
            body, _ = parse(text, title, navigation)
            lines = [line.strip(' \t　') for line, _, _, _ in body if line.strip()]
        else:
            lines = [line.strip(' \t　') for line in nonempty]
        kinds = [kind(line) for line in lines]
        japanese = [k in ('ja', 'mix') or k == 'other' and bool(re.search('[一-鿿々]', line))
                    for line, k in zip(lines, kinds)]
        latin = [bool(re.search('[A-Za-zＡ-Ｚａ-ｚ]', line)) and not bool(re.search('[ぁ-ゖァ-ヺ一-鿿]', line))
                 for line in lines]
        paired_ja = {i for i, yes in enumerate(japanese) if yes and
                     any(0 <= j < len(lines) and latin[j] for j in (i - 1, i + 1))}
        paired_latin = {i for i, yes in enumerate(latin) if yes and
                        any(0 <= j < len(lines) and japanese[j] for j in (i - 1, i + 1))}
        ja, en = sum(japanese), sum(latin)
        details.update(paired_japanese=len(paired_ja), paired_latin=len(paired_latin),
                       bilingual=bool(ja and en and len(paired_ja) == ja and len(paired_latin) == en))
        zh, mix = kinds.count('zh'), kinds.count('mix')
        details['text_sha'] = stored_text_sha(lines)
        keys = line_keys(lines, SUB_KEY_CHARS)
        row = dict(sha=hashlib.sha256(raw).hexdigest(), n=len(lines), ja=ja, zh=zh, mix=0, en=en,
                   utf8=encoding.startswith('utf-8'), keys=_pack(sorted(keys)[:SKETCH]), distinct=len(keys),
                   title='', author='', details=details)
        return relpath, row, None
    except Exception as error:
        return relpath, dict(sha=hashlib.sha256(raw).hexdigest() if raw else '', n=0, ja=0, zh=0, mix=0, en=0,
                             utf8=None, keys=b'', distinct=0, title='', author='', details=details), f'{type(error).__name__}: {error}'


def custom_duplicates(rows, disk=None, progress=None):
    kept_bytes, kept_text, result = {}, {}, []
    for position, name in enumerate(sub_order(rows, disk), 1):
        if progress:
            progress.tick(position, len(rows), name)
        row = rows[name]
        if row['error'] or not row['n']:
            continue
        sha, text_sha = row['sha'], row['details']['trimmed_sha']
        keep = kept_bytes.get(sha) or kept_text.get(text_sha)
        if keep is not None:
            how = 'same_bytes' if sha == rows[keep]['sha'] else 'same_text'
            result.append((name, keep, 1.0, how))
        else:
            keep = name
        kept_bytes[sha] = keep
        kept_text[text_sha] = keep
    dropped = {r[0] for r in result}
    left = {n: rows[n] for n in rows if n not in dropped and not rows[n]['error'] and rows[n]['n']
            and rows[n].get('distinct', 0) >= CUSTOM_DUP_MIN_LINES}
    order = {n: i for i, n in enumerate(sub_order(left, disk))}
    near = similar_groups(left, CUSTOM_DUP_SHARE, lambda n: (left[n]['distinct'], -order[n]))
    moved = {}
    for name, keep, _ in near:
        result.append((name, keep, custom_share(rows[name], rows[keep]), 'similar_text'))
        moved[name] = keep
    return [(n, moved[k], custom_share(rows[n], rows[moved[k]]), 'similar_text') if k in moved else (n, k, s, h)
            for n, k, s, h in result]


def custom_share(a, b):
    ka, kb = _unpack(a['keys']), _unpack(b['keys'])
    return min(_containment(ka, kb, a['distinct'], b['distinct']),
               _containment(ka, kb, a['distinct'], b['distinct'], of='larger'))


def _open_cache(path):
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE IF NOT EXISTS files (
        media TEXT, relpath TEXT, size INTEGER, mtime INTEGER, version INTEGER,
        sha TEXT, n INTEGER, ja INTEGER, zh INTEGER, mix INTEGER, en INTEGER, utf8 INTEGER,
        keys BLOB, distinct_keys INTEGER, title TEXT, author TEXT, error TEXT,
        PRIMARY KEY (media, relpath))""")
    if "details" not in {r[1] for r in conn.execute("PRAGMA table_info(files)")} :
        conn.execute("ALTER TABLE files ADD COLUMN details TEXT")
        conn.commit()
    return conn


def _walk(root, media, progress=None, duplicates=None):
    out = []
    if not root:
        return out
    from aobana.utils import media_walk_roots
    for source_root, dirpath, files, _ in media_walk_roots(root, media, duplicates):
        if progress: progress.tick(len(out))
        for f in files:
            if progress: progress.check()
            p = os.path.join(dirpath, f)
            try:
                st = os.stat(p)
            except OSError:
                continue
            name = sub_relpath(p, source_root) if media == "subs" else norm_relpath(p, source_root)
            out.append((os.path.relpath(p, source_root), name, p, st.st_size, st.st_mtime_ns))
    return out


def _measure(conn, media, root, files, workers, skip=(), progress=None):
    version = CUSTOM_VERSION if media == 'custom' else BOOK_VERSION if media == 'epub' else VERSION
    conn.execute('CREATE TABLE IF NOT EXISTS root_inputs (media TEXT PRIMARY KEY, roots TEXT)')
    identity = json.dumps([os.path.realpath(folder) for folder in paths.root_list(root)])
    previous = conn.execute('SELECT roots FROM root_inputs WHERE media = ?', (media,)).fetchone()
    if previous and previous[0] != identity:
        conn.execute('DELETE FROM files WHERE media = ?', (media,))
    if not previous or previous[0] != identity:
        conn.execute('INSERT OR REPLACE INTO root_inputs VALUES (?, ?)', (media, identity))
    if media == "epub":
        conn.execute(
            "UPDATE files SET version = ? WHERE media = 'epub' AND version IN (2, 3, 4, 5) "
            "AND n > 200 AND (error IS NULL OR error = '')", (BOOK_VERSION,)
        )
        conn.execute("UPDATE files SET version = 10 WHERE media = 'epub' AND version = 9 AND n > 0")
        conn.commit()
    cached = {r[0]: r for r in conn.execute(
        "SELECT relpath, size, mtime, version FROM files WHERE media = ?", (media,))}
    todo = [(p, name) for _, name, p, size, mtime in files
            if name not in skip and cached.get(name, (None, None, None, None))[1:] != (size, mtime, version)]
    stat = {name: (size, mtime) for _, name, _, size, mtime in files}
    emit("stage", f"STAGE {media}", stage=media)
    emit("total", f"TOTAL {len(todo)}", quiet=True, total=len(todo))
    if progress:
        progress.begin('reading',len(todo),stage=media,cached=len(files)-len(todo),files=len(files))
    fn = _measure_custom if media == 'custom' else _measure_sub if media == "subs" else _measure_book
    last = time.monotonic()
    for i, (name, row, error) in enumerate(parallel_map(fn, todo, min(workers,len(todo)), chunksize=8 if media == "subs" else 1,
                                                        ordered=False, stop=stop_requested), 1):
        if stop_requested():
            break
        emit("progress", f"PROGRESS {i}/{len(todo)} {name}", quiet=True, done=i, total=len(todo), file=name)
        if progress: progress.tick(i,current=name)
        size, mtime = stat[name]
        row = row or {"sha": "", "n": 0, "ja": 0, "zh": 0, "mix": 0, "en": 0, "utf8": None,
                      "keys": b"", "distinct": 0, "title": "", "author": ""}
        conn.execute("INSERT OR REPLACE INTO files VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (media, name, size, mtime, version, row["sha"], row["n"], row["ja"], row["zh"],
                      row["mix"], row["en"], None if row["utf8"] is None else int(row["utf8"]),
                      row["keys"], row["distinct"], row["title"], row["author"], error, json.dumps(row.get("details", {}))))
        if time.monotonic() - last > 2:
            conn.commit()
            last = time.monotonic()
    if stop_requested():
        conn.commit()
        return {}
    names = set(stat)
    conn.executemany("DELETE FROM files WHERE media = ? AND relpath = ?",
                     [(media, n) for n in set(cached) - names])
    conn.commit()
    rows = {}
    for r in conn.execute("SELECT relpath, sha, n, ja, zh, mix, en, utf8, keys, distinct_keys, title, author, error, details "
                          "FROM files WHERE media = ?", (media,)):
        if r[0] in names and r[0] not in skip:
            rows[r[0]] = dict(zip(("name", "sha", "n", "ja", "zh", "mix", "en", "utf8", "keys",
                                   "distinct", "title", "author", "error", "details"), r))
            rows[r[0]]["details"] = json.loads(rows[r[0]]["details"] or "{}")
    return rows


def garbled_book(details):
    return (details.get("replacement_lines", 0) >= GARBLED_MIN_LINES
            and details.get("replacement_chars", 0) >= GARBLED_SHARE * details.get("chars", 0) > 0)


def verdict(media, r):
    if media == 'custom':
        details = r.get('details', {})
        if r['error'] or details.get('mojibake') or details.get('damaged') or details.get('binary'):
            return 'unreadable'
        if details.get('empty') or details.get('wall'):
            return 'empty_or_wall'
        if not r['ja'] and r['n']:
            return 'no_japanese' if r['en'] else 'other_language'
        return 'bilingual' if details.get('bilingual') else None
    if r["error"]:
        return r.get("details", {}).get("status", "unreadable")
    if r["n"] == 0:
        if media == "epub" and r.get("details", {}).get("drm"):
            return "drm"
        return "no_japanese" if media == "subs" else "image_only"
    if media == "epub" and garbled_book(r.get("details", {})):
        return "garbled"
    reason = language(r["n"], r["ja"], r["zh"], r["mix"],
                      None if media == 'subs' or r["utf8"] is None else bool(r["utf8"]), media, r["en"],
                      r.get('details', {}).get('mojibake', 0))
    if reason == "encoding" and media == "subs" and str(r.get('details', {}).get('encoding', '')).startswith('utf-8'):
        return "garbled"
    return reason


def recheck_mark(now, size, mtime):
    return f"{now or 'none'}|{size}|{mtime}"


def _show(name):
    return re.split(r"[\\/]", name, maxsplit=1)[0]


def _subplz(name):
    m = SUBPLZ_RE.match(re.split(r"[\\/]", name)[-1])
    return (m.group(1), m.group(2).lower()) if m else None


def _in_folder(path):
    return os.sep in path or bool(os.altsep and os.altsep in path)


def sub_order(names, disk=None):
    stems = Counter()
    for n in names:
        sp = _subplz(n)
        if sp:
            stems[(os.path.dirname(n), sp[0])] += 1

    def key(n):
        loose = 0 if (disk is None or _in_folder(disk.get(n, n))) else 1
        sp = _subplz(n)
        if sp and stems[(os.path.dirname(n), sp[0])] >= 2:
            return (loose, os.path.join(os.path.dirname(n), sp[0]), SUBPLZ_RANK[sp[1]], n)
        return (loose, os.path.splitext(n)[0], 0, n)
    return sorted(names, key=key)


def subplz_sets(names):
    sets, plain = defaultdict(list), {}
    for n in names:
        sp = _subplz(n)
        if sp:
            sets[(os.path.dirname(n), sp[0])].append((SUBPLZ_RANK[sp[1]], n))
        else:
            base, ext = os.path.splitext(n)
            if ext.lower() in SUB_EXTS:
                plain.setdefault((os.path.dirname(n), os.path.basename(base)), []).append(n)
    out = []
    for (d, stem), members in sets.items():
        members.sort()
        originals = plain.get((d, stem), [])
        has_ja = members[0][0] == SUBPLZ_RANK["ja"]
        if (len(members) < 2 and not (has_ja and originals)) or members[0][0] == SUBPLZ_RANK["en"]:
            continue
        others = [n for r, n in members[1:] if r != SUBPLZ_RANK["en"]] + originals
        if others:
            out.append((members[0][1], others))
    return out


def sub_duplicates(rows, disk=None, progress=None):
    from aobana.indexing.duplicate_rules import recommend
    return recommend(rows, disk or {}, _unpack, subplz_sets, progress=progress.tick if progress else None,
                     workers=paths.index_workers())


def cached_duplicates(cache, media, rows, disk, compute):
    from aobana.indexing import duplicate_rules
    digest = hashlib.sha256(media.encode())
    for module in (duplicate_rules.__file__, __file__):
        with open(module, 'rb') as f:
            digest.update(f.read())
    def plain(value):
        return hashlib.sha256(value).hexdigest() if isinstance(value, (bytes, bytearray, memoryview)) else repr(value)
    for name in sorted(rows):
        digest.update(json.dumps([name, disk.get(name), rows[name]], sort_keys=True, default=plain).encode())
    key = digest.hexdigest()
    cache.execute("CREATE TABLE IF NOT EXISTS duplicates (media TEXT PRIMARY KEY, input TEXT, result TEXT)")
    saved = cache.execute("SELECT input, result FROM duplicates WHERE media = ?", (media,)).fetchone()
    if saved and saved[0] == key:
        return [tuple(d) for d in json.loads(saved[1])], key
    dups = compute()
    cache.execute("INSERT OR REPLACE INTO duplicates VALUES (?, ?, ?)", (media, key, json.dumps(dups)))
    cache.commit()
    return dups, key


def cached_groups(cache, media, key, build):
    cache.execute("CREATE TABLE IF NOT EXISTS recommendations (media TEXT PRIMARY KEY, input TEXT, result TEXT)")
    saved = cache.execute("SELECT input, result FROM recommendations WHERE media = ?", (media,)).fetchone()
    if saved and saved[0] == key:
        return json.loads(saved[1])
    groups = build()
    cache.execute("INSERT OR REPLACE INTO recommendations VALUES (?, ?, ?)", (media, key, json.dumps(groups)))
    cache.commit()
    return groups


def _containment(a, b, na, nb, of="smaller"):
    sa, sb = set(a), set(b)
    union = sorted(sa | sb)[:SKETCH]
    if not union:
        return 0.0
    j = sum(1 for h in union if h in sa and h in sb) / len(union)
    base = max(na, nb) if of == "larger" else min(na, nb)
    if base == 0:
        return 0.0
    return min(1.0, j * (na + nb) / ((1 + j) * base))


def book_duplicates(rows, progress=None):
    rank = lambda n: (rows[n]["n"], -len(re.split(r"[\\/]", n)), [-ord(c) for c in n])
    return [(m, keep, c, "same_text") for m, keep, c in similar_groups(rows, DUP_SHARE, rank, progress)]


def similar_groups(rows, threshold, rank, progress=None):
    names = [n for n in sorted(rows) if not rows[n]["error"] and rows[n]["distinct"]]
    sketch = {n: _unpack(rows[n]["keys"]) for n in names}
    post = defaultdict(list)
    for n in names:
        if progress: progress.tick()
        for h in sketch[n]:
            post[h].append(n)
    pairs = Counter()
    for h, ns in post.items():
        if progress: progress.tick()
        if 1 < len(ns) <= 50:
            for i in range(len(ns)):
                for j in range(i + 1, len(ns)):
                    pairs[(ns[i], ns[j])] += 1
    parent = {n: n for n in names}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    share = {}
    for (a, b), shared in pairs.items():
        if progress: progress.tick()
        if shared < 8 and min(rows[a]["distinct"], rows[b]["distinct"]) > SKETCH:
            continue
        c = _containment(sketch[a], sketch[b], rows[a]["distinct"], rows[b]["distinct"])
        if c >= threshold and _containment(sketch[a], sketch[b], rows[a]["distinct"],
                                           rows[b]["distinct"], of="larger") >= threshold:
            share[(a, b)] = c
            parent[find(a)] = find(b)
    groups = defaultdict(list)
    for n in names:
        groups[find(n)].append(n)
    out = []
    for members in groups.values():
        if len(members) < 2:
            continue
        keep = max(members, key=rank)
        for m in members:
            if m != keep:
                c = share.get((m, keep)) or share.get((keep, m)) or max(
                    (v for (x, y), v in share.items() if m in (x, y)), default=threshold)
                out.append((m, keep, c))
    return out


def report_path():
    return paths.companion('analysis.json')


def cache_path():
    return paths.companion('analysis.db')


def run(only=None):
    progress = _CheckProgress(paths.index_workers())
    progress.thread.start()
    try:
        return _run_checked(only,progress)
    except (_CheckStopped,sqlite3.OperationalError):
        if not stop_requested():
            raise
        emit('stopped','STOPPED')
        return None
    finally:
        progress.closed.set()
        progress.thread.join()
        if progress.cache:
            progress.cache.close()


def _stored_counts(cache, indexed, sources, progress):
    from aobana.indexing import source_ranges
    if "text" not in {r[1] for r in cache.execute("PRAGMA table_info(stored)")}:
        cache.execute("DROP TABLE IF EXISTS stored")
    cache.execute("CREATE TABLE IF NOT EXISTS stored (source_id INTEGER PRIMARY KEY, file_hash TEXT, "
                  "indexed_at TEXT, n INTEGER, ja INTEGER, text TEXT)")
    have = {sid: (h, at, n, ja, text) for sid, h, at, n, ja, text in cache.execute("SELECT * FROM stored")}
    out, todo = {}, {}
    for sid, _, h, at in sources.values():
        c = have.get(sid)
        if c and c[:2] == (h, str(at)):
            out[sid] = c[2:]
        else:
            todo[sid] = (h, str(at))
    if todo:
        n, ja, digest = Counter(), Counter(), {}

        def take(sid, text):
            n[sid] += 1
            ja[sid] += kind(text) == "ja"
            if sid not in digest:
                digest[sid] = hashlib.sha256()
            digest[sid].update(text.encode("utf-8", "surrogatepass") + b"\n")

        if source_ranges.ready(indexed) and len(todo) < len(sources) // 2:
            progress.begin('stored', len(todo))
            for position, sid in enumerate(todo, 1):
                progress.tick(position)
                for first, last, _ in source_ranges.spans(indexed, sid):
                    for (text,) in indexed.execute("SELECT clean_text FROM subtitles WHERE rowid BETWEEN ? AND ? "
                                                   "AND source_id = ? ORDER BY rowid", (first, last, sid)):
                        take(sid, text)
        else:
            top = indexed.execute("SELECT rowid FROM subtitles ORDER BY rowid DESC LIMIT 1").fetchone()
            progress.begin('stored', top[0] if top else 0)
            for row, (rowid, sid, text) in enumerate(indexed.execute(
                    "SELECT rowid, source_id, clean_text FROM subtitles ORDER BY rowid")):
                if row % 100_000 == 0:
                    progress.tick(rowid)
                sid = int(sid)
                if sid in todo:
                    take(sid, text)
        empty = stored_text_sha(())
        for sid, (h, at) in todo.items():
            out[sid] = (n[sid], ja[sid], digest[sid].hexdigest() if sid in digest else empty)
        cache.executemany("INSERT OR REPLACE INTO stored VALUES (?,?,?,?,?,?)",
                          [(sid, h, at, *out[sid]) for sid, (h, at) in todo.items()])
        cache.execute("DELETE FROM stored WHERE source_id NOT IN (SELECT value FROM json_each(?))",
                      (json.dumps(list(out)),))
        cache.commit()
    return out


def _run_checked(only,progress):
    started = time.time()
    roots = {media: paths.roots_value(media) for media in ('subs', 'epub', 'custom')}
    workers = paths.index_workers()
    os.makedirs(os.path.dirname(cache_path()), exist_ok=True)
    conn = _open_cache(cache_path())
    progress.cache = conn
    conn.set_progress_handler(progress.sql,10000)
    items = []
    summary = {}
    groups = []
    repair_items = []
    recheck = []
    generation = uuid.uuid4().hex
    listed = filtered_rows(paths.filtered_list())
    for media in ("subs", "epub", "custom"):
        if (only and media != only) or not paths.media_enabled("books" if media == "epub" else media):
            continue
        root = roots[media]
        if not root or any(not os.path.isdir(folder) for folder in paths.root_list(root)):
            summary[media] = {"files": 0, "root_missing": bool(root)}
            continue
        progress.begin('traversal',stage=media)
        duplicates = []
        files = _walk(root, media, progress, duplicates)
        if media == 'custom':
            files = [entry for entry in files if entry[1].lower().endswith(('.txt', '.md'))]
        for duplicate in duplicates:
            items.append(dict(id=len(items), media=media, lines=0, ja=0, zh=0, en=0,
                              title='', author='', details={}, **duplicate))
        disk = {name: rel for rel, name, _, _, _ in files}
        file_paths = {name: path for _, name, path, _, _ in files}
        file_roots = {name: next(folder for folder in paths.root_list(root)
                                if paths.inside_root(path, folder))
                      for _, name, path, _, _ in files}
        by_key = {name_key(n): n for n in disk}
        listed = [dict(r, name=by_key.get(name_key(r["name"]), r["name"])) if r["media"] == media else r
                  for r in listed]
        skip = {r["name"] for r in listed if r["media"] == media and r["reason"] != "duplicate"}
        progress.begin('cache',stage=media)
        measured = _measure(conn, media, root, files, workers, (), progress)
        rows = {n: r for n, r in measured.items() if n not in skip}
        if stop_requested():
            conn.close()
            emit("stopped", "STOPPED")
            return None

        def add(name, reason, **extra):
            r = rows[name]
            items.append(dict(id=len(items), media=media, name=name, path=disk[name], reason=reason,
                              lines=r["n"], ja=r["ja"], zh=r["zh"] + r["mix"], en=r["en"],
                              title=r["title"], author=r["author"], details={**r.get("details", {}),
                                **({'sha':r['sha']} if r.get('sha') else {}),
                                'measurement_version': CUSTOM_VERSION if media == 'custom' else BOOK_VERSION if media == 'epub' else VERSION}, **extra))
            if len(paths.root_list(root)) > 1:
                items[-1]['root'] = file_roots[name]
        flagged = set()
        progress.begin('language',len(rows))
        for position,name in enumerate(sorted(rows),1):
            progress.tick(position,current=name)
            r = rows[name]
            reason = verdict(media, r)
            if reason:
                add(name, reason, **({"error": r["error"]} if r["error"] else {}))
                flagged.add(name)
            if r["error"] or r["n"] == 0:
                continue
            if media == 'subs' and r.get('details',{}).get('encoding') in ('cp932','utf-16'):
                add(name,'encoding',**({} if os.access(file_paths[name],os.W_OK) else {'read_only':True}))
        left = {n: r for n, r in rows.items() if n not in flagged}
        progress.begin('duplicates')
        dups, dups_key = cached_duplicates(conn, media, left, disk, lambda: sub_duplicates(left, disk, progress)
                                 if media == "subs" else custom_duplicates(left, disk, progress) if media == 'custom' else book_duplicates(left, progress))
        for name, keep, share, how in dups:
            add(name, "duplicate", keep=keep, keep_path=disk[keep], share=round(share, 3), how=how)
        for keep in sorted({d[1] for d in dups}):
            add(keep, "duplicate_kept", keep=keep, keep_path=disk[keep])
        copies = {d[0] for d in dups} | {d[1] for d in dups}
        stat = {name: (size, mtime) for _, name, _, size, mtime in files}
        for saved_row in listed:
            name = saved_row["name"]
            if saved_row["media"] != media or name not in measured:
                continue
            r = measured[name]
            now = verdict(media, r)
            if saved_row["reason"] == "duplicate":
                if name in copies or now:
                    continue
            elif now == saved_row["reason"]:
                continue
            mark = recheck_mark(now, *stat[name])
            if saved_row.get("reviewed") == mark:
                continue
            recheck.append(dict(media=media, name=name, path=disk[name], saved=saved_row["reason"], now=now or "",
                                lines=r["n"], ja=r["ja"], zh=r["zh"] + r["mix"], en=r["en"],
                                error=r["error"] or "", mark=mark))
        from aobana.indexing import repair
        from aobana.indexing.duplicate_rules import RULE_VERSION, hints
        saved = {r["name"]: r for r in listed if r["media"] == media}
        paths_by_name = {name:path for _,name,path,_,_ in files}
        grouped = defaultdict(list)
        for copy, keep, share, how in dups:
            grouped[keep].append((copy, share, how))
        def build():
            built = []
            progress.begin('recommendations',len(grouped))
            for position,(keep, copies) in enumerate(sorted(grouped.items()),1):
                progress.tick(position,current=keep)
                members = []
                for name in [keep] + [c[0] for c in copies]:
                    progress.check()
                    r = rows[name]
                    sha = r["sha"] or repair.digest(paths_by_name[name])
                    own = set(_unpack(r["keys"])); keeper = set(_unpack(rows[keep]["keys"]))
                    shared = len(own & keeper)
                    near = media == 'custom' and any(c[0] == name and c[2] == 'similar_text' for c in copies)
                    members.append(dict(name=name, path=disk[name], sha=sha,
                        overlap=[1.0, 1.0] if media == 'custom' and not near else [shared/len(own) if own else 0, shared/len(keeper) if keeper else 0],
                        saved=saved.get(name), hints=hints(name) if media == "subs" else {}))
                    if len(paths.root_list(root)) > 1:
                        members[-1]['root'] = file_roots[name]
                gid = hashlib.sha256((media + "\0" + "\0".join(sorted(m["name"] for m in members))).encode()).hexdigest()[:24]
                comparisons = {}
                if media == 'subs':
                    from aobana.indexing.duplicate_rules import _shared
                    keys = {m['name']: _unpack(rows[m['name']]['keys']) for m in members}
                    for target in members:
                        progress.check()
                        a = keys[target['name']]
                        comparisons[target['name']] = {}
                        for member in members:
                            b = keys[member['name']]
                            shared = _shared(a, b) if a and b else 0
                            comparisons[target['name']][member['name']] = (
                                1.0 if member['name'] == target['name'] else min(shared/len(a), shared/len(b)) if a and b else 0.0)
                if media == 'epub':
                    for target in members:
                        progress.check()
                        comparisons[target['name']] = {}
                        for member in members:
                            progress.check()
                            a,b = rows[member['name']],rows[target['name']]
                            comparisons[target['name']][member['name']] = min(
                                _containment(_unpack(a['keys']),_unpack(b['keys']),a['distinct'],b['distinct']),
                                _containment(_unpack(a['keys']),_unpack(b['keys']),a['distinct'],b['distinct'],of='larger'))
                if media == 'custom':
                    exact = {keep} | {c[0] for c in copies if c[2] != 'similar_text'}
                    comparisons = {m['name']: {other['name']: 1.0 if m['name'] == other['name'] or {m['name'], other['name']} <= exact
                                               else custom_share(rows[m['name']], rows[other['name']]) for other in members} for m in members}
                built.append(dict(id=gid, media=media, keeper=keep, members=members, comparisons=comparisons,
                    reason=copies[0][2], confidence=min(c[1] for c in copies), rule_version=RULE_VERSION))
            return built
        groups_key = hashlib.sha256(json.dumps([dups_key, sorted((n, stat[n]) for n in left)]).encode()).hexdigest()
        groups.extend(cached_groups(conn, media, groups_key, build))
        if media == "subs":
            progress.begin('repair',len(rows))
            db = paths.subs_db()
            sources = {}
            native_sources = set()
            stored = {}
            if os.path.isfile(db):
                with closing(sqlite3.connect(Path(db).resolve().as_uri() + '?mode=ro', uri=True)) as indexed:
                    indexed.set_progress_handler(progress.sql,10000)
                    sources = {by_key.get(name_key(r[1]), r[1]):r for r in indexed.execute('SELECT id,relpath,file_hash,indexed_at FROM sources')}
                    from aobana.indexing.subtitle_ruby import indexed_native_sources
                    top = indexed.execute("SELECT rowid FROM subtitles ORDER BY rowid DESC LIMIT 1").fetchone()
                    progress.begin('native', top[0] if top else 0)
                    native_sources = indexed_native_sources(indexed, progress.tick)
                    stored = _stored_counts(conn, indexed, sources, progress)
                    progress.begin('repair', len(rows))
            for position,(name,r) in enumerate(rows.items(),1):
                progress.tick(position,current=name)
                info = r.get('details', {})
                source = sources.get(name)
                if source is None or r['error'] or source[2] != r['sha']:
                    continue
                reasons = []
                if info.get('native_ruby') and source[0] in native_sources:
                    reasons.append('Native ruby markup in stored text')
                n, ja, text = stored.get(source[0], (0, 0, None))
                if n >= MIN_LINES and ja / n < JAPANESE_SHARE and r['n'] and r['ja'] / r['n'] >= JAPANESE_SHARE:
                    reasons.append('Stored text garbled')
                if n != r['n']:
                    reasons.append(f'Line count {n} -> {r["n"]}')
                elif not reasons and text and info.get('text_sha') and text != info['text_sha']:
                    reasons.append('Stored text differs')
                if reasons and r["sha"] and source is not None:
                    repair_items.append(dict(name=name, path=disk[name], source_id=source[0] if source else None,
                        indexed_hash=source[2] if source else None, indexed_at=str(source[3]),
                        sha=r['sha'] or repair.digest(paths_by_name[name]),
                        reason='; '.join(reasons), expected_lines=r['n']))
                    if len(paths.root_list(root)) > 1:
                        repair_items[-1]['root'] = file_roots[name]
        summary[media] = {"files": len(rows), "filtered": len(skip & set(disk)),
                          **Counter(i["reason"] for i in items if i["media"] == media)}
    for media in ('manga',):
        if (only and only != media) or not paths.media_enabled(media) or len(paths.media_roots(media)) <= 1:
            continue
        roots[media] = paths.roots_value(media)
        duplicates = []
        files = _walk(roots[media], media, progress, duplicates)
        for duplicate in duplicates:
            items.append(dict(id=len(items), media=media, lines=0, ja=0, zh=0, en=0,
                              title='', author='', details={}, **duplicate))
        summary[media] = dict(files=len(files), duplicate_path=len(duplicates))
    conn.close()
    progress.cache = None
    progress.begin('saving')
    from aobana.indexing.duplicate_rules import RULE_VERSION
    report = {"version": VERSION, "rule_version": RULE_VERSION, "generation": generation, "completed": True, "groups": groups,
              "repair": {"version": 1, "root": roots["subs"], "items": repair_items}, "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
              "seconds": round(time.time() - started, 1), "only": only,
              "roots": roots, "summary": summary, "items": items, "recheck": recheck}
    tmp = report_path() + ".tmp"
    os.makedirs(os.path.dirname(tmp), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    progress.check()
    for attempt in range(60):
        try:
            os.replace(tmp, report_path())
            break
        except PermissionError:
            if attempt == 59:
                raise
            time.sleep(0.5)
    emit("summary", f"ANALYSIS_DONE {json.dumps(summary, ensure_ascii=False)}", summary=summary)
    return report


DB_BYTES_PER_CHAR = {"subs": 33.491, "epub": 25.2075, "manga": 28.9054, "custom": 31.5327}
# 12 workers; line_lengths and ruby_lexicon scale for fewer workers, others are serial.
TABLE_COST_WORKERS = 12
TABLE_COST_PER_ROW = {
    'subs': {'source_ranges': (0.0538806, 0.000000844402), 'line_lengths': (10.20955, 0.00000218972),
             'ruby_lexicon': (4.400246, 0.000000447187), 'kanji': (16.23601, 0.00000405135)},
    'epub': {'chapters': (2.33139, 0.00000151689), 'line_lengths': (8.54414, 0.00000249295),
             'ruby_lexicon': (22.674577, 0.00000440320), 'kanji': (25.36763, 0.00000751510)},
    'manga': {'line_lengths': (10.00263, 0.00000383628), 'ruby_lexicon': (0.485455, 0.00000150073),
              'kanji': (15.99744, 0.00000340153)},
}
TABLE_COST_PER_ROW['custom'] = dict(TABLE_COST_PER_ROW['manga'])
for _media, _seconds in (('subs', 0.00000500), ('epub', 0.00000763), ('manga', 0.00000108), ('custom', 0.00000380)):
    TABLE_COST_PER_ROW[_media]['repeats'] = (0.125, _seconds)
REPEATS_POOL_PER_ROW = {'subs': 15.0 / 53_622_566, 'epub': 152.4 / 136_963_885}


def _repeats_seconds(media, rows, workers):
    from aobana.indexing.line_repeats import POOL_MIN_ROWS
    one = TABLE_COST_PER_ROW[media]['repeats'][1]
    if workers <= 1 or rows < POOL_MIN_ROWS:
        return rows * one
    pooled = REPEATS_POOL_PER_ROW.get(media)
    if pooled is None:
        return rows * one / workers
    return rows * pooled * max(1, TABLE_COST_WORKERS / workers)
PARALLEL_EFFICIENCY = {"subs": 0.9, "epub": 0.89, "manga": 0.89, "custom": 0.89}
SAMPLE = {"subs": 40, "epub": 40, "manga": 40, "custom": 400}
SCALE_BY_BYTES = {"custom"}
WRITE_SECONDS_PER_ROW = {"custom": 0.00031}
ESTIMATE_MEDIA = {"subs": (lambda: paths.roots_value('subs'), paths.subs_db, "subtitles", "subs"),
                  "epub": (lambda: paths.roots_value('epub'), paths.epub_db, "epubs", "books"),
                  "manga": (lambda: paths.roots_value('manga'), paths.manga_db, "manga", "manga"),
                  "custom": (lambda: paths.roots_value('custom'), paths.custom_db, "custom", "custom")}
WARN_TOTAL_BYTES = 10 * 1024 ** 3


def _sample_job(job):
    media, path, relpath = job
    if media == "subs":
        from aobana.indexing import indexer
        indexer.get_tokenizer()
    elif media == "manga":
        from aobana.indexing import manga_indexer
        manga_indexer.get_tokenizer()
    elif media == "custom":
        from aobana.indexing import custom_indexer
        custom_indexer.get_tokenizer()
    else:
        from aobana.indexing import epub_indexer
        epub_indexer.get_tokenizer()
    t = time.perf_counter()
    try:
        c, r = _sample_one(media, path, relpath)
    except Exception:
        c = r = 0
    return c, r, time.perf_counter() - t


def _sample_one(media, path, relpath):
    if media == "subs":
        from aobana.indexing import indexer
        rows = indexer.index_rows(indexer.kept_lines(path, relpath), relpath)
        return sum(len(r[0]) for r in rows), len(rows)
    if media == "manga":
        from aobana.indexing import manga_indexer
        with open(path, encoding="utf-8-sig") as fh:
            doc = json.load(fh)
        rows = manga_indexer.volume_rows(manga_indexer.volume_blocks(doc), relpath)
        return sum(len(r[1][1]) for r in rows), len(rows)
    if media == "custom":
        from aobana.indexing import custom_indexer
        kind, _, _, payload = custom_indexer._prepare((path, relpath, None, paths.custom_trim()))
        if kind != "rows":
            return 0, 0
        rows = payload[3]
        return sum(len(r[1]) for r in rows), sum(1 for r in rows if r[10])
    from aobana.indexing import epub_indexer
    author, title, chapters = epub_indexer.extract_epub_content(path)
    rows = epub_indexer.book_rows(title, chapters)
    return sum(len(r[1]) for r in rows), len(rows)


def _estimate_cache_path():
    return paths.companion('estimate.json')


def _load_estimate_cache():
    try:
        with open(_estimate_cache_path(), encoding="utf-8") as fh:
            doc = json.load(fh)
        return doc if isinstance(doc, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_estimate_cache(doc):
    try:
        os.makedirs(os.path.dirname(_estimate_cache_path()), exist_ok=True)
        tmp = _estimate_cache_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        os.replace(tmp, _estimate_cache_path())
    except OSError:
        pass


def _estimate_key(media, new, workers, reread=()):
    h = hashlib.sha1(repr((media, workers, DB_BYTES_PER_CHAR[media], PARALLEL_EFFICIENCY[media],
                           SAMPLE[media])).encode("utf-8"))
    for tag, files in (("new", new), ("reread", reread)):
        h.update(tag.encode("ascii"))
        for p, name, size, mtime in sorted(files):
            h.update(f"\0{p}\0{name}\0{size}\0{mtime}".encode("utf-8", "surrogatepass"))
    return h.hexdigest()


def _sample_files(media, files, workers, rng):
    by_ext = defaultdict(list)
    for f in files:
        by_ext[os.path.splitext(f[0])[1].lower()].append(f)
    chars = rows = serial = 0.0
    sampled = {}
    for ext, group in sorted(by_ext.items()):
        sample = rng.sample(group, min(len(group), SAMPLE[media]))
        s_chars = s_rows = busy = 0.0
        for c, r, secs in parallel_map(_sample_job, [(media, p, name) for p, name, _ in sample],
                                       min(workers, len(sample))):
            busy += secs
            s_chars += c
            s_rows += r
        scale = len(group) / max(1, len(sample))
        if media in SCALE_BY_BYTES:
            scale = sum(f[2] for f in group) / max(1, sum(f[2] for f in sample))
        chars += s_chars * scale
        rows += s_rows * scale
        serial += busy * scale
        sampled[ext] = len(sample)
    return chars, rows, serial, sampled


def estimate(only=None):
    import random
    from aobana.indexing import line_repeats
    from aobana.search.result_cache import _result_folder
    workers = paths.index_workers()
    out = {"workers": workers, "media": {}}
    cache = _load_estimate_cache()
    cache_changed = False
    for media, (root_of, db_of, table, switch) in ESTIMATE_MEDIA.items():
        root, db = root_of(), db_of()
        size_now = os.path.getsize(db) if os.path.isfile(db) else 0
        m = {"db_now": size_now, "new_files": 0, "new_bytes": 0, "db_add": 0, "rows_add": 0, "seconds": 0}
        out["media"][media] = m
        if (only and media != only) or not root or any(not os.path.isdir(folder) for folder in paths.root_list(root)) or not paths.media_enabled(switch):
            continue
        indexed = set()
        stale = set()
        title_rows, title_of = {}, {}
        excluded = {name_key(r['name']) for r in filtered_rows(paths.filtered_list()) if r['media'] == media}
        if os.path.isfile(db):
            try:
                c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
                indexed = {name_key(r[0]) for r in c.execute("SELECT relpath FROM sources")}
                if media == "custom" and c.execute(
                        "SELECT 1 FROM sqlite_master WHERE name = 'custom_skipped'").fetchone():
                    indexed |= {name_key(r[0]) for r in c.execute("SELECT relpath FROM custom_skipped")}
                from aobana.utils import is_outdated
                if "index_format" in {r[1] for r in c.execute("PRAGMA table_info(sources)")}:
                    stale = {name_key(relpath) for relpath, fmt in c.execute(
                        "SELECT relpath, index_format FROM sources") if is_outdated(media, relpath, fmt)}
                else:
                    stale = set(indexed)
                cols = {r[1] for r in c.execute("PRAGMA table_info(sources)")}
                if media == "custom" and "kind" in cols:
                    from aobana.utils import ruby_outdated, trim_outdated
                    trim, on = paths.custom_trim(), paths.custom_ruby()
                    done = "trimmed" if "trimmed" in cols else "NULL"
                    read = "ruby" if "ruby" in cols else "NULL"
                    stale |= {name_key(relpath) for relpath, kind, was, ruby in c.execute(
                        f"SELECT relpath, kind, {done}, {read} FROM sources")
                        if trim_outdated(kind, was, trim) or ruby_outdated(kind, ruby, on)}
                from aobana.utils import missing_tables, held_removals
                m['tables'] = missing_tables(c, media)
                if m['tables']:
                    from aobana.utils import count_rows
                    m['table_rows'] = count_rows(c, table)
                if 'repeats' not in m['tables'] and media in line_repeats.TABLES:
                    titles, _ = line_repeats._titles(c, media)
                    title_rows = {t: sum(hi - lo + 1 for *_, lo, hi in runs) for t, runs in titles.items()}
                    of_source = {run[0]: t for t, runs in titles.items() for run in runs}
                    title_of = {name_key(rel): of_source[sid] for sid, rel in c.execute("SELECT id, relpath FROM sources")
                                if sid in of_source}
                c.close()
            except sqlite3.Error:
                pass
        inventory = list(_walk(root, media))
        present = {name_key(name) for _, name, _, _, _ in inventory} - excluded
        from aobana.utils import held_removals
        removals, _ = held_removals(len(indexed), indexed-present, excluded, False)
        m['pending_removals'] = len(removals)
        removal_seconds = None
        if removals:
            try:
                with open(paths.companion(os.path.basename(db) + '.phase-history.json', db),encoding='utf-8') as fh:
                    measured = json.load(fh).get('removals',{})
                if measured.get('units',0)>0:
                    removal_seconds = len(removals)*measured['seconds']/measured['units']
                    m['removal_seconds'] = round(removal_seconds,1)
                    m['seconds'] += int(removal_seconds)
            except (OSError, ValueError, KeyError, TypeError):
                pass
        if removals and removal_seconds is None:
            out['duration_unknown'] = True
        indexed |= excluded
        walked = [(p, name, size, mtime) for _, name, p, size, mtime in inventory if name_key(name) not in indexed]
        new = [(p, name, size) for p, name, size, _ in walked]
        m["new_files"], m["new_bytes"] = len(new), sum(s for _, _, s in new)
        stale_walked = [(p, name, size, mtime) for _, name, p, size, mtime in inventory
                        if name_key(name) in stale and name_key(name) not in excluded]
        reread = [(p, name, size) for p, name, size, _ in stale_walked]
        m["reread_files"] = len(reread)
        if title_rows:
            names = {name_key(name) for _, name, _ in new + reread} | set(removals)
            changed = {title_of.get(name) or (media != 'epub' and _result_folder(media, name)) for name in names}
            m['repeats_rows'] = sum(title_rows.get(t, 0) for t in changed if t)
        if not new and not reread:
            continue
        key = _estimate_key(media, walked, workers, stale_walked)
        kept = cache.get(media)
        if isinstance(kept, dict) and kept.get("key") == key:
            m.update({k: kept[k] for k in ("db_add", "rows_add", "seconds", "sampled") if k in kept})
            if removal_seconds is not None:
                m['seconds'] += int(removal_seconds)
            m["kept"] = True
            continue
        rng = random.Random(0)
        chars, rows, serial, m["sampled"] = _sample_files(media, new, workers, rng)
        _, reread_rows, reread_serial, _ = _sample_files(media, reread, workers, rng)
        serial += reread_serial
        m["db_add"] = int(chars * DB_BYTES_PER_CHAR[media])
        m["rows_add"] = int(rows)
        m["seconds"] = int(serial / max(1.0, workers * PARALLEL_EFFICIENCY[media])) if workers > 1 else int(serial)
        m["seconds"] += int((rows + reread_rows) * WRITE_SECONDS_PER_ROW.get(media, 0))
        cache[media] = {"key": key, **{k: m[k] for k in ("db_add", "rows_add", "seconds", "sampled")}}
        if removal_seconds is not None:
            m['seconds'] += int(removal_seconds)
        cache_changed = True
    if cache_changed:
        _save_estimate_cache(cache)
    for media, m in out['media'].items():
        costs = TABLE_COST_PER_ROW.get(media, {})
        missing = m.get('tables', [])
        if any(name not in costs for name in missing):
            out['duration_unknown'] = True
        rows = m.get('table_rows', 0)
        m['table_add'] = sum(max(4096, int(rows * costs[name][0] + 4095) // 4096 * 4096)
                             for name in missing if name in costs and rows)
        m['table_seconds'] = sum(_repeats_seconds(media, rows, workers) if name == 'repeats' else rows * costs[name][1] *
            (max(1, TABLE_COST_WORKERS / max(1, workers)) if name in ('line_lengths', 'ruby_lexicon') else 1)
            for name in missing if name in costs)
        m['db_add'] += m['table_add']
        m['seconds'] += m['table_seconds']
        if 'repeats_rows' in m:
            m['repeats_rows'] += m['rows_add']
            m['repeats_seconds'] = _repeats_seconds(media, m['repeats_rows'], workers)
            m['seconds'] += m['repeats_seconds']
    total =sum(m["db_now"] + m["db_add"] for m in out["media"].values())
    out.update(total_bytes=total, warn=total > WARN_TOTAL_BYTES,
               seconds=sum(m["seconds"] for m in out["media"].values()))
    for media, (_, db_of, _, _) in ESTIMATE_MEDIA.items():
        db = db_of()
        try:
            folder = os.path.dirname(os.path.abspath(db))
            while not os.path.isdir(folder) and os.path.dirname(folder) != folder:
                folder = os.path.dirname(folder)
            out["media"][media]["disk_free"] = shutil.disk_usage(folder).free
        except OSError:
            out["media"][media]["disk_free"] = None
    return out


if __name__ == "__main__":
    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1]
    if "--estimate" in sys.argv:
        print(json.dumps(estimate(only), ensure_ascii=False))
    else:
        start_output()
        run(only)
