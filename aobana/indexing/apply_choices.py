import os
import time
import unicodedata
from aobana.indexing import repair
from aobana.indexing.duplicate_rules import RULE_VERSION
from aobana.utils import name_key
from aobana import paths

EQUIVALENT = {'subs': .9, 'epub': .5, 'custom': .8}


def _input_path(root, relative):
    if isinstance(root, (list, tuple)):
        for folder in root:
            try:
                return _input_path(folder, relative)
            except ValueError:
                continue
        raise ValueError('stale_inputs')
    path = os.path.realpath(os.path.join(root, relative))
    if os.path.exists(path):
        return path
    current = root
    for part in relative.replace(chr(92), '/').split('/'):
        exact = os.path.join(current, part)
        if os.path.exists(exact):
            current = exact
            continue
        try:
            matches = [entry.name for entry in os.scandir(current)
                       if unicodedata.normalize('NFC', entry.name) == unicodedata.normalize('NFC', part)]
        except OSError:
            raise ValueError('stale_inputs') from None
        if len(matches) != 1:
            raise ValueError('stale_inputs')
        current = os.path.join(current, matches[0])
    return os.path.realpath(current)


def apply(report, roots, rows, generation, choices, progress=None):
    if not report or not report.get('completed') or report.get('generation') != generation or report.get('rule_version') != RULE_VERSION:
        raise ValueError('stale_report')
    groups = {g['id']: g for g in report['groups']}
    if not isinstance(choices, list) or not choices or any(not isinstance(c, dict) or not isinstance(c.get('group'), str) for c in choices):
        raise ValueError('bad_groups')
    if len({c['group'] for c in choices}) != len(choices):
        raise ValueError('bad_groups')
    changes = []
    saved = {(r['media'], name_key(r['name'])): r for r in rows}
    for done, choice in enumerate(choices):
        if progress:
            progress(done, len(choices))
        group = groups.get(choice['group'])
        if not group:
            raise ValueError('bad_groups')
        media = group['media']
        root = roots.get(media)
        if not root or not paths.same_roots(root, report['roots'][media]):
            raise ValueError('stale_roots')
        members = group['members']
        names = {m['name'] for m in members}
        keep_all = choice.get('keep_all') is True
        keeper = None if keep_all else choice.get('keeper', group['keeper'])
        if not keep_all and keeper not in names:
            raise ValueError('bad_keeper')
        if keep_all and 'exclude' in choice:
            raise ValueError('bad_selection')
        for member in members:
            if keeper not in (None, group['keeper']) and group.get('comparisons', {}).get(keeper, {}).get(member['name'], 0) < EQUIVALENT.get(media, 1):
                raise ValueError('keeper_not_equivalent')
            path = _input_path(root, member['path'])
            if not any(paths.inside_root(path, folder)
                       for folder in paths.root_list(root)) or repair.digest(path) != member['sha']:
                raise ValueError('stale_inputs')
            existing = saved.get((media, name_key(member['name'])))
            if existing and existing['reason'] != 'duplicate':
                raise ValueError('protected_exclusion')
        excluded = [] if keep_all else choice.get('exclude', [m['name'] for m in members if m['name'] != keeper])
        if (not isinstance(excluded, list) or any(not isinstance(n, str) for n in excluded)
                or len(set(excluded)) != len(excluded) or keeper in excluded
                or not set(excluded) <= names):
            raise ValueError('bad_selection')
        changes.append((media, keeper, members, set(excluded)))
    now = time.strftime('%Y-%m-%d %H:%M:%S')
    for media, keeper, members, excluded in changes:
        for member in members:
            key = (media, name_key(member['name']))
            if keeper is None or member['name'] == keeper:
                if key in saved and saved[key]['reason'] == 'duplicate':
                    saved.pop(key)
            elif member['name'] in excluded and not (key in saved and saved[key].get('keep') == keeper):
                saved[key] = dict(media=media, name=member['name'], reason='duplicate', keep=keeper, date=now, origin='manual')
    return list(saved.values())
