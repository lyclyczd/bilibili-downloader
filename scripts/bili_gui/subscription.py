"""订阅管理：订阅 UP 主投稿 / 视频合集，后台定期检查更新并自动下载。

数据持久化到 ~/.bili_dl/subscriptions.json：
{
  "subs": [
    {
      "id": "a1b2c3d4",          # 订阅内部 id
      "type": "up" | "season",    # UP 主投稿 / 合集
      "mid": 946974,              # UP 主 UID（两种类型都需要）
      "season_id": 123,           # 合集 id（type=season 时）
      "name": "影视飓风",          # 显示名
      "enabled": true,            # 是否启用
      "auto_download": true,      # 发现更新是否自动下载
      "added_at": 1690000000,
      "last_check": 1690000000,   # 上次检查时间
      "last_new": 0,              # 上次检查发现的新视频数
      "latest_title": "...",     # 最新一条视频标题（展示用）
      "seen": ["BV1xx...", ...]  # 已知视频 bvid（含已下载/入库时已存在的）
    }
  ]
}
"""
import os
import re
import time
import uuid
import threading

from bili.utils import APP_DIR, load_json, save_json

SUBS_FILE = os.path.join(APP_DIR, "subscriptions.json")

_LOCK = threading.Lock()

# 支持的链接形式
_RE_SPACE = re.compile(r"space\.bilibili\.com/(\d+)")
_RE_SID_QS = re.compile(r"[?&]sid=(\d+)")
_RE_LISTS = re.compile(r"space\.bilibili\.com/(\d+)/lists/(\d+)")
_RE_COLLECT = re.compile(
    r"space\.bilibili\.com/(\d+)/channel/collectiondetail\?sid=(\d+)")


def parse_target(text):
    """解析用户输入 → (type, mid, season_id)。

    支持：
    - UP 主空间链接:  https://space.bilibili.com/946974
    - 纯 UID 数字:    946974
    - 合集(新版):     https://space.bilibili.com/946974/lists/1234?type=season
    - 合集(旧版):     .../channel/collectiondetail?sid=1234
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("请输入 UP 主空间链接、UID 或合集链接")
    m = _RE_COLLECT.search(text)
    if m:
        return "season", int(m.group(1)), int(m.group(2))
    m = _RE_LISTS.search(text)
    if m:
        return "season", int(m.group(1)), int(m.group(2))
    m = _RE_SPACE.search(text)
    if m:
        mid = int(m.group(1))
        sid = _RE_SID_QS.search(text)
        if sid:
            return "season", mid, int(sid.group(1))
        return "up", mid, None
    if text.isdigit():
        return "up", int(text), None
    raise ValueError("无法识别的链接，请粘贴 UP 主空间链接、UID 或合集链接")


def _load():
    data = load_json(SUBS_FILE, {}) or {}
    subs = data.get("subs") or []
    return subs


def _save(subs):
    save_json(SUBS_FILE, {"subs": subs})


def list_subs():
    with _LOCK:
        return [dict(s, seen_count=len(s.get("seen") or []),
                     seen=None) for s in _load()]


def get_sub(sub_id):
    with _LOCK:
        for s in _load():
            if s.get("id") == sub_id:
                return s
    return None


def add_sub(type_, mid, season_id=None, name="", auto_download=True):
    with _LOCK:
        subs = _load()
        for s in subs:
            if (s.get("type") == type_ and s.get("mid") == mid and
                    s.get("season_id") == season_id):
                raise ValueError(f"已订阅过：{s.get('name') or mid}")
        sub = {
            "id": uuid.uuid4().hex[:8],
            "type": type_,
            "mid": mid,
            "season_id": season_id,
            "name": name or str(mid),
            "enabled": True,
            "auto_download": bool(auto_download),
            "added_at": int(time.time()),
            "last_check": 0,
            "last_new": 0,
            "latest_title": "",
            "seen": [],
        }
        subs.append(sub)
        _save(subs)
        return sub


def remove_sub(sub_id):
    with _LOCK:
        subs = _load()
        n = len(subs)
        subs = [s for s in subs if s.get("id") != sub_id]
        _save(subs)
        return len(subs) < n


def update_sub(sub_id, **patch):
    """更新订阅字段（enabled / auto_download / seen / last_check ...）。"""
    with _LOCK:
        subs = _load()
        for s in subs:
            if s.get("id") == sub_id:
                s.update(patch)
                _save(subs)
                return s
    return None


def fetch_latest(session, sub, limit=50):
    """拉取订阅目标的最新视频列表 → [{bvid,title,pubdate}]（新→旧）。"""
    from bili import api
    items = []
    if sub["type"] == "season":
        data = api.get_season_archives(
            session, sub["mid"], sub["season_id"], pn=1, ps=min(limit, 50),
            sort_reverse=False)
        # sort_reverse=False 默认旧→新，取 meta.total 判断顺序；统一按 pubdate 排序
        for v in (data.get("archives") or []):
            items.append({"bvid": v.get("bvid"), "title": v.get("title", ""),
                          "pubdate": v.get("pubdate") or 0})
        meta = data.get("meta") or {}
        name = meta.get("name")
        if name and name != sub.get("name"):
            sub["name"] = name
        # 合集不止一页时，还要拿最新一页（sort_reverse=True 首页即最新）
        total = (data.get("page") or {}).get("total", len(items))
        if total > len(items):
            data2 = api.get_season_archives(
                session, sub["mid"], sub["season_id"], pn=1,
                ps=min(limit, 50), sort_reverse=True)
            for v in (data2.get("archives") or []):
                if not any(i["bvid"] == v.get("bvid") for i in items):
                    items.append({"bvid": v.get("bvid"),
                                  "title": v.get("title", ""),
                                  "pubdate": v.get("pubdate") or 0})
    else:  # up
        data = api.get_space_videos(session, sub["mid"], pn=1,
                                    ps=min(limit, 50))
        for v in (data.get("list", {}).get("vlist") or []):
            items.append({"bvid": v.get("bvid"), "title": v.get("title", ""),
                          "pubdate": v.get("created") or 0})
        if items and not sub.get("_named"):
            author = (data.get("list", {}).get("vlist") or [{}])[0].get(
                "author")
            if author:
                sub["name"] = f"{author} 的投稿"
    items = [i for i in items if i.get("bvid")]
    items.sort(key=lambda x: x.get("pubdate") or 0, reverse=True)
    return items


def check_sub(session, sub, mark_only=False):
    """检查一个订阅：返回新视频列表（不在 seen 中的）。

    mark_only=True 时只把当前全部视频标记为已见（初次添加用，不下载存量）。
    """
    items = fetch_latest(session, sub)
    seen = set(sub.get("seen") or [])
    new = [i for i in items if i["bvid"] not in seen]
    now = int(time.time())
    seen |= {i["bvid"] for i in items}
    patch = {
        "seen": sorted(seen),
        "last_check": now,
        "last_new": 0 if mark_only else len(new),
        "name": sub.get("name"),
        "latest_title": items[0]["title"] if items else sub.get(
            "latest_title", ""),
    }
    update_sub(sub["id"], **patch)
    return [] if mark_only else new
