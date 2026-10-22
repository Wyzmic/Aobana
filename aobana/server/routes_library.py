import os
import sqlite3
from aobana import paths
from aobana.server import folder_picker
from aobana.server import library
from flask import jsonify, request
from aobana.server import app as server

app = server.app


@app.route("/api/library/figures", methods=["GET"])
def api_library_figures():
    return jsonify(library.figures())


@app.route("/api/activity", methods=["GET"])
def api_activity():
    return jsonify(library.activity())


@app.route("/api/activity/dismiss", methods=["POST"])
def api_activity_dismiss():
    server._require_page()
    library.dismiss_notice((request.get_json(silent=True) or {}).get("id"))
    return jsonify({"ok": True})


def _outdated(conn, media):
    if conn is not None:
        try:
            conn.execute("SELECT count(*) FROM sources").fetchone()
        except sqlite3.OperationalError as error:
            if server.index_busy(error):
                raise
    return server.outdated_sources(conn, media)


@app.route("/api/library/outdated", methods=["GET"])
def api_library_outdated():
    db_subs, db_epub = server.get_db()
    db_manga = server.get_manga_db()
    needs = library.table_needs()
    has_database = any(os.path.isfile(p) and os.path.getsize(p) > 0
                       for p in (paths.subs_db(), paths.epub_db(), paths.manga_db(), paths.custom_db()))
    return jsonify({"has_database": has_database,
                    "subs_outdated": _outdated(db_subs, "subs"),
                    "books_outdated": _outdated(db_epub, "epub"),
                    "manga_outdated": _outdated(db_manga, "manga"),
                    "custom_outdated": _outdated(server.get_custom_db(), 'custom'),
                    "subs_tables": needs["subs"], "books_tables": needs["epub"],
                    "manga_tables": needs["manga"], "custom_tables": needs.get("custom", [])})


@app.route("/api/library/open", methods=["POST"])
def api_library_open():
    server._require_page()
    which = (request.get_json(silent=True) or {}).get("which")
    error = library.open_folder(which, (request.get_json(silent=True) or {}).get('index', 0))
    if error:
        return jsonify({"error": error}), 400
    return jsonify({"ok": True})


@app.route("/api/reveal", methods=["POST"])
def api_reveal():
    server._require_page()
    if server.ON_PHONE:
        return jsonify({"error": "phone"}), 400
    body = request.get_json(silent=True) or {}
    if body.get("check"):
        error = library.reveal_check(str(body.get("media") or ""), str(body["check"]))
        return (jsonify({"error": error}), 400) if error else jsonify({"ok": True})
    db_subs, db_epub = server.get_db()
    error = library.reveal(str(body.get("media") or ""), str(body.get("folder") or ""),
                           str(body.get("file") or ""), server._media_connections(db_subs, db_epub))
    if error:
        return jsonify({"error": error}), 400
    return jsonify({"ok": True})


@app.route("/api/library/pick", methods=["POST"])
def api_library_pick():
    server._require_page()
    body = request.get_json(silent=True) or {}
    start = {"subs": paths.subs_dir, "books": paths.books_dir, "manga": paths.manga_dir, "custom": paths.custom_dir,
             "data": paths.db_dir}.get(body.get("which"))
    try:
        which, index = body.get('which'), body.get('index', 0)
        if which in paths.MEDIA_KINDS and type(index) is int:
            roots = paths.media_roots(which)
            start = roots[index] if 0 <= index < len(roots) else None
        else:
            start = start() if start else None
    except Exception:
        start = None
    status, path = folder_picker.pick(start, str(body.get("title") or "")[:200])
    return jsonify({"status": status, "path": path})


@app.route("/api/library/check-asked", methods=["POST"])
def api_library_check_asked():
    server._require_page()
    library.mark_check_asked()
    return jsonify({"ok": True})


@app.route("/api/library/findings-asked", methods=["POST"])
def api_library_findings_asked():
    server._require_page()
    key = (request.get_json(silent=True) or {}).get("key")
    if not isinstance(key, str) or not key:
        return jsonify({"error": "no key"}), 400
    library.mark_findings_asked(key)
    return jsonify({"ok": True})


@app.route("/api/library/analyse", methods=["POST"])
def api_library_analyse():
    server._require_page()
    only = (request.get_json(silent=True) or {}).get("only")
    started = library.start_analysis(only)
    return jsonify({"started": started, **library.analysis_status()})


@app.route("/api/library/analyse/stop", methods=["POST"])
def api_library_analyse_stop():
    server._require_page()
    return jsonify({"stopping": library.stop_analysis(), **library.analysis_status()})


def _media_on():
    asked = request.args.get("media")
    kinds = ('subs', 'epub', 'manga', 'custom')
    return kinds if asked is None else tuple(m for m in asked.split(",") if m in kinds)


@app.route("/api/library/analysis", methods=["GET"])
def api_library_analysis():
    status = library.analysis_status()
    if request.args.get("status"):
        return jsonify({"status": status, "has_report": library.has_report(),
                        "check_asked": library.check_asked()})
    if status.get("running"):
        return jsonify({"status": status})
    try:
        summary = library.analysis_summary(_media_on())
    except RuntimeError as error:
        return jsonify({"status": status, "error": str(error)})
    report = summary["report"]
    roots = {media: paths.roots_value(media) for media in ('subs', 'epub', 'manga', 'custom')}
    valid = bool(report) and all(paths.same_roots(roots.get(media), root)
                                for media,root in report.get('roots',{}).items())
    return jsonify({"status": status, "report": report, "filtered": summary["filtered"],
                    "view": summary["view"], "current_roots": roots,
                    "data_dir":paths.db_dir(), "backups_dir": paths.backups_dir('encoding'),
                    "selection_valid":valid, "findings_asked": library.findings_asked()})


@app.route("/api/library/analysis/page", methods=["GET"])
def api_library_analysis_page():
    try:
        start = max(0, int(request.args.get("offset", 0)))
    except ValueError:
        return jsonify({"error": "bad_offset"}), 400
    rows = library.analysis_page(str(request.args.get("section") or ""), start, _media_on(),
                                 str(request.args.get("view") or ""))
    return jsonify({"stale": True} if rows is None else {"rows": rows})


@app.route("/api/library/analysis/keys", methods=["GET"])
def api_library_analysis_keys():
    keys = library.analysis_keys(str(request.args.get("section") or ""), _media_on(),
                                 str(request.args.get("view") or ""))
    return jsonify({"stale": True} if keys is None else {"keys": keys})


@app.route("/api/library/filter", methods=["POST"])
def api_library_filter():
    server._require_page()
    body = request.get_json(silent=True) or {}
    ids = body.get("ids") or []
    try:
        ids = {int(i) for i in ids}
    except (TypeError, ValueError):
        return jsonify({"error": "bad_ids"}), 400
    error, result = library.save_choices(ids, body.get('generation'), body.get('choices') or [])
    if error:
        return jsonify({"error": error}), 400
    return jsonify({"ok": True, **result})


@app.route('/api/library/filter/progress')
def api_library_filter_progress():
    return jsonify(library.save_progress())


@app.route('/api/library/repair', methods=['POST'])
def api_subtitle_repair():
    server._require_page()
    body = request.get_json(silent=True) or {}
    try:
        header = library.check_view()
    except RuntimeError as error:
        return jsonify({'error':str(error)}), 400
    report = (header or {}).get('report')
    if not report or report.get('generation') != body.get('generation'):
        return jsonify({'error':'stale_report'}), 400
    try:
        pending = library.save_subtitle_refresh(dict(report['repair_meta'], items=library.view_section_rows(header, 'repair-doc')))
    except (ValueError, OSError, KeyError, RuntimeError) as error:
        return jsonify({'error':str(error)}), 400
    return jsonify({'saved':pending,'started':False})


@app.route('/api/library/encoding-repair', methods=['POST'])
def api_encoding_repair():
    server._require_page()
    body = request.get_json(silent=True) or {}
    try:
        header = library.check_view()
    except RuntimeError as error:
        return jsonify({'error':str(error)}),400
    report = (header or {}).get('report')
    if not report or report.get('generation') != body.get('generation'):
        return jsonify({'error':'stale_report'}),400
    try:
        started = library.start_encoding_repair(dict(report, items=library.view_section_rows(header, 'find:subs:encoding')))
    except (ValueError,OSError,RuntimeError) as error:
        return jsonify({'error':str(error)}),400
    return jsonify({'started':started, 'status':library.analysis_status()})


@app.route("/api/library/unfilter", methods=["POST"])
def api_library_unfilter():
    server._require_page()
    entries = (request.get_json(silent=True) or {}).get("entries") or []
    try:
        entries = [(str(e["media"]), str(e["name"])) for e in entries]
    except (TypeError, KeyError):
        return jsonify({"error": "bad_entries"}), 400
    error, n = library.unfilter(entries)
    if error:
        return jsonify({"error": error}), 400
    return jsonify({"ok": True, "unfiltered": n})


@app.route("/api/library/keep-left-out", methods=["POST"])
def api_library_keep_left_out():
    server._require_page()
    entries = (request.get_json(silent=True) or {}).get("entries") or []
    try:
        entries = [(str(e["media"]), str(e["name"])) for e in entries]
    except (TypeError, KeyError):
        return jsonify({"error": "bad_entries"}), 400
    error, n = library.keep_left_out(entries)
    if error:
        return jsonify({"error": error}), 400
    return jsonify({"ok": True, "kept": n})


@app.route("/api/library/estimate", methods=["GET"])
def api_library_estimate():
    return jsonify(library.estimate(request.args.get("only")))


@app.route("/api/index", methods=["POST"])
def api_index_start():
    server._require_page()
    body = request.get_json(silent=True) or {}
    only = body.get("only")
    if isinstance(only, list):
        if not only or any(not isinstance(st, str) or st not in ("subs", "epub", "manga", "custom") for st in only):
            return jsonify({"error": "Invalid media selection."}), 400
    elif only not in ("subs", "epub", "manga", "custom"):
        only = None
    started = library.start_indexing(only, bool(body.get("outdated")),
                                     tables=bool(body.get("tables")), allow_removal=bool(body.get("allow_removal")))
    return jsonify({**library.index_status(), "started": started is True, "nothing": started == "nothing"})


@app.route("/api/index/stop", methods=["POST"])
def api_index_stop():
    server._require_page()
    return jsonify({"stopping": library.stop_indexing(), **library.index_status()})


@app.route("/api/index/status", methods=["GET"])
def api_index_status():
    return jsonify(library.index_status())
