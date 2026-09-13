# `mcv` API showcase and evaluation guide

This document demonstrates the current read-only MyCourseVille API from the
CLI and from Python. It is intentionally written as an executable checklist:
replace the example course and item ids with values from the authenticated
account.

The examples use:

```bash
export MCV_COURSE=2110575   # course number or cv_cid
```

Course content, folder names, item ids, counts, and URLs are account-specific
and can change during a semester.

## 1. Quick start

```bash
uv sync
uv run mcv --help
uv run mcv auth status
```

Login is interactive and stores the authenticated session cookies, not the
raw password:

```bash
uv run mcv auth login --chula
# equivalent:
uv run mcv auth login --type chula
```

Other supported credential login forms are:

```bash
uv run mcv auth login --type platform
uv run mcv auth login --platform --email
```

The Google shortcut is intentionally rejected in this MVP because it requires
a browser OAuth flow and an approved client registration:

```bash
uv run mcv auth login --google
```

Session commands:

```bash
uv run mcv auth status
uv run mcv auth logout
```

## 2. Command grammar

The preferred content grammar is:

```text
mcv courses COURSE RESOURCE ACTION [ARGS] [OPTIONS]
```

Examples:

```bash
mcv courses "$MCV_COURSE" materials list
mcv courses "$MCV_COURSE" materials show 2160993
mcv courses "$MCV_COURSE" assignments list
mcv courses "$MCV_COURSE" assignments show 2160997
mcv courses "$MCV_COURSE" playlist
mcv courses "$MCV_COURSE" about
mcv courses "$MCV_COURSE" portfolio
```

The course reference can be an internal `cv_cid`, a course number, or an exact
current-semester course title. Running only the course reference gives an
overview:

```bash
mcv courses "$MCV_COURSE"
```

Course references use the current semester by default. Select a different
semester globally when the course number or title belongs to an older term:

```bash
mcv --semester 2025/2 courses list
mcv --semester 2025/2 courses "$MCV_COURSE"
mcv --semester 2025/2 courses "$MCV_COURSE" assignments list
```

`--semester` is a global option and must be placed before the command.

Collections use `list`, identifier-bearing resources use `show`, and singular
course pages are direct actions. Cross-course aggregate commands are separate
from course navigation:

```bash
mcv courses "$MCV_COURSE" assignments show 2160997
mcv courses "$MCV_COURSE" about
mcv courses "$MCV_COURSE" portfolio
mcv assignments list --pending
mcv announcements list
mcv meetings list
```

Global options must appear before the command:

```bash
mcv --json courses "$MCV_COURSE" materials list
mcv --jsonl courses "$MCV_COURSE" assignments list
mcv --quiet assignments list
```

Progress and shell completion are separate from the data stream. Multi-course,
multi-semester, archive, and multi-reference operations show progress on
stderr in human mode. `--quiet`/`-q` suppresses that display, while JSON and
JSONL modes disable it automatically.

## 3. Local completion cache

Completion candidates are indexed locally after successful commands and can be
refreshed explicitly. Completion itself never performs a network request:

```bash
uv run mcv --install-completion

uv run mcv courses list
uv run mcv cache refresh
uv run mcv cache refresh "$MCV_COURSE" 2110521
uv run mcv cache refresh --all-semesters
uv run mcv --json cache status
uv run mcv cache clear
```

The cache is a compact SQLite index isolated by profile and provider. It holds
course values, semester values, material-folder names, grouping ids, and
canonical addressable refs such as `mcv:assignment:86428:2160997`; it does not
hold credentials, page bodies, signed links, or meeting passwords. If it is
missing, locked, or corrupt, shell completion returns no dynamic candidates and
the command being completed is unaffected.

With a populated cache, these contexts offer dynamic candidates:

```text
mcv courses <TAB>
mcv courses 2110575 <TAB>
mcv courses 2110575 materials list --folder <TAB>
mcv courses 2110575 playlist
mcv courses 2110575 assignments show <TAB>
mcv get <TAB>
```

`mcv cache refresh` indexes the current semester by default. Pass multiple
course numbers, exact titles, or `cv_cid` values to target specific courses;
use `--all-semesters` for a full semester scope. A failed course scope does
not replace its previous resource snapshot.

## 4. Output contracts for Unix tools

The CLI has five useful output styles:

| Mode | Example | Contract |
| --- | --- | --- |
| Human | `mcv courses ...` | Rich tables or readable summaries |
| JSON document | `mcv --json courses ...` | The actual JSON value |
| JSON Lines | `mcv --jsonl courses ...` | One actual JSON value per output line |
| Shell ids | `... materials list --ids` | One raw material id per line |
| Shell refs | `... materials list --refs` | One canonical resource reference per line |

Errors are written to stderr. `--json` and `--jsonl` also make errors JSON so
they can be handled separately from stdout. Use `--envelope` with either
machine mode when a versioned protocol wrapper is useful; it is not included by
default.

Human mode has a dedicated display for every resource model. Collection
results use resource-specific tables, detail results use labeled field/value
summaries, and operation results such as downloads and archives use concise
status messages. JSON-like model dumps are reserved for `--json` and
`--jsonl`.

### JSON document

```bash
mcv --json courses "$MCV_COURSE" assignments list
```

The default JSON document is the value itself:

```json
[
  {"itemid": 2160997, "title": "Homework"}
]
```

To request the optional versioned wrapper:

```bash
mcv --json --envelope courses "$MCV_COURSE" assignments list
```

That form returns `{"schema_version": 1, "data": [...]}`.

### JSON Lines

JSON Lines is useful for `jq`, `awk`, `while read`, and streaming consumers:

```bash
mcv --jsonl courses "$MCV_COURSE" assignments list \
  | jq -s 'map({id: .itemid, title: .title, status: .status})'
```

Without `jq -s`, `jq` processes each JSON line independently:

```bash
mcv --jsonl courses "$MCV_COURSE" announcements list \
  | jq -r '.itemid, .title'
```

With `--jsonl --envelope`, address fields below the wrapper instead:
`jq -s 'map(.data)'` or `jq '.data.title'`.

### Field projection

Material lists support `--select` and its alias `--fields`:

```bash
mcv --json courses "$MCV_COURSE" materials list \
  --folder "IoT Hardware" \
  --select cv_cid,itemid,title
```

`ref` is a computed projection:

```bash
mcv --json courses "$MCV_COURSE" materials list \
  --select ref,title
```

Unknown fields produce a usage error with the available material fields.

### Shell-composable material references

Raw material ids are only meaningful together with their course. The `--refs`
form emits a qualified, stable CLI reference:

```text
mcv:material:<cv_cid>:<item_id>
```

Produce and consume those references directly:

```bash
mcv courses "$MCV_COURSE" materials show \
  $(mcv courses "$MCV_COURSE" materials list \
    --folder "IoT Hardware" --refs)
```

For large result sets, use `xargs` instead of command substitution to avoid
the shell argument-size limit:

```bash
mcv courses "$MCV_COURSE" materials list \
  --folder "IoT Hardware" --refs \
  | xargs -r -n 20 uv run mcv courses "$MCV_COURSE" materials show
```

Universal dereferencing removes the need to repeat the course context:

```bash
mcv courses "$MCV_COURSE" materials list \
  --folder "IoT Hardware" --refs \
  | xargs -r -n 20 uv run mcv get
```

Human `get` output is detailed per resource, even when multiple references are
provided. Each resource uses its own display format and is separated by a
blank line; collection commands remain table-oriented:

```bash
mcv get \
  mcv:assignment:86428:2160997 \
  mcv:material:86428:2160993

mcv courses "$MCV_COURSE" assignments list
```

Machine modes keep their composable contracts:

```bash
mcv --json get \
  mcv:assignment:86428:2160997 \
  mcv:material:86428:2160993

mcv --jsonl get \
  mcv:assignment:86428:2160997 \
  mcv:material:86428:2160993
```

`--json` returns one JSON value, using an array for multiple references;
`--jsonl` emits one resource per line.

## 5. Courses API

### List courses

```bash
uv run mcv courses list
uv run mcv --semester 2026/1 courses list
uv run mcv courses list --all
```

Behavior:

- no semester option: use MyCourseVille's current semester selector;
- `--semester`: global option that selects one semester, or a year prefix;
- `--all`: query every semester exposed by the authenticated page;
- `--semester` and `--all` together: usage error.

### Course overview

```bash
uv run mcv courses "$MCV_COURSE"
uv run mcv --json courses "$MCV_COURSE"
```

The overview contains the resolved `cv_cid`, course number, title, year,
semester, section, role, and icon when available.

Course resolution is deterministic: an exact `cv_cid` wins, then an exact
course number, then an exact whitespace-normalized title, all within the
current semester. Unknown numeric ids are errors rather than being treated as
arbitrary course ids, and multiple matches return `code: "ambiguous"` with
candidate courses in the machine-readable `details.matches` field.

### Course playlist

```bash
uv run mcv courses "$MCV_COURSE" playlist
uv run mcv --json courses "$MCV_COURSE" playlist
uv run mcv get mcv:playlist:78748
uv run mcv get \
  "https://www.mycourseville.com/?q=courseville/course/78748/playlist"
```

Playlist records are read-only metadata trees. Nested folders are preserved in
the JSON model and human output; video entries can include their title,
provider, upstream id, thumbnail, duration, watch percentage, and source or
embed URL. The client does not resolve playback streams, download videos, or
change progress.

## 6. Materials API

### List material resources

```bash
uv run mcv courses "$MCV_COURSE" materials list
uv run mcv courses "$MCV_COURSE" materials list --folder "IoT Hardware"
uv run mcv courses "$MCV_COURSE" materials list --folder "Week 1"
```

Supported list options:

```text
--folder, -f VALUE
--select, --fields FIELD[,FIELD...]
--ids
--refs
```

`--ids` and `--refs` are mutually exclusive shell selectors. Use `--refs`
when the result must retain its course namespace.

Each material can expose:

- `itemid` and `cv_cid`;
- title, created/changed metadata, and description when the detail page is
  available;
- folder id and folder name;
- direct downloadable file URL, when present;
- external links, when the material is a web document or link.

### List folders

```bash
uv run mcv courses "$MCV_COURSE" materials folders
uv run mcv --json courses "$MCV_COURSE" materials folders
```

Each folder contains `folder_id`, `name`, and its parsed `materials` list.

### Show one or more materials

```bash
uv run mcv courses "$MCV_COURSE" materials show 2160993
uv run mcv courses "$MCV_COURSE" materials show 2160993 2152316
uv run mcv courses "$MCV_COURSE" materials show mcv:material:86428:2160993
```

The course-scoped form accepts raw item ids or canonical resource refs. The
reference must belong to the selected course. Legacy reference spellings are
rejected; use the canonical `mcv:material:<cv_cid>:<item_id>` form.

### Download one material

```bash
uv run mcv courses "$MCV_COURSE" materials download 2116506 \
  --output ./lecture.pdf
```

Downloads:

- require an HTTPS URL;
- refuse to overwrite an existing output unless `--force` is supplied;
- write through a private temporary file before replacing the destination;
- set the resulting file to mode `0600`;
- report byte count and SHA-256 in the result.

### Archive a material folder

```bash
uv run mcv courses "$MCV_COURSE" materials archive "IoT Hardware" \
  --output ./iot-hardware.zip

uv run mcv courses "$MCV_COURSE" materials archive "IoT Hardware" \
  --output ./iot-hardware.tar

uv run mcv courses "$MCV_COURSE" materials archive "IoT Hardware" \
  --output ./iot-hardware.tar.gz
```

Options:

```text
--output, -o PATH   required destination
--format FORMAT     optional override: zip, tar, or tar.gz
--force             allow replacement of an existing destination
```

Without `--format`, `.zip`, `.tar`, and `.tar.gz`/`.tgz` output names infer
their archive type. Unknown or missing extensions default to ZIP.
Files without a downloadable URL are skipped and reported. If no file can be
downloaded, the archive is not installed.

## 7. Assignment API

### List assignments

```bash
uv run mcv courses "$MCV_COURSE" assignments list
uv run mcv --jsonl courses "$MCV_COURSE" assignments list
```

List records include the assignment id, title, due date/time, submission
status, group-work indicator, submitted timestamp, detail URL, and links.
The `status` field preserves the text from MyCourseVille's Status column;
`submitted_at` is a separate parsed timestamp and does not replace that status.

### Show assignment detail

```bash
uv run mcv courses "$MCV_COURSE" assignments show 2160997
uv run mcv courses "$MCV_COURSE" assignments show --full 2160997
uv run mcv --json courses "$MCV_COURSE" assignments show 2160997
```

The default human-readable assignment view is compact and presents question-set
questions as numbered prompts, selected choices, answers, and points. Use
`--full` for the complete worksheet-oriented display, including question ids,
types, instructions, grading metadata, and all links. Machine output is not
affected by this option.

Detail parsing adds instruction text, due/out dates, latest submission state,
feedback, representing-group text, normalized links from MyCourseVille rich
text, submitted file URLs, and question-set work-mode metadata when they are
exposed by the worksheet. Question-set metadata includes the visible action
and title, status, optional link, latest submission timestamp, and questions.
Questions include their prompt, type, current answer, choices, points, and any
answer key or grading text visible to the student. The assignment detail page
is kept separate from an optional submission page, and the client does not
answer, submit, upload, edit, or delete assignment work.

## 8. Announcement API

```bash
uv run mcv courses "$MCV_COURSE" announcements list
uv run mcv courses "$MCV_COURSE" announcements show 2177455
uv run mcv --jsonl courses "$MCV_COURSE" announcements list
```

Announcement detail includes title, posted date, body text, last-modified
metadata, and extracted external links.

## 9. Online meeting API

```bash
uv run mcv courses "$MCV_COURSE" meetings list
uv run mcv courses "$MCV_COURSE" meetings list --include-past
uv run mcv courses "$MCV_COURSE" meetings show 29632
```

Meeting lists hide meetings whose scheduled time has passed by default;
`--include-past` returns the complete list. Each result includes `url`, which
prefers the direct `join_url` and falls back to `detail_url`.

Meeting detail can include:

- provider, meeting id, host, schedule, and duration;
- meeting detail and entrance URLs;
- recording play/download URLs;
- recording type, start time, lifetime, and source password when the page
  exposes one.

The CLI never calls the meeting-join route. Showing meeting details is
read-only and is not intended to mark attendance. Treat JSON output and shell
logs as sensitive because recording links/passwords may be access-bearing.

## 10. Schedule API

```bash
uv run mcv courses "$MCV_COURSE" schedule list
uv run mcv --json courses "$MCV_COURSE" schedule list
```

Each schedule event exposes index, date, time, title, comment, and `cv_cid`.
An empty schedule is a valid result and is rendered as `data: []` in JSON
mode.

## 11. Course information API

```bash
uv run mcv courses "$MCV_COURSE" about
uv run mcv --json courses "$MCV_COURSE" about
```

The about record can contain course number, year/semester, English/Thai names,
abbreviation, affiliation, instructors, descriptions, learning objectives,
assigned outcomes, and custom outcomes.

## 12. Student-group API

```bash
uv run mcv courses "$MCV_COURSE" groups list
uv run mcv courses "$MCV_COURSE" groups list --grouping 54791
uv run mcv --jsonl courses "$MCV_COURSE" groups list
```

Group records contain grouping id/name, group id/name, slogan, and member
names. Group listing uses the site's read-only AJAX listing endpoint even
though the server implements that listing request as POST.

## 13. Portfolio API

```bash
uv run mcv courses "$MCV_COURSE" portfolio
uv run mcv --json courses "$MCV_COURSE" portfolio
```

The current parser exposes the available student summary: total points,
possible points, rank, grade letter, badges, and group membership. Some
portfolio tabs are lazy-loaded and are not included in this MVP.

## 14. Web-resource API

```bash
uv run mcv courses "$MCV_COURSE" web-resources list
uv run mcv --json courses "$MCV_COURSE" web-resources list
```

Each web resource contains an item id, title, URL, description when available,
and `cv_cid`. An empty web-resource page is returned as an empty list.

## 15. Cross-course resource APIs

These commands aggregate the current-semester courses by default. Pass the
global `--semester` option before the command to aggregate a selected term.
They are application services over the course-oriented `MCVAPI`, not new
upstream CourseVille primitives:

```bash
uv run mcv assignments list
uv run mcv assignments list --pending
uv run mcv assignments list --due
uv run mcv assignments list --pending --refs

uv run mcv announcements list
uv run mcv announcements list --refs

uv run mcv meetings list
uv run mcv meetings list --include-past
uv run mcv meetings list --refs
```

`--pending` excludes completed/submitted assignment records. `--due` keeps
records that expose a due date or time. Cross-course commands intentionally do
not provide raw `--ids`; use `--refs` because an upstream id has no standalone
course namespace.

Addressable machine records include `resource_type`, `ref`, `cv_cid`,
`itemid`, and `course_no` when available:

```json
[
  {
    "resource_type": "assignment",
    "ref": "mcv:assignment:86428:2160997",
    "cv_cid": 86428,
    "itemid": 2160997,
    "course_no": "2110575",
    "title": "Homework 4"
  }
]
```

## 16. Universal resource lookup

The canonical reference grammar is:

```text
mcv:<resource-type>:<cv_cid>:<resource-id>
```

Currently dereferenceable types are `material`, `assignment`, `announcement`,
and `meeting`. Course-level playlists use the special form
`mcv:playlist:<cv_cid>` without an item id. The generic dispatcher accepts one
or more mixed references:

```bash
uv run mcv get mcv:assignment:86428:2160997
uv run mcv get \
  mcv:assignment:86428:2160997 \
  mcv:material:86428:2160993
uv run mcv get \
  "https://www.mycourseville.com/?q=courseville/worksheet/78748/1889560"
uv run mcv get mcv:playlist:78748
uv run mcv get \
  "https://www.mycourseville.com/?q=courseville/course/78748/playlist"
```

`mcv get` also accepts supported HTTPS URLs copied from MyCourseVille. URLs are
validated and normalized to the equivalent typed reference before the client
lookup runs. Supported forms include playlist pages and assignment worksheet,
material content-node, announcement content-node, and meeting detail URLs.

In JSONL mode each input is independent, so a failed reference produces an
error record while other references can still succeed:

```bash
uv run mcv --jsonl get \
  mcv:assignment:86428:2160997 \
  mcv:material:86428:2160993
```

For this batch command, success and error records are both written to stdout
in input order; a nonzero exit status still signals that at least one lookup
failed. Other command errors continue to use stderr.

## 17. Python API

The CLI is a thin orchestration layer over the pure `MCVAPI`. Runtime
authentication and storage are supplied by the caller; the API itself has no
Typer, Rich, cache, completion, or terminal-output dependency:

```python
from mcv_cli.api import MCVAPI
from mcv_cli.api.core.refs import ResourceRef
from mcv_cli.runtime.auth import AuthManager
from mcv_cli.runtime.config import Settings

manager = AuthManager(settings=Settings())

with MCVAPI(manager) as api:
    course = api.courses.resolve("2110575")
    playlist = api.playlists.get(course.cv_cid)
    materials = api.materials.list(course.cv_cid)
    assignment = api.get(ResourceRef.parse("mcv:assignment:86428:2160997"))
```

Resource clients expose domain operations under their resource namespace:

| Client | Operations |
| --- | --- |
| `api.courses` | `list`, `get`, `resolve` |
| `api.playlists` | `get` |
| `api.materials` | `list`, `list_folders`, `get`, `download`, `archive` |
| `api.assignments` | `list`, `get` |
| `api.announcements` | `list`, `get` |
| `api.meetings` | `list`, `get` |
| `api.schedule` | `list` |
| `api.about` | `get` |
| `api.groups` | `list` |
| `api.portfolio` | `get` |
| `api.web_resources` | `list` |

Cross-course operations are separate aggregate services:

```python
from mcv_cli.api.aggregates.assignments import AssignmentsAggregate

with MCVAPI(manager) as api:
    pending = AssignmentsAggregate(api).list(pending=True)
```

`ResourceRef.parse` accepts canonical references and supported HTTPS
MyCourseVille URLs, normalizing both forms to one typed address.

## 17. Route coverage

These are reverse-engineered web routes used by the current implementation.
They are not an official public API contract.

| Capability | HTTP | Route/query shape | State |
| --- | --- | --- | --- |
| Course home / semester selector | GET | `/?q=courseville` | read-only |
| Course list filter | POST | `/?q=courseville/ajax/cvhomepanel_get_filter` | read-only |
| Course home content | POST | `/?q=courseville/ajax/course` with `cv_cid` | read-only |
| Course playlist | GET | `/?q=courseville/course/{cv_cid}/playlist` | read-only |
| Materials | GET | course-home material links and `view_content_node_{id}_material` | read-only |
| Assignments | GET | `/?q=courseville/course/{cv_cid}/assignment` | read-only |
| Assignment detail | GET | `/?q=courseville/worksheet/{cv_cid}/{item_id}` | read-only |
| Announcements | GET | course-home announcement links and `view_content_node_{id}` | read-only |
| Online meetings | GET | `/?q=courseville/course/{cv_cid}/meeting` | read-only |
| Meeting detail | GET | `/?q=courseville/course/{cv_cid}/meeting_view_{id}` | read-only |
| Course schedule | GET | `/?q=courseville/course/{cv_cid}/schedule` | read-only |
| Course information | GET | `/?q=courseville/course/{cv_cid}/about` | read-only |
| Student-group page | GET | `/?q=courseville/course/{cv_cid}/group` | read-only |
| Student-group cards | POST | `/?q=courseville/ajax/cvpagegroup_getgroupcardlisting` | read-only listing |
| Portfolio | GET | `/?q=courseville/course/{cv_cid}/portfolio-{student_id}` | read-only |
| Web resources | GET | `/?q=courseville/course/{cv_cid}/wlrlist` | read-only |
| Material file | GET | HTTPS URL exposed by MyCourseVille | download |

No join, attendance, upload, submit, edit, delete, notification, or
assessment-write route is implemented.

## 18. Data models

The public Pydantic models are:

| Model | Main fields |
| --- | --- |
| `Course` | `cv_cid`, `course_no`, `title`, `year`, `semester`, `section`, `role` |
| `Playlist` | `cv_cid`, title/description/source URL, ordered nested nodes |
| `PlaylistFolder` | optional folder id, name, position, child folders/videos |
| `PlaylistVideo` | provider/id, title, source/embed/thumbnail URLs, duration, watch percentage |
| `Material` | `itemid`, `cv_cid`, `title`, folder fields, URLs, metadata |
| `MaterialFolder` | `folder_id`, `name`, `materials` |
| `Assignment` | `itemid`, `cv_cid`, optional `course_no`, title, due dates, status, feedback, links, `question_set_submission` |
| `QuestionSetSubmission` | visible action/title, optional link, status, latest submission timestamp, questions |
| `QuestionSetQuestion` | question id/number, type, prompt, answer, choices, points, status |
| `QuestionSetChoice` | label, upstream value, selected state, optional correctness |
| `Announcement` | `itemid`, `cv_cid`, optional `course_no`, title, body, posted/modified dates, links |
| `OnlineMeeting` | `itemid`, `cv_cid`, optional `course_no`, provider, schedule, preferred `url`, join/detail URLs, recordings |
| `MeetingRecording` | recording type, play/download URL, timing, password |
| `ScheduleEvent` | index, `cv_cid`, date, time, title, comment |
| `CourseAbout` | course identity, names, descriptions, staff, outcomes |
| `StudentGroup` | grouping/group identity, slogan, members |
| `Portfolio` | points, rank, grade, badges, group membership |
| `WebResource` | `itemid`, `cv_cid`, title, URL, description |
| `DownloadResult` | output path, byte count, SHA-256 |
| `ArchiveResult` | output path, format, file count, byte count, skipped items |
| `ResourceRef` | resource type, `cv_cid`, optional upstream item id; playlist form `mcv:playlist:cv_cid` |

Material, assignment, announcement, and meeting `itemid` values are treated
as course-scoped. Use `mcv:<resource-type>:<cv_cid>:<item_id>` when a reference
must be unambiguous across courses; use `mcv:playlist:<cv_cid>` for a course
playlist. The machine-output adapter adds `resource_type` and `ref` to
addressable records without changing their Python model fields.

## 19. Current evaluation

### Automated checks

Run from the repository root:

```bash
UV_CACHE_DIR=/tmp/mcv-uv-cache uv run pytest -q
UV_CACHE_DIR=/tmp/mcv-uv-cache uv run ruff check .
UV_CACHE_DIR=/tmp/mcv-uv-cache uv run pyright
```

The current local evaluation recorded while writing this document is:

```text
139 passed
Ruff: all checks passed
Pyright: 0 errors, 0 warnings
```

### Authenticated live smoke evaluation

The following was checked against the stored authenticated session on
2026-09-12. Counts are observations, not fixtures:

| API | Observation |
| --- | --- |
| Current course resolution | course `2110575` resolved to `cv_cid 86428` |
| Course list | current-semester and all-semester queries returned data |
| Course overview | passed |
| Materials | 6 materials and 3 folders observed |
| Material folder pipeline | `IoT Hardware` produced 3 ids and 3 canonical refs |
| ZIP/TAR/TAR.GZ archive | covered by unit tests; implementation performs read-only remote downloads |
| Assignments | 5 assignments; detail `2160997` passed |
| Announcements | 5 announcements; detail parsing passed |
| Online meetings | 1 meeting; detail and recordings parsing passed without joining |
| Schedule | empty for the example course; populated schedule parsing also tested |
| About | passed |
| Student groups | 49 groups observed for the default grouping |
| Portfolio | read-only summary parsing passed |
| Web resources | empty page handled as an empty list |

To repeat a compact smoke check:

```bash
uv run mcv --json courses "$MCV_COURSE" materials list | jq 'length'
uv run mcv --json courses "$MCV_COURSE" materials folders | jq 'length'
uv run mcv --json courses "$MCV_COURSE" assignments list | jq 'length'
uv run mcv --json courses "$MCV_COURSE" announcements list | jq 'length'
uv run mcv --json courses "$MCV_COURSE" meetings list | jq 'length'
uv run mcv --json courses "$MCV_COURSE" groups list | jq 'length'
uv run mcv --json courses "$MCV_COURSE" about | jq '{course_no, title}'
uv run mcv --json courses "$MCV_COURSE" portfolio | jq '{total_points, rank}'
uv run mcv --json assignments list | jq 'length'
uv run mcv --json assignments list --pending | jq 'map(.ref)'
uv run mcv --json announcements list | jq 'length'
uv run mcv --json meetings list | jq 'length'
uv run mcv --json get mcv:assignment:86428:2160997 | jq '{resource_type, ref, title}'
```

### Deferred or intentionally unsupported

| Area | Reason |
| --- | --- |
| Assessment platform (`/map`) | Separate interactive grading system; no read-only stable model yet |
| Playback/download | Playlist support exposes page metadata only; it does not resolve or retrieve video streams |
| Meeting join | May record attendance; deliberately not called |
| Assignment submission/upload | State-changing and outside the student read-only scope |
| Course/material/group edits | State-changing and not implemented |
| Google login | Requires browser OAuth/client registration |

## 20. Error and safety behavior

Current exit-code meanings:

| Code | Meaning |
| ---: | --- |
| 0 | success |
| 2 | usage error |
| 3 | no authenticated session / expired session |
| 4 | authentication failure |
| 5 | upstream or not-found failure |
| 6 | credential/storage failure |
| 7 | validation or ambiguous-reference failure |
| 8 | download/archive failure |

Transport failures include the HTTP method, safe route, exception type, and
reason. For machine-readable diagnostics:

```bash
uv run mcv --json courses "$MCV_COURSE" assignments show 2160997
```

Machine errors are flat JSON by default and distinguish the failure type even
when the process exit code is shared. Add `--envelope` if a versioned error
wrapper is needed:

Common reference-related codes are `invalid_ref`,
`unsupported_resource_type`, `ref_course_mismatch`, `not_found`, and
`ambiguous`. `resource`, `operation`, and `retryable` are always present in
machine errors; they may be `null` when no narrower context is available.

```json
{
  "code": "not_found",
  "message": "Assignment 123 was not found in course 2110575.",
  "resource": "assignment",
  "operation": "get",
  "retryable": false
}
```

Credentials are session cookies and should be treated as bearer-like secrets.
Do not commit command output containing recording passwords, signed download
URLs, or private course links.
