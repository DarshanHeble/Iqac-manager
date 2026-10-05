# Backend — PDF Rendering

Every ReportLab generator lives in `backend/routes/pdf.py` (~1,200 lines) behind
4 routes. Nothing here returns an HTML template — all output is binary.

- **File:** `backend/routes/pdf.py`
- **Blueprint:** registered as `pdf` in `app.py`, so endpoints are `pdf.*`
- **Dependency:** `reportlab==4.2.5`

---

## 1. The four routes

| Endpoint | URL | Gate | Output |
|---|---|---|---|
| `pdf.generate_standard_report` | `/pdf/generate_standard_report` | coordinator | PDF stream |
| `pdf.generate_aqar_report` | `/pdf/generate_aqar_report` | coordinator | PDF stream |
| `pdf.report_standard_download` | `/pdf/report_standard_download` | **secretary** | PDF stream |
| `pdf.report_aqar_download` | `/pdf/report_aqar_download` | coordinator | PDF stream |

All four use `is_coordinator()` (`pdf.py:16-20`), a byte-for-byte duplicate of
`app.py:70-74`. Note the asymmetry: `report_standard_download` requires
**secretary**, the others require **coordinator**.

Gates are inline at `pdf.py:98-99, 108-111, 674-675, 684-687, 746-747,
756-758, 1053-1054, 1063-1066`.

---

## 2. Four reporting variants

The variant is selected from the environment, not from request parameters.

| Variant | Selected by | Consumer |
|---|---|---|
| Standard, campus | `AQAR_COORDINATOR_EMAILS` absent/empty | Campus coordinator |
| Standard, school | matches an entry in `AQAR_COORDINATOR_EMAILS` | School coordinator |
| AQAR, campus | `AQAR_COORDINATOR_NAMES` absent/empty | Campus |
| AQAR, school | matches `AQAR_COORDINATOR_EMAILS` | School |

Read sites: `pdf.py:149-152`, `:707`, `:910`, `:950`, `:1103`, `:1141`.

The coordinator's email is matched against `AQAR_COORDINATOR_EMAILS` — so
**changing who is considered a School coordinator is an environment change, not
a code change.**

### ⚠ Positional coupling between two variables

```
pdf.py:1103     AQAR_COORDINATOR_EMAILS
pdf.py:1141     AQAR_COORDINATOR_NAMES
```

The AQAR sign-off block pairs the email list with the name list **by index**. If
the two env vars have different lengths or are in different orders, the PDF
renders the wrong name against an email. One email matching one name also
short-circuits the pair. Validate at boot, not at render time.

### ⚠ Hardcoded personal Gmail address

```
pdf.py:1027
director_emails = ["director.iqac@christuniversity.in", "arnavnarula25@gmail.com"]
```

A personal address is hardcoded alongside the institutional one, in addition to
the env-configured list. Move it to `AQAR_COORDINATOR_EMAILS` or delete it.

---

## 3. Streaming directly from Cloudinary

Files are **never staged locally**. The generators fetch the source document
from Cloudinary and pipe it into ReportLab.

```
pdf.py:23        public_id is built from index + 1
pdf.py:219-231   reconciliation rewrites the stored rows
```

Consequences:

- **Cloudinary is on the critical path.** If it is down or the public id is
  stale, PDF generation fails outright — there is no local fallback.
- **The stale `cloudinary_public_id` bug** in
  [06-coordinator-reports.md](06-coordinator-reports.md) §2 can make a PDF render
  from a deleted asset.
- **Large files are buffered in memory** by ReportLab's platypus pipeline. Peak
  memory scales with the largest report in a cohort.

### Streaming vs buffering

ReportLab builds the whole document in memory, then it is streamed out. A
generator-based alternative (`canvas` incremental writes) would cut peak memory
substantially. Worth considering for the `standard` variant, which aggregates
many coordinators.

---

## 4. `dict_row` and the monkeypatch apply here too

`routes/pdf.py` opens its **own** connections rather than reusing anything from
`app.py`:

```
pdf.py:105, 681, 753, 1060      SELECT … FROM users
```

Because these go through the globally patched `psycopg.Cursor.fetchone`, the
current coordinator's row also has its role rewritten to `session['role']`. So
`is_coordinator(user["role"])` inside a PDF handler sees the **active role**, not
the CSV. That is correct — but it means PDF authorization is also subject to
every limitation listed in [03-authentication.md](03-authentication.md) §2.

---

## 5. `/pdf/report_standard_download` reads draft and roster data

| Source | Sites |
|---|---|
| `report_drafts` | `pdf.py:155-160`, `:956-961`, `:1109-1114` |
| `signed_reports` | `pdf.py:127-135`, `:1082-1090` |
| `workshop_attachment_files` | `pdf.py:219-231` |
| `worklog` | via the standard report generator |
| `users` | roster and email discriminator |

Draft reads use `json.loads` with a silent `except`, so a corrupt draft yields an
empty section rather than an error.

---

## 6. Submission window is re-implemented here

All four routes consult `check_submission_window()` and enforce it **before**
generating. As documented in
[06-coordinator-reports.md](06-coordinator-reports.md) §4, the window arithmetic
here diverges from `app.py`. A coordinator can therefore pass the gate on the
report screen and be refused on the PDF.

---

## 7. For the Angular migration

1. **PDFs need no Angular port.** Keep them as binary endpoints and link to them
   directly. An `<a download>` or `window.open` is sufficient.
2. **Add `?disposition=attachment` semantics explicitly** where the legacy
   templates relied on server-set headers; do not assume.
3. **Do not attempt to render PDFs client-side.** No PDF library is in the
   Angular dependency set and none is needed.
4. **Surface generation failures as JSON errors**, not HTML error pages. Today a
   Cloudinary failure produces a 500 with an HTML body, which an `HttpClient`
   call cannot deserialise.
5. **Fix the env-var length mismatch** (`pdf.py:1103` vs `:1141`) before
   production use — it silently misattributes signatures.
6. **Remove the hardcoded Gmail address** at `pdf.py:1027`.