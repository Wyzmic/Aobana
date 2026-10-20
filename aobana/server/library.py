import json
import hashlib
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from aobana.indexing.process_tree import OwnedProcess

from aobana import paths
from aobana.utils import media_walk, FILTER_COLUMNS, count_rows, filtered_rows, outdated_sources, missing_tables, ALLOW_REMOVAL_FLAG, JSONL_FLAG, name_key, trim_outdated, ruby_outdated

_LOCK = threading.Lock()
_STATE = {"running": False}
if paths.companion_errors():
    _STATE['error'] = paths.companion_errors()[0]['error']


def _beside_db(name):
    path = paths.companion(name)
    folder = os.path.dirname(path)
    if os.path.isdir(os.path.dirname(folder)) and not os.path.isdir(folder):
        os.makedirs(folder, exist_ok=True)
    return path


def _stop_file(kind):
    suffix = '-' + _STATE['run_id'] if kind == 'index' and _STATE.get('run_id') else ''
    return _beside_db(f".{kind}{suffix}.stop")


def _clear_stop(kind):
    try:
        os.remove(_stop_file(kind))
    except OSError:
        pass


def _run_marker():
    return _beside_db('.index_run-' + _STATE.get('run_id', 'legacy') + '.json')


def _unfinished():
    try:
        from pathlib import Path
        markers = list(Path(paths.companion('.index-runs')).parent.glob('.index_run-*.json'))
        legacy = Path(_beside_db('.index_run.json'))
        if legacy.exists():
            markers.append(legacy)
        if not markers:
            return None
        with max(markers, key=lambda p: p.stat().st_mtime).open(encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None

_STAGES = (("subs", "aobana.indexing.indexer"), ("epub", "aobana.indexing.epub_indexer"),
           ("manga", "aobana.indexing.manga_indexer"), ("custom", "aobana.indexing.custom_indexer"))
_STAGE_MEDIA = {"subs": "subs", "epub": "books", "manga": "manga", "custom": "custom"}


def _count_files(root, media, progress=None, count_other=True):
    found = other = 0
    if not any(os.path.isdir(folder) for folder in paths.root_list(root)):
        return None
    last = time.monotonic()
    from aobana.utils import media_walk_roots
    for _, _, kept, rest in media_walk_roots(root, media, deduplicate=False):
        found += len(kept)
        if count_other:
            other += rest
        if progress and time.monotonic() - last > 0.25:
            last = time.monotonic()
            progress(found, other)
    return {"files": found, "loose": 0, "other": other}


def _has_files(root, media):
    if not any(os.path.isdir(folder) for folder in paths.root_list(root)):
        return False
    return any(kept for folder in paths.root_list(root) for _, kept, _ in media_walk(folder, media))


def _stage_inputs(stage):
    getter = {'subs': paths.subs_db, 'epub': paths.epub_db, 'manga': paths.manga_db, 'custom': paths.custom_db}[stage]
    return paths.roots_value(stage), stage, getter()


def _indexed(conn, table):
    if conn is None:
        return {"files": 0, "rows": 0}
    try:
        return {"files": conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0],
                "rows": count_rows(conn, table)}
    except Exception:
        return {"files": 0, "rows": 0}


def _read_table_needs():
    out = {}
    for stage, _ in _STAGES:
        db = _stage_inputs(stage)[2]
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


def _has_outdated(stage):
    db = _stage_inputs(stage)[2]
    if not os.path.isfile(db):
        return False
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            return outdated_sources(conn, stage) > 0
        finally:
            conn.close()
    except sqlite3.Error:
        return False


_FSTATE = {"running": False}
_FIG_STALE = {"stale": True}
_FIG_SAVE_EVERY = 2.0
LONG_TASK_SECONDS = 60


def _figures_path():
    return _beside_db("library_figures.json")


_DISK_KEYS = ("subs_disk", "books_disk", "manga_disk", "custom_disk")
_DISK_MEDIA = ("subs", "epub", "manga", "custom")


def _figures_key():
    return [paths.roots_value(media) for media in _DISK_MEDIA]


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
    doc = {"key": key, "complete": False, **{k: None for k in _DISK_KEYS}}
    last_save = 0.0

    def publish(save=False):
        nonlocal last_save
        with _LOCK:
            _FSTATE.update({k: doc[k] for k in _DISK_KEYS})
        if save or time.monotonic() - last_save > _FIG_SAVE_EVERY:
            last_save = time.monotonic()
            if not shown:
                _save_figures(doc)

    try:
        for name, root, media in zip(_DISK_KEYS, key, _DISK_MEDIA):
            def progress(found, other, name=name):
                doc[name] = {"files": found, "loose": 0, "other": other, "counting": True}
                publish()
            if any(os.path.isdir(folder) for folder in paths.root_list(root)):
                doc[name] = {"files": 0, "loose": 0, "other": 0, "counting": True}
            doc[name] = _count_files(root, media, progress, count_other=name != "manga_disk")
            publish()
        doc.update(complete=True, counted_at=time.time())
        _save_figures(doc)
    finally:
        seconds = time.time() - started
        if not shown and doc["complete"] and seconds > LONG_TASK_SECONDS:
            _add_notice("figures", seconds)
        with _LOCK:
            _FSTATE.update(running=False, finished_at=time.time(), saved=doc if doc["complete"] else None)
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
                       **{k: None for k in _DISK_KEYS})
    threading.Thread(target=_walk_figures, args=(key, good), daemon=True).start()


def figures():
    ensure_figures()
    with _LOCK:
        running = bool(_FSTATE.get("running"))
        saved = _FSTATE.get("saved")
        keys = _DISK_KEYS
        if saved and saved.get("key") == _figures_key():
            out = {k: saved.get(k) for k in keys}
        else:
            out = {k: _FSTATE.get(k) for k in keys}
    out = {k: (dict(v) if v else v) for k, v in out.items()}
    out["counting"] = running
    listed = filtered_rows(paths.filtered_list())
    for key, media in zip(_DISK_KEYS, _DISK_MEDIA):
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


def describe(dbs, db_epub=None, db_manga=None):
    subs, books = paths.subs_dir(), paths.books_dir()
    fig = figures()
    summary = summaries()
    needs = summary.get("needs", {s: [] for s, _ in _STAGES})
    return {
        "installed": paths.INSTALLED,
        "media": paths.media_state(),
        "setup_needed": paths.setup_needed(),
        "default_folders": {k: paths.default_media_folder(k) for k in paths.MEDIA_KINDS},
        "subs_dir": subs,
        "books_dir": books,
        "manga_dir": paths.manga_dir(),
        "custom_dir": paths.custom_dir(),
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
        "custom_disk": fig["custom_disk"],
        "counting": fig["counting"],
        "subs_indexed": summary.get("subs_indexed"),
        "books_indexed": summary.get("books_indexed"),
        "manga_indexed": summary.get("manga_indexed"),
        "custom_indexed": summary.get("custom_indexed"),
        "updating": summary.get("updating", True),
        "subs_outdated": summary.get("subs_outdated", 0),
        "books_outdated": summary.get("books_outdated", 0),
        "manga_outdated": summary.get("manga_outdated", 0),
        "custom_outdated": summary.get("custom_outdated", 0),
        "subs_tables": needs["subs"],
        "books_tables": needs["epub"],
        "manga_tables": needs["manga"],
        "custom_tables": needs.get("custom", []),
        "index": index_status(),
        "folder_errors": paths.companion_errors(),
        **{key: paths.media_roots(kind) for kind, key in paths.MEDIA_DIR_LIST_KEYS.items()},
    }


_SETTINGS_SNAPSHOT_VERSION = 2
_SETTINGS_FIELDS = ("media", "subs_dir", "books_dir", "manga_dir", "custom_dir", "data_dir",
                    "db_is_default", "db_sizes", "port", "port_env", "search_workers",
                    "search_cache", "folder_picker", "subs_dirs", "books_dirs", "manga_dirs", "custom_dirs")


def settings_view_data():
    db = paths.db_dir()
    return {"media": paths.media_state(), "subs_dir": paths.subs_dir(),
            "books_dir": paths.books_dir(), "manga_dir": paths.manga_dir(),
            "custom_dir": paths.custom_dir(), "data_dir": db, "db_is_default": _same_folder(db, paths.default_db_dir()),
            "db_sizes": _db_sizes(db), "port": paths.server_port(),
            "port_env": bool(os.environ.get("AOBANA_PORT")),
            "search_workers": search_workers_facts(),
            "subtitle_tags": paths.subtitle_tags(),
            "custom_trim": paths.custom_trim(), "custom_trim_pending": _custom_trim_pending(),
            "custom_ruby": paths.custom_ruby(), "custom_ruby_pending": _custom_ruby_pending(),
            **{key: paths.media_roots(kind) for kind, key in paths.MEDIA_DIR_LIST_KEYS.items()}}


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


def _library_busy():
    with _LOCK:
        if _STATE.get("running") or _STATE.get("moving") or _ASTATE.get("running"):
            return True
    from aobana.indexing.run_control import writer_active
    return any(writer_active(_stage_inputs(stage)[2]) for stage, _ in _STAGES)


def set_folders(subs_dir=None, books_dir=None, manga_dir=None, custom_dir=None,
                subs_dirs=None, books_dirs=None, manga_dirs=None, custom_dirs=None):
    if _library_busy():
        return "busy"
    def change(cfg):
        final = {paths.MEDIA_DIR_KEYS[kind]: paths.set_roots(kind, cfg) for kind in paths.MEDIA_KINDS}
        changed = set()
        for key, value in (("subs_dir", subs_dirs if subs_dirs is not None else subs_dir),
                           ("books_dir", books_dirs if books_dirs is not None else books_dir),
                           ("manga_dir", manga_dirs if manga_dirs is not None else manga_dir),
                           ("custom_dir", custom_dirs if custom_dirs is not None else custom_dir)):
            if value is None:
                continue
            folders = []
            for folder in paths.root_list(value):
                folder = os.path.expanduser(str(folder).strip().strip('"'))
                if not os.path.isabs(folder):
                    return f"not_full:{key}"
                folder = os.path.abspath(folder)
                if not os.path.isdir(folder):
                    return f"not_found:{key}"
                folders.append(folder)
            cfg.pop(key, None)
            cfg[key + 's'] = folders
            final[key] = folders
            changed.add(key)
        return folder_overlap(final, changed)
    return paths.update_config(change)


def folder_overlap(final, changed):
    held = [(key, i, folder) for key, folders in final.items() for i, folder in enumerate(folders)]
    for n, (key, i, folder) in enumerate(held):
        for other, j, there in held[n + 1:]:
            if (key in changed or other in changed) and paths.folders_overlap(folder, there):
                first, second = (key, other) if key in changed else (other, key)
                return f"overlap:{first}:{second}"
    return None


def set_media(media):
    if _library_busy():
        return "busy"
    def change(cfg):
        state = {k: paths.media_enabled(k, cfg) for k in paths.MEDIA_KINDS}
        for kind, on in (media or {}).items():
            if kind not in paths.MEDIA_KINDS:
                continue
            state[kind] = bool(on)
            current = {"subs": paths.subs_dir, "books": paths.books_dir, "manga": paths.manga_dir,
                       "custom": paths.custom_dir}[kind]()
            if kind in ("manga", "custom") and current and paths.MEDIA_DIR_LIST_KEYS[kind] not in cfg:
                current = None
            if on and not current:
                folder = paths.default_media_folder(kind)
                try:
                    os.makedirs(folder, exist_ok=True)
                except OSError:
                    return f"not_found:{paths.MEDIA_DIR_KEYS[kind]}"
                final = {paths.MEDIA_DIR_KEYS[k]: paths.set_roots(k, cfg) for k in paths.MEDIA_KINDS}
                final[paths.MEDIA_DIR_KEYS[kind]] = [folder]
                clash = folder_overlap(final, {paths.MEDIA_DIR_KEYS[kind]})
                if clash:
                    return clash
                cfg[paths.MEDIA_DIR_LIST_KEYS[kind]] = [folder]
        cfg["media"] = state
    err = paths.update_config(change)
    if err:
        return err
    _FIG_STALE["stale"] = True
    _after_db_change()
    return None


def finish_setup(media, subs_dir=None, books_dir=None, manga_dir=None, custom_dir=None):
    media = {k: bool((media or {}).get(k)) for k in paths.MEDIA_KINDS}
    if not any(media.values()):
        return "none_on"
    if _library_busy():
        return "busy"
    chosen = {}
    for kind, value in (("subs", subs_dir), ("books", books_dir), ("manga", manga_dir), ("custom", custom_dir)):
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
    err = set_folders(chosen.get("subs"), chosen.get("books"), chosen.get("manga"), chosen.get("custom"))
    if err:
        return err
    def change(cfg):
        for key in paths.MEDIA_DIR_LIST_KEYS.values():
            cfg.setdefault(key, [])
        cfg.pop("check_asked", None)
    paths.update_config(change)
    err = set_media(media)
    if not err:
        _forget_last_run()
        _forget_check()
    return err


CHECK_ASKED = "2.0"


def check_asked():
    return paths.load_config().get("check_asked") == CHECK_ASKED


def mark_check_asked():
    def change(cfg):
        if cfg.get("check_asked") == CHECK_ASKED:
            return False
        cfg["check_asked"] = CHECK_ASKED
    paths.update_config(change)


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
    for name in ("analysis.json", "analysis.view.jsonl", "analysis.db"):
        _remove_retrying(os.path.join(folder, name))


_DB_NAMES = paths.DB_NAMES
_DB_SIDECARS = ("", "-wal", "-shm", "-journal")
_DB_OF_MEDIA = {"subs": "subs.db", "books": "epub.db", "manga": "manga.db", "custom": "custom.db"}


_DB_COMPANION_DBS = paths.DB_COMPANION_DBS
_DB_COMPANIONS = paths.DB_COMPANIONS


def _db_files(folder):
    if not os.path.isdir(folder):
        return []
    found = [n for n in os.listdir(folder) if n not in paths.COMPANION_FOLDERS and paths.beside_db(n)]
    for group in paths.COMPANION_FOLDERS:
        directory = Path(folder) / group
        if not directory.is_dir() or paths.companion_link(directory):
            continue
        for child in directory.iterdir():
            try:
                owned = paths.companion_folder(child.name) == group
            except ValueError:
                owned = False
            if owned and paths.beside_db(child.name) and not paths.companion_link(child):
                found.append(os.path.join(group, child.name))
    return sorted(found)


def _entry_size(path):
    if os.path.isdir(path):
        return sum(os.path.getsize(os.path.join(root, n)) for root, _, names in os.walk(path) for n in names)
    return os.path.getsize(path)


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
    from aobana.indexing.run_control import writer_active
    if any(writer_active(os.path.join(src, name)) for name in paths.DB_NAMES + paths.DB_COMPANION_DBS):
        return 'busy', None
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
    total = sum(_entry_size(os.path.join(src, n)) for n in files)
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
        _MOVE["total"] = sum(_entry_size(os.path.join(src, n)) for n in files)

    renamed, copied = [], []
    try:
        for name in files:
            s, d = os.path.join(src, name), os.path.join(dest, name)
            os.makedirs(os.path.dirname(d), exist_ok=True)
            size = _entry_size(s)
            try:
                os.replace(s, d)
                renamed.append(name)
                with _LOCK:
                    _MOVE["done"] += size
                continue
            except OSError:
                pass
            tmp = d + ".moving"
            if os.path.isdir(s):
                shutil.copytree(s, tmp, copy_function=_copy_counting)
            else:
                _copy_counting(s, tmp)
            if _entry_size(tmp) != size:
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
                _remove_retrying(os.path.join(dest, name))
            except OSError:
                pass
        for name in files:
            try:
                _remove_retrying(os.path.join(dest, name + ".moving"))
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
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
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
    cpus = paths.usable_cpus()
    rec = paths.recommended_workers()
    return {"cpus": cpus, "recommended": rec, "workers": paths.search_workers(),
            "saved_workers": count if type(count) is int else None}


def set_search_workers(count):
    if count != "auto":
        if (not isinstance(count, (str, int)) or isinstance(count, bool)
                or not str(count).strip().isdigit()):
            return "bad_search_workers"
        count = int(str(count).strip())
        if not 1 <= count <= paths.usable_cpus():
            return "bad_search_workers"

    def change(cfg):
        cfg.pop("search_worker_delay", None)
        if count == "auto":
            cfg.pop("search_workers", None)
        else:
            cfg["search_workers"] = count
    return paths.update_config(change)


def set_subtitle_tags(value):
    if not isinstance(value, bool):
        return "bad_subtitle_tags"

    def change(cfg):
        if value:
            cfg.pop("subtitle_tags", None)
        else:
            cfg["subtitle_tags"] = False
    return paths.update_config(change)


def _custom_trim_pending():
    db = paths.custom_db()
    if not os.path.isfile(db):
        return 0
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=.05)
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(sources)")}
            if "kind" not in cols:
                return 0
            trim, done = paths.custom_trim(), "trimmed" if "trimmed" in cols else "NULL"
            return sum(trim_outdated(kind, was, trim) for kind, was in conn.execute(
                f"SELECT kind, {done} FROM sources WHERE kind IN ('txt', 'md')"))
        finally:
            conn.close()
    except sqlite3.Error:
        return 0


def _custom_ruby_pending():
    db = paths.custom_db()
    if not os.path.isfile(db):
        return 0
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=.05)
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(sources)")}
            if "kind" not in cols:
                return 0
            on, done = paths.custom_ruby(), "ruby" if "ruby" in cols else "NULL"
            return sum(ruby_outdated(kind, was, on) for kind, was in conn.execute(
                f"SELECT kind, {done} FROM sources WHERE kind IN ('txt', 'md')"))
        finally:
            conn.close()
    except sqlite3.Error:
        return 0


def set_custom_ruby(value):
    if not isinstance(value, bool):
        return "bad_custom_ruby"
    if _library_busy():
        return "busy"

    def change(cfg):
        if value:
            cfg.pop("custom_ruby", None)
        else:
            cfg["custom_ruby"] = False
    return paths.update_config(change)


def set_custom_trim(value):
    if not isinstance(value, bool):
        return "bad_custom_trim"
    if _library_busy():
        return "busy"

    def change(cfg):
        if value:
            cfg.pop("custom_trim", None)
        else:
            cfg["custom_trim"] = False
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


def open_folder(which, index=0):
    target = {"subs": paths.subs_dir, "books": paths.books_dir, "manga": paths.manga_dir,
              "custom": paths.custom_dir, "data": paths.db_dir}.get(which)
    if target is None:
        return "unknown"
    if which == 'data':
        path = target()
    else:
        roots = paths.media_roots(which)
        if type(index) is not int or not 0 <= index < len(roots):
            return 'not_found'
        path = roots[index]
    if not path or not os.path.isdir(path):
        return "not_found"
    return _os_open(path)


def _reveal_target(media, folder, file, dbs, db_epub=None, db_manga=None):
    from aobana.utils import media_connections
    dbs = media_connections(dbs, db_epub, db_manga)
    db_subs = dbs.get("subs")
    db_epub = dbs.get("epub")
    db_manga = dbs.get("manga")
    split = lambda rel: re.split(r"[\\/]", rel)
    if media == "subs" and db_subs is not None:
        root = paths.roots_value('subs')
        if file:
            got = db_subs.execute("SELECT relpath FROM sources WHERE relpath = ?", (file,)).fetchone()
            return (split(got[0]), True, root) if got else (None, "not_indexed", None)
        from aobana.search.engine import folder_prefix_where
        where, params = folder_prefix_where("relpath", folder)
        rels = [r[0] for r in db_subs.execute(f"SELECT relpath FROM sources WHERE {where}", params)]
        if rels:
            return _shared_folder([split(r)[:-1] for r in rels]) or [folder], False, root
        got = db_subs.execute("SELECT relpath FROM sources WHERE relpath = ?", (folder,)).fetchone()
        return (split(got[0]), True, root) if got else (None, "not_indexed", None)
    if media == "epub" and db_epub is not None:
        root = paths.roots_value('epub')
        if file:
            from aobana import utils
            table = "chapters" if utils.has_chapters(db_epub) else "epubs"
            got = db_epub.execute(
                f"SELECT s.relpath FROM {table} c JOIN sources s ON s.id = c.source_id WHERE c.file = ? LIMIT 1",
                (file,)).fetchone()
        else:
            got = db_epub.execute(
                "SELECT relpath FROM sources WHERE title = ? OR (title = '' AND relpath IN (?, ?)) "
                "ORDER BY relpath LIMIT 1", (folder, folder + ".epub", folder + ".EPUB")).fetchone()
        return (split(got[0]), True, root) if got else (None, "not_indexed", None)
    if media == "manga" and db_manga is not None:
        root = paths.roots_value('manga')
        if file:
            got = db_manga.execute("SELECT relpath FROM sources WHERE title || char(92) || volume = ? LIMIT 1",
                                   (file,)).fetchone()
            return (split(got[0]), True, root) if got else (None, "not_indexed", None)
        rels = [r[0] for r in db_manga.execute("SELECT relpath FROM sources WHERE title = ?", (folder,))]
        return (_shared_folder([split(r)[:-1] for r in rels]), False, root) if rels else (None, "not_indexed", None)
    if media == 'custom' and dbs.get('custom') is not None:
        conn = dbs['custom']
        if file:
            got = conn.execute('SELECT relpath FROM sources WHERE replace(relpath, char(92), ?) = ? LIMIT 1',
                               ('/', name_key(file))).fetchone()
            return (split(got[0]), True, paths.roots_value('custom')) if got else (None, 'not_indexed', None)
        metadata = conn.execute('SELECT 1 FROM sqlite_master WHERE name = ?', ('custom_source_meta',)).fetchone()
        sql = ('SELECT s.relpath, s.category, COALESCE(m.path, s.relpath), m.paired_folder FROM sources s '
               'LEFT JOIN custom_source_meta m ON m.relpath = s.relpath ORDER BY s.relpath') if metadata else (
               'SELECT relpath, category, relpath, NULL FROM sources ORDER BY relpath')
        scoped = [row for row in conn.execute(sql)
                  if row[1] == folder or name_key(row[2]).startswith(name_key(folder) + '/')]
        children = [row for row in scoped if row[3] != folder]
        rels = children or scoped
        return (_shared_folder([split(row[0])[:-1] for row in rels]), False, paths.roots_value('custom')) if rels else (None, 'not_indexed', None)
    return None, "unknown", None


def _shared_folder(dirs):
    shared = list(dirs[0]) if dirs else []
    for d in dirs[1:]:
        n = 0
        while n < len(shared) and n < len(d) and shared[n] == d[n]:
            n += 1
        del shared[n:]
    return shared


def reveal(media, folder, file, dbs, db_epub=None, db_manga=None):
    if not (folder or file):
        return "unknown"
    from aobana.utils import media_connections
    dbs = media_connections(dbs, db_epub, db_manga)
    parts, select, root = _reveal_target(media, folder, file, dbs)
    if parts is None:
        return select
    if any(part in ('.', '..') for part in parts) or any(os.path.isabs(part) for part in parts):
        return 'outside'
    target = paths.resolve_media_path(media, '/'.join(parts), file_only=select) if parts else next(
        (folder for folder in paths.root_list(root) if os.path.isdir(folder)), None)
    if not target:
        return 'not_found'
    if not (os.path.isfile(target) if select else os.path.isdir(target)):
        return "not_found"
    return _os_reveal(target) if select else _os_open(target)


def reveal_check(media, path):
    if any(part in ('.', '..') for part in name_key(path).split('/')) or os.path.isabs(path):
        return "outside"
    target = paths.resolve_media_path(media, path) if media in _DISK_MEDIA else None
    if not target or not os.path.isfile(target):
        return "not_found"
    return _os_reveal(target)


def _os_reveal(path):
    try:
        if sys.platform == "win32":
            threading.Thread(target=_reveal_windows, args=(path,), daemon=True).start()
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            return _os_open(os.path.dirname(path))
    except Exception as e:
        return f"failed:{e}"
    return None


_REVEAL_PS = r"""
$dir = $env:AOBANA_REVEAL_DIR; $name = $env:AOBANA_REVEAL_NAME
$sh = New-Object -ComObject Shell.Application
function Find {
  foreach ($w in @($sh.Windows())) { try { if ($w.Document.Folder.Self.Path -eq $dir) { return $w } } catch {} }
}
$w = Find
$new = -not $w
if ($new) {
  Start-Process -FilePath (Join-Path $env:WINDIR 'explorer.exe') -ArgumentList ('/select,"' + (Join-Path $dir $name) + '"')
  for ($i = 0; $i -lt 50 -and -not $w; $i++) { Start-Sleep -Milliseconds 150; $w = Find }
  if (-not $w) { exit 1 }
  for ($i = 0; $i -lt 30; $i++) {
    try { if (@($w.Document.SelectedItems() | ForEach-Object { $_.Name }) -contains $name) { break } } catch {}
    Start-Sleep -Milliseconds 150
  }
  Start-Sleep -Milliseconds 300
}
$it = $w.Document.Folder.ParseName($name)
if ($it) { $w.Document.SelectItem($it, 29) }
[Console]::Out.WriteLine($w.HWND); [Console]::Out.Flush()
if ($new -and $it) { Start-Sleep -Milliseconds 700; $w.Document.SelectItem($it, 29) }
"""


def _reveal_windows(path):
    import base64

    env = dict(os.environ, AOBANA_REVEAL_DIR=os.path.dirname(path), AOBANA_REVEAL_NAME=os.path.basename(path))
    try:
        proc = subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                 "-EncodedCommand", base64.b64encode(_REVEAL_PS.encode("utf-16-le")).decode()], env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        before = {hwnd for hwnd, _ in _windows_explorer_windows()}
        explorer = os.path.join(os.environ.get("WINDIR", os.environ.get("SystemRoot", "")), "explorer.exe")
        subprocess.Popen(f'"{explorer}" /select,"{path}"')
        _bring_windows_folder_forward(os.path.dirname(path), before)
        return
    out = proc.stdout.readline().strip()
    hwnd = int(out) if out.isdigit() else 0
    if hwnd:
        _raise_window(hwnd)
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()


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


def _raise_window(hwnd):
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.ShowWindow(hwnd, 9)
    user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x43)
    user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x03)
    user32.SetForegroundWindow(hwnd)


def _bring_windows_folder_forward(path, before):
    import time

    name = os.path.basename(os.path.normpath(path)).casefold()
    for _ in range(20):
        windows = _windows_explorer_windows()
        new = [hwnd for hwnd, _ in windows if hwnd not in before]
        old_match = [hwnd for hwnd, title in windows if title.casefold() == name]
        if new or (_ >= 9 and old_match):
            _raise_window(new[0] if new else old_match[0])
            return
        time.sleep(0.1)


def _os_open(path):
    try:
        if sys.platform == "win32":
            before = {hwnd for hwnd, _ in _windows_explorer_windows()}
            explorer = os.path.join(os.environ.get("WINDIR", os.environ.get("SystemRoot", "")), "explorer.exe")
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


def manga_page_location(db_manga, rowid):
    if db_manga is None:
        return None
    try:
        rowid = int(rowid)
    except (TypeError, ValueError, OverflowError):
        return None
    got = db_manga.execute(
        "SELECT m.source_id, p.page FROM manga m JOIN manga_pages p ON p.rowid = m.rowid "
        "WHERE m.rowid = ?", (rowid,)).fetchone()
    return (got[0], got[1]) if got else None


_MOKURO_PAGES = {}


def _mokuro_pages(db_manga, source_id):
    if db_manga is None:
        return None, []
    got = db_manga.execute("SELECT relpath FROM sources WHERE id = ?", (source_id,)).fetchone()
    if not got:
        return None, []
    mokuro = paths.resolve_media_path('manga', got[0])
    if not mokuro or not os.path.isfile(mokuro):
        return None, []
    try:
        key = (mokuro, os.path.getmtime(mokuro))
        if key not in _MOKURO_PAGES:
            with open(mokuro, encoding="utf-8") as fh:
                pages = json.load(fh).get("pages") or []
            if len(_MOKURO_PAGES) >= 3:
                _MOKURO_PAGES.pop(next(iter(_MOKURO_PAGES)))
            _MOKURO_PAGES[key] = pages
        return mokuro, _MOKURO_PAGES[key]
    except (OSError, ValueError, AttributeError):
        return None, []


def manga_volume_image_path(db_manga, source_id, page):
    mokuro, pages = _mokuro_pages(db_manga, source_id)
    try:
        img = pages[page - 1].get("img_path") if 1 <= page <= len(pages) else None
    except AttributeError:
        return None
    if not mokuro or not img:
        return None
    folder = mokuro[:-len(".mokuro")] if mokuro.lower().endswith(".mokuro") else mokuro
    image = os.path.realpath(os.path.join(folder, img))
    roots = [os.path.realpath(root) for root in paths.media_roots('manga')]
    if any(_inside(mokuro, root) and _inside(image, root) for root in roots) and os.path.isfile(image):
        return image
    return None


def manga_page_image_path(db_manga, rowid):
    where = manga_page_location(db_manga, rowid)
    return manga_volume_image_path(db_manga, *where) if where else None


def manga_page_neighbours(db_manga, source_id, page):
    got = db_manga.execute("SELECT title, volume FROM sources WHERE id = ?", (source_id,)).fetchone() \
        if db_manga is not None else None
    if not got:
        return None
    series, volume = got[0], got[1]
    pages = len(_mokuro_pages(db_manga, source_id)[1])
    if not 1 <= page <= max(pages, 1):
        return None
    order = [r[0] for r in db_manga.execute(
        "SELECT id FROM sources WHERE title = ? ORDER BY relpath ASC", (series,))]
    at = order.index(source_id)
    nxt = prev = None
    if page < pages:
        nxt = (source_id, page + 1)
    elif at + 1 < len(order):
        nxt = (order[at + 1], 1)
    if page > 1:
        prev = (source_id, page - 1)
    elif at > 0:
        last = len(_mokuro_pages(db_manga, order[at - 1])[1])
        prev = (order[at - 1], max(last, 1))
    return {"series": series, "volume": volume, "page": page, "pages": pages,
            "next": nxt, "prev": prev}


def _index_remaining(s):
    since, first = s.get('rate_from') or (None, 0)
    done, total = s.get('done') or 0, s.get('total') or 0
    if since is None or not total or done >= total or done - first < 3 or time.time() - since < 5:
        return None
    return round((time.time() - since) * (total - done) / (done - first), 1)


def index_status():
    with _LOCK:
        out = {k: (list(v) if isinstance(v, list) else v) for k, v in _STATE.items()}
    if out.get('running'):
        out['elapsed'] = time.time() - out.get('started_at', time.time())
        out['remaining'] = _index_remaining(out)
    if not out.get("running"):
        out["unfinished"] = _unfinished()
        if paths.companion_errors() and not out.get('error'):
            out['error'] = paths.companion_errors()[0]['error']
        if str(out.get('error', '')).startswith('companion_'):
            out['folder_errors'] = paths.companion_errors()
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
        needed = _read_table_needs()
        media = paths.media_state()
        stages = tuple(st for st in _STAGES if needed[st[0]] and media[_STAGE_MEDIA[st[0]]]
                       and not _has_outdated(st[0]))
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
        root, kind, db = _stage_inputs(stage)
        return os.path.isfile(db) or (not tables and _has_files(root, kind))
    stages = tuple(st for st in stages if wanted(st[0]))
    if not stages:
        return "nothing"
    if not tables:
        outdated = bool(outdated) or any(_has_outdated(st) for st, _ in stages)
    from aobana.indexing.run_control import writer_active
    if any(writer_active(_stage_inputs(stage)[2]) for stage, _ in stages):
        return False
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
            "run_id": uuid.uuid4().hex, "prepared_done": 0, "committed_done": 0,
            "phase_done": 0, "phase_total": 0, "elapsed": 0, "remaining": None,
            "running": True, "stage": stages[0][0], "stages": [st[0] for st in stages],
            "done": 0, "total": 0, "current": "",
            "started_at": time.time(), "finished_at": None, "error": None,
            "results": {}, "skipped_clash": [], "failed": [], "ignored_other": {}, "filtered": {},
            "root_missing": [], "root_not_set": [], "log": [], "stopping": False, "stopped": False,
            "outdated": bool(outdated), "tables": bool(tables), "phase": "", "removal_held": {},
            "allow_removal": bool(allow_removal), "json_unsupported": 0,
        })
    _clear_stop("index")
    try:
        with open(_run_marker(), "w", encoding="utf-8") as fh:
            json.dump({"run_id": _STATE["run_id"], "started_at": time.time(), "stages": [st[0] for st in stages],
                       "outdated": bool(outdated), "tables": bool(tables)}, fh)
    except OSError:
        pass
    threading.Thread(target=_run, args=(stages, outdated, tables, allow_removal), daemon=True).start()
    return True


def _set(**kw):
    with _LOCK:
        _STATE.update(kw)


def _child_cmd(module, args=()):
    source_bootstrap = ("import runpy, sys, os; "
                        f"sys.path.insert(0, {paths.BASE_DIR!r}); "
                        "os.environ['AOBANA_RUN_CHILD'] = '1'; "
                        f"os.environ['AOBANA_FLAT_COMPANION_ROOTS'] = {json.dumps(sorted(paths._FLAT_COMPANION_ROOTS))!r}; "
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
    if not text.strip():
        return
    state["log"].append(text)
    del state["log"][:-200]


def _clear_stale_for_rebuild():
    from aobana.search import result_cache
    result_cache.clear_disk_cache()
    for name in ("media_cache.json", "library_summary.json", "library_figures.json", "estimate.json"):
        try:
            os.remove(_beside_db(name))
        except OSError:
            pass
    logs = paths.logs_dir()
    for entry in (os.listdir(logs) if os.path.isdir(logs) else []):
        p = os.path.join(logs, entry)
        try:
            shutil.rmtree(p) if os.path.isdir(p) and not os.path.islink(p) else os.remove(p)
        except OSError:
            pass
    with _LOCK:
        _log(_STATE, "REBUILD: saved searches, library summaries and logs/ cleared")


def _search_reset():
    try:
        from aobana.search.engine import reset_caches
        reset_caches()
    except Exception:
        pass


def _search_index_run(running):
    try:
        from aobana.search.engine import index_run
        index_run(running)
    except Exception:
        pass


def _run(stages, outdated=False, tables=False, allow_removal=False):
    _release_handles()
    if not _STATE.get('run_id'):
        _set(run_id=uuid.uuid4().hex)
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1",
               AOBANA_STOP_FILE=_stop_file("index"), AOBANA_RUN_ID=_STATE["run_id"])
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    cleared = False
    _search_index_run(True)
    try:
        for stage, script in stages:
            _set(stage=stage, done=0, total=0, current="", phase="", rate_from=None)
            from aobana.indexing import rebuild as rebuilding
            media, db = _stage_inputs(stage)[1:]
            rebuild = not tables and rebuilding.wanted(db, media)
            if rebuild:
                _release_handles()
                rebuilding.drop_old(db)
                if media == "subs":
                    from aobana.indexing import pending_reindex
                    try:
                        os.remove(pending_reindex.state_path())
                    except FileNotFoundError:
                        pass
                if not cleared:
                    cleared = True
                    _clear_stale_for_rebuild()
                with _LOCK:
                    _log(_STATE, f"REBUILD {media}: the old index was deleted; every file is read into a new one")
            args = [JSONL_FLAG] + (["--tables"] if tables else ["--outdated"] if outdated and not rebuild else [])
            if allow_removal and not tables:
                args.append(ALLOW_REMOVAL_FLAG)
            owned = OwnedProcess(_child_cmd(script, args), env, paths.BASE_DIR, _stop_file('index'))
            _set(writer_pid=owned.proc.pid, writer_identity=owned.identity)
            from aobana.indexing.run_control import process_identity
            try:
                with open(_run_marker(), 'w', encoding='utf-8') as marker:
                    json.dump(dict(run_id=_STATE['run_id'], pid=os.getpid(), identity=process_identity(os.getpid()),
                        writer_pid=owned.proc.pid, writer_identity=owned.identity,
                        started_at=_STATE.get('started_at'), outdated=outdated, tables=tables), marker)
            except OSError:
                pass
            try:
                code = _pump(owned.proc, lambda line: _read_line(stage, line))
            except BaseException:
                owned.terminate()
                raise
            finally:
                forced = owned.forced
                owned.close()
            _search_reset()
            if forced:
                _set(stopped=True, forced=True, phase='rollback')
            if code != 0:
                _set(error=f"{script} exited with code {code}")
                break
            if _STATE.get("stopped"):
                break
    except Exception as e:
        _set(error=f"{type(e).__name__}: {e}")
    finally:
        _search_reset()
        _search_index_run(False)
        _set(running=False, stopping=False, stage="done", current="", finished_at=time.time())
        _clear_stop("index")
        invalidate_summaries()
        invalidate_inventory()
        _FIG_STALE["stale"] = True
        seconds = time.time() - (_STATE.get("started_at") or time.time())
        if seconds > LONG_TASK_SECONDS:
            _add_notice("index", seconds, stopped=bool(_STATE.get("stopped")), error=_STATE.get("error"))
        try:
            if not _STATE.get('forced') and not _STATE.get('error'):
                from pathlib import Path
                for marker in Path(paths.companion('.index-runs')).parent.glob('.index_run-*.json'):
                    try:
                        doc = json.loads(marker.read_text(encoding='utf-8'))
                        from aobana.indexing.run_control import process_identity
                        if (doc.get('run_id') == _STATE.get('run_id') or
                                not doc.get('pid') or process_identity(doc['pid']) != doc.get('identity')):
                            marker.unlink()
                    except (OSError, ValueError):
                        pass
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
    if kind not in ("progress", "heartbeat", "total") and isinstance(ev.get("text"), str):
        _log(_STATE, ev["text"])
    if kind == 'heartbeat':
        if ev.get('run_id') == _STATE.get('run_id'):
            _STATE.update({k: ev[k] for k in ('phase','phase_done','phase_total','prepared_done',
                'committed_done','elapsed','remaining') if k in ev})
    elif kind == "total":
        _STATE.update(total=int(ev["total"]), phase="")
    elif kind == "phase":
        if "done" in ev:
            _STATE.update(phase=str(ev["phase"]), done=int(ev["done"]), total=int(ev["total"]))
        else:
            _STATE.update(phase=str(ev["phase"]), done=0, total=0, current="")
    elif kind == "progress":
        done = int(ev["done"])
        if not _STATE.get("rate_from") or done < _STATE["rate_from"][1]:
            _STATE["rate_from"] = (time.time(), done)
        _STATE.update(done=done, total=int(ev["total"]), current=str(ev["file"]))
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
    elif kind == "json_unsupported":
        _STATE["json_unsupported"] = int(ev["count"])
    elif kind == "summary":
        _STATE["results"][stage] = {"unchanged": int(ev["unchanged"]), "indexed": int(ev["indexed"]),
                                    "removed": int(ev["removed"])}


_ASTATE = {"running": False}
FILTERABLE = ("bilingual", "other_language", "language_review", "image_only", "drm", "garbled", "unreadable", "unsupported", "html_error", "no_japanese", "empty_or_wall")


def analysis_status():
    with _LOCK:
        return {k: (list(v) if isinstance(v, list) else v) for k, v in _ASTATE.items()}


def start_analysis(only=None):
    if only == "manga" and len(paths.media_roots(only)) <= 1:
        return False
    media = paths.media_state()
    on = [m for m in ('subs', 'epub', 'manga', 'custom')
          if media[_STAGE_MEDIA[m]] and (m in ('subs', 'epub', 'custom') or len(paths.media_roots(m)) > 1)]
    if only in ("subs", "epub", "manga", "custom"):
        if only not in on:
            return False
    elif not on:
        return False
    else:
        only = on[0] if len(on) == 1 else None
    with _LOCK:
        if _ASTATE.get("running") or _STATE.get("running") or _STATE.get("moving"):
            return False
        _ASTATE.clear()
        _ASTATE.update(running=True, stage="subs" if only != "epub" else "epub", done=0, total=0,
                       current="", started_at=time.time(), finished_at=None, error=None, log=[],
                       stopping=False, stopped=False)
    _clear_stop("check")
    _save_analysis_attempt()
    mark_check_asked()
    threading.Thread(target=_run_analysis, args=(only,), daemon=True).start()
    return True


def _read_analysis_line(line):
    ev = _event(line)
    persist = False
    with _LOCK:
        try:
            kind = ev["type"]
            if kind == "check_phase":
                persist = (_ASTATE.get('phase') != ev.get('phase') or
                           time.monotonic()-_ASTATE.get('_saved_at',0) >= 2)
                _ASTATE.update({k:ev[k] for k in ('stage','phase','done','total','elapsed','phase_elapsed',
                    'remaining','workers','cached','files','current') if k in ev})
                if persist:
                    _ASTATE['_saved_at'] = time.monotonic()
            elif kind == "progress":
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
    if persist:
        _save_analysis_attempt()


def _run_analysis(only, keep_running=False):
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
        invalidate_inventory()
        invalidate_summaries()
        if not keep_running:
            with _LOCK:
                _ASTATE.update(running=False, stopping=False, current="", finished_at=time.time())
            _save_analysis_attempt()
            _clear_stop("check")
        seconds = time.time() - (_ASTATE.get("started_at") or time.time())
        if not keep_running and seconds > LONG_TASK_SECONDS:
            _add_notice("check", seconds, stopped=bool(_ASTATE.get("stopped")), error=_ASTATE.get("error"))


def _report_path():
    return paths.companion('analysis.json')


def _save_analysis_attempt():
    path = _beside_db('analysis-attempt.json')
    with _LOCK:
        state = {k: _ASTATE.get(k) for k in ('running', 'stopped', 'started_at', 'finished_at', 'stage',
            'phase','done','total','elapsed','phase_elapsed','remaining','workers','cached','files','error','encoding_results')}
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + '.tmp', 'w', encoding='utf-8') as out:
            json.dump(state, out)
        os.replace(path + '.tmp', path)
    except OSError:
        pass


def analysis_report():
    try:
        with open(_report_path(), encoding="utf-8") as fh:
            raw = fh.read()
            report = json.loads(raw)
        report['selection_generation'] = report.get('generation') or 'legacy-' + hashlib.sha256(raw.encode('utf-8')).hexdigest()
        saved = {(r['media'], name_key(r['name'])):r for r in filtered_rows(paths.filtered_list())}
        for item in report.get('items', []):
            item['filtered'] = (item['media'],name_key(item['name'])) in saved
        for group in report.get('groups', []):
            for member in group['members']:
                member['saved'] = saved.get((group['media'], name_key(member['name'])))
        report['recheck'] = [i for i in report.get('recheck', [])
                             if (row := saved.get((i['media'], i['name']))) and row['reason'] == i['saved']
                             and row.get('reviewed') != i['mark']]
        if report.get('repair', {}).get('items'):
            report['repair']['items'] = _repair_still_due(report['repair']['items'], saved)
        from aobana.indexing import pending_reindex
        try:
            queued = pending_reindex.load()['items']
            report['pending_refresh'] = len(queued)
            report['pending_items'] = [dict(name=i['name'], reason=i.get('reason', '')) for i in queued]
        except (OSError,ValueError):
            report['pending_refresh_error'] = True
        try:
            with open(_beside_db('analysis-attempt.json'), encoding='utf-8') as attempt:
                report['last_attempt'] = json.load(attempt)
        except (OSError, ValueError):
            pass
        return report
    except (OSError, ValueError):
        return None


def has_report():
    return os.path.isfile(_report_path())


def view_path():
    return _beside_db('analysis.view.jsonl')


def replace_retrying(tmp, path):
    for attempt in range(60):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 59:
                raise
            time.sleep(0.5)


def needs_exclusion(group, member, keeper):
    saved = member.get('saved')
    return member['name'] != keeper and (not saved or saved['reason'] == 'duplicate' and saved.get('keep') != keeper)


_VIEW = {'key': None, 'header': None}
_VIEW_LOCK = threading.Lock()
_AN_MEDIA = ('subs', 'epub', 'manga', 'custom')


def _view_key():
    from aobana.indexing import pending_reindex
    db = paths.subs_db()
    return json.loads(json.dumps([_identity(p) for p in (_report_path(), paths.filtered_list(),
                                                         str(pending_reindex.state_path()), db, db + '-wal')]))


def _view_token(key):
    return hashlib.sha256(json.dumps(key).encode('utf-8')).hexdigest()[:16]


def check_view():
    from aobana.server import check_view as view
    with _VIEW_LOCK:
        for _ in range(3):
            key = _view_key()
            if _VIEW['key'] == key:
                return _VIEW['header']
            if not has_report():
                _VIEW.update(key=key, header=None)
                return None
            try:
                header = view.read_header(view_path())
            except (OSError, ValueError):
                header = None
            if not header or header.get('key') != key:
                flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                try:
                    out = subprocess.run(_child_cmd('aobana.server.check_view', ['--view', json.dumps(key)]),
                                         cwd=paths.BASE_DIR, capture_output=True, encoding='utf-8', errors='replace',
                                         timeout=900, creationflags=flags, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
                except (OSError, subprocess.SubprocessError) as error:
                    raise RuntimeError(f'{type(error).__name__}: {error}') from error
                if out.returncode != 0:
                    raise RuntimeError((out.stdout.strip().splitlines() or [f'exit {out.returncode}'])[-1])
                try:
                    header = view.read_header(view_path())
                except (OSError, ValueError) as error:
                    raise RuntimeError(f'{type(error).__name__}: {error}') from error
            if header.get('key') == key == _view_key():
                header['token'] = _view_token(key)
                _VIEW.update(key=key, header=header)
                return header
        raise RuntimeError('the check results kept changing while they were read')


def _view_parts(header, name, media_on):
    if not header:
        return []
    if name in ('pending', 'reindex'):
        keys = [name] if 'subs' in media_on else []
    elif name in ('recheck', 'recheck-dups'):
        keys = [f'{name}:{media}' for media in _AN_MEDIA if media in media_on]
    elif name.startswith(('find:', 'dup:')) and name.split(':')[1] in media_on:
        keys = [name]
    else:
        keys = []
    return [header['sections'][k] for k in keys if k in header['sections']]


def view_section_rows(header, name):
    from aobana.server import check_view as view
    section = (header or {}).get('sections', {}).get(name)
    return view.read_rows(view_path(), section, 0, section['count']) if section else []


def _rechecked(header, media_on):
    return {k for name in ('recheck', 'recheck-dups') for part in _view_parts(header, name, media_on)
            for k in part.get('keys', [])}


_SAVED = {'key': None, 'sections': {}}


def _saved_sections():
    inventory = (_identity(paths.filtered_list()), json.dumps(_figures_key()))
    with _LOCK:
        key = (inventory, _INVENTORY['key'] == inventory, _INVENTORY['generation'])
        if _SAVED['key'] == key:
            return _SAVED['sections']
    sections = {}
    for row in filtered_list():
        sections.setdefault(f"saved:{row['media']}:{row['reason']}", []).append(row)
    with _LOCK:
        _SAVED.update(key=key, sections=sections)
    return sections


def _saved_rows(name, rechecked):
    rows = _saved_sections().get(name, [])
    return [r for r in rows if f"{r['media']}\t{r['name']}" not in rechecked] if rechecked else rows


def analysis_summary(media_on):
    header = check_view()
    token = _view_token(_VIEW['key'])
    report = None
    if header and header.get('report'):
        report = dict(header['report'], sections={})
        names = ['pending', 'reindex', 'recheck-dups', 'recheck'] + [k for k in header['sections'] if k.startswith(('find:', 'dup:'))]
        for name in names:
            parts = _view_parts(header, name, media_on)
            count = sum(p['count'] for p in parts)
            if not count:
                continue
            entry = {'count': count}
            for field in ('ids', 'keys', 'groups'):
                if any(field in p for p in parts):
                    entry[field] = [x for p in parts for x in p.get(field, [])]
            if any('size' in p for p in parts):
                entry['size'] = sum(p.get('size', 0) for p in parts)
            report['sections'][name] = entry
        try:
            with open(_beside_db('analysis-attempt.json'), encoding='utf-8') as attempt:
                report['last_attempt'] = json.load(attempt)
        except (OSError, ValueError):
            pass
    rechecked = _rechecked(header, media_on)
    saved, total = [], 0
    for name in _saved_sections():
        n = len(_saved_rows(name, rechecked))
        total += n
        if n:
            saved.append({'key': name, 'media': name.split(':')[1], 'reason': name.split(':', 2)[2], 'count': n})
    return {'report': report, 'filtered': {'count': total, 'sections': saved}, 'view': token}


def _current_header(token):
    key = _view_key()
    with _VIEW_LOCK:
        if _VIEW['key'] != key or _view_token(key) != token:
            return False, None
        return True, _VIEW['header']


def analysis_page(name, start, media_on, token, size=200):
    from aobana.server import check_view as view
    current, header = _current_header(token)
    if not current:
        return None
    if name.startswith('saved:'):
        return _saved_rows(name, _rechecked(header, media_on))[start:start + size]
    out = []
    for part in _view_parts(header, name, media_on):
        if start >= part['count']:
            start -= part['count']
            continue
        out += view.read_rows(view_path(), part, start, size - len(out))
        start = 0
        if len(out) >= size:
            break
    return out


def analysis_keys(name, media_on, token):
    current, header = _current_header(token)
    if not current or not name.startswith('saved:'):
        return None
    return [f"{r['media']}\t{r['name']}" for r in _saved_rows(name, _rechecked(header, media_on))]


def _repair_still_due(items, saved):
    from contextlib import closing
    db = paths.subs_db()
    if not os.path.isfile(db):
        return []
    names = json.dumps([i['name'] for i in items], ensure_ascii=False)
    try:
        with closing(sqlite3.connect(Path(db).resolve().as_uri() + '?mode=ro', uri=True)) as conn:
            now = {r[0]: (r[1], r[2], str(r[3])) for r in conn.execute(
                'SELECT s.relpath, s.id, s.file_hash, s.indexed_at FROM json_each(?) j '
                'JOIN sources s ON s.relpath = j.value', (names,))}
    except sqlite3.Error:
        return items
    seen = {}
    if any('indexed_at' not in i for i in items):
        from aobana.indexing.analyser import cache_path
        try:
            with closing(sqlite3.connect(Path(cache_path()).resolve().as_uri() + '?mode=ro', uri=True)) as cache:
                seen = {r[0]: r[1] for r in cache.execute('SELECT source_id, indexed_at FROM stored')}
        except sqlite3.Error:
            pass
    due = []
    for item in items:
        if ('subs', name_key(item['name'])) in saved:
            continue
        row = now.get(item['name'])
        if row is None or row[:2] != (item.get('source_id'), item.get('indexed_hash')):
            continue
        at = item['indexed_at'] if 'indexed_at' in item else seen.get(item.get('source_id'))
        if at is None or at == row[2]:
            due.append(item)
    return due


def save_subtitle_refresh(doc):
    with _LOCK:
        if _STATE.get('running') or _STATE.get('moving') or _ASTATE.get('running'):
            raise ValueError('busy')
        from aobana.indexing import pending_reindex
        return pending_reindex.save(doc)


def _encoding_backups():
    target = Path(paths.backups_dir('encoding'))
    old = Path(paths.logs_dir()) / 'encoding-backups'
    if old.is_dir():
        for source in sorted(p for p in old.rglob('*') if p.is_file()):
            dest = target / source.relative_to(old)
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                if dest.read_bytes() != source.read_bytes():
                    continue
                source.unlink()
            else:
                shutil.move(str(source), str(dest))
        for folder in sorted((p for p in old.rglob('*') if p.is_dir()), reverse=True):
            try:
                folder.rmdir()
            except OSError:
                pass
        try:
            old.rmdir()
        except OSError:
            pass
    return target


def start_encoding_repair(report):
    left_out = {name_key(r['name']) for r in filtered_rows(paths.filtered_list()) if r.get('media') == 'subs'}
    items = [i for i in report.get('items',[]) if i.get('media')=='subs' and i.get('reason')=='encoding'
             and name_key(i.get('name','')) not in left_out]
    root = report.get('roots',{}).get('subs')
    if not root or not paths.same_roots(root, paths.roots_value('subs')):
        raise ValueError('stale_report')
    with _LOCK:
        if _STATE.get('running') or _STATE.get('moving') or _ASTATE.get('running'):
            raise ValueError('busy')
        _ASTATE.clear()
        _ASTATE.update(running=True,stage='subs',phase='encoding',done=0,total=len(items),current='',
            started_at=time.time(),finished_at=None,error=None,log=[],stopping=False,stopped=False,
            encoding_results=[])
    _clear_stop('check')
    _save_analysis_attempt()
    threading.Thread(target=_run_encoding_repair,args=(root,items,report.get('only')),daemon=True).start()
    return True


# encoding_repair.convert's reasons as the codes the page has a string for (an_encoding_err_<code>);
# they reached the page as these English sentences (audit 10, F56)
_ENCODING_ERRORS = {
    'Invalid encoding repair root': 'moved', 'Invalid encoding repair source': 'moved',
    'Encoding repair source changed': 'changed', 'Encoding repair source changed before replacement': 'changed',
    'read_only': 'read_only', 'Unsupported encoding repair': 'unsupported',
    'Ambiguous CP932 byte mapping': 'ambiguous', 'Damaged subtitle text': 'damaged',
    'Encoding round trip failed': 'round_trip', 'Subtitle content changed during conversion': 'round_trip',
    'Encoding backup differs from source': 'backup_differs',
}


def _encoding_error(error):
    if isinstance(error, FileNotFoundError):
        return 'missing'
    if isinstance(error, OSError):
        return 'write_failed'
    # 'failed': a cause with no string of its own; the row under the heading adds nothing
    return _ENCODING_ERRORS.get(str(error), 'failed') if isinstance(error, ValueError) else 'failed'


def _run_encoding_repair(root,items,only=None):
    from aobana.indexing.encoding_repair import convert
    from aobana.indexing.run_control import WriterLease
    results=[]
    try:
        with WriterLease(paths.subs_db()):
            backups = _encoding_backups()
            for i,item in enumerate(items,1):
                if os.path.exists(_stop_file('check')):
                    with _LOCK: _ASTATE['stopped']=True
                    break
                try:
                    result=convert(root,item,backups)
                except (OSError,ValueError,KeyError) as error:
                    result={'name':item.get('name',''),'status':'failed','error':_encoding_error(error)}
                results.append(result)
                if result['status'] == 'converted':
                    from aobana.indexing import pending_reindex
                    pending_reindex.converted(root,item['name'],item['details']['sha'],result['sha'])
                with _LOCK:
                    _ASTATE.update(done=i,current=item.get('name',''),encoding_results=list(results))
        if not _ASTATE.get('stopped'):
            _run_analysis(only,keep_running=True)
    except Exception as error:
        with _LOCK: _ASTATE['error']=f'{type(error).__name__}: {error}'
    finally:
        with _LOCK:
            _ASTATE.update(running=False,stopping=False,finished_at=time.time(),current='',encoding_results=results)
        _save_analysis_attempt()
        _clear_stop('check')


def _write_filtered(rows):
    path = paths.filtered_list()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\t".join(FILTER_COLUMNS) + "\n")
        for r in rows:
            fh.write("\t".join(str(r.get(c, "")).replace("\t", " ").replace("\n", " ")
                               for c in FILTER_COLUMNS) + "\n")
    for attempt in range(60):
        try:
            os.replace(tmp, path)
            break
        except PermissionError:
            if attempt == 59:
                raise
            time.sleep(0.5)
    invalidate_inventory()
    invalidate_summaries()


def _source_place(media, relative):
    source = paths.resolve_media_path(media, relative) if media in _DISK_MEDIA else None
    root = next((folder for folder in paths.media_roots(media)
                 if source and _inside(source, os.path.realpath(folder))), None) if media in _DISK_MEDIA else None
    if root is None and media in _DISK_MEDIA:
        root = next(iter(paths.media_roots(media)), None)
    return root, source


def _read_filtered_list():
    out = []
    for r in filtered_rows(paths.filtered_list()):
        root, p = _source_place(r['media'], r['name'])
        out.append(_filtered_evidence(dict(r, exists=bool(p) and os.path.isfile(p)), root, p))
    return out


def _language_evidence(item, report, root, source):
    if item.get('reason') not in ('bilingual', 'other_language', 'language_review'):
        return ''
    counts = {k: item.get(k) for k in ('lines', 'ja', 'zh', 'en')}
    if any(type(v) is not int or v < 0 for v in counts.values()):
        return ''
    sha = item.get('details', {}).get('sha') or None
    st = os.stat(source) if sha else None
    return json.dumps(dict(version=1, method='line_kind', measurement_version=item.get('details',{}).get('measurement_version',report.get('version')),
        check_at=report.get('generated_at'), root=os.path.realpath(root), sha=sha,
        size=st.st_size if st else None, mtime=st.st_mtime_ns if st else None, **counts), ensure_ascii=False)


def _filtered_evidence(row, root, source=None):
    row['language_evidence'] = None
    row['evidence_state'] = 'unavailable'
    try:
        evidence = json.loads(row.get('evidence') or 'null')
    except (ValueError, TypeError):
        return row
    if not isinstance(evidence, dict) or any(type(evidence.get(k)) is not int or evidence[k] < 0 for k in ('lines','ja','zh','en')):
        return row
    row['language_evidence'] = evidence
    row['evidence_state'] = 'historical'
    if not root or not _same_folder(root, evidence.get('root') or ''):
        row['evidence_state'] = 'stale'
    elif source and evidence.get('sha'):
        try:
            st = os.stat(source)
            row['evidence_state'] = 'current' if (st.st_size,st.st_mtime_ns) == (evidence.get('size'),evidence.get('mtime')) else 'stale'
        except OSError:
            pass
    return row


def filter_flagged(ids, generation=None, choices=None):
    with _LOCK:
        if _STATE.get("running") or _STATE.get("moving") or _ASTATE.get("running"):
            return "busy", None
        _STATE["moving"] = True
    try:
        from aobana.indexing.apply_choices import apply
        from aobana.indexing.run_control import WriterLease
        from aobana.indexing import repair
        roots = {media: paths.roots_value(media) for media in ('subs', 'epub', 'custom')}
        with WriterLease(paths.filtered_list()):
            report = analysis_report()
            if not report:
                return 'no_report', None
            if generation != report['selection_generation']:
                return 'stale_report', None
            original = filtered_rows(paths.filtered_list())
            choices = _with_exclusions(report, choices)
            with _LOCK:
                _SAVE.update(running=True, done=0, total=len(choices), started=time.time())
            rows = apply(report, roots, original, report.get('generation'), choices, _save_progress) if choices else list(original)
            have = {(r['media'],r['name']) for r in rows}
            id_set = set(ids)
            selected = {i['id']:i for i in report.get('items',[]) if i['id'] in id_set}
            if set(selected) != id_set:
                return 'bad_ids', None
            additions = []
            for item in selected.values():
                media = item['media']; root = roots.get(media)
                if item['reason'] not in FILTERABLE or not root or not paths.same_roots(root,report['roots'].get(media)):
                    return 'stale_roots', None
                root, source = _source_place(media, item['name'])
                if not source:
                    return 'stale_inputs', None
                expected = item.get('details',{}).get('sha')
                if expected and repair.digest(source) != expected:
                    return 'stale_inputs', None
                key = (media,item['name'])
                if key not in have:
                    additions.append(dict(media=media,name=item['name'],reason=item['reason'],keep=item.get('keep',''),
                        date=time.strftime('%Y-%m-%d %H:%M:%S'),origin='manual',
                        evidence=_language_evidence(item,report,root,source)))
                    have.add(key)
            rows += additions
            if rows != original:
                _write_filtered(rows)
            before = {(r['media'],r['name']):r for r in original}
            after = {(r['media'],r['name']):r for r in rows}
            return None, dict(filtered=list(selected),refused=[],saved=sum(before.get(k) != v for k,v in after.items()),
                included=len(set(before)-set(after)))
    except RuntimeError:
        return 'busy', None
    except (ValueError, OSError, KeyError) as error:
        return str(error), None
    finally:
        with _LOCK:
            _STATE.pop("moving", None)
            _SAVE['running'] = False


def _with_exclusions(report, choices):
    groups = {g['id']: g for g in report.get('groups', [])}
    out = []
    for choice in choices:
        group = groups.get(choice.get('group')) if isinstance(choice, dict) else None
        if not group or 'exclude' in choice:
            out.append(choice)
            continue
        members = group['members']
        if choice.get('keep_all') is True:
            if any((m.get('saved') or {}).get('reason') == 'duplicate' for m in members):
                out.append(choice)
            continue
        keeper = choice.get('keeper', group['keeper'])
        exclude = [m['name'] for m in members if needs_exclusion(group, m, keeper)]
        if exclude or any(m['name'] == keeper and (m.get('saved') or {}).get('reason') == 'duplicate' for m in members):
            out.append(dict(choice, exclude=exclude))
    return out


def save_choices(ids, generation, choices):
    with _LOCK:
        if _STATE.get("running") or _STATE.get("moving") or _ASTATE.get("running"):
            return "busy", None
        _STATE["moving"] = True
        _SAVE.update(running=True, done=0, total=len(choices), started=time.time())
    try:
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        result, tail = None, []
        with subprocess.Popen(_child_cmd('aobana.server.check_view', ['--save']), cwd=paths.BASE_DIR,
                              env=dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1'),
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              encoding='utf-8', errors='replace', creationflags=flags) as proc:
            proc.stdin.write(json.dumps(dict(ids=sorted(ids), generation=generation, choices=choices), ensure_ascii=False))
            proc.stdin.close()
            for line in proc.stdout:
                try:
                    message = json.loads(line)
                except ValueError:
                    tail = (tail + [line.strip()])[-5:]
                    continue
                if isinstance(message, dict) and 'progress' in message:
                    _save_progress(*message['progress'])
                elif isinstance(message, dict) and 'result' in message:
                    result = message['result']
        if not result:
            return next((t for t in reversed(tail) if t), f'exit {proc.returncode}'), None
        return result[0], result[1]
    except OSError as error:
        return str(error), None
    finally:
        invalidate_inventory()
        invalidate_summaries()
        with _LOCK:
            _STATE.pop("moving", None)
            _SAVE['running'] = False


_SAVE = {'running': False}


def _save_progress(done, total):
    with _LOCK:
        _SAVE.update(done=done, total=total)


def save_progress():
    with _LOCK:
        out = dict(_SAVE)
    if out.get('started'):
        out['elapsed'] = round(time.time() - out.pop('started'), 1)
    return out


def apply_recommendations(generation, choices):
    from aobana.indexing.apply_choices import apply
    from aobana.indexing.run_control import WriterLease
    with _LOCK:
        if _STATE.get('running') or _STATE.get('moving') or _ASTATE.get('running'):
            return 'busy', None
        _STATE['moving'] = True
    try:
        with WriterLease(paths.filtered_list()):
            report = analysis_report()
            roots = {media: paths.roots_value(media) for media in ('subs', 'epub', 'custom')}
            rows = apply(report, roots, filtered_rows(paths.filtered_list()), generation, choices)
            _write_filtered(rows)
            return None, {'applied': [c['group'] for c in choices]}
    except (ValueError, OSError, KeyError) as error:
        return str(error), None
    finally:
        with _LOCK:
            _STATE.pop('moving', None)


def unfilter(entries):
    with _LOCK:
        if _STATE.get("running") or _STATE.get("moving") or _ASTATE.get("running"):
            return "busy", 0
        _STATE["moving"] = True
    try:
        drop = {(str(m), str(n)) for m, n in entries}
        from aobana.indexing.run_control import WriterLease
        with WriterLease(paths.filtered_list()):
            rows = filtered_rows(paths.filtered_list())
            kept = [r for r in rows if (r["media"], r["name"]) not in drop]
            if len(kept) != len(rows):
                _write_filtered(kept)
            return None, len(rows) - len(kept)
    except RuntimeError:
        return 'busy', 0
    except OSError as error:
        return str(error), 0
    finally:
        with _LOCK:
            _STATE.pop("moving", None)


def keep_left_out(entries):
    with _LOCK:
        if _STATE.get("running") or _STATE.get("moving") or _ASTATE.get("running"):
            return "busy", 0
        _STATE["moving"] = True
    try:
        try:
            header = check_view()
        except RuntimeError as error:
            return str(error), 0
        recheck = [row for name in (header or {}).get('sections', {}) if name.startswith('recheck')
                   for row in view_section_rows(header, name)]
        wanted = {(str(m), str(n)) for m, n in entries}
        found = {(i['media'], i['name']): i for i in recheck if (i['media'], i['name']) in wanted}
        from aobana.indexing.run_control import WriterLease
        with WriterLease(paths.filtered_list()):
            rows = filtered_rows(paths.filtered_list())
            changed = 0
            for r in rows:
                item = found.get((r['media'], r['name']))
                if not item or r['reason'] != item['saved']:
                    continue
                if item['now'] in FILTERABLE:
                    r.update(reason=item['now'], keep='')
                r.update(reviewed=item['mark'], date=time.strftime('%Y-%m-%d %H:%M:%S'))
                changed += 1
            if changed:
                _write_filtered(rows)
            return None, changed
    except RuntimeError:
        return 'busy', 0
    except OSError as error:
        return str(error), 0
    finally:
        with _LOCK:
            _STATE.pop("moving", None)


def estimate(only=None):
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    cmd = _child_cmd("aobana.indexing.analyser", ["--estimate"])
    if only in ("subs", "epub", "manga", "custom"):
        cmd += ["--only", only]
    try:
        out = subprocess.run(cmd, cwd=paths.BASE_DIR, capture_output=True, encoding="utf-8",
                             errors="replace", timeout=300, creationflags=flags,
                             env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        return json.loads(out.stdout.strip().splitlines()[-1])
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


_SUMMARY = {'key': None, 'data': {}, 'running': False, 'generation': 0}
_INVENTORY = {'key': None, 'rows': [], 'running': False, 'generation': 0}

def _identity(path):
    try:
        st = os.stat(path)
        return (os.path.abspath(path), st.st_mtime_ns, st.st_size, st.st_ino)
    except OSError:
        return (os.path.abspath(path), None)

def invalidate_summaries():
    with _LOCK:
        _SUMMARY['key'] = None
        _SUMMARY['generation'] += 1

def invalidate_inventory():
    with _LOCK:
        _INVENTORY['key'] = None
        _INVENTORY['generation'] += 1

def _summary_key():
    return tuple((_identity(_stage_inputs(st)[2]), _identity(_stage_inputs(st)[2]+'-wal')) for st,_ in _STAGES) + (paths.custom_trim(), paths.custom_ruby())

def summaries():
    key = _summary_key()
    db_paths = [os.path.abspath(_stage_inputs(st)[2]) for st,_ in _STAGES]
    from aobana.indexing.run_control import writer_active
    writing = bool(_STATE.get('running')) or any(writer_active(p) for p in db_paths)
    with _LOCK:
        if _SUMMARY.get('paths') != db_paths:
            _SUMMARY.update(data={},key=None,paths=db_paths)
        if not _SUMMARY['data']:
            try:
                with open(_beside_db('library_summary.json'), encoding='utf-8') as f:
                    saved = json.load(f)
                if saved.get('paths') == [os.path.abspath(_stage_inputs(st)[2]) for st,_ in _STAGES]:
                    _SUMMARY['data'] = saved['data']
            except (OSError, ValueError, KeyError):
                pass
        updating = _SUMMARY['key'] != key or writing
        if updating and not _SUMMARY['running'] and not writing:
            _SUMMARY['running'] = True
            threading.Thread(target=_refresh_summary, args=(key, _SUMMARY['generation']), daemon=True).start()
        return dict(_SUMMARY['data'], updating=updating)

def _refresh_summary(key, generation):
    data = {'needs': {st: [] for st,_ in _STAGES}}
    try:
        for st,_ in _STAGES:
            name = 'books' if st == 'epub' else st
            db = _stage_inputs(st)[2]
            if not os.path.isfile(db):
                data[name+'_indexed'] = {'files': 0, 'rows': 0}
                data[name+'_outdated'] = 0
                continue
            conn = sqlite3.connect(f'file:{db}?mode=ro', uri=True, timeout=.05)
            try:
                conn.execute('BEGIN')
                table = {'subs':'subtitles','epub':'epubs','manga':'manga','custom':'custom'}[st]
                if not conn.execute('SELECT 1 FROM sqlite_master WHERE name=?',(table,)).fetchone():
                    data[name+'_indexed'] = {'files': 0, 'rows': 0}
                    data[name+'_outdated'] = 0
                else:
                    data[name+'_indexed'] = {'files':conn.execute('SELECT COUNT(*) FROM sources').fetchone()[0],
                                            'rows':count_rows(conn,table)}
                    if st == 'custom' and conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'custom_skipped'").fetchone():
                        # The files the index left unread, by reason, for the card's lasting line (audit 10, F43)
                        data[name+'_indexed']['skipped'] = dict(conn.execute(
                            'SELECT reason, count(*) FROM custom_skipped GROUP BY reason'))
                    data[name+'_outdated'] = outdated_sources(conn,st)
                    data['needs'][st] = missing_tables(conn,st)
            finally:
                conn.close()
        with _LOCK:
            if key != _summary_key() or generation != _SUMMARY['generation']:
                return
            _SUMMARY.update(key=key, data=data)
        path = _beside_db('library_summary.json')
        tmp = path + f'.{os.getpid()}.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(dict(paths=[os.path.abspath(_stage_inputs(st)[2]) for st,_ in _STAGES], data=data),f)
        os.replace(tmp,path)
    except (OSError, sqlite3.Error):
        pass
    finally:
        with _LOCK:
            _SUMMARY['running'] = False

def table_needs():
    return summaries().get('needs', {st: [] for st,_ in _STAGES})

def filtered_list():
    key = (_identity(paths.filtered_list()), json.dumps(_figures_key()))
    with _LOCK:
        if _INVENTORY['key'] != key and not _INVENTORY['running']:
            _INVENTORY['running'] = True
            threading.Thread(target=_refresh_inventory, args=(key,_INVENTORY['generation']),daemon=True).start()
        cached = _INVENTORY['rows'] if _INVENTORY['key'] == key else None
    out = []
    for row in cached if cached is not None else [dict(r,exists=None) for r in filtered_rows(paths.filtered_list())]:
        if row.get('reason') in ('bilingual','other_language','language_review'):
            root, source = _source_place(row['media'], row['name'])
            row = _filtered_evidence(dict(row,exists=bool(source) and os.path.isfile(source)),root,source)
        out.append(row)
    return out

def _refresh_inventory(key, generation):
    try:
        rows = _read_filtered_list()
        with _LOCK:
            if key == (_identity(paths.filtered_list()), json.dumps(_figures_key())) and generation == _INVENTORY['generation']:
                _INVENTORY.update(key=key, rows=rows)
    finally:
        with _LOCK:
            _INVENTORY['running'] = False
