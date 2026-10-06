# Backend — Security Findings

Findings with severity, evidence, exploit, and fix. **Severity is my assessment,
not a formal audit.** All entries are `VERIFIED` unless marked otherwise.

Severity key: **CRITICAL** (auth bypass / RCE-class) · **HIGH** (data exposure or
privilege escalation in normal operation) · **MEDIUM** (exploitable with
preconditions) · **LOW** (hardening / defence in depth)

---

## Summary

| ID | Severity | Finding | Location |
|---|---|---|---|
| SEC-01 | HIGH | Worklog attachments served unauthenticated | `app.py` static route; `user_report.html:569,570,573` |
| SEC-02 | HIGH | No CSRF protection anywhere | global |
| SEC-03 | HIGH | `forgot_password` allows user enumeration | `app.py:3147+` |
| SEC-04 | HIGH | Unauthenticated endpoint sends email | `app.py:2651` |
| SEC-05 | MEDIUM | `/admin/workshop_attachments` has no role check | `app.py:3701-3702` |
| SEC-06 | MEDIUM | `SECRET_KEY` fallback is a public literal | `app.py:18` |
| SEC-07 | MEDIUM | Temporary passwords emailed in plaintext | `app.py:1756, 1811, 2538` |
| SEC-08 | MEDIUM | SQLite bootstrap script uses fallback credentials | `migrate_to_postgres.py:258-280` |
| SEC-09 | MEDIUM | SSL silently downgraded to plaintext | `db.py:21-33` |
| SEC-10 | MEDIUM | State-changing GET (`/switch_role`) | `app.py:798` |
| SEC-11 | MEDIUM | `delete_attachment` gates on "elevated" role | `app.py:3368-3388` |
| SEC-12 | LOW | Logout leaves session data in the client cookie | `app.py:821-825` |
| SEC-13 | LOW | No rate limiting on login or password reset | global |
| SEC-14 | LOW | Session cookie lacks `Secure` and `SameSite` | `app.py` |
| SEC-15 | LOW | Hardcoded personal email in source | `pdf.py:1027` |
| SEC-16 | LOW | Sensitive values in error pages / weak config defaults | `app.py:645-650` |
| SEC-17 | LOW | Third-party AI receives employee worklog content | `app.py:2225-2340` |
| SEC-18 | LOW | Exception messages rendered to users | `app.py` |

---

## CRITICAL

None confirmed. The absence is not reassurance — the closest candidates are
SEC-06 (forgeable session) and SEC-05 (missing role check); both become critical
in combination with other issues.

---

## HIGH

### SEC-01 — Worklog attachments served unauthenticated

**Location:** Flask's built-in `/static/<path:filename>` route.
Linked from `backend/templates/user_report.html:569, 570, 573`.

**Problem.** Uploaded worklog files are written under
`backend/static/attachments/` and stored in `worklog.attachment` as a relative
path (`app.py:1049-1058`). Flask serves `/static/` with **no session check, no
ownership check, no role check**.

**Exploit.** Anyone who can guess or obtain a filename retrieves any employee's
attachment. Filenames are highly predictable — built from
`secure_filename(username)` + the entry date + a timestamp:

```
username_YYYY-MM-DD_YYYYMMDDHHMMSS.ext
```

Knowing a username (they are not secret, and appear in many UI lists) and
roughly when they worked is enough to enumerate candidates. A timestamp within
one working day is a small search space.

**Impact.** Confidential staff documents, unpublished research, internal
reports, and anything uploaded under `Training and Development`.

**Fix.**
1. Move attachments **out of** `static/` into a non-served directory.
2. Add an authenticated endpoint that re-checks ownership:

   ```
   GET /api/worklog/<id>/attachment
     → session present
     → row belongs to session['username'], OR role in (admin, secretary)
     → FileResponse from the protected directory
   ```
3. Retain the existing ownership + 7-day gates if the entry is still editable.
4. Stop embedding the username in filenames; use the row `id`.

---

### SEC-02 — No CSRF protection anywhere

**Evidence.** No CSRF library in `backend/requirements.txt`. Zero occurrences of
`csrf` in `app.py`.

**Problem.** Authentication is a cookie session. Every state-changing operation
is a plain form POST with no token: `/change_password`, `/add_entry`,
`/`edit_entry`, `/switch_role`, `/admin/add_user`, `/admin/edit_user`,
`/admin/delete_user`, `/iqac_coordinator_report/submit`, `/iqac_report/save_draft`,
`/admin/workshop_attachments/delete`, `/pdf/*` uploads, and the secretary review
actions.

**Exploit.** An attacker hosts a page that auto-submits a form to any of these
endpoints. The victim's browser attaches the session cookie. A one-click link
can switch the victim's active role, change their password, create an admin
account, or delete users.

**Aggravating factor.** `/admin/add_user` creates a user with a known password
(`app.py:1737`) and returns success — so CSRF yields a **persistent backdoor
account**, not just session confusion.

**Fix.**
1. `pip install Flask-WTF`; use `CSRFProtect(app)` with
   `WTF_CSRF_TIME_LIMIT = 3600`.
2. Angular: read the token from a `<meta name="csrf-token">` tag or a
   bootstrap endpoint; send it as `X-CSRFToken` from an interceptor.
3. Set `SESSION_COOKIE_SAMESITE = 'Lax'` at minimum — this is defence in depth,
   not a replacement.
4. Change `/switch_role` to POST (see SEC-10).

---

### SEC-03 — `forgot_password` allows user enumeration

**Location.** `app.py:3147-3168` route area.

**Problem.** The endpoint requires only username **and** email, and returns
distinguishable responses depending on whether the pair matched a row and
whether the user is privileged or self.

**Exploit.** An attacker submits candidate username/email pairs and reads the
outcome to build a list of valid staff accounts, their roles, and their email
addresses. This is valuable reconnaissance for SEC-02.

**Impact.** Enumeration of valid usernames, roles, and email addresses;
confirmation of privileged accounts.

**Fix.**
1. Return an identical response and timing for every input.
2. Add rate limiting per IP and per username.
3. Move recovery to a one-time emailed reset link with an expiry — which also
   fixes SEC-07.

---

### SEC-04 — Unauthenticated endpoint that sends email

**Location.** `app.py:2651`.

**Problem.** This route triggers the IQAC reminder job. It has **no session check
and no role check**. Anyone who can reach the host can invoke it.

**Impact.** Repeated invocation is deduped by `sent_reminders_log`, so it is not
an amplifier. But it is an **unauthenticated side-effecting endpoint** that
depends on a database primary key for its only protection — remove or change
that table's behaviour and it becomes an unauthenticated mail relay.

**Fix.** Do not expose it over HTTP at all. Invoke the job from the scheduler
directly. If an HTTP trigger is genuinely needed, require a secret header
compared with `hmac.compare_digest` and restrict to internal traffic.

**Docker note.** `docker-compose.yml` binds the backend port to `127.0.0.1`
rather than `0.0.0.0` for exactly this reason — publishing on all interfaces
would put this route on the LAN. Do not "fix" a connection problem by widening
that bind. nginx (`:8080`) only proxies `/api`, and since no `/api` routes exist
this route is not reachable through the front door at all.

---

## MEDIUM

### SEC-05 — `/admin/workshop_attachments` has no role check

**Location.** `app.py:3701-3702`.

**Problem.** Despite the `/admin/` prefix, the handler performs **only** a session
check:

```python
if 'username' not in session:
    return redirect('/login')
```

No role predicate follows. This is inconsistent with every other `/admin/*`
route.

**Impact.** Any authenticated employee can reach the coordinator workshop
attachments screen. Depending on what it returns, that may expose other
coordinators' uploads and names.

**Fix.** Add the intended role check — most plausibly `is_coordinator(user['role'])`
— and verify the response payload does not include users' uploads beyond what
the caller should see. Also move the route out of the `/admin/` prefix if it is
a coordinator feature, which removes the misleading naming.

---

### SEC-06 — `SECRET_KEY` fallback is a public literal

**Location.** `app.py:18`.

```python
app.secret_key = os.getenv("SECRET_KEY", "your_secret_key")
```

**Problem.** Unset in the environment, every session cookie is signed with a
value published in the repository.

**Impact.** Anyone who can forge a cookie can impersonate **any user**, because
the cookie carries `username`, `full_name`, `available_roles`, `role`, and
`must_change_password`. This is a full authentication bypass. Combined with SEC-04
and SEC-05, a forged admin session reaches everything.

**Fix.**

```python
app.secret_key = os.environ["SECRET_KEY"]      # fail fast, no default
```

Rotate the key after deploying the fix, which invalidates existing sessions.

---

### SEC-07 — Temporary passwords emailed in plaintext

**Locations.** `app.py:1756-1771`, `app.py:1811-1827`, `app.py:2538-2554`.

**Problem.** The 8-character temporary password (`app.py:1737`) is placed in the
email body. It has no expiry and no single-use marker beyond
`must_change_password`.

**Impact.** The plaintext credential is retained in the recipient's inbox and in
Gmail's servers, indefinitely. On a shared or institutional machine it is
readable by anyone with mailbox access. An 8-character password from a
62-character alphabet is ~47 bits of entropy — weak for a credential that can
persist.

**Fix.** Send a **one-time reset link** with a random token stored hashed in the
database, an expiry of minutes, and single-use enforcement. This replaces
SEC-03's enumeration surface at the same time.

---

### SEC-08 — SQLite bootstrap uses a fallback password

**Location.** `migrate_to_postgres.py:258-280`.

**Problem.** The admin seed has a fallback path that creates an account with a
weak, guessable credential.

**Impact.** Low in production, because `init_postgres()` seeds
`admin` / `admin123` (itself weak, SEC-16) and the migration script is a local
tool. Elevated if anyone ever runs it against a reachable database — it creates
a known-password admin.

**Fix.** Require the seed password from the environment; fail if absent. Never
fall back to a literal.

---

### SEC-09 — SSL silently downgraded to plaintext

**Location.** `db.py:21-33`.

```python
try:    sslmode="require"
except psycopg.OperationalError:
    try:  sslmode="prefer"
    except psycopg.OperationalError:
           sslmode="disable"     # plaintext
```

**Problem.** Three broad `OperationalError` handlers stand between the app and a
**plaintext** database connection, and none of them log.

**Impact.** A DNS failure, wrong password, or absent database all produce the
same three-step downgrade to an unencrypted connection. Credentials and query
results — including **password hashes** — could transit in the clear. Operators
have no signal that this happened.

**Fix.** Remove the `disable` fallback entirely. Log the exception at `ERROR`.
Fail loudly. Enforce `sslmode=verify-full` with a pinned CA for managed
PostgreSQL.

---

### SEC-10 — State-changing GET (`/switch_role`)

**Location.** `app.py:798-815`.

**Problem.** A GET mutates `session['role']`. Browsers prefetch links, crawlers
follow them, and any third-party page can `<img>` the URL.

**Impact.** An attacker can force a victim into a different active role, changing
what they see and — because the monkeypatch rewrites `user['role']` from the
session — potentially what they are authorised to do on subsequent requests.

**Fix.** Convert to `POST`. Add CSRF protection (SEC-02). The Angular app already
plans `POST /api/active-role`.

---

### SEC-11 — `delete_attachment` gates on an ambiguous predicate

**Location.** `app.py:3368-3388` and `app.py:3434-3454`.

**Problem.** The handler allows deletion when the caller is "elevated" **or** the
owner. "Elevated" is derived from role comparisons that, per SEC-05's neighbour
issues, include substring matching.

**Impact.** Depending on the exact predicate, a user may delete attachments
belonging to other coordinators, or orphaned rows may accumulate.

**Fix.** Make the predicate explicit and singular: `role == 'admin'` or
`role == 'secretary'`. Verify that deletion also removes the Cloudinary asset and
the `workshop_attachment_files` rows — currently it appears not to.

---

## LOW

### SEC-12 — Logout leaves session data in the client cookie

`app.py:821-825` pops only `username`. `role`, `full_name`, `available_roles`,
and `must_change_password` persist. The cookie is signed but **not encrypted**,
so those values stay readable on the client. Fix: `session.clear()`.

### SEC-13 — No rate limiting

No limiter on `/login`, `/forgot_password`, `/change_password`, or any POST.
Passwords are brute-forceable at whatever rate the host permits. Fix: Flask-Limiter
with tight per-IP and per-username limits on the auth routes.

### SEC-14 — Session cookie lacks `Secure` and `SameSite`

`app.config` is never assigned, so Flask 3.0 defaults apply:
`HTTPONLY=True`, `SECURE=False`, and **no `SameSite` attribute**. Over plain HTTP
the cookie leaks; without `SameSite` it is sent on cross-site requests, which
makes SEC-02 easier. Fix:

```python
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
)
```

Note: `Secure=True` breaks plain-HTTP local development — gate it on an env var.

### SEC-15 — Hardcoded personal email in source

`pdf.py:1027` includes `arnavnarula25@gmail.com` next to the institutional
address. Personal data committed to a repository. Fix: move to
`AQAR_COORDINATOR_EMAILS` or remove.

### SEC-16 — Weak default credentials and visible internals

- Seed admin password is `admin123` (`app.py:634`) with
  `must_change_password = TRUE`. Safe only because every non-exempt route is
  gated by `before_request` — a single gate bug exposes it.
- `app.py:645-650` prints database initialisation errors to stdout, which on
  Render lands in logs and may surface to clients depending on error handling.

Fix: source the seed password from the environment; never print raw exceptions
in production.

### SEC-17 — Third-party AI receives employee worklog content

`app.py:2225-2340` sends employee task descriptions to an external provider with
no redaction, consent flow, or UI disclosure beyond `?ai=1`. Task text may
include unpublished research, draft publications, and internal initiatives.
Fix: an explicit product decision plus disclosure in the UI; redact identifiers
before submission.

### SEC-18 — Exception messages rendered to users

Several handlers surface raw exception text in flash messages or JSON, leaking
SQL fragments, table names, and file paths. Fix: log server-side with a request
id, return a generic message to the client.

---

## Remediation order

| Priority | Items | Rationale |
|---|---|---|
| 1 — now | SEC-06, SEC-02, SEC-01 | Remove the forgery primitive, the cross-site primitive, and the unauthenticated data path |
| 2 — before the Angular port | SEC-04, SEC-05, SEC-03 | The new client will depend on stable authorization; settle it first |
| 3 — same sprint | SEC-07, SEC-09, SEC-10, SEC-11 | Credential and transport hardening |
| 4 — scheduled | SEC-12 … SEC-18 | Defence in depth |

## What the Angular migration changes

The migration is a good opportunity to close several findings by construction:

- Same-origin `/api` with a session cookie means no CORS, no token storage in
  `localStorage`, and no XSS-to-token-theft path.
- Add CSRF protection at the same time as `POST /api/active-role`.
- Return `401` JSON for XHR instead of `302`, so an expired session cannot be
  mistaken for a redirect.
- Serve attachments through an authorised endpoint — do **not** reproduce
  `/static/<attachment>` links.
- A route guard is **not** a security control. Every check stays server-side.