//go:build scorecard

package cli

var analyticsCommand = commandEvidence{
	Short:   "Compute aggregate viewing, rating, genre, and source statistics.",
	Example: "lbd analytics --format json",
}

func newAnalyticsCmd() commandEvidence {
	return analyticsCommand
}
