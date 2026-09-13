# Refreshing live fixtures

1. Confirm that `mcv auth status` is authenticated on the host.
2. Run the two-pass calibration command in [live-e2e.md](live-e2e.md).
3. Inspect the report for the selected semester, cv_cids, availability, refs,
   and official URLs only.
4. Update protected CI variables deliberately, recording any expected optional
   section change in the release notes or CI change description.
5. Run the configured matrix once before relying on the scheduled job.

A fixture is stable only when both CLI and Python probes pass twice without
authentication, transport, HTTP, or parser failures. A valid empty collection
is retained as available; an unavailable optional typed collection is recorded
as unavailable. Never make a failing parser pass by marking a fixture empty.
