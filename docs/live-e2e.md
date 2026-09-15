# Authenticated live end-to-end checks

The live suite is read-only and opt-in. It never submits work, uploads files,
edits data, joins meetings, changes attendance, plays videos, or stores raw
upstream pages.

## Host calibration

Authenticate the host first and verify the session without printing cookies:

```bash
mcv auth status
mcv auth login
```

Run discovery with a temporary cache root:

```bash
MCV_LIVE_E2E=1 \
MCV_E2E_DISCOVER_FIXTURES=1 \
MCV_E2E_FIXTURE_REPORT=/tmp/mcv-e2e-fixtures.json \
uv run pytest -m live -q
```

Calibration runs `mcv --all --json courses list`, cross-checks course discovery
through `MCVAPI`, prefers completed terms before `2025/2`, and favors previous
instances whose titles contain Network or Fund Oral. It probes each candidate
through both adapters twice. A transport, authentication, HTTP, or parser
failure is a failed candidate; it is never converted into an empty or
unsupported result. The selected report contains only course selectors,
semester/cv_cid values, boolean section availability, canonical refs, and
sanitized official MyCourseVille URLs.

The report is account-specific and must not be committed. It may be copied to
protected CI variables or supplied as `MCV_E2E_FIXTURE_FILE` from a protected
secret/artifact store.

## Configured matrix

The normal live run requires `MCV_LIVE_E2E=1`,
`MCV_E2E_SEMESTER`, and `MCV_E2E_PRIMARY_COURSE`:

```bash
MCV_LIVE_E2E=1 uv run pytest -m live -q
```

The primary/secondary course selectors may be cv_cids, course numbers, or
exact titles. A cv_cid is preferred because it identifies one semester
instance. Optional values include:

```text
MCV_E2E_SECONDARY_COURSE
MCV_E2E_SEARCH_QUERY
MCV_E2E_*_REF
MCV_E2E_*_URL
MCV_E2E_*_AVAILABLE
MCV_E2E_SECONDARY_*_REF
MCV_E2E_SECONDARY_*_URL
MCV_E2E_SECONDARY_*_AVAILABLE
MCV_E2E_PRIMARY_ARCHIVE_FOLDER
MCV_E2E_DOWNLOAD_AVAILABLE
MCV_E2E_ARCHIVE_AVAILABLE
```

`*_AVAILABLE` is used for calibrated optional behavior. `true` means the
section returned a valid present or empty collection; `false` means the typed
optional section was unavailable. Downloads and archives are tested only when
their availability and material/folder selectors are explicitly configured.

The matrix invokes the installed `mcv` entry point in a subprocess and the
Python `MCVAPI` facade separately. Assertions are semantic: valid JSON/JSONL,
Pydantic model types, positive ids, nonblank required labels, canonical refs,
course association, official URL normalization, dereferenceability, search
highlight/plain-text behavior, and independent cache clearing. Counts,
ordering, dates, and exact course content are not snapshots.

## Fixture refresh

Rerun host calibration when a fixture has an intentional course-content change,
when a scheduled live run reports a legitimate optional-section change, or
when the account/semester is rotated. Review the sanitized report before
updating protected CI values. Do not copy cookies, passwords, signed URLs,
meeting passwords, assignment feedback, or raw HTML into a fixture.

## CI safety

The live job logs in for each run with protected username/password secrets,
disables the keyring, and uses ephemeral credential and cache directories. It
runs only on protected default-branch pushes, release tags, schedules, and
manual dispatches. It is not enabled for fork pull requests. See
[docs/ci.md](ci.md) and [docs/account-rotation.md](account-rotation.md).
