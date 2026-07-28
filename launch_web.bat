@echo off
REM BiliDL 网页版一键启动脚本（需已安装 Python 3.10+ 及依赖）
REM 用法：双击本文件即可在默认浏览器打开 GUI
cd /d "%~dp0scripts"
IF EXIST "%~dp0venv\Scripts\python.exe" (
    "%~dp0venv\Scripts\python.exe" bili_gui.py
) ELSE (
    python bili_gui.py
)
IF ERRORLEVEL 1 (
    echo.
    echo 启动失败：请确认已安装 Python 并 pip install -r requirements.txt
    pause
)
