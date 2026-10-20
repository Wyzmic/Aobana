import json
import os
import sqlite3
import uuid
from pathlib import Path
from contextlib import closing
from aobana import paths
from aobana.indexing import repair
from aobana.indexing.run_control import WriterLease
from aobana.utils import filtered_names, name_key

def state_path():
    return Path(paths.companion('pending-reindex.json'))

def load():
    path = state_path()
    try:
        doc = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(doc, dict) or doc.get('version') != 1 or not isinstance(doc.get('items'), list):
            raise ValueError('not a version 1 queue')
    except FileNotFoundError:
        return {'version': 1, 'root': paths.roots_value('subs'), 'items': []}
    except ValueError as error:
        from aobana.utils import say
        try:
            os.replace(path, path.with_name(path.name + '.bad'))
        except OSError:
            pass
        say(f"PENDING_DROPPED {path.name}: unreadable ({error})")
        return {'version': 1, 'root': paths.roots_value('subs'), 'items': []}
    return doc

def _write(doc):
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with tmp.open('w',encoding='utf-8') as fh:
            json.dump(doc, fh, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp,path)
    finally:
        tmp.unlink(missing_ok=True)

def save(doc):
    with WriterLease(paths.subs_db()), WriterLease(state_path()):
        with closing(sqlite3.connect(Path(paths.subs_db()).resolve().as_uri()+'?mode=ro',uri=True)) as conn:
            repair.validate(doc,conn)
        old = load()
        if old['items'] and not paths.same_roots(old['root'], doc['root']):
            raise ValueError('Pending subtitle refresh belongs to another folder')
        excluded = filtered_names(paths.filtered_list(),'subs')
        items = {i['name']:i for i in old['items']}
        for item in doc['items']:
            if name_key(item['name']) not in excluded:
                items[item['name']] = dict(item)
        _write({'version':1,'root':doc['root'],'items':list(items.values())})
        return len(items)

def validated(conn):
    doc = load()
    if not doc['items']:
        return doc, []
    excluded = filtered_names(paths.filtered_list(),'subs')
    same_root = paths.same_roots(doc['root'], paths.media_roots('subs'))
    jobs, stale = [], []
    for item in doc['items']:
        if name_key(item['name']) in excluded:
            continue
        if not same_root:
            stale.append((item, 'the Subtitles folder changed'))
            continue
        try:
            jobs += repair.validate(dict(doc, items=[item]), conn)
        except (ValueError, OSError) as error:
            stale.append((item, str(error)))
    if stale:
        from aobana.utils import say
        for item, why in stale:
            say(f"PENDING_DROPPED {item['name']}: {why}")
        _drop([item for item, _ in stale])
        gone = {_identity(item) for item, _ in stale}
        doc = dict(doc, items=[i for i in doc['items'] if _identity(i) not in gone])
    return doc, jobs


def _identity(item):
    return (item['name'], item['sha'], item.get('source_id'), item.get('indexed_hash'))


def _drop(items):
    gone = {_identity(i) for i in items}
    with WriterLease(state_path()):
        current = load()
        kept = [i for i in current['items'] if _identity(i) not in gone]
        if len(kept) != len(current['items']):
            _write(dict(current, items=kept))


def committed(doc, names):
    if not names:
        return
    completed = {(i['name'],i['sha'],i.get('source_id'),i.get('indexed_hash'))
                 for i in doc['items'] if i['name'] in names}
    with WriterLease(state_path()):
        current = load()
        if current.get('root') != doc.get('root'):
            return
        current['items'] = [i for i in current['items'] if
            (i['name'],i['sha'],i.get('source_id'),i.get('indexed_hash')) not in completed]
        _write(current)


def converted(root, name, before_sha, after_sha):
    with WriterLease(state_path()):
        doc = load()
        if not paths.same_roots(doc['root'], root):
            return
        changed = False
        for item in doc['items']:
            if item['name'] == name and item['sha'] == before_sha:
                item['sha'] = after_sha
                changed = True
        if changed:
            _write(doc)
