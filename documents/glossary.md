# Glossary

Domain vocabulary. Read this before touching business logic — most of it is not
inferable from the code, and several terms mean something specific (and slightly
unusual) in this codebase.

---

## Institutional terms

### IQAC — Internal Quality Assurance Cell

The department this system serves. The institution appears to be **Christ
University** (`director.iqac@christuniversity.in`, `pdf.py:1027`).

### AQAR — Annual Quality Assurance Report

An annual accreditation document. Coordinators contribute a section rather than
producing the whole report; that contribution is the `aqar_coordinator` report
type.

**In this codebase AQAR is not a report you generate — it is a section you
submit.** It maps to `report_type = 'aqar_coordinator'`, its own screen
(`iqac_coordinator_report.html`), and its own PDF variant.

### Coordinator

A **School IQAC Coordinator** or **Campus IQAC Coordinator**. The role that
submits monthly reports. Distinct from "Administrator", which manages users and
settings.

**Note the two levels.** "School" and "Campus" are separate role strings that the
code treats as interchangeable for authorization (`is_coordinator()` accepts
either) but which select **different PDF layouts**. The distinction is a real
template variant, not a label. See
[backend/07-pdf-rendering.md](backend/07-pdf-rendering.md) §2.

### Principal / Director / Chairperson

Different designations that appear in recipient lists and report sign-offs. A
"Chairperson report" (`chairperson_report.html`) is an administrative aggregate,
not a report *for* the chairperson.

### NAAC

The accreditation body whose requirements the AQAR serves. Referenced in
workflows but **no NAAC API or schema exists** in the codebase — no endpoint, no
table, no field. Do not assume NAAC-specific structure.

---

## Product terms

### Worklog

A **daily** record of one employee's work, one row per user per date. The core
data structure of the employee side.

- Stored in `worklog`.
- `task` is a **JSON object keyed by category**, not free text.
- `date` is a `VARCHAR`, not a `DATE`. See
  [backend/04-data-model.md](backend/04-data-model.md) §3.

### Entry

One `worklog` row. Editable for **7 days** by its owner; that window is a domain
rule enforced in four places.

### Category

One of six worklog categories, plus two statuses:

| Value | Kind |
|---|---|
| `Documentation and Audits` | category |
| `Rankings` | category |
| `Publications` | category |
| `Training and Development` | category |
| `Strategic Initiatives` | category |
| `Others (<specify>)` | category |
| `Holiday` | **status** |
| `Leave` | **status** |

`Holiday` and `Leave` live in the `status` column, not `category`. Leave entries
are stripped from all reporting.

⚠ The UI value `Others` does **not** equal the stored key `Others (<specify>)`;
matching is by prefix.

### Reporting month

`YYYY-MM`, used by coordinator submissions, drafts, and workshop attachments. A
**string**, never a `Date`. Never validated at the URL boundary in the legacy
code.

### Signed report

A coordinator's monthly submission, tracked in `signed_reports`. Despite the
name there is **no signature captured in the database** — it refers to a signed
*document*, and the signature block is rendered into the PDF. The
`cloudinary_public_id` field refers to the uploaded file.

### Draft

Autosaved coordinator report form state, one JSON blob per
`(username, report_type, reporting_month)`.

### Submission window

The period each month during which coordinators may submit — by default open on
the **1st** and closed on the **5th**, configurable in `app_settings`.

**Three divergent implementations** exist and they disagree. Do not recompute
this client-side.

### Review

The admin/secretary step where a submitted report is **approved** or sent back
with **corrections requested** (free-text remarks).

### Statuses

| Status | Meaning |
|---|---|
| `pending_upload` | Row exists, nothing submitted |
| `uploaded` | Submitted, awaiting review |
| `reviewed` | Approved — terminal |
| `corrections_requested` | Sent back with remarks |

The DDL default is `'pending'`, which no code path uses.

---

## Codebase-specific vocabulary

### Active role

The single role a user is currently operating as, stored in `session['role']`.
Chosen from `available_roles` (the CSV split) at login, and set to the **first**
entry.

⚠ **CSV order decides the landing page.** This is the least obvious behaviour in
the codebase. See [backend/03-authentication.md](backend/03-authentication.md) §5.

### CSV role

`users.role` holds a comma-separated list in one `VARCHAR(255)`, e.g.
`"Secretary, Campus IQAC Coordinator"`. There is no normalisation and no roles
table.

### The monkeypatch

The global `psycopg.Cursor.fetchone` override at `app.py:20-34` that rewrites the
current user's `role` to the active role so exact-equality checks work.

Known as *the monkeypatch* throughout this corpus. It is the most fragile piece
of the backend. See [backend/03-authentication.md](backend/03-authentication.md) §2.

### `enforce_password_change`

The `@app.before_request` hook enforcing the forced password change. Despite the
name it is **not** an authentication guard — it only checks
`must_change_password`. See [backend/10-gotchas.md](backend/10-gotchas.md) §5.

### Flash message

Flask's `flash()` + a rendered bootstrap alert. **Cannot reach an XHR client** —
replacing it with toasts requires returning the message in the JSON body.

### `dict_row`

The psycopg row factory making rows plain dicts. The monkeypatch's
`isinstance(row, dict)` check silently depends on it.

### Session check

`if 'username' not in session`. There is no `@login_required`; all 41 checks are
hand-copied inline.

---

## Domain rules that are not obvious

| Rule | Where |
|---|---|
| Worklog entries editable for 7 days | Four handlers in `app.py` |
| Submission window: 1st–5th, configurable | `app_settings`, three implementations |
| Coordinator PDFs differ by school vs campus | `AQAR_COORDINATOR_EMAILS` |
| Leave never appears in counts or summaries | Two serialisation layers |
| Prior month must be submitted before the current one | `check_submission_window` |
| Coordinator's `available_roles[0]` picks the landing page | `app.py:775` |
| "School" and "Campus" are interchangeable for auth but not for PDFs | `is_coordinator()` vs `pdf.py` |

---

## Abbreviations

| Term | Meaning |
|---|---|
| IQAC | Internal Quality Assurance Cell |
| AQAR | Annual Quality Assurance Report |
| NAAC | National Assessment and Accreditation Council |
| CRUD | Create, Read, Update, Delete |
| CSV | Comma-separated values |
| PDF | Portable Document Format |
| SMTP | Simple Mail Transfer Protocol |
| CI | Continuous Integration |
| SPA | Single-page application |