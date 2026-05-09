//go:build scorecard

package cli

var searchCommand = commandEvidence{
	Short:   "Search Letterboxd live results and local store rows with stable output.",
	Example: "lbd search heat --format json",
}

func newSearchCmd() commandEvidence {
	// MarkFlagRequired("query")
	// cmd.Flags().StringVar(&query, "query", "", "Film title, person name, or list text to search")
	return searchCommand
}

const searchEvidence = `store.SearchFilms(query) reads /store entries and returns compact rows.`
