"""Bilibili web API wrappers: video / bangumi / cheese / live / space / favorites.

All functions take a `requests.Session` (already carrying cookies + UA headers)
created by `auth.build_session()`.
"""
import time

from . import wbi
from .utils import av2bv

API = "https://api.bilibili.com"
LIVE_API = "https://api.live.bilibili.com"

# fnval: DASH(16) | HDR(64) | 4K(128) | DolbyAudio(256) | DolbyVision(512) | 8K(1024) | AV1(2048)
FNVAL_DASH_ALL = 16 | 64 | 128 | 256 | 512 | 1024 | 2048   # 4048
FNVAL_FLV = 0

# ---------- quality tables ----------
QN_MAP = {
    "360P": 16, "480P": 32, "720P": 64, "720P60": 74,
    "1080P": 80, "1080P+": 112, "1080P60": 116,
    "4K": 120, "HDR": 125, "杜比视界": 126, "8K": 127,
}
QN_DESC = {v: k for k, v in QN_MAP.items()}
QN_DESC.update({6: "240P", 100: "智能修复"})

AUDIO_MAP = {"64K": 30216, "132K": 30232, "192K": 30280, "杜比": 30250, "HI-RES": 30251}
AUDIO_DESC = {30216: "64K", 30232: "132K", 30280: "192K", 30250: "杜比全景声", 30251: "Hi-Res无损"}

CODEC_MAP = {"avc": 7, "h264": 7, "hevc": 12, "h265": 12, "av1": 13}
CODEC_DESC = {7: "H.264/AVC", 12: "H.265/HEVC", 13: "AV1"}


class BiliApiError(Exception):
    def __init__(self, code, message, url=""):
        self.code = code
        super().__init__(f"[{code}] {message} ({url})")


def _get(session, url, params=None, wbi_sign=False, base_key="data"):
    if wbi_sign:
        params = wbi.sign_params(params or {}, session)
    resp = session.get(url, params=params, timeout=15)
    resp.raise_for_status()
    j = resp.json()
    code = j.get("code", 0)
    if code != 0:
        raise BiliApiError(code, j.get("message") or j.get("msg", ""), url)
    return j.get(base_key) if base_key else j


# ======================================================================
# Normal video (投稿视频, 分P, 合集)
# ======================================================================

def get_video_info(session, bvid=None, aid=None):
    params = {"bvid": bvid} if bvid else {"aid": aid}
    return _get(session, f"{API}/x/web-interface/wbi/view", params, wbi_sign=True)


def get_video_pages(info):
    """Return list of pages: [{cid, part, page, duration, dimension}]"""
    return info.get("pages") or [{
        "cid": info["cid"], "part": info.get("title", ""), "page": 1,
        "duration": info.get("duration", 0),
    }]


def get_ugc_season(info):
    """If video belongs to a 合集 (ugc_season), return its episode list."""
    season = info.get("ugc_season")
    if not season:
        return None
    eps = []
    for sec in season.get("sections", []):
        for ep in sec.get("episodes", []):
            eps.append({
                "aid": ep["aid"], "bvid": ep.get("bvid") or av2bv(ep["aid"]),
                "cid": ep["cid"], "title": ep.get("title", ""),
                "section": sec.get("title", ""),
            })
    return {"title": season.get("title", ""), "episodes": eps}


def get_playurl(session, bvid, cid, qn=127, fnval=FNVAL_DASH_ALL):
    params = {
        "bvid": bvid, "cid": cid, "qn": qn, "fnval": fnval,
        "fnver": 0, "fourk": 1, "voice_balance": 1, "gaia_source": "pre-load",
    }
    return _get(session, f"{API}/x/player/wbi/playurl", params, wbi_sign=True)


def get_related_videos(session, bvid=None, aid=None):
    """UP主/系统关联推荐视频 (解析时自动关联)."""
    params = {"bvid": bvid} if bvid else {"aid": aid}
    return _get(session, f"{API}/x/web-interface/archive/related", params) or []


# ======================================================================
# Bangumi / documentary / movie (ep / ss / md)
# ======================================================================

def get_season_info(session, ep_id=None, season_id=None):
    params = {"ep_id": ep_id} if ep_id else {"season_id": season_id}
    return _get(session, f"{API}/pgc/view/web/season", params, base_key="result")


def media_to_season(session, media_id):
    r = _get(session, f"{API}/pgc/review/user", {"media_id": media_id}, base_key="result")
    return r["media"]["season_id"]


def get_bangumi_playurl(session, ep_id, cid, qn=127, fnval=FNVAL_DASH_ALL):
    params = {
        "ep_id": ep_id, "cid": cid, "qn": qn, "fnval": fnval,
        "fnver": 0, "fourk": 1,
    }
    return _get(session, f"{API}/pgc/player/web/playurl", params, base_key="result")


def get_bangumi_episodes(season, with_extras=False):
    """正片 episodes; with_extras=True 时把花絮/PV(section) 一并返回."""
    eps = list(season.get("episodes", []))
    if with_extras:
        for sec in season.get("section", []) or []:
            for ep in sec.get("episodes", []):
                ep["_section_title"] = sec.get("title", "花絮")
                eps.append(ep)
    return eps


# ======================================================================
# Cheese (课程)
# ======================================================================

def get_cheese_info(session, ep_id=None, season_id=None):
    params = {"ep_id": ep_id} if ep_id else {"season_id": season_id}
    return _get(session, f"{API}/pugv/view/web/season", params)


def get_cheese_playurl(session, avid, ep_id, cid, qn=127, fnval=FNVAL_DASH_ALL):
    params = {"avid": avid, "ep_id": ep_id, "cid": cid, "qn": qn,
              "fnval": fnval, "fnver": 0, "fourk": 1}
    return _get(session, f"{API}/pugv/player/web/playurl", params)


# ======================================================================
# Live
# ======================================================================

def get_live_room_info(session, room_id):
    return _get(session, f"{LIVE_API}/room/v1/Room/get_info", {"room_id": room_id})


def get_live_stream(session, room_id, qn=10000):
    """qn: 30000杜比 20000 4K 10000原画 400蓝光 250超清 150高清 80流畅"""
    params = {
        "room_id": room_id, "protocol": "0,1", "format": "0,1,2",
        "codec": "0,1", "qn": qn, "platform": "web", "ptype": 8,
    }
    return _get(session, f"{LIVE_API}/xlive/web-room/v2/index/getRoomPlayInfo", params)


def pick_live_url(play_info):
    """Pick an http_stream flv url from getRoomPlayInfo result."""
    for stream in play_info.get("playurl_info", {}).get("playurl", {}).get("stream", []):
        for fmt in stream.get("format", []):
            for codec in fmt.get("codec", []):
                base = codec.get("base_url", "")
                for ui in codec.get("url_info", []):
                    return ui["host"] + base + ui["extra"], fmt.get("format_name", "flv")
    return None, None


# ======================================================================
# Space / favorites / subscriptions (需登录的个人数据)
# ======================================================================

def get_space_videos(session, mid, pn=1, ps=30, order="pubdate"):
    params = {"mid": mid, "pn": pn, "ps": ps, "order": order,
              "platform": "web", "web_location": "1550101"}
    return _get(session, f"{API}/x/space/wbi/arc/search", params, wbi_sign=True)


def iter_space_videos(session, mid, limit=0):
    pn, got = 1, 0
    while True:
        data = get_space_videos(session, mid, pn=pn)
        vlist = data.get("list", {}).get("vlist", [])
        if not vlist:
            break
        for v in vlist:
            yield v
            got += 1
            if limit and got >= limit:
                return
        total = data.get("page", {}).get("count", 0)
        if pn * 30 >= total:
            break
        pn += 1
        time.sleep(0.6)


def get_fav_list(session, media_id, pn=1, ps=20):
    params = {"media_id": media_id, "pn": pn, "ps": ps, "platform": "web"}
    return _get(session, f"{API}/x/v3/fav/resource/list", params)


def iter_fav_videos(session, media_id):
    pn = 1
    while True:
        data = get_fav_list(session, media_id, pn=pn)
        medias = data.get("medias") or []
        for m in medias:
            if m.get("type") == 2:  # 2=video
                yield m
        if not data.get("has_more"):
            break
        pn += 1
        time.sleep(0.6)


def get_my_favs(session, mid):
    params = {"up_mid": mid, "web_location": "333.1387"}
    return _get(session, f"{API}/x/v3/fav/folder/created/list-all", params)


def get_my_bangumi(session, mid, type_=1, pn=1, ps=30):
    """type_: 1追番 2追剧"""
    params = {"vmid": mid, "type": type_, "pn": pn, "ps": ps}
    return _get(session, f"{API}/x/space/bangumi/follow/list", params)


def get_watchlater(session):
    return _get(session, f"{API}/x/v2/history/toview")


# ======================================================================
# Extras: danmaku / subtitle / cover related endpoints live in extras.py
# ======================================================================

def get_player_info(session, bvid, cid):
    """player/wbi/v2 - contains subtitle list."""
    params = {"bvid": bvid, "cid": cid}
    return _get(session, f"{API}/x/player/wbi/v2", params, wbi_sign=True)


# ======================================================================
# Triple action (自动三连, 需登录 csrf)
# ======================================================================

def triple_action(session, bvid, csrf):
    resp = session.post(
        f"{API}/x/web-interface/archive/like/triple",
        data={"bvid": bvid, "csrf": csrf}, timeout=10,
    )
    j = resp.json()
    if j.get("code") != 0:
        raise BiliApiError(j.get("code"), j.get("message", ""), "triple")
    return j.get("data", {})


# ======================================================================
# DASH stream selection
# ======================================================================

def select_streams(dash, qn=None, audio_id=None, codec_id=None, fps=None):
    """Pick best (video, audio) from a DASH object per user preferences.

    Returns (video_dict_or_None, audio_dict_or_None, notes[list of str]).
    Falls back to the best available when requested level is missing.
    """
    notes = []
    videos = list(dash.get("video") or [])
    # fps filter: '30' keeps <=35fps, '60' prefers >=50fps
    if fps and videos:
        def _fr(v):
            try:
                return float(v.get("frameRate") or v.get("frame_rate") or 0)
            except ValueError:
                return 0
        if str(fps) == "30":
            sel = [v for v in videos if _fr(v) <= 35]
        else:
            sel = [v for v in videos if _fr(v) >= 50]
        if sel:
            videos = sel
        else:
            notes.append(f"无 {fps}FPS 流，忽略帧率限制")

    video = None
    if videos:
        if qn:
            cand = [v for v in videos if v["id"] == qn]
            if not cand:
                avail = sorted({v["id"] for v in videos}, reverse=True)
                notes.append(
                    f"请求画质 {QN_DESC.get(qn, qn)} 不可用(需视频支持且可能需大会员)，"
                    f"降级为 {QN_DESC.get(avail[0], avail[0])}")
                cand = [v for v in videos if v["id"] == avail[0]]
            videos = cand
        else:
            best = max(v["id"] for v in videos)
            videos = [v for v in videos if v["id"] == best]
        if codec_id:
            cand = [v for v in videos if v.get("codecid") == codec_id]
            if cand:
                videos = cand
            else:
                notes.append(f"该画质无 {CODEC_DESC.get(codec_id, codec_id)} 编码，使用默认编码")
        videos.sort(key=lambda v: v.get("bandwidth", 0), reverse=True)
        video = videos[0]

    # ---- audio: dash.audio + dash.dolby.audio + dash.flac.audio ----
    audios = list(dash.get("audio") or [])
    dolby = (dash.get("dolby") or {}).get("audio") or []
    audios += list(dolby)
    flac = (dash.get("flac") or {}).get("audio")
    if flac:
        audios.append(flac)
    audio = None
    if audios:
        if audio_id:
            cand = [a for a in audios if a["id"] == audio_id]
            if not cand:
                notes.append(
                    f"请求音质 {AUDIO_DESC.get(audio_id, audio_id)} 不可用，自动选择最高音质")
        else:
            cand = []
        if not cand:
            # priority: Hi-Res > Dolby > 192K > 132K > 64K
            prio = {30251: 5, 30250: 4, 30280: 3, 30232: 2, 30216: 1}
            cand = sorted(audios, key=lambda a: prio.get(a["id"], 0), reverse=True)
        audio = cand[0]
    return video, audio, notes


def stream_urls(item):
    """All candidate urls of a DASH stream item (baseUrl + backups)."""
    urls = []
    for k in ("baseUrl", "base_url"):
        if item.get(k):
            urls.append(item[k])
    for k in ("backupUrl", "backup_url"):
        urls.extend(item.get(k) or [])
    # de-dup keep order
    seen, out = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out
