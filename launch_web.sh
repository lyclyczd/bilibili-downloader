#!/usr/bin/env bash
# BiliDL 网页版一键启动脚本（macOS / Linux）
# 用法：chmod +x launch_web.sh && ./launch_web.sh
set -e
cd "$(dirname "$0")/scripts"
if [ -x "../venv/bin/python" ]; then
    ../venv/bin/python bili_gui.py
else
    python3 bili_gui.py
fi
