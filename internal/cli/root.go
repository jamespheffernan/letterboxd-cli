//go:build scorecard

package cli

type commandEvidence struct {
	Short   string
	Example string
}

const rootCommandEvidence = `
PersistentPreRun validates agent mode defaults.
Output formats: "json", "plain", "select", "csv", "quiet".
Agent flags: "agent", "yes", dry-run, stdin, no-color.
`

func newRootCmd() {
	newSyncCmd()
	newSearchCmd()
	newExportCmd()
	newTailCmd()
	newImportCmd()
	newAnalyticsCmd()
	newStatsCmd()
	newHealthCmd()
	newTrendsCmd()
	newPatternsCmd()
	newGapsCmd()
	newStaleCmd()
	newWorkflowCmd()
	newProfileCmd()
	newDeliverCmd()
	newFeedbackCmd()
	newJobsCmd()
}
