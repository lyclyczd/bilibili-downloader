#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""哔哩哔哩视频下载 - 原生桌面客户端启动器。

使用 pywebview 将本地 Web 服务嵌入原生窗口（WebView2），
双击 exe 即弹出桌面窗口，无需手动打开浏览器。
若无 WebView2 运行时则自动回退到默认浏览器。
"""
import os
import sys
import logging
import webbrowser
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from bili.utils import ensure_app_dir, LOG_FILE

from bili_gui import server

ensure_app_dir()
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    encoding="utf-8",
)
log = logging.getLogger("bili_gui_app")


def _on_loaded(srv):
    """webview 启动后注册窗口关闭事件，关闭时停止本地服务。"""
    try:
        import webview
        if webview.windows:
            webview.windows[0].events.closed += (lambda *a: _safe_shutdown(srv))
    except Exception as e:  # noqa
        log.warning("register closed event failed: %s", e)


def _safe_shutdown(srv):
    try:
        srv.shutdown()
    except Exception:
        pass


def _fallback_browser(srv, url):
    log.warning("原生窗口不可用，回退到浏览器模式")
    webbrowser.open(url)
    print(f"[bilibili-downloader] 已在浏览器打开 {url}，按 Ctrl+C 退出")
    try:
        while True:
            threading.Event().wait(3600)
    except KeyboardInterrupt:
        pass
    finally:
        _safe_shutdown(srv)


DEFAULT_PORT = 8234  # 与 bili_gui.py 保持一致，浏览器扩展可固定推送到此端口


def main():
    srv = url = port = None
    for p in (DEFAULT_PORT, 0):  # 8234 被占用则回退到随机端口
        try:
            srv, url, port = server.run(host="127.0.0.1", port=p,
                                         open_browser=False)
            break
        except OSError as e:
            log.warning("端口 %s 被占用: %s", p, e)
    if srv is None:
        log.error("本地服务启动失败")
        return
    log.info("local server started at %s", url)
    print(f"[bilibili-downloader] 本地服务已启动: {url}")

    if os.environ.get("BILI_NO_WEBVIEW"):
        _fallback_browser(srv, url)
        return

    try:
        import webview
        webview.create_window(
            "哔哩哔哩视频下载",
            url,
            width=1280,
            height=820,
            min_size=(960, 600),
        )
        webview.start(_on_loaded, (srv,))
    except Exception as e:  # noqa
        log.exception("webview 启动失败: %s", e)
        _fallback_browser(srv, url)
        return
    finally:
        _safe_shutdown(srv)


if __name__ == "__main__":
    main()
