"""Parse any user input (URL / id / short link) into a normalized resource descriptor.

Supported:
  - av / BV video ids and URLs (含分P ?p=n)
  - Bangumi / documentary / movie: ep123 / ss123 / md123 and /bangumi/play/... /bangumi/media/md...
  - Cheese course: cheese:ss123 / cheese:ep123 and /cheese/play/...
  - b23.tv & bili2233.cn short links (auto expand via redirect)
  - Live room: live.bilibili.com/12345 or "live:12345"
  - Favorites: fav:media_id or space.bilibili.com/xx/favlist?fid=xxx
  - User space: space:mid or space.bilibili.com/mid
  - Watchlater: "watchlater"
"""
import re
from dataclasses import dataclass, field


@dataclass
class Resource:
    kind: str                      # video | bangumi | cheese | live | fav | space | watchlater
    id_type: str = ""              # bvid/aid | ep/ss/md | ep/ss | room | media_id | mid
    id_value: str = ""
    page: int = 0                  # 指定分P (1-based, 0 = 未指定)
    extra: dict = field(default_factory=dict)

    def __str__(self):
        p = f" p{self.page}" if self.page else ""
        return f"<{self.kind}:{self.id_type}={self.id_value}{p}>"


SHORT_LINK_RE = re.compile(r"https?://(?:b23\.tv|bili2233\.cn)/[\w]+", re.I)


def expand_short_link(url, session):
    """Follow redirects of b23.tv short links to the real URL."""
    resp = session.get(url, allow_redirects=True, timeout=10, stream=True)
    real = resp.url
    resp.close()
    return real


def parse(text, session=None):
    """Parse input text into a Resource. session is required only for short links."""
    text = text.strip().strip('"').strip("'")

    # ---- explicit prefixes ----
    m = re.match(r"^live:(\d+)$", text, re.I)
    if m:
        return Resource("live", "room", m.group(1))
    m = re.match(r"^fav:(\d+)$", text, re.I)
    if m:
        return Resource("fav", "media_id", m.group(1))
    m = re.match(r"^space:(\d+)$", text, re.I)
    if m:
        return Resource("space", "mid", m.group(1))
    m = re.match(r"^cheese:(ep|ss)(\d+)$", text, re.I)
    if m:
        return Resource("cheese", m.group(1).lower(), m.group(2))
    if text.lower() == "watchlater":
        return Resource("watchlater", "", "")

    # ---- short link ----
    m = SHORT_LINK_RE.search(text)
    if m:
        if session is None:
            raise ValueError("解析短链接需要网络会话")
        text = expand_short_link(m.group(0), session)

    # ---- bare ids ----
    m = re.match(r"^(BV[0-9A-Za-z]{10})$", text)
    if m:
        return Resource("video", "bvid", m.group(1))
    m = re.match(r"^av(\d+)$", text, re.I)
    if m:
        return Resource("video", "aid", m.group(1))
    m = re.match(r"^(ep|ss|md)(\d+)$", text, re.I)
    if m:
        return Resource("bangumi", m.group(1).lower(), m.group(2))

    # ---- full URLs ----
    # live
    m = re.search(r"live\.bilibili\.com/(?:h5/)?(\d+)", text)
    if m:
        return Resource("live", "room", m.group(1))
    # cheese
    m = re.search(r"bilibili\.com/cheese/play/(ep|ss)(\d+)", text, re.I)
    if m:
        return Resource("cheese", m.group(1).lower(), m.group(2))
    # bangumi media page
    m = re.search(r"bilibili\.com/bangumi/media/md(\d+)", text, re.I)
    if m:
        return Resource("bangumi", "md", m.group(1))
    # bangumi play page
    m = re.search(r"bilibili\.com/bangumi/play/(ep|ss)(\d+)", text, re.I)
    if m:
        return Resource("bangumi", m.group(1).lower(), m.group(2))
    # favlist
    m = re.search(r"space\.bilibili\.com/\d+/favlist\?fid=(\d+)", text)
    if m:
        return Resource("fav", "media_id", m.group(1))
    m = re.search(r"bilibili\.com/medialist/detail/ml(\d+)", text)
    if m:
        return Resource("fav", "media_id", m.group(1))
    # user space
    m = re.search(r"space\.bilibili\.com/(\d+)", text)
    if m:
        return Resource("space", "mid", m.group(1))
    # normal video
    m = re.search(r"(BV[0-9A-Za-z]{10})", text)
    if m:
        page = _extract_page(text)
        return Resource("video", "bvid", m.group(1), page=page)
    m = re.search(r"(?:bilibili\.com/video/)?av(\d+)", text, re.I)
    if m and "bilibili.com" in text.lower():
        return Resource("video", "aid", m.group(1), page=_extract_page(text))

    raise ValueError(f"无法识别的链接或编号: {text}")


def _extract_page(url):
    m = re.search(r"[?&]p=(\d+)", url)
    return int(m.group(1)) if m else 0
