import html
import re
import unicodedata

LINK = re.compile(r'(!?)\[((?:\\.|[^\]\\])*)\]\(\s*(<[^>]*>|(?:\\.|[^()\\]|\([^()]*\))*)\s*\)')
REFERENCE = re.compile(r'^ {0,3}\[([^]]+)\]:\s*(\S+)(?:\s+.*)?$')
PREFIX = re.compile(r'^\s*(?:>\s*)*(?:(?:[-+*]|\d+[.)])\s+)?(?:\[[ xX]\]\s+)?')
HEADING = re.compile(r'^ {0,3}(#{1,6})(?:[ \t]+|$)(.*?)(?:[ \t]+#+[ \t]*)?$')
URL = re.compile(r'<?(?:https?://|mailto:)[^\s<>]+>?', re.I)
LABELS = ('追加', 'リンク', '公式サイト')
RULE = re.compile(r'^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$')
TABLE_DELIMITER = re.compile(r'^\s*\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*\|?\s*$')
WIKI = re.compile(r'(!?)\[\[([^\[\]|#]*)(?:#[^\[\]|]*)?(?:\|([^\[\]]*))?\]\]')
FOOTNOTE = re.compile(r'^ {0,3}\[\^[^\]]+\]:[ \t]?(.*)$')
FOOTNOTE_REF = re.compile(r'\[\^[^\]\s]+\]')
COMMENT = re.compile(r'<!--.*?-->|%%.*?%%', re.S)


def _blank_comments(text):
    return COMMENT.sub(lambda m: '\n' * m[0].count('\n'), text)


def _front_matter(lines):
    if not lines or lines[0].strip() != '---':
        return 0
    for index in range(1, len(lines)):
        if lines[index].strip() in ('---', '...'):
            return index + 1
    return 0


def _table_start(lines, index):
    return ('|' in lines[index] and index + 1 < len(lines) and '|' in lines[index + 1]
            and TABLE_DELIMITER.match(lines[index + 1]) is not None)


def _cells(line):
    value = line.strip()
    value = value[1:] if value.startswith('|') else value
    value = value[:-1] if value.endswith('|') and not value.endswith(chr(92) + '|') else value
    cells = [c.strip().replace(chr(92) + '|', '|') for c in re.split(r'(?<!\\)\|', value)]
    return '　'.join(c for c in cells if c)


def _wiki(match):
    if match[1]:
        return ''
    return (match[3] if match[3] is not None else match[2].rsplit('/', 1)[-1]).strip()


class Link:
    def __init__(self, start, stop, image, label, target, raw):
        self.start, self.stop = start, stop
        self.values = (raw, image, label, target)

    def __getitem__(self, index):
        return self.values[index]

    def span(self):
        return self.start, self.stop


def scan_links(value):
    index = 0
    while index < len(value):
        start = index
        image = value[index:index + 2] == '!['
        if value[index] != '[' and not image:
            index += 2 if value[index] == chr(92) else 1
            continue
        left = index + int(image)
        cursor, depth = left + 1, 1
        while cursor < len(value) and depth:
            char = value[cursor]
            if char == chr(92):
                cursor += 2
                continue
            depth += (char == '[') - (char == ']')
            cursor += 1
        if depth or value[cursor:cursor + 1] != '(':
            index = left + 1
            continue
        label = value[left + 1:cursor - 1]
        target_start = cursor + 1
        cursor, depth = target_start, 1
        while cursor < len(value) and depth:
            char = value[cursor]
            if char == chr(92):
                cursor += 2
                continue
            depth += (char == '(') - (char == ')')
            cursor += 1
        if depth:
            index = left + 1
            continue
        yield Link(start, cursor, '!' if image else '', label, value[target_start:cursor - 1], value[start:cursor])
        index = cursor


def replace_links(value, replace):
    for match in reversed(list(scan_links(value))):
        value = value[:match.start] + replace(match) + value[match.stop:]
    return value


def _label(value):
    kept = []

    def keep(match):
        kept.append(match[1])
        return '\x00' + str(len(kept) - 1) + '\x01'
    value = re.sub(r'\\([!"#$%&\'()*+,\-./:;<=>?@\[\]\\^_`{|}~])', keep, value)
    value = WIKI.sub(_wiki, FOOTNOTE_REF.sub('', value))
    value = re.sub(r'<(rt|rp)\b[^>]*>.*?</\1\s*>', '', value, flags=re.I)
    value = re.sub(r'<[^>]+>', '', value)
    value = re.sub(r'(`+)(.*?)\1', r'\2', value)
    for pattern in (r'\*\*(.+?)\*\*', r'__(.+?)__', r'~~(.+?)~~', r'==(.+?)==', r'(?<![A-Za-z0-9*])\*(?!\s)(.+?)(?<!\s)\*(?![A-Za-z0-9])', r'(?<![A-Za-z0-9_])_(?!\s)(.+?)(?<!\s)_(?![A-Za-z0-9])'):
        value = re.sub(pattern, r'\1', value)
    return html.unescape(re.sub('\x00(\\d+)\x01', lambda m: kept[int(m[1])], value))


def _target(value):
    value = value.strip()
    if value.startswith('<'):
        return value[1:value.find('>')]
    return re.split(r'\s+[\'"]', value, maxsplit=1)[0].replace(r'\(', '(').replace(r'\)', ')')


def links(text):
    fenced = None
    text = _blank_comments(text.lstrip('﻿'))
    lines = text.splitlines()
    lines = lines[_front_matter(lines):]
    references = {m[1].casefold(): m[2] for line in lines if (m := REFERENCE.match(line)) and not FOOTNOTE.match(line)}
    for line in lines:
        fence = re.match(r'^\s*(`{3,}|~{3,})', line)
        if fence:
            if fenced is None:
                fenced = fence[1][0]
            elif fence[1][0] == fenced:
                fenced = None
            continue
        if fenced or REFERENCE.match(line):
            continue
        value = PREFIX.sub('', line).strip()
        for match in scan_links(value):
            if not match[1]:
                yield _label(match[2]), _target(match[3]), match.span() == (0, len(value))
        for match in re.finditer(r'(?<!!)\[([^]]+)\]\[([^]]*)\]', value):
            target = references.get((match[2] or match[1]).casefold())
            if target:
                yield _label(match[1]), target, match.span() == (0, len(value))


def containers(lines, navigation):
    hidden, headings = set(), {}
    for index in range(len(lines) - 1, -1, -1):
        match = re.match(r'^(\s*)(?:[-+*]|\d+[.)])\s+(.+)$', lines[index])
        if not match or RULE.match(lines[index]):
            continue
        indent = len(match[1].expandtabs(4))
        children = []
        for child in range(index + 1, len(lines)):
            value = lines[child]
            if not value.strip():
                continue
            if len(value) - len(value.lstrip()) <= indent:
                break
            children.append(child)
        if not children:
            if match[2].strip() in LABELS:
                hidden.add(index)
            continue
        useful = False
        for child in children:
            value = lines[child].strip()
            if child in hidden or URL.fullmatch(value):
                continue
            matches = list(scan_links(value))
            remainder = replace_links(value, lambda m: '' if m[1] or _target(m[3]) in navigation
                                      or re.match(r'^(?:https?://|mailto:)', _target(m[3]), re.I) else m[0])
            if matches and not remainder.strip():
                continue
            useful = True
        if not useful or match[2].strip() in LABELS:
            hidden.add(index)
    return hidden, headings


def parse(text, title, navigation=()):
    source = text.lstrip('\ufeff').splitlines()
    original = _blank_comments(text.lstrip('\ufeff')).splitlines()
    erased = {i for i, (a, b) in enumerate(zip(source, original)) if a.strip() and not b.strip()} if len(source) == len(original) else set()
    start = _front_matter(original)
    original = [''] * start + original[start:]
    references = {m[1].casefold(): m[2] for line in original if (m := REFERENCE.match(line)) and not FOOTNOTE.match(line)}
    hidden_containers, list_headings = containers(original, navigation)
    rows, sections = [], [(0, None, 0)]
    section, heading, gap, first_heading, fenced = 0, None, 0, True, None
    skip_next, table = False, False
    for index, raw in enumerate(original):
        if skip_next:
            skip_next = False
            continue
        if index in hidden_containers or index in erased:
            continue
        if table and (not raw.strip() or '|' not in raw):
            table = False
        if not raw.strip():
            gap = 1
            continue
        fence = re.match(r'^ {0,3}(`{3,}|~{3,})', raw)
        if fence and fenced is None:
            fenced = (fence[1][0], len(fence[1]))
            continue
        if fence and fence[1][0] == fenced[0] and len(fence[1]) >= fenced[1] and not raw.strip()[len(fence[1]):].strip():
            fenced = None
            continue
        if fenced:
            line = raw
        else:
            if re.fullmatch(r'\s*(?:>\s*)+', raw):
                gap = 1
                continue
            if table or _table_start(original, index):
                skip_next = not table
                table = True
                raw = _cells(raw)
                if not raw:
                    continue
            elif RULE.match(raw):
                gap = 1
                continue
            footnote = FOOTNOTE.match(raw)
            if footnote:
                raw = footnote[1]
            elif REFERENCE.match(raw):
                continue
            if not raw.strip():
                continue
            match = None if table else HEADING.match(raw)
            setext = not table and index + 1 < len(original) and re.fullmatch(r' {0,3}(?:=+|-+)[ \t]*', original[index + 1])
            if match or setext or index in list_headings:
                label = list_headings.get(index, _label(replace_links(match[2] if match else raw.strip(), lambda m: '' if m[1] else m[2])))
                if setext and not match:
                    skip_next = True
                title_shape = lambda s: re.sub(r'[\s.<>:"/\\|?*]', '', unicodedata.normalize('NFKC', s))
                if first_heading and title_shape(label) == title_shape(title):
                    first_heading = False
                    continue
                first_heading = False
                section += 1
                heading = label
                sections.append((section, heading, 0))
                gap = 0
                continue
            prefix = None if table else PREFIX.match(raw)
            value = raw[prefix.end():] if prefix and prefix[0].strip() else raw
            if prefix and prefix[0].strip() and (quoted := HEADING.match(value)):
                value = quoted[2]
            if WIKI.search(value) and not WIKI.sub('', value).strip():
                continue
            found = list(scan_links(value.strip()))
            if any(not m[1] and _target(m[3]) in navigation for m in found):
                value = replace_links(value, lambda m: '' if m[1] or _target(m[3]) in navigation else _label(m[2]))
            elif len(found) == 1 and found[0].span() == (0, len(value.strip())):
                if found[0][1] or re.match(r'^(?:https?://|mailto:)', _target(found[0][3]), re.I):
                    continue
            value = replace_links(value, lambda m: '' if m[1] else _label(m[2]))
            value = re.sub(r'(!?)\[([^]]+)\]\[([^]]*)\]',
                           lambda m: '' if m[1] else m[2] if (m[3] or m[2]).casefold() in references else m[0], value)
            value = re.sub(r'(?<![\]!\\])\[([^\[\]]+)\](?![\[(:])',
                           lambda m: m[1] if m[1].casefold() in references else m[0], value)
            value = re.sub(' ?' + URL.pattern, '', value, flags=re.I)
            line = _label(re.sub(r'(?<!\\)\\$', '', value))
            if not line.strip():
                continue
        rows.append((line, gap, section, heading))
        gap = 0
    return rows, sections
