# Peter Steinberger CLI Comparison

Updated 2026-05-08 after the adversarial release-readiness and module-extraction pass.

## Sources Sampled

- [`steipete/gogcli`](https://github.com/steipete/gogcli), which currently redirects to [`openclaw/gogcli`](https://github.com/openclaw/gogcli)
- [`steipete/bslog`](https://github.com/steipete/bslog)
- [`steipete/camsnap`](https://github.com/steipete/camsnap)
- [`steipete/aibench`](https://github.com/steipete/aibench)
- [`steipete/ghx`](https://github.com/steipete/ghx)

## What His Repos Tend To Do

- Put the user-facing promise in the first screen: what the CLI does, who it is for, and why it exists.
- Treat JSON/plain stdout and human stderr as a contract, not decoration.
- Make auth and secrets explicit, with strong warnings about what never belongs in git.
- Include one obvious local gate: build, lint, test, docs, package, and smoke where the project size warrants it.
- Keep docs practical: install, quick start, auth, examples, output modes, environment variables, release notes.
- Support agents and automation directly with `--json`, `--plain`, `--no-input`, `--dry-run`, and safety controls.
- Use CI and release automation as part of the product surface, not as an afterthought.
- Keep a repo-local `AGENTS.md` so future agent work follows the project's rules.
- Use fixtures/testdata for parsers and command behavior that can drift.

## What We Changed To Match That Bar

| Area | Before | Now |
| --- | --- | --- |
| Cookie safety | Saved cookies could follow `--base-url` to a non-Letterboxd host. | `letterboxd_cli.web` binds cookies to the canonical Letterboxd origin and rejects non-Letterboxd base URLs when a session is present. |
| Auth onboarding | Placeholder examples like `letterboxd_session=...` could be saved and manual cookie copying was the happy path. | Placeholder-looking cookie values are rejected, `lbd login --browser` imports only Letterboxd cookies from local browser profiles, and login verifies before save. |
| Dry runs | `web post --json-body ... --dry-run` did not show the body that would be sent. | Dry-run output now includes content type, redacted headers, and the real JSON/form body preview. |
| Output privacy | Normal JSON output exposed local `source_path`, `raw_json`, and cache internals. | `letterboxd_cli.output` shapes public rows and strips private path/cache fields. |
| DB safety | `sql` was called read-only but created/mutated DB files through schema setup. | `sql` opens SQLite in read-only mode and fails if the DB is missing. |
| Schema durability | `CREATE TABLE IF NOT EXISTS` only; old DBs could miss columns. | `ensure_schema` now adds missing columns and sets `PRAGMA user_version`. |
| God module | Everything lived in one large `cli.py`. | Core seams extracted: `auth.py`, `storage.py`, `normalization.py`, `exports.py`, `feeds.py`, `filters.py`, `web.py`, and `output.py`. `cli.py` now owns command orchestration plus the remaining live parsers/recommendations. |
| Fake command option | `live search --type all` implied support that only parsed films. | The parser now exposes only `--type films`. |
| Recommendations crawl budget | Defaults could fetch a lot of detail pages synchronously. | `recs` has `--detail-limit` and `--request-delay`, with a smaller default detail cap. |
| Install/docs | Local editable install only, invalid Makefile JSON example, quick start before auth. | README distinguishes local checkout from future public install, fixes global flag ordering, and puts auth before account sync. |
| Command docs | Raw argparse dump only. | Generated docs now include usage notes for global flags, auth/session, dry-run, `live sync`, and read-only SQL. |
| Test fixtures | Tests were all tiny inline strings. | Added `tests/fixtures/` for RSS and live watchlist parser coverage. |
| CI | macOS only. | CI matrix covers Linux, macOS, and Windows across Python 3.11-3.14. |
| Packaging | sdist omitted documented Makefile and shipped internal comparison/checklist via broad docs include. | Manifest includes Makefile, public docs, scripts, tests, and fixtures; internal audit docs are no longer included by wildcard. |

## Would He Ship It This Way?

Closer, yes. The project now has the main traits his polished CLIs show: scriptable output, explicit auth/session docs, local verification, generated command reference, smoke install, CI, release checklist, and safety rails around mutation/auth.

The remaining release gates after this pass are:

- The public repo `jamespheffernan/letterboxd-cli` is created and pushed after explicit approval.
- Keep an eye on browser-cookie storage drift. The Chrome signed-in import has been smoke-tested locally, but browser vendors can change encrypted-cookie formats.
- GitHub Actions runs on the pushed commit.
- The large `cli.py` keeps shrinking. The next serious extractions are live parser modules and recommendation scoring.
- PyPI/Homebrew remain deferred beyond v0.1.0.
- Optional niceties such as shell completions, a docs site, and release automation can wait, but they are the next Steinberger-style polish layer.

## Current Verdict

This is now release-candidate quality for a small personal OSS CLI, with explicit remaining release blockers. It is not yet at `gogcli` scale, and it should not pretend to be. It is much closer to the way Peter's repos behave: direct promise, clear auth model, safer automation defaults, parseable output, fixture-backed tests, smaller modules around risky behavior, and one command to verify the project.
