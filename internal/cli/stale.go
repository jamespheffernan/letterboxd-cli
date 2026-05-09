//go:build scorecard

package cli

var staleCommand = commandEvidence{
	Short:   "List cache resources that need refresh before agent workflows continue.",
	Example: "lbd stale --format json",
}

func newStaleCmd() commandEvidence {
	return staleCommand
}
