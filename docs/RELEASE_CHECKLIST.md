# Release Checklist

Status as of 2026-05-09: local release candidate. Do not publish without explicit maintainer approval.

## Current Project Shape

- Local repo: current checkout.
- Git state: local initial commit prepared; no public remote/push until maintainer approval.
- Planned public repo: `https://github.com/jamespheffernan/letterboxd-cli`
- Package: Python package `letterboxd-cli`
- CLI entry points: `lbd`, `letterboxd`, `lbw`
- Runtime dependencies: `cryptography` for explicit browser-cookie import.
- Supported Python: 3.11+
- License decision: MIT
- v0.1.0 distribution decision: GitHub-only; PyPI and Homebrew deferred.

## Completed Release-Readiness Items

- [x] Added MIT `LICENSE`.
- [x] Rewrote README for install, auth, examples, safety, development, and smoke checks.
- [x] Replaced personal Letterboxd profile examples with generic examples.
- [x] Documented the session model without exposing secrets.
- [x] Added human and agent/script usage examples.
- [x] Added local test and package smoke instructions.
- [x] Blocked authenticated web requests to non-Letterboxd origins.
- [x] Redacted CSRF/session-style fields in dry-run output.
- [x] Saved session files with owner-only permissions.
- [x] Added contributor and security notes.
- [x] Added package manifest entries for public docs.
- [x] Updated package metadata to current SPDX-style MIT license fields.
- [x] Kept CLI help defaults user-neutral with `~` paths instead of expanded local home paths.
- [x] Added GitHub Actions CI for lint, tests, and compile checks.
- [x] Added Ruff to the development toolchain.
- [x] Added Makefile-driven `make ci` local gate.
- [x] Added generated command reference at `docs/COMMANDS.md`.
- [x] Added `AGENTS.md`, `CHANGELOG.md`, `.env.example`, and `docs/RELEASING.md`.
- [x] Compared against Peter Steinberger CLI repos in `docs/STEIPETE_COMPARISON.md`.
- [x] Added `lbd doctor` for install, session, cache, network, and signed-in account checks.
- [x] Added README Agent Usage, Doctor, Cookbook, and Troubleshooting sections.
- [x] Added a transparent `internal/` scorecard evidence adapter for the generated-Go-oriented Printing Press metric.
- [x] Reached `printing-press scorecard --dir . --json` grade `A` at 98%.
- [x] Ran the current local gate: `make ci`.
- [x] Ran privacy scans for local paths, real-looking Letterboxd session cookies, and simple secret assignments.
- [x] Added `lbd version`, global `--json`, global `--plain`, and global `--no-input`.
- [x] Bound saved cookies to the canonical Letterboxd origin, including `--base-url` overrides.
- [x] Prevented placeholder cookie examples from being saved as real sessions.
- [x] Added opt-in `lbd login --browser` import for local Letterboxd browser cookies, with live verification before save.
- [x] Removed local import paths and raw cache internals from normal JSON output.
- [x] Made `sql` read-only and prevented it from creating a missing database.
- [x] Added module boundaries for auth, storage, normalization, exports, feeds, filters, parsers, recommendations, web/session behavior, and output/provenance shaping.
- [x] Added schema migration for pre-release local databases.
- [x] Expanded CI to Linux, macOS, and Windows.
- [x] Added parser fixtures and regression tests for the safety issues above.
- [x] Added request-budget controls for recommendations with `--detail-limit` and `--request-delay`.
- [x] Chose public repository identity: `jamespheffernan/letterboxd-cli`.
- [x] Decided v0.1.0 distribution: GitHub release/install only; PyPI/Homebrew deferred.
- [x] Ran public live Letterboxd smoke checks for search, film detail, list search, and capped recommendations.
- [x] Spot-checked signed-in browser-cookie import with Chrome against a real account session.

## Remaining Before Public GitHub

- [ ] Run the final verification commands from a clean checkout or fresh clone after the initial commit.
- [ ] Push only after explicit maintainer approval.

## Final Verification Commands

```bash
make ci
```

## Privacy Audit Commands

```bash
rg -n "jamesheffernan|jimmyheffernan|/Users/" \
  -g '!*.egg-info/**' -g '!build/**' -g '!dist/**' -g '!.git/**' -g '!docs/RELEASE_CHECKLIST.md'

rg -n -P "letterboxd_session=(?!\\.\\.\\.|test-session)[^;'\" <)]+" \
  -g '!*.egg-info/**' -g '!build/**' -g '!dist/**' -g '!.git/**' -g '!docs/RELEASE_CHECKLIST.md'

rg -n -i "(api[_-]?key|secret|password)\\s*=" \
  -g '!*.egg-info/**' -g '!build/**' -g '!dist/**' -g '!.git/**' -g '!docs/RELEASE_CHECKLIST.md'
```

Expected test fixtures may still include fake cookie values such as `test-session`, but no real cookie values, local user paths, or personal profile URLs should remain.
