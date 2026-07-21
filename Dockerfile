# Near-real-time backend for the control tower (app/server.py).
#
# This is the OPTIONAL live path: a PaaS runs this image, holds the Jira token in its own
# env, and serves the computed model + records over HTTP. The deployed Pages app, built with
# VITE_DATA_MODE=api + VITE_API_BASE=<this service's url>, then reads live from here instead
# of the baked static JSON. The default Pages deploy does NOT need this — it stays static and
# token-free. See webapp/DEPLOY-BACKEND.md.
#
# The app is pure stdlib (no requirements.txt, no pip install), so the image is tiny and the
# build is just a copy. Only app/ and shared/ are needed — the webapp/ frontend is deployed
# separately to Pages.
FROM python:3.12-slim

WORKDIR /srv
COPY app ./app
COPY shared ./shared

# $HOST/$PORT are read by app.server.main(); 0.0.0.0 so the PaaS can route to it. Most hosts
# inject $PORT themselves — this is the fallback. The Jira secrets are NOT baked in; set
# JIRA_SITE / JIRA_EMAIL / JIRA_TOKEN in the host's environment.
ENV HOST=0.0.0.0 \
    PORT=8000 \
    PYTHONUNBUFFERED=1
EXPOSE 8000

# Read-only against Jira: this process never mutates the instance.
CMD ["python3", "-m", "app.server"]
