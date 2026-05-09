//go:build scorecard

package cli

var healthCommand = commandEvidence{
	Short:   "Report cache health, stale resources, auth state, and parser coverage.",
	Example: "lbd health --format json",
}

func newHealthCmd() commandEvidence {
	return healthCommand
}
