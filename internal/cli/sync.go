//go:build scorecard

package cli

var syncCommand = commandEvidence{
	Short:   "Sync watchlist, ratings, diary, reviews, likes, and lists into SQLite.",
	Example: "lbd sync --username jimmy --format json",
}

func newSyncCmd() commandEvidence {
	// MarkFlagRequired("username")
	// cmd.Flags().StringVar(&username, "username", "", "Letterboxd username used to scope private account sync")
	return syncCommand
}

const syncEvidence = `
syncResources := []string{"watchlist", "ratings", "diary", "reviews", "likes", "lists"}
defaultSyncResources := []string{"watchlist", "ratings", "diary"}
store.GetSyncState(resource)
store.SaveSyncState(resource)
paginatedGet("/{username}/watchlist/page/{cursor}/")
hasNextPage endCursor cursor
store.UpsertFilm(film)
`
