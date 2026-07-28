# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\赖彦呈\\WorkBuddy\\skill\\bilibili-downloader\\scripts\\bili_gui_app.py'],
    pathex=['C:\\Users\\赖彦呈\\WorkBuddy\\skill\\bilibili-downloader\\scripts'],
    binaries=[],
    datas=[('C:\\Users\\赖彦呈\\WorkBuddy\\skill\\bilibili-downloader\\scripts\\bili_gui\\static\\index.html', 'bili_gui\\static'), ('C:\\Users\\赖彦呈\\.workbuddy\\binaries\\python\\envs\\default\\Lib\\site-packages\\imageio_ffmpeg\\binaries\\ffmpeg-win-x86_64-v7.1.exe', 'ffmpeg\\ffmpeg.exe'), ('C:\\Users\\赖彦呈\\.workbuddy\\binaries\\python\\envs\\default\\Lib\\site-packages\\imageio_ffmpeg\\binaries\\ffmpeg-win-x86_64-v7.1.exe', '.'), ('C:\\Users\\赖彦呈\\.workbuddy\\binaries\\python\\envs\\default\\Lib\\site-packages\\webview\\js', 'webview\\js')],
    hiddenimports=['webview', 'webview.platforms.win32', 'webview.platforms.edgechromium', 'webview.platforms.mshtml', 'webview.platforms.winforms', 'pythonnet', 'clr', 'imageio_ffmpeg', 'bili', 'bili_gui', 'bili_gui.core', 'bili_gui.server', 'requests', 'qrcode', 'PIL'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='BilibiliDownloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['C:\\Users\\赖彦呈\\WorkBuddy\\skill\\bilibili-downloader\\assets\\icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='BilibiliDownloader',
)
