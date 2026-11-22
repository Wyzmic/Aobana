import os
import struct
import sys
import threading

_MAX_FILES = 6000
_EXTS = (".ttf", ".otf", ".ttc", ".otc")
_LOCK = threading.Lock()
_CACHE = None


def _font_dirs():
    home = os.path.expanduser("~")
    if sys.platform == "win32":
        win = os.environ.get("WINDIR") or os.environ.get("SystemRoot") or r"C:\Windows"
        local = os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
        return [os.path.join(win, "Fonts"), os.path.join(local, "Microsoft", "Windows", "Fonts")]
    if sys.platform == "darwin":
        return ["/System/Library/Fonts", "/Library/Fonts", os.path.join(home, "Library", "Fonts")]
    data = os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")
    prefix = os.environ.get("PREFIX", "")
    dirs = ["/usr/share/fonts", "/usr/local/share/fonts", os.path.join(home, ".fonts"), os.path.join(data, "fonts"),
            "/system/fonts"]
    if prefix:
        dirs.append(os.path.join(prefix, "share", "fonts"))
    return dirs


def _font_files():
    seen = set()
    for top in _font_dirs():
        if not os.path.isdir(top):
            continue
        for root, _dirs, files in os.walk(top):
            for name in files:
                if name.lower().endswith(_EXTS):
                    path = os.path.join(root, name)
                    key = os.path.normcase(os.path.realpath(path))
                    if key not in seen:
                        seen.add(key)
                        yield path
                        if len(seen) >= _MAX_FILES:
                            return


def _read(fh, offset, size):
    fh.seek(offset)
    data = fh.read(size)
    if len(data) != size:
        raise ValueError("short read")
    return data


def _tables(fh, base):
    num = struct.unpack(">H", _read(fh, base + 4, 2))[0]
    raw = _read(fh, base + 12, 16 * num)
    out = {}
    for i in range(num):
        tag, _sum, off, length = struct.unpack(">4sIII", raw[16 * i:16 * i + 16])
        out[tag] = (off, length)
    return out


def _names(fh, table):
    off, length = table
    data = _read(fh, off, min(length, 1 << 20))
    _fmt, count, storage = struct.unpack(">HHH", data[:6])
    found = {}
    for i in range(count):
        rec = data[6 + 12 * i:18 + 12 * i]
        if len(rec) < 12:
            break
        plat, enc, lang, nid, ln, so = struct.unpack(">HHHHHH", rec)
        if nid not in (1, 16):
            continue
        raw = data[storage + so:storage + so + ln]
        if plat == 3 or plat == 0:
            text = raw.decode("utf-16-be", "replace")
        elif plat == 1 and enc == 0:
            text = raw.decode("mac_roman", "replace")
        else:
            continue
        found[(plat, lang, nid)] = text.strip("\x00 ").strip()
    def pick(langs):
        for nid in (16, 1):
            for plat, lang in langs:
                text = found.get((plat, lang, nid))
                if text:
                    return text
        return ""
    english = pick([(3, 0x409), (1, 0), (0, 0)]) or next((v for k, v in found.items() if k[0] == 3 and k[2] in (16, 1)), "")
    japanese = pick([(3, 0x411), (1, 11)])
    return english, japanese


def _has_char(fh, table, cp):
    off, _length = table
    head = _read(fh, off, 4)
    count = struct.unpack(">H", head[2:4])[0]
    recs = _read(fh, off + 4, 8 * count)
    subs = {}
    for i in range(count):
        plat, enc, so = struct.unpack(">HHI", recs[8 * i:8 * i + 8])
        subs[(plat, enc)] = off + so
    for key in ((3, 10), (0, 4), (0, 6), (3, 1), (0, 3), (0, 1)):
        if key not in subs:
            continue
        pos = subs[key]
        fmt = struct.unpack(">H", _read(fh, pos, 2))[0]
        if fmt == 12:
            n = struct.unpack(">I", _read(fh, pos + 12, 4))[0]
            groups = _read(fh, pos + 16, 12 * n)
            for i in range(n):
                start, end, _gid = struct.unpack(">III", groups[12 * i:12 * i + 12])
                if start <= cp <= end:
                    return True
            return False
        if fmt == 4 and cp <= 0xFFFF:
            length = struct.unpack(">H", _read(fh, pos + 2, 2))[0]
            sub = _read(fh, pos, length)
            seg2 = struct.unpack(">H", sub[6:8])[0]
            segs = seg2 // 2
            ends = struct.unpack(f">{segs}H", sub[14:14 + seg2])
            starts = struct.unpack(f">{segs}H", sub[16 + seg2:16 + 2 * seg2])
            deltas = struct.unpack(f">{segs}h", sub[16 + 2 * seg2:16 + 3 * seg2])
            ranges_at = 16 + 3 * seg2
            for i in range(segs):
                if starts[i] <= cp <= ends[i]:
                    ro = struct.unpack(">H", sub[ranges_at + 2 * i:ranges_at + 2 * i + 2])[0]
                    if ro == 0:
                        return (cp + deltas[i]) & 0xFFFF != 0
                    at = ranges_at + 2 * i + ro + 2 * (cp - starts[i])
                    gid = struct.unpack(">H", sub[at:at + 2])[0] if at + 2 <= len(sub) else 0
                    return gid != 0
            return False
    return False


def _japanese_code_page(fh, table):
    off, length = table
    if length < 86:
        return False
    version = struct.unpack(">H", _read(fh, off, 2))[0]
    if version < 1:
        return False
    page1 = struct.unpack(">I", _read(fh, off + 78, 4))[0]
    # The Japanese code page, and no Korean one: a Korean font may claim every CJK page.
    return bool(page1 & (1 << 17)) and not page1 & ((1 << 19) | (1 << 21))


def _faces(path):
    with open(path, "rb") as fh:
        head = _read(fh, 0, 12)
        if head[:4] == b"ttcf":
            num = min(struct.unpack(">I", head[8:12])[0], 64)
            bases = struct.unpack(f">{num}I", _read(fh, 12, 4 * num))
        elif head[:4] in (b"\x00\x01\x00\x00", b"OTTO", b"true"):
            bases = (0,)
        else:
            return
        for base in bases:
            try:
                tables = _tables(fh, base)
                if b"name" not in tables or b"cmap" not in tables:
                    continue
                english, japanese = _names(fh, tables[b"name"])
                # Japanese: kana in the font, and a Japanese name or the Japanese code page; Chinese
                # and Korean fonts carry kana too, but neither of the other two.
                if not english or not _has_char(fh, tables[b"cmap"], 0x3042):
                    continue
                if not japanese and not (b"OS/2" in tables and _japanese_code_page(fh, tables[b"OS/2"])):
                    continue
                yield english, japanese
            except (ValueError, struct.error, OSError):
                continue


def _scan():
    families = {}
    for path in _font_files():
        try:
            for english, japanese in _faces(path):
                # A name that starts with a dot is the system's own; the default is listed apart.
                if english.startswith(".") or english.lower() == "noto sans jp" or english.startswith("@"):
                    continue
                key = english.lower()
                if key not in families or (japanese and not families[key]["name_ja"]):
                    families[key] = {"family": english, "name_ja": japanese if japanese != english else ""}
        except (ValueError, struct.error, OSError):
            continue
    return sorted(families.values(), key=lambda f: f["family"].lower())


def japanese_fonts():
    global _CACHE
    with _LOCK:
        if _CACHE is None:
            _CACHE = _scan()
        return list(_CACHE)
