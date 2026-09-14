---
name: mcv
description: Use the mcv CLI to read and compose MyCourseVille course content on Unix, including authentication, course/resource lookup, canonical refs, local cache/search, completion, downloads, and JSON pipelines; do not use it for write or submission actions.
metadata:
  short-description: Read MyCourseVille content with mcv
---

# mcv

Use this skill for authenticated, browser-free access to MyCourseVille through
the local `mcv` command. The client is read-only against MyCourseVille. Local
downloads and archives are allowed, but the client must not be used to submit
or edit assignments, upload files, join meetings, control attendance, or
change course content.

## Execution and authentication

When running in an isolated coding sandbox, authenticated or live `mcv`
commands must run in the host environment. The host contains the real keyring,
session, and configuration; a sandboxed process commonly reports
`authenticated False` because it has a separate home and keyring. Do not copy
cookies, keyring data, passwords, storage passphrases, signed URLs, or meeting
credentials into the workspace.

Check the session before live queries:

```bash
mcv auth status
```

If the user requests login, use the credential flow and never pass a password
on the command line:

```bash
mcv auth login --type chula
mcv auth login --type platform
mcv auth login --type platform --email
```

Do not invent OAuth credentials or replace this browser-free flow with browser
automation. If host execution is unavailable, report that boundary instead of
treating a sandbox authentication result as authoritative.

## Command grammar and course lookup

The main route is:

```text
mcv courses COURSE RESOURCE ACTION [ARGS] [OPTIONS]
```

`COURSE` may be a course number, `cv_cid`, or exact course title. The current
semester is the default. Put global options before the command; repeat
`--semester` to combine terms or use global `--all` for every available
semester on supported collection commands.

```bash
mcv --json courses list
mcv --semester 2025/2 --json courses list
mcv courses 2110575
mcv --json courses 2110575 materials list
mcv --json courses 2110575 assignments show 2160997
mcv courses 2110575 announcements list
mcv courses 2110575 meetings list --include-past
mcv courses 2110575 schedule list
mcv courses 2110575 about
mcv courses 2110575 groups list
mcv courses 2110575 playlists
mcv courses 2110575 search "docker"
```

Course resources are `materials`, `assignments`, `announcements`, and
`meetings`; supported course pages also include `schedule`, `about`, `groups`,
`portfolio`, `playlists`, and `web-resources`. Most resources use `list` and
`show`. Course-scoped search is a direct `search` action.

For current-course aggregates, use:

```bash
mcv --json assignments list
mcv --json assignments list --pending
mcv --json announcements list
mcv --json meetings list --include-past
```

Use a course-scoped command when a raw item id needs its course namespace.
Prefer canonical refs for anything that will be passed to another command.

## Canonical refs and pipelines

Use `-r` or `--refs` on list and search commands to emit one canonical ref per
line. `-r` is available everywhere `--refs` is available:

```bash
mcv courses 2110575 materials list -r
mcv assignments list --pending -r
mcv search "docker" -r
```

Refs have this form:

```text
mcv:<resource-type>:<cv_cid>:<resource-id>
```

The addressable item types are `material`, `assignment`, `announcement`, and
`meeting`. Course-level playlists use `mcv:playlist:<cv_cid>` without an item
id. Resolve one or more mixed refs with `mcv get`; supported official
MyCourseVille URLs are accepted and normalized to the same typed refs:

```bash
mcv get mcv:assignment:86428:2160997
mcv get mcv:assignment:86428:2160997 mcv:material:86428:2160993
mcv get "https://www.mycourseville.com/?q=courseville/worksheet/78748/1889560"
```

For shell composition, keep one ref per line:

```bash
mcv assignments list --pending -r | xargs -r -n 20 mcv get
```

Do not treat a raw id as globally unique. An arbitrary URL is never fetched.

## Machine-readable output

Use machine modes instead of parsing human tables. Global output options come
before the command:

```bash
mcv --json courses 2110575 assignments list
mcv --jsonl assignments list --pending
mcv --jsonl get \
  mcv:assignment:86428:2160997 \
  mcv:material:86428:2160993
```

`--json` emits one JSON value: usually an object for one result or an array
for a collection. `--jsonl` emits one JSON value per line, which is useful for
streaming and batch processing. `--envelope` adds the optional versioned
wrapper and requires either machine mode.

For example, `mcv --json courses list` returns an array:

```json
[
  {
    "cv_cid": 86428,
    "course_no": "2110575",
    "title": "Container Systems",
    "year": "2026",
    "semester": "1"
  }
]
```

`mcv --json courses COURSE` returns one course object with the same fields:

```json
{
  "cv_cid": 86428,
  "course_no": "2110575",
  "title": "Container Systems",
  "year": "2026",
  "semester": "1"
}
```

Addressable resource lists such as materials return arrays of identity-bearing
items:

```json
[
  {
    "resource_type": "material",
    "ref": "mcv:material:86428:2160993",
    "cv_cid": 86428,
    "itemid": 2160993,
    "title": "Docker Fundamentals",
    "folder_name": "Week 1"
  }
]
```

Assignments and announcements use the same item shape, with resource-specific
fields such as `duedate`, `question_set_submission`, `posted`, or `body`:

```json
[
  {
    "resource_type": "announcement",
    "ref": "mcv:announcement:86428:2177455",
    "cv_cid": 86428,
    "itemid": 2177455,
    "course_no": "2110575",
    "title": "Exam notice",
    "posted": "2026-09-14"
  }
]
```

Meeting and schedule lists are collection objects rather than bare arrays:

```json
{
  "cv_cid": 86428,
  "collection_type": "meeting",
  "available": true,
  "meetings": [
    {
      "resource_type": "meeting",
      "ref": "mcv:meeting:86428:29632",
      "itemid": 29632,
      "name": "Lecture",
      "provider": "Zoom",
      "url": "https://zoom.example/meeting/29632"
    }
  ]
}
```

Schedule collections use `events` instead of `meetings`; playlists use a
course-level `playlists` array and `mcv:playlist:<cv_cid>` ref. `available:
false` means the optional collection was not present, while an available
collection with an empty array is a valid empty result.

Addressable resource details from `show` and `mcv get` include the same
identity fields plus the full resource-specific data:

```json
{
  "resource_type": "assignment",
  "ref": "mcv:assignment:86428:2160997",
  "cv_cid": 86428,
  "itemid": 2160997,
  "course_no": "2110575",
  "title": "Homework 4"
}
```

`mcv --json search "docker"` returns an array of compact summaries pointing to
a resource:

```json
[
  {
    "resource_type": "assignment",
    "ref": "mcv:assignment:86428:2160997",
    "cv_cid": 86428,
    "course_no": "2110575",
    "title": "Homework 4",
    "snippet": "...container deployment...",
    "score": 1.25
  }
]
```

`mcv --quiet --json status` returns a live cross-course snapshot. Its three
arrays contain the same assignment, meeting, and announcement shapes shown
above:

```json
{
  "generated_at": "2026-09-14T12:00:00+07:00",
  "assignment_window_days": 7,
  "announcement_window_days": 7,
  "assignments_due": [],
  "meetings_today": [],
  "announcements_recent": []
}
```

Use `status` for current due work, today's meetings, and recent announcements;
it requires live authentication and is separate from the cache-only search.

Fields vary by resource. Read `ref` to fetch the full record with `mcv get`,
`itemid` only inside its course, and `cv_cid`/`course_no` to preserve course
identity. With `--envelope`, the same value is under `data`:

```json
{"schema_version":1,"ok":true,"data":{}}
```

An ordinary machine error has fields such as:

```json
{
  "code": "not_found",
  "message": "Assignment 123 was not found.",
  "resource": "assignment",
  "operation": "get",
  "retryable": false
}
```

Errors normally go to stderr. `--jsonl get` writes success and error records
to stdout in input order and exits nonzero if any lookup fails; with
`--envelope`, successful and failed lines are discriminated by `ok`.

## Cache, local search, and completion

Search and completion use the local cache by default. Search does not make a
hidden network request; pass `--refresh` when fresh searchable data is needed.

```bash
mcv cache status
mcv cache refresh
mcv cache refresh 2110575
mcv cache refresh --all-semesters
mcv cache clear completion
mcv cache clear search
mcv cache clear all

mcv search "docker"
mcv search "docker" --type material --type assignment --limit 20
mcv search "docker" --courses 2110575 --exact
mcv search "docker" --refresh
```

`cache refresh` requires authentication and refreshes course/resource data;
course references may be supplied as positional arguments. Do not confuse a
failed refresh or unavailable collection with a valid empty result.

Install shell completion once with `mcv --install-completion`. Completion is
fast, cache-only, and does not require a network request; after a cache refresh
it can suggest course ids, folders, groups, resource refs, and relevant
options. It is a convenience layer—use explicit commands and machine output
for agent workflows.

## Local files

Material files and folders can be saved locally:

```bash
mcv courses 2110575 materials download 2160993 --output ./lecture.pdf
mcv courses 2110575 materials archive "IoT Hardware" --output ./iot.zip
```

These operations write only to the requested local path. Existing files are
not overwritten unless `--force` is supplied.
