---
name: mcv
description: Use the mcv CLI to read and compose MyCourseVille course content on Unix, including session authentication, course/resource lookup, cached completion, local search, archives, and JSON pipelines; do not use it for write or submission actions.
metadata:
  short-description: Read MyCourseVille content with mcv
---

# mcv

Use this skill when a task needs authenticated, browser-free access to
MyCourseVille content through the local `mcv` command-line client.

The client is read-only against MyCourseVille. It can download files and create
local archives, but it must not be treated as a submission, assessment, meeting
join, Kaltura, or attendance-control interface.

## Host execution boundary

When this skill is used from an isolated coding sandbox, run authenticated or
live `mcv` commands in the host environment, outside the sandbox. The host
OS keyring and host MCV configuration contain the authenticated session; a
sandboxed `mcv` process has a separate home directory, keyring, and config and
will commonly report `authenticated False` even when the host session works.

In Codex, use the approved host/unsandboxed execution path for commands such
as `mcv auth status`, `mcv auth login`, course discovery, live probes, and live
resource reads. Do not use a sandboxed authentication result as evidence that
the account is logged out, and do not copy keyring databases, cookies,
passphrases, or raw credentials into the workspace. Sandbox execution is
appropriate only for offline tests, mocks, and deliberately isolated local
cache checks. If host execution is unavailable, report that boundary instead
of attempting to authenticate against the sandbox.

## Invocation

When working in this repository, prefer:

```bash
 mcv ...
```

Use `mcv ...` directly only when the package has already been installed or is
on `PATH`.

Before querying content, check the session:

```bash
 mcv auth status
```

For an interactive Chula login:

```bash
 mcv auth login --type chula
```

Platform-account login is also supported:

```bash
 mcv auth login --type platform
 mcv auth login --type platform --email
```

The password is prompted for and is not accepted as a command-line argument.
The tool persists authenticated session cookies using the OS keyring when
available, or an encrypted local fallback. Never print, log, or paste those
cookies, storage passphrases, signed URLs, meeting passwords, or raw passwords.

The credential-based MVP does not support Google login because it has no
approved MyCourseVille OAuth `client_id` and `client_secret`. Do not invent
OAuth credentials or replace this flow with browser automation.

## Course-scoped queries

The primary grammar is:

```text
mcv courses COURSE RESOURCE ACTION [ARGS] [OPTIONS]
```

`COURSE` may be a `cv_cid`, course number, or exact current-semester course
title. The current semester is the default for course resolution. To resolve
a course from another semester, pass the global `--semester` option before the
command. Repeat it to combine exact semesters, use a year prefix to select all
terms in that year, or use global `--all` for every available semester on
semester-wide collection commands:

```bash
 mcv --semester 2025/2 courses list
 mcv --semester 2025/2 courses 2110575
 mcv --semester 2025/2 courses 2110575 assignments list
 mcv --semester 2025/2 courses 2110575 materials list
 mcv --semester 2025/1 --semester 2026/1 courses list
 mcv --all courses list
```

Most course resources use an explicit action such as `list` or `show`. Course
pages and local search are direct actions, so use `mcv courses COURSE search
QUERY` without an extra `list` or `show`.

Useful commands:

```bash
 mcv courses list
 mcv --semester 2026/1 courses list
 mcv --all courses list
 mcv courses list --all
 mcv --all courses list --all
 mcv courses 2110575

 mcv courses 2110575 playlists

 mcv courses 2110575 materials list
 mcv courses 2110575 materials folders
 mcv courses 2110575 materials list --folder "IoT Hardware"
 mcv courses 2110575 materials show 2160993
 mcv courses 2110575 assignments list
 mcv courses 2110575 assignments show 2160997
 mcv courses 2110575 assignments show --full 2160997
 mcv courses 2110575 announcements list
 mcv courses 2110575 announcements show 2177455
 mcv courses 2110575 meetings list
 mcv courses 2110575 meetings list --include-past
 mcv courses 2110575 meetings show 29632
 mcv courses 2110575 schedule list
 mcv courses 2110575 about
 mcv courses 2110575 groups list
 mcv courses 2110575 portfolio
 mcv courses 2110575 web-resources list
 mcv courses 2110575 search "docker"
```

Meeting lists show today's not-yet-past events by default. Use
`--include-past` to show meetings from all dates, including past events. Meeting
results expose a preferred `url`, using the direct join URL when available and
otherwise the detail page.

Assignment `show` uses a compact student-facing display by default. For a
question-set assignment, each question is rendered as one numbered heading
containing the prompt and point value, followed by checkbox choices and the
student's answer:

```text
1. Which answer is correct? (1 point)
  ☐ First choice
  ☑ Second choice
  Answer: Second choice
```

Use the assignment-specific `--full` option for worksheet ids, question types,
instructions, grading/status metadata, answer keys when visible, assignment
links, and submission details. `--full` affects human output only; `--json`
and `--jsonl` always expose the complete structured assignment model.

## Cross-course queries and refs

Use top-level resource commands when the task spans the current courses:

```bash
 mcv assignments list
 mcv assignments list --pending
 mcv announcements list
 mcv meetings list --include-past
```

Raw ids are only safe inside a known course namespace. Use `--refs` when a
result will be passed to another command:

```bash
 mcv courses 2110575 materials list --refs
 mcv assignments list --pending --refs
```

Canonical refs have this form:

```text
mcv:<resource-type>:<cv_cid>:<resource-id>
```

Current individually dereferenceable types are `material`, `assignment`,
`announcement`, and `meeting`. Course-level playlists use the special
reference `mcv:playlist:<cv_cid>` without an item id. Resolve one or more mixed
refs with:

```bash
 mcv get mcv:assignment:86428:2160997
 mcv get "https://www.mycourseville.com/?q=courseville/worksheet/78748/1889560"
 mcv get mcv:playlist:78748
 mcv get "https://www.mycourseville.com/?q=courseville/course/78748/playlist"
 mcv get \
  mcv:assignment:86428:2160997 \
  mcv:material:86428:2160993
```

`mcv get` accepts supported HTTPS URLs copied from MyCourseVille as well as
canonical refs. The URL is restricted to the official host and normalized
into the same typed ref before the client fetches the resource; it does not
fetch arbitrary URLs. Supported URL forms include course playlist pages,
assignment worksheets, material content nodes, announcement content nodes, and
meeting detail pages.

Playlist output is read-only metadata. It preserves nested folders and can
include video titles, providers, ids, thumbnails, durations, watch percentages,
and source/embed URLs; it does not play, download, or mutate video progress.

The playlist page is a course-level collection: one course can contain several
playlists. `mcv courses COURSE playlists`, `mcv get mcv:playlist:COURSE_ID`, and
the equivalent MyCourseVille URL all expose a `PlaylistCollection`. Its JSON
has `available` and `playlists`; human output displays the contained playlists
and videos directly. A missing optional playlist section is
`available: false` with an empty list, while an empty present section is
`available: true` with an empty list.

For shell composition, use one ref per line and `xargs`:

```bash
set -o pipefail
 mcv courses 2110575 materials list \
  --folder "IoT Hardware" --refs \
  | xargs -r -n 20  mcv get
```

In human mode, every reference is rendered using its resource-specific detail
display and separated by a blank line. Use the course-scoped `list` commands
when a compact table is preferred. `--json` and `--jsonl` retain their machine
output contracts: an array for multiple resources in JSON mode, and one raw
resource per line in JSONL mode. `mcv --jsonl get` is a batch protocol: success
and error records are both written to stdout in input order, while the command
returns nonzero if any lookup fails. Add `--envelope` for explicit
`{"ok": true, "data": ...}` and `{"ok": false, "error": ...}` discriminants.

## Human and machine output

Default output is for humans. Each resource type has a dedicated display:
collections use resource-specific tables, details use labeled summaries, and
downloads/archives use concise completion messages. Human mode should not be
parsed as JSON. Collection tables use colored headers and portable ASCII
separators with the outer edge disabled; labeled detail views are borderless.
Keep that styling in human mode while leaving JSON and JSONL output unstyled.

The course-scoped assignment detail command uses its compact display unless
`--full` is supplied. `mcv get REF...` always uses the full resource display so
mixed-resource dereferencing remains informative. In the compact question-set
view, `☑` means the student selected the choice and `☐` means they did not; the
marks do not indicate correctness.

Use machine modes explicitly:

```bash
 mcv --json courses 2110575 assignments list
 mcv --jsonl assignments list --pending
 mcv --jsonl get \
  mcv:assignment:86428:2160997 \
  mcv:material:86428:2160993
```

`--json` emits the JSON value itself. `--jsonl` emits one JSON value per line.
Use `--envelope` only when a versioned wrapper is needed; it is not part of
ordinary machine output. Put global output options before the command.

Use `--ids` only when the receiving command already has the course context.
Use `--refs` for reusable, cross-course-safe addresses. Errors go to stderr;
machine modes serialize them as JSON.

Assignment detail parsing keeps the worksheet detail URL separate from an
optional submission page. It normalizes MyCourseVille rich-text links to
absolute URLs, exposes file-based submissions as `submission_files`, and
extracts question-set work as `question_set_submission`. Question-set data
includes the visible action/title, status, submission timestamp, question
prompts, answers, choices, points, selected state, and any answer key or
grading text visible to the student. These operations are read-only: the CLI
does not answer, submit, upload, edit, or delete assignment work.

## Downloads and archives

Material files can be downloaded directly:

```bash
 mcv courses 2110575 materials download 2160993 \
  --output ./lecture.pdf
 mcv courses 2110575 materials download 2160993
```

Archive a material folder with an output name:

```bash
 mcv courses 2110575 materials archive "IoT Hardware" \
  --output ./iot-hardware.zip
```

The archive format is inferred from the output extension first:

- `.zip` creates ZIP;
- `.tar` creates uncompressed TAR;
- `.tar.gz` and `.tgz` create gzip-compressed TAR;
- an absent or unrecognized extension defaults to ZIP.

Use `--format zip`, `--format tar`, or `--format tar.gz` to override inference.
Existing files are not overwritten unless `--force` is supplied.
`--output` is optional: downloads default to the remote filename, while
archives default to the remote folder name with the selected format extension
(or `.zip` when no format is given). Both defaults are written in the current
directory; use `--format` to select an archive extension when `--output` is
omitted.

## Local store, completion, and search

Completion is deliberately cache-only: it does not log in, make network
requests, or block the shell. Install it once, then populate the cache after
authentication:

```bash
 mcv --install-completion
 mcv courses list
 mcv cache refresh
 mcv cache status
 mcv cache clear completion
 mcv cache clear search
 mcv cache clear all
```

Dynamic completion is cache-only and matches both each candidate's inserted
value and its readable aliases. Course candidates can be found by course
number, title words, semester, or `cv_cid`; matching ignores case and
punctuation, accepts fragments anywhere in an alias, and tolerates small
spelling mistakes. For example, after refreshing the cache,
`mcv courses fault<TAB>` can insert the course number for a cached course
whose title contains “FAULT TOLERANT COMPUTING”. The same alias-aware matching
is used for semesters, folders, groupings, and canonical refs where readable
help text is available.

The local store is one SQLite file with separate logical namespaces. The
completion index contains course names, folder names, titles, semesters,
grouping ids, and refs. The resource/search cache contains only allow-listed
snapshots and derived FTS documents for searchable materials, assignments,
announcements, meetings, and playlist pages. It does not contain cookies,
passwords, signed URLs, submission material, feedback, or meeting credentials.
`mcv cache clear completion` preserves search, `mcv cache clear search`
preserves completion, and `mcv cache clear all` removes both; bare `cache clear`
is invalid.

Use `mcv cache refresh --all-semesters` when completion and searchable data
should include every semester, or pass course references to refresh selected
scopes. Search itself is local and performs no network requests:

```bash
 mcv search "docker"
 mcv courses 2110575 search "docker"
 mcv search "docker" --type material --type assignment --limit 20
 mcv search "docker" --refs
 mcv search "docker compose" --exact
 mcv --json search "docker"
 mcv --jsonl search "docker"
```

Use `--refresh` when the search command should fetch the relevant scope before
searching. Use `--exact` to match a complete query phrase literally and disable
fuzzy matching. Human search tables highlight matched terms in titles and
snippets; machine output remains unstyled. Search results have canonical refs
that can be passed to `mcv get`.

Course-scoped schedule and meeting calls also return typed collections with an
`available` flag. The completion index records those flags so playlist
references are suggested only for courses whose playlist section was observed
as available; failed refreshes leave the prior completion metadata intact.

## Development boundary

When changing the CLI itself, preserve the separation between domain models,
the client/parser layer, and CLI rendering. Add a new human renderer to the
`ResourceDisplay` registry in `src/mcv_cli/presentation/registry.py` whenever a new resource
model is introduced. Keep machine serialization in `to_jsonable()` and do not
make human output depend on JSON formatting.

Run the project checks before handing off changes:

```bash
UV_CACHE_DIR=/tmp/mcv-uv-cache  pytest
UV_CACHE_DIR=/tmp/mcv-uv-cache  ruff check src tests
UV_CACHE_DIR=/tmp/mcv-uv-cache  pyright
```
