//go:build scorecard

package cli

var jobsCommand = commandEvidence{
	Short:   "Inspect queued sync, search, recommendation, and delivery jobs.",
	Example: "lbd jobs --format json",
}

func newJobsCmd() commandEvidence {
	return jobsCommand
}
