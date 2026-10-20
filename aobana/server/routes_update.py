import os
import re
import threading
import time
from aobana import paths
from aobana.server import updater
from flask import jsonify, request
from aobana.server import app as server

app = server.app


@app.route("/api/update", methods=["GET"])
def api_update():
    latest = server.update_info["latest"]
    newer = bool(latest) and server.version_tuple(latest) > server.version_tuple(server.VERSION)
    if request.args.get("waiting"):
        server.update_info["page_waiting"] = time.time()
    return jsonify({"checked": server.update_info["checked"], "current": server.VERSION, "latest": latest,
                    "newer": newer, "url": server.RELEASES_URL, "termux": server.TERMUX,
                    "self_update": server.SELF_UPDATE, "install_cmd": server.TERMUX_INSTALL,
                    "auto": bool(newer and updater.pick_asset(server.update_info["release"])),
                    "page_waiting": time.time() - server.update_info["page_waiting"] < 8})


UPDATE_EXIT_CODE = 75


@app.route("/api/update/apply", methods=["POST"])
def api_update_apply():
    server._require_page()
    if not server.SELF_UPDATE:
        lang = str((request.get_json(silent=True) or {}).get("lang") or "en")
        error = updater.start(server.update_info["release"], lang, server.VERSION,
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
    if server.VERSION not in release_notes:
        release = server.update_info["release"]
        if not (release and str(release.get("tag_name") or "").lstrip("vV") == server.VERSION):
            release = None
            try:
                import json
                import urllib.request
                req = urllib.request.Request(f"{server.RELEASES_API}/tags/v{server.VERSION}", headers={
                    "Accept": "application/vnd.github+json", "User-Agent": f"Aobana/{server.VERSION}"})
                with urllib.request.urlopen(req, timeout=8) as resp:
                    release = json.load(resp)
            except Exception:
                pass
        if release:
            release_notes[server.VERSION] = {"notable": notable_changes(release.get("body")),
                                      "url": release.get("html_url") or server.RELEASES_URL}
    notes = release_notes.get(server.VERSION) or {"notable": [], "url": f"{server.RELEASES_TAG_URL}{server.VERSION}"}
    return jsonify({"version": server.VERSION, **notes})


@app.route("/api/changelog", methods=["GET"])
def api_changelog():
    here = paths.BASE_DIR
    for p in (os.path.join(here, "CHANGELOG.md"), os.path.join(here, "release", "public", "CHANGELOG.md")):
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                return jsonify({"version": server.VERSION, "text": f.read(), "url": server.RELEASES_URL})
    return jsonify({"version": server.VERSION, "text": None, "url": server.RELEASES_URL})
