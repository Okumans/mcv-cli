# Search and cache

`mcv` keeps a local SQLite store for shell completion and searchable resource
snapshots. Search reads this local index by default and does not perform hidden
network requests.

## Cache namespaces

The local store has separate logical namespaces:

```text
SQLite local store
├── completion index
└── resource snapshots + FTS search index
```

Completion is cache-only and never blocks on authentication or the network.
Normal successful API requests update the local projections on a best-effort
basis.

The search cache stores allow-listed projections of materials, assignments,
announcements, meetings, and playlist pages. It does not store cookies,
passwords, signed URLs, submission files, feedback, or meeting credentials.

## Refreshing and clearing the cache

Manage the store explicitly:

```bash
mcv cache status
mcv cache refresh
mcv cache refresh 2110575 2110521
mcv cache refresh --all-semesters
mcv cache clear completion
mcv cache clear search
mcv cache clear all
```

The clear targets are independent: clearing `completion` preserves search,
clearing `search` preserves completion, and `all` clears both. A bare
`mcv cache clear` is intentionally invalid.

## Normal search

Search results are compact summaries with canonical references:

```bash
mcv search "docker"
mcv courses 2110575 search "docker"
mcv search "docker" --courses=2110575,2110521
mcv search "docker" --type material --type assignment --limit 20
mcv search "docker" --refs
mcv --json search "docker"
mcv --jsonl search "docker"
```

Use `--exact` to match the complete query phrase literally and disable normal
fuzzy matching:

```bash
mcv search "docker compose" --exact
```

Top-level local search does not accept global semester scope. Use a
course-scoped search with one global `--semester` when the local search should
be refreshed for a specific course term; the search itself still reads the
local index.

## Course filters and refresh

`--courses` accepts exact cached course numbers, titles, or `cv_cid` values.
Repeat it or provide a comma-separated value. All selected courses form one OR
scope:

```bash
mcv search "docker" --courses 2110575 --courses 2110521
mcv search "docker" --courses=2110575,2110521
```

A course-scoped search uses its positional course selector:

```bash
mcv --semester 2026/1 courses 2110575 search "docker"
```

Use `--refresh` when relevant course data should be fetched before the same
local search runs:

```bash
mcv search "docker" --refresh
mcv courses 2110575 search "docker" --refresh
```

Refresh failures are reported as command failures; search does not silently
turn a failed network refresh into a claim that the course is empty.

## Interactive fuzzy search

`-z`/`--fuzzy` opens an `fzf` selector over cached results in the command's
scope:

```bash
mcv search -z
mcv search "docker" -z
mcv assignments search --fuzzy --courses 2110575
mcv courses 2110575 materials search --fuzzy
```

The query is optional. When supplied, it seeds the selector. The selector
browses up to 1,000 cached candidates after applying course and resource
filters. `Enter` returns one resource using the requested human, `--refs`,
JSON, or JSONL output mode; `Esc` exits without output. `--limit` applies to
normal search results, not the interactive browse limit.

Human output highlights matched text in titles and snippets. Typo-tolerant
matching can highlight the actual title word that matched, such as `Docker`
for a query of `dockre`.

## Shell completion

Completion reads only the local cache. It matches course numbers and readable
aliases such as title words, semester, and `cv_cid`. Matching ignores case and
punctuation and allows small spelling mistakes.

Resource arguments are scope-aware: course-scoped `show`, `download`, folder,
and grouping completions suggest values from the selected course and the
resource type accepted by that command. Cross-course typed commands such as
`mcv assignments show` remain limited to assignments but may span cached
courses. The generic `mcv get` command intentionally remains mixed-resource.
