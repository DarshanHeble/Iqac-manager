# Backend — Authentication, Roles, and the Cursor Monkeypatch

The most delicate subsystem in this codebase. Read before touching
`app.py:20-34`, any role comparison, or session handling.

---

## 1. Why a monkeypatch exists

`users.role` is a **single `VARCHAR(255)` column holding a comma-separated
list**:

```
Secretary, Campus IQAC Coordinator
```

Nearly every authorization check in the app is exact string comparison:

```python
if user["role"].lower() == "admin":      # app.py:842
if user["role"].lower() != "secretary":  # app.py:3770
```

These fail for multi-role users — `"Secretary, Campus IQAC Coordinator"` is
neither `== "admin"` nor `!= "secretary"` in the intended sense. Rather than
rewrite ~20 call sites, the app globally rewrites the `role` of the **current
user's own row** to the **currently active role** at fetch time.

---

## 2. The patch

```python
# backend/app.py:20-34
import psycopg
_orig_fetchone = psycopg.Cursor.fetchone
def _patched_fetchone(self):
    row = _orig_fetchone(self)
    if row and isinstance(row, dict) and "role" in row and "username" in row:
        try:
            from flask import session
            if session and "username" in session and row["username"] == session["username"]:
                if "role" in session:
                    row["role"] = session["role"]
        except Exception:
            pass
    return row
psycopg.Cursor.fetchone = _patched_fetchone
```

### Exact semantics

| Aspect | Behaviour |
|---|---|
| Scope | **Process-global.** Applies to every `psycopg.Cursor` in the interpreter, including `routes/pdf.py` and all secondary connections. |
| Trigger | Any `fetchone()` returning a `dict` with **both** `role` and `username` keys. |
| Restriction | Only when `row["username"] == session["username"]`. It can never rewrite another user's row. |
| Effect | Replaces `row["role"]` with `session["role"]`, **preserving session casing** (e.g. `"School IQAC Coordinator"`). |
| Mutation | Operates on the fresh dict produced by `dict_row`. The stored value is untouched. |
| Outside a request | `if session` raises `RuntimeError`, swallowed by `except Exception: pass`. Background scheduler work is therefore unaffected. |

`from flask import session` sits inside the function to avoid a circular import
with `app.py:1`.

### Limitations — all real, all load-bearing

1. **`fetchone` only.** `fetchall()` is **not** patched. Every list-shaped role
   decision is inconsistent with the single-row ones. Concretely:
   `admin_manage_users` (`app.py:2382`) and the report dropdowns
   (`app.py:1856`, `:1860`) display raw CSV roles, while the gate that admitted
   the request used the patched active role.
2. **Requires `dict_row`.** With `row_factory=None` the `isinstance(row, dict)`
   test fails and the patch silently becomes a no-op — a security behaviour that
   depends on connection configuration.
3. **Requires both columns.** `SELECT designation FROM users …` is never
   rewritten.
4. **Not idempotent.** `_orig_fetchone` is captured at module scope with no
   guard, so re-executing the module in one interpreter nests wrappers.
5. **Subclasses that override `fetchone`** bypass it.
6. **Not thread-local by construction.** It is safe only because the request
   scoping comes from Flask's context-local `session`.

> **Do not "clean this up" casually.** Replacing it requires auditing every role
> comparison in `app.py` and `routes/pdf.py`, and introducing a normalised role
> model. That is a real refactor, not a cleanup — see
> [09-conventions-and-gotchas.md](10-gotchas.md).

---

## 3. Session keys

Five keys. All are written into a **signed client-side cookie**; `app.config` is
never assigned, so Flask 3.0 defaults apply (`HTTPONLY=True`, `SECURE=False`,
no `SameSite` attribute).

| Key | Set at | Purpose |
|---|---|---|
| `username` | `app.py:771` | Identity key. **Its presence is the login test** in every handler. |
| `full_name` | `app.py:772` | Display only; never re-validated against the DB. |
| `available_roles` | `app.py:774` | CSV split + stripped. The whitelist that gates `/switch_role`. |
| `role` | `app.py:775` (`available_roles[0]`), `app.py:804` (switch) | **The active role.** Read by the monkeypatch — this is the load-bearing consumer. |
| `must_change_password` | `app.py:776` (login), `app.py:736` (change) | Gates every endpoint except `login` / `logout` / `change_password` / `static`. |

### Logout is incomplete — verified

```python
# app.py:821-825
@app.route("/logout")
def logout():
    session.pop("username", None)      # ONLY this key
    flash("You have been logged out.", "info")
    return redirect("/login")
```

`role`, `full_name`, `available_roles`, and `must_change_password` persist in
the client cookie after logout. Because the cookie is signed but **not
encrypted**, those values remain readable on the client. `session.clear()` is
never used anywhere in the codebase.

---

## 4. The global guard is not an auth guard

```python
# app.py:700-708
@app.before_request
def enforce_password_change():
    allowed_routes = ['login', 'logout', 'change_password', 'static']
    if request.endpoint in allowed_routes or not request.endpoint:
        return
    if 'username' in session and session.get('must_change_password'):
        flash("For security reasons, you must change your temporary password before proceeding.", "warning")
        return redirect(url_for('change_password'))
```

Facts:

1. It **never checks whether anyone is logged in.** It only enforces the
   password-change flag. Every route implements its own login check separately
   (37 inline guards in `app.py`, 4 in `routes/pdf.py`).
2. The allowlist is keyed on **`request.endpoint`** (the function name), not URL.
3. `not request.endpoint` is `True` for unmatched URLs, so 404s short-circuit —
   correctly, avoiding a redirect loop.
4. Being app-level (not blueprint-level), it **does** cover `pdf.*` endpoints,
   whose endpoint names are not in the allowlist.
5. `home` (`/`) is not exempt, so a flagged user is redirected to
   `/change_password` before `home`'s own `/login` redirect executes.
6. It flashes on **every** intercepted request, so duplicate warnings accumulate.
7. It trusts the **session** flag, not the database. If an admin resets a user's
   password, that user's already-open session still carries
   `must_change_password=False` until they log in again.

### Forced-password-change lifecycle

| Stage | Location | Effect |
|---|---|---|
| Column created | `app.py:556` | `must_change_password BOOLEAN DEFAULT FALSE` |
| Seed admin | `app.py:629-641` | `admin` inserted with `TRUE`, password `admin123` |
| User created | `app.py:1749` | `TRUE`, plus emailed 8-char temp password |
| Self-reset | `app.py:1804` | `TRUE` |
| Admin reset | `app.py:2531` | `TRUE` |
| Login | `app.py:776-780` | Flag copied into session; redirect to `/change_password` |
| Enforced | `app.py:700-708` | All other endpoints |
| Cleared | `app.py:734-736` | After a successful change |

`switch_role` is **not** exempt, so a flagged user cannot bypass the change by
switching roles.

---

## 5. Dashboard routing on login

```python
# app.py:770-790
if user and check_password_hash(user["password"], password):
    session["username"] = username
    session["full_name"] = user.get("full_name") or username
    available_roles = [r.strip() for r in user["role"].split(",")]
    session["available_roles"] = available_roles
    session["role"] = available_roles[0]          # <-- FIRST CSV ENTRY WINS
    session["must_change_password"] = user.get("must_change_password", False)
    flash(f"Welcome, {session['full_name']}!", "success")

    if session["must_change_password"]:
        return redirect("/change_password")

    active_role_lower = session["role"].lower()
    if active_role_lower == "admin":
        return redirect("/admin")
    elif active_role_lower in ("school iqac coordinator", "campus iqac coordinator"):
        return redirect("/iqac_dashboard")
    elif active_role_lower == "secretary":
        return redirect("/secretary_dashboard")
    else:
        return redirect("/dashboard")
```

- **CSV order is load-bearing.** `available_roles[0]` determines the landing
  page. Reordering the string in the database silently changes where a user
  lands after login.
- The same four-branch table is duplicated **three more times**: `change_password`
  (`:739-747`), `switch_role` (`:807-815`), and in a deny-shaped variant inside
  `dashboard` (`:842-849`).
- Anything unrecognised falls to `/dashboard`.
- Edge cases: `role = ''` yields `session['role'] = ''` and routes to
  `/dashboard`; `role = NULL` raises `AttributeError` → HTTP 500 at login.

---

## 6. Role matching — three inconsistent strategies

### `is_coordinator` — exact token membership

```python
# app.py:70-74  (duplicated byte-for-byte at routes/pdf.py:16-20)
def is_coordinator(role_str):
    if not role_str:
        return False
    roles = [r.strip().lower() for r in role_str.split(',')]
    return 'school iqac coordinator' in roles or 'campus iqac coordinator' in roles
```

Requires an exact lowercase token. `"IQAC Coordinator"` (no qualifier) returns
`False` — which is precisely why the boot-time migration at `app.py:624` exists.
Safe on `None`/`""`, but callers that do `user["role"].lower()` first raise
`AttributeError` on `NULL`.

### Admin panels — `strpos()` substring

```sql
-- 18 sites: app.py:1433, 1453, 1460, 1469, 1478, 1485, 1508,
--           1856, 1860, 2124, 2578, 2703, 3779, 3787, 3796, 3804, 3810, 3818
WHERE strpos(role, 'School IQAC Coordinator') > 0
   OR strpos(role, 'Campus IQAC Coordinator') > 0
```

Exclusion form (`app.py:1433`, `1856`, `2124`):

```sql
WHERE strpos(role, 'Admin') = 0
  AND strpos(role, 'School IQAC Coordinator') = 0
  AND strpos(role, 'Campus IQAC Coordinator') = 0
```

Substring matching on a CSV column means a hypothetical role such as
`"Not A School IQAC Coordinator"` would match, and `strpos(...) = 0` is **not**
equivalent to "the CSV does not contain this exact role".

### Route gates — exact equality on the patched value

```python
user["role"].lower() != "admin"        # 8 sites
user["role"].lower() not in ("admin", "secretary")   # 7 sites
user["role"].lower() != "secretary"    # 1 site
```

These only work because the monkeypatch replaced the CSV with one active role.

### Notification audiences — a fourth definition

```sql
-- app.py:156-162  (broad)
LOWER(role)='admin' OR LOWER(role) LIKE '%secretary%'
  OR LOWER(designation) LIKE '%secretary%' OR LOWER(username) LIKE '%secretary%'

-- app.py:3610, routes/pdf.py:1000  (narrow, exact + case-sensitive)
WHERE role IN ('Admin','Secretary')
```

The narrow form **will miss most rows** given multi-role CSV strings such as
`"Secretary, Campus IQAC Coordinator"` — `IN` requires whole-string equality.

---

## 7. Complete authorization check inventory

Deny targets are inconsistent: some redirect to `/login`, some to `/dashboard`.

| Location | Predicate | Deny target |
|---|---|---|
| `app.py:700-708` | `must_change_password` | `/change_password` |
| `app.py:713` | session | `/login` |
| `app.py:799` | session | `/login` |
| `app.py:802-803` | `role in available_roles` | flash + `/dashboard` |
| `app.py:831-832` | session | `/login` |
| `app.py:842-845` | Admin on employee area | flash + `/admin` |
| `app.py:847-849` | coordinator on employee area | flash + `/iqac_dashboard` |
| `app.py:918-919`, `929-932`, `934-937` | session / admin / coordinator | `/login` or role home |
| `app.py:1080-1081`, `1093-1096`, `1098-1101` | same pattern | `/login` or role home |
| `app.py:1164-1165`, `1175-1178`, `1180-1183` | same pattern | `/login` or role home |
| `app.py:1303-1304`, `1310`, `1319` | session; ownership; age ≤ 7d | `/dashboard` |
| `app.py:1386-1387`, `1393`, `1402` | session; ownership; age ≤ 7d | `/dashboard` |
| `app.py:1417-1418`, `1427-1430` | session; admin | flash + `/dashboard` |
| `app.py:1676-1677`, `1684-1687` | session; admin | flash + `/dashboard` |
| `app.py:1711-1712`, `1721-1724` | session; admin | flash + `/dashboard` |
| `app.py:1785` | **none** | — |
| `app.py:1840-1841`, `1850-1853` | session; admin or secretary | flash + `/dashboard` |
| `app.py:2108-2109`, `2118-2121` | session; **admin only** | flash + `/dashboard` |
| `app.py:2366-2367`, `2376-2379` | session; admin | flash + `/dashboard` |
| `app.py:2392-2393`, `2402-2405` | session; admin | flash + `/dashboard` |
| `app.py:2458-2459`, `2468-2471`, `2482` | session; admin; not `username='admin'` | flash + `/dashboard` |
| `app.py:2503-2504`, `2513-2516` | session; admin | flash + `/dashboard` |
| `app.py:2743` | **none** | — |
| `app.py:2754-2755`, `2764-2767` | session; coordinator | flash + `/login` |
| `app.py:2832-2833`, `2842-2845` | session; coordinator | flash + `/login` |
| `app.py:2997-2998`, `3006-3007` | session (401); coordinator (403) | JSON error |
| `app.py:3147-3148`, `3158-3161`, `3165-3168` | session; user exists; elevated or self | flash + `/dashboard` |
| `app.py:3266-3267`, `3280-3283`, `3286-3289` | session; row exists; `status='pending_upload'` | flash + `/dashboard` |
| `app.py:3311-3312`, `3321-3324` | session; admin or secretary | flash + `/dashboard` |
| `app.py:3368-3369`, `3383-3388` | session; elevated or owner | flash + `/dashboard` |
| `app.py:3434-3435`, `3449-3454` | session; elevated or owner | flash + `/dashboard` |
| `app.py:3509-3510`, `3519-3522` | session; coordinator | flash + `/login` |
| `app.py:3641-3642`, `3650-3653` | session; admin or secretary | flash + `/dashboard` |
| `app.py:3701-3702` | **session only — no role check** | `/login` |
| `app.py:3737-3738`, `3746-3749` | session; admin or secretary | flash + `/dashboard` |
| `app.py:3762-3763`, `3770-3773` | session; **secretary only** | flash + `/login` |
| `routes/pdf.py:98-99, 108-111` | session; coordinator | `/login` |
| `routes/pdf.py:674-675, 684-687` | session; coordinator | `/login` |
| `routes/pdf.py:746-747, 756-758` | session; coordinator | JSON error |
| `routes/pdf.py:1053-1054`, 1063-1066` | session; coordinator | `/login` |

**There are no custom decorators anywhere.** No `@login_required`, no
`@admin_required`. Every check is hand-copied.

---

## 8. Password handling

- Hashing: `werkzeug.security.generate_password_hash` (PBKDF2/scrypt by default),
  verified with `check_password_hash`.
- Temporary passwords: 8 characters from `ascii_letters + digits`
  (`app.py:1737`, `1801`, `2528`).
- Plaintext temporary passwords are emailed in the message body
  (`app.py:1756-1771`, `1811-1827`, `2538-2554`).
- Minimum length on change: 6 characters (`app.py:720`).
- **No CSRF token on any form**, including `/change_password` and every
  state-changing POST.
- `forgot_password` requires only username + email, with no token, no expiry,
  and no record of the reset attempt.

---

## 9. Implications for the Angular migration

1. **Keep the session cookie.** Switching to JWT would require reimplementing
   the monkeypatch's role semantics, `before_request`, and every inline guard.
   The dev proxy already keeps the app same-origin so the cookie just works.
2. **Add `GET /api/me`** returning `{username, full_name, available_roles,
   role, must_change_password}`. This is exactly the session dict and is the
   only thing the Angular shell needs to render.
3. **Replace `/switch_role` GET with a POST** to `POST /api/active-role`, and add
   CSRF protection at the same time. The current route is a state-changing GET.
4. **Add an Angular route guard** mirroring `before_request`: redirect to
   `/change-password` when `must_change_password` is true, and to `/login` when
   unauthenticated. These are client-side conveniences only — the server checks
   remain authoritative.
5. **Have the backend return 401 JSON for XHR**, not a 302 to the login page.
   Send `X-Requested-With: XMLHttpRequest` (already done by
   `sessionInterceptor`) and branch in `before_request` on that header.
6. **Do not trust client-side role gating.** Given §6's substring matching and
   `fetchall()` not being patched, any client-side assumption about roles will
   diverge from the server's view.