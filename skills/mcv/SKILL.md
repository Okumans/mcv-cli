---
name: mcv
description: Use the mcv CLI to read and compose MyCourseVille course content on Unix, including session authentication, course/resource lookup, cached completion, archives, and JSON pipelines; do not use it for write or submission actions.
metadata:
  short-description: Read MyCourseVille content with mcv
---

# mcv

Use this skill when a task needs authenticated, browser-free access to
MyCourseVille content through the local `mcv` command-line client.

The client is read-only against MyCourseVille. It can download files and create
local archives, but it must not be treated as a submission, assessment, meeting
join, Kaltura, or attendance-control interface.

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

For an interactive Chula login, use either form:

```bash
 mcv auth login --chula
 mcv auth login --type chula
```

Platform-account login is also supported:

```bash
 mcv auth login --type platform
 mcv auth login --platform --email
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
title. The current semester is the default for course resolution.

To resolve a course from another semester, pass `--semester` (or the
`--yearsem` alias) after the course-scoped action:

```bash
 mcv courses 2110575 --semester 2025/2
 mcv courses 2110575 assignments list --semester 2025/2
```

Useful commands:

```bash
 mcv courses list
 mcv courses list --semester 2026/1
 mcv courses list --all
 mcv courses 2110575

 mcv courses 2110575 materials list
 mcv courses 2110575 materials folders
 mcv courses 2110575 materials list --folder "IoT Hardware"
 mcv courses 2110575 materials show 2160993
 mcv courses 2110575 assignments list
 mcv courses 2110575 assignments show 2160997
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
```

Meetings exclude past events by default. Meeting results expose a preferred
`url`, using the direct join URL when available and otherwise the detail page.

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
`announcement`, and `meeting`. Resolve one or more mixed refs with:

```bash
 mcv get mcv:assignment:86428:2160997
 mcv get \
  mcv:assignment:86428:2160997 \
  mcv:material:86428:2160993
```

For shell composition, use one ref per line and `xargs`:

```bash
 mcv courses 2110575 materials list \
  --folder "IoT Hardware" --refs \
  | xargs -r -n 20  mcv get
```

In human mode, every reference is rendered using its resource-specific detail
display and separated by a blank line. Use the course-scoped `list` commands
when a compact table is preferred. `--json` and `--jsonl` retain their machine
output contracts: an array for multiple resources in JSON mode, and one raw
resource per line in JSONL mode.

`--unique-ids` is a deprecated material-list alias for `--refs`; use
`--refs` in new commands.

## Human and machine output

Default output is for humans. Each resource type has a dedicated display:
collections use resource-specific tables, details use labeled summaries, and
downloads/archives use concise completion messages. Human mode should not be
parsed as JSON.

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

## Downloads and archives

Material files can be downloaded directly:

```bash
 mcv courses 2110575 materials download 2160993 \
  --output ./lecture.pdf
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

## Completion cache

Completion is deliberately cache-only: it does not log in, make network
requests, or block the shell. Install it once, then populate the cache after
authentication:

```bash
 mcv --install-completion
 mcv courses list
 mcv cache refresh
 mcv cache status
 mcv cache clear
```

Use `mcv cache refresh --all-semesters` when completion should include every
semester, or pass course references to refresh selected scopes. The cache
contains completion metadata such as course names, folder names, titles,
semesters, grouping ids, and refs; it does not contain cookies, passwords,
resource bodies, signed URLs, or meeting credentials.

## Development boundary

When changing the CLI itself, preserve the separation between domain models,
the client/parser layer, and CLI rendering. Add a new human renderer to the
`ResourceDisplay` registry in `src/mcv_cli/output.py` whenever a new resource
model is introduced. Keep machine serialization in `to_jsonable()` and do not
make human output depend on JSON formatting.

Run the project checks before handing off changes:

```bash
UV_CACHE_DIR=/tmp/mcv-uv-cache  pytest
UV_CACHE_DIR=/tmp/mcv-uv-cache  ruff check src tests
UV_CACHE_DIR=/tmp/mcv-uv-cache  pyright
```
