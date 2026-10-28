"""Local desk server. Bind it to localhost. It only serves this page and its assets."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .perform import handle_click, public_state
from .view import STATIC, render_page

_LOCK = threading.Lock()

_FILES = {
    "/desk.css": (STATIC / "desk.css", "text/css; charset=utf-8"),
    "/desk.js": (STATIC / "desk.js", "text/javascript; charset=utf-8"),
}
_FONTS = {
    "/fonts/graphic-novel-sans-400.woff2",
    "/fonts/graphic-novel-sans-600.woff2",
    "/fonts/graphic-novel-sans-700.woff2",
    "/fonts/source-sans-400.woff2",
    "/fonts/source-sans-600.woff2",
    "/fonts/muthr.woff2",
}


class DeskHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        return

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/":
            with _LOCK:
                state = public_state(self.server.root)
            body = render_page(state).encode("utf-8")
            self._send(200, body, "text/html; charset=utf-8")
            return
        if path == "/api/state":
            with _LOCK:
                state = public_state(self.server.root)
            self._send(200, json.dumps(state).encode("utf-8"), "application/json")
            return
        if path in _FILES:
            file, ctype = _FILES[path]
            self._send(200, file.read_bytes(), ctype)
            return
        if path in _FONTS:
            file = STATIC / "fonts" / path.rsplit("/", 1)[1]
            self._send(200, file.read_bytes(), "font/woff2")
            return
        self._send(404, b"not found", "text/plain; charset=utf-8")

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path != "/api/click":
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(400, {"outcome": {
                "id": "", "control": "", "stage": "", "title": "Desk",
                "ok": False, "tone": "fail", "code": 1,
                "summary": "The click was not valid JSON.",
                "detail": "", "wrote": [], "changed": [],
            }})
            return
        if not isinstance(body, dict):
            self._json(400, {"outcome": {
                "id": "", "control": "", "stage": "", "title": "Desk",
                "ok": False, "tone": "fail", "code": 1,
                "summary": "The click was not a JSON object.",
                "detail": "", "wrote": [], "changed": [],
            }})
            return
        try:
            with _LOCK:
                outcome = handle_click(self.server.root, body)
                state = public_state(self.server.root)
        except Exception as exc:
            outcome = {
                "id": str(body.get("id") or ""),
                "control": "", "stage": "", "title": "Desk",
                "ok": False, "tone": "fail", "code": 1,
                "summary": "%s: %s" % (type(exc).__name__, exc),
                "detail": "", "wrote": [], "changed": [],
            }
            state = {}
            self._json(500, {"outcome": outcome, "state": state})
            return
        self._json(200, {"outcome": outcome, "state": state})

    def _json(self, status, payload):
        self._send(status, json.dumps(payload).encode("utf-8"), "application/json")

    def _send(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def make_server(root, host="127.0.0.1", port=0):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    httpd = ThreadingHTTPServer((host, port), DeskHandler)
    httpd.root = root
    return httpd


def serve_background(root, port=0):
    httpd = make_server(root, "127.0.0.1", port)
    thread = threading.Thread(target=httpd.serve_forever, name="low-tide-desk", daemon=True)
    thread.start()
    httpd._desk_thread = thread
    return httpd
