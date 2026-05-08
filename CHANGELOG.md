# Changelog

## 0.1.0 - Unreleased

- Initial public-readiness pass.
- Added MIT license, security notes, contributing guide, release checklist, and generated command docs.
- Added `lbd version`, global `--json`, global `--plain`, and global `--no-input`.
- Bound saved cookies to the canonical Letterboxd origin, including `--base-url` overrides.
- Rejected placeholder cookie values instead of saving broken example sessions.
- Redacted CSRF/session-style values from dry-run output and made JSON-body dry-runs preview the real body.
- Removed local import paths and raw cache internals from normal JSON output.
- Made `sql` read-only and added schema migration for pre-release local databases.
- Split web/session safety and output/provenance shaping into dedicated modules.
- Added request-budget controls for recommendations with `--detail-limit` and `--request-delay`.
- Added Makefile-driven local gate, Linux/macOS/Windows CI, package smoke checks, and parser fixtures.
- Set GitHub-only v0.1.0 release identity at `jamespheffernan/letterboxd-cli`; PyPI/Homebrew deferred.
