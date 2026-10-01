import os
import shutil
import subprocess
import sys
import threading

_busy = threading.Lock()


def _termux():
    return os.environ.get("AOBANA_TERMUX") == "1" or bool(os.environ.get("TERMUX_VERSION"))


def _linux_tool():
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return None
    for tool in ("zenity", "kdialog"):
        if shutil.which(tool):
            return tool
    return None


def available():
    if sys.platform == "win32":
        return True
    if sys.platform == "darwin":
        return bool(shutil.which("osascript"))
    if _termux():
        return False
    return _linux_tool() is not None


def pick(start=None, title=""):
    if not available():
        return "unavailable", None
    if not _busy.acquire(blocking=False):
        return "busy", None
    try:
        start = start if start and os.path.isdir(start) else None
        if sys.platform == "win32":
            path = _pick_windows(start, title)
        elif sys.platform == "darwin":
            path = _pick_mac(start, title)
        else:
            path = _pick_linux(start, title)
        return ("ok", path) if path else ("cancel", None)
    except Exception:
        return "unavailable", None
    finally:
        _busy.release()


def _pick_mac(start, title):
    script = ["-e", "activate"]
    prompt = (title or "").replace("\\", "\\\\").replace('"', '\\"')
    default = ""
    if start:
        default = ' default location (POSIX file "%s")' % start.replace("\\", "\\\\").replace('"', '\\"')
    script += ["-e", 'POSIX path of (choose folder with prompt "%s"%s)' % (prompt, default)]
    r = subprocess.run(["osascript", *script], capture_output=True, text=True)
    out = r.stdout.strip()
    return out.rstrip("/") or "/" if r.returncode == 0 and out else None


def _pick_linux(start, title):
    tool = _linux_tool()
    base = (start or os.path.expanduser("~")).rstrip("/") + "/"
    if tool == "zenity":
        cmd = ["zenity", "--file-selection", "--directory", "--filename", base]
        if title:
            cmd += ["--title", title]
    else:
        cmd = ["kdialog", "--getexistingdirectory", base]
        if title:
            cmd += ["--title", title]
    r = subprocess.run(cmd, capture_output=True, text=True)
    out = r.stdout.strip()
    return out if r.returncode == 0 and out else None


def _pick_windows(start, title):
    import ctypes
    from ctypes import wintypes, byref, c_void_p, POINTER, HRESULT, WINFUNCTYPE

    ole32 = ctypes.OleDLL("ole32")
    shell32 = ctypes.OleDLL("shell32")
    user32 = ctypes.WinDLL("user32", use_last_error=True)

    class GUID(ctypes.Structure):
        _fields_ = [("a", ctypes.c_uint32), ("b", ctypes.c_uint16), ("c", ctypes.c_uint16), ("d", ctypes.c_ubyte * 8)]

    def guid(s):
        g = GUID()
        ole32.CLSIDFromString(ctypes.c_wchar_p("{%s}" % s), byref(g))
        return g

    CLSID_FileOpenDialog = guid("DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7")
    IID_IFileOpenDialog = guid("D57C7288-D4AD-4768-BE02-9D969532D960")
    IID_IShellItem = guid("43826D1E-E718-42EE-BC55-A1E261C37BFE")
    FOS_PICKFOLDERS, FOS_FORCEFILESYSTEM, FOS_PATHMUSTEXIST = 0x20, 0x40, 0x800
    SIGDN_FILESYSPATH = 0x80058000
    ERROR_CANCELLED = 0x800704C7

    def method(obj, index, restype, *argtypes):
        vtbl = ctypes.cast(obj, POINTER(POINTER(c_void_p)))[0]
        return WINFUNCTYPE(restype, c_void_p, *argtypes)(vtbl[index])

    def release(obj):
        if obj:
            method(obj, 2, ctypes.c_ulong)(obj)

    ole32.CoInitializeEx(None, 0x2)
    dialog = c_void_p()
    item = c_void_p()
    folder = c_void_p()
    owner = None
    try:
        ole32.CoCreateInstance(byref(CLSID_FileOpenDialog), None, 1, byref(IID_IFileOpenDialog), byref(dialog))
        options = wintypes.DWORD()
        method(dialog, 10, HRESULT, POINTER(wintypes.DWORD))(dialog, byref(options))
        method(dialog, 9, HRESULT, wintypes.DWORD)(
            dialog, options.value | FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM | FOS_PATHMUSTEXIST)
        if title:
            method(dialog, 17, HRESULT, wintypes.LPCWSTR)(dialog, title)
        if start:
            try:
                shell32.SHCreateItemFromParsingName(ctypes.c_wchar_p(start), None, byref(IID_IShellItem), byref(folder))
                method(dialog, 12, HRESULT, c_void_p)(dialog, folder)
            except OSError:
                pass
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                           ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                           wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
        WS_EX_TOPMOST, WS_EX_TOOLWINDOW, WS_POPUP = 0x8, 0x80, 0x80000000
        owner = user32.CreateWindowExW(WS_EX_TOPMOST | WS_EX_TOOLWINDOW, "STATIC", "Aobana", WS_POPUP,
                                       0, 0, 0, 0, None, None, None, None)
        if owner:
            user32.SetForegroundWindow(owner)
        try:
            method(dialog, 3, HRESULT, wintypes.HWND)(dialog, owner)
        except OSError as e:
            if (e.winerror & 0xFFFFFFFF) == ERROR_CANCELLED:
                return None
            raise
        method(dialog, 20, HRESULT, POINTER(c_void_p))(dialog, byref(item))
        name = wintypes.LPWSTR()
        method(item, 5, HRESULT, ctypes.c_uint32, POINTER(wintypes.LPWSTR))(item, SIGDN_FILESYSPATH, byref(name))
        path = name.value
        ole32.CoTaskMemFree(name)
        return path
    finally:
        if owner:
            user32.DestroyWindow(owner)
        release(item)
        release(folder)
        release(dialog)
        ole32.CoUninitialize()
