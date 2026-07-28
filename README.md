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

---

## 🪟 两种使用模式

| 模式 | 适用 | 启动方式 |
| --- | --- | --- |
| **本地 exe 安装包**（推荐，双击即用） | Windows 用户，不想碰命令行 | 双击 `BilibiliDownloader.exe` 弹出原生窗口（WebView2），无需打开浏览器 |
| **Python 代码 + 网页** | 开发者 / macOS / Linux | `python scripts/bili_gui.py` 自动开浏览器 `http://127.0.0.1:8234` |

### 模式一：本地 exe 安装包

```bash
python build_exe.py     # 生成 build/exe/BilibiliDownloader/（单目录便携版）
python installer.py     # 安装向导：复制 exe + 创建桌面/开始菜单快捷方式
```
- `build_exe.py`：用 PyInstaller 把 GUI 打包成原生窗口程序，内置 ffmpeg、WebUI、WebView2 运行时。
- `installer.py`：tkinter 安装向导，可选同时生成便携版 `BilibiliDownloader_portable.zip`。
- 生成的 exe 直接双击运行，**不依赖浏览器**，下载完成弹系统通知并自动打开文件所在目录。

### 模式二：Python 代码 + 网页（跨平台）

```bash
# 一键启动脚本（已附带）
launch_web.bat        # Windows 双击
launch_web.sh          # macOS / Linux 执行
# 或手动：
python scripts/bili_gui.py
```

---

## 🧩 扩展功能（GUI 专属，v1.0.0）

| # | 功能 | 说明 |
| --- | --- | --- |
| ① | 系统通知 + 完成自动打开 | 下载完成弹窗提示（win10toast / MessageBox），并自动打开文件目录 |
| ② | 限速 + 代理 | 设置全局限速（KB/s）与 HTTP/SOCKS5 代理 |
| ③ | 任务暂停/恢复/排序 | 队列中可暂停、断点恢复、上下移 / 置顶排序 |
| ⑤ | 多账号切换 | Cookie 多账号管理，一键切换活跃账号 |
| ⑥ | UP 主全部投稿分页 | 输入 UID 分页拉取全部投稿并批量下载 |
| ⑦ | 浏览器扩展一键捕获 | 安装 `extension/`，在视频页点扩展图标即推送下载 |
| ⑧ | 字幕硬烧 / 裁剪 / 多 P 合并 | 把字幕烧进画面、裁剪片段、多 P 合并为带章节的专辑 |
| ⑨ | AI 字幕生成 | 本地 faster-whisper 语音识别生成字幕（首次自动下载模型） |
| ⑩ | 日志查看器 + 暗/亮主题 | 设置页实时查看 `gui.log`，一键切换主题 |
| ⑪ | 设置导入/导出 | 一键备份 / 恢复全部 GUI 设置（JSON） |
| ⑫ | 默认低速 + 随机间隔风控 | 默认开启低速模式（≈1.5MB/s）与任务间随机间隔，降低被风控概率；自动三连改为可开关、可限速 |
| ⑬ | 「仅个人学习备份」免责声明 | 登录/首次使用时弹出，明确合规边界 |
| ⑭ | 一键启动网页脚本 | 附带 `launch_web.bat` / `launch_web.sh` |
| ⑮ | 两种分发模式 | 本地 exe 安装包 / Python + 网页，见上 |

## 🔔 订阅追更（v1.0.0）

在 GUI「订阅」页可以订阅 **UP 主全部投稿** 或 **某个视频合集**，后台定期检查更新，发现新视频自动加入下载队列（可关闭自动下载，仅提醒）。

- **订阅 UP 主**：粘贴空间链接 `https://space.bilibili.com/946974` 或直接输入 UID
- **订阅合集**：粘贴合集链接 `https://space.bilibili.com/{mid}/lists/{sid}?type=season`（旧版 `channel/collectiondetail?sid=` 也支持）
- **存量控制**：默认只追新视频；勾选「同时下载现有全部视频」可把合集/投稿存量一并入队
- **检查周期**：默认每 30 分钟自动检查一次（设置页可改，最低 5 分钟），也可以点「立即检查」
- **更新提醒**：发现新视频会触发系统通知（①），标题显示在订阅列表中
- 订阅数据保存在 `~/.bili_dl/subscriptions.json`

对应 API：`/api/subs`（列表）、`/api/subs/add`、`/api/subs/remove`、`/api/subs/toggle`、`/api/subs/check`。

### 浏览器扩展（⑦）

见 `extension/README.md`：开发者模式加载 `extension/` 目录，打开哔哩哔哩页面 → 点扩展图标 → “捕获当前页面并下载”。

---

## ⚠️ 免责声明（⑬）

本工具**仅供个人学习与技术研究备份使用**。下载内容的版权归原作者 / 哔哩哔哩所有，
请勿传播、二次分发或用于任何商业用途。使用本工具即代表你已阅读并同意上述条款。

---

## 📁 项目结构

```
bilibili-downloader/
├── SKILL.md                  # 技能元信息（供 WorkBuddy / Agent 调用）
├── README.md
├── requirements.txt
├── build_exe.py             # ⑮ PyInstaller 打包原生窗口 exe
├── installer.py             # ⑮ tkinter 安装向导（含便携 zip）
├── launch_web.bat / .sh    # ⑭ 一键启动网页版
├── extension/               # ⑦ 浏览器扩展（一键捕获）
├── references/               # API 字段、qn / 音质编号对照
└── scripts/
    ├── bili_dl.py            # CLI 主程序
    ├── bili_gui.py           # GUI 网页版启动器
    ├── bili_gui_app.py       # 原生窗口(exe)启动器
    ├── bili/                 # 下载引擎（parser/wbi/api/auth/downloader/extras/muxer/taskqueue/...）
    └── bili_gui/             # GUI 后端（core/server/notifier）+ 前端（static/index.html）
```

---

## ❗ 注意事项

- 仅供**个人学习备份**使用，勿传播下载内容或用于商业用途。
- B 站接口含风控，批量下载时脚本已内置限速与随机 UA，仍建议控制并发。
- 直播录制输出 `.flv`，结束后可用 `--transcode` 转 MP4。
- 账号密码登录因极验人机校验无法全自动，等价方案为扫码或 Cookie 导入。

## 📄 许可证

[MIT](LICENSE) © lyclyczd
