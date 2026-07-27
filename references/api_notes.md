# B 站接口说明（本 skill 使用的全部端点）

Base: `https://api.bilibili.com` (下称 API)，直播 `https://api.live.bilibili.com`

## 通用要求

- Header 必须带 `User-Agent`（浏览器 UA）与 `Referer: https://www.bilibili.com/`
- 建议先请求 `API/x/frontend/finger/spi` 取得 buvid3/buvid4 写入 Cookie，降低 -352 风控
- 标注 [WBI] 的接口需要 WBI 签名：从 `API/x/web-interface/nav` 的 wbi_img 提取
  img_key/sub_key → 按 mixinKeyEncTab 重排取前 32 位 → 参数按 key 排序 + wts 时间戳
  → md5(query + mixin_key) 作为 w_rid。实现见 `scripts/bili/wbi.py`

## 视频

- 视频信息 [WBI]: `API/x/web-interface/wbi/view?bvid=` → data.pages(分P)、data.ugc_season(合集)
- 取流 [WBI]: `API/x/player/wbi/playurl?bvid=&cid=&qn=&fnval=4048&fourk=1`
  - data.dash.video[] / audio[] / dolby.audio[] / flac.audio
  - 每条流 baseUrl + backupUrl[]（多 CDN，均可 Range 分块）
  - 远古视频只有 data.durl[]（FLV 分段）
- 关联推荐: `API/x/web-interface/archive/related?bvid=`

## 番剧/纪录片/电影 (pgc)

- season 信息: `API/pgc/view/web/season?ep_id=|season_id=` → result.episodes(正片)、
  result.section[](花絮/PV)，返回体外层键是 `result` 不是 `data`
- md → ss: `API/pgc/review/user?media_id=` → result.media.season_id
- 取流: `API/pgc/player/web/playurl?ep_id=&cid=&qn=&fnval=4048`（无需 WBI）

## 课程 (pugv)

- 信息: `API/pugv/view/web/season?ep_id=|season_id=`
- 取流: `API/pugv/player/web/playurl?avid=&ep_id=&cid=&fnval=4048`（需购买/登录）

## 直播

- 房间信息: `live/room/v1/Room/get_info?room_id=`（live_status: 1=直播中）
- 取流: `live/xlive/web-room/v2/index/getRoomPlayInfo?room_id=&protocol=0,1&format=0,1,2&codec=0,1&qn=10000&platform=web`
- 录制时 Referer 用 `https://live.bilibili.com/`

## 个人数据（需 SESSDATA Cookie）

- UP主投稿 [WBI]: `API/x/space/wbi/arc/search?mid=&pn=&ps=30`（风控严，间隔≥0.5s）
- 收藏夹内容: `API/x/v3/fav/resource/list?media_id=&pn=&ps=20`
- 我的收藏夹: `API/x/v3/fav/folder/created/list-all?up_mid=`
- 追番/追剧: `API/x/space/bangumi/follow/list?vmid=&type=1|2`
- 稍后再看: `API/x/v2/history/toview`
- 三连: POST `API/x/web-interface/archive/like/triple` data: bvid + csrf(=Cookie bili_jct)

## 弹幕 / 字幕 / 封面

- 弹幕 XML: `https://comment.bilibili.com/{cid}.xml`（deflate 压缩）
- 弹幕 protobuf: `API/x/v2/dm/web/seg.so?type=1&oid={cid}&segment_index=n`（每段6分钟）
- 字幕: [WBI] `API/x/player/wbi/v2?bvid=&cid=` → data.subtitle.subtitles[].subtitle_url
  （json 格式 body[]，本工具转换为 srt/txt）；CC 字幕多数需要登录才返回
- 封面: view 接口 data.pic 直链

## 登录

- 二维码: `passport.bilibili.com/x/passport-login/web/qrcode/generate` → url + qrcode_key；
  轮询 `web/qrcode/poll?qrcode_key=`，code: 0成功 86090已扫码 86038过期
- 短信: `x/passport-login/captcha` 取 gt/challenge/token → 极验人工完成 →
  `web/sms/send` → `web/login/sms`
- 关键 Cookie: SESSDATA(身份)、bili_jct(csrf)、DedeUserID

## 常见错误码

| code | 含义 |
|------|------|
| -101 | 未登录 |
| -352 / -412 | 风控（补 buvid、降低频率、换 UA） |
| -403 | 权限不足（大会员） |
| -404 | 资源不存在/已下架 |
| 87007/87008 | 课程未购买 |
| 6002003 | 番剧地区限制 |
