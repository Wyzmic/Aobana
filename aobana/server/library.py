import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time

from aobana import paths
from aobana.utils import FILTER_COLUMNS, count_rows, filtered_rows, outdated_sources, missing_tables, ALLOW_REMOVAL_FLAG, JSONL_FLAG

_LOCK = threading.Lock()
_STATE = {"running": False}


def _beside_db(name):
    return os.path.join(os.path.dirname(os.path.abspath(paths.subs_db())), name)


def _stop_file(kind):
    return _beside_db(f".{kind}.stop")


def _clear_stop(kind):
    try:
        os.remove(_stop_file(kind))
    except OSError:
        pass


def _run_marker():
    return _beside_db(".index_run.json")


def _unfinished():
    try:
        with open(_run_marker(), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None

_STAGES = (("subs", "aobana.indexing.indexer"), ("epub", "aobana.indexing.epub_indexer"),
           ("manga", "aobana.indexing.manga_indexer"))
_STAGE_MEDIA = {"subs": "subs", "epub": "books", "manga": "manga"}


def _count_files(root, ext, skip_dot, progress=None, count_other=True):
    found = other = 0
    if not root or not os.path.isdir(root):
        return None
    last = time.monotonic()
    for dirpath, _, files in os.walk(root):
        for f in files:
            if f.lower().endswith(ext) and not (skip_dot and f.startswith('.')):
                found += 1
            elif count_other and not f.startswith('.'):
                other += 1
        if progress and time.monotonic() - last > 0.25:
            last = time.monotonic()
            progress(found, other)
    return {"files": found, "loose": 0, "other": other}


def _has_files(root, ext, skip_dot):
    if not root or not os.path.isdir(root):
        return False
    for _, _, files in os.walk(root):
        if any(f.lower().endswith(ext) and not (skip_dot and f.startswith('.')) for f in files):
            return True
    return False


def _stage_inputs(stage):
    if stage == "subs":
        return paths.subs_dir(), (".srt", ".ass", ".ssa"), False, paths.subs_db()
    if stage == "manga":
        return paths.manga_dir(), ".mokuro", True, paths.manga_db()
    return paths.books_dir(), ".epub", True, paths.epub_db()


def _indexed(conn, table):
    if conn is None:
        return {"files": 0, "rows": 0}
    try:
        return {"files": conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0],
                "rows": count_rows(conn, table)}
    except Exception:
        return {"files": 0, "rows": 0}


def table_needs():
    out = {}
    for stage, _ in _STAGES:
        db = _stage_inputs(stage)[3]
        out[stage] = []
        if not os.path.isfile(db):
            continue
        try:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            try:
                out[stage] = missing_tables(conn, stage)
            finally:
                conn.close()
        except sqlite3.Error:
            pass
    return out


_FSTATE = {"running": False}
_FIG_STALE = {"stale": True}
_FIG_SAVE_EVERY = 2.0
LONG_TASK_SECONDS = 60


def _figures_path():
    return _beside_db("library_figures.json")


def _figures_key():
    return [paths.subs_dir(), paths.books_dir(), paths.manga_dir()]


def _load_figures():
    try:
        with open(_figures_path(), encoding="utf-8") as fh:
            saved = json.load(fh)
        return saved if isinstance(saved, dict) else None
    except (OSError, ValueError):
        return None


def _save_figures(doc):
    try:
        tmp = _figures_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        os.replace(tmp, _figures_path())
    except OSError:
        pass


def _walk_figures(key, shown):
    started = time.time()
    doc = {"key": key, "complete": False, "subs_disk": None, "books_disk": None, "manga_disk": None}
    last_save = 0.0

    def publish(save=False):
        nonlocal last_save
        with _LOCK:
            _FSTATE.update(subs_disk=doc["subs_disk"], books_disk=doc["books_disk"], manga_disk=doc["manga_disk"])
        if save or time.monotonic() - last_save > _FIG_SAVE_EVERY:
            last_save = time.monotonic()
            if not shown:
                _save_figures(doc)

    try:
        for name, root, ext, skip_dot in (("subs_disk", key[0], (".srt", ".ass", ".ssa"), False),
                                          ("books_disk", key[1], ".epub", True),
                                          ("manga_disk", key[2], ".mokuro", True)):
            def progress(found, other, name=name):
                doc[name] = {"files": found, "loose": 0, "other": other, "counting": True}
                publish()
            if root and os.path.isdir(root):
                doc[name] = {"files": 0, "loose": 0, "other": 0, "counting": True}
            doc[name] = _count_files(root, ext, skip_dot, progress, count_other=name != "manga_disk")
            publish()
        doc.update(complete=True, counted_at=time.time())
        _save_figures(doc)
    finally:
        seconds = time.time() - started
        with _LOCK:
            _FSTATE.update(running=False, finished_at=time.time(), saved=doc if doc["complete"] else None)
        if not shown and doc["complete"] and seconds > LONG_TASK_SECONDS:
            _add_notice("figures", seconds)
        if _FSTATE.get("again"):
            ensure_figures()


def ensure_figures():
    key = _figures_key()
    with _LOCK:
        if _FSTATE.get("running"):
            _FSTATE["again"] = _FSTATE.get("key") != key
            return
        saved = _FSTATE.get("saved") or _load_figures()
        good = bool(saved and saved.get("key") == key and saved.get("complete"))
        if good and not _FIG_STALE["stale"]:
            _FSTATE["saved"] = saved
            return
        _FIG_STALE["stale"] = False
        _FSTATE.update(running=True, key=key, again=False, started_at=time.time(), saved=saved if good else None,
                       subs_disk=None, books_disk=None, manga_disk=None)
    threading.Thread(target=_walk_figures, args=(key, good), daemon=True).start()


def figures():
    ensure_figures()
    with _LOCK:
        running = bool(_FSTATE.get("running"))
        saved = _FSTATE.get("saved")
        keys = ("subs_disk", "books_disk", "manga_disk")
        if saved and saved.get("key") == _figures_key():
            out = {k: saved.get(k) for k in keys}
        else:
            out = {k: _FSTATE.get(k) for k in keys}
    out = {k: (dict(v) if v else v) for k, v in out.items()}
    out["counting"] = running
    listed = filtered_rows(paths.filtered_list())
    for key, media in (("subs_disk", "subs"), ("books_disk", "epub"), ("manga_disk", "manga")):
        if out[key]:
            out[key]["filtered"] = sum(1 for r in listed if r["media"] == media)
    return out


_NOTICES = []
_NOTICE_IDS = iter(range(1, 1 << 62))


def _add_notice(kind, seconds, **extra):
    with _LOCK:
        _NOTICES.append({"id": next(_NOTICE_IDS), "kind": kind, "seconds": round(seconds),
                         "finished_at": time.time(), **extra})
        del _NOTICES[:-10]


def activity():
    with _LOCK:
        return {"index": bool(_STATE.get("running")), "check": bool(_ASTATE.get("running")),
                "move": bool(_MOVE.get("running")),
                "figures": bool(_FSTATE.get("running")), "notices": [dict(n) for n in _NOTICES]}


def dismiss_notice(notice_id):
    with _LOCK:
        _NOTICES[:] = [n for n in _NOTICES if n["id"] != notice_id]


def describe(db_subs, db_epub, db_manga=None):
    subs, books = paths.subs_dir(), paths.books_dir()
    fig = figures()
    needs = table_needs()
    return {
        "installed": paths.INSTALLED,
        "media": paths.media_state(),
        "setup_needed": paths.setup_needed(),
        "default_folders": {k: paths.default_media_folder(k) for k in paths.MEDIA_KINDS},
        "subs_dir": subs,
        "books_dir": books,
        "manga_dir": paths.manga_dir(),
        "data_dir": paths.db_dir(),
        "db_default": paths.default_db_dir(),
        "db_is_default": _same_folder(paths.db_dir(), paths.default_db_dir()),
        "db_sizes": _db_sizes(paths.db_dir()),
        "port": paths.server_port(),
        "port_env": bool(os.environ.get("AOBANA_PORT")),
        "workers": workers_facts(),
        "search_workers": search_workers_facts(),
        "subs_disk": fig["subs_disk"],
        "books_disk": fig["books_disk"],
        "manga_disk": fig["manga_disk"],
        "counting": fig["counting"],
        "subs_indexed": _indexed(db_subs, "subtitles"),
        "books_indexed": _indexed(db_epub, "epubs"),
        "manga_indexed": _indexed(db_manga, "manga"),
        "subs_outdated": outdated_sources(db_subs, "subs"),
        "books_outdated": outdated_sources(db_epub, "epub"),
        "manga_outdated": outdated_sources(db_manga, "manga"),
        "subs_tables": needs["subs"],
        "books_tables": needs["epub"],
        "manga_tables": needs["manga"],
        "index": index_status(),
    }


_SETTINGS_SNAPSHOT_VERSION = 1
_SETTINGS_FIELDS = ("media", "subs_dir", "books_dir", "manga_dir", "data_dir",
                    "db_is_default", "db_sizes", "port", "port_env", "search_workers",
                    "search_cache", "folder_picker")


def settings_view_data():
    db = paths.db_dir()
    return {"media": paths.media_state(), "subs_dir": paths.subs_dir(),
            "books_dir": paths.books_dir(), "manga_dir": paths.manga_dir(),
            "data_dir": db, "db_is_default": _same_folder(db, paths.default_db_dir()),
            "db_sizes": _db_sizes(db), "port": paths.server_port(),
            "port_env": bool(os.environ.get("AOBANA_PORT")),
            "search_workers": search_workers_facts()}


def _settings_snapshot_path():
    return _beside_db("settings_snapshot.json")


def load_settings_snapshot():
    try:
        with open(_settings_snapshot_path(), encoding="utf-8") as fh:
            doc = json.load(fh)
        if (not isinstance(doc, dict) or doc.get("version") != _SETTINGS_SNAPSHOT_VERSION
                or not _same_folder(doc.get("data_dir", ""), paths.db_dir())):
            return None
        data = doc.get("settings")
        return data if isinstance(data, dict) and all(k in data for k in _SETTINGS_FIELDS) else None
    except (OSError, ValueError, TypeError):
        return None


def save_settings_snapshot(data):
    if not isinstance(data, dict) or not all(k in data for k in _SETTINGS_FIELDS):
        return
    path = _settings_snapshot_path()
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"version": _SETTINGS_SNAPSHOT_VERSION, "data_dir": paths.db_dir(),
                       "settings": {k: data[k] for k in _SETTINGS_FIELDS}}, fh, ensure_ascii=False)
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass


def set_folders(subs_dir, books_dir, manga_dir=None):
    if _STATE.get("running"):
        return "busy"
    def change(cfg):
        for key, value in (("subs_dir", subs_dir), ("books_dir", books_dir), ("manga_dir", manga_dir)):
            if value is None:
                continue
            value = os.path.expanduser(str(value).strip().strip('"'))
            if not os.path.isabs(value):
                return f"not_full:{key}"
            value = os.path.abspath(value)
            if not os.path.isdir(value):
                return f"not_found:{key}"
            cfg[key] = value
    return paths.update_config(change)


def set_media(media):
    if _STATE.get("running"):
        return "busy"
    def change(cfg):
        state = {k: paths.media_enabled(k, cfg) for k in paths.MEDIA_KINDS}
        for kind, on in (media or {}).items():
            if kind not in paths.MEDIA_KINDS:
                continue
            state[kind] = bool(on)
            current = {"subs": paths.subs_dir, "books": paths.books_dir, "manga": paths.manga_dir}[kind]()
            if kind == "manga" and current and "manga_dir" not in cfg:
                current = None
            if on and not current:
                folder = paths.default_media_folder(kind)
                try:
                    os.makedirs(folder, exist_ok=True)
                except OSError:
                    return f"not_found:{paths.MEDIA_DIR_KEYS[kind]}"
                cfg[paths.MEDIA_DIR_KEYS[kind]] = folder
        cfg["media"] = state
    err = paths.update_config(change)
    if err:
        return err
    _FIG_STALE["stale"] = True
    _after_db_change()
    return None


def finish_setup(media, subs_dir=None, books_dir=None, manga_dir=None, fresh=True):
    media = {k: bool((media or {}).get(k)) for k in paths.MEDIA_KINDS}
    if not any(media.values()):
        return "none_on"
    chosen = {}
    for kind, value in (("subs", subs_dir), ("books", books_dir), ("manga", manga_dir)):
        value = str(value or "").strip().strip('"')
        if media[kind] and value:
            folder = os.path.expanduser(value)
            if not os.path.isabs(folder):
                return f"not_full:{paths.MEDIA_DIR_KEYS[kind]}"
            folder = os.path.abspath(folder)
            try:
                os.makedirs(folder, exist_ok=True)
            except OSError:
                return f"not_found:{paths.MEDIA_DIR_KEYS[kind]}"
            chosen[kind] = folder
    err = set_folders(chosen.get("subs"), chosen.get("books"), chosen.get("manga"))
    if err:
        return err
    def change(cfg):
        if fresh:
            for key in paths.MEDIA_DIR_KEYS.values():
                cfg.setdefault(key, "")
            cfg.pop("check_asked", None)
        cfg["media_asked"] = True
    paths.update_config(change)
    err = set_media(media)
    if not err and fresh:
        _forget_last_run()
        _forget_check()
    return err


def check_asked():
    return bool(paths.load_config().get("check_asked"))


def media_asked():
    return bool(paths.load_config().get("media_asked"))


def _mark(key):
    def change(cfg):
        if cfg.get(key):
            return False
        cfg[key] = True
    paths.update_config(change)


def mark_media_asked():
    _mark("media_asked")


def mark_check_asked():
    _mark("check_asked")


def _forget_last_run():
    with _LOCK:
        if not _STATE.get("running"):
            moving = _STATE.get("moving")
            _STATE.clear()
            _STATE["running"] = False
            if moving:
                _STATE["moving"] = moving


def _forget_check():
    with _LOCK:
        if _ASTATE.get("running"):
            return
        _ASTATE.clear()
        _ASTATE["running"] = False
    folder = os.path.dirname(_report_path())
    for name in ("analysis.json", "analysis.db"):
        _remove_retrying(os.path.join(folder, name))


_DB_NAMES = ("subs.db", "epub.db", "manga.db")
_DB_SIDECARS = ("", "-wal", "-shm", "-journal")
_DB_OF_MEDIA = {"subs": "subs.db", "books": "epub.db", "manga": "manga.db"}


_DB_COMPANION_DBS = ("search_cache.db", "analysis.db")
_DB_COMPANIONS = ("filtered.tsv", "analysis.json", "estimate.json", "media_cache.json",
                  "library_figures.json", "settings_snapshot.json", ".index_run.json",
                  ".index.stop", ".check.stop")


def _db_files(folder):
    return ([n + s for n in _DB_NAMES + _DB_COMPANION_DBS for s in _DB_SIDECARS
             if os.path.isfile(os.path.join(folder, n + s))]
            + [n for n in _DB_COMPANIONS if os.path.isfile(os.path.join(folder, n))])


def _db_sizes(folder):
    return {n: (os.path.getsize(os.path.join(folder, n)) if os.path.isfile(os.path.join(folder, n)) else None)
            for n in _DB_NAMES}


def _same_folder(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


_MOVE = {"running": False}
_COPY_CHUNK = 16 * 1024 * 1024

_RELEASE_HOOKS = []


def register_release(fn):
    _RELEASE_HOOKS.append(fn)


def _release_handles():
    for fn in _RELEASE_HOOKS:
        try:
            fn()
        except Exception:
            pass
    try:
        from aobana.search.engine import release_db_handles
        release_db_handles()
    except Exception:
        pass


def move_databases(target):
    with _LOCK:
        if _STATE.get("running") or _STATE.get("moving") or _ASTATE.get("running"):
            return "busy", []
        _STATE["moving"] = True
    started = False
    try:
        error, plan = _move_plan(target)
        if error:
            return error, plan or []
        with _LOCK:
            _MOVE.clear()
            _MOVE.update(running=True, done=0, total=plan["total"], started_at=time.time(),
                         dest=plan["dest"], error=None, old_kept=[])
        threading.Thread(target=_move_worker, args=(plan,), daemon=True).start()
        started = True
        return None, []
    finally:
        if not started:
            with _LOCK:
                _STATE.pop("moving", None)


def move_status():
    with _LOCK:
        out = dict(_MOVE)
    if out.get("started_at"):
        out["elapsed"] = round((out.get("finished_at") or time.time()) - out["started_at"], 1)
    return out


def _move_plan(target):
    raw = str(target or "").strip().strip('"')
    default = raw in ("", "default")
    dest = paths.default_db_dir() if default else os.path.abspath(os.path.expanduser(raw))
    if default:
        try:
            os.makedirs(dest, exist_ok=True)
        except OSError:
            return "not_found", None
    src = paths.db_dir()
    if not os.path.isdir(dest):
        return "not_found", None
    if _same_folder(src, dest):
        return "same", None
    there = _db_files(dest)
    if there:
        return "exists", there
    probe = os.path.join(dest, ".aobana-write-test")
    try:
        with open(probe, "w"):
            pass
        os.remove(probe)
    except OSError:
        return "not_writable", None
    files = _db_files(src)
    total = sum(os.path.getsize(os.path.join(src, n)) for n in files)
    return None, {"src": src, "dest": dest, "default": default, "total": total}


def _move_worker(plan):
    error, old_kept = "failed", []
    try:
        error, old_kept = _move_files(plan)
    except Exception:
        error = "failed"
    finally:
        with _LOCK:
            _MOVE.update(running=False, error=error, old_kept=old_kept, finished_at=time.time())
            _STATE.pop("moving", None)


def _copy_counting(s, d):
    with open(s, "rb") as fi, open(d, "wb") as fo:
        while True:
            chunk = fi.read(_COPY_CHUNK)
            if not chunk:
                break
            fo.write(chunk)
            with _LOCK:
                _MOVE["done"] += len(chunk)
    shutil.copystat(s, d)


def _move_files(plan):
    src, dest = plan["src"], plan["dest"]
    _release_handles()
    from aobana.search.result_cache import clear_disk_cache
    clear_disk_cache()
    files = _db_files(src)
    with _LOCK:
        _MOVE["total"] = sum(os.path.getsize(os.path.join(src, n)) for n in files)

    renamed, copied = [], []
    try:
        for name in files:
            s, d = os.path.join(src, name), os.path.join(dest, name)
            size = os.path.getsize(s)
            try:
                os.replace(s, d)
                renamed.append(name)
                with _LOCK:
                    _MOVE["done"] += size
                continue
            except OSError:
                pass
            tmp = d + ".moving"
            _copy_counting(s, tmp)
            if os.path.getsize(tmp) != size:
                raise OSError(f"size mismatch copying {name}")
            os.replace(tmp, d)
            copied.append(name)
        def change(cfg):
            if plan["default"]:
                cfg.pop("db_dir", None)
            else:
                cfg["db_dir"] = dest
        paths.update_config(change)
    except OSError:
        for name in renamed:
            try:
                os.replace(os.path.join(dest, name), os.path.join(src, name))
            except OSError:
                pass
        for name in copied:
            try:
                os.remove(os.path.join(dest, name))
            except OSError:
                pass
        for name in files:
            try:
                os.remove(os.path.join(dest, name + ".moving"))
            except OSError:
                pass
        _after_db_change()
        return "failed", []

    _release_handles()
    old_kept = [os.path.join(src, name) for name in copied if not _remove_retrying(os.path.join(src, name))]
    _FIG_STALE["stale"] = True
    _after_db_change()
    return None, old_kept


def _remove_retrying(path):
    for attempt in range(10):
        try:
            os.remove(path)
            return True
        except FileNotFoundError:
            return True
        except OSError:
            time.sleep(0.3)
    return False


def drop_index(kind):
    name = _DB_OF_MEDIA.get(kind)
    if not name:
        return "unknown", []
    with _LOCK:
        if _STATE.get("running") or _STATE.get("moving") or _ASTATE.get("running"):
            return "busy", []
        _STATE["moving"] = True
    try:
        folder = paths.db_dir()
        files = [os.path.join(folder, name + s) for s in _DB_SIDECARS if os.path.isfile(os.path.join(folder, name + s))]
        if not files:
            return "none", []
        from aobana.search.result_cache import clear_disk_cache
        _release_handles()
        clear_disk_cache()
        _after_db_change(warm=False)
        kept = [f for f in files if not _remove_retrying(f)]
        _after_db_change()
        _FIG_STALE["stale"] = True
        _forget_last_run()
        return None, kept
    finally:
        with _LOCK:
            _STATE.pop("moving", None)


def _after_db_change(warm=True):
    try:
        from aobana.search.engine import reset_caches
        from aobana.search.media_tab import warm_media_library
        reset_caches()
        if warm:
            threading.Thread(target=warm_media_library, daemon=True).start()
    except Exception:
        pass


def set_search_cache(on):
    def change(cfg):
        if on:
            cfg["search_cache"] = True
        else:
            cfg.pop("search_cache", None)
    paths.update_config(change)


usable_cpus = paths.usable_cpus
recommended_workers = paths.recommended_workers


def parallel_available():
    try:
        import multiprocessing.synchronize
        return True
    except ImportError:
        return False


def workers_facts():
    saved = paths.load_config().get("index_workers")
    return {"cpus": usable_cpus(), "recommended": recommended_workers(), "max": usable_cpus(),
            "saved": saved if type(saved) is int and 1 <= saved <= usable_cpus() else None,
            "effective": paths.index_workers(), "env": bool(os.environ.get("AOBANA_INDEX_WORKERS")),
            "parallel": parallel_available()}


def set_workers(value):
    def change(cfg):
        if value == "auto":
            cfg.pop("index_workers", None)
            return None
        try:
            n = int(str(value).strip())
        except (TypeError, ValueError):
            return "bad_workers"
        if not 1 <= n <= usable_cpus():
            return "bad_workers"
        cfg["index_workers"] = n
    return paths.update_config(change)


def search_workers_facts():
    cfg = paths.load_config()
    count = cfg.get("search_workers")
    delay = cfg.get("search_worker_delay")
    cpus = paths.usable_cpus()
    rec = paths.recommended_workers()
    return {"cpus": cpus, "recommended": rec, "workers": paths.search_workers(), "delay": paths.search_worker_delay(),
            "saved_workers": count if type(count) is int else None,
            "saved_delay": delay if type(delay) is int else None}


def set_search_workers(count, delay):
    if count != "auto":
        if (not isinstance(count, (str, int)) or isinstance(count, bool)
                or not str(count).strip().isdigit() or not isinstance(delay, (str, int))
                or isinstance(delay, bool) or not str(delay).strip().isdigit()):
            return "bad_search_workers"
        count, delay = int(str(count).strip()), int(str(delay).strip())
        if not 1 <= count <= paths.usable_cpus() or not 0 <= delay <= 60:
            return "bad_search_workers"

    def change(cfg):
        if count == "auto":
            cfg.pop("search_workers", None)
            cfg.pop("search_worker_delay", None)
        else:
            cfg["search_workers"] = count
            cfg["search_worker_delay"] = delay
    return paths.update_config(change)


def set_port(value):
    try:
        port = int(str(value).strip())
    except (TypeError, ValueError):
        return "bad_port"
    if not 1024 <= port <= 65535:
        return "bad_port"
    return paths.update_config(lambda cfg: cfg.update(port=port))


HANDOFF_PATH = os.path.join(paths.STORE_DIR, "profile-handoff.json")


def _read_handoff():
    try:
        with open(HANDOFF_PATH, encoding="utf-8") as fh:
            doc = json.load(fh)
        return doc if isinstance(doc, dict) and isinstance(doc.get("items"), dict) else None
    except (OSError, ValueError):
        return None


def _write_handoff(doc):
    os.makedirs(paths.STORE_DIR, exist_ok=True)
    tmp = HANDOFF_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False)
    os.replace(tmp, HANDOFF_PATH)


def _string_items(items):
    return {str(k): v for k, v in items.items() if isinstance(v, str)} if isinstance(items, dict) else None


def save_profile_handoff(to_port, from_port, items):
    items = _string_items(items)
    if to_port == from_port or items is None:
        drop_profile_handoff(from_port)
        return
    _write_handoff({"to_port": to_port, "from_port": from_port, "written_at": time.time(), "items": items})


def refresh_profile_handoff(from_port, items):
    doc, items = _read_handoff(), _string_items(items)
    if doc is None or items is None or doc.get("from_port") != from_port:
        return
    doc["items"], doc["written_at"] = items, time.time()
    _write_handoff(doc)


def load_profile_handoff(port):
    doc = _read_handoff()
    return doc if doc is not None and doc.get("to_port") == port else None


def handoff_pending_from(port):
    doc = _read_handoff()
    return doc is not None and doc.get("from_port") == port


def drop_profile_handoff(port, written_at=None):
    doc = _read_handoff()
    if doc is None or port not in (doc.get("to_port"), doc.get("from_port")):
        return
    if written_at is not None and doc.get("written_at") != written_at:
        return
    try:
        os.remove(HANDOFF_PATH)
    except OSError:
        pass


def open_folder(which):
    target = {"subs": paths.subs_dir, "books": paths.books_dir, "manga": paths.manga_dir,
              "data": paths.db_dir}.get(which)
    if target is None:
        return "unknown"
    path = target()
    if not path or not os.path.isdir(path):
        return "not_found"
    return _os_open(path)


def _windows_explorer_windows():
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM), wintypes.LPARAM]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    windows = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            kind = ctypes.create_unicode_buffer(128)
            user32.GetClassNameW(hwnd, kind, len(kind))
            if kind.value in ("CabinetWClass", "ExploreWClass"):
                title = ctypes.create_unicode_buffer(512)
                user32.GetWindowTextW(hwnd, title, len(title))
                windows.append((hwnd, title.value))
        return True

    user32.EnumWindows(visit, 0)
    return windows


def _bring_windows_folder_forward(path, before):
    import ctypes
    import time
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    name = os.path.basename(os.path.normpath(path)).casefold()
    for _ in range(20):
        windows = _windows_explorer_windows()
        new = [hwnd for hwnd, _ in windows if hwnd not in before]
        old_match = [hwnd for hwnd, title in windows if title.casefold() == name]
        if new or (_ >= 9 and old_match):
            hwnd = new[0] if new else old_match[0]
            user32.ShowWindow(hwnd, 9)
            user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x43)
            user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x03)
            user32.SetForegroundWindow(hwnd)
            return
        time.sleep(0.1)


def _os_open(path):
    try:
        if sys.platform == "win32":
            before = {hwnd for hwnd, _ in _windows_explorer_windows()}
            explorer = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "explorer.exe")
            subprocess.Popen([explorer, path])
            threading.Thread(target=_bring_windows_folder_forward, args=(path, before), daemon=True).start()
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            on_phone = os.environ.get("AOBANA_TERMUX") == "1" or os.environ.get("TERMUX_VERSION")
            opener = "termux-open" if on_phone else "xdg-open"
            subprocess.Popen([opener, path])
    except Exception as e:
        return f"failed:{e}"
    return None


def _inside(path, base):
    try:
        return os.path.commonpath([path, base]) == base
    except ValueError:
        return False


def manga_page_image_path(db_manga, rowid):
    root = paths.manga_dir()
    if db_manga is None or not root:
        return None
    try:
        rowid = int(rowid)
    except (TypeError, ValueError, OverflowError):
        return None
    got = db_manga.execute(
        "SELECT s.relpath, p.page FROM manga m JOIN sources s ON s.id = m.source_id "
        "JOIN manga_pages p ON p.rowid = m.rowid WHERE m.rowid = ?", (int(rowid),)).fetchone()
    if not got:
        return None
    relpath, page = got[0], got[1]
    mokuro = os.path.realpath(os.path.join(root, *re.split(r"[\\/]", relpath)))
    base = os.path.realpath(root)
    if not _inside(mokuro, base) or not os.path.isfile(mokuro):
        return None
    try:
        with open(mokuro, encoding="utf-8") as fh:
            pages = json.load(fh).get("pages") or []
        img = pages[page - 1].get("img_path") if 1 <= page <= len(pages) else None
    except (OSError, ValueError, AttributeError):
        return None
    if not img:
        return None
    folder = mokuro[:-len(".mokuro")] if mokuro.lower().endswith(".mokuro") else mokuro
    image = os.path.realpath(os.path.join(folder, img))
    if not _inside(image, base) or not os.path.isfile(image):
        return None
    return image


def index_status():
    with _LOCK:
        out = {k: (list(v) if isinstance(v, list) else v) for k, v in _STATE.items()}
    if not out.get("running"):
        out["unfinished"] = _unfinished()
    return out


def stop_indexing():
    with _LOCK:
        if not _STATE.get("running"):
            return False
        _STATE["stopping"] = True
    try:
        open(_stop_file("index"), "w").close()
    except OSError:
        return False
    return True


def stop_analysis():
    with _LOCK:
        if not _ASTATE.get("running"):
            return False
        _ASTATE["stopping"] = True
    try:
        open(_stop_file("check"), "w").close()
    except OSError:
        return False
    return True


def start_indexing(only=None, outdated=False, tables=False, allow_removal=False):
    if tables:
        needed = table_needs()
        stages = tuple(st for st in _STAGES if needed[st[0]])
    else:
        if isinstance(only, list):
            if not only or any(not isinstance(st, str) or st not in _STAGE_MEDIA for st in only):
                raise ValueError("Invalid media selection.")
            selected = frozenset(only)
        else:
            selected = frozenset(_STAGE_MEDIA) if only in (None, "", "all") else frozenset((only,))
        media = paths.media_state()
        stages = tuple(st for st in _STAGES if st[0] in selected
                       and media[_STAGE_MEDIA[st[0]]])
    def wanted(stage):
        root, ext, skip_dot, db = _stage_inputs(stage)
        return os.path.isfile(db) or (not tables and _has_files(root, ext, skip_dot))
    stages = tuple(st for st in stages if wanted(st[0]))
    if not stages:
        return "nothing"
    with _LOCK:
        if _STATE.get("running") or _STATE.get("moving") or _ASTATE.get("running"):
            return False
        if allow_removal and not tables:
            held = frozenset(_STATE.get("removal_held", {}))
            stages = tuple(st for st in stages if st[0] in held)
            if not stages:
                return "nothing"
        _STATE.clear()
        _STATE.update({
            "running": True, "stage": stages[0][0], "stages": [st[0] for st in stages],
            "done": 0, "total": 0, "current": "",
            "started_at": time.time(), "finished_at": None, "error": None,
            "results": {}, "skipped_clash": [], "failed": [], "ignored_other": {}, "filtered": {},
            "root_missing": [], "root_not_set": [], "log": [], "stopping": False, "stopped": False,
            "outdated": bool(outdated), "tables": bool(tables), "phase": "", "removal_held": {},
            "allow_removal": bool(allow_removal),
        })
    _clear_stop("index")
    try:
        with open(_run_marker(), "w", encoding="utf-8") as fh:
            json.dump({"started_at": time.time(), "stages": [st[0] for st in stages],
                       "outdated": bool(outdated), "tables": bool(tables)}, fh)
    except OSError:
        pass
    threading.Thread(target=_run, args=(stages, outdated, tables, allow_removal), daemon=True).start()
    return True


def _set(**kw):
    with _LOCK:
        _STATE.update(kw)


def _child_cmd(module, args=()):
    source_bootstrap = ("import runpy, sys; "
                        f"sys.path.insert(0, {paths.BASE_DIR!r}); "
                        f"runpy.run_module({module!r}, run_name='__main__', alter_sys=True)")
    return [sys.executable, "-c", source_bootstrap] + list(args)


def _pump(proc, handle):
    try:
        for line in proc.stdout:
            handle(line.rstrip("\r\n"))
    except BaseException:
        proc.kill()
        raise
    finally:
        proc.stdout.close()
    return proc.wait()


def _event(line):
    try:
        ev = json.loads(line)
    except ValueError:
        ev = None
    if not isinstance(ev, dict) or not isinstance(ev.get("type"), str):
        return {"type": "malformed", "text": line}
    return ev


def _log(state, text):
    state["log"].append(text)
    del state["log"][:-200]


def _run(stages, outdated=False, tables=False, allow_removal=False):
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1",
               AOBANA_STOP_FILE=_stop_file("index"))
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        for stage, script in stages:
            _set(stage=stage, done=0, total=0, current="", phase="")
            args = [JSONL_FLAG] + (["--tables"] if tables else ["--outdated"] if outdated else [])
            if allow_removal and not tables:
                args.append(ALLOW_REMOVAL_FLAG)
            proc = subprocess.Popen(
                _child_cmd(script, args),
                cwd=paths.BASE_DIR, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                encoding="utf-8", errors="replace", creationflags=flags)
            code = _pump(proc, lambda line: _read_line(stage, line))
            if code != 0:
                _set(error=f"{script} exited with code {code}")
                break
            if _STATE.get("stopped"):
                break
    except Exception as e:
        _set(error=f"{type(e).__name__}: {e}")
    finally:
        try:
            from aobana.search.engine import reset_caches
            reset_caches()
        except Exception:
            pass
        _set(running=False, stopping=False, stage="done", current="", finished_at=time.time())
        _clear_stop("index")
        _FIG_STALE["stale"] = True
        seconds = time.time() - (_STATE.get("started_at") or time.time())
        if seconds > LONG_TASK_SECONDS:
            _add_notice("index", seconds, stopped=bool(_STATE.get("stopped")), error=_STATE.get("error"))
        try:
            os.remove(_run_marker())
        except OSError:
            pass
        try:
            from aobana.search.media_tab import warm_media_library
            threading.Thread(target=warm_media_library, daemon=True).start()
        except Exception:
            pass


def _read_line(stage, line):
    ev = _event(line)
    with _LOCK:
        try:
            _index_event(stage, ev)
        except (KeyError, TypeError, ValueError) as e:
            _log(_STATE, f"Unreadable progress line ({type(e).__name__}): {line}")


def _index_event(stage, ev):
    kind = ev["type"]
    if kind != "progress" and isinstance(ev.get("text"), str):
        _log(_STATE, ev["text"])
    if kind == "total":
        _STATE.update(total=int(ev["total"]), phase="")
    elif kind == "phase":
        if "done" in ev:
            _STATE.update(phase=str(ev["phase"]), done=int(ev["done"]), total=int(ev["total"]))
        else:
            _STATE.update(phase=str(ev["phase"]), done=0, total=0, current="")
    elif kind == "progress":
        _STATE.update(done=int(ev["done"]), total=int(ev["total"]), current=str(ev["file"]))
    elif kind == "skipped_clash":
        _STATE["skipped_clash"].append(str(ev["file"]))
    elif kind == "ignored_other":
        _STATE["ignored_other"][stage] = int(ev["count"])
    elif kind == "filtered":
        _STATE["filtered"][stage] = int(ev["count"])
    elif kind == "failed":
        _STATE["failed"].append(f"{ev['file']}: {ev['error']}")
    elif kind == "removal_held":
        _STATE["removal_held"][stage] = {"gone": int(ev["gone"]), "indexed": int(ev["indexed"])}
    elif kind == "root_missing":
        _STATE["root_missing"].append(stage)
    elif kind == "root_not_set":
        _STATE["root_not_set"].append(stage)
    elif kind == "stopped":
        _STATE["stopped"] = True
    elif kind == "summary":
        _STATE["results"][stage] = {"unchanged": int(ev["unchanged"]), "indexed": int(ev["indexed"]),
                                    "removed": int(ev["removed"])}


_ASTATE = {"running": False}
FILTERABLE = ("bilingual", "other_language", "language_review", "image_only", "duplicate", "duplicate_kept")


def analysis_status():
    with _LOCK:
        return {k: (list(v) if isinstance(v, list) else v) for k, v in _ASTATE.items()}


def start_analysis(only=None):
    if only == "manga":
        return False
    only = only if only in ("subs", "epub") else None
    with _LOCK:
        if _ASTATE.get("running") or _STATE.get("running") or _STATE.get("moving"):
            return False
        _ASTATE.clear()
        _ASTATE.update(running=True, stage="subs" if only != "epub" else "epub", done=0, total=0,
                       current="", started_at=time.time(), finished_at=None, error=None, log=[],
                       stopping=False, stopped=False)
    _clear_stop("check")
    threading.Thread(target=_run_analysis, args=(only,), daemon=True).start()
    return True


def _read_analysis_line(line):
    ev = _event(line)
    with _LOCK:
        try:
            kind = ev["type"]
            if kind == "progress":
                _ASTATE.update(done=int(ev["done"]), total=int(ev["total"]), current=str(ev["file"]))
            elif kind == "stage":
                _ASTATE.update(stage=str(ev["stage"]), done=0, total=0, current="")
            elif kind == "total":
                _ASTATE["total"] = int(ev["total"])
            elif kind == "stopped":
                _ASTATE["stopped"] = True
            elif isinstance(ev.get("text"), str):
                _log(_ASTATE, ev["text"])
        except (KeyError, TypeError, ValueError) as e:
            _log(_ASTATE, f"Unreadable progress line ({type(e).__name__}): {line}")


def _run_analysis(only):
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1",
               AOBANA_STOP_FILE=_stop_file("check"))
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    cmd = _child_cmd("aobana.indexing.analyser", [JSONL_FLAG] + (["--only", only] if only else []))
    try:
        proc = subprocess.Popen(cmd, cwd=paths.BASE_DIR, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, encoding="utf-8", errors="replace",
                                creationflags=flags)
        if _pump(proc, _read_analysis_line) != 0:
            with _LOCK:
                _ASTATE["error"] = f"analyser.py exited with code {proc.returncode}"
    except Exception as e:
        with _LOCK:
            _ASTATE["error"] = f"{type(e).__name__}: {e}"
    finally:
        with _LOCK:
            _ASTATE.update(running=False, stopping=False, current="", finished_at=time.time())
        _clear_stop("check")
        seconds = time.time() - (_ASTATE.get("started_at") or time.time())
        if seconds > LONG_TASK_SECONDS:
            _add_notice("check", seconds, stopped=bool(_ASTATE.get("stopped")), error=_ASTATE.get("error"))


def _report_path():
    return os.path.join(os.path.dirname(os.path.abspath(paths.subs_db())), "analysis.json")


def analysis_report():
    try:
        with open(_report_path(), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _write_filtered(rows):
    path = paths.filtered_list()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\t".join(FILTER_COLUMNS) + "\n")
        for r in rows:
            fh.write("\t".join(str(r.get(c, "")).replace("\t", " ").replace("\n", " ")
                               for c in FILTER_COLUMNS) + "\n")
    os.replace(tmp, path)


def filtered_list():
    roots = {"subs": paths.subs_dir(), "epub": paths.books_dir()}
    out = []
    for r in filtered_rows(paths.filtered_list()):
        root = roots.get(r["media"])
        p = os.path.join(root, r["name"]) if root else ""
        if root and r["media"] == "subs" and not os.path.isfile(p):
            p = os.path.join(root, os.path.basename(r["name"]))
        out.append(dict(r, exists=bool(root) and os.path.isfile(p)))
    return out


def filter_flagged(ids):
    report = analysis_report()
    if not report:
        return "no_report", None
    with _LOCK:
        if _STATE.get("running") or _STATE.get("moving") or _ASTATE.get("running"):
            return "busy", None
        _STATE["moving"] = True
    try:
        roots = {"subs": paths.subs_dir(), "epub": paths.books_dir()}
        rows = filtered_rows(paths.filtered_list())
        have = {(r["media"], r["name"]) for r in rows}
        added, refused = [], []
        id_set = set(ids)
        for kept in [it for it in report["items"] if it["reason"] == "duplicate_kept" and it["id"] in id_set]:
            group = [it for it in report["items"]
                     if it["media"] == kept["media"] and it.get("keep") == kept["keep"]]
            stay = [it for it in group if it["id"] not in id_set and not it.get("filtered")]
            if stay:
                new_keep = stay[0]
                kept["reason"] = "duplicate"
                kept["how"] = new_keep.get("how", "same_bytes" if kept["media"] == "subs" else "same_text")
                kept["share"] = new_keep.get("share", 1.0)
                new_keep["reason"] = "duplicate_kept"
                for it in group:
                    it["keep"] = new_keep["name"]
                    it["keep_path"] = new_keep["path"]
        for item in report["items"]:
            if item["id"] not in id_set:
                continue
            media = item["media"]
            if (item["reason"] not in FILTERABLE or not roots.get(media)
                    or not _same_folder(roots[media], report["roots"][media])):
                refused.append(item["path"])
                continue
            reason = "duplicate" if item["reason"] == "duplicate_kept" else item["reason"]
            if (media, item["name"]) not in have:
                rows.append({"media": media, "name": item["name"], "reason": reason,
                             "keep": item.get("keep", ""), "date": time.strftime("%Y-%m-%d %H:%M:%S"),
                             "origin": "manual"})
                have.add((media, item["name"]))
            item["filtered"] = True
            added.append(item["id"])
        _write_filtered(rows)
        tmp = _report_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, _report_path())
        return None, {"filtered": added, "refused": refused}
    finally:
        with _LOCK:
            _STATE.pop("moving", None)


def unfilter(entries):
    with _LOCK:
        if _STATE.get("running") or _STATE.get("moving") or _ASTATE.get("running"):
            return "busy", 0
        _STATE["moving"] = True
    try:
        drop = {(str(m), str(n)) for m, n in entries}
        rows = filtered_rows(paths.filtered_list())
        kept = [r for r in rows if (r["media"], r["name"]) not in drop]
        if len(kept) != len(rows):
            _write_filtered(kept)
        return None, len(rows) - len(kept)
    finally:
        with _LOCK:
            _STATE.pop("moving", None)


def estimate(only=None):
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    cmd = _child_cmd("aobana.indexing.analyser", ["--estimate"])
    if only in ("subs", "epub", "manga"):
        cmd += ["--only", only]
    try:
        out = subprocess.run(cmd, cwd=paths.BASE_DIR, capture_output=True, encoding="utf-8",
                             errors="replace", timeout=300, creationflags=flags,
                             env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        return json.loads(out.stdout.strip().splitlines()[-1])
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
