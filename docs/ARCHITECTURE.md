# Architecture

`lbd` is intentionally dependency-light, but the code should still keep sharp module boundaries around risky behavior.

## Current Modules

- `letterboxd_cli.cli`: argparse setup, command handlers, import normalization, local SQLite persistence, Letterboxd page parsing, and recommendation scoring.
- `letterboxd_cli.web`: session storage, cookie validation, canonical Letterboxd origin checks, HTTP retries, JSON response handling, and web-output helpers.
- `letterboxd_cli.browser_cookies`: explicit browser-cookie import for Letterboxd auth, scoped to Letterboxd cookie rows and verified before session save.
- `letterboxd_cli.output`: public display rows, provenance shaping, and redaction of local cache internals.

## Boundary Rules

- Cookie/session behavior belongs in `web.py`.
- Browser-cookie extraction belongs in `browser_cookies.py` and must stay opt-in, domain-scoped, and secret-redacted.
- Normal user-facing row shaping belongs in `output.py`.
- Parser changes must regenerate `docs/COMMANDS.md`.
- New scraping parsers need fixture-backed tests under `tests/fixtures/` when the HTML/XML shape is meaningful.
- Local SQLite schema changes must update `ensure_schema`, migration tests, and release notes.

## Refactor Direction

The next sensible extractions are:

- `storage.py` for schema, migrations, inserts, and selects.
- `parsers.py` or smaller parser modules for RSS, live posters, lists, people, availability, and member activity.
- `recommendations.py` for scoring and request-budget behavior.

Do not split these only for line count. Extract when a change needs a tighter test boundary or isolates security, output, parsing, or persistence behavior.
