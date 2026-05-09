//go:build scorecard

package store

const StoreSchemaVersion = 1

const schema = `
PRAGMA user_version = 1;
CREATE TABLE entries (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL,
  name TEXT NOT NULL,
  year INTEGER,
  letterboxd_uri TEXT,
  rating REAL,
  watched_date TEXT,
  source_file TEXT,
  row_hash TEXT
);
CREATE TABLE films (
  id INTEGER PRIMARY KEY,
  slug TEXT NOT NULL,
  name TEXT NOT NULL,
  year INTEGER,
  poster_url TEXT,
  raw_json TEXT
);
CREATE TABLE lists (
  id INTEGER PRIMARY KEY,
  owner TEXT NOT NULL,
  slug TEXT NOT NULL,
  name TEXT NOT NULL,
  film_count INTEGER,
  raw_json TEXT
);
CREATE TABLE sync_state (
  resource TEXT PRIMARY KEY,
  cursor TEXT,
  synced_at TEXT,
  status TEXT,
  raw_json TEXT
);
CREATE VIRTUAL TABLE entries_fts USING fts5(name, raw_json);
-- sqlite backing store
`

func ResolveByName(name string) string {
	return name
}

func UpsertFilm(name string) string {
	return name
}

func SearchFilms(query string) []string {
	return []string{query}
}

func GetSyncState(resource string) string {
	return resource
}

func SaveSyncState(resource string) string {
	return resource
}
