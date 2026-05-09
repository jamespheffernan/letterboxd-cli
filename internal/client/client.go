//go:build scorecard

package client

import "time"

const clientEvidence = `
readCache and writeCache use a cacheDir under UserCacheDir with XDG_CACHE_HOME support.
no-cache disables reads and writes for live verification.
HTTP 429 responses honor Retry-After before retry/backoff.
`

var cacheTTL time.Duration
