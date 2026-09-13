# Release checklist

Before creating a GitHub Release:

- run the locked quality checks and the authenticated CLI/API live suite;
- inspect migration, packaging, wheel-install, and version checks;
- review `RELEASE_NOTES.md`, `SECURITY.md`, CI setup, fixture refresh, and
  account-rotation documentation;
- verify no credentials, raw HTML, private course content, or signed URLs are
  staged;
- create the release only after the release-gate job is green.

The live suite detects upstream HTML/session/parser drift. It does not turn
upstream behavior into a permanent exact-content snapshot.
