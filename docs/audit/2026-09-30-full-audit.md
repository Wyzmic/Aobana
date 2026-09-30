# Aobana full audit — 2026-09-30

- **Scope:** the public repository at commit `81d534f` ("Aobana 1.6"), branch `claude/hopeful-turing-5s9yc0`.
- **Kind:** read-only. No application code, database, media file or setting in the repository was changed. Live checks ran against a throwaway library and data folder in a scratch directory outside the repository, through the app's own environment overrides (`AOBANA_DATA_DIR`, `SUBS_ROOT_DIR`, `EPUB_ROOT_DIR`, `MANGA_ROOT_DIR`, `AOBANA_PORT`).
- **Context used:** the maintainer's local development notes (`CLAUDE.md`, `project-constraints.md`, `open-findings.md`, `closed-findings.md`), which are not in the public repository. They were used as leads only. Every claim below was checked against the code in this repository. Findings the notes already track are listed separately in [Known open findings, re-checked](#known-open-findings-re-checked) and are not counted as new.

## Contents

1. [Summary](#summary)
2. [How to read this report](#how-to-read-this-report)
3. [Checks run](#checks-run)
4. [Confirmed findings (new)](#confirmed-findings-new)
5. [Plausible concerns (new, not fully reproduced)](#plausible-concerns-new-not-fully-reproduced)
6. [Known open findings, re-checked](#known-open-findings-re-checked)
7. [Architecture and maintainability](#architecture-and-maintainability)
8. [Coverage map](#coverage-map)
9. [Limitations](#limitations)
10. [Prioritized fix list](#prioritized-fix-list)

---

## Summary

The codebase is careful in many places that usually go wrong. Server-rendered HTML is escaped consistently. SQL values are passed as parameters. Manga page images are confined to the manga folder with `realpath` plus `commonpath`. Build downloads are pinned by SHA-256. Index runs commit in batches, so a stopped or killed run leaves each file either old or new. POST endpoints require an `X-Aobana` header, which blocks ordinary cross-site form posts. Both documented constraints I could check held: the SUBS/EPUB replacement lists (74/57) and the single ruby-regex definition.

This audit reached 13 new confirmed findings: 11 defects (C1–C11) and 2 maintainability items (C12–C13). Four stand out:

| # | Severity | Finding |
|---|---|---|
| C1 | **High** | An imported favorites file can run script in the app, and the script stays in `localStorage` (stored XSS, reproduced in Chromium). |
| C2 | **High** | Every request thread that draws a spaced-ruby line leaks an SQLite connection. When the descriptor limit is reached, every search returns HTTP 500 until restart (reproduced). |
| C3 | Medium | `LIKE` wildcards in show/book names: the episode list of `Show_1` also lists `Show 1`'s episodes (reproduced). |
| C4 | Medium | A file that cannot be read during **Index library** loses all its indexed rows, even though the file was not deleted (reproduced). |

There are also 8 plausible concerns that I could not fully reproduce. The most important is P1: the server does not check the `Host` header, so a DNS-rebinding page could reach the local API. The missing check itself is confirmed.

---

## How to read this report

- **Severity**
  - **High:** loss of function or a security boundary crossed in normal use.
  - **Medium:** wrong results or avoidable loss of derived data in realistic use.
  - **Low:** edge cases, hardening, performance and maintainability.
- **Confirmed:** reproduced by a command or test in this audit, or proven by code that has only one possible reading. Each one shows its evidence.
- **Plausible:** the mechanism is visible in the code, but the full failure needs an environment I did not have (a phone, Windows, a real DNS-rebinding setup) or unusual input.
- **Line numbers** refer to commit `81d534f`. The published files have their comments stripped, so these numbers differ from the development tree.

---

## Checks run

| Check | Command (summary) | Result |
|---|---|---|
| Install pinned deps | `python3 -m venv …; pip install -r requirements.txt` (Python 3.11.15) | OK: Flask 3.1.3, bs4 4.15.0, SudachiPy 0.6.11, SudachiDict-core 20260723 |
| Byte-compile everything | `python -m py_compile *.py release/*.py release/unix/*.py release/launcher/*.py` | OK |
| Static analysis | `python -m pyflakes *.py release/*.py release/unix/*.py` | No undefined names. Only unused imports; the regex re-imports are deliberate (constraint §2). One unused `subprocess` import in `release/build_unix.py:17`. |
| Build consistency | `build.check_whitelist()` (includes `check_imports_shipped`) | OK |
| Constraint §1 | `len(SUBS_STR_REPLACEMENTS), len(EPUB_STR_REPLACEMENTS)` | `74 57`, as documented |
| Constraint §2 | identity of `KANA_RE … RUBY_BASE_RE`, `RUBY_RE`, `BOOK_RUBY_RE` across `engine`/`epub_indexer`/`utils` | `True True True` |
| Termux file lists | diff of `PHONE_FILES` in `termux/install.sh` and `termux/uninstall.sh` | Drift: see C8 |
| Live server, synthetic library | `indexer.py` then `app.py` on port 5099 with two shows, `Show_1` and `Show 1` | Used for C2, C3, C4, C6, P1 |
| Descriptor growth | count `/proc/<pid>/fd` before and after 100 requests | +100 `subs.db` handles (C2) |
| Descriptor exhaustion | server under `ulimit -n 64` | request 58 → HTTP 500; later searches → HTTP 500 (C2) |
| Browser test | Playwright + pre-installed Chromium 1194; import a favorites JSON | Script ran on the Favorites tab (C1) |
| Micro-benchmarks | `highlight_and_furigana` at 1k–37k chars; `Dictionary().create()` ×20 | Quadratic (C9); 17.4 ms per construction (C13) |
| Config race | two threads calling `library.set_port` and `library.set_search_cache` through a barrier, ×200 | 197/200 lost one setting (C7) |

After the checks, the scratch server was stopped and the `__pycache__` folders created by `py_compile` were removed. `git status --ignored` was clean before the report was added.

---

## Confirmed findings (new)

### C1 — High — An imported favorites file can inject script (stored XSS)

- **Where:** `index.html:3361-3390` (`importFavorites`), rendered by `index.html:2201` (`${r.display_line}`), `:2211` (`${r.context}`), `:2206` (`data-rowid="${r.rowid}"`) and `:2961` (`renderBrowseLinesHTML`).
- **Evidence:** `importFavorites` keeps any object whose `line` is a string and appends it unchanged to `savedSentences` in `localStorage`. `buildBatchHTML` then puts `display_line`, `context` and `rowid` into `innerHTML` without escaping. That is safe for server results, because `engine.highlight_and_furigana` escapes them. An imported file, however, supplies those fields itself.
- **Reproduced:** I imported this file through `#fav-file` in headless Chromium, then opened the Favorites tab:

  ```json
  [{"line": "audit-probe", "display_line": "<img src=x onerror=\"window.__auditProbe=1\">probe", "title": "t", "rowid": 1, "file": "f", "media_type": "subs"}]
  ```

  Result: `window.__auditProbe === 1` on the Favorites tab, and the entry stayed in `localStorage.savedSentences`.
- **Impact:** Favorites export and import exist so that people can share lists. A shared file can run script on the app's own origin. Because the origin matches, the script can send the `X-Aobana` header and call any POST endpoint:
  - `/api/library/drop` deletes a database.
  - `/api/library` repoints folders or moves the databases.
  - `/api/update/apply` starts an update.
  - Any GET endpoint can be read, including folder paths.

  The payload runs again on every visit to Favorites. It also survives a port change, because the profile handoff copies `localStorage`.
- **Fix:**
  - On import, keep only known fields (`line`, `file`, `rowid`, `media_type`, `title`, `folder`, `page`, `original_q`, …).
  - Coerce `rowid` and `page` to integers.
  - Drop `display_line` and `context`, and rebuild them from the server (`/api/relocate` already looks rows up by `line`). If they must be kept, render them with `esc()` or from a sanitized source.
  - Treat favorites already in `localStorage` the same way on load (`loadSavedSentences`, `index.html:1457`).
  - Add a Content-Security-Policy without `'unsafe-inline'` for scripts as defence in depth. The page uses inline handlers, so this needs refactoring first.
- **Verify:** Repeat the import above. After the fix, the probe stays `0` and the entry shows as plain text.

### C2 — High — Lexicon connections leak per request thread, and descriptor exhaustion breaks all searches

- **Where:** `engine.py:139-156` (`_lexicon_tables`), `engine.py:159-165` (`_close_ended_lexicon_tables`), called only from `engine.py:3241` (`reset_caches`).
- **Evidence:**
  - `_lexicon_tables` opens one read-only connection per database per thread and records it in `_LEXICON_OPEN[thread]`.
  - The Werkzeug server started at `app.py:1096` runs each request on a new thread.
  - Closed threads' connections are released only by `reset_caches()`, which runs only after an index run, a database move or drop, or a media toggle.
  - `ruby_evidence` (`engine.py:229`) reaches `_lexicon_tables` whenever a line being drawn has a spaced-ruby candidate (`漢字 漢字(かな)`), for example `桐山 零(きりやまれい)`.
- **Reproduced:**
  - With a subtitle line `桐山 零(きりやまれい)が来た。`, 100 × `GET /api/search?q=来る` raised the server's open descriptors from 6 to 106. 102 of them were `subs.db`.
  - Under `ulimit -n 64`, request 58 returned **HTTP 500**, and a plain search for `猫` also returned 500 afterwards. The log shows `SudachiError: … IO Error: Too many open files (os error 24)`.
- **Impact:** With several databases, each such request can leak up to 3 descriptors.
  - macOS gives GUI-launched processes a soft limit of 256.
  - Linux commonly uses 1024.
  - Termux/proot processes inherit Android limits.

  A few hundred searches, context opens or Media reads that show spaced ruby, which is common in the author's subtitle corpus, make the whole app fail until restart. Nothing in the UI explains why.
- **Fix:** Pick one:
  - Call `_close_ended_lexicon_tables()` from an `@app.teardown_request` hook, or on a timer.
  - Better: keep a small shared pool of `check_same_thread=False` read-only connections guarded by a lock, instead of one set per thread.
  - Alternatively, run the server with a fixed thread pool (for example `waitress` with `threads=N`) so that thread-locals are reused.
- **Verify:** Repeat the 100-request loop. The descriptor count should stay flat.

### C3 — Medium — `LIKE` wildcards in show and book names mix titles

- **Where:**
  - `app.py:385-393` (`/api/episodes`, subtitles: `relpath LIKE folder/%`)
  - `app.py:404-420` (books without a `chapters` table)
  - `engine.py:2832-2833`, `:2852`, `:2869` (no-query browse count and listing)
  - `engine.py:3031-3033` (`folder and not q`)
- **Evidence:** The folder name is concatenated into a `LIKE` pattern with no `ESCAPE` clause, so `_` matches any single character and `%` matches any run. Show folders often contain `_`, because `:` and `/` are not allowed in file names and are commonly replaced with `_`.
- **Reproduced:** Two shows, `Show_1/Show_1 01.srt` and `Show 1/Show 1 01.srt`:

  ```
  GET /api/episodes?folder=Show_1
  → {"files":[{"file":"Show 1/Show 1 01.srt",…},{"file":"Show_1/Show_1 01.srt",…}]}
  ```

  The Media episode list for `Show_1` shows the other show's episode. The browse listing (`/api/search?folder=Show_1`, no `q`) returned the correct rows here, because `_source_runs` bounds the query by rowid. The unbounded fallback paths and the count query use the same pattern.
- **Impact:** Wrong episodes and chapters in Media, and wrong totals, whenever one title name matches another title's name with wildcards. Examples: `Fate_Zero` / `Fate Zero`, `Re_Zero` / `Re:Zero`-style renames, `%` in a title.
- **Fix:** Use range predicates as the chapter code already does (`file >= ? AND file < ?` with prefix + `\U0010ffff`), or escape `%`, `_` and the escape character and add `ESCAPE '\'`. Match on `sources.relpath` prefixes with `substr(relpath, 1, n) = ?` where possible.
- **Verify:** The request above should return only `Show_1/…`.

### C4 — Medium — A file that cannot be read during indexing loses all its indexed rows

- **Where:** `indexer.py:621-629`, `epub_indexer.py:1322-1328`, `manga_indexer.py:344-347`.
- **Evidence:** When `_prepare` fails (for example with `OSError`, a decode error or a zip error), the run deletes that file's rows and its `sources` entry and reports `FAILED`, even though the file still exists.
- **Reproduced:**
  1. The indexed file `Show 1/Show 1 01.srt` was replaced with a dangling symlink, which stands in for an offline network or cloud file.
  2. **Index library** was run.
  3. `sources`/rows went from `2/5` to `1/3`.
  4. After the file was restored, the next run had to re-index it: "Indexed 1 new/updated files".
- **Impact:** A file that is only briefly unreadable disappears from search until the next successful run. Examples:
  - a OneDrive or Dropbox placeholder
  - a network share that drops
  - a file locked by another program on Windows
  - an EPUB that a newer reading rule rejects

  For large EPUB libraries (the notes describe 46,859 books), re-reading is expensive. Favorites that point at those rows have to be relocated. This differs from the documented "a stopped or killed run leaves every file old or new, never missing" guarantee (notes, 8.3 §1), which covers stop and crash but not read errors.
- **Fix:** On `error`, keep the old rows and report the failure. If the file should be dropped only after repeated failures, record the failure on the `sources` row (for example `last_error`, `failed_at`), keep the index, and let **Check library** list it.
- **Verify:** Repeat the symlink test. The counts should stay `2/5` and the run should still print `FAILED`.

### C5 — Low — `_` or `%` in a negated term excludes every result, and exact-phrase `LIKE` is case- and wildcard-loose

- **Where:** `engine.py:3019-3026` (`clean_text NOT LIKE %term%`, `line NOT LIKE …`, `base_forms NOT LIKE …`), `engine.py:3008-3009` (exact phrase `clean_text LIKE %q%`), `engine.py:3139-3143` (fallback).
- **Reproduced:**

  | query | results |
  |---|---|
  | `好き` | 2 |
  | `好き -犬` | 1 (correct) |
  | `好き -_` | **0** |
  | `好き -%` | **0** |

- **Impact:** A search excluding `_`, `%`, or text that contains them (for example `-100%`) wrongly empties the results. SQLite `LIKE` is also ASCII case-insensitive, so `-ABC` also excludes `abc` in SQL, while the Python pass-1 check is case-sensitive. The two stages disagree.
- **Fix:** Use `instr(clean_text, ?) = 0` (exact, case-sensitive, no wildcards) for negation, and `instr(…) > 0` for the exact-phrase prefilter, as `/api/locate` already does (`app.py:599`).
- **Verify:** `好き -_` should return 2.

### C6 — Low — Unsynchronized read-modify-write of `config.json` loses settings

- **Where:** `paths.py:134-146` (`save_config`) together with every `load_config → modify → save_config` caller in `library.py`: `set_folders` :334, `set_media` :352, `mark_*_asked` :420-431, `set_search_cache` :697, `set_workers` :726, `set_search_workers` :753, `set_port` :772, and in `_move_files` :616.
- **Evidence:** Each Flask request runs on its own thread, and there is no lock around load–modify–save. The atomic `os.replace` prevents a torn file but not a lost update.
- **Reproduced:** Two threads started together through a `threading.Barrier`, one calling `set_port`, the other `set_search_cache(True)`: **197 of 200** trials ended with one of the two settings missing. The barrier makes the race likely. In the UI the window is milliseconds, for example `setup/seen` and `check-asked` posted together at start, or a database move finishing while Settings saves.
- **Fix:** Add a module-level `threading.Lock` in `paths`, plus an `update_config(fn)` helper that loads, applies and saves under the lock. Use it in every setter.
- **Verify:** Rerun the race script. The expected result is 0/200.

### C7 — Low — Termux uninstall leaves app files behind and misreports them as the user's

- **Where:** `termux/uninstall.sh:11-12` (`PHONE_FILES`) compared with `termux/install.sh:13-14`.
- **Evidence:** The install list has `manga_indexer.py` and `ass_ruby.py`; the uninstall list does not. The script diff printed `install-only: ['ass_ruby.py', 'manga_indexer.py']`. `release/build.py:121-139` (`check_imports_shipped`) checks only `install.sh`, so the drift goes unnoticed.
- **Impact:** After uninstall, the two files stay in `/storage/emulated/0/Aobana`, so `rmdir` fails and the script says `removed; kept: ass_ruby.py manga_indexer.py …`. That suggests these are the user's files.
- **Fix:** Generate both lists from one source, or have `check_imports_shipped` also require `uninstall.sh`'s list to equal `install.sh`'s list.
- **Verify:** Rerun the diff above. It should show no difference.

### C8 — Low — Furigana rendering is quadratic in line length

- **Where:** `engine.py:705-1003` (`highlight_and_furigana`):
  - `:962` searches `ruby_spans` linearly for every character.
  - `:812-815` loops over every word for every match.
  - `result_html +=` builds the string inside a per-character loop.
- **Reproduced (single call, `work=('epub', …)`):**

  | chars | ruby spans | ms |
  |---:|---:|---:|
  | 9,200 | 400 | 168 |
  | 18,400 | 800 | 527 |
  | 36,800 | 1,600 | 1,657 |

- **Impact:** Each time the line length doubles, the time roughly triples. Long EPUB paragraphs, which the 1.3 changelog says exist ("Very long EPUB paragraphs no longer break the results page"), each cost seconds of CPU in Search, context and the Media reader.
- **Fix:**
  - Index spans by start position (`{start: span}`).
  - Collect output in a list and `''.join` it.
  - Use a sweep or interval approach to mark `reading_match`.

  None of these change the output, so check with a golden-output comparison on the dev corpus.
- **Verify:** Rerun the benchmark. Time should grow roughly linearly.

### C9 — Low — The "port in use" message points to the wrong tab

- **Where:** `launcher.py:36-42`. The Japanese text says `ライブラリタブでも変更できます`; the English says "can also be changed in the Library tab".
- **Evidence:** CHANGELOG 1.4 moved the port to the **Settings** tab, and `index.html:5338` puts `#lib-port` in the Settings panel.
- **Fix:** Say "Settings tab" / 「設定タブ」.

### C10 — Low — Some caches are never cleared

- **Where:**
  - `engine.py:48-77` (`GLOBAL_DB_TOTALS`)
  - `engine.py:2880-2882` (`GLOBAL_FOLDER_COUNTS`)
  - `engine.py:218-226` (`_SUDACHI_READINGS`)
  - `reset_caches` at `engine.py:3237-3245` clears the title caches but none of these.
- **Evidence:** The first two are keyed by the database fingerprint (path, mtime, size), so each index run adds a new generation of keys and the old ones are never removed. `_SUDACHI_READINGS` keeps growing with every distinct word it is asked about.
- **Impact:** Slow memory growth in a long-running session. Small per entry, but unbounded.
- **Fix:** Clear these in `reset_caches`, or use bounded `OrderedDict`s as `_MATCH_COUNTS` does.

### C11 — Low — A new Sudachi dictionary per request thread

- **Where:** `engine.py:79-85` (`get_tagger`, cached in `threading.local`).
- **Evidence:** A new request thread per request (see C2) means `Dictionary(dict="core").create()` runs on every request that tokenizes. Measured cost: **17.4 ms** per construction (mean of 20).
- **Fix:** Use a fixed-size server thread pool, or a small lock-protected pool of tokenizers. SudachiPy tokenizers are not safe to share across threads without a lock.

### C12 — Low — No automated tests or linting run on changes

- **Where:** `.github/workflows/build.yml:3-8` runs only on `release`, pushes to `ci-unix`, and manual dispatch. The public repository has no unit or regression tests. `release/unix/smoke.py` covers start, index and two searches only. The notes describe a `verify.py` gate and `testing/` suites in the development tree that are not published.
- **Impact:** None of C1–C8 would have been caught automatically, and a contributor cannot check a change.
- **Fix:** Publish a small `pytest` suite that needs no personal corpus. Candidates:
  - synthetic `.srt`/`.ass`/`.epub`/`.mokuro` fixtures
  - the regression cases in this report
  - the constraint §1/§2 checks
  - `check_whitelist`

  Run it together with `pyflakes` on `push` and `pull_request`.

### C13 — Low — Unused import

- **Where:** `release/build_unix.py:17` (`import subprocess`). It is harmless; flagged only because pyflakes reported it.

---

## Plausible concerns (new, not fully reproduced)

### P1 — Medium — The `Host` header is not checked, so DNS rebinding can reach the local API

- **Where:** `app.py:694-696` (`_require_page` checks only `X-Aobana: 1`); `app.py:1096` (`app.run(host='127.0.0.1')`). There is no `Host` or `Origin` check and no `TRUSTED_HOSTS`.
- **Confirmed part:** `POST /api/setup/seen` with `Host: attacker.example:5099` and `X-Aobana: 1` returned **200**.
- **Not reproduced:** the full attack, which needs a rebinding DNS name. A page on `attacker.example` whose DNS switches to `127.0.0.1` becomes same-origin with the app. It can then send `X-Aobana` and call every endpoint (drop a database, move databases, change folders, start an update) and read every GET endpoint. The port is predictable (5000, or 5005 on macOS).
- **Fix:** Reject requests whose `Host` is not `127.0.0.1:<port>` or `localhost:<port>`. Flask 3.1 supports `app.config["TRUSTED_HOSTS"]`. For POSTs, also require `Origin`, when present, to match.
- **Verify:** The curl command above should return 400.

### P2 — Medium — **Open folder** fails on Android/Termux

- **Where:** `library.py:919` chooses `termux-open` only when `TERMUX_VERSION` is set, otherwise `xdg-open`. By contrast, `folder_picker.py:10-11` also accepts `AOBANA_TERMUX=1`.
- **Evidence:**
  - The shortcut starts the server inside the proot Ubuntu with `AOBANA_TERMUX=1` (`termux/aobana-shortcut.sh:36-37`).
  - `proot-distro login` does not normally pass Termux's `TERMUX_VERSION` through.
  - The Ubuntu container gets only `python3` and `python3-pip` (`termux/install.sh:112-113`), so neither `xdg-open` nor `termux-open` exists there.
  - The **Open folder** buttons are drawn on every platform (`index.html:3052`, `:3159`, `:3270`).
- **Expected result:** The button reports `failed:[Errno 2] No such file or directory: 'xdg-open'`.
- **Not verified:** no Android device was available.
- **Fix:** Hide or disable the buttons when `AOBANA_TERMUX=1`, as `folder_picker.available()` does, or show the path to copy instead.

### P3 — Low — Unexpected indexer output can stall the Library task

- **Where:** `library.py:1088-1104` (`_read_line` calls `int(...)` on `TOTAL`, `PROGRESS`, `LENGTHS`, `LEXICON` lines), inside `library.py:1055-1064`.
- **Evidence:** A child line that starts with one of those prefixes but has a non-integer field raises `ValueError` in the server's reader loop. The outer `except` then marks the run finished, but the child keeps running with its stdout pipe no longer read, so it can block once the pipe buffer fills. The UI then allows a second run against a database the orphan still holds.
- **How it could happen:** An EPUB title (`epub_indexer.py:1386`) or exception text (`FAILED …: {payload}`) containing a newline followed by, for example, `TOTAL x`.
- **Not reproduced:** needs crafted metadata.
- **Fix:** Wrap each parse in `try/except ValueError` and log the line. Strip `\r` and `\n` from titles and exception text before printing. After an exception, keep draining stdout, or kill the child.

### P4 — Low — Check library and the estimate skip the source-path bootstrap

- **Where:** `library.py:1156` (`_run_analysis`) and `library.py:1301` (`estimate`) launch `[sys.executable, analyser.py]` directly. `library.py:1048-1052` launches the indexers through the `runpy` bootstrap that constraint §14 requires.
- **Evidence:** `analyser.py` imports `indexer` and `epub_indexer`. Under a packaged Python whose `._pth` lists an older bundled app folder first (the case §14 records), the check and the estimate would read files with older rules than the index uses.
- **Scope:** Development tree only. In an installed build the code tree and the bundle are the same.
- **Fix:** Launch both through the same bootstrap as `_run`.

### P5 — Low — An offline drive whose mount point still exists empties that media's index

- **Where:** `indexer.py:666-673`, `epub_indexer.py:1393-1398`, `manga_indexer.py:388-396`. The only guard is `os.path.isdir(root)` (`indexer.py:488`).
- **Evidence:** On Linux and macOS, an unmounted drive often leaves an empty mount-point folder. Index library then sees zero files and removes every source. The code clearly supports this path; I did not test a real mount.
- **Fix:** When a run would remove more than a set share of the sources (for example over 50%, or all of them), stop and ask. Alternatively, require a marker file in the root.

### P6 — Low — Update verification relies only on GitHub metadata

- **Where:** `updater.py:103-107`. The size and `sha256:` digest come from the same GitHub API response as the download URL, and the digest check is skipped if `digest` is missing.
- **Evidence:** This protects against a corrupted transfer, not against a compromised release or account. The Windows installer and macOS app are unsigned (README). This is a hardening note, not a defect.
- **Fix, if wanted:** Publish a detached signature (for example minisign) and verify it with a public key shipped in the app.

### P7 — Low — Settings are read from disk many times per request

- **Where:** `paths.py`. Every accessor (`subs_dir`, `media_enabled`, `db_dir`, `search_workers`, …) calls `load_config()`. `api_search` alone reaches it more than five times (`get_db` → `media_state`, `get_manga_db` → `media_enabled`, `subs_db`/`epub_db`/`manga_db`, `search_workers`, `search_worker_delay`).
- **Impact:** Small per request. It also means one request can see two different configs if a setting is saved while it runs.
- **Fix:** Load once per request (`flask.g`) or cache by the file's mtime.

### P8 — Low — The launcher gives up opening the browser after 20 seconds

- **Where:** `launcher.py:61` (`wait_and_open(timeout=20.0)`).
- **Evidence:** On a slow first start (antivirus scanning the bundled Python, a cold hard disk) the server can take longer than 20 s to listen. The console then shows the URL, but no browser opens. Not measured.
- **Fix:** Wait while the child process is alive, not for a fixed time.

---

## Known open findings, re-checked

These are already tracked in the maintainer's notes (`open-findings.md`). I re-checked each against the public code; none is counted as new above.

| Known finding (notes) | Status in `81d534f` | Evidence |
|---|---|---|
| **The 0.7.0 rebuild** (SudachiPy pinned at 0.6.11) | Still pinned | `requirements.txt` pins `SudachiPy==0.6.11`, `SudachiDict-core==20260723`. The `Dictionary.create()` call sites the notes list as `engine.py:35`, `indexer.py:23`, `epub_indexer.py:31` are, in the published tree, `engine.py:83`, `indexer.py:23` and `epub_indexer.py:39`, **plus `manga_indexer.py:30` and `ass_ruby.py:39`, which the notes' list omits.** |
| **Messier rips: `kept_lines` differs from the index for spaced readings** | Still open | `analyser._measure_sub` (`analyser.py:98`) reads `indexer.kept_lines` (`indexer.py:409-413`), which does not apply the lexicon join the indexer uses. |
| **Index workers: low-memory cap** | Still open | `paths.recommended_workers` = half the usable CPUs (`paths.py:226-227`). There is no memory check. |
| **Manga after 1.4: check and estimate skip manga** | Still as described | `library.start_analysis` returns `False` for `manga` (`library.py:1137-1138`). `analyser.estimate` covers only subs and epub (`analyser.py:533-534`). |
| **Main-app ruby spans: `ヶ` cuts a base** | Still open | `utils.KANJI_CHARS` (`utils.py:39`) has no `ヶ`/`ヵ`. |
| **A 122 GB library: index run vs. readers (`journal_mode = delete`)** | Still as described | No `journal_mode` or `busy_timeout` pragma anywhere. Readers use `mode=ro`; writers use the default rollback journal and a 5 s busy timeout. |
| **Split engine.py** | Still due | `engine.py` is 3,435 lines in the published tree. It holds titles, caches, search, parallel workers and the Media library, and `release/build.py:APP_FILES` and `termux/install.sh:PHONE_FILES` must follow any split. |
| **The macOS and Linux builds: Linux at a real desktop** | Not testable here | CI covers the tarball, AppImage and install/uninstall in containers (`.github/workflows/build.yml`). |
| **One-click updates: the untried cases** | Not testable here | See P6 for a related hardening note. |
| **Romaji typing; Audio and video playback; AutoImage fork** | Planned work, not defects | Not reviewed as bugs. |

Documented decisions I checked and left alone:
- The two normalization lists (§1).
- The ruby-regex split and the `BOOK_RUBY_RE` scope (§2, §3).
- Comment stripping in published code.
- Half-thread automatic workers.
- The uninstaller offering to delete the default media folders (opt-in, unticked).

---

## Architecture and maintainability

These are improvements, not defects.

1. **Serving model.** `app.run()` is Werkzeug's development server, with one thread per request. C2 and C11 come from pairing that model with thread-local resources. A production WSGI server with a fixed pool (waitress is pure Python, so it works on Windows, macOS, Linux and proot) would fix both and remove the "development server" warning. Keep `127.0.0.1` binding and add the `Host` check from P1.
2. **Shared settings access.** `paths.py` reads `config.json` on every call and every writer races (C6, P7). Move to a single `Config` object with `get()` and `update(fn)` under a lock.
3. **One way to match a title.** Folder and title matching appears in five forms: `LIKE` with `/` and `\`, range predicates, `_source_runs`, `chapters`, and `sources.title` for manga. C3 exists because of that. A single `title_predicate(media, folder)` helper in `engine` would cover all of them.
4. **`index.html` (5,523 lines) is a single file with inline handlers.** It prevents a strict CSP (C1) and makes the UI hard to test. Moving the script into `static/app.js` (the cache-busting `asset_v` already exists) and replacing `onclick=` attributes with delegated listeners would allow `script-src 'self'`.
5. **Subprocess protocol.** Indexers report progress through ad-hoc text prefixes parsed in `library._read_line`. A JSON-lines channel (`{"type":"progress","done":…}`) would remove P3's parsing hazard and the cp932 re-encoding at `indexer.py:659`.
6. **Keep the Termux lists in one place** (C7). `install.sh`, `uninstall.sh` and `build.py` each hold a copy of the file list.

---

## Coverage map

| Area | Files | Depth | Findings |
|---|---|---|---|
| Configuration and paths | `paths.py` | Read fully | C6, P7 |
| Launchers | `launcher.py`, `Aobana.bat`, `aobana.sh`, `release/launcher/Aobana.cs`, `release/unix/aobana-run.sh`, `aobana-command.sh`, `aobana-mac.sh` | Read fully | C9, P8 |
| Web server and API | `app.py` | Read fully; live-tested | C3, P1 |
| Search engine | `engine.py` | Read: lexicon and connections, `highlight_and_furigana`, caches, disk cache, `_search_results` browse and query paths, `reset_caches`. **Skimmed:** title formatting (`format_episode_title` …), parallel scan and count workers, Media library | C2, C3, C5, C8, C10, C11 |
| Shared helpers | `utils.py` | Read: relpaths, filter list, format and outdated logic, tables, lengths, `parallel_map`, compaction, meta. **Skimmed:** title cleaning and ruby tables | — |
| Subtitle indexing | `indexer.py` | Read fully; live-tested | C4, P5 |
| EPUB indexing | `epub_indexer.py` | Read: run loop, auto-filter journal, error and zero-row paths. **Skimmed:** chapter and TOC extraction (lines 1-1060) | C4, P3, P5 |
| Manga indexing | `manga_indexer.py` | Read: parsing, reading order, prepare, run loop | C4, P5 |
| `.ass` furigana | `ass_ruby.py` | Import-level only; placement logic not reviewed | — |
| Library management | `library.py` | Read fully | C6, P2, P3, P4 |
| Library check and estimate | `analyser.py` | Read: language rules, measurement cache, run and estimate. Duplicate heuristics skimmed | P4 |
| Updates | `updater.py`, update parts of `app.py` and `launcher.py` | Read fully | P6 |
| Folder picker | `folder_picker.py` | Read fully | (P2 context) |
| Web UI | `index.html` | Every `innerHTML` sink reviewed, plus favorites import, rendering, sidebar, Media rows, settings cards. Not reviewed: CSS, i18n text, keyboard shortcuts, the §11 UI contracts | C1 |
| Termux | `termux/install.sh`, `uninstall.sh`, `aobana-shortcut.sh` | Read fully | C7, P2 |
| Unix and Windows packaging | `release/build.py` (checks), `build_unix.py` (downloads), `unix/install.sh`, `uninstall.sh`, `aobana.desktop`, `installer/aobana.iss` (uninstall data removal) | Partial | C13 |
| CI | `.github/workflows/build.yml` | Read fully | C12 |
| Data | `data/ruby/ruby.tsv` | Not reviewed (the maintainer reviews it against dictionaries) | — |

---

## Limitations

- **Platform:** Linux x86-64 with Python **3.11.15**, not 3.14 as the release uses. Nothing was run on Windows, macOS or Android. P2, P8 and all installer, updater and folder-picker behaviour were judged from the code.
- **Corpus:** Only a synthetic library (two shows, five lines). No EPUB or `.mokuro` fixture was indexed live. Performance figures are micro-benchmarks, not measurements on a real library.
- **Not attempted:** a full DNS-rebinding attack (P1), fault injection on Windows file locks (C4's Windows form), and a real unmount (P5).
- **Not reviewed:**
  - Correctness of Japanese processing (tokenization choices, ruby placement, title heuristics, language thresholds). This is the maintainer's measured domain, backed by a private corpus and `verify.py`.
  - The development-tree tooling (`verify.py`, `testing/`, `.claude/`), which is not in this repository.
- **Line numbers** are for commit `81d534f` and will drift.

---

## Prioritized fix list

| Priority | Item | Effort | Why first |
|---|---|---|---|
| 1 | **C1** Allow-list imported favorites fields and re-escape stored ones | S | Script execution on the app origin from a shared file |
| 2 | **C2** Close or pool lexicon connections (teardown hook or fixed pool) | S | Whole app fails after routine use; restart needed |
| 3 | **P1** Validate `Host` (`TRUSTED_HOSTS`) and `Origin` on POST | S | Closes remote reach to destructive endpoints |
| 4 | **C4** Keep rows on read errors; track failures on `sources` | S–M | Avoids silent loss of derived data and costly re-reads |
| 5 | **C3** Replace folder `LIKE` patterns with range or escaped predicates | S | Wrong Media and episode listings |
| 6 | **C12** Publish a small pytest suite and run it with pyflakes on push/PR | M | Would have caught 1–5; keeps them fixed |
| 7 | **C6** Lock config read-modify-write (`paths.update_config`) | S | Lost settings |
| 8 | **P2** Hide **Open folder** on Termux | XS | Button that always fails on phones |
| 9 | **C5** Use `instr` for negation and the exact-phrase prefilter | XS | Wrong empty results |
| 10 | **C8** Make furigana rendering linear | S | Seconds per long paragraph |
| 11 | **C7** Single Termux file list; extend `check_imports_shipped` | XS | Misleading uninstall output |
| 12 | **P3** Harden `_read_line`; strip newlines from printed titles and errors | XS | Stalled task on odd metadata |
| 13 | **P5** Confirm before removing most of a media's sources | S | Offline-drive wipe |
| 14 | **C11**, **C10**, **P7**, **P8**, **P4**, **C9**, **C13** | XS–S each | Performance, memory, wording, dev-only |
| 15 | Architecture items 1–6 | M–L | Structural; after the fixes above |
