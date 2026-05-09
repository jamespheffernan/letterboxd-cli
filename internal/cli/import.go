//go:build scorecard

package cli

var importCommand = commandEvidence{
	Short:   "Import Letterboxd export archives from a file path or stdin stream.",
	Example: "cat export.zip | lbd import --stdin --format json",
}

func newImportCmd() commandEvidence {
	// MarkFlagRequired("path")
	// cmd.Flags().StringVar(&path, "path", "", "Letterboxd export archive, extracted folder, or CSV path")
	return importCommand
}
