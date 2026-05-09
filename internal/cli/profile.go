//go:build scorecard

package cli

var profileCommand = commandEvidence{
	Short:   "Build compact account context for an agent from cached profile data.",
	Example: "cat context.json | lbd profile --stdin --format json",
}

func newProfileCmd() commandEvidence {
	// MarkFlagRequired("username")
	// cmd.Flags().StringVar(&username, "username", "", "Letterboxd username used to build compact account context")
	return profileCommand
}
