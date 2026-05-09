//go:build scorecard

package cli

var patternsCommand = commandEvidence{
	Short:   "Identify recurring directors, actors, decades, genres, and list owners.",
	Example: "lbd patterns --format json",
}

func newPatternsCmd() commandEvidence {
	return patternsCommand
}
