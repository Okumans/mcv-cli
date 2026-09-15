# Development

This document describes the internal architecture of `mcv`, its coupling to
MyCourseVille's authenticated web interface, and the checks used during
development. The exhaustive examples and evaluation notes remain in
[`showcases.md`](showcases.md).

## Repository and package boundaries

The project uses one Git repository and two distributions:

```text
mcv-cli distribution                     mcv-api distribution
┌─────────────────────────────┐          ┌─────────────────────────────┐
│ mcv_cli: commands, output,  │          │ mcv_api: clients, parsers,  │
│ auth, storage, cache, and   │ depends  │ models, refs, and search    │
│ completion                  │─────────▶│                             │
└─────────────────────────────┘          └─────────────────────────────┘
```

The root project is `mcv-cli` and exposes the `mcv` console script. The
workspace member at `packages/mcv-api` builds `mcv-api` and exposes the
`mcv_api` import namespace. The CLI depends on the API package; the API package
does not depend on the CLI.

The API package contains transport, parsers, Pydantic domain models, typed
references, errors, aggregates, and local-search protocols. The CLI package
contains command orchestration, terminal presentation, authentication,
credential storage, SQLite cache, completion, and progress reporting.

## Local development

From the repository root:

```bash
uv sync
uv run pytest -q
uv run pytest -q packages/mcv-api/tests
uv run ruff check .
uv run pyright
```

Build both distributions:

```bash
uv build
uv build --package mcv-api
```

The workspace shares one lockfile. `uv lock` resolves both packages, while each
package keeps its own build metadata and dependency boundary. See the
[continuous-integration checks](ci.md) for isolated wheel and Git URL smoke
tests, and [releasing](releasing.md) for the release gate.

## Upstream compatibility

`mcv` relies on MyCourseVille's current authenticated HTML and AJAX behavior.
Changes to routes, HTML elements, classes, data attributes, form fields,
CSRF/session behavior, AJAX parameters, or response shapes may require updates
to the transport layer, clients, or parsers.

That coupling is intentional for this unofficial read-only client. When the
site changes, check authentication first, then the affected route/parser and
the authenticated checks documented in [live-e2e.md](live-e2e.md).

The project does not use browser automation as a fallback and does not expose
write operations. MyCourseVille content and service terms remain outside the
project's MIT license.

## Testing boundaries

The API tests live under `packages/mcv-api/tests` and can run against the API
package without importing the CLI. Runtime, presentation, CLI, integration,
and authenticated live checks remain under `tests/`.

The API import boundary must remain free of Typer, Rich, keyring, platformdirs,
credential storage, and CLI modules. The standalone API wheel is installed in a
clean environment in CI to verify this boundary. The CLI wheel is tested with
the API wheel installed as its dependency.

Authenticated live checks are opt-in and read-only. They calibrate current
upstream behavior rather than turning private course content into permanent
fixtures. See [live-e2e.md](live-e2e.md), [fixture-refresh.md](fixture-refresh.md),
and [account-rotation.md](account-rotation.md) before enabling them.

## Reference projects

The following references informed the project sessions. The first is
especially important because it informed the authentication design:

- [CEDT-Chula/mcv-api-python-unofficial](https://github.com/CEDT-Chula/mcv-api-python-unofficial) — prior art for the MyCourseVille session-cookie authentication flow and reverse-engineered Python interaction model.
- [MyCourseVille](https://www.mycourseville.com/) — the upstream service whose authenticated pages and resource behavior this client reads.

These references are interoperability and research sources, not runtime
dependencies or claims of affiliation. This project is independent and
read-only.

## Contribution checklist

Before submitting a change:

1. Keep pure API code independent of CLI/runtime imports.
2. Add or update focused tests in the package that owns the behavior.
3. Run the local checks and inspect generated package metadata when packaging
   changes are involved.
4. Do not stage credentials, raw HTML, private course content, or signed URLs.
