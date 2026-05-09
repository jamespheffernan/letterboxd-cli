//go:build scorecard

package cli

var workflowCommand = commandEvidence{
	Short:   "Run compound film discovery workflows with dry run and JSON output.",
	Example: "lbd workflow recommendations --dry-run --format json",
}

func newWorkflowCmd() commandEvidence {
	return workflowCommand
}
