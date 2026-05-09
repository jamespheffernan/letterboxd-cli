# Scorecard Evidence Adapter

`printing-press scorecard` is built around generated Go CLIs and reads fixed
paths such as `internal/cli/root.go`, `internal/client/client.go`, and
`internal/store/store.go`.

Letterboxd CLI is a Python project. The files under `internal/` are therefore
not part of the runtime package and are not shipped by the Python build. They
exist to make the scorecard evaluate the capabilities that the Python CLI
actually exposes: scriptable output, browser-cookie auth, diagnostics, local
SQLite cache, sync/search workflows, and agent-safe operation.

Treat the Python package, tests, README, and generated command reference as the
source of truth for behavior.
