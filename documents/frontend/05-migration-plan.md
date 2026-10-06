# Frontend — Migration Plan

Screen-by-screen order for replacing the 22 Jinja templates. Screen inventory:
[data/screen-map.json](data/screen-map.json).

---

## 1. Strategy

Keep the Flask routes alive throughout. Replace screens incrementally behind
Angular routes; no big-bang cutover. Each step below is independently shippable.

Two consequences worth stating up front:

1. **You will need new backend endpoints.** Only three `fetch()` calls exist in
   the whole legacy corpus
   ([../backend/09-legacy-templates.md](../backend/09-legacy-templates.md) §4).
   Almost the entire API surface is new.
2. **Flask currently redirects instead of returning JSON.** Until the
   `X-Requested-With` branch lands
   ([../backend/02-routing-contract.md](../backend/02-routing-contract.md)),
   `sessionInterceptor` has to sniff `content-type`. Land that first — it makes
   every later step predictable.

---

## 2. ✅ Done — the design system

The foundation is in place and no screen depends on it yet, which is the right
order: this is the part that is expensive to change once 22 screens depend on it.

| Delivered | Where |
|---|---|
| Token pipeline, one hex source | `src/styles/_palette.scss` → `_semantic.scss` → `_tokens.scss` |
| Responsive thresholds | `src/styles/_breakpoints.scss` |
| Material M3 theme from the same maps | `src/styles/_material.scss` |
| Global CSS system | `src/styles/_reset.scss`, `_elements.scss`, `_layout.scss`, `_utilities.scss` |
| Theme service + pre-paint script | `core/theme/theme.service.ts`, `index.html` |
| `ui-*` components (10) | `src/app/ui/` |
| App shell (rail + top bar) | `app.html` / `app.scss` |
| Styleguide proving both themes | `/styleguide` |
| Style-discipline tests | `ui/ui.spec.ts`, `core/theme/theme.service.spec.ts` |

Before starting step 1, **look at `/styleguide` in both themes.** If any token or
component looks wrong, that is the moment to change it — every later screen is
built on top of it.

Bootstrap was removed as part of this work. If a ported screen appears to need a
Bootstrap class, it needs a `ui-*` component.

---

## 3. Prerequisites (backend)

Do these before step 1.

| # | Task | Why |
|---|---|---|
| P1 | `GET /api/me` returning the session dict | The shell cannot render without it |
| P2 | `X-Requested-With` → `401` JSON instead of a redirect | Currently XHR gets a 200 + HTML |
| P3 | `POST /api/active-role`, replacing `GET /switch_role` | State-changing GET; needed for `RoleSwitcherComponent` |
| P4 | Flash messages returned in the JSON body | `flash()` cannot reach an XHR client |
| P5 | `UNIQUE (username, reporting_month)` on `signed_reports` | Concurrency safety before submission UI exists |
| P6 | CSRF token endpoint + `X-CSRFToken` acceptance | Add once, not per feature |

---

## 4. Port order

Dependency-ordered: auth first (proves the session story), then the employee
surface, then coordinator, then admin and secretary dashboards.

### Step 1 — Auth

| Legacy | Angular | Needs |
|---|---|---|
| `login.html` (418) | `features/auth/LoginPage` | P1, P4 |
| `forgot.html` (373) | `features/auth/ForgotPasswordPage` | P4 |
| `change_password.html` (409) | `features/auth/ChangePasswordPage` | P1, P4, P6 |

Smallest coupling, lowest privilege. Proves `/api`, the interceptor, and toasts.

Also build `ShellComponent`, `ToastService`, `AuthService`, and `authGuard` here
— everything downstream needs them.

### Step 2 — Employee

| Legacy | Angular | Needs |
|---|---|---|
| `user_add_entry.html` (774) | `features/employee/AddEntryPage` | `CategoryTaskFieldComponent` |
| `user_view_entries.html` (576) | `features/employee/ViewEntriesPage` | ownership + 7-day gates |
| `edit.html` (559) | `features/employee/EditEntryPage` | |
| `dashboard.html` (617) | `features/employee/EmployeeDashboardPage` | do **not** port `/_session_check` |
| `user_report.html` (717) | `features/employee/WorklogReportPage` | **authorised attachment endpoint** |

`user_report.html` is the first place the SEC-01 insecure pattern appears
([../backend/11-security.md](../backend/11-security.md)). Do not link
`/static/<attachment>`; add `GET /api/worklog/<id>/attachment` with an ownership
check.

### Step 3 — Coordinator reports

| Legacy | Angular | Needs |
|---|---|---|
| `iqac_monthly_report.html` (1,424) | `features/coordinator/MonthlyReportPage` | draft autosave API |
| `iqac_coordinator_report.html` (1,442) | `features/coordinator/AqarReportPage` | submission window as an API object |
| `iqac_coordinator_dashboard.html` (793) | `features/coordinator/CoordinatorDashboardPage` | |

The two largest files in the project. Decompose into a reusable
`ReportSection` rather than one giant template — see
[../backend/09-legacy-templates.md](../backend/09-legacy-templates.md) §6.

**Do not recompute the submission window client-side.** Three server
implementations already disagree
([../backend/10-gotchas.md](../backend/10-gotchas.md) §23). Collapse them to one
endpoint returning `{open, reason, grace, month}`.

### Step 4 — Admin

| Legacy | Angular | Needs |
|---|---|---|
| `admin.html` (603) | `features/admin/AdminDashboardPage` | chart decision (§6 of the design-system doc) |
| `admin_manage_users.html` (223) | `features/admin/UserManagementPage` | |
| `admin_add_user.html` (110) | `features/admin/AddUserPage` | P6 |
| `admin_edit_user.html` (128) | `features/admin/EditUserPage` | P6 |
| `admin_settings.html` (40) | `features/admin/SettingsPage` | |

`admin_manage_users.html` shows **raw CSV roles** because `fetchall()` is not
monkeypatched
([../backend/10-gotchas.md](../backend/10-gotchas.md) §1). Decide deliberately
whether to reproduce that or render `available_roles` as a list. Reproducing it
is honest; a comma-joined string is not.

### Step 5 — Review and dashboards

| Legacy | Angular | Needs |
|---|---|---|
| `admin_signed_reports.html` (264) | `features/admin/SignedReportsReviewPage` | approve / request-corrections API |
| `workshop_attachments.html` (389) | `features/coordinator/WorkshopAttachmentsPage` | fix the missing role check first |
| `secretary_dashboard.html` (803) | `features/secretary/SecretaryDashboardPage` | |
| `admin_report.html` (896) | `features/admin/ChairpersonReportPage` | |
| `admin_report_ai.html` (364) | `features/admin/AiSummaryPanelComponent` | AI summary is optional |

`/admin/workshop_attachments` has **no role check** today
([../backend/11-security.md](../backend/11-security.md) SEC-05). Fix the backend
before shipping the screen, or you are reproducing the bug.

---

## 5. API surface to build

Derived from the screens. Grouped, not exhaustive — the authoritative list is
[../backend/data/routes.json](../backend/data/routes.json) plus whatever new
endpoints you add.

| Group | Endpoints | Used by |
|---|---|---|
| Session | `GET /api/me`, `POST /api/active-role` | Shell, all guards |
| Auth | `POST /api/login`, `/api/logout`, `/api/forgot-password`, `/api/change-password` | Step 1 |
| Worklog | `GET|POST /api/worklog`, `GET|PATCH|DELETE /api/worklog/<id>` | Step 2 |
| Attachments | `GET /api/worklog/<id>/attachment` | Step 2 — **authorised, not `/static`** |
| Reports | `GET|POST /api/draft`, `POST /api/reports/submit` | Step 3 |
| Window | `GET /api/submission-window` | Step 3 |
| Workshops | `GET|POST /api/workshops`, `DELETE /api/workshops/<id>` | Step 5 |
| Admin | `GET|POST /api/users`, `PATCH|DELETE /api/users/<id>` | Step 4 |
| Analytics | `GET /api/analytics` | Step 4 — `admin/analytics_data` already returns JSON |
| Review | `GET /api/submissions`, `POST /api/submissions/<id>/approve`, `…/request-corrections` | Step 5 |

Naming: `/api/…` plural nouns, `PATCH` for updates. The legacy app mixes verbs
(`/add_entry`, `/delete_attachment`, `/save_draft`) — do not copy that.

### 5.1 Verified state of the gap (checked 2026-10-05)

Probed all 39 routes against the running Docker stack
(`nginx:8080 → gunicorn:5000 → PostgreSQL`). Three facts, all confirmed by
observation rather than inference:

| Check | Result |
|---|---|
| Routes under `/api` in `app.py` | **0** |
| `jsonify()` calls in `app.py` | **0** — every route renders HTML or redirects |
| `X-Requested-With` read anywhere in `backend/` | **0 matches** |
| HTTP calls made by the Angular app | **0** — no service calls `apiUrl()` yet |
| `/login` on `:5000` | 200, then 302 → `/change_password` (DB-backed, works) |
| Any route on `:8080/api/…` | 404, and it is **Flask's** 404, not nginx's |

That last row is the one that matters for confidence in the plumbing: nginx is
forwarding correctly and Flask is answering. The 404 is the missing route, not a
broken proxy. Bare paths (`/login`, `/styleguide`) are served by nginx from the
Angular bundle; `/api/*` is proxied to Flask.

So the interceptor's documented contract — 401 JSON instead of a 302 to
`/login`, and `X-Requested-With` as the signal — describes a backend that does
not exist yet. The interceptor's `content-type` sniffing is currently the only
thing that would work, and it has never been exercised against a real 401 because
no such response can occur. Both halves of this table are prerequisites for Step
1; do not read the interceptor as evidence that the backend half is done.

---

## 6. Risks

| Risk | Mitigation |
|---|---|
| Session cookies need same-origin | Keep the reverse proxy. Do **not** migrate to JWT |
| `flash()` messages unreachable from XHR | P4 — return messages in JSON |
| XHR gets a 200 HTML login page | P2 — the interceptor sniffs `content-type` meanwhile |
| Role semantics are inconsistent server-side | Treat guards as cosmetic; server stays authoritative |
| Concurrency on `signed_reports` | P5 before step 3 |
| Attachments are unauthenticated | Authorised endpoint from step 2 |
| Bundle budget breached by Chart.js | Lazy load; decide on `ng2-charts` early |
| Two 1,400-line report screens | Shared `ReportSection` component |
| Legacy UI flashes are a UX contract | Audit every flash before cutting over |

---

## 7. Definition of done per screen

- [ ] Component is standalone, lazily loaded, and named per
      [04-conventions.md](04-conventions.md) §2
- [ ] No `any`; API payloads typed in `core/models/`
- [ ] Loading, empty, and error states all handled
- [ ] Server validation errors surface on the form
- [ ] `npm run format && npm run lint && npm run build && npm test` all pass
- [ ] Authorization still enforced server-side, and verified with a direct HTTP
      call as an authenticated user of the **wrong** role
- [ ] No `/static/<attachment>` links
- [ ] Keyboard navigable; labels bound to controls
- [ ] Flash-message parity with the legacy screen confirmed

The role check in the second-to-last item is the one most often skipped. A
hidden button is not an authorization check.