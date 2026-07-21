import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Two ways this app gets its data (see src/App.jsx):
//   - dev:   the Vite dev server proxies /api to the Python backend (app.server), which
//            holds the Jira token. The browser never talks to Jira directly.
//   - Pages: `python3 -m app.export_pages` bakes the model to webapp/public/data/*.json at
//            build time (token stays in CI), and the app fetches those static files.
//
// `base` must match the GitHub Pages path. A project site lives at
// https://<user>.github.io/<repo>/, so CI builds with VITE_BASE=/JIRADemo/. Locally base is
// "/". import.meta.env.BASE_URL reflects this, and the app prefixes data fetches with it.
export default defineConfig({
  base: process.env.VITE_BASE || "/",
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
