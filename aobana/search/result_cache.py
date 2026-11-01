
import functools
import hashlib
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
_MEDIA_CODES = {"subs": 0, "epub": 1, "manga": 2, "custom": 3}
_MEDIA_NAMES = ("subs", "epub", "manga", "custom")


def _result_folder(media_type, file):
    if media_type == 'custom':
        from pathlib import PurePosixPath
        parts = file.replace(chr(92), '/').split('/')
        return parts[0] if len(parts) > 1 else PurePosixPath(file).stem
    if media_type == "epub":
        return file.rsplit('\\', 1)[0] if '\\' in file else file.partition("/")[0]
    return file.partition("\\")[0].partition("/")[0]


@functools.lru_cache(maxsize=8)
def _table_hash(files):
    digest = hashlib.sha256()
    for path, state in files:
        digest.update(os.path.basename(path).encode('utf-8'))
        if state is None:
            digest.update(b'missing')
        else:
            with open(path, 'rb') as handle:
                for chunk in iter(lambda: handle.read(65536), b''):
                    digest.update(chunk)
    return digest.hexdigest()[:12]


def _rules_version():
    from aobana.server.app import VERSION
    files = []
    for path in (paths.RUBY_TABLES_PATH, paths.KANJI_READINGS_PATH):
        try:
            stat = os.stat(path)
            state = (stat.st_size, stat.st_mtime_ns)
        except OSError:
            state = None
        files.append((path, state))
    return ('order-2-8', VERSION, _table_hash(tuple(files)))


def _result_cache_key(q, sort, seed, media, exact, folder, file, targets, ruby_only=False, learn=''):
    if not RESULT_CACHE_ENABLED or (sort == "random" and seed is None):
        return None
    key = (_rules_version(), q, sort, seed if sort == "random" else None, media, bool(exact), folder or None,
           file or None, db_fingerprint(*[conn for _, conn, _ in targets])) + (('ruby-only',) if ruby_only else ())
    # i+1: its mode and the known words' fingerprint, which names the rules too; 'groups-typed'
    # names おすすめ's i+1 first by unknown words, a known target's i+1 and the reading typed, so an
    # order saved under an older rule is never served
    if learn:
        key += ('learn', learn, 'groups-typed')
    return key


def _result_cache_get(key):
    if key is None:
        return None
    with _RESULT_CACHE_LOCK:
        entry = _RESULT_CACHE.get(key)
        if entry is not None:
            _RESULT_CACHE.move_to_end(key)
            return entry
    return None


def clear_result_cache():
    with _RESULT_CACHE_LOCK:
        _RESULT_CACHE.clear()


def remove_disk_cache():
    folder = os.path.dirname(os.path.abspath(paths.subs_db()))
    for where in (os.path.join(folder, "cache"), folder):
        for suffix in ("", "-wal", "-shm", "-journal"):
            try:
                os.remove(os.path.join(where, "search_cache.db" + suffix))
            except OSError:
                pass
    def drop(cfg):
        cfg.pop("search_cache", None)
    try:
        if "search_cache" in paths.load_config():
            paths.update_config(drop)
    except Exception:
        pass


_LEAN_LINE, _LEAN_ROWID, _LEAN_MEDIA, _LEAN_FOLDER, _LEAN_SCORE, _LEAN_CHARS = range(6)


def _result_entry(valid_results):
    names, folder_counts = {}, {}
    for r in valid_results:
        f = r[_LEAN_FOLDER]
        names.setdefault(f, len(names))
        folder_counts[f] = folder_counts.get(f, 0) + 1
    return {
        "media": array("b", (_MEDIA_CODES[r[_LEAN_MEDIA]] for r in valid_results)),
        "fidx": array("i", (names[r[_LEAN_FOLDER]] for r in valid_results)),
        "folders": list(names),
        "rowid": array("q", (r[_LEAN_ROWID] for r in valid_results)),
        "score": array("d", (r[_LEAN_SCORE] for r in valid_results)),
        "char_count": array("q", (r[_LEAN_CHARS] for r in valid_results)),
        "folder_counts": folder_counts,
    }


def _result_cache_put(key, entry):
    if key is None:
        return
    with _RESULT_CACHE_LOCK:
        _RESULT_CACHE[key] = entry
        _RESULT_CACHE.move_to_end(key)
        total = sum(len(e["rowid"]) for e in _RESULT_CACHE.values())
        while total > RESULT_CACHE_MAX_ROWS and len(_RESULT_CACHE) > 1:
            _, old = _RESULT_CACHE.popitem(last=False)
            total -= len(old["rowid"])


def _result_cache_page(entry, idx, targets, keep_text=False):
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
        if not keep_text:
            del row_dict["clean_text"]
        chunk.append(row_dict)
    return chunk
