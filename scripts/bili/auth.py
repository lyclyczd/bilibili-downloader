"""Login & session management.

- QR-code login (推荐): terminal renders QR, scan with Bilibili App
- SMS login: send captcha-protected sms code (geetest 需人工在浏览器完成后回填)
- Cookie import: paste browser cookie string
- Session builder with proper headers/cookies for all API calls
"""
import re
import sys
import time
import json
import os

import requests

from .utils import (COOKIE_FILE, ACCOUNTS_FILE, ensure_app_dir,
                       load_json, save_json, pick_ua)

PASSPORT = "https://passport.bilibili.com"
_ACTIVE = None  # 当前激活账号名（多账号模式下）


# ======================================================================
# 多账号管理（⑤）
# ======================================================================

def _load_accounts():
    data = load_json(ACCOUNTS_FILE, None)
    if not isinstance(data, dict):
        data = {}
    data.setdefault("active", None)
    data.setdefault("accounts", {})
    return data


def _save_accounts(data):
    save_json(ACCOUNTS_FILE, data)


def list_accounts():
    """Return [{'name', 'active', 'uname'}]."""
    data = _load_accounts()
    out = []
    for name, ck in data["accounts"].items():
        out.append({"name": name,
                    "active": name == data.get("active"),
                    "uname": ck.get("DedeUserID")})
    if not out and os.path.exists(COOKIE_FILE):
        out.append({"name": "默认", "active": True, "uname": None})
    return out


def get_active():
    return _load_accounts().get("active") or "默认"


def switch_account(name):
    data = _load_accounts()
    if name not in data["accounts"]:
        raise ValueError(f"账号不存在: {name}")
    data["active"] = name
    _save_accounts(data)
    return name


def add_account(name, cookie_str):
    pairs = _parse_cookie(cookie_str)
    if "SESSDATA" not in pairs:
        raise ValueError("Cookie 中缺少 SESSDATA 字段")
    data = _load_accounts()
    data["accounts"][name] = pairs
    if not data.get("active"):
        data["active"] = name
    _save_accounts(data)
    return name


def remove_account(name):
    data = _load_accounts()
    data["accounts"].pop(name, None)
    if data.get("active") == name:
        data["active"] = next(iter(data["accounts"]), None)
    _save_accounts(data)
    return True


def _parse_cookie(cookie_str):
    pairs = {}
    for part in cookie_str.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            pairs[k.strip()] = v.strip()
    return pairs


# ======================================================================
# Session 构建（兼容旧单账号 COOKIE_FILE）
# ======================================================================

def build_session(account=None):
    """Create a requests.Session with UA/Referer headers and saved cookies.

    account: 指定账号名；None 时用激活账号；若都没有则用旧
    单账号 COOKIE_FILE。
    """
    s = requests.Session()
    s.headers.update({
        "User-Agent": pick_ua(),
        "Referer": "https://www.bilibili.com/",
        "Origin": "https://www.bilibili.com",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    cookies = _load_cookies(account)
    for k, v in cookies.items():
        s.cookies.set(k, v, domain=".bilibili.com")
    if "buvid3" not in cookies:
        _ensure_buvid(s)
    return s


def _load_cookies(account=None):
    data = _load_accounts()
    if account and account in data["accounts"]:
        return data["accounts"][account]
    if (not account) and data["active"] and data["active"] in data["accounts"]:
        return data["accounts"][data["active"]]
    return load_json(COOKIE_FILE, {}) or {}


def _save_cookies(cookies, account=None):
    data = _load_accounts()
    if account and account in data["accounts"]:
        data["accounts"][account] = cookies
        _save_accounts(data)
    elif (not account) and data["active"] and data["active"] in data["accounts"]:
        data["accounts"][data["active"]] = cookies
        _save_accounts(data)
    else:
        save_json(COOKIE_FILE, cookies)


def _ensure_buvid(session):
    """Fetch buvid3/buvid4 to reduce risk-control rejections (-352)."""
    try:
        r = session.get("https://api.bilibili.com/x/frontend/finger/spi", timeout=8)
        data = r.json().get("data", {})
        if data.get("b_3"):
            session.cookies.set("buvid3", data["b_3"], domain=".bilibili.com")
        if data.get("b_4"):
            session.cookies.set("buvid4", data["b_4"], domain=".bilibili.com")
    except Exception:
        pass


def save_session_cookies(session, account=None):
    keep = {}
    for c in session.cookies:
        if "bilibili" in (c.domain or "") or c.domain == "":
            keep[c.name] = c.value
    _save_cookies(keep, account=account or get_active())


def get_csrf(session):
    return session.cookies.get("bili_jct", "")


# ----------------------------------------------------------------------
# QR code login
# ----------------------------------------------------------------------

def login_qrcode():
    session = build_session()
    r = session.get(f"{PASSPORT}/x/passport-login/web/qrcode/generate", timeout=10)
    data = r.json()["data"]
    url, qr_key = data["url"], data["qrcode_key"]

    _print_qr(url)
    print("请使用哔哩哔哩手机 App 扫描二维码登录（180 秒内有效）...")

    t0 = time.time()
    while time.time() - t0 < 180:
        time.sleep(2)
        r = session.get(
            f"{PASSPORT}/x/passport-login/web/qrcode/poll",
            params={"qrcode_key": qr_key}, timeout=10)
        d = r.json()["data"]
        code = d.get("code")
        if code == 0:
            save_session_cookies(session, account=get_active())
            print("✅ 登录成功！Cookie 已保存到本地。")
            check_login()
            return True
        if code == 86090:
            print("已扫码，请在手机上确认登录...")
        elif code == 86038:
            print("❌ 二维码已过期，请重新运行 login。")
            return False
    print("❌ 登录超时。")
    return False


def _print_qr(url):
    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.make(fit=True)
        # invert for dark terminals compat; ascii for widest support
        qr.print_ascii(invert=True)
    except ImportError:
        print("(未安装 qrcode 库，无法在终端渲染二维码。请 pip install qrcode)")
        print("请手动将以下链接生成二维码后用 App 扫描：")
        print(url)


# ----------------------------------------------------------------------
# SMS login (geetest captcha must be completed manually)
# ----------------------------------------------------------------------

def login_sms():
    session = build_session()
    print("短信登录需要完成极验人机验证，流程如下：")
    r = session.get(f"{PASSPORT}/x/passport-login/captcha?source=main_web", timeout=10)
    cap = r.json()["data"]
    token = cap["token"]
    gee = cap["geetest"]
    print("1. 在浏览器打开极验演示页完成验证并获取 validate/seccode：")
    print(f"   gt={gee['gt']}  challenge={gee['challenge']}")
    print("   （可使用 https://kuresaru.github.io/geetest-validator/ 辅助生成）")
    validate = input("2. 输入 validate: ").strip()
    seccode = input("3. 输入 seccode (通常为 validate|jordan): ").strip() or (validate + "|jordan")
    cid = input("4. 国际区号 [86]: ").strip() or "86"
    tel = input("5. 手机号: ").strip()
    r = session.post(f"{PASSPORT}/x/passport-login/web/sms/send", data={
        "cid": cid, "tel": tel, "source": "main_web",
        "token": token, "challenge": gee["challenge"],
        "validate": validate, "seccode": seccode,
    }, timeout=10)
    j = r.json()
    if j.get("code") != 0:
        print(f"❌ 发送短信失败: {j.get('message')}")
        return False
    captcha_key = j["data"]["captcha_key"]
    code = input("6. 输入收到的短信验证码: ").strip()
    r = session.post(f"{PASSPORT}/x/passport-login/web/login/sms", data={
        "cid": cid, "tel": tel, "code": code,
        "source": "main_web", "captcha_key": captcha_key,
    }, timeout=10)
    j = r.json()
    if j.get("code") != 0:
        print(f"❌ 登录失败: {j.get('message')}")
        return False
    save_session_cookies(session, account=get_active())
    print("✅ 短信登录成功！")
    check_login()
    return True


# ----------------------------------------------------------------------
# Cookie import & status
# ----------------------------------------------------------------------

def import_cookie(cookie_str, name=None):
    """cookie_str like 'SESSDATA=xxx; bili_jct=yyy; DedeUserID=zzz'

    name: 账号名（多账号）。为 None 时用激活账号或 '默认'。
    """
    pairs = _parse_cookie(cookie_str)
    if "SESSDATA" not in pairs:
        print("❌ Cookie 中缺少 SESSDATA 字段。")
        return False
    name = name or get_active() or "默认"
    add_account(name, cookie_str)
    print(f"✅ Cookie 已导入到账号 [{name}]。")
    return check_login(build_session(account=name))


def check_login(session=None):
    """Print & return (is_login, is_vip, mid, uname)."""
    session = session or build_session()
    try:
        r = session.get("https://api.bilibili.com/x/web-interface/nav", timeout=10)
        d = r.json().get("data", {})
    except Exception as e:
        print(f"网络错误: {e}")
        return False, False, 0, ""
    if not d.get("isLogin"):
        print("当前未登录（游客最高可下载 720P/1080P 部分内容）。运行 login 扫码登录。")
        return False, False, 0, ""
    vip = d.get("vipStatus", 0) == 1
    vip_label = (d.get("vip_label") or {}).get("text") or ("大会员" if vip else "普通用户")
    print(f"已登录: {d.get('uname')} (UID {d.get('mid')}) | {vip_label}")
    if not vip:
        print("提示：非大会员无法获取 1080P+ / 4K / HDR / 杜比 等高档位流。")
    return True, vip, d.get("mid", 0), d.get("uname", "")
