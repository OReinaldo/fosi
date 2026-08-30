# Secure scouting trigger

GitHub Pages is static and must never contain a GitHub token. The production trigger is therefore a tiny serverless endpoint (Cloudflare Worker, Netlify Function, etc.) that receives `{country, competition, team}` and calls GitHub Actions `workflow_dispatch` using a server-side token.

The public dashboard stores only the active scouting session in browser state. The trigger is intentionally separated from the UI so credentials are never exposed.

Required server-side secrets:
- `FOSI_GITHUB_TOKEN`
- `FOSI_REPOSITORY=OReinaldo/fosi`

The endpoint should validate the requested team against `config/competitions.json`, then dispatch the scouting workflow with inputs `country`, `competition`, and `team`.
