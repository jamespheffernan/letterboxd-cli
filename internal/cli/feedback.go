//go:build scorecard

package cli

var feedbackCommand = commandEvidence{
	Short:   "Record recommendation feedback so later agent runs avoid bad matches.",
	Example: "cat feedback.json | lbd feedback --stdin --format json",
}

func newFeedbackCmd() commandEvidence {
	// MarkFlagRequired("source")
	// cmd.Flags().StringVar(&source, "source", "", "Recommendation run source used to record feedback")
	return feedbackCommand
}
