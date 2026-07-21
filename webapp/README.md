# Control tower — React app

An interactive control tower for the L1/L2 tower, in React, aligned with Jira.

It is the moving-parts sibling of the static `app/control_tower.py` page: same numbers
(both come from `app/analytics.py`), but with a project switcher, window selector, theme
toggle, refresh, and sortable tables.

## Two data sources, one UI

The app reads its model from one of two places (chosen automatically, override with
`VITE_DATA_MODE`):

| Mode | Where it runs | Data source |
|---|---|---|
| `api` | **local dev** | the live `app/server.py` backend, which holds the token |
| `static` | **GitHub Pages** | JSON baked at deploy time by `app/export_pages.py` |

Both consume the same `app/analytics.py` model, so they cannot disagree about a figure, and
in neither case does the browser ever hold the Jira token or call Jira directly.

**Hosting on GitHub Pages → [DEPLOY-PAGES.md](DEPLOY-PAGES.md).** A scheduled GitHub Action
bakes the data (token stays in CI) and deploys; the page is current to within the refresh
interval and re-polls itself so a left-open tab reflects each new deploy.

## Why there is a backend (local dev)

A browser cannot call Jira Cloud directly — CORS blocks the origin, and the API token
must never reach the frontend. So a small Python API (`app/server.py`) holds the token,
fetches once through the same `app/store` + `app/analytics` pipeline the static page uses,
and serves the computed model as JSON. The React app fetches that. The two can never
disagree about a figure, and no secret is exposed to the browser.

```
 browser ──/api/tower──►  Vite dev server (5173)  ──proxy──►  app.server (8000)  ──►  Jira
 React UI                 (webapp/)                            (holds the token)
```

## Run it on localhost

Two processes. From the repo root, with your Jira env sourced (`JIRA_SITE`, `JIRA_EMAIL`,
`JIRA_TOKEN`):

```bash
# 1. the API (holds the token, read-only against Jira)
python3 -m app.server                 # http://127.0.0.1:8000

# 2. the React dev server (in another terminal)
cd webapp
bun install                           # first time only
bun run dev                           # http://localhost:5173
```

Open **http://localhost:5173**. Switch OPS/ITSM, change the window, toggle the theme.
`npm` also works if it is healthy on your machine; this repo was built with `bun` because
`npm` was broken here.

## Build a static bundle

```bash
cd webapp && bun run build            # -> webapp/dist/  (still needs app.server for data)
```

`node_modules/` and `dist/` are gitignored — `bun install` and `bun run build` recreate them.
