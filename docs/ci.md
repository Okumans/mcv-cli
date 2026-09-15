# Continuous integration

The `quality` job runs on pushes and pull requests. It tests Python 3.11,
3.12, 3.13, and 3.14, enforces the coverage threshold, runs Ruff and Pyright,
audits dependencies, builds both repository distributions, and tests each wheel
in an isolated environment. The API wheel is installed by itself to verify that
`mcv_api` imports without CLI/runtime modules. A separate environment installs
the API and CLI wheels together, verifies the `mcv` entry point and optional
`fzf` extra, and runs installed-package integration checks for CLI smoke
behavior, shell completion, and fuzzy search.

The `windows-quality` job runs the same Python-version matrix on
`windows-latest`. It exercises the non-live suite, builds native Windows
distributions, verifies the `mcv.exe` and `fzf.exe` entry points, and runs the
installed-package integration checks through PowerShell. The authenticated
live suite remains on Ubuntu because its protected terminal harness uses POSIX
pseudo-terminals.

For non-pull-request events, CI also installs both distributions from the Git
URL at the checked-out commit. This catches broken `#subdirectory` metadata for
the standalone API package and the root CLI package.

The `live-e2e` job runs only on protected default-branch pushes, `v*` tags,
the daily schedule, and manual dispatch. Configure these protected secrets:

```text
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
