# Command Reference

Generated from the current argparse parser. Regenerate with:

```bash
make docs
```

## Usage Notes

- Global flags such as `--json`, `--plain`, `--db`, `--session-file`, and `--no-input` go before the command: `lbd --json q "Heat"`.
- Per-command output flags go after the command: `lbd q "Heat" --format json`.
- Commands under `web`, `login`, `auth`, `whoami`, and signed-in availability/actions use the saved or provided browser session.
- State-changing commands support `--dry-run` where available and redact CSRF/session-style values in previews.
- `live sync` and account collection commands need either an explicit username or a signed-in session that can reveal the username.
- `sql` opens the local database read-only and never creates a missing database.

## `lbd`

```text
usage: lbd [-h] [--db DB] [--session-file SESSION_FILE] [--cookie COOKIE] [--base-url BASE_URL] [--json] [--plain]
           [--no-input] [--version]
           {version,doctor,load,feed,login,whoami,query,q,search,watchlist,history,ratings,reviews,movie,film,watch,where-to-watch,availability,streaming,providers,cast,people,lists,person,films,recs,log,watched,diary,rate,review,heart,like,stats,export,sql,auth,web,live} ...

Search live Letterboxd, sync account sections, inspect a local SQLite cache, and run scriptable film workflows.

positional arguments:
  {version,doctor,load,feed,login,whoami,query,q,search,watchlist,history,ratings,reviews,movie,film,watch,where-to-watch,availability,streaming,providers,cast,people,lists,person,films,recs,log,watched,diary,rate,review,heart,like,stats,export,sql,auth,web,live}
    version                 Print the lbd version.
    doctor                  Check local install, session, database, and Letterboxd reachability.
    load                    Load a Letterboxd export ZIP, folder, or CSV.
    feed                    Fetch and store recent public RSS activity.
    login                   Save your signed-in Letterboxd browser cookie.
    whoami                  Show the signed-in Letterboxd username detected from the saved session.
    query                   Query local data and/or live Letterboxd, then display or save results.
    q                       Query local data and/or live Letterboxd, then display or save results.
    search                  Search across all imported data.
    watchlist               Show watchlist rows.
    history                 Show diary and watched history rows.
    ratings                 Show ratings.
    reviews                 Show reviews.
    movie                   Show everything known about a film title.
    film                    Fetch live film details: poster URLs, cast, crew, and account actions.
    watch (where-to-watch, availability, streaming, providers)
                            Fetch the signed-in Where to watch panel for a film.
    cast                    Fetch the live cast for a film.
    people                  Search Letterboxd contributors such as actors, directors, and writers.
    lists                   Search live Letterboxd lists and return list URLs usable as film-set bases.
    person                  Fetch a live actor/director/writer filmography from Letterboxd.
    films                   Browse any live Letterboxd film set with metadata filters.
    recs                    Recommend unwatched films from a filtered Letterboxd set with grounded reasons.
    log                     Log, rate, review, tag, and like a film.
    watched                 Mark a film watched, optionally with rating/review/like fields.
    diary                   Add a film to your diary. Defaults to today's date when --date is omitted.
    rate                    Set a star rating for a film.
    review                  Add or update a review for a film.
    heart                   Heart/like a film.
    like                    Heart/like a film.
    stats                   Show local database summary stats.
    export                  Export query results.
    sql                     Run a read-only SQL query against the local database.
    auth                    Manage saved Letterboxd web session cookies.
    web                     Use your authenticated Letterboxd web session.
    live                    Read live Letterboxd pages with your web session.

options:
  -h, --help                show this help message and exit
  --db DB                   SQLite database path. Defaults to ~/.letterboxd-cli/letterboxd.sqlite3
  --session-file SESSION_FILE
                            Saved Letterboxd web session path. Defaults to ~/.letterboxd-cli/session.json
  --cookie COOKIE           Letterboxd Cookie header. Overrides saved session for this run.
  --base-url BASE_URL       Letterboxd web base URL.
  --json                    Prefer JSON output for commands that support structured output.
  --plain                   Prefer stable plain output for commands that support it.
  --no-input                Never read interactive input such as the clipboard or stdin.
  --version                 show program's version number and exit
```

## `lbd version`

```text
usage: lbd version [-h] [--format {table,json}]

options:
  -h, --help             show this help message and exit
  --format {table,json}
```

## `lbd doctor`

```text
usage: lbd doctor [-h] [--format {table,json}] [--skip-network]

options:
  -h, --help             show this help message and exit
  --format {table,json}
  --skip-network         Skip Letterboxd reachability and sign-in checks.
```

## `lbd load`

```text
usage: lbd load [-h] [--append] path

positional arguments:
  path        Path to a Letterboxd export ZIP, extracted folder, or CSV file.

options:
  -h, --help  show this help message and exit
  --append    Append rows instead of replacing export rows.
```

## `lbd feed`

```text
usage: lbd feed [-h] [--url URL] [--limit LIMIT] [--format {table,json,csv}] [username]

positional arguments:
  username                  Letterboxd username.

options:
  -h, --help                show this help message and exit
  --url URL                 Custom RSS URL.
  --limit LIMIT             Rows to print after fetching.
  --format {table,json,csv}
```

## `lbd login`

```text
usage: lbd login [-h] [--cookie COOKIE] [--clipboard] [--no-verify]
                 [--browser [{auto,chrome,arc,comet,edge,brave,vivaldi,chromium,firefox}]]
                 [--browser-profile BROWSER_PROFILE]

options:
  -h, --help                show this help message and exit
  --cookie COOKIE           Raw Cookie header copied from your signed-in browser.
  --clipboard               Read the cookie from the macOS clipboard. This is also tried automatically when --cookie is
                            omitted.
  --no-verify               Save without checking that Letterboxd accepts the session.
  --browser [{auto,chrome,arc,comet,edge,brave,vivaldi,chromium,firefox}]
                            Import Letterboxd cookies from a local browser profile. Defaults to auto when no browser is
                            named.
  --browser-profile BROWSER_PROFILE
                            Restrict --browser import to a profile name such as Default or Profile 1.
```

## `lbd whoami`

```text
usage: lbd whoami [-h] [--format {table,json}]

options:
  -h, --help             show this help message and exit
  --format {table,json}
```

## `lbd query`

```text
usage: lbd query [-h] [--source {local,live,both}] [--live] [--both] [--local]
                 [--kind {diary,feed,film,history,like,likes,rating,ratings,review,reviews,watched,watchlist}]
                 [--year YEAR] [--min-rating MIN_RATING] [--max-rating MAX_RATING] [--pages PAGES] [--limit LIMIT]
                 [--hydrate] [--save] [--format {table,json,csv}] [--decade DECADE] [--genre GENRE]
                 [--exclude-genre EXCLUDE_GENRE] [--filter FILTER]
                 [--sort {longest,name,popular,rating,rating-lowest,release,release-earliest,shortest,your-rating,your-rating-lowest}]
                 [query]

positional arguments:
  query                     Search text.

options:
  -h, --help                show this help message and exit
  --source {local,live,both}
                            Data source to query. Defaults to live; use --local for cached rows.
  --live                    Shortcut for --source live.
  --both                    Shortcut for --source both.
  --local                   Shortcut for --source local/cache.
  --kind {diary,feed,film,history,like,likes,rating,ratings,review,reviews,watched,watchlist}
                            Restrict local rows by kind.
  --year YEAR               Filter by release year.
  --min-rating MIN_RATING   Minimum local rating.
  --max-rating MAX_RATING   Maximum local rating.
  --pages PAGES             Maximum live result pages.
  --limit LIMIT             Maximum rows to display/save.
  --hydrate                 Fetch live film JSON for richer rows.
  --save                    Save live rows into the local query database.
  --format {table,json,csv}
  --decade DECADE           Filter by decade, for example 1990s or 1990.
  --genre GENRE             Include genre slug/name. Repeat or comma-separate, for example --genre crime --genre
                            thriller.
  --exclude-genre EXCLUDE_GENRE
                            Exclude genre slug/name. Repeat or comma-separate, for example --exclude-genre documentary.
  --filter FILTER           Raw Letterboxd filter path segment, for example country/usa, language/english, or
                            on/netflix-us.
  --sort {longest,name,popular,rating,rating-lowest,release,release-earliest,shortest,your-rating,your-rating-lowest}
                            Letterboxd sort for filtered live film sets.
```

## `lbd q`

```text
usage: lbd q [-h] [--source {local,live,both}] [--live] [--both] [--local]
             [--kind {diary,feed,film,history,like,likes,rating,ratings,review,reviews,watched,watchlist}] [--year YEAR]
             [--min-rating MIN_RATING] [--max-rating MAX_RATING] [--pages PAGES] [--limit LIMIT] [--hydrate] [--save]
             [--format {table,json,csv}] [--decade DECADE] [--genre GENRE] [--exclude-genre EXCLUDE_GENRE]
             [--filter FILTER]
             [--sort {longest,name,popular,rating,rating-lowest,release,release-earliest,shortest,your-rating,your-rating-lowest}]
             [query]

positional arguments:
  query                     Search text.

options:
  -h, --help                show this help message and exit
  --source {local,live,both}
                            Data source to query. Defaults to live; use --local for cached rows.
  --live                    Shortcut for --source live.
  --both                    Shortcut for --source both.
  --local                   Shortcut for --source local/cache.
  --kind {diary,feed,film,history,like,likes,rating,ratings,review,reviews,watched,watchlist}
                            Restrict local rows by kind.
  --year YEAR               Filter by release year.
  --min-rating MIN_RATING   Minimum local rating.
  --max-rating MAX_RATING   Maximum local rating.
  --pages PAGES             Maximum live result pages.
  --limit LIMIT             Maximum rows to display/save.
  --hydrate                 Fetch live film JSON for richer rows.
  --save                    Save live rows into the local query database.
  --format {table,json,csv}
  --decade DECADE           Filter by decade, for example 1990s or 1990.
  --genre GENRE             Include genre slug/name. Repeat or comma-separate, for example --genre crime --genre
                            thriller.
  --exclude-genre EXCLUDE_GENRE
                            Exclude genre slug/name. Repeat or comma-separate, for example --exclude-genre documentary.
  --filter FILTER           Raw Letterboxd filter path segment, for example country/usa, language/english, or
                            on/netflix-us.
  --sort {longest,name,popular,rating,rating-lowest,release,release-earliest,shortest,your-rating,your-rating-lowest}
                            Letterboxd sort for filtered live film sets.
```

## `lbd search`

```text
usage: lbd search [-h] [--query QUERY] [--year YEAR] [--from-date FROM_DATE] [--to-date TO_DATE]
                  [--min-rating MIN_RATING] [--max-rating MAX_RATING] [--sort {date,rating,title,year,kind}] [--desc]
                  [--limit LIMIT] [--format {table,json,csv}]
                  query

positional arguments:
  query                     Text to search.

options:
  -h, --help                show this help message and exit
  --query, -q QUERY         Text filter.
  --year YEAR               Filter by release year.
  --from-date FROM_DATE     Filter dates on or after YYYY-MM-DD.
  --to-date TO_DATE         Filter dates on or before YYYY-MM-DD.
  --min-rating MIN_RATING   Minimum rating.
  --max-rating MAX_RATING   Maximum rating.
  --sort {date,rating,title,year,kind}
                            Sort column.
  --desc                    Sort descending.
  --limit LIMIT             Maximum rows.
  --format {table,json,csv}
```

## `lbd watchlist`

```text
usage: lbd watchlist [-h] [--query QUERY] [--year YEAR] [--from-date FROM_DATE] [--to-date TO_DATE]
                     [--min-rating MIN_RATING] [--max-rating MAX_RATING] [--sort {date,rating,title,year,kind}] [--desc]
                     [--limit LIMIT] [--format {table,json,csv}]

options:
  -h, --help                show this help message and exit
  --query, -q QUERY         Text filter.
  --year YEAR               Filter by release year.
  --from-date FROM_DATE     Filter dates on or after YYYY-MM-DD.
  --to-date TO_DATE         Filter dates on or before YYYY-MM-DD.
  --min-rating MIN_RATING   Minimum rating.
  --max-rating MAX_RATING   Maximum rating.
  --sort {date,rating,title,year,kind}
                            Sort column.
  --desc                    Sort descending.
  --limit LIMIT             Maximum rows.
  --format {table,json,csv}
```

## `lbd history`

```text
usage: lbd history [-h] [--query QUERY] [--year YEAR] [--from-date FROM_DATE] [--to-date TO_DATE]
                   [--min-rating MIN_RATING] [--max-rating MAX_RATING] [--sort {date,rating,title,year,kind}] [--desc]
                   [--limit LIMIT] [--format {table,json,csv}]

options:
  -h, --help                show this help message and exit
  --query, -q QUERY         Text filter.
  --year YEAR               Filter by release year.
  --from-date FROM_DATE     Filter dates on or after YYYY-MM-DD.
  --to-date TO_DATE         Filter dates on or before YYYY-MM-DD.
  --min-rating MIN_RATING   Minimum rating.
  --max-rating MAX_RATING   Maximum rating.
  --sort {date,rating,title,year,kind}
                            Sort column.
  --desc                    Sort descending.
  --limit LIMIT             Maximum rows.
  --format {table,json,csv}
```

## `lbd ratings`

```text
usage: lbd ratings [-h] [--query QUERY] [--year YEAR] [--from-date FROM_DATE] [--to-date TO_DATE]
                   [--min-rating MIN_RATING] [--max-rating MAX_RATING] [--sort {date,rating,title,year,kind}] [--desc]
                   [--limit LIMIT] [--format {table,json,csv}]

options:
  -h, --help                show this help message and exit
  --query, -q QUERY         Text filter.
  --year YEAR               Filter by release year.
  --from-date FROM_DATE     Filter dates on or after YYYY-MM-DD.
  --to-date TO_DATE         Filter dates on or before YYYY-MM-DD.
  --min-rating MIN_RATING   Minimum rating.
  --max-rating MAX_RATING   Maximum rating.
  --sort {date,rating,title,year,kind}
                            Sort column.
  --desc                    Sort descending.
  --limit LIMIT             Maximum rows.
  --format {table,json,csv}
```

## `lbd reviews`

```text
usage: lbd reviews [-h] [--query QUERY] [--year YEAR] [--from-date FROM_DATE] [--to-date TO_DATE]
                   [--min-rating MIN_RATING] [--max-rating MAX_RATING] [--sort {date,rating,title,year,kind}] [--desc]
                   [--limit LIMIT] [--format {table,json,csv}]

options:
  -h, --help                show this help message and exit
  --query, -q QUERY         Text filter.
  --year YEAR               Filter by release year.
  --from-date FROM_DATE     Filter dates on or after YYYY-MM-DD.
  --to-date TO_DATE         Filter dates on or before YYYY-MM-DD.
  --min-rating MIN_RATING   Minimum rating.
  --max-rating MAX_RATING   Maximum rating.
  --sort {date,rating,title,year,kind}
                            Sort column.
  --desc                    Sort descending.
  --limit LIMIT             Maximum rows.
  --format {table,json,csv}
```

## `lbd movie`

```text
usage: lbd movie [-h] [--query QUERY] [--year YEAR] [--from-date FROM_DATE] [--to-date TO_DATE]
                 [--min-rating MIN_RATING] [--max-rating MAX_RATING] [--sort {date,rating,title,year,kind}] [--desc]
                 [--limit LIMIT] [--format {table,json,csv}]
                 query

positional arguments:
  query                     Film title search.

options:
  -h, --help                show this help message and exit
  --query, -q QUERY         Text filter.
  --year YEAR               Filter by release year.
  --from-date FROM_DATE     Filter dates on or after YYYY-MM-DD.
  --to-date TO_DATE         Filter dates on or before YYYY-MM-DD.
  --min-rating MIN_RATING   Minimum rating.
  --max-rating MAX_RATING   Maximum rating.
  --sort {date,rating,title,year,kind}
                            Sort column.
  --desc                    Sort descending.
  --limit LIMIT             Maximum rows.
  --format {table,json,csv}
```

## `lbd film`

```text
usage: lbd film [-h] [--cast-limit CAST_LIMIT] [--format {table,json}] film

positional arguments:
  film                     Film title, slug, /film/... path, or full Letterboxd film URL.

options:
  -h, --help               show this help message and exit
  --cast-limit CAST_LIMIT  Maximum cast members to include.
  --format {table,json}
```

## `lbd watch`

```text
usage: lbd watch [-h] [--format {table,json,csv}] film

positional arguments:
  film                      Film title, slug, /film/... path, or full Letterboxd film URL.

options:
  -h, --help                show this help message and exit
  --format {table,json,csv}
```

## `lbd cast`

```text
usage: lbd cast [-h] [--limit LIMIT] [--format {table,json,csv}] film

positional arguments:
  film                      Film title, slug, /film/... path, or full Letterboxd film URL.

options:
  -h, --help                show this help message and exit
  --limit LIMIT             Maximum cast members to display.
  --format {table,json,csv}
```

## `lbd people`

```text
usage: lbd people [-h] [--limit LIMIT] [--format {table,json,csv}] query

positional arguments:
  query                     Person search text.

options:
  -h, --help                show this help message and exit
  --limit LIMIT             Maximum people to display.
  --format {table,json,csv}
```

## `lbd lists`

```text
usage: lbd lists [-h] [--user USER] [--pages PAGES] [--limit LIMIT] [--min-quality MIN_QUALITY] [--min-films MIN_FILMS]
                 [--min-likes MIN_LIKES] [--max-films MAX_FILMS] [--require-notes] [--strict] [--include-junk]
                 [--prefer-following | --no-prefer-following] [--only-following] [--following-pages FOLLOWING_PAGES]
                 [--sort {quality,likes,films,comments,relevance}] [--format {table,json,csv}]
                 query

positional arguments:
  query                     List search text.

options:
  -h, --help                show this help message and exit
  --user USER               Restrict results to a Letterboxd username/display name when possible.
  --pages PAGES             Maximum search pages to fetch.
  --limit LIMIT             Maximum lists to display.
  --min-quality MIN_QUALITY
                            Minimum list quality score. Defaults to 12.
  --min-films MIN_FILMS     Minimum number of films in the list. Defaults to 5.
  --min-likes MIN_LIKES     Minimum likes. Defaults to 1 to suppress zero-signal copies.
  --max-films MAX_FILMS     Maximum number of films in the list.
  --require-notes           Only show lists with notes/description text.
  --strict                  Use stronger quality thresholds: min quality 30, min films 10, min likes 10.
  --include-junk            Disable default quality filtering; still computes quality_score.
  --prefer-following, --no-prefer-following
                            Boost and top-rank lists by people you follow when signed in. Defaults to on.
  --only-following          Only show lists by people you follow.
  --following-pages FOLLOWING_PAGES
                            Following pages to scan for owner boosts. Defaults to 5.
  --sort {quality,likes,films,comments,relevance}
                            Sort list results. Defaults to quality.
  --format {table,json,csv}
```

## `lbd person`

```text
usage: lbd person [-h] [--role {actor,director,writer,producer,composer,cinematography,editor}] [--pages PAGES]
                  [--limit LIMIT] [--hydrate] [--save] [--format {table,json,csv}] [--year YEAR] [--decade DECADE]
                  [--genre GENRE] [--exclude-genre EXCLUDE_GENRE] [--filter FILTER]
                  [--sort {longest,name,popular,rating,rating-lowest,release,release-earliest,shortest,your-rating,your-rating-lowest}]
                  person

positional arguments:
  person                    Person name, /actor/... path, /director/... path, or full Letterboxd URL.

options:
  -h, --help                show this help message and exit
  --role {actor,director,writer,producer,composer,cinematography,editor}
                            Contributor role path to use when the input is a plain name.
  --pages PAGES             Maximum filmography pages to fetch.
  --limit LIMIT             Maximum films to display.
  --hydrate                 Fetch film JSON/account state for each result.
  --save                    Save fetched film rows into the local query database.
  --format {table,json,csv}
  --year YEAR               Filter by release year, for example 1995.
  --decade DECADE           Filter by decade, for example 1990s or 1990.
  --genre GENRE             Include genre slug/name. Repeat or comma-separate, for example --genre crime --genre
                            thriller.
  --exclude-genre EXCLUDE_GENRE
                            Exclude genre slug/name. Repeat or comma-separate, for example --exclude-genre documentary.
  --filter FILTER           Raw Letterboxd filter path segment, for example country/usa, language/english, or
                            on/netflix-us.
  --sort {longest,name,popular,rating,rating-lowest,release,release-earliest,shortest,your-rating,your-rating-lowest}
                            Letterboxd sort for filtered live film sets.
```

## `lbd films`

```text
usage: lbd films [-h] [--query QUERY] [--pages PAGES] [--limit LIMIT] [--hydrate] [--save] [--format {table,json,csv}]
                 [--year YEAR] [--decade DECADE] [--genre GENRE] [--exclude-genre EXCLUDE_GENRE] [--filter FILTER]
                 [--sort {longest,name,popular,rating,rating-lowest,release,release-earliest,shortest,your-rating,your-rating-lowest}]
                 [base]

positional arguments:
  base                      Film-set path or URL. Defaults to /films/. Examples: /films/, /example-user/watchlist/,
                            /director/michael-mann/.

options:
  -h, --help                show this help message and exit
  --query, -q QUERY         Client-side title filter after Letterboxd metadata filters.
  --pages PAGES             Maximum pages to fetch.
  --limit LIMIT             Maximum films to display.
  --hydrate                 Fetch film JSON/account state for each result.
  --save                    Save fetched film rows into the local query database.
  --format {table,json,csv}
  --year YEAR               Filter by release year, for example 1995.
  --decade DECADE           Filter by decade, for example 1990s or 1990.
  --genre GENRE             Include genre slug/name. Repeat or comma-separate, for example --genre crime --genre
                            thriller.
  --exclude-genre EXCLUDE_GENRE
                            Exclude genre slug/name. Repeat or comma-separate, for example --exclude-genre documentary.
  --filter FILTER           Raw Letterboxd filter path segment, for example country/usa, language/english, or
                            on/netflix-us.
  --sort {longest,name,popular,rating,rating-lowest,release,release-earliest,shortest,your-rating,your-rating-lowest}
                            Letterboxd sort for filtered live film sets.
```

## `lbd recs`

```text
usage: lbd recs [-h] [--username USERNAME] [--query QUERY] [--pages PAGES] [--pool-size POOL_SIZE] [--limit LIMIT]
                [--include-watched] [--watched-pages WATCHED_PAGES] [--bias-person BIAS_PERSON]
                [--taste-from-ratings | --no-taste-from-ratings] [--taste-films TASTE_FILMS] [--taste-pages TASTE_PAGES]
                [--cast-limit CAST_LIMIT] [--detail-limit DETAIL_LIMIT] [--request-delay REQUEST_DELAY]
                [--format {table,json,csv}] [--year YEAR] [--decade DECADE] [--genre GENRE]
                [--exclude-genre EXCLUDE_GENRE] [--filter FILTER]
                [--sort {longest,name,popular,rating,rating-lowest,release,release-earliest,shortest,your-rating,your-rating-lowest}]
                [base]

positional arguments:
  base                      Film-set path or URL to recommend from. Defaults to /films/.

options:
  -h, --help                show this help message and exit
  --username USERNAME       Letterboxd username for watched exclusion and taste signals.
  --query, -q QUERY         Client-side title filter after Letterboxd metadata filters.
  --pages PAGES             Candidate pages to fetch.
  --pool-size POOL_SIZE     Maximum candidate films to score before trimming.
  --limit LIMIT             Recommendations to display.
  --include-watched         Do not exclude films already watched by the user.
  --watched-pages WATCHED_PAGES
                            Watched pages to scan for exclusion.
  --bias-person BIAS_PERSON
                            Person to boost when they appear as director or cast. Repeatable.
  --taste-from-ratings, --no-taste-from-ratings
                            Derive additional director/cast boosts from the user's highest-rated films.
  --taste-films TASTE_FILMS
                            Highest-rated films to inspect for taste signals.
  --taste-pages TASTE_PAGES
                            Rating pages to scan for taste signals.
  --cast-limit CAST_LIMIT   Cast members to inspect per film.
  --detail-limit DETAIL_LIMIT
                            Maximum candidate film detail pages to fetch while scoring.
  --request-delay REQUEST_DELAY
                            Seconds to wait between recommendation detail requests.
  --format {table,json,csv}
  --year YEAR               Filter by release year, for example 1995.
  --decade DECADE           Filter by decade, for example 1990s or 1990.
  --genre GENRE             Include genre slug/name. Repeat or comma-separate, for example --genre crime --genre
                            thriller.
  --exclude-genre EXCLUDE_GENRE
                            Exclude genre slug/name. Repeat or comma-separate, for example --exclude-genre documentary.
  --filter FILTER           Raw Letterboxd filter path segment, for example country/usa, language/english, or
                            on/netflix-us.
  --sort {longest,name,popular,rating,rating-lowest,release,release-earliest,shortest,your-rating,your-rating-lowest}
                            Letterboxd sort for filtered live film sets.
```

## `lbd log`

```text
usage: lbd log [-h] [--date DATE] [--rating RATING] [--review REVIEW] [--tags TAGS] [--rewatch] [--like] [--spoilers]
               [--privacy {Anyone,Friends,You,Draft}] [--dry-run]
               film

positional arguments:
  film                      Film slug, title, /film/... path, or full Letterboxd film URL.

options:
  -h, --help                show this help message and exit
  --date DATE               Watched date as YYYY-MM-DD. For diary, defaults to today.
  --rating RATING           Rating from 0.5 to 5.0.
  --review REVIEW           Review text.
  --tags TAGS               Comma-separated tags.
  --rewatch                 Mark the entry as a rewatch.
  --like, --heart           Heart/like the film.
  --spoilers                Mark the review as containing spoilers.
  --privacy {Anyone,Friends,You,Draft}
                            Entry privacy.
  --dry-run                 Print the request that would be made.
```

## `lbd watched`

```text
usage: lbd watched [-h] [--date DATE] [--rating RATING] [--review REVIEW] [--tags TAGS] [--rewatch] [--like]
                   [--spoilers] [--privacy {Anyone,Friends,You,Draft}] [--dry-run]
                   film

positional arguments:
  film                      Film slug, title, /film/... path, or full Letterboxd film URL.

options:
  -h, --help                show this help message and exit
  --date DATE               Watched date as YYYY-MM-DD. For diary, defaults to today.
  --rating RATING           Rating from 0.5 to 5.0.
  --review REVIEW           Review text.
  --tags TAGS               Comma-separated tags.
  --rewatch                 Mark the entry as a rewatch.
  --like, --heart           Heart/like the film.
  --spoilers                Mark the review as containing spoilers.
  --privacy {Anyone,Friends,You,Draft}
                            Entry privacy.
  --dry-run                 Print the request that would be made.
```

## `lbd diary`

```text
usage: lbd diary [-h] [--date DATE] [--rating RATING] [--review REVIEW] [--tags TAGS] [--rewatch] [--like] [--spoilers]
                 [--privacy {Anyone,Friends,You,Draft}] [--dry-run]
                 film

positional arguments:
  film                      Film slug, title, /film/... path, or full Letterboxd film URL.

options:
  -h, --help                show this help message and exit
  --date DATE               Watched date as YYYY-MM-DD. For diary, defaults to today.
  --rating RATING           Rating from 0.5 to 5.0.
  --review REVIEW           Review text.
  --tags TAGS               Comma-separated tags.
  --rewatch                 Mark the entry as a rewatch.
  --like, --heart           Heart/like the film.
  --spoilers                Mark the review as containing spoilers.
  --privacy {Anyone,Friends,You,Draft}
                            Entry privacy.
  --dry-run                 Print the request that would be made.
```

## `lbd rate`

```text
usage: lbd rate [-h] [--date DATE] [--review REVIEW] [--tags TAGS] [--rewatch] [--like] [--spoilers]
                [--privacy {Anyone,Friends,You,Draft}] [--dry-run]
                film rating_value

positional arguments:
  film                      Film slug, title, /film/... path, or full Letterboxd film URL.
  rating_value              Rating from 0.5 to 5.0.

options:
  -h, --help                show this help message and exit
  --date DATE               Watched date as YYYY-MM-DD. For diary, defaults to today.
  --review REVIEW           Review text.
  --tags TAGS               Comma-separated tags.
  --rewatch                 Mark the entry as a rewatch.
  --like, --heart           Heart/like the film.
  --spoilers                Mark the review as containing spoilers.
  --privacy {Anyone,Friends,You,Draft}
                            Entry privacy.
  --dry-run                 Print the request that would be made.
```

## `lbd review`

```text
usage: lbd review [-h] [--date DATE] [--rating RATING] [--tags TAGS] [--rewatch] [--like] [--spoilers]
                  [--privacy {Anyone,Friends,You,Draft}] [--dry-run]
                  film review_text

positional arguments:
  film                      Film slug, title, /film/... path, or full Letterboxd film URL.
  review_text               Review text.

options:
  -h, --help                show this help message and exit
  --date DATE               Watched date as YYYY-MM-DD. For diary, defaults to today.
  --rating RATING           Rating from 0.5 to 5.0.
  --tags TAGS               Comma-separated tags.
  --rewatch                 Mark the entry as a rewatch.
  --like, --heart           Heart/like the film.
  --spoilers                Mark the review as containing spoilers.
  --privacy {Anyone,Friends,You,Draft}
                            Entry privacy.
  --dry-run                 Print the request that would be made.
```

## `lbd heart`

```text
usage: lbd heart [-h] [--date DATE] [--rating RATING] [--review REVIEW] [--tags TAGS] [--rewatch] [--spoilers]
                 [--privacy {Anyone,Friends,You,Draft}] [--dry-run]
                 film

positional arguments:
  film                      Film slug, title, /film/... path, or full Letterboxd film URL.

options:
  -h, --help                show this help message and exit
  --date DATE               Watched date as YYYY-MM-DD. For diary, defaults to today.
  --rating RATING           Rating from 0.5 to 5.0.
  --review REVIEW           Review text.
  --tags TAGS               Comma-separated tags.
  --rewatch                 Mark the entry as a rewatch.
  --spoilers                Mark the review as containing spoilers.
  --privacy {Anyone,Friends,You,Draft}
                            Entry privacy.
  --dry-run                 Print the request that would be made.
```

## `lbd like`

```text
usage: lbd like [-h] [--date DATE] [--rating RATING] [--review REVIEW] [--tags TAGS] [--rewatch] [--spoilers]
                [--privacy {Anyone,Friends,You,Draft}] [--dry-run]
                film

positional arguments:
  film                      Film slug, title, /film/... path, or full Letterboxd film URL.

options:
  -h, --help                show this help message and exit
  --date DATE               Watched date as YYYY-MM-DD. For diary, defaults to today.
  --rating RATING           Rating from 0.5 to 5.0.
  --review REVIEW           Review text.
  --tags TAGS               Comma-separated tags.
  --rewatch                 Mark the entry as a rewatch.
  --spoilers                Mark the review as containing spoilers.
  --privacy {Anyone,Friends,You,Draft}
                            Entry privacy.
  --dry-run                 Print the request that would be made.
```

## `lbd stats`

```text
usage: lbd stats [-h]

options:
  -h, --help  show this help message and exit
```

## `lbd export`

```text
usage: lbd export [-h] [--query QUERY] [--year YEAR] [--from-date FROM_DATE] [--to-date TO_DATE]
                  [--min-rating MIN_RATING] [--max-rating MAX_RATING] [--sort {date,rating,title,year,kind}] [--desc]
                  [--limit LIMIT] [--format {table,json,csv}]
                  [--kind {diary,feed,history,like,likes,rating,ratings,review,reviews,watched,watchlist}]

options:
  -h, --help                show this help message and exit
  --query, -q QUERY         Text filter.
  --year YEAR               Filter by release year.
  --from-date FROM_DATE     Filter dates on or after YYYY-MM-DD.
  --to-date TO_DATE         Filter dates on or before YYYY-MM-DD.
  --min-rating MIN_RATING   Minimum rating.
  --max-rating MAX_RATING   Maximum rating.
  --sort {date,rating,title,year,kind}
                            Sort column.
  --desc                    Sort descending.
  --limit LIMIT             Maximum rows.
  --format {table,json,csv}
  --kind {diary,feed,history,like,likes,rating,ratings,review,reviews,watched,watchlist}
                            Restrict exported rows.
```

## `lbd sql`

```text
usage: lbd sql [-h] [--format {table,json,csv}] query

positional arguments:
  query                     SELECT query to run.

options:
  -h, --help                show this help message and exit
  --format {table,json,csv}
```

## `lbd auth`

```text
usage: lbd auth [-h] {save,status,clear} ...

positional arguments:
  {save,status,clear}
    save               Save a Letterboxd Cookie header for web commands.
    status             Check whether the saved web session appears signed in.
    clear              Delete the saved web session.

options:
  -h, --help           show this help message and exit
```

## `lbd auth save`

```text
usage: lbd auth save [-h] --cookie COOKIE

options:
  -h, --help       show this help message and exit
  --cookie COOKIE  Raw Cookie header copied from your signed-in browser.
```

## `lbd auth status`

```text
usage: lbd auth status [-h] [--format {table,json}]

options:
  -h, --help             show this help message and exit
  --format {table,json}
```

## `lbd auth clear`

```text
usage: lbd auth clear [-h]

options:
  -h, --help  show this help message and exit
```

## `lbd web`

```text
usage: lbd web [-h] {get,post,film,watchlist,log} ...

positional arguments:
  {get,post,film,watchlist,log}
    get                     GET a Letterboxd path or URL.
    post                    POST form data to a Letterboxd path or URL.
    film                    Fetch Letterboxd's JSON metadata for a film slug or URL.
    watchlist               Add/remove a film from your watchlist.
    log                     Create or update a diary/review/rating entry.

options:
  -h, --help                show this help message and exit
```

## `lbd web get`

```text
usage: lbd web get [-h] [--format {auto,raw,json}] path

positional arguments:
  path                      Path or URL, for example /film/heat-1995/json/.

options:
  -h, --help                show this help message and exit
  --format {auto,raw,json}
```

## `lbd web post`

```text
usage: lbd web post [-h] [--data DATA] [--json-body JSON_BODY] [--csrf-from CSRF_FROM] [--dry-run]
                    [--format {auto,raw,json}]
                    path

positional arguments:
  path                      Path or URL.

options:
  -h, --help                show this help message and exit
  --data DATA               Form field as key=value. Can be repeated.
  --json-body JSON_BODY     JSON request body instead of form data.
  --csrf-from CSRF_FROM     Fetch this page/path first and include its CSRF token.
  --dry-run                 Print the request that would be made.
  --format {auto,raw,json}
```

## `lbd web film`

```text
usage: lbd web film [-h] [--format {json,table}] film

positional arguments:
  film                   Film slug, /film/... URL path, or full Letterboxd film URL.

options:
  -h, --help             show this help message and exit
  --format {json,table}
```

## `lbd web watchlist`

```text
usage: lbd web watchlist [-h] [--dry-run] {add,remove} film

positional arguments:
  {add,remove}
  film          Film slug, /film/... URL path, or full Letterboxd film URL.

options:
  -h, --help    show this help message and exit
  --dry-run     Print the request that would be made.
```

## `lbd web log`

```text
usage: lbd web log [-h] [--date DATE] [--rating RATING] [--review REVIEW] [--tags TAGS] [--rewatch] [--like]
                   [--spoilers] [--privacy {Anyone,Friends,You,Draft}] [--dry-run]
                   film

positional arguments:
  film                      Film slug, /film/... URL path, or full Letterboxd film URL.

options:
  -h, --help                show this help message and exit
  --date DATE               Watched date as YYYY-MM-DD. Omit to save rating/review without diary date.
  --rating RATING           Rating from 0.5 to 5.0.
  --review REVIEW           Review text.
  --tags TAGS               Comma-separated tags.
  --rewatch                 Mark the diary entry as a rewatch.
  --like                    Like the film.
  --spoilers                Mark the review as containing spoilers.
  --privacy {Anyone,Friends,You,Draft}
                            Entry privacy.
  --dry-run                 Print the request that would be made.
```

## `lbd live`

```text
usage: lbd live [-h] {me,whoami,search,watchlist,watched,diary,reviews,ratings,sync} ...

positional arguments:
  {me,whoami,search,watchlist,watched,diary,reviews,ratings,sync}
    me                      Show the signed-in username detected from Letterboxd.
    whoami                  Show the signed-in username detected from Letterboxd.
    search                  Search Letterboxd live, display results, and optionally save them.
    watchlist               Fetch a user's live watchlist.
    watched                 Fetch a user's live watched films.
    diary                   Fetch a user's live diary.
    reviews                 Fetch a user's live reviews.
    ratings                 Fetch a user's live rated films.
    sync                    Fetch multiple live account sections and save them locally.

options:
  -h, --help                show this help message and exit
```

## `lbd live me`

```text
usage: lbd live me [-h] [--format {table,json}]

options:
  -h, --help             show this help message and exit
  --format {table,json}
```

## `lbd live whoami`

```text
usage: lbd live whoami [-h] [--format {table,json}]

options:
  -h, --help             show this help message and exit
  --format {table,json}
```

## `lbd live search`

```text
usage: lbd live search [-h] [--type {films}] [--pages PAGES] [--limit LIMIT] [--hydrate] [--save]
                       [--format {table,json,csv}] [--year YEAR] [--decade DECADE] [--genre GENRE]
                       [--exclude-genre EXCLUDE_GENRE] [--filter FILTER]
                       [--sort {longest,name,popular,rating,rating-lowest,release,release-earliest,shortest,your-rating,your-rating-lowest}]
                       query

positional arguments:
  query                     Search text.

options:
  -h, --help                show this help message and exit
  --type {films}            Search surface to query. Only film search is currently supported.
  --pages PAGES             Maximum result pages to fetch.
  --limit LIMIT             Maximum rows to display/save.
  --hydrate                 Fetch each film JSON result for richer metadata.
  --save                    Save fetched rows into the local query database.
  --format {table,json,csv}
  --year YEAR               Filter by release year, for example 1995.
  --decade DECADE           Filter by decade, for example 1990s or 1990.
  --genre GENRE             Include genre slug/name. Repeat or comma-separate, for example --genre crime --genre
                            thriller.
  --exclude-genre EXCLUDE_GENRE
                            Exclude genre slug/name. Repeat or comma-separate, for example --exclude-genre documentary.
  --filter FILTER           Raw Letterboxd filter path segment, for example country/usa, language/english, or
                            on/netflix-us.
  --sort {longest,name,popular,rating,rating-lowest,release,release-earliest,shortest,your-rating,your-rating-lowest}
                            Letterboxd sort for filtered live film sets.
```

## `lbd live watchlist`

```text
usage: lbd live watchlist [-h] [--pages PAGES] [--limit LIMIT] [--save] [--format {table,json,csv}] [--year YEAR]
                          [--decade DECADE] [--genre GENRE] [--exclude-genre EXCLUDE_GENRE] [--filter FILTER]
                          [username]

positional arguments:
  username                  Letterboxd username. Defaults to signed-in user when detectable.

options:
  -h, --help                show this help message and exit
  --pages PAGES             Maximum pages to fetch.
  --limit LIMIT             Maximum rows to display/save.
  --save                    Save fetched rows into the local query database.
  --format {table,json,csv}
  --year YEAR               Filter by release year, for example 1995.
  --decade DECADE           Filter by decade, for example 1990s or 1990.
  --genre GENRE             Include genre slug/name. Repeat or comma-separate, for example --genre crime --genre
                            thriller.
  --exclude-genre EXCLUDE_GENRE
                            Exclude genre slug/name. Repeat or comma-separate, for example --exclude-genre documentary.
  --filter FILTER           Raw Letterboxd filter path segment, for example country/usa, language/english, or
                            on/netflix-us.
```

## `lbd live watched`

```text
usage: lbd live watched [-h] [--pages PAGES] [--limit LIMIT] [--save] [--format {table,json,csv}] [--year YEAR]
                        [--decade DECADE] [--genre GENRE] [--exclude-genre EXCLUDE_GENRE] [--filter FILTER]
                        [username]

positional arguments:
  username                  Letterboxd username. Defaults to signed-in user when detectable.

options:
  -h, --help                show this help message and exit
  --pages PAGES             Maximum pages to fetch.
  --limit LIMIT             Maximum rows to display/save.
  --save                    Save fetched rows into the local query database.
  --format {table,json,csv}
  --year YEAR               Filter by release year, for example 1995.
  --decade DECADE           Filter by decade, for example 1990s or 1990.
  --genre GENRE             Include genre slug/name. Repeat or comma-separate, for example --genre crime --genre
                            thriller.
  --exclude-genre EXCLUDE_GENRE
                            Exclude genre slug/name. Repeat or comma-separate, for example --exclude-genre documentary.
  --filter FILTER           Raw Letterboxd filter path segment, for example country/usa, language/english, or
                            on/netflix-us.
```

## `lbd live diary`

```text
usage: lbd live diary [-h] [--pages PAGES] [--limit LIMIT] [--save] [--format {table,json,csv}] [--year YEAR]
                      [--decade DECADE] [--genre GENRE] [--exclude-genre EXCLUDE_GENRE] [--filter FILTER]
                      [username]

positional arguments:
  username                  Letterboxd username. Defaults to signed-in user when detectable.

options:
  -h, --help                show this help message and exit
  --pages PAGES             Maximum pages to fetch.
  --limit LIMIT             Maximum rows to display/save.
  --save                    Save fetched rows into the local query database.
  --format {table,json,csv}
  --year YEAR               Filter by release year, for example 1995.
  --decade DECADE           Filter by decade, for example 1990s or 1990.
  --genre GENRE             Include genre slug/name. Repeat or comma-separate, for example --genre crime --genre
                            thriller.
  --exclude-genre EXCLUDE_GENRE
                            Exclude genre slug/name. Repeat or comma-separate, for example --exclude-genre documentary.
  --filter FILTER           Raw Letterboxd filter path segment, for example country/usa, language/english, or
                            on/netflix-us.
```

## `lbd live reviews`

```text
usage: lbd live reviews [-h] [--pages PAGES] [--limit LIMIT] [--save] [--format {table,json,csv}] [--year YEAR]
                        [--decade DECADE] [--genre GENRE] [--exclude-genre EXCLUDE_GENRE] [--filter FILTER]
                        [username]

positional arguments:
  username                  Letterboxd username. Defaults to signed-in user when detectable.

options:
  -h, --help                show this help message and exit
  --pages PAGES             Maximum pages to fetch.
  --limit LIMIT             Maximum rows to display/save.
  --save                    Save fetched rows into the local query database.
  --format {table,json,csv}
  --year YEAR               Filter by release year, for example 1995.
  --decade DECADE           Filter by decade, for example 1990s or 1990.
  --genre GENRE             Include genre slug/name. Repeat or comma-separate, for example --genre crime --genre
                            thriller.
  --exclude-genre EXCLUDE_GENRE
                            Exclude genre slug/name. Repeat or comma-separate, for example --exclude-genre documentary.
  --filter FILTER           Raw Letterboxd filter path segment, for example country/usa, language/english, or
                            on/netflix-us.
```

## `lbd live ratings`

```text
usage: lbd live ratings [-h] [--pages PAGES] [--limit LIMIT] [--save] [--format {table,json,csv}] [--year YEAR]
                        [--decade DECADE] [--genre GENRE] [--exclude-genre EXCLUDE_GENRE] [--filter FILTER]
                        [username]

positional arguments:
  username                  Letterboxd username. Defaults to signed-in user when detectable.

options:
  -h, --help                show this help message and exit
  --pages PAGES             Maximum pages to fetch.
  --limit LIMIT             Maximum rows to display/save.
  --save                    Save fetched rows into the local query database.
  --format {table,json,csv}
  --year YEAR               Filter by release year, for example 1995.
  --decade DECADE           Filter by decade, for example 1990s or 1990.
  --genre GENRE             Include genre slug/name. Repeat or comma-separate, for example --genre crime --genre
                            thriller.
  --exclude-genre EXCLUDE_GENRE
                            Exclude genre slug/name. Repeat or comma-separate, for example --exclude-genre documentary.
  --filter FILTER           Raw Letterboxd filter path segment, for example country/usa, language/english, or
                            on/netflix-us.
```

## `lbd live sync`

```text
usage: lbd live sync [-h] [--pages PAGES] [--kinds KINDS] [username]

positional arguments:
  username       Letterboxd username. Defaults to signed-in user when detectable.

options:
  -h, --help     show this help message and exit
  --pages PAGES  Maximum pages per section.
  --kinds KINDS  Comma-separated sections: watchlist,watched,diary,reviews,ratings.
```
