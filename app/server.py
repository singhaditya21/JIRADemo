#!/usr/bin/env python3
"""Local JSON API for the React control tower.

The React app cannot call Jira directly - Jira Cloud blocks browser-origin requests
(CORS) and the token must never reach the browser. So this holds the token server-side,
fetches once through the same app/ pipeline the static control tower uses, and serves the
computed model as JSON at:

    GET /api/tower?project=OPS&days=90   ->  app.control_tower.build_model(...) as JSON

It is the exact same model the HTML renderer consumes, so the React UI and the static
page can never disagree about a number. Read-only: no endpoint mutates Jira.

    python3 -m app.server [--port 8000]

Then run the React dev server (webapp/), which proxies /api to this port.
"""

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from shared.jira_client import Jira, require_env
from shared import fields as FIELDS
from app import store as S
from app.control_tower import build_model

_CACHE = {}
_LOCK = threading.Lock()
_TTL = 120  # seconds; the tower is a monitoring view, a 2-minute cache is plenty


def compute(project, days):
    """Fetch + build the model, memoised briefly so a page refresh is cheap."""
    key = (project, days)
    now = time.time()
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < _TTL:
            return hit[1]
    j = Jira()
    F = FIELDS.resolve(j)
    st = S.fetch(j, project, F)
    model = build_model(st.issues, st.now, days, project,
                        site=st.site, pages=st.pages, warnings=list(st.warnings))
    payload = json.loads(json.dumps(model, default=str))  # datetime -> str, once
    payload["_meta"] = {"fetched_pages": st.pages,
                        "field_warnings": list(F.warnings()),
                        "generated_epoch": now}
    with _LOCK:
        _CACHE[key] = (now, payload)
    return payload


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", "*")  # dev only; Vite proxies anyway
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api/health":
            return self._send(200, json.dumps({"ok": True}))
        if u.path == "/api/tower":
            q = parse_qs(u.query)
            project = (q.get("project") or ["OPS"])[0]
            try:
                days = int((q.get("days") or ["90"])[0])
            except ValueError:
                days = 90
            if project not in ("OPS", "ITSM"):
                return self._send(400, json.dumps({"error": "unknown project"}))
            try:
                return self._send(200, json.dumps(compute(project, days)))
            except Exception as e:  # surface the real error to the browser, don't hang
                return self._send(500, json.dumps({"error": str(e)[:400]}))
        return self._send(404, json.dumps({"error": "not found"}))

    def log_message(self, *a):
        pass  # quiet; the dev server logs requests


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    require_env()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"control-tower API on http://127.0.0.1:{args.port}  "
          f"(GET /api/tower?project=OPS&days=90)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
