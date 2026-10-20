import functools
import html
from html.parser import HTMLParser
import json
import os

from aobana import paths
from aobana.search.furigana import highlight_and_furigana, work_key
from aobana.search.reading import parse_reading_terms, row_matches
from aobana.search.titles import format_custom_title, get_sort_key
from aobana.utils import fold_title_filter, load_ruby_trims, name_key, ruby_merge_key


def draw_row(row, highlight=None):
    row['line_html'] = draw_line(row['line'], row['marks'], row.get('file', ''), highlight)
    row['display_line'] = row['line_html']


@functools.lru_cache(maxsize=1)
def _trims():
    return load_ruby_trims(paths.RUBY_TABLES_PATH)


def attach_ruby(text, marks):
    # A reading the text wrote over its word (utils.custom_ruby) covers that word, or the part a
    # ruling of the ruby_trim table names: 盲目的文刃(もんじん) over 文刃
    attached = {}
    for i, (kind, start, end, value) in enumerate(marks):
        if kind == 'ruby' and start < end:
            reading = value.partition(':')[2]
            cut = _trims().get((text[start:end], ruby_merge_key(reading)), 0)
            attached[i] = (start + cut, end, reading)
    return attached


VOID_TAGS = {'br', 'img', 'wbr', 'hr'}


class MarkedHTML(HTMLParser):
    def __init__(self, attached):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.text_pos = 0
        self.in_reading = 0
        self.open_tags = []
        self.opens = {s: r for s, e, r in attached.values()}
        self.closes = {e: r for s, e, r in attached.values()}

    def handle_starttag(self, tag, attrs):
        if tag == 'rt':
            self.in_reading += 1
        elif tag not in VOID_TAGS and not self.in_reading:
            self.open_tags.append((tag, self.get_starttag_text()))
        self.parts.append(self.get_starttag_text())

    def handle_endtag(self, tag):
        self.parts.append(f'</{tag}>')
        if tag == 'rt':
            self.in_reading -= 1
        elif not self.in_reading and self.open_tags and self.open_tags[-1][0] == tag:
            self.open_tags.pop()

    def around(self, html_part):
        # A highlight open across a written reading's edge is closed and opened again there, or the
        # <b> ends inside the <ruby> and the browser draws the reading beside the word (盲目的文刃)
        closing = ''.join(f'</{t}>' for t, _ in reversed(self.open_tags))
        opening = ''.join(s for _, s in self.open_tags)
        self.parts.append(closing + html_part + opening)

    def handle_data(self, data):
        if self.in_reading:
            self.parts.append(html.escape(data))
            return
        for char in data:
            if self.text_pos in self.opens:
                self.around('<ruby>')
            self.parts.append(html.escape(char))
            self.text_pos += 1
            if self.text_pos in self.closes:
                self.around(f'<rt>{html.escape(self.closes[self.text_pos])}</rt></ruby>')


def draw_line(text, marks, file='', highlight=None):
    args = {'content_bases': [], 'q': '', 'mark': False, 'bold': False, 'work': work_key('custom', file)}
    args.update(highlight or {})
    rendered = highlight_and_furigana(text, **args)
    parser = MarkedHTML(attach_ruby(text, marks or []))
    parser.feed(rendered)
    return f'<span class="custom-text">{"".join(parser.parts)}</span>'


def decorate_result(row, conn, highlight):
    data = conn.execute('SELECT * FROM custom_lines WHERE rowid = ?', (row['rowid'],)).fetchone()
    if data is None:
        return
    data = dict(data)
    row.update(data)
    row['marks'] = json.loads(data['marks'] or '[]')
    row['title'] = format_custom_title(row['file'])
    draw_row(row, highlight)


def _source_fields(row, metadata=None):
    out = dict(row)
    out['file'] = out['relpath']
    out['path'] = (metadata or {}).get(out['relpath'], {}).get('path', name_key(out['relpath']))
    out['title'] = format_custom_title(out['path'])
    out['type'] = 'file'
    return out


def lone_file(sources, folder):
    inside = [s for s in sources if s['path'].startswith(folder + '/') or (s['category'] == folder and '/' not in s['path'])]
    if len(inside) != 1:
        return None
    parent, _, name = inside[0]['path'].rpartition('/')
    if parent not in ('', folder) or os.path.splitext(name)[0].casefold() != folder.rpartition('/')[2].casefold():
        return None
    return inside[0]


def all_sources(conn):
    def rows(sql):
        cursor = conn.execute(sql)
        names = [d[0] for d in cursor.description]
        return [dict(zip(names, r)) for r in cursor]
    metadata = {r['relpath']: r for r in rows('SELECT * FROM custom_source_meta')} if conn.execute(
        'SELECT 1 FROM sqlite_master WHERE name = ?', ('custom_source_meta',)).fetchone() else {}
    return metadata, [_source_fields(r, metadata) for r in rows('SELECT id, relpath, category, kind, lines, order_key FROM sources ORDER BY order_key, relpath')]


# Default follows each source's own order, then natural names.
FOLDER_SORTS = {
    'name': lambda r: get_sort_key(r['title']),
    'parts_desc': lambda r: -r.get('files', 1),
    'parts_asc': lambda r: r.get('files', 1),
    'lines_desc': lambda r: -(r.get('lines') or 0),
    'lines_asc': lambda r: r.get('lines') or 0,
}


class Stopped(Exception):
    pass


def _reading_where(needle, exact, ruby_only, conn, stop=None):
    from aobana.search.engine import analyze_query, _match_where, fts_phrase, like_escape, split_negated_terms
    from aobana.search.furigana import detect_script, line_analysis
    q_plain, terms, neg_terms, q_rest = parse_reading_terms(needle)
    rest = split_negated_terms(q_rest)[0].strip('""“”')
    excluded = [n.strip('""“”') for n in split_negated_terms(q_plain)[1] if n.strip('""“”')]
    if not terms and not rest:
        return '0', []

    def where(table):
        wheres, params = [], []
        if rest and exact:
            wheres.append('instr(clean_text, ?) > 0')
            params.append(rest)
        elif rest:
            _, bases, readings, _ = analyze_query(rest)
            found = _match_where(table, bases, readings, detect_script(rest))
            found = found or ('line LIKE ? ESCAPE char(92)', ['%' + like_escape(rest) + '%'])
            wheres.append(found[0])
            params.extend(found[1])
        for term in terms:
            found = None
            if not exact:
                _, bases, readings, _ = analyze_query(term.word)
                found = _match_where(table, bases, readings, detect_script(term.word))
                if found and len(term.lemmas) == 1:
                    lemmas = ' OR '.join(f'base_forms:{fts_phrase(lemma)}' for lemma in sorted(term.lemmas[0]))
                    found = (found[0], [f'({found[1][0]}) OR ({lemmas})'])
            if found:
                wheres.append(f'({table}.rowid IN (SELECT rowid FROM {table} WHERE {found[0]}) OR instr(clean_text, ?) > 0)')
                params.extend(found[1])
            else:
                wheres.append('instr(clean_text, ?) > 0')
            params.append(term.word)
        for phrase in excluded:
            wheres.append('instr(clean_text, ?) = 0')
            params.append(phrase)
        return ' AND '.join(wheres), params

    from aobana.search import engine
    from aobana.search.engine import reading_prefilter
    from aobana.utils import has_token_lengths
    lens = has_token_lengths(conn)

    def select(table):
        # The search page's columns, so its prefilter skips the rows that cannot hold the word before Sudachi reads them
        cols = f'{table}.rowid, {table}.file, {table}.line, {table}.clean_text, {table}.readings, {table}.base_forms'
        if lens:
            return f'{cols}, token_lengths.lens FROM {table} LEFT JOIN token_lengths ON token_lengths.rowid = {table}.rowid'
        return f'{cols}, NULL FROM {table}'
    sql, args = where('custom')
    kept = []
    for rowid, file, line, clean_text, row_readings, row_bases, row_lens in conn.execute(
            f'SELECT {select("custom")} WHERE {sql}', args):
        # The connection's interrupt is lost when it lands between statements: the flag is not
        if stop and stop[0]:
            raise Stopped()
        work = work_key('custom', file)
        if terms and engine.READING_PREFILTER and not reading_prefilter(
                terms, line, clean_text, row_readings, 'custom', work, row_bases, row_lens):
            continue
        if row_matches(line_analysis(line, work), terms, neg_terms, work, exact, ruby_only):
            kept.append(rowid)
    return 'rowid IN (SELECT value FROM json_each(?))', [json.dumps(kept)]


def _content_where(needle, exact, ruby_only, conn=None, stop=None):
    from aobana.search.engine import analyze_query, _match_where, query_highlight_args, like_escape, split_negated_terms
    from aobana.search.furigana import detect_script
    # `猫 -犬`: the words matched, and a line holding an excluded one left out, as the search page does
    wanted, excluded = split_negated_terms(needle)
    wanted = wanted.strip('""“”')
    excluded = [n.strip('""“”') for n in excluded if n.strip('""“”')]

    if parse_reading_terms(needle)[1:3] != ((), ()):
        sql, args = _reading_where(needle, exact, ruby_only, conn, stop)
    elif not wanted:
        sql, args = '0', []
    else:
        _, bases, readings, _ = analyze_query(wanted)
        where = None if exact else _match_where('custom', bases, readings, detect_script(wanted))
        sql, args = where or ('clean_text LIKE ? ESCAPE char(92)', ['%' + like_escape(wanted) + '%'])
        for phrase in excluded:
            sql, args = f'({sql}) AND instr(clean_text, ?) = 0', [*args, phrase]
    if ruby_only:
        sql = f'({sql}) AND EXISTS (SELECT 1 FROM custom_lines r WHERE r.rowid = custom.rowid AND r.marks LIKE ?)'
        args = [*args, '%"ruby"%']
    return f'({sql})', list(args), query_highlight_args(needle, 'custom')


def folder_page(conn, path='', needle='', mode='title', offset=0, limit=500, exact=False, ruby_only=False, sort='default',
                stop=None):
    path = name_key(path).strip('/')
    if any(p in ('.', '..') for p in path.split('/')):
        return None
    folder = conn.execute('SELECT * FROM custom_folders WHERE path = ?', (path,)).fetchone()
    if folder is None:
        return None
    metadata, sources = all_sources(conn)

    def below(item):
        return not path or item['path'].startswith(path + '/') or (item['category'] == path and '/' not in item['path'])
    scoped = [s for s in sources if below(s) and not metadata.get(s['relpath'], {}).get('folder_page')]
    introduction = next((s for s in scoped if metadata.get(s['relpath'], {}).get('paired_folder') == path), None)
    rows, hl = [], None
    if needle and mode == 'content':
        sql, args, hl = _content_where(needle, exact, ruby_only, conn, stop)
        ids = {s['id']: s for s in scoped}
        for r in conn.execute(f'SELECT rowid, source_id, file, line FROM custom WHERE {sql} ORDER BY rowid', args):
            if r['source_id'] not in ids:
                continue
            item = dict(r)
            item.update(type='hit', path=name_key(r['file']))
            rows.append(item)
    elif needle:
        folded = fold_title_filter(needle)
        rows = [s for s in scoped if folded in fold_title_filter(s['title'])]
    else:
        for child in conn.execute('SELECT * FROM custom_folders WHERE parent = ? AND path != ? ORDER BY order_key, name', (path, path)):
            child = dict(child)
            if not child['files']:
                continue
            # A folder is a folder, one file in it or more, but for its one file under its own name
            alone = lone_file(sources, child['path'])
            if alone is not None and alone in scoped:
                rows.append(dict(alone, shown_in=path))
            else:
                rows.append(dict(child, type='folder', title=child['name']))
        shown = {r['path'] for r in rows if r['type'] == 'file'}
        rows.extend(s for s in scoped if s is not introduction and s['path'] not in shown and (s['path'].rpartition('/')[0] == path or (s['category'] == path and '/' not in s['path'])))
        if any(s['kind'] == 'md' for s in scoped):
            rows.sort(key=lambda r: (r.get('order_key', ''), r['path']))
        if path and '/' not in path and not any(s['kind'] == 'md' for s in scoped):
            rows.sort(key=lambda r: get_sort_key(r['title']))
    if mode != 'content' and sort in FOLDER_SORTS:
        rows.sort(key=FOLDER_SORTS[sort])
    page = rows[offset:offset + limit]
    for item in page:
        # Only the page's hits are drawn: 21,394 hits took 5.8 s, all but 500 thrown away
        if hl is not None:
            decorate_result(item, conn, hl)
        if needle:
            relative = item['path'][len(path) + 1:] if path and item['path'].startswith(path + '/') else item['path']
            item['relative_title'] = format_custom_title(relative)
    return {'path': path, 'parent': path.rpartition('/')[0], 'folder': dict(folder),
            'items': page, 'total': len(rows), 'has_more': offset + limit < len(rows),
            'page': file_page(conn, introduction['file']) if introduction and not needle else None}


def _content(conn):
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'custom_quiet'").fetchone() is None:
        return 'custom_content'
    return '(SELECT id, c0, c1, c2 FROM custom_content UNION ALL SELECT rowid, source_id, file, line FROM custom_quiet)'


# A .txt or .md file is read a page at a time, as an episode is: a .txt of 102,033 lines took
# 14 s and 40 MB as one answer. A .md page starts and ends at a heading, so a fold is never cut.
PAGED_KINDS = ('txt', 'md')
PAGE_LINES = 500
CONTEXT_ABOVE = 200


def _page_bounds(starts, total, offset, limit, at=None, before=None):
    import bisect
    reach = 4 * limit

    def back(i):
        if starts is None:
            return i
        k = bisect.bisect_right(starts, i) - 1
        return starts[k] if k >= 0 and i - starts[k] <= reach else i

    def ahead(i):
        if starts is None or i >= total:
            return min(i, total)
        k = bisect.bisect_left(starts, i)
        to = starts[k] if k < len(starts) else total
        return to if to - i <= reach else i
    if before is not None:
        end = max(0, min(before, total))
        return back(max(0, end - limit)), end
    start = max(0, at - CONTEXT_ABOVE) if at is not None else offset
    start = back(min(max(0, start), total))
    return start, max(ahead(min(total, start + limit)), min(total, start + 1))


def file_page(conn, file, needle='', exact=False, ruby_only=False, stop=None, offset=0, limit=None, at=None, before=None,
              heading=''):
    source = conn.execute('SELECT * FROM sources WHERE replace(relpath, char(92), ?) = ?', ('/', name_key(file))).fetchone()
    if source is None:
        return None
    # A search on a file page keeps its matching lines only, highlighted
    hits, hl = None, None
    if needle:
        sql, args, hl = _content_where(needle, exact, ruby_only, conn, stop)
        hits = {r[0] for r in conn.execute(f'SELECT rowid FROM custom WHERE ({sql}) AND source_id = ?', (*args, source['id']))}
    sections = [dict(s) for s in conn.execute('SELECT section_no, heading FROM custom_sections WHERE source_id = ? ORDER BY section_no', (source['id'],))]
    # Every line's place first, the lines of the page alone drawn
    order = [(r[0], r[1]) for r in conn.execute(f'SELECT c.id, l.section_no FROM {_content(conn)} c JOIN custom_lines l ON l.rowid = c.id '
                                                f'WHERE c.c0 = ? ORDER BY c.id', (source['id'],))
             if hits is None or r[0] in hits]
    # A .md fold starts at each heading, as the page groups them
    titled = {s['section_no']: s['heading'] for s in sections if s['heading']} if source['kind'] == 'md' else {}

    def fold_firsts(rows):
        return [i for i, (_, sec) in enumerate(rows) if i == 0 or (sec != rows[i - 1][1] and sec in titled)]
    firsts = fold_firsts(order)
    # Whether the page folds, and its one-line folds, are the whole file's
    fold_lines, counts, fold_of = len(order), {}, None
    for i, (_, sec) in enumerate(order):
        if sec in titled and (i == 0 or sec != order[i - 1][1]):
            fold_of = sec
        counts[fold_of] = counts.get(fold_of, 0) + 1
    if heading and source['kind'] in PAGED_KINDS:
        folded, first, fold_of, kept = fold_title_filter(heading), set(firsts), None, []
        for i, row in enumerate(order):
            if i in first:
                fold_of = titled.get(row[1])
            if fold_of and folded in fold_title_filter(fold_of):
                kept.append(row)
        order = kept
        firsts = fold_firsts(order)
    total = len(order)
    start, end = 0, total
    if limit is not None and source['kind'] in PAGED_KINDS:
        place = next((i for i, (rowid, _) in enumerate(order) if rowid == at), None) if at is not None else None
        start, end = _page_bounds(firsts if titled else None, total, offset, limit, place, before)
    page = order[start:end]
    wanted = {rowid for rowid, _ in page}
    rows = []
    if page:
        for r in conn.execute(f'SELECT c.id AS rowid, c.c1 AS file, c.c2 AS line, l.* FROM {_content(conn)} c JOIN custom_lines l ON l.rowid = c.id '
                              f'WHERE c.c0 = ? AND c.id BETWEEN ? AND ? ORDER BY c.id', (source['id'], page[0][0], page[-1][0])):
            if r['rowid'] not in wanted:
                continue
            item = dict(r)
            item['marks'] = json.loads(item['marks'] or '[]')
            draw_row(item, hl)
            rows.append(item)
    if (start, end) != (0, total):
        # A page's own sections: those its lines are in, and the empty ones before its next heading
        lo = page[0][1] if start else None
        hi = order[end][1] if end < total else None
        sections = [s for s in sections if (lo is None or s['section_no'] >= lo)
                    and (hi is None or s['section_no'] < hi or s['section_no'] == page[-1][1])]
    logical = source['relpath']
    if source['kind'] == 'md' and conn.execute('SELECT 1 FROM sqlite_master WHERE name = ?', ('custom_source_meta',)).fetchone():
        meta = conn.execute('SELECT path FROM custom_source_meta WHERE relpath = ?', (source['relpath'],)).fetchone()
        logical = meta[0] if meta else logical
    return {'file': source['relpath'], 'path': logical, 'title': format_custom_title(logical), 'kind': source['kind'], 'lines': rows, 'sections': sections,
            'start': start, 'end': end, 'total': total, 'fold_lines': fold_lines, 'headed': len(titled),
            'all_one': all(n <= 1 for sec, n in counts.items() if sec is not None)}


def reader_place(conn, rowid, file, text):
    source = conn.execute('SELECT id, relpath, category, kind, lines, order_key FROM sources WHERE replace(relpath, char(92), ?) = ?',
                          ('/', name_key(file))).fetchone()
    if source is None:
        return None
    metadata = {}
    if conn.execute('SELECT 1 FROM sqlite_master WHERE name = ?', ('custom_source_meta',)).fetchone():
        metadata = {r['relpath']: dict(r) for r in conn.execute('SELECT * FROM custom_source_meta WHERE relpath = ?', (source['relpath'],))}
    fields = _source_fields(source, metadata)
    row = conn.execute(f'SELECT c0, c2 FROM {_content(conn)} WHERE id = ?', (rowid,)).fetchone()
    found = row is not None and row[0] == source['id'] and (not text or row[1] == text)
    folder = fields['path'].rpartition('/')[0] or source['category']
    alone = lone_file(all_sources(conn)[1], folder)
    if alone is not None and alone['id'] == source['id']:
        folder = folder.rpartition('/')[0]
    return {'file': source['relpath'], 'folder': source['category'], 'path': folder, 'found': found}


def context_page(conn, rowid, file='', query='', before=3, after=3):
    target = conn.execute('SELECT c.c0 AS source_id, c.c1 AS file, l.* FROM custom_lines l JOIN custom_content c ON c.id = l.rowid WHERE l.rowid = ?', (rowid,)).fetchone()
    if target is None or (file and name_key(target['file']) != name_key(file)):
        return {'lines': [], 'focus_index': 0}
    candidates = [dict(r) for r in conn.execute(f'SELECT c.id AS rowid, c.c1 AS file, c.c2 AS line, l.* FROM {_content(conn)} c JOIN custom_lines l ON l.rowid = c.id '
                                                f'WHERE c.c0 = ? AND l.section_no IS ? ORDER BY c.id',
                                                (target['source_id'], target['section_no']))]
    focus = next(i for i, r in enumerate(candidates) if r['rowid'] == rowid)
    start = max(0, focus - before)
    window = candidates[start:focus + after + 1]
    from aobana.search.engine import query_highlight_args
    for item in window:
        item['marks'] = json.loads(item['marks'] or '[]')
        draw_row(item, query_highlight_args(query, 'custom'))
    # Lines spaced as every other media's context: a paragraph gap is the reader's, not a second spacer here
    context = []
    for i, item in enumerate(window):
        heading = f'<div class="custom-heading">{html.escape(item["heading"])}</div>' if i == 0 and item['heading'] else ''
        context.append(heading + item['display_line'])
    return {'context': '<div class="spacer"></div>'.join(context), 'lines': [r['display_line'] for r in window],
            'match': focus - start, 'text': candidates[focus]['line'], 'focus_index': focus - start,
            'rows': window, 'media_type': 'custom'}
