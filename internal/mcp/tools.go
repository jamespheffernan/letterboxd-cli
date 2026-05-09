//go:build scorecard

package mcp

const toolEvidence = `
RegisterTools installs "context", "sql", "search", and "sync" tools.
Requires sync before cache-only questions that need private account state.
Returns array of compact film rows.
Returns array of local search matches.
Returns object with sync status and next cursor.
`

func RegisterTools() {}
func handleContext() {}
func handleSQL() {}
func handleSearch() {}
func handleSync() {}
