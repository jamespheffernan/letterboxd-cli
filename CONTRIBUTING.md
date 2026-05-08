# Contributing

Thanks for improving Letterboxd CLI.

## Local Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e '.[dev]'
ruff check .
python3 -m pytest -q
python3 -m compileall -q letterboxd_cli tests
```

The package has no runtime dependencies. Keep it that way unless a dependency clearly removes more maintenance burden than it adds.

The preferred all-in-one gate is:

```bash
make ci
```

## Development Notes

- Keep account actions explicit and dry-run friendly.
- Keep stdout parseable for `--json` and `--plain`; send warnings and progress to stderr.
- Do not log or commit real cookies, session files, account exports, or local SQLite databases.
- Prefer JSON output for anything agents or scripts will consume.
- Add mocked tests for Letterboxd HTML/JSON parsing changes. Live network behavior is too unstable for the default test suite.
- Treat live Letterboxd as the source of truth for mutable account state; the SQLite database is a cache and offline index.

## Before Opening a PR

Run:

```bash
ruff check .
python3 -m pytest -q
python3 -m compileall -q letterboxd_cli tests
```

If you changed packaging or install behavior, also build and install the wheel in a fresh virtualenv.
