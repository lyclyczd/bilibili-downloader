---
name: bilibili-downloader
description: 哔哩哔哩（B站）视频下载工具。This skill should be used when the user wants to download Bilibili videos, bangumi (番剧), documentaries (纪录片), courses (课程), live stream recordings (直播录制), audio-only files, danmaku (弹幕), subtitles (字幕) or covers (封面) from bilibili.com / b23.tv links, av/BV/ep/ss/md numbers. Supports quality selection (360P~8K/杜比视界/HDR), audio quality (64K~192K/杜比全景声/Hi-Res), multi-thread download with resume, batch queue, QR-code login for VIP content, favorites/collections download, ffmpeg mux and H.264/H.265 transcode with GPU acceleration.
agent_created: true
---

# Bilibili Downloader（哔哩哔哩视频下载）

功能完整的 B 站下载工具集：解析 UP 主投稿（分 P、合集）、番剧/纪录片/电影、课程、直播流；全档位画质音质选择；弹幕/字幕/封面抓取；多线程断点续传；批量队列；扫码登录支持大会员内容；ffmpeg 混流转码（含 GPU 加速）。

## 环境准备（首次使用执行一次）

```bash
pip install requests qrcode
# ffmpeg 必须在 PATH 中（混流/转码需要）。检测：ffmpeg -version
```

所有脚本入口为 `scripts/bili_dl.py`，用 Python 3.9+ 运行：

```bash
python scripts/bili_dl.py <子命令> [参数]
```

## 图形界面 (GUI) —— 推荐

无需安装浏览器框架，用标准库内置 Web 服务启动一个现代化本地界面
（纯 Python，跨平台；前端为单文件 HTML，无 CDN 依赖）：

```bash
# 启动后自动打开浏览器 http://127.0.0.1:8234
python scripts/bili_gui.py

# 指定端口 / 允许局域网访问 / 不自动开浏览器
python scripts/bili_gui.py --port 9000
python scripts/bili_gui.py --host 0.0.0.0
python scripts/bili_gui.py --no-browser
```

GUI 提供的能力（覆盖全部七大需求）：

- **解析**：粘贴链接 / BV / av / ep / ss / md / 短链 / 直播 / fav / 收藏夹，一键解析并展示封面、分 P 列表、可选画质与音质
- **选项**：画质（360P~8K/HDR/杜比视界）、音质（64K~192K/杜比全景声/Hi-Res）、帧率 30/60、编码 H.264/H.265/AV1、输出 MP4/MKV、纯音频(MP3/M4A/WebM/FLAC)/无声视频、弹幕(xml/ass/protobuf)、字幕(srt/txt/json)、封面、歌词、自动三连、转码重编码、GPU 加速、线程数、保存目录、序号
- **任务队列**：右侧实时进度条（百分比/速度/ETA），支持取消、失败重试、打开文件所在目录
- **剪贴板监视**：开关一键启用，复制 B 站链接自动解析下载
- **登录**：扫码二维码（状态实时轮询）或 Cookie 导入，访问大会员/收藏夹/追番内容
- **我的列表**：收藏夹 / 追番 / 追剧 一键拉取并下载
- **历史记录**：本地缓存的下载记录，可打开文件
- **设置**：默认画质/音质/线程/目录等持久化；展示 ffmpeg 与 GPU 编码器探测结果

> 后端 `scripts/bili_gui/` 复用 `bili` 引擎（解析/下载/混流/登录），通过 `download_file`/`process_job` 的进度回调实时上报，CLI 与 GUI 共用同一套下载逻辑。

## 扩展功能清单（GUI，v1.0.0）

| # | 功能 | 说明 |
| --- | --- | --- |
| ① | 系统通知 + 完成自动打开 | 下载完成弹窗 + 自动打开目录 |
| ② | 限速 + 代理 | 全局限速 KB/s、HTTP/SOCKS5 代理 |
| ③ | 任务暂停/恢复/排序 | 断点续传式暂停、恢复、队列排序 |
| ⑤ | 多账号切换 | Cookie 多账号管理与一键切换 |
| ⑥ | UP 主全部投稿分页 | 输入 UID 分页拉取并批量下载 |
| ⑦ | 浏览器扩展一键捕获 | 见 `extension/README.md` |
| ⑧ | 字幕硬烧/裁剪/多 P 合并 | 烧字幕、裁片段、合并为带章节专辑 |
| ⑨ | AI 字幕生成 | 本地 faster-whisper 识别生成字幕 |
| ⑩ | 日志查看器 + 暗/亮主题 | 实时查看 gui.log、切换主题 |
| ⑪ | 设置导入/导出 | 一键备份恢复 GUI 设置 |
| ⑫ | 默认低速 + 随机间隔风控 | 默认低速≈1.5MB/s、任务间随机间隔；自动三连可开关可限速 |
| ⑬ | 「仅个人学习备份」免责声明 | 首次/登录时弹出合规声明 |
| ⑭ | 一键启动网页脚本 | `launch_web.bat` / `launch_web.sh` |
| ⑮ | 两种分发模式 | 本地 exe 安装包 / Python+网页 |
| ⑰ | 订阅追更（v1.0.0） | 订阅 UP 主投稿或合集，后台每 N 分钟检查更新并自动下载新视频 |

## 订阅追更（⑰，v1.0.0）

GUI「订阅」页粘贴 UP 主空间链接 / UID（订阅全部投稿）或合集链接（`.../lists/{sid}?type=season`）即可追更；默认只追新视频，可勾选同时下载存量。后台按 `sub_interval_min`（默认 30 分钟）自动检查，新视频自动入队 + 系统通知。数据存 `~/.bili_dl/subscriptions.json`。API：`/api/subs`、`/api/subs/add`、`/api/subs/remove`、`/api/subs/toggle`、`/api/subs/check`。

## 两种使用模式（⑮）

- **本地 exe 安装包（推荐，双击即用）**：`python build_exe.py` 生成 `build/exe/BilibiliDownloader/`，`python installer.py` 安装；双击 `BilibiliDownloader.exe` 弹出原生窗口，无需浏览器。
- **Python 代码 + 网页（跨平台）**：`python scripts/bili_gui.py`（或 `launch_web.bat/.sh`）自动打开 `http://127.0.0.1:8234`。

## 免责声明（⑬）

本工具**仅供个人学习与技术研究备份**。下载内容版权归原作者 / 哔哩哔哩，请勿传播、二次分发或商业使用。

## 快速用法

### 1. 解析并查看可用画质/音质（不下载）

```bash
python scripts/bili_dl.py info "https://www.bilibili.com/video/BV1xx411c7mD"
```

支持的输入形式：完整 URL、`BV1xx411c7mD`、`av170001`、`ep374717`、`ss33802`、`md28228367`、
`https://b23.tv/xxxx` 短链、直播间 URL/房号（`live:12345`）、收藏夹 URL（`fav:媒体id`）、
UP 主空间 URL（`space:mid`）、课程 `cheese:ss123` / `cheese:ep123`。

### 2. 下载视频

```bash
# 默认：最高可用画质 + 最高音质，自动混流为 MP4
python scripts/bili_dl.py download "BV1xx411c7mD" -o ./downloads

# 指定画质/音质/编码/帧率
python scripts/bili_dl.py download "BV1xx411c7mD" --quality 1080P60 --audio 192K --codec hevc

# 全部分 P / 指定分 P / 整个合集
python scripts/bili_dl.py download "BV1xx411c7mD" --pages all
python scripts/bili_dl.py download "BV1xx411c7mD" --pages 1,3-5
python scripts/bili_dl.py download "BV1xx411c7mD" --season        # 下载视频所属合集全部视频

# 番剧：正片+花絮一起解析，全集下载
python scripts/bili_dl.py download "ss33802" --episodes all --with-extras

# 纯音频（MP3 / M4A / WebM）或无声视频
python scripts/bili_dl.py download "BV1xx411c7mD" --audio-only mp3
python scripts/bili_dl.py download "BV1xx411c7mD" --video-only

# 弹幕/字幕/封面一起下载，弹幕转 ASS 供本地播放器加载
python scripts/bili_dl.py download "BV1xx411c7mD" --danmaku xml,ass --subtitle srt --cover

# 直播录制（Ctrl+C 停止后文件可直接播放）
python scripts/bili_dl.py record "live:21452505" -o ./rec --quality 原画
```

画质档位：`360P 480P 720P 720P60 1080P 1080P+ 1080P60 4K HDR 杜比视界 8K`（或直接给 qn 数值）。
音质档位：`64K 132K 192K 杜比 Hi-Res`。高画质/高音质需视频本身支持且账号为大会员，
无权限时自动降级到最高可用档并打印提示。

### 3. 登录（访问大会员/1080P+ 以上内容前先执行）

```bash
python scripts/bili_dl.py login              # 终端显示二维码，手机 B 站 App 扫码
python scripts/bili_dl.py login --sms        # 短信验证码登录（需人工完成极验后输入验证码）
python scripts/bili_dl.py login --check      # 查看当前登录状态 / 是否大会员
```

Cookie 保存在 `~/.bili_dl/cookies.json`。也可手动导入浏览器 Cookie：
`python scripts/bili_dl.py login --import-cookie "SESSDATA=xxx; bili_jct=yyy"`。
账号密码登录因极验人机校验无法全自动，等价方案是 `--import-cookie`。

### 4. 批量与队列

```bash
# 多个链接排队下载，最多 3 个任务并行、每任务 8 线程
python scripts/bili_dl.py batch urls.txt --workers 3 --threads 8

# 收藏夹 / 订阅合集 / 追番列表 / UP 主全部投稿
python scripts/bili_dl.py download "fav:12345678" 
python scripts/bili_dl.py download "space:672328094" --limit 50
python scripts/bili_dl.py mylist bangumi      # 我的追番（需登录）
python scripts/bili_dl.py mylist favs         # 我的收藏夹列表

# 监视剪贴板：复制 B 站链接即自动解析并下载
python scripts/bili_dl.py watch -o ./downloads
```

失败自动重试（默认 3 次，指数退避）；`.part` 分块断点续传，中断后重跑同一命令即可续传；
下载中实时打印速度/百分比/剩余时间；`--numbering` 给批量文件添加序号前缀。

### 5. 其他常用参数

- `--auto-triple`：下载完成后自动点赞+投币+收藏（需登录）
- `--flv`：以 FLV durl 模式下载远古老视频（无 DASH 流的场景自动回退）
- `--transcode h264|hevc`：下载后重新编码输出；`--gpu` 启用 NVENC/QSV/AMF 硬件加速（自动探测）
- `--fps 30|60`：限制帧率档位选择
- `history`：`python scripts/bili_dl.py history` 查看本地下载记录（个人中心缓存记录）

## 工作流建议（供 Agent 参考）

1. 用户给出链接 → 先 `info` 查看可用流，再按用户要求 `download`。
2. 遇到 `-403`/`大会员` 提示 → 引导用户 `login` 扫码后重试。
3. 批量任务 → 写入临时 `urls.txt` 后用 `batch`。
4. 需要弹幕本地播放 → `--danmaku ass`，输出的 `.ass` 与视频同名，PotPlayer/VLC 自动加载。
5. 详细 API 字段、qn/音质编号对照见 `references/quality_codes.md`；接口说明见 `references/api_notes.md`。

## 注意事项

- 仅供个人学习备份，勿传播下载内容或用于商业用途。
- B 站接口有风控，批量下载时脚本已内置限速与随机 UA，仍建议控制并发。
- 直播录制输出 `.flv`，结束后可用 `--transcode` 转 MP4。
