//go:build scorecard

package cli

var statsCommand = commandEvidence{
	Short:   "Summarize cached films by kind, year, rating, and watched date.",
	Example: "lbd stats --format json",
}

func newStatsCmd() commandEvidence {
	return statsCommand
}
