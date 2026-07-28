"""Common utilities: paths, filename sanitize, size/time formatting, config dir."""
import os
import re
import json
import time
import random

APP_DIR = os.path.join(os.path.expanduser("~"), ".bili_dl")
COOKIE_FILE = os.path.join(APP_DIR, "cookies.json")
ACCOUNTS_FILE = os.path.join(APP_DIR, "accounts.json")
HISTORY_FILE = os.path.join(APP_DIR, "history.json")
WBI_CACHE_FILE = os.path.join(APP_DIR, "wbi_cache.json")
LOG_DIR = os.path.join(APP_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "gui.log")
VERSION_FILE = os.path.join(APP_DIR, "VERSION")

# 软件版本（用于自动更新检查）。推送 GitHub 后请同步此处与 Release 的 tag。
VERSION = "1.2.0"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
]


def ensure_app_dir():
    os.makedirs(APP_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)
    return APP_DIR


def risk_interval(base=2.0, jitter=4.0):
    """降低风控：在 base~base+jitter 秒间随机间隔（任务之间调用）。"""
    return base + random.uniform(0, jitter)


def pick_ua():
    return random.choice(USER_AGENTS)


def sanitize_filename(name, max_len=120):
    """Remove characters illegal on Windows/macOS/Linux filesystems."""
    name = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", str(name)).strip(" .")
    if len(name) > max_len:
        name = name[:max_len].rstrip(" .")
    return name or "untitled"


def format_size(n):
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.2f}{unit}" if unit != "B" else f"{int(n)}B"
        n /= 1024
    return f"{n:.2f}TB"


def format_eta(seconds):
    if seconds is None or seconds < 0 or seconds != seconds:
        return "--:--"
    seconds = int(seconds)
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    ensure_app_dir()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def add_history(record):
    """Append a download record to local history (个人中心缓存记录)."""
    hist = load_json(HISTORY_FILE, []) or []
    if not isinstance(hist, list):
        hist = []
    record = dict(record)
    record["time"] = time.strftime("%Y-%m-%d %H:%M:%S")
    hist.append(record)
    save_json(HISTORY_FILE, hist[-500:])


_BV_ALPHABET = "FcwAPNKTMug3GV5Lj7EJnHpWsx4tb8haYeviqBz6rkCy12mUSDQX9RdoZf"
_BV_XOR = 23442827791579
_BV_MASK = 2251799813685247
_BV_MAX = 1 << 51
_BV_BASE = 58
_BV_ENC_MAP = (8, 7, 0, 5, 1, 3, 2, 4, 6)   # positions in 9-char suffix after "BV1"
_BV_DEC_MAP = tuple(reversed(_BV_ENC_MAP))


def av2bv(aid):
    """Convert av number to BV id (2023 XOR algorithm)."""
    suffix = [""] * 9
    tmp = (_BV_MAX | int(aid)) ^ _BV_XOR
    for i in range(9):
        suffix[_BV_ENC_MAP[i]] = _BV_ALPHABET[tmp % _BV_BASE]
        tmp //= _BV_BASE
    return "BV1" + "".join(suffix)


def bv2av(bvid):
    """Convert BV id to av number."""
    if not bvid.startswith("BV1") or len(bvid) != 12:
        raise ValueError(f"非法 BV 号: {bvid}")
    tmp = 0
    for i in range(9):
        tmp = tmp * _BV_BASE + _BV_ALPHABET.index(bvid[3 + _BV_DEC_MAP[i]])
    return (tmp & _BV_MASK) ^ _BV_XOR
