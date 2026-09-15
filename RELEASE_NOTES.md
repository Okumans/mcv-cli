# Release notes

## 0.6.0

This release splits the reusable client from the terminal application while
keeping both distributions in this Git repository.

- Added the standalone `mcv-api` distribution, installable from
  `#subdirectory=packages/mcv-api`.
- Moved the public Python namespace from `mcv_cli.api` to `mcv_api` without a
  compatibility alias.
- Kept `mcv-cli` as the CLI distribution and `mcv` entry point; it depends on
  `mcv-api` and retains authentication storage, SQLite cache, presentation, and
  terminal features.
- Made `SessionProvider` and the optional `LocalStore` protocol public from
  `mcv_api` so applications can inject authentication and caching policy.

## 0.5.0

This release makes shell completion independent of the normal Typer command
tree and keeps the completion process lightweight.

- Replaced the Typer completion client with the stdlib-only `completion.cli`
  protocol dispatcher.
- Kept dynamic course, resource, semester, folder, grouping, and reference
  completion backed by the current SQLite cache.
- Repaired completion-state activation for existing authenticated profiles and
  ordered root commands before global options.
- Organized completion into the `runtime.completion` subpackage.

## 0.4.0

This release improves the interactive CLI workflow and keeps cached content
strictly within the selected course and semester scope.

- Added the unified `mcv status` dashboard for upcoming assignments, today's
  meetings, and recent announcements, including `--all` detail output.
- Added progress reporting for multi-course and multi-resource fetches while
  keeping machine-readable output clean.
- Added resource-specific aggregate and course-scoped search aliases, exact
  search support, and optional `fzf` interactive selection.
- Improved shell completion with fuzzy course aliases, readable help text,
  and canonical resource references.
- Fixed completion to default to the current semester, honor repeated
  `--semester` selections and `--all`, and hide out-of-scope course/resource
  references.
- Preserved the current-semester cache marker during incremental updates and
  recorded the server-selected current semester during cache refreshes.
- Made material downloads and folder archives use the remote filename or
  folder name when `--output` is omitted.

## 0.3.0

This release adds a host-calibrated, authenticated read-only release gate.

- Added opt-in CLI/Python live checks with dynamic historical-course fixture
  discovery, two-pass stability checks, optional-section classification, and
  sanitized fixture reports.
- Added the shared CLI/API semantic matrix for course resources, aggregate
  queries, canonical and official-URL dereferencing, cache namespaces, search,
  and explicitly configured material downloads/archives.
- Added typed aggregate `show`/`search` aliases, course-resource search
  aliases, multi-course `--courses` filters, and fuzzy course/reference
  completion for search pipelines.
- Added optional `fzf`-backed interactive selection to every local search
  alias, with course and resource-type scope preserved.
- Added explicit SQLite cache migrations for schemas 1, 2, and 3, with safe
  rejection of invalid or future schemas.
- Added isolated `MCV_CACHE_DIR`, `MCV_CONFIG_DIR`, and
  `MCV_PREFER_KEYRING` settings for reproducible CI runs.
- Added Python 3.11/3.12/3.13 quality coverage, dependency auditing, package
  build/install smoke checks, and a release gate requiring quality and live
  jobs.
- Added the MIT license for original project code. MyCourseVille content and
  the reverse-engineered integration remain subject to the upstream service's
  terms; this project is unofficial and not affiliated with MyCourseVille.

The live suite is intentionally not run by default. See
[docs/live-e2e.md](docs/live-e2e.md) before enabling it.
