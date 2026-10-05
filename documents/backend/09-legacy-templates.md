# Backend — Legacy Templates

The 22 Jinja templates being replaced by the Angular app. Read this when
extracting UI requirements; do not port the structure.

- **Directory:** `backend/templates/`
- **Verified:** 22 files, 12,162 lines, 106 `<script>` blocks

Machine-readable inventory with the planned component for each:
[../frontend/data/screen-map.json](../frontend/data/screen-map.json)

---

## 1. ⚠ The layout problem

**Only 8 of 22 templates extend `base.html`:**

```
admin.html                admin_add_user.html      admin_manage_users.html
admin_edit_user.html      admin_report.html        admin_report_ai.html
admin_signed_reports.html admin_settings.html
```

The other **14 are fully self-contained** — each inlines its own `<head>`,
CSS links, navbar, sidebar, and flash-message block. `base.html` (240 lines)
therefore governs only the admin area.

**Consequence:** any shell change (a new nav item, a theme fix, a brand update)
requires editing up to **15 files**. This is the single strongest argument for
the Angular port.

Note the irony: `admin_settings.html` is the smallest file in the corpus (40
lines) *because* it is the one admin screen that correctly uses blocks. That is
the pattern to follow.

---

## 2. What to extract, and what to discard

### Carry into Angular

| Pattern | Where | Angular target |
|---|---|---|
| Role-dependent nav links | 14 templates | `ShellComponent` with role blocks |
| Flash messages | 22 templates | `ToastService` + toast component |
| Theme toggle | 14 templates | `ThemeService` |
| Active-role switcher | 6 templates | `RoleSwitcherComponent` |
| Category select + task textarea | 3 templates | `CategoryTaskFieldComponent` |
| Month picker emitting `YYYY-MM` | 9 templates | `MonthPickerComponent` |
| Validation messages | throughout | Shared validators |

### Discard outright

| Pattern | Why |
|---|---|
| Inline `<style>` blocks in every template | Becomes global SCSS |
| Inline `<script>` blocks (106 of them) | Becomes component logic |
| Jinja `if` loops for rendering tables | Becomes `@for` / `*ngFor` |
| `url_for('static', …)` calls | Becomes Angular asset paths or an API URL |
| Bootstrap 4/5 markup rewritten per screen | Use `ui-*` components over Angular Material |
| Per-screen duplicated `<head>` | One `index.html` |

### ⚠ The two-attribute theme claim is wrong — only one attribute matters

Legacy markup writes **two** attributes from one toggle:

```js
document.documentElement.setAttribute('data-theme', theme);
document.documentElement.setAttribute('data-bs-theme', theme);
```

and persists to `localStorage.theme`.

**Correction:** `data-bs-theme` is dead. No stylesheet in this repo reads it and
no template depends on it — verified across all 22 templates. The templates load
Bootstrap from a CDN for layout and components, but never theme it, so Bootstrap's
own `data-bs-theme` dark-mode support was never actually switched on. An earlier
revision of this document claimed Bootstrap required it; that is incorrect.

`data-theme` is the only attribute that does anything. The Angular app scopes
every `--ui-*` and `--mat-sys-*` token to it, and keeps writing `data-bs-theme`
for compatibility rather than necessity.

Do not reintroduce a dependency on `data-bs-theme` while migrating. See
[../frontend/03-design-system.md](../frontend/03-design-system.md) §2.

---

## 3. ⚠ `dashboard.html` calls a route that does not exist

```js
fetch('/_session_check')
```

```
backend/templates/dashboard.html
```

There is **no `/_session_check` route** in the app. The request 404s on every
employee dashboard load. The template apparently tolerates the failure, which is
why it has gone unnoticed.

- **Do not replicate this call in Angular.**
- The intent was presumably a lightweight session-validity probe. `GET /api/me`
  replaces it properly.

---

## 4. The four `fetch()` calls in the corpus

| File | Target | Method | Status |
|---|---|---|---|
| `dashboard.html` | `/_session_check` | GET | **BROKEN — no route** |
| `iqac_monthly_report.html` | `/iqac_report/save_draft` | POST | OK |
| `iqac_coordinator_report.html` | `/iqac_report/save_draft` | POST | OK |
| `iqac_coordinator_report.html` | `/iqac_coordinator_report/submit` | POST | OK |

Everything else is a normal HTML form POST. So the AJAX surface is tiny: **three
working endpoints**. Most of the Angular API surface will be new, not ported.

Both large coordinator templates (1,424 and 1,442 lines — the two biggest files
in the whole project) each contain only 2 `fetch()` calls, meaning nearly all of
their bulk is inline form markup and validation.

---

## 5. ⚠ Unauthenticated asset links

`user_report.html` links worklog attachments directly:

```
user_report.html:569, 570, 573
    <a href="/static/{{ entry['attachment'] }}">
```

`/static/` is Flask's built-in static route and performs **no session check**.
Any request with a filename returns the file. See
[11-security.md](11-security.md) **SEC-01**.

In Angular, `<a href>` to `/static/...` would work identically and identically
insecurely. **Serve attachments through an authenticated endpoint** that
re-checks ownership, and return a blob or a short-lived signed URL.

---

## 6. The two largest templates

| File | Lines | Component |
|---|---|---|
| `iqac_coordinator_report.html` | 1,442 | `AqarReportPage` |
| `iqac_monthly_report.html` | 1,424 | `MonthlyReportPage` |

At 1,400 lines each with inline CSS and 5 script blocks, these are the hardest
screens to port. Recommended decomposition:

```
pages/
  AqarReportPage            ← route, layout, submit
  components/
    ReportSection           ← one reusable collapsible section
    WorkshopUploader        ← per-index upload + reconcile
    EvidenceLinkList        ← uploaded files
    DraftAutosaveIndicator  ← save_draft status
    ValidationSummary       ← client-side validation display
```

Extracting a single `ReportSection` is the highest-leverage refactor here: both
templates are the same shape with different field sets.

---

## 7. Charts

`admin.html` is the only template referencing chart libraries. Angular already
ships **Chart.js 4.5.1** via `ng2-charts`, so the legacy charting approach is
replaced rather than ported.

Data source: `/admin/analytics_data` (already JSON). Apply the `Others`-prefix
matching rule from [05-worklog.md](05-worklog.md) §1 or the counts will not
match the legacy dashboard.

---

## 8. Extraction order

Recommended order — each step is independently shippable behind a route:

| Step | Templates | Why first |
|---|---|---|
| 1 | `login`, `forgot`, `change_password` | Unauthenticated, lowest coupling, proves the API session story |
| 2 | `base` shell extraction | Enables everything after |
| 3 | `user_add_entry`, `user_view_entries`, `edit` | Self-contained forms, no cross-entity reads |
| 4 | `dashboard`, `user_report` | Employee surface complete |
| 5 | `admin.html`, `admin_manage_users`, `admin_add_user`, `admin_edit_user` | Admin CRUD |
| 6 | `iqac_monthly_report` | First coordinator screen; proves the draft API |
| 7 | `iqac_coordinator_report` | Largest, most complex |
| 8 | `secretary_dashboard`, `iqac_coordinator_dashboard` | Dashboards depend on 5–7 |
| 9 | `admin_signed_reports`, `workshop_attachments`, `admin_report*`, `admin_settings` | Review and reporting |

Keep the Flask routes alive throughout. The Angular app should replace screens
incrementally, not in a single cutover.