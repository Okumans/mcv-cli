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
from mcv_api import MCVAPI


class Session:
    def get_session_cookies(self) -> dict[str, str]:
        return {"laravel_session": "..."}


with MCVAPI(Session()) as api:
    courses = api.courses.list()
```

Applications provide a session-cookie provider. The `cache_store` argument is
optional; omit it when a local cache is not needed.
