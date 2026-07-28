"""本地 Web 服务：用标准库 http.server 提供 GUI 页面与 JSON API（无额外依赖）。"""
import os
import sys
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .core import GuiCore

CORE = GuiCore()


def _static_dir():
    """Locate the GUI static dir in dev, one-folder EXE, or one-file EXE."""
    here = os.path.dirname(os.path.abspath(__file__))
    meipass = getattr(sys, "_MEIPASS", "")
    cands = [
        os.path.join(here, "static"),
        os.path.join(meipass, "bili_gui", "static"),
        os.path.join(meipass, "static"),
    ]
    for c in cands:
        if c and os.path.isfile(os.path.join(c, "index.html")):
            return c
    return os.path.join(here, "static")


STATIC_DIR = _static_dir()

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}


def _read_body(handler):
    length = int(handler.headers.get("Content-Length") or 0)
    if not length:
        return {}
    raw = handler.rfile.read(length)
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}


def _send_json(handler, data, code=200):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


def _send_file(handler, path):
    ext = os.path.splitext(path)[1].lower()
    ctype = MIME.get(ext, "application/octet-stream")
    try:
        with open(path, "rb") as f:
            data = f.read()
    except Exception:
        handler.send_error(404)
        return
    handler.send_response(200)
    handler.send_header("Content-Type", ctype)
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass  # silence default logging

    def _dispatch_api(self, path, body):
        if path == "/api/meta":
            return CORE.meta()
        if path == "/api/status":
            return CORE.status()
        if path == "/api/resolve":
            return CORE.resolve(body.get("url", ""),
                                season=body.get("season", False),
                                with_extras=body.get("with_extras"),
                                limit=body.get("limit", 0))
        if path == "/api/submit":
            return CORE.submit(body.get("plan_id"), body.get("indices") or [],
                               body.get("options") or {})
        if path == "/api/tasks":
            return {"tasks": CORE.list_tasks()}
        if path == "/api/tasks/clear":
            CORE.clear_tasks()
            return {"ok": True}
        if path == "/api/record":
            return CORE.record(body.get("room_id"), body.get("quality", "原画"))
        if path == "/api/login/qr":
            return CORE.login_qr_start()
        if path == "/api/login/status":
            return CORE.login_status()
        if path == "/api/login/cookie":
            return CORE.import_cookie(body.get("cookie", ""))
        if path == "/api/login/check":
            return CORE.login_status()
        if path == "/api/mylist":
            return {"items": CORE.mylist(body.get("kind", "favs"))}
        if path == "/api/history":
            return {"items": CORE.history(body.get("limit", 50))}
        if path == "/api/settings":
            return CORE.settings
        if path == "/api/clipboard":
            act = body.get("action")
            if act == "start":
                CORE.clipboard_start()
            elif act == "stop":
                CORE.clipboard_stop()
            return CORE.clipboard_state()
        if path == "/api/clipboard/state":
            return CORE.clipboard_state()
        if path == "/api/settings/save":
            return CORE.save_settings(body or {})
        if path in ("/api/task/cancel", "/api/tasks/cancel"):
            return {"ok": CORE.cancel(body.get("id"))}
        if path in ("/api/task/retry", "/api/tasks/retry"):
            return {"id": CORE.retry(body.get("id"))}
        if path in ("/api/task/pause", "/api/tasks/pause"):
            return {"ok": CORE.pause(body.get("id"))}
        if path in ("/api/task/resume", "/api/tasks/resume"):
            return {"id": CORE.resume(body.get("id"))}
        if path in ("/api/task/reorder", "/api/tasks/reorder"):
            return {"ok": CORE.reorder(body.get("ids") or [])}
        if path in ("/api/task/open", "/api/tasks/open"):
            return {"ok": CORE.open_path(body.get("path"))}
        # 自动更新检查路由已移除（纯本地软件，不依赖 GitHub）
        if path == "/api/space":
            return CORE.space_videos(body.get("mid"), pn=int(body.get("pn", 1)),
                                      ps=int(body.get("ps", 30)))
        if path == "/api/push":
            return {"tasks": CORE.push_url(body.get("url", ""))}
        if path == "/api/logs":
            return {"lines": CORE.read_logs(int(body.get("lines", 200)))}
        if path == "/api/accounts":
            act = body.get("action")
            if act == "add":
                return {"ok": CORE.add_account(body.get("name"), body.get("cookie"))}
            if act == "switch":
                return {"status": CORE.switch_account(body.get("name"))}
            if act == "remove":
                return {"ok": CORE.remove_account(body.get("name"))}
            return CORE.list_accounts()
        if path == "/api/subs":
            return CORE.sub_list()
        if path == "/api/subs/add":
            return CORE.sub_add(
                body.get("target", ""),
                auto_download=bool(body.get("auto_download", True)),
                download_existing=bool(body.get("download_existing", False)))
        if path == "/api/subs/remove":
            return {"ok": CORE.sub_remove(body.get("id"))}
        if path == "/api/subs/toggle":
            return CORE.sub_toggle(body.get("id"),
                                   body.get("field", "enabled"))
        if path == "/api/subs/check":
            return CORE.sub_check(body.get("id") or None)
        if path == "/api/settings/export":
            return CORE.export_settings()
        if path == "/api/settings/import":
            return {"ok": bool(CORE.import_settings(body.get("settings")))}
        if path == "/api/proc/burn":
            return {"out": CORE.proc_burn(body.get("video"), body.get("sub"),
                                           body.get("out"), int(body.get("font_size", 24)))}
        if path == "/api/proc/cut":
            return {"out": CORE.proc_cut(body.get("video"), body.get("out"),
                                         body.get("start"), body.get("end") or None)}
        if path == "/api/proc/merge":
            return {"out": CORE.proc_merge(body.get("files") or [],
                                           body.get("out"), body.get("titles"))}
        if path == "/api/proc/ai_sub":
            return {"out": CORE.proc_ai_sub(body.get("video"),
                                            body.get("lang", "zh"),
                                            body.get("model", "base"))}
        raise ValueError(f"未知接口: {path}")

    def do_OPTIONS(self):
        # 浏览器扩展跨域推送 (CORS 预检)
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        import urllib.parse
        full = self.path
        path = full.split("?", 1)[0]
        if path == "/" or path == "/index.html":
            _send_file(self, os.path.join(STATIC_DIR, "index.html"))
            return
        if path.startswith("/static/"):
            name = os.path.basename(path)
            _send_file(self, os.path.join(STATIC_DIR, name))
            return
        if path.startswith("/api/"):
            qs = urllib.parse.parse_qs(full.split("?", 1)[1]) if "?" in full else {}
            body = {k: (v[0] if len(v) == 1 else v) for k, v in qs.items()}
            try:
                _send_json(self, self._dispatch_api(path, body))
            except Exception as e:  # noqa
                _send_json(self, {"error": str(e)}, code=400)
            return
        self.send_error(404)

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if not path.startswith("/api/"):
            self.send_error(404)
            return
        body = _read_body(self)
        try:
            _send_json(self, self._dispatch_api(path, body))
        except Exception as e:  # noqa
            _send_json(self, {"error": str(e)}, code=400)


def run(host="127.0.0.1", port=0, open_browser=True):
    server = ThreadingHTTPServer((host, port), Handler)
    actual_port = server.server_address[1]
    url = f"http://{host}:{actual_port}/"
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    if open_browser:
        import webbrowser
        try:
            webbrowser.open(url)
        except Exception:
            pass
    return server, url, actual_port


if __name__ == "__main__":
    srv, url, port = run(port=8234)
    print(f"BiliDL GUI 已启动: {url}  (Ctrl+C 退出)")
    try:
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        srv.shutdown()
