"""Minimal Paystack API mock so billing flows can be exercised end-to-end.

Endpoints:
  POST /transaction/initialize  -> returns authorization_url/reference/access_code
  GET  /transaction/verify/:ref -> returns verified transaction
Any other path -> 404
"""
import json
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 9200
_tx = {}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        print("[paystack-mock] %s" % (fmt % args), flush=True)

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        ln = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(ln) if ln else b"{}"
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {}
        if self.path == "/transaction/initialize":
            ref = payload.get("reference") or f"mock-ref-{uuid.uuid4().hex[:12]}"
            amount = payload.get("amount")
            _tx[ref] = {"status": True, "amount": amount, "reference": ref}
            self._json(200, {
                "status": True,
                "message": "Authorization URL created",
                "data": {
                    "authorization_url": "https://checkout.paystack.com/mock",
                    "access_code": "mock-access-code",
                    "reference": ref,
                },
            })
        else:
            self._json(404, {"status": False, "message": "not found"})

    def do_GET(self):
        if self.path.startswith("/transaction/verify/"):
            ref = self.path.rsplit("/", 1)[-1]
            if ref in _tx:
                self._json(200, {
                    "status": True,
                    "message": "Verification successful",
                    "data": {"reference": ref, "status": "success", "amount": _tx[ref].get("amount")},
                })
            else:
                self._json(404, {"status": False, "message": "Unknown reference"})
        else:
            self._json(404, {"status": False, "message": "not found"})


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"paystack mock listening on 0.0.0.0:{PORT}", flush=True)
    srv.serve_forever()
