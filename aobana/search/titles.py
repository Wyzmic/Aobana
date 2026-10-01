
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
SUB_PURE_EP_BRACKET_RE = re.compile(r"^\d{1,3}(?:v\d+)?(?:[～\-・/]\d{1,3}(?:v\d+)?)?$", re.IGNORECASE)
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


def format_episode_title(relpath):
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
            if title:
                return f"{folder_name}｜{title}｜{season_ep}" if season_ep else f"{folder_name}｜{title}"
    if season_ep:
        return f"{folder_name}｜{season_ep}"
    return folder_name or filename


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


def title_of(media_type, file, db_subs=None, db_epub=None):
    if media_type == "epub":
        return format_book_title(file, db_epub=db_epub)
    if media_type == "manga":
        return format_manga_title(file)
    return get_formatted_title(db_subs, file)


def get_sort_key(f):
    from aobana import utils
    mixed = utils.katakana_to_hiragana(f).replace('ゔ', 'う').lower()
    return mixed.encode('shift_jis', errors='ignore')
