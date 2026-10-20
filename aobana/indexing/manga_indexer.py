import functools
import json
import os
import re
import statistics
import sqlite3
import sys
import hashlib
import time
from datetime import datetime

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from sudachipy import tokenizer, dictionary

from aobana import paths
BASE_DIR = paths.BASE_DIR
MANGA_ROOT_DIR = paths.manga_dir()
DB_PATH = paths.manga_db()

_TOKENIZER = None
mode = tokenizer.Tokenizer.SplitMode.A


def get_tokenizer():
    global _TOKENIZER
    if _TOKENIZER is None:
        _TOKENIZER = dictionary.Dictionary(dict="core").create()
    return _TOKENIZER


from aobana.utils import (
    BOOK_RUBY_RE, normalize_manga_text, katakana_to_hiragana, sudachi_pieces,
    norm_relpath, INDEX_FORMAT, is_outdated, ensure_format_column, compact_if_worth, stop_requested,
    write_tokenizer_meta, ruby_index_extras, fold_compat, parallel_map, filtered_names, held_removals, ALLOW_REMOVAL_FLAG,
    name_key, start_output, emit, say,
    ensure_line_lengths, has_line_lengths, write_line_lengths, drop_orphan_lengths, token_lengths_blob, stored_display_length,
    write_token_lengths,
    ensure_ruby_lexicon, has_ruby_lexicon, write_ruby_lexicon, drop_ruby_lexicon, ruby_table,
)

MOKURO_EXT = ".mokuro"
TABLE = "manga"
WORD_RE = re.compile(r'\w')

PAGES_SCHEMA = "CREATE TABLE IF NOT EXISTS manga_pages (rowid INTEGER PRIMARY KEY, page INTEGER NOT NULL)"

_EXCLUDED_LOG = []


def compute_file_hash(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def volume_key(relpath, doc_title):
    parts = re.split(r"[\\/]", relpath)
    stem = parts[-1][:-len(MOKURO_EXT)] if parts[-1].lower().endswith(MOKURO_EXT) else parts[-1]
    if len(parts) == 1:
        series = (doc_title or "").strip() or stem
        volume = stem
    else:
        series = parts[0]
        volume = "｜".join(parts[1:-1] + [stem])
    return series, volume, f"{series}\\{volume}"


VERTICAL_COLON_RE = re.compile(r'(?<![０-９Ａ-Ｚａ-ｚ0-9A-Za-z])：(?![０-９Ａ-Ｚａ-ｚ0-9A-Za-z])')
DUPLICATE_IOU = 0.5
_DUP_NOISE_RE = re.compile(r'[．…ー～―\s]')


def _box(block):
    b = block.get("box") or [0, 0, 0, 0]
    return b if len(b) == 4 else [0, 0, 0, 0]


def _xy_order(idx, boxes):
    if len(idx) <= 1:
        return list(idx)

    def groups(lo, hi):
        s = sorted(idx, key=lambda i: boxes[i][lo])
        out, end = [[s[0]]], boxes[s[0]][hi]
        for i in s[1:]:
            if boxes[i][lo] >= end:
                out.append([i])
            else:
                out[-1].append(i)
            end = max(end, boxes[i][hi])
        return out

    rows = groups(1, 3)
    if len(rows) > 1:
        return [i for row in rows for i in _xy_order(row, boxes)]
    cols = groups(0, 2)
    if len(cols) > 1:
        right = cols[-1]
        return _xy_order(right, boxes) + _xy_order([i for c in cols[:-1] for i in c], boxes)
    return sorted(idx, key=lambda i: (-boxes[i][2], boxes[i][1]))


def reading_order(page):
    blocks = page.get("blocks") or []
    boxes = [_box(b) for b in blocks]
    idx = list(range(len(blocks)))
    w, h = page.get("img_width") or 0, page.get("img_height") or 0
    if w > h:
        mid = w / 2
        right = [i for i in idx if (boxes[i][0] + boxes[i][2]) / 2 >= mid]
        left = [i for i in idx if (boxes[i][0] + boxes[i][2]) / 2 < mid]
        order = _xy_order(right, boxes) + _xy_order(left, boxes)
    else:
        order = _xy_order(idx, boxes)
    return [blocks[i] for i in order]


def _iou(a, b):
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    inter = w * h
    return inter / max(1, (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


SHIPPED_RUBY_TABLES = ("ruby_dict_merge", "ruby_whole", "gloss_ruby", "unclosed_ruby", "ass_pairs", "ruby_kana_base")
_FUSED_KANJI_RE = re.compile(r'[一-龯々]{2,}')
_FUSED_KANA_RE = re.compile(r'[ぁ-ゖ]{2,}')
_KANA_BLOCK_RE = re.compile(r'[ぁ-ゖァ-ヶー]+')
_KANJI_RE = re.compile(r'[一-龯々]')


@functools.lru_cache(maxsize=1)
def shipped_ruby_pairs():
    pairs = {}
    for table in SHIPPED_RUBY_TABLES:
        for _, cols in ruby_table(paths.RUBY_TABLES_PATH, table):
            base, reading = cols[-2:] if table == "unclosed_ruby" else cols[:2]
            if base and reading:
                pairs.setdefault(base, set()).add(katakana_to_hiragana(reading))
    return {base: frozenset(r) for base, r in pairs.items()}


@functools.lru_cache(maxsize=1)
def _fused_forms():
    forms, clash = {}, set()
    for base, readings in shipped_ruby_pairs().items():
        if not _FUSED_KANJI_RE.fullmatch(base):
            continue
        for reading in readings:
            if not _FUSED_KANA_RE.fullmatch(reading):
                continue
            for form in (reading + base, base + reading):
                ruby = f"｜{base}({reading})"
                if forms.get(form, ruby) != ruby:
                    clash.add(form)
                forms[form] = ruby
    index = {}
    for form in sorted(set(forms) - clash, key=lambda f: (-len(f), f)):
        index.setdefault(form[:2], []).append((form, forms[form]))
    return index


def unfuse_ruby(text: str) -> str:
    index = _fused_forms()
    out, last = [], 0
    for m in list(BOOK_RUBY_RE.finditer(text)) + [None]:
        end = m.start() if m else len(text)
        i, start = last, last
        while i < end - 3:
            hit = next((f for f in index.get(text[i:i + 2], ()) if text.startswith(f[0], i) and i + len(f[0]) <= end), None)
            if hit:
                out.append(text[start:i] + hit[1])
                i = start = i + len(hit[0])
            else:
                i += 1
        out.append(text[start:end])
        if m:
            out.append(m[0])
            last = m.end()
    return "".join(out)


def _small_kana_targets(block, blocks, median):
    raw = "".join(block.get("lines") or []).strip()
    f = block.get("font_size") or 0
    if len(raw) < 2 or not _KANA_BLOCK_RE.fullmatch(raw) or not f or f > 0.62 * median:
        return []
    x1, y1, x2, y2 = _box(block)
    found = []
    for j, t in enumerate(blocks):
        tf = t.get("font_size") or 0
        if tf < f * 1.6 or not _KANJI_RE.search("".join(t.get("lines") or [])):
            continue
        a, c, d, e = _box(t)
        if block.get("vertical") and t.get("vertical"):
            overlap, gap = max(0, min(y2, e) - max(y1, c)) / max(1, y2 - y1), x1 - d
        elif not block.get("vertical") and not t.get("vertical"):
            overlap, gap = max(0, min(x2, d) - max(x1, a)) / max(1, x2 - x1), c - y2
        else:
            continue
        if -f <= gap <= tf * 1.2 and overlap >= 0.6:
            found.append(j)
    return found


def attach_ruby(page):
    blocks = page.get("blocks") or []
    raws = ["".join(b.get("lines") or []).strip() for b in blocks]
    fonts = [b.get("font_size") or 0 for b in blocks if b.get("font_size")]
    median = statistics.median(fonts) if fonts else 0
    pairs = None
    for i, block in enumerate(blocks):
        targets = _small_kana_targets(block, blocks, median)
        if not targets:
            continue
        pairs = pairs or shipped_ruby_pairs()
        reading = katakana_to_hiragana(raws[i])
        hits = [(j, base) for j in targets for base, readings in pairs.items()
                if len(base) >= 2 and reading in readings and raws[j].count(base) == 1]
        if len(hits) == 1:
            j, base = hits[0]
            raws[j] = raws[j].replace(base, f"｜{base}({raws[i]})")
            _EXCLUDED_LOG.append(("RUBY_ATTACHED", raws[i]))
            raws[i] = ""
    return {id(b): raw for b, raw in zip(blocks, raws)}


def volume_blocks(doc):
    out = []
    for page_no, page in enumerate(doc.get("pages") or [], 1):
        kept = []
        raws = attach_ruby(page)
        for block in reading_order(page):
            raw = raws[id(block)]
            if block.get("vertical"):
                raw = VERTICAL_COLON_RE.sub("…", raw)
            text = unfuse_ruby(normalize_manga_text(raw))
            text, fused = manga_fused.unfuse(text)
            for rule, kana, kanji, new in fused:
                _EXCLUDED_LOG.append((f"FUSED_{rule}", f"{kana}{kanji} -> {new or 'left as read'}: {text}"))
            if not text:
                continue
            if not WORD_RE.search(text):
                _EXCLUDED_LOG.append(("PUNCTUATION_ONLY", text))
                continue
            box, key = _box(block), _DUP_NOISE_RE.sub("", text)
            twin = next((k for k in kept if k[1] == key and _iou(k[0], box) >= DUPLICATE_IOU), None)
            if twin:
                if len(text) > len(out[twin[2]][1]):
                    _EXCLUDED_LOG.append(("DUPLICATE", out[twin[2]][1]))
                    out[twin[2]] = (page_no, text)
                else:
                    _EXCLUDED_LOG.append(("DUPLICATE", text))
                continue
            kept.append((box, key, len(out)))
            out.append((page_no, text))
    return out


def get_clean_text(line: str) -> str:
    return BOOK_RUBY_RE.sub(r'\1\2', line)


def analyze_with_sudachi(clean_text: str):
    return analyze_tokens(clean_text)[:2]


def analyze_tokens(clean_text: str):
    base_forms, readings = [], []
    words = [w for piece in sudachi_pieces(clean_text) for w in get_tokenizer().tokenize(piece, mode)]
    for word in words:
        base_forms.append(word.normalized_form())
        kana = word.reading_form()
        readings.append(katakana_to_hiragana(kana) if kana else word.surface())
    return " ".join(base_forms), " ".join(readings), token_lengths_blob(w.surface() for w in words)


def volume_rows(blocks, file_key):
    rows = []
    for i, (page, line) in enumerate(blocks):
        if i % 128 == 0:
            control.check_stop()
        clean_text = fold_compat(get_clean_text(line))
        base_forms, readings, lens = analyze_tokens(clean_text)
        base_forms, readings = ruby_index_extras(line, BOOK_RUBY_RE, base_forms, readings)
        rows.append((page, (file_key, line, clean_text, base_forms, readings, lens)))
    return rows


def _prepare(job):
    path, relpath, known_hash = job
    _EXCLUDED_LOG.clear()
    try:
        file_hash = compute_file_hash(path)
        if file_hash == known_hash:
            return ('same', relpath, file_hash, None)
        with open(path, encoding='utf-8-sig') as f:
            doc = json.load(f)
        if not isinstance(doc, dict) or not isinstance(doc.get("pages"), list):
            raise ValueError("not a .mokuro file (no pages)")
        series, volume, file_key = volume_key(relpath, doc.get("title"))
        rows = [(page, r + (stored_display_length(r[1], "manga"), kanji_table.tokens(r[2])))
                for page, r in volume_rows(volume_blocks(doc), file_key)]
    except Exception as e:
        return ('error', relpath, None, f"{type(e).__name__}: {e}")
    excluded = [(file_key, reason, text) for reason, text in _EXCLUDED_LOG]
    return ('rows', relpath, file_hash, (series, volume, len(doc["pages"]), rows, excluded))


COMMIT_EVERY_FILES = 50
COMMIT_EVERY_SECONDS = 20


from aobana.indexing import run_control as control, kanji_table, manga_fused, rebuild as rebuilding
from aobana.indexing.preparation import prepare_changed
from aobana.utils import media_walk

def build_tables(conn, top, db=None):
    if top and not has_line_lengths(conn):
        emit("phase", "LENGTHS building the display-length table (once, reads the whole index)...", phase="lengths")
    ensure_line_lengths(conn, db or DB_PATH, TABLE, "manga", paths.index_workers())
    if stop_requested():
        return
    if top and not has_ruby_lexicon(conn):
        emit("phase", "LEXICON building the ruby lexicon table (once, reads the whole index)...", phase="lexicon")
    ensure_ruby_lexicon(conn, TABLE, "manga", paths.index_workers())
    if stop_requested():
        return
    kanji_table.build(conn, TABLE)


@control.owned(lambda: DB_PATH)
def run_tables():
    say(f"Building the manga index's tables ({DB_PATH})...")
    with control.connection(DB_PATH) as conn:
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (TABLE,)).fetchone() is None:
            say("Tables ready: no manga index yet.")
            return
        build_tables(conn, conn.execute(f"SELECT rowid FROM {TABLE} ORDER BY rowid DESC LIMIT 1").fetchone())
    if stop_requested():
        emit("stopped", "STOPPED")
    else:
        say("Tables ready.")


@control.owned(lambda: DB_PATH)
def run_manga_indexer(force=False, outdated=False, allow_removal=False, rebuild=False):
    say(f"Starting manga indexer on {MANGA_ROOT_DIR} (force={force}, outdated={outdated}, rebuild={rebuild})...")
    roots = paths.index_roots('manga', MANGA_ROOT_DIR, paths.media_roots('manga'))
    if MANGA_ROOT_DIR is None:
        emit("root_not_set", "ROOT_NOT_SET manga", media="manga")
        say("No manga folder is set (Library tab). Nothing was changed.")
        return
    if not paths.media_enabled("manga"):
        say("Manga is off in Settings. Nothing was changed.")
        return
    if any(not os.path.isdir(root) for root in roots):
        missing = next(root for root in roots if not os.path.isdir(root))
        emit("root_missing", f"ROOT_MISSING {missing}", folder=missing)
        say("Manga indexing aborted: the manga folder does not exist. Nothing was changed.")
        return
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    excluded = control.StreamLog(os.path.join(paths.logs_dir(), 'excluded_manga_lines.txt'),
                                 lambda r: f'[{r[0]}] [{r[1]}] {r[2]}')

    db, old_files, failed_keys, result = DB_PATH, {}, [], None
    if rebuild:
        old_files = rebuilding.old_sources(DB_PATH)
        db = rebuilding.path(DB_PATH)
        rebuilding.discard(DB_PATH)
        say(f"REBUILD a new index beside the old one ({len(old_files)} volumes indexed)")
    with control.connection(db) as conn:
        conn.row_factory = sqlite3.Row
        if force:
            say("Force rebuild requested. Dropping existing tables in manga.db...")
            for t in (TABLE, "sources", "manga_pages", "line_lengths", "token_lengths", "ruby_lexicon"):
                conn.execute(f"DROP TABLE IF EXISTS {t}")
            kanji_table.drop(conn, TABLE)
            conn.commit()

        conn.execute('''
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                relpath TEXT UNIQUE NOT NULL,
                file_hash TEXT NOT NULL,
                title TEXT NOT NULL,
                volume TEXT NOT NULL,
                pages INTEGER NOT NULL DEFAULT 0,
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute(f'''
            CREATE VIRTUAL TABLE IF NOT EXISTS {TABLE} USING fts5(
                source_id UNINDEXED,
                file UNINDEXED,
                line UNINDEXED,
                clean_text UNINDEXED,
                base_forms,
                readings,
                tokenize = "unicode61"
            )
        ''')
        conn.execute(PAGES_SCHEMA)
        conn.commit()

        ensure_format_column(conn)
        from aobana.utils import report_outdated
        report_outdated(conn, 'manga')
        conn.commit()
        top = conn.execute(f"SELECT rowid FROM {TABLE} ORDER BY rowid DESC LIMIT 1").fetchone()
        build_tables(conn, top, db)
        lengths = has_line_lengths(conn)
        lexicon = has_ruby_lexicon(conn)
        control.check_stop()
        kanji = kanji_table.ready(conn, TABLE)
        existing_files = {name_key(row['relpath']): {'id': row['id'], 'hash': None if outdated and is_outdated('manga', row['relpath'], row['index_format']) else row['file_hash']}
                          for row in conn.execute("SELECT id, relpath, file_hash, index_format FROM sources")}
        deleted_rows = inserted_rows = 0
        floor = top[0] if top else 0
        next_rowid = floor + 1
        replaced = []

        removed = 0
        swept = [0]
        def flush():
            nonlocal deleted_rows
            control.check_stop()
            if replaced:
                marks = ",".join("?" * len(replaced))
                deleted_rows += conn.execute(f"DELETE FROM {TABLE} WHERE rowid <= ? AND source_id IN ({marks})",
                                             [floor] + replaced).rowcount
                replaced.clear()
            if kanji and deleted_rows != swept[0]:
                kanji_table.drop_orphans(conn, TABLE)
                swept[0] = deleted_rows
            conn.commit()
            control.committed(new_or_updated, skipped, removed)

        mokuro_paths = []
        roots_by_path = {}
        from aobana.utils import media_walk_roots
        for source_root, dirpath, kept, _ in media_walk_roots(roots, "manga"):
            control.check_stop()
            mokuro_paths.extend(os.path.join(dirpath, fname) for fname in kept)
            roots_by_path.update({os.path.join(dirpath, fname): source_root for fname in kept})
        say(f"Found {len(mokuro_paths)} .mokuro file(s) in {MANGA_ROOT_DIR}.")
        emit("total", f"TOTAL {len(mokuro_paths)}", quiet=True, total=len(mokuro_paths))

        filtered = filtered_names(paths.filtered_list(), "manga")
        current_disk_files = set()
        jobs, n_filtered = [], 0
        for path in mokuro_paths:
            relpath = norm_relpath(path, roots_by_path[path])
            key = name_key(relpath)
            if key in filtered:
                n_filtered += 1
                continue
            current_disk_files.add(key)
            jobs.append((path, relpath, existing_files.get(key, {}).get('hash')))
        if n_filtered:
            emit("filtered", f"FILTERED {n_filtered}", count=n_filtered)

        workers = paths.index_workers() if len(jobs) > 1 else 1
        if workers > 1:
            say(f"Workers: {workers}")
        meta_written = False
        new_or_updated = skipped = failed = 0
        pending, last_commit = 0, time.monotonic()
        stopped = False
        control.phase('preparation', total=len(jobs))
        for n, (kind, relpath, file_hash, payload) in enumerate(
                prepare_changed(_prepare, jobs, workers, compute_file_hash, stop=stop_requested), 1):
            if stop_requested():
                stopped = True
                break
            emit("progress", f"PROGRESS {n}/{len(jobs)} {relpath}", quiet=True, done=n, total=len(jobs), file=relpath)
            if kind == 'same':
                skipped += 1
                continue
            old = existing_files.get(name_key(relpath))
            if kind == 'error':
                if old:
                    conn.execute("UPDATE sources SET file_hash = '' WHERE id = ?", (old['id'],))
                failed += 1
                if rebuilding.transient(payload):
                    failed_keys.append(name_key(relpath))
                emit("failed", f"FAILED {relpath}: {payload}", file=relpath, error=str(payload))
                continue
            control.phase('writing', n-1, len(jobs))
            series, volume, n_pages, rows, file_excluded = payload
            rows = list(rows)
            excluded.extend(file_excluded)
            if not meta_written:
                write_tokenizer_meta(conn, 1)
                meta_written = True
            if old:
                source_id = old['id']
                replaced.append(source_id)
                if lexicon:
                    drop_ruby_lexicon(conn, [source_id])
                conn.execute("UPDATE sources SET relpath = ?, file_hash = ?, indexed_at = ?, index_format = ? WHERE id = ?",
                             (relpath, file_hash, datetime.now().isoformat(' '), INDEX_FORMAT['manga'], source_id))
            else:
                source_id = conn.execute(
                    "INSERT INTO sources (relpath, file_hash, title, volume, index_format) VALUES (?, ?, '', '', ?)",
                    (relpath, file_hash, INDEX_FORMAT['manga'])).lastrowid
            conn.execute("UPDATE sources SET title = ?, volume = ?, pages = ? WHERE id = ?",
                         (series, volume, n_pages, source_id))
            new_or_updated += 1
            inserted_rows += conn.executemany(
                f"INSERT INTO {TABLE}(rowid, source_id, file, line, clean_text, base_forms, readings) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(next_rowid + i, source_id) + r[:5] for i, (_, r) in enumerate(rows)]).rowcount
            conn.executemany("INSERT OR REPLACE INTO manga_pages VALUES (?, ?)",
                             [(next_rowid + i, page) for i, (page, _) in enumerate(rows)])
            if lengths:
                write_line_lengths(conn, ((next_rowid + i, r[6]) for i, (_, r) in enumerate(rows)), "manga", computed=True)
            write_token_lengths(conn, ((next_rowid + i, r[5]) for i, (_, r) in enumerate(rows)))
            if kanji:
                kanji_table.write(conn, TABLE, ((next_rowid + i, r[7]) for i, (_, r) in enumerate(rows)), computed=True)
            if lexicon:
                write_ruby_lexicon(conn, "manga", ((source_id, r[0], r[1]) for _, r in rows))
            next_rowid += len(rows)
            say(f"Indexed manga: {series}｜{volume} ({len(rows)} blocks, {n_pages} pages)")
            pending += 1
            if pending >= COMMIT_EVERY_FILES or time.monotonic() - last_commit >= COMMIT_EVERY_SECONDS:
                flush()
                pending, last_commit = 0, time.monotonic()
        control.check_stop()
        flush()

        deleted_files, _ = held_removals(len(existing_files), set(existing_files.keys()) - current_disk_files,
                                         filtered, allow_removal)
        control.phase('removals', total=len(deleted_files))
        removal_pending, removal_time = 0, time.monotonic()
        for relpath in sorted(deleted_files):
            control.check_stop()
            source_id = existing_files[relpath]['id']
            deleted_rows += conn.execute(f"DELETE FROM {TABLE} WHERE source_id = ?", (source_id,)).rowcount
            conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
            if lexicon:
                drop_ruby_lexicon(conn, [source_id])
            removed += 1
            removal_pending += 1
            control.CURRENT.publish(phase='removals', phase_done=removed, phase_total=len(deleted_files))
            if removal_pending >= 200 or time.monotonic() - removal_time >= 20:
                flush()
                removal_pending, removal_time = 0, time.monotonic()
            say(f"Removed {'filtered' if relpath in filtered else 'deleted'} manga: {relpath}")

        if rebuild and not stopped:
            gone, held = held_removals(len(old_files), set(old_files) - current_disk_files, filtered, allow_removal)
            removed = len(gone)
            why = rebuilding.refused(old_files, failed_keys, held)
            result = 'refused' if why else 'rebuilt'
            if why:
                say(f"REBUILD_REFUSED {why}: the old index is kept and updated instead.")

        if deleted_rows:
            conn.execute(f"DELETE FROM manga_pages WHERE rowid NOT IN (SELECT id FROM {TABLE}_docsize)")
            drop_orphan_lengths(conn, TABLE)

        for key, n, rels in conn.execute(
                "SELECT title || '｜' || volume, COUNT(*), group_concat(relpath, ' | ') FROM sources "
                "GROUP BY title, volume HAVING COUNT(*) > 1"):
            say(f"WARNING: {n} files share the volume {key}: {rels}")

        ident = write_tokenizer_meta(conn, 0)
        if new_or_updated:
            say(f"Tokenizer: SudachiDict-core {ident['sudachidict_version']} "
                  f"({ident['dictionary_format']}), SudachiPy {ident['sudachipy_version']}, "
                  f"system.dic {ident['system_dic_sha256'][:12]}")
        flush()
        if stopped:
            emit("stopped", "STOPPED")
        else:
            compact_if_worth(conn, TABLE, deleted_rows, inserted_rows)

    excluded.close()

    if rebuild:
        conn.close()
        if result == 'rebuilt':
            open(rebuilding.done_path(DB_PATH), 'w').close()
        else:
            rebuilding.discard(DB_PATH)
        if result == 'refused':
            return result

    emit("summary", f"Manga indexing complete! Skipped {skipped} unchanged files. Indexed {new_or_updated} new/updated volumes. Removed {removed} deleted."
         + (f" Failed {failed}." if failed else ""),
         unchanged=skipped, indexed=new_or_updated, removed=removed, failed=failed)
    return result


if __name__ == "__main__":
    from aobana.indexing.process_tree import cli_owner
    cli_owner('aobana.indexing.manga_indexer')
    start_output()
    if "--tables" in sys.argv:
        if os.path.exists(DB_PATH):
            run_tables()
        sys.exit(0)
    if rebuilding.FLAG in sys.argv:
        rebuilding.main(run_manga_indexer, DB_PATH, sys.argv, ALLOW_REMOVAL_FLAG in sys.argv)
    else:
        run_manga_indexer(force="--force" in sys.argv, outdated="--outdated" in sys.argv,
                          allow_removal=ALLOW_REMOVAL_FLAG in sys.argv)
