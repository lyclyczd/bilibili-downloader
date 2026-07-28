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
from PyInstaller.utils.win32.versioninfo import (
    VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable,
    StringStruct, VarFileInfo, VarStruct,
)

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "scripts")
ENTRY = os.path.join(SCRIPTS, "bili_gui_app.py")
DIST = os.path.join(HERE, "build", "exe")
WORK = os.path.join(HERE, "build", "work")
ASSETS = os.path.join(HERE, "assets")
ICON = os.path.join(ASSETS, "icon.ico")
VERSION_TXT = os.path.join(HERE, "build", "version_info.txt")


def make_version_file():
    """从 bili.utils.VERSION 生成 PyInstaller 版本资源（如 1.0.0 -> 1.0.0.0）。"""
    sys.path.insert(0, SCRIPTS)
    from bili.utils import VERSION as app_ver
    parts = [int(x) for x in app_ver.split(".")]
    while len(parts) < 4:
        parts.append(0)
    vt = tuple(parts[:4])
    dotted = ".".join(str(x) for x in vt)
    info = VSVersionInfo(
        ffi=FixedFileInfo(
            filevers=vt, prodvers=vt, mask=0x3F, flags=0x0,
            OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0),
        ),
        kids=[
            StringFileInfo([StringTable(u"040904B0", [
                StringStruct(u"CompanyName", u""),
                StringStruct(u"FileDescription", u"BilibiliDownloader"),
                StringStruct(u"FileVersion", u"{}".format(dotted)),
                StringStruct(u"InternalName", u"BilibiliDownloader"),
                StringStruct(u"LegalCopyright", u"\u00a9 BilibiliDownloader"),
                StringStruct(u"OriginalFilename", u"BilibiliDownloader.exe"),
                StringStruct(u"ProductName", u"BilibiliDownloader"),
                StringStruct(u"ProductVersion", u"{}".format(dotted)),
            ])]),
            VarFileInfo([VarStruct(u"Translation", [1033, 1200])]),
        ],
    )
    with open(VERSION_TXT, "w", encoding="utf-8") as f:
        f.write(info.save())
    print("version file:", VERSION_TXT, "->", app_ver)


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
    make_version_file()

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
        "--version-file", VERSION_TXT,
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

    def _has(*parts):
        # PyInstaller 6.x 把附加数据收集到 _internal/ 下
        cands = [os.path.join(out, *parts),
                 os.path.join(out, "_internal", *parts)]
        return any(os.path.exists(c) for c in cands)

    print("\n=== build output ===")
    print("exe:", os.path.join(out, "BilibiliDownloader.exe"))
    print("ffmpeg bundled:",
          _has("ffmpeg", "ffmpeg.exe") or
          _has("imageio_ffmpeg", "binaries", "ffmpeg-win-x86_64-v7.1.exe"))
    print("webview js bundled:", _has("webview", "js", "api.js"))
    print("index.html bundled:", _has("bili_gui", "static", "index.html"))
    print("OK")


if __name__ == "__main__":
    main()
