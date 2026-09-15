# Release checklist

Before creating a GitHub Release:

- run the locked quality checks and the authenticated CLI/API live suite;
- inspect migration, both package builds, isolated API/CLI wheel-install, and
  Git URL checks;
- review `RELEASE_NOTES.md`, `SECURITY.md`, CI setup, fixture refresh, and
  account-rotation documentation;
- verify no credentials, raw HTML, private course content, or signed URLs are
  staged;
- create the release only after the release-gate job is green.

The repository uses one Git checkout for two distributions. Build both from the
workspace root:

```bash
uv build
uv build --package mcv-api
```

The CLI distribution is `mcv-cli` and exposes `mcv`; the reusable distribution
is `mcv-api` and exposes the `mcv_api` import namespace without a console
script. Keep their versions synchronized.

The live suite detects upstream HTML/session/parser drift. It does not turn
upstream behavior into a permanent exact-content snapshot.
