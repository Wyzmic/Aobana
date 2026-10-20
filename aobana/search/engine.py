
import bisect
import concurrent.futures
import functools
import math
import multiprocessing
import random
import re
import sqlite3
import sys
import threading
import time
from collections import OrderedDict
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path
from aobana.indexing.subtitle_ruby import has_native_ruby

from aobana.utils import (
    KANJI_CHARS, count_rows, fold_compat, fts_query_error, has_line_lengths, has_token_lengths, index_busy,
    katakana_to_hiragana, media_has, parse_media, token_surfaces,
)
from aobana.search.furigana import (
    bound_auxiliary, calculate_display_length, detect_script, drawn_ruby_re, drop_lexicon,
    forget_lexicon_memo, highlight_and_furigana, line_analysis, tagger, token_base, work_key,
)
from aobana.search.reading import (
    literal_equal_terms, own_work_readings, parse_reading_terms, prefilter_keys, row_matches,
)
from aobana.search.titles import (
    GLOBAL_BOOK_AUTHORS, GLOBAL_BOOK_TITLES, GLOBAL_MANGA_TITLES, GLOBAL_TITLES, get_sort_key,
    load_book_authors, title_of,
)
from aobana.search import iplusone, result_cache
from aobana.search.result_cache import (
    _LEAN_CHARS, _LEAN_FOLDER, _LEAN_LINE, _LEAN_MEDIA, _LEAN_ROWID, _LEAN_SCORE, _result_cache_get,
    _result_cache_key, _result_cache_page, _result_cache_put, _result_entry, _result_folder,
    db_fingerprint,
)
from aobana.search.media_tab import (
    _BACKGROUND_READERS, _BACKGROUND_READERS_LOCK, _media_library_cached,
)


GLOBAL_FOLDER_COUNTS = {}
GLOBAL_DB_TOTALS = {}


def get_db_total(db_subs, db_epub, media='all', db_manga=None):
    global GLOBAL_DB_TOTALS
    media = parse_media(media)
    from aobana.utils import media_connections
    dbs = media_connections(db_subs, db_epub, db_manga)
    db_subs, db_epub, db_manga = (dbs.get(m) for m in ('subs', 'epub', 'manga'))
    key = (media, db_fingerprint(*dbs.values()))
    if key in GLOBAL_DB_TOTALS:
        return GLOBAL_DB_TOTALS[key]
    lib = _media_library_cached(key[1])
    if lib is not None:
        total = sum(it["lines"] for it in lib if media_has(media, it["media"]))
        GLOBAL_DB_TOTALS[key] = total
        return total

    total = 0
    if media_has(media, 'subs') and db_subs is not None:
        try:
            total += count_rows(db_subs, "subtitles")
        except Exception:
            pass
    if media_has(media, 'epub') and db_epub is not None:
        try:
            total += count_rows(db_epub, "epubs")
        except Exception:
            pass
    if media_has(media, 'manga') and db_manga is not None:
        try:
            total += count_rows(db_manga, "manga")
        except Exception:
            pass

    if media_has(media, 'custom') and dbs.get('custom') is not None:
        total += count_rows(dbs['custom'], 'custom')
    GLOBAL_DB_TOTALS[key] = total
    return total


def folder_prefix_where(col: str, folder: str):
    prefixes = (folder + "\\", folder + "/")
    return (f"(({col} >= ? AND {col} < ?) OR ({col} >= ? AND {col} < ?))",
            [x for pre in prefixes for x in (pre, pre + "\U0010ffff")])


def like_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


_SUBS_QUERY_FOLD = str.maketrans({"?": "？", "!": "！"})


def media_query(text: str, m_type) -> str:
    if m_type == 'custom':
        from aobana.utils import CUSTOM_STR_REPLACEMENTS
        for old, new in CUSTOM_STR_REPLACEMENTS:
            text = text.replace(old, new)
        return text
    return text.translate(_SUBS_QUERY_FOLD) if text and (m_type or "subs") == "subs" else text


def release_db_handles():
    drop_lexicon(close_live=True)
    with _BACKGROUND_READERS_LOCK:
        readers = list(_BACKGROUND_READERS)
    for conn in readers:
        try:
            conn.interrupt()
        except Exception:
            pass
    _close_search_pool()

def split_negated_terms(query: str):
    tokens = []
    current = ""
    in_quotes = False
    for char in query:
        if char in ('"', '“', '”'):
            in_quotes = not in_quotes
            current += char
        elif not in_quotes and char.isspace():
            if current:
                tokens.append(current)
            current = ""
        else:
            current += char
    if current:
        tokens.append(current)
        
    positives = []
    negatives = []
    for token in tokens:
        if len(token) > 1 and (token.startswith('-') or token.startswith('－')):
            term = token[1:].strip('""“”')
            if term:
                negatives.append(term)
        else:
            positives.append(token)
            
    positive_query = " ".join(positives)
    return positive_query, negatives


def _space_tokens(column):
    parts = column.split(' ')
    if '  ' not in column and column != ' ':
        return parts
    out, i = [], 0
    while i < len(parts):
        if parts[i] == '' and i + 1 < len(parts) and parts[i + 1] == '':
            out.append(' ')
            i += 2
        else:
            out.append(parts[i])
            i += 1
    return out


def drawn_sequence_matches(line, groups, work):
    words = [w for w in line_analysis(line, work)['words'] if w['pos'] != '空白']
    for group in groups:
        n = len(group)
        if any(all(token_base(w) == base or w['surface'] == base
                   for w, base in zip(words[i:i+n], group))
               for i in range(len(words)-n+1)):
            return True
    return False


def bound_auxiliary_in_row(bound, base_forms, readings):
    if not base_forms or not readings:
        return None
    bases, reads = _space_tokens(base_forms), _space_tokens(readings)
    lemma, reading = bound
    if len(bases) != len(reads):
        return lemma in bases and any(r.startswith(reading) for r in reads)
    i = -1
    while True:
        try:
            i = bases.index(lemma, i + 1)
        except ValueError:
            return False
        if reads[i].startswith(reading):
            return True


def _is_symbol(pos, surface):
    return pos in ('補助記号', '空白') and not re.search(
        rf'[{KANJI_CHARS}\u3040-\u30FFa-zA-Z0-9ａ-ｚＡ-Ｚ０-９]', surface)


def fts_phrase(text):
    return '"' + text.replace('"', '""') + '"'


def _own_lemma(chunk, words):
    if (len(words) != 1 or words[0].surface() != chunk or words[0].normalized_form() == chunk
            or not re.search(f'[{KANJI_CHARS}]', chunk)):
        return words
    if all(k in words[0].normalized_form() for k in re.findall(f'[{KANJI_CHARS}]', chunk)):
        return words
    from aobana.search import furigana
    own = []
    for m in furigana._TAGGER_DICT[0].lookup(chunk):
        pos = m.part_of_speech()
        if (m.surface() == chunk and m.dictionary_form() == chunk and m.normalized_form() == chunk
                and pos[0] in ('動詞', '形容詞') and pos[5].startswith('終止形')
                and not pos[4].startswith('文語')):
            own.append(m)
    return own[:1] or words


def _learn_target(q):
    with tagger() as (tokenizer_obj, mode):
        words = tokenizer_obj.tokenize(q, mode)
        own = _own_lemma(q, words)
        if own is not words:
            form = own[0].normalized_form()
            return () if iplusone.is_grammar(form) else (form,)
    return iplusone.target_units(q)


def analyze_query(q):
    content_bases = []
    sql_bases = []
    readings = []
    base_groups = []

    with tagger() as (tokenizer_obj, mode):
        words = tokenizer_obj.tokenize(q, mode)
    if words and all(_is_symbol(w.part_of_speech()[0], w.surface()) for w in words):
        return content_bases, sql_bases, readings, base_groups

    script_type = detect_script(q)
    
    if script_type == 'katakana':
        with tagger() as (tokenizer_obj, mode):
            words = tokenizer_obj.tokenize(q, mode)
        content_bases = [q]
        hiragana_readings = []
        for word in words:
            norm = word.normalized_form()
            if norm != q:
                content_bases.append(norm)
            kana = word.reading_form()
            if kana:
                hiragana_readings.append(katakana_to_hiragana(kana))
        readings = hiragana_readings

        base_parts = [f'base_forms:{fts_phrase(q)}']
        for norm in content_bases:
            if norm != q:
                base_parts.append(f'base_forms:{fts_phrase(norm)}')
        sql_bases = [f'({"|" .join(base_parts).replace("|", " OR ")})']
        base_groups = [[b] for b in content_bases]
    else:
        for chunk in q.split():
            sa_verb_match = re.fullmatch(r'(屯|たむろ)(する|し|して|した|してる|している|してるんだ|します|しません|しよう)', chunk)
            ru_verb_match = re.fullmatch(r'(屯|たむろ)(る|り|れ|ろ|ら|って|った|っ|ってる|っている|ってて|ってた|ってろ|ってない|ってたい)', chunk)
            stem_match = re.fullmatch(r'(屯|たむろ)', chunk)
            
            if sa_verb_match:
                sql_bases.append('(readings:"たむろする" OR readings:("たむろ" "する") OR readings:("たむろ" "し"))')
                content_bases.extend(['屯', '為る', '屯する'])
                base_groups.extend([['屯'], ['為る'], ['屯する']])
                readings.extend(['たむろ', 'する', 'たむろっ'])
                continue
                
            if ru_verb_match:
                sql_bases.append('(readings:("たむろ" "る") OR readings:("たむろ" "って") OR readings:("たむろ" "った") OR readings:"たむろっ")')
                content_bases.extend(['屯', 'り', 'って', 'った', '屯する'])
                base_groups.extend([['屯'], ['り'], ['って'], ['った'], ['屯する']])
                readings.extend(['たむろ', 'する', 'たむろっ'])
                continue
                
            if stem_match:
                sql_bases.append('("屯 為る" OR "屯する" OR "屯")')
                content_bases.extend(['屯', '為る', '屯する'])
                base_groups.extend([['屯'], ['為る'], ['屯する']])
                readings.extend(['たむろ', 'する', 'たむろっ'])
                continue
                
            chunk_bases = []
            chunk_readings = []
            stripped_particles = 0
            kept_at = []
            with tagger() as (tokenizer_obj, mode):
                words = tokenizer_obj.tokenize(chunk, mode)
                words = _own_lemma(chunk, words)
            for at, word in enumerate(words):
                pos = word.part_of_speech()[0]
                base = word.normalized_form()
                surface = word.surface()
                
                if surface == 'いい' and base == '言う':
                    base = '良い'
                
                kana = word.reading_form()
                reading = katakana_to_hiragana(kana) if kana else surface
                
                readings.append(reading)
                
                is_symbol = pos == '補助記号' and _is_symbol(pos, surface)
                if (pos not in ('助動詞', '助詞') and not is_symbol) or script_type in ('hiragana', 'katakana'):
                    content_bases.append(base)
                    chunk_bases.append(base)
                    kept_at.append(at)
                    if script_type == 'hiragana':
                        content_bases.append(reading)
                        chunk_readings.append(reading)
                else:
                    stripped_particles += 1
                        
            if chunk_bases:
                if script_type in ('hiragana', 'katakana') or stripped_particles == 0:
                    phrase = fts_phrase(" ".join(chunk_bases))
                    base_groups.append(list(chunk_bases))
                    if chunk_readings and chunk_readings != chunk_bases:
                        base_groups.append(list(chunk_readings))
                else:
                    base_groups.extend([[b] for b in chunk_bases])
                    base_groups.extend([[r] for r in chunk_readings])
                    if len(chunk_bases) > 1:
                        args = " ".join(fts_phrase(b) for b in chunk_bases)
                        span = kept_at[-1] - kept_at[0] - 1
                        phrase = f"NEAR({args}, {max(stripped_particles + 2, span)})"
                    else:
                        phrase = fts_phrase(chunk_bases[0])
                    
                if script_type in ('hiragana', 'katakana'):
                    unbroken = katakana_to_hiragana(chunk) if script_type == 'katakana' else chunk
                    if fts_phrase(unbroken) != phrase:
                        sql_bases.append(f'(({phrase}) OR {fts_phrase(unbroken)})')
                    else:
                        sql_bases.append(f"({phrase})")
                    if unbroken not in content_bases:
                        content_bases.append(unbroken)
                        base_groups.append([unbroken])
                elif len(chunk_bases) > 1 and '"' not in chunk:
                    sql_bases.append(f'(({phrase}) OR {fts_phrase(chunk)})')
                    if chunk not in content_bases:
                        content_bases.append(chunk)
                        base_groups.append([chunk])
                else:
                    sql_bases.append(f"({phrase})")
                
        if not content_bases:
            content_bases = readings
            if readings:
                phrase = fts_phrase(" ".join(readings))
                sql_bases = [f"({phrase})"]
                base_groups = [list(readings)]
            
    return content_bases, sql_bases, readings, base_groups

@functools.lru_cache(maxsize=256)
def excluded_sequence(term, media):
    if media == 'custom':
        from aobana.indexing.custom_indexer import analyze_tokens
        return analyze_tokens(fold_compat(media_query(term, media)))[0]
    from aobana.indexing import indexer, epub_indexer, manga_indexer
    modules = {'subs': indexer, 'epub': epub_indexer, 'manga': manga_indexer}
    module = modules[media]
    clean = module.get_clean_text(term) if media == 'manga' else module.get_clean_text_for_mecab(term)
    clean = fold_compat(media_query(clean, media))
    if media == 'epub':
        clean = module.drawn_gloss_text(clean)
    return module.analyze_with_sudachi(clean)[0]


def query_highlight_args(q, m_type="all"):
    _, terms, _, q_rest = parse_reading_terms(q)
    pos_q, _ = split_negated_terms(q_rest)
    clean_q = media_query(pos_q.strip('""“”'), m_type)
    content_bases, _, readings, base_groups = analyze_query(clean_q)
    return {"content_bases": content_bases, "q": clean_q, "base_groups": base_groups,
            "readings": readings, "reading_terms": terms or None}


def reading_prefilter(terms, line, clean_text, row_readings, media, work, row_bases=None, lens=None):
    if fold_compat(line) != clean_text or next(drawn_ruby_re(media).finditer(line), None) is not None:
        return True
    joined = (row_readings or "").replace(" ", "")
    near = []
    for term in terms:
        keys = prefilter_keys(term)
        if not keys or own_work_readings(work, term.word):
            continue
        if not any(k in joined for k in keys):
            return False
        near.append((term, keys))
    if not near:
        return True
    surf = token_surfaces(clean_text, lens)
    if surf is None:
        return True
    reads, bases = _space_tokens(row_readings or ""), _space_tokens(row_bases or "")
    if len(reads) < len(surf) or len(bases) < len(surf):
        return True
    for term, keys in near:
        kanji, span = set(term.kanji), len(term.word) - 1
        at = [i for i, s in enumerate(surf) if kanji & set(s) or kanji & set(bases[i])]
        if at and not any(k in "".join(reads[max(0, i - span):i + span + 1]) for i in at for k in keys):
            return False
    return True


READING_PREFILTER = True


def line_text(clean_text, media):
    if media == 'custom':
        return (clean_text or '').split('\u2029', 1)[0]
    return clean_text or ''


def sentence_score(line, query, is_exact, length=None):
    if length is None:
        length = calculate_display_length(line)
    score = math.exp(-0.5 * ((length - 27) / 15) ** 2)
    if is_exact:
        score += 0.5
    return score


def add_manga_pages(rows, db_manga):
    rowids = [r["rowid"] for r in rows if r.get("media_type") == "manga"]
    if not rowids or db_manga is None:
        return
    pages = {}
    try:
        for j in range(0, len(rowids), 500):
            part = rowids[j:j + 500]
            pages.update(db_manga.execute(
                f"SELECT rowid, page FROM manga_pages WHERE rowid IN ({','.join('?' * len(part))})", part).fetchall())
    except sqlite3.Error:
        return
    for r in rows:
        if r.get("media_type") == "manga" and r["rowid"] in pages:
            r["page"] = pages[r["rowid"]]


_LENGTHS_READY = {}
_KANJI_READY = {}


def _kanji_ready(conn, table):
    key = (db_fingerprint(conn), table)
    if key not in _KANJI_READY:
        if len(_KANJI_READY) > 16:
            _KANJI_READY.clear()
        from aobana.indexing import kanji_table
        _KANJI_READY[key] = kanji_table.ready(conn, table)
    return _KANJI_READY[key]


_SEARCH_POOL_LOCK = threading.Lock()
_SEARCH_POOL = None
_SEARCH_POOL_SIZE = 0
_SEARCH_POOL_CANCEL = None
_SEARCH_POOL_PROGRESS = None
_SEARCH_POOL_IDLE = 300.0
_SEARCH_POOL_TIMER = None
_SEARCH_POOL_USES = 0
_SEARCH_POOL_GEN = [0]
_SEARCH_POOL_BORN = 0
_INDEX_RUN = threading.Event()
_SCAN_WORKER_CANCEL = None
_SCAN_WORKER_PROGRESS = None
_POOL_MIN_ROWS = 20000


class _WorkerAbort:
    def __getitem__(self, index):
        return _SCAN_WORKER_CANCEL is not None and _SCAN_WORKER_CANCEL.is_set()


def _init_scan_worker(cancel_event, progress_val=None):
    global _SCAN_WORKER_CANCEL, _SCAN_WORKER_PROGRESS
    _SCAN_WORKER_CANCEL = cancel_event
    _SCAN_WORKER_PROGRESS = progress_val


def _shut_search_pool():
    global _SEARCH_POOL, _SEARCH_POOL_SIZE, _SEARCH_POOL_CANCEL, _SEARCH_POOL_PROGRESS, _SEARCH_POOL_TIMER
    if _SEARCH_POOL_TIMER is not None:
        _SEARCH_POOL_TIMER.cancel()
        _SEARCH_POOL_TIMER = None
    if _SEARCH_POOL_CANCEL is not None:
        try:
            _SEARCH_POOL_CANCEL.set()
        except Exception:
            pass
    if _SEARCH_POOL is not None:
        _SEARCH_POOL.shutdown(wait=True, cancel_futures=True)
    _SEARCH_POOL = None
    _SEARCH_POOL_SIZE = 0
    _SEARCH_POOL_CANCEL = None
    _SEARCH_POOL_PROGRESS = None


def _close_search_pool():
    with _SEARCH_POOL_LOCK:
        _shut_search_pool()


def _retire_search_pool():
    _SEARCH_POOL_GEN[0] += 1
    if _SEARCH_POOL_LOCK.acquire(blocking=False):
        try:
            _shut_search_pool()
        finally:
            _SEARCH_POOL_LOCK.release()


def index_run(running):
    if running:
        _INDEX_RUN.set()
        _retire_search_pool()
    else:
        _INDEX_RUN.clear()


def _search_pool(workers):
    global _SEARCH_POOL, _SEARCH_POOL_SIZE, _SEARCH_POOL_CANCEL, _SEARCH_POOL_PROGRESS, _SEARCH_POOL_TIMER
    global _SEARCH_POOL_USES, _SEARCH_POOL_BORN
    _SEARCH_POOL_USES += 1
    if _SEARCH_POOL_TIMER is not None:
        _SEARCH_POOL_TIMER.cancel()
        _SEARCH_POOL_TIMER = None
    if _SEARCH_POOL is not None and (_SEARCH_POOL_SIZE != workers or getattr(_SEARCH_POOL, "_broken", False)
                                     or _SEARCH_POOL_BORN != _SEARCH_POOL_GEN[0]):
        _shut_search_pool()
    if _SEARCH_POOL is None:
        _SEARCH_POOL_BORN = _SEARCH_POOL_GEN[0]
        ctx = multiprocessing.get_context("spawn")
        _SEARCH_POOL_CANCEL = ctx.Event()
        _SEARCH_POOL_PROGRESS = ctx.Value("q", 0)
        _SEARCH_POOL = concurrent.futures.ProcessPoolExecutor(
            max_workers=workers, mp_context=ctx,
            initializer=_init_scan_worker,
            initargs=(_SEARCH_POOL_CANCEL, _SEARCH_POOL_PROGRESS))
        _SEARCH_POOL_SIZE = workers
    _SEARCH_POOL_CANCEL.clear()
    _SEARCH_POOL_PROGRESS.value = 0
    return _SEARCH_POOL


def _search_pool_done(futures):
    global _SEARCH_POOL_TIMER
    if _SEARCH_POOL_CANCEL is not None:
        try:
            _SEARCH_POOL_CANCEL.set()
        except Exception:
            pass
    left = [f for f in (futures or ()) if f is not None]
    for future in left:
        future.cancel()
    if left:
        concurrent.futures.wait(left)
    if _INDEX_RUN.is_set():
        _shut_search_pool()
    elif _SEARCH_POOL is not None:
        _SEARCH_POOL_TIMER = threading.Timer(_SEARCH_POOL_IDLE, _idle_search_pool, (_SEARCH_POOL_USES,))
        _SEARCH_POOL_TIMER.daemon = True
        _SEARCH_POOL_TIMER.start()


def _idle_search_pool(uses):
    if not _SEARCH_POOL_LOCK.acquire(blocking=False):
        return
    try:
        if uses == _SEARCH_POOL_USES:
            _shut_search_pool()
    finally:
        _SEARCH_POOL_LOCK.release()


def _small_table(conn, table):
    try:
        top = conn.execute(f"SELECT MAX(rowid) FROM {table}").fetchone()[0] or 0
    except sqlite3.Error:
        return False
    return top < _POOL_MIN_ROWS


def _scan_chunk_worker(db_path, media, q, sort, exact, seed, lo, hi, abort_flag=None, folder=None, ruby_only=False,
                       learn=''):
    conn = sqlite3.connect(Path(db_path).as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    if abort_flag is None:
        abort_flag = _WorkerAbort() if _SCAN_WORKER_CANCEL is not None else [False]
    conn.set_progress_handler(lambda: 1 if abort_flag[0] else 0, 1000)
    try:
        return _search_results({media: conn}, q, None, sort, folder, exact,
                               abort_flag,
                               0, 0, None, None, media, seed, [],
                               scan_bounds=(lo, hi), scan_only=True,
                               ruby_only=ruby_only, learn=learn)
    except sqlite3.OperationalError as e:
        if "interrupted" in str(e):
            return [], {}, set(), 0
        raise
    finally:
        conn.close()


def _parallel_scan_remainder(conn, table, media, q, sort, exact, seed, lo, base, counts, raw,
                             workers, abort_flag, entry, ruby_only=False, learn=''):
    hi = conn.execute(f"SELECT MAX(rowid) FROM {table}").fetchone()[0] or 0
    if lo > hi:
        return base, counts, 0
    db_path = next((r[2] for r in conn.execute("PRAGMA database_list") if r[1] == "main"), "")
    if not db_path:
        return None
    count = min(workers * 4, hi - lo + 1)
    width = (hi - lo + count) // count
    bounds = [(start, min(start + width - 1, hi)) for start in range(lo, hi + 1, width)]
    base_done = entry.get("pass_done", 0) if entry is not None else 0
    if entry is not None:
        entry["parallel_base"] = base_done
        entry["parallel_start"] = None
        entry["parallel_first_done"] = 0
    done_seen = {}
    futures = None
    locked = _SEARCH_POOL_LOCK.acquire(blocking=False)
    try:
        if locked:
            try:
                pool = _search_pool(workers)
                futures = [pool.submit(_scan_chunk_worker, db_path, media, q, sort, exact,
                                       seed, a, b, ruby_only=ruby_only, learn=learn) for a, b in bounds]
                if entry is not None and len(futures) > 1:
                    entry["workers"] = min(workers, len(futures))
            except (ImportError, OSError, NotImplementedError, BrokenProcessPool):
                futures = None

        merged = list(base)
        seen_raw = dict.fromkeys(raw)
        seen_raw.update((row[_LEAN_LINE], i) for i, row in enumerate(merged))
        total_seen = 0
        for i, (a, b) in enumerate(bounds):
            if abort_flag and abort_flag[0]:
                return None
            if futures is None:
                part, part_counts, part_raw, part_seen = _scan_chunk_worker(
                    db_path, media, q, sort, exact, seed, a, b, abort_flag, ruby_only=ruby_only, learn=learn)
                total_seen += part_seen
                if entry is not None:
                    entry["pass_done"] = base_done + total_seen
            else:
                while True:
                    if abort_flag and abort_flag[0]:
                        return None
                    if entry is not None:
                        live = _SEARCH_POOL_PROGRESS.value if _SEARCH_POOL_PROGRESS is not None else 0
                        for k, fut in enumerate(futures):
                            if (fut is not None and k not in done_seen and fut.done()
                                    and not fut.cancelled() and fut.exception() is None):
                                done_seen[k] = fut.result()[3]
                        best_done = max(live, sum(done_seen.values()))
                        if best_done > 0 and entry.get("parallel_start") is None:
                            entry["parallel_start"] = time.monotonic()
                            entry["parallel_first_done"] = best_done
                        entry["pass_done"] = max(entry.get("pass_done", 0), base_done + best_done)
                    try:
                        part, part_counts, part_raw, part_seen = futures[i].result(timeout=0.2)
                        futures[i] = None
                        done_seen[i] = part_seen
                        if entry is not None:
                            live = _SEARCH_POOL_PROGRESS.value if _SEARCH_POOL_PROGRESS is not None else 0
                            best_done = max(live, sum(done_seen.values()))
                            if best_done > 0 and entry.get("parallel_start") is None:
                                entry["parallel_start"] = time.monotonic()
                                entry["parallel_first_done"] = best_done
                            entry["pass_done"] = max(entry.get("pass_done", 0), base_done + best_done)
                        break
                    except concurrent.futures.TimeoutError:
                        continue
                    except Exception:
                        futures[i] = None
                        part, part_counts, part_raw, part_seen = _scan_chunk_worker(
                            db_path, media, q, sort, exact, seed, a, b, abort_flag, ruby_only=ruby_only,
                            learn=learn)
                        done_seen[i] = part_seen
                        if entry is not None:
                            entry["pass_done"] = max(entry.get("pass_done", 0), base_done + sum(done_seen.values()))
                        break
                total_seen += part_seen
            for row_number, row in enumerate(part):
                if row_number % 1000 == 0 and abort_flag and abort_flag[0]:
                    return None
                line = row[_LEAN_LINE]
                if line not in seen_raw:
                    seen_raw[line] = len(merged)
                    merged.append(row)
            for title, n in part_counts.items():
                counts[title] = counts.get(title, 0) + n
        if entry is not None and entry.get("merge_start") is None:
            entry["merge_start"] = time.monotonic()
        merged.sort(key=lambda row: row[_LEAN_LINE])
        return merged, counts, total_seen
    finally:
        if locked:
            try:
                _search_pool_done(futures)
            finally:
                _SEARCH_POOL_LOCK.release()


def _parallel_chrono_runs(conn, table, media, q, exact, seed, runs, folder_set, workers, abort_flag, entry, ruby_only=False,
                          learn=''):
    if not _SEARCH_POOL_LOCK.acquire(blocking=False):
        return None
    pool = None
    pending = {}
    try:
        db_path = next((r[2] for r in conn.execute('PRAGMA database_list') if r[1] == 'main'), '')
        if not db_path:
            return None
        if runs is None:
            top = conn.execute(f'SELECT MAX(rowid) FROM {table}').fetchone()[0] or 0
            intervals = [(1, top)] if top else []
        else:
            intervals = [(lo,hi) for lo,hi,_ in runs]
        total = sum(hi-lo+1 for lo,hi in intervals)
        width = max(1, (total + workers*4 - 1)//(workers*4))
        bounds = [(start,min(start+width-1,hi)) for lo,hi in intervals for start in range(lo,hi+1,width)]
        if len(bounds) < 2:
            return None
        pool = _search_pool(workers)
        if entry is not None:
            entry['workers'] = min(workers,len(bounds))
        merged, counts, seen = [], {}, 0
        cursor = iter(enumerate(bounds))
        while True:
            while len(pending) < workers*2:
                try:
                    index,(lo,hi) = next(cursor)
                except StopIteration:
                    break
                pending[index] = pool.submit(_scan_chunk_worker,db_path,media,q,'chrono',exact,seed,lo,hi,None,tuple(folder_set or ()),ruby_only,learn)
            if not pending:
                break
            index = min(pending)
            while True:
                if abort_flag and abort_flag[0]:
                    raise sqlite3.OperationalError('interrupted')
                try:
                    part, part_counts, _, n = pending[index].result(timeout=.2)
                    break
                except concurrent.futures.TimeoutError:
                    continue
            del pending[index]
            merged.extend(part); seen += n
            for name,count in part_counts.items():
                counts[name] = counts.get(name,0)+count
            if entry is not None:
                entry['pass_done'] = seen
        files = {}
        ids = [r[_LEAN_ROWID] for r in merged]
        for i in range(0,len(ids),500):
            chunk = ids[i:i+500]
            files.update(conn.execute(f"SELECT rowid,file FROM {table} WHERE rowid IN ({','.join('?' for _ in chunk)})",chunk))
        merged.sort(key=lambda r:(files[r[_LEAN_ROWID]],r[_LEAN_ROWID]))
        return merged,seen,counts
    except (ImportError,OSError,NotImplementedError,BrokenProcessPool):
        return None
    finally:
        try:
            if pool is not None:
                _search_pool_done(list(pending.values()))
        finally:
            _SEARCH_POOL_LOCK.release()


def _scan_columns(conn, table, tokens=False):
    key = db_fingerprint(conn)
    if key not in _LENGTHS_READY:
        if len(_LENGTHS_READY) > 16:
            _LENGTHS_READY.clear()
        _LENGTHS_READY[key] = (has_line_lengths(conn), has_token_lengths(conn))
    chars, lens = _LENGTHS_READY[key]
    cols = f"{table}.rowid, line, file, clean_text, readings, base_forms"
    cols += ", line_lengths.chars" if chars else ", NULL"
    cols += ", token_lengths.lens" if tokens and lens else ", NULL"
    cols += f" FROM {table}"
    if chars:
        cols += f" LEFT JOIN line_lengths ON line_lengths.rowid = {table}.rowid"
    if tokens and lens:
        cols += f" LEFT JOIN token_lengths ON token_lengths.rowid = {table}.rowid"
    return cols


class _ChronoHandoff(Exception):
    pass


def _scan_rows(conn, cols, where_clause, params, sort, m_type, pass1, abort_flag, entry, counts,
               raw_lines=None, split_state=None, folder_filter=None):
    rowid = cols.split(".", 1)[0] + ".rowid"
    if sort == "chrono":
        cur = conn.execute(f"SELECT {cols} {where_clause} ORDER BY file ASC, {rowid} ASC", params)
        lean, seen = [], 0
        base = entry.get("pass_base", 0) if entry is not None else 0
        for r in cur:
            seen += 1
            if entry is not None and entry.get('chrono_deadline') is not None and seen % 100 == 0 and time.monotonic() >= entry['chrono_deadline']:
                raise _ChronoHandoff()
            if abort_flag and abort_flag[0] and seen % 100 == 0:
                return None, seen
            if entry is not None and seen % 2000 == 0:
                entry["pass_done"] = base + seen
            if folder_filter is not None and _result_folder(m_type, r[2]) not in folder_filter:
                continue
            got = pass1(r, m_type)
            if got is not None:
                f = got[_LEAN_FOLDER]
                counts[f] = counts.get(f, 0) + 1
                lean.append(got)
        return lean, seen
    base = entry.get("pass_base", 0) if entry is not None else 0
    cur = conn.execute(f"SELECT {cols} {where_clause}", params)
    first = {}
    lean, seen, prev, reported = [], 0, -1, 0
    for r in cur:
        seen += 1
        if abort_flag and abort_flag[0] and seen % 100 == 0:
            return None, seen
        if (split_state is not None and seen % 200 == 0
                and __import__('time').monotonic() >= split_state["deadline"]):
            split_state["next_rowid"] = prev + 1
            split_state["raw_lines"] = first
            cur.close()
            lean.sort(key=lambda x: x[_LEAN_LINE])
            return lean, seen - 1
        if seen % 500 == 0:
            if entry is not None:
                entry["pass_done"] = base + seen
            if _SCAN_WORKER_PROGRESS is not None:
                with _SCAN_WORKER_PROGRESS.get_lock():
                    _SCAN_WORKER_PROGRESS.value += seen - reported
                reported = seen
        if r[0] < prev:
            cur.close()
            counts.clear()
            return _scan_grouped(conn, cols, rowid, where_clause, params, m_type, pass1,
                                 abort_flag, counts, folder_filter=folder_filter)
        prev = r[0]
        if folder_filter is not None and _result_folder(m_type, r[2]) not in folder_filter:
            continue
        line = r[1]
        got = pass1(r, m_type)
        if got is None:
            continue
        f = got[_LEAN_FOLDER]
        counts[f] = counts.get(f, 0) + 1
        if line not in first:
            first[line] = len(lean)
            lean.append(got)
    if _SCAN_WORKER_PROGRESS is not None and seen > reported:
        with _SCAN_WORKER_PROGRESS.get_lock():
            _SCAN_WORKER_PROGRESS.value += seen - reported
    if raw_lines is None:
        lean.sort(key=lambda x: x[_LEAN_LINE])
    return lean, seen


def _scan_runs(conn, cols, where_clause, params, runs, table, sort, m_type, pass1,
               abort_flag, entry, counts, folder_filter=None):
    clause = where_clause[:-1] + f" AND {table}.rowid BETWEEN ? AND ?)"
    lean, seen = [], 0
    keep_file = sort == "chrono" and len(runs) > 1
    if keep_file:
        def row_pass1(r, m):
            g = pass1(r, m)
            return (*g, r[2]) if g is not None else None
    else:
        row_pass1 = pass1
    for lo, hi, _ in runs:
        if entry is not None:
            entry["pass_base"] = seen
        run_counts = {}
        part, n = _scan_rows(conn, cols, clause, list(params) + [lo, hi], sort, m_type, row_pass1,
                             abort_flag, entry, run_counts, folder_filter=folder_filter)
        seen += n
        if part is None:
            return None, seen
        lean.extend(part)
        for f, count in run_counts.items():
            counts[f] = counts.get(f, 0) + count
    if keep_file:
        lean.sort(key=lambda x: (x[6], x[_LEAN_ROWID]))
        lean = [x[:6] for x in lean]
    elif sort != "chrono" and len(runs) > 1:
        first = {}
        for x in lean:
            if x[_LEAN_LINE] not in first or x[_LEAN_ROWID] < first[x[_LEAN_LINE]][_LEAN_ROWID]:
                first[x[_LEAN_LINE]] = x
        lean = sorted(first.values(), key=lambda x: x[_LEAN_LINE])
    return lean, seen


def _scan_grouped(conn, cols, rowid, where_clause, params, m_type, pass1, abort_flag, counts, folder_filter=None):
    first = {}
    seen = 0
    for n, r in enumerate(conn.execute(f"SELECT {cols} {where_clause}", params)):
        seen = n + 1
        if abort_flag and abort_flag[0] and n % 100 == 0:
            return None, seen
        if folder_filter is not None and _result_folder(m_type, r[2]) not in folder_filter:
            continue
        got = pass1(r, m_type)
        if got is not None:
            f = got[_LEAN_FOLDER]
            counts[f] = counts.get(f, 0) + 1
            line = got[_LEAN_LINE]
            if line not in first or got[_LEAN_ROWID] < first[line][_LEAN_ROWID]:
                first[line] = got
    return sorted(first.values(), key=lambda x: x[_LEAN_LINE]), seen


def _book_scope(targets, folder_set):
    from aobana import utils
    epub = next((c for _, c, m in targets if m == "epub" and c is not None), None)
    if epub is None or not folder_set or not utils.has_chapters(epub):
        return None
    spans = []
    for f in folder_set:
        mine = []
        for pre in (f + "\\", f + "/"):
            for file, lo, hi in epub.execute(
                    "SELECT file, first_rowid, last_rowid FROM chapters WHERE file >= ? AND file < ?",
                    (pre, pre + "\U0010ffff")):
                if _result_folder("epub", file) == f:
                    mine.append((lo, hi, file))
        spans.extend(mine)
    return _merge_runs(spans)


def _merge_runs(spans):
    runs = []
    for lo, hi, file in sorted(spans):
        if runs and lo <= runs[-1][1] + 1:
            runs[-1][1] = max(runs[-1][1], hi)
            runs[-1][2] = min(runs[-1][2], file)
        else:
            runs.append([lo, hi, file])
    runs.sort(key=lambda r: r[2])
    return runs


_SOURCE_INDEX = {}


def _source_runs(conn, table, m_type, folder_set):
    if conn is None or not folder_set:
        return None
    if m_type == 'subs':
        from aobana.indexing.source_ranges import ready
        if ready(conn):
            runs = []
            for folder in sorted(folder_set):
                where, params = folder_prefix_where('s.relpath', folder)
                runs.extend([a, b, rel] for a, b, rel in conn.execute(
                    'SELECT r.first_rowid,r.last_rowid,s.relpath FROM source_ranges r '
                    f'JOIN sources s ON s.id=r.source_id WHERE {where}', params))
            return _merge_runs(runs)
    key = (db_fingerprint(conn), m_type)
    idx = _SOURCE_INDEX.get(key)
    if idx is None:
        try:
            if m_type == "manga":
                rows = [(r[0], r[1], f"{r[1]}\\{r[2]}", r[3])
                        for r in conn.execute("SELECT id, title, volume, indexed_at FROM sources")]
            elif m_type == 'custom':
                rows = [(r[0], r[1], r[2], r[3])
                        for r in conn.execute('SELECT id, category, relpath, indexed_at FROM sources')]
            else:
                rows = [(r[0], _result_folder("subs", r[1]), r[1], r[2])
                        for r in conn.execute("SELECT id, relpath, indexed_at FROM sources")]
            if not rows:
                return None
            rows.sort(key=lambda r: ((r[3] or "").replace("T", " ")[:19], r[0]))
            file_rank = {}
            folder_spans = {}
            for rank, (_, folder, file_key, _) in enumerate(rows):
                file_rank[file_key] = rank
                spans = folder_spans.setdefault(folder, [])
                if spans and rank == spans[-1][1] + 1:
                    spans[-1][1] = rank
                    if file_key < spans[-1][2]:
                        spans[-1][2] = file_key
                else:
                    spans.append([rank, rank, file_key])
            max_id = conn.execute(f"SELECT MAX(id) FROM {table}_content").fetchone()[0] or 0
            idx = (file_rank, folder_spans, max_id, {})
            if len(_SOURCE_INDEX) > 8:
                _SOURCE_INDEX.clear()
            _SOURCE_INDEX[key] = idx
        except sqlite3.Error:
            return None
    file_rank, folder_spans, max_id, resolved = idx
    if max_id <= 0:
        return []

    def probe(target_rank):
        lo, hi = 1, max_id
        ans = None
        while lo <= hi:
            mid = (lo + hi) // 2
            row = conn.execute(f"SELECT id, c1 FROM {table}_content WHERE id >= ? LIMIT 1", (mid,)).fetchone()
            if row is None:
                hi = mid - 1
                continue
            rid, c1 = row
            rk = file_rank.get(c1)
            if rk is None:
                return False
            if rk >= target_rank:
                ans = rid
                hi = mid - 1
            else:
                lo = rid + 1
        return ans

    all_spans = []
    for f in folder_set:
        f_runs = resolved.get(f)
        if f_runs is None:
            rank_spans = folder_spans.get(f)
            if not rank_spans:
                return None
            f_runs = []
            try:
                for r_lo, r_hi, min_file in rank_spans:
                    row_lo = probe(r_lo)
                    if row_lo is False:
                        return None
                    after_hi = probe(r_hi + 1)
                    if after_hi is False:
                        return None
                    row_hi = (after_hi - 1) if after_hi is not None else max_id
                    if row_lo is None or row_lo > row_hi:
                        continue
                    f_runs.append([row_lo, row_hi, min_file])
            except sqlite3.Error:
                return None
            resolved[f] = f_runs
        all_spans.extend(f_runs)
    return _merge_runs(all_spans)


def _search_key(q, sort, seed, media, exact, folder_set, file, targets, folder_media=None, ruby_only=False,
                learn=''):
    key = _result_cache_key(q, sort, seed, media, exact, None, file, targets, ruby_only, learn)
    if not q or not folder_set or file:
        return key, None
    if folder_media is None:
        try:
            _, folder_media = _folder_list_for(targets)
        except Exception:
            folder_media = {}
    runs_by_media = {}
    for table, conn, m_type in targets:
        if conn is None:
            continue
        m_folders = {f for f in folder_set if m_type in folder_media.get(f, ())}
        if not m_folders:
            runs_by_media[m_type] = []
            continue
        if m_type == "epub":
            m_runs = _book_scope(targets, m_folders)
        else:
            m_runs = _source_runs(conn, table, m_type, m_folders)
        if m_runs is None:
            return key, None
        runs_by_media[m_type] = m_runs
    if not runs_by_media:
        return key, None
    scoped = _result_cache_key(q, sort, seed, media, exact, tuple(sorted(folder_set)), file, targets, ruby_only, learn)
    if scoped is not None and _result_cache_get(scoped) is not None:
        return scoped, runs_by_media
    if key is not None and _result_cache_get(key) is not None:
        return key, None
    return scoped, runs_by_media


def _match_where(table_name, sql_bases, readings, script_type):
    match_str = " AND ".join(sql_bases)
    if match_str:
        if len(readings) >= 2 and script_type == 'hiragana':
            r_str = fts_phrase(" ".join(readings))
            return f"{table_name} MATCH ?", [f"({match_str}) OR (readings: {r_str})"]
        return f"{table_name} MATCH ?", [match_str]
    if readings:
        match_str = fts_phrase(" ".join(readings))
        if match_str != '""':
            return f"{table_name} MATCH ?", [f"readings: {match_str}"]
    return None


_MATCH_COUNTS = OrderedDict()


def folder_match_counts(db_subs, q, exact=False, db_epub=None, media='all', db_manga=None, abort_flag=None,
                        search_workers=1, search_delay=10, search_started=None):
    import time
    if search_started is None:
        search_started = time.monotonic()
    if is_reading_search(q):
        return None
    pos_q, neg_terms = split_negated_terms(q)
    clean_q = pos_q.strip('""“”')
    if (not clean_q or exact or any(n.strip('""“”') for n in neg_terms)
            or (pos_q.startswith('"') and pos_q.endswith('"'))
            or (pos_q.startswith('”') and pos_q.endswith('”')) or bound_auxiliary(clean_q)
            or re.search(r'(?:屯|たむろ)', clean_q)):
        return None
    _, sql_bases, readings, _ = analyze_query(clean_q)
    script_type = detect_script(clean_q)
    targets = _search_targets(db_subs, db_epub, media, db_manga)
    wheres = {}
    for table, conn, m_type in targets:
        if conn is None:
            continue
        wheres[table] = _match_where(table, sql_bases, readings, script_type)
        if wheres[table] is None:
            return None
    key = (q, media, db_fingerprint(*[c for _, c, _ in targets]))
    if result_cache.RESULT_CACHE_ENABLED and key in _MATCH_COUNTS:
        _MATCH_COUNTS.move_to_end(key)
        return _MATCH_COUNTS[key]
    from aobana import utils
    counts = {}
    for table, conn, m_type in targets:
        if conn is None:
            continue
        sql, params = wheres[table]
        if m_type == "epub" and utils.has_chapters(conn):
            got = _count_by_chapters(conn, table, sql, params, abort_flag,
                                     search_workers=search_workers,
                                     search_delay=search_delay,
                                     search_started=search_started)
        else:
            got = {}
            for n, (file,) in enumerate(conn.execute(f"SELECT file FROM {table} WHERE {sql}", params)):
                if abort_flag and abort_flag[0] and n % 10000 == 0:
                    got = None
                    break
                f = _result_folder(m_type, file)
                got[f] = got.get(f, 0) + 1
        if got is None:
            return None
        for f, n in got.items():
            counts[f] = counts.get(f, 0) + n
    out = (counts, sorted(counts, key=lambda f: counts[f], reverse=True), sum(counts.values()))
    if result_cache.RESULT_CACHE_ENABLED:
        _MATCH_COUNTS[key] = out
        if len(_MATCH_COUNTS) > 16:
            _MATCH_COUNTS.popitem(last=False)
    return out


def _finish_chapter_counts(conn, table, names, per_chapter, stray):
    counts = {}
    for name, n in zip(names, per_chapter):
        if n:
            counts[name] = counts.get(name, 0) + n
    for k in range(0, len(stray), 500):
        part = stray[k:k + 500]
        for (file,) in conn.execute(f"SELECT file FROM {table} WHERE rowid IN ({','.join('?' * len(part))})", part):
            f = _result_folder("epub", file)
            counts[f] = counts.get(f, 0) + 1
    return counts


def _count_chunk_worker(db_path, table, sql, params, lo, hi, abort_flag=None):
    conn = sqlite3.connect(Path(db_path).as_uri() + "?mode=ro", uri=True)
    conn.execute("PRAGMA query_only=ON")
    if abort_flag is None:
        abort_flag = _WorkerAbort() if _SCAN_WORKER_CANCEL is not None else [False]
    conn.set_progress_handler(lambda: 1 if abort_flag[0] else 0, 5000)
    try:
        chapters = conn.execute(
            "SELECT first_rowid, last_rowid, file FROM chapters WHERE last_rowid >= ? AND first_rowid <= ? ORDER BY first_rowid",
            (lo, hi)).fetchall()
        if not chapters:
            return {}
        starts = [c[0] for c in chapters]
        ends = [c[1] for c in chapters]
        names = [_result_folder("epub", c[2]) for c in chapters]
        per_chapter = [0] * len(chapters)
        stray = []
        i, c_lo, c_hi = 0, starts[0], ends[0]
        cur = conn.execute(
            f"SELECT {table}.rowid FROM {table} WHERE ({sql}) AND {table}.rowid BETWEEN ? AND ?",
            [*params, lo, hi])
        while True:
            batch = cur.fetchmany(50000)
            if not batch:
                break
            if abort_flag and abort_flag[0]:
                return {}
            for (rowid,) in batch:
                if not c_lo <= rowid <= c_hi:
                    i = max(bisect.bisect_right(starts, rowid) - 1, 0)
                    c_lo, c_hi = starts[i], ends[i]
                    if not c_lo <= rowid <= c_hi:
                        stray.append(rowid)
                        continue
                per_chapter[i] += 1
        return _finish_chapter_counts(conn, table, names, per_chapter, stray)
    except sqlite3.OperationalError as e:
        if "interrupted" in str(e):
            return {}
        raise
    finally:
        conn.close()


def _parallel_count_remainder(conn, table, sql, params, lo, base_counts, workers, abort_flag):
    hi =conn.execute(f"SELECT MAX(rowid) FROM {table}").fetchone()[0] or 0
    if lo > hi:
        return dict(base_counts)
    db_path = next((r[2] for r in conn.execute("PRAGMA database_list") if r[1] == "main"), "")
    if not db_path:
        return None
    locked = _SEARCH_POOL_LOCK.acquire(blocking=False)
    if not locked:
        return None
    count = min(workers * 4, hi - lo + 1)
    width = (hi - lo + count) // count
    bounds = [(start, min(start + width - 1, hi)) for start in range(lo, hi + 1, width)]
    futures = None
    try:
        try:
            pool = _search_pool(workers)
            futures = [pool.submit(_count_chunk_worker, db_path, table, sql, params, a, b)
                       for a, b in bounds]
        except (ImportError, OSError, NotImplementedError, BrokenProcessPool):
            return None
        counts = dict(base_counts)
        for i, (a, b) in enumerate(bounds):
            while True:
                if abort_flag and abort_flag[0]:
                    return None
                try:
                    part_counts = futures[i].result(timeout=0.2)
                    futures[i] = None
                    break
                except concurrent.futures.TimeoutError:
                    continue
                except Exception:
                    futures[i] = None
                    part_counts = _count_chunk_worker(db_path, table, sql, params, a, b, abort_flag)
                    break
            for title, n in part_counts.items():
                counts[title] = counts.get(title, 0) + n
        return counts
    finally:
        try:
            _search_pool_done(futures)
        finally:
            _SEARCH_POOL_LOCK.release()


def _count_by_chapters(conn, table, sql, params, abort_flag, search_workers=1, search_delay=10, search_started=None):
    import time
    chapters = conn.execute("SELECT first_rowid, last_rowid, file FROM chapters ORDER BY first_rowid").fetchall()
    if not chapters:
        return None
    deadline = (search_started if search_started is not None else time.monotonic()) + search_delay
    parallel_ok = search_workers > 1 and not _small_table(conn, table)
    if parallel_ok and time.monotonic() >= deadline:
        merged = _parallel_count_remainder(conn, table, sql, params, 1, {}, search_workers, abort_flag)
        if merged is None and abort_flag and abort_flag[0]:
            return None
        if merged is not None:
            return merged
    starts = [c[0] for c in chapters]
    ends = [c[1] for c in chapters]
    names = [_result_folder("epub", c[2]) for c in chapters]
    per_chapter = [0] * len(chapters)
    stray = []
    i, lo, hi = 0, starts[0], ends[0]
    cur = conn.execute(f"SELECT {table}.rowid FROM {table} WHERE {sql}", params)
    while True:
        batch = cur.fetchmany(20000)
        if not batch:
            break
        if abort_flag and abort_flag[0]:
            cur.close()
            return None
        for (rowid,) in batch:
            if not lo <= rowid <= hi:
                i = max(bisect.bisect_right(starts, rowid) - 1, 0)
                lo, hi = starts[i], ends[i]
                if not lo <= rowid <= hi:
                    stray.append(rowid)
                    continue
            per_chapter[i] += 1
        if parallel_ok and time.monotonic() >= deadline:
            base_counts = _finish_chapter_counts(conn, table, names, per_chapter, stray)
            merged = _parallel_count_remainder(conn, table, sql, params, batch[-1][0] + 1,
                                               base_counts, search_workers, abort_flag)
            if merged is None and abort_flag and abort_flag[0]:
                cur.close()
                return None
            if merged is not None:
                cur.close()
                return merged
            parallel_ok = False
    return _finish_chapter_counts(conn, table, names, per_chapter, stray)


_RESULT_FLIGHT = {}
_RESULT_FLIGHT_LOCK = threading.Lock()
_ABORTED = object()


def _result_flight_join(key, abort_flag, held):
    while True:
        with _RESULT_FLIGHT_LOCK:
            ev = _RESULT_FLIGHT.get(key)
            if ev is None:
                ev = _RESULT_FLIGHT[key] = threading.Event()
                held.append((key, ev))
                return None
        while not ev.wait(0.25):
            if abort_flag and abort_flag[0]:
                return _ABORTED
        entry = _result_cache_get(key)
        if entry is not None:
            return entry


def _result_flight_release(held):
    with _RESULT_FLIGHT_LOCK:
        while held:
            key, ev = held.pop()
            if _RESULT_FLIGHT.get(key) is ev:
                del _RESULT_FLIGHT[key]
            ev.set()


SEARCH_COST = {"subtitles": 20e-6, "epubs": 16e-6, "manga": 20e-6, "custom": 20e-6, "pass": 0.0, "like": 0.6e-6, "fixed": 0.5,
               "reading": 0.2e-3}
_READING_SLICES, _READING_SLICE_ROWS = 16, 2000
_SEARCH_PROGRESS = {}
_SEARCH_PROGRESS_LOCK = threading.Lock()


def _file_lookup(conn, table, kind, file):
    from aobana import utils
    if kind == 'epub' and utils.has_chapters(conn):
        return 'SELECT 1 FROM chapters WHERE file = ? LIMIT 1', [file]
    has_sources = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'sources'").fetchone()
    if has_sources and kind == 'subs':
        return 'SELECT 1 FROM sources WHERE relpath = ? LIMIT 1', [file]
    if has_sources and kind == 'manga':
        return 'SELECT 1 FROM sources WHERE title || char(92) || volume = ? LIMIT 1', [file]
    return f'SELECT 1 FROM {table} WHERE file = ? LIMIT 1', [file]


def reader_target(targets, file, rowid=None):
    for table, conn, kind in targets:
        if conn is None:
            continue
        try:
            if rowid is not None:
                sql, params = f'SELECT 1 FROM {table} WHERE file = ? AND rowid = ? LIMIT 1', [file, rowid]
            else:
                sql, params = _file_lookup(conn, table, kind, file)
            if conn.execute(sql, params).fetchone():
                return table, conn, kind
        except sqlite3.OperationalError as error:
            if index_busy(error):
                raise
    return None


def _search_targets(db_subs, db_epub, media, db_manga=None):
    from aobana.utils import media_connections
    dbs = media_connections(db_subs, db_epub, db_manga)
    db_subs, db_epub, db_manga = (dbs.get(m) for m in ('subs', 'epub', 'manga'))
    targets = []
    if media_has(media, 'subs') and db_subs is not None:
        targets.append(('subtitles', db_subs, 'subs'))
    if media_has(media, 'epub') and db_epub is not None:
        targets.append(('epubs', db_epub, 'epub'))
    if media_has(media, 'manga') and db_manga is not None:
        targets.append(('manga', db_manga, 'manga'))
    if media_has(media, 'custom') and dbs.get('custom') is not None:
        targets.append(('custom', dbs['custom'], 'custom'))
    if not targets and db_subs is not None:
        targets.append(('subtitles', db_subs, 'subs'))
    return targets


_COMPUTING = {}
_COMPUTING_LOCK = threading.Lock()


def _computing_enter():
    me = {"shared": False}
    with _COMPUTING_LOCK:
        if _COMPUTING:
            me["shared"] = True
            for other in _COMPUTING.values():
                other["shared"] = True
        _COMPUTING[id(me)] = me
    return me


def _computing_exit(me):
    with _COMPUTING_LOCK:
        _COMPUTING.pop(id(me), None)


def _learn_cost(name, seconds, rows, alone=True, workers=1, min_rows=20000):
    if alone and workers == 1 and rows >= min_rows and seconds > 0:
        SEARCH_COST[name] = 0.7 * SEARCH_COST[name] + 0.3 * (seconds / rows)


def _count_runs(conn, sql, spec, abort_flag=None, budget=0.6):
    runs, params = spec["runs"], spec["params"]
    total_width = sum(hi - lo + 1 for lo, hi in runs) or 1
    t0 = time.monotonic()
    conn.set_progress_handler(
        lambda: 1 if (abort_flag and abort_flag[0]) or (time.monotonic() - t0 > budget) else 0, 5000)
    n = done_width = 0
    try:
        for lo, hi in runs:
            try:
                n += conn.execute(sql, [*params, lo, hi]).fetchone()[0]
            except sqlite3.OperationalError as e:
                if (abort_flag and abort_flag[0]) or "interrupted" not in str(e):
                    raise
                break
            done_width += hi - lo + 1
            if time.monotonic() - t0 > budget:
                break
    finally:
        conn.set_progress_handler(None, 0)
    if done_width < total_width:
        n = n * total_width // done_width if done_width else total_width // 6
    return n


def _reading_candidates(conn, table, sql, params, abort_flag=None):
    max_id = conn.execute(f"SELECT MAX(rowid) FROM {table}").fetchone()[0] or 0
    if max_id <= _READING_SLICES * _READING_SLICE_ROWS:
        return conn.execute(sql, params).fetchone()[0]
    step = max_id // _READING_SLICES
    found = read = 0
    for k in range(_READING_SLICES):
        if abort_flag and abort_flag[0]:
            break
        lo = k * step + 1
        hi = lo + _READING_SLICE_ROWS - 1
        found += conn.execute(f"{sql} AND {table}.rowid BETWEEN ? AND ?", [*params, lo, hi]).fetchone()[0]
        read += _READING_SLICE_ROWS
    return round(found * max_id / read) if read else 0


def search_progress(db_subs, db_epub, q, sort="recommended", seed=None, media="all", exact=False,
                    folder=None, file=None, db_manga=None, status_only=False, abort_flag=None,
                    ruby_only=False, learn=''):
    import time
    targets = _search_targets(db_subs, db_epub, media, db_manga)
    if isinstance(folder, (list, tuple)):
        folder_set = {f for f in folder if f} or None
    else:
        folder_set = {folder} if folder else None
    if q:
        folder_media = None
        if folder_set:
            try:
                _, folder_media = _folder_list_for(targets, abort_flag)
                folder_set = {f for f in folder_set if f in folder_media} or None
            except Exception:
                pass
        key, _ = _search_key(q, sort, seed, media, exact, folder_set, file, targets, folder_media, ruby_only, learn)
        plain = _search_key(q, sort, seed, media, exact, folder_set, file, targets, folder_media, ruby_only)[0] \
            if learn else None
    else:
        key = _result_cache_key(q, sort, seed, media, exact, folder, file, targets, ruby_only)
        plain = None
    with _SEARCH_PROGRESS_LOCK:
        p = _SEARCH_PROGRESS.get(key)
        if p is None and plain is not None:
            p = _SEARCH_PROGRESS.get(plain)
    if p is None:
        return {"running": False}
    now = time.monotonic()
    if status_only:
        return {"running": True, "elapsed": round(now - p["start"], 1),
                "workers": p.get("workers", 1), "delay": p.get("delay", 10)}
    if p.get("expected_rows") is None:
        conns = {table: conn for table, conn, _ in targets}
        rows = {}
        uncounted = False
        for table, sql, params, kind in p["counts"]:
            conn = conns.get(table)
            try:
                if sql is None:
                    rows[table] = ("like", conn.execute(f"SELECT MAX(rowid) FROM {table}").fetchone()[0] or 0)
                elif isinstance(params, dict):
                    rows[table] = ("reading" if kind == "reading" else "match",
                                   _count_runs(conn, sql, params, abort_flag))
                elif kind == "reading" and "_kanji(" not in sql:
                    rows[table] = ("reading", _reading_candidates(conn, table, sql, params, abort_flag))
                else:
                    t0 = time.monotonic()
                    conn.set_progress_handler(
                        lambda: 1 if (abort_flag and abort_flag[0]) or (time.monotonic() - t0 > 0.6) else 0,
                        5000)
                    try:
                        n = conn.execute(sql, params).fetchone()[0]
                    except sqlite3.OperationalError as e:
                        conn.set_progress_handler(None, 0)
                        if abort_flag and abort_flag[0]:
                            raise
                        if "interrupted" not in str(e):
                            raise
                        max_id = conn.execute(f"SELECT MAX(rowid) FROM {table}").fetchone()[0] or 0
                        sample_hi = max(1, max_id // 64)
                        t1 = time.monotonic()
                        conn.set_progress_handler(
                            lambda: 1 if (abort_flag and abort_flag[0]) or (time.monotonic() - t1 > 0.6) else 0,
                            5000)
                        try:
                            sample = conn.execute(f"{sql} AND rowid <= ?", [*params, sample_hi]).fetchone()[0]
                            n = sample * 64
                        except sqlite3.OperationalError:
                            if abort_flag and abort_flag[0]:
                                raise
                            n = max_id // 6
                    finally:
                        conn.set_progress_handler(None, 0)
                    rows[table] = ("reading" if kind == "reading" else "match", n)
            except sqlite3.OperationalError as e:
                if "interrupted" in str(e) and abort_flag and abort_flag[0]:
                    raise
                uncounted = True
            except sqlite3.Error:
                uncounted = True
            except AttributeError:
                rows[table] = ("match", 0)
        if uncounted:
            return {"running": True, "elapsed": round(time.monotonic() - p["start"], 1),
                    "workers": p.get("workers", 1), "delay": p.get("delay", 10)}
        p["expected_rows"] = rows
        now = time.monotonic()
    rows = p["expected_rows"]
    matched = sum(n for kind, n in rows.values() if kind == "match")
    w = max(1, p.get("workers", 1))
    eff_w = min(w, 8)
    finalize_est = matched * (3.3e-6 if w > 1 else 2.0e-6)
    sql_left = 0.0

    def cost(kind, table):
        return SEARCH_COST["like"] if kind == "like" else SEARCH_COST["reading"] if kind == "reading" \
            else SEARCH_COST[table]

    if p["phase"] == "query":
        in_table = now - p["table_start"]
        cur = rows.get(p["table"])
        cur_total = (cur[1] * cost(cur[0], p["table"]) / eff_w) if cur else 0
        rest = sum(n * cost(kind, t) / eff_w
                   for t, (kind, n) in rows.items() if t not in p["sql_seconds"] and t != p["table"])
        done = p["pass_done"]
        if cur and cur[1] > 0 and done >= int(cur[1] * 0.95) and p.get("merge_start") is None:
            p["merge_start"] = now
        p_start = p.get("parallel_start")
        p_base = p.get("parallel_base", 0)
        p_first = p.get("parallel_first_done", 0)
        counted = cur and cur[0] in ("match", "reading")
        if counted and p_start and (done - p_base - p_first) >= 2000 * eff_w and (now - p_start) > 0.35:
            rate = (now - p_start) / (done - p_base - p_first)
            sql_left = max(cur[1] - done, 0) * rate + rest
        elif counted and p_start and (done - p_base) >= 2000 * eff_w:
            rate = max(now - p_start, 0.25) / (done - p_base)
            sql_left = max(cur[1] - done, 0) * rate + rest
        elif counted and done >= 2000 and in_table > 0.5:
            rate = (in_table / done) / (eff_w if w > 1 and p_base > 0 else 1)
            sql_left = max(cur[1] - done, 0) * rate + rest
        else:
            sql_left = max(cur_total - in_table, 0.1 * cur_total) + rest
        m_start = p.get("merge_start")
        pass_left = max(finalize_est - (now - m_start), 0.0) if m_start else finalize_est
    elif p["phase"] == "finalize":
        m_start = p.get("merge_start") or p.get("finalize_start") or now
        pass_left = max(finalize_est - (now - m_start), 0.0)
    elif p["phase"] == "pass":
        done, total = p["pass_done"], p["pass_total"]
        spent = now - p["pass_start"]
        rate = spent / done if done > 1000 else SEARCH_COST["pass"]
        pass_left = (total - done) * rate
    else:
        pass_left = 0.0
    return {"running": True, "elapsed": round(now - p["start"], 1),
            "remaining": round(sql_left + pass_left + SEARCH_COST["fixed"], 1),
            "workers": p.get("workers", 1), "delay": p.get("delay", 10)}


def is_reading_search(q):
    return parse_reading_terms(q)[1:3] != ((), ())


_CUSTOM_ORDER = {}


def _custom_source_order(rows, conn):
    at = [i for i, r in enumerate(rows) if r[_LEAN_MEDIA] == 'custom']
    if len(at) < 2:
        return
    key = db_fingerprint(conn)
    order = _CUSTOM_ORDER.get(key)
    if order is None:
        rank = {sid: n for n, (sid,) in enumerate(conn.execute('SELECT id FROM sources ORDER BY order_key, relpath'))}
        runs = sorted((first, rank.get(sid, len(rank))) for sid, first in
                      conn.execute('SELECT c0, min(id) FROM custom_content GROUP BY c0'))
        order = ([f for f, _ in runs], [r for _, r in runs])
        _CUSTOM_ORDER.clear()
        _CUSTOM_ORDER[key] = order
    firsts, ranks = order
    ordered = sorted((rows[i] for i in at), key=lambda r: (ranks[max(0, bisect.bisect_right(firsts, r[_LEAN_ROWID]) - 1)], r[_LEAN_ROWID]))
    for i, r in zip(at, ordered):
        rows[i] = r


_SUBS_ORDER = {}


def _subs_media_order(rows, conn):
    at = [i for i, r in enumerate(rows) if r[_LEAN_MEDIA] == 'subs']
    if len(at) < 2:
        return
    key = db_fingerprint(conn)
    order = _SUBS_ORDER.get(key)
    if order is None:
        from aobana.indexing import source_ranges
        if not source_ranges.ready(conn):
            return
        from aobana.search.titles import episode_order, get_formatted_title
        ranges = conn.execute('SELECT source_id, first_rowid FROM source_ranges').fetchall()
        shows = {}
        for sid, relpath in conn.execute('SELECT id, relpath FROM sources'):
            shows.setdefault(re.split(r'[\\/]', relpath, 1)[0], []).append(
                {'id': sid, 'file': relpath, 'title': get_formatted_title(conn, relpath)})
        rank = {}
        for show, items in shows.items():
            episode_order(items)
            rank.update((x['id'], (show + x['file'][len(show):len(show) + 1], n)) for n, x in enumerate(items))
        runs = sorted((lo, rank[sid]) for sid, lo in ranges if sid in rank)
        order = ([lo for lo, _ in runs], [r for _, r in runs])
        _SUBS_ORDER.clear()
        _SUBS_ORDER[key] = order
    firsts, ranks = order
    if not firsts:
        return
    ordered = sorted((rows[i] for i in at), key=lambda r: (ranks[max(0, bisect.bisect_right(firsts, r[_LEAN_ROWID]) - 1)], r[_LEAN_ROWID]))
    for i, r in zip(at, ordered):
        rows[i] = r


def get_search_results(db, q, folders=None, sort='recommend', folder=None, exact=False, abort_flag=None, limit=500, offset=0, file=None, db_epub=None, media='all', seed=None, db_manga=None, info=None, search_workers=1, search_delay=10, search_started=None, pins=None, ruby_only=False, learn=''):
    held = []
    progress = []
    computing = []
    if _INDEX_RUN.is_set():
        forget_lexicon_memo()
    try:
        return _search_results(db, q, folders, sort, folder, exact, abort_flag, limit, offset,
                               file, db_epub, media, seed, held, progress, db_manga, info, computing,
                               search_workers=search_workers, search_delay=search_delay,
                               search_started=search_started, pins=pins, ruby_only=ruby_only, learn=learn)
    finally:
        for me in computing:
            _computing_exit(me)
        with _SEARCH_PROGRESS_LOCK:
            for key in progress:
                _SEARCH_PROGRESS.pop(key, None)
        _result_flight_release(held)


_FOLDER_LISTS = {}


def _folder_list_for(targets, abort_flag=None):
    list_key = (tuple(m for _, c, m in targets if c is not None),
                db_fingerprint(*[c for _, c, _ in targets if c is not None]))
    listed = _FOLDER_LISTS.get(list_key)
    if listed is not None:
        return listed
    all_folders_set = set()
    folder_media = {}
    for table_name, db_conn, m_type in targets:
        if db_conn is None:
            continue
        if abort_flag and abort_flag[0]:
            raise sqlite3.OperationalError("interrupted")
        try:
            if m_type == 'epub':
                cur = db_conn.execute("SELECT relpath, title FROM sources")
                for r in cur:
                    title = r["title"]
                    f_name = title if title else (r["relpath"][:-5] if r["relpath"].lower().endswith(".epub") else r["relpath"])
                    all_folders_set.add(f_name)
                    folder_media.setdefault(f_name, set()).add(m_type)
            elif m_type == 'custom':
                for r in db_conn.execute('SELECT DISTINCT category FROM sources'):
                    all_folders_set.add(r['category'])
                    folder_media.setdefault(r['category'], set()).add(m_type)
            elif m_type == 'manga':
                for r in db_conn.execute("SELECT DISTINCT title FROM sources"):
                    all_folders_set.add(r["title"])
                    folder_media.setdefault(r["title"], set()).add(m_type)
            else:
                cur = db_conn.execute("SELECT relpath FROM sources")
                for r in cur:
                    f_name = re.split(r"[\\/]", r["relpath"])[0]
                    all_folders_set.add(f_name)
                    folder_media.setdefault(f_name, set()).add(m_type)
        except sqlite3.OperationalError as e:
            if "interrupted" in str(e) or (abort_flag and abort_flag[0]) or index_busy(e):
                raise
        except Exception:
            if abort_flag and abort_flag[0]:
                raise sqlite3.OperationalError("interrupted")
    if abort_flag and abort_flag[0]:
        raise sqlite3.OperationalError("interrupted")
    listed = (sorted(all_folders_set, key=get_sort_key), folder_media)
    if len(_FOLDER_LISTS) > 8:
        _FOLDER_LISTS.clear()
    _FOLDER_LISTS[list_key] = listed
    return listed


def _search_results(db, q, folders, sort, folder, exact, abort_flag, limit, offset, file, db_epub, media, seed, held, progress=None, db_manga=None, info=None, computing=None, search_workers=1, search_delay=10, search_started=None, scan_bounds=None, scan_only=False, pins=None, ruby_only=False, learn=''):
    import time
    if search_started is None:
        search_started = time.monotonic()
    neg_info = []
    clean_q = ""
    content_bases = []
    readings = []
    cache_key = cached = cached_page = None
    entry = None

    if isinstance(db, dict):
        db_subs, db_epub, db_manga = (db.get(m) for m in ('subs', 'epub', 'manga'))
    elif isinstance(db, (tuple, list)):
        db_subs = db[0] if len(db) > 0 else None
        if len(db) > 1 and db_epub is None:
            db_epub = db[1]
        if len(db) > 2 and db_manga is None:
            db_manga = db[2]
    else:
        db_subs = db

    if db_epub is not None and not scan_only:
        load_book_authors(db_epub)

    dbs = db if isinstance(db, dict) else {'subs': db_subs, 'epub': db_epub, 'manga': db_manga}
    targets = _search_targets(dbs, db_epub, media, db_manga)

    if isinstance(folder, (list, tuple)):
        folder_set = {f for f in folder if f} or None
    else:
        folder_set = {folder} if folder else None
    if isinstance(pins, (list, tuple, set)):
        pin_list = [f for f in pins if f]
    elif pins:
        pin_list = [pins]
    else:
        pin_list = []
    if not q:
        folder = next(iter(folder_set)) if folder_set and len(folder_set) == 1 else None

    all_folders_list = ()
    folder_media = {}
    if not scan_only and (not q or folder_set or pin_list):
        try:
            all_folders_list, folder_media = _folder_list_for(targets, abort_flag)
        except sqlite3.OperationalError as e:
            if "interrupted" in str(e) or (abort_flag and abort_flag[0]):
                return [], {}, 0, [], False
            raise
        checked_folders = list(dict.fromkeys([*(folder_set or ()), *pin_list]))
        outside_media = [f for f in checked_folders if f not in folder_media]
        if info is not None:
            info["outside_media"] = outside_media
    elif info is not None:
        info["outside_media"] = []

    if not q:
        all_folders = list(all_folders_list)
        by_media = {m_type: (table_name, db_conn, m_type) for table_name, db_conn, m_type in targets}
        global_counts = {f: 0 for f in all_folders}
        if not folder or folder not in folder_media:
            return [], global_counts, 0, all_folders, False

        m_types = folder_media.get(folder) or ()
        candidates = [target for target in targets if target[2] in m_types]
        target_info = reader_target(candidates, file) if file else None
        if target_info is None:
            target_info = next(iter(candidates), None)
        if target_info:
            target_table, target_db, target_media = target_info
        else:
            target_table, target_db, target_media = targets[0]

        folder_sql, folder_params = folder_prefix_where("file", folder)
        if target_media == 'custom':
            folder_sql = 'source_id IN (SELECT id FROM sources WHERE category = ?)'
            folder_params = [folder]
        folder_where = "WHERE " + folder_sql
        if file:
            where_clause = "WHERE file = ?"
            query_params = [file]
        else:
            where_clause, query_params = folder_where, folder_params

        fingerprint = db_fingerprint(target_db)
        from aobana import utils
        if target_media == 'epub' and utils.has_chapters(target_db):
            spans = target_db.execute(
                "SELECT file, first_rowid, last_rowid, lines FROM chapters WHERE " + folder_sql,
                folder_params).fetchall()
            mine = [s for s in spans if not file or s[0] == file]
            if not mine:
                return [], {**global_counts, folder: 0}, 0, all_folders, False
            lo, hi = min(s[1] for s in mine), max(s[2] for s in mine)
            folder_where = "WHERE rowid BETWEEN ? AND ? AND " + folder_sql
            folder_params = [min(s[1] for s in spans), max(s[2] for s in spans)] + folder_params
            if file:
                where_clause, query_params = "WHERE rowid BETWEEN ? AND ? AND file = ?", [lo, hi, file]
            else:
                where_clause, query_params = folder_where, folder_params
            chapter_counts = {folder: sum(s[3] for s in spans)}
            if file:
                chapter_counts[(folder, file)] = sum(s[3] for s in mine)
        else:
            chapter_counts = {}
            m_runs = _source_runs(target_db, target_table, target_media, {folder})
            if m_runs is not None:
                if not m_runs:
                    return [], {**global_counts, folder: 0}, 0, all_folders, False
                bounds = []
                for lo, hi, _ in sorted(m_runs):
                    if bounds and lo <= bounds[-1][1] + 1:
                        bounds[-1][1] = max(bounds[-1][1], hi)
                    else:
                        bounds.append([lo, hi])
                if len(bounds) > 250:
                    bounds = [[min(r[0] for r in bounds), max(r[1] for r in bounds)]]
                range_sql = " OR ".join("rowid BETWEEN ? AND ?" for _ in bounds)
                range_params = [x for r in bounds for x in r]
                folder_where = f"WHERE ({range_sql}) AND {folder_sql}"
                folder_params = range_params + folder_params
                if file:
                    where_clause, query_params = f"WHERE ({range_sql}) AND file = ?", range_params + [file]
                else:
                    where_clause, query_params = folder_where, folder_params

        def cached_count(key, where, params):
            if key in chapter_counts:
                return chapter_counts[key]
            key = (key, fingerprint)
            if key not in GLOBAL_FOLDER_COUNTS:
                GLOBAL_FOLDER_COUNTS[key] = target_db.execute(f"SELECT COUNT(rowid) FROM {target_table} {where}", params).fetchone()[0]
            return GLOBAL_FOLDER_COUNTS[key]

        try:
            global_counts[folder] = cached_count(folder, folder_where, folder_params)
            total_in_folder = cached_count((folder, file), where_clause, query_params) if file else global_counts[folder]
            query = f"SELECT rowid, line, file, clean_text, readings, base_forms FROM {target_table} {where_clause} ORDER BY file ASC, rowid ASC LIMIT ? OFFSET ?"
            cur = target_db.execute(query, query_params + [limit, offset])
            rows = cur.fetchall()
            
            results = []
            for r in rows:
                row_dict = dict(r)
                row_dict["media_type"] = target_media
                row_dict["folder"] = folder
                row_dict["score"] = 1.0
                row_dict["char_count"] = calculate_display_length(row_dict["line"], target_media)
                row_dict["title"] = title_of(target_media, row_dict["file"], target_db, db_epub)
                line = row_dict["line"]
                row_dict["display_line"] = highlight_and_furigana(line, [], "", mark=False, bold=False, work=work_key(target_media, row_dict["file"]))
                if target_media == 'custom':
                    from aobana.search.custom import decorate_result
                    decorate_result(row_dict, target_db, {})
                results.append(row_dict)
            add_manga_pages(results, db_manga)

            has_more = (offset + len(rows)) < total_in_folder
            db_total = get_db_total(dbs, db_epub, media, db_manga)
            return results, global_counts, db_total, all_folders, has_more
        except sqlite3.OperationalError as e:
            if "interrupted" in str(e) or (abort_flag and abort_flag[0]) or index_busy(e):
                raise
            db_total = get_db_total(dbs, db_epub, media, db_manga)
            return [], global_counts, db_total, all_folders, False
    else:
        q_plain, r_terms, r_neg, q_rest = parse_reading_terms(q)
        pos_q, neg_terms = split_negated_terms(q_plain)
        literal_terms = literal_equal_terms(q_rest)
        is_exact_phrase =exact or (pos_q.startswith('"') and pos_q.endswith('"')) or (pos_q.startswith('”') and pos_q.endswith('”'))
        clean_q = pos_q.strip('""“”')
        
        if not clean_q:
            return [], {}, 0, [], False

        if not scan_only and folder_set:
            in_media_folders = {f for f in folder_set if f in folder_media}
            if not in_media_folders:
                return [], {f: 0 for f in folder_set}, None, list(all_folders_list), False
            folder_set = in_media_folders
        
        script_type = detect_script(clean_q)
        content_bases, sql_bases, readings, base_groups = analyze_query(clean_q)
        bound = None if is_exact_phrase else bound_auxiliary(clean_q)
        
        rest_clean, rest_query, term_queries = "", None, []
        if r_terms:
            rest_clean = split_negated_terms(q_rest)[0].strip('""“”')
            rest_query = analyze_query(rest_clean) if rest_clean else None
            content_bases = content_bases + sorted({l for t in r_terms for s in t.lemmas for l in s})
            term_queries = [(t.word, analyze_query(t.word), detect_script(t.word),
                             " OR ".join(f'base_forms:{fts_phrase(lemma)}' for lemma in sorted(t.lemmas[0]))
                             if len(t.lemmas) == 1 else "")
                            for t in r_terms]

        neg_info = []
        for neg in neg_terms:
            neg_clean = neg.strip('""“”')
            if neg_clean:
                neg_info.append({
                    'term': neg_clean,
                    'subs_term': media_query(neg_clean, 'subs'),
                    'sequences': {kind: excluded_sequence(neg_clean, kind) for _, _, kind in targets},
                })
        
        global_counts = {}
        valid_results = []
        folder_counts = {}

        def pass1(r, m_type):
            line, clean_text, row_readings, row_bases = r[1], r[3], r[4], r[5]
            subs = (m_type or 'subs') == 'subs'
            row_q = subs_q if subs else clean_q
            for n in neg_info:
                term = n['subs_term'] if subs else n['term']
                if term in clean_text or term in line:
                    return None
                sequence = n['sequences'].get(m_type or 'subs', '')
                if sequence and (' ' + sequence + ' ') in (' ' + (row_bases or '') + ' '):
                    return None
            if bound and bound_auxiliary_in_row(bound, row_bases, row_readings) is False:
                return None
            if (not r_terms and not is_exact_phrase and ' ' not in clean_q
                    and any(len(g) > 1 for g in base_groups)
                    and row_q not in (clean_text if m_type == 'custom' else line)
                    and not drawn_sequence_matches(line, base_groups, work_key(m_type or 'subs', r[2]))):
                return None
            is_exact = row_q in line_text(clean_text, m_type)
            if not is_exact and readings:
                if row_readings and q_reading in row_readings.replace(" ", ""):
                    is_exact = True
            if len(row_q) > 0 and not is_exact:
                for cb in content_bases:
                    if cb in clean_text or (row_readings and cb in row_readings) or (row_bases and cb in row_bases):
                        break
                else:
                    return None
            if r_terms or r_neg:
                work = work_key(m_type or "subs", r[2])
                if (r_terms and READING_PREFILTER
                        and not reading_prefilter(r_terms, line, clean_text, row_readings, m_type or "subs", work,
                                                  row_bases, r[7])):
                    return None
                if not row_matches(line_analysis(line, work), r_terms, r_neg, work, is_exact_phrase, ruby_only):
                    return None
            native = subs and has_native_ruby(line)
            char_count = r[6] if r[6] is not None and not native else calculate_display_length(line, m_type or "subs")
            return (line, r[0], m_type, _result_folder(m_type, r[2]),
                    sentence_score(line, row_q, is_exact, char_count), char_count)
        q_reading = "".join(readings)
        subs_q = media_query(clean_q, 'subs')

        learn_mode = learn_vocab = learn_target = row_typed = None
        target_known = False
        one_word = not (r_neg or is_exact_phrase) and len(r_terms) <= 1 and ' ' not in clean_q.strip()
        if not learn and one_word and not scan_only:
            learn_vocab = iplusone.current()
            learn_target = _learn_target(clean_q) if learn_vocab is not None else None
            if not learn_target:
                learn_vocab = learn_target = None
        if learn:
            learn_mode, learn_vocab = iplusone.resolve(learn)
            if one_word:
                learn_target = _learn_target(clean_q)
            if not learn_target:
                learn_mode = learn_vocab = None
        if learn_target:
            if not r_terms:
                row_typed = iplusone.typed_reading(clean_q, learn_target)
            target_known = learn_vocab.knows(learn_target)
        if learn:
            if info is not None:
                info["learn"] = {"mode": learn_mode or "off", "unsupported": learn_mode is None,
                                 "target_known": target_known}
            if learn_mode is None:
                learn = ''
        if learn_mode is not None:
            plain_pass1 = pass1
            grouped = sort == "recommended"
            stop = 1 if target_known else 0

            def pass1(r, m_type):
                got = plain_pass1(r, m_type)
                if got is None:
                    return None
                units = iplusone.row_units(r[5], r[3], m_type or 'subs')
                if learn_mode == 'only':
                    if not iplusone.classify(units, learn_target, learn_vocab, target_known, row_typed,
                                             r[4], r[3], stop_at=stop)[0]:
                        return None
                    return got
                i1, known, total, other = iplusone.classify(units, learn_target, learn_vocab, target_known,
                                                            row_typed, r[4], r[3])
                if grouped:
                    score = iplusone.first_score(sentence_score(got[_LEAN_LINE], '', False, got[_LEAN_CHARS]),
                                                 i1, known, total, other)
                else:
                    score = 1.0 if i1 else -1.0 if other else 0.0
                return got[:_LEAN_SCORE] + (score,) + got[_LEAN_SCORE + 1:]

        cache_key, runs = _search_key(q, sort, seed, media, exact, folder_set, file, targets, folder_media, ruby_only, learn)
        if scan_only:
            cache_key = None
            runs = None
        scan_targets = targets
        if runs is not None:
            scan_targets = [t for t in targets if t[1] is not None
                            and any(t[2] in folder_media.get(f, ()) for f in (folder_set or ()))]
            if info is not None:
                info["scoped"] = True
        cached = _result_cache_get(cache_key)
        if cached is None and cache_key is not None:
            cached = _result_flight_join(cache_key, abort_flag, held)
            if cached is _ABORTED:
                return [], {}, 0, [], False
        if cached is not None:
            if folder_set:
                names = cached["folders"]
                cached_sel = [i for i, fi in enumerate(cached["fidx"]) if names[fi] in folder_set]
            else:
                cached_sel = range(len(cached["rowid"]))
            cached_page = _result_cache_page(cached, cached_sel[offset:offset + limit], targets,
                                             keep_text=learn_vocab is not None)
        if cached_page is None:
            cached = None

        kanji_ok = ({t: c is not None and _kanji_ready(c, t) for t, c, _ in targets} if r_terms else {})

        def kanji_lead(table_name, wheres, where_params, terms):
            if not kanji_ok.get(table_name) or any("MATCH" in w and "rowid IN" not in w for w in wheres):
                return
            from aobana.indexing import kanji_table
            for word, match in terms:
                k = kanji_table.query(word)
                if k is None:
                    continue
                kanji_sql = f"SELECT rowid FROM {kanji_table.name(table_name)}(?)"
                if match:
                    wheres.insert(0, f"{table_name}.rowid IN (SELECT rowid FROM {table_name} WHERE {match[0]}"
                                     f" UNION ALL {kanji_sql})")
                    where_params[0:0] = [*match[1], k]
                else:
                    wheres.insert(0, f"{table_name}.rowid IN ({kanji_sql})")
                    where_params[0:0] = [k]
                return

        def build_where(table_name):
            wheres = []
            where_params = []
            own = (lambda s: media_query(s, 'subs')) if table_name == 'subtitles' else (lambda s: s)

            def exact_where(phrase, bases, phrase_readings):
                match_str = " AND ".join(bases)
                if match_str:
                    wheres.append(f"{table_name} MATCH ?")
                    where_params.append(match_str)
                elif phrase_readings:
                    match_str = fts_phrase(" ".join(phrase_readings))
                    if match_str != '""':
                        wheres.append(f"{table_name} MATCH ?")
                        where_params.append(f"readings: {match_str}")
                if '=' in phrase or '＝' in phrase:
                    wheres.append("instr(replace(clean_text, '=', '＝'), ?) > 0")
                    where_params.append(own(phrase).replace('=', '＝'))
                else:
                    wheres.append("instr(clean_text, ?) > 0")
                    where_params.append(own(phrase))

            if is_exact_phrase and r_terms:
                if rest_clean:
                    exact_where(rest_clean, rest_query[1], rest_query[2])
                for word, *_ in term_queries:
                    wheres.append("instr(clean_text, ?) > 0")
                    where_params.append(word)
                kanji_lead(table_name, wheres, where_params, [(word, None) for word, *_ in term_queries])
            elif is_exact_phrase:
                exact_where(clean_q, sql_bases, readings)
            elif r_terms:
                if rest_clean:
                    match = _match_where(table_name, rest_query[1], rest_query[2], detect_script(rest_clean))
                    if match:
                        wheres.append(match[0])
                        where_params.extend(match[1])
                    else:
                        wheres.append("line LIKE ? ESCAPE char(92)")
                        where_params.append(f"%{like_escape(own(rest_clean))}%")
                term_matches = []
                for word, term_query, term_script, lemmas in term_queries:
                    match = _match_where(table_name, term_query[1], term_query[2], term_script)
                    if match and lemmas:
                        match = (match[0], [f'({match[1][0]}) OR ({lemmas})'])
                    if match:
                        wheres.append(f"({table_name}.rowid IN (SELECT rowid FROM {table_name} WHERE {match[0]})"
                                      " OR instr(clean_text, ?) > 0)")
                        where_params.extend(match[1])
                    else:
                        wheres.append("instr(clean_text, ?) > 0")
                    where_params.append(word)
                    term_matches.append((word, match))
                kanji_lead(table_name, wheres, where_params, term_matches)
            else:
                match = _match_where(table_name, sql_bases, readings, script_type)
                if match:
                    wheres.append(match[0])
                    where_params.extend(match[1])
                else:
                    wheres.append("line LIKE ? ESCAPE char(92)")
                    where_params.append(f"%{like_escape(own(clean_q))}%")

            for phrase in literal_terms:
                wheres.append("instr(replace(clean_text, '=', '＝'), ?) > 0")
                where_params.append(own(phrase).replace('=', '＝'))
            for n in neg_info:
                wheres.append("instr(clean_text, ?) = 0")
                where_params.append(own(n['term']))
                wheres.append("instr(line, ?) = 0")
                where_params.append(own(n['term']))
                kind = next(kind for table, _, kind in targets if table == table_name)
                sequence = n['sequences'].get(kind, '')
                if sequence:
                    wheres.append("instr(' ' || base_forms || ' ', ?) = 0")
                    where_params.append(' ' + sequence + ' ')

            if file:
                wheres.append("file = ?")
                where_params.append(file)
            elif folder and not q:
                folder_sql, folder_params = folder_prefix_where("file", folder)
                wheres.append(folder_sql)
                where_params.extend(folder_params)
            if scan_bounds is not None:
                wheres.append(f"{table_name}.rowid BETWEEN ? AND ?")
                where_params.extend(scan_bounds)
            match = None
            if r_terms or r_neg:
                match = (f"SELECT count(*) FROM {table_name} WHERE {' AND '.join(wheres)}", where_params,
                         "reading")
            elif wheres and "MATCH" in wheres[0]:
                n_params = wheres[0].count("?")
                match = (f"SELECT count(*) FROM {table_name} WHERE {wheres[0]}", where_params[:n_params], "match")
            return wheres, where_params, match

        def _count_sql(table_name, m_type):
            match = build_where(table_name)[2]
            m_runs = runs.get(m_type) if isinstance(runs, dict) else runs
            if match is None or not m_runs:
                return match or (None, None, None)
            m_sql, m_params, kind = match
            return (f"{m_sql} AND rowid BETWEEN ? AND ?",
                    {"params": list(m_params), "runs": [(lo, hi) for lo, hi, _ in m_runs]}, kind)

        if cached is None and cache_key is not None and progress is not None:
            now = time.monotonic()
            entry = {"start": search_started or now, "phase": "query", "table": None, "table_start": now,
                     "sql_seconds": {}, "pass_done": 0, "pass_base": 0, "pass_total": 0, "pass_start": None,
                     "workers": 1, "delay": search_delay,
                     "expected_rows": None,
                     "counts": [(t, *_count_sql(t, m)) for t, c, m in scan_targets if c is not None]}
            with _SEARCH_PROGRESS_LOCK:
                _SEARCH_PROGRESS[cache_key] = entry
            progress.append(cache_key)
        else:
            entry = None

        compute_start = time.monotonic()
        if cached is None and computing is not None:
            computing.append(_computing_enter())
        scan_raw_lines = set() if scan_only else None
        total_seen = 0
        parallel_ok = (not scan_only and search_workers > 1 and sort != "chrono"
                       and runs is None and not file)
        deadline = search_started + search_delay
        for table_name, db_conn, m_type in (scan_targets if cached is None else ()):
            if db_conn is None: continue
            if abort_flag and abort_flag[0]:
                return ([], {}, set(), 0) if scan_only else ([], {}, 0, [], False)
            wheres, where_params, _ = build_where(table_name)
            if entry is not None:
                entry["table"], entry["table_start"] = table_name, time.monotonic()
                entry["pass_done"] = entry["pass_base"] = 0
                entry["workers"] = 1
                entry["parallel_start"] = None
                entry["parallel_base"] = 0
                entry["parallel_first_done"] = 0
                entry["merge_start"] = None

            where_clause = f"WHERE ({' AND '.join(wheres)})"
            cols = _scan_columns(db_conn, table_name, bool(r_terms))
            plain_cols = cols
            table_counts = {}
            f_filter = folder_set if runs is not None else None
            m_runs = runs.get(m_type) if isinstance(runs, dict) else (runs if m_type == "epub" else None)
            table_workers = search_workers if search_workers > 1 and not _small_table(db_conn, table_name) else 1
            table_parallel = parallel_ok and table_workers > 1
            if entry is not None:
                entry.pop('chrono_deadline', None)
            if entry is not None and not scan_only and q and sort == 'chrono' and table_workers > 1 and not file:
                entry['chrono_deadline'] = deadline
            try:
                chrono_parallel = None
                if not scan_only and q and sort == 'chrono' and table_workers > 1 and not file and time.monotonic() >= deadline:
                    chrono_parallel = _parallel_chrono_runs(db_conn,table_name,m_type,q,exact,seed,m_runs,folder_set,search_workers,abort_flag,entry,ruby_only,learn)
                if chrono_parallel is not None:
                    lean, seen, table_counts = chrono_parallel
                elif m_runs is None:
                    if table_parallel and time.monotonic() >= deadline:
                        merged = _parallel_scan_remainder(
                            db_conn, table_name, m_type, q, sort, exact, seed, 1, [],
                            table_counts, set(), search_workers, abort_flag, entry, ruby_only, learn)
                        if merged is None and abort_flag and abort_flag[0]:
                            return [], {}, 0, [], False
                        if merged is not None:
                            lean, table_counts, seen = merged
                        else:
                            table_counts.clear()
                            lean, seen = _scan_rows(db_conn, cols, where_clause, where_params,
                                                    sort, m_type, pass1, abort_flag, entry, table_counts,
                                                    folder_filter=f_filter)
                    else:
                        split_state = {"deadline": deadline} if table_parallel else None
                        lean, seen = _scan_rows(db_conn, cols, where_clause, where_params, sort,
                                                m_type, pass1, abort_flag, entry, table_counts,
                                                raw_lines=scan_raw_lines, split_state=split_state,
                                                folder_filter=f_filter)
                        if split_state is not None and "next_rowid" in split_state:
                            if entry is not None:
                                entry["pass_done"] = seen
                            merged = _parallel_scan_remainder(
                                db_conn, table_name, m_type, q, sort, exact, seed,
                                split_state["next_rowid"], lean, table_counts,
                                split_state["raw_lines"], search_workers, abort_flag, entry, ruby_only, learn)
                            if merged is None and abort_flag and abort_flag[0]:
                                return [], {}, 0, [], False
                            if merged is not None:
                                lean, table_counts, tail_seen = merged
                                seen += tail_seen
                            else:
                                table_counts.clear()
                                lean, seen = _scan_rows(db_conn, cols, where_clause,
                                                        where_params, sort, m_type, pass1,
                                                        abort_flag, entry, table_counts,
                                                        folder_filter=f_filter)
                else:
                    lean, seen = _scan_runs(db_conn, cols, where_clause, where_params, m_runs, table_name,
                                            sort, m_type, pass1, abort_flag, entry, table_counts,
                                            folder_filter=f_filter)
            except _ChronoHandoff:
                entry.pop('chrono_deadline',None)
                combined = _parallel_chrono_runs(db_conn,table_name,m_type,q,exact,seed,m_runs,folder_set,search_workers,abort_flag,entry,ruby_only,learn)
                if combined is not None:
                    lean,seen,table_counts = combined
                else:
                    table_counts.clear()
                    if m_runs is not None:
                        lean,seen = _scan_runs(db_conn,cols,where_clause,where_params,m_runs,table_name,sort,m_type,pass1,abort_flag,entry,table_counts,folder_filter=f_filter)
                    else:
                        lean,seen = _scan_rows(db_conn,cols,where_clause,where_params,sort,m_type,pass1,abort_flag,entry,table_counts)
            except sqlite3.OperationalError as e:
                if "interrupted" in str(e):
                    raise
                if index_busy(e) or not fts_query_error(e):
                    raise
                print(f"search: {table_name} MATCH failed ({e}); retried as LIKE", file=sys.stderr)
                fallback_wheres = ["line LIKE ? ESCAPE char(92)"]
                fallback_params = [f"%{like_escape(media_query(clean_q, m_type))}%"]
                for n in neg_info:
                    fallback_wheres.append("instr(line, ?) = 0")
                    fallback_params.append(n['term'])
                if file:
                    fallback_wheres.append("file = ?")
                    fallback_params.append(file)
                if scan_bounds is not None:
                    fallback_wheres.append(f"{table_name}.rowid BETWEEN ? AND ?")
                    fallback_params.extend(scan_bounds)
                fb_clause = f"WHERE ({' AND '.join(fallback_wheres)})"
                table_counts.clear()
                try:
                    if m_runs is not None:
                        lean, seen = _scan_runs(db_conn, plain_cols, fb_clause, fallback_params, m_runs, table_name,
                                                sort, m_type, pass1, abort_flag, entry, table_counts,
                                                folder_filter=f_filter)
                    else:
                        lean, seen = _scan_rows(db_conn, plain_cols, fb_clause, fallback_params, sort, m_type,
                                                pass1, abort_flag, entry, table_counts,
                                                raw_lines=scan_raw_lines, folder_filter=f_filter)
                except sqlite3.OperationalError as e2:
                    if "interrupted" in str(e2) or index_busy(e2):
                        raise
                    print(f"search: {table_name} LIKE failed too ({e2})", file=sys.stderr)
                    lean, seen = [], 0
                except Exception as e2:
                    print(f"search: {table_name} LIKE failed too ({e2!r})", file=sys.stderr)
                    lean, seen = [], 0
            if lean is None:
                return ([], {}, set(), 0) if scan_only else ([], {}, 0, [], False)
            total_seen += seen
            valid_results.extend(lean)
            for f, count in table_counts.items():
                folder_counts[f] = folder_counts.get(f, 0) + count
            if entry is not None:
                spent = time.monotonic() - entry["table_start"]
                entry["sql_seconds"][table_name] = spent
                alone = not (computing and computing[-1]["shared"])
                if r_terms or r_neg:
                    _learn_cost("reading", spent, seen, alone=alone, workers=entry.get("workers", 1), min_rows=2000)
                elif "MATCH" in wheres[0]:
                    _learn_cost(table_name, spent, seen, alone=alone, workers=entry.get("workers", 1))

    if scan_only:
        return valid_results, folder_counts, scan_raw_lines, total_seen

    results = []
    global_total = 0

    if entry is not None:
        entry["phase"] = "finalize"
        entry["finalize_start"] = time.monotonic()
    if sort == "desc":
        valid_results.sort(key=lambda x: x[_LEAN_CHARS], reverse=True)
    elif sort == "asc":
        valid_results.sort(key=lambda x: x[_LEAN_CHARS], reverse=False)
    elif sort == "random":
        (random.Random(seed) if seed is not None else random).shuffle(valid_results)
    elif sort == "chrono":
        if dbs.get('subs') is not None:
            _subs_media_order(valid_results, dbs['subs'])
        if dbs.get('custom') is not None:
            _custom_source_order(valid_results, dbs['custom'])
    else:
        valid_results.sort(key=lambda x: x[_LEAN_SCORE], reverse=True)
    if cached is None and learn_mode == 'first' and sort != "recommended":
        valid_results = ([x for x in valid_results if x[_LEAN_SCORE] > 0.5]
                         + [x for x in valid_results if -0.5 <= x[_LEAN_SCORE] <= 0.5]
                         + [x for x in valid_results if x[_LEAN_SCORE] < -0.5])
    if cached is None:
        cached = _result_entry(valid_results, folder_counts)
        valid_results = None
        _result_cache_put(cache_key, cached, time.monotonic() - compute_start)
        _result_flight_release(held)
        if folder_set:
            names = cached["folders"]
            cached_sel = [i for i, fi in enumerate(cached["fidx"]) if names[fi] in folder_set]
        else:
            cached_sel = range(len(cached["rowid"]))
        cached_page = _result_cache_page(cached, cached_sel[offset:offset + limit], targets,
                                         keep_text=learn_vocab is not None) or []
    if entry is not None:
        entry["phase"] = "render"
    paginated_chunk = cached_page
    folder_counts = dict(cached["folder_counts"])
    n_valid = len(cached_sel)

    hl_by_media = {}
    for row_dict in paginated_chunk:
        if abort_flag and abort_flag[0]:
            return [], {}, 0, [], False
            
        row_dict["title"] = title_of(row_dict.get("media_type"), row_dict["file"], db_subs, db_epub)
        line = row_dict["line"]
        m_type = row_dict.get("media_type") or "subs"
        if learn_vocab is not None:
            clean = row_dict.pop("clean_text", "") or ""
            i1, known, total, _ = iplusone.classify(iplusone.row_units(row_dict.get("base_forms"), clean, m_type),
                                                    learn_target, learn_vocab, target_known, row_typed,
                                                    row_dict.get("readings") or "", clean)
            row_dict["knowledge"] = {"known": known, "total": total, "i1": i1}
        hl = hl_by_media.get(m_type)
        if hl is None:
            hl = hl_by_media[m_type] = query_highlight_args(q, m_type)
        row_dict["display_line"] = highlight_and_furigana(line, hl["content_bases"], hl["q"], mark=False, bold=True, base_groups=hl["base_groups"], readings=hl["readings"], reading_terms=hl["reading_terms"], mark_guessed=True, work=work_key(row_dict.get("media_type") or "subs", row_dict["file"]))
        if m_type == 'custom':
            from aobana.search.custom import decorate_result
            decorate_result(row_dict, dbs['custom'], hl)
        results.append(row_dict)
    add_manga_pages(results, db_manga)

    if q:
        global_counts = folder_counts
        all_folders = sorted(global_counts.keys(), key=lambda f: global_counts[f], reverse=True)
        global_total = sum(global_counts.values())
    else:
        global_total = get_db_total(dbs, db_epub, media, db_manga)
    has_more = (offset + limit) < n_valid
    return results, global_counts, global_total, all_folders, has_more


def reset_caches():
    _retire_search_pool()
    drop_lexicon()
    GLOBAL_BOOK_TITLES.clear()
    GLOBAL_BOOK_AUTHORS.clear()
    GLOBAL_TITLES.clear()
    GLOBAL_MANGA_TITLES.clear()
    GLOBAL_DB_TOTALS.clear()
    GLOBAL_FOLDER_COUNTS.clear()
