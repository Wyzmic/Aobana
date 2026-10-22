import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime

from sudachipy import dictionary, tokenizer
from aobana import paths, utils
from aobana.indexing import kanji_table, line_repeats, run_control as control, subtitle_input
from aobana.custom_source import Catalog, natural_key
from aobana.indexing.preparation import prepare_changed
from aobana.search.titles import get_sort_key
from aobana.utils import CUSTOM_STR_REPLACEMENTS

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = paths.BASE_DIR
CUSTOM_ROOT_DIR = paths.custom_dir()
DB_PATH = paths.custom_db()
TABLE = 'custom'
_TOKENIZER = None
mode = tokenizer.Tokenizer.SplitMode.A
GLOSS_SEP = chr(0x2029)
KANA_ONLY = re.compile('[ぁ-ゖァ-ヺー・･]+')
COMMIT_EVERY_FILES = 50
COMMIT_EVERY_SECONDS = 20


def get_tokenizer():
    global _TOKENIZER
    if _TOKENIZER is None:
        _TOKENIZER = dictionary.Dictionary(dict='core').create()
    return _TOKENIZER


def compute_file_hash(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def analyze_tokens(clean_text):
    base_forms, readings = [], []
    words = [w for piece in utils.sudachi_pieces(clean_text) for w in get_tokenizer().tokenize(piece, mode)]
    for word in words:
        base_forms.append(word.normalized_form())
        kana = word.reading_form()
        readings.append(utils.katakana_to_hiragana(kana) if kana else word.surface())
    return ' '.join(base_forms), ' '.join(readings), utils.token_lengths_blob(w.surface() for w in words)


def order_key(name):
    return natural_key(name)


def ruby_extra(line, extra, ruby):
    if not ruby:
        return line, extra, ()
    text, marks, readings = utils.custom_ruby(line)
    if not marks:
        return line, extra, ()
    extra = list(extra or (None,) * 3)
    extra[2] = json.dumps(marks, ensure_ascii=False, separators=(',', ':'))
    return text, tuple(extra), readings


def txt_rows(text, file_key, trim, ruby=False):
    rows, gap = [], 0
    for n, line in enumerate(text.splitlines()):
        if n % 128 == 0:
            control.check_stop()
        if trim:
            line = line.strip(' \t　')
        for old, new in CUSTOM_STR_REPLACEMENTS:
            line = line.replace(old, new)
        if not line:
            gap = 1
            continue
        line, extra, readings = ruby_extra(line, None, ruby)
        rows.append(_row(file_key, line, gap, extra, glosses=readings))
        gap = 0
    return rows


def _row(file_key, line, gap, extra, glosses=()):
    if not utils.has_readable(line):
        return (file_key, line, line, '', '', None, None, None, gap, extra, False)
    bases, readings, lengths = analyze_tokens(line)
    for gloss in glosses:
        if KANA_ONLY.fullmatch(gloss):
            # A kana reading is a sound, not a word: Sudachi would read こうせいせい as 構成
            kana = utils.katakana_to_hiragana(gloss)
            more = (kana, kana)
        else:
            more = analyze_tokens(gloss)
        bases, readings = f'{bases} {more[0]}'.strip(), f'{readings} {more[1]}'.strip()
    clean = line + ''.join(GLOSS_SEP + g for g in glosses)
    return (file_key, line, clean, bases, readings, lengths, utils.stored_display_length(line, 'custom'),
            kanji_table.tokens(line), gap, extra, True)


def _md_row(file_key, line, gap, heading, number, ruby):
    line, extra, readings = ruby_extra(line, (heading, number, None), ruby)
    return _row(file_key, line, gap, extra, glosses=readings)


def _prepare(job):
    path, relpath, known_hash, trim = job[:4]
    ruby = job[5] if len(job) > 5 else paths.custom_ruby()
    try:
        file_hash = compute_file_hash(path)
        if file_hash == known_hash:
            return 'same', relpath, file_hash, None
        with open(path, 'rb') as handle:
            raw = handle.read()
        parts = utils.name_key(relpath).split('/')
        title = os.path.splitext(parts[-1])[0]
        category = parts[0] if len(parts) > 1 else title
        text, encoding = subtitle_input.decode_bytes(raw)
        if relpath.lower().endswith('.md'):
            from aobana.custom_source import clean_path, link_target
            from aobana.indexing.custom_markdown import links, parse
            meta = job[4] if len(job) > 4 else None
            if meta is None:
                clean = clean_path(utils.name_key(relpath))
                title = os.path.splitext(clean.split('/')[-1])[0]
                category = clean.split('/')[0] if '/' in clean else title
                stem = os.path.splitext(clean)[0] + '/'
                navigation = {target for _, target, _ in links(text)
                              if (link_target(clean, target) or '').startswith(stem)}
                body, sections = parse(text, title, navigation)
                key = order_key(clean)
            else:
                from aobana.custom_source import page_body
                title, category, key = meta['title'], meta['category'], meta['order_key']
                body, sections = page_body(text, meta)
            rows = [_md_row(relpath, line.strip(' \t　') if trim else line, gap, heading, number, ruby)
                    for line, gap, number, heading in body]
            if not any(row[10] for row in rows):
                return 'skip', relpath, file_hash, 'empty'
            return 'rows', relpath, file_hash, (category, title, key, rows, 'md', sections)
        if not relpath.lower().endswith('.txt'):
            return 'skip', relpath, file_hash, 'unsupported'
        rows = txt_rows(text, relpath, trim, ruby)
        return 'rows', relpath, file_hash, (category, title, order_key(relpath), rows, 'txt', [])
    except Exception as error:
        return 'error', relpath, None, f'{type(error).__name__}: {error}'


def create_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS sources (
        id INTEGER PRIMARY KEY AUTOINCREMENT, relpath TEXT UNIQUE NOT NULL,
        category TEXT NOT NULL, kind TEXT NOT NULL, file_hash TEXT NOT NULL,
        title TEXT NOT NULL, order_key TEXT NOT NULL, lines INTEGER NOT NULL,
        indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, index_format INTEGER NOT NULL
    )''')
    conn.execute('''CREATE VIRTUAL TABLE IF NOT EXISTS custom USING fts5(
        source_id UNINDEXED, file UNINDEXED, line UNINDEXED, clean_text UNINDEXED,
        base_forms, readings, tokenize="unicode61"
    )''')
    # A file's reader page and a line's context read that file's lines only, not every line
    conn.execute('CREATE INDEX IF NOT EXISTS custom_content_source ON custom_content (c0)')
    conn.execute('''CREATE TABLE IF NOT EXISTS custom_lines (
        rowid INTEGER PRIMARY KEY, heading TEXT, section_no INTEGER,
        gap_before INTEGER NOT NULL DEFAULT 0, marks TEXT
    )''')
    columns = {r[1] for r in conn.execute('PRAGMA table_info(sources)')}
    # trimmed: the custom_trim a .txt or .md was read with (NULL: before the column, read trimmed)
    if 'trimmed' not in columns:
        conn.execute('ALTER TABLE sources ADD COLUMN trimmed INTEGER')
    # ruby: the custom_ruby a .txt or .md was read with (NULL: before the column, read without readings)
    if 'ruby' not in columns:
        conn.execute('ALTER TABLE sources ADD COLUMN ruby INTEGER')
    conn.execute('''CREATE TABLE IF NOT EXISTS custom_skipped (
        relpath TEXT PRIMARY KEY, file_hash TEXT NOT NULL, reason TEXT NOT NULL
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS custom_folders (
        path TEXT PRIMARY KEY, parent TEXT, name TEXT NOT NULL, order_key TEXT NOT NULL,
        files INTEGER NOT NULL, lines INTEGER NOT NULL
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS custom_sections (
        source_id INTEGER NOT NULL, section_no INTEGER NOT NULL, heading TEXT,
        PRIMARY KEY (source_id, section_no)
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS custom_quiet (
        rowid INTEGER PRIMARY KEY, source_id INTEGER NOT NULL, file TEXT NOT NULL, line TEXT NOT NULL
    )''')
    conn.execute('CREATE INDEX IF NOT EXISTS custom_quiet_source ON custom_quiet (source_id)')
    conn.execute('CREATE TABLE IF NOT EXISTS custom_source_meta (relpath TEXT PRIMARY KEY, path TEXT NOT NULL, folder_page INTEGER NOT NULL, paired_folder TEXT)')
    if 'paired_folder' not in {r[1] for r in conn.execute('PRAGMA table_info(custom_source_meta)')}:
        conn.execute('ALTER TABLE custom_source_meta ADD COLUMN paired_folder TEXT')


class RowRanges:
    # 613 changed files took 250.8 s that way, 0.33 s a file

    def __init__(self, conn):
        self.conn = conn
        self.ranges = None

    def get(self, source_id):
        if self.ranges is None:
            self.ranges = {s: (lo, hi) for s, lo, hi in self.conn.execute(
                f'SELECT source_id, MIN(rowid), MAX(rowid) FROM {TABLE} GROUP BY source_id')}
        return self.ranges.pop(source_id, None)


def drop_rows(conn, source_id, ranges):
    conn.execute('DELETE FROM custom_quiet WHERE source_id = ?', (source_id,))
    span = ranges.get(source_id)
    if span is None:
        return 0
    return conn.execute(f'DELETE FROM {TABLE} WHERE rowid BETWEEN ? AND ? AND source_id = ?',
                        (*span, source_id)).rowcount


def build_folders(conn):
    folders = {'': [None, '', order_key(''), 0, 0]}
    metadata = dict(conn.execute('SELECT relpath, path FROM custom_source_meta'))
    for relpath, category, key, lines in conn.execute('SELECT relpath, category, order_key, lines FROM sources'):
        parts = metadata.get(relpath, utils.name_key(relpath)).split('/')
        parents = [''] + (['/'.join(parts[:n]) for n in range(1, len(parts))] if len(parts) > 1 else [category])
        for path in parents:
            parent, _, name = path.rpartition('/')
            item = folders.setdefault(path, [parent, name, key, 0, 0])
            item[2] = min(item[2], key) if item[3] else key
            item[3] += 1
            item[4] += lines
    conn.execute('DELETE FROM custom_folders')
    conn.executemany('INSERT INTO custom_folders VALUES (?, ?, ?, ?, ?, ?)',
                     [(path, *item) for path, item in folders.items()])


def build_tables(conn):
    utils.ensure_line_lengths(conn, DB_PATH, TABLE, 'custom', paths.index_workers())
    control.check_stop()
    utils.ensure_ruby_lexicon(conn, TABLE, 'custom', paths.index_workers())
    control.check_stop()
    kanji_table.build(conn, TABLE)
    build_folders(conn)


@control.owned(lambda: DB_PATH)
def run_tables():
    with control.connection(DB_PATH) as conn:
        if conn.execute('SELECT 1 FROM sqlite_master WHERE name = ?', (TABLE,)).fetchone() is None:
            utils.say('Tables ready: no custom index yet.')
            return
        build_tables(conn)
        conn.commit()
        line_repeats.ensure(conn, 'custom', DB_PATH, paths.index_workers(), show=True)
    utils.say('Tables ready.')


@control.owned(lambda: DB_PATH)
def run_custom_indexer(force=False, outdated=False, allow_removal=False):
    utils.say(f'Starting custom indexer on {CUSTOM_ROOT_DIR} (force={force}, outdated={outdated})...')
    roots = paths.index_roots('custom', CUSTOM_ROOT_DIR, paths.media_roots('custom'))
    if CUSTOM_ROOT_DIR is None:
        utils.emit('root_not_set', 'ROOT_NOT_SET custom', media='custom')
        return
    if not paths.media_enabled('custom'):
        utils.say('Custom is off in Settings. Nothing was changed.')
        return
    if any(not os.path.isdir(root) for root in roots):
        missing = next(root for root in roots if not os.path.isdir(root))
        utils.emit('root_missing', f'ROOT_MISSING {missing}', folder=missing)
        return
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    excluded = control.StreamLog(os.path.join(paths.logs_dir(), 'excluded_custom_lines.txt'),
                                 lambda row: f'[{row[0]}] {row[1]}')
    with control.connection(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        if force:
            for table in (TABLE, 'sources', 'custom_lines', 'custom_folders', 'custom_skipped', 'custom_sections', 'custom_quiet', 'custom_source_meta', 'line_lengths', 'token_lengths', 'ruby_lexicon'):
                conn.execute(f'DROP TABLE IF EXISTS {table}')
            kanji_table.drop(conn, TABLE)
            line_repeats.drop(conn, 'custom')
            conn.commit()
        create_schema(conn)
        utils.report_outdated(conn, 'custom')
        conn.commit()
        build_tables(conn)
        existing = {utils.name_key(row['relpath']): dict(row) for row in conn.execute('SELECT * FROM sources')}
        skipped_before = {utils.name_key(r['relpath']): dict(r) for r in conn.execute('SELECT * FROM custom_skipped')}
        filtered = utils.filtered_names(paths.filtered_list(), 'custom')
        jobs, current, other_count, n_filtered = [], set(), 0, 0
        trim, ruby = paths.custom_trim(), paths.custom_ruby()
        for source_root, folder, kept, other in utils.media_walk_roots(roots, 'custom'):
            control.check_stop()
            other_count += other
            for name in kept:
                path = os.path.join(folder, name)
                relpath = utils.norm_relpath(path, source_root)
                key = utils.name_key(relpath)
                if key in filtered:
                    n_filtered += 1
                    continue
                current.add(key)
                old = existing.get(key)
                known = old['file_hash'] if old else (skipped_before[key]['file_hash'] if key in skipped_before else None)
                if outdated and old and (utils.is_outdated('custom', relpath, old['index_format'])
                                         or utils.trim_outdated(old['kind'], old['trimmed'], trim)
                                         or utils.ruby_outdated(old['kind'], old['ruby'], ruby)):
                    known = None
                if old and old['kind'] not in ('txt', 'md'):
                    known = None
                jobs.append((path, relpath, known, trim))
        jobs.sort(key=lambda job: order_key(job[1]))
        catalog = Catalog((job[0], job[1]) for job in jobs)
        jobs = [(*job, catalog.get(job[1]), ruby) for job in jobs]
        conn.execute('DELETE FROM custom_source_meta')
        conn.executemany('INSERT INTO custom_source_meta VALUES (?, ?, ?, ?)',
                         [(job[1], meta['path'], meta['folder_page'], meta['paired_folder']) for job in jobs
                          if (meta := catalog.get(job[1])) is not None])
        # By id: a WHERE on replace(relpath, ...) read every source once a page (16,000 files: 19 s)
        ids = {}
        for source_id, relpath in conn.execute('SELECT id, relpath FROM sources'):
            ids.setdefault(utils.name_key(relpath), []).append(source_id)
        conn.executemany('UPDATE sources SET category = ?, title = ?, order_key = ? WHERE id = ?',
                         [(meta['category'], meta['title'], meta['order_key'], source_id)
                          for relpath, meta in catalog.meta.items() for source_id in ids.get(relpath, ())])
        n_txt = sum(job[1].lower().endswith('.txt') for job in jobs)
        n_md = len(catalog.meta)
        utils.say(f'Found {n_txt} .txt and {n_md} .md file(s) in {CUSTOM_ROOT_DIR}.')
        utils.say(f'other files: {other_count}')
        reasons = {}
        conn.executemany('DELETE FROM custom_skipped WHERE relpath = ?',
                         [(r['relpath'],) for k, r in skipped_before.items() if k not in current])
        utils.emit('total', f'TOTAL {len(jobs)}', quiet=True, total=len(jobs))
        if n_filtered:
            utils.emit('filtered', f'FILTERED {n_filtered}', count=n_filtered)
        top = conn.execute('SELECT MAX(COALESCE((SELECT rowid FROM custom ORDER BY rowid DESC LIMIT 1), 0), '
                           'COALESCE((SELECT MAX(rowid) FROM custom_quiet), 0))').fetchone()
        next_rowid = top[0] + 1
        ranges = RowRanges(conn)
        indexed = skipped = failed = removed = deleted_rows = inserted_rows = pending = 0
        last_commit = time.monotonic()
        meta_written = False

        def flush():
            control.check_stop()
            conn.execute('DELETE FROM custom_lines WHERE rowid NOT IN (SELECT id FROM custom_docsize) '
                         'AND rowid NOT IN (SELECT rowid FROM custom_quiet)')
            utils.drop_orphan_lengths(conn, TABLE)
            kanji_table.drop_orphans(conn, TABLE)
            build_folders(conn)
            conn.commit()
            control.committed(indexed, skipped, removed)

        workers = paths.index_workers() if len(jobs) > 1 else 1
        control.phase('preparation', total=len(jobs))
        for n, (kind, relpath, file_hash, payload) in enumerate(
                prepare_changed(_prepare, jobs, workers, compute_file_hash, stop=utils.stop_requested), 1):
            control.check_stop()
            utils.emit('progress', f'PROGRESS {n}/{len(jobs)} {relpath}', quiet=True, done=n, total=len(jobs), file=relpath)
            nkey = utils.name_key(relpath)
            old = existing.get(nkey)
            if kind == 'same':
                if old is None and nkey in skipped_before:
                    reasons[skipped_before[nkey]['reason']] = reasons.get(skipped_before[nkey]['reason'], 0) + 1
                else:
                    skipped += 1
                continue
            if kind == 'skip':
                reasons[payload] = reasons.get(payload, 0) + 1
                conn.execute('INSERT OR REPLACE INTO custom_skipped (relpath, file_hash, reason) VALUES (?, ?, ?)',
                             (relpath, file_hash, payload))
                if old:
                    deleted_rows += drop_rows(conn, old['id'], ranges)
                    utils.drop_ruby_lexicon(conn, [old['id']])
                    conn.execute('DELETE FROM sources WHERE id = ?', (old['id'],))
                    removed += 1
                    pending += 1
                continue
            if nkey in skipped_before:
                conn.execute('DELETE FROM custom_skipped WHERE relpath = ?', (skipped_before[nkey]['relpath'],))
            if kind == 'error':
                if old:
                    conn.execute('UPDATE sources SET file_hash = ? WHERE id = ?', ('', old['id']))
                excluded.extend([(relpath, payload)])
                utils.emit('failed', f'FAILED {relpath}: {payload}', file=relpath, error=str(payload))
                failed += 1
                continue
            control.phase('writing', n-1, len(jobs))
            category, title, key, rows, source_kind, sections = payload
            rows = list(rows)
            if not meta_written:
                utils.write_tokenizer_meta(conn, 1)
                meta_written = True
            readable = sum(1 for r in rows if r[10])
            trimmed = int(trim) if source_kind in ('txt', 'md') else None
            read_ruby = int(ruby) if source_kind in ('txt', 'md') else None
            if old:
                source_id = old['id']
                deleted_rows += drop_rows(conn, source_id, ranges)
                utils.drop_ruby_lexicon(conn, [source_id])
                conn.execute('UPDATE sources SET relpath = ?, category = ?, kind = ?, file_hash = ?, title = ?, order_key = ?, lines = ?, indexed_at = ?, index_format = ?, trimmed = ?, ruby = ? WHERE id = ?',
                             (relpath, category, source_kind, file_hash, title, key, readable, datetime.now().isoformat(' '), utils.INDEX_FORMAT['custom'], trimmed, read_ruby, source_id))
            else:
                source_id = conn.execute('INSERT INTO sources (relpath, category, kind, file_hash, title, order_key, lines, index_format, trimmed, ruby) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                                         (relpath, category, source_kind, file_hash, title, key, readable, utils.INDEX_FORMAT['custom'], trimmed, read_ruby)).lastrowid
            inserted_rows += conn.executemany('INSERT INTO custom (rowid, source_id, file, line, clean_text, base_forms, readings) VALUES (?, ?, ?, ?, ?, ?, ?)',
                                              [(next_rowid + i, source_id, *r[:5]) for i, r in enumerate(rows) if r[10]]).rowcount
            conn.executemany('INSERT INTO custom_quiet (rowid, source_id, file, line) VALUES (?, ?, ?, ?)',
                             [(next_rowid + i, source_id, r[0], r[1]) for i, r in enumerate(rows) if not r[10]])
            conn.execute('DELETE FROM custom_sections WHERE source_id = ?', (source_id,))
            conn.executemany('INSERT INTO custom_sections (source_id, section_no, heading) VALUES (?, ?, ?)',
                             [(source_id, s[0], s[1]) for s in sections])
            conn.executemany('INSERT INTO custom_lines (rowid, gap_before, heading, section_no, marks) VALUES (?, ?, ?, ?, ?)',
                             [(next_rowid + i, r[8], *(tuple(r[9] or ()) + (None,) * 3)[:3]) for i, r in enumerate(rows)])
            utils.write_line_lengths(conn, ((next_rowid + i, r[6]) for i, r in enumerate(rows) if r[10]), 'custom', computed=True)
            utils.write_token_lengths(conn, ((next_rowid + i, r[5]) for i, r in enumerate(rows) if r[10]))
            kanji_table.write(conn, TABLE, ((next_rowid + i, r[7]) for i, r in enumerate(rows) if r[10]), computed=True)
            next_rowid += len(rows)
            indexed += 1
            pending += 1
            utils.say(f'Indexed custom: {relpath} ({len(rows)} lines)')
            if pending >= COMMIT_EVERY_FILES or time.monotonic() - last_commit >= COMMIT_EVERY_SECONDS:
                flush()
                pending, last_commit = 0, time.monotonic()
        gone, held = utils.held_removals(len(existing), set(existing) - current, filtered, allow_removal)
        control.phase('removals', total=len(gone))
        for key in sorted(gone):
            control.check_stop()
            source_id = existing[key]['id']
            deleted_rows += drop_rows(conn, source_id, ranges)
            utils.drop_ruby_lexicon(conn, [source_id])
            conn.execute('DELETE FROM sources WHERE id = ?', (source_id,))
            removed += 1
            pending += 1
            utils.say(f'Removed custom: {existing[key]["relpath"]}')
            if pending >= 200 or time.monotonic() - last_commit >= COMMIT_EVERY_SECONDS:
                flush()
                pending, last_commit = 0, time.monotonic()
        flush()
        conn.execute('DELETE FROM custom_sections WHERE source_id NOT IN (SELECT id FROM sources)')
        conn.execute('DELETE FROM custom_lines WHERE rowid NOT IN (SELECT rowid FROM custom) '
                     'AND rowid NOT IN (SELECT rowid FROM custom_quiet)')
        conn.commit()
        line_repeats.ensure(conn, 'custom', DB_PATH, paths.index_workers())
        utils.compact_if_worth(conn, TABLE, deleted_rows, inserted_rows)
    excluded.close()
    if reasons.get('empty'):
        utils.say(f'Markdown files with no readable lines: {reasons["empty"]}')
    utils.emit('summary', f'Custom indexing complete! Skipped {skipped} unchanged files. Indexed {indexed} new/updated files. Removed {removed} deleted.'
               + (f' Failed {failed}.' if failed else ''), unchanged=skipped, indexed=indexed, removed=removed, failed=failed)


if __name__ == '__main__':
    from aobana.indexing.process_tree import cli_owner
    cli_owner('aobana.indexing.custom_indexer')
    utils.start_output()
    if '--tables' in sys.argv:
        if os.path.exists(DB_PATH):
            run_tables()
    else:
        run_custom_indexer(force='--force' in sys.argv, outdated='--outdated' in sys.argv,
                           allow_removal=utils.ALLOW_REMOVAL_FLAG in sys.argv)
