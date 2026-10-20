import functools
import re
from html import unescape
from html.parser import HTMLParser

from aobana import paths
from aobana.utils import (RUBY_RE, NATIVE_TAG_RE, NATIVE_ENCODED_TAG_RE as _ENCODED_TAG_RE,
                          NATIVE_RUBY_RE as _RUBY_RE, NATIVE_RB_RE as _RB_RE, NATIVE_PAIR_RE as _PAIR_RE,
                          NATIVE_RB_LABEL_RE, NATIVE_RB_TAIL_RE as _KANA_TAIL_RE,
                          SUBS_STR_REPLACEMENTS, convert_hw_katakana, katakana_to_hiragana, ruby_table)

_STYLE_RE = re.compile(r'</?(?:i|b|u|s|font)\b[^>]*>', re.I)
_SPACE_RE = re.compile(r'[ 　]+')


def has_native_ruby(text):
    return bool(text and (NATIVE_TAG_RE.search(text) or _ENCODED_TAG_RE.search(text)))


def indexed_native_sources(conn, tick=None):
    out = set()
    for n, (rowid, source, line) in enumerate(conn.execute(
            'SELECT rowid,source_id,line FROM subtitles WHERE subtitles MATCH ?',
            ('rb OR rt OR ruby OR rp',))):
        if tick and n % 1000 == 0:
            tick(rowid)
        if has_native_ruby(line):
            out.add(source)
    return out


def _tags(text):
    text = _ENCODED_TAG_RE.sub(lambda m: unescape(m.group()), text)
    return NATIVE_TAG_RE.sub(lambda m: m.group().replace('＜', '<').replace('＞', '>'), text)


def _plain(text):
    return unescape(_STYLE_RE.sub('', text))


def _key(text):
    return katakana_to_hiragana(convert_hw_katakana(_SPACE_RE.sub('', text)))


def _bounded(base, reading, notes):
    base, reading = base.strip(), _SPACE_RE.sub('', reading.strip())
    if not reading:
        return base
    value = f'｜{base}({reading})'
    if RUBY_RE.fullmatch(value):
        return value
    value = f'｜｜{base}({reading})'
    if RUBY_RE.fullmatch(value):
        return value
    if notes is not None:
        notes.append(('unsupported_span', base, reading))
    return f'{base}（{reading}）'


class _RubyBody(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.base, self.reading, self.fallback = [], [], []
        self.in_rt = self.in_rp = False
        self.parts = []
        self.invalid = False

    def flush(self):
        if self.reading:
            self.parts.append((''.join(self.base), ''.join(self.reading)))
            self.base, self.reading, self.fallback = [], [], []

    def handle_starttag(self, tag, attrs):
        if tag == 'rt':
            if self.in_rt:
                self.invalid = True
            self.flush()
            self.in_rt = True
        elif tag == 'rp':
            self.in_rp = True
        elif tag == 'ruby':
            self.invalid = True
        elif tag not in ('rb', 'i', 'b', 'u', 's', 'font'):
            self.handle_data(self.get_starttag_text())

    def handle_endtag(self, tag):
        if tag == 'rt':
            self.in_rt = False
        elif tag == 'rp':
            self.in_rp = False
        elif tag not in ('rb', 'i', 'b', 'u', 's', 'font'):
            self.handle_data(f'</{tag}>')

    def handle_data(self, data):
        if self.in_rp:
            self.fallback.append(data)
        elif self.in_rt:
            self.reading.append(data)
        else:
            if self.reading:
                self.flush()
            self.base.append(data)

    def result(self, notes):
        self.flush()
        if self.invalid or any(not base for base, _ in self.parts):
            return None
        if not self.parts:
            return None
        return ''.join(_bounded(base, reading, notes) for base, reading in self.parts) + ''.join(self.base)


def source_readings(text):
    if not has_native_ruby(text):
        return {}
    text = _tags(text)
    found = {}
    for match in _RUBY_RE.finditer(text):
        body = _RubyBody()
        body.feed(match.group(1))
        body.close()
        if body.result(None) is not None:
            for base, reading in body.parts:
                found.setdefault(base.strip(), set()).add(_key(reading))
    for match in _PAIR_RE.finditer(text):
        found.setdefault(_plain(match.group(1)).strip(), set()).add(_key(_plain(match.group(2))))
    for match in NATIVE_RB_LABEL_RE.finditer(text):
        found.setdefault(_plain(match.group(1)).strip(), set()).add(_key(match.group(2)))
    return found


def dictionary_prefixes(base, tail, tokenize):
    result = set()
    tokens = list(tokenize(base))
    reading = _key(''.join(t.reading_form() for t in tokens))
    if reading and _key(tail).startswith(reading):
        result.add(reading)
    isolated = _key(''.join(''.join(t.reading_form() for t in tokenize(word.surface())) for word in tokens))
    if isolated and _key(tail).startswith(isolated):
        result.add(isolated)
    for cut in range(1, min(len(tail), 24)):
        prefix = _key(tail[:cut])
        if not prefix:
            continue
        words = list(tokenize(base + tail[cut:]))
        if not words:
            continue
        word = words[0]
        surface = word.surface()
        if word.is_oov() or not surface.startswith(base) or len(surface) <= len(base):
            continue
        suffix = _key(surface[len(base):])
        read = _key(word.reading_form())
        if suffix and read.endswith(suffix) and read[:-len(suffix)] == prefix:
            lemma = word.dictionary_form()
            normalized = word.normalized_form()
            if normalized.startswith(base) and lemma != normalized:
                continue
            if not lemma.startswith(base):
                continue
            okuri = _key(lemma[len(base):])
            lemma_read = _key(''.join(t.reading_form() for t in tokenize(lemma)))
            if okuri and lemma_read.endswith(okuri) and lemma_read[:-len(okuri)] == prefix:
                result.add(prefix)
    return result


@functools.lru_cache(maxsize=1)
def rb_readings():
    out = {}
    for _, (base, tail, reading) in ruby_table(paths.RUBY_TABLES_PATH, 'rb_readings'):
        out.setdefault(base, {})[tail] = '' if reading == '-' else _key(reading)
    return out


def _stored(text):
    for src, dst in SUBS_STR_REPLACEMENTS:
        text = text.replace(src, dst)
    return text


def table_reading(table, base, tail):
    rows = table.get(base) or table.get(_stored(base))
    tail = tail.rstrip(' 　')
    if not rows or not tail:
        return None
    if tail in rows:
        return rows[tail]
    compact = _key(tail)
    fits = {r for t, r in rows.items() if (t.startswith(tail) or tail.startswith(t))
            and (not r or compact.startswith(r))}
    return fits.pop() if len(fits) == 1 else None


RB_TYPOS = (('もう<rb>捕</rb>つかままって', 'もう<rb>捕</rb>つかまって'),)


def normalize_subtitle_ruby(text, lookup=None, aliases=None, notes=None, prefixes=None, frozen=True):
    if not has_native_ruby(text):
        return text
    for typo, fixed in RB_TYPOS:
        text = text.replace(typo, fixed)
    if frozen is True:
        frozen = rb_readings()
    text = _tags(text)
    evidence = source_readings(text)
    if aliases:
        for base, values in aliases.items():
            evidence.setdefault(base, set()).update(values)

    def complete(match):
        body = _RubyBody()
        body.feed(match.group(1))
        body.close()
        result = body.result(notes)
        if result is None:
            if notes is not None:
                notes.append(('malformed_ruby', match.group(), ''))
            return match.group()
        return result

    text = _RUBY_RE.sub(complete, text)
    text = _PAIR_RE.sub(lambda m: _bounded(_plain(m.group(1)), _plain(m.group(2)), notes), text)
    result, end = [], 0
    for match in _RB_RE.finditer(text):
        if match.start() < end:
            continue
        result.append(text[end:match.start()])
        written = _plain(match.group(1))
        base = written.strip()
        tail_match = _KANA_TAIL_RE.match(text, match.end())
        tail = tail_match.group() if tail_match else ''
        compact = _key(tail)
        choices = [r for r in evidence.get(base, ()) if r and compact.startswith(r)]
        if not choices and lookup:
            candidate = _key(lookup(base) or '')
            if candidate and compact.startswith(candidate):
                choices = [candidate]
        if not choices and prefixes and tail:
            choices = list(prefixes(base, tail))
        ruled = table_reading(frozen, base, tail) if frozen and len(set(choices)) != 1 else None
        if ruled:
            choices = [ruled]
        if len(set(choices)) == 1:
            reading = choices[0]
            consumed = 0
            while consumed < len(tail) and len(_key(tail[:consumed])) < len(reading):
                consumed += 1
            result.append(_bounded(base, tail[:consumed], notes))
            end = match.end() + consumed
        else:
            result.append(written)
            end = match.end()
            if notes is not None:
                notes.append(('left_rb' if ruled == '' else 'unbounded_rb', base, tail))
    result.append(text[end:])
    text = ''.join(result)
    if NATIVE_TAG_RE.search(text):
        if notes is not None:
            notes.append(('orphan_markup', text, ''))
        text = NATIVE_TAG_RE.sub('', text)
    return text
