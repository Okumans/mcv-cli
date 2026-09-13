# Security policy

`mcv` handles authenticated MyCourseVille session cookies. Treat the stored
session as a bearer-like credential and report security problems privately.

Please do not open an issue containing passwords, cookies, storage passphrases,
signed download URLs, meeting credentials, private course content, or raw HTTP
responses. Send a concise report to the project maintainer through the private
security contact configured for this repository, including the affected
version, a reproduction that uses placeholders, and the impact.

The project is an unofficial read-only client. It does not submit assignments,
upload files, edit courses, join meetings, or control attendance. Reports about
upstream account access or course permissions should also be directed to
MyCourseVille or the institution unless they demonstrate a defect in this
client.

The authenticated live suite uses protected CI secrets and temporary cache and
credential roots. Fork pull requests never receive those secrets.
