import sqlite3
import time

VERSION = '1'
SCHEMA = ('(source_id INTEGER NOT NULL, first_rowid INTEGER NOT NULL, '
          'last_rowid INTEGER NOT NULL, lines INTEGER NOT NULL, '
          'PRIMARY KEY(source_id, first_rowid)) WITHOUT ROWID')

def ready(conn):
    try:
        return (conn.execute("SELECT v FROM meta WHERE k='source_ranges_version'").fetchone()[0]
                == VERSION and conn.execute("SELECT 1 FROM sqlite_master WHERE name='source_ranges'").fetchone() is not None)
    except (sqlite3.Error, TypeError):
        return False

_TRIGGERS = tuple(f'_ranges_{table}_{action}' for table in ('sources', 'subtitles_content')
                  for action in ('INSERT', 'UPDATE', 'DELETE'))


def _drop_input(conn):
    for name in _TRIGGERS:
        conn.execute(f'DROP TRIGGER IF EXISTS {name}')
    conn.execute('DROP TABLE IF EXISTS _source_range_input')


def leftovers(conn) -> int:
    names = (*_TRIGGERS, '_source_range_input')
    return conn.execute(f"SELECT count(*) FROM sqlite_master WHERE name IN ({','.join('?' * len(names))})",
                        names).fetchone()[0]


def ensure(conn, stop=lambda: False, progress=lambda **kw: None, chunk=100_000):
    if ready(conn):
        if leftovers(conn):
            _drop_input(conn)
            conn.commit()
        return True
    conn.execute('CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY,v TEXT NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS _source_range_input(generation INTEGER NOT NULL)')
    if not conn.execute('SELECT 1 FROM _source_range_input').fetchone():
        conn.execute('INSERT INTO _source_range_input VALUES(0)')
    for table in ('sources', 'subtitles_content'):
        for action in ('INSERT', 'UPDATE', 'DELETE'):
            conn.execute(f'CREATE TRIGGER IF NOT EXISTS _ranges_{table}_{action} AFTER {action} ON {table} '
                         'BEGIN UPDATE _source_range_input SET generation=generation+1; END')
    conn.execute('CREATE TABLE IF NOT EXISTS _source_range_checkpoint '
                 '(epoch INTEGER, cursor INTEGER, scanned INTEGER, sid INTEGER, first INTEGER, last INTEGER, lines INTEGER)')
    epoch = conn.execute('SELECT generation FROM _source_range_input').fetchone()[0]
    saved = conn.execute('SELECT * FROM _source_range_checkpoint').fetchone()
    if saved is None or saved[0] != epoch:
        conn.execute('DROP TABLE IF EXISTS _source_ranges_stage')
        conn.execute('CREATE TABLE _source_ranges_stage ' + SCHEMA)
        conn.execute('DELETE FROM _source_range_checkpoint')
        conn.execute('INSERT INTO _source_range_checkpoint VALUES(?,0,0,NULL,0,0,0)', (epoch,))
        saved = (epoch, 0, 0, None, 0, 0, 0)
    conn.commit()
    _, cursor, scanned, sid, first, last, lines = saved
    top = conn.execute('SELECT rowid FROM subtitles ORDER BY rowid DESC LIMIT 1').fetchone()
    total = top[0] if top else 0
    started = time.monotonic()
    while not stop():
        batch = conn.execute('SELECT rowid,source_id FROM subtitles WHERE rowid>? ORDER BY rowid LIMIT ?',
                             (cursor, chunk)).fetchall()
        if not batch:
            if sid is not None:
                conn.execute('INSERT INTO _source_ranges_stage VALUES(?,?,?,?)', (sid, first, last, lines))
            conn.execute('DROP TABLE IF EXISTS source_ranges')
            conn.execute('ALTER TABLE _source_ranges_stage RENAME TO source_ranges')
            conn.execute("INSERT OR REPLACE INTO meta VALUES('source_ranges_version',?)", (VERSION,))
            conn.execute('DROP TABLE _source_range_checkpoint')
            _drop_input(conn)
            conn.commit()
            progress(phase='migration', phase_done=total, phase_total=total, elapsed=time.monotonic()-started)
            return True
        for rowid, source in batch:
            if source != sid or rowid != last + 1:
                if sid is not None:
                    conn.execute('INSERT INTO _source_ranges_stage VALUES(?,?,?,?)', (sid, first, last, lines))
                sid, first, lines = source, rowid, 0
            last, lines = rowid, lines + 1
        cursor = batch[-1][0]
        scanned += len(batch)
        conn.execute('UPDATE _source_range_checkpoint SET cursor=?,scanned=?,sid=?,first=?,last=?,lines=?',
                     (cursor, scanned, sid, first, last, lines))
        conn.commit()
        progress(phase='migration', phase_done=cursor, phase_total=total, elapsed=time.monotonic()-started)
    return False

def spans(conn, source_id):
    return conn.execute('SELECT first_rowid,last_rowid,lines FROM source_ranges WHERE source_id=? '
                        'ORDER BY first_rowid', (source_id,)).fetchall()

def delete(conn, source_id):
    removed = 0
    lengths = conn.execute("SELECT 1 FROM sqlite_master WHERE name='line_lengths'").fetchone()
    tokens = conn.execute("SELECT 1 FROM sqlite_master WHERE name='token_lengths'").fetchone()
    kanji = conn.execute("SELECT 1 FROM sqlite_master WHERE name='subtitles_kanji'").fetchone()
    for first, last, count in spans(conn, source_id):
        conn.execute('DELETE FROM subtitles WHERE rowid BETWEEN ? AND ? AND source_id=?',
                     (first, last, source_id))
        if lengths:
            conn.execute('DELETE FROM line_lengths WHERE rowid BETWEEN ? AND ?', (first, last))
        if tokens:
            conn.execute('DELETE FROM token_lengths WHERE rowid BETWEEN ? AND ?', (first, last))
        if kanji:
            conn.execute('DELETE FROM subtitles_kanji WHERE rowid BETWEEN ? AND ?', (first, last))
        removed += count
    conn.execute('DELETE FROM source_ranges WHERE source_id=?', (source_id,))
    return removed

def record(conn, source_id, first, count):
    if count:
        conn.execute('INSERT INTO source_ranges VALUES(?,?,?,?)', (source_id, first, first+count-1, count))

def counts(conn):
    return conn.execute('SELECT s.id,s.relpath,COALESCE(r.lines,0) FROM sources s LEFT JOIN '
                        '(SELECT source_id,SUM(lines) lines FROM source_ranges GROUP BY source_id) r ON r.source_id=s.id')
