# Architecture

`lbd` is intentionally dependency-light, but the code should still keep sharp module boundaries around risky behavior.

## Current Modules

- `letterboxd_cli.cli`: argparse setup, command handlers, live fetch orchestration, and web mutation workflows.
- `letterboxd_cli.auth`: `login`, `auth save/status/clear`, signed-in username detection, and manual/browser-session handoff.
- `letterboxd_cli.storage`: SQLite connections, schema creation, migrations, inserts, and query selection.
- `letterboxd_cli.normalization`: shared parsing for dates, ratings, row hashes, search text, and CSV/feed row primitives.
- `letterboxd_cli.exports`: account export discovery and CSV row normalization.
- `letterboxd_cli.feeds`: public RSS fetch/parse behavior.
- `letterboxd_cli.filters`: Letterboxd filter state and URL segment construction for global, account, contributor, and list film sets.
- `letterboxd_cli.parsers`: Letterboxd HTML parsing, film/person/list/live row extraction, URL normalization, and display cleanup helpers.
- `letterboxd_cli.recommendations`: list quality scoring, recommendation scoring, person-key normalization, watched-row slug extraction, and crawl pacing.
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
- Letterboxd HTML parsing belongs in `parsers.py`; command handlers should not contain regexes for page shapes.
- Recommendation/list-quality scoring belongs in `recommendations.py`; command handlers should only assemble inputs and print results.
- Shared row normalization belongs in `normalization.py`.
- Normal user-facing row shaping belongs in `output.py`.
- Parser changes must regenerate `docs/COMMANDS.md`.
- New scraping parsers need fixture-backed tests under `tests/fixtures/` when the HTML/XML shape is meaningful.
- Local SQLite schema changes must update `ensure_schema`, migration tests, and release notes.

## Refactor Direction

The next sensible extractions are:

- `live.py` for live fetch orchestration if those workflows grow beyond the current command handlers.
- `mutations.py` for watchlist/diary/rating/review form workflows if the state-changing surface expands.
- focused parser/recommendation test files if those modules start carrying more direct unit coverage than command-level regression tests.

Do not split these only for line count. Extract when a change needs a tighter test boundary or isolates security, output, parsing, or persistence behavior.
