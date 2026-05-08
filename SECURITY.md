# Security

Letterboxd CLI can use your signed-in browser cookie for account actions. Treat that cookie like a password.

## Reporting

If you find a security issue, do not include real cookies, CSRF tokens, exports, or private account data in a public issue. Open a minimal report with reproduction steps and redact sensitive values.

## Session Handling

- `lbd login` stores sessions at `~/.letterboxd-cli/session.json` with owner-only permissions.
- `LETTERBOXD_COOKIE=...` can be used for one-off commands without writing a session file.
- `lbd auth clear` deletes the saved session file.
- Authenticated web requests are restricted to the configured Letterboxd origin.
- Dry-run output redacts CSRF/session-style values.
- `--no-input` prevents clipboard/stdin reads in automation.

## Scope

This project is not affiliated with Letterboxd and does not bypass access controls. Commands act with the permissions of the supplied browser session.
