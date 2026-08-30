# FOSI secure scouting trigger

The public dashboard must never contain a GitHub token. This endpoint is the contract for the small serverless bridge that accepts a scouting selection and dispatches `.github/workflows/update-data.yml` with `country`, `competition` and `team` inputs.

## Request
`POST /api/scouting-trigger`

JSON:
```json
{"country":"Poland","competition":"Ekstraklasa","team":"pogon-szczecin"}
```

## Server-side configuration
- `FOSI_GITHUB_TOKEN`: fine-grained token restricted to this repository with Actions write permission.
- `FOSI_REPOSITORY`: `OReinaldo/fosi`.
- Optional `FOSI_ALLOWED_ORIGINS`: the GitHub Pages origin.

The server must validate the three selection fields, reject arbitrary workflow names, and call GitHub's workflow-dispatch endpoint only for `update-data.yml`. Never expose the token to browser JavaScript.

The endpoint should return `202` with `{ "accepted": true }` after GitHub accepts the dispatch.
