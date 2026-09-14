# Release notes

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
