# IQAC Manager — Documentation Index

Exhaustive architecture corpus for the Flask backend and the Angular 22 frontend.
Written for an AI agent that has not seen this codebase: every claim carries a
`file:line` reference, and facts are separated from recommendations.

---

## Start here

| I want to… | Read |
|---|---|
| Get oriented in 60 seconds | This file → [backend/README.md](backend/README.md) |
| Work on the backend | [backend/README.md](backend/README.md) |
| Work on the frontend | [frontend/README.md](frontend/README.md) |
| Understand the domain | [glossary.md](glossary.md) |
| Load a machine-readable fact | The `data/*.json` files below |
| Avoid a trap | [backend/10-gotchas.md](backend/10-gotchas.md) |

## Structure

```
documents/
├── README.md              this file — top-level router
├── glossary.md            domain vocabulary (IQAC, AQAR, worklog, coordinator)
├── backend/
│   ├── README.md          backend router — start here
│   ├── data/              machine-readable facts, prefer over prose
│   │   ├── routes.json        all 39 routes + auth gates + anomalies
│   │   ├── schema.json        all 7 tables, columns, indexes, defects
│   │   ├── permissions.json   roles, 4 matching strategies, session keys
│   │   └── env-vars.json      every env var + failure modes
│   └── 01..11*.md         prose by domain
├── frontend/
│   ├── README.md          frontend router — start here
│   ├── data/
│   │   └── screen-map.json  22 legacy templates → planned components
│   └── 01..05*.md         prose
└── manifest.json          machine index of every file in this corpus
```

**Prose for narrative, `data/*.json` for facts.** Route tables, schemas,
permissions, and env vars are all available in structured form — query those
rather than parsing markdown tables.

## Machine-readable data

Prefer these over the `.md` files for anything tabular. Authoritative, and
mechanically generated or verified against source.

| File | Records | Notes |
|---|---|---|
| [backend/data/routes.json](backend/data/routes.json) | 39 routes | Generated from the live Flask `app.url_map`. Includes methods, `file:line`, auth gate, response kind, and 4 known anomalies |
| [backend/data/schema.json](backend/data/schema.json) | 7 tables | Columns, types, nullability, keys, enums, missing indexes, per-table defects |
| [backend/data/permissions.json](backend/data/permissions.json) | 4 role strings | Role model, the monkeypatch, all 4 matching strategies, session keys, endpoint grants, escalation candidates |
| [backend/data/env-vars.json](backend/data/env-vars.json) | 15 vars | Each with `file:line`, default, required flag, and what breaks when unset. Plus 2 hardcoded secrets found |
| [frontend/data/screen-map.json](frontend/data/screen-map.json) | 22 templates | Line counts, script-block counts, planned Angular component per screen, shared UI to extract |

## Project at a glance

| | |
|---|---|
| Backend | Flask 3.0.0, PostgreSQL via `psycopg` 3.3.4, ReportLab 4.2.5, Cloudinary, APScheduler 3.10.4 |
| Backend size | `app.py` 3,915 lines · `routes/pdf.py` ~1,200 lines |
| Frontend | Angular 22.1.2, standalone only, Angular Material 22.2.1 + CDK, Chart.js 4.5.1 (no wrapper) |
| Frontend state | Scaffold only — `routes: Routes = []`, no feature screens |
| Backend size | 39 routes, 7 tables, 22 templates (12,162 lines) |
| Auth | Flask signed session cookie + the global `psycopg` fetchone monkeypatch |
| Sessions | Same-origin; dev proxy → Flask `:5000`; production serves the compiled bundle |
| Deployment | Render, `gunicorn --chdir backend app:app` |

## The five things to know

1. **The `psycopg.Cursor.fetchone` monkeypatch** (`app.py:20-34`) globally rewrites
   the current user's `role` to the active role, which is the only reason ~20
   exact-equality role checks work against a comma-separated `VARCHAR`. It is not
   patched for `fetchall()`, so list-shaped role decisions disagree. Read
   [backend/03-authentication.md](backend/03-authentication.md) before touching
   anything role-related.
2. **CSV order is load-bearing.** `session['role'] = available_roles[0]`
   (`app.py:775`) — reordering the string in `users.role` changes which dashboard
   a user lands on.
3. **`signed_reports` has no `UNIQUE (username, reporting_month)`**, yet five code
   paths assume one row per coordinator per month. Add it before building the
   submission UI.
4. **Only 8 of 22 templates extend `base.html`.** The other 14 inline their own
   navbar, sidebar, and `<head>`, so a shell change means 15 file edits.
5. **`/_session_check` is called by `dashboard.html` and does not exist.** The
   request 404s on every employee dashboard load and the failure is swallowed.

## Corrections

Earlier revisions of this corpus stated **23 templates**. The verified count is
**22** (12,162 lines). Counts elsewhere are mechanically checked; regenerate the
`data/*.json` rather than hand-editing.

## Conventions

- **`file:line`** everywhere, relative to the repo root.
- **`VERIFIED`** — I read the code. Anything else is a hypothesis; confirm before
  acting.
- **`⚠`** marks a defect, not a style opinion.
- Descriptions are current-state. Recommendations live in explicit "what to do"
  sections and are never mixed into factual sections.

## Keeping this corpus accurate

- Route table and counts: regenerate [backend/data/routes.json](backend/data/routes.json)
  from `app.url_map`.
- Schema changes: update [backend/data/schema.json](backend/data/schema.json) and
  [backend/04-data-model.md](backend/04-data-model.md) together.
- New screens: add to [frontend/data/screen-map.json](frontend/data/screen-map.json) and
  [frontend/05-migration-plan.md](frontend/05-migration-plan.md).
- New findings: add to [backend/11-security.md](backend/11-security.md) with
  evidence, exploit, and fix.
- New env var: add to [backend/data/env-vars.json](backend/data/env-vars.json) with a
  failure mode.
- Anything that will surprise a future contributor belongs in
  [backend/10-gotchas.md](backend/10-gotchas.md).