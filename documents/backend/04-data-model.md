# Backend — Data Model

Complete PostgreSQL schema. All DDL originates from `init_postgres()`
(`app.py:521-643`) except `sent_reminders_log` (`app.py:2657-2661`).

> **There is no migration framework.** The schema is created by
> `CREATE TABLE IF NOT EXISTS` plus idempotent `ALTER TABLE … ADD COLUMN IF NOT
> EXISTS`, executed at **import time on every process boot** (`app.py:645-650`).
> The whole function is wrapped in a `try/except` that only prints a warning, so
> a partial failure leaves a half-built schema and the app keeps serving.

---

## 1. Table overview

| Table | Rows | Purpose | Unique constraints |
|---|---|---|---|
| `users` | staff and coordinators | Identity, roles, forced password change | `username` |
| `worklog` | daily staff activity | Six-category worklog entries, one per user per date | **none** |
| `signed_reports` | coordinator submissions | Submission lifecycle state machine | **none** ⚠ |
| `workshop_attachment_files` | workshop uploads | Cloudinary refs per coordinator per month | `(username, reporting_month, workshop_index)` |
| `report_drafts` | coordinator drafts | JSON form state, one per type per month | `(username, report_type, reporting_month)` |
| `app_settings` | 2 rows | Submission window configuration | `key` (PK) |
| `sent_reminders_log` | 1 row/day | Reminder idempotency | `sent_date` (PK) |

---

## 2. `users`

```sql
-- app.py:527-540
CREATE TABLE IF NOT EXISTS users (
    id           SERIAL PRIMARY KEY,
    username     VARCHAR(255) UNIQUE NOT NULL,
    password     VARCHAR(255) NOT NULL,
    emp_id       VARCHAR(255),
    email        VARCHAR(255),
    gender       VARCHAR(255),
    designation  VARCHAR(255),
    department   VARCHAR(255),
    role         VARCHAR(255),
    full_name    VARCHAR(255)
);
-- app.py:555-556
ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN DEFAULT FALSE;
```

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | `SERIAL` | no | PK |
| `username` | `VARCHAR(255)` | no | **The only real constraint.** The login identifier and the join key used by every other table. |
| `password` | `VARCHAR(255)` | no | Werkzeug hash only |
| `emp_id` | `VARCHAR(255)` | yes | Employee code, e.g. `CU0001` |
| `email` | `VARCHAR(255)` | yes | **Not unique.** Used as the AQAR-coordinator discriminator (`pdf.py:149-152`) |
| `gender` | `VARCHAR(255)` | yes | |
| `designation` | `VARCHAR(255)` | yes | Matched with `LIKE '%secretary%'` at `app.py:160` |
| `department` | `VARCHAR(255)` | yes | |
| `role` | `VARCHAR(255)` | yes | **CSV**, e.g. `Secretary, Campus IQAC Coordinator`. Indexed. `NULL` → 500 at login. |
| `full_name` | `VARCHAR(255)` | yes | Added by `ALTER`, also in the `CREATE` |
| `must_change_password` | `BOOLEAN` | yes | Default `FALSE`. **Not in the `CREATE`**, only via `ALTER`. |

Boot-time data migration (`app.py:624`):

```sql
UPDATE users SET role='School IQAC Coordinator' WHERE role='IQAC Coordinator'
```

Default seed row (`app.py:629-641`): `admin` / `admin123` / `CU0001` /
`admin@university.edu` / `Male` / `Director, IQAC` / `IQAC` / `Admin` /
`must_change_password = TRUE`.

**Defects:**
- **No foreign keys.** `worklog.username`, `signed_reports.username`,
  `report_drafts.username`, and `workshop_attachment_files.username` are all
  free-text with no reference to `users.username`.
- No `CHECK` constraint on `role`, so any string is accepted.
- `email` is not unique, yet user creation rejects `username OR email`
  collisions in application code (`app.py:1741`) rather than by constraint.

### Read / write sites

| Operation | Sites |
|---|---|
| `SELECT * FROM users WHERE username=%s` (the auth lookup) | `app.py:765, 1090, 1172, 2761, 2839, 3004, 3155, 3171, 3318, 3373, 3439, 3647, 3767`; `pdf.py:105, 681, 753, 1060` |
| Coordinator rosters (`strpos` filters) | `app.py:1467, 1476, 1485, 1508, 2702, 3779, 3794, 3802, 3810, 3818` |
| Employee list (admin/coordinator exclusion) | `app.py:1433, 1856, 2124` |
| Joined with `worklog` for analytics/charts | `app.py:1592, 1602, 1613, 1622` |
| Joined with `signed_reports` | `app.py:1537, 1545, 1893, 3869` |
| Notification audience | `app.py:156-162` (broad), `app.py:3610`, `pdf.py:1000` (narrow) |
| `INSERT` | `app.py:629-641` (seed), `app.py:1748-1750` (add user) |
| `UPDATE` password | `app.py:734, 1804, 2531` |
| `UPDATE` profile | `app.py:2438, 2531` |
| Full listing | `app.py:2382` (`ORDER BY role DESC, username ASC`) |

---

## 3. `worklog`

```sql
-- app.py:543-554
CREATE TABLE IF NOT EXISTS worklog (
    id         SERIAL PRIMARY KEY,
    username   VARCHAR(255) NOT NULL,
    date       VARCHAR(20),
    status     VARCHAR(50),
    category   TEXT,
    task       TEXT,
    attachment TEXT
);
ALTER TABLE worklog ADD COLUMN IF NOT EXISTS attachment TEXT;
```

| Column | Type | Notes |
|---|---|---|
| `id` | `SERIAL` | PK. Used only intra-request (`app.py:1310, 1393, 1407`) |
| `username` | `VARCHAR(255)` | No FK |
| `date` | **`VARCHAR(20)`** | ⚠ **Text, not `DATE`.** Holds `YYYY-MM-DD` ISO strings |
| `status` | `VARCHAR(50)` | `Holiday` / `Leave` / effectively unused otherwise |
| `category` | `TEXT` | Denormalised copy of the primary JSON key |
| `task` | `TEXT` | **A JSON object**, e.g. `{"Documentation and Audits": "…"}` |
| `attachment` | `TEXT` | Relative path `attachments/<name>` |

### The `date` column is text

Every range comparison is a lexicographic string comparison:

```sql
WHERE w.date BETWEEN %s AND %s     -- app.py:1214, 1232, 1246, 1595, 1984
```

This is correct **only because** the stored format is zero-padded ISO. It is
fragile: a legacy row in any other format silently falls outside every range
filter. Two places compensate:

```sql
EXTRACT(YEAR FROM date::date) = %s    -- app.py:288-289
date LIKE %s                          -- app.py:876
```

### `task` holds JSON in a TEXT column

Consequences:

1. **Category filtering is a substring search over serialised JSON:**

   ```python
   # app.py:1600, 1606, 1620, 1626
   like_pattern = '%"Others%' if category_filter == "Others" else f'%"{category_filter}"%'
   ... WHERE w.task::text LIKE %s
   ```

   The value is parameterised (no injection), but `%` or `_` inside the filter
   string would broaden the match. `"Others"` prefix-matches
   `Others (<specify>)` keys by design.

2. **Legacy plaintext must be tolerated.** Several readers branch on whether the
   value parses:

   ```python
   # app.py:883-892, 2252-2241, 252-281 analogues
   try:
       tasks_dict = json.loads(row["task"])
   except (json.JSONDecodeError, TypeError):
       tasks_dict = {row["category"]: row["task"]}
   ```

### The six categories

Derived from the form field mapping at `app.py:1022-1044`. Categories are
`Documentation and Audits`, `Rankings`, `Publications`,
`Training and Development`, `Strategic Initiatives`, `Others (<specify>)`,
plus the two special-cased statuses `Holiday` and `Leave`.

`Leave` entries are filtered out of AI summaries at both serialisation layers
(`app.py:405-406`, `418-419`).

### Attachments

`app.py:1049-1058` writes the file to
`backend/static/attachments/{secure_filename(username)}_{YYYY-MM-DD}_{YYYYMMDDHHMMSS}.{ext}`
and stores the **relative** value `attachments/<name>`.

Allowed extensions (`app.py:656-659`): `pdf, jpg, jpeg, png, doc, docx`.

⚠ **Served unauthenticated.** Templates link directly to
`/static/{{ log['attachment'] }}` (`user_report.html:569, 570, 573`) — no
session, no ownership check. See
[08-security-findings.md](11-security.md), SEC-01.

**Defects:**
- **No uniqueness on `(username, date)`.** Duplicate prevention is an
  application-level check at `app.py:981-985`, racy under concurrency.
- No index beyond `idx_worklog_username` and `idx_worklog_date`.

---

## 4. `signed_reports`

```sql
-- app.py:559-571
CREATE TABLE IF NOT EXISTS signed_reports (
    id                 SERIAL PRIMARY KEY,
    username           VARCHAR(255) NOT NULL,
    reporting_month    VARCHAR(20),
    uploaded_file_path VARCHAR(500),
    uploaded_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status             VARCHAR(20) DEFAULT 'pending'
);
ALTER TABLE signed_reports ADD COLUMN IF NOT EXISTS remarks TEXT;
ALTER TABLE signed_reports ALTER COLUMN status TYPE VARCHAR(50);
ALTER TABLE signed_reports ADD COLUMN IF NOT EXISTS cloudinary_public_id VARCHAR(500);
```

| Column | Type | Notes |
|---|---|---|
| `id` | `SERIAL` | PK |
| `username` | `VARCHAR(255)` | No FK |
| `reporting_month` | `VARCHAR(20)` | `YYYY-MM`. **Never format-validated** at the URL boundary (`app.py:3226`) |
| `uploaded_file_path` | `VARCHAR(500)` | Full `https://` Cloudinary URL, or legacy local path |
| `uploaded_at` | `TIMESTAMP` | Default `CURRENT_TIMESTAMP` |
| `status` | `VARCHAR(50)` | Was `VARCHAR(20)`, widened by `ALTER` at `:570` |
| `remarks` | `TEXT` | Rejection remarks |
| `cloudinary_public_id` | `VARCHAR(500)` | Used for deletion |

Status values in use: `pending_upload`, `uploaded`, `reviewed`,
`corrections_requested`. (The DDL default `'pending'` is never used.)

### ⚠ Missing uniqueness constraint

There is **no `UNIQUE (username, reporting_month)`**. This table drives a state
machine, and several code paths assume one row per user per month:

- `check_submission_window` uses `COUNT(*)` to decide whether the prior month was
  submitted (`app.py:440-510`).
- `pdf.py:127-135` and `pdf.py:1082-1090` read `status` from a single row.
- `app.py:3293-3296` (unlock) issues a `DELETE … WHERE username AND reporting_month`,
  removing **all** matching rows.
- `app.py:3592-3601` reads-then-writes to decide `INSERT` vs `UPDATE`.

Under concurrent requests this yields duplicate rows, ambiguous `fetchone`
results, and multi-row deletes. **Recommend adding
`UNIQUE (username, reporting_month)` before the Angular migration**, since the
new API will make concurrency easier to trigger.

### ⚠ Missing index

No index on `reporting_month`, despite it being the hottest filter
(`app.py:3664`, `1540`, `3864`, `3872`).

### Stale `cloudinary_public_id`

`pdf.py:255-262` resets `status`, `remarks`, and `uploaded_file_path` to their
new values but **does not clear `cloudinary_public_id`**, leaving a public id
pointing at a deleted or superseded asset.

---

## 5. `workshop_attachment_files`

```sql
-- app.py:574-586
CREATE TABLE IF NOT EXISTS workshop_attachment_files (
    id                   SERIAL PRIMARY KEY,
    username             VARCHAR(255) NOT NULL,
    reporting_month      VARCHAR(20) NOT NULL,
    workshop_index       INTEGER NOT NULL,
    filename             VARCHAR(500),
    cloudinary_url       VARCHAR(1000),
    cloudinary_public_id VARCHAR(500),
    uploaded_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (username, reporting_month, workshop_index)
);
```

The one table with a proper composite unique constraint.

`workshop_index` is 1-based at the presentation layer (`workshop_{i+1}`) but
0-based in the Cloudinary `public_id` (`pdf.py:23`, `index + 1`).

### Churn problem

Reconciliation **deletes every row for the month and re-inserts** —
`app.py:3123-3132` and `pdf.py:219-231`. Consequently `id` changes on each
reconciliation, and the unique constraint is exercised on every insert rather
than an upsert.

---

## 6. `report_drafts`

```sql
-- app.py:600-610
CREATE TABLE IF NOT EXISTS report_drafts (
    id              SERIAL PRIMARY KEY,
    username        VARCHAR(255) NOT NULL,
    report_type     VARCHAR(50) NOT NULL,
    reporting_month VARCHAR(20) NOT NULL,
    form_data       TEXT NOT NULL,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (username, report_type, reporting_month)
);
```

`form_data` is the **entire report form serialised as JSON**. Upserted with:

```sql
INSERT INTO report_drafts (...) VALUES (...)
ON CONFLICT (username, report_type, reporting_month)
DO UPDATE SET form_data = EXCLUDED.form_data, updated_at = CURRENT_TIMESTAMP
```

Sites: `app.py:3061-3067` (save draft), `pdf.py:155-160` (monthly download),
`pdf.py:956-961` (AQAR submit), `pdf.py:1109-1114` (AQAR download).

`report_type` is `standard` or `aqar_coordinator`. This is the **only** proper
upsert pattern in the codebase and a good model for the new API.

Reads use `json.loads` with a silent `except` (`app.py:2907-2911`), so a
corrupt draft degrades to an empty form rather than an error.

---

## 7. `app_settings`

```sql
-- app.py:589-597
CREATE TABLE IF NOT EXISTS app_settings (
    key   VARCHAR(100) PRIMARY KEY,
    value VARCHAR(255)
);
INSERT INTO app_settings (key, value) VALUES ('submission_open_day', '1')    ON CONFLICT (key) DO NOTHING;
INSERT INTO app_settings (key, value) VALUES ('submission_close_day', '5')  ON CONFLICT (key) DO NOTHING;
```

A generic key-value store, but only these two keys are ever used. Read by three
divergent implementations — see
[01-system-overview.md](01-architecture.md) §5.

---

## 8. `sent_reminders_log`

```sql
-- app.py:2657-2661 — created lazily inside the scheduler job, NOT in init_postgres()
CREATE TABLE IF NOT EXISTS sent_reminders_log (
    sent_date DATE PRIMARY KEY
);
```

Reminder idempotency: insert once per day, `INSERT` fails on the second attempt
and is swallowed (`app.py:2669-2675`). Because APScheduler starts in **every**
gunicorn worker, this table is the only thing preventing N duplicate sends.

**DDL executed inside a runtime job** is an anti-pattern here — the table is not
created by `init_postgres()`, so a fresh deployment relies on the scheduler
running successfully to create it.

---

## 9. Index summary

```sql
-- app.py:613-621
CREATE INDEX IF NOT EXISTS idx_worklog_username ON worklog(username);
CREATE INDEX IF NOT EXISTS idx_worklog_date     ON worklog(date);
CREATE INDEX IF NOT EXISTS idx_users_role       ON users(role);
```

Only three indexes exist. Missing:

| Table | Missing index | Hot filter sites |
|---|---|---|
| `signed_reports` | `(reporting_month)` | `app.py:1540, 3664, 3864, 3872` |
| `signed_reports` | `(username, reporting_month)` | `app.py:3037, 3286, 3592`; `pdf.py:127, 1082` |
| `report_drafts` | `(username, reporting_month)` | `app.py:2853, 3181, 3553` |
| `workshop_attachment_files` | `(username, reporting_month)` | `app.py:2777, 2892, 3196, 3714` |
| `worklog` | `(username, date)` | `app.py:852, 1104` — the per-user listing query |

---

## 10. `db.py` connection behaviour

```python
# db.py:9  — read ONCE at import
DATABASE_URL = os.getenv("DATABASE_URL")
```

```python
# db.py:21-33 — three-stage SSL fallback
try:    psycopg.connect(db_url, sslmode="require", row_factory=dict_row)
except psycopg.OperationalError:
    try:  psycopg.connect(db_url, sslmode="prefer",  row_factory=dict_row)
    except psycopg.OperationalError:
           psycopg.connect(db_url, sslmode="disable", row_factory=dict_row)
```

- **No connection pool.** A new physical connection per `get_db_connection()`
  call. Handlers open 1–3 per request.
- **`row_factory=dict_row` is set on the connection**, so every `conn.cursor()`
  inherits it. This is what makes the monkeypatch's `isinstance(row, dict)`
  check succeed.
- **`load_dotenv(override=True)`** (`db.py:7`) means a stale local `.env`
  **overrides** the platform-injected `DATABASE_URL` on Render.
- **Silent SSL downgrade.** Any `OperationalError` — DNS failure, bad password,
  missing database — is indistinguishable from "SSL unsupported", causing two
  pointless reconnects before a plaintext attempt. Nothing is logged.
- No `connect_timeout`, no retry, no context manager.

`get_cursor(conn)` (`db.py:35-37`) is a bare alias for `conn.cursor()`.

---

## 11. `migrate_to_postgres.py`

A **bootstrap-era, partially stale** one-shot script (`backend/migrate_to_postgres.py`).

Pipeline (`main()` at `:296-365`): load env → create the database if absent
(`:50-92`, connects to the `postgres` maintenance DB) → create `users` +
`worklog` (`:127-170`) → migrate `users` (`:172-213`, dedupe on `username`) →
migrate `worklog` (`:215-256`, dedupe on `(username, date)`) → seed admin
(`:258-280`) → verify (`:282-294`). Re-runnable; errors are printed and swallowed
so the process always exits 0.

### ⚠ Two problems

**1. It creates a strict subset of the schema.** It knows nothing about
`signed_reports`, `workshop_attachment_files`, `app_settings`, `report_drafts`,
or `sent_reminders_log`. Those come only from `init_postgres()`. Running this
script alone yields a database the app cannot use — and because
`app.py:646-650` swallows `init_postgres()` failures, the app would start and
then fail per request.

Column widths also diverge; `CREATE TABLE IF NOT EXISTS` means whichever script
runs first wins:

| Column | `migrate_to_postgres.py` | `app.py` |
|---|---|---|
| `users.emp_id` | `VARCHAR(50)` (`:137`) | `VARCHAR(255)` (`:532`) |
| `users.gender` | `VARCHAR(20)` (`:139`) | `VARCHAR(255)` (`:534`) |
| `users.role` | `VARCHAR(50)` (`:142`) | `VARCHAR(255)` (`:537`) |

**2. `LOCAL_SQLITE` is a bare relative filename — CWD-dependent.**

```python
# migrate_to_postgres.py:28
LOCAL_SQLITE = "worklog.db"
```

No `__file__`, no env override. Resolution is purely `os.getcwd()`. Worse, a
missing file is treated as a legitimate state rather than an error
(`:339-341` prints "No SQLite database found … Creating fresh PostgreSQL
database…"), so **running it from the wrong directory silently performs no
migration and still prints "✅ MIGRATION COMPLETED SUCCESSFULLY!"**.

`.gitignore` excludes `*.db`, so this can only ever run on a developer's machine.

Recommended fix: `LOCAL_SQLITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "worklog.db")`
plus a hard failure when absent.

---

## 12. Recommendations before the Angular migration

Priority order:

1. **Add `UNIQUE (username, reporting_month)` to `signed_reports`.** The
   lifecycle state machine is not concurrency-safe without it.
2. **Add the missing indexes** in §9, especially `signed_reports(reporting_month)`
   and `worklog(username, date)`.
3. **Add foreign keys** from `username` columns to `users(username)`, or at
   minimum cascade the rename in `app.py:2444` to all four tables.
4. **Convert `worklog.date` to a real `DATE`** with a migration that parses
   existing ISO strings. Removes an entire class of range-filter bugs.
5. **Introduce a proper migration tool** (Alembic) so schema changes stop
   depending on import-time DDL.
6. **Introduce a `user_roles` join table** and retire the monkeypatch. This is
   the prerequisite for sane authorization and for trusting client-side guards.
7. **Fix `admin_delete_user`** to clean up `signed_reports`, `report_drafts`,
   and `workshop_attachment_files` (`app.py:2488-2491`).
8. **Make `db.py` use a connection pool** and stop calling `load_dotenv(override=True)`.