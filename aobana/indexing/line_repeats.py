import concurrent.futures
import hashlib
import json
import sqlite3
import time
from pathlib import Path

from aobana.search.result_cache import _result_folder

VERSION = '1'
TABLES = {'subs': 'subtitles', 'epub': 'epubs', 'manga': 'manga', 'custom': 'custom'}
POOL_MIN_ROWS = 2_000_000
SAVE_EVERY = 30.0


def _key(table):
    return f"{table}_repeats_stamp"


def _stamp(conn, table):
    top = conn.execute(f"SELECT MAX(id) FROM {table}_content").fetchone()[0] or 0
    n, high = conn.execute("SELECT COUNT(*), MAX(id) FROM sources").fetchone()
    return f"{VERSION}:{top}:{n}:{high or 0}"


def ready(conn, media):
    table = TABLES.get(media)
    if table is None:
        return False
    try:
        row = conn.execute("SELECT v FROM meta WHERE k = ?", (_key(table),)).fetchone()
        return row is not None and row[0] == _stamp(conn, table)
    except sqlite3.Error:
        return False


def bits(conn, media):
    if not ready(conn, media):
        return None
    row = conn.execute(f"SELECT bits FROM {TABLES[media]}_repeat_bits WHERE id = 1").fetchone()
    return bytes(row[0]) if row else None


def drop(conn, media):
    table = TABLES[media]
    conn.execute(f"DROP TABLE IF EXISTS {table}_repeat_bits")
    conn.execute(f"DROP TABLE IF EXISTS {table}_repeat_titles")
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'meta'").fetchone():
        conn.execute("DELETE FROM meta WHERE k = ?", (_key(table),))


def _titles(conn, media):
    out, by_line = {}, set()
    if media == 'subs':
        rows = conn.execute("SELECT s.id, s.file_hash, s.relpath, r.first_rowid, r.last_rowid "
                            "FROM source_ranges r JOIN sources s ON s.id = r.source_id")
    elif media == 'epub':
        rows = conn.execute("SELECT c.source_id, s.file_hash, c.file, c.first_rowid, c.last_rowid "
                            "FROM chapters c JOIN sources s ON s.id = c.source_id")
    elif media == 'custom':
        names = {i: (h, kind) for i, h, kind in conn.execute("SELECT id, file_hash, kind FROM sources")}
        voiced = 'audio' in {r[1] for r in conn.execute("PRAGMA table_info(custom_lines)")}
        rows = []
        for sid, lo, hi in conn.execute("SELECT c0, MIN(id), MAX(id) FROM custom_content GROUP BY c0").fetchall():
            file = conn.execute("SELECT c1 FROM custom_content WHERE id = ?", (lo,)).fetchone()[0]
            file_hash, kind = names.get(sid, ('', ''))
            if kind not in ('txt', 'md') or voiced and conn.execute(
                    "SELECT 1 FROM custom_lines WHERE rowid BETWEEN ? AND ? AND audio IS NOT NULL LIMIT 1",
                    (lo, hi)).fetchone():
                by_line.add(_result_folder(media, file))
            rows.append((sid, file_hash, file, lo, hi))
    else:
        names = {i: (h, rel) for i, h, rel in conn.execute("SELECT id, file_hash, relpath FROM sources")}
        rows = ((sid, *names.get(sid, ('', str(sid))), lo, hi) for sid, lo, hi in conn.execute(
            "SELECT c0, MIN(id), MAX(id) FROM manga_content GROUP BY c0"))
    for sid, file_hash, file, lo, hi in rows:
        out.setdefault(_result_folder(media, file), []).append((sid, file_hash, lo, hi))
    for runs in out.values():
        runs.sort(key=lambda r: r[2])
    return out, by_line


def runs(conn, media):
    table = TABLES.get(media)
    if table is None:
        return None
    try:
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (f"{table}_content",)).fetchone() is None:
            return None
        if media == 'subs':
            from aobana.indexing.source_ranges import ready as ranges_ready
            if not ranges_ready(conn):
                return None
        if media == 'epub' and conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'chapters'").fetchone() is None:
            return None
        titles, by_line = _titles(conn, media)
    except sqlite3.Error:
        return None
    spans = sorted((lo, hi, title) for title, rs in titles.items() for _, _, lo, hi in rs)
    if any(b[0] <= a[1] for a, b in zip(spans, spans[1:])):
        return None
    return [s[0] for s in spans], [s[1] for s in spans], [s[2] for s in spans], by_line


def _sig(runs):
    return hashlib.sha256(repr(runs).encode('utf-8')).hexdigest()[:24]


def _marks_of(db_path, table, spans):
    conn = sqlite3.connect(Path(db_path).as_uri() + "?mode=ro", uri=True)
    try:
        return _marks_in(conn, table, spans)
    finally:
        conn.close()


def _marks_in(conn, table, spans):
    seen, marked = set(), []
    for lo, hi in sorted(spans):
        for rowid, line in conn.execute(f"SELECT id, c2 FROM {table}_content WHERE id BETWEEN ? AND ? ORDER BY id",
                                        (lo, hi)):
            h = hash(line)
            if h in seen:
                marked.append(rowid)
            else:
                seen.add(h)
    return marked


def _clear(bits, lo, hi):
    hi = min(hi, len(bits) * 8 - 1)
    while lo <= hi and lo & 7:
        bits[lo >> 3] &= ~(1 << (lo & 7)) & 0xFF
        lo += 1
    while lo + 7 <= hi:
        end = min((hi + 1) >> 3, len(bits))
        bits[lo >> 3:end] = bytes(end - (lo >> 3))
        lo = end << 3
    while lo <= hi:
        bits[lo >> 3] &= ~(1 << (lo & 7)) & 0xFF
        lo += 1


def build(conn, media, db_path=None, workers=1, stop=lambda: False, progress=lambda done, total: None):
    table = TABLES[media]
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (f"{table}_content",)).fetchone() is None:
        return False
    if media == 'subs':
        from aobana.indexing.source_ranges import ready as ranges_ready
        if not ranges_ready(conn):
            return False
    if media == 'epub' and conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'chapters'").fetchone() is None:
        return False
    stamp = _stamp(conn, table)
    conn.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
    old = conn.execute("SELECT v FROM meta WHERE k = ?", (_key(table),)).fetchone()
    if old is not None and old[0] == stamp:
        return True
    if old is None or not old[0].startswith(VERSION + ':'):
        drop(conn, media)
    conn.execute(f"CREATE TABLE IF NOT EXISTS {table}_repeat_titles "
                 "(title TEXT PRIMARY KEY, sig TEXT NOT NULL, spans TEXT NOT NULL)")
    conn.execute(f"CREATE TABLE IF NOT EXISTS {table}_repeat_bits "
                 "(id INTEGER PRIMARY KEY CHECK (id = 1), bits BLOB NOT NULL)")
    conn.execute("INSERT OR REPLACE INTO meta (k, v) VALUES (?, ?)", (_key(table), f"{VERSION}:building"))
    conn.commit()
    top = int(stamp.split(':')[1])
    row = conn.execute(f"SELECT bits FROM {table}_repeat_bits WHERE id = 1").fetchone()
    marks = bytearray(row[0]) if row else bytearray()
    size = top // 8 + 1
    marks = marks[:size] + bytearray(max(0, size - len(marks)))
    current, by_line = _titles(conn, media)
    current = {t: runs for t, runs in current.items() if t not in by_line}
    stored = {t: (sig, json.loads(spans)) for t, sig, spans in
              conn.execute(f"SELECT title, sig, spans FROM {table}_repeat_titles")}
    todo = {t: runs for t, runs in current.items() if stored.get(t, (None,))[0] != _sig(runs)}
    for t, (_, spans) in stored.items():
        if t not in current or t in todo:
            for lo, hi in spans:
                _clear(marks, lo, hi)
    gone = [t for t in stored if t not in current]
    if gone:
        conn.executemany(f"DELETE FROM {table}_repeat_titles WHERE title = ?", ((t,) for t in gone))
    for runs in todo.values():
        for _, _, lo, hi in runs:
            _clear(marks, lo, hi)
    done_titles, rows_done = [], 0
    total = sum(hi - lo + 1 for runs in todo.values() for _, _, lo, hi in runs)
    if total:
        progress(0, total)
    last_save = time.monotonic()

    def save():
        conn.execute(f"INSERT OR REPLACE INTO {table}_repeat_bits (id, bits) VALUES (1, ?)", (bytes(marks),))
        conn.executemany(f"INSERT OR REPLACE INTO {table}_repeat_titles (title, sig, spans) VALUES (?, ?, ?)",
                         ((t, _sig(current[t]), json.dumps([[lo, hi] for _, _, lo, hi in current[t]]))
                          for t in done_titles))
        conn.commit()
        done_titles.clear()

    last_shown = 0.0

    def take(title, marked):
        nonlocal rows_done, last_save, last_shown
        for rowid in marked:
            marks[rowid >> 3] |= 1 << (rowid & 7)
        done_titles.append(title)
        rows_done += sum(hi - lo + 1 for _, _, lo, hi in current[title])
        if time.monotonic() - last_shown >= 0.5:
            progress(rows_done, total)
            last_shown = time.monotonic()
        if time.monotonic() - last_save >= SAVE_EVERY:
            save()
            last_save = time.monotonic()

    order = sorted(todo, key=lambda t: todo[t][0][2])
    spans_of = {t: [(lo, hi) for _, _, lo, hi in todo[t]] for t in order}
    stopped = False
    if workers > 1 and db_path and total >= POOL_MIN_ROWS:
        with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as pool:
            pending = {pool.submit(_marks_of, str(db_path), table, spans_of[t]): t for t in order}
            try:
                for fut in concurrent.futures.as_completed(pending):
                    take(pending[fut], fut.result())
                    if stop():
                        stopped = True
                        break
            finally:
                if stopped:
                    for fut in pending:
                        fut.cancel()
    else:
        for t in order:
            if stop():
                stopped = True
                break
            take(t, _marks_in(conn, table, spans_of[t]))
    save()
    if stopped:
        return False
    conn.execute("INSERT OR REPLACE INTO meta (k, v) VALUES (?, ?)", (_key(table), stamp))
    conn.commit()
    return True


def ensure(conn, media, db_path, workers, show=False):
    from aobana.indexing import run_control
    from aobana.utils import emit, stop_requested
    if ready(conn, media):
        return True
    if show:
        emit("phase", "REPEATS marking the lines each title repeats...", phase="repeats")

    def progress(done, total):
        if run_control.CURRENT:
            run_control.CURRENT.publish(phase="repeats", phase_done=done, phase_total=total)

    return build(conn, media, db_path, workers, stop_requested, progress)


def drift(conn, media):
    found = bits(conn, media)
    if found is None:
        return None
    table, bad = TABLES[media], 0
    titles, by_line = _titles(conn, media)
    for title, runs in titles.items():
        if title in by_line:
            continue
        spans = [(lo, hi) for _, _, lo, hi in runs]
        fresh = set(_marks_in(conn, table, spans))
        for lo, hi in spans:
            if any(((rowid >> 3) < len(found) and found[rowid >> 3] >> (rowid & 7) & 1) != (rowid in fresh)
                   for rowid in range(lo, hi + 1)):
                bad += 1
                break
    return bad
