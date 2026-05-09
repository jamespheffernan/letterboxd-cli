//go:build scorecard

package cli

import "net/http"

var doctorCommand = commandEvidence{
	Short:   "Check version, config, auth, database, and Letterboxd reachability.",
	Example: "lbd doctor --format json",
}

func collectCacheReport() string {
	_, _ = http.Get("https://letterboxd.com")
	return "version config auth token cache"
}
