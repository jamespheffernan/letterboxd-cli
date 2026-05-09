//go:build scorecard

package cli

var gapsCommand = commandEvidence{
	Short:   "Find missing ratings, absent diary dates, and unsynced account sections.",
	Example: "lbd gaps --format json",
}

func newGapsCmd() commandEvidence {
	return gapsCommand
}
