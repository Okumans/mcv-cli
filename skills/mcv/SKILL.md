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

## Choosing a command

Use the narrowest operation that satisfies the request:

- Current deadlines, today's meetings, and recent announcements:
  `mcv --quiet --json status`
- A general "what is happening with my courses?" request: prefer `status`
  over separate assignment, meeting, and announcement queries.
- Find something by text: `mcv search QUERY`
- Fresh search results: `mcv search QUERY --refresh`
- A known canonical ref or MyCourseVille URL: `mcv get REF`
- Browse a course resource: `mcv courses COURSE RESOURCE list`
- Inspect a known resource: `mcv courses COURSE RESOURCE show ID`
- Save material locally: `mcv courses COURSE materials download ...` or
  `mcv courses COURSE materials archive ...`

Prefer `--json` or `--jsonl` when reasoning over results or composing a
pipeline.

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
mcv auth login
```

If host execution is unavailable, report that boundary instead of treating a
sandbox authentication result as authoritative.

## Command grammar and course lookup

The main route is:

```text
mcv courses COURSE RESOURCE ACTION [ARGS] [OPTIONS]
```

`COURSE` may be a course number, `cv_cid`, or exact course title. The current
semester is the default. Put global options before the command; repeat
`--semester` to combine terms or use global `--all` for every available
semester on supported collection commands.

If a course title is ambiguous or only approximate, resolve it with
`mcv --json courses list` first rather than guessing a course selector.

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

For a broad current-status request, prefer `mcv --quiet --json status`; it
provides the due assignments, today's meetings, and recent announcements in a
single live snapshot.

Use a course-scoped command when a raw item id needs its course namespace.
Prefer canonical refs for anything that will be passed to another command.

## Canonical refs and pipelines

When preserving identity across commands or turns, prefer this order:

1. canonical `ref`
2. `cv_cid` plus `itemid`
3. `course_no` plus `itemid`

Never persist or pass a raw `itemid` without its course context.

Use `-r` or `--refs` on list and search commands to emit one canonical ref per
line. `-r` is available everywhere `--refs` is available. When the next
command only needs resource identity, prefer `-r/--refs` instead of JSON and
avoid extracting ids manually with `jq`:

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
set -o pipefail
mcv assignments list --pending -r | xargs -r -n 20 mcv get
```

The core composition pattern is: use refs to select; use `get` to hydrate.
For machine-readable batch processing, collect the JSONL records if needed:

```bash
set -o pipefail
mcv assignments list --pending -r \
  | xargs -r -n 20 mcv --jsonl get \
  | jq -s '.'
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

Common identity fields are:

| Field | Meaning |
|---|---|
| `resource_type` | Typed resource kind |
| `ref` | Canonical reusable reference |
| `cv_cid` | CourseVille course identity |
| `itemid` | Resource id, scoped to the course |
| `course_no` | Human course number |
| `title` | Resource title |

`mcv --json courses list` returns an array; `mcv --json courses COURSE`
returns one course object. Addressable resource lists and details use the
identity fields above; assignments and announcements add resource-specific
fields such as `duedate`, `question_set_submission`, `posted`, or `body`.

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

`mcv --json search "docker"` returns an array of compact summaries with a
resource `ref`, title, matched `snippet`, and relevance `score`.

`mcv --quiet --json status` returns a live cross-course snapshot. Its three
arrays are `assignments_due`, `meetings_today`, and `announcements_recent`,
along with the generation time and window sizes.

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

On `not_found`, do not retry blindly. On an authentication error, check
`mcv auth status` in the host environment. Retry only when the machine record
has `"retryable": true`. For JSONL batches, inspect every output line even
when the overall process exits nonzero; successful records remain usable.

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
