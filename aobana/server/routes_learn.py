from flask import jsonify, request
from aobana.server import app as server

app = server.app


def _known_words_input():
    upload = request.files.get("file")
    form = request.form
    data, name = (upload.read(8 * 1024 * 1024 + 1), upload.filename or "") if upload is not None else (b"", "")

    def num(key):
        value = form.get(key, "")
        return int(value) if value.lstrip("-").isdigit() else None

    options = {"column": num("column"), "reading_column": num("reading_column"),
               "migaku_known": form.get("migaku_known") == "1"}
    return data, name, options


def _known_words_error(error):
    return jsonify({"error": error.code, "detail": error.detail}), 422


@app.route("/api/known-words", methods=["GET"])
def api_known_words():
    from aobana.search import known_words
    return jsonify(known_words.status())


@app.route("/api/known-words/preview", methods=["POST"])
def api_known_words_preview():
    server._require_page()
    from aobana.search import known_words
    data, name, options = _known_words_input()
    try:
        return jsonify(known_words.preview(data, name, **options))
    except known_words.KnownWordsError as error:
        return _known_words_error(error)


@app.route("/api/known-words/import", methods=["POST"])
def api_known_words_import():
    server._require_page()
    from aobana.search import known_words
    data, name, options = _known_words_input()
    try:
        got = known_words.import_list(data, name, name=request.form.get("name", ""), origin="file", **options)
    except known_words.KnownWordsError as error:
        return _known_words_error(error)
    return jsonify({"ok": True, "source": got, **known_words.status()})


@app.route("/api/known-words/<sid>", methods=["DELETE"])
def api_known_words_source(sid):
    server._require_page()
    from aobana.search import known_words
    if not known_words.remove(sid):
        return jsonify({"error": "not_found"}), 404
    return jsonify({"ok": True, **known_words.status()})


def _anki_error(error):
    return jsonify({"error": error.code, "detail": error.detail}), 422


def _anki_call(fn, *args, **kwargs):
    from aobana.search import anki_link, known_words
    try:
        return jsonify(fn(*args, **kwargs))
    except anki_link.AnkiError as error:
        return _anki_error(error)
    except known_words.KnownWordsError as error:
        return _known_words_error(error)


@app.route("/api/anki/decks", methods=["GET"])
def api_anki_decks():
    server._require_page()
    from aobana.search import anki_link
    return _anki_call(anki_link.decks)


@app.route("/api/anki/fields", methods=["POST"])
def api_anki_fields():
    server._require_page()
    from aobana.search import anki_link
    body = request.get_json(silent=True) or {}
    ids = body.get("decks") if isinstance(body.get("decks"), list) else []
    if not all(isinstance(d, int) or (isinstance(d, str) and d.isdigit()) for d in ids):
        return jsonify({"error": "anki_bad_choice"}), 400
    return _anki_call(anki_link.note_types, ids, body.get("subdecks", True) is not False)


@app.route("/api/anki/preview", methods=["POST"])
def api_anki_preview():
    server._require_page()
    from aobana.search import anki_link
    return _anki_call(anki_link.preview, request.get_json(silent=True))


@app.route("/api/anki/import", methods=["POST"])
def api_anki_import():
    server._require_page()
    from aobana.search import anki_link, known_words
    body = request.get_json(silent=True) or {}
    replace = body.get("replace") if isinstance(body.get("replace"), str) else None

    def run():
        got = anki_link.import_selection(body.get("selection"), replace=replace)
        return {"ok": True, **got, **known_words.status()}
    return _anki_call(run)


@app.route("/api/anki/update/<sid>", methods=["POST"])
def api_anki_update(sid):
    server._require_page()
    from aobana.search import anki_link, known_words

    def run():
        got = anki_link.update(sid)
        return {"ok": True, **got, **known_words.status()}
    return _anki_call(run)


@app.route("/api/anki/selection/<sid>", methods=["GET"])
def api_anki_selection(sid):
    server._require_page()
    from aobana.search import anki_link
    return _anki_call(anki_link.selection_of, sid)
