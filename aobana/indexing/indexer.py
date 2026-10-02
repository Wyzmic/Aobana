import os
import re
import sqlite3
import hashlib
import time
from sudachipy import tokenizer, dictionary
from datetime import datetime

from aobana import paths
BASE_DIR = paths.BASE_DIR
ROOT_DIR = paths.subs_dir()
DB_PATH = paths.subs_db()

_TOKENIZER = None
mode = tokenizer.Tokenizer.SplitMode.A
from aobana.utils import SUDACHI_MAX_BYTES


def get_tokenizer():
    global _TOKENIZER
    if _TOKENIZER is None:
        _TOKENIZER = dictionary.Dictionary(dict="core").create()
    return _TOKENIZER

from aobana.utils import (
    KANA_RE, KANJI_CHARS, KANJI_PATTERN,
    ALPHA_CHARS, ALPHA_PATTERN, RUBY_BASE_RE, RUBY_RE,
    norm_relpath, INDEX_FORMAT, is_outdated, ensure_format_column, compact_if_worth, stop_requested, sub_relpath, write_tokenizer_meta, ruby_index_extras, parallel_map,
    strip_chinese_chunks, is_chinese_text, filtered_names, held_removals, ALLOW_REMOVAL_FLAG,
    start_output, emit, say,
    ensure_line_lengths, has_line_lengths, write_line_lengths, drop_orphan_lengths,
    ensure_ruby_lexicon, has_ruby_lexicon, write_ruby_lexicon, drop_ruby_lexicon,
)

HTML_TAG_RE = re.compile(r'</?(?:i|b|u|s|font)[^>]*>', re.IGNORECASE)
BIDI_MARK_RE = re.compile(r'&(?:lrm|rlm);|[‎‏]')
HTML_ENTITIES = (('&lt;', '<'), ('&gt;', '>'), ('&amp;', '&'))
SQUARE_BRACKETS_RE = re.compile(r'\[[^\[\]]*\]')
TIMECODE_RE = re.compile(r'\d{2,}(?::\d{2}){2,3},[^ ]+\s*-->\s*\d{2,}(?::\d{2}){2,3},[^ ]+')

SIMP_CHINESE_RE = re.compile(r'[这吗呢吧啦么谁们从说话样觉视频听欢买卖错让帮确对爱关门图运无计场动时发现经还进长您她啥够钟钱馆帅步舔护见恼变樱联语弃寻伫战龙击两亚丽丝态类优恶办统层头谈论戏极气为复杂转带质压雾辈适厌连隐谓认费愿拥应废东获谢闪诚责过军预给险刚脑测实迟钝虽剑临圣请哪呗尔谅创兰鲁伙开读网电车专乐业产农风飞杀药权树桥决减满卫织续损]')
PROMO_URL_RE = re.compile(r'(?:https?://|www\.|(?:\.com|\.cc|\.net|\.org)(?:\b|/))', re.IGNORECASE)
JAPANESE_CHARS_RE = re.compile(r'[\u3040-\u30FF\u4E00-\u9FFF\u3400-\u4DBF\uF900-\uFAFF\U00020000-\U000323AF\U0002F800-\U0002FA1F]')

_EXCLUDED_LOG = []
_WAKATI_LOG = []
_NOTES = []

from aobana.utils import convert_hw_katakana, SUBS_STR_REPLACEMENTS, katakana_to_hiragana, ruby_table

_RE_REPLACEMENTS = [
    (re.compile(r'＠ルビ.*?［(.+?)[｜|](.+?)］＠'), r'\1(\2)'),
    (re.compile(r'(?<![―—])[―—](?![―—])'), '――'),
    (re.compile(r'[・]{3,}'), '…'),
    (re.compile(r'~~~'), '～～～'),
    (re.compile(r'~~'),  '～～'),
    (re.compile(r'~'),   '～'),
]

def _postprocess_sentence(text: str) -> str:
    text = convert_hw_katakana(text)
    for src, dst in SUBS_STR_REPLACEMENTS:
        text = text.replace(src, dst)
    for pattern, dst in _RE_REPLACEMENTS:
        text = pattern.sub(dst, text)
    return close_unclosed_ruby(text)

UNCLOSED_RUBY_RE = re.compile(r'ルビ[上下右左]?［[^［］｜\n]*｜')

def _load_unclosed_ruby():
    rulings = []
    for _, (tag, base, reading) in ruby_table(paths.RUBY_TABLES_PATH, 'unclosed_ruby'):
        ruby = f'｜{base}({reading})'
        if not RUBY_RE.fullmatch(ruby):
            ruby = f'{base}（{reading}）'
        rulings.append((tag, ruby))
    return sorted(rulings, key=lambda r: -len(r[0]))

_UNCLOSED_RUBY = _load_unclosed_ruby()

def close_unclosed_ruby(text: str) -> str:
    if 'ルビ' not in text:
        return text
    for tag, ruby in _UNCLOSED_RUBY:
        text = text.replace(tag, ruby)
    return text

def clean_ruby_match(m) -> str:
    furi = m.group(3)
    return m.group(0)[:-len(furi) - 2] + '(' + re.sub(r'[ 　]', '', furi) + ')'

def is_paren_only_line(line):
    s = line.strip()
    if re.fullmatch(r'（[^）]+）', s): return True
    if re.fullmatch(r'\([^)]*\)', s): return True
    return False

def bar_ruby_plain(text):
    return RUBY_RE.sub(lambda m: m.group(1) if m.group(1) else m.group(0), text)


def smart_join(lines):
    if not lines: return ''
    result = [lines[0]]
    for prev, curr in zip(lines, lines[1:]):
        last  = prev[-1] if prev else ''
        tail = [m for m in RUBY_RE.finditer(prev) if m.end() == len(prev) and m.group(1)]
        if tail:
            last = tail[-1].group(1)[-1]
        first = curr.lstrip('｜')[:1]
        if (re.match(r'[\u3040-\u30FF\u4E00-\u9FFF\w]', last)
                and re.match(r'[\u3040-\u30FF\u4E00-\u9FFF\w]', first)
                and last  not in '・―…、。！？）」'
                and first not in '・―…、。！？（「'):
            result.append(' ' + curr)
        else:
            result.append(curr)
    return ''.join(result)

def clean_line(line, relpath):
    folder = re.split(r"[\\/]", relpath)[0]
    line = BIDI_MARK_RE.sub('', line)
    for entity, char in HTML_ENTITIES:
        line = line.replace(entity, char)
    line, chinese = strip_chinese_chunks(line)
    for chunk in chinese:
        _EXCLUDED_LOG.append((folder, "CHINESE_PART", chunk))
    if SIMP_CHINESE_RE.search(line) or is_chinese_text(line):
        _EXCLUDED_LOG.append((folder, "CHINESE", line))
        return ""
    if PROMO_URL_RE.search(line) and not JAPANESE_CHARS_RE.search(line):
        _EXCLUDED_LOG.append((folder, "URL_PROMO", line))
        return ""
        
    line = HTML_TAG_RE.sub('', line)
    line = SQUARE_BRACKETS_RE.sub('', line)
    line = re.sub(r'^-\s*(?=[（\(])', '', line)
    result = []
    skip = 0
    for char in line:
        if char == '{': skip += 1
        elif char == '}':
            if skip > 0: skip -= 1
        elif skip == 0: result.append(char)
    cleaned_text = _postprocess_sentence(''.join(result).strip())
    if UNCLOSED_RUBY_RE.search(cleaned_text):
        _NOTES.append(f"UNCLOSED_RUBY {relpath}: {cleaned_text}")
    return cleaned_text

def is_music_only_line(line):
    s = re.sub(r'[\u202A-\u202E\u200B-\u200F\u2066-\u2069  ]', '', line)
    return bool(re.fullmatch(r'[♪♬〜～]+', s))

def is_line_number(line): return line.strip().isdigit()
def is_timecode(line): return bool(TIMECODE_RE.fullmatch(line.strip())) or bool(TIMECODE_RE.search(line))

def is_punctuation_line(line):
    s = line.strip()
    if bool(re.fullmatch(r'[-–—><\s,]+', s)): return True
    if bool(re.fullmatch(r'[-–—]+[A-Za-z\s]+[-–—]+', s)): return True
    return False

def _merge_group(group_texts):
    merged_lines = []
    paren_buffer = ""
    for text in group_texts:
        if is_paren_only_line(text):
            paren_buffer += text
        else:
            if paren_buffer:
                merged_lines.append(paren_buffer + text)
                paren_buffer = ""
            else:
                merged_lines.append(text)
    if paren_buffer:
        merged_lines.append(paren_buffer)
    return smart_join(merged_lines)

def assess_and_clean_wakati(lines, relpath=""):
    total_spaced = 0
    chunk_ratio_sum = 0.0

    for line in lines:
        spaces = line.count(' ')
        if spaces == 0:
            continue
        chars = len(line) - spaces
        total_spaced += 1
        chunk_ratio_sum += chars / (spaces + 1)

    if total_spaced >= 20:
        mean_chunk_chars = chunk_ratio_sum / total_spaced
        if mean_chunk_chars <= 3.0:
            cleaned_lines = [line.replace(' ', '') for line in lines]
            if relpath:
                _WAKATI_LOG.append((relpath, len(lines), mean_chunk_chars))
            return cleaned_lines, True

    return lines, False

def extract_lines_grouped_by_timecode(srt_content, relpath):
    lines = []
    group_texts = []
    current_timecode = None

    def flush():
        if current_timecode is not None and group_texts:
            joined = _merge_group(group_texts)
            if not is_music_only_line(joined):
                if lines and bar_ruby_plain(lines[-1]) == bar_ruby_plain(joined):
                    if len(joined) > len(lines[-1]):
                        lines[-1] = joined
                else:
                    lines.append(joined)

    for raw_line in srt_content.splitlines():
        line = raw_line.strip()
        if not line: continue
        if is_line_number(line): continue
        if is_timecode(line):
            flush()
            current_timecode = line
            group_texts = []
            continue
        
        if is_punctuation_line(line):
            folder = re.split(r"[\\/]", relpath)[0]
            _EXCLUDED_LOG.append((folder, "SYMBOL/JUNK", line))
            continue
            
        cleaned = clean_line(line, relpath)
        if cleaned: group_texts.append(cleaned)

    flush()
    cleaned_lines, _ = assess_and_clean_wakati(lines, relpath)
    return cleaned_lines

SUB_EXTS = ('.srt', '.ass', '.ssa')
ASS_TAG_RE = re.compile(r'\{[^}]*\}')
ASS_GAIJI_RE = re.compile(r'\[外:[0-9A-Fa-f]+\]')
ASS_TIME_RE = re.compile(r'(\d+):(\d{2}):(\d{2})[.:](\d{1,3})')
ASS_RUBY_STYLE_RE = re.compile(r'rubi|ruby|furigana', re.IGNORECASE)
ASS_CREDIT_STYLE_RE = re.compile(r'staff|credit|製作|制作|注釋|注释|^cmt', re.IGNORECASE)
KANA_RE_ASS = re.compile(r'[ぁ-ゖァ-ヺー]')
KANA_ONLY_RE = re.compile(r'[ぁ-ゖァ-ヺー\s　]+')
ASS_KANA_SHARE = 0.2


def read_subtitle_text(path):
    if not path.lower().endswith(('.ass', '.ssa')):
        with open(path, encoding='utf-8', errors='ignore') as f:
            return f.read()
    with open(path, 'rb') as f:
        raw = f.read()
    if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
        return raw.decode('utf-16', errors='ignore')
    for enc in ('utf-8-sig', 'cp932'):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode('utf-8', errors='ignore')


def _ass_time(s):
    m = ASS_TIME_RE.match(s.strip())
    if not m:
        return None
    h, mi, se, frac = m.groups()
    ms = int(frac.ljust(3, '0')[:3])
    return ((int(h) * 60 + int(mi)) * 60 + int(se)) * 1000 + ms


def _srt_time(ms):
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _ass_last_tag(tags, name):
    found = re.findall(r'\\' + name + r'(-?[\d.]+)', tags)
    return float(found[-1]) if found else None


def parse_ass_events(content, stats=None):
    section, fields, style_size = None, None, {}
    style_fields = None
    events = []
    for line in content.splitlines():
        s = line.strip()
        if s.startswith('[') and s.endswith(']'):
            section = s.lower()
            continue
        if ':' not in s:
            continue
        key, _, value = s.partition(':')
        key = key.strip().lower()
        if section in ('[v4+ styles]', '[v4 styles]'):
            if key == 'format':
                style_fields = [f.strip().lower() for f in value.split(',')]
            elif key == 'style' and style_fields:
                vals = [v.strip() for v in value.split(',')]
                row = dict(zip(style_fields, vals))
                try:
                    style_size[row.get('name', '').lower()] = float(row.get('fontsize', ''))
                except ValueError:
                    pass
        elif section == '[events]':
            if key == 'format':
                fields = [f.strip().lower() for f in value.split(',')]
            elif key == 'dialogue' and fields:
                parts = value.split(',', len(fields) - 1)
                if len(parts) < len(fields):
                    continue
                ev = dict(zip(fields, parts))
                start, end = _ass_time(ev.get('start', '')), _ass_time(ev.get('end', ''))
                if start is None or end is None:
                    continue
                raw = ev.get('text', '')
                tags = ''.join(ASS_TAG_RE.findall(raw))
                text = ASS_TAG_RE.sub('', raw)
                text = text.replace('\\N', '\n').replace('\\n', '\n').replace('\\h', ' ')
                text = ASS_GAIJI_RE.sub('', text)
                text = '\n'.join(t.strip() for t in text.split('\n') if t.strip())
                events.append({'start': start, 'end': end, 'raw': raw, 'tags': tags,
                               'style': ev.get('style', '').strip(), 'text': text, 'drop': None})

    cjk, kana = {}, {}
    for ev in events:
        st = ev['style'].lower()
        if JAPANESE_CHARS_RE.search(ev['text']):
            cjk[st] = cjk.get(st, 0) + 1
            if KANA_RE_ASS.search(ev['text']):
                kana[st] = kana.get(st, 0) + 1
    japanese = {st for st, n in cjk.items() if kana.get(st, 0) / n >= ASS_KANA_SHARE}

    for ev in events:
        st, text, tags = ev['style'].lower(), ev['text'], ev['tags']
        p = _ass_last_tag(tags, 'p')
        fscy = _ass_last_tag(tags, 'fscy')
        fs = _ass_last_tag(tags, 'fs')
        base = style_size.get(st) or style_size.get('*' + st) or style_size.get('default')
        small = (fscy is not None and fscy < 100) or (fs is not None and base and fs < base * 0.75)
        if p:
            ev['drop'] = 'drawing'
        elif not text:
            ev['drop'] = 'empty'
        elif ASS_RUBY_STYLE_RE.search(st):
            ev['drop'] = 'ruby-style'
        elif small and KANA_ONLY_RE.fullmatch(text):
            ev['drop'] = 'ruby-small'
        elif ASS_CREDIT_STYLE_RE.search(st):
            ev['drop'] = 'credits'
        elif st not in japanese:
            ev['drop'] = 'not-japanese-style'
        elif not JAPANESE_CHARS_RE.search(text):
            ev['drop'] = 'no-japanese'
        if stats is not None:
            stats[ev['drop'] or 'kept'] += 1
    return events


def ass_to_srt(content, stats=None, ev=None):
    events = parse_ass_events(content, stats)
    if any(ev['drop'] in ('ruby-small', 'ruby-style') for ev in events):
        from aobana.indexing import ass_ruby
        ass_ruby.attach(events, content, ev=ev, stats=stats)
    groups = {}
    for e in events:
        if e['drop']:
            continue
        texts = groups.setdefault((e['start'], e['end']), [])
        same = [n for n, t in enumerate(texts) if bar_ruby_plain(t) == bar_ruby_plain(e['text'])]
        if not same:
            texts.append(e['text'])
        elif len(e['text']) > len(texts[same[0]]):
            texts[same[0]] = e['text']
    out = []
    for n, ((start, end), texts) in enumerate(sorted(groups.items(), key=lambda kv: kv[0]), 1):
        out.append(f"{n}\n{_srt_time(start)} --> {_srt_time(end)}\n" + '\n'.join(texts) + "\n")
    return '\n'.join(out)

def get_clean_text_for_mecab(line: str) -> str:
    return RUBY_RE.sub(r'\1\2', line)


def analyze_with_sudachi(clean_text: str):
    base_forms = []
    readings = []
    for word in get_tokenizer().tokenize(clean_text, mode):
        base_forms.append(word.normalized_form())
        
        kana = word.reading_form()
        if kana:
            readings.append(katakana_to_hiragana(kana))
        else:
            readings.append(word.surface())
            
    return " ".join(base_forms), " ".join(readings)

def compute_file_hash(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()

def kept_lines(path, relpath):
    content = read_subtitle_text(path)
    if path.lower().endswith(('.ass', '.ssa')):
        content = ass_to_srt(content)
    return extract_lines_grouped_by_timecode(content, relpath)


def index_rows(flat_lines, relpath):
    rows = []
    for line in flat_lines:
        clean_text = get_clean_text_for_mecab(line)
        if len(clean_text.encode('utf-8')) > SUDACHI_MAX_BYTES:
            _EXCLUDED_LOG.append((re.split(r"[\\/]", relpath)[0], "TOO_LONG", clean_text[:200]))
            _NOTES.append(f"TOO_LONG {relpath}: {len(clean_text.encode('utf-8'))} bytes")
            continue
        base_forms, readings = analyze_with_sudachi(clean_text)

        extracted_rubies = [m[2] for m in RUBY_RE.findall(line)]
        if extracted_rubies:
            base_forms, readings = ruby_index_extras(line, RUBY_RE, base_forms, readings)
            line = RUBY_RE.sub(clean_ruby_match, line)

        rows.append((line, clean_text, base_forms, readings))
    return rows


def _prepare(job):
    path, relpath, known_hash = job
    _EXCLUDED_LOG.clear()
    _WAKATI_LOG.clear()
    _NOTES.clear()
    try:
        file_hash = compute_file_hash(path)
        if file_hash == known_hash:
            return ('same', relpath, file_hash, None)
        rows = index_rows(kept_lines(path, relpath), relpath)
    except Exception as e:
        return ('error', relpath, None, f"{type(e).__name__}: {e}")
    return ('rows', relpath, file_hash, (rows, list(_EXCLUDED_LOG), list(_WAKATI_LOG), list(_NOTES)))


COMMIT_EVERY_FILES = 200
COMMIT_EVERY_SECONDS = 20


def build_lexicon(conn, top):
    if top and not has_ruby_lexicon(conn):
        emit("phase", "LEXICON building the ruby lexicon table (once, reads the whole index)...", phase="lexicon")
    ensure_ruby_lexicon(conn, "subtitles", "subs", paths.index_workers())


def build_tables():
    say(f"Building the subtitle index's tables ({DB_PATH})...")
    with sqlite3.connect(DB_PATH) as conn:
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'subtitles'").fetchone() is None:
            say("Tables ready: no subtitle index yet.")
            return
        top = conn.execute("SELECT rowid FROM subtitles ORDER BY rowid DESC LIMIT 1").fetchone()
        if top and not has_line_lengths(conn):
            emit("phase", "LENGTHS building the display-length table (once, reads the whole index)...", phase="lengths")
        ensure_line_lengths(conn, DB_PATH, "subtitles", "subs", paths.index_workers())
        if stop_requested():
            emit("stopped", "STOPPED")
            return
        build_lexicon(conn, top)
    say("Tables ready.")


def run_indexer(force=False, outdated=False, allow_removal=False):
    say(f"Starting indexer on {ROOT_DIR} (force={force}, outdated={outdated})...")
    _EXCLUDED_LOG.clear()
    _WAKATI_LOG.clear()
    if ROOT_DIR is None:
        emit("root_not_set", "ROOT_NOT_SET subs", media="subs")
        say("No subtitle folder is set (Library tab). Nothing was changed.")
        return
    if not paths.media_enabled("subs"):
        say("Subtitles are off in Settings. Nothing was changed.")
        return
    if not os.path.isdir(ROOT_DIR):
        emit("root_missing", f"ROOT_MISSING {ROOT_DIR}", folder=ROOT_DIR)
        say("Indexing aborted: the subtitle folder does not exist. Nothing was changed.")
        return
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    excluded, wakati = [], []

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row

        if force:
            say("Force rebuild requested. Dropping existing tables...")
            conn.execute("DROP TABLE IF EXISTS subtitles")
            conn.execute("DROP TABLE IF EXISTS line_lengths")
            conn.execute("DROP TABLE IF EXISTS ruby_lexicon")
            conn.execute("DROP TABLE IF EXISTS sources")
            conn.commit()

        conn.execute('''
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                relpath TEXT UNIQUE NOT NULL,
                file_hash TEXT NOT NULL,
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.execute('''
            CREATE VIRTUAL TABLE IF NOT EXISTS subtitles USING fts5(
                source_id UNINDEXED,
                file UNINDEXED,
                line UNINDEXED,
                clean_text UNINDEXED,
                base_forms,
                readings,
                tokenize = "unicode61"
            )
        ''')
        conn.commit()

        ensure_format_column(conn)
        conn.commit()
        cur = conn.execute("SELECT id, relpath, file_hash, index_format FROM sources")
        existing_files = {row['relpath']: {'id': row['id'], 'hash': None if outdated and is_outdated('subs', row['relpath'], row['index_format']) else row['file_hash']}
                          for row in cur}
        deleted_rows = inserted_rows = 0
        if outdated:
            n_old = sum(1 for v in existing_files.values() if v['hash'] is None)
            if n_old:
                say(f"OUTDATED {n_old}")
        top = conn.execute("SELECT rowid FROM subtitles ORDER BY rowid DESC LIMIT 1").fetchone()
        if top and not has_line_lengths(conn):
            emit("phase", "LENGTHS building the display-length table (once, reads the whole index)...", phase="lengths")
        ensure_line_lengths(conn, DB_PATH, "subtitles", "subs", paths.index_workers())
        lengths = has_line_lengths(conn)
        build_lexicon(conn, top)
        lexicon = has_ruby_lexicon(conn)
        floor = top[0] if top else 0
        next_rowid = floor + 1
        replaced = []

        def flush():
            nonlocal deleted_rows
            if replaced:
                marks = ",".join("?" * len(replaced))
                deleted_rows += conn.execute(f"DELETE FROM subtitles WHERE rowid <= ? AND source_id IN ({marks})",
                                             [floor] + replaced).rowcount
                replaced.clear()
            conn.commit()

        current_disk_files = set()
        new_or_updated = 0
        skipped = 0
        failed = 0

        srt_paths, ignored = [], 0
        for dirpath, _, filenames in os.walk(ROOT_DIR):
            for fname in filenames:
                if not fname.lower().endswith(SUB_EXTS):
                    if not fname.startswith('.'):
                        ignored += 1
                    continue
                srt_paths.append((dirpath, fname))
        if ignored:
            emit("ignored_other", f"IGNORED_OTHER {ignored}", count=ignored)
        emit("total", f"TOTAL {len(srt_paths)}", quiet=True, total=len(srt_paths))

        filtered = filtered_names(paths.filtered_list(), "subs")
        jobs, n_filtered = [], 0
        for dirpath, fname in srt_paths:
            path = os.path.join(dirpath, fname)
            relpath = sub_relpath(path, ROOT_DIR)
            if relpath in filtered:
                n_filtered += 1
                continue
            if relpath in current_disk_files:
                emit("skipped_clash", f"SKIPPED_CLASH {fname}", file=fname)
                continue
            current_disk_files.add(relpath)
            jobs.append((path, relpath, existing_files.get(relpath, {}).get('hash')))
        if n_filtered:
            emit("filtered", f"FILTERED {n_filtered}", count=n_filtered)

        workers = paths.index_workers() if len(jobs) > 1 else 1
        if workers > 1:
            say(f"Workers: {workers}")
        meta_written = False
        pending, last_commit = 0, time.monotonic()
        stopped = False
        for n, (kind, relpath, file_hash, payload) in enumerate(
                parallel_map(_prepare, jobs, workers, chunksize=4), 1):
            if stop_requested():
                stopped = True
                break
            emit("progress", f"PROGRESS {n}/{len(jobs)} {relpath}", quiet=True, done=n, total=len(jobs), file=relpath)
            if kind == 'same':
                skipped += 1
                continue
            old = existing_files.get(relpath)
            if kind == 'error':
                if old:
                    conn.execute("UPDATE sources SET file_hash = '' WHERE id = ?", (old['id'],))
                failed += 1
                emit("failed", f"FAILED {relpath}: {payload}", file=relpath, error=str(payload))
                continue
            rows, file_excluded, file_wakati, notes = payload
            excluded.extend(file_excluded)
            wakati.extend(file_wakati)
            for note in notes:
                say(note)
            if not meta_written:
                write_tokenizer_meta(conn, 1)
                meta_written = True
            if old:
                source_id = old['id']
                replaced.append(source_id)
                if lexicon:
                    drop_ruby_lexicon(conn, [source_id])
                conn.execute("UPDATE sources SET file_hash = ?, indexed_at = ?, index_format = ? WHERE id = ?",
                             (file_hash, datetime.now(), INDEX_FORMAT['subs'], source_id))
            else:
                cur = conn.execute("INSERT INTO sources (relpath, file_hash, index_format) VALUES (?, ?, ?)",
                                   (relpath, file_hash, INDEX_FORMAT['subs']))
                source_id = cur.lastrowid
            new_or_updated += 1
            inserted_rows += conn.executemany(
                "INSERT INTO subtitles(rowid, source_id, file, line, clean_text, base_forms, readings) VALUES (?, ?, ?, ?, ?, ?, ?);",
                [(next_rowid + i, source_id, relpath) + r for i, r in enumerate(rows)]
            ).rowcount
            if lengths:
                write_line_lengths(conn, ((next_rowid + i, r[0]) for i, r in enumerate(rows)), "subs")
            if lexicon:
                write_ruby_lexicon(conn, "subs", ((source_id, relpath, r[0]) for r in rows))
            next_rowid += len(rows)
            say(f"Indexed: {relpath}")
            pending += 1
            if pending >= COMMIT_EVERY_FILES or time.monotonic() - last_commit >= COMMIT_EVERY_SECONDS:
                flush()
                pending, last_commit = 0, time.monotonic()
        flush()

        deleted_files, _ = held_removals(len(existing_files), set(existing_files.keys()) - current_disk_files,
                                         filtered, allow_removal)
        for relpath in deleted_files:
            source_id = existing_files[relpath]['id']
            deleted_rows += conn.execute("DELETE FROM subtitles WHERE source_id = ?", (source_id,)).rowcount
            conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
            if lexicon:
                drop_ruby_lexicon(conn, [source_id])
            say(f"Removed {'filtered' if relpath in filtered else 'deleted'} file: {relpath}")

        if deleted_rows and lengths:
            drop_orphan_lengths(conn, "subtitles")

        ident = write_tokenizer_meta(conn, 0)
        if new_or_updated:
            say(f"Tokenizer: SudachiDict-core {ident['sudachidict_version']} "
                  f"({ident['dictionary_format']}), SudachiPy {ident['sudachipy_version']}, "
                  f"system.dic {ident['system_dic_sha256'][:12]}")

        conn.commit()
        if stopped:
            emit("stopped", "STOPPED")
        else:
            compact_if_worth(conn, "subtitles", deleted_rows, inserted_rows)
    
    if excluded:
        log_path = os.path.join(paths.logs_dir(), "excluded_lines.txt")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "w", encoding="utf-8") as log_f:
            for folder, reason, text in excluded:
                log_f.write(f"[{folder}] [{reason}] {text}\n")

    if wakati:
        log_path = os.path.join(paths.logs_dir(), "wakati_normalized.txt")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "w", encoding="utf-8") as log_f:
            for relp, count, mean_c in wakati:
                log_f.write(f"[{relp}] {count} lines normalized (mean chunk: {mean_c:.2f} chars)\n")

    emit("summary", f"Indexing complete! Skipped {skipped} unchanged files. Indexed {new_or_updated} new/updated files. Removed {len(deleted_files)} deleted files."
         + (f" Failed {failed}." if failed else ""),
         unchanged=skipped, indexed=new_or_updated, removed=len(deleted_files), failed=failed)
    if wakati:
        total_wakati_lines = sum(c for _, c, _ in wakati)
        say(f"Wakati-Gaki Normalization: Encountered and normalized {len(wakati)} file(s) ({total_wakati_lines} lines).")
    else:
        say("Wakati-Gaki Normalization: 0 wakati-spaced files encountered.")

if __name__ == "__main__":
    import sys
    start_output()
    force_rebuild = "--force" in sys.argv
    if "--tables" in sys.argv:
        if os.path.exists(DB_PATH):
            build_tables()
        sys.exit(0)
    run_indexer(force=force_rebuild, outdated="--outdated" in sys.argv, allow_removal=ALLOW_REMOVAL_FLAG in sys.argv)
