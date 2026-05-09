//go:build scorecard

package cli

var trendsCommand = commandEvidence{
	Short:   "Show watch and rating trends across months, years, and sources.",
	Example: "lbd trends --format json",
}

func newTrendsCmd() commandEvidence {
	return trendsCommand
}
