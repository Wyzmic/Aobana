import json
import os
import sys
import threading
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
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


MEDIA_NAMES = ("Subtitles", "Books", "Manga")


def make_source_folders():
    if INSTALLED:
        return
    root = _default_media_root()
    cfg = load_config()
    try:
        entries = set(os.listdir(root)) if os.path.isdir(root) else set()
        if entries <= set(MEDIA_NAMES):
            for i, key in enumerate(("subs_dir", "books_dir")):
                new = os.path.join(root, MEDIA_NAMES[i])
                named = cfg.get(key)
                if key in cfg and (not named or os.path.normcase(os.path.abspath(named)) != os.path.normcase(new)):
                    continue
                os.makedirs(new, exist_ok=True)
    except OSError:
        pass


def load_config():
    cfg = _read_json(CONFIG_PATH)
    if not INSTALLED:
        return cfg
    seed = _read_json(MARKER_PATH)
    stamp = seed.get("installed_at")
    new_install = stamp is not None and cfg.get("installed_at") != stamp
    if not new_install:
        return cfg
    before = dict(cfg)
    if "subs_dir" in seed or "books_dir" in seed:
        cfg.update(subs_dir=seed.get("subs_dir") or "", books_dir=seed.get("books_dir") or "")
    if "manga_dir" in seed:
        cfg["manga_dir"] = seed.get("manga_dir") or ""
    if isinstance(seed.get("port"), int):
        cfg["port"] = seed["port"]
    if "db_dir" in seed:
        if seed["db_dir"]:
            cfg["db_dir"] = seed["db_dir"]
        else:
            cfg.pop("db_dir", None)
    cfg["installed_at"] = stamp
    try:
        for folder in (cfg.get("subs_dir"), cfg.get("books_dir"), cfg.get("manga_dir")):
            if folder:
                os.makedirs(folder, exist_ok=True)
        if cfg.get("db_dir"):
            os.makedirs(cfg["db_dir"], exist_ok=True)
        if cfg != before:
            save_config(cfg)
    except OSError:
        pass
    return cfg


MEDIA_KINDS = ("subs", "books", "manga")
MEDIA_DIR_KEYS = {"subs": "subs_dir", "books": "books_dir", "manga": "manga_dir"}


def media_enabled(kind, cfg=None):
    cfg = load_config() if cfg is None else cfg
    media = cfg.get("media")
    if isinstance(media, dict) and kind in media:
        return bool(media[kind])
    if kind == "manga":
        if "manga_dir" in cfg or os.environ.get("MANGA_ROOT_DIR"):
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
    return "media" not in cfg and not any(k in cfg for k in MEDIA_DIR_KEYS.values())


def default_media_folder(kind):
    return _source_media(MEDIA_KINDS.index(kind))


def save_config(cfg):
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
    if os.environ.get("SUBS_ROOT_DIR"):
        return os.environ["SUBS_ROOT_DIR"]
    cfg = load_config()
    if "subs_dir" in cfg:
        return cfg["subs_dir"] or None
    d = _source_media(0)
    if not INSTALLED and not os.path.exists(d) and os.path.isdir(_default_media_root()):
        return _default_media_root()
    return d


def books_dir():
    if os.environ.get("EPUB_ROOT_DIR"):
        return os.environ["EPUB_ROOT_DIR"]
    cfg = load_config()
    if "books_dir" in cfg:
        return cfg["books_dir"] or None
    return _source_media(1)


def manga_dir():
    if os.environ.get("MANGA_ROOT_DIR"):
        return os.environ["MANGA_ROOT_DIR"]
    cfg = load_config()
    if "manga_dir" in cfg:
        return cfg["manga_dir"] or None
    return _source_media(2)


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


def search_worker_delay():
    value = load_config().get("search_worker_delay")
    return value if type(value) is int and 0 <= value <= 60 else 10


def index_workers():
    for value in (os.environ.get("AOBANA_INDEX_WORKERS"), load_config().get("index_workers")):
        try:
            if value not in (None, ""):
                return max(1, int(value))
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


def filtered_list():
    return os.path.join(os.path.dirname(os.path.abspath(subs_db())), "filtered.tsv")


def logs_dir():
    return os.path.join(STORE_DIR, "logs")


def data_file(*parts):
    return os.path.join(BASE_DIR, "data", *parts)


RUBY_TABLES_PATH = data_file("ruby", "ruby.tsv")
