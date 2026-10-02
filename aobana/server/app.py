import os
import sys
import re
import sqlite3
import threading
import time
import uuid

if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')

from aobana import paths
from flask import Flask, render_template, make_response, request, jsonify, g, abort, send_file
from aobana.search.engine import get_search_results, folder_prefix_where
from aobana.search.furigana import warm_ruby_lexicon
from aobana.search.titles import format_episode_title, format_book_title, get_formatted_title
from aobana.search import furigana, result_cache
from aobana.server import library
from aobana.server import folder_picker
from aobana.server import updater
from aobana.utils import media_wanted, outdated_sources, parse_media

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

VERSION = "1.9"
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

@app.teardown_appcontext
def close_db(error):
    for name in ('db_subs', 'db_epub', 'db_manga'):
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


def _search_identity(q, sort, seed, media, exact, folder, file_param):
    return (q, sort, seed if sort == "random" else None, media, exact, None if q else folder, file_param)


def _interrupt(entries):
    for _, flag, conns in entries:
        flag[0] = True
        for conn in conns:
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
    sort = request.args.get("sort", "recommended")
    exact = request.args.get("exact", "")
    media = request.args.get("media", "all")
    resp = make_response(render_template("index.html", q=q, sort=sort, exact=exact, media=media,
                                         boot=BOOT_ID, asset_v=_asset_v(), version=VERSION,
                                         handoff=library.load_profile_handoff(PORT),
                                         handoff_pending=library.handoff_pending_from(PORT),
                                         media_boot=_media_boot(), termux=ON_PHONE))
    resp.headers["Cache-Control"] = "no-store"
    return resp

def _media_boot():
    setup = paths.setup_needed()
    return {"on": paths.media_state(), "setup": setup,
            "defaults": {k: paths.default_media_folder(k) for k in paths.MEDIA_KINDS},
            "folders": {"subs": paths.subs_dir(), "books": paths.books_dir(), "manga": paths.manga_dir()},
            "picker": folder_picker.available(), "check_asked": library.check_asked()}


def _media_unavailable(media, db_subs, db_epub, db_manga):
    if media == "all":
        return False
    dbs = {"subs": db_subs, "epub": db_epub, "manga": db_manga}
    wanted = media_wanted(media)
    return bool(wanted) and all(dbs[m] is None for m in wanted)


@app.route("/api/capabilities", methods=["GET"])
def api_capabilities():
    return jsonify({"version": VERSION, "media_sets": True})


@app.route("/api/search", methods=["GET"])
def api_search():
    client_key = _client_key()
    accepted_at = time.monotonic()
    _keep_client(client_key)
    q = request.args.get("q", "")
    sort = request.args.get("sort", "recommended")
    folders = tuple(sorted(f for f in request.args.getlist("folder") if f))
    folder = folders[0] if len(folders) == 1 else (folders or None)
    pins = tuple(f for f in request.args.getlist("pin") if f)
    exact = request.args.get("exact") == "on"
    limit = request.args.get("limit", 500, type=int)
    offset = request.args.get("offset", 0, type=int)
    file_param = request.args.get("file", "")
    media = parse_media(request.args.get("media", "all"))
    seed = request.args.get("seed", type=int)

    db_subs, db_epub = get_db()
    db_manga = get_manga_db()
    if _media_unavailable(media, db_subs, db_epub, db_manga):
        return jsonify({
            "results": [], "folder_counts": {}, "global_total": 0, "all_folders": [],
            "has_more": False, "outside_media": list(dict.fromkeys([*folders, *pins]))
        })
    abort_flag = [False]
    search = _search_identity(q, sort, seed, media, exact, folder, file_param)
    mine = (search, abort_flag, (db_subs, db_epub, db_manga))

    with queries_lock:
        running = active_queries.get(client_key, [])
        _interrupt([r for r in running if r[0] != search])
        active_queries[client_key] = [r for r in running if r[0] == search] + [mine]

    info = {}
    try:
        results, folder_counts, global_total, all_folders, has_more = get_search_results(
            db_subs, q, sort=sort, folder=folder, exact=exact, 
            abort_flag=abort_flag, limit=limit, offset=offset, file=file_param,
            db_epub=db_epub, media=media, seed=seed, db_manga=db_manga, info=info,
            search_workers=paths.search_workers(), search_delay=paths.search_worker_delay(),
            search_started=accepted_at, pins=pins
        )
        if abort_flag[0]:
            return jsonify({"aborted": True}), 499
    except sqlite3.OperationalError as e:
        if "interrupted" in str(e):
            return jsonify({"aborted": True}), 499
        raise
    finally:
        with queries_lock:
            left = [r for r in active_queries.get(client_key, []) if r is not mine]
            if left:
                active_queries[client_key] = left
            else:
                active_queries.pop(client_key, None)
    
    return jsonify({
        "results": results,
        "folder_counts": folder_counts,
        "global_total": global_total,
        "all_folders": all_folders,
        "has_more": has_more,
        "scoped": bool(info.get("scoped")),
        "outside_media": info.get("outside_media", []),
    })

@app.route("/api/search/counts", methods=["GET"])
def api_search_counts():
    from aobana.search.engine import folder_match_counts
    client_key = _client_key()
    accepted_at = time.monotonic()
    _keep_client(client_key)
    q = request.args.get("q", "")
    sort = request.args.get("sort", "recommended")
    seed = request.args.get("seed", type=int)
    media = parse_media(request.args.get("media", "all"))
    exact = request.args.get("exact") == "on"
    db_subs, db_epub = get_db()
    db_manga = get_manga_db()
    if _media_unavailable(media, db_subs, db_epub, db_manga):
        return jsonify({"folder_counts": {}, "all_folders": [], "global_total": 0})
    abort_flag = [False]
    mine = (_search_identity(q, sort, seed, media, exact, None, ""), abort_flag, (db_subs, db_epub, db_manga))
    with queries_lock:
        active_queries.setdefault(client_key, []).append(mine)
    try:
        got = folder_match_counts(
            db_subs, q, exact=exact, db_epub=db_epub, media=media,
            db_manga=db_manga, abort_flag=abort_flag,
            search_workers=paths.search_workers(), search_delay=paths.search_worker_delay(),
            search_started=accepted_at)
        if abort_flag[0]:
            return jsonify({"aborted": True}), 499
    except sqlite3.OperationalError as e:
        if "interrupted" in str(e):
            return jsonify({"aborted": True}), 499
        raise
    finally:
        with queries_lock:
            left = [r for r in active_queries.get(client_key, []) if r is not mine]
            if left:
                active_queries[client_key] = left
            else:
                active_queries.pop(client_key, None)
    if got is None:
        return jsonify({"fallback": True})
    counts, order, total = got
    return jsonify({"folder_counts": counts, "all_folders": order, "global_total": total})


@app.route("/api/search/progress", methods=["GET"])
def api_search_progress():
    from aobana.search.engine import search_progress
    client_key = _client_key()
    _keep_client(client_key)
    db_subs, db_epub = get_db()
    db_manga = get_manga_db()
    q = request.args.get("q", "")
    sort = request.args.get("sort", "recommended")
    seed = request.args.get("seed", type=int)
    media = parse_media(request.args.get("media", "all"))
    exact = request.args.get("exact") == "on"
    folders = tuple(sorted(f for f in request.args.getlist("folder") if f))
    folder = folders[0] if len(folders) == 1 else (folders or None)
    file_param = request.args.get("file", "")
    abort_flag = [False]
    mine = (_search_identity(q, sort, seed, media, exact, folder, file_param), abort_flag,
            (db_subs, db_epub, db_manga))
    with queries_lock:
        active_queries.setdefault(client_key, []).append(mine)
    try:
        return jsonify(search_progress(
            db_subs, db_epub, q, sort=sort, seed=seed, media=media, exact=exact,
            folder=folder, file=file_param or None, db_manga=db_manga,
            status_only=request.args.get("status") == "1", abort_flag=abort_flag))
    except sqlite3.OperationalError as e:
        if "interrupted" in str(e):
            return jsonify({"running": False, "aborted": True})
        raise
    finally:
        with queries_lock:
            left = [r for r in active_queries.get(client_key, []) if r is not mine]
            if left:
                active_queries[client_key] = left
            else:
                active_queries.pop(client_key, None)


CANCEL_GRACE_MAX = 60


@app.route("/api/search/cancel", methods=["POST"])
def api_search_cancel():
    _require_page()
    client_key = _client_key()
    body = request.get_json(silent=True) or {}
    try:
        grace = min(max(float(body.get("grace", 0)), 0), CANCEL_GRACE_MAX)
    except (TypeError, ValueError):
        grace = 0
    if not grace:
        _cancel_client(client_key)
        return jsonify({"ok": True})
    timer = threading.Timer(grace, _cancel_client, args=(client_key,))
    timer.daemon = True
    with queries_lock:
        old = pending_cancels.pop(client_key, None)
        pending_cancels[client_key] = timer
    if old is not None:
        old.cancel()
    timer.start()
    return jsonify({"ok": True, "grace": grace})

@app.route("/api/episodes", methods=["GET"])
def api_episodes():
    folder = request.args.get("folder", "")
    media = request.args.get("media", "all")
    if not folder:
        return jsonify({"files": []})
        
    db_subs, db_epub = get_db()
    files_data = []
    
    if media in ("all", "subs") and db_subs is not None:
        where, params = folder_prefix_where("relpath", folder)
        try:
            cur = db_subs.execute(f"SELECT relpath FROM sources WHERE {where} ORDER BY relpath ASC", params)
            for row in cur:
                relpath = row["relpath"]
                title = get_formatted_title(db_subs, relpath)
                files_data.append({
                    "file": relpath,
                    "title": title
                })
        except Exception:
            pass

    if not files_data and media in ("all", "epub") and db_epub is not None:
        where, params = folder_prefix_where("file", folder)
        try:
            from aobana import utils
            if utils.has_chapters(db_epub):
                cur_epub = db_epub.execute(
                    f"SELECT DISTINCT file FROM chapters WHERE {where} ORDER BY file ASC", params)
            else:
                cur_epub = db_epub.execute(
                    f"SELECT DISTINCT file FROM epubs WHERE {where} ORDER BY file ASC", params)
            for row in cur_epub:
                file_key = row["file"]
                title = format_book_title(file_key, db_epub=db_epub)
                files_data.append({
                    "file": file_key,
                    "title": title
                })
        except Exception:
            pass

    db_manga = get_manga_db()
    if not files_data and media in ("all", "manga") and db_manga is not None:
        from aobana.search.titles import format_manga_title
        try:
            for row in db_manga.execute(
                    "SELECT volume FROM sources WHERE title = ? ORDER BY relpath ASC", (folder,)):
                file_key = f"{folder}\\{row['volume']}"
                if not any(x["file"] == file_key for x in files_data):
                    files_data.append({"file": file_key, "title": format_manga_title(file_key)})
        except Exception:
            pass

    if files_data and any('話' in x['title'] for x in files_data):
        files_data.sort(key=lambda x: (
            1 if '話' in x['title'] else (0 if re.search(r'(?:Movie|Film|劇場版|映画|劇場|\[映\])', x['file'], re.IGNORECASE) else 1),
            x['file']
        ))
        
    return jsonify({"files": files_data})

@app.route("/api/context", methods=["GET"])
def api_context():
    rowid = request.args.get("rowid", type=int)
    file = request.args.get("file", "")
    q = request.args.get("q", "")
    media = request.args.get("media", "").strip().lower()
    
    db_subs, db_epub = get_db()
    db_manga = get_manga_db()
    if rowid is None:
        return jsonify({"error": "Missing rowid"}), 400

    if media not in ("subs", "epub", "manga") and db_manga is not None and file:
        if db_manga.execute("SELECT 1 FROM manga WHERE rowid = ? AND file = ?", (rowid, file)).fetchone():
            media = "manga"
    if media == "manga":
        return _manga_context(db_manga, rowid, file, q)

    if not file:
        if media == "epub" and db_epub is not None:
            r = db_epub.execute("SELECT file FROM epubs WHERE rowid = ?", (rowid,)).fetchone()
            if r:
                file = r["file"]
        elif media == "subs" and db_subs is not None:
            r = db_subs.execute("SELECT file FROM subtitles WHERE rowid = ?", (rowid,)).fetchone()
            if r:
                file = r["file"]
        else:
            if db_subs is not None:
                r = db_subs.execute("SELECT file FROM subtitles WHERE rowid = ?", (rowid,)).fetchone()
                if r:
                    file = r["file"]
                    media = "subs"
            if not file and db_epub is not None:
                r = db_epub.execute("SELECT file FROM epubs WHERE rowid = ?", (rowid,)).fetchone()
                if r:
                    file = r["file"]
                    media = "epub"

    if not file:
        return jsonify({"error": "Missing file or unknown rowid"}), 400

    def window(name, default):
        n = request.args.get(name, type=int)
        return default if n is None else max(0, min(10, n))
        
    rows = []
    
    is_epub = False
    if media == "epub":
        is_epub = True
    elif media == "subs":
        is_epub = False
    elif db_epub is not None:
        try:
            chk = db_epub.execute("SELECT 1 FROM epubs WHERE rowid = ? AND file = ?", (rowid, file)).fetchone()
            if chk:
                is_epub = True
        except Exception:
            pass

    if is_epub and db_epub is not None:
        try:
            cur = db_epub.execute("""
                SELECT rowid, line FROM epubs 
                WHERE rowid BETWEEN ? AND ? AND file = ? 
                  AND source_id = (SELECT source_id FROM epubs WHERE rowid = ?)
                ORDER BY rowid ASC
            """, (rowid - window("before", 3), rowid + window("after", 3), file, rowid))
            rows = cur.fetchall()
        except Exception:
            pass

    if not is_epub and db_subs is not None:
        query = """
            SELECT rowid, line FROM subtitles 
            WHERE rowid BETWEEN ? AND ? AND file = ? 
              AND source_id = (SELECT source_id FROM subtitles WHERE rowid = ?)
            ORDER BY rowid ASC
        """
        cur = db_subs.execute(query, (rowid - window("before", 4), rowid + window("after", 4), file, rowid))
        rows = cur.fetchall()
    
    from aobana.search.engine import analyze_query, split_negated_terms
    from aobana.search.furigana import highlight_and_furigana, work_key
    
    pos_q, _ = split_negated_terms(q)
    clean_q = pos_q.strip('""“”')
    content_bases, sql_bases, readings, base_groups = analyze_query(clean_q)
    
    context_html_lines = []
    for r in rows:
        line = r['line']
        hl_context = highlight_and_furigana(line, content_bases, clean_q, mark=True, bold=False, base_groups=base_groups, readings=readings, work=work_key("epub" if is_epub else "subs", file))
        context_html_lines.append(hl_context)
        
    html = '<div class="spacer"></div>'.join(context_html_lines)
    match = next((i for i, r in enumerate(rows) if r['rowid'] == rowid), None)
    text = None
    db = db_epub if is_epub else db_subs
    if match is not None and db is not None:
        r = db.execute(f"SELECT clean_text FROM {'epubs' if is_epub else 'subtitles'} WHERE rowid = ?",
                       (rowid,)).fetchone()
        text = r["clean_text"] if r else None
    return jsonify({"context": html, "lines": context_html_lines, "match": match, "text": text})

def _manga_context(db_manga, rowid, file, q):
    if db_manga is None:
        return jsonify({"error": "Missing file or unknown rowid"}), 400
    if not file:
        r = db_manga.execute("SELECT file FROM manga WHERE rowid = ?", (rowid,)).fetchone()
        file = r["file"] if r else ""
    if not file:
        return jsonify({"error": "Missing file or unknown rowid"}), 400

    def window(name, default):
        n = request.args.get(name, type=int)
        return default if n is None else max(0, min(10, n))

    rows = db_manga.execute("""
        SELECT rowid, line, clean_text FROM manga
        WHERE rowid BETWEEN ? AND ? AND file = ?
          AND source_id = (SELECT source_id FROM manga WHERE rowid = ?)
        ORDER BY rowid ASC
    """, (rowid - window("before", 4), rowid + window("after", 4), file, rowid)).fetchall()
    from aobana.search.engine import analyze_query, split_negated_terms
    from aobana.search.furigana import highlight_and_furigana, work_key
    pos_q, _ = split_negated_terms(q)
    clean_q = pos_q.strip('""“”')
    content_bases, _, readings, base_groups = analyze_query(clean_q)
    lines = [highlight_and_furigana(r['line'], content_bases, clean_q, mark=True, bold=False,
                                    base_groups=base_groups, readings=readings, work=work_key("manga", file))
             for r in rows]
    match = next((i for i, r in enumerate(rows) if r['rowid'] == rowid), None)
    text = rows[match]["clean_text"] if match is not None else None
    return jsonify({"context": '<div class="spacer"></div>'.join(lines), "lines": lines, "match": match, "text": text})


@app.route("/api/locate", methods=["GET"])
def api_locate():
    texts = [t.replace('\xa0', ' ').strip() for t in request.args.getlist("text") if t.strip()]
    media_req = request.args.get("media", "").strip().lower()
    if not texts:
        return jsonify({"error": "Missing text"}), 400
    db_subs, db_epub = get_db()
    db_manga = get_manga_db()
    if db_subs is None and db_epub is None and db_manga is None:
        return jsonify({"rows": []})

    from aobana.search.furigana import tagger
    from aobana.search.titles import title_of
    contains = " AND ".join(["instr(replace(clean_text, char(160), ' '), ?) > 0"] * len(texts))
    forms = []
    for text in texts:
        with tagger() as (tokenizer_obj, mode):
            words = tokenizer_obj.tokenize(text, mode)
        for word in words:
            form = word.normalized_form()
            if form and any(ch.isalnum() for ch in form) and form not in forms:
                forms.append(form)
    forms = sorted(forms, key=len, reverse=True)[:3]
    match = " AND ".join('base_forms:"%s"' % f.replace('"', '""') for f in forms) if forms else ""

    def query_corpus(db, table, media_type):
        if db is None:
            return []
        res = []
        if match:
            try:
                res = db.execute(
                    f"SELECT rowid, file, line, clean_text FROM {table} WHERE {table} MATCH ? AND "
                    + contains + " ORDER BY length(clean_text) LIMIT 500", (match, *texts)).fetchall()
            except sqlite3.OperationalError:
                res = []
        if not res:
            res = db.execute(
                f"SELECT rowid, file, line, clean_text FROM {table} WHERE " + contains
                + " ORDER BY length(clean_text) LIMIT 500",
                tuple(texts)).fetchall()
        out = []
        for r in res:
            title = title_of(media_type, r["file"], db, db)
            out.append({
                "rowid": r["rowid"],
                "file": r["file"],
                "line": r["line"],
                "clean_text": r["clean_text"],
                "title": title,
                "media_type": media_type
            })
        return out

    rows = []
    if media_req in ("", "all", "subs") and db_subs is not None:
        rows.extend(query_corpus(db_subs, "subtitles", "subs"))
    if media_req in ("", "all", "epub") and db_epub is not None:
        rows.extend(query_corpus(db_epub, "epubs", "epub"))
    if media_req in ("", "all", "manga") and db_manga is not None:
        rows.extend(query_corpus(db_manga, "manga", "manga"))

    rows.sort(key=lambda r: len(r.get("clean_text") or ""))
    return jsonify({"rows": rows[:500]})

@app.route("/api/relocate", methods=["POST"])
def api_relocate():
    _require_page()
    items = (request.get_json(silent=True) or {}).get("items", [])[:5000]
    db_subs, db_epub = get_db()
    db_manga = get_manga_db()
    from aobana.search.furigana import tagger
    ruby = re.compile(r'｜?([^()\s　（）]+)[（(][^()（）]*[)）]')
    out = []
    for it in items:
        is_book = it.get("media_type") == "epub"
        db, table = {"epub": (db_epub, "epubs"), "manga": (db_manga, "manga")}.get(
            it.get("media_type"), (db_subs, "subtitles"))
        line, rowid, file = it.get("line") or "", it.get("rowid"), it.get("file") or ""
        if db is None or not line or rowid is None:
            out.append(None)
            continue
        r = db.execute(f"SELECT file, line FROM {table} WHERE rowid = ?", (rowid,)).fetchone()
        if r and r["line"] == line and r["file"] == file:
            out.append(None)
            continue
        text = ruby.sub(r'\1', line).replace('｜', '').strip()
        forms = []
        with tagger() as (tokenizer_obj, mode):
            words = tokenizer_obj.tokenize(text, mode)
        for word in words:
            form = word.normalized_form()
            if form and any(ch.isalnum() for ch in form) and form not in forms:
                forms.append(form)
        forms = sorted(forms, key=len, reverse=True)[:3]
        rows = []
        if forms:
            try:
                rows = db.execute(
                    f"SELECT rowid, file, line FROM {table} WHERE {table} MATCH ? LIMIT 2000",
                    (" AND ".join('base_forms:"%s"' % f.replace('"', '""') for f in forms),)).fetchall()
            except sqlite3.OperationalError:
                rows = []
        work = lambda f: f.split("\\")[0] if is_book else f.replace("\\", "/").rsplit("/", 1)[0]
        same = [x for x in rows if x["line"] == line]
        best = (min(same, key=lambda x: (work(x["file"]) != work(file), abs(x["rowid"] - rowid))) if same else None)
        out.append({"rowid": best["rowid"], "file": best["file"]} if best else None)
    return jsonify({"items": out})


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


@app.route("/api/media", methods=["GET"])
def api_media():
    from aobana.search.media_tab import get_media_library, media_library_status, media_page
    db_subs, db_epub = get_db()
    db_manga = get_manga_db()
    status = media_library_status(db_subs, db_epub, db_manga)
    if not status["ready"]:
        return jsonify(status), 202
    folder = request.args.get("folder")
    page = media_page(get_media_library(db_subs, db_epub, db_manga),
                      media=request.args.get("media", "all"),
                      needle=request.args.get("q", ""),
                      offset=max(0, request.args.get("offset", 0, type=int)),
                      limit=max(0, request.args.get("limit", 0, type=int)),
                      folder=folder, sort=request.args.get("sort", "name"))
    page["ready"] = True
    return jsonify(page)


@app.route("/api/library", methods=["GET"])
def api_library():
    db_subs, db_epub = get_db()
    data = {**library.describe(db_subs, db_epub, get_manga_db()),
            "folder_picker": folder_picker.available(), "search_cache": _search_cache_facts()}
    library.save_settings_snapshot(data)
    return jsonify(data)


def _settings_payload():
    return {**library.settings_view_data(), "folder_picker": folder_picker.available(),
            "search_cache": _search_cache_facts()}


@app.route("/api/library/settings", methods=["GET"])
def api_library_settings():
    data = _settings_payload()
    library.save_settings_snapshot(data)
    return jsonify(data)


@app.route("/api/library/settings-snapshot", methods=["GET"])
def api_library_settings_snapshot():
    return jsonify({"settings": library.load_settings_snapshot()})


def _search_cache_facts():
    return {**result_cache.disk_cache_stats(), "on": result_cache.disk_cache_enabled()}


@app.route("/api/search-cache", methods=["POST"])
def api_search_cache_set():
    _require_page()
    library.set_search_cache((request.get_json(silent=True) or {}).get("on") is True)
    library.save_settings_snapshot(_settings_payload())
    return jsonify({"ok": True, "search_cache": _search_cache_facts()})


@app.route("/api/search-cache/clear", methods=["POST"])
def api_search_cache_clear():
    _require_page()
    ok = result_cache.clear_disk_cache()
    library.save_settings_snapshot(_settings_payload())
    return jsonify({"ok": ok, "search_cache": _search_cache_facts()})


@app.route("/api/library/figures", methods=["GET"])
def api_library_figures():
    return jsonify(library.figures())


@app.route("/api/activity", methods=["GET"])
def api_activity():
    return jsonify(library.activity())


@app.route("/api/activity/dismiss", methods=["POST"])
def api_activity_dismiss():
    _require_page()
    library.dismiss_notice((request.get_json(silent=True) or {}).get("id"))
    return jsonify({"ok": True})


@app.route("/api/library/outdated", methods=["GET"])
def api_library_outdated():
    db_subs, db_epub = get_db()
    db_manga = get_manga_db()
    needs = library.table_needs()
    has_database = any(os.path.isfile(p) and os.path.getsize(p) > 0
                       for p in (paths.subs_db(), paths.epub_db(), paths.manga_db()))
    return jsonify({"has_database": has_database,
                    "subs_outdated": outdated_sources(db_subs, "subs"),
                    "books_outdated": outdated_sources(db_epub, "epub"),
                    "manga_outdated": outdated_sources(db_manga, "manga"),
                    "subs_tables": needs["subs"], "books_tables": needs["epub"],
                    "manga_tables": needs["manga"]})


@app.route("/api/library", methods=["POST"])
def api_library_set():
    _require_page()
    body = request.get_json(silent=True) or {}
    if "db_dir" in body:
        error, files = library.move_databases(body.get("db_dir"))
        if error:
            return jsonify({"error": error, "files": files}), 400
        return jsonify({"ok": True, "started": True})
    if "media" in body:
        error = library.set_media(body.get("media") if isinstance(body.get("media"), dict) else {})
    elif "index_workers" in body:
        error = library.set_workers(body.get("index_workers"))
    elif "search_workers" in body:
        error = library.set_search_workers(body.get("search_workers"), body.get("search_worker_delay"))
    elif "port" in body:
        error = library.set_port(body.get("port"))
        if not error and not os.environ.get("AOBANA_PORT"):
            library.save_profile_handoff(int(str(body["port"]).strip()), PORT, body.get("profile"))
    else:
        error = library.set_folders(body.get("subs_dir"), body.get("books_dir"), body.get("manga_dir"))
    if error:
        return jsonify({"error": error}), 400
    library.save_settings_snapshot(_settings_payload())
    return jsonify({"ok": True})


@app.route("/api/library/move", methods=["GET"])
def api_library_move():
    return jsonify(library.move_status())


@app.route("/api/setup", methods=["POST"])
def api_setup():
    _require_page()
    body = request.get_json(silent=True) or {}
    media = body.get("media") if isinstance(body.get("media"), dict) else {}
    error = library.finish_setup(media, body.get("subs_dir"), body.get("books_dir"), body.get("manga_dir"))
    if error:
        return jsonify({"error": error}), 400
    return jsonify({"ok": True})


@app.route("/api/library/drop", methods=["POST"])
def api_library_drop():
    _require_page()
    error, kept = library.drop_index((request.get_json(silent=True) or {}).get("which"))
    if error:
        return jsonify({"error": error}), 400
    library.save_settings_snapshot(_settings_payload())
    return jsonify({"ok": True, "kept": kept})


@app.route("/api/profile-handoff", methods=["POST"])
def api_profile_handoff():
    _require_page()
    body = request.get_json(silent=True) or {}
    if "items" in body:
        library.refresh_profile_handoff(PORT, body["items"])
    elif "applied" in body:
        library.drop_profile_handoff(PORT, body["applied"])
    elif body.get("drop"):
        library.drop_profile_handoff(PORT)
    return jsonify({"ok": True})


_MANGA_PAGE_MISSING = """<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>露草</title>
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;font-family:system-ui,sans-serif;
background:#f6f5f2;color:#3a3a3a}@media (prefers-color-scheme:dark){body{background:#16181c;color:#c9ccd2}}
p{margin:.4em 1em;text-align:center}</style></head><body><div>
<p>このページの画像が見つかりません。</p><p lang="en">The image of this page was not found.</p>
</div></body></html>"""


@app.route("/manga/page/<int:rowid>", methods=["GET"])
def manga_page_image(rowid):
    image = library.manga_page_image_path(get_manga_db(), rowid)
    if not image:
        return make_response(_MANGA_PAGE_MISSING, 404, {"Content-Type": "text/html; charset=utf-8",
                                                        "Cache-Control": "no-store"})
    response = send_file(image, conditional=True, max_age=0)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.route("/api/library/open", methods=["POST"])
def api_library_open():
    _require_page()
    which = (request.get_json(silent=True) or {}).get("which")
    error = library.open_folder(which)
    if error:
        return jsonify({"error": error}), 400
    return jsonify({"ok": True})


@app.route("/api/reveal", methods=["POST"])
def api_reveal():
    _require_page()
    if ON_PHONE:
        return jsonify({"error": "phone"}), 400
    body = request.get_json(silent=True) or {}
    db_subs, db_epub = get_db()
    error = library.reveal(str(body.get("media") or ""), str(body.get("folder") or ""),
                           str(body.get("file") or ""), db_subs, db_epub, get_manga_db())
    if error:
        return jsonify({"error": error}), 400
    return jsonify({"ok": True})


@app.route("/api/library/pick", methods=["POST"])
def api_library_pick():
    _require_page()
    body = request.get_json(silent=True) or {}
    start = {"subs": paths.subs_dir, "books": paths.books_dir, "manga": paths.manga_dir,
             "data": paths.db_dir}.get(body.get("which"))
    try:
        start = start() if start else None
    except Exception:
        start = None
    status, path = folder_picker.pick(start, str(body.get("title") or "")[:200])
    return jsonify({"status": status, "path": path})


@app.route("/api/library/check-asked", methods=["POST"])
def api_library_check_asked():
    _require_page()
    library.mark_check_asked()
    return jsonify({"ok": True})


@app.route("/api/library/analyse", methods=["POST"])
def api_library_analyse():
    _require_page()
    only = (request.get_json(silent=True) or {}).get("only")
    started = library.start_analysis(only)
    return jsonify({"started": started, **library.analysis_status()})


@app.route("/api/library/analyse/stop", methods=["POST"])
def api_library_analyse_stop():
    _require_page()
    return jsonify({"stopping": library.stop_analysis(), **library.analysis_status()})


@app.route("/api/library/analysis", methods=["GET"])
def api_library_analysis():
    return jsonify({"status": library.analysis_status(), "report": library.analysis_report(),
                    "filtered": library.filtered_list()})


@app.route("/api/library/filter", methods=["POST"])
def api_library_filter():
    _require_page()
    ids = (request.get_json(silent=True) or {}).get("ids") or []
    try:
        ids = {int(i) for i in ids}
    except (TypeError, ValueError):
        return jsonify({"error": "bad_ids"}), 400
    error, result = library.filter_flagged(ids)
    if error:
        return jsonify({"error": error}), 400
    return jsonify({"ok": True, **result})


@app.route("/api/library/unfilter", methods=["POST"])
def api_library_unfilter():
    _require_page()
    entries = (request.get_json(silent=True) or {}).get("entries") or []
    try:
        entries = [(str(e["media"]), str(e["name"])) for e in entries]
    except (TypeError, KeyError):
        return jsonify({"error": "bad_entries"}), 400
    error, n = library.unfilter(entries)
    if error:
        return jsonify({"error": error}), 400
    return jsonify({"ok": True, "unfiltered": n})


@app.route("/api/library/estimate", methods=["GET"])
def api_library_estimate():
    return jsonify(library.estimate(request.args.get("only")))


@app.route("/api/index", methods=["POST"])
def api_index_start():
    _require_page()
    body = request.get_json(silent=True) or {}
    only = body.get("only")
    if isinstance(only, list):
        if not only or any(not isinstance(st, str) or st not in ("subs", "epub", "manga") for st in only):
            return jsonify({"error": "Invalid media selection."}), 400
    elif only not in ("subs", "epub", "manga"):
        only = None
    started = library.start_indexing(only, bool(body.get("outdated")),
                                     tables=bool(body.get("tables")), allow_removal=bool(body.get("allow_removal")))
    return jsonify({**library.index_status(), "started": started is True, "nothing": started == "nothing"})


@app.route("/api/index/stop", methods=["POST"])
def api_index_stop():
    _require_page()
    return jsonify({"stopping": library.stop_indexing(), **library.index_status()})


@app.route("/api/update", methods=["GET"])
def api_update():
    latest = update_info["latest"]
    newer = bool(latest) and version_tuple(latest) > version_tuple(VERSION)
    if request.args.get("waiting"):
        update_info["page_waiting"] = time.time()
    return jsonify({"checked": update_info["checked"], "current": VERSION, "latest": latest,
                    "newer": newer, "url": RELEASES_URL, "termux": TERMUX,
                    "self_update": SELF_UPDATE, "install_cmd": TERMUX_INSTALL,
                    "auto": bool(newer and updater.pick_asset(update_info["release"])),
                    "page_waiting": time.time() - update_info["page_waiting"] < 8})


UPDATE_EXIT_CODE = 75


@app.route("/api/update/apply", methods=["POST"])
def api_update_apply():
    _require_page()
    if not SELF_UPDATE:
        lang = str((request.get_json(silent=True) or {}).get("lang") or "en")
        error = updater.start(update_info["release"], lang, VERSION,
                              lambda: threading.Timer(1.0, os._exit, args=(0,)).start())
        if error:
            return jsonify({"error": error}), 400
        return jsonify({"ok": True})
    threading.Timer(0.5, os._exit, args=(UPDATE_EXIT_CODE,)).start()
    return jsonify({"ok": True})


@app.route("/api/update/status", methods=["GET"])
def api_update_status():
    return jsonify(updater.status)


release_notes = {}


def notable_changes(body):
    m = re.search(r"^###\s+Notable Changes\s*$(.*?)(?=^##|\Z)", body or "", re.M | re.S)
    if not m:
        return []
    return [line[2:].strip() for line in m.group(1).splitlines() if line.startswith("- ")]


@app.route("/api/release-notes", methods=["GET"])
def api_release_notes():
    if VERSION not in release_notes:
        release = update_info["release"]
        if not (release and str(release.get("tag_name") or "").lstrip("vV") == VERSION):
            release = None
            try:
                import json
                import urllib.request
                req = urllib.request.Request(f"{RELEASES_API}/tags/v{VERSION}", headers={
                    "Accept": "application/vnd.github+json", "User-Agent": f"Aobana/{VERSION}"})
                with urllib.request.urlopen(req, timeout=8) as resp:
                    release = json.load(resp)
            except Exception:
                pass
        if release:
            release_notes[VERSION] = {"notable": notable_changes(release.get("body")),
                                      "url": release.get("html_url") or RELEASES_URL}
    notes = release_notes.get(VERSION) or {"notable": [], "url": f"{RELEASES_TAG_URL}{VERSION}"}
    return jsonify({"version": VERSION, **notes})


@app.route("/api/changelog", methods=["GET"])
def api_changelog():
    here = paths.BASE_DIR
    for p in (os.path.join(here, "CHANGELOG.md"), os.path.join(here, "release", "public", "CHANGELOG.md")):
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                return jsonify({"version": VERSION, "text": f.read(), "url": RELEASES_URL})
    return jsonify({"version": VERSION, "text": None, "url": RELEASES_URL})


@app.route("/api/index/status", methods=["GET"])
def api_index_status():
    return jsonify(library.index_status())


DEBUG = paths.debug_mode()
PORT = paths.server_port()
app.config['TEMPLATES_AUTO_RELOAD'] = DEBUG

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
    start_background()
    app.run(host='127.0.0.1', port=PORT, debug=DEBUG, request_handler=_QuietRequestHandler)
