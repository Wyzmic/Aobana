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
    
    db_subs, db_epub = server.get_db()
    db_manga = server.get_manga_db()
    if rowid is None:
        return jsonify({"error": "Missing rowid"}), 400

    from aobana.search.engine import _search_targets, reader_target
    targets = _search_targets(server._media_connections(db_subs, db_epub), db_epub, media or 'all', db_manga)
    if media not in ("subs", "epub", "manga", "custom") and file:
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

    def query_corpus(db, table, media_type):
        if db is None:
            return []
        res = []
        text = "line" if media_type == "custom" else "clean_text"
        if match:
            try:
                res = db.execute(
                    f"SELECT rowid, file, line, {text} AS clean_text FROM {table} WHERE {table} MATCH ? AND "
                    + contains(text) + f" ORDER BY length({text}) LIMIT 500", (match, *texts)).fetchall()
            except sqlite3.OperationalError:
                res = []
        if not res:
            res = db.execute(
                f"SELECT rowid, file, line, {text} AS clean_text FROM {table} WHERE " + contains(text)
                + f" ORDER BY length({text}) LIMIT 500",
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
    if db_custom is not None:
        rows.extend(query_corpus(db_custom, "custom", "custom"))

    rows.sort(key=lambda r: len(r.get("clean_text") or ""))
    return jsonify({"rows": rows[:500]})

RELOCATE_MAX = 5000


@app.route("/api/relocate", methods=["POST"])
def api_relocate():
    server._require_page()
    sent = (request.get_json(silent=True) or {}).get("items", [])
    # RELOCATE_MAX a request; the page sends more in batches, and an answer that cut says how many (audit 10, F54)
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
    response = send_file(image, conditional=True, max_age=0)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
