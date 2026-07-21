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
   every ~15 min                                                                        reads /data/*.json
```

If you need genuinely live-on-load data, that requires a tiny always-on backend to hold the
token (Vercel / Cloudflare Worker / Render) that the page calls — which is no longer "hosted
on GitHub Pages". The scheduled-refresh model here is the Pages-native answer.

## One-time setup

### 1. Make the repo publishable on Pages

The repo is currently **private**. Two consequences to decide on first:

- Publishing Pages from a **private** repo requires **GitHub Pro** (Free will not publish).
- The published site is **world-readable** regardless of repo visibility (private Pages with
  viewer access control is Enterprise-only). The baked data is synthetic/seeded — there is no
  real PII in it (verified: no email addresses, analyst names are made up) — so this is low
  risk, but be aware the tower's numbers become public.

For this demo the simplest and recommended choice is **make the repo public** — it gives free
Pages *and* unlimited Actions minutes (see step 4). Your call:

```bash
gh repo edit singhaditya21/JIRADemo --visibility public   # or leave private + GitHub Pro
```

### 2. Turn on Pages with the Actions source

Settings → Pages → **Build and deployment → Source: GitHub Actions**. (The workflow also runs
`actions/configure-pages`, which enables it where permitted.)

### 3. Add the Jira credentials as repo secrets

**You do this yourself** so the token is never handled in chat or committed. Settings →
Secrets and variables → Actions → New repository secret, add three:

| Secret | Value |
|---|---|
| `JIRA_SITE` | `https://singhaditya21.atlassian.net` |
| `JIRA_EMAIL` | your Atlassian account email |
| `JIRA_TOKEN` | an Atlassian API token (id.atlassian.com → API tokens) |

Or from a shell where you paste the token yourself:

```bash
gh secret set JIRA_SITE  --repo singhaditya21/JIRADemo --body "https://singhaditya21.atlassian.net"
gh secret set JIRA_EMAIL --repo singhaditya21/JIRADemo --body "you@example.com"
gh secret set JIRA_TOKEN --repo singhaditya21/JIRADemo               # prompts, not echoed
```

### 4. (Private repo only) mind the Actions minutes

Actions minutes are metered on **private** repos (2000/month free). The default cron is every
15 min; that can exceed the budget on a private repo. Widen it in
[`.github/workflows/pages.yml`](../.github/workflows/pages.yml) (e.g. `0 * * * *` hourly) — the
seeded data changes rarely, so hourly is plenty — or make the repo public for unlimited
minutes.

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
