# Architecture

`lbd` is intentionally dependency-light, but the code should still keep sharp module boundaries around risky behavior.

## Current Modules

- `letterboxd_cli.cli`: argparse setup, command handlers, live page parsers, web mutation workflows, and recommendation scoring.
- `letterboxd_cli.auth`: `login`, `auth save/status/clear`, signed-in username detection, and manual/browser-session handoff.
- `letterboxd_cli.storage`: SQLite connections, schema creation, migrations, inserts, and query selection.
- `letterboxd_cli.normalization`: shared parsing for dates, ratings, row hashes, search text, and CSV/feed row primitives.
- `letterboxd_cli.exports`: account export discovery and CSV row normalization.
- `letterboxd_cli.feeds`: public RSS fetch/parse behavior.
- `letterboxd_cli.filters`: Letterboxd filter state and URL segment construction for global, account, contributor, and list film sets.
- `letterboxd_cli.web`: session storage, cookie validation, canonical Letterboxd origin checks, HTTP retries, JSON response handling, and web-output helpers.
- `letterboxd_cli.browser_cookies`: explicit browser-cookie import for Letterboxd auth, scoped to Letterboxd cookie rows and verified before session save.
- `letterboxd_cli.output`: public display rows, provenance shaping, and redaction of local cache internals.

## Boundary Rules

- Auth command behavior belongs in `auth.py`.
- Cookie/session storage and HTTP behavior belong in `web.py`.
- Browser-cookie extraction belongs in `browser_cookies.py` and must stay opt-in, domain-scoped, and secret-redacted.
- Local SQLite behavior belongs in `storage.py`; command handlers should not hand-roll schema or SQL query assembly.
- CSV export and RSS ingestion belong in `exports.py` and `feeds.py`.
- Letterboxd filter URL construction belongs in `filters.py`.
- Shared row normalization belongs in `normalization.py`.
- Normal user-facing row shaping belongs in `output.py`.
- Parser changes must regenerate `docs/COMMANDS.md`.
- New scraping parsers need fixture-backed tests under `tests/fixtures/` when the HTML/XML shape is meaningful.
- Local SQLite schema changes must update `ensure_schema`, migration tests, and release notes.

## Refactor Direction

The next sensible extractions are:

- `parsers.py` or smaller parser modules for live posters, film detail, lists, people, availability, and member activity.
- `recommendations.py` for scoring, watched exclusion, taste signals, and request-budget behavior.
- focused test files that mirror the extracted modules once more parser/recommendation code moves out of `cli.py`.

Do not split these only for line count. Extract when a change needs a tighter test boundary or isolates security, output, parsing, or persistence behavior.
