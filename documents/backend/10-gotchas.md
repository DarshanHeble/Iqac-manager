# Backend — Gotchas

**Read this before changing anything.** Every item here will silently produce
wrong behaviour rather than an error.

---

## 1. The `psycopg.Cursor.fetchone` monkeypatch

```
backend/app.py:20-34
```

Globally overrides `fetchone` so the current user's `role` is replaced by
`session['role']`.

- It makes ~20 exact-equality role checks work against a CSV column.
- It is **process-global**, so it affects `routes/pdf.py` and every secondary
  connection.
- It only works because `dict_row` is set on the connection.
- **`fetchall()` is not patched**, so list-shaped role decisions disagree with
  single-row ones.

Full detail: [03-authentication.md](03-authentication.md) §2.

> Changing this is a refactor of the entire authorization model, not a cleanup.

---

## 2. CSV order decides the landing page

```python
session["role"] = available_roles[0]     # app.py:775
```

Reordering the string in `users.role` — e.g. from
`"Secretary, Campus IQAC Coordinator"` to `"Campus IQAC Coordinator, Secretary"`
— silently changes which dashboard a user lands on after login. **Never
normalise or reorder `role` data without checking every consumer.**

Also: `role = NULL` raises `AttributeError` at login (HTTP 500), because
`None.split(",")` is called.

---

## 3. Three different definitions of "secretary"

| Predicate | Sites | Behaviour |
|---|---|---|
| Broad (`LIKE '%secretary%'` on role, designation, **and username**) | `app.py:156-162` | Very loose |
| Narrow (`role IN ('Admin','Secretary')`) | `app.py:3610`, `pdf.py:1000` | **Misses multi-role rows** |
| Exact (`role.lower() != "secretary"`) | `app.py:3770` | Patched value only |

The narrow form silently omits most coordinators from notifications. See
[03-authentication.md](03-authentication.md) §6.

---

## 4. Four different role-matching strategies

exact equality · `is_coordinator()` token membership · `strpos()` **substring**
(18 sites) · notification audience queries.

`strpos(role, 'School IQAC Coordinator') > 0` would match a hypothetical role
`"Not A School IQAC Coordinator"`. And `strpos(...) = 0` is **not** the same as
"the CSV does not contain this role".

---

## 5. `before_request` is not an auth guard

```python
# app.py:700-708
```

It enforces `must_change_password` **only**. It never checks whether anyone is
logged in. All 41 login/role checks are hand-copied inline — there is no
`@login_required` anywhere.

The allowlist is keyed on `request.endpoint`, so it does cover `pdf.*` endpoints,
but any **renamed** endpoint silently drops out of protection.

---

## 6. Logout leaves the session populated

```python
session.pop("username", None)     # app.py:822
```

`role`, `full_name`, `available_roles`, and `must_change_password` survive in the
**signed but unencrypted** client cookie. Use `session.clear()`.

---

## 7. `init_postgres()` runs on every boot and swallows failures

```python
# app.py:645-650
except Exception as e:
    print(f"Warning: Could not initialize database: {e}")
```

A partial schema failure prints a warning and the app **keeps serving**, failing
per request instead. There is no migration framework — schema correctness depends
on import-time DDL succeeding in every worker.

---

## 8. ⚠ `signed_reports` has no unique constraint

`UNIQUE (username, reporting_month)` is **missing**, yet five code paths assume
one row per coordinator per month. Concurrent submissions produce duplicates and
multi-row deletes. **Add it before the Angular submission UI ships.**

---

## 9. `worklog.date` is `VARCHAR(20)`

```sql
WHERE w.date BETWEEN %s AND %s     -- lexicographic, not chronological
```

Correct only because the format is always zero-padded ISO. Two places cast
(`app.py:288-289`, `:876`) and will throw on a malformed legacy row.

---

## 10. `worklog.task` is JSON inside a TEXT column

Category filtering is `LIKE` over serialised JSON (`app.py:1600, 1606, 1620,
1626`), and legacy **plaintext** rows must be tolerated everywhere with a
`try/except json.loads`. Any new reader must do the same or it will crash on
historical data.

Also: the UI category `Others` does **not** equal the stored key
`Others (<specify>)` — matching is by prefix.

---

## 11. `migrate_to_postgres.py` is CWD-dependent and lies about success

```python
LOCAL_SQLITE = "worklog.db"     # migrate_to_postgres.py:28
```

A bare relative path. Run from the wrong directory, it finds nothing, treats
that as a legitimate state, and **prints `✅ MIGRATION COMPLETED SUCCESSFULLY!`
having migrated nothing.**

It also creates only `users` + `worklog` — none of the five other tables — and
with **narrower column widths** than `app.py`. Whichever script runs first wins,
because the `CREATE TABLE`s are `IF NOT EXISTS`.

---

## 12. `load_dotenv(override=True)`

```python
# db.py:7
```

A local `.env` **overrides** the platform-injected `DATABASE_URL`. On Render, a
stray `.env` in the deploy directory silently redirects production to a
developer's database.

---

## 13. SSL fallback swallows the real error

```python
# db.py:21-33
try:    sslmode="require"
except psycopg.OperationalError:   # DNS failure, bad password, missing DB all land here
    try:  sslmode="prefer"
    except psycopg.OperationalError:
           sslmode="disable"       # then tries PLAINTEXT
```

Every connection failure costs two pointless reconnects, then a plaintext
attempt. Nothing is logged, so the real cause is invisible. **No connection
pool** either — one new physical connection per call, 1–3 per request.

---

## 14. Cloudinary config raises at import

```python
# app.py:41-47 — not guarded
```

Any of the three vars missing → `AttributeError` during import → the app does
not start. Cloudinary credentials are mandatory even for unrelated local work.

---

## 15. APScheduler runs in every gunicorn worker

Started at import. N workers → N schedulers → N threads. The **only** thing
preventing N duplicate reminder emails is the `sent_reminders_log` primary key.

And that table is created **inside the job**, not in `init_postgres()`.

---

## 16. `SECRET_KEY` falls back to a public literal

```python
app.secret_key = os.getenv("SECRET_KEY", "your_secret_key")     # app.py:18
```

Unset means every session cookie is forgeable, and the cookie carries
`username` and `role`. That is authentication bypass.

---

## 17. Two endpoints that break the admin URL convention

| Endpoint | Problem |
|---|---|
| `/admin/workshop_attachments` | `/admin/` prefix but **no role check** — session only (`app.py:3701-3702`) |
| `/auto_iqac_reminders` | **No session check at all**, and it sends email (`app.py:2651`) |

---

## 18. `/_session_check` is called but does not exist

`dashboard.html` fetches it on every load → 404, silently ignored. Replace with
`GET /api/me`; do not reproduce.

---

## 19. `/switch_role` mutates the session on a GET

```python
# app.py:798
```

State-changing GET — prefetch, crawler, or a stray link switches the user's
active role. Should be a POST. See
[03-authentication.md](03-authentication.md) §8.

---

## 20. No CSRF anywhere

No CSRF library in `requirements.txt`, no token on any form — including
`/change_password` and every state-changing POST. With cookie-session auth,
cross-site form posts are all authenticated.

---

## 21. `int()` cast at import

```python
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))     # app.py:94
```

A typo in `SMTP_PORT` is an import-time `ValueError` with a misleading traceback.

---

## 22. Hardcoded personal email in source

```
backend/routes/pdf.py:1027
["director.iqac@christuniversity.in", "arnavnarula25@gmail.com"]
```

---

## 23. Submission window is implemented three different ways

`check_submission_window()` is called from the coordinator dashboard, both report
screens, and the PDF routes, with differing grace and rollover logic. **A
coordinator can see the window open on the dashboard and closed on the PDF
download.** Do not reimplement it client-side.

---

## 24. Environment-dependent report variants

`AQAR_COORDINATOR_EMAILS` and `AQAR_COORDINATOR_NAMES` decide whether a report
renders as campus or school, and are paired **by list index**
(`pdf.py:1103` vs `:1141`). Mismatched lengths or ordering produce PDFs with the
wrong signature name.

---

## 25. Rename a table or column and nothing tells you

No FKs anywhere, and `admin_delete_user` (`app.py:2488-2491`) deletes only from
`users`. Orphaned rows accumulate in `worklog`, `signed_reports`,
`report_drafts`, and `workshop_attachment_files` silently.

---

## 26. Divergent delete targets

Inconsistent across handlers: some unauthorized requests get `redirect("/login")`,
others get `redirect("/dashboard")`. Complete inventory:
[03-authentication.md](03-authentication.md) §7.

---

## 27. Three `load_dotenv` + import-order dependencies

`.env` must be loaded **before** `db.py` reads `DATABASE_URL` at import, and
before `app.py` reads `SECRET_KEY`. Changing import order breaks configuration
silently rather than loudly.

---

## 28. Silent `except` blocks hide data loss

| Site | Effect |
|---|---|
| `app.py:2907-2911` | A corrupt draft becomes an **empty form** — the coordinator's work appears lost, no error |
| `app.py:2669-2675` | Reminder-send failures are swallowed, so sends silently stop happening |
| `app.py:20-34` | The monkeypatch swallows its own `RuntimeError` outside a request context, by design |

---

## 29. `.gitignore` excludes `*.db`

So `migrate_to_postgres.py` can only ever run on a developer's machine. There is
no committed schema file — the schema **is** `init_postgres()`.

---

## 30. Three script blocks in five templates, seven in two

`user_report.html` and `secretary_dashboard.html` each contain **7** inline
script blocks; `base.html` has 5. Any shared JS behaviour exists in 3+ copies.
Port logic into services/components; do not copy inline scripts into components.