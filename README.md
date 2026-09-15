# mcv

Ever have a hard time with MyCourseVille, downloading materials one file at a
time, wrestling with its interface, or simply wishing you could use a
terminal?

`mcv` is a small, unofficial command-line client for reading and organizing
MyCourseVille course content on Linux, macOS, and Windows.

Its basic workflow is:

```text
discover course content → get a stable reference → retrieve the resource
```

The client is read-only against MyCourseVille. It can download files and create
local archives, but it does not submit assignments, upload files, edit course
content, join meetings, or control attendance.

## Features

- Course and semester discovery
- Materials, folders, assignments, announcements, meetings, downloads, and archives
- Schedules, groups, portfolios, playlists, and web resources
- Material downloads and folder archives
- Stable course-qualified resource references
- Local cache and full-text search
- Interactive `fzf` search
- Human-readable tables, JSON, and JSONL output
- A status dashboard for assignments, meetings, and announcements

## Installation

`mcv` requires Python 3.11 or newer. This repository contains two
distributions: `mcv-cli` provides the `mcv` command, and `mcv-api` provides the
reusable Python client.

Install the CLI as an isolated [`uv`](https://docs.astral.sh/uv/) tool from GitHub:

```bash
uv tool install \
  --with 'git+https://github.com/Okumans/mcv-cli.git#subdirectory=packages/mcv-api' \
  'git+https://github.com/Okumans/mcv-cli.git'
mcv --version
```

On Windows, run the same installation from PowerShell. `uv` creates the
native `mcv.exe` entry point:

```powershell
uv tool install --with "git+https://github.com/Okumans/mcv-cli.git#subdirectory=packages/mcv-api" "git+https://github.com/Okumans/mcv-cli.git"
mcv --version
mcv --install-completion powershell
```

Install only the API in an application environment:

```bash
uv add 'git+https://github.com/Okumans/mcv-cli.git#subdirectory=packages/mcv-api'
```

`mcv-api` is a library and has no console script. Use `uv pip install` with the
same Git URL when installing into an existing virtual environment.

For local development:

```bash
git clone https://github.com/Okumans/mcv-cli.git
cd mcv-cli
uv tool install --editable .
```

For fuzzy search, add `--with fzf-bin` to the CLI command above. The optional
extra provides `fzf.exe` on supported Windows architectures.

## Authentication

Log in with a Chula account:

```bash
mcv auth login
```

Passwords are requested interactively and never accepted as command-line
arguments. Check or remove the current session with:

```bash
mcv auth status
mcv auth logout
```

Sessions use the operating system keyring when available, with an encrypted
local fallback otherwise. See [Authentication](docs/auth.md) for storage
behavior, environment variables, and non-interactive setups.

## Quick start

After logging in:

```bash
mcv status
mcv courses list
mcv courses 2110575 materials list
mcv courses 2110575 assignments list
mcv search "docker"
mcv search -z
```

Use `mcv --help` or `<command> --help` for command-specific options.

## Common commands

The main course-scoped form is:

```text
mcv courses COURSE RESOURCE ACTION
```

`COURSE` may be a CourseVille id, course number, or exact course title.

```bash
mcv courses 2110575 materials show 2160993
mcv courses 2110575 assignments show 2160997
mcv courses 2110575 materials archive "Week 1" --output ./week-1.zip
```

Select another semester with the global option:

```bash
mcv --semester 2025/2 courses list
```

See the [CLI reference](docs/cli.md) for selectors, cross-course commands,
`--all`, search aliases, filters, and output behavior.

## Stable references

Resources use course-qualified references:

```text
mcv:<resource-type>:<cv_cid>:<item_id>
mcv:assignment:86428:2160997
```

Retrieve one directly, or compose commands with one `--refs` value per line:

```bash
mcv get mcv:assignment:86428:2160997
mcv assignments list --pending --refs | xargs -r -n 20 mcv get
```

See [References and IDs](docs/cli.md#references-and-ids) for supported forms.

## Search

`mcv` maintains a local searchable cache. Search is local by default and does
not perform hidden network requests.

```bash
mcv courses 2110575 search "docker"
mcv search "docker" --type material --type assignment
mcv search "docker" --refresh
```

See [Search and cache](docs/search-and-cache.md) for cache behavior, filters,
refresh, fuzzy matching, and completion.

## Machine-readable output

Most commands support JSON and JSONL:

```bash
mcv --json courses 2110575 assignments list
mcv --jsonl assignments list --pending
```

Use `--envelope` for explicit protocol metadata and `--quiet` to suppress
progress output. See [Machine-readable output](docs/cli.md#machine-readable-output)
for batch behavior.

## Downloads

Download a material or archive a material folder:

```bash
mcv courses 2110575 materials download 2160993 --output ./lecture.pdf
mcv courses 2110575 materials archive "Week 1" --output ./week-1.zip
```

ZIP, TAR, and compressed TAR archives are supported. Existing files are not
overwritten unless `--force` is supplied.

## Python API

The reusable client is provided by the separate `mcv-api` distribution; import
it with `from mcv_api import MCVAPI`.

See [Python API documentation](docs/python-api.md) for authentication
injection, models, errors, and timestamp behavior.

## Documentation

- [CLI reference](docs/cli.md)
- [Authentication and credential storage](docs/auth.md)
- [Search and cache](docs/search-and-cache.md)
- [Python API](docs/python-api.md)
- [Development and architecture](docs/development.md)
- [Complete command showcases](docs/showcases.md)

## Development

```bash
uv sync
uv run pytest -q
uv run ruff check .
uv run pyright
```

Architecture, upstream compatibility, package boundaries, and live checks are
documented in [Development](docs/development.md).

## License

Original project code is licensed under the [MIT License](LICENSE).

`mcv` is an independent, unofficial client for MyCourseVille; MyCourseVille
content and service terms remain outside this license.
