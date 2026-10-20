import csv
import hashlib
import html
import io
import json
import os
import re
import threading
import time

from aobana import paths
from aobana.search import iplusone

MAX_BYTES = 8 * 1024 * 1024
MAX_ROWS = 200_000
MAX_ENTRY = 2_000
ENVELOPE = 'aobana-known-words'
ENVELOPE_VERSION = 1
FORMATS = ('text', 'tsv', 'csv', 'jiten', 'migaku', 'reibun')
JITEN_STATES = ('MASTERED', 'MATURE', 'YOUNG', 'BLACKLISTED')
_LOCK = threading.RLock()
_EXPRESSION_NAMES = ('front', 'expression', 'word', 'vocab', 'vocabulary', 'term', 'kanji', '単語', '語彙',
                     '表記', 'dictform')
_READING_NAMES = ('reading', 'kana', 'hiragana', 'furigana', 'expressionreading', 'main_reading', '読み')


class KnownWordsError(ValueError):

    def __init__(self, code, **detail):
        super().__init__(code)
        self.code = code
        self.detail = detail


_RUBY = re.compile(r'<ruby>(.*?)</ruby>', re.I | re.S)
_RT = re.compile(r'<rt>(.*?)</rt>', re.I | re.S)
_RP = re.compile(r'<rp>.*?</rp>', re.I | re.S)
_TAG = re.compile(r'<[^>]+>')
_SOUND = re.compile(r'\[sound:[^\]]*\]', re.I)
_ANKI_FURIGANA = re.compile(r' ?([^\s\[\]]+)\[([^\]]*)\]')
_INVISIBLE = re.compile('[​‌‍⁠﻿­]')


def clean_field(value):
    value = _SOUND.sub('', _RP.sub('', value or ''))
    reading = ''
    rubies = _RUBY.findall(value)
    if rubies:
        reading = ''.join((_RT.findall(r) or [_TAG.sub('', r)])[0] for r in rubies)
        value = _RUBY.sub(lambda m: _RT.sub('', m.group(1)), value)
    furigana = _ANKI_FURIGANA.findall(value)
    if furigana and not reading:
        reading = ''.join(r for _, r in furigana)
        value = _ANKI_FURIGANA.sub(lambda m: m.group(1), value)
    value = re.sub(r'<br\s*/?>|</(?:div|p)>', ' ', value, flags=re.I)
    value = html.unescape(_TAG.sub('', value))
    expression = ' '.join(_INVISIBLE.sub('', value).split())
    reading = ' '.join(html.unescape(_TAG.sub('', reading)).split())
    return expression, reading


def _decode(data):
    if len(data) > MAX_BYTES:
        raise KnownWordsError('too_large', limit_mb=MAX_BYTES // 2 ** 20)
    for enc in ('utf-8-sig', 'utf-16'):
        try:
            text = data.decode(enc)
            if enc == 'utf-16' and not data.startswith((b'\xff\xfe', b'\xfe\xff')):
                raise UnicodeDecodeError(enc, data, 0, 1, 'no BOM')
            return text
        except UnicodeDecodeError:
            continue
    raise KnownWordsError('not_utf8')


def detect(text, filename=''):
    name = (filename or '').lower()
    head = text.lstrip()[:4096]
    if head.startswith('{') and ENVELOPE in head:
        return 'reibun'
    if re.search(r'^=== [A-Z]+ ===$', head, re.M):
        return 'jiten'
    if head.startswith('dictForm,secondary,hasCard'):
        return 'migaku'
    lines = [ln for ln in head.splitlines() if ln.strip() and not ln.startswith('#')]
    if name.endswith('.tsv') or any('\t' in ln for ln in lines[:20]) or '#separator:tab' in head.lower():
        return 'tsv'
    if name.endswith('.csv'):
        return 'csv'
    return 'text'


def _table(text, fmt):
    names = None
    delimiter = '\t' if fmt == 'tsv' else ','
    body = []
    for ln in text.splitlines():
        low = ln.lower()
        if ln.startswith('#'):
            if low.startswith('#separator:'):
                sep = low.split(':', 1)[1].strip()
                delimiter = {'tab': '\t', 'comma': ',', 'semicolon': ';', 'pipe': '|', 'space': ' '}.get(sep, delimiter)
            elif low.startswith('#columns:'):
                names = ln.split(':', 1)[1].split(delimiter)
            continue
        body.append(ln)
    rows = [r for r in csv.reader(io.StringIO('\n'.join(body), newline=''), delimiter=delimiter) if any(c.strip() for c in r)]
    return rows, names


def _pick(names, wanted):
    for i, n in enumerate(names or ()):
        if n.strip().lower() in wanted:
            return i
    return None


_KANA = re.compile(r'[ぁ-ゖァ-ヺー・ ]+')


def _kana_column(rows, word):
    width = max((len(r) for r in rows[:50]), default=0)
    for i in range(width):
        if i == word:
            continue
        cells = [clean_field(r[i])[0] for r in rows[:50] if i < len(r) and r[i].strip()]
        if len(cells) >= max(1, len(rows[:50]) // 2) and \
                sum(bool(_KANA.fullmatch(c)) for c in cells) >= 0.9 * len(cells):
            return i
    return None


def read_list(data, filename='', fmt=None, column=None, reading_column=None, header=None,
              states=('MASTERED', 'MATURE'), migaku_known=False):
    text = _decode(data)
    fmt = fmt or detect(text, filename)
    if fmt not in FORMATS:
        raise KnownWordsError('unsupported_format')
    out = {'format': fmt, 'columns': None, 'column': None, 'reading_column': None,
           'sample_rows': [], 'skipped': 0, 'rejected': 0, 'meta': {}}
    entries = []
    if fmt == 'text':
        for ln in text.splitlines():
            if not ln.strip() or ln.lstrip().startswith('#'):
                continue
            entries.append(clean_field(ln))
    elif fmt in ('tsv', 'csv'):
        rows, names = _table(text, fmt)
        if header is None:
            header = names is None and bool(rows) and _pick(rows[0], _EXPRESSION_NAMES) is not None
        if header and rows:
            names, rows = rows[0], rows[1:]
        width = max((len(r) for r in rows), default=0)
        if column is None:
            column = _pick(names, _EXPRESSION_NAMES) or 0
        if reading_column is None:
            reading_column = _pick(names, _READING_NAMES)
            if reading_column is None and names is None:
                reading_column = _kana_column(rows, column)
        elif reading_column < 0:
            reading_column = None
        if column < 0 or (width and column >= width):
            raise KnownWordsError('column_missing', column=column + 1)
        first = rows[0] if rows else []
        out.update(columns=list(names) if names else
                   [f'{i + 1}: {clean_field(first[i])[0][:16]}' if i < len(first) else str(i + 1) for i in range(width)],
                   column=column, reading_column=reading_column,
                   sample_rows=[[c[:40] for c in r[:8]] for r in rows[:5]])
        for r in rows:
            if column >= len(r):
                out['rejected'] += 1
                continue
            expression, reading = clean_field(r[column])
            if reading_column is not None and reading_column < len(r) and not reading:
                reading = clean_field(r[reading_column])[0]
            entries.append((expression, reading))
    elif fmt == 'jiten':
        bad = set(states) - set(JITEN_STATES)
        if bad:
            raise KnownWordsError('unsupported_format')
        current = None
        for ln in text.splitlines():
            if not ln.strip():
                continue
            m = re.fullmatch(r'=== ([A-Z]+) ===', ln.strip())
            if m:
                current = m.group(1)
                continue
            if current is None:
                raise KnownWordsError('jiten_header')
            if current in states:
                entries.append(clean_field(ln))
            else:
                out['skipped'] += 1
        out['meta'] = {'states': list(states)}
    elif fmt == 'migaku':
        if not migaku_known:
            raise KnownWordsError('migaku_confirm')
        reader = csv.DictReader(io.StringIO(text, newline=''))
        if reader.fieldnames != ['dictForm', 'secondary', 'hasCard']:
            raise KnownWordsError('unsupported_format')
        for row in reader:
            entries.append(clean_field(row.get('dictForm') or ''))
    else:
        try:
            env = json.loads(text)
        except ValueError:
            raise KnownWordsError('reibun_schema')
        if not isinstance(env, dict) or env.get('schema') != ENVELOPE or env.get('version') != ENVELOPE_VERSION:
            raise KnownWordsError('reibun_schema')
        for e in env.get('entries') or ():
            if isinstance(e, dict) and e.get('state', 'known') == 'known':
                entries.append((clean_field(str(e.get('expression', '')))[0], str(e.get('reading', '') or '')))
            else:
                out['skipped'] += 1
        src = env.get('source') if isinstance(env.get('source'), dict) else {}
        out['meta'] = {k: src.get(k) for k in ('name', 'decks', 'query', 'exported', 'anki') if src.get(k) is not None}
    if len(entries) > MAX_ROWS:
        raise KnownWordsError('too_many_rows', limit=MAX_ROWS)
    if any(len(e) > MAX_ENTRY for e, _ in entries):
        raise KnownWordsError('entry_too_long', limit=MAX_ENTRY)
    kept = [(e, r) for e, r in entries if e]
    out['rejected'] += len(entries) - len(kept)
    if not kept:
        raise KnownWordsError('empty')
    out['entries'] = kept
    return out


def preview(data, filename='', **options):
    got = read_list(data, filename, **options)
    sample = []
    for expression, reading in got['entries'][:8]:
        sample.append({'expression': expression, 'reading': reading,
                       'forms': ' '.join(iplusone.entry_units(expression, reading))})
    got = {k: v for k, v in got.items() if k != 'entries'} | {'entries': len(got['entries']), 'sample': sample}
    return got


def _sources_dir():
    return os.path.join(paths.known_words_dir(), 'sources')


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as fh:
        json.dump(data, fh, ensure_ascii=False)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _read_sources():
    out = []
    try:
        names = sorted(os.listdir(_sources_dir()))
    except FileNotFoundError:
        return out
    for name in names:
        if not name.endswith('.json'):
            continue
        try:
            with open(os.path.join(_sources_dir(), name), encoding='utf-8') as fh:
                data = json.load(fh)
            if data.get('schema') == ENVELOPE and data.get('id') == name[:-5]:
                out.append(data)
        except (OSError, ValueError):
            continue
    return out


def _units(entries):
    vocab = iplusone.compile_vocabulary(entries)
    return [[s] for s in sorted(vocab.singles)] + [list(p) for ps in vocab.phrases.values() for p in ps]


_ID = re.compile(r'[0-9a-f]{12}')


def import_list(data, filename='', name='', origin='file', replace=None, **options):
    if replace and not (_ID.fullmatch(replace) and any(r['id'] == replace for r in _read_sources())):
        raise KnownWordsError('not_found')
    got = read_list(data, filename, **options)
    with _LOCK:
        units = _units(got['entries'])
        if not units:
            raise KnownWordsError('only_grammar')
        stamp = time.strftime('%Y-%m-%dT%H:%M:%S')
        label = (name or got['meta'].get('name') or os.path.splitext(os.path.basename(filename))[0] or 'list')[:80]
        sid = replace or hashlib.sha1(f'{label}\0{stamp}\0{len(data)}'.encode('utf-8')).hexdigest()[:12]
        record = {'schema': ENVELOPE, 'version': ENVELOPE_VERSION, 'id': sid, 'name': label,
                  'origin': origin, 'format': got['format'], 'imported': stamp,
                  'meta': got['meta'], 'column': got['column'], 'reading_column': got['reading_column'],
                  'entries': [[e, r] for e, r in got['entries']],
                  'policy': iplusone.POLICY, 'units': units}
        _write_json(os.path.join(_sources_dir(), sid + '.json'), record)
        rebuild()
        return _summary(record)


def _summary(rec):
    return {'id': rec['id'], 'name': rec['name'], 'origin': rec.get('origin', 'file'),
            'format': rec.get('format'), 'imported': rec.get('imported'),
            'entries': len(rec.get('entries') or ()), 'words': len(rec.get('units') or ()),
            'meta': rec.get('meta') or {}}


def sources():
    return [_summary(r) for r in _read_sources()]


def remove(sid):
    with _LOCK:
        path = os.path.join(_sources_dir(), sid + '.json')
        if not _ID.fullmatch(sid or '') or not os.path.exists(path):
            return False
        os.remove(path)
        rebuild()
        return True


def rebuild():
    with _LOCK:
        units, entries = set(), 0
        for rec in _read_sources():
            if rec.get('policy') != iplusone.POLICY:
                rec['units'] = _units([tuple(e) for e in rec.get('entries') or ()])
                rec['policy'] = iplusone.POLICY
                _write_json(os.path.join(_sources_dir(), rec['id'] + '.json'), rec)
            units.update(tuple(u) for u in rec.get('units') or ())
        if not units:
            iplusone.drop_snapshot()
            return None
        singles = {u[0] for u in units if len(u) == 1}
        phrases = sorted(u for u in units if len(u) > 1)
        digest = hashlib.sha256(json.dumps([iplusone.POLICY, sorted(units)], ensure_ascii=False).encode('utf-8'))
        vocab = iplusone.Vocabulary(singles, phrases, digest.hexdigest()[:16], len(units))
        iplusone.save_snapshot(vocab)
        return vocab


def status():
    vocab = iplusone.current()
    return {'available': vocab is not None, 'words': vocab.entries if vocab else 0,
            'fingerprint': vocab.fingerprint if vocab else '', 'sources': sources(),
            'formats': list(FORMATS), 'envelope': {'schema': ENVELOPE, 'version': ENVELOPE_VERSION}}
