"""Clipboard watcher: auto-parse bilibili links copied by the user.

Cross-platform clipboard read:
- Windows: ctypes user32 / PowerShell fallback
- macOS: pbpaste
- Linux: xclip / wl-paste
"""
import re
import sys
import time
import subprocess

BILI_PATTERN = re.compile(
    r"(https?://(?:www\.|m\.)?bilibili\.com/\S+|https?://b23\.tv/\w+|"
    r"BV[0-9A-Za-z]{10}|av\d{1,12}|ep\d{1,9}|ss\d{1,9}|md\d{1,9})", re.I)


def read_clipboard():
    if sys.platform == "win32":
        return _read_win()
    if sys.platform == "darwin":
        return _run(["pbpaste"])
    for cmd in (["wl-paste", "-n"], ["xclip", "-selection", "clipboard", "-o"]):
        out = _run(cmd)
        if out is not None:
            return out
    return None


def _run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, timeout=5,
                              text=True, encoding="utf-8", errors="ignore").stdout
    except Exception:
        return None


def _read_win():
    try:
        import ctypes
        CF_UNICODETEXT = 13
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        if not user32.OpenClipboard(0):
            return None
        try:
            h = user32.GetClipboardData(CF_UNICODETEXT)
            if not h:
                return None
            ptr = kernel32.GlobalLock(h)
            try:
                return ctypes.wstring_at(ptr)
            finally:
                kernel32.GlobalUnlock(h)
        finally:
            user32.CloseClipboard()
    except Exception:
        return _run(["powershell", "-NoProfile", "-Command", "Get-Clipboard"])


def watch(callback, interval=1.0):
    """Poll clipboard; call callback(match_str) for each new bilibili link."""
    print("==> 剪贴板监视已启动，复制 B 站链接即自动解析下载 (Ctrl+C 退出)")
    seen = set()
    last = read_clipboard() or ""
    # 忽略启动时已有内容? 不，首次也解析一次
    last = ""
    while True:
        try:
            time.sleep(interval)
            text = read_clipboard() or ""
            if text == last:
                continue
            last = text
            for m in BILI_PATTERN.finditer(text):
                key = m.group(0)
                if key in seen:
                    continue
                seen.add(key)
                print(f"\n==> 检测到链接: {key}")
                try:
                    callback(key)
                except Exception as e:  # noqa
                    print(f"  处理失败: {e}")
        except KeyboardInterrupt:
            print("\n剪贴板监视已停止。")
            return
