
import ast
import os
import sqlite3
import threading
from array import array
from collections import OrderedDict
from aobana import paths


def db_fingerprint(*conns):
    out = []
    for conn in conns:
        if conn is None:
            out.append(None)
            continue
        try:
            path = next((r[2] for r in conn.execute("PRAGMA database_list") if r[1] == "main"), "")
        except sqlite3.Error:
            path = ""
        out.append(_file_fingerprint(path))
    return tuple(out)


def _file_fingerprint(path):
    entry = [path]
    for p in (path, path + "-wal"):
        try:
            st = os.stat(p)
            entry.append((st.st_mtime_ns, st.st_size))
        except (OSError, ValueError):
            entry.append(None)
    return tuple(entry)


RESULT_CACHE_ENABLED = True
RESULT_CACHE_MAX_ROWS = 4_000_000
_RESULT_CACHE = OrderedDict()
_RESULT_CACHE_LOCK = threading.Lock()
_MEDIA_CODES = {"subs": 0, "epub": 1, "manga": 2}
_MEDIA_NAMES = ("subs", "epub", "manga")


def _result_folder(media_type, file):
    if media_type == "epub":
        return file.rsplit('\\', 1)[0] if '\\' in file else file.partition("/")[0]
    return file.partition("\\")[0].partition("/")[0]


def _result_cache_key(q, sort, seed, media, exact, folder, file, targets):
    if not RESULT_CACHE_ENABLED or (sort == "random" and seed is None):
        return None
    return (q, sort, seed if sort == "random" else None, media, bool(exact), folder or None,
            file or None, db_fingerprint(*[conn for _, conn, _ in targets]))


def _result_cache_get(key):
    if key is None:
        return None
    with _RESULT_CACHE_LOCK:
        entry = _RESULT_CACHE.get(key)
        if entry is not None:
            _RESULT_CACHE.move_to_end(key)
            return entry
    entry = _disk_cache_get(key)
    if entry is not None:
        _result_cache_put(key, entry)
    return entry


DISK_CACHE_ENABLED = None


def disk_cache_enabled():
    if DISK_CACHE_ENABLED is not None:
        return DISK_CACHE_ENABLED
    return paths.load_config().get("search_cache") is True


DISK_CACHE_MIN_SECONDS = 1.0
DISK_CACHE_MAX_BYTES = 1024 ** 3
_DISK_LOCK = threading.Lock()
_DISK_ARRAYS = (("media", "b"), ("fidx", "i"), ("rowid", "q"), ("score", "d"), ("char_count", "q"))


def disk_cache_path():
    return os.path.join(os.path.dirname(os.path.abspath(paths.subs_db())), "search_cache.db")


def _disk_open():
    conn = sqlite3.connect(disk_cache_path(), timeout=5)
    try:
        conn.execute("PRAGMA auto_vacuum = INCREMENTAL")
        conn.execute("CREATE TABLE IF NOT EXISTS entries (key TEXT PRIMARY KEY, fp TEXT, rows INTEGER, "
                     "bytes INTEGER, used REAL, media BLOB, fidx BLOB, rowid BLOB, score BLOB, "
                     "char_count BLOB, folders TEXT, folder_counts TEXT)")
    except BaseException:
        conn.close()
        raise
    return conn


def _disk_drop_file():
    for suffix in ("", "-wal", "-shm", "-journal"):
        try:
            os.remove(disk_cache_path() + suffix)
        except OSError:
            pass


def _disk_cache_get(key):
    if key is None or not disk_cache_enabled():
        return None
    import json
    import time
    with _DISK_LOCK:
        if not os.path.exists(disk_cache_path()):
            return None
        try:
            conn = _disk_open()
            try:
                row = conn.execute("SELECT media, fidx, rowid, score, char_count, folders, folder_counts "
                                   "FROM entries WHERE key = ?", (repr(key),)).fetchone()
                if row is None:
                    return None
                entry = {}
                for (name, code), blob in zip(_DISK_ARRAYS, row):
                    a = array(code)
                    a.frombytes(blob)
                    entry[name] = a
                entry["folders"] = json.loads(row[5])
                entry["folder_counts"] = json.loads(row[6])
                if len({len(entry[name]) for name, _ in _DISK_ARRAYS}) != 1:
                    return None
                conn.execute("UPDATE entries SET used = ? WHERE key = ?", (time.time(), repr(key)))
                conn.commit()
                return entry
            finally:
                conn.close()
        except sqlite3.DatabaseError:
            _disk_drop_file()
        except (sqlite3.Error, OSError, ValueError, TypeError):
            pass
    return None


def _disk_cache_put(key, entry):
    import json
    import time
    blobs = [entry[name].tobytes() for name, _ in _DISK_ARRAYS]
    folders, counts = json.dumps(entry["folders"]), json.dumps(entry["folder_counts"])
    size = sum(len(b) for b in blobs) + len(folders.encode()) + len(counts.encode())
    if size > DISK_CACHE_MAX_BYTES:
        return
    with _DISK_LOCK:
        try:
            conn = _disk_open()
            try:
                dead = []
                for old_key, old_fp in conn.execute("SELECT key, fp FROM entries").fetchall():
                    try:
                        files = ast.literal_eval(old_fp)
                        if any(f is not None and _file_fingerprint(f[0]) != f for f in files):
                            dead.append((old_key,))
                    except (ValueError, SyntaxError, TypeError, IndexError):
                        dead.append((old_key,))
                conn.executemany("DELETE FROM entries WHERE key = ?", dead)
                conn.execute("INSERT OR REPLACE INTO entries VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                             (repr(key), repr(key[-1]), len(entry["rowid"]), size, time.time(),
                              *blobs, folders, counts))
                total = conn.execute("SELECT COALESCE(SUM(bytes), 0) FROM entries").fetchone()[0]
                for old_key, old_bytes in conn.execute(
                        "SELECT key, bytes FROM entries ORDER BY used").fetchall():
                    if total <= DISK_CACHE_MAX_BYTES:
                        break
                    conn.execute("DELETE FROM entries WHERE key = ?", (old_key,))
                    total -= old_bytes
                conn.commit()
                conn.execute("PRAGMA incremental_vacuum").fetchall()
            finally:
                conn.close()
        except sqlite3.DatabaseError:
            _disk_drop_file()
        except (sqlite3.Error, OSError):
            pass


def _disk_cache_put_later(key, entry, seconds):
    if (key is None or seconds < DISK_CACHE_MIN_SECONDS or key[1] == "random"
            or not disk_cache_enabled()):
        return
    threading.Thread(target=_disk_cache_put, args=(key, entry), daemon=True).start()


def disk_cache_stats():
    with _DISK_LOCK:
        path = disk_cache_path()
        if not os.path.exists(path):
            return {"entries": 0, "bytes": 0}
        try:
            conn = _disk_open()
            try:
                n = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
            finally:
                conn.close()
            return {"entries": n, "bytes": os.path.getsize(path)}
        except (sqlite3.Error, OSError):
            return {"entries": 0, "bytes": 0}


def clear_disk_cache():
    with _DISK_LOCK:
        _disk_drop_file()
        gone = not os.path.exists(disk_cache_path())
    with _RESULT_CACHE_LOCK:
        _RESULT_CACHE.clear()
    return gone


_LEAN_LINE, _LEAN_ROWID, _LEAN_MEDIA, _LEAN_FOLDER, _LEAN_SCORE, _LEAN_CHARS = range(6)


def _result_entry(valid_results, folder_counts):
    names = {}
    for r in valid_results:
        names.setdefault(r[_LEAN_FOLDER], len(names))
    return {
        "media": array("b", (_MEDIA_CODES[r[_LEAN_MEDIA]] for r in valid_results)),
        "fidx": array("i", (names[r[_LEAN_FOLDER]] for r in valid_results)),
        "folders": list(names),
        "rowid": array("q", (r[_LEAN_ROWID] for r in valid_results)),
        "score": array("d", (r[_LEAN_SCORE] for r in valid_results)),
        "char_count": array("q", (r[_LEAN_CHARS] for r in valid_results)),
        "folder_counts": dict(folder_counts),
    }


def _result_cache_put(key, entry, seconds=None):
    if key is None:
        return
    if seconds is not None:
        _disk_cache_put_later(key, entry, seconds)
    with _RESULT_CACHE_LOCK:
        _RESULT_CACHE[key] = entry
        _RESULT_CACHE.move_to_end(key)
        total = sum(len(e["rowid"]) for e in _RESULT_CACHE.values())
        while total > RESULT_CACHE_MAX_ROWS and len(_RESULT_CACHE) > 1:
            _, old = _RESULT_CACHE.popitem(last=False)
            total -= len(old["rowid"])


def _result_cache_page(entry, idx, targets):
    tables = {m_type: (table, conn) for table, conn, m_type in targets}
    wanted = {}
    for i in idx:
        wanted.setdefault(_MEDIA_NAMES[entry["media"][i]], []).append(entry["rowid"][i])
    rows = {}
    for m_type, rowids in wanted.items():
        if m_type not in tables:
            return None
        table, conn = tables[m_type]
        for j in range(0, len(rowids), 500):
            part = rowids[j:j + 500]
            sql = (f"SELECT rowid, line, file, clean_text, readings, base_forms FROM {table} "
                   f"WHERE rowid IN ({','.join('?' * len(part))})")
            for r in conn.execute(sql, part):
                rows[(m_type, r["rowid"])] = dict(r)
    chunk = []
    for i in idx:
        m_type = _MEDIA_NAMES[entry["media"][i]]
        row_dict = rows.get((m_type, entry["rowid"][i]))
        if row_dict is None:
            return None
        row_dict["media_type"] = m_type
        row_dict["folder"] = _result_folder(m_type, row_dict["file"])
        row_dict["score"] = entry["score"][i]
        row_dict["char_count"] = entry["char_count"][i]
        del row_dict["clean_text"]
        chunk.append(row_dict)
    return chunk
