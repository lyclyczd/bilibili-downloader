#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""构建 BilibiliDownloader 独立 exe（原生窗口，无需浏览器）。

产物：build/exe/BilibiliDownloader/  (单目录便携版，可直接运行)
依赖：pyinstaller, pywebview, pythonnet, imageio-ffmpeg
"""
import os
import sys
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "scripts")
ENTRY = os.path.join(SCRIPTS, "bili_gui_app.py")
DIST = os.path.join(HERE, "build", "exe")
WORK = os.path.join(HERE, "build", "work")
ASSETS = os.path.join(HERE, "assets")
ICON = os.path.join(ASSETS, "icon.ico")


def make_icon():
    from PIL import Image, ImageDraw, ImageFont
    os.makedirs(ASSETS, exist_ok=True)
    size = 256
    img = Image.new("RGBA", (size, size), (22, 24, 28, 255))
    d = ImageDraw.Draw(img)
    # 圆角背景 (B站粉)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=56,
                        fill=(251, 114, 153, 255))
    # 画一个白色 "B"
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 170)
    except Exception:
        font = ImageFont.load_default()
    d.text((size // 2, size // 2), "B", font=font, fill=(255, 255, 255, 255),
           anchor="mm")
    # 生成多尺寸 ico
    img.save(ICON, sizes=[(16, 16), (32, 32), (48, 48), (64, 64),
                          (128, 128), (256, 256)])
    print("icon:", ICON)


def main():
    os.makedirs(DIST, exist_ok=True)
    make_icon()

    import imageio_ffmpeg
    import webview
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    webview_dir = os.path.dirname(webview.__file__)
    js_dir = os.path.join(webview_dir, "js")
    assert os.path.isdir(js_dir), "webview/js missing"

    datas = [
        (os.path.join(SCRIPTS, "bili_gui", "static", "index.html"),
         os.path.join("bili_gui", "static")),
        (ff, os.path.join("ffmpeg", "ffmpeg.exe")),
        (ff, "."),
        (js_dir, os.path.join("webview", "js")),
    ]
    hidden = [
        "webview", "webview.platforms.win32", "webview.platforms.edgechromium",
        "webview.platforms.mshtml", "webview.platforms.winforms",
        "pythonnet", "clr",
        "imageio_ffmpeg", "bili", "bili_gui", "bili_gui.core",
        "bili_gui.server", "requests", "qrcode", "PIL",
    ]

    cmd = [
        sys.executable, "-m", "PyInstaller",
        ENTRY,
        "--name", "BilibiliDownloader",
        "--paths", SCRIPTS,
        "--onedir",
        "--noconsole",
        "--icon", ICON,
        "--clean",
        "--distpath", DIST,
        "--workpath", WORK,
        "--log-level", "WARN",
    ]
    for s, d in datas:
        cmd += ["--add-data", f"{s}{os.pathsep}{d}"]
    for h in hidden:
        cmd += ["--hidden-import", h]

    print("=== PyInstaller ===")
    print(" ".join(cmd))
    r = subprocess.run(cmd)
    if r.returncode != 0:
        sys.exit(r.returncode)

    out = os.path.join(DIST, "BilibiliDownloader")
    print("\n=== build output ===")
    print("exe:", os.path.join(out, "BilibiliDownloader.exe"))
    print("ffmpeg bundled:", os.path.exists(os.path.join(out, "ffmpeg", "ffmpeg.exe")))
    print("webview js bundled:", os.path.exists(os.path.join(out, "webview", "js", "api.js")))
    print("OK")


if __name__ == "__main__":
    main()
