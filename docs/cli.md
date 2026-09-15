# CLI reference

This document describes `mcv` command structure, course and semester
selection, resource addressing, output modes, and command-specific behavior.
For installation and a short introduction, see the [README](../README.md).

## Command structure

The main course-scoped form is:

```text
mcv courses COURSE RESOURCE ACTION [ARGS] [OPTIONS]
```

`COURSE` may be a CourseVille id, course number, or exact current-semester
course title. Course-level pages such as `playlists`, `about`, and `portfolio`
are direct actions. Other collections generally use `list`, while
identifier-bearing resources use `show`.

```bash
# Courses
mcv courses list
mcv courses 2110575

# Course resources
mcv courses 2110575 materials list
mcv courses 2110575 materials folders
mcv courses 2110575 materials show 2160993
mcv courses 2110575 assignments list
mcv courses 2110575 assignments show 2160997
mcv courses 2110575 announcements list
mcv courses 2110575 meetings list
mcv courses 2110575 schedule list
mcv courses 2110575 playlists
mcv courses 2110575 about
mcv courses 2110575 groups list
mcv courses 2110575 portfolio
mcv courses 2110575 web-resources list
```

Assignment details can include question-set and submission metadata visible to
the student, but the CLI does not answer or submit work. Meeting lists show
meetings dated today by default, including meetings whose scheduled time has
passed. Use `--include-past` to include meetings from all dates. Meeting links
and recordings are displayed as metadata; the CLI does not open or join them.

## Status dashboard

`mcv status` combines pending assignments due within the next seven days,
meetings dated today, and announcements posted or modified in the last seven
days. `mcv today` is a short alias. Use a global semester option before the
command when needed, for example `mcv --semester 2026/1 status`.

The current unread state is not exposed by the read-only parser, so the
announcements section uses a recent-activity fallback. `mcv status --all`
adds identity fields such as raw ids and canonical references to human tables;
it does not expand the dashboard's data scope.

## Course and semester selectors

Use the global `--semester` option before a command:

```bash
mcv --semester 2025/2 courses list
mcv --semester 2025/1 --semester 2026/1 courses list
```

Repeated values combine explicit semesters. A year prefix such as `--semester
2025` selects every available term in that year. Use either `--all` or one or
more `--semester` options, not both.

The global `--all` selects every available semester for supported semester-wide
collection commands:

```bash
mcv --all courses list
mcv --all assignments list
mcv --all announcements list
mcv --all meetings list
```

Course-scoped commands accept one semester selection. Repeated selections and
global `--all` are reserved for semester-wide collections. The explicit
all-semester cache operation is `mcv cache refresh --all-semesters`.

## Course-scoped and cross-course commands

The indexed resource groups also expose `search` aliases. They use the central
local search engine while retaining the resource type in the command:

```bash
mcv courses 2110575 assignments list
mcv courses 2110575 assignments list --pending
mcv courses 2110575 assignments show --full 2160997
mcv courses 2110575 assignments search "docker"
mcv courses 2110575 announcements search "deadline"
mcv courses 2110575 meetings search "zoom"
mcv courses 2110575 materials search "docker"
mcv courses 2110575 playlists search "lecture"
```

Cross-course typed commands accept canonical references or supported official
MyCourseVille URLs:

```bash
mcv assignments list
mcv assignments show mcv:assignment:86428:2160997
mcv assignments search "docker" --courses=2110575,2110521
mcv announcements show mcv:announcement:86428:2177455
mcv meetings search "zoom" --courses=2110575
mcv --all assignments list
```

## `--all`

`--all` has two unrelated scopes depending on its position.

Global:

```bash
mcv --all assignments list
```

selects all available semesters for supported collection commands.

Local:

```bash
mcv assignments list --all
mcv courses 2110575 materials list --all
mcv search "docker" --all
```

expands the human-readable table with identity fields such as raw ids and
canonical references. The local form affects presentation only; it does not
change JSON/JSONL schemas, search limits, or filters.

## References and IDs

Use `--ids` only when the receiving command already has a course context. Use
`-r` or `--refs` when results will be passed between commands or across
courses:

```bash
mcv courses 2110575 materials list --folder "Week 1" --ids
mcv courses 2110575 materials list --folder "Week 1" --refs
```

Canonical references have a course-qualified form:

```text
mcv:<resource-type>:<cv_cid>:<item_id>
```

Course playlists use the special course-level form `mcv:playlist:<cv_cid>`.
The course qualifier prevents a raw item id from being ambiguous.

## `mcv get`

Resolve one or more references in input order:

```bash
mcv get mcv:assignment:86428:2160997
mcv get \
  mcv:assignment:86428:2160997 \
  mcv:material:86428:2160993
```

Supported official MyCourseVille URLs are accepted as well:

```bash
mcv get "https://www.mycourseville.com/?q=courseville/worksheet/78748/1889560"
mcv get "https://www.mycourseville.com/?q=courseville/course/123/view_content_node_9_material"
mcv get "https://www.mycourseville.com/?q=courseville/course/78748/playlist"
```

URLs are restricted to the official host and normalized to the same typed
reference. An arbitrary URL is never fetched.

For shell composition, keep one reference per line and use `xargs`:

```bash
set -o pipefail
mcv assignments list --pending --refs | xargs -r -n 20 mcv get
```

## Machine-readable output

Put global output options before the command:

```bash
mcv --json courses 2110575 assignments list
mcv --jsonl assignments list --pending
mcv --jsonl get \
  mcv:assignment:86428:2160997 \
  mcv:material:86428:2160993
```

The modes are:

- `--json` emits one JSON document, using an object or array as appropriate.
- `--jsonl` emits one JSON value per line for streaming and batch processing.
- `--envelope` adds explicit `schema_version` and `ok` protocol fields.
- `--quiet`/`-q` suppresses progress and status output.

The human-table `--all` option and global semester `--all` do not change JSON
or JSONL schemas. `--refs` and `--ids` continue to emit one value per line.
JSONL `get` writes successes and failures in input order and exits nonzero if
any lookup fails. Use `--envelope` when consumers need an unambiguous
success/error discriminator.

## Downloads and archives

Download a material or archive a material folder:

```bash
mcv courses 2110575 materials download 2160993 --output ./lecture.pdf
mcv courses 2110575 materials archive "Week 1" --output ./week-1.zip
```

When `--output` is omitted, downloads use the remote filename and archives use
the remote folder name with `.zip`. ZIP, TAR, and compressed TAR archives are
supported. The format can be selected explicitly with `--format tar` or
`--format tar.gz`, or inferred from `.zip`, `.tar`, `.tar.gz`, and `.tgz`.
Existing files are not overwritten unless `--force` is supplied.
