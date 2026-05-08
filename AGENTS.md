# Repository Guidelines

## Project Structure

- `letterboxd_cli/cli.py`: parser, command handlers, import/scraper/persistence logic.
- `letterboxd_cli/web.py`: web session, cookie validation, origin safety, HTTP response handling.
- `letterboxd_cli/output.py`: public display-row shaping and provenance redaction.
- `tests/`: mocked unit tests plus small parser fixtures for exports, RSS parsing, live page parsing, auth, actions, filters, lists, and recommendations.
- `docs/`: release notes, command reference, and comparison/audit notes.
- `scripts/`: development helpers such as command-doc generation.

## Build, Test, and Development Commands

- `make install-dev`: create `.venv` and install editable dev dependencies.
- `make lint`: run Ruff.
- `make test`: run pytest.
- `make compile`: compile Python sources.
- `make docs`: regenerate `docs/COMMANDS.md` from the argparse parser.
- `make ci`: full local gate: lint, tests, compile, docs check, package build, and smoke install.
- `make lbd -- ...`: run the local editable CLI.

## Coding Style

- Keep stdout parseable for `--json` and `--plain`; send warnings and progress to stderr.
- Keep account mutations explicit and dry-run friendly.
- Do not send saved cookies to non-Letterboxd origins.
- Avoid runtime dependencies unless they clearly remove more maintenance burden than they add.
- Prefer small seams around security, output, parsing, and persistence over broad rewrites.

## Testing

- Add mocked tests for Letterboxd HTML/JSON parsing changes.
- Do not require live network or a real Letterboxd account for the default test suite.
- Run `make ci` before publishing or opening a PR.

## Security

- Never commit cookies, session files, exports, `.env` files, or local SQLite databases.
- Use `--no-input` in automation when clipboard/stdin reads would be surprising.
- Keep raw web escape-hatch behavior restricted to the configured Letterboxd origin.
