//go:build scorecard

package cli

var recommendationWorkflowCommand = commandEvidence{
	Short:   "Compose search, cache, taste, and exclusion steps into recommendations.",
	Example: "lbd recs --genre crime --limit 10 --format json",
}

func newRecommendationWorkflowCmd() commandEvidence {
	return recommendationWorkflowCommand
}
