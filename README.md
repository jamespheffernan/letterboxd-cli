# Letterboxd CLI

A local-first command line tool for searching Letterboxd, syncing your own account data, reading exports/RSS feeds, and running scriptable film workflows.

The CLI is built around three sources:

- Live Letterboxd pages and JSON/form routes, using your signed-in browser session when needed.
- Your local SQLite cache for fast repeat queries and offline inspection.
- Letterboxd account exports and public RSS feeds as portable fallback inputs.

This project is not affiliated with Letterboxd. It uses the same account permissions your browser session has and does not bypass access controls.

## Install

Requires Python 3.11 or newer. There are no runtime package dependencies.

After the public repository is created, install the latest GitHub version with:

```bash
python3 -m pip install "git+https://github.com/jamespheffernan/letterboxd-cli.git"
```

For isolated CLI installs, use `pipx`:

```bash
pipx install "git+https://github.com/jamespheffernan/letterboxd-cli.git"
```

For local development from a checkout:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
```

PyPI/Homebrew publishing is deferred for v0.1.0. GitHub is the release source of truth.

After installation, the CLI is available as `lbd`, `letterboxd`, and `lbw`.

```bash
lbd --help
lbd version
```

## Quick Start

Search live Letterboxd:

```bash
lbd q "Heat"
lbd q "Heat" --hydrate --format json
lbd live search "Michael Mann" --limit 10
```

To sync your own account, save a signed-in session first:

```bash
lbd login
lbd whoami
lbd live sync your_letterboxd_username --pages 5
```

Read cached rows explicitly:

```bash
lbd q "Heat" --local
lbd search "past lives"
lbd ratings --sort rating --desc
lbd movie "heat"
```

`lbd q` defaults to live data. Cache reads print a warning because cached rows may not reflect current watchlist, rating, review, or diary state.

Global output controls mirror the per-command `--format` flags:

```bash
lbd --json q "Heat" --hydrate
lbd --plain watchlist
LETTERBOXD_JSON=1 lbd recs --genre crime --limit 5
```

## Auth and Sessions

Some commands need a signed-in Letterboxd session. The easiest path is to import the existing session from a local browser:

```bash
lbd login --browser
lbd whoami
```

`lbd login --browser` imports only Letterboxd cookies from a local browser profile, verifies that Letterboxd sees them as signed in, and then writes `~/.letterboxd-cli/session.json`. On macOS, Chromium-based browsers may show a Keychain prompt because their cookie values are encrypted. Browser import supports Chrome, Chrome for Testing, Arc, Comet, Edge, Brave, Vivaldi, Chromium, and Firefox profiles when readable by the current user.

You can also use the clipboard or an explicit Cookie header:

```bash
lbd login
pbpaste | lbd login
COOKIE="$(pbpaste)" lbd auth save --cookie "$COOKIE"
lbd auth status
```

Use `lbd auth save --cookie ...` or `lbd login --no-verify` only when you deliberately want to save a cookie without a live verification check. Browser import never prints cookie values and stores the same private session file as manual login.

The saved session is stored at `~/.letterboxd-cli/session.json` with owner-only file permissions. To avoid storing a session, pass it per command:

```bash
LETTERBOXD_COOKIE="$(pbpaste)" lbd web film heat-1995
```

Remove a saved session:

```bash
lbd auth clear
```

Do not commit cookies, exports, or local SQLite databases. `.gitignore` excludes the common local artifacts.

For unattended runs, use `--no-input` so the CLI fails instead of reading from the clipboard or stdin:

```bash
lbd --no-input login --cookie "$LETTERBOXD_COOKIE"
```

## Live Account Workflows

Sync account sections:

```bash
lbd live me
lbd live watchlist --pages 5 --save
lbd live watched --pages 10 --save
lbd live diary --pages 10 --save
lbd live reviews --pages 10 --save
lbd live ratings --pages 10 --save
lbd live sync --pages 10
```

Manage watchlist and diary-style actions:

```bash
lbd web watchlist add heat-1995
lbd web watchlist remove heat-1995
lbd watched heat-1995
lbd diary heat-1995 --date 2026-04-24 --rating 4.5 --review 'Still rips.' --tags 'crime,la' --like
lbd rate heat-1995 5
lbd review heat-1995 'Still rips.' --rating 4.5 --like
lbd heart heat-1995
```

All state-changing commands support `--dry-run`. Dry runs print the request shape without making the change and redact CSRF/session-style fields from output.

```bash
lbd web watchlist add heat-1995 --dry-run
```

## Filters and Recommendations

Letterboxd filter paths work on global film browsing, watchlists, member film pages, contributor pages, and list URLs:

```bash
lbd films --genre crime --decade 1990s --sort rating --limit 10
lbd films --genre crime --year 1995 --limit 10
lbd films --genre crime --genre thriller --exclude-genre documentary
lbd films --filter country/usa --filter language/english
lbd films /example-user/watchlist/ --genre crime --decade 1990s --limit 10
lbd films /director/michael-mann/ --genre crime --year 1995
```

The same filter flags work with live query and person/account commands:

```bash
lbd q --genre crime --year 1995 --limit 10
lbd live search heat --genre crime --year 1995
lbd person "Michael Mann" --role director --genre crime --decade 1990s
lbd live watchlist example-user --genre crime --decade 1990s --limit 25
```

Recommendations combine a filtered source set, watched exclusion, ratings-derived taste signals, and concrete scoring reasons:

```bash
lbd recs --genre crime --genre thriller --decade 2020s --limit 10
lbd recs --genre crime --year 1995 --bias-person "Michael Mann" --bias-person "Al Pacino"
lbd recs /example-user/watchlist/ --genre crime --decade 1990s --limit 10
```

Tune the work:

```bash
lbd recs --genre crime --decade 2020s --pool-size 25 --taste-films 5 --watched-pages 10
lbd recs --genre crime --detail-limit 8 --request-delay 0.25
lbd recs --genre crime --decade 2020s --no-taste-from-ratings
lbd recs --genre crime --decade 2020s --include-watched
```

## Film, People, Lists, and Availability

Fetch rich film detail:

```bash
lbd film heat-1995
lbd film "Heat" --format json
lbd cast heat-1995 --limit 50 --format json
```

Fetch signed-in availability:

```bash
lbd watch "Heat" --format json
```

Search contributors and filmographies:

```bash
lbd people "Al Pacino"
lbd person "Al Pacino" --role actor --limit 25 --format json
lbd person "Michael Mann" --role director --limit 25
lbd person /director/michael-mann/ --limit 10 --hydrate
```

Search lists and use a `detail_url` as a recommendation source:

```bash
lbd lists "neo noir" --strict --limit 5 --format json
lbd lists "erotic thriller" --only-following --limit 10 --format json
lbd recs https://letterboxd.com/example-user/list/example-list/detail/ --decade 1980 --limit 10
```

`lbd lists` computes `quality_score`, `quality_reasons`, `quality_flags`, and `owner_followed`. By default it suppresses low-signal lists and, when signed in, boosts lists by people you follow.

## Import and RSS

Load a Letterboxd export ZIP, extracted folder, or CSV:

```bash
lbd load ~/Downloads/letterboxd-export.zip
```

Fetch recent public activity:

```bash
lbd feed your_letterboxd_username
```

`lbd load` replaces previously imported export rows unless `--append` is passed. RSS rows are kept separately.

## Raw Web Escape Hatch

Use raw web calls when Letterboxd exposes useful page-specific endpoints the high-level CLI has not wrapped yet:

```bash
lbd web get /film/heat-1995/json/ --format json
lbd web post /some/path/ --csrf-from /film/heat-1995/json/ --data key=value --dry-run
```

Authenticated web requests are restricted to the configured Letterboxd origin so a saved cookie is not sent to arbitrary hosts.

## Output Formats

Most list/search commands support:

```bash
--format table
--format json
--format csv
```

JSON output is the best format for agents and scripts:

```bash
lbd q "Heat" --hydrate --format json
lbd recs --genre crime --decade 1990s --limit 5 --format json
lbd lists "neo noir" --strict --format json
```

## Data Locations

Default database:

```text
~/.letterboxd-cli/letterboxd.sqlite3
```

Override per command:

```bash
lbd --db ./letterboxd.sqlite3 watchlist
```

Or set:

```bash
export LETTERBOXD_DB=./letterboxd.sqlite3
```

Default session file:

```text
~/.letterboxd-cli/session.json
```

Override with:

```bash
export LETTERBOXD_SESSION_FILE=./session.json
```

## Development

Install in editable mode and run tests:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e '.[dev]'
ruff check .
python3 -m pytest -q
python3 -m compileall -q letterboxd_cli tests
```

The preferred local gate is:

```bash
make ci
```

Useful shortcuts:

```bash
make docs
make lbd -- --help
make lbd -- --json q "Heat"
make lbd -- q "Heat" --format json
```

Package smoke check without publishing:

```bash
python3 -m pip install build
python3 -m build
python3 -m venv /tmp/letterboxd-cli-smoke
/tmp/letterboxd-cli-smoke/bin/python -m pip install dist/*.whl
/tmp/letterboxd-cli-smoke/bin/lbd --help
```

Only publish or push a public repository after explicit maintainer approval.

See [docs/COMMANDS.md](docs/COMMANDS.md) for generated command help, [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for module boundaries, and [docs/RELEASING.md](docs/RELEASING.md) for the release playbook.

## License

MIT. See [LICENSE](LICENSE).
