# mcv

`mcv` is a small, unofficial command-line client for reading MyCourseVille
course content from Unix systems.

It is designed around one simple workflow:

```text
discover course content → get a stable reference → retrieve the resource
```

The client is read-only against MyCourseVille. It can download files and create
local archives, but it does not submit, upload, edit, delete, join meetings,
control attendance, or mutate CourseVille data. The upstream web behavior is
reverse-engineered and may change without notice.

## Upstream coupling

This project relies heavily on MyCourseVille's current authenticated HTML and
AJAX structure. A purely visual CSS change may not affect it, but changes to
HTML elements, classes, data attributes, page routes, form fields, CSRF/session
behavior, AJAX parameters, or response shapes can cause the CLI and Python API
to stop working until the parsers or clients are updated.

That coupling is intentional for this unofficial read-only client. When the
site changes, check authentication first, then the affected route/parser and
the authenticated smoke checks documented in [showcases.md](showcases.md).

## Quick start

The project requires Python 3.11 or newer and uses [`uv`](https://docs.astral.sh/uv/)
for its environment and locked dependencies.

```bash
uv sync
uv run mcv --help
```

The command is `mcv`; the Python distribution is `mcv-cli`.

## Authentication

Log in with a Chula account:

```bash
uv run mcv auth login --type chula
```

For a MyCourseVille platform account:

```bash
uv run mcv auth login --type platform --email
```

The login command prompts for the password. Passwords are not accepted as
command-line arguments and are never stored. `--username` or `MCV_USERNAME`
can provide the non-secret username without a prompt.

Check or remove the stored session:

```bash
uv run mcv auth status
uv run mcv auth logout
```

Session cookies are stored in the OS keyring when available. If no keyring
backend is available, `mcv` uses an AES-GCM encrypted local file; set
`MCV_STORAGE_PASSPHRASE` for non-interactive use of that fallback. Treat the
stored session as a bearer-like credential.

This credential-based MVP does not implement Google login or require a
MyCourseVille OAuth client. Browser OAuth and the public mobile API are outside
the current authentication boundary.

## Course-first CLI

The primary command grammar is:

```text
mcv courses COURSE RESOURCE ACTION [ARGS] [OPTIONS]
```

`COURSE` may be a CourseVille id, course number, or exact current-semester
course title. Use the global `--semester` option before the command when a
different semester is needed.

```bash
# Discover courses and inspect one course
mcv courses list
mcv courses list --all
mcv courses 2110575
mcv --semester 2025/2 courses list

# Materials and folders
mcv courses 2110575 materials list
mcv courses 2110575 materials folders
mcv courses 2110575 materials list --folder "Week 1"
mcv courses 2110575 materials show 2160993

# Assignments and announcements
mcv courses 2110575 assignments list
mcv courses 2110575 assignments list --all
mcv courses 2110575 assignments show 2160997
mcv courses 2110575 assignments show --full 2160997
mcv courses 2110575 announcements list
mcv courses 2110575 announcements show 2177455

# Meetings, schedule, and course pages
mcv courses 2110575 meetings list
mcv courses 2110575 meetings list --all
mcv courses 2110575 meetings list --include-past
mcv courses 2110575 schedule list
mcv courses 2110575 playlists
mcv courses 2110575 about
mcv courses 2110575 groups list
mcv courses 2110575 portfolio
mcv courses 2110575 web-resources list
```

Course-level pages such as `playlists`, `about`, and `portfolio` are direct
actions. Other collections generally use `list`, while identifier-bearing
resources use `show`.

For list and search commands, put `--all`/`-a` after the action to show the
expanded human table with useful identity columns such as raw ids, canonical
refs, and available summary fields:

```bash
mcv courses list --all
mcv courses 2110575 materials list --all
mcv courses 2110575 meetings list --all
mcv search "docker" --all
```

On `courses list`, `--all` currently expands the columns for the selected or
current semester. It does not select every semester; a future global option
may provide that behavior. The existing `mcv cache refresh --all-semesters`
operation remains the explicit all-semester cache operation.

Assignments, announcements, meeting metadata, and course pages are read-only.
Assignment details expose the information visible to the student, including
question-set and submission metadata when available; they do not answer or
submit work. Meetings expose available links and recordings without opening or
joining them.

## References and shell pipelines

Use `--ids` only when the receiving command already has a course context. Use
`--refs` when the result will be passed between commands or across courses:

```bash
mcv courses 2110575 materials list --folder "Week 1" --ids
mcv courses 2110575 materials list --folder "Week 1" --refs
mcv courses 2110575 materials list --folder "Week 1" --all
```

Canonical references have a course-qualified form:

```text
mcv:<resource-type>:<cv_cid>:<item_id>
```

Course playlists use the special course-level form
`mcv:playlist:<cv_cid>`. Resolve one or more references with `mcv get`:

```bash
mcv get mcv:assignment:86428:2160997
mcv get mcv:material:86428:2160993
mcv get \
  mcv:assignment:86428:2160997 \
  mcv:material:86428:2160993
```

The same lookup accepts supported official MyCourseVille URLs:

```bash
# Assignment worksheet
mcv get "https://www.mycourseville.com/?q=courseville/worksheet/78748/1889560"

# Material content node
mcv get "https://www.mycourseville.com/?q=courseville/course/123/view_content_node_9_material"

# Course playlist page
mcv get "https://www.mycourseville.com/?q=courseville/course/78748/playlist"
```

`mcv get` also accepts supported HTTPS URLs copied from MyCourseVille. URLs are
restricted to the official host and normalized to the same typed reference; an
arbitrary URL is never fetched.

For shell composition, keep one reference per line and use `xargs`:

```bash
set -o pipefail
mcv assignments list --pending --refs | xargs -r -n 20 mcv get
```

## Machine-readable output

Human output uses resource-specific tables and detail views. Put global output
options before the command when producing data for another program:

```bash
mcv --json courses 2110575 assignments list
mcv --jsonl assignments list --pending
mcv --jsonl get \
  mcv:assignment:86428:2160997 \
  mcv:material:86428:2160993
```

`--all`/`-a` is a human-table display option. It does not change JSON or JSONL
schemas, search limits, filters, or the one-reference-per-line behavior of
`--refs` and `--ids`.

The output modes are:

- `--json` emits one JSON document, using an object or array as appropriate.
- `--jsonl` emits one JSON value per line for streaming and batch processing.
- `--envelope` adds the explicit `schema_version` and `ok` protocol fields.
- `--quiet`/`-q` suppresses progress and status output.

JSONL `get` is an intentional batch protocol: successes and failures are
written in input order and the process exits nonzero if any lookup fails. Use
`--envelope` when consumers need an unambiguous success/error discriminator.

## Local cache and search

The local store is one SQLite file with separate logical namespaces:

```text
SQLite local store
├── completion index
└── resource snapshots + FTS search index
```

Completion is cache-only and never blocks on authentication or the network.
Normal successful API requests update the local projections on a best-effort
basis. The search cache stores only allow-listed projections of searchable
materials, assignments, announcements, meetings, and playlist pages. It does
not store cookies, passwords, signed URLs, submission files, feedback, or
meeting credentials.

Manage the local store explicitly:

```bash
mcv cache status
mcv cache refresh
mcv cache refresh 2110575 2110521
mcv cache refresh --all-semesters
mcv cache clear completion
mcv cache clear search
mcv cache clear all
```

The cache clear targets are independent: clearing `completion` preserves
search, clearing `search` preserves completion, and `all` clears both. A bare
`mcv cache clear` is intentionally invalid.

Search is local by default and never performs hidden network requests:

```bash
mcv search "docker"
mcv courses 2110575 search "docker"
mcv search "docker" --all
mcv courses 2110575 search "docker" --all
mcv search "docker" --type material --type assignment --limit 20
mcv search "docker" --refs
mcv --json search "docker"
mcv --jsonl search "docker"
```

Use `--refresh` when the relevant course data should be fetched before the
same local search runs:

```bash
mcv search "docker" --refresh
mcv courses 2110575 search "docker" --refresh
```

Search results are compact summaries with canonical references. Human output
highlights matched text in titles and snippets, including the actual title
word rescued by typo-tolerant matching. Pass a result reference to `mcv get`
when the full resource is needed.

## Downloads and archives

Material files can be downloaded to a local path:

```bash
mcv courses 2110575 materials download 2160993 \
  --output ./lecture.pdf
```

Archive a material folder locally:

```bash
mcv courses 2110575 materials archive "Week 1" \
  --output ./week-1.zip
```

The archive format is inferred from the output extension. `.zip`, `.tar`,
`.tar.gz`, and `.tgz` are supported; an unrecognized or missing extension
defaults to ZIP. Use `--format` to select the format explicitly. Existing
files are not overwritten unless `--force` is supplied.

## Python API

The reusable client is `mcv_cli.api.MCVAPI`. It is independent of Typer, Rich,
CLI options, terminal progress, and shell completion.

```python
from mcv_cli.api import MCVAPI
from mcv_cli.runtime.auth import AuthManager
from mcv_cli.runtime.cache import CacheStore
from mcv_cli.runtime.config import Settings

manager = AuthManager(settings=Settings())
store = CacheStore(profile_name="default", provider="chula")

with MCVAPI(manager, cache_store=store) as api:
    course = api.courses.resolve("2110575")
    results = api.search.search(
        "docker",
        cv_cid=course.cv_cid,
        resource_types={"material", "assignment"},
        limit=20,
    )
    resource = api.get(results[0].ref) if results else None
```

The public API also provides resource clients such as `api.materials`,
`api.assignments`, `api.meetings`, and `api.playlists`, cross-course services
under `api.aggregates`, and `api.get_many()` for ordered multi-reference
retrieval.

`api.search.search()` never performs network I/O. It requires an injected local
store and returns `SearchResult` summaries whose `ref` can be passed directly
to `api.get()`. Addressable domain models expose typed, non-serialized
`resource_type` and `ref` properties.

The canonical public exception name is `MCVError`. Common subclasses include
`AuthenticationRequired`, `AuthenticationError`, `InvalidReferenceError`,
`UnsupportedResourceError`, `NotFoundError`, `AmbiguousError`,
`TransportError`, `ParseError`, `DownloadError`, and
`SearchUnavailableError`. Exceptions expose structured fields such as
`code`, `resource`, `operation`, `retryable`, and `details`; callers do not
need to parse exception text.

Raw CourseVille temporal values remain available for faithful access. Typed
convenience properties return standard `date`, `time`, or timezone-aware
`datetime` values. Naive timestamps are interpreted as `Asia/Bangkok`; aware
timestamps are converted there; malformed or sentinel values return `None`.

## Architecture

The project keeps the reusable API, terminal presentation, and runtime policy
separate:

```text
CLI commands
    │
    ▼
MCVAPI and resource clients
    │
    ▼
parsers and Pydantic domain models
    │
    ├── presentation: human tables and machine serialization
    └── runtime: auth, storage, cache, completion, and progress
```

The API layer talks to the authenticated MyCourseVille HTML/AJAX surface and
converts upstream changes into typed errors. The project does not use browser
automation as a fallback and does not expose write operations.

## Reference projects and session context

The following references were used during the project sessions. The first is
especially important because it informed the authentication design:

- [CEDT-Chula/mcv-api-python-unofficial](https://github.com/CEDT-Chula/mcv-api-python-unofficial) — primary prior art for the MyCourseVille session-cookie authentication flow and reverse-engineered Python interaction model.
- [MyCourseVille](https://www.mycourseville.com/) — the upstream service whose authenticated pages and resource behavior this client reads.

These references are interoperability and research sources, not runtime
dependencies or claims of affiliation. This project is an independent,
read-only client.

## Development

Install the locked development environment and run the same checks used by CI:

```bash
uv sync
uv run pytest -q
uv run ruff check .
uv run pyright
```

For the complete command showcase, Python API contract, route coverage, data
models, and evaluation notes, see [showcases.md](showcases.md). Agent-facing
CLI guidance is in [skills/mcv/SKILL.md](skills/mcv/SKILL.md).
