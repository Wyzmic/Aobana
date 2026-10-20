
import os
import re
import sqlite3
import threading
from aobana import paths
from aobana.utils import media_connections
from aobana.search.result_cache import (
    db_fingerprint,
)


_BACKGROUND_READERS = set()
_BACKGROUND_READERS_LOCK = threading.Lock()


_MEDIA_LIBRARY = {}
_MEDIA_LIBRARY_LOCK = threading.Lock()
_MEDIA_SCHEDULE_LOCK = threading.Lock()
_MEDIA_SCHEDULED = set()


def _library_sort_key(name):
    from aobana.search.titles import get_sort_key
    return get_sort_key(name)


def get_media_library(dbs, db_epub=None, db_manga=None):
    dbs = media_connections(dbs, db_epub, db_manga)
    key = db_fingerprint(*dbs.values())
    cached = _media_library_cached(key)
    if cached is not None:
        return cached
    with _MEDIA_LIBRARY_LOCK:
        cached = _media_library_cached(key)
        if cached is not None:
            return cached
        return _compute_media_library(dbs, key=key)


MEDIA_SECONDS_PER_GB = 3.2
_MEDIA_COMPUTE = {"started": None, "expected": None}


MEDIA_CACHE_FORM = 2


def _media_cache_path():
    return paths.companion('media_cache.json')


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
    if data and data.get("key") == repr(key) and data.get("form") == MEDIA_CACHE_FORM and isinstance(data.get("items"), list):
        _MEDIA_LIBRARY.clear()
        _MEDIA_LIBRARY[key] = data["items"]
        return data["items"]
    return None


def _db_bytes(dbs):
    total = 0
    for entry in db_fingerprint(*dbs.values()):
        if entry:
            total += sum(st[1] for st in entry[1:] if st)
    return total


def media_library_status(dbs, db_epub=None, db_manga=None):
    import time
    dbs = media_connections(dbs, db_epub, db_manga)
    db_subs = dbs.get("subs")
    key = db_fingerprint(*dbs.values())
    if _media_library_cached(key) is not None:
        return {"ready": True}
    if db_subs is not None:
        from aobana.indexing.source_ranges import ready
        if not ready(db_subs):
            from aobana.utils import outdated_sources
            need = {'requires_index': True} if outdated_sources(db_subs, 'subs') else {'requires_tables': ['source_ranges']}
            return dict({'ready': False, 'elapsed': 0, 'remaining': None}, **need)
    with _MEDIA_SCHEDULE_LOCK:
        if key not in _MEDIA_SCHEDULED:
            _MEDIA_SCHEDULED.add(key)
            def build():
                try:
                    warm_media_library()
                finally:
                    with _MEDIA_SCHEDULE_LOCK:
                        _MEDIA_SCHEDULED.discard(key)
            threading.Thread(target=build, daemon=True).start()
    started = _MEDIA_COMPUTE["started"] or time.monotonic()
    expected = _MEDIA_COMPUTE["expected"] or _media_expected_seconds(dbs)
    elapsed = time.monotonic() - started
    return {"ready": False, "elapsed": round(elapsed, 1),
            "remaining": round(expected-elapsed, 1) if expected > elapsed else None}


def _media_expected_seconds(dbs, db_epub=None, db_manga=None):
    dbs = media_connections(dbs, db_epub, db_manga)
    data = _media_cache_read() or {}
    rate = data.get("seconds_per_gb") or MEDIA_SECONDS_PER_GB
    return rate * _db_bytes(dbs) / 1024 ** 3


def warm_media_library():
    conns = {}
    try:
        on = paths.media_state()
        for media, (path, kind) in {"subs": (paths.subs_db(), "subs"), "epub": (paths.epub_db(), "books"), "manga": (paths.manga_db(), "manga"), "custom": (paths.custom_db(), "custom")}.items():
            conns[media] = (sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
                            if on[kind] and os.path.exists(path) else None)
        with _BACKGROUND_READERS_LOCK:
            _BACKGROUND_READERS.update(c for c in conns.values() if c is not None)
        get_media_library(conns)
    except Exception:
        pass
    finally:
        with _BACKGROUND_READERS_LOCK:
            _BACKGROUND_READERS.difference_update(conns.values())
        for c in conns.values():
            if c is not None:
                c.close()


def _compute_media_library(dbs, db_epub=None, key=None, db_manga=None):
    dbs = media_connections(dbs, db_epub, db_manga)
    import time
    _MEDIA_COMPUTE["started"] = time.monotonic()
    _MEDIA_COMPUTE["expected"] = _media_expected_seconds(dbs)
    opened = []
    try:
        conns = [c for c in dbs.values() if c is not None]
        for c in conns:
            if not c.in_transaction:
                c.execute('BEGIN')
                opened.append(c)
        out = _count_media_library(dbs)
    finally:
        for c in opened:
            c.rollback()
        seconds = time.monotonic() - _MEDIA_COMPUTE["started"]
        _MEDIA_COMPUTE["started"] = _MEDIA_COMPUTE["expected"] = None
    if db_fingerprint(*dbs.values()) != key:
        return out
    _MEDIA_LIBRARY.clear()
    _MEDIA_LIBRARY[key] = out
    size = _db_bytes(dbs)
    try:
        import json
        path = _media_cache_path()
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"key": repr(key), "form": MEDIA_CACHE_FORM, "items": out, "seconds": round(seconds, 2),
                       "seconds_per_gb": round(seconds / (size / 1024 ** 3), 3) if size else None},
                      f, ensure_ascii=False)
        os.replace(tmp, path)
    except OSError:
        pass
    return out


def _count_media_library(dbs, db_epub=None, db_manga=None):
    dbs = media_connections(dbs, db_epub, db_manga)
    db_subs = dbs.get("subs")
    db_epub = dbs.get("epub")
    db_manga = dbs.get("manga")
    items = {}
    if db_subs is not None:
        try:
            from aobana.indexing.source_ranges import ready, counts
            if ready(db_subs):
                rows = counts(db_subs)
                lines = None
            else:
                raise sqlite3.OperationalError('Subtitle source ranges need explicit table preparation.')
            for sid, relpath, count in rows:
                show = re.split(r"[\\/]", relpath)[0]
                it = items.setdefault(("subs", show), {
                    "media": "subs", "folder": show, "author": "", "episodes": 0, "lines": 0})
                it["episodes"] += 1
                it["lines"] += count
        except sqlite3.Error:
            raise
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
            raise
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
            raise
    if dbs.get('custom') is not None:
        from aobana.search.custom import all_sources, lone_file
        sources = None
        for category, files, lines in dbs['custom'].execute('SELECT path, files, lines FROM custom_folders WHERE parent = ? AND path != ?', ('', '')):
            items[('custom', category)] = {'media': 'custom', 'folder': category, 'author': '', 'episodes': files, 'lines': lines}
            if files == 1:
                # A category of one file under its own name opens that file
                sources = sources if sources is not None else all_sources(dbs['custom'])[1]
                alone = lone_file(sources, category)
                if alone is not None:
                    items[('custom', category)]['file'] = alone['file']
    return sorted(items.values(), key=lambda it: _library_sort_key(it["folder"]))


MEDIA_SORTS = {"name": None, "parts_desc": ("episodes", True), "parts_asc": ("episodes", False),
               "lines_desc": ("lines", True), "lines_asc": ("lines", False)}


def media_page(items, media="all", needle="", offset=0, limit=0, folder=None, sort="name"):
    if folder is not None:
        rows = [it for it in items if it["folder"] == folder and media in ("all", it["media"])]
        return {"items": rows[:1], "total": len(rows[:1]), "has_more": False}
    from aobana.utils import fold_title_filter
    needle = fold_title_filter(needle.strip())
    rows = [it for it in items
            if media in ("all", it["media"])
            and (not needle or needle in fold_title_filter(it["folder"]) or needle in fold_title_filter(it["author"]))]
    key = MEDIA_SORTS.get(sort)
    if key:
        rows = sorted(rows, key=lambda it: it[key[0]] or 0, reverse=key[1])
    page = rows[offset:offset + limit] if limit else rows[offset:]
    return {"items": page, "total": len(rows), "has_more": offset + len(page) < len(rows),
            "shows": sum(1 for it in items if it["media"] == "subs"),
            "books": sum(1 for it in items if it["media"] == "epub"),
            "manga": sum(1 for it in items if it["media"] == "manga"),
            "custom": sum(1 for it in items if it["media"] == "custom")}
