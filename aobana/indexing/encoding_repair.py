import hashlib
import os
import tempfile
from pathlib import Path
from aobana.indexing import subtitle_input
from aobana.utils import sub_relpath

def backup_path(backups, relpath, raw):
    first = Path(backups)/Path(str(relpath)+'.bak')
    n = 1
    while True:
        path = first if n == 1 else first.with_name(f'{Path(relpath).name} ({n}).bak')
        if not path.exists() or path.read_bytes() == raw:
            return path
        n += 1


def migrate_backups(backups):
    backups = Path(backups)
    if not backups.is_dir():
        return 0
    moved = 0
    for folder in sorted(p for p in backups.iterdir() if p.is_dir() and _is_digest(p.name)):
        for old in sorted(p for p in folder.rglob('*') if p.is_file()):
            raw = old.read_bytes()
            rel = old.relative_to(folder)
            relpath = rel.with_name(rel.name[:-4]) if rel.name.endswith('.bak') else rel
            dest = backup_path(backups, relpath, raw)
            if dest.exists():
                old.unlink()
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.replace(old, dest)
            moved += 1
        for sub in sorted((p for p in folder.rglob('*') if p.is_dir()), reverse=True):
            try:
                sub.rmdir()
            except OSError:
                pass
        try:
            folder.rmdir()
        except OSError:
            pass
    return moved


def _is_digest(name):
    return len(name) == 64 and all(c in '0123456789abcdef' for c in name)


def convert(root, item, backups):
    from aobana import paths
    selected = item.get('root') or next(iter(paths.root_list(root)), None)
    if not selected or not any(paths.same_roots(selected, folder) for folder in paths.root_list(root)):
        raise ValueError('Invalid encoding repair root')
    root = selected
    base = Path(root).resolve(strict=True)
    source = (base/item['path']).resolve(strict=True)
    if (not source.is_relative_to(base) or not source.is_file() or
            sub_relpath(str(source),str(base)) != item['name']):
        raise ValueError('Invalid encoding repair source')
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    expected = item.get('details',{}).get('sha')
    if not expected or digest != expected:
        raise ValueError('Encoding repair source changed')
    if not os.access(source,os.W_OK):
        raise ValueError('read_only')
    observed = subtitle_input.read(source)
    encoding = observed['encoding']
    if encoding == 'utf-8-sig':
        return {'name':item['name'],'status':'unchanged'}
    if encoding not in ('cp932','utf-16') or observed['format'] not in ('srt','ass'):
        raise ValueError('Unsupported encoding repair')
    text = raw.decode(encoding,errors='strict')
    if encoding == 'cp932' and text.encode('cp932',errors='strict') != raw:
        raise ValueError('Ambiguous CP932 byte mapping')
    if '\ufffd' in text or '\x00' in text:
        raise ValueError('Damaged subtitle text')
    converted = text.encode('utf-8',errors='strict')
    if converted.decode('utf-8') != text:
        raise ValueError('Encoding round trip failed')
    backup = backup_path(backups, source.relative_to(base), raw)
    backup.parent.mkdir(parents=True,exist_ok=True)
    if not backup.exists():
        with backup.open('xb') as fh:
            fh.write(raw); fh.flush(); os.fsync(fh.fileno())
    fd, name = tempfile.mkstemp(prefix='.aobana-encoding-',suffix=source.suffix,dir=source.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd,'wb') as fh:
            fh.write(converted); fh.flush(); os.fsync(fh.fileno())
        after = subtitle_input.read(temporary)
        if after['text'] != observed['text'] or after['format'] != observed['format']:
            raise ValueError('Subtitle content changed during conversion')
        if source.read_bytes() != raw or source.resolve() != source:
            raise ValueError('Encoding repair source changed before replacement')
        os.replace(temporary,source)
    finally:
        temporary.unlink(missing_ok=True)
    return {'name':item['name'],'status':'converted','backup':str(backup),
            'sha':hashlib.sha256(converted).hexdigest()}
