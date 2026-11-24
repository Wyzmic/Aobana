
import json
import os
import re
import sqlite3
import threading
import time

from aobana import paths
from aobana.search import iplusone

# 1: the first form. Bump it when what a sentence counts changes (iplusone.row_units, analyze).
COVERAGE_FORM = 1
SAVE_EVERY = 5.0
# The page shows the notice and its bar only for a count expected to take longer than this.
NOTICE_SECONDS = 30
# A first guess at the time a sentence takes (2.5 to 5.6 µs on a large library); a first run
# also looks up every form in the dictionary once.
DEFAULT_SECONDS_PER_ROW = 8e-6
# The tables, in the order counted.
CORPORA = (("subs", "subtitles", "subs"), ("epub", "epubs", "books"),
           ("manga", "manga", "manga"), ("custom", "custom", "custom"))
# A target no row holds: analyze then counts a sentence's words and nothing else.
_NO_TARGET = ("",)

_LOCK = threading.Lock()
_STATE = {"running": None, "done": 0, "total": 0, "started": None, "expected": None, "retry_after": 0.0}
_READY = {}


def _cache_path():
    return paths.companion("coverage_cache.json")


def _db_path(media):
    return {"subs": paths.subs_db, "epub": paths.epub_db, "manga": paths.manga_db, "custom": paths.custom_db}[media]()


def _read_cache(fingerprint):
    try:
        with open(_cache_path(), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = None
    if (not isinstance(data, dict) or data.get("form") != COVERAGE_FORM or data.get("policy") != iplusone.POLICY
            or data.get("fingerprint") != fingerprint or not isinstance(data.get("sources"), dict)):
        rate = data.get("seconds_per_row") if isinstance(data, dict) else None
        return {"form": COVERAGE_FORM, "policy": iplusone.POLICY, "fingerprint": fingerprint,
                "seconds_per_row": rate, "sources": {}}
    return data


def _write_cache(data):
    path = _cache_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    for attempt in range(20):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 19:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                raise
            time.sleep(0.05)


def sentence_counts(tokens, vocab):
    _, known, total = iplusone.analyze(tokens, _NO_TARGET, vocab, target_known=False)
    return known, total


def _work_of(media, row):
    if media == "subs":
        return re.split(r"[\\/]", row["relpath"])[0]
    if media == "epub":
        rel = row["relpath"]
        return row["title"] or (rel[:-5] if rel.lower().endswith(".epub") else rel)
    if media == "manga":
        return row["title"]
    return row["category"]


def _sources(conn, media):
    conn.row_factory = sqlite3.Row
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(sources)")}
        want = [c for c in ("id", "relpath", "file_hash", "index_format", "title", "category") if c in cols]
        rows = conn.execute(f"SELECT {', '.join(want)} FROM sources").fetchall()
    finally:
        conn.row_factory = None
    lines = _line_counts(conn, media)
    out = []
    for r in rows:
        r = dict(r)
        r.setdefault("title", None)
        r.setdefault("category", None)
        key = "\t".join((r["relpath"] or "", r.get("file_hash") or "", str(r.get("index_format") or "")))
        out.append((r["id"], key, _work_of(media, r), lines.get(r["id"], 0)))
    return out


def _line_counts(conn, media):
    try:
        if media == "subs":
            from aobana.indexing.source_ranges import ready, counts
            if ready(conn):
                return {sid: n for sid, _, n in counts(conn)}
        if media == "epub":
            from aobana import utils
            if utils.has_chapters(conn):
                return dict(conn.execute("SELECT source_id, SUM(lines) FROM chapters GROUP BY source_id"))
        if media == "custom":
            return dict(conn.execute("SELECT id, lines FROM sources"))
        table = dict((m, t) for m, t, _ in CORPORA)[media]
        return dict(conn.execute(f"SELECT source_id, COUNT(*) FROM {table} GROUP BY source_id"))
    except sqlite3.Error:
        return {}


def _open(media_on):
    conns = {}
    for media, _, kind in CORPORA:
        path = _db_path(media)
        if media_on.get(kind) and os.path.exists(path):
            conns[media] = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
    return conns


def _db_key(conns):
    from aobana.search.result_cache import db_fingerprint
    return repr(db_fingerprint(*(conns.get(m) for m, _, _ in CORPORA)))


def _figures(plan, sources):
    sums = {}
    for media, items in plan.items():
        got = sources.get(media, {})
        for _, key, work, _ in items:
            c = got.get(key)
            if c:
                s = sums.setdefault((media, work), [0, 0, 0, 0, 0, 0])
                for i, v in enumerate(c):
                    s[i] += v
    out = {}
    for k, (_, rows, known, total, i0, i1) in sums.items():
        out[k] = {"sentences": rows,
                  "known": round(100.0 * known / total, 1) if total else None,
                  "i0": round(100.0 * i0 / rows, 1) if rows else None,
                  "i1": round(100.0 * i1 / rows, 1) if rows else None}
    return out


def _iter_media_rows(conn, media, table, todo, total_files):
    if len(todo) * 2 < total_files:
        spans_sql = None
        if media == "subs":
            from aobana.indexing.source_ranges import ready
            if ready(conn):
                spans_sql = "SELECT first_rowid, last_rowid FROM source_ranges WHERE source_id = ? ORDER BY first_rowid"
        elif media == "epub":
            from aobana import utils
            if utils.has_chapters(conn):
                spans_sql = "SELECT first_rowid, last_rowid FROM chapters WHERE source_id = ? ORDER BY first_rowid"
        if spans_sql:
            for sid in sorted(todo):
                for lo, hi in conn.execute(spans_sql, (sid,)).fetchall():
                    for row in conn.execute(
                        f"SELECT source_id, base_forms, clean_text FROM {table} WHERE rowid BETWEEN ? AND ?",
                        (lo, hi),
                    ):
                        if row[0] == sid:
                            yield row
            return
    for row in conn.execute(f"SELECT source_id, base_forms, clean_text FROM {table}"):
        yield row


def _count(vocab, conns, plan, cache, stop):
    fp = vocab.fingerprint
    last_save = time.monotonic()
    t0 = time.monotonic()
    counted = 0
    scanned = 0
    for media, table, _ in CORPORA:
        if media not in plan:
            continue
        done = cache["sources"].setdefault(media, {})
        keep = {key for _, key, _, _ in plan[media]}
        for key in [k for k in done if k not in keep]:
            del done[key]
        todo = {sid: key for sid, key, _, _ in plan[media] if key not in done}
        if not todo:
            continue
        conn = conns[media]
        acc, finished, prev, whole = {}, set(), None, True
        conn.execute("BEGIN")
        try:
            for sid, base_forms, clean_text in _iter_media_rows(conn, media, table, todo, len(plan[media])):
                scanned += 1
                if sid != prev:
                    if prev in todo:
                        finished.add(prev)
                    if sid in finished:
                        # Rows of one file out of order (not seen so far): its counts are saved only whole, at the end
                        whole = False
                        finished.discard(sid)
                        done.pop(todo[sid], None)
                    prev = sid
                key = todo.get(sid)
                if key is None:
                    continue
                c = acc.get(sid)
                if c is None:
                    c = acc[sid] = [0, 0, 0, 0, 0, 0]
                known, total = sentence_counts(iplusone.row_units(base_forms, clean_text, media), vocab)
                c[0] += 1
                if total:
                    c[1] += 1
                    c[2] += known
                    c[3] += total
                    if known == total:
                        c[4] += 1
                    elif total - known == 1:
                        c[5] += 1
                counted += 1
                if not counted % 2000:
                    _STATE["done"] += 2000
                    stopping = stop()
                    now = time.monotonic()
                    if _STATE["done"] >= 2000 and _STATE["total"] and _STATE["started"] is not None:
                        _STATE["expected"] = (now - _STATE["started"]) * _STATE["total"] / _STATE["done"]
                    if stopping or now - last_save >= SAVE_EVERY:
                        cur = iplusone.current()
                        if cur is None or cur.fingerprint != fp:
                            return False
                        if whole:
                            for s in finished:
                                done[todo[s]] = acc[s]
                        if scanned <= counted * 1.25:
                            cache["seconds_per_row"] = (now - t0) / counted
                        _write_cache(cache)
                        last_save = now
                    if stopping:
                        return False
        finally:
            conn.rollback()
        for sid, key in todo.items():
            done[key] = acc.get(sid, [0, 0, 0, 0, 0, 0])
        if counted and scanned <= counted * 1.25 and (counted >= 1000 or cache.get("seconds_per_row") is None):
            cache["seconds_per_row"] = (time.monotonic() - t0) / counted
        _write_cache(cache)
    return True


def _run(fingerprint, stop):
    from aobana.search.media_tab import _BACKGROUND_READERS, _BACKGROUND_READERS_LOCK
    conns = {}
    failed = False
    try:
        vocab = iplusone.current()
        if vocab is None or vocab.fingerprint != fingerprint:
            return
        conns = _open(paths.media_state())
        with _BACKGROUND_READERS_LOCK:
            _BACKGROUND_READERS.update(conns.values())
        key = _db_key(conns)
        plan = {media: _sources(conn, media) for media, conn in conns.items()}
        cache = _read_cache(fingerprint)
        rate = cache.get("seconds_per_row") or DEFAULT_SECONDS_PER_ROW
        todo = sum(n for media, items in plan.items() for _, k, _, n in items
                   if k not in cache["sources"].get(media, {}))
        _STATE.update(done=0, total=todo, started=time.monotonic(), expected=todo * rate)
        if _count(vocab, conns, plan, cache, stop):
            _READY.clear()
            _READY[(fingerprint, key)] = _figures(plan, cache["sources"])
    except (sqlite3.Error, OSError):
        failed = True
    finally:
        with _BACKGROUND_READERS_LOCK:
            _BACKGROUND_READERS.difference_update(conns.values())
        for c in conns.values():
            c.close()
        with _LOCK:
            _STATE.update(running=None, started=None, expected=None,
                          retry_after=time.monotonic() + 5.0 if failed else 0.0)


def status(dbs):
    vocab = iplusone.current()
    if vocab is None:
        return {"words": False}
    fp = vocab.fingerprint
    key = repr(_fingerprint_of(dbs))
    figures = _READY.get((fp, key))
    if figures is not None:
        return {"words": True, "ready": True, "figures": figures}
    with _LOCK:
        if _STATE["running"] is None and time.monotonic() >= _STATE.get("retry_after", 0.0):
            _STATE.update(running=fp, done=0, total=0, started=time.monotonic(), expected=None)
            threading.Thread(target=_run, args=(fp, lambda: iplusone.current() is None), daemon=True).start()
    started = _STATE["started"] or time.monotonic()
    elapsed = time.monotonic() - started
    expected = _STATE["expected"]
    total, done = _STATE["total"], min(_STATE["done"], _STATE["total"])
    return {"words": True, "ready": False, "elapsed": round(elapsed, 1),
            "remaining": round(max(0.0, expected - elapsed), 1) if expected is not None else None,
            "expected": round(expected, 1) if expected is not None else None,
            "notice": expected is not None and expected > NOTICE_SECONDS,
            "done": done, "total": total}


def _fingerprint_of(dbs):
    from aobana.search.result_cache import db_fingerprint
    return db_fingerprint(*(dbs.get(m) for m, _, _ in CORPORA))


def sort_items(rows, figures, hardest):
    out = []
    for it in rows:
        f = figures.get((it["media"], it["folder"]))
        out.append(dict(it, coverage=f) if f else dict(it, coverage=None))
    have = [it for it in out if it["coverage"] and it["coverage"]["known"] is not None]
    none = [it for it in out if not (it["coverage"] and it["coverage"]["known"] is not None)]
    have.sort(key=lambda it: it["coverage"]["known"], reverse=not hardest)
    return have + none
