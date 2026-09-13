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
the current evaluation checklist. The agent-facing usage skill is at
[skills/mcv/SKILL.md](skills/mcv/SKILL.md).

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
mcv --semester 2026/1 courses list
mcv courses list --all
mcv courses 2110575

# Course video playlist
mcv courses 2110575 playlist

# Materials and folders
mcv courses 2110575 materials list
mcv courses 2110575 materials folders
mcv courses 2110575 materials list --folder "Week 1"
mcv courses 2110575 materials show 12345 12346
mcv courses 2110575 materials list --folder "Week 1" --refs
mcv courses 2110575 materials archive "Week 1" \
  --output ./week-1.zip
mcv courses 2110575 materials archive "Week 1" \
  --output ./week-1.tar
mcv courses 2110575 materials archive "Week 1" \
  --output ./week-1.tar.gz
mcv courses 2110575 materials download 12345 --output ./lecture.pdf

# Read-only assignment and announcement views
mcv courses 2110575 assignments list
mcv courses 2110575 assignments show 2160997
mcv courses 2110575 assignments show --full 2160997
mcv courses 2110575 assignments list --ids
mcv courses 2110575 assignments list --refs
mcv courses 2110575 announcements list
mcv courses 2110575 announcements show 2177455

# Other student-facing course pages
mcv courses 2110575 meetings list
mcv courses 2110575 meetings list --include-past
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
pages are direct actions: use `courses 2110575 playlist`,
`courses 2110575 about`, and `courses 2110575 portfolio`. Playlist results
preserve nested folders and expose read-only video metadata such as titles,
providers, ids, thumbnails, durations, watch percentages, and source URLs.
They do not download or play videos.

Assignment details use a compact human-readable question-set view by default.
Use the assignment-specific `--full` option when you need worksheet ids,
question types, instructions, grading metadata, and all assignment links. This
only changes human-readable output; `--json` and `--jsonl` always return the
complete structured assignment data.

Running `mcv courses COURSE` is shorthand for the course overview. It shows
the resolved CourseVille id, course number, title, semester, section, and
student role.

`courses list` and all course-scoped commands default to the current semester
selected by MyCourseVille. `--semester` is a global course-selection option,
so put it before `courses`. Use `--all` to query every available semester:

```bash
mcv --semester 2025/2 courses list
mcv --semester 2025/2 courses 2110575
mcv --semester 2025/2 courses 2110575 assignments list
mcv --semester 2025/2 courses 2110575 materials list
```

`--semester` and `--all` cannot be used together.

`courses COURSE materials folders` shows folder ids and material counts. A folder can
be selected by name or id. `materials archive` creates an archive using the
downloadable files in that folder, refuses to overwrite an existing output
unless `--force` is supplied, and reports materials that have no downloadable
file. The archive operation uses temporary files and only replaces the
destination after the archive is complete.

The archive format is inferred from the output name first: `.zip` creates ZIP,
`.tar` creates an uncompressed TAR, and `.tar.gz` (or `.tgz`) creates a gzip-
compressed TAR. An unrecognized or missing extension defaults to ZIP. Use
`--format zip`, `--format tar`, or `--format tar.gz` to override inference.

For shell composition, `--ids` prints one material id per line. This makes it
possible to pass a folder selection directly to the detail command, like a
Docker id pipeline:

```bash
mcv courses 2110575 materials show \
  $(mcv courses 2110575 materials list --folder "Week 1" --ids)
```

`--refs` prints canonical course-qualified references in the form
`mcv:<resource-type>:<cv_cid>:<item_id>`. These references are safe to use
without separately carrying the course id:

```bash
mcv courses 2110575 materials show \
  $(mcv courses 2110575 materials list \
    --folder "Week 1" --refs)

mcv courses 2110575 assignments show mcv:assignment:86428:2160997
```

## Shell completion and local cache

Install completion for the current shell:

```bash
uv run mcv --install-completion
```

Completion is deliberately cache-only. It never logs in, makes a network
request, or blocks the shell while MyCourseVille is unavailable. Populate or
refresh it after login:

```bash
mcv courses list                         # also indexes returned course refs
mcv cache refresh                        # current-semester courses
mcv cache refresh 2110575 2110521        # selected courses
mcv cache refresh --all-semesters        # every semester exposed by the site
mcv cache status
mcv cache clear
```

The cache stores only completion metadata such as course numbers, folder names,
resource titles, canonical refs, semester values, and grouping ids. It does
not store cookies, passwords, resource bodies, signed URLs, or meeting
credentials. It is isolated by the active profile and login provider under the
platform cache directory. A missing or corrupt cache simply produces no
dynamic candidates.

The cache refresh accepts either no course arguments or multiple specific
course references. `--all-semesters` cannot be combined with specific course
arguments. Refresh reports per-course failures and leaves the previous
snapshot for a resource scope that could not be fetched.

Long-running multi-request commands show a compact progress display on stderr:

```bash
mcv courses list --all
mcv assignments list
mcv cache refresh
```

Use `--quiet`/`-q` to suppress progress while preserving the intended result.
Progress is automatically disabled for `--json` and `--jsonl`, so machine
output remains safe to pipe:

```bash
mcv --quiet --json assignments list | jq '.[] | .ref'
```

Use `--json` with `--select`/`--fields` when a structured projection is more
useful than line-oriented ids:

```bash
mcv --json courses 2110575 materials list \
  --folder "Week 1" --select cv_cid,itemid
```

`courses COURSE materials show` accepts one or more material ids or qualified
material references. With `--json --ids`, the producer emits the raw id array
instead of shell-oriented lines.

Use `--jsonl` for any list/detail command when downstream tools expect one
JSON value per line:

```bash
mcv --jsonl courses 2110575 assignments list | jq -s 'map(.itemid)'
```

By default, `--json` prints the actual JSON value and `--jsonl` prints one
actual value per line. This keeps the common Unix pipelines direct: use
`.[]` for a JSON list and `.field` for a JSONL record. If a versioned protocol
envelope is useful, opt into it explicitly:

```bash
mcv --json --envelope courses 2110575 assignments list
mcv --jsonl --envelope courses 2110575 assignments list
```

The envelope has the shape `{"schema_version": 1, "data": ...}` (or one such
object per JSONL line). Existing v1 fields are not renamed or removed; new
fields may be added. Machine errors are flat JSON by default and use the same
versioned `error` wrapper only with `--envelope`.

Without `--json` or `--jsonl`, each resource uses a human-oriented display:
lists are tables, detail results are labeled summaries, meetings include their
join link and recordings, and download/archive results use short completion
messages. Human mode does not fall back to printing resource objects as JSON.

Assignment and announcement detail commands are read-only. Meeting detail
lists provider information and available recordings; it does not open or join
the meeting, so it cannot mark attendance as a side effect. `portfolio` is a
read-only summary of the currently exposed points/rank information.

Add `--json` before the command for script-friendly output:

```bash
mcv --json courses list
mcv --json auth status
```

## Cross-course resource commands

Use these commands when the question is about a resource across the current
semester rather than one course:

```bash
mcv assignments list
mcv assignments list --pending
mcv assignments list --due
mcv assignments list --pending --refs

mcv announcements list
mcv announcements list --refs

mcv meetings list
mcv meetings list --include-past
mcv meetings list --refs
```

Cross-course commands attach `course_no`, `cv_cid`, and the canonical `ref` to
machine-readable addressable resources. Raw `--ids` is intentionally not
available because an id without its course namespace is ambiguous.

Meeting lists exclude meetings whose scheduled time has passed by default.
Use `--include-past` to include them. Meeting records expose `url`, which
prefers the direct `join_url` and falls back to the MyCourseVille
`detail_url`.

## Universal resource lookup

Addressable resources use the generic reference format:

```text
mcv:<resource-type>:<cv_cid>:<resource-id>
```

Currently supported resource types are `material`, `assignment`,
`announcement`, and `meeting`. Course-level playlists use the special form
`mcv:playlist:<cv_cid>` (there is no playlist item id). Resolve one or more
mixed references with:

```bash
mcv get mcv:assignment:86428:2160997
mcv get "https://www.mycourseville.com/?q=courseville/worksheet/78748/1889560"
mcv get mcv:playlist:78748
mcv get \
  "https://www.mycourseville.com/?q=courseville/course/78748/playlist"
mcv get \
  mcv:assignment:86428:2160997 \
  mcv:material:86428:2160993

mcv assignments list --pending --refs | xargs -r -n 20 mcv get
```

`mcv get` also accepts supported HTTPS URLs copied directly from MyCourseVille.
The URL is validated against the official host and normalized to the same
canonical resource reference before fetching; it never fetches an arbitrary
URL. Supported URL forms include course playlist pages, assignment worksheets,
material content nodes, announcement content nodes, and meeting detail pages.

Use `--jsonl` for batch lookup when individual failures should be represented
alongside successful records:

```bash
mcv --jsonl get \
  mcv:assignment:86428:2160997 \
  mcv:material:86428:2160993
```

`mcv get --jsonl` writes success and error records to stdout in input order and
returns nonzero if any lookup fails. Other machine-mode errors are written to
stderr.

Assignment detail output keeps the worksheet detail page separate from an
optional submission page. Rich-text instruction links are normalized to
absolute URLs, and file-based assignments expose submitted files as the
`submission_files` list when MyCourseVille provides them.
Question-set work modes are exposed separately as `question_set_submission`
with the visible action/title, worksheet status, optional link, submission
timestamp, and the extracted questions. Each question includes its prompt,
type, answer, choices, points, and any answer key/feedback visible to the
student. This is read-only metadata for now; it is not a question-set answer
or submission API.

In human-readable mode, `get` displays every referenced resource with its
resource-specific detail format, separated by a blank line. Use the list
commands when a compact table is desired:

```bash
mcv get \
  mcv:assignment:86428:2160997 \
  mcv:material:86428:2160993

mcv courses 2110575 assignments list
```

Machine output is unchanged: `--json` returns one JSON value (an array for
multiple references), and `--jsonl` returns one resource per line.

## Python API and package boundaries

The reusable client is `mcv_cli.api.MCVAPI`. Resource models, parsers,
endpoints, and transport live under `mcv_cli.api`; it does not import Typer,
Rich, CLI options, completion, cache, or terminal progress. Human rendering
and JSON serialization live under `mcv_cli.presentation`, command wiring under
`mcv_cli.cli`, and authentication, storage, cache, completion, and progress
under `mcv_cli.runtime`.

```python
from mcv_cli.api import MCVAPI
from mcv_cli.runtime.auth import AuthManager
from mcv_cli.runtime.config import Settings

manager = AuthManager(settings=Settings())
with MCVAPI(manager) as api:
    course = api.courses.resolve("2110575")
    playlist = api.playlists.get(course.cv_cid)
    materials = api.materials.list(course.cv_cid)
    assignment = api.get("mcv:assignment:86428:2160997")
```

Cross-course queries are exposed by `mcv_cli.api.aggregates`; presentation
and CLI concerns are not part of the API model or client contracts.

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
/?q=courseville/course/{cv_cid}/assignment
/?q=courseville/course/{cv_cid}/playlist
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
interactive grading system. Course playlist pages are supported as read-only
metadata trees, including nested folders and the video identifiers/URLs exposed
by the page. Playback, stream resolution, download, and progress mutation are
outside the API. Web resources are supported when they are present in the
course page.
