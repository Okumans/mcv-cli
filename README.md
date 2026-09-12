# mcv

`mcv` is a small command-line client for reading MyCourseVille course content
on Unix systems.

This is a demo-phase interface. Breaking CLI and machine-output changes are
allowed while the course-scoped API settles.

The MVP uses the session-cookie login flow documented by
[CEDT-Chula/mcv-api-python-unofficial](https://github.com/CEDT-Chula/mcv-api-python-unofficial).
It does not require a MyCourseVille OAuth `client_id` or `client_secret`.

## Development setup

This project uses `uv`:

```bash
uv sync
uv run mcv --help
```

The executable is `mcv`; the distribution package is named `mcv-cli`.

See [showcases.md](showcases.md) for the complete CLI/Python API showcase and
the current evaluation checklist.

## Login

Log in with a Chula account:

```bash
uv run mcv auth login --type chula
```

Or use the shortcut:

```bash
uv run mcv auth login --chula
```

The command prompts for the username and password. The password is sent only
to the MyCourseVille login form and is never stored. The login flow first
initializes a MyCourseVille web session, obtains the current CSRF token, posts
the credentials to the current form action, follows same-site redirects, and
verifies the resulting session through the authenticated web homepage.

For a MyCourseVille platform account:

```bash
uv run mcv auth login --type platform
uv run mcv auth login --platform --email
```

`--type mcv` is retained as a compatibility alias for `--type platform`.
`--username` or `MCV_USERNAME` can provide the non-secret username without a
prompt. The password is intentionally not accepted as a command-line option
because it would be exposed in shell history and process listings.

Google login is not supported by this credential-based MVP. Google requires a
browser OAuth flow; supporting it without an approved MyCourseVille OAuth
client would require a separate browser/cookie-import design.

Check or clear the stored session:

```bash
uv run mcv auth status
uv run mcv auth logout
```

## Course-centric content commands

The course-first commands accept either the internal CourseVille id (`cv_cid`)
or the course number shown by `courses list`. They resolve courses in the
current semester by default.

```bash
mcv courses list
mcv courses list --semester 2026/1
mcv courses list --all
mcv courses 2110575

# Materials and folders
mcv courses 2110575 materials list
mcv courses 2110575 materials folders
mcv courses 2110575 materials list --folder "Week 1"
mcv courses 2110575 materials show 12345 12346
mcv courses 2110575 materials list --folder "Week 1" --unique-ids
mcv courses 2110575 materials archive "Week 1" \
  --output ./week-1.zip --format zip
mcv courses 2110575 materials archive "Week 1" \
  --output ./week-1.tar --format tar
mcv courses 2110575 materials download 12345 --output ./lecture.pdf

# Read-only assignment and announcement views
mcv courses 2110575 assignments list
mcv courses 2110575 assignments show 2160997
mcv courses 2110575 announcements list
mcv courses 2110575 announcements show 2177455

# Other student-facing course pages
mcv courses 2110575 meetings list
mcv courses 2110575 meetings show 29632
mcv courses 2110575 schedule list
mcv courses 2110575 about
mcv courses 2110575 groups list
mcv courses 2110575 portfolio
mcv courses 2110575 web-resources list
```

The supported grammar is `mcv courses COURSE RESOURCE ACTION [ARGS] [OPTIONS]`,
similar to a Docker Compose command scope. The course may be a CourseVille id
or course number. Command-specific options follow the action, for example
`courses 2110575 materials list --folder "Week 1"` and
`courses 2110575 materials archive "Week 1" --format tar`. Singular course
pages are direct actions: use `courses 2110575 about` and
`courses 2110575 portfolio`.

Running `mcv courses COURSE` is shorthand for the course overview. It shows
the resolved CourseVille id, course number, title, semester, section, and
student role.

`courses list` defaults to the current semester selected by MyCourseVille.
Use `--semester` to select one semester explicitly; `--yearsem` remains an
alias for compatibility. Use `--all` to query every available semester.

`courses COURSE materials folders` shows folder ids and material counts. A folder can
be selected by name or id. `materials archive` creates a ZIP or uncompressed
TAR using the downloadable files in that folder, refuses to overwrite an
existing output unless `--force` is supplied, and reports materials that have
no downloadable file. The archive operation uses temporary files and only
replaces the destination after the archive is complete.

For shell composition, `--ids` prints one material id per line. This makes it
possible to pass a folder selection directly to the detail command, like a
Docker id pipeline:

```bash
mcv courses 2110575 materials show \
  $(mcv courses 2110575 materials list --folder "Week 1" --ids)
```

`--unique-ids` prints course-qualified references in the form
`mcv-material:<cv_cid>:<item_id>`. These references are safe to use without
separately carrying the course id:

```bash
mcv courses 2110575 materials show \
  $(mcv courses 2110575 materials list \
    --folder "Week 1" --unique-ids)
```

Use `--json` with `--select`/`--fields` when a structured projection is more
useful than line-oriented ids:

```bash
mcv --json courses 2110575 materials list \
  --folder "Week 1" --select cv_cid,itemid
```

`courses COURSE materials show` accepts one or more material ids or qualified
material references. With `--json --ids`, the producer emits the id array in
the versioned `data` field instead of shell-oriented lines.

Use `--jsonl` for any list/detail command when downstream tools expect one
JSON value per line:

```bash
mcv --jsonl courses 2110575 assignments list | jq -s 'map(.data.itemid)'
```

Each JSON document has the shape `{"schema_version": 1, "data": ...}`. Each
JSONL record has the same envelope on one line. Existing v1 fields are not
renamed or removed; new fields may be added. Error envelopes use the same
schema and include a machine-readable `code`, plus `resource`, `operation`,
and `retryable` when applicable.

Assignment and announcement detail commands are read-only. Meeting detail
lists provider information and available recordings; it does not open or join
the meeting, so it cannot mark attendance as a side effect. `portfolio` is a
read-only summary of the currently exposed points/rank information.

Add `--json` before the command for script-friendly output:

```bash
mcv --json courses list
mcv --json auth status
```

## Credential storage

The MVP stores one `default` profile. It uses the Unix OS keyring when
available. If no keyring backend is available, it stores an AES-GCM encrypted
file at the platform-specific `mcv` config directory, normally
`~/.config/mcv/credentials.enc`.

The raw MyCourseVille password is never stored. The persisted values are the
authenticated MyCourseVille session cookies, including the Laravel session,
CSRF, and session-key cookies. These cookies are bearer-like credentials, so
protect the keyring or the storage passphrase. Set `MCV_STORAGE_PASSPHRASE` for
non-interactive use of the encrypted-file fallback.

## API boundary

The current implementation uses the reverse-engineered cookie-authenticated
HTML/AJAX routes used by existing MyCourseVille clients:

```text
/?q=courseville
/?q=courseville/ajax/cvhomepanel_get_filter
/?q=courseville/ajax/course
/?q=courseville/ajax/getactivepanelcontent
/?q=courseville/course/{cv_cid}/assignment
/?q=courseville/course/{cv_cid}/meeting
/?q=courseville/course/{cv_cid}/schedule
/?q=courseville/course/{cv_cid}/about
/?q=courseville/course/{cv_cid}/group
/?q=courseville/ajax/cvpagegroup_getgroupcardlisting
/?q=courseville/course/{cv_cid}/portfolio-{student_id}
```

The `/api/v1/public/*` endpoints used by some mobile clients require an OAuth
bearer access token; a web session cookie alone is not sufficient for them.
These routes are not official public API documentation. Endpoint, form,
cookie, HTML, and response-shape changes are converted into clear CLI errors
rather than silently falling back to browser automation. The MVP intentionally
contains no write, attendance, submission, upload, join, or notification
operations.

Assessment-platform pages (`/map`) are deferred because they are a separate
interactive grading system. Kaltura/media-gallery pages are also deferred:
the current page launches an external LTI flow and does not expose a stable
playlist API in the authenticated course HTML. Web resources are supported
when they are present in the course page; no playlist scraping is attempted
until a stable, read-only source can be identified.
