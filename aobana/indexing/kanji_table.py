import sqlite3
import time

from aobana.search.reading import _KANJI_RE

VERSION = '1'
MIN_SQLITE = (3, 43, 0)
CHUNK = 100_000


def name(table):
    return f"{table}_kanji"


def supported():
    return sqlite3.sqlite_version_info >= MIN_SQLITE


def _schema(t):
    return (f"CREATE VIRTUAL TABLE {t} USING fts5(k, content='', contentless_delete=1, detail=none, "
            "tokenize='unicode61')")


def tokens(clean_text):
    return " ".join(sorted(set(_KANJI_RE.findall(clean_text or ""))))


def query(word):
    chars = sorted(set(_KANJI_RE.findall(word or "")))
    return " AND ".join(f'"{c}"' for c in chars) or None


def _top(conn, t):
    row = conn.execute(f"SELECT rowid FROM {t} ORDER BY rowid DESC LIMIT 1").fetchone()
    return row[0] if row else 0


def ready(conn, table):
    try:
        row = conn.execute("SELECT v FROM meta WHERE k = ?", (f"{name(table)}_version",)).fetchone()
        if row is None or row[0] != VERSION:
            return False
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (name(table),)).fetchone() is None:
            return False
        return _top(conn, table) == _top(conn, name(table))
    except sqlite3.Error:
        return False


def write(conn, table, rows, computed=False):
    conn.executemany(f"INSERT OR REPLACE INTO {name(table)}(rowid, k) VALUES (?, ?)",
                     ((rowid, text if computed else tokens(text)) for rowid, text in rows))


def delete_range(conn, table, first, last):
    conn.execute(f"DELETE FROM {name(table)} WHERE rowid BETWEEN ? AND ?", (first, last))


def drop_orphans(conn, table):
    conn.execute(f"DELETE FROM {name(table)} WHERE rowid NOT IN (SELECT id FROM {table}_docsize)")


def drop(conn, table):
    _begin(conn)
    conn.execute(f"DROP TABLE IF EXISTS {name(table)}")
    conn.execute(f"DROP TABLE IF EXISTS _{name(table)}_build")
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'meta'").fetchone():
        conn.execute("DELETE FROM meta WHERE k = ?", (f"{name(table)}_version",))


def _begin(conn):
    if not conn.in_transaction:
        conn.execute("BEGIN")


def ensure(conn, table, stop=lambda: False, progress=lambda done, total: None):
    if not supported():
        return False
    _begin(conn)
    conn.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
    conn.commit()
    if ready(conn, table):
        return True
    stage = f"_{name(table)}_build"
    _begin(conn)
    conn.execute(f"DROP TABLE IF EXISTS {stage}")
    conn.execute(_schema(stage))
    conn.commit()
    total = _top(conn, table)
    cursor = 0
    while True:
        if stop():
            _begin(conn)
            conn.execute(f"DROP TABLE IF EXISTS {stage}")
            conn.commit()
            return False
        batch = conn.execute(f"SELECT rowid, clean_text FROM {table} WHERE rowid > ? ORDER BY rowid LIMIT ?",
                             (cursor, CHUNK)).fetchall()
        if not batch:
            break
        conn.executemany(f"INSERT INTO {stage}(rowid, k) VALUES (?, ?)",
                         ((rowid, tokens(text)) for rowid, text in batch))
        conn.commit()
        cursor = batch[-1][0]
        progress(cursor, total)
    conn.execute(f"INSERT INTO {stage}({stage}) VALUES ('optimize')")
    conn.execute(f"DROP TABLE IF EXISTS {name(table)}")
    conn.execute(f"ALTER TABLE {stage} RENAME TO {name(table)}")
    conn.execute("INSERT OR REPLACE INTO meta (k, v) VALUES (?, ?)", (f"{name(table)}_version", VERSION))
    conn.commit()
    return True


def build(conn, table):
    from aobana.utils import emit, stop_requested
    if supported() and not ready(conn, table) and _top(conn, table):
        emit("phase", "KANJI building the kanji table (once, reads the whole index)...", phase="kanji")
    return ensure(conn, table, stop_requested,
                  lambda done, total: emit("phase", f"KANJI {done}/{total}", quiet=True, phase="kanji",
                                           done=done, total=total))
