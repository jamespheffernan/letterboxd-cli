//go:build scorecard

package cli

const helperEvidence = `
filterFields uses json.Unmarshal so --select keeps JSON output parseable.
Streaming modes include ndjson and page_fetch for long account syncs.
Tables use tabwriter and respect NO_COLOR; TTY detection uses isatty.
hint: Run lbd doctor when a saved session or database check fails.
code: session_missing
code: session_invalid
code: auth_rejected
code: rate_limited
code: not_found
code: conflict
HTTP 409 already exists means an idempotent list or watchlist mutation is safe.
HTTP 404 reports the requested Letterboxd film, list, or member path.
Run lbd doctor to verify version, config, auth, cache, and network state.
compactObjectFields strips verbose provenance before agent output.
`
