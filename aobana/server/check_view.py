import json
import os
import sys

from aobana.server import library

PAGE = 200
HEAD_WIDTH = 20


def _overruled(group, keepers_of):
    indexed = [m for m in group['members'] if not m.get('saved')]
    if len(indexed) != 1 or indexed[0]['name'] == group['keeper']:
        return False
    return any(other is not group and any(m['name'] == group['keeper'] for m in other['members'])
               for other in keepers_of.get((group['media'], indexed[0]['name']), ()))


def actionable_groups(groups):
    keepers_of = {}
    for group in groups:
        keepers_of.setdefault((group['media'], group['keeper']), []).append(group)
    out = []
    for group in groups:
        if _overruled(group, keepers_of):
            continue
        if any(library.needs_exclusion(group, m, group['keeper']) for m in group['members']) or any(
                m['name'] == group['keeper'] and (m.get('saved') or {}).get('reason') == 'duplicate' for m in group['members']):
            out.append(group)
    return out


def _sections(report):
    out = []
    queued = report.get('pending_items') or []
    queued_names = {i['name'] for i in queued}
    due = (report.get('repair') or {}).get('items') or []
    out.append(('pending', queued, {}))
    out.append(('reindex', [i for i in due if i['name'] not in queued_names], {}))
    out.append(('repair-doc', due, {}))
    recheck = report.get('recheck') or []
    for media in ('subs', 'epub', 'manga', 'custom'):
        for name, dups in (('recheck-dups', True), ('recheck', False)):
            rows = [i for i in recheck if i['media'] == media and (i['saved'] == 'duplicate' and not i.get('now')) == dups]
            if rows:
                out.append((f'{name}:{media}', rows, {'keys': [f"{i['media']}\t{i['name']}" for i in rows]}))
    groups = report.get('groups') or []
    books = {item['name']: item for item in report.get('items', []) if item['media'] == 'epub' and item.get('title')}
    for media in ('subs', 'epub', 'manga', 'custom'):
        reasons = {}
        for item in report.get('items', []):
            if item['media'] != media or item.get('filtered') or item['reason'] == 'duplicate_kept':
                continue
            if item['reason'] == 'duplicate' and groups:
                continue
            reasons.setdefault(item['reason'], []).append(item)
        for reason, rows in reasons.items():
            out.append((f'find:{media}:{reason}', rows,
                        {'ids': [int(i['id']) for i in rows if i['reason'] in library.FILTERABLE]}))
        listed = actionable_groups([g for g in groups if g['media'] == media]) if groups else []
        if listed:
            for group in listed:
                for member in group['members']:
                    book = books.get(member['name']) if media == 'epub' else None
                    if book:
                        member['title'], member['author'] = book.get('title'), book.get('author')
            out.append((f'dup:{media}', listed, {
                'groups': [[g['id'], g['keeper']] for g in listed],
                'size': sum(sum(library.needs_exclusion(g, m, g['keeper']) for m in g['members']) for g in listed)}))
    return out


def build(path, key):
    report = library.analysis_report(with_key=True)
    header = {'key': key, 'report': None, 'sections': {}}
    tmp = f'{path}.{os.getpid()}.tmp'
    with open(tmp, 'wb') as out:
        out.write(b'0' * HEAD_WIDTH + b'\n')
        if report is not None:
            header['report'] = {k: v for k, v in report.items()
                                if k not in ('items', 'groups', 'recheck', 'repair', 'pending_items', 'last_attempt')}
            header['report']['repair_meta'] = {k: v for k, v in (report.get('repair') or {}).items() if k != 'items'}
            for name, rows, extra in _sections(report):
                pages = []
                for n, row in enumerate(rows):
                    if n % PAGE == 0:
                        pages.append(out.tell())
                    out.write(json.dumps(row, ensure_ascii=False, separators=(',', ':')).encode('utf-8') + b'\n')
                header['sections'][name] = dict(extra, count=len(rows), pages=pages)
        at = out.tell()
        out.write(json.dumps(header, ensure_ascii=False, separators=(',', ':')).encode('utf-8') + b'\n')
        out.seek(0)
        out.write(str(at).rjust(HEAD_WIDTH, '0').encode('ascii'))
    library.replace_retrying(tmp, path)


def read_header(path):
    with open(path, 'rb') as fh:
        at = int(fh.readline())
        fh.seek(at)
        return json.loads(fh.readline())


def read_rows(path, section, start, limit):
    pages = section['pages']
    if start >= section['count'] or limit <= 0:
        return []
    with open(path, 'rb') as fh:
        fh.seek(pages[start // PAGE])
        for _ in range(start % PAGE):
            fh.readline()
        return [json.loads(fh.readline()) for _ in range(min(limit, section['count'] - start))]


def _save():
    request = json.loads(sys.stdin.buffer.read().decode('utf-8'))
    library._save_progress = lambda done, total: print(json.dumps({'progress': [done, total]}), flush=True)
    error, result = library.filter_flagged(request.get('ids') or [], request.get('generation'), request.get('choices') or [])
    print(json.dumps({'result': [error, result]}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    if sys.argv[1:2] == ['--view']:
        key = json.loads(sys.argv[2])
        if [k[0] for k in key] != [k[0] for k in library._view_key()]:
            sys.exit('check_view: the server reads other files than this process')
        build(library.view_path(), key)
    elif sys.argv[1:2] == ['--save']:
        _save()
    else:
        sys.exit('usage: check_view --view KEY | --save')
