import os
import sys
import re
import sqlite3
import subprocess
import threading
import time
import uuid

if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')

from aobana import paths
if __name__ == '__main__':
    paths.start_companions()
if __name__ in ('__main__', '__mp_main__') and getattr(sys.modules.get(__name__), '__dict__', None) is globals():
    sys.modules.setdefault('aobana.server.app', sys.modules[__name__])
from flask import Flask, render_template, make_response, request, jsonify, g, abort, send_file
from aobana.search.engine import get_search_results, folder_prefix_where, is_reading_search, fts_phrase
from aobana.search.furigana import warm_ruby_lexicon
from aobana.search.reading import parse_reading_terms, reading_fallback_words
from aobana.search.titles import format_episode_title, format_book_title, get_formatted_title
from aobana.search import furigana, result_cache
from aobana.search.iplusone import StaleVocabulary
from aobana.server import library
from aobana.server import folder_picker
from aobana.server import updater
from aobana.utils import fold_compat, normalize_query, index_busy, media_wanted, outdated_sources, parse_media, RUBY_RE, BOOK_RUBY_RE, MEDIA_NAMES

app = Flask(__name__, template_folder='.', static_folder=os.path.join(paths.BASE_DIR, 'static'))
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 365 * 24 * 3600


def _asset_version():
    import hashlib
    h = hashlib.sha1()
    root = os.path.join(paths.BASE_DIR, "static")
    for d, _, names in sorted(os.walk(root)):
        for n in sorted(names):
            st = os.stat(os.path.join(d, n))
            h.update(f"{n}:{st.st_size}:{st.st_mtime_ns};".encode())
    return h.hexdigest()[:10]


ASSET_V = _asset_version()


def _asset_v():
    return _asset_version() if DEBUG else ASSET_V


@app.route("/favicon.ico")
def favicon():
    return app.send_static_file("aobana.svg")

BOOT_ID = os.environ.setdefault("AOBANA_BOOT_ID", uuid.uuid4().hex)

VERSION = "2.0"
RELEASES_URL = "https://github.com/Wyzmic/Aobana/releases/latest"
RELEASES_API = "https://api.github.com/repos/Wyzmic/Aobana/releases"
LATEST_API = f"{RELEASES_API}/latest"
RELEASES_TAG_URL = "https://github.com/Wyzmic/Aobana/releases/tag/v"
update_info = {"checked": False, "latest": None, "release": None, "page_waiting": 0.0}
TERMUX = os.environ.get("AOBANA_TERMUX") == "1"
SELF_UPDATE = TERMUX and os.environ.get("AOBANA_UPDATER") == "1"
ON_PHONE = TERMUX or bool(os.environ.get("TERMUX_VERSION"))
TERMUX_INSTALL = "curl -fsSL https://raw.githubusercontent.com/Wyzmic/Aobana/main/termux/install.sh | bash"


def version_tuple(v):
    return tuple(int(n) for n in re.findall(r"\d+", v or ""))


def check_for_update():
    try:
        import json
        import urllib.request
        req = urllib.request.Request(LATEST_API, headers={
            "Accept": "application/vnd.github+json", "User-Agent": f"Aobana/{VERSION}"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            release = json.load(resp)
        tag = str(release.get("tag_name") or "")
        update_info["latest"] = tag.lstrip("vV") or None
        update_info["release"] = release
    except Exception:
        pass
    finally:
        update_info["checked"] = True


from aobana.search.media_tab import warm_media_library


def start_background():
    targets = [check_for_update, warm_ruby_lexicon, warm_media_library]
    if os.environ.get("AOBANA_CLIENT") == "reibun":
        update_info["checked"] = True
        targets = [warm_ruby_lexicon]
    for target in targets:
        threading.Thread(target=target, daemon=True).start()

def get_db():
    media = paths.media_state() if 'db_subs' not in g or 'db_epub' not in g else None
    if 'db_subs' not in g:
        subs_path = paths.subs_db()
        if media["subs"] and os.path.exists(subs_path):
            g.db_subs = sqlite3.connect(f"file:{subs_path}?mode=ro", uri=True)
            g.db_subs.row_factory = sqlite3.Row
            g.db_subs.execute("PRAGMA mmap_size = 2147483648;")
        else:
            g.db_subs = None

    if 'db_epub' not in g:
        epub_path = paths.epub_db()
        if media["books"] and os.path.exists(epub_path):
            g.db_epub = sqlite3.connect(f"file:{epub_path}?mode=ro", uri=True)
            g.db_epub.row_factory = sqlite3.Row
            g.db_epub.execute("PRAGMA mmap_size = 536870912;")
        else:
            g.db_epub = None

    return g.db_subs, g.db_epub


def get_manga_db():
    if 'db_manga' not in g:
        path = paths.manga_db()
        if paths.media_enabled("manga") and os.path.exists(path):
            g.db_manga = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            g.db_manga.row_factory = sqlite3.Row
        else:
            g.db_manga = None
    return g.db_manga


def get_custom_db():
    if 'db_custom' not in g:
        path = paths.custom_db()
        if paths.media_enabled('custom') and os.path.exists(path):
            g.db_custom = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
            g.db_custom.row_factory = sqlite3.Row
        else:
            g.db_custom = None
    return g.db_custom

@app.teardown_appcontext
def close_db(error):
    for name in ('db_subs', 'db_epub', 'db_manga', 'db_custom'):
        conn = g.pop(name, None)
        if conn is not None:
            conn.close()


@app.teardown_request
def release_thread_resources(error):
    furigana.release_thread_resources()

active_queries = {}
queries_lock = threading.Lock()
pending_cancels = {}


def _client_key():
    token = request.args.get("client", "")
    return f"client:{token}" if token else f"ip:{request.remote_addr}"


def _learn_param():
    from aobana.search import iplusone
    return iplusone.learn_token(request.args.get("learn", "off"))


def _no_known_words():
    return jsonify({"error": "known_words_unavailable"}), 409


def _search_identity(q, sort, seed, media, exact, folder, file_param, origin="", ruby_only=False, learn=""):
    media_content = origin == "media"
    return (q, sort, seed if sort == "random" else None, media, exact,
            None if q and not media_content else folder, file_param, media_content, ruby_only, learn)


def _interrupt(entries):
    for _, flag, conns in entries:
        flag[0] = True
        for conn in conns.values():
            if conn is not None:
                try:
                    conn.interrupt()
                except Exception:
                    pass


def _cancel_client(client_key):
    with queries_lock:
        pending_cancels.pop(client_key, None)
        running = list(active_queries.get(client_key, []))
    _interrupt(running)


def _keep_client(client_key):
    with queries_lock:
        timer = pending_cancels.pop(client_key, None)
    if timer is not None:
        timer.cancel()


def _interrupt_all_searches(wait=5.0):
    with queries_lock:
        running = [r for rs in active_queries.values() for r in rs]
    _interrupt(running)
    end = time.monotonic() + wait
    while time.monotonic() < end:
        with queries_lock:
            if not active_queries:
                return
        time.sleep(0.05)


library.register_release(_interrupt_all_searches)

@app.route("/", methods=["GET"])
def index():
    q = request.args.get("q", "")
    sort = parse_sort(request.args.get("sort", "recommended"))
    exact = request.args.get("exact", "")
    media = request.args.get("media", "all")
    resp = make_response(render_template("index.html", q=q, sort=sort, exact=exact, media=media,
                                         boot=BOOT_ID, asset_v=_asset_v(), version=VERSION,
                                         handoff=library.load_profile_handoff(PORT),
                                         handoff_pending=library.handoff_pending_from(PORT),
                                         media_boot=_media_boot(), termux=ON_PHONE,
                                         known_words=_known_words_boot()))
    resp.headers["Cache-Control"] = "no-store"
    return resp

def _known_words_boot():
    try:
        from aobana.search import known_words
        return known_words.status()
    except Exception:
        return {"available": False, "sources": []}


def _media_boot():
    setup = paths.setup_needed()
    return {"on": paths.media_state(), "setup": setup,
            "defaults": {k: paths.default_media_folder(k) for k in paths.MEDIA_KINDS},
            "folders": {"subs": paths.subs_dir(), "books": paths.books_dir(), "manga": paths.manga_dir(), "custom": paths.custom_dir()},
            "picker": folder_picker.available(), "check_asked": library.check_asked(),
            "subtitle_tags": paths.subtitle_tags()}


def _media_connections(db_subs, db_epub):
    return {"subs": db_subs, "epub": db_epub, "manga": get_manga_db(), "custom": get_custom_db()}


def _media_unavailable(media, dbs, db_epub=None, db_manga=None):
    if media == "all":
        return False
    from aobana.utils import media_connections
    dbs = media_connections(dbs, db_epub, db_manga)
    wanted = media_wanted(media)
    return bool(wanted) and all(dbs.get(m) is None for m in wanted)


SORTS = ("recommended", "random", "asc", "desc", "chrono")
_unknown_sorts = set()


def parse_sort(value):
    if value in SORTS:
        return value
    if value not in _unknown_sorts and len(_unknown_sorts) < 100:
        _unknown_sorts.add(value)
        print(f"search: unknown sort {value!r}; using recommended", file=sys.stderr)
    return "recommended"


_LOCAL_HOSTS = ("127.0.0.1", "localhost", "[::1]")


def _local_authority(value, port):
    host, sep, p = value.rpartition(":") if not value.endswith("]") else (value, "", "")
    if not sep or not host:
        host, p = value, ""
    return host.lower() in _LOCAL_HOSTS and (p == "" or p == port)


@app.before_request
def _check_host():
    port = str(request.environ.get("SERVER_PORT", ""))
    if not _local_authority(request.host or "", port):
        abort(400)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("Origin")
        if origin is not None and not (origin.startswith("http://") and _local_authority(origin[7:], port)):
            abort(400)


def _require_page():
    if request.headers.get("X-Aobana") != "1":
        abort(403)


@app.errorhandler(sqlite3.OperationalError)
def _index_busy(error):
    if index_busy(error):
        return jsonify({"busy": True, "error": "index_busy"}), 503
    raise error


DEBUG = paths.debug_mode()
PORT = paths.server_port()
app.config['TEMPLATES_AUTO_RELOAD'] = DEBUG

from aobana.server import routes_search, routes_reader, routes_media, routes_library
from aobana.server import routes_settings, routes_learn, routes_update

if __name__ == "__main__":
    from werkzeug.serving import WSGIRequestHandler

    class _QuietRequestHandler(WSGIRequestHandler):
        def log_request(self, code="-", size="-"):
            if str(code) == "200" and self.path.split("?", 1)[0] in ("/api/activity", "/api/search/progress"):
                return
            super().log_request(code, size)

    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.kernel32.SetConsoleTitleW("露草 / Aobana")
            except Exception:
                pass
        print(f"露草 / Aobana - http://127.0.0.1:{PORT}/")
        print("Termux を閉じるとサーバーが止まります。 / Close Termux to stop the server." if TERMUX else
              "このウィンドウを閉じるとサーバーが止まります。 / Close this window to stop the server.")
    paths.make_source_folders()
    if not DEBUG or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        start_background()
    app.run(host='127.0.0.1', port=PORT, debug=DEBUG, request_handler=_QuietRequestHandler)
