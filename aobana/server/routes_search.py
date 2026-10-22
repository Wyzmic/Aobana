import sqlite3
import threading
import time
from aobana import paths
from flask import jsonify, request
from aobana.server import app as server

app = server.app


@app.route("/api/capabilities", methods=["GET"])
def api_capabilities():
    from aobana.search import known_words
    return jsonify({"version": server.VERSION, "media_sets": True, "media": list(server.MEDIA_NAMES),
                    "known_words": {"schema": known_words.ENVELOPE, "version": known_words.ENVELOPE_VERSION}})


@app.route("/api/search", methods=["GET"])
def api_search():
    client_key = server._client_key()
    accepted_at = time.monotonic()
    server._keep_client(client_key)
    q = server.fold_compat(server.normalize_query(request.args.get("q", "")))
    sort = server.parse_sort(request.args.get("sort", "recommended"))
    folders = tuple(sorted(f for f in request.args.getlist("folder") if f))
    folder = folders[0] if len(folders) == 1 else (folders or None)
    pins = tuple(f for f in request.args.getlist("pin") if f)
    exact = request.args.get("exact") == "on"
    ruby_only = request.args.get("ruby_only") == "on"
    limit = request.args.get("limit", 500, type=int)
    offset = request.args.get("offset", 0, type=int)
    file_param = request.args.get("file", "")
    media = server.parse_media(request.args.get("media", "all"))
    seed = request.args.get("seed", type=int)
    learn = server._learn_param()
    if learn is None:
        return server._no_known_words()

    db_subs, db_epub = server.get_db()
    db_manga = server.get_manga_db()
    dbs = server._media_connections(db_subs, db_epub)
    if server._media_unavailable(media, dbs):
        return jsonify({
            "results": [], "folder_counts": {}, "global_total": 0, "all_folders": [],
            "has_more": False, "outside_media": list(dict.fromkeys([*folders, *pins]))
        })
    abort_flag = [False]
    search = server._search_identity(q, sort, seed, media, exact, folder, file_param, request.args.get("origin", ""), ruby_only, learn)
    mine = (search, abort_flag, dbs)

    with server.queries_lock:
        running = server.active_queries.get(client_key, [])
        if q:
            server._interrupt([r for r in running if r[0] != search])
        server.active_queries[client_key] = ([r for r in running if r[0] == search] if q else running) + [mine]

    info = {}
    try:
        results, folder_counts, global_total, all_folders, has_more = server.get_search_results(
            dbs, q, sort=sort, folder=folder, exact=exact,
            abort_flag=abort_flag, limit=limit, offset=offset, file=file_param,
            db_epub=db_epub, media=media, seed=seed, db_manga=db_manga, info=info,
            search_workers=paths.search_workers(), search_delay=paths.search_worker_delay(server.is_reading_search(q)),
            search_started=accepted_at, pins=pins, ruby_only=ruby_only, learn=learn
        )
        if abort_flag[0]:
            return jsonify({"aborted": True}), 499
    except sqlite3.OperationalError as e:
        if abort_flag[0] or "interrupted" in str(e):
            return jsonify({"aborted": True}), 499
        raise
    except server.StaleVocabulary:
        return server._no_known_words()
    finally:
        with server.queries_lock:
            left = [r for r in server.active_queries.get(client_key, []) if r is not mine]
            if left:
                server.active_queries[client_key] = left
            else:
                server.active_queries.pop(client_key, None)
    
    return jsonify({
        "results": results,
        "folder_counts": folder_counts,
        "global_total": global_total,
        "all_folders": all_folders,
        "has_more": has_more,
        "scoped": bool(info.get("scoped")),
        "outside_media": info.get("outside_media", []),
        "reading_words": [term.word for term in server.parse_reading_terms(q)[1]] if q else [],
        "reading_dropped": server.reading_fallback_words(q) if q else [],
        "learn": info.get("learn"),
    })

@app.route("/api/search/counts", methods=["GET"])
def api_search_counts():
    from aobana.search.engine import folder_match_counts
    client_key = server._client_key()
    accepted_at = time.monotonic()
    server._keep_client(client_key)
    q = server.fold_compat(server.normalize_query(request.args.get("q", "")))
    sort = server.parse_sort(request.args.get("sort", "recommended"))
    seed = request.args.get("seed", type=int)
    media = server.parse_media(request.args.get("media", "all"))
    exact = request.args.get("exact") == "on"
    ruby_only = request.args.get("ruby_only") == "on"
    if request.args.get("learn") == "only":
        return jsonify({"fallback": True})
    db_subs, db_epub = server.get_db()
    db_manga = server.get_manga_db()
    dbs = server._media_connections(db_subs, db_epub)
    if server._media_unavailable(media, dbs):
        return jsonify({"folder_counts": {}, "all_folders": [], "global_total": 0})
    abort_flag = [False]
    mine = (server._search_identity(q, sort, seed, media, exact, None, "", request.args.get("origin", ""), ruby_only,
                             server._learn_param() or ""), abort_flag, dbs)
    with server.queries_lock:
        server.active_queries.setdefault(client_key, []).append(mine)
    try:
        got = folder_match_counts(
            dbs, q, exact=exact, db_epub=db_epub, media=media,
            db_manga=db_manga, abort_flag=abort_flag,
            search_workers=paths.search_workers(), search_delay=paths.search_worker_delay(),
            search_started=accepted_at, sort=sort)
        if abort_flag[0]:
            return jsonify({"aborted": True}), 499
    except sqlite3.OperationalError as e:
        if abort_flag[0] or "interrupted" in str(e):
            return jsonify({"aborted": True}), 499
        raise
    finally:
        with server.queries_lock:
            left = [r for r in server.active_queries.get(client_key, []) if r is not mine]
            if left:
                server.active_queries[client_key] = left
            else:
                server.active_queries.pop(client_key, None)
    if got is None:
        return jsonify({"fallback": True})
    counts, order, total = got
    return jsonify({"folder_counts": counts, "all_folders": order, "global_total": total})


@app.route("/api/search/progress", methods=["GET"])
def api_search_progress():
    from aobana.search.engine import search_progress
    client_key = server._client_key()
    server._keep_client(client_key)
    db_subs, db_epub = server.get_db()
    db_manga = server.get_manga_db()
    q = server.fold_compat(server.normalize_query(request.args.get("q", "")))
    sort = server.parse_sort(request.args.get("sort", "recommended"))
    seed = request.args.get("seed", type=int)
    media = server.parse_media(request.args.get("media", "all"))
    exact = request.args.get("exact") == "on"
    ruby_only = request.args.get("ruby_only") == "on"
    folders = tuple(sorted(f for f in request.args.getlist("folder") if f))
    folder = folders[0] if len(folders) == 1 else (folders or None)
    file_param = request.args.get("file", "")
    abort_flag = [False]
    learn = server._learn_param() or ""
    mine = (server._search_identity(q, sort, seed, media, exact, folder, file_param, request.args.get("origin", ""), ruby_only,
                             learn), abort_flag, server._media_connections(db_subs, db_epub))
    with server.queries_lock:
        server.active_queries.setdefault(client_key, []).append(mine)
    try:
        return jsonify(search_progress(
            server._media_connections(db_subs, db_epub), db_epub, q, sort=sort, seed=seed, media=media, exact=exact,
            folder=folder, file=file_param or None, db_manga=db_manga,
            status_only=request.args.get("status") == "1", abort_flag=abort_flag,
            ruby_only=ruby_only, learn=learn))
    except sqlite3.OperationalError as e:
        if "interrupted" in str(e):
            return jsonify({"running": False, "aborted": True})
        raise
    finally:
        with server.queries_lock:
            left = [r for r in server.active_queries.get(client_key, []) if r is not mine]
            if left:
                server.active_queries[client_key] = left
            else:
                server.active_queries.pop(client_key, None)


CANCEL_GRACE_MAX = 60


@app.route("/api/search/cancel", methods=["POST"])
def api_search_cancel():
    server._require_page()
    client_key = server._client_key()
    body = request.get_json(silent=True) or {}
    try:
        grace = min(max(float(body.get("grace", 0)), 0), CANCEL_GRACE_MAX)
    except (TypeError, ValueError):
        grace = 0
    if not grace:
        server._cancel_client(client_key)
        return jsonify({"ok": True})
    timer = threading.Timer(grace, server._cancel_client, args=(client_key,))
    timer.daemon = True
    with server.queries_lock:
        old = server.pending_cancels.pop(client_key, None)
        server.pending_cancels[client_key] = timer
    if old is not None:
        old.cancel()
    timer.start()
    return jsonify({"ok": True, "grace": grace})
