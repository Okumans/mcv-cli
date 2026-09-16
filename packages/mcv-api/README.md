# mcv-api

`mcv-api` is the reusable, presentation-free Python client for reading
MyCourseVille content. It contains no Typer CLI, Rich output, authentication
storage, or local cache implementation.

Install it directly from this repository:

```bash
uv add 'git+https://github.com/Okumans/mcv-cli.git#subdirectory=packages/mcv-api'
```

The public import namespace is `mcv_api`:

```python
import asyncio

from mcv_api import MCVAPI


class Session:
    def get_session_cookies(self) -> dict[str, str]:
        return {"laravel_session": "..."}


async def main() -> None:
    async with MCVAPI(Session(), max_concurrency=8) as api:
        courses = await api.courses.list()


asyncio.run(main())
```

Applications provide a session-cookie provider. The `cache_store` argument is
optional; omit it when a local cache is not needed. Network-bearing resource
and aggregate methods are awaitable, and `MCVAPI` must be closed with
`async with` or `await api.aclose()`. `max_concurrency` bounds in-flight
requests made by aggregate fan-out (default: 8).
