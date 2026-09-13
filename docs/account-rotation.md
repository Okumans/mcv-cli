# Live account rotation

The live account is operational test infrastructure, not a repository secret.
Use a least-privilege read-only student account where the service permits it.

When rotating it:

- create and verify the replacement account before changing CI variables;
- run host calibration and review the sanitized report;
- update the protected username, provider, password, storage passphrase, and
  fixture values together;
- run the configured CLI/API matrix manually;
- revoke the old session and remove its CI secret;
- check the logs and artifacts for accidental credential exposure.

Never commit encrypted credential files, keyring exports, cookies, passwords,
signed URLs, meeting credentials, or private course snapshots. If an account
expires, treat the live job as blocked by authentication and rotate the account;
do not weaken parser or transport assertions.
