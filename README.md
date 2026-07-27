# Bilibili Downloader · 哔哩哔哩视频下载工具

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9%2B-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg" alt="Platform">
  <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License">
  <img src="https://img.shields.io/badge/ffmpeg-required-orange.svg" alt="ffmpeg">
</p>

功能完整的 B 站下载工具集：解析 UP 主投稿（分 P、合集）、番剧 / 纪录片 / 电影、课程、直播流；
全档位画质音质选择；弹幕 / 字幕 / 封面抓取；多线程断点续传；批量队列；扫码登录支持大会员内容；
ffmpeg 混流转码（含 GPU 加速）。

提供 **命令行（CLI）** 与 **图形界面（GUI）** 两种用法，引擎共享同一套下载逻辑。

---

## ✨ 功能特性

| 模块 | 能力 |
| --- | --- |
| ① 解析范围 | 投稿视频（分 P / 合集）、番剧 / 纪录片（`ep` `ss` `md`）、课程、直播录制、b23.tv 短链、av / BV 号、收藏夹、UP 主全部投稿、稍后再看 |
| ② 画质音质 | 360P ~ 8K / HDR / 杜比视界全档位；64K ~ 192K / 杜比全景声 / Hi-Res 音质；H.264 / H.265 / AV1 编码；30 / 60 FPS 过滤；纯音频（MP3 / M4A / WebM / FLAC）与无声视频；无权限自动降级并提示需大会员 |
| ③ 附加资源 | 弹幕（xml / protobuf / **ASS**，本地播放器直接看弹幕）、字幕（srt / txt / json 互转）、封面、歌词 |
| ④ 批量任务 | 并行队列、关联视频推荐、剪贴板监视、失败指数退避重试、实时进度（速度 / 百分比 / ETA）、`.part` 断点续传、最多 8 线程分块下载 |
| ⑤ 账号权限 | 终端二维码扫码、短信登录、Cookie 导入；收藏夹 / 订阅合集 / 追番追剧列表；下载后自动三连；番剧正片 + 花絮同时解析 |
| ⑥ 格式转码 | ffmpeg 自动混流 MP4 / MKV、`--transcode h264/hevc` 重编码、`--gpu` 自动探测 NVENC / QSV / AMF 硬件加速、FLV 模式兼容远古老视频 |
| ⑦ 跨平台易用 | 纯 Python 跨平台（Windows / macOS / Linux）；智能建文件夹、序号前缀、本地历史缓存 |

---

## 📦 安装

```bash
pip install -r requirements.txt   # requests, qrcode
# ffmpeg 必须可用（混流 / 转码需要）：检测 ffmpeg -version
```

> ffmpeg 不在本仓库内，请自行从 <https://ffmpeg.org> 下载并加入 PATH；仅下载纯音频（如 `--audio-only mp3`）且源为单流时可免去 ffmpeg。

---

## 🚀 快速开始

### 图形界面（推荐）

```bash
python scripts/bili_gui.py            # 自动打开浏览器 http://127.0.0.1:8234
python scripts/bili_gui.py --port 9000
python scripts/bili_gui.py --host 0.0.0.0   # 允许局域网访问
python scripts/bili_gui.py --no-browser
```

GUI 提供：链接解析、画质 / 音质 / 帧率 / 编码 / 格式配置、实时进度队列、剪贴板监视、二维码登录、我的列表、历史记录、设置。

### 命令行（CLI）

```bash
python scripts/bili_dl.py <子命令> [参数]
```

---

## 🖥️ 命令行用法

```bash
# 查看可用画质 / 音质（不下载）
python scripts/bili_dl.py info "BV1xx411c7mD"

# 下载（默认最高画质 + 音质，自动混流 MP4）
python scripts/bili_dl.py download "BV1xx411c7mD" -o ./downloads

# 指定画质 / 音质 / 编码 / 帧率
python scripts/bili_dl.py download "BV1xx411c7mD" --quality 1080P60 --audio 192K --codec hevc

# 分 P / 合集 / 番剧全集
python scripts/bili_dl.py download "BV1xx411c7mD" --pages all
python scripts/bili_dl.py download "BV1xx411c7mD" --season
python scripts/bili_dl.py download "ss33802" --episodes all --with-extras

# 纯音频 / 无声视频
python scripts/bili_dl.py download "BV1xx411c7mD" --audio-only mp3
python scripts/bili_dl.py download "BV1xx411c7mD" --video-only

# 弹幕 / 字幕 / 封面
python scripts/bili_dl.py download "BV1xx411c7mD" --danmaku xml,ass --subtitle srt --cover

# 直播录制
python scripts/bili_dl.py record "live:21452505" -o ./rec --quality 原画
```

**登录**（访问大会员 / 1080P+ 内容前先执行）：

```bash
python scripts/bili_dl.py login                # 终端二维码扫码
python scripts/bili_dl.py login --sms          # 短信验证码（需人工完成极验）
python scripts/bili_dl.py login --check        # 查看登录状态 / 大会员
python scripts/bili_dl.py login --import-cookie "SESSDATA=xxx; bili_jct=yyy"
```

**批量与队列**：

```bash
python scripts/bili_dl.py batch urls.txt --workers 3 --threads 8
python scripts/bili_dl.py download "fav:12345678"
python scripts/bili_dl.py download "space:672328094" --limit 50
python scripts/bili_dl.py mylist favs
python scripts/bili_dl.py watch -o ./downloads      # 监视剪贴板
```

画质档位：`360P 480P 720P 720P60 1080P 1080P+ 1080P60 4K HDR 杜比视界 8K`。
音质档位：`64K 132K 192K 杜比 Hi-Res`。高画质 / 高音质需视频本身支持且账号为大会员。

---

## 📁 项目结构

```
bilibili-downloader/
├── SKILL.md                  # 技能元信息（供 WorkBuddy / Agent 调用）
├── requirements.txt
├── references/               # API 字段、qn / 音质编号对照
└── scripts/
    ├── bili_dl.py            # CLI 主程序
    ├── bili_gui.py           # GUI 启动器
    ├── bili/                 # 下载引擎（parser/wbi/api/auth/downloader/extras/muxer/taskqueue/...）
    └── bili_gui/             # GUI 后端（core/server）+ 前端（static/index.html）
```

---

## ❗ 注意事项

- 仅供**个人学习备份**使用，勿传播下载内容或用于商业用途。
- B 站接口含风控，批量下载时脚本已内置限速与随机 UA，仍建议控制并发。
- 直播录制输出 `.flv`，结束后可用 `--transcode` 转 MP4。
- 账号密码登录因极验人机校验无法全自动，等价方案为扫码或 Cookie 导入。

## 📄 许可证

[MIT](LICENSE) © lyclyczd
