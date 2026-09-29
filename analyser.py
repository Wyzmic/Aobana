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
from collections import Counter, defaultdict

import paths
from utils import norm_relpath, sub_relpath, parallel_map, line_kind, filtered_rows, write_filtered_rows, refresh_auto_filtered, stop_requested

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PROGRESS = os.environ.get("AOBANA_PROGRESS") == "1"
SUB_EXTS = ('.srt', '.ass', '.ssa')
VERSION = 2
BOOK_VERSION = 5

kind = line_kind


MIN_LINES = 50
BILINGUAL_SHARE = 0.02
JAPANESE_SHARE = 0.5
EPUB_JAPANESE_REVIEW_SHARE = 0.3


def language(n, ja, zh, mix, utf8, media="subs", en=0):
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
    if (zh + mix) / n >= BILINGUAL_SHARE:
        return "bilingual"
    if ja / n < JAPANESE_SHARE:
        return "encoding" if utf8 is False else "other_language"
    return None


NORM = re.compile(r"[^ぁ-ゖァ-ヺー一-鿿]")
SUB_KEY_CHARS = 4
BOOK_KEY_CHARS = 8
SKETCH = 256
DUP_SHARE = 0.5
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


def _measure_sub(job):
    path, relpath = job
    import indexer
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
        sha = hashlib.sha256(raw).hexdigest()
        utf8 = None
        if path.lower().endswith(".srt"):
            try:
                raw.decode("utf-8")
                utf8 = True
            except UnicodeDecodeError:
                utf8 = False
        lines = indexer.kept_lines(path, relpath)
    except Exception as e:
        return relpath, None, f"{type(e).__name__}: {e}"
    n, ja, zh, mix, en = _counts(lines)
    return relpath, {"sha": sha, "n": n, "ja": ja, "zh": zh, "mix": mix, "en": en, "utf8": utf8,
                     "keys": _pack(line_keys(lines, SUB_KEY_CHARS)), "distinct": 0,
                     "title": "", "author": ""}, None


def _measure_book(job):
    path, relpath = job
    import epub_indexer
    try:
        author, title, chapters = epub_indexer.extract_epub_content(path)
    except Exception as e:
        return relpath, None, f"{type(e).__name__}: {e}"
    lines = [s for ch in chapters for s in ch["sentences"]]
    n, ja, zh, mix, en = _counts(lines)
    keys = line_keys(lines, BOOK_KEY_CHARS)
    return relpath, {"sha": "", "n": n, "ja": ja, "zh": zh, "mix": mix, "en": en, "utf8": None,
                     "keys": _pack(sorted(keys)[:SKETCH]), "distinct": len(keys),
                     "title": title or "", "author": author or ""}, None


def _open_cache(path):
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE IF NOT EXISTS files (
        media TEXT, relpath TEXT, size INTEGER, mtime INTEGER, version INTEGER,
        sha TEXT, n INTEGER, ja INTEGER, zh INTEGER, mix INTEGER, en INTEGER, utf8 INTEGER,
        keys BLOB, distinct_keys INTEGER, title TEXT, author TEXT, error TEXT,
        PRIMARY KEY (media, relpath))""")
    return conn


def _walk(root, media):
    out = []
    if not root or not os.path.isdir(root):
        return out
    for dirpath, _, files in os.walk(root):
        for f in files:
            if media == "subs":
                if not f.lower().endswith(SUB_EXTS):
                    continue
            elif not f.lower().endswith(".epub") or f.startswith("."):
                continue
            p = os.path.join(dirpath, f)
            try:
                st = os.stat(p)
            except OSError:
                continue
            name = sub_relpath(p, root) if media == "subs" else norm_relpath(p, root)
            out.append((norm_relpath(p, root), name, p, st.st_size, st.st_mtime_ns))
    return out


def _measure(conn, media, root, files, workers, skip=()):
    version = BOOK_VERSION if media == 'epub' else VERSION
    if media == "epub":
        conn.execute(
            "UPDATE files SET version = 5 WHERE media = 'epub' AND version IN (2, 3, 4) "
            "AND n > 200 AND (error IS NULL OR error = '')"
        )
        conn.commit()
    cached = {r[0]: r for r in conn.execute(
        "SELECT relpath, size, mtime, version FROM files WHERE media = ?", (media,))}
    todo = [(p, name) for _, name, p, size, mtime in files
            if name not in skip and cached.get(name, (None, None, None, None))[1:] != (size, mtime, version)]
    stat = {name: (size, mtime) for _, name, _, size, mtime in files}
    print(f"STAGE {media}", flush=True)
    if PROGRESS:
        print(f"TOTAL {len(todo)}", flush=True)
    fn = _measure_sub if media == "subs" else _measure_book
    last = time.monotonic()
    for i, (name, row, error) in enumerate(parallel_map(fn, todo, workers, chunksize=8 if media == "subs" else 1,
                                                        ordered=False, stop=stop_requested), 1):
        if stop_requested():
            break
        if PROGRESS:
            print(f"PROGRESS {i}/{len(todo)} {name}", flush=True)
        size, mtime = stat[name]
        row = row or {"sha": "", "n": 0, "ja": 0, "zh": 0, "mix": 0, "en": 0, "utf8": None,
                      "keys": b"", "distinct": 0, "title": "", "author": ""}
        conn.execute("INSERT OR REPLACE INTO files VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (media, name, size, mtime, version, row["sha"], row["n"], row["ja"], row["zh"],
                      row["mix"], row["en"], None if row["utf8"] is None else int(row["utf8"]),
                      row["keys"], row["distinct"], row["title"], row["author"], error))
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
    for r in conn.execute("SELECT relpath, sha, n, ja, zh, mix, en, utf8, keys, distinct_keys, title, author, error "
                          "FROM files WHERE media = ?", (media,)):
        if r[0] in names and r[0] not in skip:
            rows[r[0]] = dict(zip(("name", "sha", "n", "ja", "zh", "mix", "en", "utf8", "keys",
                                   "distinct", "title", "author", "error"), r))
    return rows


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


def sub_duplicates(rows, disk=None):
    out, dropped = [], set()
    for keep, others in subplz_sets([n for n in rows if not rows[n]["error"]]):
        for n in others:
            out.append((n, keep, 1.0, "subplz"))
            dropped.add(n)
    first = {}
    for name in sub_order(list(rows), disk):
        sha = rows[name]["sha"]
        if not sha or rows[name]["error"] or name in dropped:
            continue
        if sha in first:
            out.append((name, first[sha], 1.0, "same_bytes"))
            dropped.add(name)
        else:
            first[sha] = name
    by_show = defaultdict(list)
    for name in rows:
        if name not in dropped and not rows[name]["error"]:
            by_show[_show(name)].append(name)
    folder_owner = {}
    loose_left = []
    for show, names in by_show.items():
        owner = {}
        for name in sub_order(names, disk):
            k = _unpack(rows[name]["keys"])
            hits = Counter(owner[h] for h in k if h in owner)
            if len(k) and hits:
                same, n = hits.most_common(1)[0]
                if n >= DUP_SHARE * len(k):
                    out.append((name, same, n / len(k), "same_lines"))
                    dropped.add(name)
                    continue
            for h in k:
                owner.setdefault(h, name)
            if disk is not None and not _in_folder(disk.get(name, name)):
                loose_left.append(name)
            else:
                for h in k:
                    folder_owner.setdefault(h, name)
    for name in sub_order(loose_left, disk):
        k = _unpack(rows[name]["keys"])
        hits = Counter(folder_owner[h] for h in k if h in folder_owner)
        if len(k) and hits:
            same, n = hits.most_common(1)[0]
            if n >= DUP_SHARE * len(k):
                out.append((name, same, n / len(k), "same_lines"))
                continue
        for h in k:
            folder_owner.setdefault(h, name)
    return out


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


def book_duplicates(rows):
    names = [n for n in sorted(rows) if not rows[n]["error"] and rows[n]["distinct"]]
    sketch = {n: _unpack(rows[n]["keys"]) for n in names}
    post = defaultdict(list)
    for n in names:
        for h in sketch[n]:
            post[h].append(n)
    pairs = Counter()
    for h, ns in post.items():
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
        if shared < 8 and min(rows[a]["distinct"], rows[b]["distinct"]) > SKETCH:
            continue
        c = _containment(sketch[a], sketch[b], rows[a]["distinct"], rows[b]["distinct"])
        if c >= DUP_SHARE and _containment(sketch[a], sketch[b], rows[a]["distinct"],
                                           rows[b]["distinct"], of="larger") >= DUP_SHARE:
            share[(a, b)] = c
            parent[find(a)] = find(b)
    groups = defaultdict(list)
    for n in names:
        groups[find(n)].append(n)
    out = []
    for members in groups.values():
        if len(members) < 2:
            continue
        keep = max(members, key=lambda n: (rows[n]["n"], -int(_in_folder(n)), [-ord(c) for c in n]))
        for m in members:
            if m != keep:
                c = share.get((m, keep)) or share.get((keep, m)) or max(
                    (v for (x, y), v in share.items() if m in (x, y)), default=DUP_SHARE)
                out.append((m, keep, c, "same_text"))
    return out


def report_path():
    return os.path.join(os.path.dirname(os.path.abspath(paths.subs_db())), "analysis.json")


def cache_path():
    return os.path.join(os.path.dirname(os.path.abspath(paths.subs_db())), "analysis.db")


def run(only=None):
    started = time.time()
    roots = {"subs": paths.subs_dir(), "epub": paths.books_dir()}
    workers = paths.index_workers()
    os.makedirs(os.path.dirname(cache_path()), exist_ok=True)
    conn = _open_cache(cache_path())
    items = []
    summary = {}
    listed = filtered_rows(paths.filtered_list())
    for media in ("subs", "epub"):
        if only and media != only:
            continue
        root = roots[media]
        if not root or not os.path.isdir(root):
            summary[media] = {"files": 0, "root_missing": bool(root)}
            continue
        files = _walk(root, media)
        disk = {name: rel for rel, name, _, _, _ in files}
        if media == "epub":
            listed = refresh_auto_filtered(paths.filtered_list(), media,
                                           {name: path for _, name, path, _, _ in files})
            cached = {r[0]: r for r in conn.execute(
                "SELECT relpath, n, ja, zh, mix, en FROM files WHERE media = 'epub' "
                "AND (error IS NULL OR error = '')")}
            file_paths = {name: path for _, name, path, _, _ in files}
            rescue = set()
            for entry in listed:
                name = entry["name"]
                if entry["media"] != "epub" or entry["reason"] != "other_language" or name not in file_paths:
                    continue
                old = cached.get(name)
                if not old or not old[1] or language(old[1], old[2], old[3], old[4], None, "epub", old[5]) == "other_language":
                    continue
                _, fresh, error = _measure_book((file_paths[name], name))
                if not error and fresh["n"] and language(fresh["n"], fresh["ja"], fresh["zh"],
                                                           fresh["mix"], None, "epub", fresh["en"]) != "other_language":
                    rescue.add(name)
            if rescue:
                listed = [r for r in listed if not (r["media"] == "epub" and r["reason"] == "other_language"
                                                     and r["name"] in rescue)]
                write_filtered_rows(paths.filtered_list(), listed)
        skip = {r["name"] for r in listed if r["media"] == media}
        rows = _measure(conn, media, root, files, workers, skip)
        if stop_requested():
            conn.close()
            print("STOPPED", flush=True)
            return None

        def add(name, reason, **extra):
            r = rows[name]
            items.append(dict(id=len(items), media=media, name=name, path=disk[name], reason=reason,
                              lines=r["n"], ja=r["ja"], zh=r["zh"] + r["mix"], en=r["en"],
                              title=r["title"], author=r["author"], **extra))
        flagged = set()
        for name in sorted(rows):
            r = rows[name]
            if r["error"]:
                add(name, "unreadable", error=r["error"])
                flagged.add(name)
                continue
            if media == "epub" and r["n"] == 0:
                add(name, "image_only")
                flagged.add(name)
                continue
            lang = language(r["n"], r["ja"], r["zh"], r["mix"],
                            None if r["utf8"] is None else bool(r["utf8"]), media, r["en"])
            if lang:
                add(name, lang)
                flagged.add(name)
        left = {n: r for n, r in rows.items() if n not in flagged}
        dups = sub_duplicates(left, disk) if media == "subs" else book_duplicates(left)
        for name, keep, share, how in dups:
            add(name, "duplicate", keep=keep, keep_path=disk[keep], share=round(share, 3), how=how)
        for keep in sorted({d[1] for d in dups}):
            add(keep, "duplicate_kept", keep=keep, keep_path=disk[keep])
        summary[media] = {"files": len(rows), "filtered": len(skip & set(disk)),
                          **Counter(i["reason"] for i in items if i["media"] == media)}
    conn.close()
    report = {"version": VERSION, "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
              "seconds": round(time.time() - started, 1), "only": only,
              "roots": roots, "summary": summary, "items": items}
    tmp = report_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, report_path())
    print(f"ANALYSIS_DONE {json.dumps(summary, ensure_ascii=False)}", flush=True)
    return report


DB_BYTES_PER_CHAR = {"subs": 30.0, "epub": 22.9}
PARALLEL_EFFICIENCY = {"subs": 0.9, "epub": 0.89}
SAMPLE = {"subs": 40, "epub": 40}
WARN_TOTAL_BYTES = 10 * 1024 ** 3


def _sample_job(job):
    media, path, relpath = job
    if media == "subs":
        import indexer
        indexer.get_tokenizer()
    else:
        import epub_indexer
        epub_indexer.get_tokenizer()
    t = time.perf_counter()
    try:
        c, r = _sample_one(media, path, relpath)
    except Exception:
        c = r = 0
    return c, r, time.perf_counter() - t


def _sample_one(media, path, relpath):
    if media == "subs":
        import indexer
        rows = indexer.index_rows(indexer.kept_lines(path, relpath), relpath)
        return sum(len(r[0]) for r in rows), len(rows)
    import epub_indexer
    author, title, chapters = epub_indexer.extract_epub_content(path)
    rows = epub_indexer.book_rows(title, chapters)
    return sum(len(r[1]) for r in rows), len(rows)


def _estimate_cache_path():
    return os.path.join(os.path.dirname(os.path.abspath(paths.subs_db())), "estimate.json")


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


def _estimate_key(media, new, workers):
    h = hashlib.sha1(repr((media, workers, DB_BYTES_PER_CHAR[media], PARALLEL_EFFICIENCY[media],
                           SAMPLE[media])).encode("utf-8"))
    for p, name, size, mtime in sorted(new):
        h.update(f"\0{p}\0{name}\0{size}\0{mtime}".encode("utf-8", "surrogatepass"))
    return h.hexdigest()


def estimate(only=None):
    import random
    workers = paths.index_workers()
    out = {"workers": workers, "media": {}}
    cache = _load_estimate_cache()
    cache_changed = False
    for media, root, db, table in (("subs", paths.subs_dir(), paths.subs_db(), "subtitles"),
                                   ("epub", paths.books_dir(), paths.epub_db(), "epubs")):
        size_now = os.path.getsize(db) if os.path.isfile(db) else 0
        m = {"db_now": size_now, "new_files": 0, "new_bytes": 0, "db_add": 0, "rows_add": 0, "seconds": 0}
        out["media"][media] = m
        if (only and media != only) or not root or not os.path.isdir(root):
            continue
        indexed = set()
        if os.path.isfile(db):
            try:
                c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
                indexed = {r[0] for r in c.execute("SELECT relpath FROM sources")}
                c.close()
            except sqlite3.Error:
                pass
        indexed |= {r["name"] for r in filtered_rows(paths.filtered_list()) if r["media"] == media}
        walked = [(p, name, size, mtime) for _, name, p, size, mtime in _walk(root, media) if name not in indexed]
        new = [(p, name, size) for p, name, size, _ in walked]
        m["new_files"], m["new_bytes"] = len(new), sum(s for _, _, s in new)
        if not new:
            continue
        key = _estimate_key(media, walked, workers)
        kept = cache.get(media)
        if isinstance(kept, dict) and kept.get("key") == key:
            m.update({k: kept[k] for k in ("db_add", "rows_add", "seconds", "sampled") if k in kept})
            m["kept"] = True
            continue
        by_ext = defaultdict(list)
        for f in new:
            by_ext[os.path.splitext(f[0])[1].lower()].append(f)
        rng = random.Random(0)
        chars = rows = serial = 0.0
        for ext, files in sorted(by_ext.items()):
            sample = rng.sample(files, min(len(files), SAMPLE[media]))
            s_chars = s_rows = busy = 0.0
            for c, r, secs in parallel_map(_sample_job, [(media, p, name) for p, name, _ in sample],
                                           min(workers, len(sample))):
                busy += secs
                s_chars += c
                s_rows += r
            scale = len(files) / max(1, len(sample))
            chars += s_chars * scale
            rows += s_rows * scale
            serial += busy * scale
            m.setdefault("sampled", {})[ext] = len(sample)
        m["db_add"] = int(chars * DB_BYTES_PER_CHAR[media])
        m["rows_add"] = int(rows)
        m["seconds"] = int(serial / max(1.0, workers * PARALLEL_EFFICIENCY[media])) if workers > 1 else int(serial)
        cache[media] = {"key": key, **{k: m[k] for k in ("db_add", "rows_add", "seconds", "sampled")}}
        cache_changed = True
    if cache_changed:
        _save_estimate_cache(cache)
    total =sum(m["db_now"] + m["db_add"] for m in out["media"].values())
    out.update(total_bytes=total, warn=total > WARN_TOTAL_BYTES,
               seconds=sum(m["seconds"] for m in out["media"].values()))
    for media, db in (("subs", paths.subs_db()), ("epub", paths.epub_db())):
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
        run(only)
