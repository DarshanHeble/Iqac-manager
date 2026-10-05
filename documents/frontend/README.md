# Frontend — Document Router

> **You are working on the Angular app.** Start here. Read only what your task
> needs.

## Read this first, always

| File | Why |
|---|---|
| [../glossary.md](../glossary.md) | IQAC, AQAR, worklog, coordinator. Required domain vocabulary. |
| [../backend/10-gotchas.md](../backend/10-gotchas.md) | The server behaviours that will shape your API design. |

## Query this instead of reading prose

| File | Contains | Use for |
|---|---|---|
| [data/screen-map.json](data/screen-map.json) | All 22 legacy templates → planned components, line counts, script-block counts, shared UI patterns to extract. | "What replaces template X?", "How big is this screen?", "What's shared?" |

## Prose

| # | File | Read when |
|---|---|---|
| 01 | [01-architecture.md](01-architecture.md) | Standalone architecture, current file tree, providers, routing setup, the session-cookie strategy. **Start here for orientation.** |
| 02 | [02-toolchain.md](02-toolchain.md) | Exact dependency versions, Node/npm, scripts, lint/format/test config, build budgets. |
| 03 | [03-design-system.md](03-design-system.md) | Bootstrap + ng-bootstrap setup, the ported theme layer, the two-attribute contract, tokens. |
| 04 | [04-conventions.md](04-conventions.md) | Naming, file layout, standalone rules, component/folder conventions to follow. |
| 05 | [05-migration-plan.md](05-migration-plan.md) | Screen-by-screen port order and the API surface each step needs. |

## Task → file

| Task | Read |
|---|---|
| Add a screen | [01-architecture.md](01-architecture.md), [04-conventions.md](04-conventions.md), [data/screen-map.json](data/screen-map.json) |
| Call a backend endpoint | [01-architecture.md](01-architecture.md) §5, `core/api/api-base-url.ts` |
| Add an API endpoint first | [../backend/02-routing-contract.md](../backend/02-routing-contract.md), [../backend/03-authentication.md](../backend/03-authentication.md) |
| Add a guard | [04-conventions.md](04-conventions.md), [../backend/03-authentication.md](../backend/03-authentication.md) §4 |
| Style something | [03-design-system.md](03-design-system.md) |
| Add a chart | [03-design-system.md](03-design-system.md) §6 |
| Handle an expired session | [01-architecture.md](01-architecture.md) §5 |
| Fix a lint or build error | [02-toolchain.md](02-toolchain.md) |
| Work out what to build next | [05-migration-plan.md](05-migration-plan.md) |

## Commands

```bash
cd frontend
npm start          # dev server on :4200, proxies /api -> localhost:5000
npm run build      # production bundle
npm run lint       # angular-eslint
npm test           # Vitest
npm run format     # Prettier write
```

Backend must be running on `:5000` for the proxy to work:

```bash
cd backend && ../venv/bin/python app.py
```

## Current state

| Item | Status |
|---|---|
| Workspace scaffolded | done |
| Standalone, no `NgModule` | done |
| Providers (`app.config.ts`) | done |
| Session interceptor | done |
| API base token + `apiUrl()` | done |
| Theme layer + static assets | done |
| Routing table | **empty** — `routes: Routes = []` |
| Feature screens | none |
| `GET /api/me` backend endpoint | **does not exist yet** |
| CSRF token plumbing | not started |

`data/screen-map.json` holds the planned component name for every legacy screen.

## Conventions used in this corpus

- **`file:line`** relative to the repo root.
- **`VERIFIED`** means I read the file. Otherwise treat as a hypothesis.
- Versions are from `package.json` and were installed — not aspirational.
- Note: `chart.js` is installed but **`ng2-charts` is not**. Chart work needs a
  decision; see [03-design-system.md](03-design-system.md) §6.