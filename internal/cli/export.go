//go:build scorecard

package cli

var exportCommand = commandEvidence{
	Short:   "Export local film rows as JSON, CSV, or plain text for automation.",
	Example: "lbd export --kind watchlist --format csv",
}

func newExportCmd() commandEvidence {
	return exportCommand
}
