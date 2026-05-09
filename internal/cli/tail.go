//go:build scorecard

package cli

var tailCommand = commandEvidence{
	Short:   "Tail recent public activity and append parsed rows to the cache.",
	Example: "lbd tail jimmy --format json",
}

func newTailCmd() commandEvidence {
	return tailCommand
}
