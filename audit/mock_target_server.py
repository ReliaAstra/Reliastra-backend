"""Mock dependency target server used for production-readiness tests.

Emulates the httpbin.org behaviors the test plan expects:
  /get          -> 200 OK            (healthy)
  /status/500   -> 500               (unhealthy)
  /delay/15     -> sleep 15s -> 200  (slow / timeout)
  /redirect/3   -> 3x 302 -> 200     (redirect chain)
  /status/404   -> 404               (not found / unhealthy)
  /robots.txt   -> 200 with body
Any other path  -> 200 OK

Binds 0.0.0.0 so it can be reached via the public preview hostname.
"""
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 9100


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code: int, body: bytes = b"", headers: dict | None = None) -> None:
        self.send_response(code)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def log_message(self, fmt, *args):
        print("[mock-target] %s" % (fmt % args), flush=True)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path.startswith("/delay/"):
            secs = float(path.rsplit("/", 1)[1] or "15")
            time.sleep(secs)
            self._send(200, b"delayed ok")
        elif path.startswith("/redirect/"):
            n = int(path.rsplit("/", 1)[1] or "1")
            if n > 1:
                self._send(302, b"", {"Location": f"/redirect/{n - 1}"})
            else:
                self._send(200, b"redirected ok")
        elif path == "/status/500":
            self._send(500, b"boom")
        elif path == "/status/404":
            self._send(404, b"nope")
        elif path == "/status/503":
            self._send(503, b"unavailable")
        else:
            self._send(200, b'{"ok": true}')

    do_POST = do_GET
    do_PATCH = do_GET


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"mock target listening on 0.0.0.0:{PORT}", flush=True)
    srv.serve_forever()
