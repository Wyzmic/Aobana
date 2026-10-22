import sqlite3
from flask import jsonify, request
from aobana.server import app as server

app = server.app


def _media_request(conn, work, unknown):
    from aobana.search.custom import Stopped
    key = 'media:' + server._client_key()
    stop = [False]
    mine = (None, stop, {'custom': conn})
    with server.queries_lock:
        server._interrupt(server.active_queries.get(key, []))
        server.active_queries[key] = [mine]
    try:
        data = work(stop)
    except Stopped:
        return jsonify({'aborted': True}), 499
    except sqlite3.OperationalError as e:
        # Stopped while FTS5 opened its table, the interrupt reads "vtable constructor failed"
        if stop[0] or 'interrupted' in str(e):
            return jsonify({'aborted': True}), 499
        raise
    finally:
        with server.queries_lock:
            if server.active_queries.get(key) == [mine]:
                server.active_queries.pop(key, None)
    return (jsonify(data), 200) if data is not None else (jsonify({'error': unknown}), 404)


@app.route('/api/custom/folder')
def api_custom_folder():
    from aobana.search.custom import folder_page
    conn = server.get_custom_db()
    if conn is None:
        return jsonify({'items': [], 'total': 0, 'has_more': False})
    args = request.args
    # The query as /api/search reads it: `ー` the minus, `- ない` one word, 者 (U+FA5B) as 者 (audit 13, A13-01)
    q = server.fold_compat(server.normalize_query(args.get('q', '')))
    return _media_request(conn, lambda stop: folder_page(
        conn, args.get('path', ''), q, args.get('mode', 'title'),
        max(0, args.get('offset', 0, type=int)), max(1, min(500, args.get('limit', 500, type=int))),
        args.get('exact') == 'on', args.get('ruby_only') == 'on', args.get('sort', 'default'), stop), 'Unknown folder')


@app.route('/api/custom/file')
def api_custom_file():
    from aobana.search.custom import file_page
    conn = server.get_custom_db()
    if conn is None:
        return jsonify({'error': 'Unknown file'}), 404
    args = request.args
    # A .txt or .md comes a page at a time: from `offset`, around line `at`, or just above `before`
    q = server.fold_compat(server.normalize_query(args.get('q', '')))
    return _media_request(conn, lambda stop: file_page(
        conn, args.get('file', ''), q,
        args.get('exact') == 'on', args.get('ruby_only') == 'on', stop,
        offset=max(0, args.get('offset', 0, type=int)), limit=max(1, min(2000, args.get('limit', 500, type=int))),
        at=args.get('at', type=int), before=args.get('before', type=int), heading=args.get('heading', '').strip()), 'Unknown file')


@app.route("/api/media", methods=["GET"])
def api_media():
    from aobana.search.media_tab import get_media_library, media_library_status, media_page
    db_subs, db_epub = server.get_db()
    db_manga = server.get_manga_db()
    dbs = server._media_connections(db_subs, db_epub)
    status = media_library_status(dbs)
    if not status["ready"]:
        return jsonify(status), 202
    folder = request.args.get("folder")
    page = media_page(get_media_library(dbs),
                      media=request.args.get("media", "all"),
                      needle=server.normalize_query(request.args.get("q", "")),
                      offset=max(0, request.args.get("offset", 0, type=int)),
                      limit=max(0, request.args.get("limit", 0, type=int)),
                      folder=folder, sort=request.args.get("sort", "name"))
    page["ready"] = True
    return jsonify(page)


@app.route("/api/folder-authors", methods=["GET"])
def api_folder_authors():
    from aobana.search.media_tab import get_media_library, media_library_status
    db_subs, db_epub = server.get_db()
    db_manga = server.get_manga_db()
    dbs = server._media_connections(db_subs, db_epub)
    if not media_library_status(dbs)["ready"]:
        return jsonify({"ready": False, "authors": {}})
    authors = {}
    for it in get_media_library(dbs):
        if it["media"] == "epub" and it["author"]:
            authors[it["folder"]] = it["author"]
    return jsonify({"ready": True, "authors": authors})
