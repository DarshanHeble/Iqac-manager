# Backend — System Overview

Covers `backend/app.py` (3,915 lines), `backend/db.py`, `backend/routes/pdf.py`
(1,469 lines), and the module-level startup sequence.

---

## 1. What the system does

IQAC Manager is an internal portal for the Internal Quality Assurance Cell of
Christ (Deemed to be University). It has three jobs:

1. **Worklog capture** — staff record daily activities under one of six
   categories, optionally attaching a file.
2. **Report compilation** — IQAC coordinators fill a monthly report form whose
   contents are rendered to an official PDF by ReportLab.
3. **Submission and signing workflow** — the generated PDF is signed by hand,
   uploaded back, then reviewed or rejected by an Admin/Secretary, driving an
   email notification loop.

An AI-assisted summary of worklog activity is generated on demand by Gemini or an
NVIDIA-hosted Llama model.

---

## 2. Startup sequence

Executed by `gunicorn --chdir backend app:app` or `python app.py` from within
`backend/`. **Import-time side effects are pervasive** — the module is not a
thin entry point, it is the application.

| Order | `app.py` | Action |
|---|---|---|
| 1 | `:10-15` | `load_dotenv(override=True)` — **overrides real env vars with `.env`** |
| 2 | `:17-18` | `Flask(__name__)`, `secret_key` from env, falling back to the literal `"your_secret_key"` |
| 3 | `:20-34` | **Monkeypatches `psycopg.Cursor.fetchone` globally** |
| 4 | `:36-37` | Imports and registers the `pdf` blueprint |
| 5 | `:40-47` | Configures Cloudinary from env |
| 6 | `:63-68` | Registers the `inline_url` Jinja filter |
| 7 | `:70-74` | Defines `is_coordinator(role_str)` |
| 8 | `:77-85` | Registers Jinja globals (`datetime`, `timedelta`, `ist_now`) and the `now` context processor |
| 9 | `:88` | `from db import get_db_connection, get_cursor` |
| 10 | `:90-94` | Reads SMTP config into module globals |
| 11 | `:110-125` | Defines `send_email` |
| 12 | `:127-133` | Defines `send_reminder_email` (first definition) |
| 13 | `:135-191` | `notify_admins_and_secretaries` |
| 14 | `:193-240` | `notify_coordinator_of_rejection` |
| 15 | `:304-310` | **Redefines `send_reminder_email`** — shadows the copy at `:127` |
| 16 | `:334-354` | Reads AI keys, constructs NVIDIA and Gemini clients at import |
| 17 | `:356-424` | `build_ai_summary_prompt` |
| 18 | `:427-438` | `get_submission_window` |
| 19 | `:440-510` | `check_submission_window` |
| 20 | `:521-643` | **`init_postgres()` — creates the entire schema** |
| 21 | `:645-650` | Calls `init_postgres()` inside `try/except` that only prints a warning |
| 22 | `:652-654` | `os.makedirs` for `static/signed_reports` and `static/attachments` |
| 23 | `:696-3911` | Defines 35 routes and helper functions |
| 24 | `:3899-3910` | **Starts APScheduler** |
| 25 | `:3914-3915` | `if __name__ == "__main__": app.run(debug=True)` — port 5000 |

### Consequences worth knowing

- **Schema creation is not optional and not transactional.** `init_postgres()`
  runs on every worker boot. A partial failure leaves a half-created schema and
  the app continues serving (`app.py:646-650` swallows the exception).
- **APScheduler starts in every gunicorn worker**, not just one. With multiple
  workers, the daily reminder job is registered N times. The `sent_reminders_log`
  table is the only thing preventing duplicate sends (`app.py:2657-2675`).
- **The dev server hard-codes `debug=True`.** Never reachable in production
  because the Procfile uses gunicorn.

### Running it under Docker

`./setup.sh` then `./run.sh` at the repo root brings up PostgreSQL, gunicorn
and nginx. Three things about that setup are worth recording here because they
are consequences of the startup sequence above:

- **`--workers 1` is a requirement, not a default.** `backend/Dockerfile` pins
  it for the APScheduler reason above, and `--preload` is deliberately *not*
  used. Scale with `--threads` instead. Verified: one worker process, and
  `scheduler.get_jobs()` returns exactly one `iqac_report_reminder`.
- **The healthcheck opens a real DB connection.** An earlier version only
  requested `GET /login`, which renders a template and never queries the
  database — so a backend with a broken `DATABASE_URL` still reported healthy
  while `POST /login` returned 500. It now calls `db.get_db_connection()`
  directly, which is the same path every route uses.
- **`load_dotenv(override=True)` decides who wins.** `db.py:7` and `app.py:11`
  both override already-set environment variables, so a `.env` file *inside*
  the container silently beats whatever Compose injects. Both Dockerfiles
  exclude `.env` via `.dockerignore` so the injected values are the only source.
  `DATABASE_URL` is read once at import, so changing it needs a restart.

One deployment trap: `POSTGRES_PASSWORD` in `.env` is only used the first time
the volume is created. Postgres stores the password it was initialised with, so
editing it afterwards breaks authentication without changing anything on the
database side — the backend then 500s on every database-backed request.

---

## 3. Request lifecycle

1. Browser issues the request.
2. `@app.before_request` → `enforce_password_change()` (`app.py:700-708`).
   **This is not an auth guard.** It only forces a password change when
   `session['must_change_password']` is truthy. Endpoints
   `login`, `logout`, `change_password`, `static` are exempt.
3. The view function runs and **implements its own authentication check**, since
   no decorator exists. 37 separate `if "username" not in session` guards live in
   `app.py`.
4. Any `SELECT * FROM users WHERE username=%s` returning a single row passes
   through the monkeypatched `fetchone`, which overwrites `row["role"]` with
   `session["role"]` for the current user. All exact-string role comparisons then
   resolve against the **active** role.
5. The handler opens one or more PostgreSQL connections, queries, closes, and
   either renders a Jinja template or returns JSON / a streamed file.

---

## 4. Roles

Five roles exist, stored as a comma-separated string in `users.role`:

| Role | Lands on | Notes |
|---|---|---|
| `Employee` (or any unrecognised value) | `/dashboard` | Default bucket |
| `School IQAC Coordinator` | `/iqac_dashboard` | Recognised by `is_coordinator` |
| `Campus IQAC Coordinator` | `/iqac_dashboard` | Recognised by `is_coordinator` |
| `Secretary` | `/secretary_dashboard` | |
| `Admin` | `/admin` | |

A user may hold several, e.g. `Secretary, Campus IQAC Coordinator`. The **first
entry in the CSV determines the landing page at login** (`app.py:775`). Users
switch the active role at runtime via `GET /switch_role/<role>`, which writes
`session["role"]`; the monkeypatch makes every downstream check honour it.

Matching is inconsistent by design history:

- `is_coordinator()` (`app.py:70-74`) splits on commas and requires exact
  lowercase token membership. Duplicated verbatim at `routes/pdf.py:16-20`.
- Admin panels use `strpos(role, 'School IQAC Coordinator') > 0` substring
  matching (18 sites, e.g. `app.py:1433`, `1453`, `2703`, `3818`).
- Most gates use `user["role"].lower() != "admin"`, which only works because the
  monkeypatch replaced the CSV with a single active role.

> **Critical:** `app.py:28-30` — the monkeypatch reads `session["role"]`. If
> `session["role"]` is absent, the DB CSV is used unchanged and every exact-match
> gate fails. `session["role"]` is set at login (`app.py:775`) and by role switch
> (`app.py:804`).

A boot-time data migration normalises a legacy role name
(`app.py:624`): `UPDATE users SET role='School IQAC Coordinator' WHERE role='IQAC Coordinator'`.

---

## 5. Submission window

The monthly submission window is configured in `app_settings`:

| Key | Default | Set at |
|---|---|---|
| `submission_open_day` | `'1'` | `app.py:596-597` (seed) |
| `submission_close_day` | `'5'` | Seeded `'5'`; **read with default `10`** |

Editable by Admin at `POST /admin_settings`, which forces `open_day` to `'1'` and
validates `close_day` as `1..31` (`app.py:1694-1699`).

**Three divergent implementations compute "is the window open".**

| Implementation | Location | Default close | Logic |
|---|---|---|---|
| `get_submission_window` | `app.py:427-438` | `10` | Pure read of the two settings |
| `check_submission_window` | `app.py:440-510` | `10` | Adds day-window + prior-submission checks |
| `_check_submission_window` | `routes/pdf.py:598-669` | `5` | Duplicate of the above with a **different default** and a hardcoded `if current_day <= 9` |

All three self-gate on `open_day <= today.day <= close_day`, target the
**previous** month, and are bypassed when a report is in
`corrections_requested` status. The defaults only diverge if the settings table
read fails, but the two layers disagree about the closed window.

---

## 6. Signed-report lifecycle

```
                    report_drafts (JSON form state)
                            │
              [download]    │  generates PDF, then sets
                            ▼
                   status = pending_upload  ◄──────── LOCK POINT
                            │
              [upload signed copy]
                            ▼
                     status = uploaded
                            │
        ┌───────────────────┴───────────────────┐
        ▼                                       ▼
  status = reviewed                  status = corrections_requested
  (terminal)                        (reopens; deletes Cloudinary object,
                                       clears path/public_id/remarks)
        │
        └── [unlock] allowed only from pending_upload;
             DELETEs the signed_reports row entirely
```

Status values: `pending_upload`, `uploaded`, `reviewed`, `corrections_requested`.

`signed_reports` has **no unique constraint** on `(username, reporting_month)`
(see [04-data-model.md](04-data-model.md)), so this state machine is not
protected against duplicate rows under concurrency.

See [06-integrations.md](08-integrations.md) for the Cloudinary and email
side-effects at each transition, and [02-api-inventory.md](02-routing-contract.md)
for the exact endpoints.

---

## 7. Reporting variants

Coordinators fill one of two report forms, discriminated **by email address**,
not by role:

```python
# routes/pdf.py:149-152
aqar_emails = [e.strip().lower() for e in os.getenv("AQAR_COORDINATOR_EMAILS", "").split(",") if e.strip()]
email = (user.get("email") or "").strip().lower()
report_type = "aqar_coordinator" if email in aqar_emails else "standard"
```

| | Standard (`report_type='standard'`) | AQAR (`report_type='aqar_coordinator'`) |
|---|---|---|
| Template | `iqac_monthly_report.html` | `iqac_coordinator_report.html` |
| Generator | `_generate_iqac_pdf` (`pdf.py:284-591`) | `_generate_aqar_coordinator_pdf` (`pdf.py:1178-1469`) |
| Sections | I(a) Meetings, I(b) Workshops, II Plans | 1 Activities, 2 Meetings, 3 Achievements, 4 Challenges, 5 Action Plan |
| Data tables | 2 | 3 |
| Server-side validation | none | full row-completeness (see [05-pdf-generation.md](07-pdf-rendering.md)) |
| Submission | manual: generate PDF → sign → upload | one-click: generate → Cloudinary → `uploaded` |

`report_drafts` is keyed `(username, report_type, reporting_month)`, so a
coordinator can hold one draft of each type per month simultaneously.

---

## 8. Reporting paths this document does not cover

- Every route → [02-api-inventory.md](02-routing-contract.md)
- Session, role, and the monkeypatch → [03-authentication-and-roles.md](03-authentication.md)
- Tables, columns, indexes → [04-data-model.md](04-data-model.md)
- ReportLab layout details → [05-pdf-generation.md](07-pdf-rendering.md)
- Email / AI / Cloudinary / scheduler → [06-integrations.md](08-integrations.md)
- The Jinja2 templates → [07-legacy-frontend.md](09-legacy-templates.md)
- Verified vulnerabilities → [08-security-findings.md](11-security.md)