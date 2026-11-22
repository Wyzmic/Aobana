import re
import sqlite3
from aobana.server import library
from flask import g, jsonify, make_response, request, send_file
from aobana.server import app as server

app = server.app


def _custom_context(conn, rowid, file, q):
    from aobana.search.custom import context_page
    def window(name):
        n = request.args.get(name, type=int)
        return 3 if n is None else max(0, min(10, n))
    return jsonify(context_page(conn, rowid, file, q, window('before'), window('after'))
                   if conn is not None else {'lines': [], 'focus_index': 0})

@app.route("/api/episodes", methods=["GET"])
def api_episodes():
    folder = request.args.get("folder", "")
    media = request.args.get("media", "all")
    if not folder:
        return jsonify({"files": []})
        
    db_subs, db_epub = server.get_db()
    files_data = []
    
    if media in ("all", "subs") and db_subs is not None:
        where, params = server.folder_prefix_where("relpath", folder)
        try:
            from aobana.indexing import source_ranges
            count_sql = (", (SELECT COALESCE(SUM(lines),0) FROM source_ranges WHERE source_id=sources.id) AS lines"
                         if source_ranges.ready(db_subs) else "")
            cur = db_subs.execute(f"SELECT relpath{count_sql} FROM sources WHERE {where} ORDER BY relpath ASC", params)
            for row in cur:
                relpath = row["relpath"]
                title = server.get_formatted_title(db_subs, relpath)
                item = {
                    "file": relpath,
                    "title": title,
                    "subfolders": re.split(r"[\\/]", relpath)[1:-1],
                }
                if count_sql:
                    item["lines"] = row["lines"]
                files_data.append(item)
        except Exception:
            pass

    book_chapters = False
    if not files_data and media in ("all", "epub") and db_epub is not None:
        where, params = server.folder_prefix_where("file", folder)
        try:
            from aobana import utils
            if utils.has_chapters(db_epub):
                folder_sql = "MAX(folder)" if utils.has_chapter_folder(db_epub) else "NULL"
                cur_epub = db_epub.execute(
                    f"SELECT file, {folder_sql} AS folder FROM chapters WHERE {where} GROUP BY file ORDER BY file ASC", params)
            else:
                cur_epub = db_epub.execute(
                    f"SELECT DISTINCT file, NULL AS folder FROM epubs WHERE {where} ORDER BY file ASC", params)
            for row in cur_epub:
                file_key = row["file"]
                title = server.format_book_title(file_key, db_epub=db_epub)
                item = {"file": file_key, "title": title}
                if row["folder"]:
                    item["book_folder"] = row["folder"]
                files_data.append(item)
            def chapter_number(item):
                m = re.match(r"(\d+)\.", item["file"][len(folder) + 1:])
                return (int(m.group(1)) if m else 0, item["file"])
            files_data.sort(key=chapter_number)
            book_chapters = bool(files_data)
        except Exception:
            pass

    db_manga = server.get_manga_db()
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

    if files_data and not book_chapters:
        from aobana.search.titles import episode_order
        episode_order(files_data, grouping='subfolders' in files_data[0])

    return jsonify({"files": files_data})

@app.route("/api/context", methods=["GET"])
def api_context():
    rowid = request.args.get("rowid", type=int)
    file = request.args.get("file", "")
    q = server.fold_compat(server.normalize_query(request.args.get("q", "")))
    media = request.args.get("media", "").strip().lower()
    if rowid is None:
        return jsonify({"error": "Missing rowid"}), 400
    if media == 'custom':
        return _custom_context(server.get_custom_db(), rowid, file, q)
    if media == "manga":
        return _manga_context(server.get_manga_db(), rowid, file, q)

    db_subs, db_epub = server.get_db()
    from aobana.search.engine import _search_targets, reader_target
    if media in ("subs", "epub"):
        db_manga = None
        targets = _search_targets({"subs": db_subs, "epub": db_epub}, db_epub, media)
    else:
        db_manga = server.get_manga_db()
        targets = _search_targets(server._media_connections(db_subs, db_epub), db_epub, media or 'all', db_manga)
    if media not in ("subs", "epub") and file:
        target = reader_target(targets, file, rowid)
        if target:
            media = target[2]
    if media == 'custom':
        return _custom_context(server.get_custom_db(), rowid, file, q)
    if media == "manga":
        return _manga_context(db_manga, rowid, file, q)

    if not file:
        for table, conn, kind in targets:
            if conn is not None:
                r = conn.execute(f"SELECT file FROM {table} WHERE rowid = ?", (rowid,)).fetchone()
                if r:
                    file, media = r['file'], kind
                    break
        if media == 'manga':
            return _manga_context(db_manga, rowid, file, q)
        if media == 'custom':
            return _custom_context(server.get_custom_db(), rowid, file, q)

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
    
    from aobana.search.engine import query_highlight_args
    from aobana.search.furigana import highlight_and_furigana, work_key

    hl = query_highlight_args(q, "epub" if is_epub else "subs")
    context_html_lines = []
    for r in rows:
        line = r['line']
        hl_context = highlight_and_furigana(line, mark=True, bold=False, work=work_key("epub" if is_epub else "subs", file), **hl)
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

def _reader_offset(conn, table, file, rowid):
    n, hi = 0, rowid
    while hi > 1:
        lo = max(1, hi - 2000)
        rows = conn.execute(f'SELECT rowid, file FROM {table} WHERE rowid >= ? AND rowid < ? ORDER BY rowid DESC',
                            (lo, hi)).fetchall()
        for r in rows:
            if r[1] != file:
                return n
            n += 1
        if not rows or rows[-1][0] != lo:
            return n
        hi = lo
    return n


@app.route("/api/reader/at", methods=["GET"])
def api_reader_at():
    media = request.args.get("media", "").strip().lower()
    file = request.args.get("file", "")
    text = request.args.get("text", "")
    rowid = request.args.get("rowid", type=int)
    if rowid is None or not file or media not in server.MEDIA_NAMES:
        return jsonify({"error": "Missing media, file or rowid"}), 400
    if media == "custom":
        from aobana.search.custom import reader_place
        conn = server.get_custom_db()
        place = reader_place(conn, rowid, file, text) if conn is not None else None
        if place is None:
            return jsonify({"status": "file_gone"})
        return jsonify({"status": "ok" if place.pop("found") else "line_gone", "media": media, "rowid": rowid, **place})
    from aobana.search.engine import _search_targets, _file_lookup
    db_subs, db_epub = server.get_db()
    targets = _search_targets(server._media_connections(db_subs, db_epub), db_epub, media, server.get_manga_db())
    target = next(((t, c) for t, c, kind in targets if kind == media and c is not None), None)
    if target is None:
        return jsonify({"status": "file_gone"})
    table, conn = target
    from aobana.search.result_cache import _result_folder
    folder = _result_folder(media, file)
    sql, params = _file_lookup(conn, table, media, file)
    if conn.execute(sql, params).fetchone() is None:
        return jsonify({"status": "file_gone", "media": media, "folder": folder})
    row = conn.execute(f"SELECT file, line FROM {table} WHERE rowid = ?", (rowid,)).fetchone()
    found = row is not None and row[0] == file and (not text or row[1] == text)
    return jsonify({"status": "ok" if found else "line_gone", "media": media, "file": file, "folder": folder,
                    "rowid": rowid, "offset": _reader_offset(conn, table, file, rowid) if found else 0})


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
    from aobana.search.engine import query_highlight_args
    from aobana.search.furigana import highlight_and_furigana, work_key
    hl = query_highlight_args(q)
    lines = [highlight_and_furigana(r['line'], mark=True, bold=False, work=work_key("manga", file), **hl)
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
    db_subs, db_epub = server.get_db()
    db_manga = server.get_manga_db()
    db_custom = server.get_custom_db() if media_req == "custom" else None
    if db_subs is None and db_epub is None and db_manga is None and db_custom is None:
        return jsonify({"rows": []})

    from aobana.search.furigana import tagger
    from aobana.search.titles import title_of
    from aobana.search.custom import shown_title
    def contains(column):
        return " AND ".join([f"instr(replace({column}, char(160), ' '), ?) > 0"] * len(texts))
    forms = []
    for text in texts:
        with tagger() as (tokenizer_obj, mode):
            words = tokenizer_obj.tokenize(text, mode)
        for word in words:
            form = word.normalized_form()
            if form and any(ch.isalnum() for ch in form) and form not in forms:
                forms.append(form)
    forms = sorted(forms, key=len, reverse=True)[:3]
    match = " AND ".join('base_forms:' + server.fts_phrase(f) for f in forms) if forms else ""

    def query_corpus(db, table, media_type, scan=False):
        text = "line" if media_type == "custom" else "clean_text"
        if scan:
            res = db.execute(
                f"SELECT rowid, file, line, {text} AS clean_text FROM {table} WHERE " + contains(text)
                + f" ORDER BY length({text}) LIMIT 500",
                tuple(texts)).fetchall()
        else:
            try:
                res = db.execute(
                    f"SELECT rowid, file, line, {text} AS clean_text FROM {table} WHERE {table} MATCH ? AND "
                    + contains(text) + f" ORDER BY length({text}) LIMIT 500", (match, *texts)).fetchall()
            except sqlite3.OperationalError:
                return None
        out = []
        for r in res:
            title = shown_title(db, r["file"]) if media_type == "custom" else title_of(media_type, r["file"], db, db)
            out.append({
                "rowid": r["rowid"],
                "file": r["file"],
                "line": r["line"],
                "clean_text": r["clean_text"],
                "title": title,
                "media_type": media_type
            })
        return out

    corpora = []
    if media_req in ("", "all", "subs") and db_subs is not None:
        corpora.append((db_subs, "subtitles", "subs"))
    if media_req in ("", "all", "epub") and db_epub is not None:
        corpora.append((db_epub, "epubs", "epub"))
    if media_req in ("", "all", "manga") and db_manga is not None:
        corpora.append((db_manga, "manga", "manga"))
    if db_custom is not None:
        corpora.append((db_custom, "custom", "custom"))
    rows, scan = [], []
    for corpus in corpora:
        got = query_corpus(*corpus) if match else None
        if got is None:
            scan.append(corpus)
        else:
            rows.extend(got)
    if not rows:
        scan = corpora
    for corpus in scan:
        rows.extend(query_corpus(*corpus, scan=True))

    rows.sort(key=lambda r: len(r.get("clean_text") or ""))
    return jsonify({"rows": rows[:500]})

RELOCATE_MAX = 5000


@app.route("/api/relocate", methods=["POST"])
def api_relocate():
    server._require_page()
    sent = (request.get_json(silent=True) or {}).get("items", [])
    # RELOCATE_MAX a request; the page sends more in batches, and an answer that cut says how many
    items = sent[:RELOCATE_MAX]
    db_subs, db_epub = server.get_db()
    db_manga = server.get_manga_db()
    from aobana.search.furigana import tagger
    out = []
    for it in items:
        db, table = {"epub": (db_epub, "epubs"), "manga": (db_manga, "manga"),
                     "custom": (server.get_custom_db(), "custom")}.get(
            it.get("media_type"), (db_subs, "subtitles"))
        line, rowid, file = it.get("line") or "", it.get("rowid"), it.get("file") or ""
        if db is None or not line or rowid is None:
            out.append(None)
            continue
        r = db.execute(f"SELECT file, line FROM {table} WHERE rowid = ?", (rowid,)).fetchone()
        if r and r["line"] == line and r["file"] == file:
            out.append(None)
            continue
        from aobana.search.engine import _source_runs, _result_folder
        kind = it.get('media_type') or 'subs'
        folder = _result_folder(kind, file)
        ranges = None
        if kind == 'epub':
            from aobana import utils
            if utils.has_chapters(db):
                clause, params = server.folder_prefix_where('file', folder)
                ranges = db.execute('SELECT first_rowid,last_rowid,file FROM chapters WHERE '+clause,params).fetchall()
        else:
            ranges = _source_runs(db, table, kind, {folder})
        exact_rows = []
        if ranges is not None:
            for lo, hi, *_ in ranges:
                candidate = db.execute(f'SELECT rowid,file,line FROM {table} WHERE rowid BETWEEN ? AND ? '
                                       'AND line = ? ORDER BY (file != ?), abs(rowid-?) LIMIT 1',
                                       (lo, hi, line, file, rowid)).fetchone()
                if candidate:
                    exact_rows.append(candidate)
        else:
            exact_rows = db.execute(f'SELECT rowid,file,line FROM {table} WHERE file = ? AND line = ? '
                                    'ORDER BY abs(rowid-?) LIMIT 1',(file,line,rowid)).fetchall()
        if exact_rows:
            best = min(exact_rows,key=lambda x:(x['file'] != file,abs(x['rowid']-rowid)))
            out.append({'rowid':best['rowid'],'file':best['file']})
            continue
        if kind == 'custom':
            text = line.strip()
        else:
            ruby = server.RUBY_RE if it.get("media_type") not in ("epub", "manga") else server.BOOK_RUBY_RE
            text = ruby.sub(r'\1\2', line).replace('｜', '').strip()
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
                    (" AND ".join('base_forms:' + server.fts_phrase(f) for f in forms),)).fetchall()
            except sqlite3.OperationalError:
                out.append(None)
                continue
        work = lambda f: _result_folder(kind, f)
        same = [x for x in rows if x["line"] == line and work(x['file']) == work(file)]
        best = (min(same, key=lambda x: (work(x["file"]) != work(file), abs(x["rowid"] - rowid))) if same else None)
        out.append({"rowid": best["rowid"], "file": best["file"]} if best else {"gone": True})
    return jsonify({"items": out, **({"cut": len(sent) - len(items)} if len(sent) > len(items) else {})})


_MANGA_PAGE_MISSING = """<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>露草</title>
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;font-family:system-ui,sans-serif;
background:#f6f5f2;color:#3a3a3a}@media (prefers-color-scheme:dark){body{background:#16181c;color:#c9ccd2}}
p{margin:.4em 1em;text-align:center}</style></head><body><div>
<p>このページの画像が見つかりません。</p><p lang="en">The image of this page was not found.</p>
</div></body></html>"""


def _manga_missing():
    return make_response(_MANGA_PAGE_MISSING, 404, {"Content-Type": "text/html; charset=utf-8",
                                                    "Cache-Control": "no-store"})


_MANGA_VIEWER = """<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title>
<style>html,body{{margin:0;height:100%;background:#f6f5f2;color:#3a3a3a;font-family:system-ui,sans-serif}}
@media (prefers-color-scheme:dark){{html,body{{background:#16181c;color:#c9ccd2}}}}
main{{min-height:100%;display:flex}}
img{{margin:auto;display:block;cursor:zoom-in;max-width:100vw;max-height:100vh}}
img.sized{{max-width:none;max-height:none}}img.full{{max-width:100%;max-height:none;cursor:zoom-out}}
#gone{{display:none;text-align:center}}#gone p{{margin:.4em 1em}}</style>
</head><body><main><img src="{image}" alt="" onerror="this.remove();document.getElementById('gone').style.display='block'">
<div id="gone"><p>このページの画像が見つかりません。</p><p lang="en">The image of this page was not found.</p></div></main>
<script>
const next = {next}, prev = {prev};
document.addEventListener('keydown', e => {{
  if (e.ctrlKey || e.altKey || e.metaKey || e.shiftKey) return;
  const to = e.key === 'ArrowLeft' ? next : e.key === 'ArrowRight' ? prev : null;
  if (to) {{ e.preventDefault(); location.replace(to); }}
}});
const img = document.querySelector('img');
let ratio = devicePixelRatio;
function fit() {{
  if (!img || !img.naturalWidth || !innerWidth || !innerHeight || img.classList.contains('full')) return;
  const s = Math.min(1, innerWidth / img.naturalWidth, innerHeight / img.naturalHeight);
  img.style.width = img.naturalWidth * s + 'px';
  img.classList.add('sized');
}}
if (img) {{
  img.addEventListener('load', fit);
  if (img.complete) fit();
  img.addEventListener('click', () => {{
    img.classList.remove('sized');
    img.classList.toggle('full');
    img.style.width = '';
    fit();
  }});
}}
addEventListener('resize', () => {{ if (devicePixelRatio === ratio) fit(); ratio = devicePixelRatio; }});
if (next) {{ const n = new Image(); n.src = next.replace('/manga/read/', '/manga/image/'); }}
</script></body></html>"""


@app.route("/manga/page/<int:rowid>", methods=["GET"])
def manga_page_image(rowid):
    where = library.manga_page_location(server.get_manga_db(), rowid)
    return manga_volume_image(*where) if where else _manga_missing()


@app.route("/manga/view/<int:rowid>", methods=["GET"])
def manga_page_view(rowid):
    where = library.manga_page_location(server.get_manga_db(), rowid)
    if not where:
        return _manga_missing()
    from flask import redirect
    return redirect(f"/manga/read/{where[0]}/{where[1]}")


@app.route("/manga/read/<int:source_id>/<int:page>", methods=["GET"])
def manga_page_viewer(source_id, page):
    import html
    import json
    place = library.manga_page_neighbours(server.get_manga_db(), source_id, page)
    if not place:
        return _manga_missing()
    link = lambda to: json.dumps(f"/manga/read/{to[0]}/{to[1]}" if to else None)
    body = _MANGA_VIEWER.format(
        title=html.escape(f"{place['page']} / {place['pages']} · {place['volume']}"),
        image=f"/manga/image/{source_id}/{page}", next=link(place["next"]), prev=link(place["prev"]))
    return make_response(body, 200, {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store"})


@app.route("/manga/image/<int:source_id>/<int:page>", methods=["GET"])
def manga_volume_image(source_id, page):
    image = library.manga_volume_image_path(server.get_manga_db(), source_id, page)
    if not image:
        return _manga_missing()
    response = send_file(image, conditional=True, max_age=3600)
    response.headers["Cache-Control"] = "private, max-age=3600"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


import datetime
import html as _html_mod
import json as _json
import os
import posixpath
import threading
import time as _time
import unicodedata
import urllib.parse
import xml.etree.ElementTree as _ET
import zipfile
import zlib
from collections import OrderedDict
from bs4 import BeautifulSoup, CData, Comment, Declaration, Doctype, NavigableString, ProcessingInstruction, Tag
from flask import Response
from aobana import paths

_READER_ALLOWED_MEDIA = ("epub", "subs", "manga")
_READER_STATE_LOCK = threading.Lock()
_EPUB_META_LOCK = threading.Lock()
_EPUB_META_CACHE = OrderedDict()
_EPUB_META_MAX = 12

# Skipping through parts loads only the one stopped on: each tab numbers its
# part loads, and a load stops as soon as a newer one from the same tab has started.
_PART_SEQ_LOCK = threading.Lock()
_PART_LATEST = OrderedDict()
_PART_LATEST_MAX = 256
_PART_CTX = threading.local()


class _PartSuperseded(BaseException):
    pass


def _part_begin(client, seq):
    _PART_CTX.key = None
    if not client or seq is None:
        return True
    with _PART_SEQ_LOCK:
        if seq < _PART_LATEST.get(client, -1):
            return False
        _PART_LATEST[client] = seq
        _PART_LATEST.move_to_end(client)
        while len(_PART_LATEST) > _PART_LATEST_MAX:
            _PART_LATEST.popitem(last=False)
    _PART_CTX.key = (client, seq)
    return True


def _part_check():
    key = getattr(_PART_CTX, "key", None)
    if key is not None and _PART_LATEST.get(key[0], -1) > key[1]:
        raise _PartSuperseded()

_READER_PREFS_DEFAULT = {
    "theme": "app",
    "font_size": 20,
    "font_weight": 400,
    "line_height": 1.85,
    "font_family": "",
    "max_width": 44,
    "furigana": "on",
    "writing_mode": "auto",
    "v_layout": "paginated",
    "h_layout": "continuous",
    "sub_timestamps": False,
    "manga_boxes": "hover",
    "manga_layout": "single",
    "edge_click_nav": True,
    "edge_click_width": 12,
    "show_progress": True,
}

_READER_THEMES = ("app", "paper", "haze", "sepia", "night", "midnight")
_READER_FURI = ("on", "hover", "off")
_READER_LAYOUTS = ("paginated", "continuous")
_READER_DIRS = ("vertical", "horizontal")
_READER_PREF_DIRS = ("auto", "vertical", "horizontal")
_READER_MANGA_BOXES = ("hover", "always", "off")
_READER_MANGA_LAYOUTS = ("single", "strip")


def _reader_state_path():
    return os.path.join(paths.STORE_DIR, "reader-state.json")


def _log_reader_fallback(media, file_key, reason, detail=""):
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    safe_file = str(file_key or "").replace("\r", " ").replace("\n", " ")
    safe_detail = str(detail or "").replace("\r", " ").replace("\n", " ")
    line = f"{stamp} [fallback] media={media} file={safe_file} reason={reason}"
    if safe_detail:
        line += f" detail={safe_detail}"
    try:
        log_dir = paths.logs_dir()
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "reader_fallbacks.txt"), "a", encoding="utf-8", newline="\n") as fh:
            fh.write(line + "\n")
    except OSError:
        pass
    try:
        app.logger.info("%s", line)
    except Exception:
        pass


def _clamp_font_family(val):
    # An installed font's family name, or "" for the bundled Noto Sans JP. The old two choices
    # ("mincho", "gothic") and anything that could leave a CSS string become "".
    if not isinstance(val, str):
        return ""
    val = val.strip()
    if not val or len(val) > 100 or val in ("mincho", "gothic"):
        return ""
    if any(ch in "\"'\\;{}<>" or ord(ch) < 32 or ord(ch) == 127 for ch in val):
        return ""
    return val


def _clamp_prefs(raw):
    out = dict(_READER_PREFS_DEFAULT)
    if not isinstance(raw, dict):
        return out
    if raw.get("theme") in _READER_THEMES:
        out["theme"] = raw["theme"]
    out["font_family"] = _clamp_font_family(raw.get("font_family"))
    if raw.get("furigana") in _READER_FURI:
        out["furigana"] = raw["furigana"]
    if raw.get("writing_mode") in _READER_PREF_DIRS:
        out["writing_mode"] = raw["writing_mode"]
    if raw.get("v_layout") in _READER_LAYOUTS:
        out["v_layout"] = raw["v_layout"]
    if raw.get("h_layout") in _READER_LAYOUTS:
        out["h_layout"] = raw["h_layout"]
    if raw.get("manga_boxes") in _READER_MANGA_BOXES:
        out["manga_boxes"] = raw["manga_boxes"]
    if raw.get("manga_layout") in _READER_MANGA_LAYOUTS:
        out["manga_layout"] = raw["manga_layout"]
    for key, lo, hi, cast in (
        ("font_size", 12, 36, int),
        ("font_weight", 200, 900, int),
        ("line_height", 1.0, 2.6, float),
        ("max_width", 10, 72, int),
        ("edge_click_width", 5, 35, int),
    ):
        if key in raw:
            try:
                val = cast(raw[key])
                if lo <= val <= hi:
                    out[key] = round(val, 2) if cast is float else val
            except (TypeError, ValueError):
                pass
    for bkey in ("sub_timestamps", "show_progress", "edge_click_nav"):
        if isinstance(raw.get(bkey), bool):
            out[bkey] = raw[bkey]
    return out


def _clamp_media_prefs(raw):
    # Subtitles, books and manga keep their own display settings. A flat
    # dict from before the split seeds all three.
    if not isinstance(raw, dict):
        raw = {}
    nested = any(isinstance(raw.get(m), dict) for m in _READER_ALLOWED_MEDIA)
    return {m: _clamp_prefs(raw.get(m) if nested else raw) for m in _READER_ALLOWED_MEDIA}


def _clean_work_state(raw, existing=None):
    out = dict(existing) if isinstance(existing, dict) else {}
    if not isinstance(raw, dict):
        return out
    if isinstance(raw.get("file"), str):
        out["file"] = raw["file"]
    for ikey in ("part_index", "char_offset", "page"):
        if ikey in raw and raw[ikey] is not None:
            try:
                out[ikey] = max(0, int(raw[ikey]))
            except (TypeError, ValueError):
                pass
    if "scroll_ratio" in raw and raw["scroll_ratio"] is not None:
        try:
            r = float(raw["scroll_ratio"])
            out["scroll_ratio"] = max(0.0, min(1.0, round(r, 5)))
        except (TypeError, ValueError):
            pass
    if "writing_mode" in raw:
        wm = raw["writing_mode"]
        out["writing_mode"] = wm if wm in _READER_DIRS else None
    if "layout" in raw:
        lo = raw["layout"]
        out["layout"] = lo if lo in _READER_LAYOUTS else None
    if "bookmark" in raw:
        bm = raw["bookmark"]
        if bm is None:
            out["bookmark"] = None
        elif isinstance(bm, dict) and isinstance(bm.get("file"), str):
            try:
                ratio = max(0.0, min(1.0, float(bm.get("scroll_ratio", 0.0))))
            except (TypeError, ValueError):
                ratio = 0.0
            try:
                page = max(0, int(bm.get("page", 0)))
            except (TypeError, ValueError):
                page = 0
            try:
                coff = max(0, int(bm.get("char_offset", 0)))
            except (TypeError, ValueError):
                coff = 0
            out["bookmark"] = {
                "file": bm["file"],
                "scroll_ratio": round(ratio, 5),
                "page": page,
                "char_offset": coff,
                "label": str(bm.get("label") or "")[:120],
            }
    out["updated_at"] = int(datetime.datetime.now().timestamp())
    return out


def _read_reader_state():
    path = _reader_state_path()
    try:
        with open(path, encoding="utf-8") as fh:
            data = _json.load(fh)
        if not isinstance(data, dict):
            data = {}
    except OSError:
        data = {}
    except ValueError:
        data = {}
        bad = f"{path}.bad"
        if not os.path.exists(bad):
            try:
                os.replace(path, bad)
            except OSError:
                pass
    prefs = _clamp_media_prefs(data.get("prefs"))
    works = data.get("works") if isinstance(data.get("works"), dict) else {}
    return {"prefs": prefs, "works": works}


def _write_reader_state(doc):
    path = _reader_state_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        _json.dump(doc, fh, ensure_ascii=False, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    for attempt in range(20):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 19:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                raise
            _time.sleep(0.05)


_EPUB_HTML_EXTS = (".xhtml", ".html", ".htm")
_EPUB_HTML_MIMES = {"application/xhtml+xml", "text/html"}
_EPUB_ASSET_MIMES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".gif": "image/gif", ".webp": "image/webp", ".avif": "image/avif",
    ".bmp": "image/bmp", ".svg": "image/svg+xml",
}
_EPUB_DROP_TAGS = {
    "script", "style", "iframe", "frame", "frameset", "object", "embed",
    "applet", "form", "input", "button", "textarea", "select", "option",
    "meta", "link", "base", "title", "head", "noscript", "audio", "video",
    "source", "track", "canvas", "template", "foreignobject", "animate",
    "animatetransform", "animatemotion", "set", "handler",
}
_EPUB_ALLOW_TAGS = {
    "div", "section", "article", "header", "footer", "main", "aside", "nav",
    "p", "span", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6",
    "blockquote", "pre", "code", "kbd", "samp", "var",
    "em", "strong", "b", "i", "u", "s", "del", "ins", "mark", "small", "sub", "sup", "abbr", "cite", "q", "dfn", "time",
    "ruby", "rb", "rt", "rp", "rtc", "bdi", "bdo", "wbr",
    "ul", "ol", "li", "dl", "dt", "dd",
    "table", "caption", "thead", "tbody", "tfoot", "tr", "th", "td", "colgroup", "col",
    "figure", "figcaption", "img", "a",
    "svg", "g", "image", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "text", "tspan", "defs", "clippath",
}
_EPUB_ALLOW_ATTRS = {
    "class", "id", "lang", "xml:lang", "dir", "title", "alt",
    "colspan", "rowspan", "scope", "headers", "start", "reversed",
    "viewbox", "width", "height", "x", "y", "x1", "y1", "x2", "y2",
    "cx", "cy", "r", "rx", "ry", "d", "points", "transform",
    "fill", "stroke", "stroke-width", "preserveaspectratio", "opacity",
}
_SAFE_INLINE_PROPS = {
    "text-align", "text-indent", "font-weight", "font-style", "text-decoration",
    "text-emphasis", "text-emphasis-style", "text-emphasis-position",
    "-webkit-text-emphasis", "-webkit-text-emphasis-style", "-webkit-text-emphasis-position",
    "-epub-text-emphasis", "-epub-text-emphasis-style", "-epub-text-emphasis-position",
    "text-combine-upright", "-webkit-text-combine", "-epub-text-combine",
    "margin", "margin-top", "margin-bottom", "margin-left", "margin-right",
    "margin-block-start", "margin-block-end", "margin-inline-start", "margin-inline-end",
    "padding", "padding-top", "padding-bottom", "padding-left", "padding-right",
    "border", "border-top", "border-bottom", "border-left", "border-right",
    "white-space", "vertical-align", "display", "list-style-type",
    "letter-spacing", "word-break", "overflow-wrap",
}
_CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
_CSS_DANGEROUS_VAL_RE = re.compile(
    r"(?:url\s*\(|image-set\s*\(|image\s*\(|src\s*\(|element\s*\(|cross-fade\s*\(|expression\s*\("
    r"|javascript:|behavior\s*:|-moz-binding|@import)", re.I)
_CSS_ESCAPE_RE = re.compile(r"\\([0-9a-fA-F]{1,6})\s?|\\(.)", re.S)


def _css_unescape(text):
    def one(m):
        if m.group(1):
            cp = int(m.group(1), 16)
            return chr(cp) if 0 < cp <= 0x10FFFF else "\ufffd"
        return m.group(2)
    return _CSS_ESCAPE_RE.sub(one, text or "")


def _css_value_dangerous(val):
    plain = re.sub(r"[\x00-\x20]+", "", _css_unescape(val))
    return bool(_CSS_DANGEROUS_VAL_RE.search(val) or _CSS_DANGEROUS_VAL_RE.search(plain))
_CSS_STRIP_PROPS = {
    "writing-mode", "-webkit-writing-mode", "-epub-writing-mode", "-ms-writing-mode",
    "position", "z-index", "overflow", "overflow-x", "overflow-y",
    "page-break-before", "page-break-after", "break-before", "break-after",
    "column-count", "column-width", "columns", "cursor",
}
_CSS_ROOT_STRIP_PROPS = {
    "font-size", "line-height", "font-family", "color", "background", "background-color",
    "width", "height", "min-width", "min-height", "max-width", "max-height", "margin", "padding",
}
_WM_DECL_RE = re.compile(r"(?:^|[;\s])(?:-webkit-|-epub-|-ms-)?writing-mode\s*:\s*([a-z-]+)", re.I)
_RT_STRIP_RE = re.compile(r"<(?:rt|rp)\b[^>]*>.*?</(?:rt|rp)>", re.I | re.S)
_TAG_STRIP_RE = re.compile(r"<[^>]+>")
_HEAD_STRIP_RE = re.compile(r"<head\b.*?</head\s*>", re.I | re.S)
_IMG_ALT_RE = re.compile(r"""<img\b[^>]*?\balt\s*=\s*(?:"([^"]*)"|'([^']*)')[^>]*>""", re.I)
_PLAIN_NOISE_RE = re.compile(r"[^\w\u3040-\u30ff\u3400-\u9fff]+")


def _plain_for_match(text):
    if not text:
        return ""
    s = server.BOOK_RUBY_RE.sub(r"\1\2", text)
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("｜", "").replace("|", "")
    return _PLAIN_NOISE_RE.sub("", s)


def _xhtml_plain(raw_bytes):
    txt = raw_bytes.decode("utf-8", errors="replace")
    txt = _HEAD_STRIP_RE.sub("", txt)
    txt = _IMG_ALT_RE.sub(lambda m: m.group(1) or m.group(2) or "", txt)
    txt = _RT_STRIP_RE.sub("", txt)
    txt = _TAG_STRIP_RE.sub("", txt)
    txt = _html_mod.unescape(txt)
    txt = unicodedata.normalize("NFKC", txt)
    return _PLAIN_NOISE_RE.sub("", txt)


def _norm_zip_member(base_dir, href):
    if not href:
        return None
    href = href.split("#", 1)[0].split("?", 1)[0].strip()
    if not href:
        return None
    lower = href.lower()
    if lower.startswith(("http:", "https:", "//", "javascript:", "vbscript:", "data:", "mailto:", "file:")):
        return None
    href = urllib.parse.unquote(href).replace("\\", "/")
    joined = posixpath.join(base_dir, href) if base_dir else href
    norm = posixpath.normpath(joined).lstrip("/")
    if norm in ("", ".", "..") or norm.startswith("../") or "/../" in norm:
        return None
    return norm


def _epub_parse_meta(epub_path):
    st = os.stat(epub_path)
    cache_key = (epub_path, st.st_mtime_ns, st.st_size)
    with _EPUB_META_LOCK:
        hit = _EPUB_META_CACHE.get(cache_key)
        if hit is not None:
            _EPUB_META_CACHE.move_to_end(cache_key)
            return hit
    with zipfile.ZipFile(epub_path, "r") as zf:
        zip_names = set(zf.namelist())
        opf = None
        content_dir = ""
        try:
            cxml = _ET.fromstring(zf.read("META-INF/container.xml"))
            rf = cxml.find(".//{*}rootfile").attrib["full-path"]
            opf = _ET.fromstring(zf.read(rf))
            content_dir = posixpath.dirname(rf)
        except Exception:
            opfs = [n for n in zf.namelist() if n.endswith(".opf")]
            if opfs:
                try:
                    opf = _ET.fromstring(zf.read(opfs[0]))
                    content_dir = posixpath.dirname(opfs[0])
                except Exception:
                    opf = None

        ppd = ""
        spine_members = []
        if opf is not None:
            spine_el = opf.find(".//{*}spine")
            if spine_el is not None:
                ppd = (spine_el.attrib.get("page-progression-direction") or "").strip().lower()
            manifest = {}
            media_types = {}
            for item in opf.findall(".//{*}manifest/{*}item"):
                iid = item.attrib.get("id")
                href = item.attrib.get("href")
                if iid and href:
                    manifest[iid] = href
                    media_types[href] = item.attrib.get("media-type", "")
            for ref in opf.findall(".//{*}spine/{*}itemref"):
                href = manifest.get(ref.attrib.get("idref", ""))
                if not href:
                    continue
                mt = media_types.get(href, "")
                if mt and mt not in _EPUB_HTML_MIMES and not href.lower().endswith(_EPUB_HTML_EXTS):
                    continue
                cand = None
                for h in dict.fromkeys((href, urllib.parse.unquote(href))):
                    for c in (h, posixpath.normpath(posixpath.join(content_dir, h)) if content_dir else h):
                        if c in zip_names:
                            cand = c
                            break
                    if cand:
                        break
                if cand:
                    spine_members.append(cand)
        else:
            cand_list = [n for n in zf.namelist()
                         if n.lower().endswith(_EPUB_HTML_EXTS)
                         and not n.lower().endswith(("navigation-documents.xhtml", "nav.xhtml", "toc.xhtml"))]
            def _sp_key(p):
                b = posixpath.basename(p).lower()
                if "cover" in b: return (0, 0)
                if "title" in b: return (0, 1)
                if "caution" in b: return (0, 2)
                m = re.search(r"(\d+)", b)
                if m: return (1, int(m.group(1)))
                if "atogaki" in b or "afterword" in b: return (2, 0)
                if "author" in b: return (2, 1)
                if "colophon" in b: return (2, 2)
                return (1, 999)
            cand_list.sort(key=_sp_key)
            spine_members = cand_list

        toc_entries = []
        toc_map = {}
        try:
            from aobana.indexing import epub_indexer
            toc_map = epub_indexer.extract_toc_map(zf, opf, content_dir)
        except Exception:
            toc_map = {}
        spine_idx_of = {m: i for i, m in enumerate(spine_members)}
        for raw_path, label in toc_map.items():
            norm_p = posixpath.normpath(raw_path)
            if norm_p not in spine_idx_of and content_dir:
                alt = posixpath.normpath(posixpath.join(content_dir, raw_path))
                if alt in spine_idx_of:
                    norm_p = alt
            if norm_p in spine_idx_of:
                clean_lab = re.sub(r"[\s\u3000]+", "", label or "")
                toc_entries.append((spine_idx_of[norm_p], clean_lab, label or ""))

        meta = {
            "spine": spine_members,
            "spine_idx": spine_idx_of,
            "ppd": ppd,
            "toc": toc_entries,
            "zip_names": zip_names,
            "content_dir": content_dir,
        }
    with _EPUB_META_LOCK:
        _EPUB_META_CACHE[cache_key] = meta
        while len(_EPUB_META_CACHE) > _EPUB_META_MAX:
            _EPUB_META_CACHE.popitem(last=False)
    return meta


def _detect_epub_writing_mode(soup, raw_css_list, ppd):
    html_el = soup.find("html")
    body_el = soup.find("body")
    classes = set()
    for el in (html_el, body_el):
        if el is None:
            continue
        cls = el.get("class") or []
        if isinstance(cls, str):
            cls = cls.split()
        for c in cls:
            classes.add(c.lower())
        style = el.get("style") or ""
        m = _WM_DECL_RE.search(style)
        if m:
            val = m.group(1).lower()
            if val.startswith("vertical"):
                return "vertical"
            if val.startswith("horizontal"):
                return "horizontal"
    if classes & {"vrtl", "vertical", "vertical-rl", "tategaki"}:
        return "vertical"
    if classes & {"hltr", "horizontal", "horizontal-tb", "yokogaki"}:
        return "horizontal"

    matched_wm = None
    for css in raw_css_list:
        clean = _CSS_COMMENT_RE.sub("", css)
        for sel_part, body_part in re.findall(r"([^{}@]+)\{([^{}]+)\}", clean):
            m = _WM_DECL_RE.search(body_part)
            if not m:
                continue
            val = m.group(1).lower()
            sels = [s.strip().lower() for s in sel_part.split(",")]
            applies = False
            for s in sels:
                if s in ("html", "body", ":root", "html body", "html, body"):
                    applies = True
                else:
                    for c in classes:
                        if s == "." + c or s.endswith("." + c) or s.startswith("html." + c) or s.startswith("body." + c):
                            applies = True
                            break
                if applies:
                    break
            if applies:
                if val.startswith("vertical"):
                    matched_wm = "vertical"
                elif val.startswith("horizontal"):
                    matched_wm = "horizontal"
    if matched_wm:
        return matched_wm
    if ppd == "rtl":
        return "vertical"
    if ppd == "ltr":
        return "horizontal"
    return "horizontal"


def _iter_css_rules(css):
    n = len(css)
    i = 0
    while i < n:
        while i < n and css[i] in " \t\r\n;":
            i += 1
        if i >= n:
            break
        if css[i] == "@":
            in_str = None
            depth = 0
            while i < n:
                ch = css[i]
                if in_str:
                    if ch == "\\" and i + 1 < n:
                        i += 2
                        continue
                    if ch == in_str:
                        in_str = None
                else:
                    if ch in ("'", '"'):
                        in_str = ch
                    elif ch == "{":
                        depth += 1
                    elif ch == "}":
                        if depth > 0:
                            depth -= 1
                            if depth == 0:
                                i += 1
                                break
                    elif ch == ";" and depth == 0:
                        i += 1
                        break
                i += 1
            continue
        sel_start = i
        in_str = None
        while i < n:
            ch = css[i]
            if in_str:
                if ch == "\\" and i + 1 < n:
                    i += 2
                    continue
                if ch == in_str:
                    in_str = None
            else:
                if ch in ("'", '"'):
                    in_str = ch
                elif ch in ("{", "}"):
                    break
            i += 1
        if i >= n or css[i] != "{":
            i += 1
            continue
        sel_raw = css[sel_start:i]
        i += 1
        body_start = i
        depth = 1
        in_str = None
        nested = False
        while i < n and depth > 0:
            ch = css[i]
            if in_str:
                if ch == "\\" and i + 1 < n:
                    i += 2
                    continue
                if ch == in_str:
                    in_str = None
            else:
                if ch in ("'", '"'):
                    in_str = ch
                elif ch == "{":
                    depth += 1
                    nested = True
                elif ch == "}":
                    depth -= 1
            i += 1
        if depth == 0 and not nested:
            yield sel_raw, css[body_start:i - 1]


_CSS_PROP_RE = re.compile(r"^-?[a-z][a-z0-9-]*$")
# A book's ids reach the page as rm-ep-<id> (_sanitize_epub_fragment), so its #id selectors follow;
# an attribute selector is left as written.
_CSS_ID_SEL_RE = re.compile(r"\[[^\]]*\]|#(-?[^\W\d][\w-]*)")


def _css_id_sel(m):
    name = m.group(1)
    if name is None or name.startswith("rm-ep-"):
        return m.group(0)
    return "#rm-ep-" + name


def _sanitize_epub_css(raw_css_list, scope="#rm-epub-root"):
    out_rules = []
    for raw in raw_css_list:
        css = _CSS_COMMENT_RE.sub("", raw or "")
        for sel_raw, decls_raw in _iter_css_rules(css):
            if "@" in sel_raw or ";" in sel_raw or _css_value_dangerous(sel_raw):
                continue
            sels = []
            is_root_sel = False
            for s in sel_raw.split(","):
                s = s.strip()
                if not s or "@" in s or ";" in s or _css_value_dangerous(s):
                    continue
                low = s.lower()
                if low in ("html", "body", ":root", "html body"):
                    is_root_sel = True
                    sels.append(scope)
                else:
                    s_fixed = re.sub(r"^(?:html|body)\b", "", s, flags=re.I).strip()
                    if s_fixed[:1] in ("~", "+") or re.match(r"^(?:html|body)\b", s_fixed, re.I):
                        continue
                    s_fixed = _CSS_ID_SEL_RE.sub(_css_id_sel, s_fixed)
                    sels.append(f"{scope} {s_fixed}" if s_fixed else scope)
            if not sels:
                continue
            kept = []
            for decl in decls_raw.split(";"):
                if ":" not in decl:
                    continue
                prop, val = decl.split(":", 1)
                prop = _css_unescape(prop.strip()).lower()
                val = val.strip()
                if not prop or not val or not _CSS_PROP_RE.fullmatch(prop):
                    continue
                if prop in _CSS_STRIP_PROPS:
                    continue
                if is_root_sel and prop in _CSS_ROOT_STRIP_PROPS:
                    continue
                if prop in ("font-family", "font") and "monospace" not in val.lower():
                    continue
                if _css_value_dangerous(val) or _css_value_dangerous(prop):
                    continue
                if prop in ("font-size", "line-height") and re.search(r"(?:vh|vw|dvh|dvw|svh|svw)", val, re.I):
                    continue
                kept.append(f"{prop}: {val}")
            if kept:
                out_rules.append(f"{', '.join(sels)} {{ {'; '.join(kept)}; }}")
    return "\n".join(out_rules)


def _sanitize_inline_style(style_val):
    if not style_val or _css_value_dangerous(style_val):
        return ""
    kept = []
    for decl in style_val.split(";"):
        if ":" not in decl:
            continue
        prop, val = decl.split(":", 1)
        prop = prop.strip().lower()
        val = val.strip()
        if prop in _SAFE_INLINE_PROPS and val and not _css_value_dangerous(val):
            kept.append(f"{prop}: {val}")
    return "; ".join(kept)


def _sanitize_epub_fragment(root_tag, source_id, page_dir, zip_names, cur_member=None):
    for c in list(root_tag.find_all(string=lambda s: isinstance(s, (Comment, CData, Declaration, Doctype, ProcessingInstruction)))):
        c.extract()
    for el in list(root_tag.find_all(True)):
        if el.parent is None:
            continue
        name = (el.name or "").lower()
        if name in _EPUB_DROP_TAGS:
            el.decompose()
            continue
        if name not in _EPUB_ALLOW_TAGS:
            el.unwrap()
            continue
        new_attrs = {}
        for k, v in list(el.attrs.items()):
            kl = k.lower()
            if kl.startswith("on") or kl in ("srcdoc", "formaction"):
                continue
            if kl == "style":
                cleaned = _sanitize_inline_style(v if isinstance(v, str) else " ".join(v))
                if cleaned:
                    new_attrs["style"] = cleaned
                continue
            if name == "img" and kl == "src":
                src = v if isinstance(v, str) else ""
                member = _norm_zip_member(page_dir, src)
                ext = os.path.splitext(member or "")[1].lower()
                if member and member in zip_names and ext in _EPUB_ASSET_MIMES:
                    new_attrs["src"] = f"/api/reading/epub-asset/{source_id}/{urllib.parse.quote(member, safe='/')}"
                    new_attrs["loading"] = "lazy"
                    new_attrs["decoding"] = "async"
                continue
            if name == "image" and kl in ("href", "xlink:href"):
                src = v if isinstance(v, str) else ""
                member = _norm_zip_member(page_dir, src)
                ext = os.path.splitext(member or "")[1].lower()
                if member and member in zip_names and ext in _EPUB_ASSET_MIMES:
                    new_attrs["href"] = f"/api/reading/epub-asset/{source_id}/{urllib.parse.quote(member, safe='/')}"
                continue
            if name == "a" and kl == "href":
                href = (v if isinstance(v, str) else "").strip()
                if href.startswith("#") and len(href) > 1:
                    new_attrs["href"] = href
                    if cur_member:
                        new_attrs["data-rm-href"] = cur_member + href
                elif re.match(r"^https?://", href, re.I):
                    new_attrs["href"] = href
                    new_attrs["target"] = "_blank"
                    new_attrs["rel"] = "noopener noreferrer"
                elif href and not re.match(r"^[a-z][a-z0-9+.-]*:", href, re.I):
                    path_part, _, frag = href.partition("#")
                    target = _norm_zip_member(page_dir, path_part) if path_part else cur_member
                    if target and target in zip_names:
                        new_attrs["href"] = "#" + frag if frag else "#"
                        new_attrs["data-rm-href"] = target + ("#" + frag if frag else "")
                continue
            if kl == "id":
                val = (v if isinstance(v, str) else "").strip()
                if val:
                    new_attrs["id"] = val if val.startswith("rm-ep-") else f"rm-ep-{val}"
                continue
            if kl == "name" and name == "a" and "id" not in new_attrs:
                val = (v if isinstance(v, str) else "").strip()
                if val:
                    new_attrs["id"] = val if val.startswith("rm-ep-") else f"rm-ep-{val}"
                continue
            if kl in _EPUB_ALLOW_ATTRS:
                new_attrs[kl] = v
        el.attrs = new_attrs
        if name == "img" and "src" not in el.attrs:
            el.decompose()
    for p in list(root_tag.find_all("p")):
        kids = [k for k in p.contents if not (type(k) is NavigableString and not k.strip())]
        if len(kids) == 1 and isinstance(kids[0], Tag) and kids[0].name == "code":
            for k in list(p.contents):
                if type(k) is NavigableString and not k.strip():
                    k.extract()
            cls = p.get("class") or []
            cls = cls.split() if isinstance(cls, str) else list(cls)
            p["class"] = cls + ["rm-code-block"]
    for br in list(root_tag.find_all("br")):
        nxt = br.next_sibling
        if isinstance(nxt, NavigableString) and type(nxt) is NavigableString and br.find_parent(["pre", "code"]):
            s = str(nxt)
            if s.startswith(("\r\n", "\n", "\r")):
                s = s[2:] if s.startswith("\r\n") else s[1:]
                if s:
                    nxt.replace_with(NavigableString(s))
                else:
                    nxt.extract()


def _needle_variants(line):
    p = _plain_for_match(line)
    if not p:
        return []
    out = []
    if len(p) >= 24:
        out.append(p[:24])
        out.append(p[-24:])
        mid = len(p) // 2
        out.append(p[max(0, mid - 12):mid + 12])
    elif len(p) >= 12:
        out.append(p[:12])
        out.append(p[-12:])
    out.append(p)
    return list(dict.fromkeys(x for x in out if len(x) >= 2))


def _plain_has(haystack, needles):
    if not haystack or not needles:
        return False
    for nd in needles:
        if nd in haystack:
            return True
    return False


def _pick_anchor_line(rows, from_end=False):
    seq = list(reversed(rows)) if from_end else list(rows)
    best = ""
    best_len = 0
    for r in seq:
        line = r["line"] if isinstance(r, sqlite3.Row) else r[0]
        plen = len(_plain_for_match(line))
        if plen >= 8:
            return line
        if plen > best_len:
            best = line
            best_len = plen
    return best


def _slice_body_by_needles(body, ch_title, start_needles, end_needles, clip_start, clip_end, head_plain="",
                           next_needles=None, lead=()):
    if not clip_start and not clip_end:
        return body

    def elem_plain(node):
        if isinstance(node, NavigableString):
            return _plain_for_match(str(node))
        parts = []
        stack = [node]
        while stack:
            cur = stack.pop()
            if isinstance(cur, NavigableString):
                if type(cur) is NavigableString:
                    parts.append(str(cur))
                continue
            if not isinstance(cur, Tag):
                continue
            nm = (cur.name or "").lower()
            if nm in ("rt", "rp"):
                continue
            if nm == "img":
                alt = cur.get("alt")
                if alt:
                    parts.append(str(alt))
                continue
            kids = cur.contents
            for k in reversed(kids):
                stack.append(k)
        return _plain_for_match("".join(parts))

    container = body
    for _ in range(6):
        elems = [c for c in container.contents if isinstance(c, Tag) or (isinstance(c, NavigableString) and c.strip())]
        if len(elems) == 1 and isinstance(elems[0], Tag) and elems[0].name in ("div", "section", "article", "main"):
            container = elems[0]
            continue
        if elems and len(elems) > 1:
            plains = [elem_plain(el) for el in elems]
            s_hits = [i for i, pl in enumerate(plains) if _plain_has(pl, start_needles)] if clip_start and start_needles else []
            e_hits = [i for i, pl in enumerate(plains) if _plain_has(pl, end_needles)] if clip_end and end_needles else []
            only_idx = None
            if s_hits and e_hits and s_hits[0] == e_hits[-1]:
                only_idx = s_hits[0]
            elif s_hits and not clip_end and len(s_hits) == 1:
                if not any(plains[s_hits[0] + 1:]):
                    only_idx = s_hits[0]
            elif e_hits and not clip_start and len(e_hits) == 1:
                if not any(plains[:e_hits[0]]):
                    only_idx = e_hits[0]
            if only_idx is not None and isinstance(elems[only_idx], Tag) and elems[only_idx].name in ("div", "section", "article", "main"):
                inner = [c for c in elems[only_idx].contents if isinstance(c, Tag) or (isinstance(c, NavigableString) and c.strip())]
                if len(inner) > 1:
                    container = elems[only_idx]
                    continue
        break

    elems = [c for c in container.contents if isinstance(c, Tag) or (isinstance(c, NavigableString) and c.strip())]
    if len(elems) <= 1:
        only = elem_plain(elems[0]) if elems else ""
        if not only or (clip_start and start_needles and not _plain_has(only, start_needles)):
            return None
        if clip_end and next_needles and _plain_has(only, next_needles) and not _plain_has(only, end_needles or []):
            return None
        return body

    plains = [elem_plain(el) for el in elems]
    lo = 0
    hi = len(elems) - 1
    if clip_start and start_needles:
        found = next((i for i, pl in enumerate(plains) if _plain_has(pl, start_needles)), None)
        if found is None:
            return None
        lo = found
        # A heading, or one of the chapter's lines before its first long line, comes too when it
        # is just before the start, across up to three blank elements.
        ch_norm = _plain_for_match(ch_title.split("｜")[-1] if ch_title else "")
        lead_set = set(lead)
        cur = lo
        for _ in range(6):
            if cur <= 0:
                break
            prev_el = elems[cur - 1]
            prev_p = plains[cur - 1]
            is_head_tag = isinstance(prev_el, Tag) and prev_el.name in ("h1", "h2", "h3", "h4", "h5", "h6")
            if not prev_p and not is_head_tag and lo - cur < 3:
                cur -= 1
                continue
            # A title inside a long element (a list of contents) is not this chapter's heading.
            near_title = ch_norm and ((ch_norm in prev_p and len(prev_p) <= 2 * len(ch_norm) + 20) or prev_p in ch_norm)
            matches_title = bool(prev_p and (near_title or (head_plain and prev_p == head_plain)))
            if is_head_tag or matches_title or prev_p in lead_set:
                cur -= 1
                lo = cur
            else:
                break
    if clip_end and end_needles:
        cap = len(plains)
        if next_needles:
            own = start_needles or []
            nxt_cap = next((i for i in range(lo + 1, len(plains))
                            if any(plains[i].startswith(n) for n in next_needles) and not _plain_has(plains[i], own)), None)
            if nxt_cap is not None:
                cap = nxt_cap
        found = None
        for i in range(cap - 1, lo - 1, -1):
            if _plain_has(plains[i], end_needles):
                found = i
                break
        if found is None and cap < len(plains):
            for i in range(len(plains) - 1, cap - 1, -1):
                if _plain_has(plains[i], end_needles):
                    found = i
                    break
        if found is None:
            heads = [n for n in (next_needles or []) if n]
            own = start_needles or []
            first = next((i for i, pl in enumerate(plains) if own and _plain_has(pl, own)), lo)
            nxt = next((i for i in range(max(lo, first) + 1, len(plains))
                        if any(plains[i].startswith(n) for n in heads) and not _plain_has(plains[i], own)), None)
            if nxt is None:
                return None
            found = nxt - 1
        hi = found
    if lo > hi:
        return None
    wrapper = BeautifulSoup("<div></div>", "html.parser").div
    for el in elems[lo:hi + 1]:
        wrapper.append(el.extract())
    return wrapper


def _epub_db_fallback(db_epub, file_key, folder, reason, detail=""):
    _log_reader_fallback("epub", file_key, reason, detail)
    try:
        rng = db_epub.execute("SELECT first_rowid, last_rowid FROM chapters WHERE file = ? LIMIT 1", (file_key,)).fetchone()
    except sqlite3.OperationalError:
        rng = None
    if rng:
        rows = db_epub.execute(
            "SELECT rowid, line FROM epubs WHERE rowid BETWEEN ? AND ? AND file = ? ORDER BY rowid ASC",
            (rng["first_rowid"], rng["last_rowid"], file_key),
        ).fetchall()
    else:
        rows = db_epub.execute(
            "SELECT rowid, line FROM epubs WHERE file = ? ORDER BY rowid ASC", (file_key,)
        ).fetchall()
    from aobana.search.engine import query_highlight_args
    from aobana.search.furigana import highlight_and_furigana, work_key
    wk = work_key("epub", file_key)
    hl = query_highlight_args("", "epub")
    lines = []
    total_chars = 0
    for r in rows:
        _part_check()
        line = r["line"]
        total_chars += len(line)
        lines.append({
            "rowid": r["rowid"],
            "html": highlight_and_furigana(line, mark=False, bold=False, work=wk, **hl),
            "text": line,
        })
    return {
        "media": "epub",
        "folder": folder,
        "file": file_key,
        "source": "db",
        "fallback_reason": reason,
        "writing_mode": "horizontal",
        "css": "",
        "html": "",
        "lines": lines,
        "char_count": total_chars,
    }


def _load_epub_chapter(db_epub, folder, file_key):
    try:
        ch_row = db_epub.execute(
            "SELECT source_id, first_rowid, last_rowid, lines FROM chapters WHERE file = ? LIMIT 1",
            (file_key,),
        ).fetchone()
    except sqlite3.OperationalError:
        return _epub_db_fallback(db_epub, file_key, folder, "chapters_missing")
    if ch_row is None:
        r0 = db_epub.execute("SELECT source_id, MIN(rowid) AS a, MAX(rowid) AS b FROM epubs WHERE file = ?", (file_key,)).fetchone()
        if not r0 or r0["source_id"] is None:
            return None
        source_id, first_rid, last_rid = r0["source_id"], r0["a"], r0["b"]
    else:
        source_id, first_rid, last_rid = ch_row["source_id"], ch_row["first_rowid"], ch_row["last_rowid"]

    src = db_epub.execute("SELECT relpath, title, author FROM sources WHERE id = ?", (source_id,)).fetchone()
    if not src:
        return _epub_db_fallback(db_epub, file_key, folder, "source_missing")

    epub_path = paths.resolve_media_path("books", src["relpath"])
    if not epub_path or not os.path.isfile(epub_path):
        return _epub_db_fallback(db_epub, file_key, folder, "file_missing", src["relpath"])

    all_chs = db_epub.execute(
        "SELECT file, first_rowid, last_rowid FROM chapters WHERE source_id = ? ORDER BY first_rowid ASC",
        (source_id,),
    ).fetchall()
    ch_idx = next((i for i, c in enumerate(all_chs) if c["file"] == file_key), 0)
    own_rows = db_epub.execute(
        "SELECT line FROM epubs WHERE rowid BETWEEN ? AND ? AND file = ? ORDER BY rowid ASC",
        (first_rid, last_rid, file_key),
    ).fetchall()
    first_rows = own_rows[:5]
    last_rows = own_rows[-4:]
    first_line = _pick_anchor_line(first_rows, from_end=False)
    head_plain = _plain_for_match(first_rows[0]["line"]) if first_rows else ""
    last_line = _pick_anchor_line(last_rows, from_end=True)
    prev_last = ""
    next_first = ""
    if ch_idx > 0:
        p_lo, p_hi, p_file = all_chs[ch_idx - 1]["first_rowid"], all_chs[ch_idx - 1]["last_rowid"], all_chs[ch_idx - 1]["file"]
        p_rows = db_epub.execute(
            "SELECT line FROM epubs WHERE rowid BETWEEN ? AND ? AND file = ? ORDER BY rowid ASC",
            (max(p_lo, p_hi - 3), p_hi, p_file),
        ).fetchall()
        prev_last = _pick_anchor_line(p_rows, from_end=True)
    if ch_idx + 1 < len(all_chs):
        n_lo, n_hi, n_file = all_chs[ch_idx + 1]["first_rowid"], all_chs[ch_idx + 1]["last_rowid"], all_chs[ch_idx + 1]["file"]
        n_rows = db_epub.execute(
            "SELECT line FROM epubs WHERE rowid BETWEEN ? AND ? AND file = ? ORDER BY rowid ASC LIMIT 5",
            (n_lo, min(n_hi, n_lo + 4), n_file),
        ).fetchall()
        next_first = _pick_anchor_line(n_rows, from_end=False)

    ch_part = file_key.split("\\", 1)[1] if "\\" in file_key else file_key
    ch_title = re.sub(r"^\d+\.", "", ch_part)

    try:
        meta = _epub_parse_meta(epub_path)
    except (OSError, zipfile.BadZipFile, KeyError, _ET.ParseError) as exc:
        return _epub_db_fallback(db_epub, file_key, folder, "file_unreadable", f"{type(exc).__name__}: {exc}")

    spine = meta["spine"]
    if not spine:
        return _epub_db_fallback(db_epub, file_key, folder, "empty_spine", src["relpath"])

    start_needles = _needle_variants(first_line)
    end_needles = _needle_variants(last_line)
    prev_needles = _needle_variants(prev_last)
    next_needles = _needle_variants(next_first)

    try:
        with zipfile.ZipFile(epub_path, "r") as zf:
            plain_cache = {}
            raw_cache = {}

            def get_raw(idx):
                if idx not in raw_cache:
                    raw_cache[idx] = zf.read(spine[idx])
                return raw_cache[idx]

            def get_plain(idx):
                if idx not in plain_cache:
                    plain_cache[idx] = _xhtml_plain(get_raw(idx))
                return plain_cache[idx]

            ch_norm = re.sub(r"[\s\u3000]+", "", ch_title)
            ch_tail = re.sub(r"[\s\u3000]+", "", ch_title.split("｜")[-1]) if "｜" in ch_title else ch_norm
            toc_cands = []
            for sp_i, norm_lab, raw_lab in meta["toc"]:
                lab_tail = re.sub(r"[\s\u3000]+", "", raw_lab.split("｜")[-1]) if "｜" in raw_lab else norm_lab
                if norm_lab == ch_norm or (ch_tail and (norm_lab == ch_tail or lab_tail == ch_tail)):
                    if sp_i not in toc_cands:
                        toc_cands.append(sp_i)

            # The first file holding the chapter's first line is the start, and the end is the
            # file with its last line, or the one before the next chapter starts, within 40 files.
            # That pick stays when what it spans fits the chapter: at most three times its text
            # (plus 3,000 characters), and at least half of its lines in it. Otherwise each later
            # file holding the first line is tried, with no 40-file cap, and the first that reaches
            # the last line before the next chapter starts and fits is taken. The old pick stays if
            # none fits; the index is shown only when nothing reaches an end.
            own_plains = [x for x in (_plain_for_match(r["line"]) for r in own_rows) if x]
            budget = 3 * sum(len(x) for x in own_plains) + 3000
            probes = [x for x in own_plains if len(x) >= 4]
            if len(probes) > 60:
                step_p = len(probes) / 60
                probes = [probes[int(i * step_p)] for i in range(60)]

            def start_order():
                for cand in toc_cands:
                    yield cand
                    if cand + 1 < len(spine):
                        yield cand + 1
                guess = min(len(spine) - 1, int(ch_idx * len(spine) / max(len(all_chs), 1)))
                yield guess
                for step in range(1, len(spine)):
                    if guess + step < len(spine):
                        yield guess + step
                    if guess - step >= 0:
                        yield guess - step

            def starts():
                seen = set()
                for cand in start_order():
                    if cand in seen:
                        continue
                    seen.add(cand)
                    if _plain_has(get_plain(cand), start_needles):
                        yield cand

            def near_end(lo):
                if not end_needles or _plain_has(get_plain(lo), end_needles):
                    return lo
                for idx in range(lo + 1, min(len(spine) - 1, lo + 40) + 1):
                    if _plain_has(get_plain(idx), end_needles):
                        return idx
                    if next_needles and _plain_has(get_plain(idx), next_needles):
                        return max(lo, idx - 1)
                return None

            def far_end(lo):
                size = 0
                for idx in range(lo, len(spine)):
                    plain = get_plain(idx)
                    if _plain_has(plain, end_needles):
                        return idx
                    if idx > lo:
                        if next_needles and _plain_has(plain, next_needles):
                            return None
                        size += len(plain)
                        if size > budget:
                            return None
                return None

            def fits(lo, hi, other=False):
                a = get_plain(lo)
                # The anchors are the first and last long lines: short lines can come before and after.
                s0 = min([h for h in (a.find(n) for n in start_needles) if h >= 0] or [0])
                s = max(0, s0 - 200)
                z = get_plain(hi)
                e = max([z.rfind(n) + len(n) + 200 for n in end_needles if z.rfind(n) >= 0] or [len(z)])
                # Another start before the previous chapter's last line is a quote inside that chapter.
                if other and prev_needles and _plain_has(a[s0 + 1:] if lo != hi else a[s0 + 1:e - 200], prev_needles):
                    return False
                if lo == hi:
                    text = a[s:e] if e > s else a[s:]
                else:
                    text = a[s:] + "".join(get_plain(i) for i in range(lo + 1, hi)) + z[:e]
                if len(text) > budget:
                    return False
                return not probes or sum(1 for x in probes if x in text) * 2 >= len(probes)

            first_start = next(starts(), None) if start_needles else None

            if first_start is None and len(toc_cands) == 1:
                first_start = toc_cands[0]

            if first_start is None:
                return _epub_db_fallback(db_epub, file_key, folder, "chapter_unmapped", ch_title)

            near_hi = near_end(first_start)
            lo_idx = hi_idx = None
            if near_hi is not None and fits(first_start, near_hi):
                lo_idx, hi_idx = first_start, near_hi
            elif start_needles and end_needles:
                for n_tried, cand in enumerate(starts()):
                    if n_tried >= 8:
                        break
                    hi = far_end(cand)
                    if hi is not None and fits(cand, hi, other=True):
                        lo_idx, hi_idx = cand, hi
                        break
            if lo_idx is None:
                if near_hi is None:
                    return _epub_db_fallback(db_epub, file_key, folder, "end_unmatched", ch_title)
                lo_idx, hi_idx = first_start, near_hi

            # The short lines before the first long line can be a page of their own (a heading
            # page): the file before comes too, across up to two empty files, when it holds nothing
            # but the start of those lines and nothing of the previous chapter's last line.
            anchor = _plain_for_match(first_line)
            lead_lines = []
            for r in first_rows:
                x = _plain_for_match(r["line"])
                if x == anchor:
                    break
                if x:
                    lead_lines.append(x)
            lead = "".join(lead_lines)
            if lead and lo_idx > 0 and not (prev_needles and _plain_has(get_plain(lo_idx), prev_needles)):
                a = get_plain(lo_idx)
                s0 = min([h for h in (a.find(n) for n in start_needles) if h >= 0] or [0])
                j = lo_idx - 1
                while j > 0 and lo_idx - j <= 2 and not get_plain(j):
                    j -= 1
                pp = get_plain(j)
                if pp and lead.startswith(pp) and pp not in a[:s0] and not _plain_has(pp, prev_needles):
                    lo_idx = j

            clip_start = bool(prev_needles and _plain_has(get_plain(lo_idx), prev_needles))
            clip_end = bool(next_needles and _plain_has(get_plain(hi_idx), next_needles))

            raw_css_seen = OrderedDict()
            html_parts = []
            detected_wm = None
            total_chars = 0

            for idx in range(lo_idx, hi_idx + 1):
                _part_check()
                member = spine[idx]
                page_dir = posixpath.dirname(member)
                raw_xhtml = get_raw(idx)
                soup = BeautifulSoup(raw_xhtml, "html.parser")

                page_css = []
                for link in soup.find_all("link"):
                    rel = " ".join(link.get("rel") or []).lower() if isinstance(link.get("rel"), list) else str(link.get("rel") or "").lower()
                    if "stylesheet" in rel or str(link.get("type") or "").lower() == "text/css":
                        css_member = _norm_zip_member(page_dir, link.get("href"))
                        if css_member and css_member in meta["zip_names"]:
                            if css_member not in raw_css_seen:
                                raw_css_seen[css_member] = zf.read(css_member).decode("utf-8", errors="replace")
                            page_css.append(raw_css_seen[css_member])
                for st_tag in soup.find_all("style"):
                    st_txt = st_tag.string or st_tag.get_text() or ""
                    if st_txt.strip():
                        page_css.append(st_txt)
                        raw_css_seen[f"__inline_{idx}_{len(raw_css_seen)}"] = st_txt

                if detected_wm is None:
                    detected_wm = _detect_epub_writing_mode(soup, page_css, meta["ppd"])

                body = soup.find("body") or soup
                orig_body_id = (body.get("id") or "").strip() if isinstance(body, Tag) else ""
                do_start = clip_start and idx == lo_idx
                do_end = clip_end and idx == hi_idx
                if do_start or do_end:
                    sliced = _slice_body_by_needles(body, ch_title, start_needles, end_needles, do_start, do_end,
                                                    head_plain=head_plain, next_needles=next_needles if do_end else None,
                                                    lead=lead_lines)
                    if sliced is None:
                        return _epub_db_fallback(db_epub, file_key, folder, "slice_unmatched", ch_title)
                    body = sliced

                _sanitize_epub_fragment(body, source_id, page_dir, meta["zip_names"], cur_member=member)
                inner = body.decode_contents()
                total_chars += len(_plain_for_match(body.get_text()))
                sec_id_attr = ""
                if orig_body_id and not do_start:
                    pref_id = orig_body_id if orig_body_id.startswith("rm-ep-") else f"rm-ep-{orig_body_id}"
                    sec_id_attr = f' id="{_html_mod.escape(pref_id, quote=True)}"'
                html_parts.append(f'<section class="rm-epub-spine"{sec_id_attr} data-spine="{idx}" data-member="{_html_mod.escape(member, quote=True)}">{inner}</section>')

            scoped_css = _sanitize_epub_css(list(raw_css_seen.values()))
            return {
                "media": "epub",
                "folder": folder,
                "file": file_key,
                "source_id": source_id,
                "source": "file",
                "fallback_reason": None,
                "writing_mode": detected_wm or "horizontal",
                "css": scoped_css,
                "html": "\n".join(html_parts),
                "lines": [],
                "char_count": total_chars,
            }
    except (OSError, zipfile.BadZipFile, KeyError, RuntimeError, ValueError, zlib.error, EOFError) as exc:
        return _epub_db_fallback(db_epub, file_key, folder, "file_unreadable", f"{type(exc).__name__}: {exc}")


@app.route("/api/reading/fonts", methods=["GET"])
def api_reading_fonts():
    from aobana.server import system_fonts
    return jsonify({"fonts": system_fonts.japanese_fonts()})


@app.route("/api/reading/epub-asset/<int:source_id>/<path:member>", methods=["GET"])
def api_reading_epub_asset(source_id, member):
    _, db_epub = server.get_db()
    if db_epub is None:
        return make_response("", 404)
    src = db_epub.execute("SELECT relpath FROM sources WHERE id = ?", (source_id,)).fetchone()
    if not src:
        return make_response("", 404)
    epub_path = paths.resolve_media_path("books", src["relpath"])
    if not epub_path or not os.path.isfile(epub_path):
        return make_response("", 404)
    norm = _norm_zip_member("", member)
    if not norm:
        return make_response("", 400)
    ext = os.path.splitext(norm)[1].lower()
    mime = _EPUB_ASSET_MIMES.get(ext)
    if not mime:
        return make_response("", 403)
    try:
        with zipfile.ZipFile(epub_path, "r") as zf:
            info = zf.getinfo(norm)
            if info.file_size > 25 * 1024 * 1024:
                return make_response("", 413)
            data = zf.read(info)
    except (OSError, zipfile.BadZipFile, KeyError):
        return make_response("", 404)
    resp = Response(data, mimetype=mime)
    resp.headers["Cache-Control"] = "private, max-age=3600"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    if ext == ".svg":
        resp.headers["Content-Security-Policy"] = "sandbox"
    return resp


def _anchor_plain(raw_xhtml, frag, limit=600):
    soup = BeautifulSoup(raw_xhtml, "html.parser")
    for t in soup.find_all(["rt", "rp"]):
        t.decompose()
    start = None
    if frag:
        start = soup.find(id=frag) or soup.find(attrs={"name": frag})
    if start is None:
        start = soup.find("body") or soup
        pieces = [start.get_text()]
    else:
        pieces = []
        blk = start.find_parent(["p", "li", "dd", "dt", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6"])
        if blk is not None:
            pre = []
            for s in blk.descendants:
                if s is start:
                    break
                if isinstance(s, NavigableString) and not isinstance(s, (Comment, CData, Declaration, Doctype, ProcessingInstruction)):
                    pre.append(str(s))
            pre_txt = "".join(pre).rsplit("。", 1)[-1][-240:]
            if pre_txt:
                pieces.append(pre_txt)
        for s in start.find_all_next(string=True):
            if isinstance(s, (Comment, CData, Declaration, Doctype, ProcessingInstruction)):
                continue
            pieces.append(str(s))
            if sum(len(p) for p in pieces) > limit * 2:
                break
    text = unicodedata.normalize("NFKC", "".join(pieces))
    return _PLAIN_NOISE_RE.sub("", text)[:limit]


@app.route("/api/reading/resolve-link", methods=["GET"])
def api_reading_resolve_link():
    file_key = request.args.get("file") or ""
    target = request.args.get("target") or ""
    if not file_key or not target:
        return jsonify({"error": "Missing file or target"}), 400
    _, db_epub = server.get_db()
    if db_epub is None:
        return jsonify({"error": "Books database unavailable"}), 404
    try:
        row = db_epub.execute("SELECT source_id FROM chapters WHERE file = ? LIMIT 1", (file_key,)).fetchone()
    except sqlite3.OperationalError:
        row = None
    if not row:
        return jsonify({"error": "Chapter not found"}), 404
    source_id = row["source_id"]
    src = db_epub.execute("SELECT relpath FROM sources WHERE id = ?", (source_id,)).fetchone()
    epub_path = paths.resolve_media_path("books", src["relpath"]) if src else None
    if not epub_path or not os.path.isfile(epub_path):
        return jsonify({"error": "Book file missing"}), 404
    member, _, frag = target.partition("#")
    frag = urllib.parse.unquote(frag)
    member = _norm_zip_member("", member)
    try:
        meta = _epub_parse_meta(epub_path)
        if not member or member not in meta["spine_idx"]:
            return jsonify({"error": "Target not in the book's reading order"}), 404
        with zipfile.ZipFile(epub_path, "r") as zf:
            tp = _anchor_plain(zf.read(member), frag)
    except (OSError, zipfile.BadZipFile, KeyError, RuntimeError, ValueError, zlib.error, _ET.ParseError):
        return jsonify({"error": "Book file unreadable"}), 404
    chs = db_epub.execute(
        "SELECT file, first_rowid, last_rowid FROM chapters WHERE source_id = ? ORDER BY first_rowid", (source_id,)
    ).fetchall()
    if not chs or not tp:
        return jsonify({"error": "Target not found"}), 404
    lo, hi = chs[0]["first_rowid"], max(c["last_rowid"] for c in chs)
    rows = [(r["file"], _plain_for_match(r["line"])) for r in db_epub.execute(
        "SELECT file, line FROM epubs WHERE rowid BETWEEN ? AND ? AND source_id = ? ORDER BY rowid", (lo, hi, source_id))]
    min_len = min(4, len(tp))
    ch_pos = {c["file"]: i for i, c in enumerate(chs)}
    guess = meta["spine_idx"][member] * len(chs) / max(1, len(meta["spine"]))
    skip_file = file_key if request.args.get("exclude_source") == "1" else None
    best = None
    for i, (f, plain) in enumerate(rows):
        if len(plain) < min_len or f == skip_file:
            continue
        pos = tp.find(plain)
        if pos < 0:
            continue
        score, cur, j = len(plain), pos + len(plain), i + 1
        while j < len(rows) and j - i <= 15 and cur < len(tp):
            pj = rows[j][1]
            j += 1
            if not pj:
                continue
            k = tp.find(pj, cur)
            if k < 0 or k - cur > 40:
                break
            score += len(pj)
            cur = k + len(pj)
        key = (score, -abs(ch_pos.get(f, 0) - guess), -pos)
        if best is None or key > best[0]:
            best = (key, f)
    if best is None:
        return jsonify({"error": "Target not found"}), 404
    return jsonify({"file": best[1], "member": member, "fragment": frag, "spine": meta["spine_idx"][member]})


@app.route("/api/reading/chapters", methods=["GET"])
def api_reading_chapters():
    media = (request.args.get("media") or "").strip().lower()
    folder = request.args.get("folder") or ""
    if media not in _READER_ALLOWED_MEDIA:
        return jsonify({"error": "Reading mode supports epub, subs, and manga only"}), 400
    if not folder:
        return jsonify({"error": "Missing folder"}), 400
    with app.test_request_context(f"/api/episodes?folder={urllib.parse.quote(folder)}&media={urllib.parse.quote(media)}"):
        ep_resp = api_episodes()
    if isinstance(ep_resp, tuple):
        ep_resp = ep_resp[0]
    data = ep_resp.get_json(silent=True) or {"files": []}
    with _READER_STATE_LOCK:
        st = _read_reader_state()
    work_key = f"{media}:{folder}"
    return jsonify({
        "media": media,
        "folder": folder,
        "files": data.get("files", []),
        "prefs": st["prefs"][media],
        "work": st["works"].get(work_key),
    })


_SUB_START_TS_RE = re.compile(r"(\d{1,3}:\d{2}:\d{2})")


def _extract_timed_subtitles(srt_content, relpath):
    from aobana.indexing import indexer as sub_idx
    logs = [v for v in (getattr(sub_idx, "_EXCLUDED_LOG", None), getattr(sub_idx, "_WAKATI_LOG", None), getattr(sub_idx, "_NOTES", None)) if isinstance(v, list)]
    marks = [len(v) for v in logs]
    try:
        return _extract_timed_subtitles_inner(srt_content, relpath, sub_idx)
    finally:
        for v, n in zip(logs, marks):
            del v[n:]


def _extract_timed_subtitles_inner(srt_content, relpath, sub_idx):
    native_aliases = sub_idx.source_readings(srt_content)
    unwrap = sub_idx.bracket_wrapped(srt_content)
    items = []
    group_texts = []
    current_ts = None

    def flush():
        if current_ts is not None and group_texts:
            joined = sub_idx._merge_group(group_texts)
            if not sub_idx.is_music_only_line(joined):
                plain = sub_idx.bar_ruby_plain(joined)
                if items and sub_idx.bar_ruby_plain(items[-1][1]) == plain and (items[-1][1] == joined or plain in (items[-1][1], joined)):
                    if len(joined) > len(items[-1][1]):
                        items[-1] = (items[-1][0], joined)
                else:
                    items.append((current_ts, joined))

    stripped = [raw.strip() for raw in srt_content.splitlines()]
    for i, line in enumerate(stripped):
        if not line:
            continue
        if not i & 63:
            _part_check()
        if sub_idx.is_line_number(line) and sub_idx._timecode_follows(stripped, i):
            continue
        if sub_idx.is_timecode(line):
            flush()
            m_ts = _SUB_START_TS_RE.search(line)
            current_ts = m_ts.group(1) if m_ts else ""
            group_texts = []
            continue
        if sub_idx.is_punctuation_line(line):
            continue
        if unwrap:
            m = sub_idx.WHOLE_BRACKET_RE.fullmatch(line)
            if m:
                line = m.group(1).strip()
                if not line:
                    continue
        cleaned = sub_idx.clean_line(line, relpath, native_aliases)
        if cleaned:
            group_texts.append(cleaned)
    flush()

    raw_texts = [t for _, t in items]
    cleaned_texts, _ = sub_idx.assess_and_clean_wakati(raw_texts, relpath)
    out = []
    for (ts, _), txt in zip(items, cleaned_texts):
        fin = sub_idx.finish_caption(txt)
        if fin:
            out.append((ts, fin))
    if not any(sub_idx.JAPANESE_CHARS_RE.search(t) for _, t in out):
        return []
    return out


def _subs_db_fallback(db_subs, folder, file_key, reason, detail=""):
    _log_reader_fallback("subs", file_key, reason, detail)
    from aobana.indexing import source_ranges
    src = db_subs.execute("SELECT id FROM sources WHERE relpath = ?", (file_key,)).fetchone()
    if src is not None and source_ranges.ready(db_subs):
        rows = []
        for first, last, _n in source_ranges.spans(db_subs, src["id"]):
            rows += db_subs.execute(
                "SELECT rowid, line FROM subtitles WHERE rowid BETWEEN ? AND ? AND source_id = ? ORDER BY rowid ASC",
                (first, last, src["id"]),
            ).fetchall()
    elif src is not None:
        rows = db_subs.execute(
            "SELECT rowid, line FROM subtitles WHERE source_id = ? AND file = ? ORDER BY rowid ASC",
            (src["id"], file_key),
        ).fetchall()
    else:
        rows = db_subs.execute(
            "SELECT rowid, line FROM subtitles WHERE file = ? ORDER BY rowid ASC",
            (file_key,),
        ).fetchall()
    from aobana.search.engine import query_highlight_args
    from aobana.search.furigana import highlight_and_furigana, work_key
    wk = work_key("subs", file_key)
    hl = query_highlight_args("", "subs")
    lines = []
    total_chars = 0
    for r in rows:
        _part_check()
        line = r["line"]
        total_chars += len(line)
        lines.append({
            "start": "",
            "html": highlight_and_furigana(line, mark=False, bold=False, work=wk, **hl),
            "text": line,
        })
    return {
        "media": "subs",
        "folder": folder,
        "file": file_key,
        "source": "db",
        "fallback_reason": reason,
        "writing_mode": "horizontal",
        "lines": lines,
        "char_count": total_chars,
    }


def _load_subtitle_episode(db_subs, folder, file_key):
    src = db_subs.execute("SELECT id, relpath FROM sources WHERE relpath = ?", (file_key,)).fetchone()
    relpath = src["relpath"] if src else file_key
    sub_path = paths.resolve_media_path("subs", relpath)
    if not sub_path or not os.path.isfile(sub_path):
        return _subs_db_fallback(db_subs, folder, relpath, "file_missing", relpath)

    try:
        from aobana.indexing import subtitle_input, indexer as sub_idx
        info = subtitle_input.read(sub_path)
        content = info["text"]
        if info["format"] == "ass":
            content = sub_idx.ass_to_srt(content)
        timed = _extract_timed_subtitles(content, relpath)
    except Exception as exc:
        return _subs_db_fallback(db_subs, folder, relpath, "file_unreadable", f"{type(exc).__name__}: {exc}")
    if not timed:
        return _subs_db_fallback(db_subs, folder, relpath, "file_no_lines", relpath)

    from aobana.search.engine import query_highlight_args
    from aobana.search.furigana import highlight_and_furigana, work_key
    wk = work_key("subs", relpath)
    hl = query_highlight_args("", "subs")
    lines = []
    total_chars = 0
    for ts, line in timed:
        _part_check()
        total_chars += len(line)
        lines.append({
            "start": ts,
            "html": highlight_and_furigana(line, mark=False, bold=False, work=wk, **hl),
            "text": line,
        })
    return {
        "media": "subs",
        "folder": folder,
        "file": relpath,
        "source": "file",
        "fallback_reason": None,
        "writing_mode": "horizontal",
        "lines": lines,
        "char_count": total_chars,
    }


def _manga_db_fallback(db_manga, folder, file_key, source_id, reason, detail=""):
    _log_reader_fallback("manga", file_key, reason, detail)
    if source_id is not None:
        rows = []
        bounds = None
        try:
            if db_manga.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='source_ranges'").fetchone():
                sr = db_manga.execute(
                    "SELECT MIN(first_rowid), MAX(last_rowid) FROM source_ranges WHERE source_id = ?",
                    (source_id,),
                ).fetchone()
                if sr and sr[0] is not None:
                    bounds = (sr[0], sr[1])
            elif folder and db_manga.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='manga_repeat_titles'").fetchone():
                rt = db_manga.execute("SELECT spans FROM manga_repeat_titles WHERE title = ?", (folder,)).fetchone()
                if rt and rt[0]:
                    spans = _json.loads(rt[0])
                    if spans:
                        bounds = (min(s[0] for s in spans), max(s[1] for s in spans))
        except (sqlite3.OperationalError, ValueError, TypeError):
            bounds = None
        if bounds is not None:
            rows = db_manga.execute(
                "SELECT m.rowid, m.line, COALESCE(p.page, 1) AS page FROM manga m "
                "LEFT JOIN manga_pages p ON p.rowid = m.rowid "
                "WHERE m.rowid BETWEEN ? AND ? AND m.source_id = ? ORDER BY m.rowid ASC",
                (bounds[0], bounds[1], source_id),
            ).fetchall()
        if not rows:
            rows = db_manga.execute(
                "SELECT m.rowid, m.line, COALESCE(p.page, 1) AS page FROM manga m "
                "LEFT JOIN manga_pages p ON p.rowid = m.rowid "
                "WHERE m.source_id = ? ORDER BY m.rowid ASC",
                (source_id,),
            ).fetchall()
    else:
        rows = db_manga.execute(
            "SELECT m.rowid, m.line, COALESCE(p.page, 1) AS page FROM manga m "
            "LEFT JOIN manga_pages p ON p.rowid = m.rowid "
            "WHERE m.file = ? ORDER BY m.rowid ASC",
            (file_key,),
        ).fetchall()
    from aobana.search.engine import query_highlight_args
    from aobana.search.furigana import highlight_and_furigana, work_key
    wk = work_key("manga", file_key)
    hl = query_highlight_args("", "manga")
    by_page = OrderedDict()
    total_chars = 0
    for r in rows:
        _part_check()
        pno = int(r["page"] or 1)
        line = r["line"]
        total_chars += len(line)
        by_page.setdefault(pno, []).append({
            "box": None,
            "vertical": True,
            "font_size": 16,
            "text": line,
            "html": highlight_and_furigana(line, mark=False, bold=False, work=wk, **hl),
        })
    pages = [{
        "page": pno,
        "img_width": 0,
        "img_height": 0,
        "image_url": None,
        "blocks": blks,
    } for pno, blks in by_page.items()]
    return {
        "media": "manga",
        "folder": folder,
        "file": file_key,
        "source_id": source_id,
        "source": "db",
        "fallback_reason": reason,
        "pages": pages,
        "char_count": total_chars,
    }


def _load_manga_volume(db_manga, folder, file_key):
    if "\\" in file_key:
        series, volume = file_key.split("\\", 1)
    else:
        series, volume = folder, file_key
    src = db_manga.execute(
        "SELECT id, relpath, title, volume FROM sources WHERE title = ? AND volume = ? LIMIT 1",
        (series, volume),
    ).fetchone()
    if src is None:
        return _manga_db_fallback(db_manga, folder, file_key, None, "file_missing", file_key)

    source_id = src["id"]
    relpath = src["relpath"]
    mokuro_path = paths.resolve_media_path("manga", relpath)
    if not mokuro_path or not os.path.isfile(mokuro_path):
        return _manga_db_fallback(db_manga, folder, file_key, source_id, "file_missing", relpath)

    try:
        with open(mokuro_path, encoding="utf-8-sig") as fh:
            doc = _json.load(fh)
        raw_pages = doc.get("pages") if isinstance(doc, dict) else None
        if not isinstance(raw_pages, list):
            raise ValueError("missing pages list")
    except (OSError, ValueError, TypeError) as exc:
        return _manga_db_fallback(db_manga, folder, file_key, source_id, "file_unreadable", f"{type(exc).__name__}: {exc}")

    from aobana.indexing import manga_fused, manga_indexer as m_idx
    from aobana.search.engine import query_highlight_args
    from aobana.search.furigana import highlight_and_furigana, work_key
    from aobana.utils import normalize_manga_text
    wk = work_key("manga", file_key)
    hl = query_highlight_args("", "manga")

    img_dirs = library.manga_volume_image_dirs(mokuro_path)
    pages_out = []
    total_chars = 0
    excl_log = getattr(m_idx, "_EXCLUDED_LOG", None)
    excl_mark = len(excl_log) if isinstance(excl_log, list) else 0
    try:
        for page_no, pg in enumerate(raw_pages, 1):
            _part_check()
            if not isinstance(pg, dict):
                continue
            img_w = int(pg.get("img_width") or 0)
            img_h = int(pg.get("img_height") or 0)
            has_img = library.manga_volume_image_in_dirs(img_dirs, pg.get("img_path")) is not None
            image_url = f"/manga/image/{source_id}/{page_no}" if has_img else None
            raws = m_idx.attach_ruby(pg)
            blks_out = []
            for blk in m_idx.reading_order(pg):
                if not has_img:
                    _part_check()
                raw_lines = [str(ln) for ln in (blk.get("lines") or []) if str(ln).strip()]
                if not raw_lines:
                    continue
                joined = raws.get(id(blk), "".join(raw_lines).strip())
                if not joined:
                    continue
                vert = bool(blk.get("vertical"))
                cleaned = m_idx.VERTICAL_COLON_RE.sub("…", joined) if vert else joined
                unfused = m_idx.unfuse_ruby(normalize_manga_text(cleaned))
                norm_txt = manga_fused.unfuse(unfused)[0] or unfused or joined
                total_chars += len(norm_txt)
                box = blk.get("box")
                if not (isinstance(box, list) and len(box) == 4):
                    box = None
                blks_out.append({
                    "box": [float(v) for v in box] if box else None,
                    "vertical": vert,
                    "font_size": int(blk.get("font_size") or 16),
                    "lines": raw_lines,
                    "text": norm_txt,
                    "html": None if has_img else highlight_and_furigana(norm_txt, mark=False, bold=False, work=wk, **hl),
                })
            pages_out.append({
                "page": page_no,
                "img_width": img_w,
                "img_height": img_h,
                "image_url": image_url,
                "blocks": blks_out,
            })
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        return _manga_db_fallback(db_manga, folder, file_key, source_id, "file_unreadable", f"{type(exc).__name__}: {exc}")
    finally:
        if isinstance(excl_log, list):
            del excl_log[excl_mark:]

    return {
        "media": "manga",
        "folder": series,
        "file": file_key,
        "source_id": source_id,
        "source": "file",
        "fallback_reason": None,
        "pages": pages_out,
        "char_count": total_chars,
    }


@app.route("/api/reading/part", methods=["GET"])
def api_reading_part():
    media = (request.args.get("media") or "").strip().lower()
    folder = request.args.get("folder") or ""
    file_key = request.args.get("file") or ""
    if media not in _READER_ALLOWED_MEDIA:
        return jsonify({"error": "Reading mode supports epub, subs, and manga only"}), 400
    if not file_key:
        return jsonify({"error": "Missing file"}), 400
    try:
        seq = int(request.args.get("seq") or "")
    except ValueError:
        seq = None
    if not _part_begin((request.args.get("client") or "")[:80], seq):
        return jsonify({"superseded": True}), 409
    try:
        return _reading_part(media, folder, file_key)
    except _PartSuperseded:
        return jsonify({"superseded": True}), 409
    finally:
        _PART_CTX.key = None


def _reading_part(media, folder, file_key):
    if media == "epub":
        _, db_epub = server.get_db()
        if db_epub is None:
            return jsonify({"error": "Books database unavailable"}), 404
        res = _load_epub_chapter(db_epub, folder, file_key)
        if res is None:
            return jsonify({"error": "Chapter not found"}), 404
        return jsonify(res)

    if media == "subs":
        db_subs, _ = server.get_db()
        if db_subs is None:
            return jsonify({"error": "Subtitles database unavailable"}), 404
        res = _load_subtitle_episode(db_subs, folder, file_key)
        return jsonify(res)

    if media == "manga":
        db_manga = server.get_manga_db()
        if db_manga is None:
            return jsonify({"error": "Manga database unavailable"}), 404
        res = _load_manga_volume(db_manga, folder, file_key)
        return jsonify(res)

    return jsonify({"error": "Unsupported media"}), 400


@app.route("/api/reading/state", methods=["GET", "POST"])
def api_reading_state():
    if request.method == "GET":
        media = (request.args.get("media") or "").strip().lower()
        folder = request.args.get("folder") or ""
        if media and media not in _READER_ALLOWED_MEDIA:
            return jsonify({"error": "Reading mode supports epub, subs, and manga only"}), 400
        with _READER_STATE_LOCK:
            st = _read_reader_state()
        if media and folder:
            return jsonify({"prefs": st["prefs"][media], "work": st["works"].get(f"{media}:{folder}")})
        if media:
            return jsonify({"prefs": st["prefs"][media]})
        return jsonify({"prefs_by_media": st["prefs"], "works": st["works"]})

    server._require_page()
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify({"error": "Invalid payload"}), 400
    media = body.get("media") or ""
    folder = body.get("folder") or ""
    if not isinstance(media, str) or not isinstance(folder, str):
        return jsonify({"error": "Invalid payload"}), 400
    media = media.strip().lower()
    if media and media not in _READER_ALLOWED_MEDIA:
        return jsonify({"error": "Reading mode supports epub, subs, and manga only"}), 400
    with _READER_STATE_LOCK:
        st = _read_reader_state()
        if isinstance(body.get("prefs"), dict):
            if not media:
                return jsonify({"error": "Display settings need a media"}), 400
            merged = dict(st["prefs"][media])
            merged.update(body["prefs"])
            st["prefs"][media] = _clamp_prefs(merged)
        work_out = None
        if media and folder and isinstance(body.get("work"), dict):
            wkey = f"{media}:{folder}"
            st["works"][wkey] = _clean_work_state(body["work"], st["works"].get(wkey))
            work_out = st["works"][wkey]
        _write_reader_state(st)
    return jsonify({"ok": True, "prefs": st["prefs"][media] if media else None, "work": work_out})
