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
        if request.args.get("shown"):
            server.update_info["page_shown"] = time.time()
    return jsonify({"checked": server.update_info["checked"], "current": server.VERSION, "latest": latest,
                    "newer": newer, "url": server.RELEASES_URL, "termux": server.TERMUX,
                    "self_update": server.SELF_UPDATE, "install_cmd": server.TERMUX_INSTALL,
                    "auto": bool(newer and updater.pick_asset(server.update_info["release"])),
                    "page_waiting": time.time() - server.update_info["page_waiting"] < 8,
                    "page_shown": time.time() - server.update_info["page_shown"] < 8})


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


HOLD_BEAT = 60
_ALIVE = {"pages": set(), "holds": 0, "quitting": False, "at": "/", "written": None}
_ALIVE_LOCK = threading.Lock()


def _page_address(value):
    at = str(value or "")
    if not at.startswith("/") or at.startswith("//") or len(at) > 1500:
        return None
    if any(ord(c) < 33 or ord(c) == 127 for c in at) or "'" in at or '"' in at or "\\" in at:
        return None
    return at


def _last_place():
    try:
        with open(paths.KEPT_TAB_PATH, encoding="utf-8") as f:
            at = _page_address(f.readline().rstrip("\n"))
    except (OSError, UnicodeDecodeError):
        return
    if at:
        _ALIVE["at"] = at
        _ALIVE["written"] = at + "\n"


_last_place()


def _write_note():
    text = _ALIVE["at"] + "\n"
    if _ALIVE["written"] == text and os.path.exists(paths.KEPT_TAB_PATH):
        return
    tmp = paths.KEPT_TAB_PATH + ".new"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, paths.KEPT_TAB_PATH)
    _ALIVE["written"] = text


def _sync_kept_tab():
    if _ALIVE["quitting"]:
        return
    try:
        if _ALIVE["pages"]:
            _write_note()
        elif os.path.exists(paths.KEPT_TAB_PATH):
            os.remove(paths.KEPT_TAB_PATH)
            _ALIVE["written"] = None
    except OSError:
        pass


def _note_place(value):
    at = _page_address(value)
    if at:
        with _ALIVE_LOCK:
            _ALIVE["at"] = at
            _sync_kept_tab()


def _add_pages(value):
    pages = {p[:40] for p in str(value or "").split(",") if p}
    with _ALIVE_LOCK:
        _ALIVE["pages"] |= pages
        _sync_kept_tab()
    server.update_info["page_waiting"] = time.time()


@app.route("/api/alive", methods=["GET", "POST"])
def api_alive():
    if request.method == "POST":
        if request.values.get("hidden"):
            _note_place(request.values.get("at"))
            return ("", 204)
        with _ALIVE_LOCK:
            _ALIVE["pages"].discard(str(request.values.get("page") or "")[:40])
            _sync_kept_tab()
        return ("", 204)
    if request.values.get("shown"):
        _note_place(request.values.get("at"))
    _add_pages(request.values.get("page"))
    if request.values.get("shown"):
        server.update_info["page_shown"] = time.time()
    return ("", 204, {"X-Aobana-Assets": server._asset_v(), "Cache-Control": "no-store"})


@app.route("/api/alive/hold", methods=["GET"])
def api_alive_hold():
    _add_pages(request.args.get("pages"))

    def stream():
        with _ALIVE_LOCK:
            _ALIVE["holds"] += 1
        try:
            yield b" "
            while True:
                time.sleep(HOLD_BEAT)
                yield b" "
        finally:
            with _ALIVE_LOCK:
                _ALIVE["holds"] -= 1
                if not _ALIVE["holds"]:
                    _ALIVE["pages"].clear()
                    _sync_kept_tab()
    return server.app.response_class(stream(), mimetype="text/plain",
                                     headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


QUIT_WAIT = 30


@app.route("/api/quit", methods=["POST"])
def api_quit():
    server._require_page()
    from aobana.server import library
    if library._STATE.get("moving"):
        return jsonify({"error": "moving"}), 409
    keep = (request.get_json(silent=True) or {}).get("keep") is True
    with _ALIVE_LOCK:
        if not keep:
            _ALIVE["at"] = "/"
        if keep or server.ON_PHONE:
            _ALIVE["quitting"] = True
            try:
                _write_note()
            except OSError:
                pass
        else:
            _sync_kept_tab()
    stopping = bool(library.stop_indexing()) | bool(library.stop_analysis())

    def leave():
        end = time.monotonic() + (QUIT_WAIT if stopping else 0)
        while time.monotonic() < end and library.busy_reason():
            time.sleep(0.2)
        time.sleep(1.0)
        os._exit(0)
    threading.Thread(target=leave, daemon=True).start()
    return jsonify({"ok": True, "stopping": stopping})


@app.route("/api/update/status", methods=["GET"])
def api_update_status():
    with updater._lock:
        return jsonify(dict(updater.status))


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
