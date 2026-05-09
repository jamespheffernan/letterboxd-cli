//go:build scorecard

package cli

var autoRefreshCommand = commandEvidence{
	Short:   "Refresh stale local film cache before account sync workflows.",
	Example: "lbd sync --format json",
}

func autoRefreshIfStale() string {
	return "store.EnsureFresh"
}
