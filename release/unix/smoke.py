"""Start a built Aobana the way a user does, index a tiny library through the Library tab's API,
and search it. Exit 0 only if the subtitle, the book, the manga line and both Custom lines (a
.txt and a .md) all come back.

    python release/unix/smoke.py <command that starts Aobana> [args...]

Runs with any Python 3 (stdlib only), not the bundled one: it tests the build from outside.
Everything the app writes goes into one temporary folder (HOME, the data folder, the media).
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


PORT = free_port()
BASE = f"http://127.0.0.1:{PORT}"
SRT_LINE = "猫が屋根の上で昼寝をしている"
BOOK_LINE = "図書館で古い地図を見つけた。"
MANGA_LINES = ["その傘は誰のだ？", "駅前で拾ったんだ．．．"]
TXT_LINE = "庭の桜が満開になった。"
MD_LINE = "川の向こうに灯台が見える。"


def make_library(root):
    subs = os.path.join(root, "media", "字幕")
    books = os.path.join(root, "media", "書籍")
    os.makedirs(os.path.join(subs, "テスト番組"))
    os.makedirs(books)
    with open(os.path.join(subs, "テスト番組", "テスト番組 01.srt"), "w", encoding="utf-8") as fh:
        fh.write(f"1\n00:00:01,000 --> 00:00:03,000\n{SRT_LINE}\n\n"
                 "2\n00:00:04,000 --> 00:00:06,000\nそろそろ帰ろう\n")
    with zipfile.ZipFile(os.path.join(books, "テスト本.epub"), "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip")
        z.writestr("META-INF/container.xml",
                   '<?xml version="1.0"?><container version="1.0" '
                   'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
                   '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
                   "</rootfiles></container>")
        z.writestr("OEBPS/content.opf",
                   '<?xml version="1.0" encoding="utf-8"?><package xmlns="http://www.idpf.org/2007/opf" '
                   'version="3.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
                   '<dc:identifier id="id">smoke</dc:identifier><dc:title>テスト本</dc:title>'
                   "<dc:language>ja</dc:language></metadata><manifest>"
                   '<item id="c1" href="c1.xhtml" media-type="application/xhtml+xml"/></manifest>'
                   '<spine><itemref idref="c1"/></spine></package>')
        z.writestr("OEBPS/c1.xhtml",
                   '<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml">'
                   f"<head><title>一</title></head><body><p>{BOOK_LINE}</p>"
                   "<p>それは祖父のものだった。</p></body></html>")
    manga = os.path.join(root, "media", "漫画")
    os.makedirs(os.path.join(manga, "テスト漫画"))
    page = {"img_width": 1000, "img_height": 1500, "blocks": [
        {"box": [700, 100, 760, 400], "vertical": True, "lines": [MANGA_LINES[0]]},
        {"box": [300, 100, 360, 400], "vertical": True, "lines": [MANGA_LINES[1]]}]}
    with open(os.path.join(manga, "テスト漫画", "テスト漫画 01.mokuro"), "w", encoding="utf-8") as fh:
        json.dump({"version": "0.2.5", "title": "テスト漫画", "volume": "テスト漫画 01",
                   "pages": [dict(page, img_path="001.jpg")]}, fh, ensure_ascii=False)
    custom = os.path.join(root, "media", "カスタム")
    os.makedirs(os.path.join(custom, "テスト"))
    with open(os.path.join(custom, "テスト", "日記.txt"), "w", encoding="utf-8") as fh:
        fh.write(f"{TXT_LINE}\n風が少し冷たい。\n")
    with open(os.path.join(custom, "テスト", "ノート.md"), "w", encoding="utf-8") as fh:
        fh.write(f"# 第一章\n\n{MD_LINE}\n\n夜になると光る。\n")
    return subs, books, manga, custom


def get(path, timeout=10):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def post(path):
    req = urllib.request.Request(BASE + path, data=b"{}", method="POST",
                                 headers={"Content-Type": "application/json", "X-Aobana": "1"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def wait_for(what, check, timeout):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            value = check()
            if value:
                return value
        except (OSError, urllib.error.URLError, ValueError):
            pass
        time.sleep(1)
    sys.exit(f"smoke: timed out waiting for {what}")


def update_check_ok(update, network_available):
    return bool(update.get('checked') and (update.get('latest') or not network_available))


def release_network_available():
    try:
        req = urllib.request.Request('https://api.github.com/repos/Wyzmic/Aobana/releases/latest',
                                     headers={'User-Agent': 'Aobana-smoke'})
        with urllib.request.urlopen(req, timeout=10):
            return True
    except urllib.error.HTTPError as error:
        return error.code not in (403, 429)
    except (OSError, urllib.error.URLError):
        return False


def main(cmd):
    root = tempfile.mkdtemp(prefix="aobana-smoke-")
    subs, books, manga, custom = make_library(root)
    env = dict(os.environ, HOME=os.path.join(root, "home"), AOBANA_DATA_DIR=os.path.join(root, "data"),
               SUBS_ROOT_DIR=subs, EPUB_ROOT_DIR=books, MANGA_ROOT_DIR=manga, CUSTOM_ROOT_DIR=custom,
               AOBANA_PORT=str(PORT), AOBANA_DEBUG="0",
               AOBANA_NO_TERMINAL="1", BROWSER="true", PYTHONIOENCODING="utf-8")
    os.makedirs(env["HOME"])
    os.makedirs(env["AOBANA_DATA_DIR"])
    with open(os.path.join(env["AOBANA_DATA_DIR"], "config.json"), "w", encoding="utf-8") as fh:
        json.dump({"media": {"subs": True, "books": True, "manga": True, "custom": True}}, fh)
    log = open(os.path.join(root, "server.log"), "w", encoding="utf-8")
    print(f"smoke: {' '.join(cmd)}", flush=True)
    proc = subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    ok = False
    try:
        wait_for("the server", lambda: get("/api/library"), 120)
        print("smoke: server answers", flush=True)
        post("/api/index")
        status = wait_for("indexing", lambda: (lambda s: s if not s.get("running") else None)(
            get("/api/index/status")), 600)
        if status.get("error") or status.get("failed"):
            sys.exit(f"smoke: indexing failed: {status.get('error')} {status.get('failed')}")
        print(f"smoke: indexed {json.dumps(status.get('results'), ensure_ascii=False)}", flush=True)
        q = urllib.request.quote
        subs_hits = get(f"/api/search?q={q('昼寝')}&media=subs")["results"]
        book_hits = get(f"/api/search?q={q('地図')}&media=epub")["results"]
        manga_hits = get(f"/api/search?q={q('傘')}&media=manga")["results"]
        txt_hits = get(f"/api/search?q={q('桜')}&media=custom")["results"]
        md_hits = get(f"/api/search?q={q('灯台')}&media=custom")["results"]
        print(f"smoke: 昼寝 -> {len(subs_hits)} subtitle line(s), 地図 -> {len(book_hits)} book sentence(s), "
              f"傘 -> {len(manga_hits)} manga line(s), 桜 -> {len(txt_hits)} and 灯台 -> {len(md_hits)} "
              "Custom line(s)")
        update = wait_for("the update check", lambda: (lambda u: u if u.get("checked") else None)(
            get("/api/update")), 30)
        print(f"smoke: /api/update current {update['current']}, latest {update['latest']}")
        page = urllib.request.urlopen(BASE + "/", timeout=10).read().decode("utf-8")
        ok = (bool(subs_hits) and bool(book_hits) and bool(manga_hits) and bool(txt_hits) and bool(md_hits)
              and "露草" in page)
        network = bool(update.get('latest')) or release_network_available()
        if not update_check_ok(update, network):
            print('smoke: FAIL update check finished with network but no latest release')
            ok = False
        elif not network:
            print('smoke: SKIP latest-release assertion: release endpoint is unreachable')
        stray = [n for n in ("subs.db", "epub.db", "manga.db", "custom.db")
                 if not os.path.exists(os.path.join(env["AOBANA_DATA_DIR"], "db", n))]
        if stray:
            print(f"smoke: {stray} not in the data folder's db folder: the build does not use the installed layout")
            ok = False
    finally:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        else:
            try:
                os.killpg(proc.pid, 15)
            except OSError:
                proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()
        if not ok:
            print("---- server log ----")
            print(open(os.path.join(root, "server.log"), encoding="utf-8", errors="replace").read())
        shutil.rmtree(root, ignore_errors=True)
    print("smoke: PASS" if ok else "smoke: FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1:]))
