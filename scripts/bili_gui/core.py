"""GUI 后端核心：封装 bili 引擎，提供解析 / 任务队列 / 登录 / 剪贴板 / 列表 / 历史。

所有对外方法返回可 JSON 序列化的 dict / list；耗时网络操作（解析、下载）在
后台线程执行，进度通过 TaskProgress 实时写入内存任务表，前端轮询 /api/tasks 即可。
"""
import os
import io
import sys
import time
import json
import uuid
import base64
import threading
import subprocess
from types import SimpleNamespace

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../scripts
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from bili import api, auth, parser, extras, muxer  # noqa
from bili.downloader import download_file, record_stream  # noqa
from bili.taskqueue import TaskQueue  # noqa
from bili.utils import (sanitize_filename, format_size, add_history, load_json,
                        save_json, HISTORY_FILE, av2bv, ensure_app_dir, APP_DIR)  # noqa
import bili_dl  # noqa
from bili.clipboard_watch import read_clipboard, BILI_PATTERN  # noqa


# ======================================================================
# Task model
# ======================================================================

class Task:
    def __init__(self, tid, title, kind="video"):
        self.id = tid
        self.title = title
        self.kind = kind
        self.status = "queued"      # queued / running / done / failed / canceled
        self.phase = "排队中"
        self.done = 0
        self.total = 0
        self.progress = 0.0
        self.speed = 0
        self.eta = None
        self.error = None
        self.result_path = None
        self.log = []
        self.created = time.time()
        self._job = None
        self._args = None


class TaskProgress:
    """Sink passed to engine (download_file / process_job)."""

    def __init__(self, task):
        self.task = task

    def set_phase(self, name):
        self.task.phase = name
        if self.task.status == "queued":
            self.task.status = "running"

    def update(self, done, total, label, speed=0, eta=None):
        self.task.phase = label or self.task.phase
        self.task.status = "running"
        self.task.done = done
        self.task.total = total
        self.task.progress = (done / total * 100) if total else self.task.progress
        self.task.speed = speed or 0
        self.task.eta = eta

    def finish(self, path):
        self.task.status = "done"
        self.task.phase = "完成"
        self.task.progress = 100
        self.task.result_path = path
        self.task.speed = 0

    def error(self, msg):
        self.task.status = "failed"
        self.task.phase = "失败"
        self.task.error = msg
        self.task.speed = 0

    def log(self, msg):
        self.task.log.append(msg)


class Store:
    def __init__(self):
        self.tasks = {}
        self.lock = threading.Lock()

    def new_task(self, title, kind="video"):
        with self.lock:
            t = Task(uuid.uuid4().hex[:8], title, kind)
            self.tasks[t.id] = t
            return t

    def get(self, tid):
        return self.tasks.get(tid)

    def list(self):
        with self.lock:
            return sorted(self.tasks.values(), key=lambda x: x.created, reverse=True)

    def remove(self, tid):
        with self.lock:
            self.tasks.pop(tid, None)


# ======================================================================
# GuiCore
# ======================================================================

class GuiCore:
    def __init__(self):
        self.store = Store()
        self.session = auth.build_session()
        self.plans = {}
        self._clip = {"on": False, "thread": None}
        self._qr = {"status": "none", "msg": "", "key": None, "session": None}
        self.settings = self._load_settings()

    # ---------- settings ----------
    def _load_settings(self):
        defaults = {
            "output": os.path.abspath(os.path.join(os.getcwd(), "downloads")),
            "threads": 8,
            "workers": 3,
            "quality": "",
            "audio": "",
            "codec": "",
            "fps": "",
            "mode": "full",        # full | audio | video
            "audio_fmt": "m4a",
            "danmaku": ["xml", "ass"],
            "subtitle": [],
            "cover": True,
            "lyrics": False,
            "auto_triple": False,
            "gpu": False,
            "transcode": "",
            "numbering": True,
            "with_extras": False,
            "open_folder": True,
        }
        s = load_json(os.path.join(APP_DIR, "gui_settings.json"), {}) or {}
        defaults.update(s)
        if isinstance(defaults.get("danmaku"), str):
            defaults["danmaku"] = [x for x in defaults["danmaku"].split(",") if x]
        if isinstance(defaults.get("subtitle"), str):
            defaults["subtitle"] = [x for x in defaults["subtitle"].split(",") if x]
        return defaults

    def save_settings(self, patch):
        clean = {}
        for k, v in patch.items():
            if k in self.settings:
                clean[k] = v
        self.settings.update(clean)
        save_json(os.path.join(APP_DIR, "gui_settings.json"), self.settings)
        return self.settings

    # ---------- meta / status ----------
    def meta(self):
        return {
            "qualities": [{"label": k, "qn": v} for k, v in api.QN_MAP.items()],
            "audios": [{"label": k, "id": v} for k, v in api.AUDIO_MAP.items()],
            "codecs": ["", "h264", "hevc", "av1"],
            "audio_fmts": ["m4a", "mp3", "webm", "flac"],
            "danmaku_fmts": ["xml", "ass", "protobuf"],
            "subtitle_fmts": ["srt", "txt", "json"],
        }

    def status(self):
        try:
            gpu = muxer.detect_gpu_encoders()
        except Exception:
            gpu = {"h264": "libx264", "hevc": "libx265"}
        return {
            "ffmpeg": muxer.has_ffmpeg(),
            "ffmpeg_path": muxer.FFMPEG,
            "gpu": gpu,
            "output_default": self.settings["output"],
        }

    # ---------- resolve ----------
    def resolve(self, url, season=False, with_extras=None, limit=0):
        res = parser.parse(url, self.session)
        if res.kind == "live":
            info = api.get_live_room_info(self.session, res.id_value)
            return {
                "kind": "live", "room_id": res.id_value,
                "title": info.get("title"),
                "live_status": {0: "未开播", 1: "直播中", 2: "轮播中"}.get(
                    info.get("live_status"), "?"),
                "online": info.get("online"),
            }
        we = with_extras if with_extras is not None else self.settings["with_extras"]
        args = SimpleNamespace(output=self.settings["output"], season=season,
                               pages="all", with_extras=we, episodes="all",
                               limit=limit or None)
        jobs, title = bili_dl.resolve_jobs(self.session, res, args)
        plan_id = uuid.uuid4().hex[:10]
        job_summ = [{"title": j.title, "type": j.type, "bvid": j.bvid,
                     "aid": j.aid, "cid": j.cid, "ep_id": j.ep_id,
                     "index": j.index} for j in jobs]
        cover = jobs[0].pic if jobs else None
        qualities, audios = self._probe_quality(jobs)
        plan = {
            "plan_id": plan_id, "kind": res.kind, "title": title,
            "count": len(jobs), "jobs": job_summ, "cover": cover,
            "qualities": qualities, "audios": audios,
        }
        self.plans[plan_id] = {"res": res, "jobs": jobs, "title": title,
                               "kind": res.kind}
        return plan

    def _probe_quality(self, jobs):
        if not jobs:
            return [], []
        job = jobs[0]
        try:
            if job.cid is None:
                info = api.get_video_info(self.session, bvid=job.bvid)
                job.cid = api.get_video_pages(info)[0]["cid"]
            if job.type == "bangumi":
                play = api.get_bangumi_playurl(self.session, job.ep_id, job.cid)
            elif job.type == "cheese":
                play = api.get_cheese_playurl(self.session, job.aid, job.ep_id, job.cid)
            else:
                play = api.get_playurl(self.session, job.bvid, job.cid)
        except Exception:
            return [], []
        dash = play.get("dash")
        if not dash:
            return [{"qn": 0, "label": "FLV/durl (远古视频)", "codecs": [],
                     "need_vip": False}], []
        seen = {}
        for v in dash.get("video", []):
            seen.setdefault(v["id"], set()).add(
                api.CODEC_DESC.get(v.get("codecid"), "?"))
        qualities = []
        for qn in sorted(seen, reverse=True):
            qualities.append({"qn": qn, "label": api.QN_DESC.get(qn, qn),
                              "codecs": sorted(seen[qn]), "need_vip": False})
        need_vip = set(f["new_description"] for f in (play.get("support_formats") or [])
                       if f.get("need_vip"))
        for q in qualities:
            if q["label"] in need_vip:
                q["need_vip"] = True
        auds = list(dash.get("audio") or [])
        auds += (dash.get("dolby") or {}).get("audio") or []
        if (dash.get("flac") or {}).get("audio"):
            auds.append(dash["flac"]["audio"])
        audios = [{"id": a["id"], "label": api.AUDIO_DESC.get(a["id"], a["id"])}
                  for a in sorted(auds, key=lambda x: x["id"])]
        return qualities, audios

    # ---------- submit ----------
    def _build_args(self, options, out_root):
        s = self.settings
        mode = options.get("mode", s["mode"])
        audio_only = None
        video_only = False
        if mode == "audio":
            audio_only = options.get("audio_fmt", s.get("audio_fmt", "m4a"))
        elif mode == "video":
            video_only = True
        danmaku = options.get("danmaku", s.get("danmaku"))
        if isinstance(danmaku, list):
            danmaku = ",".join(danmaku) if danmaku else None
        subtitle = options.get("subtitle", s.get("subtitle"))
        if isinstance(subtitle, list):
            subtitle = ",".join(subtitle) if subtitle else None
        return SimpleNamespace(
            output=out_root,
            quality=options.get("quality") or s.get("quality") or None,
            audio=options.get("audio") or s.get("audio") or None,
            codec=options.get("codec") or s.get("codec") or None,
            fps=options.get("fps") or s.get("fps") or None,
            pages="all", episodes="all",
            season=options.get("season", False),
            with_extras=options.get("with_extras", s.get("with_extras", False)),
            audio_only=audio_only, video_only=video_only,
            danmaku=danmaku, subtitle=subtitle,
            cover=options.get("cover", s.get("cover", True)),
            lyrics=options.get("lyrics", s.get("lyrics", False)),
            flv=options.get("flv", False),
            keep_flv=options.get("keep_flv", False),
            transcode=options.get("transcode") or s.get("transcode") or None,
            gpu=options.get("gpu", s.get("gpu", False)),
            threads=options.get("threads", s.get("threads", 8)),
            workers=options.get("workers", s.get("workers", 3)),
            limit=options.get("limit"),
            numbering=options.get("numbering", s.get("numbering", True)),
            auto_triple=options.get("auto_triple", s.get("auto_triple", False)),
        )

    def submit(self, plan_id, indices, options):
        plan = self.plans.get(plan_id)
        if not plan:
            raise ValueError("plan 不存在或已过期，请重新解析链接")
        res = plan["res"]
        out_root = options.get("output") or self.settings["output"]
        args = self._build_args(options, out_root)
        jobs, _ = bili_dl.resolve_jobs(self.session, res, args)
        if options.get("season"):
            sel = jobs
        elif indices:
            sel = [j for j in jobs if j.index in indices]
        else:
            sel = jobs
        if not sel:
            raise ValueError("未选择任何任务")
        q = TaskQueue(workers=args.workers or 3, retries=2)
        tasks = []
        for job in sel:
            t = self.store.new_task(job.title, job.type)
            prog = TaskProgress(t)
            q.add(job.title, self._run_job, self.session, job, args, prog)
            tasks.append(t)
        threading.Thread(target=self._run_queue, args=(q,), daemon=True).start()
        return {"queued": len(sel), "tasks": [t.id for t in tasks]}

    def _run_job(self, session, job, args, prog):
        prog.task._job = job
        prog.task._args = args
        try:
            bili_dl.process_job(session, job, args, prog)
        except Exception as e:  # noqa
            prog.error(f"{type(e).__name__}: {e}")
            raise

    def _run_queue(self, q):
        q.run()

    def quick_download(self, url):
        """Used by clipboard watcher: resolve + submit all with defaults."""
        try:
            res = parser.parse(url, self.session)
            if res.kind == "live":
                return {"skipped": "live"}
            args = self._build_args({}, self.settings["output"])
            jobs, _ = bili_dl.resolve_jobs(self.session, res, args)
            q = TaskQueue(workers=self.settings["workers"] or 3, retries=2)
            tasks = []
            for job in jobs:
                t = self.store.new_task(job.title, job.type)
                prog = TaskProgress(t)
                q.add(job.title, self._run_job, self.session, job, args, prog)
                tasks.append(t)
            threading.Thread(target=self._run_queue, args=(q,), daemon=True).start()
            return [t.id for t in tasks]
        except Exception as e:  # noqa
            return {"error": str(e)}

    # ---------- live record ----------
    def record(self, room_id, quality="原画"):
        qn_map = {"杜比": 30000, "4K": 20000, "原画": 10000, "蓝光": 400,
                  "超清": 250, "高清": 150, "流畅": 80}
        qn = qn_map.get(quality, 10000)
        info = api.get_live_room_info(self.session, room_id)
        if info.get("live_status") != 1:
            raise ValueError(f"直播间未开播: {info.get('title')}")
        play = api.get_live_stream(self.session, room_id, qn=qn)
        url, _ = api.pick_live_url(play)
        if not url:
            raise ValueError("未取得直播流地址（可能需要登录）")
        title = sanitize_filename(info.get("title", f"live_{room_id}"))
        dest = os.path.join(self.settings["output"],
                            f"{title}_{time.strftime('%Y%m%d_%H%M%S')}.flv")
        t = self.store.new_task(f"录制: {title}", "live")
        prog = TaskProgress(t)
        threading.Thread(target=self._run_record, args=(url, dest, t, prog),
                         daemon=True).start()
        return {"task": t.id, "dest": dest}

    def _run_record(self, url, dest, task, prog):
        try:
            prog.set_phase("录制中")
            record_stream(self.session, url, dest, label="直播录制")
            add_history({"title": os.path.basename(dest), "type": "live",
                         "path": dest})
            prog.finish(dest)
        except Exception as e:  # noqa
            prog.error(f"{type(e).__name__}: {e}")

    # ---------- tasks ----------
    @staticmethod
    def serialize(t):
        return {
            "id": t.id, "title": t.title, "status": t.status, "phase": t.phase,
            "progress": round(t.progress, 1), "speed": t.speed, "eta": t.eta,
            "result_path": t.result_path, "error": t.error, "kind": t.kind,
            "log": t.log[-25:],
        }

    def list_tasks(self):
        return [self.serialize(t) for t in self.store.list()]

    def get_task(self, tid):
        t = self.store.get(tid)
        return self.serialize(t) if t else None

    def cancel(self, tid):
        t = self.store.get(tid)
        if t and t.status in ("queued", "running"):
            t.status = "canceled"
            t.phase = "已取消"
            return True
        return False

    def retry(self, tid):
        t = self.store.get(tid)
        if not t or not getattr(t, "_job", None):
            return None
        if t.status != "failed":
            return None
        nt = self.store.new_task(t.title, t.kind)
        nt._job = t._job
        nt._args = t._args
        q = TaskQueue(workers=1, retries=2)
        q.add(t.title, self._run_job, self.session, t._job, t._args, TaskProgress(nt))
        threading.Thread(target=self._run_queue, args=(q,), daemon=True).start()
        return nt.id

    def clear_tasks(self):
        self.store.tasks.clear()
        return True

    def open_path(self, path):
        try:
            if os.path.isfile(path):
                path = os.path.dirname(path)
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.run(["open", path])
            else:
                subprocess.run(["xdg-open", path])
            return True
        except Exception:
            return False

    # ---------- login ----------
    def login_qr_start(self):
        session = auth.build_session()
        r = session.get(f"{auth.PASSPORT}/x/passport-login/web/qrcode/generate",
                        timeout=10)
        data = r.json()["data"]
        url, qr_key = data["url"], data["qrcode_key"]
        png = self._qr_png(url)
        self._qr = {"status": "waiting", "msg": "请使用哔哩哔哩 App 扫码",
                    "key": qr_key, "session": session}
        threading.Thread(target=self._poll_qr, args=(qr_key, session),
                         daemon=True).start()
        return {"qr": png}

    def _qr_png(self, url):
        import qrcode
        buf = io.BytesIO()
        q = qrcode.QRCode(box_size=8, border=2)
        q.add_data(url)
        q.make(fit=True)
        q.make_image(fill_color="black", back_color="white").save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")

    def _poll_qr(self, qr_key, session):
        t0 = time.time()
        while time.time() - t0 < 180:
            time.sleep(2)
            try:
                r = session.get(
                    f"{auth.PASSPORT}/x/passport-login/web/qrcode/poll",
                    params={"qrcode_key": qr_key}, timeout=10)
                d = r.json()["data"]
                code = d.get("code")
            except Exception:
                continue
            if code == 0:
                auth.save_session_cookies(session)
                self.session = auth.build_session()
                self._qr["status"] = "success"
                self._qr["msg"] = "登录成功！Cookie 已保存"
                return
            elif code == 86090:
                self._qr["status"] = "scanned"
                self._qr["msg"] = "已扫码，请在手机上确认登录"
            elif code == 86038:
                self._qr["status"] = "expired"
                self._qr["msg"] = "二维码已过期，请重新获取"
                return
        self._qr["status"] = "timeout"
        self._qr["msg"] = "登录超时"

    def login_status(self):
        try:
            ok, vip, mid, uname = auth.check_login(self.session)
        except Exception:
            ok, vip, mid, uname = False, False, 0, ""
        return {"logged_in": ok, "vip": vip, "uname": uname,
                "mid": mid,
                "qr_status": self._qr.get("status", "none"),
                "qr_msg": self._qr.get("msg", "")}

    def import_cookie(self, cookie_str):
        auth.import_cookie(cookie_str)
        self.session = auth.build_session()
        return self.login_status()

    # ---------- mylist / history ----------
    def mylist(self, kind):
        ok, vip, mid, uname = auth.check_login(self.session)
        if not ok:
            raise ValueError("需先登录后才能查看个人列表")
        if kind == "favs":
            data = api.get_my_favs(self.session, mid)
            return [{"id": f["id"], "title": f["title"], "count": f["media_count"]}
                    for f in (data or {}).get("list", []) or []]
        t = 1 if kind == "bangumi" else 2
        data = api.get_my_bangumi(self.session, mid, type_=t)
        return [{"id": s["season_id"], "title": s["title"],
                 "index": s.get("new_ep", {}).get("index_show", "")}
                for s in (data or {}).get("list", []) or []]

    def history(self, limit=50):
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 50
        hist = load_json(HISTORY_FILE, []) or []
        if not isinstance(hist, list):
            hist = []
        return hist[-limit:][::-1]

    # ---------- clipboard ----------
    def clipboard_start(self):
        if self._clip["on"]:
            return False
        self._clip["on"] = True
        self._clip["thread"] = threading.Thread(target=self._clip_loop, daemon=True)
        self._clip["thread"].start()
        return True

    def clipboard_stop(self):
        self._clip["on"] = False
        return True

    def clipboard_state(self):
        return {"on": self._clip["on"]}

    def _clip_loop(self):
        seen = set()
        last = ""
        while self._clip["on"]:
            time.sleep(1)
            try:
                text = read_clipboard() or ""
            except Exception:
                continue
            if text == last:
                continue
            last = text
            for m in BILI_PATTERN.finditer(text):
                key = m.group(0)
                if key in seen:
                    continue
                seen.add(key)
                try:
                    self.quick_download(key)
                except Exception:
                    pass
