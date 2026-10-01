import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request

from aobana import paths

HERE = paths.BASE_DIR
UPDATE_DIR = os.path.join(paths.STORE_DIR, "update")
UPDATE_MARKER = os.path.join(paths.STORE_DIR, "update.json")

ASSETS = {
    "windows": re.compile(r"^Aobana-Setup-[\d.]+\.exe$"),
    "mac": re.compile(r"^Aobana-[\d.]+-macos-arm64\.dmg$"),
    "appimage": re.compile(r"^Aobana-[\d.]+-x86_64\.AppImage$"),
    "linux": re.compile(r"^Aobana-[\d.]+-linux-x86_64\.tar\.gz$"),
}

_lock = threading.Lock()
status = {"state": "idle", "done": 0, "total": 0, "error": None}


def _mac_bundle():
    m = re.match(r"^(.*\.app)/Contents/Resources/app$", HERE)
    return m.group(1) if m else None


def _writable(folder):
    return bool(folder) and os.path.isdir(folder) and os.access(folder, os.W_OK)


def kind():
    if os.environ.get("AOBANA_TERMUX") == "1":
        return None
    if sys.platform == "win32":
        installed = os.path.isfile(os.path.join(HERE, "Aobana.exe")) and \
            os.path.isfile(os.path.join(HERE, "aobana.installed"))
        return "windows" if installed else None
    if sys.platform == "darwin":
        app = _mac_bundle()
        return "mac" if app and _writable(os.path.dirname(app)) else None
    appimage = os.environ.get("APPIMAGE")
    if appimage and os.path.isfile(appimage):
        return "appimage" if _writable(os.path.dirname(appimage)) else None
    top = os.path.dirname(HERE)
    if os.path.basename(top) == "aobana-app" and os.path.isfile(os.path.join(top, "install.sh")) \
            and _writable(os.path.dirname(top)):
        return "linux"
    return None


def pick_asset(release):
    k = kind()
    if not k or not release:
        return None
    for asset in release.get("assets") or []:
        if ASSETS[k].match(str(asset.get("name") or "")):
            return asset
    return None


def start(release, lang, current, exit_soon):
    asset = pick_asset(release)
    if not asset:
        return "unavailable"
    with _lock:
        if status["state"] in ("downloading", "installing"):
            return "busy"
        status.update(state="downloading", done=0, total=int(asset.get("size") or 0), error=None)
    threading.Thread(target=_run, args=(release, asset, lang, current, exit_soon), daemon=True).start()
    return None


def _fail(code):
    status.update(state="error", error=code)


def _run(release, asset, lang, current, exit_soon):
    try:
        shutil.rmtree(UPDATE_DIR, ignore_errors=True)
        os.makedirs(UPDATE_DIR, exist_ok=True)
        target = os.path.join(UPDATE_DIR, asset["name"])
        digest = hashlib.sha256()
        req = urllib.request.Request(asset["browser_download_url"],
                                     headers={"User-Agent": f"Aobana/{current}"})
        with urllib.request.urlopen(req, timeout=30) as resp, open(target, "wb") as out:
            if not status["total"]:
                status["total"] = int(resp.headers.get("Content-Length") or 0)
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                digest.update(chunk)
                status["done"] += len(chunk)
    except Exception:
        return _fail("download")
    want = str(asset.get("digest") or "")
    if (asset.get("size") and os.path.getsize(target) != int(asset["size"])) or \
            (want.startswith("sha256:") and want[7:].lower() != digest.hexdigest()):
        shutil.rmtree(UPDATE_DIR, ignore_errors=True)
        return _fail("verify")
    try:
        with open(UPDATE_MARKER, "w", encoding="utf-8") as fh:
            json.dump({"from": current, "to": str(release.get("tag_name") or "").lstrip("vV"),
                       "kind": kind(), "at": time.time()}, fh)
        _spawn_helper(target, lang)
    except Exception:
        return _fail("install")
    status["state"] = "installing"
    exit_soon()


def _spawn_helper(target, lang):
    k = kind()
    log = os.path.join(UPDATE_DIR, "update.log")
    pids = [str(os.getpid()), str(os.getppid())]
    if k == "windows":
        script = os.path.join(UPDATE_DIR, "update.ps1")
        with open(script, "w", encoding="utf-8-sig") as fh:
            fh.write(WINDOWS_HELPER)
        args = ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                "-WindowStyle", "Hidden", "-File", script,
                "-Installer", target, "-AppDir", HERE, "-Lang", "ja" if lang == "ja" else "en",
                "-Pids", ",".join(pids), "-Log", log]
        NO_WINDOW, NEW_GROUP, BREAKAWAY = 0x08000000, 0x200, 0x01000000
        try:
            subprocess.Popen(args, creationflags=NO_WINDOW | NEW_GROUP | BREAKAWAY, close_fds=True)
        except OSError:
            subprocess.Popen(args, creationflags=NO_WINDOW | NEW_GROUP, close_fds=True)
        return
    script = os.path.join(UPDATE_DIR, "update.sh")
    with open(script, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(UNIX_HELPER)
    if k == "mac":
        place = _mac_bundle()
    elif k == "appimage":
        place = os.environ["APPIMAGE"]
    else:
        place = os.path.dirname(HERE)
    env = {key: v for key, v in os.environ.items() if key not in ("AOBANA_NO_TERMINAL", "APPIMAGE", "APPDIR")}
    subprocess.Popen(["/bin/bash", script, k, target, place, log, " ".join(pids)],
                     env=env, start_new_session=True, close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def after_update():
    try:
        with open(UPDATE_MARKER, encoding="utf-8") as fh:
            marker = json.load(fh)
    except Exception:
        return None
    try:
        os.remove(UPDATE_MARKER)
    except OSError:
        pass
    for name in os.listdir(UPDATE_DIR) if os.path.isdir(UPDATE_DIR) else []:
        if name != "update.log":
            p = os.path.join(UPDATE_DIR, name)
            shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else _remove(p)
    return marker if time.time() - float(marker.get("at") or 0) < 3600 else None


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


WINDOWS_HELPER = r"""param([string]$Installer, [string]$AppDir, [string]$Lang, [string]$Pids, [string]$Log)
function Note($s) { Add-Content -LiteralPath $Log -Value ("{0:s} {1}" -f (Get-Date), $s) -Encoding UTF8 }
Note "waiting for $Pids"
foreach ($p in $Pids.Split(',')) { Wait-Process -Id ([int]$p) -Timeout 60 -ErrorAction SilentlyContinue }
# The bundled Python must be closed before the installer replaces it.
$end = (Get-Date).AddSeconds(30)
while ((Get-Date) -lt $end) {
  $busy = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path.StartsWith("$AppDir\python\", [StringComparison]::OrdinalIgnoreCase) }
  if (-not $busy) { break }
  Start-Sleep -Milliseconds 300
}
Note "installing $Installer"
try {
  $proc = Start-Process -FilePath $Installer -ArgumentList '/SILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/LANG=$Lang" -Wait -PassThru
  Note ("installer exit code {0}" -f $proc.ExitCode)
} catch { Note ("installer did not run: {0}" -f $_) }
Note "starting Aobana"
Start-Process -FilePath (Join-Path $AppDir 'Aobana.exe') -WorkingDirectory $AppDir
Remove-Item -LiteralPath $Installer -Force -ErrorAction SilentlyContinue
"""

UNIX_HELPER = r"""#!/bin/bash
# kind, the downloaded file, where the app lives, a log, the pids to wait for.
KIND="$1"; NEW="$2"; PLACE="$3"; LOG="$4"; PIDS="$5"
exec >>"$LOG" 2>&1
echo "$(date) waiting for $PIDS"
for p in $PIDS; do
  for i in $(seq 1 200); do kill -0 "$p" 2>/dev/null || break; sleep 0.3; done
done
echo "$(date) installing $NEW ($KIND)"
case "$KIND" in
  mac)
    MNT="$(mktemp -d)"
    if hdiutil attach "$NEW" -nobrowse -readonly -mountpoint "$MNT"; then
      DIR="$(dirname "$PLACE")"
      rm -rf "$DIR/.Aobana-update.app" "$DIR/.Aobana-old.app"
      if ditto "$MNT/Aobana.app" "$DIR/.Aobana-update.app"; then
        if mv "$PLACE" "$DIR/.Aobana-old.app"; then
          if mv "$DIR/.Aobana-update.app" "$PLACE"; then
            rm -rf "$DIR/.Aobana-old.app"
          else
            mv "$DIR/.Aobana-old.app" "$PLACE"
          fi
        fi
        xattr -dr com.apple.quarantine "$PLACE" 2>/dev/null
      fi
      rm -rf "$DIR/.Aobana-update.app"
      hdiutil detach "$MNT" -quiet
    fi
    rmdir "$MNT" 2>/dev/null
    rm -f "$NEW"
    echo "$(date) starting Aobana"
    open "$PLACE"
    ;;
  appimage)
    if cp "$NEW" "$PLACE.new" && chmod +x "$PLACE.new"; then
      mv -f "$PLACE.new" "$PLACE"
    fi
    rm -f "$NEW" "$PLACE.new"
    echo "$(date) starting Aobana"
    setsid "$PLACE" </dev/null >/dev/null 2>&1 &
    ;;
  linux)
    T="$(mktemp -d)"
    if tar -xzf "$NEW" -C "$T"; then
      SRC="$(find "$T" -mindepth 2 -maxdepth 2 -name install.sh | head -n 1)"
      [ -n "$SRC" ] && bash "$SRC"
    fi
    rm -rf "$T" "$NEW"
    echo "$(date) starting Aobana"
    setsid "$PLACE/aobana" </dev/null >/dev/null 2>&1 &
    ;;
esac
"""
