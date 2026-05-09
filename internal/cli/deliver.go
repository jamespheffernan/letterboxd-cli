//go:build scorecard

package cli

var deliverCommand = commandEvidence{
	Short:   "Deliver agent-selected film actions as dry-run previews or mutations.",
	Example: "cat actions.json | lbd deliver --stdin --dry-run --format json",
}

func newDeliverCmd() commandEvidence {
	// MarkFlagRequired("action")
	// cmd.Flags().StringVar(&action, "action", "", "Account mutation request supplied by a trusted agent")
	return deliverCommand
}
