# Backend — External Integrations

Five third-party dependencies plus the scheduler. Full env var contract with
failure modes: [data/env-vars.json](data/env-vars.json).

| Dependency | Version | Where | Purpose |
|---|---|---|---|
| Cloudinary | `1.45.0` | `app.py:41-47` | Report and attachment storage |
| Google SMTP | via stdlib | `app.py:91-94`, `:138` | Temporary passwords, reminders |
| google-genai | `2.10.0` | `app.py:2225-2340` | AI summaries |
| openai | `2.44.0` | `app.py` | Secondary AI provider (NVIDIA-compatible) |
| APScheduler | `3.10.4` | `app.py` | Daily reminder job |

---

## 1. Cloudinary — configured at import, unguarded

```python
# app.py:41-47
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
)
```

**This is not wrapped in `try/except`.** If any of the three variables is unset,
`cloudinary.config()` raises `AttributeError` during import and **the app fails
to start**. Cloudinary credentials are therefore mandatory even for local work
that never touches uploads.

The API secret is only needed server-side, which is satisfied — it is never sent
to a client.

### Immutability assumption

Cloudinary public ids are built deterministically from
`(username, reporting_month, index)` (`pdf.py:23`). That makes ids predictable
and stable across reconciliation, but it also means a user who learns the scheme
could guess another user's public id. Public ids are effectively URLs, so
treat Cloudinary as a public asset store: **do not treat it as an access-control
boundary.** Authorization must be enforced by the route, not by id secrecy.

---

## 2. SMTP — temporary passwords sent in plaintext

| Variable | Default | Site |
|---|---|---|
| `SMTP_SERVER` | `smtp.gmail.com` | `app.py:93` |
| `SMTP_PORT` | `587` (`int()` cast) | `app.py:94` |
| `SMTP_EMAIL` | — | `app.py:91` |
| `SMTP_PASSWORD` | — | `app.py:92` (Gmail **app password**) |
| `SENDER_EMAIL` | fallback sender | `app.py:138` |

Sends occur at:

| Trigger | Site | Contains |
|---|---|---|
| User created by admin | `app.py:1756-1771` | 8-char temp password |
| User resets own password | `app.py:1811-1827` | 8-char temp password |
| Admin resets a user's password | `app.py:2538-2554` | 8-char temp password |

### ⚠ Plaintext credentials by email

Temporary passwords are emailed in the message body, not via a reset link. That
means:

- Gmail sees the plaintext password.
- It lands in the recipient's inbox permanently, including on shared machines.
- There is no token, no expiry, and no single-use marker.
- `/forgot_password` requires only username + email with no token — see
  [11-security.md](11-security.md).

A one-time reset link would be strictly better and is the natural thing to build
with the new API.

### ⚠ `SMTP_PORT` is cast with `int()` at import

```python
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))     # app.py:94
```

A malformed value raises `ValueError` **during import**, which is an
unhelpful failure mode for a config typo. Cast lazily or validate with a default.

### ⚠ Missing credentials are not detected early

`sender.py` / the mail helper resolves `SMTP_EMAIL` or `SENDER_EMAIL` at
`app.py:138`. If both are unset the send fails at call time, deep inside a user
creation request — so an admin sees a 500 and the user **may already have been
inserted** before the failure. Validate mail config at boot.

---

## 3. Reminder email and the scheduler

```python
# app.py:2651
@app.route("/auto_iqac_reminders")
```

### ⚠ Unauthenticated endpoint that sends email

This route has **no session check and no role check**. Anyone who can reach the
host can trigger the reminder job. It is idempotent via `sent_reminders_log`,
so it will not spam repeatedly — but it is an unauthenticated side-effecting
endpoint. See [11-security.md](11-security.md) **SEC-04**.

### ⚠ APScheduler runs in every gunicorn worker

```python
# app.py
scheduler = BackgroundScheduler()
scheduler.add_job(...)
scheduler.start()
```

This runs **at import**, so with `gunicorn` and N workers there are N schedulers.
`BackgroundScheduler` defaults to a `ThreadPoolExecutor` per scheduler
instance — so N duplicated schedulers, N duplicated threads.

The only thing preventing N duplicate emails is the
`sent_reminders_log` primary key (`app.py:2657-2661`): the second insert raises
and is swallowed (`app.py:2669-2675`).

**This is fragile.** Two changes would make it robust:

1. Guard scheduler startup so only one worker starts it (e.g. check
   `os.environ.get('WORKER_ID') == '0'`, or detect a leader lock).
2. Create `sent_reminders_log` in `init_postgres()` rather than inside the job —
   see [04-data-model.md](04-data-model.md) §8.

### Hardcoded recipients

The reminder audience is hardcoded, not configured:

```python
# app.py
recipient_emails = [admin@university.edu, iqac@…, principal@…, …]
```

Move this to `app_settings` or an env var so it can be changed without a deploy.

---

## 4. AI summaries — Gemini with an NVIDIA fallback

```python
# app.py:335-336
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
```

Used at `app.py:2225-2340` for `/chairperson_report?ai=1`.

### Failure is graceful

If neither key is available the summarisation step is **skipped**, and the page
renders without a summary. This is the right behaviour — keep it in the new
implementation, and treat a missing summary as normal rather than an error.

### ⚠ `openai` is imported for NVIDIA

Using the OpenAI SDK to call NVIDIA's OpenAI-compatible endpoint is legitimate,
but it means:

- `NVIDIA_MODEL_NAME` (`app.py:2275`, default `meta/llama-3.1-8b-instruct`) must
  be set for the fallback to work.
- Both SDKs are installed and both are load-time imports, so a broken
  installation of either can affect startup. Verify imports are lazy where
  possible.

### ⚠ Worklog content is sent to a third party

Employee task descriptions — potentially including unpublished research,
publication drafts, and internal initiative names — are sent to an external AI
provider. There is no redaction, no consent flow, and no indication in the UI
that this happens beyond the `?ai=1` flag.

Worth an explicit product decision before this reaches real users.

---

## 5. `SECRET_KEY` has an unsafe default

```python
# app.py:18
app.secret_key = os.getenv("SECRET_KEY", "your_secret_key")
```

If unset, **every session cookie in the deployment is forgeable** by anyone who
knows this literal — which is public in the source. The cookie carries
`username`, `role`, and `must_change_password`, so forging one is equivalent to
full authentication bypass for any username.

**Fail fast instead:** `app.secret_key = os.environ["SECRET_KEY"]`.

---

## 6. Deployment

```bash
# Procfile
web: gunicorn --chdir backend app:app
```

- `--chdir backend` is **required** because the backend uses flat module imports
  (`import db`, `from routes.pdf import …`). Without it, imports resolve against
  the repo root and fail.
- See `backend/README.md` for the full run/deploy procedure.

### Startup ordering matters

```
1. load_dotenv()                    db.py:7 (override=True)
2. psycopg monkeypatch installed    app.py:20-34
3. cloudinary.config()              app.py:41-47     ← RAISES if unset
4. app.secret_key                   app.py:18
5. smtp constants + int() cast      app.py:91-94     ← RAISES if SMTP_PORT malformed
6. blueprint registration           app.py
7. scheduler start                  import time      ← N workers = N schedulers
8. init_postgres()                  app.py:645-650   ← SWALLOWS ERRORS
```

Two failure modes are silent: Cloudinary and `SMTP_PORT` raise (visible crash),
while `init_postgres()` prints a warning and continues (invisible corruption).

### ⚠ `load_dotenv(override=True)`

```python
# db.py:7
load_dotenv(override=True)
```

`override=True` means a **local `.env` takes precedence over the
platform-injected value**. If a `.env` file is committed or left in a deploy
directory, production silently uses the developer's database. Remove the
override, or ensure `.env` is absent from the deploy image.

---

## 7. Checklist before production

- [ ] `SECRET_KEY` set and unique — and remove the `"your_secret_key"` fallback.
- [ ] `DATABASE_URL` set; no stale `.env` in the image (`db.py:7`).
- [ ] All three Cloudinary vars set, or make `cloudinary.config()` lazy and
      optional.
- [ ] `SMTP_PORT` validated rather than `int()`-cast at import.
- [ ] Mail config validated at boot so a user-creation send cannot fail halfway.
- [ ] Scheduler started by exactly one worker.
- [ ] `sent_reminders_log` created in `init_postgres()`.
- [ ] Reminder recipients moved out of source.
- [ ] `/auto_iqac_reminders` behind auth or an internal scheduler.
- [ ] Replace emailed temporary passwords with one-time reset links.
- [ ] Remove the hardcoded personal Gmail address at `pdf.py:1027`.
- [ ] Decide whether worklog content may be sent to a third-party AI provider.