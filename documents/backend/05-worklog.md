# Backend — Worklog Domain

Employee daily activity tracking. The largest user-facing feature by route count
and the one with the most data-modelling problems.

- **Table:** `worklog` — see [data/schema.json](data/schema.json)
- **Templates:** `user_add_entry.html`, `user_view_entries.html`,
  `user_report.html`, `edit.html`, `dashboard.html`
- **Routes:** `/add_entry`, `/edit_entry`, `/view_worklog`, `/worklog_report`

---

## 1. The entry model

One row per user per day. Six categories plus two statuses.

| Value | Kind | Meaning |
|---|---|---|
| `Documentation and Audits` | category | Evidence collection, audits |
| `Rankings` | category | Ranking submissions |
| `Publications` | category | Papers, ISBNs, journals |
| `Training and Development` | category | FDPs, workshops attended |
| `Strategic Initiatives` | category | MoUs, initiatives |
| `Others (<specify>)` | category | Free-text, requires a sub-description |
| `Holiday` | **status** | Not a category. Marks the day |
| `Leave` | **status** | Not a category. Marks the day |

Category vocabulary is derived from the form field mapping at `app.py:1022-1044`.
`Holiday` and `Leave` are stored in the `status` column, not `category`.

### ⚠ "Others" matching is asymmetric by design

The special key is `"Others (<specify>)"` but filtering searches `"Others`:

```python
# app.py:1600, 1606, 1620, 1626
like_pattern = '%"Others%' if category_filter == "Others" else f'%"{category_filter}"%'
```

So selecting `Others` in the UI matches `Others (<specify>)` in the database, and
vice versa. This is intentional — but it means the category strings in the UI
and in the DB are **not equal**, and any equality-based Angular filter will find
nothing. Reuse the prefix rule.

### ⚠ Leave entries are stripped at two serialisation layers

```
app.py:405-406    and    app.py:418-419
```

Leave is removed when building payloads for both the PDF and the AI summary. If
you are counting categories for a dashboard, Leave never appears.

---

## 2. `task` is a JSON object in a TEXT column

The form submits one input per category. All six are serialised into a single
`task` string.

Stored value:

```json
{"Documentation and Audits": "Compiled 3 audit files", "Publications": "ISBN submitted"}
```

Three consequences, all of which affect new code:

### 2.1 Category filtering is a LIKE over serialised JSON

```sql
WHERE w.task::text LIKE %s    -- parameterised; pattern built in Python
```

Safe from injection (parameterised), but **not** from pattern semantics. `%` or
`_` inside a category filter string would broaden the match. If the Angular app
exposes a free-text category search, escape those characters or use a JSONB
column.

### 2.2 Legacy plaintext must be tolerated everywhere

Several readers branch on parse failure:

```python
try:
    tasks_dict = json.loads(row["task"])
except (json.JSONDecodeError, TypeError):
    tasks_dict = {row["category"]: row["task"]}
```

Any new consumer of `worklog.task` **must** do the same, or it will crash on
historical rows. Assume plaintext rows exist.

### 2.3 `category` is redundant

`worklog.category` duplicates the primary key of the JSON object. It is written
but reads generally prefer the parsed dict. It is a fallback for legacy rows and
nothing more.

---

## 3. `date` is VARCHAR, not DATE

```sql
date VARCHAR(20)     -- app.py:547
```

Stored as zero-padded ISO `YYYY-MM-DD`. Every range filter is therefore a
**lexicographic string comparison**:

```sql
WHERE w.date BETWEEN %s AND %s     -- app.py:1214, 1232, 1246, 1595, 1984
```

This is correct only because the format never varies. Two places compensate by
casting:

```sql
EXTRACT(YEAR FROM date::date) = %s    -- app.py:288-289
date LIKE %s                          -- app.py:876
```

**This will throw** if any row predates the ISO format or is malformed. Anything
new that sorts or filters by date inherits the fragility. Converting to a real
`DATE` column is listed as a recommendation in
[04-data-model.md](04-data-model.md) §12.

### ⚠ No uniqueness on `(username, date)`

Duplicate prevention is an application-level check before insert:

```
app.py:981-985
```

Under two concurrent submissions on the same day, both pass the check and two
rows are written. Everything downstream (`/view_worklog`, `/edit_entry`,
`/worklog_report`) then disagrees about how many entries exist. Add
`UNIQUE (username, date)`.

---

## 4. Entry lifecycle

```
   create ──> view ──> edit (≤7 days) ──> delete
                │            │
                └── report ─┘
```

### Ownership and age gates

Every per-user route enforces **both** conditions inline:

| Route | Session | Owner | Age ≤ 7d | Deny |
|---|---|---|---|---|
| `/add_entry` | yes | n/a | n/a | `/dashboard` |
| `/edit_entry` | yes | yes | yes | `/dashboard` |
| `/view_worklog` | yes | yes | yes | `/dashboard` |
| `/worklog_report` | yes | yes | yes | `/dashboard` |

The 7-day window is the domain rule for "how long may a staff member amend their
own record". It is duplicated across four handlers, so changing it means four
edits. The age comparison is done in SQL, not Python.

`/view_worklog` and `/worklog_report` are therefore **not** reporting endpoints —
they are "my own last 7 days" endpoints. Aggregate reporting is admin-only
(`/admin/analytics_data`, `/chairperson_report`).

---

## 5. Attachments

### Write path

```
app.py:1049-1058
```

1. Validate extension against the allowlist.
2. `secure_filename(username)` + `YYYY-MM-DD` + `YYYYMMDDHHMMSS` + extension.
3. Save to `backend/static/attachments/`.
4. Store the **relative** value `attachments/<filename>` in `worklog.attachment`.

Allowed extensions (`app.py:656-659`):

```
pdf, jpg, jpeg, png, doc, docx
```

### ⚠ Read path is completely unauthenticated

`/static/<path:filename>` is Flask's built-in static route. It is excluded from
`routes.json` as an application endpoint, but it serves `worklog.attachment`.

Templates link to it directly:

```
backend/templates/user_report.html:569, 570, 573
```

Any request with the filename gets the file. No session, no ownership check, no
role check. Because filenames embed the username and date, they are
**guessable by anyone who knows a username and roughly when they worked**.

Full analysis: [11-security.md](11-security.md) **SEC-01**.

**Do not replicate this pattern in Angular.** Serve attachments through an
authenticated endpoint that re-checks ownership.

### Upload limits

No explicit `MAX_CONTENT_LENGTH` is configured in the code paths reviewed, so
the effective limit is whatever the platform (Render) imposes. Large uploads
fail at the proxy with a non-JSON error. If the Angular app needs friendly
errors, set `MAX_CONTENT_LENGTH` explicitly and handle `413`.

---

## 6. Reporting

| Report | Route | Audience | Scope |
|---|---|---|---|
| Worklog report | `/worklog_report` | owner | Own entries, ≤ 7 days |
| Chairperson report | `/chairperson_report` | admin | Aggregate |
| AI report | `/chairperson_report?ai=1` | admin | Aggregate + AI summary |
| Analytics | `/admin/analytics_data` | admin, secretary | JSON for charts |
| Monthly PDF | `/pdf/report_standard_download` | secretary | Per coordinator |

### `/admin/analytics_data` returns raw counts

Category counts drive the only charts in the legacy UI (`admin.html`). It is
JSON already, which makes it the easiest endpoint to port to Angular unchanged.

Note it applies the same `Others`-prefix LIKE rule, so the counts it returns are
consistent with §1.

### AI summary

`/chairperson_report?ai=1` triggers summarisation over the selected range.
Pipeline and failure modes: [08-integrations.md](08-integrations.md) §4.

If `GEMINI_API_KEY` is unset the page still renders — it simply has no summary.
Do not treat an absent summary as an error in the new client.

---

## 7. What to carry into Angular

1. **Keep the `Others` prefix rule** in any category filter.
2. **Tolerate plaintext `task`** in every renderer.
3. **Never link `/static/<attachment>` directly.** Route through an
   authenticated endpoint.
4. **Add `UNIQUE (username, date)`** before the new client makes concurrent
   submissions likely.
5. **Preserve the 7-day edit window**, but define it once on the server. Do not
   replicate it in four handlers or in the client.
6. **Treat `date` as a string.** Do not assume a `Date` type; the API returns
   `YYYY-MM-DD` and the column is `VARCHAR`.
7. **Leave entries never appear in counts.** Match that behaviour or the
   dashboard totals will not reconcile.