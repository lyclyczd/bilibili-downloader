"""本地 Web 服务：用标准库 http.server 提供 GUI 页面与 JSON API（无额外依赖）。"""
import os
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .core import GuiCore

CORE = GuiCore()
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

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
        if path == "/api/task/cancel":
            return {"ok": CORE.cancel(body.get("id"))}
        if path == "/api/task/retry":
            return {"id": CORE.retry(body.get("id"))}
        if path == "/api/task/open":
            return {"ok": CORE.open_path(body.get("path"))}
        raise ValueError(f"未知接口: {path}")

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
