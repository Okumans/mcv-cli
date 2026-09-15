# Authentication

`mcv` authenticates directly against MyCourseVille and stores the resulting
session locally. Passwords are used only during login and are never stored by
the client.

## Login

Log in with a Chula account:

```bash
mcv auth login --type chula
```

For a MyCourseVille platform account:

```bash
mcv auth login --type platform --email
```

The login command prompts for the password. Passwords are not accepted as
command-line arguments. `--username` or `MCV_USERNAME` can provide the
non-secret username without a prompt.

Check or remove the stored session:

```bash
mcv auth status
mcv auth logout
```

## Credential storage

When a supported system keyring is available, `mcv` stores the authenticated
session there.

If no keyring backend is available, the session is stored in an AES-GCM
encrypted local file. Set `MCV_STORAGE_PASSPHRASE` when that fallback must be
used non-interactively.

Treat the stored session as a bearer-like credential. Do not share the keyring,
credential file, passphrase, or cache directory with untrusted users.

## Environment variables

For isolated automation:

- `MCV_CONFIG_DIR` selects the credential-file directory.
- `MCV_CACHE_DIR` selects the SQLite cache root.
- `MCV_PREFER_KEYRING=false` disables keyring use.
- `MCV_STORAGE_PASSPHRASE` supplies the fallback encryption passphrase.
- `MCV_USERNAME` supplies a non-secret username for login.

These settings are useful for ephemeral CI jobs and live checks. Do not point
them at a shared credential directory when rotating accounts.

## Authentication boundary

This credential-based MVP does not implement Google login or require a
MyCourseVille OAuth client. Browser OAuth and the public mobile API are outside
the current authentication boundary.

The reusable `mcv-api` package has no login flow or credential storage. It
accepts an injected session-cookie provider; see the [Python API
documentation](python-api.md).
