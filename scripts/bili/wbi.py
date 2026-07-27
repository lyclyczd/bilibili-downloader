"""WBI signature for bilibili web APIs (imgKey/subKey mixin + md5)."""
import time
import urllib.parse
from hashlib import md5

from .utils import WBI_CACHE_FILE, load_json, save_json

MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52,
]


def _get_mixin_key(orig):
    return "".join(orig[i] for i in MIXIN_KEY_ENC_TAB)[:32]


def get_wbi_keys(session):
    """Fetch img_key/sub_key from nav api, cached for 12h."""
    cache = load_json(WBI_CACHE_FILE, {}) or {}
    if cache.get("ts", 0) > time.time() - 12 * 3600 and cache.get("img") and cache.get("sub"):
        return cache["img"], cache["sub"]
    resp = session.get("https://api.bilibili.com/x/web-interface/nav", timeout=10)
    data = resp.json().get("data", {})
    wbi_img = data.get("wbi_img", {})
    img_key = wbi_img.get("img_url", "").rsplit("/", 1)[-1].split(".")[0]
    sub_key = wbi_img.get("sub_url", "").rsplit("/", 1)[-1].split(".")[0]
    if img_key and sub_key:
        save_json(WBI_CACHE_FILE, {"img": img_key, "sub": sub_key, "ts": time.time()})
    return img_key, sub_key


def sign_params(params, session):
    """Return params dict with wts & w_rid appended (WBI signed)."""
    img_key, sub_key = get_wbi_keys(session)
    mixin_key = _get_mixin_key(img_key + sub_key)
    params = dict(params)
    params["wts"] = int(time.time())
    params = dict(sorted(params.items()))
    # filter special chars per spec
    params = {
        k: "".join(ch for ch in str(v) if ch not in "!'()*")
        for k, v in params.items()
    }
    query = urllib.parse.urlencode(params)
    params["w_rid"] = md5((query + mixin_key).encode()).hexdigest()
    return params
