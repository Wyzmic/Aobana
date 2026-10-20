import hashlib
import json
import os
from aobana import paths
from aobana.utils import sub_relpath


def digest(path):
    sha = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            sha.update(block)
    return sha.hexdigest()


def validate(doc, conn):
    if doc.get('version') != 1 or not paths.same_roots(doc['root'], paths.media_roots('subs')):
        raise ValueError('Stale subtitle repair root')
    jobs, names = [], set()
    for item in doc['items']:
        selected = item.get('root') or next(iter(paths.root_list(doc['root'])), None)
        if not selected or not any(paths.same_roots(selected, folder) for folder in paths.root_list(doc['root'])):
            raise ValueError('Invalid subtitle repair root')
        root = os.path.realpath(selected)
        path = os.path.realpath(os.path.join(root, item['path']))
        if os.path.commonpath((root, path)) != root or item['name'] in names or sub_relpath(path, root) != item['name']:
            raise ValueError('Invalid subtitle repair input')
        names.add(item['name'])
        if paths.resolve_media_path('subs', item['name']) != path:
            raise ValueError('Subtitle repair source is shadowed')
        source = conn.execute('SELECT id,file_hash FROM sources WHERE relpath=?', (item['name'],)).fetchone()
        expected = (item.get('source_id'), item.get('indexed_hash'))
        if source is None or tuple(source) != expected or digest(path) != item['sha']:
            raise ValueError('Subtitle repair input changed: ' + item['name'])
        jobs.append((path, item['name'], None))
    return jobs


def load(path):
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)
