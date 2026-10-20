import os
from aobana.search import result_cache
from aobana.server import folder_picker
from aobana.server import library
from flask import jsonify, request
from aobana.server import app as server

app = server.app


@app.route("/api/library", methods=["GET"])
def api_library():
    db_subs, db_epub = server.get_db()
    data = {**library.describe(server._media_connections(db_subs, db_epub)),
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
    server._require_page()
    library.set_search_cache((request.get_json(silent=True) or {}).get("on") is True)
    library.save_settings_snapshot(_settings_payload())
    return jsonify({"ok": True, "search_cache": _search_cache_facts()})


@app.route("/api/search-cache/clear", methods=["POST"])
def api_search_cache_clear():
    server._require_page()
    ok = result_cache.clear_disk_cache()
    library.save_settings_snapshot(_settings_payload())
    return jsonify({"ok": ok, "search_cache": _search_cache_facts()})


@app.route("/api/library", methods=["POST"])
def api_library_set():
    server._require_page()
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
        error = library.set_search_workers(body.get("search_workers"))
    elif "subtitle_tags" in body:
        error = library.set_subtitle_tags(body.get("subtitle_tags"))
    elif "custom_trim" in body:
        error = library.set_custom_trim(body.get("custom_trim"))
    elif "custom_ruby" in body:
        error = library.set_custom_ruby(body.get("custom_ruby"))
    elif "port" in body:
        error = library.set_port(body.get("port"))
        if not error and not os.environ.get("AOBANA_PORT"):
            library.save_profile_handoff(int(str(body["port"]).strip()), server.PORT, body.get("profile"))
    else:
        error = library.set_folders(body.get("subs_dir"), body.get("books_dir"), body.get("manga_dir"),
                                    body.get("custom_dir"), body.get("subs_dirs"), body.get("books_dirs"),
                                    body.get("manga_dirs"), body.get("custom_dirs"))
    if error:
        return jsonify({"error": error}), 400
    library.save_settings_snapshot(_settings_payload())
    return jsonify({"ok": True})


@app.route("/api/library/move", methods=["GET"])
def api_library_move():
    return jsonify(library.move_status())


@app.route("/api/setup", methods=["POST"])
def api_setup():
    server._require_page()
    body = request.get_json(silent=True) or {}
    media = body.get("media") if isinstance(body.get("media"), dict) else {}
    error = library.finish_setup(media, body.get("subs_dir"), body.get("books_dir"), body.get("manga_dir"),
                                 body.get("custom_dir"))
    if error:
        return jsonify({"error": error}), 400
    return jsonify({"ok": True})


@app.route("/api/library/drop", methods=["POST"])
def api_library_drop():
    server._require_page()
    error, kept = library.drop_index((request.get_json(silent=True) or {}).get("which"))
    if error:
        return jsonify({"error": error}), 400
    library.save_settings_snapshot(_settings_payload())
    return jsonify({"ok": True, "kept": kept})


@app.route("/api/profile-handoff", methods=["POST"])
def api_profile_handoff():
    server._require_page()
    body = request.get_json(silent=True) or {}
    if "items" in body:
        library.refresh_profile_handoff(server.PORT, body["items"])
    elif "applied" in body:
        library.drop_profile_handoff(server.PORT, body["applied"])
    elif body.get("drop"):
        library.drop_profile_handoff(server.PORT)
    return jsonify({"ok": True})
