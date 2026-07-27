#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bili_dl - 哔哩哔哩全能下载器 CLI

子命令:
  info      解析链接, 查看可用画质/音质/分P/剧集/关联视频
  download  下载视频/番剧/课程/收藏夹/UP主投稿 (画质音质选择/弹幕/字幕/封面/纯音频)
  record    直播流录制
  login     扫码/短信/Cookie 登录, --check 查看状态
  batch     从文件批量下载 (队列并行)
  watch     监视剪贴板自动解析下载
  mylist    我的收藏夹 / 追番追剧列表
  history   本地下载记录 (个人中心缓存)
"""
import os
import re
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bili import api, auth, extras, muxer, parser
from bili.downloader import download_file, record_stream
from bili.taskqueue import TaskQueue
from bili.utils import (sanitize_filename, format_size, add_history,
                        load_json, HISTORY_FILE, av2bv)


# ======================================================================
# helpers
# ======================================================================

def parse_quality(text):
    if not text:
        return None
    t = str(text).strip().upper().replace("P+", "P+")
    if t.isdigit():
        return int(t)
    alias = {"DOLBY": "杜比视界", "DOLBYVISION": "杜比视界", "HDR10": "HDR",
             "1080P高码率": "1080P+", "4K超清": "4K"}
    t = alias.get(t, t)
    if t in api.QN_MAP:
        return api.QN_MAP[t]
    raise SystemExit(f"未知画质: {text}. 可选: {', '.join(api.QN_MAP)}")


def parse_audio(text):
    if not text:
        return None
    t = str(text).strip().upper()
    if t.isdigit():
        return int(t)
    alias = {"DOLBY": "杜比", "杜比全景声": "杜比", "HIRES": "HI-RES",
             "HI-RES无损": "HI-RES", "FLAC": "HI-RES", "无损": "HI-RES"}
    t = alias.get(t, t)
    if t in api.AUDIO_MAP:
        return api.AUDIO_MAP[t]
    raise SystemExit(f"未知音质: {text}. 可选: {', '.join(api.AUDIO_MAP)}")


def parse_pages(spec, total):
    """'all' | '1,3-5' -> sorted 1-based list."""
    if not spec or spec == "all":
        return list(range(1, total + 1))
    out = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            out.update(range(int(a), int(b) + 1))
        elif part:
            out.add(int(part))
    return sorted(x for x in out if 1 <= x <= total)


def ep_seq_or_title(ep, idx):
    t = str(ep.get("title", "")).strip()
    lt = str(ep.get("long_title", "")).strip()
    name = f"第{t}话 {lt}".strip() if t and t.replace('.', '').isdigit() else (t or lt)
    return name or f"EP{idx}"


# ======================================================================
# Job model: one downloadable item
# ======================================================================

class Job:
    """type: video / bangumi / cheese"""
    def __init__(self, jtype, title, out_dir, bvid=None, aid=None, cid=None,
                 ep_id=None, index=0, pic=None):
        self.type = jtype
        self.title = title
        self.out_dir = out_dir
        self.bvid = bvid
        self.aid = aid
        self.cid = cid
        self.ep_id = ep_id
        self.index = index
        self.pic = pic


def get_play(session, job, qn, fnval):
    if job.type == "bangumi":
        return api.get_bangumi_playurl(session, job.ep_id, job.cid, qn=qn, fnval=fnval)
    if job.type == "cheese":
        return api.get_cheese_playurl(session, job.aid, job.ep_id, job.cid,
                                      qn=qn, fnval=fnval)
    return api.get_playurl(session, job.bvid, job.cid, qn=qn, fnval=fnval)


# ======================================================================
# resolve: Resource -> [Job]
# ======================================================================

def resolve_jobs(session, res, args):
    jobs = []
    out_root = os.path.abspath(args.output)

    if res.kind == "video":
        info = (api.get_video_info(session, bvid=res.id_value)
                if res.id_type == "bvid"
                else api.get_video_info(session, aid=res.id_value))
        bvid = info["bvid"]
        title = sanitize_filename(info["title"])
        pages = api.get_video_pages(info)

        if getattr(args, "season", False):
            season = api.get_ugc_season(info)
            if season:
                sdir = os.path.join(out_root, sanitize_filename(season["title"]))
                for i, ep in enumerate(season["episodes"], 1):
                    jobs.append(Job("video", sanitize_filename(ep["title"]) or f"P{i}",
                                    sdir, bvid=ep["bvid"], aid=ep["aid"],
                                    cid=ep["cid"], index=i, pic=info.get("pic")))
                return jobs, season["title"]
            print("该视频不属于任何合集，按普通视频处理。")

        if len(pages) == 1:
            p = pages[0]
            jobs.append(Job("video", title, out_root, bvid=bvid,
                            aid=info["aid"], cid=p["cid"], index=1,
                            pic=info.get("pic")))
        else:
            want = ([res.page] if res.page else
                    parse_pages(getattr(args, "pages", "all") or "all", len(pages)))
            vdir = os.path.join(out_root, title)
            for pno in want:
                p = pages[pno - 1]
                pname = sanitize_filename(p.get("part") or f"P{pno}")
                jobs.append(Job("video", f"P{pno:02d}_{pname}", vdir, bvid=bvid,
                                aid=info["aid"], cid=p["cid"], index=pno,
                                pic=info.get("pic")))
        return jobs, title

    if res.kind == "bangumi":
        if res.id_type == "md":
            season = api.get_season_info(
                session, season_id=api.media_to_season(session, res.id_value))
        elif res.id_type == "ss":
            season = api.get_season_info(session, season_id=res.id_value)
        else:
            season = api.get_season_info(session, ep_id=res.id_value)
        stitle = sanitize_filename(season.get("title", "bangumi"))
        sdir = os.path.join(out_root, stitle)
        eps = api.get_bangumi_episodes(season, with_extras=args.with_extras)
        if res.id_type == "ep" and (args.episodes or "current") == "current":
            eps = [e for e in eps if str(e.get("id")) == str(res.id_value)] or eps[:1]
        elif args.episodes and args.episodes not in ("all", "current"):
            idxs = parse_pages(args.episodes, len(eps))
            eps = [eps[i - 1] for i in idxs]
        for i, ep in enumerate(eps, 1):
            name = sanitize_filename(ep_seq_or_title(ep, i))
            sec = ep.get("_section_title")
            d = os.path.join(sdir, sanitize_filename(sec)) if sec else sdir
            jobs.append(Job("bangumi", name, d, bvid=ep.get("bvid"),
                            aid=ep.get("aid"), cid=ep["cid"], ep_id=ep["id"],
                            index=i, pic=ep.get("cover")))
        return jobs, stitle

    if res.kind == "cheese":
        season = (api.get_cheese_info(session, season_id=res.id_value)
                  if res.id_type == "ss"
                  else api.get_cheese_info(session, ep_id=res.id_value))
        stitle = sanitize_filename(season.get("title", "course"))
        sdir = os.path.join(out_root, stitle)
        eps = season.get("episodes", [])
        if res.id_type == "ep" and (args.episodes or "current") == "current":
            eps = [e for e in eps if str(e.get("id")) == str(res.id_value)] or eps[:1]
        elif args.episodes and args.episodes not in ("all", "current"):
            idxs = parse_pages(args.episodes, len(eps))
            eps = [eps[i - 1] for i in idxs]
        for i, ep in enumerate(eps, 1):
            jobs.append(Job("cheese", sanitize_filename(ep.get("title") or f"第{i}课"),
                            sdir, aid=ep.get("aid"), cid=ep["cid"],
                            ep_id=ep["id"], index=i, pic=ep.get("cover")))
        return jobs, stitle

    if res.kind == "fav":
        print("解析收藏夹...")
        vids = list(api.iter_fav_videos(session, res.id_value))
        if args.limit:
            vids = vids[: args.limit]
        fdir = os.path.join(out_root, f"收藏夹_{res.id_value}")
        for i, v in enumerate(vids, 1):
            jobs.append(Job("video", sanitize_filename(v["title"]), fdir,
                            bvid=v.get("bvid") or av2bv(v["id"]), aid=v["id"],
                            cid=None, index=i, pic=v.get("cover")))
        return jobs, f"收藏夹 {res.id_value} ({len(jobs)}个视频)"

    if res.kind == "space":
        print("解析 UP 主投稿列表...")
        vids = list(api.iter_space_videos(session, res.id_value,
                                          limit=args.limit or 0))
        udir = os.path.join(out_root, f"UP_{res.id_value}")
        for i, v in enumerate(vids, 1):
            jobs.append(Job("video", sanitize_filename(v["title"]), udir,
                            bvid=v.get("bvid"), aid=v.get("aid"), cid=None,
                            index=i, pic=v.get("pic")))
        return jobs, f"UP主 {res.id_value} 投稿 ({len(jobs)}个视频)"

    if res.kind == "watchlater":
        data = api.get_watchlater(session)
        vids = data.get("list", [])
        wdir = os.path.join(out_root, "稍后再看")
        for i, v in enumerate(vids, 1):
            jobs.append(Job("video", sanitize_filename(v["title"]), wdir,
                            bvid=v.get("bvid"), aid=v.get("aid"),
                            cid=v.get("cid"), index=i, pic=v.get("pic")))
        return jobs, f"稍后再看 ({len(jobs)}个视频)"

    raise SystemExit(f"download 不支持该资源类型: {res.kind} (直播请用 record)")


# ======================================================================
# process one job: playurl -> download -> mux -> extras
# ======================================================================

def process_job(session, job, args, progress=None):
    os.makedirs(job.out_dir, exist_ok=True)
    prefix = f"{job.index:03d}_" if args.numbering else ""
    base = prefix + sanitize_filename(job.title)
    print(f"\n==> {job.title}")
    if progress:
        progress.set_phase("准备中")

    # lazily fill cid (fav/space lists don't carry cid)
    if job.cid is None:
        info = api.get_video_info(session, bvid=job.bvid)
        job.cid = api.get_video_pages(info)[0]["cid"]
        job.pic = job.pic or info.get("pic")

    qn = parse_quality(args.quality) or 127
    audio_id = parse_audio(args.audio)
    codec_id = api.CODEC_MAP.get((args.codec or "").lower()) or None
    fnval = api.FNVAL_FLV if args.flv else api.FNVAL_DASH_ALL

    play = get_play(session, job, qn, fnval)
    dash = play.get("dash")
    out_ext = "mkv" if (audio_id in (30250, 30251) and not args.audio_only) else "mp4"
    final_path = os.path.join(job.out_dir, f"{base}.{out_ext}")

    if os.path.exists(final_path) and not args.audio_only:
        print(f"  已存在，跳过: {final_path}")
        if progress:
            progress.finish(final_path)
        return final_path
    elif dash and not args.flv:
        video, audio, notes = api.select_streams(
            dash, qn=qn if args.quality else None, audio_id=audio_id,
            codec_id=codec_id, fps=args.fps)
        for n in notes:
            print(f"  ⚠ {n}")
        if args.audio_only:
            video = None
        if args.video_only:
            audio = None
        if video:
            print(f"  视频: {api.QN_DESC.get(video['id'], video['id'])} "
                  f"{api.CODEC_DESC.get(video.get('codecid'), '')} "
                  f"{video.get('width')}x{video.get('height')} "
                  f"@{video.get('frameRate', '?')}fps "
                  f"~{format_size(video.get('bandwidth', 0) / 8)}/s")
        if audio:
            print(f"  音频: {api.AUDIO_DESC.get(audio['id'], audio['id'])} "
                  f"~{format_size(audio.get('bandwidth', 0) / 8)}/s")

        tmp_v = os.path.join(job.out_dir, f"{base}.video.m4s")
        tmp_a = os.path.join(job.out_dir, f"{base}.audio.m4s")
        if video:
            if progress:
                progress.set_phase("下载视频流")
            download_file(session, api.stream_urls(video), tmp_v,
                          threads=args.threads, label="视频流", progress=progress)
        if audio:
            if progress:
                progress.set_phase("下载音频流")
            download_file(session, api.stream_urls(audio), tmp_a,
                          threads=args.threads, label="音频流", progress=progress)

        if args.audio_only:
            if progress:
                progress.set_phase("提取音频")
            fmt = args.audio_only if isinstance(args.audio_only, str) else "m4a"
            out = muxer.extract_audio(tmp_a, os.path.join(job.out_dir, base), fmt=fmt)
            os.remove(tmp_a)
            final_path = out
            print(f"  ✅ 音频已保存: {out}")
        else:
            if not muxer.has_ffmpeg():
                print("  ⚠ 未检测到 ffmpeg，保留原始 m4s 流文件（无法混流为 MP4）")
                final_path = tmp_v
            else:
                if progress:
                    progress.set_phase("混流中")
                v_in = tmp_v if video else None
                a_in = tmp_a if audio else None
                muxer.merge_av(v_in, a_in, final_path) if v_in else None
                if v_in and os.path.exists(final_path):
                    for p in (tmp_v, tmp_a):
                        if os.path.exists(p):
                            os.remove(p)
                print(f"  ✅ 已保存: {final_path}")
                if args.transcode:
                    if progress:
                        progress.set_phase("转码中")
                    tpath = os.path.join(job.out_dir,
                                         f"{base}.{args.transcode}.mp4")
                    muxer.transcode(final_path, tpath, codec=args.transcode,
                                    gpu=args.gpu)
                    print(f"  ✅ 转码完成: {tpath}")
    else:
        # FLV / durl mode (远古视频或 --flv)
        durl = play.get("durl") or []
        if not durl:
            raise SystemExit("接口未返回可用流（可能需要登录/大会员，或视频已下架）")
        print(f"  FLV 模式: {len(durl)} 段")
        seg_files = []
        for i, d in enumerate(durl, 1):
            if progress:
                progress.set_phase(f"下载FLV段{i}/{len(durl)}")
            seg = os.path.join(job.out_dir, f"{base}.seg{i}.flv")
            download_file(session, [d["url"]] + (d.get("backup_url") or []),
                          seg, threads=args.threads, label=f"FLV段{i}", progress=progress)
            seg_files.append(seg)
        flv_out = os.path.join(job.out_dir, f"{base}.flv")
        if len(seg_files) == 1:
            os.replace(seg_files[0], flv_out)
        else:
            with open(flv_out, "wb") as fo:  # naive concat; ffmpeg concat更稳
                for s in seg_files:
                    with open(s, "rb") as fi:
                        fo.write(fi.read())
                    os.remove(s)
        final_path = flv_out
        if muxer.has_ffmpeg() and not args.keep_flv:
            mp4 = os.path.join(job.out_dir, f"{base}.mp4")
            try:
                muxer.flv_to_mp4(flv_out, mp4)
                os.remove(flv_out)
                final_path = mp4
            except RuntimeError as e:
                print(f"  ⚠ FLV 转 MP4 失败，保留 FLV: {e}")
        print(f"  ✅ 已保存: {final_path}")

    # ---- extras ----
    dest_base = os.path.join(job.out_dir, base)
    if progress:
        progress.set_phase("下载弹幕/字幕/封面")
    if args.danmaku:
        fmts = [x.strip().lower() for x in args.danmaku.split(",")]
        if "xml" in fmts or "ass" in fmts:
            xmlp = extras.download_danmaku_xml(session, job.cid, dest_base + ".danmaku.xml")
            print(f"  弹幕(xml): {xmlp}")
            if "ass" in fmts:
                assp = extras.xml_to_ass(xmlp, dest_base + ".ass")
                print(f"  弹幕(ass, 本地播放器自动加载): {assp}")
                if "xml" not in fmts:
                    os.remove(xmlp)
        if "protobuf" in fmts or "pb" in fmts:
            pbp = extras.download_danmaku_protobuf(session, job.cid, dest_base + ".danmaku.pb")
            print(f"  弹幕(protobuf): {pbp}")
    if args.subtitle:
        fmts = tuple(x.strip().lower() for x in args.subtitle.split(","))
        try:
            subs = extras.get_subtitles(session, job.bvid or av2bv(job.aid), job.cid)
            if not subs:
                print("  该视频无 CC 字幕")
            for sub in subs:
                for p in extras.download_subtitle(session, sub, dest_base, formats=fmts):
                    print(f"  字幕[{sub.get('lan_doc', sub.get('lan'))}]: {p}")
        except Exception as e:
            print(f"  ⚠ 字幕获取失败: {e}")
    if args.cover and job.pic:
        try:
            p = extras.download_cover(session, job.pic, dest_base + ".cover.jpg")
            print(f"  封面: {p}")
        except Exception as e:
            print(f"  ⚠ 封面下载失败: {e}")
    if args.lyrics and job.bvid:
        got = extras.try_download_lyrics(session, job.bvid, job.cid, dest_base + ".lyrics")
        for p in got:
            print(f"  歌词: {p}")

    # ---- auto triple ----
    if args.auto_triple and job.bvid:
        csrf = auth.get_csrf(session)
        if not csrf:
            print("  ⚠ 未登录，无法自动三连")
        else:
            try:
                api.triple_action(session, job.bvid, csrf)
                print("  👍 已自动三连（点赞+投币+收藏）")
            except Exception as e:
                print(f"  ⚠ 三连失败: {e}")

    add_history({"title": job.title, "type": job.type,
                 "bvid": job.bvid, "cid": job.cid, "path": final_path})
    if progress:
        progress.finish(final_path)
    return final_path


# ======================================================================
# subcommands
# ======================================================================

def cmd_info(args):
    session = auth.build_session()
    res = parser.parse(args.url, session)
    print(f"资源类型: {res}")

    if res.kind == "live":
        info = api.get_live_room_info(session, res.id_value)
        st = {0: "未开播", 1: "直播中", 2: "轮播中"}.get(info.get("live_status"), "?")
        print(f"直播间: {info.get('title')} | 状态: {st} | 人气: {info.get('online')}")
        return

    if res.kind == "video":
        info = (api.get_video_info(session, bvid=res.id_value)
                if res.id_type == "bvid" else
                api.get_video_info(session, aid=res.id_value))
        print(f"标题: {info['title']}\nUP主: {info['owner']['name']} "
              f"(UID {info['owner']['mid']})\nBV号: {info['bvid']} | av{info['aid']}")
        pages = api.get_video_pages(info)
        if len(pages) > 1:
            print(f"分P: 共 {len(pages)} 个")
            for p in pages[:20]:
                print(f"  P{p['page']}: {p['part']}")
            if len(pages) > 20:
                print(f"  ... 共{len(pages)}P")
        season = api.get_ugc_season(info)
        if season:
            print(f"所属合集: {season['title']} ({len(season['episodes'])}个视频) "
                  f"-> 加 --season 可整合集下载")
        play = api.get_playurl(session, info["bvid"], pages[0]["cid"])
        _print_streams(play)
        try:
            rel = api.get_related_videos(session, bvid=info["bvid"])[:8]
            if rel:
                print("关联推荐视频 (可直接复制 BV 号下载):")
                for v in rel:
                    print(f"  {v['bvid']}  {v['title']}  [UP: {v['owner']['name']}]")
        except Exception:
            pass
        return

    if res.kind == "bangumi":
        if res.id_type == "md":
            season = api.get_season_info(
                session, season_id=api.media_to_season(session, res.id_value))
        elif res.id_type == "ss":
            season = api.get_season_info(session, season_id=res.id_value)
        else:
            season = api.get_season_info(session, ep_id=res.id_value)
        eps = season.get("episodes", [])
        print(f"剧集: {season.get('title')} | 共 {len(eps)} 话")
        for i, ep in enumerate(eps[:30], 1):
            print(f"  [{i}] ep{ep['id']}  {ep_seq_or_title(ep, i)}")
        secs = season.get("section") or []
        for sec in secs:
            print(f"  ── {sec.get('title')}: {len(sec.get('episodes', []))} 个 "
                  f"(加 --with-extras 一并下载)")
        if eps:
            play = api.get_bangumi_playurl(session, eps[0]["id"], eps[0]["cid"])
            _print_streams(play)
        return

    if res.kind == "cheese":
        season = (api.get_cheese_info(session, season_id=res.id_value)
                  if res.id_type == "ss" else
                  api.get_cheese_info(session, ep_id=res.id_value))
        eps = season.get("episodes", [])
        print(f"课程: {season.get('title')} | 共 {len(eps)} 课时")
        for i, ep in enumerate(eps[:30], 1):
            print(f"  [{i}] ep{ep['id']}  {ep.get('title')}")
        return

    if res.kind in ("fav", "space"):
        print("列表型资源，直接用 download 命令即可批量下载 (--limit 限制数量)")
        return


def _print_streams(play):
    dash = play.get("dash")
    if not dash:
        print("流格式: FLV/durl (远古视频)")
        return
    print("可用画质:")
    seen = {}
    for v in dash.get("video", []):
        seen.setdefault(v["id"], set()).add(
            api.CODEC_DESC.get(v.get("codecid"), "?"))
    for qn in sorted(seen, reverse=True):
        print(f"  {api.QN_DESC.get(qn, qn):8s} qn={qn:<4d} [{', '.join(sorted(seen[qn]))}]")
    accept = play.get("accept_description") or []
    sup = play.get("support_formats") or []
    need_vip = [f["new_description"] for f in sup if f.get("need_vip")]
    if need_vip:
        print(f"  (需大会员: {', '.join(need_vip)})")
    print("可用音质:")
    auds = list(dash.get("audio") or [])
    auds += (dash.get("dolby") or {}).get("audio") or []
    if (dash.get("flac") or {}).get("audio"):
        auds.append(dash["flac"]["audio"])
    for a in sorted(auds, key=lambda x: x["id"]):
        print(f"  {api.AUDIO_DESC.get(a['id'], a['id'])} (id={a['id']})")


def cmd_download(args):
    session = auth.build_session()
    res = parser.parse(args.url, session)
    if res.kind == "live":
        raise SystemExit("直播请使用 record 子命令")
    jobs, title = resolve_jobs(session, res, args)
    if not jobs:
        raise SystemExit("没有可下载的内容")
    print(f"==> {title}: 共 {len(jobs)} 个下载任务")
    if len(jobs) == 1:
        process_job(session, jobs[0], args)
    else:
        q = TaskQueue(workers=args.workers, retries=2)
        for job in jobs:
            q.add(job.title, process_job, session, job, args)
        q.run()


def cmd_record(args):
    session = auth.build_session()
    res = parser.parse(args.url, session)
    if res.kind != "live":
        raise SystemExit("record 仅支持直播间链接/房号 (如 live:12345)")
    info = api.get_live_room_info(session, res.id_value)
    if info.get("live_status") != 1:
        raise SystemExit(f"直播间未开播: {info.get('title')}")
    qn_map = {"杜比": 30000, "4K": 20000, "原画": 10000, "蓝光": 400,
              "超清": 250, "高清": 150, "流畅": 80}
    qn = qn_map.get(args.quality or "原画", 10000)
    play = api.get_live_stream(session, res.id_value, qn=qn)
    url, fmt = api.pick_live_url(play)
    if not url:
        raise SystemExit("未取得直播流地址（可能需要登录）")
    title = sanitize_filename(info.get("title", f"live_{res.id_value}"))
    import time as _t
    dest = os.path.join(os.path.abspath(args.output),
                        f"{title}_{_t.strftime('%Y%m%d_%H%M%S')}.flv")
    record_stream(session, url, dest)
    if args.transcode and muxer.has_ffmpeg():
        mp4 = os.path.splitext(dest)[0] + ".mp4"
        muxer.flv_to_mp4(dest, mp4)
        print(f"已转封装: {mp4}")
    add_history({"title": info.get("title"), "type": "live", "path": dest})


def cmd_login(args):
    if args.check:
        auth.check_login()
    elif args.import_cookie:
        auth.import_cookie(args.import_cookie)
    elif args.sms:
        auth.login_sms()
    else:
        auth.login_qrcode()


def cmd_batch(args):
    with open(args.file, "r", encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    if not lines:
        raise SystemExit("文件中没有有效链接")
    session = auth.build_session()
    all_jobs = []
    for ln in lines:
        try:
            res = parser.parse(ln, session)
            jobs, title = resolve_jobs(session, res, args)
            all_jobs += jobs
            print(f"  解析成功: {title} (+{len(jobs)})")
        except Exception as e:
            print(f"  ⚠ 解析失败 [{ln}]: {e}")
    if not all_jobs:
        raise SystemExit("没有可下载任务")
    q = TaskQueue(workers=args.workers, retries=2)
    for job in all_jobs:
        q.add(job.title, process_job, session, job, args)
    q.run()


def cmd_watch(args):
    from bili.clipboard_watch import watch
    session = auth.build_session()

    def handle(text):
        res = parser.parse(text, session)
        if res.kind == "live":
            print("  检测到直播间，剪贴板模式不自动录制，请手动运行 record")
            return
        jobs, title = resolve_jobs(session, res, args)
        print(f"  {title}: {len(jobs)} 个任务，开始下载")
        for job in jobs:
            process_job(session, job, args)

    watch(handle)


def cmd_mylist(args):
    session = auth.build_session()
    ok, vip, mid, uname = auth.check_login(session)
    if not ok:
        raise SystemExit("需先登录")
    if args.what == "favs":
        data = api.get_my_favs(session, mid)
        for f in (data or {}).get("list", []) or []:
            print(f"  fav:{f['id']}  {f['title']}  ({f['media_count']}个内容)")
        print('用 download "fav:<id>" 下载整个收藏夹')
    elif args.what in ("bangumi", "cinema"):
        t = 1 if args.what == "bangumi" else 2
        data = api.get_my_bangumi(session, mid, type_=t)
        for s in (data or {}).get("list", []) or []:
            print(f"  ss{s['season_id']}  {s['title']}  [{s.get('new_ep', {}).get('index_show', '')}]")
        print('用 download "ss<id>" --episodes all 下载整部')


def cmd_history(args):
    hist = load_json(HISTORY_FILE, []) or []
    if not hist:
        print("暂无下载记录")
        return
    for h in hist[-(args.limit or 50):]:
        print(f"  [{h.get('time')}] {h.get('type', ''):8s} {h.get('title')}\n"
              f"      -> {h.get('path')}")
    print(f"共 {len(hist)} 条记录 (存于 ~/.bili_dl/history.json)")


# ======================================================================
# argparse
# ======================================================================

def add_download_opts(p):
    p.add_argument("-o", "--output", default="./downloads", help="保存目录")
    p.add_argument("--quality", help="画质: 360P~8K/HDR/杜比视界 或 qn 数值")
    p.add_argument("--audio", help="音质: 64K/132K/192K/杜比/Hi-Res")
    p.add_argument("--codec", choices=["h264", "avc", "h265", "hevc", "av1"],
                   help="视频编码偏好")
    p.add_argument("--fps", choices=["30", "60"], help="帧率档位")
    p.add_argument("--pages", help="分P选择: all 或 1,3-5")
    p.add_argument("--episodes", help="剧集选择: all/current 或 1,3-5")
    p.add_argument("--season", action="store_true", help="下载视频所属整个合集")
    p.add_argument("--with-extras", action="store_true", help="番剧正片+花絮同时解析")
    p.add_argument("--audio-only", nargs="?", const="m4a",
                   choices=["mp3", "m4a", "webm", "flac"], help="仅下载音频并转为指定格式")
    p.add_argument("--video-only", action="store_true", help="仅下载无声视频")
    p.add_argument("--danmaku", help="弹幕格式: xml,ass,protobuf (逗号分隔)")
    p.add_argument("--subtitle", help="字幕格式: srt,txt,json (逗号分隔)")
    p.add_argument("--cover", action="store_true", help="下载封面")
    p.add_argument("--lyrics", action="store_true", help="尝试下载歌词")
    p.add_argument("--flv", action="store_true", help="FLV durl 模式(远古视频)")
    p.add_argument("--keep-flv", action="store_true", help="FLV 模式不转 MP4")
    p.add_argument("--transcode", choices=["h264", "hevc"], help="下载后重新编码")
    p.add_argument("--gpu", action="store_true", help="转码启用 GPU 硬件加速")
    p.add_argument("--threads", type=int, default=8, help="单文件下载线程数(<=8)")
    p.add_argument("--workers", type=int, default=3, help="队列并行任务数")
    p.add_argument("--limit", type=int, help="列表型资源最多下载条数")
    p.add_argument("--numbering", action="store_true", help="文件名添加序号前缀")
    p.add_argument("--auto-triple", action="store_true", help="下载后自动三连(需登录)")


def main():
    ap = argparse.ArgumentParser(
        prog="bili_dl", description="哔哩哔哩全能下载器",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("info", help="解析并查看资源信息")
    p.add_argument("url")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("download", help="下载")
    p.add_argument("url")
    add_download_opts(p)
    p.set_defaults(func=cmd_download)

    p = sub.add_parser("record", help="直播录制")
    p.add_argument("url")
    p.add_argument("-o", "--output", default="./downloads")
    p.add_argument("--quality", help="原画/蓝光/超清/高清/4K/杜比")
    p.add_argument("--transcode", action="store_true", help="录制后转 MP4")
    p.set_defaults(func=cmd_record)

    p = sub.add_parser("login", help="登录")
    p.add_argument("--sms", action="store_true", help="短信验证码登录")
    p.add_argument("--check", action="store_true", help="查看登录状态")
    p.add_argument("--import-cookie", help="导入浏览器 Cookie 字符串")
    p.set_defaults(func=cmd_login)

    p = sub.add_parser("batch", help="批量下载(文件, 每行一个链接)")
    p.add_argument("file")
    add_download_opts(p)
    p.set_defaults(func=cmd_batch)

    p = sub.add_parser("watch", help="监视剪贴板自动下载")
    add_download_opts(p)
    p.set_defaults(func=cmd_watch)

    p = sub.add_parser("mylist", help="我的收藏夹/追番列表")
    p.add_argument("what", choices=["favs", "bangumi", "cinema"])
    p.set_defaults(func=cmd_mylist)

    p = sub.add_parser("history", help="本地下载记录")
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(func=cmd_history)

    args = ap.parse_args()
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\n已取消")
        sys.exit(130)
    except api.BiliApiError as e:
        print(f"\nAPI 错误: {e}")
        if e.code in (-101, -400, -403, 87007, 87008, 6002003):
            print("提示: 该内容可能需要登录或大会员，运行 `login` 扫码后重试。")
        sys.exit(1)


if __name__ == "__main__":
    main()
