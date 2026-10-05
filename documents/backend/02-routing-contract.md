# Backend — API Inventory

All **39 routes**: 35 in `backend/app.py` plus 4 in the `pdf` blueprint
(`backend/routes/pdf.py`). Flask's implicit `static` endpoint is excluded.

This is the implicit contract the Angular rewrite must satisfy. Line numbers are
the authoritative definition sites.

> **Reading this document.** Every route implements its own auth check inline;
> there are no decorators. The "Auth" column below records the check each route
> actually performs, which is **not uniform**. Where the behaviour contradicts
> what the column implies, the notes win.

---

## 1. Role gate vocabulary

| Label | Predicate | Used by |
|---|---|---|
| `PUBLIC` | No session check | 2 routes |
| `SESSION` | `"username" not in session` → redirect `/login` | most |
| `EMPLOYEE` | session, and **excludes** Admin and coordinators | 4 routes |
| `COORD` | `is_coordinator(user["role"])` | 6 routes |
| `ADMIN` | `user["role"].lower() != "admin"` | 8 routes |
| `ADMIN|SEC` | `user["role"].lower() not in ("admin","secretary")` | 7 routes |
| `SECRETARY` | `user["role"].lower() != "secretary"` | 1 route |
| `OWNER` | `session['username'] == row.username` | 5 routes |
| `ADMIN|SEC|OWNER` | elevated, else must own the row | 2 routes |

The `ADMIN`, `COORD`, and `ADMIN|SEC` predicates compare against a **single
role string** — they only work because the `psycopg` monkeypatch rewrites
`row["role"]` to `session["role"]`. See
[03-authentication-and-roles.md](03-authentication.md).

---

## 2. Public routes

| Line | Method | URL | Endpoint | Auth | Behaviour |
|---|---|---|---|---|---|
| 696 | GET | `/` | `home` | `PUBLIC` | Bare `redirect("/login")`. No DB. |
| 821 | GET | `/logout` | `logout` | `SESSION` | Pops **only** `session["username"]`, flashes, redirects `/login`. Leaves `role`, `full_name`, `available_roles`, `must_change_password` in the cookie. |
| 1785 | POST | `/forgot_password` | `forgot_password` | `PUBLIC` | `SELECT * FROM users WHERE username=%s AND email=%s`. On match: generates an 8-char password, sets `must_change_password=TRUE`, emails it. **Distinct flash text for "no such user" vs "email failed"** makes this a user-enumeration oracle. No rate limiting. |
| 2743 | GET | `/auto_iqac_reminders` | `trigger_auto_iqac_reminders` | **`PUBLIC`** | Calls `send_auto_iqac_reminders()` and returns a `text/plain` log string. **Unauthenticated trigger of the reminder email blast.** Intended for external cron, but duplicates the in-process APScheduler job. |

---

## 3. Authentication

| Line | Method | URL | Auth | Behaviour |
|---|---|---|---|---|
| 756 | GET,POST | `/login` | `PUBLIC` | `SELECT * FROM users WHERE username=%s`, `check_password_hash`. On success sets 5 session keys (`:771-776`), flashes a welcome, then redirects to `/change_password` if `must_change_password`, else role-routed (`:782-790`). Generic "Invalid username or password." on failure. |
| 711 | GET,POST | `/change_password` | `SESSION` | POST validates `new_password` ≥ 6 chars and `== confirm_password`, hashes, runs `UPDATE users SET password=%s, must_change_password=FALSE WHERE username=%s`, commits, sets `session["must_change_password"]=False`, then re-dispatches by role. |
| 797 | GET | `/switch_role/<role>` | `SESSION` | Validates `role in session["available_roles"]`, writes `session["role"]`, flashes, re-dispatches. Invalid role → flash + `/dashboard`. **State-changing GET with no CSRF token.** |

---

## 4. Employee routes

`EMPLOYEE` = session present, Admin redirected to `/admin`, coordinators
redirected to `/iqac_dashboard`. The user area actively blocks the other two
roles rather than 403-ing.

| Line | Method | URL | Auth | Template | Behaviour |
|---|---|---|---|---|---|
| 829 | GET | `/dashboard` | `EMPLOYEE` | `dashboard.html` | Loads all own `worklog` rows, computes `total_entries` / `month_entries` / `week_entries`, parses legacy-plaintext vs JSON `task` values (`:883-892`), returns the last 5 by date desc. |
| 916 | GET,POST | `/user_add_entry` | `EMPLOYEE` | `user_add_entry.html` | POST enforces a backdating minimum derived from the submission window (`:949-958`), accepts `%Y-%m-%d` and `%d/%m/%Y` (`:963-970`), rejects future dates and locked months, rejects duplicate `(username, date)` (`:981-985`). Three branches: holiday → `{"Holiday":"Holiday"}`; leave → `{"Leave":"Leave"}`; otherwise maps the six categories into `task_*` form fields, supports `Others (<specify>)` keys, optional attachment upload (`:1050-1058`), then `INSERT INTO worklog (username,date,status,category,task,attachment)` (`:1064-1067`). |
| 1078 | GET | `/user_view_entries` | `EMPLOYEE` | `user_view_entries.html` | Loads own rows, parses tasks, applies `?category_filter=` (prefix-matches `Others (...)` keys, `:1136`), sets `can_edit = age <= 7 days` (`:1152`), sorts newest first. |
| 1162 | GET,POST | `/user_report` | `EMPLOYEE` | `user_report.html` | Three filter modes. `academic_year` `2025-2026` → `May-01`…`Apr-30` (`:1206-1216`); `month` → month bounds (`:1224-1234`); `date` → raw range (`:1242-1248`). Joins `worklog` to `users` for `emp_id`, `designation`, `full_name`. |
| 1301 | GET,POST | `/edit/<int:id>` | `OWNER` + age ≤ 7d | `edit.html` | Scoped read `WHERE id=%s AND username=%s` (`:1310`) and age check (`:1319`). Rebuilds the six-category dict and `UPDATE worklog SET category=%s, task=%s WHERE id=%s` (`:1361`) — the UPDATE is keyed on `id` alone, relying on the earlier ownership check. |
| 1384 | POST | `/delete_entry/<int:id>` | `OWNER` + age ≤ 7d | — | `DELETE FROM worklog WHERE id=%s` after ownership (`:1393`) and recency (`:1402`) checks. 302 + flash. |

---

## 5. Admin routes

| Line | Method | URL | Auth | Template | Behaviour |
|---|---|---|---|---|---|
| 1415 | GET,POST | `/admin` | `ADMIN` | `admin.html` | Largest admin handler. Employee dropdown excluding Admin + coordinators via `strpos` (`:1433`); `total_users` / `total_entries` / `month_entries`; coordinator submission progress for the **previous** month (`:1451-1463`); submitted / draft / pending coordinator name lists (`:1466-1490`); POST `update_window` forces `submission_open_day='1'` and writes `submission_close_day` after `isdigit()` + range validation (`:1493-1505`); Quick Summary `coord_form` reading `status='reviewed'` reports between months (`:1536-1552`); then a worklog aggregate by month / academic year / date range, optionally per user, optionally filtered by `w.task::text LIKE %s` (`:1589-1630`). |
| 1674 | GET,POST | `/admin_settings` | `ADMIN` | `admin_settings.html` | Submission window only. **Leaks the connection** — see [09-conventions-and-gotchas.md](10-gotchas.md). |
| 1709 | GET,POST | `/admin_add_user` | `ADMIN` | `admin_add_user.html` | Reads 8 fields plus a `roles[]` list → `role = ", ".join(roles)` (`:1734-1735`). Generates an 8-char temp password, hashes it, rejects `username OR email` collisions (`:1741`), `INSERT … must_change_password=TRUE`, then emails plaintext credentials (`:1754-1772`). |
| 1838 | GET,POST | `/admin_report` | `ADMIN|SEC` | `admin_report.html` | Two forms discriminated by `form_type` (`:1882`). *coordinator*: dynamically concatenated SQL from validated fragments with a params list (`:1892-1934`), excludes `status='pending_upload'`, filters by month / academic year (`BETWEEN start-05 AND end-04`) / date range truncated via `[:7]`; per row derives `report_type` and loads the matching `report_drafts` row (`:1940-1957`). *worklog*: user + month / academic year / date, with `"All"` variants (`:1979-2046`). |
| 2106 | GET,POST | `/admin_report_ai` | `ADMIN` | `admin_report_ai.html` | Same worklog filtering, then calls an LLM on POST. **Strictly admin-only** — Secretaries are blocked, unlike most sibling routes. Result is **not persisted**; every page load re-bills the model. |
| 2364 | GET | `/admin_manage_users` | `ADMIN` | `admin_manage_users.html` | `SELECT * FROM users ORDER BY role DESC, username ASC`. |
| 2390 | GET,POST | `/admin_edit_user/<int:id>` | `ADMIN` | `admin_edit_user.html` | Conflict check `(username=%s OR email=%s) AND id!=%s` (`:2430`), `UPDATE users` (`:2437-2440`), then **cascades the rename into `worklog`** (`:2444`). Does **not** rename `signed_reports`, `report_drafts`, or `workshop_attachment_files` → orphaned history. |
| 2456 | POST | `/admin_delete_user/<int:id>` | `ADMIN`, username ≠ `"admin"` | — | `DELETE FROM worklog WHERE username=%s` then `DELETE FROM users WHERE id=%s` (`:2488-2491`). Leaves `signed_reports`, `report_drafts`, `workshop_attachment_files` rows behind → orphans. |
| 2501 | POST | `/admin_reset_password/<int:id>` | `ADMIN` | — | 8-char temp password, `must_change_password=TRUE`, emails it in plaintext (`:2528-2555`). |

---

## 6. IQAC coordinator routes

| Line | Method | URL | Auth | Template | Behaviour |
|---|---|---|---|---|---|
| 2752 | GET | `/iqac_dashboard` | `COORD` | `iqac_coordinator_dashboard.html` | Own `signed_reports` ordered `uploaded_at DESC` (`:2770`); a **second** connection fetches `workshop_attachment_files` for the relevant months (`:2777-2790`); computes `check_submission_window` and draft existence; passes `is_aqar_coordinator(user)` to the template. |
| 2830 | GET | `/iqac_monthly_report` | `COORD` | **`iqac_coordinator_report.html` or `iqac_monthly_report.html`** | Chooses template on `is_aqar_coordinator` (`:2915` / `:2928`). Derives `reporting_month` from the window (`:2847`), loads the draft, computes lock state from `signed_reports.status` (`:2860-2867`): `locked` for `pending_upload`/`uploaded`/`reviewed`, `can_unlock` only for `pending_upload`, `rejection_remarks` when `corrections_requested`. Overrides `locked=False` while drafting the current calendar month (`:2878-2887`). `json.loads` on the draft with a silent `except` (`:2907-2911`). |
| 2995 | POST | `/iqac_report/save_draft` | `COORD` | — | **The only properly implemented JSON endpoint.** Accepts JSON *or* form (`:3009-3026`, `[]`-suffixed keys via `getlist`). 400 if `status IN ('pending_upload','uploaded','reviewed')` (`:3037`) or if the window is closed for a non-current month without a correction request (`:3046`). Sorts via `sort_list_fields` (`:3054`), upserts `report_drafts ON CONFLICT (username, report_type, reporting_month) DO UPDATE` (`:3061-3067`), then for non-JSON requests reconciles workshop attachments against Cloudinary (`:3093-3132`). Wrapped in `try/except → rollback / 500` with `finally: conn.close()` (`:3137-3141`). **The one handler with correct close discipline.** |
| 3145 | GET | `/iqac_report/view_raw/<target_username>/<reporting_month>` | `ADMIN|SEC` or self | read-only report template | Cross-coordinator read (`:3165-3168`). Loads the target's `report_type`, draft, and `signed_reports` row; renders read-only with `back_url="/admin_signed_reports"` for elevated roles. Path params are plain strings — `reporting_month` is never format-validated (try/except at `:3226`). |
| 3264 | POST | `/iqac_report/unlock/<reporting_month>` | `COORD`, self only | — | Unlocks only when `status == 'pending_upload'` (`:3286`). Performs `DELETE FROM signed_reports WHERE username=%s AND reporting_month=%s` (`:3293`) — **destroys the row**, losing the link to the Cloudinary object, which is not deleted here. |
| 3507 | POST | `/iqac_upload_signed_report` | `COORD` | — | Multi-step validation: month present (`:3527`); correction-requested bypass (`:3533-3545`); a `report_drafts` row must exist (`:3553-3560`); file present (`:3562`); extension in `{pdf,jpg,jpeg,png}` (`:3567`, helper `_allowed_file` at `:3504`). Uploads to Cloudinary `iqac/signed_reports`, `public_id = f"{secure_filename(username)}_{reporting_month}"`, `resource_type="raw"` (`:3573-3575`); deletes the previous object if `public_id` changed (`:3590`); upserts `status='uploaded'` (`:3592-3601`); then emails every `role IN ('Admin','Secretary')` row (`:3608-3612`). |

---

## 7. Secretary routes

| Line | Method | URL | Auth | Template | Behaviour |
|---|---|---|---|---|---|
| 3760 | GET,POST | `/secretary_dashboard` | `SECRETARY` | `secretary_dashboard.html` | Near-clone of the `/admin` progress section: `total_coordinators`, `submitted_coordinators` + `submission_pct`, submitted/draft/pending name lists, coordinator dropdown, `update_window` POST handler, Quick Summary `coord_form`. |
| 3639 | GET | `/admin_signed_reports` | `ADMIN|SEC` | `admin_signed_reports.html` | Defaults `?month=` to the previous month (`:3655`). `SELECT sr.*, u.designation, u.department, u.full_name FROM signed_reports sr JOIN users u … WHERE sr.reporting_month=%s AND sr.status != 'pending_upload' ORDER BY sr.uploaded_at DESC` (`:3660-3666`); a second connection loads all users' workshop attachments for the month (`:3671-3680`). |
| 3696 | GET | `/workshop_attachments` | **`SESSION` only — no role check** | `workshop_attachments.html` | Lists `workshop_attachment_files` for **every** `username` for `?month=` (default previous month, `:3704-3710`) with **no owner filter** (`:3714-3719`). Despite the `public_` function name, any authenticated user can enumerate other users' workshop attachments. See [08-security-findings.md](11-security.md). |

---

## 8. Review and file-proxy routes

| Line | Method | URL | Auth | Behaviour |
|---|---|---|---|---|
| 3735 | POST | `/admin_review_report/<int:id>` | `ADMIN|SEC` | `UPDATE signed_reports SET status='reviewed' WHERE id=%s` (`:3751`). No existence check, no `uploaded_at` check. |
| 3309 | POST | `/admin_reject_report/<int:id>` | `ADMIN|SEC` | Loads the report, `cloudinary_delete(public_id)` if present (`:3338`), reads free-text `remarks`, then `UPDATE … SET status='corrections_requested', remarks=%s, uploaded_file_path=NULL, uploaded_at=NULL, cloudinary_public_id=NULL` (`:3345-3349`), commits, calls `notify_coordinator_of_rejection` (`:3353`). |
| 3366 | GET | `/view_report/<int:report_id>` | `ADMIN|SEC\|OWNER` | Streams `application/pdf` inline. Requires a non-empty `uploaded_file_path` that is `http(s)://` (`:3399`) — legacy local paths are rejected as "no longer available". Rewrites `/image/upload/` → `/raw/upload/` (`:3406`), fetches via `urllib.request.urlopen(timeout=20)` with a `Mozilla/5.0` UA, streams 64 KiB chunks through `stream_with_context`. The `remote` handle is never closed. |
| 3432 | GET | `/view_attachment/<int:attachment_id>` | `ADMIN|SEC\|OWNER` | Same proxy pattern; MIME from `mimetypes.guess_type` with `application/octet-stream` fallback (`:3472`), `Content-Disposition: inline` using the **raw DB filename** (`:3492`). |

---

## 9. `pdf` blueprint routes

Blueprint `pdf` (`routes/pdf.py:94`), registered with **no URL prefix**, so its
routes are root-relative. All four are POST-only and share the same gate:
session → user lookup → `is_coordinator` → `REPORTLAB_AVAILABLE`.

| Line | Method | URL | Endpoint | Response | Notes |
|---|---|---|---|---|---|
| 96 | POST | `/iqac_monthly_report/download` | `pdf.iqac_monthly_report_download` | `send_file`, `as_attachment=True` | Rejects the **current** calendar month as "drafting phase" (`:120-124`). Rejects locked months (`:127-135`). **Auto-saves the draft on download** (`:154-164`). Reconciles workshop attachments to Cloudinary using two extra connections (`:171-234`). Generates via `_generate_iqac_pdf` (`:246`). Sets `status='pending_upload'` **only after a successful build** (`:255-262`) — the correct ordering. |
| 672 | POST | `/iqac_coordinator_report/preview` | `pdf.iqac_coordinator_report_preview` | `send_file`, `as_attachment=False` | Deliberately **side-effect free**: no window check, no draft write, no `signed_reports` write. Closes the connection before generating (`:718`). Injects the `AQAR_COORDINATOR_NAMES` env list (`:707`). |
| 744 | POST | `/iqac_coordinator_report/submit` | `pdf.iqac_coordinator_report_submit` | JSON `{success}` / `{success:false, error}` | The one-click AQAR path and the **most thorough server-side validation in the codebase** (`:783-904`): `responsibility_areas` required; per-row "any filled ⇒ all required" for Sections 1, 2 and 5; `Related Area (Specify other)` enforcement; non-empty report check. Generates the PDF, uploads the buffer straight to Cloudinary (`:934-944`), upserts draft + `signed_reports` to `uploaded` clearing remarks (`:955-987`), then emails Admins/Secretaries **plus two hardcoded director addresses** (`:1027`). Uses the deferred `from app import send_email` at `:997`. |
| 1051 | POST | `/iqac_coordinator_report/download` | `pdf.iqac_coordinator_report_download` | `send_file`, `as_attachment=True` | Same current-month rejection (`:1075`) and lock check (`:1082`) as route 1. Draft upsert and `pending_upload` write happen **inside the same `try`** (`:1108-1138`), so a failure rolls back both — unlike route 1, which commits the draft first and swallows the error. Does not upload workshop attachments. |

---

## 10. Routes referenced by the frontend that do not exist

| Reference | Source | Reality |
|---|---|---|
| `GET /_session_check` | `templates/dashboard.html:585` | **No such route.** The session-expiry heartbeat 404s on every load. Confirmed absent from the route table and from `app.py`. |

All other client-referenced endpoints resolve to real routes.

---

## 11. The JSON contract, for reference

Only **three** routes return JSON:

| Route | Shape | Status codes |
|---|---|---|
| `POST /iqac_report/save_draft` | `{success: bool, message?}` or `{success: false, error}` | 200 / 400 / 401 / 403 / 500 |
| `POST /iqac_coordinator_report/submit` | `{success: true}` or `{success: false, error}` | 200 only, **including on failure** |
| `GET /auto_iqac_reminders` | `text/plain` log string | 200 |

Everything else is HTML, a redirect, or a streamed file. The Angular migration
must **create** the JSON API; it does not exist yet beyond these three.

---

## 12. Endpoint groups the Angular app will need

Mapping from [../frontend/04-screen-map.md](../frontend/data/screen-map.json). These
do not exist yet.

| Group | New endpoints |
|---|---|
| Session | `GET /api/me`, `POST /api/active-role`, `POST /api/logout` |
| Employee | `GET/POST /api/worklog`, `GET/PATCH/DELETE /api/worklog/<id>` |
| Coordinator | `GET /api/coordinator/dashboard`, `GET/PUT /api/report/draft`, `POST /api/report/download`, `POST /api/report/submit`, `POST /api/signed-report` |
| Admin | `GET/POST /api/admin/users`, `GET /api/admin/analytics`, `GET /api/admin/reports`, `POST /api/admin/signed-reports/<id>/review|reject` |
| Secretary | `GET /api/secretary/dashboard` |
| Files | `GET /api/files/worklog-attachment/<id>`, `GET /api/files/report/<id>`, `GET /api/files/workshop-attachment/<id>` |

> The current `/static/<path>` attachment links (`templates/user_report.html:569`)
> are **unauthenticated**. New endpoints must gate on ownership — see
> [08-security-findings.md](11-security.md), finding SEC-01.