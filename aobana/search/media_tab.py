
import os
import re
import sqlite3
import threading
from aobana import paths
from aobana.search.result_cache import (
    db_fingerprint,
)


_BACKGROUND_READERS = set()
_BACKGROUND_READERS_LOCK = threading.Lock()


_MEDIA_LIBRARY = {}
_MEDIA_LIBRARY_LOCK = threading.Lock()


def _library_sort_key(name):
    from aobana import utils
    return utils.katakana_to_hiragana(name).replace('ゔ', 'う').lower().encode('shift_jis', errors='ignore')


def get_media_library(db_subs, db_epub, db_manga=None):
    key = db_fingerprint(db_subs, db_epub, db_manga)
    cached = _media_library_cached(key)
    if cached is not None:
        return cached
    with _MEDIA_LIBRARY_LOCK:
        cached = _media_library_cached(key)
        if cached is not None:
            return cached
        return _compute_media_library(db_subs, db_epub, key, db_manga)


MEDIA_SECONDS_PER_GB = 3.2
_MEDIA_COMPUTE = {"started": None, "expected": None}


def _media_cache_path():
    return os.path.join(os.path.dirname(os.path.abspath(paths.subs_db())), "media_cache.json")


def _media_cache_read():
    try:
        import json
        with open(_media_cache_path(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _media_library_cached(key):
    if key in _MEDIA_LIBRARY:
        return _MEDIA_LIBRARY[key]
    data = _media_cache_read()
    if data and data.get("key") == repr(key) and isinstance(data.get("items"), list):
        _MEDIA_LIBRARY.clear()
        _MEDIA_LIBRARY[key] = data["items"]
        return data["items"]
    return None


def _db_bytes(*conns):
    total = 0
    for entry in db_fingerprint(*conns):
        if entry:
            total += sum(st[1] for st in entry[1:] if st)
    return total


def media_library_status(db_subs, db_epub, db_manga=None):
    import time
    key = db_fingerprint(db_subs, db_epub, db_manga)
    if _media_library_cached(key) is not None:
        return {"ready": True}
    if _MEDIA_COMPUTE["started"] is None and not _MEDIA_LIBRARY_LOCK.locked():
        threading.Thread(target=warm_media_library, daemon=True).start()
    started = _MEDIA_COMPUTE["started"] or time.monotonic()
    expected = _MEDIA_COMPUTE["expected"] or _media_expected_seconds(db_subs, db_epub, db_manga)
    elapsed = time.monotonic() - started
    return {"ready": False, "elapsed": round(elapsed, 1),
            "remaining": round(max(expected - elapsed, 1.0), 1)}


def _media_expected_seconds(db_subs, db_epub, db_manga=None):
    data = _media_cache_read() or {}
    rate = data.get("seconds_per_gb") or MEDIA_SECONDS_PER_GB
    return rate * _db_bytes(db_subs, db_epub, db_manga) / 1024 ** 3


def warm_media_library():
    conns = []
    try:
        on = paths.media_state()
        for path, kind in ((paths.subs_db(), "subs"), (paths.epub_db(), "books"), (paths.manga_db(), "manga")):
            conns.append(sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
                         if on[kind] and os.path.exists(path) else None)
        with _BACKGROUND_READERS_LOCK:
            _BACKGROUND_READERS.update(c for c in conns if c is not None)
        get_media_library(*conns)
    except Exception:
        pass
    finally:
        with _BACKGROUND_READERS_LOCK:
            _BACKGROUND_READERS.difference_update(conns)
        for c in conns:
            if c is not None:
                c.close()


def _compute_media_library(db_subs, db_epub, key, db_manga=None):
    import time
    _MEDIA_COMPUTE["started"] = time.monotonic()
    _MEDIA_COMPUTE["expected"] = _media_expected_seconds(db_subs, db_epub, db_manga)
    try:
        out = _count_media_library(db_subs, db_epub, db_manga)
    finally:
        seconds = time.monotonic() - _MEDIA_COMPUTE["started"]
        _MEDIA_COMPUTE["started"] = _MEDIA_COMPUTE["expected"] = None
    _MEDIA_LIBRARY.clear()
    _MEDIA_LIBRARY[key] = out
    size = _db_bytes(db_subs, db_epub, db_manga)
    try:
        import json
        path = _media_cache_path()
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"key": repr(key), "items": out, "seconds": round(seconds, 2),
                       "seconds_per_gb": round(seconds / (size / 1024 ** 3), 3) if size else None},
                      f, ensure_ascii=False)
        os.replace(tmp, path)
    except OSError:
        pass
    return out


def _count_media_library(db_subs, db_epub, db_manga=None):
    items = {}
    if db_subs is not None:
        try:
            lines = dict(db_subs.execute(
                "SELECT source_id, COUNT(*) FROM subtitles GROUP BY source_id").fetchall())
            for sid, relpath in db_subs.execute("SELECT id, relpath FROM sources"):
                show = re.split(r"[\\/]", relpath)[0]
                it = items.setdefault(("subs", show), {
                    "media": "subs", "folder": show, "author": "", "episodes": 0, "lines": 0})
                it["episodes"] += 1
                it["lines"] += lines.get(sid, 0)
        except sqlite3.Error:
            pass
    if db_epub is not None:
        try:
            from aobana import utils
            stats_sql = ("SELECT source_id, SUM(lines), COUNT(*) FROM chapters GROUP BY source_id"
                         if utils.has_chapters(db_epub) else
                         "SELECT source_id, COUNT(*), COUNT(DISTINCT file) FROM epubs GROUP BY source_id")
            stats = {sid: (n, ch) for sid, n, ch in db_epub.execute(stats_sql)}
            for sid, relpath, title, author in db_epub.execute(
                    "SELECT id, relpath, title, author FROM sources"):
                name = title or (relpath[:-5] if relpath.lower().endswith(".epub") else relpath)
                n, ch = stats.get(sid, (0, 0))
                it = items.setdefault(("epub", name), {
                    "media": "epub", "folder": name, "author": author or "", "episodes": 0, "lines": 0})
                it["episodes"] += ch
                it["lines"] += n
        except sqlite3.Error:
            pass
    if db_manga is not None:
        try:
            lines = dict(db_manga.execute(
                "SELECT source_id, COUNT(*) FROM manga GROUP BY source_id").fetchall())
            for sid, series in db_manga.execute("SELECT id, title FROM sources"):
                it = items.setdefault(("manga", series), {
                    "media": "manga", "folder": series, "author": "", "episodes": 0, "lines": 0})
                it["episodes"] += 1
                it["lines"] += lines.get(sid, 0)
        except sqlite3.Error:
            pass
    return sorted(items.values(), key=lambda it: _library_sort_key(it["folder"]))


MEDIA_SORTS = {"name": None, "parts_desc": ("episodes", True), "parts_asc": ("episodes", False),
               "lines_desc": ("lines", True), "lines_asc": ("lines", False)}


def media_page(items, media="all", needle="", offset=0, limit=0, folder=None, sort="name"):
    if folder is not None:
        rows = [it for it in items if it["folder"] == folder and media in ("all", it["media"])]
        return {"items": rows[:1], "total": len(rows[:1]), "has_more": False}
    needle = needle.strip().lower()
    rows = [it for it in items
            if media in ("all", it["media"])
            and (not needle or needle in it["folder"].lower() or needle in (it["author"] or "").lower())]
    key = MEDIA_SORTS.get(sort)
    if key:
        rows = sorted(rows, key=lambda it: it[key[0]] or 0, reverse=key[1])
    page = rows[offset:offset + limit] if limit else rows[offset:]
    return {"items": page, "total": len(rows), "has_more": offset + len(page) < len(rows),
            "shows": sum(1 for it in items if it["media"] == "subs"),
            "books": sum(1 for it in items if it["media"] == "epub"),
            "manga": sum(1 for it in items if it["media"] == "manga")}
