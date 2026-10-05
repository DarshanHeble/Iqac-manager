# Backend — Document Router

> **You are working on the Flask backend.** Start here. Read only what your task
> needs; do not read the whole corpus.

## Read this first, always

| File | Why |
|---|---|
| [../glossary.md](../glossary.md) | IQAC, AQAR, worklog, coordinator. You cannot reason about this domain without it. |
| [10-gotchas.md](10-gotchas.md) | The traps that silently break unrelated work. Read before *any* change. |

## Query these instead of reading prose

Prefer these over the `.md` files for anything tabular. They are authoritative and
mechanically generated or verified against source.

| File | Contains | Use for |
|---|---|---|
| [data/routes.json](data/routes.json) | All **39** routes: methods, URL, `file:line`, auth gate, response kind. Also 4 known anomalies. | "What endpoints exist?", "What calls `/x`?", "Is this route protected?" |
| [data/schema.json](data/schema.json) | All **7** tables, columns, types, nullability, keys, enums, indexes, defects. | "What columns exist?", "Is there a FK?", "What are the enum values?" |
| [data/permissions.json](data/permissions.json) | Role model, 4 matching strategies, monkeypatch, session keys, endpoint grants, escalation candidates. | "Who can access X?", "How is role checked?", "What breaks if I touch this?" |
| [data/env-vars.json](data/env-vars.json) | Every env var, `file:line`, default, and failure mode. Plus hardcoded secrets found. | "What env do I need?", "What breaks if it's unset?" |

## Prose, by domain

| # | File | Read when |
|---|---|---|
| 01 | [01-architecture.md](01-architecture.md) | Boot sequence, request lifecycle, submission window logic, report lifecycle. **Start here for orientation.** |
| 02 | [02-routing-contract.md](02-routing-contract.md) | Route groups by role, the JSON response contract, endpoints referenced by templates that do not exist, endpoint groups the Angular app will need. |
| 03 | [03-authentication.md](03-authentication.md) | Sessions, the `psycopg` monkeypatch, role matching, all 41 inline auth checks, password handling. **Highest-risk file in the corpus.** |
| 04 | [04-data-model.md](04-data-model.md) | Narrative schema: per-table read/write sites, index gaps, `db.py` connection behaviour, `migrate_to_postgres.py` analysis. |
| 05 | [05-worklog.md](05-worklog.md) | Employee daily entries, the six categories, entry lifecycle, attachments, JSON-in-TEXT handling, reporting. |
| 06 | [06-coordinator-reports.md](06-coordinator-reports.md) | Coordinator monthly submissions, the four statuses, review workflow, drafts, workshop attachments. |
| 07 | [07-pdf-rendering.md](07-pdf-rendering.md) | ReportLab generators, every PDF route, the four reporting variants, direct-to-cloudinary streaming. |
| 08 | [08-integrations.md](08-integrations.md) | Cloudinary, SMTP/Gmail, Gemini + NVIDIA, APScheduler, Render deployment. |
| 09 | [09-legacy-templates.md](09-legacy-templates.md) | The 22 Jinja templates, layout duplication, what to carry into Angular. |
| 10 | [10-gotchas.md](10-gotchas.md) | Everything that will surprise you. **Never skip.** |
| 11 | [11-security.md](11-security.md) | Findings with severity, evidence, exploit, and fix. |

## Task → file

| Task | Read |
|---|---|
| Add or change an endpoint | `data/routes.json`, [02-routing-contract.md](02-routing-contract.md) |
| Add a column or table | `data/schema.json`, [04-data-model.md](04-data-model.md) §9–12 |
| Change who can see a page | [03-authentication.md](03-authentication.md) §6–7, `data/permissions.json` |
| Add a form field to the worklog | [05-worklog.md](05-worklog.md) |
| Add a field to a coordinator report | [06-coordinator-reports.md](06-coordinator-reports.md) |
| Change a PDF's layout | [07-pdf-rendering.md](07-pdf-rendering.md) |
| Add email or AI summarisation | [08-integrations.md](08-integrations.md) |
| Build an Angular screen | [../frontend/README.md](../frontend/README.md), [../frontend/data/screen-map.json](../frontend/data/screen-map.json) |
| Deploy or debug startup | [01-architecture.md](01-architecture.md) §2, [08-integrations.md](08-integrations.md) §6, `data/env-vars.json` |
| Security review | [11-security.md](11-security.md), `data/permissions.json` → `privilege_escalation_candidates` |
| Anything touching `role` | [03-authentication.md](03-authentication.md) first. Always. |

## Source files

| Path | Lines | Role |
|---|---|---|
| `backend/app.py` | 3,915 | Everything except PDFs: auth, all 35 routes, schema init, integrations, scheduler |
| `backend/routes/pdf.py` | ~1,200 | 4 routes plus every ReportLab generator |
| `backend/db.py` | 37 | Connection factory with SSL fallback |
| `backend/migrate_to_postgres.py` | 365 | One-shot SQLite → PostgreSQL bootstrap |
| `backend/templates/` | 22 files, 12,162 lines | Legacy UI |
| `backend/static/css/theme.css` | — | Design tokens to port to SCSS |
| `backend/requirements.txt` | 9 lines | Runtime deps |

## Conventions used in this corpus

- **`file:line` everywhere.** Always relative to the repo root.
- **`VERIFIED`** means I read the code. Anything else is marked as a hypothesis
  and needs confirmation before you act on it.
- **`⚠` marks a defect**, not a style opinion.
- Numbers (route counts, template counts, line counts) are mechanically checked.
  If you change the code, regenerate the `data/*.json` rather than hand-editing
  counts.