"""Build 露草 / Aobana for macOS and Linux. Run on the system it builds for (GitHub Actions does,
see .github/workflows/build.yml); the Windows installer is release/build.py's.

    python release/build_unix.py mac      release/dist/Aobana-<ver>-macos-arm64.dmg
    python release/build_unix.py linux    release/dist/Aobana-<ver>-x86_64.AppImage
                                          release/dist/Aobana-<ver>-linux-x86_64.tar.gz

Each bundles its own Python (python-build-standalone, pinned by SHA-256 below) with the
packages pinned in requirements.txt, and carries the aobana.installed marker: the library,
the databases and the settings live in each account's data folder, never inside the app.
Downloads go to release/vendor/ and are checked against the pins before use. It needs network
for those and for the wheels (pip download, the pinned versions only).
"""
import os
import re
import shutil
import sys
import tarfile
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build
from build import (BUILD, DIST, RELEASE, ROOT, VENDOR, VERSION, check_packages,
                   check_published, check_whitelist, copy_checked, program_pairs, rmtree, run,
                   sha256, smoke, step)

UNIX = os.path.join(RELEASE, "unix")
PBS = "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/"
PYTHONS = {
    "mac": ("cpython-3.14.7+20260924-aarch64-apple-darwin-install_only.tar.gz",
            "d3da099bb2bdd57e2f5ff8496cb9827f7d92eee332b09f8dc93706dabfc51a96"),
    "linux": ("cpython-3.14.7+20260924-x86_64-unknown-linux-gnu-install_only.tar.gz",
              "5539eaf1de20bd9b5f43ea11c3c1f84cbac74fe927ac050318a9210c022618cb"),
}
APPIMAGETOOL = ("https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage",
                "ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0")
RUNTIME = ("https://github.com/AppImage/type2-runtime/releases/download/20251108/runtime-x86_64",
           "2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d")


def fetch(url, digest, name=None):
    os.makedirs(VENDOR, exist_ok=True)
    path = os.path.join(VENDOR, name or url.rsplit("/", 1)[1])
    if not os.path.isfile(path) or sha256(path) != digest:
        print(f"  download {url}", flush=True)
        urllib.request.urlretrieve(url, path + ".part")
        os.replace(path + ".part", path)
    if sha256(path) != digest:
        sys.exit(f"build: {os.path.basename(path)} does not match its pinned SHA-256")
    return path


def executable(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.chmod(path, 0o755)


def unix_file(name):
    src = os.path.join(UNIX, name)
    text = build.public_text(src)
    if text is None:
        with open(src, encoding="utf-8") as fh:
            text = fh.read()
    return text


def constraints():
    notices = next(p for p in (os.path.join(build.PUBLIC, "THIRD_PARTY_NOTICES.md"),
                               os.path.join(ROOT, "THIRD_PARTY_NOTICES.md")) if os.path.isfile(p))
    pins = []
    with open(notices, encoding="utf-8") as fh:
        for line in fh:
            cells = [c.strip() for c in line.split("|")]
            if len(cells) > 3 and re.fullmatch(r"[A-Za-z0-9_.-]+", cells[1]) \
                    and re.fullmatch(r"\d[\w.]*", cells[2]):
                pins.append(f"{cells[1]}=={cells[2]}")
    path = os.path.join(BUILD, "constraints.txt")
    os.makedirs(BUILD, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(pins) + "\n")
    return path


def image(platform, dest):
    step(f"image -> {dest}")
    check_whitelist()
    print(f"  {copy_checked(program_pairs(dest, image=True))} program files, byte-checked")
    check_published(dest)
    name, digest = PYTHONS[platform]
    with tarfile.open(fetch(PBS + name.replace("+", "%2B"), digest, name)) as tf:
        tf.extractall(dest, filter="tar")
    py = os.path.join(dest, "python")
    exe = os.path.join(py, "bin", "python3")
    wheels = os.path.join(VENDOR, f"wheels-{platform}")
    rmtree(wheels)
    req = os.path.join(ROOT, "requirements.txt")
    run([exe, "-m", "pip", "download", "--disable-pip-version-check", "--only-binary=:all:",
         "-d", wheels, "-r", req, "-c", constraints()])
    run([exe, "-m", "pip", "install", "--disable-pip-version-check", "--no-index", "--find-links",
         wheels, "--only-binary=:all:", "--no-compile", "-r", req])
    check_packages(py, exe=exe, wheels_dir=wheels, ignore=("pip",))
    smoke(py, exe=exe, image=dest)
    run([exe, "-m", "compileall", "-q", "-f", "-j", "0", "--invalidation-mode", "checked-hash", dest])
    with open(os.path.join(dest, "aobana.installed"), "w", encoding="utf-8") as fh:
        fh.write("{}\n")
    total = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(dest) for f in fs)
    print(f"  image: {total / 2**20:.0f} MB")
    return exe


def mac():
    root = os.path.join(BUILD, "mac")
    rmtree(root)
    app = os.path.join(root, "dmg", "Aobana.app")
    contents = os.path.join(app, "Contents")
    res = os.path.join(contents, "Resources")
    image("mac", os.path.join(res, "app"))
    step(f"app -> {app}")
    os.makedirs(os.path.join(contents, "MacOS"))
    with open(os.path.join(contents, "Info.plist"), "w", encoding="utf-8") as fh:
        fh.write(unix_file("Info.plist").replace("@VERSION@", VERSION))
    executable(os.path.join(contents, "MacOS", "Aobana"), unix_file("aobana-mac.sh"))
    executable(os.path.join(res, "Aobana.command"), unix_file("aobana-command.sh"))
    shutil.copy2(os.path.join(UNIX, "aobana.icns"), os.path.join(res, "aobana.icns"))
    run(["codesign", "--force", "--deep", "--sign", "-", app])
    run(["codesign", "--verify", "--deep", "--strict", app])
    os.symlink("/Applications", os.path.join(root, "dmg", "Applications"))
    os.makedirs(DIST, exist_ok=True)
    out = os.path.join(DIST, f"Aobana-{VERSION}-macos-arm64.dmg")
    if os.path.exists(out):
        os.remove(out)
    run(["hdiutil", "create", "-volname", "Aobana", "-srcfolder", os.path.join(root, "dmg"),
         "-ov", "-format", "UDZO", out])
    print(f"  {out}: {os.path.getsize(out) / 2**20:.0f} MB, sha256 {sha256(out)}")
    return out


def linux():
    root = os.path.join(BUILD, "linux")
    rmtree(root)
    name = f"Aobana-{VERSION}-linux-x86_64"
    dest = os.path.join(root, name)
    image("linux", os.path.join(dest, "app"))
    step("launch files")
    executable(os.path.join(dest, "aobana"), unix_file("aobana-run.sh"))
    executable(os.path.join(dest, "install.sh"), unix_file("install.sh"))
    executable(os.path.join(dest, "uninstall.sh"), unix_file("uninstall.sh"))
    shutil.copy2(os.path.join(UNIX, "aobana.png"), os.path.join(dest, "aobana.png"))
    with open(os.path.join(dest, "aobana.desktop"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(unix_file("aobana.desktop"))
    os.makedirs(DIST, exist_ok=True)
    outs = []

    step("tarball")
    tgz = os.path.join(DIST, name + ".tar.gz")
    run(["tar", "-C", root, "-czf", tgz, name])
    outs.append(tgz)

    step("AppImage")
    appdir = os.path.join(root, "Aobana.AppDir")
    shutil.copytree(dest, appdir, symlinks=True)
    for f in ("install.sh", "uninstall.sh"):
        os.remove(os.path.join(appdir, f))
    os.rename(os.path.join(appdir, "aobana"), os.path.join(appdir, "AppRun"))
    with open(os.path.join(appdir, "aobana.desktop"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(unix_file("aobana.desktop").replace("Exec=@EXEC@", "Exec=aobana"))
    tool = fetch(*APPIMAGETOOL)
    runtime = fetch(*RUNTIME)
    os.chmod(tool, 0o755)
    appimage = os.path.join(DIST, f"Aobana-{VERSION}-x86_64.AppImage")
    env = dict(os.environ, APPIMAGE_EXTRACT_AND_RUN="1", ARCH="x86_64")
    run([tool, "--runtime-file", runtime, "--no-appstream", appdir, appimage], env=env)
    outs.append(appimage)
    for out in outs:
        print(f"  {out}: {os.path.getsize(out) / 2**20:.0f} MB, sha256 {sha256(out)}")
    return outs


def main(argv):
    what = argv[1] if len(argv) > 1 else ""
    if what == "mac" and sys.platform == "darwin":
        mac()
    elif what == "linux" and sys.platform.startswith("linux"):
        linux()
    else:
        sys.exit(__doc__ + "\nbuild_unix: build mac on a Mac and linux on Linux.")


if __name__ == "__main__":
    main(sys.argv)
