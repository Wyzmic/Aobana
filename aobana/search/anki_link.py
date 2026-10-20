import json
import time
import urllib.error
import urllib.request

from aobana import paths
from aobana.search import known_words

PROTOCOL = 1
DEFAULT_PORT = 5020
RULES = ("mature", "reviewed", "all")
DEFAULT_IVL = 21
TIMEOUT_HELLO_S = 3
TIMEOUT_DECKS_S = 30
TIMEOUT_WORDS_S = 180
SAMPLE = 10


class AnkiError(Exception):

    def __init__(self, code, **detail):
        super().__init__(code)
        self.code = code
        self.detail = detail


def port():
    try:
        value = int(paths.load_config().get("reibun_port", DEFAULT_PORT))
    except (TypeError, ValueError):
        return DEFAULT_PORT
    return value if 1024 <= value <= 65535 else DEFAULT_PORT


def _call(method, path, body=None, timeout=TIMEOUT_DECKS_S):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{port()}{path}", data=data, method=method,
                                 headers={"X-Aobana": "1", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        try:
            code = json.loads(error.read().decode("utf-8")).get("error")
        except (ValueError, AttributeError, UnicodeDecodeError):
            code = None
        if error.code == 503 and code == "no_collection":
            raise AnkiError("anki_no_profile")
        if error.code == 503:
            raise AnkiError("anki_busy")
        if error.code in (403, 404):
            raise AnkiError("anki_old")
        raise AnkiError("anki_error")
    except (urllib.error.URLError, OSError, ValueError):
        raise AnkiError("anki_closed")


def hello():
    got = _call("GET", "/hello", timeout=TIMEOUT_HELLO_S)
    if not isinstance(got, dict) or got.get("app") != "aobana-reibun" or got.get("protocol") != PROTOCOL:
        raise AnkiError("anki_old")
    if not got.get("ready"):
        raise AnkiError("anki_no_profile")
    return {"version": got.get("version") or "", "profile": got.get("profile") or ""}


def decks():
    who = hello()
    got = _call("GET", "/decks")
    return {**who, "decks": got.get("decks") or []}


def _anki_sources():
    out = []
    for rec in known_words._read_sources():
        sel = (rec.get("meta") or {}).get("anki")
        if rec.get("origin") == "anki" and isinstance(sel, dict):
            out.append((float(sel.get("chosen") or 0), rec["id"], sel))
    return sorted(out, key=lambda x: x[0], reverse=True)


def guess_fields(fields, saved=None):
    if saved and saved.get("expression") in fields and (not saved.get("reading") or saved["reading"] in fields):
        return saved["expression"], saved.get("reading") or ""
    low = [f.strip().lower() for f in fields]
    word = next((fields[i] for i, f in enumerate(low) if f in known_words._EXPRESSION_NAMES), fields[0] if fields else "")
    reading = next((fields[i] for i, f in enumerate(low) if f in known_words._READING_NAMES and fields[i] != word), "")
    return word, reading


def note_types(deck_ids, subdecks=True):
    hello()
    got = _call("POST", "/fields", {"decks": [int(d) for d in deck_ids], "subdecks": bool(subdecks)})
    saved = {}
    for _stamp, _sid, sel in reversed(_anki_sources()):
        saved.update((sel.get("fields") or {}))
    out = []
    for nt in got.get("note_types") or []:
        word, reading = guess_fields(nt.get("fields") or [], saved.get(str(nt.get("id"))))
        out.append({**nt, "expression": word, "reading": reading})
    return {"note_types": out, "missing": got.get("missing") or []}


def clean_selection(raw):
    if not isinstance(raw, dict):
        raise AnkiError("anki_bad_choice")
    chosen = []
    for d in raw.get("decks") or []:
        try:
            chosen.append({"id": int(d["id"]), "name": str(d.get("name") or "")[:200]})
        except (KeyError, TypeError, ValueError):
            raise AnkiError("anki_bad_choice")
    if not chosen:
        raise AnkiError("anki_no_decks")
    rule = raw.get("rule") or {}
    kind = rule.get("kind", "mature")
    if kind not in RULES:
        raise AnkiError("anki_bad_choice")
    clean_rule = {"kind": kind}
    if kind == "mature":
        try:
            ivl = int(rule.get("ivl", DEFAULT_IVL))
        except (TypeError, ValueError):
            raise AnkiError("anki_bad_choice")
        if not 1 <= ivl <= 36500:
            raise AnkiError("anki_bad_choice")
        clean_rule["ivl"] = ivl
    fields = {}
    for mid, pair in (raw.get("fields") or {}).items():
        if not isinstance(pair, dict) or not str(mid).isdigit():
            raise AnkiError("anki_bad_choice")
        word = str(pair.get("expression") or "")
        if word:
            fields[str(mid)] = {"expression": word, "reading": str(pair.get("reading") or "")}
    if not fields:
        raise AnkiError("anki_no_fields")
    return {"decks": chosen, "subdecks": raw.get("subdecks", True) is not False, "rule": clean_rule,
            "fields": fields}


def _fetch(selection):
    who = hello()
    got = _call("POST", "/words", {"decks": [d["id"] for d in selection["decks"]],
                                   "subdecks": selection["subdecks"], "rule": selection["rule"],
                                   "fields": selection["fields"]}, timeout=TIMEOUT_WORDS_S)
    missing = set(got.get("missing") or [])
    gone = [d["name"] for d in selection["decks"] if d["id"] in missing]
    if gone and len(gone) == len(selection["decks"]):
        raise AnkiError("anki_decks_gone", decks="、".join(gone))
    entries = []
    for pair in got.get("entries") or []:
        if isinstance(pair, list) and pair:
            reading = known_words.clean_field(str(pair[1]) if len(pair) > 1 else "")[0]
            entries.append({"expression": str(pair[0]), "reading": reading})
    kept = [d for d in selection["decks"] if d["id"] not in missing]
    label = "Anki: " + ", ".join(d["name"] for d in kept)
    envelope = {"schema": known_words.ENVELOPE, "version": known_words.ENVELOPE_VERSION,
                "source": {"name": label, "decks": [d["name"] for d in kept], "query": got.get("query") or "",
                           "exported": time.strftime("%Y-%m-%dT%H:%M:%S"),
                           "anki": {**selection, "decks": kept, "profile": who["profile"], "chosen": time.time()}},
                "entries": entries}
    counts = {"notes": int(got.get("notes") or 0), "skipped": int(got.get("skipped") or 0), "gone": gone,
              "profile": who["profile"]}
    return json.dumps(envelope, ensure_ascii=False).encode("utf-8"), label, counts


def _no_words(error):
    if error.code == "empty":
        return AnkiError("anki_empty")
    return error


def preview(raw):
    selection = clean_selection(raw)
    data, label, counts = _fetch(selection)
    try:
        got = known_words.preview(data, "anki.json", fmt="reibun")
    except known_words.KnownWordsError as error:
        raise _no_words(error)
    return {**counts, "name": label, "entries": got["entries"], "sample": got["sample"][:SAMPLE]}


def import_selection(raw, replace=None):
    selection = clean_selection(raw)
    if replace and not any(sid == replace for _s, sid, _sel in _anki_sources()):
        raise AnkiError("anki_not_found")
    data, label, counts = _fetch(selection)
    try:
        source = known_words.import_list(data, "anki.json", name=label, origin="anki", replace=replace,
                                         fmt="reibun")
    except known_words.KnownWordsError as error:
        raise _no_words(error)
    return {**counts, "source": source}


def update(sid):
    for _stamp, found, sel in _anki_sources():
        if found == sid:
            return import_selection(sel, replace=sid)
    raise AnkiError("anki_not_found")


def selection_of(sid):
    for _stamp, found, sel in _anki_sources():
        if found == sid:
            return sel
    raise AnkiError("anki_not_found")
