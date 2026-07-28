"""系统通知（①）：下载完成弹窗提示。

平台策略：
- 优先尝试 win10toast（若已安装）。
- Windows 退回 ctypes MessageBox（独立线程，不阻塞下载）。
- 其他/异常：仅打印日志。
"""
import threading
import sys


def _mb(title, msg):
    try:
        import ctypes
        if sys.platform == "win32":
            ctypes.windll.user32.MessageBoxW(
                0, str(msg), str(title), 0x40)  # MB_OK | MB_ICONINFORMATION
    except Exception:
        pass


def toast(title, msg):
    """Show a (non-blocking) system notification."""
    # 1) win10toast（UWP 真· toast，最优雅）
    try:
        from win10toast import Toast
        t = Toast()
        threading.Thread(
            target=lambda: t.show_toast(title, msg, duration=8),
            daemon=True).start()
        return
    except Exception:
        pass
    # 2) Windows 弹出消息框（独立线程，不阻塞主流程）
    if sys.platform == "win32":
        threading.Thread(target=_mb, args=(title, msg), daemon=True).start()
        return
    # 3) 兜底
    try:
        print(f"[通知] {title}: {msg}")
    except Exception:
        pass
