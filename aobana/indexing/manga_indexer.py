import json
import os
import re
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
    write_tokenizer_meta, ruby_index_extras, parallel_map, filtered_names, held_removals, ALLOW_REMOVAL_FLAG,
    start_output, emit, say,
    ensure_line_lengths, has_line_lengths, write_line_lengths, drop_orphan_lengths,
    ensure_ruby_lexicon, has_ruby_lexicon, write_ruby_lexicon, drop_ruby_lexicon,
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


def volume_blocks(doc):
    out = []
    for page_no, page in enumerate(doc.get("pages") or [], 1):
        kept = []
        for block in reading_order(page):
            raw = "".join(block.get("lines") or []).strip()
            if block.get("vertical"):
                raw = VERTICAL_COLON_RE.sub("…", raw)
            text = normalize_manga_text(raw)
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
    base_forms, readings = [], []
    words = [w for piece in sudachi_pieces(clean_text) for w in get_tokenizer().tokenize(piece, mode)]
    for word in words:
        base_forms.append(word.normalized_form())
        kana = word.reading_form()
        readings.append(katakana_to_hiragana(kana) if kana else word.surface())
    return " ".join(base_forms), " ".join(readings)


def volume_rows(blocks, file_key):
    rows = []
    for page, line in blocks:
        clean_text = get_clean_text(line)
        base_forms, readings = analyze_with_sudachi(clean_text)
        base_forms, readings = ruby_index_extras(line, BOOK_RUBY_RE, base_forms, readings)
        rows.append((page, (file_key, line, clean_text, base_forms, readings)))
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
        rows = volume_rows(volume_blocks(doc), file_key)
    except Exception as e:
        return ('error', relpath, None, f"{type(e).__name__}: {e}")
    excluded = [(file_key, reason, text) for reason, text in _EXCLUDED_LOG]
    return ('rows', relpath, file_hash, (series, volume, len(doc["pages"]), rows, excluded))


COMMIT_EVERY_FILES = 50
COMMIT_EVERY_SECONDS = 20


def build_tables(conn, top):
    if top and not has_line_lengths(conn):
        emit("phase", "LENGTHS building the display-length table (once, reads the whole index)...", phase="lengths")
    ensure_line_lengths(conn, DB_PATH, TABLE, "manga", paths.index_workers())
    if stop_requested():
        return
    if top and not has_ruby_lexicon(conn):
        emit("phase", "LEXICON building the ruby lexicon table (once, reads the whole index)...", phase="lexicon")
    ensure_ruby_lexicon(conn, TABLE, "manga", paths.index_workers())


def run_tables():
    say(f"Building the manga index's tables ({DB_PATH})...")
    with sqlite3.connect(DB_PATH) as conn:
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (TABLE,)).fetchone() is None:
            say("Tables ready: no manga index yet.")
            return
        build_tables(conn, conn.execute(f"SELECT rowid FROM {TABLE} ORDER BY rowid DESC LIMIT 1").fetchone())
    if stop_requested():
        emit("stopped", "STOPPED")
    else:
        say("Tables ready.")


def run_manga_indexer(force=False, outdated=False, allow_removal=False):
    say(f"Starting manga indexer on {MANGA_ROOT_DIR} (force={force}, outdated={outdated})...")
    if MANGA_ROOT_DIR is None:
        emit("root_not_set", "ROOT_NOT_SET manga", media="manga")
        say("No manga folder is set (Library tab). Nothing was changed.")
        return
    if not paths.media_enabled("manga"):
        say("Manga is off in Settings. Nothing was changed.")
        return
    if not os.path.isdir(MANGA_ROOT_DIR):
        emit("root_missing", f"ROOT_MISSING {MANGA_ROOT_DIR}", folder=MANGA_ROOT_DIR)
        say("Manga indexing aborted: the manga folder does not exist. Nothing was changed.")
        return
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    excluded = []

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        if force:
            say("Force rebuild requested. Dropping existing tables in manga.db...")
            for t in (TABLE, "sources", "manga_pages", "line_lengths", "ruby_lexicon"):
                conn.execute(f"DROP TABLE IF EXISTS {t}")
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
        conn.commit()
        top = conn.execute(f"SELECT rowid FROM {TABLE} ORDER BY rowid DESC LIMIT 1").fetchone()
        build_tables(conn, top)
        lengths = has_line_lengths(conn)
        lexicon = has_ruby_lexicon(conn)
        existing_files = {row['relpath']: {'id': row['id'], 'hash': None if outdated and is_outdated('manga', row['relpath'], row['index_format']) else row['file_hash']}
                          for row in conn.execute("SELECT id, relpath, file_hash, index_format FROM sources")}
        deleted_rows = inserted_rows = 0
        if outdated:
            n_old = sum(1 for v in existing_files.values() if v['hash'] is None)
            if n_old:
                say(f"OUTDATED {n_old}")
        floor = top[0] if top else 0
        next_rowid = floor + 1
        replaced = []

        def flush():
            nonlocal deleted_rows
            if replaced:
                marks = ",".join("?" * len(replaced))
                deleted_rows += conn.execute(f"DELETE FROM {TABLE} WHERE rowid <= ? AND source_id IN ({marks})",
                                             [floor] + replaced).rowcount
                replaced.clear()
            conn.commit()

        mokuro_paths = []
        for dirpath, dirnames, filenames in os.walk(MANGA_ROOT_DIR):
            dirnames[:] = [d for d in dirnames if not d.startswith('.')]
            for fname in filenames:
                if fname.lower().endswith(MOKURO_EXT) and not fname.startswith('.'):
                    mokuro_paths.append(os.path.join(dirpath, fname))
        say(f"Found {len(mokuro_paths)} .mokuro file(s) in {MANGA_ROOT_DIR}.")
        emit("total", f"TOTAL {len(mokuro_paths)}", quiet=True, total=len(mokuro_paths))

        filtered = filtered_names(paths.filtered_list(), "manga")
        current_disk_files = set()
        jobs, n_filtered = [], 0
        for path in mokuro_paths:
            relpath = norm_relpath(path, MANGA_ROOT_DIR)
            if relpath in filtered:
                n_filtered += 1
                continue
            current_disk_files.add(relpath)
            jobs.append((path, relpath, existing_files.get(relpath, {}).get('hash')))
        if n_filtered:
            emit("filtered", f"FILTERED {n_filtered}", count=n_filtered)

        workers = paths.index_workers() if len(jobs) > 1 else 1
        if workers > 1:
            say(f"Workers: {workers}")
        meta_written = False
        new_or_updated = skipped = failed = 0
        pending, last_commit = 0, time.monotonic()
        stopped = False
        for n, (kind, relpath, file_hash, payload) in enumerate(parallel_map(_prepare, jobs, workers), 1):
            if stop_requested():
                stopped = True
                break
            emit("progress", f"PROGRESS {n}/{len(jobs)} {relpath}", quiet=True, done=n, total=len(jobs), file=relpath)
            if kind == 'same':
                skipped += 1
                continue
            old = existing_files.get(relpath)
            if kind == 'error':
                if old:
                    conn.execute("UPDATE sources SET file_hash = '' WHERE id = ?", (old['id'],))
                failed += 1
                emit("failed", f"FAILED {relpath}: {payload}", file=relpath, error=str(payload))
                continue
            series, volume, n_pages, rows, file_excluded = payload
            excluded.extend(file_excluded)
            if not meta_written:
                write_tokenizer_meta(conn, 1)
                meta_written = True
            if old:
                source_id = old['id']
                replaced.append(source_id)
                if lexicon:
                    drop_ruby_lexicon(conn, [source_id])
                conn.execute("UPDATE sources SET file_hash = ?, indexed_at = ?, index_format = ? WHERE id = ?",
                             (file_hash, datetime.now(), INDEX_FORMAT['manga'], source_id))
            else:
                source_id = conn.execute(
                    "INSERT INTO sources (relpath, file_hash, title, volume, index_format) VALUES (?, ?, '', '', ?)",
                    (relpath, file_hash, INDEX_FORMAT['manga'])).lastrowid
            conn.execute("UPDATE sources SET title = ?, volume = ?, pages = ? WHERE id = ?",
                         (series, volume, n_pages, source_id))
            new_or_updated += 1
            inserted_rows += conn.executemany(
                f"INSERT INTO {TABLE}(rowid, source_id, file, line, clean_text, base_forms, readings) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(next_rowid + i, source_id) + r for i, (_, r) in enumerate(rows)]).rowcount
            conn.executemany("INSERT OR REPLACE INTO manga_pages VALUES (?, ?)",
                             [(next_rowid + i, page) for i, (page, _) in enumerate(rows)])
            if lengths:
                write_line_lengths(conn, ((next_rowid + i, r[1]) for i, (_, r) in enumerate(rows)), "manga")
            if lexicon:
                write_ruby_lexicon(conn, "manga", ((source_id, r[0], r[1]) for _, r in rows))
            next_rowid += len(rows)
            say(f"Indexed manga: {series}｜{volume} ({len(rows)} blocks, {n_pages} pages)")
            pending += 1
            if pending >= COMMIT_EVERY_FILES or time.monotonic() - last_commit >= COMMIT_EVERY_SECONDS:
                flush()
                pending, last_commit = 0, time.monotonic()
        flush()

        deleted_files, _ = held_removals(len(existing_files), set(existing_files.keys()) - current_disk_files,
                                         filtered, allow_removal)
        for relpath in deleted_files:
            source_id = existing_files[relpath]['id']
            deleted_rows += conn.execute(f"DELETE FROM {TABLE} WHERE source_id = ?", (source_id,)).rowcount
            conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
            if lexicon:
                drop_ruby_lexicon(conn, [source_id])
            say(f"Removed {'filtered' if relpath in filtered else 'deleted'} manga: {relpath}")

        if deleted_rows:
            conn.execute(f"DELETE FROM manga_pages WHERE rowid NOT IN (SELECT id FROM {TABLE}_docsize)")
            if lengths:
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
        conn.commit()
        if stopped:
            emit("stopped", "STOPPED")
        else:
            compact_if_worth(conn, TABLE, deleted_rows, inserted_rows)

    if excluded:
        log_path = os.path.join(paths.logs_dir(), "excluded_manga_lines.txt")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "w", encoding="utf-8") as log_f:
            for key, reason, text in excluded:
                log_f.write(f"[{key}] [{reason}] {text}\n")

    emit("summary", f"Manga indexing complete! Skipped {skipped} unchanged files. Indexed {new_or_updated} new/updated volumes. Removed {len(deleted_files)} deleted."
         + (f" Failed {failed}." if failed else ""),
         unchanged=skipped, indexed=new_or_updated, removed=len(deleted_files), failed=failed)


if __name__ == "__main__":
    start_output()
    if "--tables" in sys.argv:
        if os.path.exists(DB_PATH):
            run_tables()
        sys.exit(0)
    run_manga_indexer(force="--force" in sys.argv, outdated="--outdated" in sys.argv,
                      allow_removal=ALLOW_REMOVAL_FLAG in sys.argv)
