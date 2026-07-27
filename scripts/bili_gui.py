#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BiliDL 图形界面启动器。

启动本地 Web 服务并打开浏览器，提供现代化 GUI：
  解析 / 画质音质选择 / 弹幕字幕封面 / 批量任务队列 / 实时进度 /
  二维码登录 / 剪贴板监视 / 我的列表 / 历史记录 / 设置。

用法:
  python bili_gui.py                 # 启动并自动打开浏览器 (http://127.0.0.1:8234)
  python bili_gui.py --port 9000     # 指定端口
  python bili_gui.py --no-browser    # 仅启动服务，不打开浏览器
  python bili_gui.py --host 0.0.0.0  # 允许局域网访问
"""
import os
import sys
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from bili_gui.server import run  # noqa


def main():
    ap = argparse.ArgumentParser(description="BiliDL 图形界面")
    ap.add_argument("--host", default="127.0.0.1", help="监听地址 (默认 127.0.0.1)")
    ap.add_argument("--port", type=int, default=8234, help="端口 (默认 8234)")
    ap.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = ap.parse_args()

    srv, url, port = run(host=args.host, port=args.port,
                         open_browser=not args.no_browser)
    print(f"\n  BiliDL GUI 已启动 → {url}")
    print("  在浏览器中打开上面的地址即可使用。按 Ctrl+C 退出。\n")
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n正在关闭…")
        srv.shutdown()


if __name__ == "__main__":
    main()
