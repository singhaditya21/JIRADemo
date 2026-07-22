#!/usr/bin/env python3
"""JSON API for the React control tower — local dev, and the OPTIONAL near-real-time backend.

The React app cannot call Jira directly - Jira Cloud blocks browser-origin requests
(CORS) and the token must never reach the browser. So this holds the token server-side,
fetches once through the same app/ pipeline the static control tower uses, and serves the
computed model as JSON at:

    GET /api/tower?project=OPS&days=90    ->  app.control_tower.build_model(...) as JSON
    GET /api/records?project=ITSM         ->  the record-level dataset (drill-down rows)
    GET /api/health                       ->  {"ok": true}

Both /api/tower and /api/records go through the SAME builders the static bake uses
(app.control_tower.build_model and app.export_pages._record), so the live backend and the
baked Pages files can never disagree about a number or a row. Read-only: no endpoint
mutates Jira.

Two ways to run it:

  1. Local dev:      python3 -m app.server            (127.0.0.1:8000; Vite proxies /api)
  2. Hosted backend: a PaaS (Render/Railway/Fly) runs the Docker image; the deployed Pages
                     app is built with VITE_DATA_MODE=api + VITE_API_BASE=<this URL> and
                     then reads live from here instead of the baked JSON. This is the
                     "near-real-time" mode — see webapp/DEPLOY-BACKEND.md. Host/port come
                     from $HOST/$PORT so the PaaS can inject them; the Jira token stays in
                     the host's env, never in the browser.
"""

import argparse
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from shared.jira_client import Jira, require_env
from shared import fields as FIELDS
from app import store as S
from app.control_tower import build_model
from app.export_pages import _record  # reuse the EXACT bake row-builder — no drift
from app import sfc_export as SFC       # SFC has its own schema (stages/deploys/health)

PROJECTS = ("OPS", "ITSM", "SFC")

_CACHE = {}
_LOCK = threading.Lock()
_TTL = 120       # aggregate model: a 2-minute cache is plenty for a monitoring view
_RECORDS_TTL = 300  # records need a changelog fetch (~6-9s), so cache them a little longer
# One shared client/field-map, resolved lazily once, so we don't re-handshake every request.
_JIRA = None


def _jira():
    global _JIRA
    with _LOCK:
        if _JIRA is None:
            j = Jira()
            _JIRA = (j, FIELDS.resolve(j))
        return _JIRA


def _iso_now():
    # app.sfc_export stamps generated_at as an ISO string; the module bans Date.now-style
    # helpers only in workflow scripts, so a plain UTC isoformat is fine here.
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def compute(project, days):
    """Fetch + build the aggregate model, memoised briefly so a page refresh is cheap."""
    key = ("tower", project, days)
    now = time.time()
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < _TTL:
            return hit[1]
    j, _F = _jira()
    if project == "SFC":
        records, ts = SFC.fetch_sfc_records(j)
        payload = json.loads(json.dumps(SFC.sfc_model(records, days, ts, _iso_now()), default=str))
    else:
        st = S.fetch(j, project, _F)
        model = build_model(st.issues, st.now, days, project,
                            site=st.site, pages=st.pages, warnings=list(st.warnings))
        payload = json.loads(json.dumps(model, default=str))  # datetime -> str, once
        payload["_meta"] = {"fetched_pages": st.pages,
                            "field_warnings": list(_F.warnings()),
                            "generated_epoch": now}
    with _LOCK:
        _CACHE[key] = (now, payload)
    return payload


def compute_records(project):
    """The record-level dataset (with changelog timelines), same rows the bake writes."""
    key = ("records", project)
    now = time.time()
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < _RECORDS_TTL:
            return hit[1]
    j, F = _jira()
    if project == "SFC":
        records, _ts = SFC.fetch_sfc_records(j)
    else:
        st = S.fetch(j, project, F, with_changelog=True)
        records = [_record(i, None) for i in st.issues]
    payload = json.loads(json.dumps(
        {"project": project, "count": len(records),
         "generated_epoch": now, "records": records}, default=str))
    with _LOCK:
        _CACHE[key] = (now, payload)
    return payload


def _cors_origin():
    """Which origin may read this API. A public read-only tower defaults to open; pin
    CORS_ALLOW_ORIGIN=https://<user>.github.io to lock it to the deployed Pages origin."""
    return os.environ.get("CORS_ALLOW_ORIGIN", "*")


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", _cors_origin())
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):  # CORS preflight for a cross-origin (Pages -> backend) call
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", _cors_origin())
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api/health":
            return self._send(200, json.dumps({"ok": True}))
        q = parse_qs(u.query)
        project = (q.get("project") or ["OPS"])[0]
        if u.path in ("/api/tower", "/api/records") and project not in PROJECTS:
            return self._send(400, json.dumps({"error": "unknown project"}))
        if u.path == "/api/tower":
            try:
                days = int((q.get("days") or ["90"])[0])
            except ValueError:
                days = 90
            try:
                return self._send(200, json.dumps(compute(project, days)))
            except Exception as e:  # surface the real error to the browser, don't hang
                return self._send(500, json.dumps({"error": str(e)[:400]}))
        if u.path == "/api/records":
            try:
                return self._send(200, json.dumps(compute_records(project)))
            except Exception as e:
                return self._send(500, json.dumps({"error": str(e)[:400]}))
        return self._send(404, json.dumps({"error": "not found"}))

    def log_message(self, *a):
        pass  # quiet; the dev server logs requests


def main():
    ap = argparse.ArgumentParser()
    # $PORT/$HOST let a PaaS (Render/Railway/Fly) inject the bind address; the Docker image
    # sets HOST=0.0.0.0. Local dev keeps 127.0.0.1 so nothing is exposed off-box by default.
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    ap.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    args = ap.parse_args()
    require_env()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"control-tower API on http://{args.host}:{args.port}  "
          f"(GET /api/tower?project=OPS&days=90 · GET /api/records?project=ITSM)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
