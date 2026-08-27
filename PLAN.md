# Shipment Label Printing Portal — Implementation Plan

Frozen 2026-08-27. Copied from `tasks/2026-08-11/shipment-label-portal.md`
in the parent workspace, which remains the single source of truth for the
full request history, Q&A, decisions, and test/outcome log. This file is a
snapshot of the plan itself plus the Phase 0 EPG-discovery findings, kept
in-repo for reference.

---

## Plan

All open questions (round 1 + follow-up A–F) resolved as of 2026-08-12.
Written Opus/X-High per CLAUDE.md Part 0, stage 3. Nothing below has been
implemented — this is the plan to freeze before any code is written.

---

### 1. Goals & non-goals (v1)

#### Goals

- Internal portal for Green Shadow Enterprises, behind a single shared admin
  password, that creates **US domestic** shipment labels through the ePost
  Global (EPG) API.
- **Single-label** generation from a form, with an optional per-label
  override of the "from" (shipper) address.
- **Bulk generation** from an uploaded Excel file: one EPG call per row,
  keep going past failures, and afterwards produce (a) a pass/fail report
  covering every row so bad rows can be fixed and re-uploaded, and (b) a zip
  of every PDF produced in that run.
- Every label is converted from EPG's **PNG** response to a **PDF** and saved
  into a directory that is configurable from inside the portal.
- **Search** past labels by partial recipient name / address / phone, and
  **filter** by a date range, fast enough to feel instant.
- **Download** any past label's PDF.
- **Void / cancel** a label through EPG, with cancelled labels still visible
  (and clearly marked) in the search and report views.
- **Count** how many labels have been generated (total, this month, voided).
- **Settings** in the portal: the global from-address profile, the save
  directory, the default service code, and the sandbox/production switch.
- UI that looks professional and matches `taxation-service`'s visual system.
- Deployed as Docker containers on the home server, with the save directory
  as a mounted volume, following the `docker-compose.yml` + `deploy.sh`
  convention already used by the sibling internal tools.

#### Non-goals (explicitly out of v1)

| Out of scope | Why |
|---|---|
| International shipments (`customs` object, the 20 international service codes, VAT/IOSS fields) | Answer 1: domestic only for v1. |
| Billing / cost calculation of any kind | Answer 7: dropped from requirements entirely. `/rate` is therefore only used as a safe authentication probe, never for pricing. |
| Manifest Close (`GET`/`POST /api/v1/Ship/Close`) | Answer D: the EPG doc never states closing is required for a label to be valid or collected. Follow the documentation, nothing more. |
| Per-user accounts, roles, audit log | Answer 8: one shared admin password. There is only ever one actor, so an actor column would always hold the same value. |
| Multi-carrier support, a carrier plugin layer, a rate-shopping engine | One carrier, one account. YAGNI. |
| Column-mapping wizard for the bulk upload | We define the template and hand it to the customer, so the columns are ours to fix. (This is the one place this project is deliberately *simpler* than `taxation-service`.) |
| Retry-from-the-portal of failed bulk rows | The report is downloadable and re-uploadable — that is the retry path Nitin asked for. An in-portal retry button is a nice-to-have, not a requirement. |
| `subAccount` support | EPG has not set one up for us. One nullable settings field can be added the day they do. |
| Cloud/S3 storage, notifications, analytics dashboards | Single self-hosted box; local volume is enough. |

---

### 2. Decision record

| # | Decision | Why |
|---|----------|-----|
| **D1** | **Split stack**: Next.js 15 (App Router, TS, Tailwind, shadcn/ui "new-york", light) web tier + a Python **FastAPI** backend, sharing one Postgres. | Confirmed by Nitin (follow-up E). Matches `taxation-service` exactly, so the "professional, like taxation-service" ask is satisfied by reusing its design tokens rather than inventing a look. The backend work (Excel parsing, PNG→PDF, HTTP to EPG) is all cheaper in Python. |
| **D2** | **The web tier is a pure UI over the backend's REST API.** No database access, no EPG access, no filesystem access from Next.js. | One schema owner (SQLAlchemy) instead of two that drift. One place that can spend money at the carrier. The web container never holds the DB URL or the EPG key. This is also what `taxation-service` converged on in practice — its backend lives in `engine/api`, its `web` is UI. |
| **D3** | **Single origin**: `next.config.ts` rewrites `/api/:path*` → `http://backend:8000/api/:path*`; the browser only ever talks to the web origin. | The session cookie is then same-origin — no CORS config, no `SameSite=None`, no extra nginx container to reverse-proxy the two. |
| **D4** | **Postgres 16**, schema defined by **numbered plain SQL migrations** in `migrations/` (`001_initial.sql`, …), applied at backend startup by a ~20-line runner that records applied filenames in a `schema_migrations` table. | Matches the `migrations/NNN_*.sql` convention already used by `kapoortraders-service`, `daily-purchase-tracker-kt` and `sheets-dashboard`. Alembic is a whole extra dependency and mental model for a five-table app. Auto-applying on startup means a deploy can't silently run old code against a new schema, or vice versa. |
| **D5** | **SQLAlchemy 2 (async) + asyncpg** for queries, Pydantic v2 for request/response schemas. | Same as `taxation-service`'s engine. No new stack to learn. |
| **D6** | **PNG → PDF via Pillow**, page size derived from the PNG's own DPI metadata (falling back to `LABEL_PDF_DPI_FALLBACK`, default 203). | One call (`img.save(path, "PDF", resolution=dpi)`), lossless Flate encoding — important, because a re-compressed barcode that a scanner can't read is a silent failure. Pillow is already the natural dependency for anything image-shaped. `img2pdf` is the named fallback if a real label's page size comes out wrong. |
| **D7** | **Bulk runs are a DB-backed queue**, drained by an **in-process asyncio poller** inside the backend container. It claims a run with `SELECT … FOR UPDATE SKIP LOCKED`; every row's outcome is written to `bulk_run_rows` as it happens. | A synchronous HTTP request cannot survive 200 rows × ~1–2 s of external API latency — it would time out at the proxy and the browser long before finishing. But Celery/Redis or a separate worker container is more infrastructure than this needs. A DB table + a poller in the same process is durable across restarts (the state is in Postgres, not in memory) with zero extra moving parts, and `SKIP LOCKED` keeps it correct even if a second replica ever appears. |
| **D8** | **A row that has already produced a label is never re-sent, and a timed-out `/ship` call is never auto-retried.** A crashed/restarted run resumes only the rows still marked `pending`; a call that timed out leaves its `labels` row in `pending` and surfaces on the dashboard as "needs checking". | Every `/ship` call is a real purchase from the carrier. "Retry on failure" is the correct instinct for most APIs and the wrong one here — a retry after a timeout may buy a second label for the same parcel. Per-row status is the mechanism that makes this safe, not an optimisation. |
| **D9** | **Search is one `ILIKE '%term%'` against a generated `search_text` column**, plus a b-tree index on `created_at` for the date filter. `pg_trgm` is **deferred**, with a named trigger: add it if the table passes ~100k rows or search p95 exceeds ~300 ms. | At this business's volume a sequential scan over a single short text column is single-digit milliseconds — already "fast partial match". The decisive point: adding `pg_trgm` later is *one migration* (`CREATE EXTENSION` + a GIN index on the same column) and **zero application code change**, because the query stays `ILIKE`. So starting simple costs nothing later. `tsvector` is rejected outright — it matches whole words, so "navd" would not find "Navdeep" and it handles addresses and phone numbers badly. |
| **D10** | Phone is stored **twice**: exactly as entered, and digits-only (`recipient_phone_digits`). Both are folded into `search_text`. | Correctness, not speed: `(609) 123-4567` must be findable by typing `6091234567`, and vice versa. Cheap to do at write time, impossible to do well at read time. |
| **D11** | **Storage root is fixed by env** (`LABEL_STORAGE_ROOT`, the mounted volume). The portal's configurable "save directory" is a **relative subpath under that root**, validated to reject `..`, absolute paths, and symlink escapes (`resolve()` then `is_relative_to(root)`). `labels.pdf_path` is stored **relative to the root** and is the only way the app ever locates a file. | Satisfies "directory is configurable in the portal" without giving a web application arbitrary write access to the host filesystem — which is what a free-form absolute path would mean. Storing the path relative also means the volume can be remounted somewhere else without rewriting every row. |
| **D12** | Every label **snapshots** the from-address and the service code it was actually created with, rather than referencing the settings row. | Settings change over time. A label that was printed in March must not appear to have a different return address in June. |
| **D13** | Store the full **EPG request JSON**, and the **response JSON with the label image payload stripped out**. | This API is under-documented (no sample payloads anywhere), so the stored request/response pair is the primary debugging tool when something goes wrong. Stripping the base64 image keeps rows small — the image already lives on disk as a PDF. |
| **D14** | **Admin auth**: shared password from `.env`, compared with `hmac.compare_digest`; on success issue a **JWT (HS256)** signed with `SESSION_SECRET` in an **HttpOnly, SameSite=Lax** cookie, `Secure` gated on `COOKIE_SECURE`, 12-hour expiry; a small in-memory failed-attempt lockout. Next.js `middleware.ts` only redirects to `/login` when the cookie is absent — **UX only, never the security boundary**; the backend re-checks the token on every request. | Simplest thing that is actually correct for one shared password: no sessions table to maintain, no revocation story needed for a single user (changing `SESSION_SECRET` logs everyone out, which is the whole revocation requirement here). Constant-time comparison avoids a timing oracle; the lockout blunts brute force. **Per CLAUDE.md Part 5 this whole piece is implemented at Opus X-High, not Sonnet.** |
| **D15** | **Bulk uploads get a preflight step.** Upload → parse + validate → the run is created as `draft` with counts and per-row errors shown → an explicit "Generate N labels" button moves it to `queued`. | Every row spends real money. A file with a shifted column or a wrong unit should be caught *before* 200 labels are bought, not reported afterwards. One extra status, large downside avoided. Flagged for Nitin in §12 since it wasn't asked for. |
| **D16** | **Effective unit = batch override ?? per-row column.** The upload screen's weight-unit and dimension-unit selectors each default to "use each row's own unit"; when set to a concrete unit they override that column for **every row in the file**. A row with neither an override nor a valid unit fails validation **before** any EPG call. | Exactly the rule Nitin confirmed in follow-up answer B. Implemented as described, not redesigned. It is also precisely the kind of small rule that goes silently wrong, so it gets its own unit tests (§10). |
| **D17** | **Convert everything to pounds and inches before calling EPG**, rounding **up** at 2 decimal places. Store both the raw value+unit as entered and the converted value actually submitted. | Pounds + inches is the standard for a US domestic small-parcel carrier — but this is an **unverified assumption**, see §6. Rounding up means we never under-declare weight or dimensions (under-declaring invites a carrier weight-adjustment charge; over-declaring by a hundredth of a pound does not). Storing both means that if the unit assumption turns out wrong, it is a re-derivation, not lost data. |
| **D18** | The bulk **report** and the bulk **zip** are generated **on demand at download time** from the DB and the PDFs on disk — not built and stored during the run. No `report_path` / `zip_path` columns. | One source of truth. A stored zip goes stale the moment a label in it is voided; a stored report goes stale the moment anything changes. Both are ~15 lines with stdlib `zipfile` / `openpyxl` over data we already have indexed by `bulk_run_id`, and it avoids keeping a second copy of every PDF on disk. |
| **D19** | **Void keeps the PDF on disk** and flips the label's status; voided labels stay in search results with a clear badge, plus a status filter (all / active / voided). | Deleting the file destroys the audit trail and gains nothing — disk is not the constraint. Answer 11 explicitly requires cancelled labels to be visible in the report/search view. |
| **D20** | The bulk Excel template is **fixed** and **downloadable from the portal**. Header matching is exact by name (case- and whitespace-insensitive); a file with missing or unknown columns is rejected up front with a message naming them. | If the customer always starts from the file the portal produced, a whole class of "wrong columns" failures disappears. Guessing at near-miss header names would trade a clear error today for a silently mis-mapped column tomorrow. |
| **D21** | Deploy as **three compose services** (`postgres`, `backend`, `web`) with the storage volume mounted into `backend`; `deploy.sh` prompts for a version, writes it into `web/src/version.ts`, and builds + pushes **both** images at the same tag. | Matches the sibling convention (`kapoortraders-service`, `daily-purchase-tracker-kt`, `sheets-dashboard`) and Nitin's existing bump-version-then-redeploy habit. Two images rather than one because Next.js needs a Node runtime and FastAPI needs Python; cramming both into one container with a supervisor is worse than one extra image. |
| **D22** | `APP_TIMEZONE=America/New_York`. `created_at` is `timestamptz`; date-range filters and the `YYYY/MM` storage folders are computed in that timezone. | The business is in Trenton, NJ. Without this, a label made at 8pm ET is filed under tomorrow's date and disappears from "today's labels". |
| **D23** | **Two EPG key env vars** — `EPG_API_KEY_SANDBOX` and `EPG_API_KEY_PRODUCTION`, both optional — with the portal's environment setting choosing between them. An environment with no key set is **not selectable** in the UI. | Makes it structurally impossible to point at the production URL without a deliberate production key being present. Costs about five lines. (Today only one key exists; §6 step 1 determines which slot it belongs in.) |
| **D24** | **No audit log table, no `activity_log`.** | Single shared admin: an actor column would hold the same value on every row forever. `created_at` / `voided_at` on the label already carry the only "who did what when" information that exists. |

---

### 3. High-level architecture

```
┌──────────────────────────────┐        ┌───────────────────────────────────┐
│ web  (Next.js 15, TS)        │        │ backend  (Python, FastAPI)        │
│ - login page                 │        │ - auth (shared password → JWT)    │
│ - dashboard / counts         │        │ - settings CRUD                   │
│ - single-label form          │ /api/* │ - EPG client (rate/ship/void)     │
│ - bulk upload + run detail   │───────►│ - unit conversion (→ lb / in)     │
│ - label search + detail      │rewrite │ - PNG → PDF (Pillow)              │
│ - settings                   │        │ - Excel parse/validate (openpyxl) │
│ - middleware: cookie present?│        │ - bulk poller (asyncio, in-proc)  │
│   → /login   (UX only)       │        │ - report .xlsx / zip on demand    │
└──────────────────────────────┘        └────────┬──────────────┬───────────┘
                                                 │              │
                                                 ▼              ▼
                              ┌────────── Postgres ──────────┐  │
                              │ app_settings · labels        │  │
                              │ bulk_runs · bulk_run_rows    │  │
                              │ schema_migrations            │  │
                              └──────────────────────────────┘  │
                                                                ▼
                                          storage volume (LABEL_STORAGE_ROOT)
                                            <save_dir>/<YYYY>/<MM>/*.pdf
                                            bulk/<run_id>/upload.xlsx
                                                                │
                                                                ▼
                                             https://[test_]api.epgparcels.com
```

**Single-label flow:** form → `POST /api/labels` → validate → insert `labels`
row as `pending` (so the id exists before any money is spent, and a crashed
call still leaves a trace) → build the EPG request with `referenceId =
SL-<id>` → `POST /api/v1/ship` → extract PNG → Pillow → PDF written under the
configured directory → update the row to `created` with tracking number,
`uniqueReferenceId`, and `pdf_path` → return the row → UI offers the download.

**Bulk flow:** upload → parse + validate all rows → `bulk_runs` (`draft`) +
one `bulk_run_rows` per data row → preflight summary shown → "Generate" →
`queued` → poller claims it → per row: rows already marked `invalid` are
skipped without touching EPG, valid rows go through the same single-label
path → run ends `completed` or `completed_with_errors` → report and zip are
generated on demand from `bulk_run_rows`.

**Download flow:** every PDF, report and zip is streamed through an
authenticated backend endpoint that looks the path up from the DB row. A raw
file path is never exposed and the storage directory is never served
statically.

---

### 4. Data model

Five tables. Schema lives in `migrations/001_initial.sql`, mirrored by
SQLAlchemy models in `backend/app/models.py`.

#### `app_settings` — exactly one row

Enforced single-row (`id smallint primary key default 1 check (id = 1)`).
Typed columns rather than a key/value bag: there is one settings record and
every field has a known type, so parsing strings back out would be pure
overhead.

| Column | Notes |
|---|---|
| `from_name`, `from_company`, `from_address1`, `from_address2`, `from_city`, `from_state`, `from_postal_code`, `from_phone`, `from_email` | The global shipper profile. Seeded from the sample label: Navdeep Bajaj / Green Shadow Enterprises / 293 Whitehead Rd / Trenton, NJ 08619-3250. |
| `from_country` | Fixed `'US'` in v1. |
| `label_directory` | Relative subpath under `LABEL_STORAGE_ROOT` (D11). Default `labels`. |
| `default_service_code` | `'EP03'` (Domestic Priority Parcel) or `'EP05'` (Domestic eDGE). |
| `epg_environment` | `'sandbox'` \| `'production'`. Picks both base URL and which key env var is used (D23). |
| `last_quota_available`, `last_quota_checked_at` | Mirrored from EPG's `X-Quota-*` response headers on the most recent call, shown on the dashboard. Our account's actual quota is undocumented, so seeing the live number matters. |
| `updated_at` | |

#### `labels` — one row per label ever attempted

| Column | Notes |
|---|---|
| `id` | `bigserial`. Also becomes EPG's `referenceId` as `SL-<id>` so their records correlate to ours. |
| `created_at` | `timestamptz`. Indexed descending — drives both the date-range filter and the default list order. |
| `status` | `pending` \| `created` \| `failed` \| `voided`. `pending` that never resolved = "needs checking" (D8). |
| `source` | `single` \| `bulk`. |
| `bulk_run_id` | Nullable FK → `bulk_runs`. Denormalised (the row also points back) so "all labels in run X" is a one-table query for the zip. |
| `service_code` | Snapshot of what was actually sent (D12). |
| `recipient_name`, `recipient_company`, `recipient_address1`, `recipient_address2`, `recipient_city`, `recipient_state`, `recipient_postal_code`, `recipient_country`, `recipient_phone`, `recipient_phone_digits`, `recipient_email` | `recipient_country` fixed `'US'` in v1. |
| `from_name` … `from_email` | Snapshot of the shipper block actually printed (D12) — global profile, or the single-label override. |
| `weight_value`, `weight_unit`, `weight_lb` | As entered (`oz` \| `kg` \| `lb`) and as submitted. |
| `length_value`, `width_value`, `height_value`, `dimension_unit`, `length_in`, `width_in`, `height_in` | All nullable — dimensions are optional. |
| `declared_value`, `currency_code` | `package.value` / `currencyCode`; currency fixed `'USD'` in v1. |
| `reference1` | Customer order/reference. Renders as a barcode on the label at ≤22 chars, plain text at ≥23 — the UI shows that hint next to the field. |
| `tracking_number` | Nullable until §6 step 3 tells us which response field carries it. |
| `unique_reference_id` | EPG's `uniqueReferenceId`. **Unique index.** This is the only key that can void the label — losing it means the label can never be cancelled. |
| `epg_request_json`, `epg_response_json` | `jsonb`; response stored with the label image payload stripped (D13). |
| `epg_error_code`, `epg_error_message` | Set when `status='failed'`, or on a timeout while `pending`. |
| `pdf_path`, `pdf_size_bytes` | Path relative to `LABEL_STORAGE_ROOT` (D11). |
| `voided_at`, `void_error` | |
| `search_text` | `GENERATED ALWAYS AS (…) STORED` — recipient name, company, address1, address2, city, state, postal code, phone, phone-digits, and `reference1` concatenated and lower-cased. One column to `ILIKE`, and exactly the column a future `pg_trgm` GIN index would sit on (D9). |

Indexes: `created_at DESC`, `status`, `bulk_run_id`, unique
`unique_reference_id`.

#### `bulk_runs` — one row per uploaded file

| Column | Notes |
|---|---|
| `id`, `created_at`, `started_at`, `finished_at` | |
| `status` | `draft` \| `queued` \| `running` \| `completed` \| `completed_with_errors` \| `failed`. |
| `source_filename`, `source_path` | The original upload, kept at `bulk/<run_id>/upload.xlsx` for audit and re-inspection. |
| `weight_unit_override`, `dimension_unit_override` | Nullable — null means "use each row's own unit column" (D16). |
| `default_service_code` | Snapshot of the settings default at upload time, so a mid-run settings change can't split a batch across two services. |
| `total_rows`, `valid_rows`, `success_count`, `failure_count` | |
| `error_message` | Run-level failure only (unreadable file, quota exhausted mid-run). |

#### `bulk_run_rows` — one row per Excel data row

| Column | Notes |
|---|---|
| `id`, `bulk_run_id`, `row_number` | `row_number` is the 1-based **data** row, and is shown in the report so the user can find it in their file. |
| `raw` | `jsonb` of the cells exactly as read — the report's "here's what you gave us" column and the reason the report can be regenerated on demand (D18). |
| `status` | `pending` \| `invalid` \| `success` \| `failed` \| `skipped`. `invalid` = failed validation, never sent to EPG. `skipped` = quota ran out before we got to it. |
| `validation_error` | Set at parse time. |
| `epg_error_code`, `epg_error_message` | Set at run time. |
| `label_id` | Nullable FK → `labels`. |
| `processed_at` | |

Index: `(bulk_run_id, status)` — drives resume-after-restart, the report, the
zip, and the live counts.

#### `schema_migrations`

`filename text primary key, applied_at timestamptz` — the migration runner's
bookkeeping (D4).

---

### 5. API surface (our backend, not EPG's)

All routes are under `/api`. Everything except `/api/health` and
`/api/auth/login` requires a valid session cookie.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Liveness for the compose healthcheck. Unauthenticated, returns no configuration detail. |
| `POST` | `/api/auth/login` | Body `{password}`. Constant-time compare; sets the session cookie. Rate-limited. |
| `POST` | `/api/auth/logout` | Clears the cookie. |
| `GET` | `/api/auth/me` | `{authenticated: true}` — lets the UI distinguish "logged out" from "backend down". |
| `GET` | `/api/settings` | From-address, save directory, default service code, EPG environment, plus which environments have a key configured (D23) and the last-seen quota. |
| `PUT` | `/api/settings` | Validates the save directory (D11), the state code, and the service code before writing. |
| `POST` | `/api/labels` | Single-label generation. Body: recipient block, package block (weight+unit, optional dims+unit, declared value, reference), optional `service_code`, optional `from_override` block. |
| `GET` | `/api/labels` | Search + filter + paginate. Params: `q` (partial name/address/phone/reference), `from_date`, `to_date` (interpreted in `APP_TIMEZONE`, D22), `status`, `bulk_run_id`, `page`, `page_size`. Returns rows + total. |
| `GET` | `/api/labels/{id}` | Full detail, including the stored EPG error if it failed. |
| `GET` | `/api/labels/{id}/pdf` | Streams the PDF as an attachment, path resolved from the DB row. |
| `POST` | `/api/labels/{id}/void` | Calls EPG `GET /api/v1/Ship/{uniqueReferenceId}/Void`. |
| `GET` | `/api/labels/stats` | Total, this month, voided, and `pending`-needs-checking counts for the dashboard. |
| `GET` | `/api/bulk/template` | Streams a freshly generated blank `.xlsx` with the locked headers (D20). |
| `POST` | `/api/bulk/uploads` | Multipart file + `weight_unit_override` + `dimension_unit_override`. Parses, validates, stores the file, creates a `draft` run. Returns counts and the per-row validation errors for the preflight screen. |
| `POST` | `/api/bulk/runs/{id}/start` | `draft` → `queued`. Rejected if the run is not `draft`. |
| `GET` | `/api/bulk/runs` | Run history with counts and status. |
| `GET` | `/api/bulk/runs/{id}` | Live status + counts; the run-detail page polls this every ~2 s while `running`. |
| `GET` | `/api/bulk/runs/{id}/report.xlsx` | Generated on demand (D18). Two sheets — see §7. |
| `GET` | `/api/bulk/runs/{id}/labels.zip` | Generated on demand from that run's successful rows. |

---

### 6. EPG integration — what we know, what we don't, and how we find out

The vendor doc is a summary, not a specification. Three real gaps block or
threaten the design, and all three are cheap to close empirically. **These
come first, before any feature work.**

#### Gap 1 — is the `.env` key sandbox or production?

The doc gives no way to tell from the key itself, and this was not
conclusively answered. It matters a great deal: building against production
means every test label is a real, chargeable purchase.

**Step:** a throwaway `tools/epg_probe.py` that sends one identical minimal
`POST /api/v1/rate` to **both** base URLs with the key, and prints HTTP
status, `X-Quota-*` headers, and the body — never the key. `/rate` is a
quote, not a purchase: safe, reversible, non-billable, and the only endpoint
we can probe without consequence. Whichever URL authenticates tells us which
environment we hold.

Two things to check first, in the same step:

- `https://test_api.epgparcels.com/` contains an **underscore in the
  hostname**, which is unusual and not universally resolvable. Confirm DNS
  resolves before concluding "sandbox rejected the key".
- Also **request the Postman collection** from ePost Global, which the doc
  says is available on request. It is very likely the fastest single answer
  to Gaps 2 and 3 together, and costs one email.

**Gate:** report the finding to Nitin before proceeding. If the key turns out
to be production-only, that is a decision for Nitin, not a silent choice —
see §12 item 3.

#### Gap 2 — what unit does EPG expect for weight and dimensions?

The doc never states it and there are no sample payloads.

**Working assumption (D17):** convert everything to **pounds and inches**
before calling — the near-universal default for a US domestic small-parcel
carrier. Explicitly flagged as **unverified**.

**Step:** once `/rate` authenticates, quote the same parcel twice with values
differing by a known factor (e.g. weight `1` vs `16`) and see whether the
returned rate moves the way pounds-vs-ounces would predict. The Postman
collection, or a one-line answer from the EPG onboarding rep, closes this
faster and more reliably than inference — ask for both. Storing the raw
value alongside the converted one (D17) means a wrong guess is a re-send, not
a data-loss event.

#### Gap 3 — how does the label image actually come back from `/ship`?

Unknown: base64 in a JSON field, a URL to fetch, or something else. **The
entire PNG→PDF pipeline depends on this**, so it must be answered before
Phase 2 is built, not discovered during it.

**Step:** one real sandbox `/ship` call, dumping the response's key structure
(keys and value types, not the whole base64 blob), then **immediately void
it**. The same call also answers two other unknowns: which field carries the
**tracking number**, and the exact spelling of `uniqueReferenceId` in a real
response.

**Design containment:** all of this lives behind one small function,
`extract_label_png(response) -> bytes`, which handles "base64 field" and
"URL to fetch" and raises clearly on anything else. Nothing downstream cares
which it was.

**Why PNG and not ZPL:** ZPL→PDF has no good offline path (the usual answer,
Labelary, is an external web service), whereas PNG→PDF is one Pillow call.
If PNG turns out to be problematic, that is a genuine escalation, not a
quiet fallback.

#### Gap 4 — the `/rate` response shape is undocumented

Not a blocker, because **billing is out of scope (answer 7)**. `/rate` is
used only as the safe authentication probe above. Worth stating plainly so
nobody later assumes rate parsing is a missing feature.

#### Other integration notes

- **Quota:** our account's limits are undocumented. Read `X-Quota-*` from
  every response, mirror the latest into `app_settings`, and show it on the
  dashboard. If a bulk run sees quota exhausted, stop the run, mark the
  remaining rows `skipped`, and record it on the run — do not keep hammering.
- **Rate limiting:** bulk rows are processed **sequentially**, one call at a
  time, with a small delay between them. Parallelism buys nothing here and
  risks tripping limits on an API whose limits we don't know.
- **429 / 5xx on a `/ship` call:** treated as a row failure, recorded, and
  the run continues. Not auto-retried (D8).
- **`stateOrProvince`** is required for domestic recipients — validated
  against the 50-state + DC + territories list before the call.

---

### 7. The bulk Excel template and the per-row flow

#### Template — final for v1

Locked as drafted and confirmed through the Q&A. Downloadable from the portal
(D20).

| # | Column | Maps to | Required |
|---|---|---|---|
| 1 | Recipient Name | `recipient.name` | Yes |
| 2 | Recipient Company | `recipient.company` | No |
| 3 | Address Line 1 | `recipient.address1` | Yes |
| 4 | Address Line 2 | `recipient.address2` | No |
| 5 | City | `recipient.city` | Yes |
| 6 | State | `recipient.stateOrProvince` | Yes |
| 7 | Postal Code | `recipient.postalCode` | Yes |
| 8 | Phone | `recipient.phone` | No |
| 9 | Email | `recipient.email` | No |
| 10 | Weight | `package.weight` (converted to lb) | Yes |
| 11 | Weight Unit | `oz` / `kg` / `lb` | Yes, unless a batch override is set |
| 12 | Length | `package.dimensions.length` (converted to in) | No |
| 13 | Width | `package.dimensions.width` | No |
| 14 | Height | `package.dimensions.height` | No |
| 15 | Dimension Unit | `inch` / `cm` | Required if any of L/W/H is given and no batch override is set |
| 16 | Declared Value | `package.value` | Yes |
| 17 | Reference / Order # | `package.reference1` (barcode at ≤22 chars) | No |
| 18 | Service Code | `EP03` / `EP05`; blank = settings default | No |

Fixed, not columns: `country = US`, `currencyCode = USD`, `labelFormat =
PNG`, and the `from` block (global profile — see §12 item 1).

#### End-to-end row flow

1. **Upload.** File + the two batch-level unit selectors. File is stored at
   `bulk/<run_id>/upload.xlsx`. A row cap (`BULK_MAX_ROWS`, default 500)
   rejects an accidental 10,000-row file before it can spend anything.
2. **Structural check.** Headers matched case/whitespace-insensitively
   against the 18 above. Missing or unknown columns → the whole file is
   rejected with those names listed. Nothing is created.
3. **Per-row validation** (no EPG calls at all in this stage):
   - required fields present and non-blank;
   - `State` is a real 2-letter US code; `Postal Code` is `NNNNN` or
     `NNNNN-NNNN`;
   - `Weight` is numeric and > 0; `Declared Value` is numeric and ≥ 0;
   - **effective weight unit** = batch override ?? row's `Weight Unit`; must
     be one of `oz`/`kg`/`lb`. Missing → invalid (D16);
   - if any of L/W/H is present, all three must be present and numeric, and
     the **effective dimension unit** (batch override ?? row's column) must
     be `inch`/`cm`;
   - `Service Code`, if present, must be `EP03` or `EP05`; blank → the run's
     snapshotted default.
   - Field-length limits are deliberately **not** invented — the doc states
     none, so an over-long address comes back as a real EPG error and is
     recorded as such rather than being rejected against a guessed rule.
4. **Preflight (D15).** `bulk_runs` = `draft`; the screen shows total /
   valid / invalid with every invalid row and its reason. Nothing has been
   spent yet.
5. **Start.** `draft` → `queued`. The poller claims the run.
6. **Per row, sequentially:** `invalid` rows are marked failed without
   touching EPG (saving quota and money). Valid rows go through the same
   path as a single label: build request → `/ship` → extract PNG → PDF to
   disk → `labels` row → mark the run row `success`. Any error →
   `failed` with the EPG code and message, **and the run keeps going**
   (answer 10). Counts update live so the UI can show progress.
7. **Finish.** `completed` if every row succeeded, `completed_with_errors`
   otherwise.
8. **Report** (`report.xlsx`, on demand, two sheets):
   - **`All Rows`** — every row: row number, status, error reason, and the
     values as submitted. The complete audit of what happened.
   - **`Failed Rows`** — the failed rows only, **in exactly the 18 template
     columns**, so the file can be opened, corrected, and re-uploaded
     directly with no reshaping. This is the retry path Nitin asked for.
9. **Zip** (`labels.zip`, on demand): every PDF from that run's successful
   rows, named the same as on disk.

---

### 8. Repo / file structure

Matches the sibling convention (`backend/` + `migrations/` +
`docker-compose.yml` + `deploy.sh`) with `web/` named as in
`taxation-service`.

```
shipmentlabel-service/
  README.md
  PLAN.md                      # this plan, copied into the repo at Phase 1
  .gitignore                   # MUST be the first file created — see §9
  .env                         # already exists (API_KEY); gitignored
  .env.example                 # committed, values blanked
  docker-compose.yml           # postgres + backend + web + storage volume
  deploy.sh                    # version prompt → build + push both images
  documents/                   # already present: EPG API PDF, sample label PDF
  migrations/
    001_initial.sql
  tools/
    epg_probe.py               # §6 gap-closing script, kept for re-checks
  backend/
    Dockerfile
    pyproject.toml
    app/
      main.py                  # app + startup: run migrations, start poller
      config.py                # env loading, typed settings
      db.py  models.py  schemas.py
      security.py              # password compare, JWT issue/verify, deps
      storage.py               # path validation + resolution (D11)
      units.py                 # oz/kg → lb, cm → in, rounding (D17)
      pdf.py                   # PNG → PDF (D6)
      epg/
        client.py              # HTTP, auth header, quota headers, errors
        mapping.py             # our model → EPG request; extract_label_png
      bulk/
        template.py            # blank .xlsx generator
        parse.py               # read + validate (D16)
        runner.py              # the poller and per-row loop (D7, D8)
        report.py              # report.xlsx + labels.zip (D18)
      routers/
        health.py  auth.py  settings.py  labels.py  bulk.py
    tests/
      test_units.py  test_bulk_parse.py  test_bulk_runner.py
      test_report.py  test_storage.py  test_auth.py  test_pdf.py
      test_void.py
      integration/test_epg_sandbox.py    # opt-in, network, quota-consuming
  web/
    Dockerfile  package.json  next.config.ts  tailwind.config.ts
    src/
      version.ts               # written by deploy.sh
      middleware.ts            # cookie-presence redirect (UX only)
      app/
        login/page.tsx
        (dashboard)/layout.tsx           # nav + shell
        (dashboard)/page.tsx             # counts, quota, needs-checking
        (dashboard)/new/page.tsx         # single label
        (dashboard)/bulk/page.tsx        # upload + run history
        (dashboard)/bulk/[id]/page.tsx   # preflight, progress, downloads
        (dashboard)/labels/page.tsx      # search + date filter + status
        (dashboard)/labels/[id]/page.tsx # detail, download, void
        (dashboard)/settings/page.tsx
      components/{ui,app}/
      lib/api.ts
  storage/                     # gitignored; the mounted volume in Docker
    <save_dir>/<YYYY>/<MM>/<YYYY-MM-DD>_<tracking>_<id>.pdf
    bulk/<run_id>/upload.xlsx
```

**PDF filename:** `<YYYY-MM-DD>_<tracking>_<id>.pdf`, tracking sanitised to
`[A-Za-z0-9-]` with `notrack` as the fallback, and the label id guaranteeing
uniqueness. Readable when Nitin opens the folder in Finder, collision-proof,
and never the thing the app relies on to find a file — that is always
`labels.pdf_path` (D11).

**Env vars:** `EPG_API_KEY_SANDBOX`, `EPG_API_KEY_PRODUCTION`,
`DATABASE_URL`, `ADMIN_PASSWORD`, `SESSION_SECRET`, `SESSION_HOURS` (12),
`COOKIE_SECURE`, `LABEL_STORAGE_ROOT` (`/data`),
`LABEL_PDF_DPI_FALLBACK` (203), `APP_TIMEZONE` (`America/New_York`),
`BULK_MAX_ROWS` (500); `BACKEND_URL` for the web container only. The existing
`API_KEY` is renamed into the correct slot once §6 step 1 says which one.

---

### 9. Security notes

- **`.gitignore` is the very first file created.** The repo currently has one
  commit (`README.md` only) and **no `.gitignore`**, while `.env` — holding
  the live EPG bearer token — sits untracked in the working tree. A single
  `git add -A` would commit it. This is a real, present exposure and gets
  fixed before anything else: ignore `.env`, `storage/`, `__pycache__/`,
  `node_modules/`, `.next/`, `*.xlsx` under `storage/`.
- **Admin auth is implemented at Opus X-High**, per CLAUDE.md Part 5's
  carve-out for authentication and secret boundaries — not at Sonnet with the
  rest of the build. See D14 for the mechanism.
- The EPG key **never leaves the backend container** and is never logged,
  never returned by an endpoint, and never written into a task doc or a
  stored request JSON (the `Authorization` header is stripped before
  `epg_request_json` is persisted).
- **Uploads:** only `.xlsx`/`.xls` accepted, size-capped, row-capped, and
  parsed with `openpyxl` in read-only data-only mode. Stored under a
  server-generated path — the client-supplied filename is recorded as a
  string but never used to build a path.
- **Path traversal** on `label_directory` is the one place user input reaches
  the filesystem; it is validated by resolution + containment check (D11) and
  has its own test.
- **Downloads** are always streamed through an authenticated endpoint that
  resolves the path from the DB. The storage directory is never mounted into
  the web container or served statically.
- **Accepted limits, stated plainly:** a JWT cannot be revoked before it
  expires — rotating `SESSION_SECRET` is the "log everyone out" lever, which
  is sufficient for one shared password. `COOKIE_SECURE` must be turned on
  once this sits behind HTTPS; if it runs plain-HTTP on the LAN, the session
  cookie is visible on the wire and that is a conscious trade, not an
  oversight.
- **Double-submit is a money bug, not just a UX bug**: the single-label
  "Generate" button disables on submit and the bulk "Generate N labels"
  button is behind a confirm dialog showing the count.

---

### 10. Testing plan (CLAUDE.md Part 6)

This is new functionality, so the requirement is tests for the new logic
using the stack's natural framework — `pytest` for the backend (as
`taxation-service` and `kapoortraders-service` already use).

#### Backend unit tests — the logic that is easy to get silently wrong

| File | Covers |
|---|---|
| `test_units.py` | `oz→lb` (/16), `kg→lb` (×2.2046226218), `lb→lb`, `cm→in` (/2.54), `inch→inch`; rounding **up** at 2 dp so nothing is ever under-declared; zero/negative/non-numeric weight rejected; unknown unit string rejected. |
| `test_bulk_parse.py` | Missing/unknown headers reject the file with the names listed; each required field missing → that row `invalid` with a readable reason; per-row unit used when no batch override; **batch override wins over the row column, weight and dimensions independently**; neither present → invalid; partial L/W/H → invalid; blank Service Code → run default; invalid Service Code → invalid row; bad state code and bad postal code rejected; row cap enforced. |
| `test_bulk_runner.py` | With a faked EPG client: 5 rows where rows 2 and 4 fail → run ends `completed_with_errors`, counts 3/2, all 5 rows present, 3 `labels` rows and 3 PDFs on disk. **Restart-resume:** re-running the poller over a half-finished run does not re-send rows already `success` (D8). A timed-out row leaves its `labels` row `pending` and is not retried. Quota exhaustion stops the run and marks the rest `skipped`. |
| `test_report.py` | The report has both sheets; `All Rows` has one row per data row including the successful ones; **`Failed Rows`'s headers are byte-identical to the template's headers**, so a corrected report can be re-uploaded without reshaping. The zip contains exactly the successful rows' PDFs. |
| `test_storage.py` | `label_directory` values of `../..`, `/etc`, and a symlink pointing outside the root are all rejected; a valid subpath resolves inside the root; `pdf_path` round-trips relative→absolute. |
| `test_auth.py` | Wrong password → 401 and no cookie; right password → cookie with HttpOnly/SameSite set; protected route without a cookie → 401; tampered and expired tokens → 401; lockout after N failures. |
| `test_pdf.py` | A known PNG converts to a PDF whose page box is the expected physical size (4×6 in = 288×432 pt at 203 DPI), and whose DPI is taken from the PNG's metadata when present. |
| `test_void.py` | Void flips `status` and sets `voided_at`; a second void is rejected; an EPG error leaves the status unchanged and records `void_error`; a voided label still appears in search and its PDF still downloads. |

#### Integration test — against the EPG **sandbox** only

`tests/integration/test_epg_sandbox.py`, marked `@pytest.mark.integration`
and **skipped unless `EPG_API_KEY_SANDBOX` is set**. Not part of the default
suite: it needs network and consumes real quota. One `/rate` call, then one
`/ship` → assert we can extract label bytes and a tracking number → then
`Void` it in the same test, in a `finally`, so it never leaves a live label
behind. Hard rule: this test may never be pointed at the production base URL.

#### Web tier

`npm run lint` and `npm run typecheck` are the baseline and must pass — that
is exactly what `taxation-service/web` configures, and it has no test runner.
No Jest/Vitest is added speculatively: all the tricky logic (unit override,
validation, conversion) lives in the backend by design, so the UI stays thin
enough that a type error is the realistic failure mode. If a genuinely tricky
client-side rule appears during the build, add a runner then. A single
Playwright login→generate smoke test is noted as a possible later addition,
not built now.

#### Acceptance walk-through (the Part 6 "trace every layer" requirement)

Once Phase 3 is done, one deliberate end-to-end pass, verified by hand, not
by reading code: Excel cell → parsed row → effective unit → converted lb/in →
EPG request JSON → EPG response → PNG bytes → PDF on disk at the right
physical size → `labels` row → appears in search by partial name, by street,
and by unformatted phone → downloads correctly → **prints and the barcode
scans**. The print/scan step is the one that cannot be faked in a test and is
the actual definition of "this works".

---

### 11. Phased roadmap

Ordered so the only genuine unknown — how the real EPG API behaves — is
closed first, not discovered in week three.

| Phase | Contents | Done when |
|---|---|---|
| **0 — EPG discovery (blocking)** | Add `.gitignore` (§9). Email EPG for the Postman collection. DNS-check both base URLs. Run `tools/epg_probe.py` `/rate` against sandbox and production to determine which environment the key belongs to. If sandbox authenticates: one `/ship`, dump the response structure, identify the label payload mechanism, tracking field and `uniqueReferenceId`, probe the unit question, then **void it immediately**. | Nitin has a written answer to all three gaps in §6. **Phase 2 does not start until Gap 3 is closed.** |
| **1 — Scaffolding, auth, settings** | Repo layout, `docker-compose.yml`, `001_initial.sql` + migration runner, `/api/health`. Admin login and session (**Opus X-High**), login page, middleware redirect. Settings API + page, including save-directory validation and the environment switch. Next.js shell with the taxation-service design tokens. | Log in, save settings, restart the whole stack, settings persist and the session behaves correctly. Runs in parallel with Phase 0's waiting time — it depends on nothing EPG-related. |
| **2 — Single label, end to end** | EPG client + request mapping, unit conversion, `extract_label_png`, PNG→PDF, storage write, `labels` row lifecycle including `pending`. Single-label form with the from-address override and the ≤22-char reference hint. | A real sandbox label is generated, the PDF opens at 4×6, **it prints and the barcode scans**, and the row is in the DB with its `uniqueReferenceId`. |
| **3 — Bulk** | Template download, upload + parse + validate, preflight screen, run start, poller, per-row processing, live progress, report (two sheets), zip. | A 10-row file with 3 deliberately bad rows produces 7 PDFs, a report listing all 10 with reasons, a zip of 7, and restarting the backend mid-run neither duplicates a label nor loses the run. |
| **4 — Search, filter, download, counts** | `GET /api/labels` with `q` / date range / status, the labels list and detail pages, PDF download, dashboard counts and quota display. | Partial searches on name, street and unformatted phone all hit; the date range is correct for a label created at 8pm ET (D22); every count matches the DB. |
| **5 — Void** | Void endpoint, confirm dialog, status badge, status filter, idempotency guard. | A sandbox label is voided, shows as cancelled in search, its PDF still downloads with a warning, and a second void is refused. |
| **6 — Deploy** | Dockerfiles, `deploy.sh`, `.env.example`, README run/deploy instructions, storage volume mount, production key switched in, first deploy to the home server. | Running on the server, labels landing in the mounted directory. **Per CLAUDE.md Part 5 the deploy itself needs Nitin's explicit go-ahead**, as does the first production-environment label. |

---

### 12. Open items for Nitin

Judgment calls made while writing this, worth an explicit yes/no rather than
being decided silently.

| # | Item | Recommendation |
|---|---|---|
| 1 | **Can bulk rows override the "from" address?** The Q&A confirmed one global from-address profile with a single-label override, but never said whether bulk rows can override too. | **No per-row from-address in bulk.** A batch is normally all shipped from the same place, and 9 extra columns on every row for a value that will be identical is noise that invites typos. The global profile applies to every bulk label. Easy to add later if a real case appears. |
| 2 | **The bulk preflight step (D15)** — parse and validate, show counts and bad rows, then require an explicit "Generate N labels" click. Not requested. | **Keep it.** Every row is a real purchase; catching a shifted column before spending is worth one extra click. Say if you'd rather it just run on upload. |
| 3 | **If the `.env` key turns out to be production-only** (§6 gap 1). | **Ask EPG for a sandbox key** before building further — developing against production means buying and voiding real labels. If no sandbox key is obtainable, the fallback is developing against production with an immediate void after every test call, done manually and never from the automated test suite. Your call, not mine. |
| 4 | **Admin password form in `.env`** — plaintext compared with a constant-time compare, vs a bcrypt hash. | **Plaintext + constant-time compare.** The same `.env` already holds the EPG key, which is the more valuable secret, so hashing the password protects against nothing the key isn't already exposed to — and it removes a "generate the hash" step from every password change. Say the word and it becomes a bcrypt hash. |
| 5 | **Save directory as a validated subpath under a fixed mounted root** (D11), not a free-form absolute path. | Recommended as planned. Worth confirming this still reads as "configurable in the portal" to you — you'd type e.g. `labels` or `GreenShadow/labels`, not `/Users/…`. |
| 6 | **Voided labels keep their PDF on disk** and stay in search with a badge. | Recommended. Confirm you don't want the file deleted on cancel. |
| 7 | **Report format** — one `.xlsx` with an `All Rows` sheet and a `Failed Rows` sheet in the exact template shape, rather than a CSV. | Recommended: the second sheet is directly re-uploadable, which is the retry loop you asked for. |
| 8 | **Row cap per bulk file** — `BULK_MAX_ROWS`, proposed **500**. | Confirm the number. It exists to stop an accidental 10,000-row file from spending real money. |
| 9 | **Session length 12 hours**, and no per-device revocation (rotating `SESSION_SECRET` logs out everything). | Confirm 12h suits how you actually use it. |
| 10 | **Timezone `America/New_York`** for date filters and folder dates (D22). | Recommended — the business is in Trenton. |
| 11 | **Docker image names** for `deploy.sh` — proposed `<your-dockerhub-namespace>/shipmentlabel-service-api` and `-web`, versioned together. | Confirm the namespace and whether you'd rather have one combined image. |
| 12 | **`documents/` is currently untracked** along with `.env`. The PDFs contain only Green Shadow's own address (no customer data), so committing them is fine — but `.env` must be ignored before any `git add`. | Add `.gitignore` first (Phase 0), then commit `documents/` if you want the API doc in the repo. |

## Codex review

Skipped. Nitin moved straight to "start development" on 2026-08-27 instead
of requesting the review — treated as declining GCDR for this plan rather
than re-asking, per his explicit instruction to just build and correct later.

## Decisions

**2026-08-27 — plan frozen, implementation authorized.** Nitin: "the key is
sandbox, so you can use it as a test key and it will [be] configured in the
UI. Start the development of backend and frontend. I will provide changes
later. Complete it end to end with tests. push the code to
https://github.com/nitkap01/shipmentlabel-service".

- **Gap 1 (sandbox vs production) resolved by Nitin directly:** the `.env`
  key is confirmed **sandbox**. Renamed into `EPG_API_KEY_SANDBOX`. No
  production key exists yet — `epg_environment` defaults to `sandbox` and
  `production` is not selectable in the UI until a production key is added
  (D23 as written).
- **All 12 "open items for Nitin" (§12) accepted as recommended**, since
  Nitin said he'll provide changes later rather than answer each now:
  1. No per-row from-address override in bulk. 2. Bulk preflight step kept.
  3. N/A — key is confirmed sandbox. 4. Admin password stored plaintext in
  `.env`, compared with `hmac.compare_digest` (not hashed). 5. Save directory
  is a validated relative subpath under `LABEL_STORAGE_ROOT`. 6. Voided
  labels keep their PDF on disk. 7. Bulk report is `.xlsx` (two sheets).
  8. `BULK_MAX_ROWS=500`. 9. 12-hour session length. 10. Timezone
  `America/New_York`. 11. Docker image names `nitkap01/shipmentlabel-service-api`
  and `nitkap01/shipmentlabel-service-web` (matches the GitHub namespace
  given for the push). 12. `.gitignore` added first (done), `documents/`
  committed since it holds no customer data.
- Gaps 2 (unit) and 3 (label byte format) to be closed empirically in Phase 0
  via `tools/epg_probe.py` against the confirmed sandbox key before Phase 2
  (single-label) is built, per the plan's own gate.
- Admin auth (D14) implemented with extra care per CLAUDE.md Part 5's
  security carve-out, even though the rest of the build runs at Sonnet 5.

## Phase 0 — EPG discovery findings (2026-08-27)

All three real gaps from §6 closed empirically against the sandbox host
(`https://test_api.epgparcels.com`), via `tools/epg_probe.py`-style calls
(one real `/ship` + immediate `/Void`, plus several `/rate` boundary probes).
No secrets printed anywhere in this process.

- **Gap 1 (sandbox vs production):** the key authenticates on **both**
  `test_api.epgparcels.com` and `api.epgparcels.com` (same account,
  `X-Quota-AccountId: 12184`) — EPG's doc statement "sandbox gives full
  access to all the API calls available on Production" is literally true
  here. The Void response for the one real test shipment explicitly said
  **"Package detected as Test Mode package"** — confirms this account/key
  behaves as sandbox/test regardless of which base URL is called. Portal
  still defaults to the sandbox base URL per D23; production stays
  unselectable until a distinct production key is added later.
- **Gap 2 (units) — corrected, was wrong in the plan.** The API's own error
  text is unambiguous: `"100 did not meet maximum weight requirement of
  480 oz"` → **weight is in ounces**, not pounds as D17 assumed.
  `"999.0 did not meet maximum length requirement of 30 inches"` →
  **dimensions are in inches**, as assumed. **D17 is amended:** convert
  everything to **ounces + inches** before calling EPG (not pounds+inches).
- **Gap 3 (label bytes) — resolved.** A real sandbox `/ship` call
  (service `EP05`) returned `wasSuccessful: true`,
  `package.trackingNumber` ("EPG451119100000017"),
  `package.uniqueReferenceId` (the Void key), and
  **`package.labels`: an array of base64-encoded PNG strings** (verified by
  the `iVBORw0KGgo...` PNG magic-number prefix). `extract_label_png` reads
  `package.labels[0]`, base64-decodes it, done. The shipment was voided
  immediately after inspection, confirmed `"Test Mode Package processed
  internally"`.
- **New, unplanned finding: `customs` is required by this account's live
  API even for a pure domestic US→US shipment**, contradicting the doc
  (which frames `customs` as an EU/UK/VAT concern). Minimal shape that
  satisfies it: `customs.description` (string) + `customs.items` with at
  least one item (`quantity`, `code`, `name`, `value`, `hsCode`,
  `originManufactureCountry`). **Decision:** the backend sends a fixed,
  internal, non-user-facing customs block on every shipment (generic
  description, one item mirroring the package's own declared value/name),
  so the "domestic only, no customs UI" promise to Nitin holds — this is a
  vendor implementation quirk, not a product requirement, and gets no
  Excel column or form field.
- **Also observed, not a blocker:** `EP03` (Domestic Priority Parcel)
  returned `"No rate was returned for this service"` for every address
  tried on this account, while `EP05` (Domestic eDGE) worked end-to-end.
  Both service codes stay selectable in the UI as planned — if `EP03`
  really isn't provisioned on this account, that surfaces as a normal EPG
  error at generation time, which is the documented, expected failure mode
  (D8), not something to special-case in code.
- `/rate` response shape (Gap 4, not a blocker since billing is out of
  scope): `{wasSuccessful, responseMessage, rateErrors[], package: {rates:
  [{productCode, serviceName, accountNumber, sortFacilityId,
  sortFacility, baseCharge, totalCharge, extraInsurance}], ...}}`.

**Phase 2 gate (per §11) is now clear** — proceeding to scaffolding (Phase 1)
and the EPG client (Phase 2) with the corrected unit and customs handling.

