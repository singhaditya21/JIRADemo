# Near-real-time backend (optional)

By default the control tower is **static**: a scheduled GitHub Action bakes Jira into JSON and
GitHub Pages serves it. That is robust, free, and token-free in the browser — but the data is
only as fresh as the last bake (daily by default).

If you want the dashboard to read Jira **live on load** ("near-real-time"), stand up the
backend in `app/server.py` on a host that runs Python, and point the Pages app at it. This is
entirely optional; the static path keeps working untouched if you skip it.

Nothing here handles your token in a terminal or in this repo — the token lives only in the
host's own secret store, which you set yourself.

---

## What you get

`app/server.py` serves the **same** numbers the bake produces (it calls the identical
`app.control_tower.build_model` and `app.export_pages._record`), so live and static can never
disagree:

| Endpoint | Returns |
|---|---|
| `GET /api/tower?project=OPS&days=90` | the aggregate model the panels render |
| `GET /api/records?project=ITSM` | the record-level rows the drill-downs use |
| `GET /api/health` | `{"ok": true}` |

It is read-only — no endpoint mutates Jira — and caches briefly (2 min aggregate, 5 min
records) so a page refresh is cheap.

---

## 1. Deploy the backend

The repo ships a `Dockerfile` (pure stdlib, tiny image) and a Render blueprint (`render.yaml`).
Any host that runs a container or Python works — Render, Railway, Fly.io, a VM, etc.

**Render (blueprint):** New → Blueprint → pick this repo. It reads `render.yaml` and prompts
for the three Jira secrets in its dashboard (they are `sync:false`, so they are never
committed). Deploy, then copy the service URL, e.g. `https://control-tower-api.onrender.com`.

**Railway / Fly / other:** build the `Dockerfile` and set these env vars on the service:

| Var | Value |
|---|---|
| `JIRA_SITE` | `https://your-site.atlassian.net` |
| `JIRA_EMAIL` | your Atlassian account email |
| `JIRA_TOKEN` | an Atlassian API token (you create + set it; it stays on the host) |
| `HOST` | `0.0.0.0` (the image already defaults to this) |
| `CORS_ALLOW_ORIGIN` | `https://<you>.github.io` (recommended) or `*` to start |

Most PaaS inject `$PORT`; the server honours it. Verify with
`curl https://<your-backend>/api/health` → `{"ok": true}`.

> **Free tiers sleep.** Render/Fly free instances idle out and cold-start on the next request
> (a few seconds). Fine for a demo; use a paid instance or a keep-warm ping for always-on.

---

## 2. Point the Pages app at it

Rebuild the Pages app in **api mode** with the backend URL. Edit the build step in
[`.github/workflows/pages.yml`](../.github/workflows/pages.yml):

```yaml
      - name: Build the React app
        working-directory: webapp
        env:
          VITE_BASE: /JIRADemo/
          VITE_DATA_MODE: api                 # was: static
          VITE_API_BASE: https://<your-backend>   # add this
        run: |
          bun install --frozen-lockfile
          bun run build
```

Push, let the Action redeploy, and the dashboard now fetches `VITE_API_BASE/api/tower` and
`/api/records` on every load — live from Jira through your backend.

To go back to static, revert those two env values. (You can keep the daily bake step either
way; in api mode it just becomes a warm fallback you are not reading.)

---

## Which mode should I use?

| | Static (default) | Near-real-time |
|---|---|---|
| Freshness | last bake (daily/cron) | live on load |
| Cost | free (Pages only) | a hosted backend |
| Token in browser | never | never |
| Extra moving parts | none | one service to keep up |

Static is the right default for a public demo. Reach for the backend when someone needs the
board to reflect Jira *right now* rather than "as of the last refresh".
