# Continuous integration

The `quality` job runs on pushes and pull requests. It tests Python 3.11,
3.12, and 3.13, enforces the coverage threshold, runs Ruff and Pyright,
audits dependencies, builds the package, installs the wheel into an isolated
environment, and runs CLI version/help smoke checks.

The `live-e2e` job runs only on protected default-branch pushes, `v*` tags,
the daily schedule, and manual dispatch. Configure these protected secrets:

```text
MCV_E2E_PROVIDER
MCV_E2E_USERNAME
MCV_E2E_PASSWORD
MCV_STORAGE_PASSPHRASE
MCV_E2E_SEMESTER
MCV_E2E_PRIMARY_COURSE
MCV_E2E_SECONDARY_COURSE       # optional
MCV_E2E_SEARCH_QUERY            # optional; otherwise derived from a material title
MCV_E2E_*_REF / *_URL / *_AVAILABLE
```

The job sets `MCV_CONFIG_DIR` and `MCV_CACHE_DIR` below the runner's temporary
directory, uses `MCV_PREFER_KEYRING=false`, and never runs with those secrets
on fork pull requests. The release gate depends on both quality and live jobs;
it does not publish a release by itself.
