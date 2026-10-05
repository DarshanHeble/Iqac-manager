# Backend — Coordinator Reports Domain

The monthly submission lifecycle for School and Campus IQAC Coordinators. This is
the most stateful part of the system and the primary target of the Angular port.

- **Tables:** `signed_reports`, `report_drafts`, `workshop_attachment_files`
- **Templates:** `iqac_monthly_report.html`, `iqac_coordinator_report.html`,
  `iqac_coordinator_dashboard.html`, `admin_signed_reports.html`
- **Routes:** `/iqac_dashboard`, `/iqac_report`, `/iqac_coordinator_report`,
  `/iqac_report/save_draft`, `/admin/signed_reports`, `/admin/workshop_attachments`

---

## 1. Two report types

| `report_drafts.report_type` | Screen | Meaning |
|---|---|---|
| `standard` | `iqac_monthly_report.html` | Ordinary monthly activity report |
| `aqar_coordinator` | `iqac_coordinator_report.html` | The AQAR (Annual Quality Assurance Report) contribution |

They share tables and helpers but are separate screens with separate drafts and
separate PDFs. In the Angular app these are distinct routes, not a variant flag.

`report_type` is one of exactly two strings; there is no enum or `CHECK`
constraint, so validate at the API boundary in the new code.

---

## 2. The status state machine

```
                  create / open
                        │
                        ▼
              ┌──────────────────┐
              │  pending_upload  │   row exists, nothing submitted
              └────────┬─────────┘
                       │ submit
                       ▼
              ┌──────────────────┐
              │     uploaded     │   file in Cloudinary, awaiting review
              └────────┬─────────┘
                       │ admin/secretary reviews
            ┌──────────┴──────────┐
       approve                    request corrections
            │                         │
            ▼                         ▼
       ┌──────────┐          ┌────────────────────────┐
       │ reviewed │          │ corrections_requested  │
       └──────────┘          └───────────┬────────────┘
              ▲                          │ coordinator resubmits
              └──────────────────────────┘
```

| Status | Set at | Meaning |
|---|---|---|
| `pending_upload` | row created | No file yet |
| `uploaded` | coordinator submits | Awaiting review |
| `reviewed` | admin approves | Terminal |
| `corrections_requested` | admin requests changes | Includes free-text `remarks` |

The DDL default is `'pending'` (`app.py:566`), which **no code path uses**. Do
not rely on it.

### Resubmission leaves stale state

```
backend/routes/pdf.py:255-262
```

On resubmit, `status`, `remarks`, and `uploaded_file_path` are overwritten, but
**`cloudinary_public_id` is not cleared**. The row ends up pointing at a public
id for a deleted or superseded asset. Any delete-or-replace logic keyed on
`cloudinary_public_id` can therefore act on the wrong object.

---

## 3. ⚠ The missing unique constraint

```sql
-- app.py:559-568 — note what is NOT here
CREATE TABLE IF NOT EXISTS signed_reports (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) NOT NULL,
    reporting_month VARCHAR(20),
    uploaded_file_path VARCHAR(500),
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'pending'
);
```

**There is no `UNIQUE (username, reporting_month)`,** yet at least five code paths
assume exactly one row per coordinator per month:

| Site | Assumption |
|---|---|
| `app.py:440-510` | `COUNT(*)` decides whether the prior month was submitted |
| `app.py:3293-3296` | `DELETE … WHERE username AND reporting_month` removes **all** matches |
| `app.py:3592-3601` | read-then-write to choose `INSERT` vs `UPDATE` |
| `pdf.py:127-135` | reads `status` from a single row |
| `pdf.py:1082-1090` | same, for the AQAR variant |

Concurrent requests produce duplicate rows, ambiguous `fetchone()` results, and
multi-row deletes.

**Add this constraint before building the Angular client.** The new UI will make
double-submission far easier to trigger, and the resulting state is very hard to
repair by hand. See [04-data-model.md](04-data-model.md) §4.

### Missing index on `reporting_month`

The hottest filter in the table has no index:

```
app.py:1540, 3664, 3864, 3872
```

---

## 4. ⚠ The submission window — three divergent implementations

Administrators configure `submission_open_day` (default `1`) and
`submission_close_day` (default `5`) in `app_settings`.

`check_submission_window()` reads them. It is called from the coordinator
dashboard, the report screens, and the PDF routes — and the arithmetic is not
identical between call sites:

| Aspect | Inconsistency |
|---|---|
| Previous-month grace | `app.py:440-510` gives a wider grace window; the PDF paths do not |
| Day-of-month rollover | Some paths compare against the *current* day, others against the last day of the target month |
| Role sensitivity | Secretary and Admin bypass the window in some paths and not others |

**Consequence: the same coordinator can see the window open on the dashboard and
closed on the PDF download.** If the Angular app reimplements this rule
client-side it will disagree with at least one server path.

**Recommendation:** collapse to a single function returning a structured result
(`{open, closed_reason, grace, target_month}`), have every caller use it, and let
the API return that object so the client never recomputes.

---

## 5. Drafts

`report_drafts` autosaves the entire report form as JSON.

```sql
UNIQUE (username, report_type, reporting_month)   -- app.py:608
```

This is the **only properly implemented upsert** in the codebase:

```sql
INSERT INTO report_drafts (username, report_type, reporting_month, form_data, updated_at)
VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
ON CONFLICT (username, report_type, reporting_month)
DO UPDATE SET form_data = EXCLUDED.form_data,
              updated_at = CURRENT_TIMESTAMP
```

Sites: `app.py:3061-3067` (save), `pdf.py:155-160`, `pdf.py:956-961`,
`pdf.py:1109-1114` (read).

### Reads fail silently

```
app.py:2907-2911
```

```python
try:
    form_data = json.loads(row["form_data"])
except (...):
    form_data = {}
```

A corrupt draft yields an **empty form**, not an error. The coordinator's work
appears to have vanished with no message. When building the new draft API,
surface a parse failure explicitly.

### Save targets

Both large templates POST to the same endpoint:

```
POST /iqac_report/save_draft
```

called from `iqac_monthly_report.html` and `iqac_coordinator_report.html`.
The draft API is therefore already de-duplicated and is a good model for the new
surface.

---

## 6. Review workflow

`/admin/signed_reports` (admin) and `/secretary_review` (admin or secretary) show
submitted reports and allow **approve** or **request corrections**.

Both gate on `role.lower() in ("admin", "secretary")`. Neither uses a decorator;
the check is inline at:

```
app.py:3311-3312 / 3321-3324      (signed reports)
app.py:3641-3642 / 3650-3653      (secretary review)
```

⚠ The notification query that accompanies these pages uses the **narrow**
audience predicate:

```sql
WHERE role IN ('Admin','Secretary')     -- app.py:3610, pdf.py:1000
```

`IN` requires whole-string equality, so a row with role
`"Secretary, Campus IQAC Coordinator"` **will not match**. Most multi-role
secretaries are silently omitted from notifications. The broad variant at
`app.py:156-162` behaves differently — four definitions of "who is a secretary"
exist in one codebase. See [03-authentication.md](03-authentication.md) §6.

---

## 7. ⚠ `/admin/workshop_attachments` has no role check

Despite the `/admin/` prefix, the handler performs **only** a session check:

```
app.py:3701-3702      if 'username' not in session: return redirect('/login')
```

No role predicate. Any authenticated employee can reach it. Depending on what it
returns, this may expose other coordinators' uploads. See
[11-security.md](11-security.md).

---

## 8. Workshop attachment reconciliation

`workshop_attachment_files` is the one table with a correct composite unique key:

```
UNIQUE (username, reporting_month, workshop_index)    -- app.py:584
```

But the write path is **delete-then-reinsert**, not upsert:

```
app.py:3123-3132
pdf.py:219-231
```

Every reconciliation deletes all rows for the month and re-inserts. So:

- `id` changes on every run. Never expose `id` to the client as a stable handle.
- The unique constraint is exercised on insert rather than as conflict handling.
- A failure between the delete and the inserts loses all workshop data for the
  month with no transaction guaranteeing recovery.

`workshop_index` is **1-based in templates** (`workshop_{i+1}`) but **0-based in
the Cloudinary public_id** (`pdf.py:23`, `index + 1`). Off-by-one bugs here are
easy to introduce.

**For Angular:** key workshop rows by `(username, reporting_month,
workshop_index)`, never by `id`.

---

## 9. `reporting_month` is never validated

`YYYY-MM` is assumed everywhere but enforced nowhere:

```
app.py:3226     — taken straight from the URL
```

Any string reaches `signed_reports` and `report_drafts`. Month-picker validation
must be added server-side; the client control is a convenience, not a guarantee.

---

## 10. What to carry into Angular

1. **Two separate report screens**, not a variant flag — `standard` and
   `aqar_coordinator`.
2. **Add `UNIQUE (username, reporting_month)` to `signed_reports`** before
   shipping submission UI.
3. **Expose the submission window as an API object.** Never recompute the window
   client-side; three server implementations already disagree.
4. **Make draft-save failure visible.** Silent `except` hides data loss.
5. **Surface `corrections_requested` prominently**, including `remarks`.
6. **Key workshop rows by `(username, reporting_month, workshop_index)`**, not
   `id`.
7. **Validate `reporting_month` server-side** on every path that accepts it.
8. **Add an `X-Requested-With` branch** so these endpoints return 401 JSON rather
   than a 302 to `/login`.