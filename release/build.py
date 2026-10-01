"""Build 露草 / Aobana's Windows installer, and export the public repository.

    python release/build.py              export, bundle, installer
    python release/build.py export       only release/repo/ (the git repository that is pushed)
    python release/build.py bundle       only release/build/app/ (the install image)
    python release/build.py installer    bundle, then ISCC -> release/dist/Aobana-Setup-<ver>.exe
    python release/build.py check        release/repo/ carries no comments but the kept ones

Run it with a Python 3.14 that has pip and Pillow (for the icon); it also needs Chrome or Edge
(the icon), Inno Setup 7 (the installer) and the .NET Framework 4 compiler every Windows has.
It never installs anything into that Python: the packages go into the bundled one, from the
wheel cache in release/vendor/wheels, with no network. release/vendor/ is not in the
repository; fill it once, and refill the wheels only when requirements.txt changes:

    python-3.14.7-embed-amd64.zip   from python.org (its SHA-256 is PY_ZIP_SHA256 below)
    python -m pip download -r requirements.txt --only-binary=:all: --platform win_amd64
        --python-version 3.14 --implementation cp -d release/vendor/wheels
"""
import hashlib
import os
import re
import shutil
import stat
import subprocess
import sys
import zipfile

RELEASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(RELEASE)
with open(os.path.join(ROOT, "aobana", "server", "app.py"), encoding="utf-8") as _fh:
    VERSION = re.search(r'^VERSION = "([^"]+)"', _fh.read(), re.M).group(1)
VENDOR = os.path.join(RELEASE, "vendor")
WHEELS = os.path.join(VENDOR, "wheels")
PY_ZIP = os.path.join(VENDOR, "python-3.14.7-embed-amd64.zip")
PY_ZIP_SHA256 = "d297e5ff019966817ad8502465176139f2d3d840fa4ed84b13bed399a6ab1f15"
BUILD = os.path.join(RELEASE, "build")
IMAGE = os.path.join(BUILD, "app")
REPO = os.path.join(RELEASE, "repo")
DIST = os.path.join(RELEASE, "dist")
PUBLIC = os.path.join(RELEASE, "public")
CSC = r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
ISCC = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Inno Setup 7", "ISCC.exe")

APP_FILES = [
    "aobana/__init__.py", "aobana/__main__.py", "aobana/paths.py", "aobana/utils.py",
    "aobana/server/__init__.py", "aobana/server/app.py", "aobana/server/launcher.py",
    "aobana/server/library.py", "aobana/server/updater.py", "aobana/server/folder_picker.py",
    "aobana/server/index.html",
    "aobana/search/__init__.py", "aobana/search/engine.py", "aobana/search/furigana.py",
    "aobana/search/titles.py", "aobana/search/result_cache.py", "aobana/search/media_tab.py",
    "aobana/indexing/__init__.py", "aobana/indexing/indexer.py", "aobana/indexing/epub_indexer.py",
    "aobana/indexing/manga_indexer.py", "aobana/indexing/ass_ruby.py", "aobana/indexing/analyser.py",
    "Aobana.bat", "aobana.sh", "requirements.txt",
    "data/ruby/ruby.tsv",
    "static/app.css", "static/i18n.js", "static/app.js",
    "static/aobana.svg", "static/fonts/NotoSansJP.ttf", "static/fonts/OFL.txt",
]
NOT_EXPORTED = {
    "data/ruby/ruby_splits.tsv": "a review list keyed by rowids of one index; the engine never reads it",
    **{f"static/icons/{name}": "local launcher shortcut art; never part of the web app or release"
       for name in ("aobana.ico", "aobana-build-1.6.ico", "aobana-latest.ico",
                    "aobana-mattias.ico", "aobana-mattias-1.5.ico")},
}
TSV_COLUMNS = {"ruby.tsv": 5}
PUBLIC_FILES = ["README.md", "README.ja.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "CHANGELOG.md"]
REPO_ONLY = {"README.md", "README.ja.md", "requirements.txt"}
PUBLIC_ASSETS = [f"{view}.{lang}.png" for view in ("search-night", "search-haze", "media-haze")
                 for lang in ("en", "ja")]
REPO_FILES = ["termux/install.sh", "termux/aobana-shortcut.sh", "termux/uninstall.sh"]
BUILD_FILES = ["build.py", "launcher/Aobana.cs", "launcher/make_icon.py", "installer/aobana.iss",
               "build_unix.py", "unix/aobana-mac.sh", "unix/aobana-command.sh", "unix/aobana-run.sh",
               "unix/install.sh", "unix/uninstall.sh", "unix/aobana.desktop", "unix/Info.plist",
               "unix/aobana.png", "unix/aobana.icns", "unix/smoke.py"]
WORKFLOWS = {"github/build.yml": ".github/workflows/build.yml", "github/FUNDING.yml": ".github/FUNDING.yml"}


def step(msg):
    print(f"\n== {msg}", flush=True)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def rmtree(path):
    def clear_and_retry(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    if os.path.exists(path):
        shutil.rmtree(path, onexc=clear_and_retry)


def run(cmd, **kw):
    print("  $ " + " ".join(f'"{c}"' if " " in c else c for c in cmd), flush=True)
    subprocess.run(cmd, check=True, **kw)


def app_source(filename):
    if filename == "Aobana.bat":
        private = os.path.join(ROOT, "launchers", filename)
        if os.path.isfile(private):
            return private
    return os.path.join(ROOT, filename)


def check_whitelist():
    missing = [f for f in APP_FILES if not os.path.isfile(app_source(f))]
    missing += [f for f in REPO_FILES if not os.path.isfile(os.path.join(ROOT, f))]
    if missing:
        sys.exit(f"build: whitelisted files missing from the dev tree: {missing}")
    unsized = [f for f in APP_FILES if f.endswith(".tsv") and os.path.basename(f) not in TSV_COLUMNS]
    if unsized:
        sys.exit(f"build: {unsized} not in TSV_COLUMNS - say how many columns the loader reads")
    listed = set(APP_FILES + REPO_FILES)
    for folder, pattern in (("aobana", r".*\.(py|html)$"), ("static", r".*"), ("data/ruby", r".*\.tsv$"),
                            ("termux", r".*")):
        for dirpath, dirs, files in os.walk(os.path.join(ROOT, folder)):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for f in files:
                rel = os.path.relpath(os.path.join(dirpath, f), ROOT).replace("\\", "/")
                if re.match(pattern, f) and rel not in listed and rel not in NOT_EXPORTED:
                    sys.exit(f"build: {rel} is not in APP_FILES - add it, or say why it stays out")
    check_imports_shipped()
    check_ruby_merged()


def check_ruby_merged():
    if not os.path.isfile(os.path.join(ROOT, "data", "ruby_dev", "merge_ruby.py")):
        return
    sys.path.insert(0, os.path.join(ROOT, "data", "ruby_dev"))
    import merge_ruby
    with open(os.path.join(ROOT, "data", "ruby", "ruby.tsv"), encoding="utf-8", newline="") as f:
        if f.read() != merge_ruby.merged_text():
            sys.exit("build: data/ruby/ruby.tsv is stale - python data/ruby_dev/merge_ruby.py")


def check_imports_shipped():
    lists = {}
    for script in ("install.sh", "uninstall.sh"):
        with open(os.path.join(ROOT, "termux", script), encoding="utf-8") as fh:
            m = re.search(r'^PHONE_FILES="([^"]*)"', fh.read(), re.M)
        lists[script] = set(m.group(1).split()) if m else set()
    phone = lists["install.sh"]
    if lists["uninstall.sh"] != phone:
        sys.exit("build: termux/uninstall.sh's PHONE_FILES differs from install.sh's: "
                 f"install only {sorted(phone - lists['uninstall.sh'])}, "
                 f"uninstall only {sorted(lists['uninstall.sh'] - phone)}")
    roots = ["aobana/__main__.py", "aobana/server/app.py", "aobana/indexing/indexer.py",
             "aobana/indexing/epub_indexer.py", "aobana/indexing/manga_indexer.py",
             "aobana/indexing/analyser.py"]
    seen, todo = set(), list(roots)
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        parts = name.split("/")
        for i in range(1, len(parts)):
            init = "/".join(parts[:i] + ["__init__.py"])
            if init not in seen:
                todo.append(init)
        with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
            text = fh.read()
        mods = re.findall(r"^\s*import\s+(aobana(?:\.\w+)*)", text, re.M)
        for pkg, paren, names in re.findall(
                r"^[ \t]*from[ \t]+(aobana(?:\.\w+)*)[ \t]+import[ \t]+(?:\(([^)]*)\)|([\w \t,]+))", text, re.M):
            names = paren or names
            mods.append(pkg)
            mods += [f"{pkg}.{n.split(' as ')[0].strip()}" for n in names.split(",") if n.strip()]
        for mod in mods:
            rel = mod.replace(".", "/")
            for cand in (rel + ".py", rel + "/__init__.py"):
                if os.path.isfile(os.path.join(ROOT, cand)):
                    todo.append(cand)
    if not {"aobana/search/engine.py", "aobana/utils.py", "aobana/paths.py"} <= seen:
        sys.exit(f"build: check_imports_shipped followed only {sorted(seen)} - it no longer reads the imports")

    def on_phone(f):
        return any(f == p or f.startswith(p.rstrip("/") + "/") for p in phone)
    for name in sorted(seen):
        if name not in APP_FILES:
            sys.exit(f"build: the app needs {name}, which is not in APP_FILES")
        if not on_phone(name):
            sys.exit(f"build: the app needs {name}, which termux/install.sh's PHONE_FILES does not download")
    for name in APP_FILES:
        if name.startswith(("aobana/", "static/")) and not on_phone(name):
            sys.exit(f"build: {name} ships, but termux/install.sh's PHONE_FILES does not download it")


KEEP_MODULE_DOC = ("build.py", "make_icon.py", "build_unix.py", "smoke.py")


def _eol(line):
    return line[len(line.rstrip("\r\n")):]


def _strip_py(text, name=""):
    import ast
    import io
    import tokenize
    lines = text.splitlines(keepends=True)
    drop, repl = set(), {}
    for node in ast.walk(ast.parse(text)):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = node.body
        if not (body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            continue
        if isinstance(node, ast.Module) and name in KEEP_MODULE_DOC:
            continue
        d = body[0]
        first, last = lines[d.lineno - 1], lines[d.end_lineno - 1]
        if first[:d.col_offset].strip() or last[d.end_col_offset:].strip():
            sys.exit(f"build: {name}:{d.lineno}: a docstring shares its line with code")
        span = range(d.lineno, d.end_lineno + 1)
        if len(body) == 1:
            repl[d.lineno] = first[:d.col_offset] + "pass" + _eol(first)
            drop.update(n for n in span if n != d.lineno)
        else:
            drop.update(span)
    text = "".join(repl.get(n, line) for n, line in enumerate(lines, 1) if n not in drop)
    lines = text.splitlines(keepends=True)
    cuts = {}
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type == tokenize.COMMENT:
            cuts[tok.start[0]] = (tok.start[1], tok.string)
    out = []
    for n, line in enumerate(lines, 1):
        if n in cuts:
            col, com = cuts[n]
            code = line[:col].rstrip()
            if com.startswith("#:"):
                line = line[:col] + "#" + com[2:] + _eol(line)
            elif not code:
                continue
            else:
                line = code + _eol(line)
        out.append(line)
    text = "".join(out)
    tidy = re.sub(r"(\r?\n)(?:[ \t]*\r?\n){3,}", r"\1\1\1", text)
    return tidy if ast.dump(ast.parse(tidy)) == ast.dump(ast.parse(text)) else text


def _strip_hash(text, name="", marker="#", keep="#:"):
    out = []
    for n, line in enumerate(text.splitlines(keepends=True), 1):
        s = line.lstrip()
        if n == 1 and s.startswith("#!"):
            out.append(line)
        elif s.startswith(keep):
            out.append(line[:len(line) - len(s)] + marker + s[len(keep):])
        elif s.upper().startswith(marker.upper()):
            continue
        else:
            out.append(line)
    return "".join(out)


def _strip_iss(text, name=""):
    out, code = [], False
    for line in text.splitlines(keepends=True):
        s = line.strip()
        ind = line[:len(line) - len(line.lstrip())]
        if s.startswith("[") and s.endswith("]"):
            code = s.lower() == "[code]"
        if s.startswith(";:"):
            out.append(ind + ";" + line.lstrip()[2:])
        elif code and s.startswith("//:"):
            out.append(ind + "//" + line.lstrip()[3:])
        elif s.startswith(";") or (code and s.startswith("//")):
            continue
        else:
            if code and "  // " in line:
                line = line[:line.index("  // ")].rstrip() + _eol(line)
            out.append(line)
    return "".join(out)


def _template(s, i, end):
    while i < end:
        if s[i] == "\\":
            i += 2
        elif s[i] == "`":
            return i + 1, False
        elif s.startswith("${", i):
            return i + 2, True
        else:
            i += 1
    return end, False


def _js_comments(s, i, end, css=False):
    spans = []
    prev, word = "", ""
    regex_after = set("(,=:[!&|?{};+-*%<>~^")
    keywords = {"return", "typeof", "case", "do", "else", "in", "of", "new", "delete", "void",
                "throw", "yield", "await", "instanceof"}
    subs, depth = [], 0
    while i < end:
        c = s[i]
        if c == "/" and s.startswith("//", i) and not css:
            j = s.find("\n", i)
            j = end if j < 0 or j > end else j
            spans.append((i, j))
            i = j
        elif c == "/" and s.startswith("/*", i):
            j = s.find("*/", i + 2)
            if j < 0 or j > end:
                sys.exit("build: an unclosed /* comment")
            spans.append((i, j + 2))
            i = j + 2
        elif c in "'\"":
            j = i + 1
            while j < end and s[j] != c and s[j] != "\n":
                j += 2 if s[j] == "\\" else 1
            i, prev, word = j + 1, "a", ""
        elif c == "`" and not css:
            i, opened = _template(s, i + 1, end)
            if opened:
                subs.append(depth)
                depth += 1
                prev, word = "{", ""
            else:
                prev, word = "a", ""
        elif c == "}" and subs and depth - 1 == subs[-1]:
            depth -= 1
            subs.pop()
            i, opened = _template(s, i + 1, end)
            if opened:
                subs.append(depth)
                depth += 1
                prev, word = "{", ""
            else:
                prev, word = "a", ""
        elif c == "/" and not css and (prev in regex_after or prev == "" or word in keywords):
            j, cls = i + 1, False
            while j < end and s[j] != "\n":
                if s[j] == "\\":
                    j += 2
                    continue
                if s[j] == "[":
                    cls = True
                elif s[j] == "]":
                    cls = False
                elif s[j] == "/" and not cls:
                    break
                j += 1
            j += 1
            while j < end and s[j].isalnum():
                j += 1
            i, prev, word = j, "a", ""
        else:
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            if c.isalnum() or c in "_$":
                word = word + c if prev == "w" else c
                prev = "w"
            elif not c.isspace():
                prev, word = ("a" if c in ")]" else c), ""
            i += 1
    return spans


def _cut(s, spans, keep=None):
    out, last = [], 0
    for a, b in spans:
        if keep and s.startswith(keep, a):
            continue
        ls = s.rfind("\n", 0, a) + 1
        le = s.find("\n", b)
        le = len(s) if le < 0 else le
        if not s[ls:a].strip() and not s[b:le].strip():
            a, b = max(ls, last), min(le + 1, len(s))
        else:
            while a > ls and s[a - 1] in " \t":
                a -= 1
        out.append(s[last:a])
        last = b
    out.append(s[last:])
    return "".join(out)


def _html_spans(text):
    spans = []
    for m in re.finditer(r"<(script|style)\b[^>]*>(.*?)</\1>|<!--.*?-->", text, flags=re.S | re.I):
        if m.group(0).startswith("<!--"):
            spans.append((m.start(), m.end()))
        else:
            spans += _js_comments(text, m.start(2), m.end(2), css=m.group(1).lower() == "style")
    return spans


def _strip_html(text, name=""):
    return _cut(text, _html_spans(text), keep="//:").replace("//:", "//")


def _strip_svg(text, name=""):
    return _cut(text, [m.span() for m in re.finditer(r"<!--.*?-->", text, flags=re.S)])


def _strip_cs(text, name=""):
    return _cut(text, _js_comments(text, 0, len(text)))


def _strip_js(text, name=""):
    return _cut(text, _js_comments(text, 0, len(text)), keep="//:").replace("//:", "//")


def _strip_css(text, name=""):
    return _cut(text, _js_comments(text, 0, len(text), css=True))


def _strip_tsv(text, name=""):
    n = TSV_COLUMNS[name]
    return "".join("\t".join(line.rstrip("\r\n").split("\t")[:n]) + _eol(line)
                   for line in text.splitlines(True))


STRIPPERS = {".py": _strip_py, ".html": _strip_html, ".svg": _strip_svg, ".cs": _strip_cs,
             ".js": _strip_js, ".css": _strip_css,
             ".sh": _strip_hash, ".txt": _strip_hash, ".iss": _strip_iss, ".tsv": _strip_tsv,
             ".yml": _strip_hash,
             ".bat": lambda t, name="": _strip_hash(t, name, marker="REM", keep="REM:")}
DEV_NOTE = re.compile(r"§|docs/|task-\d|\b20\d\d-\d\d-\d\d\b|\bthe user\b|verify\.py|measure_state|"
                      r"known-facts|manual-decisions|CHANGELOG \d|\bv[1-8]\.\d\b|subagent|Gemini")


def comments(src, text):
    ext = os.path.splitext(src)[1]
    if ext == ".py":
        import ast
        import io
        import tokenize
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                yield tok.start[0], tok.string
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node, clean=False)
                if doc:
                    for i, line in enumerate(doc.splitlines()):
                        yield node.body[0].lineno + i, line
        return
    if ext in (".html", ".cs", ".js", ".css"):
        spans = (_html_spans(text) if ext == ".html"
                 else _js_comments(text, 0, len(text), css=ext == ".css"))
        for a, b in spans:
            yield text.count("\n", 0, a) + 1, text[a:b]
        return
    if ext == ".tsv":
        n = TSV_COLUMNS.get(os.path.basename(src), 0)
        for i, line in enumerate(text.splitlines(), 1):
            extra = line.split("\t")[n:]
            if extra:
                yield i, "\t".join(extra)
        return
    marker = {".iss": r"^\s*(;|//)", ".sh": r"^\s*#(?!!)", ".txt": r"^\s*#", ".yml": r"^\s*#",
              ".bat": r"(?i)^\s*rem\b", ".svg": r"<!--"}[ext]
    for n, line in enumerate(text.splitlines(), 1):
        if re.search(marker, line):
            yield n, line


def public_text(src):
    strip = STRIPPERS.get(os.path.splitext(src)[1])
    if strip is None or os.path.basename(src) in ("OFL.txt",):
        return None
    with open(src, encoding="utf-8", newline="") as fh:
        text = fh.read()
    return strip(text, os.path.basename(src))


def copy_checked(pairs):
    leaks = []
    for src, dst in pairs:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        text = public_text(src)
        if text is None:
            shutil.copy2(src, dst)
            continue
        with open(dst, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        for n, note in comments(src, text):
            if DEV_NOTE.search(note):
                leaks.append(f"{os.path.relpath(src, ROOT)}:{n}: {note.strip()[:100]}")
    if leaks:
        sys.exit("build: a kept comment carries a development note:\n  "
                 + "\n  ".join(leaks))
    bad = []
    for src, dst in pairs:
        text = public_text(src)
        if text is None:
            if sha256(src) != sha256(dst):
                bad.append(dst)
        else:
            with open(dst, encoding="utf-8", newline="") as fh:
                if fh.read() != text:
                    bad.append(dst)
    if bad:
        sys.exit(f"build: copies differ from their source: {bad}")
    return len(pairs)


def program_pairs(dest, image=False):
    pairs = [(app_source(f), os.path.join(dest, f)) for f in APP_FILES
             if not (image and f in REPO_ONLY)]
    for f in PUBLIC_FILES:
        if image and f in REPO_ONLY:
            continue
        src = next((p for p in (os.path.join(PUBLIC, f), os.path.join(ROOT, f)) if os.path.isfile(p)), None)
        if src is None:
            sys.exit(f"build: {f} not found in release/public or the repository root")
        pairs.append((src, os.path.join(dest, f)))
    return pairs


def export():
    step(f"export -> {REPO}")
    check_whitelist()
    missing = [f for f in PUBLIC_FILES + [f"assets/{a}" for a in PUBLIC_ASSETS]
               if not os.path.isfile(os.path.join(PUBLIC, f))]
    if missing:
        sys.exit(f"build: release/public is missing {missing}")
    pairs = program_pairs(REPO)
    pairs += [(os.path.join(PUBLIC, "assets", a), os.path.join(REPO, "assets", a)) for a in PUBLIC_ASSETS]
    pairs += [(os.path.join(RELEASE, f), os.path.join(REPO, "release", f)) for f in BUILD_FILES]
    pairs += [(os.path.join(RELEASE, src), os.path.join(REPO, dst)) for src, dst in WORKFLOWS.items()]
    pairs += [(os.path.join(ROOT, f), os.path.join(REPO, f)) for f in REPO_FILES]
    pairs.append((os.path.join(PUBLIC, "gitignore"), os.path.join(REPO, ".gitignore")))
    pairs.append((os.path.join(PUBLIC, "gitattributes"), os.path.join(REPO, ".gitattributes")))
    wanted = {os.path.normcase(os.path.abspath(dst)) for _, dst in pairs}
    if os.path.isdir(REPO):
        for dirpath, dirs, files in os.walk(REPO):
            dirs[:] = [d for d in dirs if d != ".git"]
            for f in files:
                p = os.path.join(dirpath, f)
                if os.path.normcase(os.path.abspath(p)) not in wanted:
                    print(f"  removed stale {os.path.relpath(p, REPO)}")
                    os.remove(p)
    print(f"  {copy_checked(pairs)} files, byte-checked against the dev tree")
    check_published(REPO)


def _kept_comments():
    kept = set()
    workflows = [os.path.join("release", w) if os.path.isfile(os.path.join(RELEASE, w)) else d
                 for w, d in WORKFLOWS.items()]
    for f in APP_FILES + REPO_FILES + [os.path.join("release", b) for b in BUILD_FILES] + workflows:
        p = app_source(f) if f in APP_FILES else os.path.join(ROOT, f)
        if STRIPPERS.get(os.path.splitext(p)[1]) is None:
            continue
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                m = re.match(r"\s*(#:|//:|;:|REM:)(.*)", line)
                if m:
                    kept.add(m.group(2).strip())
    return kept


def check_published(folder):
    kept, left = _kept_comments(), []
    icons = os.path.join(folder, "static", "icons")
    if os.path.isdir(icons) and any(os.scandir(icons)):
        sys.exit("build: private launcher icons must not ship")
    for dirpath, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in (".git", "python", "__pycache__", "assets")]
        for f in files:
            p = os.path.join(dirpath, f)
            if STRIPPERS.get(os.path.splitext(f)[1]) is None or f == "OFL.txt":
                continue
            with open(p, encoding="utf-8", newline="") as fh:
                text = fh.read()
            module_doc = set()
            if f in KEEP_MODULE_DOC:
                import ast
                tree = ast.parse(text)
                if ast.get_docstring(tree):
                    d = tree.body[0]
                    module_doc = set(range(d.lineno, d.end_lineno + 1))
            for n, note in comments(p, text):
                if n in module_doc:
                    continue
                body = re.sub(r"^\s*(#|//|;|REM\b)", "", note.strip(), flags=re.I).strip()
                if body not in kept:
                    left.append(f"{os.path.relpath(p, folder)}:{n}: {note.strip()[:90]}")
    if left:
        sys.exit(f"build: {len(left)} comments would be published (mark one #: to keep it):\n  "
                 + "\n  ".join(left[:40]))
    print(f"  no comments in {os.path.relpath(folder, ROOT)} but the {len(kept)} kept lines")


def pinned_requirements():
    pins = {}
    with open(os.path.join(ROOT, "requirements.txt"), encoding="utf-8") as fh:
        for line in fh:
            m = re.match(r"\s*([A-Za-z0-9_.-]+)==(\S+)", line)
            if m:
                pins[re.sub(r"[-_.]+", "-", m.group(1)).lower()] = m.group(2)
    return pins


def bundle_python():
    py = os.path.join(IMAGE, "python")
    if sha256(PY_ZIP) != PY_ZIP_SHA256:
        sys.exit("build: the embeddable Python zip does not match python.org's SHA-256")
    with zipfile.ZipFile(PY_ZIP) as z:
        z.extractall(py)
    pth = os.path.join(py, "python314._pth")
    with open(pth, encoding="utf-8") as fh:
        text = fh.read()
    if "#import site" not in text:
        sys.exit("build: python314._pth no longer looks as expected; check it by hand")
    text = text.replace("#import site", "import site").replace(".\n", ".\nLib\\site-packages\n..\n", 1)
    with open(pth, "w", encoding="utf-8") as fh:
        fh.write(text)
    site = os.path.join(py, "Lib", "site-packages")
    run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-index",
         "--find-links", WHEELS, "--only-binary=:all:", "--no-compile", "--target", site,
         "--platform", "win_amd64", "--python-version", "3.14", "--implementation", "cp",
         "--abi", "cp314",
         "-r", os.path.join(ROOT, "requirements.txt")])
    rmtree(os.path.join(site, "bin"))
    return py, site


def check_packages(py, exe=None, wheels_dir=WHEELS, ignore=()):
    code = ("import importlib.metadata as md, json; "
            "print(json.dumps({d.metadata['Name']: d.version for d in md.distributions()}))")
    out = subprocess.run([exe or os.path.join(py, "python.exe"), "-c", code], check=True,
                         capture_output=True, text=True).stdout
    import json
    got = {re.sub(r"[-_.]+", "-", k).lower(): v for k, v in json.loads(out).items()}
    got = {k: v for k, v in got.items() if k not in ignore}
    wheels = {}
    for w in os.listdir(wheels_dir):
        name, ver = w.split("-")[:2]
        wheels[re.sub(r"[-_.]+", "-", name).lower()] = ver
    bad = [f"{k} {v} (wanted {pinned_requirements().get(k) or wheels.get(k)})"
           for k, v in got.items() if v != (pinned_requirements().get(k) or wheels.get(k))]
    if bad or set(got) != set(wheels):
        sys.exit(f"build: bundled packages differ: {bad or sorted(set(got) ^ set(wheels))}")
    for k in sorted(got):
        print(f"  {k} {got[k]}")
    notices = next(p for p in (os.path.join(PUBLIC, "THIRD_PARTY_NOTICES.md"),
                               os.path.join(ROOT, "THIRD_PARTY_NOTICES.md")) if os.path.isfile(p))
    rows = {}
    with open(notices, encoding="utf-8") as fh:
        for line in fh:
            cells = [c.strip() for c in line.split("|")]
            if len(cells) > 3:
                rows[re.sub(r"[^a-z0-9]", "", cells[1].lower())] = cells[2]
    alias = {"beautifulsoup4": "beautifulsoup"}
    stale = [f"{k} {v}" for k, v in got.items()
             if rows.get(alias.get(k, re.sub(r"[^a-z0-9]", "", k))) != v]
    if stale:
        sys.exit(f"build: THIRD_PARTY_NOTICES.md does not list: {stale}")
    print("  THIRD_PARTY_NOTICES.md lists every bundled package at its version")


def smoke(py, exe=None, image=IMAGE):
    exe = exe or os.path.join(py, "python.exe")
    cwd = os.path.dirname(image)
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    env["PYTHONIOENCODING"] = "utf-8"
    tok = subprocess.run([exe, "-c",
                          "from sudachipy import dictionary; t = dictionary.Dictionary().create(); "
                          "print(' '.join(m.surface() for m in t.tokenize('食べられなかった')))"],
                         check=True, capture_output=True, env=env, cwd=cwd,
                         encoding="utf-8").stdout.strip()
    if tok != "食べ られ なかっ た":
        sys.exit(f"build: Sudachi smoke test gave {tok!r}")
    print(f"  Sudachi: {tok}")
    mods = ("aobana.paths, aobana.utils, aobana.server.library, aobana.indexing.indexer, "
            "aobana.indexing.epub_indexer, aobana.indexing.manga_indexer, aobana.search.engine")
    subprocess.run([exe, "-c", f"import sys; sys.path.insert(0, sys.argv[1]); import {mods}", image],
                   check=True, env=env, cwd=cwd)
    print(f"  {mods}: import")
    stray = [f for f in os.listdir(image) if f.endswith((".db", ".db-wal", ".db-shm", ".json"))
             or f in ("logs", "content", "aobana.installed")]
    stray += ["data/" + f for f in os.listdir(os.path.join(image, "data")) if f != "ruby"]
    if stray:
        sys.exit(f"build: the smoke test left files in the install image: {stray}")


def compile_launcher():
    out = os.path.join(BUILD, "launcher")
    os.makedirs(out, exist_ok=True)
    ico = os.path.join(out, "aobana.ico")
    run([sys.executable, os.path.join(RELEASE, "launcher", "make_icon.py"), ico])
    shutil.copy2(os.path.join(RELEASE, "launcher", "Aobana.cs"), out)
    v = VERSION + ".0.0"
    with open(os.path.join(out, "AssemblyInfo.cs"), "w", encoding="utf-8") as fh:
        fh.write("using System.Reflection;\n"
                 '[assembly: AssemblyTitle("Aobana")]\n[assembly: AssemblyProduct("Aobana")]\n'
                 f'[assembly: AssemblyVersion("{v}")]\n[assembly: AssemblyFileVersion("{v}")]\n')
    run([CSC, "-nologo", "-codepage:65001", "-target:winexe", "-win32icon:aobana.ico",
         "-r:System.Windows.Forms.dll", "-out:Aobana.exe", "Aobana.cs", "AssemblyInfo.cs"], cwd=out)
    copy_checked([(os.path.join(out, "Aobana.exe"), os.path.join(IMAGE, "Aobana.exe"))])
    return ico


def bundle():
    step(f"bundle -> {IMAGE}")
    check_whitelist()
    rmtree(BUILD)
    print(f"  {copy_checked(program_pairs(IMAGE, image=True))} program files, byte-checked")
    check_published(IMAGE)
    py, site = bundle_python()
    check_packages(py)
    smoke(py)
    ico = compile_launcher()
    run([os.path.join(py, "python.exe"), "-m", "compileall", "-q", "-f", "-j", "0",
         "--invalidation-mode", "checked-hash", IMAGE])
    total = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(IMAGE) for f in fs)
    print(f"  install image: {total / 2**20:.0f} MB")
    return ico


def installer(ico):
    step(f"installer -> {DIST}")
    if not os.path.isfile(ISCC):
        sys.exit(f"build: Inno Setup 7 not found at {ISCC}")
    iss = os.path.join(BUILD, "aobana.iss")
    with open(os.path.join(RELEASE, "installer", "aobana.iss"), encoding="utf-8-sig") as fh:
        text = fh.read()
    with open(iss, "w", encoding="utf-8-sig") as fh:
        fh.write(text)
    os.makedirs(DIST, exist_ok=True)
    run([ISCC, "/Qp", f"/DAppVersion={VERSION}", f"/DSourceDir={IMAGE}", f"/DIconFile={ico}",
         f"/O{DIST}", iss])
    out = os.path.join(DIST, f"Aobana-Setup-{VERSION}.exe")
    print(f"  {out}: {os.path.getsize(out) / 2**20:.0f} MB, sha256 {sha256(out)}")


def check_release_notes():
    path = os.path.join(RELEASE, f"notes-{VERSION}.md")
    if not os.path.isfile(path):
        sys.exit(f"build: {os.path.relpath(path, ROOT)} is missing - write the release notes first "
                 "(Downloads, What's Changed > Notable Changes; docs/style-guide.md section 8)")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    m = re.search(r"^###\s+Notable Changes\s*$(.*?)(?=^##|\Z)", text, re.M | re.S)
    lines = [l for l in (m.group(1).splitlines() if m else []) if l.startswith("- ")]
    if not lines:
        sys.exit(f"build: {os.path.basename(path)} has no '### Notable Changes' lines - the what's-new "
                 "window shows only those")
    print(f"  release notes: {len(lines)} notable changes")


def check_reibun_code():
    with open(os.path.join(ROOT, "static", "app.js"), encoding="utf-8") as fh:
        empty = re.search(r"const REIBUN_CODE = ''", fh.read())
    left = ["static/app.js (REIBUN_CODE)"] if empty else []
    for name in ("README.md", "README.ja.md"):
        with open(os.path.join(PUBLIC, name), encoding="utf-8") as fh:
            if "shared/info/CODE" in fh.read():
                left.append(f"release/public/{name} (CODE)")
    if left:
        sys.exit("build: the AnkiWeb code is still a placeholder in " + ", ".join(left))
    print("  AnkiWeb code: filled in")


def main(argv):
    what = argv[1] if len(argv) > 1 else "all"
    if what not in ("all", "export", "bundle", "installer", "check"):
        sys.exit(__doc__)
    if what == "check":
        check_published(REPO)
        check_reibun_code()
        return
    if what in ("all", "export"):
        export()
    if what in ("all", "installer"):
        check_release_notes()
        check_reibun_code()
    if what in ("all", "bundle", "installer"):
        ico = bundle()
        if what != "bundle":
            installer(ico)


if __name__ == "__main__":
    main(sys.argv)
