import hashlib
import math
import re

TIMECODE_RE = re.compile(r'\d{2,}(?::\d{2}){2,3}[,.][^\s]+\s*-->\s*\d{2,}(?::\d{2}){2,3}[,.][^\s]+')
ASS_HEADER = re.compile(r'^\s*\[(?:script info|events|v4\+? styles)\]\s*$', re.I | re.M)
HTML = re.compile(r'^\s*(?:<!doctype\s+html|<html\b)', re.I)
NUMERIC_TAG = re.compile(r'\\(fscx|fscy|fsp|fs|frx|fry|frz|p|an)(?![a-z])([^\\})]*)', re.I)
POSITION_TAG = re.compile(r'\\(pos|org|move)\(([^)]*)\)', re.I)
BINARY = re.compile(rb'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
KANA = re.compile('[\u3041-\u3096\u30a1-\u30fa]')
DAMAGED_LINES_MAX = 0.05
KANA_MIN = 0.01


class SubtitleInputError(ValueError):
    def __init__(self, reason, message):
        self.reason = reason
        super().__init__(message)


def number(value):
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError('non-finite subtitle number')
    return parsed


def sanitize_ass(text, warnings):
    def numeric(m):
        try:
            number(m[2])
            return m[0]
        except ValueError:
            warnings.add('Ignored malformed ASS override: ' + m[0])
            return ''

    def position(m):
        try:
            values = m[2].split(',')
            allowed = (4, 6) if m[1].lower() == 'move' else (2,)
            if len(values) not in allowed:
                raise ValueError('coordinate count')
            for value in values:
                number(value)
            return m[0]
        except ValueError:
            warnings.add('Ignored malformed ASS override: ' + m[0])
            return ''

    def block(m):
        return POSITION_TAG.sub(position, NUMERIC_TAG.sub(numeric, m[0]))

    return re.sub(r'\{[^}]*\}', block, text)


def salvage(raw):
    raw = raw.removeprefix(b'\xef\xbb\xbf')
    lines = re.findall(rb'[^\n]*\n|[^\n]+$', raw) or [raw]
    best = None
    for encoding in ('utf-8', 'cp932'):
        broken = 0
        for line in lines:
            try:
                line.decode(encoding)
            except UnicodeDecodeError:
                broken += 1
        if best is None or broken < best[1]:
            best = (encoding, broken)
    encoding, broken = best
    kept = []
    for line in lines:
        if not BINARY.search(line):
            kept.append(line.decode(encoding, errors='replace'))
    text = ''.join(kept)
    if broken > len(lines) * DAMAGED_LINES_MAX or len(KANA.findall(text)) < len(text) * KANA_MIN:
        return None
    return text, encoding + '-damaged', broken


def decode_bytes(raw):
    if raw.startswith((b'\xff\xfe', b'\xfe\xff')):
        try:
            return raw.decode('utf-16'), 'utf-16'
        except UnicodeDecodeError as error:
            raise SubtitleInputError('unreadable', 'Invalid UTF-16 subtitle') from error
    if b'\x1b$' in raw or b'\x1b(' in raw:
        try:
            return raw.decode('iso2022_jp'), 'iso2022_jp'
        except UnicodeDecodeError:
            pass
    for encoding in ('utf-8-sig', 'cp932', 'euc_jp'):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            pass
    kept = salvage(raw)
    if kept is None:
        raise SubtitleInputError('unreadable', 'Cannot decode as UTF-8, CP932, EUC-JP or ISO-2022-JP')
    return kept[0], kept[1]


def read(path):
    with open(path, 'rb') as handle:
        raw = handle.read()
    text, encoding = decode_bytes(raw)
    warnings = set()
    if encoding.endswith('-damaged'):
        broken = sum('\ufffd' in line for line in text.splitlines())
        warnings.add(f'Broken bytes on {broken} lines, shown as \ufffd')
    if HTML.search(text):
        raise SubtitleInputError('html_error', 'HTML document instead of subtitles')
    if ASS_HEADER.search(text):
        actual = 'ass'
    elif TIMECODE_RE.search(text):
        actual = 'srt'
    elif not text.strip():
        actual = 'empty'
    else:
        raise SubtitleInputError('unsupported', 'Unrecognized subtitle format')
    if actual == 'ass':
        text = sanitize_ass(text, warnings)
    return {'text': text, 'format': actual, 'encoding': encoding,
            'dot_timecodes': actual == 'srt' and bool(re.search(r'\d{2,}(?::\d{2}){2,3}\.\d+\s*-->', text)),
            'warnings': sorted(warnings), 'sha': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
