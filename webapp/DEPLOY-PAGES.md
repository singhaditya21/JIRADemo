# Deploying the control tower to GitHub Pages

The React control tower can be hosted on GitHub Pages, **aligned with Jira and refreshed on
a schedule**. This file is the one-time setup and the honest description of what "real time"
means on a static host.

## Why it is scheduled-refresh, not live-on-load

GitHub Pages serves **static files only** — there is no server to hold the Jira token, and a
browser on a public `github.io` page cannot call Jira Cloud directly anyway (CORS blocks the
cross-origin request, and the API token must never be shipped to the browser). So a truly
live "fetch Jira on every page load" is not securely possible on Pages.

Instead the token stays in CI. A GitHub Action runs [`app/export_pages.py`](../app/export_pages.py)
on a schedule, fetches through the **same** `app/store` + `app/control_tower` pipeline the
local `app.server` uses, bakes the computed model into `webapp/public/data/*.json`, builds
the app, and deploys it. The page reads those static files. It is therefore current to
within the cron interval, auto-updates (a left-open tab re-polls every 5 min and reflects the
newest deploy), and never exposes a secret.

```
 GitHub Action (holds token)                          Browser (no token, no Jira call)
   app/export_pages.py ──► webapp/public/data/*.json ──► built into dist/ ──► Pages ──► React app
   daily (06:00 UTC)                                                                    reads /data/*.json
```

If you need genuinely live-on-load data, that requires a tiny always-on backend to hold the
token (Vercel / Cloudflare Worker / Render) that the page calls — which is no longer "hosted
on GitHub Pages". The scheduled-refresh model here is the Pages-native answer.

## Setup status — one step left

Most of the setup is already done:

- ✅ **Repo is public** (`gh repo edit … --visibility public`) — free Pages + unlimited
  Actions minutes. Note the published site is **world-readable**; the baked data is
  synthetic/seeded with no real PII (verified: no emails, analyst names are made up).
- ✅ **Pages enabled** with the GitHub Actions source (`build_type: workflow`).
- ✅ **`JIRA_SITE` and `JIRA_EMAIL` secrets set** (neither is sensitive).
- ✅ **Refresh is daily** (cron `0 6 * * *`).

**The one remaining step — add the token yourself** (never handled in chat or committed):

```bash
gh secret set JIRA_TOKEN --repo singhaditya21/JIRADemo    # paste when prompted, not echoed
```
Get one at id.atlassian.com → API tokens. Then trigger a build (below); it publishes at the
URL above. Until the token is set, the build stops cleanly at "Missing environment variables:
… JIRA_TOKEN" and nothing deploys.

## Deploy

Push to `main` (the workflow also runs on every push), or trigger it manually:

```bash
gh workflow run "Deploy control tower to GitHub Pages" --repo singhaditya21/JIRADemo
```

The site publishes at:

**https://singhaditya21.github.io/JIRADemo/**

Watch the run under the repo's **Actions** tab; the deploy job prints the URL.

## Local development is unchanged

Nothing above affects local dev. The app still runs live against the backend:

```bash
python3 -m app.server                 # holds the token, http://127.0.0.1:8000
cd webapp && bun run dev              # http://localhost:5173  (proxies /api -> backend)
```

`src/App.jsx` picks the data source automatically: `api` (the backend) in dev, `static` (the
baked JSON) in a production build. Override with `VITE_DATA_MODE`.
