"""Extra resources: danmaku (xml/protobuf/ass), subtitles (srt/txt/json), cover, lyrics.

Danmaku→ASS conversion enables local players (PotPlayer/VLC/mpv) to render
danmaku alongside the video (same basename auto-load).
"""
import os
import re
import math
import json
import html

from .utils import sanitize_filename


# ----------------------------------------------------------------------
# Danmaku
# ----------------------------------------------------------------------

def download_danmaku_xml(session, cid, dest):
    """Classic XML danmaku (deflate compressed, requests handles it)."""
    url = f"https://comment.bilibili.com/{cid}.xml"
    r = session.get(url, timeout=15)
    r.raise_for_status()
    r.encoding = "utf-8"
    with open(dest, "w", encoding="utf-8") as f:
        f.write(r.text)
    return dest


def download_danmaku_protobuf(session, cid, dest, max_segments=50):
    """Protobuf segmented danmaku (6min/segment), concatenated raw .pb file."""
    with open(dest, "wb") as f:
        for i in range(1, max_segments + 1):
            r = session.get(
                "https://api.bilibili.com/x/v2/dm/web/seg.so",
                params={"type": 1, "oid": cid, "segment_index": i}, timeout=15)
            if r.status_code != 200 or not r.content:
                break
            ct = r.headers.get("Content-Type", "")
            if "octet-stream" not in ct:
                break  # json error => no more segments
            f.write(r.content)
    return dest


def xml_to_ass(xml_path, ass_path, width=1920, height=1080, font_size=50,
               duration=12, alpha=0.8, lanes=None):
    """Convert bilibili XML danmaku to ASS subtitle for local playback."""
    with open(xml_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    items = []
    for m in re.finditer(r'<d p="([^"]+)"[^>]*>([^<]*)</d>', content):
        p = m.group(1).split(",")
        try:
            t = float(p[0])
            mode = int(p[1])       # 1-3 scroll, 4 bottom, 5 top
            color = int(p[3])
        except (ValueError, IndexError):
            continue
        text = html.unescape(m.group(2)).replace("\n", " ")
        if text.strip():
            items.append((t, mode, color, text))
    items.sort(key=lambda x: x[0])

    lanes = lanes or max(1, int(height * 0.85 // (font_size + 4)))
    scroll_free = [0.0] * lanes     # time when lane becomes free
    top_free = [0.0] * lanes
    bottom_free = [0.0] * lanes

    def fmt_t(sec):
        h = int(sec // 3600)
        mnt = int(sec % 3600 // 60)
        s = sec % 60
        return f"{h:d}:{mnt:02d}:{s:05.2f}"

    alpha_hex = f"{int((1 - alpha) * 255):02X}"
    header = f"""[Script Info]
Title: Bilibili Danmaku
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: DM,Microsoft YaHei,{font_size},&H{alpha_hex}FFFFFF,&H{alpha_hex}FFFFFF,&H{alpha_hex}000000,&H{alpha_hex}000000,0,0,0,0,100,100,0,0,1,2,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for t, mode, color, text in items:
        b, g, r_ = (color >> 16) & 255, (color >> 8) & 255, color & 255
        # ASS colour is &HBBGGRR
        col = f"&H{alpha_hex}{b:02X}{g:02X}{r_:02X}" if color != 0xFFFFFF else ""
        col_tag = f"\\c{col}" if col else ""
        esc = text.replace("{", "｛").replace("}", "｝")
        text_w = sum(2 if ord(ch) > 127 else 1 for ch in esc) * font_size / 2
        if mode in (1, 2, 3):
            # find a free scroll lane
            lane = min(range(lanes), key=lambda i: scroll_free[i])
            if scroll_free[lane] > t:
                lane = lane  # overlap tolerated
            speed = (width + text_w) / duration
            scroll_free[lane] = t + text_w / speed + 0.5
            y = lane * (font_size + 4)
            lines.append(
                f"Dialogue: 0,{fmt_t(t)},{fmt_t(t + duration)},DM,,0,0,0,,"
                f"{{\\move({width},{y},{-int(text_w)},{y}){col_tag}}}{esc}")
        elif mode in (4, 5):
            pool = bottom_free if mode == 4 else top_free
            lane = min(range(lanes), key=lambda i: pool[i])
            pool[lane] = t + 5
            y = height - (lane + 1) * (font_size + 4) if mode == 4 else lane * (font_size + 4)
            x = width // 2
            lines.append(
                f"Dialogue: 1,{fmt_t(t)},{fmt_t(t + 5)},DM,,0,0,0,,"
                f"{{\\pos({x},{y})\\an8{col_tag}}}{esc}")
    with open(ass_path, "w", encoding="utf-8-sig") as f:
        f.write(header)
        f.write("\n".join(lines))
    return ass_path


# ----------------------------------------------------------------------
# Subtitles
# ----------------------------------------------------------------------

def get_subtitles(session, bvid, cid):
    """Return subtitle list [{lan, lan_doc, subtitle_url}] via player api."""
    from . import api
    info = api.get_player_info(session, bvid, cid)
    subs = (info.get("subtitle") or {}).get("subtitles") or []
    return subs


def download_subtitle(session, sub, dest_base, formats=("srt",)):
    """Download one subtitle json and convert to requested formats.

    sub: item from get_subtitles(); dest_base: path without extension.
    formats: subset of {json, srt, txt}
    Returns list of written files.
    """
    url = sub.get("subtitle_url") or ""
    if url.startswith("//"):
        url = "https:" + url
    r = session.get(url, timeout=15)
    r.raise_for_status()
    data = r.json()
    body = data.get("body", [])
    written = []
    lan = sub.get("lan", "und")
    if "json" in formats:
        p = f"{dest_base}.{lan}.json"
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        written.append(p)
    if "srt" in formats:
        p = f"{dest_base}.{lan}.srt"
        with open(p, "w", encoding="utf-8") as f:
            for i, line in enumerate(body, 1):
                f.write(f"{i}\n{_srt_time(line['from'])} --> {_srt_time(line['to'])}\n"
                        f"{line.get('content', '')}\n\n")
        written.append(p)
    if "txt" in formats:
        p = f"{dest_base}.{lan}.txt"
        with open(p, "w", encoding="utf-8") as f:
            for line in body:
                f.write(line.get("content", "") + "\n")
        written.append(p)
    return written


def _srt_time(sec):
    ms = int(round((sec - math.floor(sec)) * 1000))
    sec = int(sec)
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# ----------------------------------------------------------------------
# Cover / lyrics
# ----------------------------------------------------------------------

def download_cover(session, pic_url, dest):
    if pic_url.startswith("//"):
        pic_url = "https:" + pic_url
    r = session.get(pic_url, timeout=15)
    r.raise_for_status()
    ext = os.path.splitext(pic_url.split("?")[0])[1] or ".jpg"
    if not dest.endswith(ext):
        dest = os.path.splitext(dest)[0] + ext
    with open(dest, "wb") as f:
        f.write(r.content)
    return dest


def try_download_lyrics(session, bvid, cid, dest_base):
    """B站音乐区部分视频带歌词字幕，尝试用字幕接口抓取保存为 .lrc 样式 txt。"""
    try:
        subs = get_subtitles(session, bvid, cid)
    except Exception:
        return []
    out = []
    for sub in subs:
        if "歌词" in (sub.get("lan_doc") or "") or sub.get("lan") == "lrc":
            out += download_subtitle(session, sub, dest_base, formats=("txt", "srt"))
    return out
