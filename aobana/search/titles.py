
import re


def to_fullwidth(num_str, pad=1):
    trans = str.maketrans('0123456789', '０１２３４５６７８９')
    return str(int(num_str)).zfill(pad).translate(trans)


GLOBAL_TITLES = {}
GLOBAL_BOOK_TITLES = {}
GLOBAL_MANGA_TITLES = {}

def get_formatted_title(db_conn, relpath):
    global GLOBAL_TITLES
    if relpath not in GLOBAL_TITLES:
        GLOBAL_TITLES[relpath] = format_episode_title(relpath)
    return GLOBAL_TITLES[relpath]


FW_TO_HW_DIGITS = str.maketrans('０１２３４５６７８９', '0123456789')
_KANJI_DIGITS = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}


def parse_int_or_kanji(s):
    s = s.translate(FW_TO_HW_DIGITS)
    if s.isdigit():
        return int(s)
    total = curr = 0
    for ch in s:
        if ch in _KANJI_DIGITS:
            curr = _KANJI_DIGITS[ch]
        elif ch == '十':
            total += (curr or 1) * 10
            curr = 0
        elif ch == '百':
            total += (curr or 1) * 100
            curr = 0
        else:
            return None
    total += curr
    return total or None


SUB_EXT_RE = re.compile(r"\.(?:srt|ass|ssa)$", re.IGNORECASE)
SUB_LANG_SUFFIX_RE = re.compile(
    r"[\._\-](?:ja|jp|jpn|jap|ja[\-_]jp|ja[\-_]en|jpn[\-_]en|jp[\-_]en|chs|cht|zh|en|eng)"
    r"(?:[\._\-](?:sdh|cc|hi|forced|full))?(?:\[(?:cc|sdh|hi|forced)\])?$",
    re.IGNORECASE,
)
SUB_CRC_RE = re.compile(r"\s*[\[\(（]\s*[0-9A-Fa-f]{8}\s*[\]\)）]")
SUB_LEADING_GROUP_RE = re.compile(r"^\s*\[([^\]]*)\]\s*")
SUB_PURE_EP_BRACKET_RE = re.compile(
    r"^(?:\d{1,3}(?:v\d+)?(?:[～\-・/]\d{1,3}(?:v\d+)?)?|第\s*[0-9０-９]{1,4}\s*話)$", re.IGNORECASE)
SUB_SEASON_IN_BRACKET_RE = re.compile(
    r"(?:\d+(?:st|nd|rd|th)\s+Season|Season\s+\d+|第[0-9０-９一二三四五六七八九十]+(?:期|季|シリーズ))",
    re.IGNORECASE,
)
SUB_SE_RE = re.compile(
    r"(?:^|(?<![A-Za-z0-9]))S(\d{1,2})[\s\._\-]*E(?:P)?(\d{1,4})"
    r"(?:[\s\._\-]*(?:[\-~～]|E(?:P)?)(\d{1,4}))?(?:v\d+)?(?![A-Za-z0-9])",
    re.IGNORECASE,
)
SUB_SXE_RE = re.compile(r"(?:^|(?<![A-Za-z0-9x×]))(\d{1,2})x(\d{2,3})(?:v\d+)?(?![A-Za-z0-9x×])", re.IGNORECASE)
SUB_SPE_RE = re.compile(r"(?:^|[\s\.\-_\[（\(])SPE(\d{1,2})(?:\b|[\s\.\-_\]）\)])", re.IGNORECASE)
SUB_EP_MULTI_PREFIX_RE = re.compile(
    r"(?: - |[#＃]|第|\[|(?i:(?:^|(?<![A-Za-z0-9]))EP?[\s\._]*)|[（\(])"
    r"([0-9０-９]{1,3})(?:v\d+)?"
    r"(?:([～\-・/])(?:[#＃]|第|(?i:EP?))?([0-9０-９]{1,3})(?:v\d+)?)?"
    r"(?:話|回|幕| |\.|_|$|\]|[）\)]|(?=[「『【]))"
)
SUB_DAI_KANJI_EP_RE = re.compile(r"第\s*([0-9０-９一二三四五六七八九十百]{1,5})\s*(話|回|幕|首)(?:[\s\._\-]*|$|(?=[「『【]))")
SUB_FOUR_DIGIT_EP_RE = re.compile(r"\s+-\s+(0\d{3}|1[0-8]\d{2})(?:\s+-\s+|\b)")
SUB_BOGUS_EP_NUMS = frozenset({480, 576, 720, 1080, 1440, 1920, 2160})
SUB_SECONDARY_EP_RE = re.compile(
    r"^(?:"
    r"第([一二三四五六七八九十百0-9０-９]+)(話|幕|首|回|章)(?:[\.\s_]*|(?=[「『【!！末：:])|$)|"
    r"[#＃]?([一二三四五六七八九十百0-9０-９]+)(話|幕|首|回)(?:[\.\s_]+|(?=[「『【!！])|$)|"
    r"[#＃]([0-9０-９]{1,4})(?:[\.\s_]+|(?=[「『【])|$)|"
    r"([0-9０-９]{1,3})[\.\s_]+(?![0-9]|\s*(?:p|i|bit|fps|ch)\b)"
    r")"
)
SUB_BRACKET_JUNK_RE = re.compile(
    r"[\[\(][^\]\)]*?(?<!"
    r"[A-Za-z0-9])(?:"
    r"1080[pi]|720p|480p|576p|2160p|4K|FHD|HDTV|HEVC|AVC|AAC|FLAC|AC3|EAC3|DTS|MP3|Opus|"
    r"x264|x265|H\.?264|H\.?265|XviD|DivX|WMV9|MPEG2|RMVB|MKV|AVI|MP4|10bit|8bit|Hi10p?|"
    r"WEBRip|WEB-DL|WEBDL|WEB|BDRip|BDREMUX|BDSUP|BDSUB|BD|BluRay|Blu-ray|DVDRip|DVD-Rip|DVD|TVRip|"
    r"FFF|JPN|JAP|CHS|CHT|ENG|JPSC|JPTC|SC[\s_]*JP|JP[\s_]*SC|Japanese[\s_]*Origin|"
    r"TX|AMZN|NF|DSNP|CR|DDP|Amazon|Netflix|Hulu|Disney|Crunchyroll|Bilibili|Abema|dAnime|"
    r"SubtitleTools|Sakurato|Retimed|Re-Timed|OCR\s*unchecked|Tesseract\s*OCR|Zoro\.to|SoftSub|HardSub|big5|gbk|utf-?8|ass|srt|ssa|"
    r"1920x1080|1280x720|720x480|640x480|848x480|1440x1080|"
    r"AT-X|BS11|BSP|NHK|NHKG|NHKE|TOKYO\s*MX|MBS|TBS"
    r")(?![A-Za-z0-9])[^\]\)]*?[\]\)]",
    re.IGNORECASE,
)
SUB_EXACT_BRACKET_JUNK_RE = re.compile(
    r"\s*(?:[\[\(（](?:TV|BD|DVD|WEB|720|1080|480|AT-X|BS11|BSP|NHK|TOKYO\s*MX|MBS|TBS|JP|JA|JPN|SS|cc|sdh|hi|forced|jp_cn|ch_jp|jpn,\s*chi|日本語字幕|吹き替え|日本語|字|BS4K同時放送)[\]\)）]|\[(?:二|多|解|デ|閉|初|再|新|終)\])",
    re.IGNORECASE,
)
SUB_SPLIT_JUNK_RE = re.compile(
    r"(?: - |\s*\[|\(|\s+|[\._]|^|(?<=[」』】\)）]))(?:"
    r"DUAL|DualAudio|1080[pi]|720p|480p|576p|2160p|HD1080[pi]|HD720p|1080pNF|720pNF|Horriblesubs720p|Horriblesubs1080p|"
    r"WEB(?=$|[\s\._\-\]\)）])|WEBRip|WEB-DL|WEBDL|BDRip|BluRay|Blu-ray|BDSUP|BDSUB|BDsub|ITBD|BD(?=$|[\s\._\-\]\)）])|DVDRip|"
    r"HDTV|HEVC|hevc10|x264|x265|H\.?264|H\.?265|10bit|8bit|Hi10p?|AAC|FLAC|AC3|JPSC|JPTC|Re-?Timed\s+for|"
    r"Netflix|Amazon|AMZN|NF(?=$|[\s\._\-\[\(（\)）])|Hulu|UNCENSORED|REPACK|PROPER"
    r")(?=$|[\s\._\-\[\(（\)）])",
    re.IGNORECASE,
)
SUB_TECH_BRACKET_RE = re.compile(
    r"[\[\(（【][^\]\)）】]*?(?:@|(?<![A-Za-z0-9])(?:hevc\d*|crf|\d{3,4}[x×]\d{3,4})(?![A-Za-z0-9]))[^\]\)）】]*[\]\)）】]",
    re.IGNORECASE,
)
SUB_TECH_TAIL_RE = re.compile(
    r"[\s\._\-]*(?<![A-Za-z0-9])(?:\d{3,4}-\d{3,4}@|\S*@KFMVFR|hevc\d+(?![A-Za-z])|\d{3,4}[x×]\d{3,4}(?![0-9]))",
    re.IGNORECASE,
)
SUB_SEASON_WORD_RE = re.compile(
    r"シーズン\s*([0-9０-９]{1,2})(?:\s*(?=[#＃第]|EP?\s*\d)|[-_]([0-9０-９]{1,3})[-_ ])", re.IGNORECASE
)
SUB_SPECIAL_MARKER_RE = re.compile(r"(総集編|特別編|特別篇|番外編|完結編|スペシャル)\s*(?=[#＃第]|EP?\s*\d| - )", re.IGNORECASE)
SUB_ZH_WORD_RE = re.compile(r"字幕|简|繁|BIG5|中日|双语|雙語|汉化|卖萌", re.IGNORECASE)
SUB_JPTVCLUB_RE = re.compile(r"[\s_\-]*\d{4}-\d{2}-\d{2}[\s_\-]*JPTVclub$", re.IGNORECASE)
SUB_BARE_LANG_RE = re.compile(
    r"^(?:ja|jp|jpn|jap|sc|tc|jpsc|jptc|ja[\-_ ]jp|ja[\-_ ]en|jpn[\-_ ]en|chs|cht|en|eng|big5|retimed)$",
    re.IGNORECASE,
)
SUB_TRAILING_LANG_RE = re.compile(r"(?i)(?:^|\s+)(?:ja|jp|jpn|jap|jpsc|jptc|ja[\-_]jp|ja[\-_]en)(?:\s*\[(?:cc|sdh|hi)\])?$")
_ROMAN = {'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5, 'VI': 6, 'VII': 7, 'VIII': 8, 'IX': 9, 'X': 10, 'XI': 11, 'XII': 12}


def _wrapped_by(s, open_ch, close_ch):
    if len(s) < 2 or s[0] != open_ch or s[-1] != close_ch:
        return False
    depth = 0
    for i, ch in enumerate(s):
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return i == len(s) - 1
    return False


def _strip_outer_brackets(s):
    s = s.strip(" ._")
    while s:
        if s[0] in " ._)]":
            s = s[1:].lstrip(" ._")
        elif s[-1] in " ._([":
            s = s[:-1].rstrip(" ._")
        elif s.endswith("()") or s.endswith("[]"):
            s = s[:-2].rstrip(" ._")
        elif s.startswith("()") or s.startswith("[]"):
            s = s[2:].lstrip(" ._")
        elif _wrapped_by(s, "(", ")") or _wrapped_by(s, "[", "]"):
            s = s[1:-1].strip(" ._")
        elif s.startswith("(") and s.count("(") > s.count(")"):
            s = s[1:].lstrip(" ._")
        elif s.endswith(")") and s.count(")") > s.count("("):
            s = s[:-1].rstrip(" ._")
        elif s.startswith("[") and s.count("[") > s.count("]"):
            s = s[1:].lstrip(" ._")
        elif s.endswith("]") and s.count("]") > s.count("["):
            s = s[:-1].rstrip(" ._")
        else:
            break
    return s


def _episode_stem(filename):
    s = filename
    for _ in range(2):
        s = SUB_EXT_RE.sub("", s)
    for _ in range(2):
        s = SUB_LANG_SUFFIX_RE.sub("", s)
        s = SUB_CRC_RE.sub("", s)
    while True:
        m = SUB_LEADING_GROUP_RE.match(s)
        if not m:
            break
        inner = m.group(1).strip()
        rest = s[m.end():].lstrip()
        if not rest.strip() or SUB_PURE_EP_BRACKET_RE.match(inner) or SUB_SEASON_IN_BRACKET_RE.search(inner):
            break
        s = rest
    return s


def subtitle_group(relpath):
    parts = [part.translate(FW_TO_HW_DIGITS) for part in re.split(r"[\\/]", relpath)[1:]]
    clues = "/".join(parts)
    if re.search(r"(?<![A-Za-z0-9])OVA(?![A-Za-z0-9])", clues, re.I):
        return {"kind": "ova", "label": "OVA", "order": 1001}
    if re.search(r"劇場版|映画|\[映\]|(?<![A-Za-z0-9])(?:Movie|Film)(?![A-Za-z0-9])", clues, re.I):
        return {"kind": "movie", "label": "劇場版", "order": 1002}
    for part in reversed(parts):
        match = SUB_SE_RE.search(part)
        if not match:
            match = re.search(r"(?<![0-9一二三四五六七八九十百])(?:第)?([0-9一二三四五六七八九十]{1,3})(?:期|季|シリーズ)", part)
        if not match:
            match = SUB_SEASON_WORD_RE.search(part)
        if not match:
            match = re.search(r"([0-9]+)(?:st|nd|rd|th)\b", part, re.I)
        if not match:
            match = re.search(r"(?<![A-Za-z0-9])(?:Season[\s_.-]*|S)(\d{1,2})(?!\d)(?:$|[\s_.-]|E\d)", part, re.I)
        season = parse_int_or_kanji(match.group(1)) if match else None
        if season and 1 <= season <= 99:
            return {"kind": "season", "label": f"{season}期", "order": season}
    return {"kind": "other", "label": "", "order": 1003}


_FILM_FILE_RE = re.compile(r'(?:Movie|Film|劇場版|映画|劇場|\[映\])', re.IGNORECASE)


def episode_order(items, grouping=True):
    if any('話' in x['title'] for x in items):
        items.sort(key=lambda x: (1 if '話' in x['title'] else (0 if _FILM_FILE_RE.search(x['file']) else 1),
                                  x['file']))
    if not grouping:
        return
    clues = [subtitle_group(x['file']) for x in items]
    if (any(re.split(r"[\\/]", x['file'])[1:-1] for x in items)
            or any(g['kind'] == 'season' for g in clues)
            or (len(items) > 1 and any(g['kind'] == 'ova' for g in clues))):
        for x, g in zip(items, clues):
            x['subtitle_group'] = g
        items.sort(key=lambda x: x['subtitle_group']['order'])


def _format_episode_title_accepted(relpath):
    from aobana import utils
    parts = re.split(r"[\\/]", relpath)
    folder_name = parts[0]
    raw_filename = parts[-1]
    filename = _episode_stem(raw_filename)
    orig_stem = utils.clean_sub_stem(raw_filename)
    stem_cleaned_more = filename != orig_stem

    season_ep = ""
    title = ""

    match_se = SUB_SE_RE.search(filename)
    match_sxe = None if match_se else SUB_SXE_RE.search(filename)
    if match_sxe:
        s_cand, e_cand = int(match_sxe.group(1)), int(match_sxe.group(2))
        if not (1 <= s_cand <= 30 and 1 <= e_cand <= 250) or (s_cand == 3 and e_cand == 3 and "3x3" in filename.lower()):
            match_sxe = None

    if match_se or match_sxe:
        if match_se:
            s = int(match_se.group(1))
            e = int(match_se.group(2))
            e2_raw = int(match_se.group(3)) if match_se.group(3) else None
            if e2_raw is not None and e < e2_raw <= e + 12:
                e2 = e2_raw
                se_end = match_se.end()
            else:
                e2 = None
                se_end = match_se.end(2)
                if filename[se_end:match_se.end()].lower().startswith("v"):
                    se_end = match_se.end()
        else:
            s = int(match_sxe.group(1))
            e = int(match_sxe.group(2))
            e2 = None
            se_end = match_sxe.end()

        if e2 is not None:
            season_ep = f"{to_fullwidth(s)}期{to_fullwidth(e, 2)}～{to_fullwidth(e2, 2)}話"
        else:
            season_ep = f"{to_fullwidth(s)}期{to_fullwidth(e, 2)}話"

        title_part = filename[se_end:]
        is_fractional = bool(re.match(r"^\.\d+\b", title_part))
        title_part = re.split(r"\.(?:WEBRip|WEB-DL|WEBDL|BDRip|BluRay|DVDRip|BD|2160p|1080[pi]|720p|576p|480p)",
                              title_part, flags=re.IGNORECASE)[0]
        title_part = title_part.strip(" ._")

        m_ep = None if is_fractional else SUB_SECONDARY_EP_RE.match(title_part)
        if m_ep:
            ep_num_str = m_ep.group(1) or m_ep.group(3) or m_ep.group(5) or m_ep.group(6)
            counter = m_ep.group(2) or m_ep.group(4) or ""
            rest = title_part[m_ep.end():].strip(" ._")
            ep_hw = ep_num_str.translate(FW_TO_HW_DIGITS)
            if ep_hw.isdigit():
                ep_num = int(ep_hw)
                if ep_num == e:
                    title_part = rest
                elif counter not in ("回", "章"):
                    title_part = f"{to_fullwidth(ep_num)}話｜{rest}" if rest else f"{to_fullwidth(ep_num)}話"
            else:
                title_part = rest

        title_part = re.sub(r"^(?:最終話|最終章(?:\.前編|\.後編)?)[\.\s]*", "", title_part)
        title_part = re.sub(r"^【.*?】", "", title_part)
        title_part = re.split(r"(?:WEBRip|WEB-DL|WEBDL|BDRip|BluRay|DVDRip|BD|2160p|1080[pi]|720p|576p|480p)",
                              title_part, flags=re.IGNORECASE)[0]
        title = title_part.strip(" ._").replace(".", " ").replace("_", " ")
    else:
        s_str = ""
        match_s = re.search(r"([０-９0-9]+)(?:st|nd|rd|th)\b", filename, re.IGNORECASE)
        if match_s:
            s_str = f"{to_fullwidth(match_s.group(1).translate(FW_TO_HW_DIGITS))}期"
            filename = filename[:match_s.start()] + filename[match_s.end():]
        else:
            match_s = SUB_SEASON_WORD_RE.search(filename)
            if match_s:
                s_str = f"{to_fullwidth(match_s.group(1).translate(FW_TO_HW_DIGITS))}期"
                ep_here = f" ＃{match_s.group(2)} " if match_s.group(2) else " "
                filename = filename[:match_s.start()] + ep_here + filename[match_s.end():]

        match_jp_se = re.search(r"第([０-９0-9]+)(?:シリーズ|期)(.*?)[（\(]([０-９0-9]{2,3})[）\)]", filename)
        if match_jp_se:
            s = int(match_jp_se.group(1).translate(FW_TO_HW_DIGITS))
            extra = match_jp_se.group(2).strip()
            e = int(match_jp_se.group(3).translate(FW_TO_HW_DIGITS))
            season_ep = f"{to_fullwidth(s)}期{to_fullwidth(e, 2)}話"
            title_part = filename[match_jp_se.end():].strip()
            title = re.split(r"(?: - | \[)", title_part)[0].strip()
            if extra:
                folder_name += extra
        else:
            match_ova = re.search(r"\b(OVA\s+.*?)(?:\s*\(|$)", filename, re.IGNORECASE)
            if match_ova:
                title = match_ova.group(1).strip()

            match_spe = SUB_SPE_RE.search(filename)
            match_4d = None if match_spe else SUB_FOUR_DIGIT_EP_RE.search(filename)
            if match_4d and "0080" in match_4d.group(1) and "Gundam" in filename:
                match_4d = None

            valid_ep_match = None
            for m_cand in SUB_EP_MULTI_PREFIX_RE.finditer(filename):
                v1 = int(m_cand.group(1).translate(FW_TO_HW_DIGITS))
                if m_cand.group(0)[:1] in "[(（" and (v1 in SUB_BOGUS_EP_NUMS or 1900 <= v1 <= 2030):
                    continue
                valid_ep_match = m_cand
                break

            match_kanji_dai = None if (match_spe or match_4d or valid_ep_match) else SUB_DAI_KANJI_EP_RE.search(filename)

            if match_spe or match_4d:
                m = match_spe or match_4d
                season_ep = s_str + f"{to_fullwidth(int(m.group(1)), 2)}話"
                title_part = filename[m.end():].strip(" ._-")
                title = re.split(r"(?: - | \[)", title_part)[0].strip()
            elif valid_ep_match:
                e1 = int(valid_ep_match.group(1).translate(FW_TO_HW_DIGITS))
                sep = valid_ep_match.group(2)
                if valid_ep_match.group(3):
                    e2 = int(valid_ep_match.group(3).translate(FW_TO_HW_DIGITS))
                    norm_sep = "～" if sep in ("～", "・", "/") else "-"
                    season_ep = f"{to_fullwidth(e1, 2)}{norm_sep}{to_fullwidth(e2, 2)}話"
                else:
                    season_ep = f"{to_fullwidth(e1, 2)}話"
                season_ep = s_str + season_ep

                title_part = filename[valid_ep_match.end():].strip(" ._-")
                if not title_part and orig_stem.endswith(filename[valid_ep_match.start():]):
                    title_part = filename[:valid_ep_match.start()].strip(" ._-")
                    if re.fullmatch(r"(?:\s*\[[^\]]*\])+", title_part) or (
                            stem_cleaned_more and title_part.lower() == folder_name.strip(" ._-").lower()):
                        title_part = ""
                title = re.split(r"(?: - | \[)", title_part)[0].strip()
            elif match_kanji_dai:
                e1 = parse_int_or_kanji(match_kanji_dai.group(1))
                if e1 is not None:
                    season_ep = s_str + f"{to_fullwidth(e1, 2)}話"
                    title_part = filename[match_kanji_dai.end():].strip(" ._-")
                    title = re.split(r"(?: - | \[)", title_part)[0].strip()

            if season_ep:
                m_sp = SUB_SPECIAL_MARKER_RE.search(filename)
                if m_sp and m_sp.group(1) not in title:
                    title = m_sp.group(1) + title

            if not season_ep:
                match_word_ep = re.search(
                    r"\b(?:Karte|Stage|Phase|Episode|ACT)\s+(\d{1,3}|I{1,3}|IV|V|VI{1,3}|IX|X{1,2}|XI{1,2})\b",
                    filename, re.IGNORECASE)
                if match_word_ep:
                    val = match_word_ep.group(1).upper()
                    e1 = int(val) if val.isdigit() else _ROMAN.get(val, 1)
                    season_ep = s_str + f"{to_fullwidth(e1, 2)}話"
                    title_part = filename[match_word_ep.end():].strip(" ._-")
                    title_part = re.sub(r"^OVA\s+", "", title_part, flags=re.IGNORECASE)
                    title = re.split(r"(?: - | \[)", title_part)[0].strip()

            if not title and not season_ep:
                title = filename

    title = _clean_episode_title(title)
    if title:
        return f"{folder_name}｜{title}｜{season_ep}" if season_ep else f"{folder_name}｜{title}"
    if season_ep:
        return f"{folder_name}｜{season_ep}"
    return folder_name or filename


def _clean_episode_title(title):
    from aobana import utils
    if title:
        t = SUB_BRACKET_JUNK_RE.sub("", title).strip()
        t = SUB_EXACT_BRACKET_JUNK_RE.sub("", t).strip()
        parts_junk = SUB_SPLIT_JUNK_RE.split(t, maxsplit=1)
        t = parts_junk[0].strip()
        if t and len(parts_junk) > 1:
            for inner in re.findall(r"\[([^\[\]]+)\]", parts_junk[-1]):
                if (re.search(r"[぀-ヿ㐀-鿿]{2}", inner)
                        and not SUB_BRACKET_JUNK_RE.search(f"[{inner}]")
                        and not SUB_TECH_BRACKET_RE.search(f"[{inner}]")
                        and not SUB_ZH_WORD_RE.search(inner)):
                    t = f"{t}（{inner.strip()}）"
                    break
        t = SUB_JPTVCLUB_RE.sub("", t).strip()
        t = re.sub(r"^【テレビ東京オンデマンド】[\.\s]*", "", t).strip()
        t = re.sub(r"\[字\]", "", t).strip()
        t = re.sub(r"\[映\]", "", t).strip()
        t = SUB_TECH_BRACKET_RE.sub("", t).strip()
        t = SUB_TECH_TAIL_RE.split(t)[0].strip()

        title = _strip_outer_brackets(t)
        title = re.sub(r"\s+-\s*$", "", title)
        title = re.sub(r"^\s*-\s+", "", title)
        if re.fullmatch(r"-\s*", title):
            title = ""
        title = title.replace(".", " ").replace("_", " ")

        title = re.sub(r"(?i)\bChapter\s*\d+\b", "", title)
        after_lang = SUB_TRAILING_LANG_RE.sub("", title)
        if SUB_BARE_LANG_RE.match(after_lang.strip()):
            after_lang = ""
        old_after_lang = re.sub(r"(?i)\s+(?:ja|jp)$", "", title)
        title = after_lang.strip() if after_lang != old_after_lang else old_after_lang
        title = re.sub(r"\b\d{3,5}-(DLC)", r"\1", title, flags=re.IGNORECASE)

        if title:
            title = utils.convert_hw_katakana(title)
            for old, new in utils.SUBS_STR_REPLACEMENTS:
                title = title.replace(old, new)
            title = title.replace("(", "（").replace(")", "）")
    return title


SUB_FORMATTED_COUNTER_RE = re.compile(
    r"(?:^|｜)(?:[0-9０-９]+期)?[0-9０-９]+(?:\.[0-9０-９]+)?"
    r"(?:[～\-・/][0-9０-９]+(?:\.[0-9０-９]+)?)?話(?:$|｜)"
)
_HYBRID_RANGE = r"(?:\s*[-~～‒–—・/,，]\s*(?:EP?|[#＃])?\s*([0-9０-９]{1,4})(?:v\d+)?)?"
SUB_HYBRID_EXPLICIT_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:EP[\s._-]*|E[\s._]*)([0-9０-９]{1,4})(?:v\d+)?"
    + _HYBRID_RANGE + r"(?![A-Za-z0-9])", re.I
)
SUB_HYBRID_BARE_RE = re.compile(
    r"(?:^|[\s._\-‒–—\[（(])([0-9０-９]{1,4})(v\d+)?"
    + _HYBRID_RANGE + r"(?![A-Za-z0-9])", re.I
)
SUB_HYBRID_PROTECTED_RE = re.compile(
    r"劇場版|映画|\[映\]|(?<![A-Za-z0-9])(?:Movie|Film)(?![A-Za-z0-9])|"
    r"(?:Cinematic|Cutscene|StoryMode|Mission|Quest)[\s_]*\d+", re.I
)
SUB_HYBRID_METADATA_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:\d{3,4}[x×]\d{3,4}|(?:480|576|720|1080|1440|1920|2160)[pi]|"
    r"(?:480|576|720|1080|1440|1920|2160)(?=[._](?:BD|WEB|HDTV))|"
    r"H[._]?26[45]|x26[45]|(?:8|10|12)bit|\d+(?:fps|ch))(?![A-Za-z0-9])", re.I
)
SUB_HYBRID_RELEASE_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:Re-?Timed\b|(?:480|576|720|1080|1440|1920|2160)(?=[._](?:BD|WEB|HDTV)))", re.I
)
SUB_HYBRID_BROADCAST_RE = re.compile(r"^(?:\d{8}|\d{4}[._-]\d{2}[._-]\d{2})[\s_-]+\d{4}(?!\d)")
SUB_HYBRID_LIST_RE = re.compile(r"\s*[,，]\s*(?:EP?)?([0-9０-９]{1,4})(?:v\d+)?(?![A-Za-z0-9])", re.I)
SUB_HYBRID_LANG_SUFFIX_RE = re.compile(r"[._-](?:sc_jp|sc&ja|jps)(?=\.(?:ass|srt|ssa)$)", re.I)
SUB_HYBRID_ANNOTATION_RE = re.compile(
    r"[\[(](?:Japanese|WhisperAI|AI Generated|Contains mistakes|Creators\+Repack|"
    r"includes songs|v\d+|first \d+(?:\.\d+)?\s*MB trimmed from TS)[\])]", re.I
)
SUB_HYBRID_COPY_RE = re.compile(
    r"([._-](?:ja|jp|jpn|jap|chs|cht|en|eng))\s*\(\d+\)(?=\.(?:srt|ass|ssa)$)", re.I
)


def _hybrid_range_end(inspected, match_end, first, last):
    if re.match(r"\.\d|[-~～‒–—・/]\s*(?:EP?)?\d", inspected[match_end:], re.I):
        return last, match_end, False
    while match := SUB_HYBRID_LIST_RE.match(inspected, match_end):
        following = int(match.group(1).translate(FW_TO_HW_DIGITS))
        if last is None or following != last + 1:
            return last, match_end, False
        last, match_end = following, match.end()
    return last, match_end, last is None or first < last <= first + 50


def _hybrid_inspection(stem, folder):
    inspected = list(stem.translate(FW_TO_HW_DIGITS))
    for pattern in (SUB_BRACKET_JUNK_RE, SUB_EXACT_BRACKET_JUNK_RE,
                    SUB_TECH_BRACKET_RE, SUB_HYBRID_METADATA_RE):
        for match in pattern.finditer(stem):
            inspected[match.start():match.end()] = " " * (match.end() - match.start())
    work = re.sub(r"\[[^\]]*\]", "", folder).translate(FW_TO_HW_DIGITS)
    work_tokens = re.findall(r"[^\W_]+", work.casefold())
    stem_tokens = list(re.finditer(r"[^\W_]+", stem.translate(FW_TO_HW_DIGITS)))
    for expected, actual in zip(work_tokens, stem_tokens):
        expected = re.sub(r"^(\d+)(?:st|nd|rd|th)$", r"\1", expected)
        if expected != actual.group().casefold():
            break
        if expected.isdigit():
            inspected[actual.start():actual.end()] = " " * (actual.end() - actual.start())
    if re.search(r"Gundam|ガンダム", stem, re.I):
        for match in re.finditer(r"(?<![A-Za-z0-9])0080(?![A-Za-z0-9])", stem):
            inspected[match.start():match.end()] = " " * 4
    return "".join(inspected)


def _format_episode_title_hybrid(relpath):
    accepted = _format_episode_title_accepted(relpath)
    parts = re.split(r"[\\/]", relpath)
    folder, raw = parts[0], parts[-1]
    inspected_name = SUB_HYBRID_COPY_RE.sub(r'\1', raw)
    if inspected_name != raw:
        corrected, metadata = _format_episode_title_hybrid('/'.join(parts[:-1] + [inspected_name]))
        corrected_counter = SUB_FORMATTED_COUNTER_RE.search(corrected)
        if corrected_counter:
            old_counter = SUB_FORMATTED_COUNTER_RE.search(accepted)
            return corrected, {**metadata, "rule": "download_copy", "changed": corrected != accepted,
                               "counter_corrected": bool(old_counter and old_counter.group() != corrected_counter.group())}
    if SUB_FORMATTED_COUNTER_RE.search(accepted):
        return accepted, {"rule": "accepted", "changed": False}
    if SUB_HYBRID_PROTECTED_RE.search(relpath):
        return accepted, {"rule": "protected", "changed": False}
    stem = _episode_stem(SUB_HYBRID_LANG_SUFFIX_RE.sub('', raw))
    if SUB_HYBRID_BROADCAST_RE.search(stem):
        return accepted, {"rule": "protected", "changed": False}
    inspected = _hybrid_inspection(stem, folder)

    explicit = list(SUB_HYBRID_EXPLICIT_RE.finditer(inspected))
    candidates = []
    invalid_range = False
    if explicit:
        for match in explicit:
            if candidates and match.start() < candidates[-1][3]:
                continue
            first = int(match.group(1))
            last = int(match.group(2)) if match.group(2) else None
            if last is not None and re.search(r"[,，]", match.group()) and last != first + 1:
                invalid_range = True
            last, end, valid = _hybrid_range_end(inspected, match.end(), first, last)
            if not valid:
                invalid_range = True
            candidates.append((first, last, match.start(), end, "explicit"))
    else:
        for match in SUB_HYBRID_BARE_RE.finditer(inspected):
            first = int(match.group(1))
            last = int(match.group(3)) if match.group(3) else None
            if last is not None and re.search(r"[,，]", match.group()) and last != first + 1:
                invalid_range = True
            last, end, valid = _hybrid_range_end(inspected, match.end(), first, last)
            if re.match(r"\.\d", inspected[match.end():]) or re.search(r"\d\.$", inspected[:match.start(1)]):
                continue
            padded = len(match.group(1)) == 4 and match.group(1).startswith('0')
            if first == 0 or (first in SUB_BOGUS_EP_NUMS and not padded) or 1900 <= first <= 2099:
                continue
            if last is not None:
                padded_end = len(match.group(3)) == 4 and match.group(3).startswith('0')
                if (not valid or (last in SUB_BOGUS_EP_NUMS and not padded_end) or 1900 <= last <= 2099):
                    invalid_range = True
                    continue
                rule = "range"
            elif len(match.group(1)) == 4 and first <= 1899:
                rule = "four_digit"
            elif re.search(r"[‒–—]\s*$", stem[:match.start(1)]):
                rule = "alternate_dash"
            elif re.match(r"\s*\[", stem[match.end():]):
                rule = "attached_bracket"
            elif (len(match.group(1)) >= 2 and stem[:match.start(1)].endswith('_')
                  and re.match(r"_(?:480|576|720|1080|1440|1920|2160)[._](?:BD|WEB|HDTV)",
                               stem[match.end():], re.I)):
                rule = "underscore_release"
            elif match.group(2) and len(match.group(1)) >= 2 and "_" in stem[:match.start(1)]:
                rule = "versioned"
            else:
                continue
            if not valid:
                invalid_range = True
                continue
            candidates.append((first, last, match.start(), end, rule))

    values = {(first, last) for first, last, _, _, _ in candidates}
    if invalid_range or len(values) != 1:
        rule = "ambiguous" if candidates or invalid_range else "unclassified"
        return accepted, {"rule": rule, "changed": False}
    first, last, _, _, rule = candidates[0]
    title_parts, previous = [], 0
    for _, _, start, end, _ in sorted(candidates, key=lambda item: item[2]):
        title_parts.append(stem[previous:start].strip(" ._ -‒–—"))
        previous = end
    title_parts.append(stem[previous:].strip(" ._ -‒–—"))
    title_raw = " ".join(part for part in title_parts if part)
    title_raw = SUB_HYBRID_ANNOTATION_RE.sub('', title_raw)
    title_raw = re.sub(r"(?:[-_.\s]*(?:JPN|JP|JA)[-_.\s]*)?内封用.*$", "", title_raw, flags=re.I)
    for match in SUB_BRACKET_JUNK_RE.finditer(title_raw):
        if re.fullmatch(r"[\s_]*(?:\([A-Za-z][A-Za-z0-9_-]{1,30}\)|\[[A-Za-z][A-Za-z0-9_-]{1,30}\])\s*",
                        title_raw[match.end():]):
            title_raw = title_raw[:match.end()]
            break
    title_raw = SUB_HYBRID_RELEASE_RE.split(title_raw, maxsplit=1)[0]
    title = _clean_episode_title(title_raw.strip(" ._ -‒–—"))
    title = re.sub(r"\s+", " ", title).strip(" -‒–—")
    if title.casefold() == folder.casefold():
        title = ""
    counter = to_fullwidth(first, 2)
    if last is not None:
        counter += "～" + to_fullwidth(last, 2)
    result = f"{folder}｜{title}｜{counter}話" if title else f"{folder}｜{counter}話"
    return result, {"rule": rule, "changed": result != accepted, "episode": first, "end": last}


def format_episode_title(relpath):
    return _format_episode_title_hybrid(relpath)[0]


GLOBAL_BOOK_AUTHORS = {}

def load_book_authors(db_epub):
    global GLOBAL_BOOK_AUTHORS
    if db_epub is not None and not GLOBAL_BOOK_AUTHORS:
        try:
            cur = db_epub.execute("SELECT title, author FROM sources")
            for r in cur:
                if r["title"] and r["author"]:
                    GLOBAL_BOOK_AUTHORS[r["title"]] = r["author"]
        except Exception:
            pass

def format_book_title(file_key, db_epub=None):
    if file_key in GLOBAL_BOOK_TITLES:
        return GLOBAL_BOOK_TITLES[file_key]
    load_book_authors(db_epub)
    from aobana import utils
    parts = re.split(r"[\\/]", file_key)
    book_title = parts[0]
    ch_part = parts[1] if len(parts) > 1 else ""
    
    ch_num = re.match(r'^(\d+)\.', ch_part)
    ch_clean = re.sub(r'^\d+\.', '', ch_part).strip()
    raw_head = re.match(r'^([^｜]+)｜(.+)$', ch_clean)
    if raw_head and utils.BOOK_RAW_FILE_CH_RE.search(raw_head.group(1)):
        ch_clean = raw_head.group(2).strip()

    author = GLOBAL_BOOK_AUTHORS.get(book_title, "")
    if not author:
        m = re.match(r'^\[(.*?)\]\s*(.*)$', book_title)
        if m:
            author = m.group(1).strip()
            book_title = m.group(2).strip()
            
    book_title = utils.clean_book_title(book_title)
    book_title = utils.convert_hw_katakana(book_title)
    for old, new in utils.EPUB_STR_REPLACEMENTS:
        book_title = book_title.replace(old, new)
        
    if ch_clean:
        ch_clean = utils.convert_hw_katakana(ch_clean)
        for old, new in utils.EPUB_STR_REPLACEMENTS:
            ch_clean = ch_clean.replace(old, new)
            
    if author:
        author = utils.convert_hw_katakana(author)
        for old, new in utils.EPUB_STR_REPLACEMENTS:
            author = author.replace(old, new)

    if utils.BOOK_RAW_FILE_CH_RE.search(ch_clean):
        ch_clean = str(int(ch_num.group(1))) if ch_num else ''
    elif ch_clean in (book_title, '本文', '本編', ''):
        ch_clean = ''
        
    if author:
        res = f"{author}｜{book_title}｜{ch_clean}" if ch_clean else f"{author}｜{book_title}"
    else:
        res = f"{book_title}｜{ch_clean}" if ch_clean else book_title
    GLOBAL_BOOK_TITLES[file_key] = res
    return res

_MANGA_AUTHOR_TAG_RE = re.compile(r'^\s*[\[［【][^\]］】]*[\]］】]\s*')


def format_manga_title(file_key):
    if file_key in GLOBAL_MANGA_TITLES:
        return GLOBAL_MANGA_TITLES[file_key]
    series, _, volume = file_key.partition("\\")
    volume = _MANGA_AUTHOR_TAG_RE.sub('', volume.replace('_', ' ')).strip() or volume
    res = f"{series}｜{volume}" if volume else series
    GLOBAL_MANGA_TITLES[file_key] = res
    return res


def format_custom_title(file_key):
    from pathlib import PurePosixPath
    if file_key.lower().endswith('.md'):
        from aobana.custom_source import clean_path
        file_key = clean_path(file_key)
    parts = file_key.replace(chr(92), '/').split('/')
    parts[-1] = PurePosixPath(parts[-1]).stem
    return '｜'.join(parts)


def title_of(media_type, file, db_subs=None, db_epub=None):
    if media_type == 'custom':
        return format_custom_title(file)
    if media_type == "epub":
        return format_book_title(file, db_epub=db_epub)
    if media_type == "manga":
        return format_manga_title(file)
    return get_formatted_title(db_subs, file)


def get_sort_key(f):
    from aobana import utils
    mixed = utils.katakana_to_hiragana(f).replace('ゔ', 'う').lower()
    return mixed.encode('cp932', errors='ignore')
