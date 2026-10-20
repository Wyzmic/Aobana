import json
import os
import re
import sys
import threading
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARKER_PATH = os.path.join(BASE_DIR, "aobana.installed")


def _user_data_dir():
    if os.environ.get("AOBANA_DATA_DIR"):
        return os.environ["AOBANA_DATA_DIR"]
    if sys.platform == "win32":
        root = os.environ.get("LOCALAPPDATA") or os.path.expanduser(r"~\AppData\Local")
        return os.path.join(root, "Aobana")
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/Aobana")
    root = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(root, "aobana")


INSTALLED = os.path.exists(MARKER_PATH)

DATA_FOLDER = "data"

DB_NAMES = ("subs.db", "epub.db", "manga.db", "custom.db")
DB_COMPANION_DBS = ("search_cache.db", "analysis.db")
DB_COMPANIONS = ("filtered.tsv", "analysis.json", "analysis.view.jsonl", "analysis-attempt.json", "estimate.json",
                 "media_cache.json", "library_summary.json", "library_figures.json",
                 "settings_snapshot.json", ".index_run.json", ".index.stop", ".check.stop",
                 "pending-reindex.json", "pending-reindex.json.writer.lock",
                 "pending-reindex.json.bad", "filtered.tsv.epub-pending", ".index-runs")

COMPANION_FOLDERS = ('choices', 'check', 'cache', 'runs')
_COMPANION_MIGRATION_LOCK = threading.RLock()
_FLAT_COMPANION_ROOTS = set()
_COMPANION_ERRORS = []
_MIGRATION_LOCK_NAME = '.companion-migration.writer.lock'


def companion_link(path):
    from pathlib import Path
    path = Path(path)
    return path.is_symlink() or getattr(path, 'is_junction', lambda: False)()


def companion_folder(name):
    if not isinstance(name, str) or name in ('', '.', '..') or '/' in name or '\\' in name:
        raise ValueError('A companion must be one file name.')
    if name in DB_NAMES or any(name == db + suffix for db in DB_NAMES
                              for suffix in ('-wal', '-shm', '-journal')):
        return ''
    if name.endswith(('.writer.lock', '.phase-history.json')):
        return 'runs'
    if name == '.index-runs' or re.fullmatch(r'\.index_run(?:-[A-Za-z0-9]+)?\.json', name):
        return 'runs'
    if re.fullmatch(r'\.(?:index(?:-[A-Za-z0-9]+)?|check)\.stop', name):
        return 'runs'
    if name in ('filtered.tsv', 'filtered.tsv.epub-pending', 'pending-reindex.json', 'pending-reindex.json.bad'):
        return 'choices'
    if name.startswith('analysis.') or name == 'analysis-attempt.json':
        if name in DB_COMPANIONS or any(name == 'analysis.db' + s for s in ('', '-wal', '-shm', '-journal')):
            return 'check'
    if name in DB_COMPANIONS or any(name == 'search_cache.db' + s for s in ('', '-wal', '-shm', '-journal')):
        return 'cache'
    raise ValueError('Unknown database companion: ' + name)


def companion(name, db=None):
    root = os.path.dirname(os.path.abspath(db or subs_db()))
    folder = companion_folder(name)
    new = os.path.join(root, folder, name) if folder else os.path.join(root, name)
    old = os.path.join(root, name)
    flat = _FLAT_COMPANION_ROOTS | set(json.loads(os.environ.get('AOBANA_FLAT_COMPANION_ROOTS', '[]')))
    if folder and not os.path.exists(new) and (root in flat or os.path.exists(old)):
        return old
    return new


def companion_writer_lock(db):
    absolute = os.path.abspath(db)
    root, name = os.path.dirname(absolute), os.path.basename(absolute)
    if os.path.basename(root) in COMPANION_FOLDERS and name not in DB_NAMES:
        root = os.path.dirname(root)
    return companion(name + '.writer.lock', os.path.join(root, 'subs.db'))


def writer_lock_paths(db):
    absolute = os.path.abspath(db)
    root, name = os.path.dirname(absolute), os.path.basename(absolute)
    if os.path.basename(root) in COMPANION_FOLDERS and name not in DB_NAMES:
        root = os.path.dirname(root)
    return {absolute + '.writer.lock', os.path.join(root, name + '.writer.lock'),
            os.path.join(root, 'runs', name + '.writer.lock')}


def migrate_companions(db=None):
    from pathlib import Path
    from aobana.indexing.run_control import WriterLease, writer_active
    root = Path(db or subs_db()).absolute().parent
    if not root.exists():
        return []
    with _COMPANION_MIGRATION_LOCK:
        if any(writer_active(root / name) for name in DB_NAMES + DB_COMPANION_DBS + ('filtered.tsv', 'pending-reindex.json')):
            raise RuntimeError('An existing writer prevents companion migration.')
        if companion_link(root / 'runs'):
            raise OSError('Companion directory is a link: runs')
        lease = WriterLease(root / 'subs.db')
        lease.path = str(root / 'runs' / _MIGRATION_LOCK_NAME)
        with lease:
            return _move_companions(db)


def _move_companions(db=None):
    from pathlib import Path
    from aobana.indexing.run_control import writer_active
    root = Path(db or subs_db()).absolute().parent
    with _COMPANION_MIGRATION_LOCK:
        if not root.exists():
            return []
        for name in DB_NAMES + DB_COMPANION_DBS + ('filtered.tsv', 'pending-reindex.json'):
            if writer_active(root / name):
                raise RuntimeError('An existing writer prevents companion migration.')
        targets = []
        conflicts = set()
        for source in sorted(root.iterdir()):
            if beside_db(source.name):
                try:
                    folder = companion_folder(source.name)
                except ValueError:
                    continue
                if folder and (root / folder / source.name).exists():
                    base = next((n for n in DB_COMPANION_DBS if source.name == n or source.name.startswith(n + '-')), source.name)
                    conflicts.add(base)
                    _COMPANION_ERRORS.append(dict(error='companion_conflict', file=source.name, root=str(root)))
        for source in sorted(root.iterdir()):
            if not beside_db(source.name):
                continue
            try:
                folder = companion_folder(source.name)
            except ValueError:
                continue
            if not folder:
                continue
            if any(source.name == name or source.name.startswith(name + '-') for name in conflicts):
                continue
            destination = root / folder / source.name
            if companion_link(source) or companion_link(destination.parent):
                raise OSError('Companion link cannot be migrated: ' + source.name)
            if destination.exists() or destination.is_symlink():
                raise FileExistsError('Both companion locations exist: ' + source.name)
            targets.append((source, destination))
        created, moved = [], []
        try:
            for name in COMPANION_FOLDERS:
                directory = root / name
                if companion_link(directory):
                    raise OSError('Companion directory is a link: ' + name)
                if not directory.exists():
                    directory.mkdir()
                    created.append(directory)
            for source, destination in targets:
                os.rename(source, destination)
                moved.append((source, destination))
        except OSError:
            rollback_failures = []
            for source, destination in reversed(moved):
                try:
                    os.rename(destination, source)
                except OSError:
                    rollback_failures.append(str(destination))
            for directory in reversed(created):
                try:
                    directory.rmdir()
                except OSError:
                    pass
            if rollback_failures:
                raise OSError('Migration recovery required; retained at: ' + ', '.join(rollback_failures))
            raise
        return [str(destination.relative_to(root)) for _, destination in moved]


def start_companions():
    if os.environ.get('AOBANA_RUN_CHILD') == '1':
        return []
    _COMPANION_ERRORS.clear()
    outcomes = []
    roots = dict.fromkeys(os.path.dirname(os.path.abspath(getter()))
                         for getter in (subs_db, epub_db, manga_db, custom_db))
    for root in roots:
        _FLAT_COMPANION_ROOTS.discard(root)
        try:
            moved = migrate_companions(os.path.join(root, 'subs.db'))
            outcomes.append(dict(root=root, moved=moved, skipped=False))
        except (RuntimeError, OSError) as error:
            _FLAT_COMPANION_ROOTS.add(root)
            if isinstance(error, OSError):
                _COMPANION_ERRORS.append(dict(error='companion_migration_failed', root=root, details=str(error)))
            outcomes.append(dict(root=root, moved=[], skipped=True))
    return outcomes


def companion_errors():
    return [dict(error) for error in _COMPANION_ERRORS]


def beside_db(name):
    if name == _MIGRATION_LOCK_NAME:
        return True
    if name in COMPANION_FOLDERS:
        return True
    if re.fullmatch(r'\.index_run-[A-Za-z0-9]+\.json|\.index-[A-Za-z0-9]+\.stop', name):
        return True
    if name in DB_COMPANIONS:
        return True
    if name.endswith('.writer.lock') and name.removesuffix('.writer.lock') in DB_COMPANIONS:
        return True
    return any(name == db + suffix for db in DB_NAMES + DB_COMPANION_DBS
               for suffix in ("", "-wal", "-shm", "-journal", ".writer.lock", ".phase-history.json"))


def _source_store():
    return os.path.join(BASE_DIR, DATA_FOLDER)


STORE_DIR = _user_data_dir() if INSTALLED else (os.environ.get("AOBANA_DATA_DIR") or _source_store())
CONFIG_PATH = os.path.join(STORE_DIR, "config.json")


def _read_json(path):
    try:
        with open(path, encoding="utf-8-sig") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


MEDIA_NAMES = ("Subtitles", "Books", "Manga", "Custom")


def make_source_folders():
    if INSTALLED:
        return
    root = _default_media_root()
    cfg = load_config()
    try:
        entries = set(os.listdir(root)) if os.path.isdir(root) else set()
        if entries <= set(MEDIA_NAMES):
            for i, (key, env) in enumerate((("subs_dir", "SUBS_ROOT_DIR"), ("books_dir", "EPUB_ROOT_DIR"))):
                new = os.path.join(root, MEDIA_NAMES[i])
                named = cfg.get(key + 's')
                if os.environ.get(env):
                    continue
                if key + 's' in cfg and (not named or not same_roots(named, new)):
                    continue
                os.makedirs(new, exist_ok=True)
    except OSError:
        pass


def load_config():
    cfg = _read_json(CONFIG_PATH)
    if not INSTALLED:
        return _migrate_media_config(cfg)
    seed = _read_json(MARKER_PATH)
    stamp = seed.get("installed_at")
    new_install = stamp is not None and cfg.get("installed_at") != stamp
    if not new_install:
        return _migrate_media_config(cfg)
    before = dict(cfg)
    if "subs_dir" in seed or "books_dir" in seed:
        cfg.update(subs_dirs=root_list(seed.get('subs_dir')), books_dirs=root_list(seed.get('books_dir')))
        cfg.pop('subs_dir', None)
        cfg.pop('books_dir', None)
    if "manga_dir" in seed:
        cfg['manga_dirs'] = root_list(seed.get('manga_dir'))
        cfg.pop('manga_dir', None)
    if isinstance(seed.get("port"), int):
        cfg["port"] = seed["port"]
    if "db_dir" in seed:
        if seed["db_dir"]:
            cfg["db_dir"] = seed["db_dir"]
        else:
            cfg.pop("db_dir", None)
    cfg["installed_at"] = stamp
    try:
        for folder in (folder for kind in ('subs', 'books', 'manga')
                       for folder in root_list(cfg.get(MEDIA_DIR_LIST_KEYS[kind], cfg.get(MEDIA_DIR_KEYS[kind])))):
            if folder:
                os.makedirs(folder, exist_ok=True)
        if cfg.get("db_dir"):
            os.makedirs(cfg["db_dir"], exist_ok=True)
        if cfg != before:
            with _CONFIG_LOCK:
                now = _read_json(CONFIG_PATH)
                if now.get("installed_at") != stamp:
                    now.update({k: v for k, v in cfg.items() if k not in before or before[k] != v})
                    for k in before.keys() - cfg.keys():
                        now.pop(k, None)
                    save_config(now)
                cfg = now
    except OSError:
        pass
    return _migrate_media_config(cfg)


def _migrate_media_config(cfg):
    if not any(key in cfg for key in MEDIA_DIR_KEYS.values()):
        return cfg
    with _CONFIG_LOCK:
        now = _read_json(CONFIG_PATH)
        for key in MEDIA_DIR_KEYS.values():
            if key in now:
                value = now.pop(key)
                now.setdefault(key + 's', [value] if value else [])
        try:
            save_config(now)
        except OSError:
            pass
        return now


MEDIA_KINDS = ("subs", "books", "manga", "custom")
MEDIA_DIR_KEYS = {"subs": "subs_dir", "books": "books_dir", "manga": "manga_dir", "custom": "custom_dir"}
MEDIA_DIR_LIST_KEYS = {kind: key + 's' for kind, key in MEDIA_DIR_KEYS.items()}


def media_enabled(kind, cfg=None):
    cfg = load_config() if cfg is None else cfg
    media = cfg.get("media")
    if isinstance(media, dict) and kind in media:
        return bool(media[kind])
    if kind == "custom":
        return False
    if kind == "manga":
        if "manga_dirs" in cfg or "manga_dir" in cfg or os.environ.get("MANGA_ROOT_DIR"):
            return bool(manga_dir())
        return os.path.isdir(_source_media(2))
    folder = {"subs": subs_dir, "books": books_dir}.get(kind)
    return bool(folder and folder())


def media_state():
    cfg = load_config()
    return {k: media_enabled(k, cfg) for k in MEDIA_KINDS}


def setup_needed():
    if not INSTALLED:
        return False
    cfg = load_config()
    return "media" not in cfg and not any(k in cfg for k in (*MEDIA_DIR_KEYS.values(), *MEDIA_DIR_LIST_KEYS.values()))


def default_media_folder(kind):
    return _source_media(MEDIA_KINDS.index(kind))


_CONFIG_LOCK = threading.RLock()


def update_config(fn):
    with _CONFIG_LOCK:
        cfg = load_config()
        err = fn(cfg)
        if err is None:
            save_config(cfg)
        return err


def save_config(cfg):
    with _CONFIG_LOCK:
        _save_config(cfg)


def _save_config(cfg):
    os.makedirs(STORE_DIR, exist_ok=True)
    tmp = f"{CONFIG_PATH}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)
    for attempt in range(20):
        try:
            os.replace(tmp, CONFIG_PATH)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.05)


def _documents_dir():
    if sys.platform == "win32":
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(260)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:
                return buf.value
        except Exception:
            pass
    return os.path.join(os.path.expanduser("~"), "Documents")


def _default_media_root():
    if INSTALLED:
        return os.path.join(_documents_dir(), "Aobana")
    return os.path.join(BASE_DIR, "content")


def subs_dir():
    return next(iter(media_roots('subs')), None)


def books_dir():
    return next(iter(media_roots('epub')), None)


def manga_dir():
    return next(iter(media_roots('manga')), None)


def media_roots(media):
    media = 'epub' if media == 'books' else media
    kind, i, env = {'subs': ('subs', 0, 'SUBS_ROOT_DIR'), 'epub': ('books', 1, 'EPUB_ROOT_DIR'),
                    'manga': ('manga', 2, 'MANGA_ROOT_DIR'), 'custom': ('custom', 3, 'CUSTOM_ROOT_DIR')}[media]
    if os.environ.get(env):
        return [os.environ[env]]
    cfg = load_config()
    key = MEDIA_DIR_LIST_KEYS[kind]
    if key in cfg:
        value = cfg[key]
        return [folder for folder in value if isinstance(folder, str) and folder] if isinstance(value, list) else []
    old = MEDIA_DIR_KEYS[kind]
    if old in cfg:
        return [cfg[old]] if cfg[old] else []
    default = _source_media(i)
    if media == 'subs' and not INSTALLED and not os.path.exists(default) and os.path.isdir(_default_media_root()):
        default = _default_media_root()
    return [default]


def root_list(value):
    return list(value) if isinstance(value, (list, tuple)) else [value] if value else []


def roots_value(media):
    roots = media_roots(media)
    return roots[0] if len(roots) == 1 else roots or None


def same_roots(left, right):
    normalize = lambda value: [os.path.normcase(os.path.realpath(root)) for root in root_list(value)]
    return normalize(left) == normalize(right)


def folder_key(path):
    return os.path.normcase(os.path.realpath(path))


def folders_overlap(a, b):
    a, b = folder_key(a), folder_key(b)
    try:
        common = os.path.commonpath((a, b))
    except ValueError:
        return False
    return common in (a, b)


def set_roots(kind, cfg):
    env = {"subs": "SUBS_ROOT_DIR", "books": "EPUB_ROOT_DIR", "manga": "MANGA_ROOT_DIR", "custom": "CUSTOM_ROOT_DIR"}[kind]
    if os.environ.get(env):
        return [os.environ[env]]
    if MEDIA_DIR_LIST_KEYS[kind] in cfg:
        value = cfg[MEDIA_DIR_LIST_KEYS[kind]]
        return [folder for folder in value if isinstance(folder, str) and folder] if isinstance(value, list) else []
    if cfg.get(MEDIA_DIR_KEYS[kind]):
        return [cfg[MEDIA_DIR_KEYS[kind]]]
    return media_roots(kind) if media_enabled(kind, cfg) else []


def inside_root(path, root):
    try:
        return os.path.commonpath((os.path.realpath(root), os.path.realpath(path))) == os.path.realpath(root)
    except ValueError:
        return False


def resolve_media_path(media, relative, roots=None, file_only=True):
    from aobana.utils import name_key
    parts = name_key(relative).split('/')
    if any(part in ('', '.', '..') for part in parts) or os.path.isabs(relative):
        return None
    for root in media_roots(media) if roots is None else root_list(roots):
        base = os.path.realpath(root)
        target = os.path.realpath(os.path.join(base, *parts))
        inside = inside_root(target, base)
        if inside and (os.path.isfile(target) if file_only else os.path.exists(target)):
            return target
        if media == 'subs' and len(parts) == 2:
            target = os.path.join(base, parts[-1])
            if inside and os.path.isfile(target):
                from aobana.utils import sub_relpath
                if name_key(sub_relpath(target, base)) == name_key(relative):
                    return target
    return None


def index_roots(media, first, roots=None):
    roots = media_roots(media) if roots is None else roots
    return roots if (roots[0] if roots else None) == first else root_list(first)


def custom_dir():
    return next(iter(media_roots('custom')), None)


def _source_media(i):
    return os.path.join(_default_media_root(), MEDIA_NAMES[i])


def server_port():
    for value in (os.environ.get("AOBANA_PORT"), load_config().get("port")):
        try:
            if value not in (None, ""):
                return int(value)
        except (TypeError, ValueError):
            pass
    return 5005 if sys.platform == "darwin" else 5000


def debug_mode():
    env = os.environ.get("AOBANA_DEBUG")
    if env is not None:
        return env == "1"
    return load_config().get("debug") is True


def custom_trim():
    return load_config().get("custom_trim", True) is not False


def custom_ruby():
    return load_config().get("custom_ruby", True) is not False


def subtitle_tags(cfg=None):
    return (load_config() if cfg is None else cfg).get("subtitle_tags", True) is not False


def usable_cpus():
    if hasattr(os, "process_cpu_count"):
        return os.process_cpu_count() or 1
    if hasattr(os, "sched_getaffinity"):
        return len(os.sched_getaffinity(0)) or 1
    return os.cpu_count() or 1


def recommended_workers():
    return max(1, usable_cpus() // 2)


def search_workers():
    value = load_config().get("search_workers")
    if type(value) is int and 1 <= value <= usable_cpus():
        return value
    return recommended_workers()


def search_worker_delay(reading=False):
    return 0 if reading else 5


def index_workers():
    for value in (os.environ.get("AOBANA_INDEX_WORKERS"), load_config().get("index_workers")):
        try:
            if value not in (None, ""):
                return min(usable_cpus(), max(1, int(value)))
        except (TypeError, ValueError):
            pass
    return recommended_workers()


def db_dir():
    return load_config().get("db_dir") or default_db_dir()


DB_FOLDER = "db"


def default_db_dir():
    if INSTALLED:
        chosen = _read_json(MARKER_PATH).get("db_dir")
        if isinstance(chosen, str) and chosen.strip():
            return chosen
    return os.path.join(STORE_DIR, DB_FOLDER)


def subs_db():
    return os.environ.get("SUBS_DB_PATH") or os.path.join(db_dir(), "subs.db")


def epub_db():
    return os.environ.get("EPUB_DB_PATH") or os.path.join(db_dir(), "epub.db")


def manga_db():
    return os.environ.get("MANGA_DB_PATH") or os.path.join(db_dir(), "manga.db")


def custom_db():
    return os.environ.get("CUSTOM_DB_PATH") or os.path.join(db_dir(), "custom.db")


def filtered_list():
    return companion('filtered.tsv')


def logs_dir():
    return os.path.join(STORE_DIR, "logs")


def known_words_dir():
    return os.path.join(STORE_DIR, "known-words")


def backups_dir(*parts):
    return os.path.join(STORE_DIR, "backups", *parts)


def data_file(*parts):
    return os.path.join(BASE_DIR, "data", *parts)


RUBY_TABLES_PATH = data_file("ruby", "ruby.tsv")

KANJI_READINGS_PATH = data_file("ruby", "kanji_readings.tsv")
