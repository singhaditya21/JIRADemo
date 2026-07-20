#!/usr/bin/env python3
"""Minimal Jira Cloud REST client. Credentials come from the environment only."""

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request


class Jira:
    def __init__(self):
        self.site = os.environ["JIRA_SITE"].rstrip("/")
        email = os.environ["JIRA_EMAIL"]
        token = os.environ["JIRA_TOKEN"]
        self.auth = base64.b64encode(f"{email}:{token}".encode()).decode()

    def _call(self, method, path, body=None, retries=7):
        url = path if path.startswith("http") else f"{self.site}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Basic {self.auth}")
        req.add_header("Accept", "application/json")
        if data:
            req.add_header("Content-Type", "application/json")

        for attempt in range(retries):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    raw = r.read().decode()
                    return json.loads(raw) if raw.strip() else {}
            except urllib.error.HTTPError as e:
                detail = e.read().decode()[:500]
                # 429/5xx are worth retrying; other 4xx are caller error
                if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                    # Jira returns Retry-After on rate limits; honour it rather than
                    # guessing, otherwise a big seed run half-fails under throttling.
                    wait = e.headers.get("Retry-After") or e.headers.get("X-RateLimit-Reset")
                    try:
                        delay = min(float(wait), 60.0)
                    except (TypeError, ValueError):
                        delay = min(2 ** attempt, 30.0)
                    time.sleep(delay + 0.25 * attempt)
                    continue
                raise RuntimeError(f"{method} {url} -> {e.code}: {detail}") from None
            except urllib.error.URLError as e:
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"{method} {url} -> {e}") from None

    def get(self, p):
        return self._call("GET", p)

    def post(self, p, b):
        return self._call("POST", p, b)

    def put(self, p, b):
        return self._call("PUT", p, b)

    def delete(self, p):
        return self._call("DELETE", p)

    def try_get(self, p, default=None):
        try:
            return self.get(p)
        except RuntimeError:
            return default


def adf(text):
    """Wrap plain text as Atlassian Document Format."""
    paras = [p for p in text.split("\n\n") if p.strip()]
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": p.strip()}]}
            for p in paras
        ],
    }


def log(msg):
    print(msg, flush=True)


def warn(msg):
    """Diagnostics go to stderr so stdout stays a machine-diffable report body.

    Field-ambiguity notices fire or not depending on which instance you point at.
    On stdout they would silently prepend a line to every report, which breaks
    golden-output diffs and any cron capture that treats stdout as the artifact.
    """
    print(msg, file=sys.stderr, flush=True)


def require_env():
    missing = [v for v in ("JIRA_SITE", "JIRA_EMAIL", "JIRA_TOKEN") if not os.environ.get(v)]
    if missing:
        print(f"Missing environment variables: {', '.join(missing)}", file=sys.stderr)
        print("Source your env file first; never hardcode the token.", file=sys.stderr)
        sys.exit(1)
