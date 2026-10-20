import os
import re
from collections import Counter, defaultdict

from aobana.utils import RUBY_RE

RULE_VERSION = 4
_SONG_RE = re.compile('[♪♬]')
_KANJI_RE = re.compile('[一-鿿々]')
_KANA_READING_RE = re.compile('[ぁ-ゖァ-ヺー・ 　]+')


def has_author_furigana(lines):
    for line in lines:
        if _SONG_RE.search(line):
            continue
        for match in RUBY_RE.finditer(line):
            if match[1] and _KANJI_RE.search(match[1]) and _KANA_READING_RE.fullmatch(match[3]):
                return True
    return False


SERVICES = {
    'Netflix': ('netflix', 'nf'), 'Amazon': ('amazon', 'amzn', 'primevideo'),
    'Hulu': ('hulu',), 'Disney+': ('disney+', 'dsnp'), 'AppleTV': ('appletv', 'atvp'),
    'TVer': ('tver',), 'Bandai': ('bandai',),
}
PRIMARY_SERVICES = {'Netflix', 'Amazon'}


def hints(name):
    base = re.split(r'[\\/]', name)[-1]
    services = []
    for family, aliases in SERVICES.items():
        for alias in aliases:
            pattern = r'(?<![\w])' + re.escape(alias) + r'(?![\w])'
            match = re.search(pattern, base, re.I)
            if not match:
                continue
            metadata = (re.search(r'\[[^\]]*' + re.escape(alias) + r'[^\]]*\]', base, re.I)
                        or (match.start() > 0 and base[match.start()-1] in '._-+')
                        or (match.end() < len(base) and base[match.end()] in '._-+[')
                        or re.search(r'\b' + re.escape(alias) + r'[ ._-]+(?:\d{3,4}p|web[ ._-]?(?:dl|rip)|ja|jpn|cc|sdh)\b', base, re.I))
            if not metadata:
                continue
            if alias == 'nf' and not (re.search(r'\[[^\]]*\bnf\b[^\]]*\]', base, re.I)
                                      or re.search(r'\bnf[ ._-]+(?:web[ ._-]?(?:dl|rip)|\d{3,4}p)\b', base, re.I)
                                      or re.search(r'(?:\d{3,4}p|web[ ._-]?(?:dl|rip))[ ._-]+nf\b', base, re.I)):
                continue
            services.append(family)
            break
    machine = bool(re.search(r'(?<![\w])(?:ocr|asr|whisper)(?![\w])', base, re.I))
    caption = bool(re.search(r'(?<![\w])(?:cc|sdh)(?![\w])|\[字\]', base, re.I))
    return {'services': services, 'machine': machine, 'caption': caption}


def rank(name, row, disk):
    detected = hints(name)
    actual = row.get('details', {}).get('format', os.path.splitext(name)[1][1:].lower())
    placed = disk.get(name, name) if disk else name
    folder = bool(re.search(r'[\\/]', placed))
    services = detected['services']
    service = 0 if PRIMARY_SERVICES.intersection(services) else 1 if services else 2
    author_ruby = row.get('details', {}).get('author_furigana', False)
    return (not author_ruby, actual != 'srt', detected['machine'], service,
            not detected['caption'], -row['n'], not folder, name.casefold(), name)


def _shared(a, b):
    i = j = total = 0
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            total += 1; i += 1; j += 1
        elif a[i] < b[j]:
            i += 1
        else:
            j += 1
    return total


def _scope_job(job):
    names, rows, disk, exact_of, reserved, loose_keys, unpack = job
    order = lambda n: (n in exact_of, rank(n, rows[n], disk))
    out, final, twins, loose_hits = [], {}, [], {}
    posts, keys = defaultdict(list), {}
    for name in names:
        own = unpack(rows[name]['keys'])
        if name in exact_of:
            keys[name] = own
            for key in own:
                posts[key].append(name)
            continue
        candidates = Counter(k for key in own for k in posts[key])
        keeper = None
        if name not in reserved:
            keeper = next((k for k in sorted(candidates, key=order)
                           if len(own) and candidates[k] / len(own) >= .9
                           and candidates[k] / len(keys[k]) >= .9), None)
        if keeper:
            share = min(candidates[keeper]/len(own), candidates[keeper]/len(keys[keeper]))
            if keeper in exact_of:
                twins.append((name, keeper, share))
            else:
                out.append((name, keeper, share, 'same_lines')); final[name] = keeper
        else:
            keys[name] = own
            for key in own:
                posts[key].append(name)
    for name, own in loose_keys.items():
        if name in reserved:
            continue
        candidates = Counter(k for key in own for k in posts.get(key, ()))
        for keeper in sorted(candidates, key=order):
            shared = candidates[keeper]
            if own and shared/len(own) >= .9 and shared/len(keys[keeper]) >= .9:
                loose_hits[name] = (keeper, min(shared/len(own), shared/len(keys[keeper])), order(keeper))
                break
    return out, final, twins, loose_hits


def recommend(rows, disk, unpack, subplz_sets, progress=None, workers=1):
    pulse = progress or (lambda: None)
    readable = {n: r for n, r in rows.items() if not r.get('error') and r['n'] > 0}
    out, dropped, reserved = [], set(), set()
    for keep, copies in subplz_sets(list(readable)):
        pulse()
        reserved.add(keep)
        for copy in copies:
            out.append((copy, keep, 1.0, 'subplz'))
            dropped.add(copy)
    by_scope, loose, exact = defaultdict(list), [], {}
    exact_copies, exact_of, twins = [], {}, []
    def scope_of(n):
        return re.split(r'[\\/]', n, maxsplit=1)[0] if re.search(r'[\\/]', disk.get(n, n) if disk else n) else None
    for name in sorted(readable, key=lambda n: (n not in reserved, rank(n, readable[n], disk))):
        pulse()
        if name in dropped:
            continue
        sha = readable[name].get('sha')
        copy = bool(name not in reserved and sha and sha in exact)
        if copy:
            exact_copies.append((name, exact[sha])); exact_of[name] = exact[sha]
        elif sha:
            exact.setdefault(sha, name)
        if re.search(r'[\\/]', disk.get(name, name) if disk else name):
            scope = re.split(r'[\\/]', name, maxsplit=1)[0]
            if not copy or scope_of(exact_of[name]) != scope:
                by_scope[scope].append(name)
            else:
                del exact_of[name]
        elif not copy:
            loose.append(name)
    loose_keys = {n: unpack(readable[n]['keys']) for n in loose}
    def jobs():
        for scope in sorted(by_scope):
            pulse()
            names = sorted(by_scope[scope], key=lambda n: (n not in exact_of, n not in reserved, rank(n, readable[n], disk)))
            near = {}
            if loose_keys:
                lines = set()
                for n in names:
                    lines.update(unpack(readable[n]['keys']))
                near = {n: own for n, own in loose_keys.items() if not lines.isdisjoint(own)}
            yield (names, {n: readable[n] for n in names}, {n: disk[n] for n in names if n in disk} if disk else disk,
                   {n: exact_of[n] for n in names if n in exact_of}, reserved.intersection(names), near, unpack)
    from aobana.utils import parallel_map, stop_requested
    loose_best, final = {}, {}
    for scope_out, scope_final, scope_twins, loose_hits in parallel_map(
            _scope_job, jobs(), max(1, min(workers, len(by_scope))), stop=stop_requested):
        pulse()
        out.extend(scope_out)
        final.update(scope_final)
        twins.extend(scope_twins)
        for name, (keeper, share, rank_key) in loose_hits.items():
            prior = loose_best.get(name)
            if prior is None or rank_key < prior[2]:
                loose_best[name] = (keeper, share, rank_key)
    if stop_requested():
        pulse()
        raise RuntimeError('duplicate comparison stopped')
    for name,(keeper,share,_) in sorted(loose_best.items()):
        if keeper in exact_of:
            twins.append((name, keeper, share))
        else:
            out.append((name,keeper,share,'same_lines')); final[name] = keeper
    for name,via,share in twins:
        pulse()
        if exact_of[via] == name:
            continue
        keeper = final.get(exact_of[via], exact_of[via])
        if keeper == name:
            keeper = exact_of[via]
        if keeper != exact_of[via]:
            a,b = unpack(readable[name]['keys']),unpack(readable[keeper]['keys'])
            shared = _shared(a,b)
            if a and b and shared/len(a) >= .9 and shared/len(b) >= .9:
                share = min(shared/len(a),shared/len(b))
            else:
                keeper = exact_of[via]
        out.append((name,keeper,share,'same_lines')); final[name] = keeper
    for name,keeper in exact_copies:
        pulse()
        keeper = final.get(keeper,keeper)
        a,b = unpack(readable[name]['keys']),unpack(readable[keeper]['keys'])
        same = readable[name]['sha'] == readable[keeper]['sha']
        shared = _shared(a,b)
        if same or (a and b and shared/len(a) >= .9 and shared/len(b) >= .9):
            out.append((name,keeper,1.0 if same else min(shared/len(a),shared/len(b)),
                        'same_bytes' if same else 'same_lines'))
    return out
