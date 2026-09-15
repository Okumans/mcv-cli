# Python API

`mcv-api` provides the reusable client behind the `mcv` CLI. Its public import
namespace is `mcv_api`; it is independent of Typer, Rich, terminal output,
progress reporting, shell completion, authentication storage, and the SQLite
cache implementation.

## Installation

Add the API package to a uv-managed application:

```bash
uv add 'git+https://github.com/Okumans/mcv-cli.git#subdirectory=packages/mcv-api'
```

Or install it into an existing virtual environment:

```bash
uv pip install 'git+https://github.com/Okumans/mcv-cli.git#subdirectory=packages/mcv-api'
```

## Creating a client

The API does not implement login. Applications provide a `SessionProvider`
whose `get_session_cookies()` method returns the authenticated session cookies.

```python
from dataclasses import dataclass

from mcv_api import MCVAPI


@dataclass(frozen=True)
class CookieSession:
    cookies: dict[str, str]

    def get_session_cookies(self) -> dict[str, str]:
        return self.cookies


session = CookieSession({"laravel_session": "..."})
with MCVAPI(session) as api:
    courses = api.courses.list()
    materials = api.materials.list(courses[0].cv_cid) if courses else []
```

`MCVAPI` accepts optional injected HTTP clients, a timeout, a sleeper for
transport retry control, and an optional `cache_store`. Omit `cache_store` when
local caching and search are not needed. The API never creates or manages a
credential store itself.

## Resource clients

The facade exposes clients for courses, materials, assignments, announcements,
meetings, schedules, groups, portfolios, playlists, and web resources:

```python
course = api.courses.resolve("2110575")
assignments = api.assignments.list(course.cv_cid)
material = api.materials.get(course.cv_cid, 2160993)
```

Cross-course services are available under `api.aggregates`. `api.get()` accepts
a canonical `ResourceRef` or supported official MyCourseVille URL, and
`api.get_many()` resolves references sequentially in input order.

## Search

`api.search` is a local `SearchClient`. It never performs network I/O and
requires an injected object implementing the public `LocalStore` protocol:

```python
from mcv_api import MCVAPI

with MCVAPI(session, cache_store=store) as api:
    results = api.search.search("docker", cv_cid=86428, limit=20)
    resource = api.get(results[0].ref) if results else None
```

Search results are `SearchResult` summaries with typed `resource_type`, a
course-qualified `ref`, title, optional snippet, and score. The reference can
be passed directly to `api.get()`.

## References and models

Canonical references use:

```text
mcv:<resource-type>:<cv_cid>:<item_id>
```

Playlist collections use `mcv:playlist:<cv_cid>`. Addressable domain models
expose typed `resource_type` and `ref` properties. Those properties are
available to Python callers but are not duplicated as ordinary serialized model
fields.

## Errors

The public base exception is `MCVError`. Common subclasses include:

- `AuthenticationRequired`
- `AuthenticationError`
- `InvalidReferenceError`
- `UnsupportedResourceError`
- `NotFoundError`
- `AmbiguousError`
- `TransportError`
- `ParseError`
- `DownloadError`
- `SearchUnavailableError`

Errors expose structured fields such as `code`, `resource`, `operation`,
`retryable`, and `details`; callers should not parse exception messages.

## Dates and timestamps

Raw CourseVille temporal values remain available for faithful access. Typed
convenience properties return standard `date`, `time`, or timezone-aware
`datetime` values. Naive timestamps are interpreted as `Asia/Bangkok`; aware
timestamps are converted there. Malformed or sentinel values return `None`.

The API is read-only. It does not answer or submit assignments, upload files,
edit course content, join meetings, or control attendance.
