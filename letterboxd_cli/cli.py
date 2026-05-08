from __future__ import annotations

import argparse
import csv
import html
import io
import json
import math
import os
import re
import sqlite3
import sys
import textwrap
import time
import urllib.parse
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from letterboxd_cli import __version__
from letterboxd_cli.auth import (
    cmd_auth_clear,
    cmd_auth_save,
    cmd_auth_status,
    cmd_login,
    detect_username,
    username_from_cookie,
)
from letterboxd_cli.browser_cookies import browser_choices
from letterboxd_cli.exports import normalize_csv_row, read_csv_sources
from letterboxd_cli.feeds import fetch_url, parse_rss
from letterboxd_cli.filters import (
    LETTERBOXD_SORTS,
    LetterboxdFilters,
    filtered_path,
    filters_from_args,
    filters_have_values,
    is_global_films_base,
    letterboxd_filter_segments,
    looks_like_letterboxd_film_set,
)
from letterboxd_cli.normalization import (
    build_search_text,
    key_for,
    normalize_date,
    now_iso,
    parse_int,
    parse_rating,
    parse_rating10,
    parse_rating_from_text,
    row_hash,
    today_iso,
)
from letterboxd_cli.output import ensure_provenance, public_display_row
from letterboxd_cli.storage import KIND_ALIASES, connect, ensure_schema, insert_entry, select_entries
from letterboxd_cli.web import (
    LETTERBOXD_BASE_URL,
    LetterboxdWebClient,
    LetterboxdWebError,
    WebResponse,
    parse_json_response,
    print_web_response,
    redact_sensitive_values,
)


DEFAULT_DB = Path("~/.letterboxd-cli/letterboxd.sqlite3")
DEFAULT_SESSION_FILE = Path("~/.letterboxd-cli/session.json")

def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not hasattr(args, "func"):
        parser.print_help()
        return 2

    try:
        db_path = Path(args.db).expanduser()
        apply_global_output_mode(args)
        if getattr(args, "no_db", False):
            return args.func(None, args)
        readonly_db = bool(getattr(args, "readonly_db", False))
        with connect(db_path, readonly=readonly_db) as db:
            if not readonly_db:
                ensure_schema(db)
            return args.func(db, args)
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except (OSError, sqlite3.Error, ValueError, zipfile.BadZipFile) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lbd",
        description=(
            "Search live Letterboxd, sync account sections, inspect a local SQLite cache, "
            "and run scriptable film workflows."
        ),
    )
    parser.add_argument(
        "--db",
        default=os.environ.get("LETTERBOXD_DB", str(DEFAULT_DB)),
        help=f"SQLite database path. Defaults to {DEFAULT_DB}",
    )
    parser.add_argument(
        "--session-file",
        default=os.environ.get("LETTERBOXD_SESSION_FILE", str(DEFAULT_SESSION_FILE)),
        help=f"Saved Letterboxd web session path. Defaults to {DEFAULT_SESSION_FILE}",
    )
    parser.add_argument(
        "--cookie",
        default=os.environ.get("LETTERBOXD_COOKIE"),
        help="Letterboxd Cookie header. Overrides saved session for this run.",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("LETTERBOXD_BASE_URL", LETTERBOXD_BASE_URL),
        help="Letterboxd web base URL.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=env_flag("LETTERBOXD_JSON"),
        help="Prefer JSON output for commands that support structured output.",
    )
    parser.add_argument(
        "--plain",
        action="store_true",
        default=env_flag("LETTERBOXD_PLAIN"),
        help="Prefer stable plain output for commands that support it.",
    )
    parser.add_argument(
        "--no-input",
        action="store_true",
        default=env_flag("LETTERBOXD_NO_INPUT"),
        help="Never read interactive input such as the clipboard or stdin.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    sub = parser.add_subparsers(dest="command")

    version = sub.add_parser("version", help="Print the lbd version.")
    version.add_argument("--format", choices=("table", "json"), default="table")
    version.set_defaults(func=cmd_version, no_db=True)

    load = sub.add_parser("load", help="Load a Letterboxd export ZIP, folder, or CSV.")
    load.add_argument("path", help="Path to a Letterboxd export ZIP, extracted folder, or CSV file.")
    load.add_argument("--append", action="store_true", help="Append rows instead of replacing export rows.")
    load.set_defaults(func=cmd_load)

    feed = sub.add_parser("feed", help="Fetch and store recent public RSS activity.")
    feed.add_argument("username", nargs="?", help="Letterboxd username.")
    feed.add_argument("--url", help="Custom RSS URL.")
    feed.add_argument("--limit", type=int, default=20, help="Rows to print after fetching.")
    feed.add_argument("--format", choices=("table", "json", "csv"), default="table")
    feed.set_defaults(func=cmd_feed)

    login = sub.add_parser("login", help="Save your signed-in Letterboxd browser cookie.")
    login.add_argument("--cookie", help="Raw Cookie header copied from your signed-in browser.")
    login.add_argument(
        "--clipboard",
        action="store_true",
        help="Read the cookie from the macOS clipboard. This is also tried automatically when --cookie is omitted.",
    )
    login.add_argument(
        "--no-verify",
        action="store_true",
        help="Save without checking that Letterboxd accepts the session.",
    )
    login.add_argument(
        "--browser",
        nargs="?",
        const="auto",
        choices=browser_choices(),
        help="Import Letterboxd cookies from a local browser profile. Defaults to auto when no browser is named.",
    )
    login.add_argument("--browser-profile", help="Restrict --browser import to a profile name such as Default or Profile 1.")
    login.set_defaults(func=cmd_login, no_db=True)

    whoami = sub.add_parser("whoami", help="Show the signed-in Letterboxd username detected from the saved session.")
    whoami.add_argument("--format", choices=("table", "json"), default="table")
    whoami.set_defaults(func=cmd_live_me, no_db=True)

    for command_name in ("query", "q"):
        query_cmd = sub.add_parser(
            command_name,
            help="Query local data and/or live Letterboxd, then display or save results.",
        )
        query_cmd.add_argument("query", nargs="?", default="", help="Search text.")
        query_cmd.add_argument(
            "--source",
            choices=("local", "live", "both"),
            default="live",
            help="Data source to query. Defaults to live; use --local for cached rows.",
        )
        query_cmd.add_argument("--live", action="store_true", help="Shortcut for --source live.")
        query_cmd.add_argument("--both", action="store_true", help="Shortcut for --source both.")
        query_cmd.add_argument("--local", action="store_true", help="Shortcut for --source local/cache.")
        query_cmd.add_argument(
            "--kind",
            choices=sorted(KIND_ALIASES | {"film": "film"}),
            help="Restrict local rows by kind.",
        )
        query_cmd.add_argument("--year", type=int, help="Filter by release year.")
        query_cmd.add_argument("--min-rating", type=float, help="Minimum local rating.")
        query_cmd.add_argument("--max-rating", type=float, help="Maximum local rating.")
        query_cmd.add_argument("--pages", type=int, default=1, help="Maximum live result pages.")
        query_cmd.add_argument("--limit", type=int, default=25, help="Maximum rows to display/save.")
        query_cmd.add_argument("--hydrate", action="store_true", help="Fetch live film JSON for richer rows.")
        query_cmd.add_argument("--save", action="store_true", help="Save live rows into the local query database.")
        query_cmd.add_argument("--format", choices=("table", "json", "csv"), default="table")
        add_letterboxd_filter_args(query_cmd)
        query_cmd.set_defaults(func=cmd_query)

    search = sub.add_parser("search", help="Search across all imported data.")
    add_query_args(search)
    search.add_argument("query", help="Text to search.")
    search.set_defaults(func=cmd_search)

    for name, help_text, kind in [
        ("watchlist", "Show watchlist rows.", "watchlist"),
        ("history", "Show diary and watched history rows.", "history"),
        ("ratings", "Show ratings.", "rating"),
        ("reviews", "Show reviews.", "review"),
    ]:
        p = sub.add_parser(name, help=help_text)
        add_query_args(p)
        p.set_defaults(func=cmd_list, fixed_kind=kind)

    movie = sub.add_parser("movie", help="Show everything known about a film title.")
    add_query_args(movie)
    movie.add_argument("query", help="Film title search.")
    movie.set_defaults(func=cmd_movie)

    film = sub.add_parser("film", help="Fetch live film details: poster URLs, cast, crew, and account actions.")
    film.add_argument("film", help="Film title, slug, /film/... path, or full Letterboxd film URL.")
    film.add_argument("--cast-limit", type=int, default=25, help="Maximum cast members to include.")
    film.add_argument("--format", choices=("table", "json"), default="table")
    film.set_defaults(func=cmd_film, no_db=True)

    watch = sub.add_parser(
        "watch",
        aliases=("where-to-watch", "availability", "streaming", "providers"),
        help="Fetch the signed-in Where to watch panel for a film.",
    )
    watch.add_argument("film", help="Film title, slug, /film/... path, or full Letterboxd film URL.")
    watch.add_argument("--format", choices=("table", "json", "csv"), default="table")
    watch.set_defaults(func=cmd_watch, no_db=True)

    cast = sub.add_parser("cast", help="Fetch the live cast for a film.")
    cast.add_argument("film", help="Film title, slug, /film/... path, or full Letterboxd film URL.")
    cast.add_argument("--limit", type=int, default=100, help="Maximum cast members to display.")
    cast.add_argument("--format", choices=("table", "json", "csv"), default="table")
    cast.set_defaults(func=cmd_cast, no_db=True)

    people = sub.add_parser("people", help="Search Letterboxd contributors such as actors, directors, and writers.")
    people.add_argument("query", help="Person search text.")
    people.add_argument("--limit", type=int, default=10, help="Maximum people to display.")
    people.add_argument("--format", choices=("table", "json", "csv"), default="table")
    people.set_defaults(func=cmd_people, no_db=True)

    lists = sub.add_parser("lists", help="Search live Letterboxd lists and return list URLs usable as film-set bases.")
    lists.add_argument("query", help="List search text.")
    lists.add_argument("--user", help="Restrict results to a Letterboxd username/display name when possible.")
    lists.add_argument("--pages", type=int, default=1, help="Maximum search pages to fetch.")
    lists.add_argument("--limit", type=int, default=10, help="Maximum lists to display.")
    lists.add_argument("--min-quality", type=float, default=12, help="Minimum list quality score. Defaults to 12.")
    lists.add_argument("--min-films", type=int, default=5, help="Minimum number of films in the list. Defaults to 5.")
    lists.add_argument("--min-likes", type=int, default=1, help="Minimum likes. Defaults to 1 to suppress zero-signal copies.")
    lists.add_argument("--max-films", type=int, help="Maximum number of films in the list.")
    lists.add_argument("--require-notes", action="store_true", help="Only show lists with notes/description text.")
    lists.add_argument("--strict", action="store_true", help="Use stronger quality thresholds: min quality 30, min films 10, min likes 10.")
    lists.add_argument("--include-junk", action="store_true", help="Disable default quality filtering; still computes quality_score.")
    lists.add_argument(
        "--prefer-following",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Boost and top-rank lists by people you follow when signed in. Defaults to on.",
    )
    lists.add_argument("--only-following", action="store_true", help="Only show lists by people you follow.")
    lists.add_argument("--following-pages", type=int, default=5, help="Following pages to scan for owner boosts. Defaults to 5.")
    lists.add_argument(
        "--sort",
        choices=("quality", "likes", "films", "comments", "relevance"),
        default="quality",
        help="Sort list results. Defaults to quality.",
    )
    lists.add_argument("--format", choices=("table", "json", "csv"), default="table")
    lists.set_defaults(func=cmd_lists, no_db=True)

    person = sub.add_parser("person", help="Fetch a live actor/director/writer filmography from Letterboxd.")
    person.add_argument("person", help="Person name, /actor/... path, /director/... path, or full Letterboxd URL.")
    person.add_argument(
        "--role",
        default="actor",
        choices=("actor", "director", "writer", "producer", "composer", "cinematography", "editor"),
        help="Contributor role path to use when the input is a plain name.",
    )
    person.add_argument("--pages", type=int, default=1, help="Maximum filmography pages to fetch.")
    person.add_argument("--limit", type=int, default=25, help="Maximum films to display.")
    person.add_argument("--hydrate", action="store_true", help="Fetch film JSON/account state for each result.")
    person.add_argument("--save", action="store_true", help="Save fetched film rows into the local query database.")
    person.add_argument("--format", choices=("table", "json", "csv"), default="table")
    add_letterboxd_filter_args(person, include_year=True)
    person.set_defaults(func=cmd_person)

    films = sub.add_parser("films", help="Browse any live Letterboxd film set with metadata filters.")
    films.add_argument(
        "base",
        nargs="?",
        default="/films/",
        help="Film-set path or URL. Defaults to /films/. Examples: /films/, /example-user/watchlist/, /director/michael-mann/.",
    )
    films.add_argument("--query", "-q", help="Client-side title filter after Letterboxd metadata filters.")
    films.add_argument("--pages", type=int, default=1, help="Maximum pages to fetch.")
    films.add_argument("--limit", type=int, default=25, help="Maximum films to display.")
    films.add_argument("--hydrate", action="store_true", help="Fetch film JSON/account state for each result.")
    films.add_argument("--save", action="store_true", help="Save fetched film rows into the local query database.")
    films.add_argument("--format", choices=("table", "json", "csv"), default="table")
    add_letterboxd_filter_args(films, include_year=True)
    films.set_defaults(func=cmd_films)

    recs = sub.add_parser("recs", help="Recommend unwatched films from a filtered Letterboxd set with grounded reasons.")
    recs.add_argument(
        "base",
        nargs="?",
        default="/films/",
        help="Film-set path or URL to recommend from. Defaults to /films/.",
    )
    recs.add_argument("--username", help="Letterboxd username for watched exclusion and taste signals.")
    recs.add_argument("--query", "-q", help="Client-side title filter after Letterboxd metadata filters.")
    recs.add_argument("--pages", type=int, default=1, help="Candidate pages to fetch.")
    recs.add_argument("--pool-size", type=int, default=50, help="Maximum candidate films to score before trimming.")
    recs.add_argument("--limit", type=int, default=10, help="Recommendations to display.")
    recs.add_argument("--include-watched", action="store_true", help="Do not exclude films already watched by the user.")
    recs.add_argument("--watched-pages", type=int, default=20, help="Watched pages to scan for exclusion.")
    recs.add_argument(
        "--bias-person",
        action="append",
        default=[],
        help="Person to boost when they appear as director or cast. Repeatable.",
    )
    recs.add_argument(
        "--taste-from-ratings",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Derive additional director/cast boosts from the user's highest-rated films.",
    )
    recs.add_argument("--taste-films", type=int, default=12, help="Highest-rated films to inspect for taste signals.")
    recs.add_argument("--taste-pages", type=int, default=3, help="Rating pages to scan for taste signals.")
    recs.add_argument("--cast-limit", type=int, default=8, help="Cast members to inspect per film.")
    recs.add_argument("--detail-limit", type=int, default=15, help="Maximum candidate film detail pages to fetch while scoring.")
    recs.add_argument("--request-delay", type=float, default=0.0, help="Seconds to wait between recommendation detail requests.")
    recs.add_argument("--format", choices=("table", "json", "csv"), default="table")
    add_letterboxd_filter_args(recs, include_year=True, default_sort="rating")
    recs.set_defaults(func=cmd_recs, no_db=True)

    log = sub.add_parser("log", help="Log, rate, review, tag, and like a film.")
    log.add_argument("film", help="Film slug, title, /film/... path, or full Letterboxd film URL.")
    add_log_entry_args(log)
    log.set_defaults(func=cmd_log_entry, no_db=True)

    watched = sub.add_parser("watched", help="Mark a film watched, optionally with rating/review/like fields.")
    watched.add_argument("film", help="Film slug, title, /film/... path, or full Letterboxd film URL.")
    add_log_entry_args(watched, include_date=True)
    watched.set_defaults(func=cmd_log_entry, no_db=True)

    diary = sub.add_parser("diary", help="Add a film to your diary. Defaults to today's date when --date is omitted.")
    diary.add_argument("film", help="Film slug, title, /film/... path, or full Letterboxd film URL.")
    add_log_entry_args(diary, include_date=True)
    diary.set_defaults(func=cmd_log_entry, default_today=True, no_db=True)

    rate = sub.add_parser("rate", help="Set a star rating for a film.")
    rate.add_argument("film", help="Film slug, title, /film/... path, or full Letterboxd film URL.")
    rate.add_argument("rating_value", type=float, help="Rating from 0.5 to 5.0.")
    add_log_entry_args(rate, include_rating=False, include_date=True)
    rate.set_defaults(func=cmd_log_entry, no_db=True)

    review = sub.add_parser("review", help="Add or update a review for a film.")
    review.add_argument("film", help="Film slug, title, /film/... path, or full Letterboxd film URL.")
    review.add_argument("review_text", help="Review text.")
    add_log_entry_args(review, include_review=False, include_date=True)
    review.set_defaults(func=cmd_log_entry, no_db=True)

    for name in ("heart", "like"):
        heart = sub.add_parser(name, help="Heart/like a film.")
        heart.add_argument("film", help="Film slug, title, /film/... path, or full Letterboxd film URL.")
        add_log_entry_args(heart, include_like=False, include_date=True)
        heart.set_defaults(func=cmd_log_entry, liked_default=True, no_db=True)

    stats = sub.add_parser("stats", help="Show local database summary stats.")
    stats.set_defaults(func=cmd_stats)

    export = sub.add_parser("export", help="Export query results.")
    add_query_args(export)
    export.add_argument("--kind", choices=sorted(KIND_ALIASES), help="Restrict exported rows.")
    export.set_defaults(func=cmd_export)

    sql = sub.add_parser("sql", help="Run a read-only SQL query against the local database.")
    sql.add_argument("query", help="SELECT query to run.")
    sql.add_argument("--format", choices=("table", "json", "csv"), default="table")
    sql.set_defaults(func=cmd_sql, readonly_db=True)

    auth = sub.add_parser("auth", help="Manage saved Letterboxd web session cookies.")
    auth_sub = auth.add_subparsers(dest="auth_command", required=True)

    auth_save = auth_sub.add_parser("save", help="Save a Letterboxd Cookie header for web commands.")
    auth_save.add_argument("--cookie", required=True, help="Raw Cookie header copied from your signed-in browser.")
    auth_save.set_defaults(func=cmd_auth_save, no_db=True)

    auth_status = auth_sub.add_parser("status", help="Check whether the saved web session appears signed in.")
    auth_status.add_argument("--format", choices=("table", "json"), default="table")
    auth_status.set_defaults(func=cmd_auth_status, no_db=True)

    auth_clear = auth_sub.add_parser("clear", help="Delete the saved web session.")
    auth_clear.set_defaults(func=cmd_auth_clear, no_db=True)

    web = sub.add_parser("web", help="Use your authenticated Letterboxd web session.")
    web_sub = web.add_subparsers(dest="web_command", required=True)

    web_get = web_sub.add_parser("get", help="GET a Letterboxd path or URL.")
    web_get.add_argument("path", help="Path or URL, for example /film/heat-1995/json/.")
    web_get.add_argument("--format", choices=("auto", "raw", "json"), default="auto")
    web_get.set_defaults(func=cmd_web_get, no_db=True)

    web_post = web_sub.add_parser("post", help="POST form data to a Letterboxd path or URL.")
    web_post.add_argument("path", help="Path or URL.")
    web_post.add_argument("--data", action="append", default=[], help="Form field as key=value. Can be repeated.")
    web_post.add_argument("--json-body", help="JSON request body instead of form data.")
    web_post.add_argument("--csrf-from", help="Fetch this page/path first and include its CSRF token.")
    web_post.add_argument("--dry-run", action="store_true", help="Print the request that would be made.")
    web_post.add_argument("--format", choices=("auto", "raw", "json"), default="auto")
    web_post.set_defaults(func=cmd_web_post, no_db=True)

    web_film = web_sub.add_parser("film", help="Fetch Letterboxd's JSON metadata for a film slug or URL.")
    web_film.add_argument("film", help="Film slug, /film/... URL path, or full Letterboxd film URL.")
    web_film.add_argument("--format", choices=("json", "table"), default="table")
    web_film.set_defaults(func=cmd_web_film, no_db=True)

    web_watchlist = web_sub.add_parser("watchlist", help="Add/remove a film from your watchlist.")
    web_watchlist.add_argument("action", choices=("add", "remove"))
    web_watchlist.add_argument("film", help="Film slug, /film/... URL path, or full Letterboxd film URL.")
    web_watchlist.add_argument("--dry-run", action="store_true", help="Print the request that would be made.")
    web_watchlist.set_defaults(func=cmd_web_watchlist, no_db=True)

    web_log = web_sub.add_parser("log", help="Create or update a diary/review/rating entry.")
    web_log.add_argument("film", help="Film slug, /film/... URL path, or full Letterboxd film URL.")
    web_log.add_argument("--date", help="Watched date as YYYY-MM-DD. Omit to save rating/review without diary date.")
    web_log.add_argument("--rating", type=float, help="Rating from 0.5 to 5.0.")
    web_log.add_argument("--review", default="", help="Review text.")
    web_log.add_argument("--tags", default="", help="Comma-separated tags.")
    web_log.add_argument("--rewatch", action="store_true", help="Mark the diary entry as a rewatch.")
    web_log.add_argument("--like", action="store_true", help="Like the film.")
    web_log.add_argument("--spoilers", action="store_true", help="Mark the review as containing spoilers.")
    web_log.add_argument("--privacy", choices=("Anyone", "Friends", "You", "Draft"), help="Entry privacy.")
    web_log.add_argument("--dry-run", action="store_true", help="Print the request that would be made.")
    web_log.set_defaults(func=cmd_web_log, no_db=True)

    live = sub.add_parser("live", help="Read live Letterboxd pages with your web session.")
    live_sub = live.add_subparsers(dest="live_command", required=True)

    live_me = live_sub.add_parser("me", help="Show the signed-in username detected from Letterboxd.")
    live_me.add_argument("--format", choices=("table", "json"), default="table")
    live_me.set_defaults(func=cmd_live_me, no_db=True)

    live_whoami = live_sub.add_parser("whoami", help="Show the signed-in username detected from Letterboxd.")
    live_whoami.add_argument("--format", choices=("table", "json"), default="table")
    live_whoami.set_defaults(func=cmd_live_me, no_db=True)

    live_search = live_sub.add_parser("search", help="Search Letterboxd live, display results, and optionally save them.")
    live_search.add_argument("query", help="Search text.")
    live_search.add_argument(
        "--type",
        choices=("films",),
        default="films",
        help="Search surface to query. Only film search is currently supported.",
    )
    live_search.add_argument("--pages", type=int, default=1, help="Maximum result pages to fetch.")
    live_search.add_argument("--limit", type=int, default=25, help="Maximum rows to display/save.")
    live_search.add_argument("--hydrate", action="store_true", help="Fetch each film JSON result for richer metadata.")
    live_search.add_argument("--save", action="store_true", help="Save fetched rows into the local query database.")
    live_search.add_argument("--format", choices=("table", "json", "csv"), default="table")
    add_letterboxd_filter_args(live_search, include_year=True)
    live_search.set_defaults(func=cmd_live_search)

    for name, route, kind, help_text in [
        ("watchlist", "watchlist", "watchlist", "Fetch a user's live watchlist."),
        ("watched", "films", "watched", "Fetch a user's live watched films."),
        ("diary", "films/diary", "diary", "Fetch a user's live diary."),
        ("reviews", "films/reviews", "review", "Fetch a user's live reviews."),
        ("ratings", "films/by/entry-rating", "rating", "Fetch a user's live rated films."),
    ]:
        p = live_sub.add_parser(name, help=help_text)
        p.add_argument("username", nargs="?", help="Letterboxd username. Defaults to signed-in user when detectable.")
        p.add_argument("--pages", type=int, default=1, help="Maximum pages to fetch.")
        p.add_argument("--limit", type=int, default=50, help="Maximum rows to display/save.")
        p.add_argument("--save", action="store_true", help="Save fetched rows into the local query database.")
        p.add_argument("--format", choices=("table", "json", "csv"), default="table")
        add_letterboxd_filter_args(p, include_year=True, include_sort=False)
        p.set_defaults(func=cmd_live_collection, live_route=route, live_kind=kind)

    live_sync = live_sub.add_parser("sync", help="Fetch multiple live account sections and save them locally.")
    live_sync.add_argument("username", nargs="?", help="Letterboxd username. Defaults to signed-in user when detectable.")
    live_sync.add_argument("--pages", type=int, default=3, help="Maximum pages per section.")
    live_sync.add_argument(
        "--kinds",
        default="watchlist,watched,diary,reviews,ratings",
        help="Comma-separated sections: watchlist,watched,diary,reviews,ratings.",
    )
    live_sync.set_defaults(func=cmd_live_sync)

    return parser


def add_log_entry_args(
    parser: argparse.ArgumentParser,
    *,
    include_date: bool = True,
    include_rating: bool = True,
    include_review: bool = True,
    include_like: bool = True,
) -> None:
    if include_date:
        parser.add_argument("--date", help="Watched date as YYYY-MM-DD. For diary, defaults to today.")
    if include_rating:
        parser.add_argument("--rating", type=float, help="Rating from 0.5 to 5.0.")
    if include_review:
        parser.add_argument("--review", default="", help="Review text.")
    else:
        parser.set_defaults(review="")
    parser.add_argument("--tags", default="", help="Comma-separated tags.")
    parser.add_argument("--rewatch", action="store_true", help="Mark the entry as a rewatch.")
    if include_like:
        parser.add_argument("--like", "--heart", dest="like", action="store_true", help="Heart/like the film.")
    else:
        parser.set_defaults(like=False)
    parser.add_argument("--spoilers", action="store_true", help="Mark the review as containing spoilers.")
    parser.add_argument("--privacy", choices=("Anyone", "Friends", "You", "Draft"), help="Entry privacy.")
    parser.add_argument("--dry-run", action="store_true", help="Print the request that would be made.")


def add_letterboxd_filter_args(
    parser: argparse.ArgumentParser,
    *,
    include_year: bool = False,
    include_sort: bool = True,
    default_sort: str = "popular",
) -> None:
    if include_year:
        parser.add_argument("--year", type=int, help="Filter by release year, for example 1995.")
    parser.add_argument("--decade", help="Filter by decade, for example 1990s or 1990.")
    parser.add_argument(
        "--genre",
        action="append",
        default=[],
        help="Include genre slug/name. Repeat or comma-separate, for example --genre crime --genre thriller.",
    )
    parser.add_argument(
        "--exclude-genre",
        action="append",
        default=[],
        help="Exclude genre slug/name. Repeat or comma-separate, for example --exclude-genre documentary.",
    )
    parser.add_argument(
        "--filter",
        action="append",
        default=[],
        help="Raw Letterboxd filter path segment, for example country/usa, language/english, or on/netflix-us.",
    )
    if include_sort:
        parser.add_argument(
            "--sort",
            choices=sorted(LETTERBOXD_SORTS),
            default=default_sort,
            help="Letterboxd sort for filtered live film sets.",
        )


def add_query_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--query", "-q", help="Text filter.")
    parser.add_argument("--year", type=int, help="Filter by release year.")
    parser.add_argument("--from-date", help="Filter dates on or after YYYY-MM-DD.")
    parser.add_argument("--to-date", help="Filter dates on or before YYYY-MM-DD.")
    parser.add_argument("--min-rating", type=float, help="Minimum rating.")
    parser.add_argument("--max-rating", type=float, help="Maximum rating.")
    parser.add_argument(
        "--sort",
        choices=("date", "rating", "title", "year", "kind"),
        default="date",
        help="Sort column.",
    )
    parser.add_argument("--desc", action="store_true", help="Sort descending.")
    parser.add_argument("--limit", type=int, default=50, help="Maximum rows.")
    parser.add_argument("--format", choices=("table", "json", "csv"), default="table")


def env_flag(name: str) -> bool:
    value = os.environ.get(name, "")
    return value.casefold() in {"1", "true", "yes", "on"}


def apply_global_output_mode(args: argparse.Namespace) -> None:
    if args.json and args.plain:
        raise ValueError("Use either --json or --plain, not both.")
    if not hasattr(args, "format"):
        return
    if args.json:
        args.format = "json"
    elif args.plain and args.format in {"table", "csv"}:
        args.format = "csv"
    elif args.plain and args.format in {"auto", "raw"}:
        args.format = "raw"


def cmd_version(db: sqlite3.Connection | None, args: argparse.Namespace) -> int:
    payload = {"name": "letterboxd-cli", "command": "lbd", "version": __version__}
    if args.format == "json":
        print(json.dumps(payload, indent=2))
    else:
        print(f"lbd {__version__}")
    return 0


def cmd_load(db: sqlite3.Connection, args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser()
    if not path.exists():
        raise OSError(f"Path does not exist: {path}")

    if not args.append:
        db.execute("DELETE FROM entries WHERE kind != 'feed'")

    sources = list(read_csv_sources(path))
    imported = 0
    file_counts: Counter[str] = Counter()

    for source in sources:
        reader = csv.DictReader(io.StringIO(source.text))
        for row in reader:
            if not row or not any((value or "").strip() for value in row.values()):
                continue
            normalized = normalize_csv_row(row, source)
            insert_entry(db, normalized)
            imported += 1
            file_counts[source.name] += 1

    db.execute(
        """
        INSERT INTO import_runs(source_path, imported_at, rows_imported, files_imported)
        VALUES (?, ?, ?, ?)
        """,
        (str(path.resolve()), now_iso(), imported, len(file_counts)),
    )
    db.commit()

    print(f"Imported {imported} rows from {len(file_counts)} CSV file(s).")
    for file_name, count in sorted(file_counts.items()):
        print(f"  {file_name}: {count}")
    return 0


def cmd_feed(db: sqlite3.Connection, args: argparse.Namespace) -> int:
    if args.url:
        url = args.url
    elif args.username:
        url = f"https://letterboxd.com/{args.username.strip('/')}/rss/"
    else:
        raise ValueError("Provide a username or --url.")

    body = fetch_url(url)
    rows = parse_rss(body, url)
    for row in rows:
        insert_entry(db, row)
    db.commit()

    print(f"Fetched {len(rows)} RSS item(s) from {url}.", file=sys.stderr)
    query_args = argparse.Namespace(
        fixed_kind="feed",
        query=None,
        year=None,
        from_date=None,
        to_date=None,
        min_rating=None,
        max_rating=None,
        sort="date",
        desc=True,
        limit=args.limit,
        format=args.format,
    )
    return cmd_list(db, query_args)


def cmd_query(db: sqlite3.Connection, args: argparse.Namespace) -> int:
    rows: list[dict[str, Any]] = []
    source = args.source
    if args.live:
        source = "live"
    if args.both:
        source = "both"
    if args.local:
        source = "local"

    if source in {"local", "both"}:
        warn_cache_read("q --local" if source == "local" else "q --both")
        local_args = argparse.Namespace(
            query=args.query,
            year=args.year,
            from_date=None,
            to_date=None,
            min_rating=args.min_rating,
            max_rating=args.max_rating,
            sort="date",
            desc=True,
            limit=args.limit,
        )
        rows.extend(dict(row) for row in select_entries(db, local_args, kind=args.kind, text=args.query))

    live_rows: list[dict[str, Any]] = []
    if source in {"live", "both"}:
        client = LetterboxdWebClient.from_args(args)
        filters = filters_from_args(args)
        if filters_have_values(filters):
            live_rows = fetch_filtered_films(
                client,
                base="/films/",
                filters=filters,
                pages=args.pages,
                limit=args.limit,
                hydrate=args.hydrate,
                query=args.query,
            )
        else:
            live_rows = fetch_live_search(
                client,
                query=args.query,
                search_type="films",
                pages=args.pages,
                limit=args.limit,
                hydrate=args.hydrate,
            )
        if args.save:
            for row in live_rows:
                insert_entry(db, row)
            db.commit()
            print(f"Saved {len(live_rows)} live row(s).", file=sys.stderr)
        rows.extend(live_rows)

    return print_rows(dedupe_display_rows(rows)[: max(1, args.limit)], args.format)


def cmd_search(db: sqlite3.Connection, args: argparse.Namespace) -> int:
    warn_cache_read("search")
    return print_rows(select_entries(db, args, text=args.query), args.format)


def cmd_list(db: sqlite3.Connection, args: argparse.Namespace) -> int:
    warn_cache_read(args.fixed_kind)
    return print_rows(select_entries(db, args, kind=args.fixed_kind), args.format)


def cmd_movie(db: sqlite3.Connection, args: argparse.Namespace) -> int:
    warn_cache_read("movie")
    rows = select_entries(db, args, text=args.query)
    if not rows:
        print("No matching rows.")
        return 0

    grouped: dict[tuple[str, int | None], list[sqlite3.Row]] = {}
    for row in rows:
        grouped.setdefault((row["name"] or "(untitled)", row["year"]), []).append(row)

    for (name, year), group in sorted(grouped.items(), key=lambda item: item[0]):
        print(f"{name}{f' ({year})' if year else ''}")
        ratings = [row["rating"] for row in group if row["rating"] is not None]
        kinds = Counter(row["kind"] for row in group)
        if ratings:
            print(f"  ratings: {', '.join(format_rating(r) for r in ratings)}")
        print(f"  rows: {sum(kinds.values())} ({', '.join(f'{k}: {v}' for k, v in sorted(kinds.items()))})")
        for row in group[: args.limit]:
            date = row["watched_date"] or row["date"] or ""
            detail = " | ".join(
                part
                for part in [
                    row["kind"],
                    date,
                    format_rating(row["rating"]) if row["rating"] is not None else "",
                    truncate(row["review"] or "", 100),
                ]
                if part
            )
            print(f"  - {detail}")
    return 0


def cmd_film(db: sqlite3.Connection, args: argparse.Namespace) -> int:
    client = LetterboxdWebClient.from_args(args)
    slug = resolve_film_slug(client, args.film)
    detail = fetch_film_detail(client, slug=slug, cast_limit=max(1, args.cast_limit))
    if args.format == "json":
        print(json.dumps(detail, indent=2, ensure_ascii=False))
        return 0
    return print_film_detail(detail)


def cmd_watch(db: sqlite3.Connection, args: argparse.Namespace) -> int:
    client = LetterboxdWebClient.from_args(args)
    username = detect_username(client)
    if not username:
        raise ValueError("A signed-in Letterboxd session is required. Run `lbd login` first.")
    slug = resolve_film_slug(client, args.film)
    try:
        availability = fetch_film_availability(client, slug=slug, username=username)
    except LetterboxdWebError as exc:
        if exc.status != 404:
            raise
        canonical_slug = search_film_slug(client, film_slug_search_query(slug))
        if canonical_slug == slug:
            raise
        availability = fetch_film_availability(client, slug=canonical_slug, username=username)
        availability["requested_film"] = args.film
        availability["requested_slug"] = slug
    return print_availability(availability, args.format)


def cmd_cast(db: sqlite3.Connection, args: argparse.Namespace) -> int:
    client = LetterboxdWebClient.from_args(args)
    slug = resolve_film_slug(client, args.film)
    detail = fetch_film_detail(client, slug=slug, cast_limit=max(1, args.limit))
    rows = detail.get("cast") or []
    return print_generic_rows(rows[: max(1, args.limit)], args.format, ["name", "character", "url"])


def cmd_people(db: sqlite3.Connection, args: argparse.Namespace) -> int:
    client = LetterboxdWebClient.from_args(args)
    rows = fetch_people_search(client, args.query, limit=max(1, args.limit))
    return print_generic_rows(rows, args.format, ["name", "role", "description", "url"])


def cmd_lists(db: sqlite3.Connection, args: argparse.Namespace) -> int:
    client = LetterboxdWebClient.from_args(args)
    following_usernames: set[str] = set()
    if args.prefer_following or args.only_following:
        username = username_from_cookie(client.cookie)
        if username:
            following_usernames = fetch_following_usernames(
                client,
                username,
                pages=max(1, args.following_pages),
            )
    min_quality = 0 if args.include_junk else args.min_quality
    min_films = 0 if args.include_junk else args.min_films
    min_likes = 0 if args.include_junk else args.min_likes
    if args.strict and not args.include_junk:
        min_quality = max(min_quality, 30)
        min_films = max(min_films, 10)
        min_likes = max(min_likes, 10)
    rows = fetch_list_search(
        client,
        args.query,
        user=args.user,
        pages=max(1, args.pages),
        limit=max(1, args.limit),
        min_quality=min_quality,
        min_films=min_films,
        min_likes=min_likes,
        max_films=args.max_films,
        require_notes=args.require_notes,
        sort=args.sort,
        following_usernames=following_usernames,
        only_following=args.only_following,
    )
    return print_generic_rows(
        rows,
        args.format,
        [
            "source",
            "owner_followed",
            "quality_score",
            "name",
            "owner",
            "films",
            "likes",
            "comments",
            "url",
            "detail_url",
        ],
    )


def cmd_films(db: sqlite3.Connection, args: argparse.Namespace) -> int:
    client = LetterboxdWebClient.from_args(args)
    rows = fetch_filtered_films(
        client,
        base=args.base,
        filters=filters_from_args(args),
        pages=args.pages,
        limit=args.limit,
        hydrate=args.hydrate,
        query=args.query,
    )
    if args.save:
        for row in rows:
            insert_entry(db, row)
        db.commit()
        print(f"Saved {len(rows)} filtered film row(s).", file=sys.stderr)
    return print_person_rows(rows, args.format)


def cmd_recs(db: sqlite3.Connection, args: argparse.Namespace) -> int:
    client = LetterboxdWebClient.from_args(args)
    username = args.username or detect_username(client)
    if not username and not args.include_watched:
        print(
            "Warning: no signed-in username detected; watched exclusion is disabled. "
            "Use lbd login or pass --username.",
            file=sys.stderr,
        )
    filters = filters_from_args(args)
    base = args.base
    query = args.query
    if is_global_films_base(base) and query and looks_like_letterboxd_film_set(query):
        base = query
        query = None
    rows = recommend_films(
        client,
        base=base,
        filters=filters,
        username=username,
        query=query,
        pages=args.pages,
        pool_size=args.pool_size,
        limit=args.limit,
        include_watched=args.include_watched,
        watched_pages=args.watched_pages,
        bias_people=args.bias_person,
        taste_from_ratings=args.taste_from_ratings,
        taste_films=args.taste_films,
        taste_pages=args.taste_pages,
        cast_limit=args.cast_limit,
        detail_limit=args.detail_limit,
        request_delay=args.request_delay,
    )
    return print_recommendations(rows, args.format)


def cmd_person(db: sqlite3.Connection, args: argparse.Namespace) -> int:
    client = LetterboxdWebClient.from_args(args)
    rows = fetch_person_filmography(
        client,
        args.person,
        role=args.role,
        pages=max(1, args.pages),
        limit=max(1, args.limit),
        hydrate=args.hydrate,
        filters=filters_from_args(args),
    )
    if args.save:
        for row in rows:
            insert_entry(db, row)
        db.commit()
        print(f"Saved {len(rows)} person film row(s).", file=sys.stderr)
    return print_person_rows(rows, args.format)


def cmd_stats(db: sqlite3.Connection, args: argparse.Namespace) -> int:
    total = db.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    print(f"Rows: {total}")

    by_kind = db.execute(
        "SELECT kind, COUNT(*) AS count FROM entries GROUP BY kind ORDER BY kind"
    ).fetchall()
    for row in by_kind:
        print(f"{row['kind']}: {row['count']}")

    rating_rows = db.execute(
        """
        SELECT rating, COUNT(*) AS count
        FROM entries
        WHERE rating IS NOT NULL
        GROUP BY rating
        ORDER BY rating DESC
        """
    ).fetchall()
    if rating_rows:
        print("\nRating distribution:")
        for row in rating_rows:
            print(f"{format_rating(row['rating'])}: {row['count']}")

    top_tags = Counter()
    for row in db.execute("SELECT tags FROM entries WHERE tags IS NOT NULL"):
        for tag in split_tags(row["tags"]):
            top_tags[tag] += 1
    if top_tags:
        print("\nTop tags:")
        for tag, count in top_tags.most_common(15):
            print(f"{tag}: {count}")
    return 0


def cmd_export(db: sqlite3.Connection, args: argparse.Namespace) -> int:
    kind = KIND_ALIASES.get(args.kind) if args.kind else None
    return print_rows(select_entries(db, args, kind=kind), args.format)


def cmd_sql(db: sqlite3.Connection, args: argparse.Namespace) -> int:
    query = args.query.strip()
    if not query.lower().startswith("select"):
        raise ValueError("Only SELECT queries are allowed.")
    cursor = db.execute(query)
    rows = cursor.fetchall()
    columns = [description[0] for description in (cursor.description or [])]
    return print_generic_rows(rows, args.format, columns)


def cmd_web_get(db: sqlite3.Connection, args: argparse.Namespace) -> int:
    client = LetterboxdWebClient.from_args(args)
    response = client.get(args.path)
    return print_web_response(response, args.format)


def cmd_web_post(db: sqlite3.Connection, args: argparse.Namespace) -> int:
    client = LetterboxdWebClient.from_args(args)
    data = parse_key_values(args.data)
    headers: dict[str, str] = {}

    if args.csrf_from:
        csrf_response = client.get(args.csrf_from)
        csrf = extract_csrf(csrf_response.text)
        if csrf:
            data.setdefault("csrf", csrf)
            data.setdefault("__csrf", csrf)
            headers["X-CSRF-Token"] = csrf
            headers["X-CSRFToken"] = csrf

    body, content_type, body_preview = build_web_post_body(args.json_body, data)
    headers["Content-Type"] = content_type

    if args.dry_run:
        print(
            json.dumps(
                {
                    "method": "POST",
                    "url": client.url(args.path),
                    "content_type": content_type,
                    "headers": redact_sensitive_values(headers),
                    "body": redact_sensitive_values(body_preview),
                },
                indent=2,
            )
        )
        return 0

    response = client.request("POST", args.path, body=body, headers=headers)
    return print_web_response(response, args.format)


def build_web_post_body(json_body: str | None, data: dict[str, str]) -> tuple[bytes, str, Any]:
    if json_body:
        try:
            payload = json.loads(json_body)
        except json.JSONDecodeError as exc:
            raise ValueError("--json-body must be valid JSON.") from exc
        return (
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            "application/json",
            payload,
        )
    return (
        urllib.parse.urlencode(data).encode("utf-8"),
        "application/x-www-form-urlencoded",
        data,
    )


def cmd_web_film(db: sqlite3.Connection, args: argparse.Namespace) -> int:
    client = LetterboxdWebClient.from_args(args)
    film_path = film_json_path(args.film)
    response = client.get(film_path)
    payload = parse_json_response(response)
    if args.format == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    rows = [
        {"field": "name", "value": payload.get("name", "")},
        {"field": "year", "value": str(payload.get("releaseYear", ""))},
        {"field": "slug", "value": payload.get("slug", "")},
        {"field": "lid", "value": payload.get("lid", "")},
        {"field": "uid", "value": payload.get("uid", "")},
        {"field": "watchlist action", "value": payload.get("watchlistAction", "")},
        {"field": "list action", "value": payload.get("filmlistAction", "")},
    ]
    print_table(rows, ["field", "value"])
    return 0


def cmd_web_watchlist(db: sqlite3.Connection, args: argparse.Namespace) -> int:
    client = LetterboxdWebClient.from_args(args)
    film_response = fetch_loggable_film_response(client, args.film)
    film = parse_json_response(film_response)
    action = watchlist_action_for(film, args.action)
    csrf = str(film.get("csrf") or extract_csrf(film_response.text) or "")

    data = {}
    headers = {}
    if csrf:
        data["csrf"] = csrf
        data["__csrf"] = csrf
        headers["X-CSRF-Token"] = csrf
        headers["X-CSRFToken"] = csrf

    if args.dry_run:
        print(
            json.dumps(
                {
                    "method": "POST",
                    "url": client.url(action),
                    "film": film.get("name"),
                    "action": args.action,
                    "data": redact_sensitive_values(data),
                },
                indent=2,
            )
        )
        return 0

    response = client.request(
        "POST",
        action,
        body=urllib.parse.urlencode(data).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded", **headers},
    )
    print_web_response(response, "auto")
    return 0


def cmd_log_entry(db: sqlite3.Connection, args: argparse.Namespace) -> int:
    if getattr(args, "default_today", False) and not getattr(args, "date", None):
        args.date = today_iso()
    if getattr(args, "rating_value", None) is not None:
        args.rating = args.rating_value
    elif not hasattr(args, "rating"):
        args.rating = None
    if getattr(args, "review_text", None) is not None:
        args.review = args.review_text
    elif not hasattr(args, "review"):
        args.review = ""
    if getattr(args, "liked_default", False):
        args.like = True
    elif not hasattr(args, "like"):
        args.like = False
    return save_log_entry(args)


def cmd_web_log(db: sqlite3.Connection, args: argparse.Namespace) -> int:
    return save_log_entry(args)


def save_log_entry(args: argparse.Namespace) -> int:
    client = LetterboxdWebClient.from_args(args)
    film_response = fetch_loggable_film_response(client, args.film)
    film = parse_json_response(film_response)
    csrf = str(film.get("csrf") or "")
    lid = str(film.get("lid") or "")
    if not lid:
        raise ValueError("Could not find the film LID needed to save an entry.")

    if args.rating is not None:
        if args.rating < 0.5 or args.rating > 5 or (args.rating * 2) % 1:
            raise ValueError("Rating must be from 0.5 to 5.0 in half-star increments.")

    payload = build_log_entry_payload(film, args)

    headers = {"Content-Type": "application/json; charset=UTF-8", "Accept": "application/json"}
    if csrf:
        headers["X-CSRF-TOKEN"] = csrf

    if args.dry_run:
        print(
            json.dumps(
                {
                    "method": "POST",
                    "url": client.url("/api/v0/production-log-entries"),
                    "film": film.get("name"),
                    "data": payload,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    response = client.request(
        "POST",
        "/api/v0/production-log-entries",
        body=json.dumps(payload).encode("utf-8"),
        headers=headers,
    )
    return print_web_response(response, "auto")


def build_log_entry_payload(film: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    lid = str(film.get("lid") or "")
    payload: dict[str, Any] = {
        "productionId": lid,
        "tags": split_tags(args.tags),
        "like": bool(args.like),
    }
    if args.date:
        payload["diaryDetails"] = {
            "diaryDate": args.date,
            "rewatch": bool(args.rewatch),
        }
    if args.review:
        payload["review"] = {
            "text": args.review,
            "containsSpoilers": bool(args.spoilers),
        }
    if args.rating is not None:
        payload["rating"] = args.rating
    if args.privacy:
        payload["privacyPolicy"] = args.privacy
    return payload


def fetch_loggable_film_response(client: LetterboxdWebClient, value: str) -> WebResponse:
    slug = resolve_film_slug(client, value)
    return client.get(f"/film/{slug}/json/")


def cmd_live_me(db: sqlite3.Connection, args: argparse.Namespace) -> int:
    client = LetterboxdWebClient.from_args(args)
    username = detect_username(client)
    if args.format == "json":
        print(json.dumps({"signed_in": bool(username), "username": username}, indent=2))
        return 0 if username else 1
    if not username:
        print("No signed-in username detected.")
        return 1
    print(username)
    return 0


def cmd_live_search(db: sqlite3.Connection, args: argparse.Namespace) -> int:
    client = LetterboxdWebClient.from_args(args)
    filters = filters_from_args(args)
    if args.type == "films" and filters_have_values(filters):
        rows = fetch_filtered_films(
            client,
            base="/films/",
            filters=filters,
            pages=args.pages,
            limit=args.limit,
            hydrate=args.hydrate,
            query=args.query,
        )
    else:
        rows = fetch_live_search(
            client,
            query=args.query,
            search_type=args.type,
            pages=args.pages,
            limit=args.limit,
            hydrate=args.hydrate,
        )
    if args.save:
        for row in rows:
            insert_entry(db, row)
        db.commit()
        print(f"Saved {len(rows)} live search row(s).", file=sys.stderr)
    return print_rows(rows, args.format)


def cmd_live_collection(db: sqlite3.Connection, args: argparse.Namespace) -> int:
    client = LetterboxdWebClient.from_args(args)
    username = args.username or detect_username(client)
    if not username:
        raise ValueError("Provide a username or save a signed-in session first.")

    rows = fetch_live_collection(
        client,
        username=username,
        route=args.live_route,
        kind=args.live_kind,
        pages=args.pages,
        filters=filters_from_args(args),
    )[: max(1, args.limit)]
    if args.save:
        for row in rows:
            insert_entry(db, row)
        db.commit()
        print(f"Saved {len(rows)} live {args.live_kind} row(s).", file=sys.stderr)
    return print_rows(rows, args.format)


def cmd_live_sync(db: sqlite3.Connection, args: argparse.Namespace) -> int:
    client = LetterboxdWebClient.from_args(args)
    username = args.username or detect_username(client)
    if not username:
        raise ValueError("Provide a username or save a signed-in session first.")

    section_map = {
        "watchlist": ("watchlist", "watchlist"),
        "watched": ("films", "watched"),
        "diary": ("films/diary", "diary"),
        "reviews": ("films/reviews", "review"),
        "ratings": ("films/by/entry-rating", "rating"),
    }
    requested = [part.strip() for part in args.kinds.split(",") if part.strip()]
    unknown = [kind for kind in requested if kind not in section_map]
    if unknown:
        raise ValueError(f"Unknown live section(s): {', '.join(unknown)}")

    counts = {}
    for section in requested:
        route, kind = section_map[section]
        rows = fetch_live_collection(
            client,
            username=username,
            route=route,
            kind=kind,
            pages=args.pages,
            filters=LetterboxdFilters(),
        )
        for row in rows:
            insert_entry(db, row)
        counts[section] = len(rows)
    db.commit()

    for section, count in counts.items():
        print(f"{section}: {count}")
    return 0


def parse_key_values(values: list[str]) -> dict[str, str]:
    parsed = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"Expected key=value for --data, got {value!r}.")
        key, item = value.split("=", 1)
        parsed[key] = item
    return parsed


def extract_csrf(body: str) -> str | None:
    patterns = [
        r"\bsupermodelCSRF\s*=\s*['\"]([^'\"]+)['\"]",
        r'"csrf"\s*:\s*"([^"]+)"',
        r"name=['\"]csrf['\"]\s+value=['\"]([^'\"]+)['\"]",
        r"name=['\"]__csrf['\"]\s+value=['\"]([^'\"]+)['\"]",
        r"<meta\s+name=['\"]csrf-token['\"]\s+content=['\"]([^'\"]+)['\"]",
    ]
    for pattern in patterns:
        match = re.search(pattern, body)
        if match:
            return html.unescape(match.group(1))
    return None


def film_json_path(value: str) -> str:
    slug = film_slug(value)
    return f"/film/{slug}/json/"


def film_slug(value: str) -> str:
    text = value.strip()
    parsed = urllib.parse.urlparse(text)
    path = parsed.path if parsed.scheme else text
    match = re.search(r"/?film/([^/]+)/?", path)
    if match:
        return match.group(1)
    slug = text.strip("/")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug):
        raise ValueError("Provide a Letterboxd film slug or URL, for example heat-1995.")
    return slug


def watchlist_action_for(film: dict[str, Any], action: str) -> str:
    add_action = str(film.get("watchlistAction") or "")
    slug = str(film.get("slug") or "")
    if not add_action and not slug:
        raise ValueError("Could not find a watchlist action for this film.")
    if action == "add":
        return add_action or f"/film/{slug}/add-to-watchlist/"
    if add_action:
        candidates = [
            ("add-to-watchlist", "remove-from-watchlist"),
            ("add-to-watchlist", "remove-from-watchlist/"),
        ]
        for old, new in candidates:
            if old in add_action:
                return add_action.replace(old, new)
    return f"/film/{slug}/remove-from-watchlist/"


def warn_cache_read(command: str) -> None:
    print(
        f"Cache read: `{command}` uses the local lbd cache, not live Letterboxd account state. "
        "Use live commands for current watchlist/watched/rating/review truth.",
        file=sys.stderr,
    )


def resolve_film_slug(client: LetterboxdWebClient, value: str) -> str:
    try:
        return film_slug(value)
    except ValueError:
        pass
    return search_film_slug(client, value)


def search_film_slug(client: LetterboxdWebClient, value: str) -> str:
    rows = fetch_live_search(client, query=value, search_type="films", pages=1, limit=1, hydrate=False)
    if not rows:
        raise ValueError(f"No Letterboxd film result found for {value!r}.")
    url = str(rows[0].get("url") or "")
    if not url:
        raise ValueError(f"Could not resolve a film slug for {value!r}.")
    return film_slug(url)


def film_slug_search_query(slug: str) -> str:
    return re.sub(r"\s+\d{4}$", "", slug.replace("-", " ")).strip() or slug


def fetch_film_detail(client: LetterboxdWebClient, *, slug: str, cast_limit: int) -> dict[str, Any]:
    json_response = client.get(f"/film/{slug}/json/")
    film_json = parse_json_response(json_response) if json_response.status < 400 else {}
    page_response = client.get(f"/film/{slug}/")
    page_html = page_response.text if page_response.status < 400 else ""
    crew_response = client.get(f"/film/{slug}/crew/")
    crew_html = crew_response.text if crew_response.status < 400 else page_html

    title = str(film_json.get("name") or film_json.get("filmName") or slug.replace("-", " ").title())
    year = parse_int(str(film_json.get("releaseYear") or ""))
    film_url = absolute_letterboxd_url(str(film_json.get("url") or f"/film/{slug}/"))
    cast = parse_film_cast(page_html, limit=cast_limit)
    crew = parse_film_crew(crew_html)
    directors = [
        person.get("name")
        for person in film_json.get("directors") or []
        if isinstance(person, dict) and person.get("name")
    ]
    if not directors and crew.get("Director"):
        directors = [person["name"] for person in crew["Director"] if person.get("name")]

    return {
        "name": title,
        "year": year,
        "slug": str(film_json.get("slug") or slug),
        "url": film_url,
        "uid": film_json.get("uid"),
        "lid": film_json.get("lid"),
        "directors": directors,
        "poster_urls": collect_poster_urls(film_json, page_html),
        "cast": cast,
        "crew": crew,
        "actions": {
            "watchlist": film_json.get("watchlistAction"),
            "list": film_json.get("filmlistAction"),
        },
        "raw_json": film_json,
    }


def fetch_film_availability(client: LetterboxdWebClient, *, slug: str, username: str) -> dict[str, Any]:
    path = f"/csi/film/{slug}/availability/?esiAllowUser=true&esiAllowCountry=true"
    response = client.get(path)
    if response.status >= 400:
        raise LetterboxdWebError(
            f"Could not fetch Letterboxd availability for {slug}: HTTP {response.status}.",
            status=response.status,
            url=response.url,
        )
    services = parse_availability_services(response.text)
    extras = parse_availability_extras(response.text)
    return {
        "film": slug,
        "url": absolute_letterboxd_url(f"/film/{slug}/"),
        "user": username,
        "source": "letterboxd_availability",
        "source_url": response.url,
        "fetched_at": now_iso(),
        "services": services,
        "extras": extras,
    }


def parse_availability_services(body: str) -> list[dict[str, Any]]:
    services: list[dict[str, Any]] = []
    for match in re.finditer(r"<p\b(?P<attrs>[^>]*\bclass=\"[^\"]*\bservice\b[^\"]*\"[^>]*)>(?P<html>.*?)</p>", body, re.S):
        attrs = parse_attrs(match.group("attrs"))
        class_names = set(attrs.get("class", "").split())
        if "js-expand-services" in class_names:
            continue
        chunk = match.group("html")
        anchors = list(re.finditer(r"<a\b(?P<attrs>[^>]*)>(?P<html>.*?)</a>", chunk, re.S))
        if not anchors:
            continue

        label_attrs = parse_attrs(anchors[0].group("attrs"))
        label_html = anchors[0].group("html")
        name_match = re.search(r"<span\b[^>]*\bclass=\"[^\"]*\bname\b[^\"]*\"[^>]*>(?P<name>.*?)</span>", label_html, re.S)
        locale_match = re.search(r"<span\b[^>]*\bclass=\"[^\"]*\blocale\b[^\"]*\"[^>]*>(?P<locale>.*?)</span>", label_html, re.S)
        img_match = re.search(r"<img\b(?P<attrs>[^>]*)>", label_html, re.S)
        img_attrs = parse_attrs(img_match.group("attrs")) if img_match else {}
        service_name = clean_html(name_match.group("name")) if name_match else clean_html(label_html)
        locale = clean_html(locale_match.group("locale")) if locale_match else ""
        service_id = availability_service_id(attrs)

        options = []
        for option_match in anchors[1:]:
            option_attrs = parse_attrs(option_match.group("attrs"))
            option_label = clean_html(option_match.group("html"))
            if not option_label:
                continue
            options.append(
                {
                    "type": availability_option_type(option_attrs, option_label),
                    "label": option_label,
                    "title": option_attrs.get("title", ""),
                    "url": html.unescape(option_attrs.get("href", "")),
                }
            )

        services.append(
            {
                "service": service_name,
                "service_id": service_id,
                "locale": locale,
                "url": html.unescape(label_attrs.get("href", "")),
                "icon_url": absolute_url(img_attrs.get("src")),
                "options": options,
                "option_types": sorted({str(option.get("type") or "") for option in options if option.get("type")}),
            }
        )
    return services


def availability_service_id(attrs: dict[str, str]) -> str:
    source_id = attrs.get("id", "")
    if source_id.startswith("source-"):
        return source_id.removeprefix("source-")
    for class_name in attrs.get("class", "").split():
        if class_name.startswith("-") and class_name not in {"-showmore"}:
            return class_name.removeprefix("-")
    return ""


def availability_option_type(attrs: dict[str, str], label: str) -> str:
    class_names = attrs.get("class", "").split()
    for option_type in ("stream", "rent", "buy"):
        if f"-{option_type}" in class_names:
            return option_type
    normalized = key_for(label)
    if normalized in {"play", "watch"}:
        return "stream"
    if normalized:
        return normalized
    return "link"


def parse_availability_extras(body: str) -> dict[str, str]:
    extras: dict[str, str] = {}
    trailer_match = re.search(r"<p\b[^>]*\btrailer-link\b[^>]*>.*?<a\b(?P<attrs>[^>]*)>", body, re.S)
    if trailer_match:
        attrs = parse_attrs(trailer_match.group("attrs"))
        extras["trailer_url"] = absolute_url(attrs.get("href")) or ""

    more_match = re.search(r"<a\b(?P<attrs>[^>]*\bjs-film-availability-link\b[^>]*)>", body, re.S)
    if more_match:
        attrs = parse_attrs(more_match.group("attrs"))
        extras["more_services_url"] = absolute_letterboxd_url(attrs.get("href")) or ""
        extras["more_services_data_url"] = absolute_letterboxd_url(attrs.get("data-url")) or ""
        extras["more_services_csi_url"] = absolute_letterboxd_url(attrs.get("data-availability-href")) or ""

    justwatch_match = re.search(r"<a\b(?P<attrs>[^>]*\bjw-branding\b[^>]*)>", body, re.S)
    if justwatch_match:
        attrs = parse_attrs(justwatch_match.group("attrs"))
        extras["justwatch_url"] = html.unescape(attrs.get("href", ""))

    ticket_match = re.search(r"<a\b(?P<attrs>[^>]*\bjs-buy-tickets-link\b[^>]*)>", body, re.S)
    if ticket_match:
        attrs = parse_attrs(ticket_match.group("attrs"))
        extras["ticketing_url"] = html.unescape(attrs.get("href", ""))
    return {key: value for key, value in extras.items() if value}


def collect_poster_urls(film_json: dict[str, Any], page_html: str) -> dict[str, str]:
    urls: dict[str, str] = {}
    slug = str(film_json.get("slug") or "").strip()
    for key, value in film_json.items():
        normalized = key.casefold()
        if isinstance(value, str) and (
            normalized.startswith("image") or "poster" in normalized or normalized in {"backdrop", "image"}
        ):
            url = absolute_letterboxd_url(value)
            if url:
                urls[key] = url

    for attrs in iter_tags_with_class(page_html, "div", "react-component"):
        if attrs.get("data-component-class") != "LazyPoster":
            continue
        if slug and attrs.get("data-item-slug") not in ("", slug):
            continue
        if slug and attrs.get("data-item-link") not in ("", f"/film/{slug}/"):
            continue
        poster_url = poster_url_from_attrs(attrs)
        if poster_url:
            urls["poster_url"] = poster_url

    for attrs in iter_tags(page_html, "meta"):
        label = attrs.get("property") or attrs.get("name") or ""
        content = attrs.get("content")
        if label in {"og:image", "twitter:image"} and content:
            url = absolute_letterboxd_url(content)
            if url:
                urls[label.replace(":", "_")] = url
    return urls


def parse_film_cast(body: str, *, limit: int) -> list[dict[str, str]]:
    section_match = re.search(
        r'<div\b[^>]*class="[^"]*\bcast-list\b[^"]*"[^>]*>(?P<section>.*?)</div>',
        body,
        re.S,
    )
    section = section_match.group("section") if section_match else body
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for match in re.finditer(r'<a\b(?P<attrs>[^>]*href="(?P<href>/actor/[^"]+/)"[^>]*)>(?P<label>.*?)</a>', section, re.S):
        attrs = parse_attrs(match.group("attrs"))
        href = attrs.get("href") or match.group("href")
        name = clean_html(match.group("label"))
        if not name or href in seen:
            continue
        seen.add(href)
        rows.append(
            {
                "name": name,
                "character": clean_html(attrs.get("title", "")),
                "url": absolute_letterboxd_url(href) or "",
            }
        )
        if len(rows) >= limit:
            break
    return rows


def parse_film_crew(body: str) -> dict[str, list[dict[str, str]]]:
    crew: dict[str, list[dict[str, str]]] = {}
    pattern = re.compile(
        r"<h3\b[^>]*>(?P<header>.*?)</h3>\s*<div\b[^>]*class=\"[^\"]*\btext-sluglist\b[^\"]*\"[^>]*>(?P<people>.*?)</div>",
        re.S,
    )
    for match in pattern.finditer(body):
        header_html = match.group("header")
        if "crewrole" not in header_html:
            continue
        role_match = re.search(r'<span\b[^>]*class="[^"]*crewrole[^"]*-full[^"]*"[^>]*>(?P<role>.*?)</span>', header_html, re.S)
        role = clean_html(role_match.group("role")) if role_match else clean_html(header_html)
        role = re.sub(r"\s+", " ", role).strip()
        role = re.sub(r"\b(Show|Hide)\b.*$", "", role).strip()
        if not role:
            continue
        people = []
        for person_match in re.finditer(r'<a\b(?P<attrs>[^>]*href="(?P<href>/[^"]+/[^"]+/)"[^>]*)>(?P<label>.*?)</a>', match.group("people"), re.S):
            attrs = parse_attrs(person_match.group("attrs"))
            href = attrs.get("href") or person_match.group("href")
            name = clean_html(person_match.group("label"))
            if not name:
                continue
            people.append({"name": name, "url": absolute_letterboxd_url(href) or ""})
        if people:
            crew[role] = people
    return crew


def fetch_people_search(client: LetterboxdWebClient, query: str, *, limit: int) -> list[dict[str, str]]:
    encoded = urllib.parse.quote(query.strip())
    response = client.get(f"/s/search/{encoded}/")
    if response.status >= 400:
        raise ValueError(f"Letterboxd returned HTTP {response.status} for people search.")
    return parse_people_search_entries(response.text, source_url=response.url)[:limit]


def parse_people_search_entries(body: str, *, source_url: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for match in re.finditer(r'<li\b(?P<attrs>[^>]*\bsearch-result\b[^>]*-contributor[^>]*)>(?P<html>.*?)</li>', body, re.S):
        attrs = parse_attrs(match.group("attrs"))
        chunk = match.group("html")
        link_match = re.search(r'<a\b[^>]*href="(?P<href>/(?:actor|director|writer|producer|composer|cinematography|editor)/[^"]+/)"[^>]*>(?P<label>.*?)</a>', chunk, re.S)
        if not link_match:
            continue
        href = link_match.group("href")
        role_match = re.search(r"-(actor|director|writer|producer|composer|cinematography|editor)\b", attrs.get("class", ""))
        description_match = re.search(r'<p\b[^>]*class="[^"]*\bfilm-metadata\b[^"]*"[^>]*>(?P<text>.*?)</p>', chunk, re.S)
        rows.append(
            {
                "name": clean_html(link_match.group("label")),
                "role": role_match.group(1) if role_match else person_role_from_path(href) or "",
                "description": clean_html(description_match.group("text")) if description_match else "",
                "url": absolute_letterboxd_url(href) or "",
                "source_url": source_url,
            }
        )
    return rows


def fetch_list_search(
    client: LetterboxdWebClient,
    query: str,
    *,
    user: str | None,
    pages: int,
    limit: int,
    min_quality: float,
    min_films: int,
    min_likes: int,
    max_films: int | None,
    require_notes: bool,
    sort: str,
    following_usernames: set[str] | None = None,
    only_following: bool = False,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    user_filter = person_key(user or "")
    following_keys = {person_key(username) for username in (following_usernames or set()) if username}
    encoded = urllib.parse.quote(query.strip())
    fetch_limit = max(limit * 5, limit)
    for page in range(1, pages + 1):
        path = f"/s/search/{encoded}/" if page == 1 else f"/s/search/{encoded}/page/{page}/"
        response = client.get(path)
        if response.status == 404 and page > 1:
            break
        if response.status >= 400:
            raise ValueError(f"Letterboxd returned HTTP {response.status} for list search.")
        page_rows = parse_list_search_entries(response.text, source_url=client.url(path), query=query)
        for row in page_rows:
            if user_filter and user_filter not in {
                person_key(str(row.get("owner") or "")),
                person_key(str(row.get("owner_username") or "")),
            }:
                continue
            apply_following_signal(row, following_keys, query=query)
            if only_following and not row.get("owner_followed"):
                continue
            if not list_passes_quality(
                row,
                min_quality=min_quality,
                min_films=min_films,
                min_likes=min_likes,
                max_films=max_films,
                require_notes=require_notes,
            ):
                continue
            url = str(row.get("url") or "")
            if not url or url in seen:
                continue
            seen.add(url)
            rows.append(row)
            if len(rows) >= fetch_limit:
                return sort_list_rows(rows, sort)[:limit]
        if not page_rows:
            break
    return sort_list_rows(rows, sort)[:limit]


def fetch_following_usernames(client: LetterboxdWebClient, username: str, *, pages: int) -> set[str]:
    usernames: set[str] = set()
    for page in range(1, pages + 1):
        path = f"/{username}/following/" if page == 1 else f"/{username}/following/page/{page}/"
        response = client.get(path)
        if response.status == 404 and page > 1:
            break
        if response.status >= 400:
            break
        page_usernames = parse_following_usernames(response.text)
        if not page_usernames:
            break
        usernames.update(page_usernames)
        if f"/{username}/following/page/{page + 1}/" not in response.text:
            break
    return usernames


def parse_following_usernames(body: str) -> set[str]:
    usernames: set[str] = set()
    for match in re.finditer(
        r'<td\b[^>]*\btable-person\b[^>]*>.*?<a\b[^>]*href="/(?P<username>[^"/]+)/"\s+class="name"',
        body,
        re.S,
    ):
        usernames.add(html.unescape(match.group("username")))
    for match in re.finditer(r'\bdata-username="(?P<username>[^"]+)"', body):
        usernames.add(html.unescape(match.group("username")))
    return usernames


def parse_list_search_entries(body: str, *, source_url: str, query: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for match in re.finditer(r'<article\b(?P<attrs>[^>]*\blist-summary\b[^>]*)>(?P<html>.*?)</article>', body, re.S):
        attrs = parse_attrs(match.group("attrs"))
        chunk = match.group("html")
        title_match = re.search(r'<h2\b[^>]*class="[^"]*\bname\b[^"]*"[^>]*>\s*<a\b[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>', chunk, re.S)
        if not title_match:
            title_match = re.search(r'<a\b[^>]*href="(?P<href>/[^"]+/list/[^"]+/)"[^>]*>(?P<title>.*?)</a>', chunk, re.S)
        if not title_match:
            continue
        href = html.unescape(title_match.group("href"))
        if "/list/" not in href:
            continue
        owner_match = re.search(r'<a\b[^>]*class="[^"]*\bowner\b[^"]*"[^>]*>.*?<strong\b[^>]*class="[^"]*\bdisplayname\b[^"]*"[^>]*>(?P<owner>.*?)</strong>', chunk, re.S)
        film_count_match = re.search(r'<span\b[^>]*class="[^"]*\bvalue\b[^"]*"[^>]*>\s*(?P<count>[\d,]+)&nbsp;films?\s*</span>', chunk, re.S)
        likes_match = re.search(r'/likes/.*?<span\b[^>]*class="[^"]*\blabel\b[^"]*"[^>]*>(?P<likes>[\d,]+)</span>', chunk, re.S)
        comments_match = re.search(r'#comments.*?<span\b[^>]*class="[^"]*\blabel\b[^"]*"[^>]*>(?P<comments>[\d,]+)</span>', chunk, re.S)
        notes_match = re.search(r'<div\b[^>]*class="[^"]*\bnotes\b[^"]*"[^>]*>(?P<notes>.*?)</div>', chunk, re.S)
        preview_rows = parse_poster_entries(chunk, kind="film", source_url=source_url)[:5]
        list_url = absolute_letterboxd_url(href) or ""
        row = {
            "name": clean_html(title_match.group("title")),
            "owner": clean_html(owner_match.group("owner")) if owner_match else attrs.get("data-person", ""),
            "owner_username": attrs.get("data-person", ""),
            "films": parse_count(film_count_match.group("count")) if film_count_match else None,
            "likes": parse_count(likes_match.group("likes")) if likes_match else None,
            "comments": parse_count(comments_match.group("comments")) if comments_match else None,
            "url": list_url,
            "detail_url": detail_list_url(list_url),
            "notes": clean_html(notes_match.group("notes")) if notes_match else "",
            "preview_films": [title_with_year(row.get("name"), row.get("year")) for row in preview_rows],
            "owner_followed": False,
            "_provenance": {
                "source": "live",
                "fetched_at": now_iso(),
                "source_url": source_url,
            },
            "source": "live",
        }
        score, reasons, flags = score_list_quality(row, query=query)
        row["quality_score"] = score
        row["quality_reasons"] = reasons
        row["quality_flags"] = flags
        rows.append(row)
    return rows


def apply_following_signal(row: dict[str, Any], following_keys: set[str], *, query: str) -> None:
    followed = False
    if following_keys:
        followed = person_key(str(row.get("owner_username") or "")) in following_keys
        if not followed:
            followed = person_key(str(row.get("owner") or "")) in following_keys
    row["owner_followed"] = followed
    score, reasons, flags = score_list_quality(row, query=query)
    row["quality_score"] = score
    row["quality_reasons"] = reasons
    row["quality_flags"] = flags


def list_passes_quality(
    row: dict[str, Any],
    *,
    min_quality: float,
    min_films: int,
    min_likes: int,
    max_films: int | None,
    require_notes: bool,
) -> bool:
    films = int(row.get("films") or 0)
    likes = int(row.get("likes") or 0)
    if films < min_films:
        return False
    if max_films is not None and films > max_films:
        return False
    if likes < min_likes and not row.get("owner_followed"):
        return False
    if require_notes and not row.get("notes"):
        return False
    return float(row.get("quality_score") or 0) >= min_quality


def sort_list_rows(rows: list[dict[str, Any]], sort: str) -> list[dict[str, Any]]:
    if sort == "likes":
        return sorted(
            rows,
            key=lambda row: (bool(row.get("owner_followed")), int(row.get("likes") or 0), float(row.get("quality_score") or 0)),
            reverse=True,
        )
    if sort == "films":
        return sorted(
            rows,
            key=lambda row: (bool(row.get("owner_followed")), int(row.get("films") or 0), float(row.get("quality_score") or 0)),
            reverse=True,
        )
    if sort == "comments":
        return sorted(
            rows,
            key=lambda row: (
                bool(row.get("owner_followed")),
                int(row.get("comments") or 0),
                float(row.get("quality_score") or 0),
            ),
            reverse=True,
        )
    if sort == "relevance":
        return rows
    return sorted(
        rows,
        key=lambda row: (bool(row.get("owner_followed")), float(row.get("quality_score") or 0), int(row.get("likes") or 0)),
        reverse=True,
    )


def score_list_quality(row: dict[str, Any], *, query: str) -> tuple[float, list[str], list[str]]:
    films = int(row.get("films") or 0)
    likes = int(row.get("likes") or 0)
    comments = int(row.get("comments") or 0)
    notes = str(row.get("notes") or "")
    preview_count = len(row.get("preview_films") or [])
    title = str(row.get("name") or "")

    score = 0.0
    reasons: list[str] = []
    flags: list[str] = []

    if films >= 10:
        score += min(20, math.log10(films + 1) * 10)
        reasons.append(f"{films} films")
    elif films:
        score += films
        flags.append("small list")
    else:
        flags.append("unknown film count")

    if likes:
        score += min(30, math.log10(likes + 1) * 12)
        reasons.append(f"{likes} likes")
    else:
        flags.append("no likes")

    if comments:
        score += min(10, math.log10(comments + 1) * 6)
        reasons.append(f"{comments} comments")

    if notes:
        score += min(10, 3 + len(notes) / 80)
        reasons.append("has notes")
    else:
        flags.append("no notes")

    if preview_count >= 3:
        score += 5
        reasons.append("preview films available")

    if row.get("owner_username"):
        score += 2

    if row.get("owner_followed"):
        score += 25
        reasons.append("owner is followed")

    if query_title_overlap(title, query) >= 0.6:
        score += 8
        reasons.append("title matches query")

    lowered = title.casefold()
    if any(word in lowered for word in ("copy", "clone", "duplicate")):
        score -= 10
        flags.append("possible copy")
    if films > 1000:
        score -= 8
        flags.append("very broad list")

    return round(max(0.0, score), 2), reasons, flags


def query_title_overlap(title: str, query: str) -> float:
    query_words = significant_words(query)
    if not query_words:
        return 0.0
    title_words = significant_words(title)
    if not title_words:
        return 0.0
    return len(query_words & title_words) / len(query_words)


def significant_words(value: str) -> set[str]:
    stop = {"a", "an", "and", "the", "of", "to", "in", "on", "for", "with", "list"}
    return {word for word in re.findall(r"[a-z0-9]+", value.casefold()) if len(word) > 2 and word not in stop}


def detail_list_url(url: str) -> str:
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.rstrip("/")
    if path.endswith("/detail"):
        detail_path = path + "/"
    else:
        detail_path = path + "/detail/"
    if parsed.scheme:
        return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, detail_path, "", "", ""))
    return absolute_letterboxd_url(detail_path) or ""


def parse_count(value: str | None) -> int | None:
    if not value:
        return None
    digits = re.sub(r"[^\d]", "", value)
    return int(digits) if digits else None


def fetch_person_filmography(
    client: LetterboxdWebClient,
    value: str,
    *,
    role: str,
    pages: int,
    limit: int,
    hydrate: bool,
    filters: LetterboxdFilters | None = None,
) -> list[dict[str, Any]]:
    path = person_path(value, role=role)
    filters = filters or LetterboxdFilters()
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str | None, int | None, str | None]] = set()
    for page in range(1, pages + 1):
        page_path = filtered_path(path, filters, page, global_browser=False)
        response = client.get(page_path)
        if response.status == 404 and page > 1:
            break
        if response.status >= 400:
            raise ValueError(f"Letterboxd returned HTTP {response.status} for {page_path}.")
        parsed = parse_poster_entries(response.text, kind="film", source_url=client.url(page_path))
        if not parsed:
            break
        for row in parsed:
            row = add_person_context(row, person_path=path, role=person_role_from_path(path) or role)
            key = (row.get("name"), row.get("year"), row.get("url"))
            if key in seen:
                continue
            seen.add(key)
            rows.append(hydrate_search_row(client, row) if hydrate else row)
            if len(rows) >= limit:
                return rows
    return rows[:limit]


def add_person_context(row: dict[str, Any], *, person_path: str, role: str) -> dict[str, Any]:
    raw = json.loads(row["raw_json"])
    raw["person_path"] = person_path
    raw["person_role"] = role
    row = dict(row)
    row["review"] = f"{role.title()} credit"
    row["raw_json"] = json.dumps(raw, ensure_ascii=False, sort_keys=True)
    row["row_hash"] = row_hash(row["raw_json"])
    row["search_text"] = build_search_text(row)
    poster_url = poster_url_from_attrs(raw)
    if poster_url:
        row["_poster_url"] = poster_url
    return row


def person_path(value: str, *, role: str) -> str:
    text = value.strip()
    parsed = urllib.parse.urlparse(text)
    path = parsed.path if parsed.scheme else text
    match = re.search(r"/?(actor|director|writer|producer|composer|cinematography|editor)/([^/]+)/?", path)
    if match:
        return f"/{match.group(1)}/{match.group(2)}/"
    if re.fullmatch(r"[a-z0-9][a-z0-9-]*", text):
        return f"/{role}/{text}/"
    return f"/{role}/{slugify_person_name(text)}/"


def person_role_from_path(path: str) -> str | None:
    match = re.search(r"/(actor|director|writer|producer|composer|cinematography|editor)/", path)
    return match.group(1) if match else None


def slugify_person_name(value: str) -> str:
    text = value.strip().casefold()
    text = re.sub(r"['’]", "", text)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    if not text:
        raise ValueError("Provide a person name or Letterboxd contributor path.")
    return text


def fetch_filtered_films(
    client: LetterboxdWebClient,
    *,
    base: str,
    filters: LetterboxdFilters,
    pages: int,
    limit: int,
    hydrate: bool,
    query: str | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str | None, int | None, str | None]] = set()
    max_rows = max(1, limit)
    global_browser = is_global_films_base(base)
    query_text = (query or "").strip().casefold()

    for page in range(1, max(1, pages) + 1):
        path = filtered_path(base, filters, page, global_browser=global_browser)
        response = client.get(path)
        if response.status == 404 and page > 1:
            break
        if response.status >= 400:
            raise ValueError(f"Letterboxd returned HTTP {response.status} for {path}.")
        page_rows = parse_poster_entries(response.text, kind="film", source_url=client.url(path))
        if not page_rows:
            break
        for row in page_rows:
            if query_text and query_text not in str(row.get("name") or "").casefold():
                continue
            row = add_filter_context(row, filters=filters, base=base)
            key = (row.get("name"), row.get("year"), row.get("url"))
            if key in seen:
                continue
            seen.add(key)
            rows.append(hydrate_search_row(client, row) if hydrate else row)
            if len(rows) >= max_rows:
                return rows
    return rows[:max_rows]


def add_filter_context(row: dict[str, Any], *, filters: LetterboxdFilters, base: str) -> dict[str, Any]:
    raw = json.loads(row["raw_json"])
    raw["filter_base"] = base
    raw["filters"] = {
        "year": filters.year,
        "decade": filters.decade,
        "genres": list(filters.genres),
        "exclude_genres": list(filters.exclude_genres),
        "raw_segments": list(filters.raw_segments),
        "sort": filters.sort,
    }
    row = dict(row)
    poster_url = poster_url_from_attrs(raw)
    if poster_url:
        row["_poster_url"] = poster_url
    row["raw_json"] = json.dumps(raw, ensure_ascii=False, sort_keys=True)
    row["row_hash"] = row_hash(row["raw_json"])
    row["search_text"] = build_search_text(row)
    return row


def recommend_films(
    client: LetterboxdWebClient,
    *,
    base: str,
    filters: LetterboxdFilters,
    username: str | None,
    query: str | None,
    pages: int,
    pool_size: int,
    limit: int,
    include_watched: bool,
    watched_pages: int,
    bias_people: list[str],
    taste_from_ratings: bool,
    taste_films: int,
    taste_pages: int,
    cast_limit: int,
    detail_limit: int,
    request_delay: float,
) -> list[dict[str, Any]]:
    candidates = fetch_filtered_films(
        client,
        base=base,
        filters=filters,
        pages=pages,
        limit=max(limit, pool_size),
        hydrate=False,
        query=query,
    )
    watched_slugs: set[str] = set()
    watched_exclusion = {
        "source": "disabled",
        "reason": "include_watched was requested" if include_watched else "no signed-in username detected",
        "username": username,
    }
    if username and not include_watched:
        watched_slugs = fetch_watched_slugs(
            client,
            username=username,
            filters=filters,
            pages=max(1, watched_pages),
        )
        watched_exclusion = {
            "source": "live",
            "username": username,
            "fetched_at": now_iso(),
            "pages": max(1, watched_pages),
            "matched_count": len(watched_slugs),
        }

    manual_bias = [name for value in bias_people for name in split_people_arg(value)]
    taste_bias = derive_taste_people(
        client,
        username=username,
        enabled=bool(taste_from_ratings and username),
        taste_films=max(0, taste_films),
        taste_pages=max(1, taste_pages),
        cast_limit=max(1, cast_limit),
        request_delay=max(0.0, request_delay),
    )
    taste_source = {
        "source": "live",
        "username": username,
        "films_inspected": max(0, taste_films),
        "pages": max(1, taste_pages),
    } if taste_from_ratings and username and taste_films > 0 else {
        "source": "disabled",
        "reason": "taste_from_ratings disabled, no username, or taste_films is 0",
        "username": username,
    }
    bias_scores = merge_bias_scores(manual_bias, taste_bias)

    scored = []
    detail_fetches = 0
    max_detail_fetches = max(0, detail_limit)
    for index, row in enumerate(candidates):
        slug = row_slug(row)
        if slug and slug in watched_slugs:
            continue
        detail = {}
        if slug and detail_fetches < max_detail_fetches:
            sleep_between_requests(request_delay)
            detail = fetch_film_detail(client, slug=slug, cast_limit=max(1, cast_limit))
            detail_fetches += 1
        scored.append(
            score_recommendation(
                row,
                detail,
                bias_scores=bias_scores,
                index=index,
                watched_exclusion=watched_exclusion,
                taste_source=taste_source,
            )
        )
        if len(scored) >= max(limit * 3, limit):
            # Score a little beyond the limit so bias can reorder without turning one command into a crawl.
            break

    scored.sort(key=lambda item: (-item["score"], item["rank"]))
    return scored[: max(1, limit)]


def fetch_watched_slugs(
    client: LetterboxdWebClient,
    *,
    username: str,
    filters: LetterboxdFilters,
    pages: int,
) -> set[str]:
    watched = fetch_live_collection(
        client,
        username=username,
        route="films",
        kind="watched",
        pages=pages,
        filters=filters,
    )
    return {slug for row in watched if (slug := row_slug(row))}


def derive_taste_people(
    client: LetterboxdWebClient,
    *,
    username: str | None,
    enabled: bool,
    taste_films: int,
    taste_pages: int,
    cast_limit: int,
    request_delay: float,
) -> dict[str, float]:
    if not enabled or not username or taste_films <= 0:
        return {}
    rows = fetch_live_collection(
        client,
        username=username,
        route="films/by/entry-rating",
        kind="rating",
        pages=taste_pages,
        filters=LetterboxdFilters(),
    )[:taste_films]
    scores: dict[str, float] = {}
    for row in rows:
        slug = row_slug(row)
        if not slug:
            continue
        sleep_between_requests(request_delay)
        detail = fetch_film_detail(client, slug=slug, cast_limit=cast_limit)
        rating = float(row.get("rating") or 5)
        for name in detail.get("directors") or []:
            add_bias_score(scores, str(name), 2.0 * rating)
        for cast_row in detail.get("cast") or []:
            add_bias_score(scores, str(cast_row.get("name") or ""), 0.5 * rating)
    return scores


def sleep_between_requests(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


def merge_bias_scores(manual_people: list[str], derived_scores: dict[str, float]) -> dict[str, float]:
    scores = dict(derived_scores)
    for name in manual_people:
        add_bias_score(scores, name, 10.0)
    return scores


def add_bias_score(scores: dict[str, float], name: str, amount: float) -> None:
    key = person_key(name)
    if not key:
        return
    scores[key] = scores.get(key, 0.0) + amount


def score_recommendation(
    row: dict[str, Any],
    detail: dict[str, Any],
    *,
    bias_scores: dict[str, float],
    index: int,
    watched_exclusion: dict[str, Any],
    taste_source: dict[str, Any],
) -> dict[str, Any]:
    directors = [str(name) for name in detail.get("directors") or [] if name]
    cast = [str(item.get("name")) for item in detail.get("cast") or [] if item.get("name")]
    matched_directors = [name for name in directors if person_key(name) in bias_scores]
    matched_cast = [name for name in cast if person_key(name) in bias_scores]

    score = max(0.0, 20.0 - index * 0.1)
    reasons = ["high Letterboxd filter rank"]
    for name in matched_directors:
        boost = 3.0 + bias_scores[person_key(name)] / 5
        score += boost
        reasons.append(f"director match: {name}")
    for name in matched_cast[:5]:
        boost = 1.0 + bias_scores[person_key(name)] / 20
        score += boost
        reasons.append(f"cast match: {name}")

    poster_urls = detail.get("poster_urls") or {}
    return {
        "name": row.get("name"),
        "year": row.get("year"),
        "url": row.get("url"),
        "poster_url": row.get("_poster_url") or first_poster_url(poster_urls),
        "score": round(score, 2),
        "rank": index + 1,
        "reasons": reasons,
        "directors": directors,
        "matched_directors": matched_directors,
        "matched_cast": matched_cast,
        "cast": cast[:8],
        "source_url": row.get("source_file"),
        "candidate_source": "live",
        "candidate_fetched_at": (row.get("_provenance") or {}).get("fetched_at") if isinstance(row.get("_provenance"), dict) else row.get("imported_at"),
        "watched_exclusion": watched_exclusion,
        "taste_source": taste_source,
    }


def split_people_arg(value: str) -> list[str]:
    return [part.strip() for part in str(value).split(",") if part.strip()]


def person_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def row_slug(row: dict[str, Any]) -> str | None:
    url = str(row.get("url") or row.get("letterboxd_uri") or "")
    try:
        return film_slug(url)
    except ValueError:
        return None


def fetch_live_search(
    client: LetterboxdWebClient,
    *,
    query: str,
    search_type: str,
    pages: int,
    limit: int,
    hydrate: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str | None, int | None, str | None]] = set()
    max_pages = max(1, pages)
    max_rows = max(1, limit)

    for page in range(1, max_pages + 1):
        path = live_search_path(query, search_type, page)
        response = client.get(path)
        if response.status == 404 and page > 1:
            break
        if response.status >= 400:
            raise ValueError(f"Letterboxd returned HTTP {response.status} for {path}.")

        page_rows = parse_search_entries(response.text, source_url=client.url(path))
        for row in page_rows:
            key = (row.get("name"), row.get("year"), row.get("url"))
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
            if len(rows) >= max_rows:
                break
        if len(rows) >= max_rows or not page_rows:
            break

    if hydrate:
        rows = [hydrate_search_row(client, row) for row in rows]
    return rows[:max_rows]


def live_search_path(query: str, search_type: str, page: int) -> str:
    encoded = urllib.parse.quote(query.strip())
    if search_type == "films":
        if page > 1:
            return f"/s/search/{encoded}/page/{page}/"
        return f"/s/search/{encoded}/"
    prefix = "/search/"
    if page <= 1:
        return f"{prefix}{encoded}/"
    return f"{prefix}{encoded}/page/{page}/"


def parse_search_entries(body: str, *, source_url: str) -> list[dict[str, Any]]:
    rows = parse_poster_entries(body, kind="film", source_url=source_url)
    if rows:
        return rows

    fallback_rows = []
    for match in re.finditer(r'<a\b(?P<attrs>[^>]*href="(?P<href>/film/[^"]+/)"[^>]*)>(?P<label>.*?)</a>', body, re.S):
        attrs = parse_attrs(match.group("attrs"))
        label = clean_html(match.group("label"))
        title, year = split_title_year(label)
        href = attrs.get("href") or match.group("href")
        fallback_rows.append(
            live_row(
                kind="film",
                name=title or film_slug(href).replace("-", " ").title(),
                year=year,
                rating=None,
                date=None,
                review=None,
                tags=None,
                url=absolute_letterboxd_url(href),
                source_url=source_url,
                raw={"href": href, "label": label, "attrs": attrs},
            )
        )
    return dedupe_live_rows(fallback_rows)


def hydrate_search_row(client: LetterboxdWebClient, row: dict[str, Any]) -> dict[str, Any]:
    url = str(row.get("url") or "")
    if not url:
        return row
    try:
        response = client.get(film_json_path(url))
        if response.status >= 400:
            return row
        film = parse_json_response(response)
    except ValueError:
        return row

    directors = film.get("directors") or []
    director_text = ", ".join(
        director.get("name", "")
        for director in directors
        if isinstance(director, dict) and director.get("name")
    )
    raw = json.loads(row["raw_json"])
    raw["film_json"] = film
    row = dict(row)
    row.update(
        {
            "name": film.get("name") or row.get("name"),
            "year": film.get("releaseYear") or row.get("year"),
            "letterboxd_uri": absolute_letterboxd_url(film.get("url")) or row.get("letterboxd_uri"),
            "url": absolute_letterboxd_url(film.get("url")) or row.get("url"),
            "review": f"Directed by {director_text}" if director_text else row.get("review"),
            "raw_json": json.dumps(raw, ensure_ascii=False, sort_keys=True),
        }
    )
    row["row_hash"] = row_hash(row["raw_json"])
    row["search_text"] = build_search_text(row)
    row = hydrate_member_activity(client, row)
    return row


def hydrate_member_activity(client: LetterboxdWebClient, row: dict[str, Any]) -> dict[str, Any]:
    slug = film_slug(str(row.get("url") or ""))
    username = username_from_cookie(client.cookie)
    if not slug or not username:
        return row

    sidebar = client.get(f"/csi/film/{slug}/sidebar-user-actions/?esiAllowUser=true")
    if sidebar.status >= 400:
        return row

    raw = json.loads(row["raw_json"])
    raw["member_sidebar"] = truncate(clean_html(sidebar.text), 2000)

    liked = 'data-is-liked="true"' in sidebar.text
    member_paths = member_activity_paths(sidebar.text, username=username, slug=slug)

    activity_data: dict[str, Any] = {}
    for path in member_paths:
        response = client.get(path)
        if response.status >= 400:
            continue
        if "/diary/" in path:
            activity_data = parse_member_diary_page(response.text)
        else:
            activity_data = parse_member_review_page(response.text)
        if activity_data:
            raw["member_activity_path"] = path
            raw["member_activity"] = activity_data
            break

    row = dict(row)
    if liked:
        row["like"] = 1
    if activity_data.get("rating") is not None:
        row["rating"] = activity_data["rating"]
    if activity_data.get("date"):
        row["date"] = activity_data["date"]
        row["watched_date"] = activity_data["date"]
    if activity_data.get("review"):
        row["review"] = activity_data["review"]
    row["raw_json"] = json.dumps(raw, ensure_ascii=False, sort_keys=True)
    row["row_hash"] = row_hash(row["raw_json"])
    row["search_text"] = build_search_text(row)
    return row


def member_activity_paths(sidebar_html: str, *, username: str, slug: str) -> list[str]:
    paths = []
    for match in re.finditer(r'href="([^"]+)"', sidebar_html):
        path = html.unescape(match.group(1))
        if f"/{username}/film/{slug}/" not in path:
            continue
        if any(part in path for part in ("/diary/", "/reviews/", f"/{slug}/1/", f"/{slug}/")):
            paths.append(path)
    paths.extend(
        [
            f"/{username}/film/{slug}/reviews/",
            f"/{username}/film/{slug}/diary/",
            f"/{username}/film/{slug}/",
        ]
    )
    deduped = []
    for path in paths:
        if path not in deduped:
            deduped.append(path)
    return deduped


def parse_member_diary_page(body: str) -> dict[str, Any]:
    rows = re.findall(r"<tr\b[^>]*\bdiary-entry-row\b[^>]*>.*?</tr>", body, re.S)
    if not rows:
        return {}
    return parse_member_diary_row(rows[0])


def parse_member_diary_row(row_html: str) -> dict[str, Any]:
    rating_match = re.search(r'type="range"[^>]*\bvalue="(\d+)"', row_html)
    date_match = re.search(r'href="[^"]*/for/(\d{4})/(\d{2})/"[^>]*>\s*([A-Za-z]+)\s*</a>.*?class="daydate"[^>]*>\s*(\d{1,2})\s*</a>', row_html, re.S)
    review_text = extract_review_text(row_html)
    result: dict[str, Any] = {}
    if rating_match:
        result["rating"] = int(rating_match.group(1)) / 2
    if date_match:
        result["date"] = f"{date_match.group(1)}-{date_match.group(2)}-{int(date_match.group(4)):02d}"
    if review_text:
        result["review"] = review_text
    return result


def parse_member_review_page(body: str) -> dict[str, Any]:
    rows = parse_viewing_entries(body, kind="review", source_url="")
    if not rows:
        return {}
    row = rows[0]
    return {
        "rating": row.get("rating"),
        "date": row.get("date"),
        "review": row.get("review"),
    }


def fetch_live_collection(
    client: LetterboxdWebClient,
    *,
    username: str,
    route: str,
    kind: str,
    pages: int,
    filters: LetterboxdFilters | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    max_pages = max(1, pages)
    filters = filters or LetterboxdFilters()

    for page in range(1, max_pages + 1):
        path = live_page_path(username, route, page, filters=filters)
        response = client.get(path)
        if response.status == 404:
            break
        if response.status >= 400:
            raise ValueError(f"Letterboxd returned HTTP {response.status} for {path}.")

        parsed = parse_live_entries(response.text, kind=kind, source_url=client.url(path))
        new_rows = []
        for row in parsed:
            if row["row_hash"] in seen_hashes:
                continue
            seen_hashes.add(row["row_hash"])
            new_rows.append(row)
        if not new_rows:
            break
        rows.extend(new_rows)
    return rows


def live_page_path(username: str, route: str, page: int, *, filters: LetterboxdFilters) -> str:
    clean_user = username.strip().strip("/")
    clean_route = route.strip("/")
    base = f"/{clean_user}/{clean_route}/"
    segments = letterboxd_filter_segments(filters, include_sort=False)
    if segments:
        base += "/".join(segments).strip("/") + "/"
    if page <= 1:
        return base
    return f"{base}page/{page}/"


def parse_live_entries(body: str, *, kind: str, source_url: str) -> list[dict[str, Any]]:
    if kind in {"diary", "review"}:
        rows = parse_viewing_entries(body, kind=kind, source_url=source_url)
        if rows:
            return rows
    return parse_poster_entries(body, kind=kind, source_url=source_url)


def parse_poster_entries(body: str, *, kind: str, source_url: str) -> list[dict[str, Any]]:
    rows = []
    for match in re.finditer(r"<li\b(?P<attrs>[^>]*\bfilm-list-entry\b[^>]*)>", body, re.S):
        attrs = parse_attrs(match.group("attrs"))
        name = html.unescape(attrs.get("data-film-name", "")).strip()
        if not name:
            continue
        owner_rating = parse_rating10(attrs.get("data-film-owner-rating"))
        rows.append(
            live_row(
                kind=kind,
                name=name,
                year=parse_int(attrs.get("data-film-year")),
                rating=owner_rating,
                date=parse_live_date_near(body, str(match.start())),
                review=None,
                tags=None,
                url=None,
                source_url=source_url,
                raw=attrs,
            )
        )

    for attrs in iter_tags_with_class(body, "div", "react-component"):
        if attrs.get("data-component-class") != "LazyPoster":
            continue
        name = html.unescape(attrs.get("data-item-name", "")).strip()
        slug = attrs.get("data-item-slug", "").strip()
        link = attrs.get("data-item-link", "").strip()
        if not name and not slug:
            continue

        title, year = split_title_year(name)
        rating = parse_rating(attrs.get("data-owner-rating")) or parse_rating_from_attrs(attrs)
        row = live_row(
            kind=kind,
            name=title or slug.replace("-", " ").title(),
            year=year,
            rating=rating,
            date=parse_live_date_near(body, attrs.get("_match_start", "")),
            review=None,
            tags=None,
            url=absolute_letterboxd_url(link or f"/film/{slug}/"),
            source_url=source_url,
            raw=attrs,
        )
        rows.append(row)
    return dedupe_live_rows(rows)


def parse_viewing_entries(body: str, *, kind: str, source_url: str) -> list[dict[str, Any]]:
    rows = []
    for match in re.finditer(r"<article\b(?P<attrs>[^>]*\bproduction-viewing\b[^>]*)>(?P<html>.*?)</article>", body, re.S):
        attrs = parse_attrs(match.group("attrs"))
        chunk = match.group("html")
        link_match = re.search(r'href="([^"]*/film/[^"]+)"', chunk)
        slug = film_slug(link_match.group(1)) if link_match else ""
        title_match = re.search(r'class="[^"]*\bheadline-[^"]*"[^>]*>\s*<a[^>]*>(.*?)</a>', chunk, re.S)
        title = clean_html(title_match.group(1)) if title_match else slug.replace("-", " ").title()
        year_match = re.search(r"<small[^>]*>\s*(\d{4})\s*</small>", chunk)
        date_match = re.search(r"<time[^>]*datetime=\"([^\"]+)\"", chunk)
        rating = parse_rating_from_text(clean_html(chunk))
        review = extract_review_text(chunk)
        raw = {"attrs": attrs, "html": truncate(clean_html(chunk), 1000)}
        rows.append(
            live_row(
                kind=kind,
                name=title,
                year=int(year_match.group(1)) if year_match else None,
                rating=rating,
                date=normalize_date(date_match.group(1)) if date_match else None,
                review=review,
                tags=None,
                url=absolute_letterboxd_url(link_match.group(1)) if link_match else None,
                source_url=source_url,
                raw=raw,
            )
        )
    return dedupe_live_rows(rows)


def iter_tags_with_class(body: str, tag: str, class_name: str) -> Iterable[dict[str, str]]:
    pattern = re.compile(rf"<{tag}\b(?P<attrs>[^>]*\bclass=\"[^\"]*\b{re.escape(class_name)}\b[^\"]*\"[^>]*)>", re.S)
    for match in pattern.finditer(body):
        attrs = parse_attrs(match.group("attrs"))
        attrs["_match_start"] = str(match.start())
        yield attrs


def iter_tags(body: str, tag: str) -> Iterable[dict[str, str]]:
    pattern = re.compile(rf"<{tag}\b(?P<attrs>[^>]*)>", re.S)
    for match in pattern.finditer(body):
        attrs = parse_attrs(match.group("attrs"))
        attrs["_match_start"] = str(match.start())
        yield attrs


def parse_attrs(attr_text: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for match in re.finditer(r"([:\w-]+)\s*=\s*(['\"])(.*?)\2", attr_text, re.S):
        attrs[match.group(1)] = html.unescape(match.group(3))
    return attrs


def split_title_year(value: str) -> tuple[str | None, int | None]:
    text = clean_html(value)
    match = re.match(r"(.+?)\s*\((\d{4})\)\s*$", text)
    if match:
        return match.group(1).strip(), int(match.group(2))
    return text or None, None


def parse_rating_from_attrs(attrs: dict[str, str]) -> float | None:
    for key, value in attrs.items():
        if "rating" in key.casefold():
            rating = parse_rating10(value) if "owner" in key.casefold() else parse_rating(value)
            if rating is not None:
                return rating
    return None


def parse_live_date_near(body: str, start_text: str) -> str | None:
    if not start_text.isdigit():
        return None
    start = int(start_text)
    chunk = body[max(0, start - 800) : min(len(body), start + 800)]
    match = re.search(r"<time[^>]*datetime=\"([^\"]+)\"", chunk)
    return normalize_date(match.group(1)) if match else None


def extract_review_text(chunk: str) -> str | None:
    match = re.search(r'<div[^>]*class="[^"]*\bjs-review-body\b[^"]*"[^>]*>(.*?)</div>', chunk, re.S)
    if not match:
        match = re.search(r'<p[^>]*class="[^"]*\bbody-text\b[^"]*"[^>]*>(.*?)</p>', chunk, re.S)
    if not match:
        return None
    text = clean_html(match.group(1))
    return text or None


def live_row(
    *,
    kind: str,
    name: str | None,
    year: int | None,
    rating: float | None,
    date: str | None,
    review: str | None,
    tags: str | None,
    url: str | None,
    source_url: str,
    raw: dict[str, Any],
) -> dict[str, Any]:
    raw_json = json.dumps(raw, ensure_ascii=False, sort_keys=True)
    fetched_at = now_iso()
    data = {
        "kind": kind,
        "name": name,
        "year": year,
        "letterboxd_uri": url,
        "rating": rating,
        "date": date,
        "watched_date": date if kind == "diary" else None,
        "rewatch": None,
        "tags": tags,
        "review": review,
        "like": None,
        "url": url,
        "source_file": source_url,
        "source_path": source_url,
        "row_hash": row_hash(raw_json),
        "raw_json": raw_json,
        "search_text": "",
        "imported_at": fetched_at,
        "_provenance": {
            "source": "live",
            "fetched_at": fetched_at,
            "source_url": source_url,
        },
    }
    data["search_text"] = build_search_text(data)
    return data


def dedupe_live_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for row in rows:
        key = (row.get("kind"), row.get("url"), row.get("date"), row.get("rating"), row.get("review"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def dedupe_display_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for row in rows:
        key = (
            row.get("kind"),
            row.get("url") or row.get("letterboxd_uri"),
            row.get("name"),
            row.get("year"),
            row.get("date") or row.get("watched_date"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def absolute_letterboxd_url(value: str | None) -> str | None:
    if not value:
        return None
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return f"{LETTERBOXD_BASE_URL}/{value.lstrip('/')}"


def absolute_url(value: str | None) -> str | None:
    if not value:
        return None
    if value.startswith("//"):
        return f"https:{value}"
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return absolute_letterboxd_url(value)


def print_rows(rows: Iterable[sqlite3.Row], output_format: str) -> int:
    materialized = [public_display_row(dict(row)) for row in rows]
    columns = ["source", "kind", "name", "year", "rating", "date", "watched_date", "tags", "review", "url"]

    if output_format == "json":
        print(json.dumps(materialized, indent=2, ensure_ascii=False))
        return 0

    if output_format == "csv":
        writer = csv.DictWriter(sys.stdout, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(materialized)
        return 0

    table_rows = []
    for row in materialized:
        provenance = row.get("_provenance") if isinstance(row.get("_provenance"), dict) else {}
        table_rows.append(
            {
                "source": str(provenance.get("source") or ""),
                "kind": row.get("kind") or "",
                "title": title_with_year(row.get("name"), row.get("year")),
                "rating": format_rating(row.get("rating")) if row.get("rating") is not None else "",
                "date": row.get("watched_date") or row.get("date") or "",
                "tags": truncate(row.get("tags") or "", 24),
                "review": truncate(row.get("review") or "", 60),
            }
        )
    print_table(table_rows, ["source", "kind", "title", "rating", "date", "tags", "review"])
    return 0


def print_generic_rows(rows: Iterable[dict[str, Any]], output_format: str, columns: list[str]) -> int:
    materialized = [dict(row) for row in rows]
    if output_format == "json":
        print(json.dumps(materialized, indent=2, ensure_ascii=False))
        return 0
    if output_format == "csv":
        writer = csv.DictWriter(sys.stdout, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(materialized)
        return 0
    print_table(
        [
            {column: truncate("" if row.get(column) is None else str(row.get(column)), 72) for column in columns}
            for row in materialized
        ],
        columns,
    )
    return 0


def print_film_detail(detail: dict[str, Any]) -> int:
    poster_urls = detail.get("poster_urls") or {}
    cast = detail.get("cast") or []
    crew = detail.get("crew") or {}
    fields = [
        {"field": "title", "value": title_with_year(detail.get("name"), detail.get("year"))},
        {"field": "slug", "value": str(detail.get("slug") or "")},
        {"field": "url", "value": str(detail.get("url") or "")},
        {"field": "directors", "value": ", ".join(detail.get("directors") or [])},
        {"field": "poster", "value": first_poster_url(poster_urls) or ""},
        {"field": "cast", "value": ", ".join(person.get("name", "") for person in cast[:8])},
        {"field": "crew", "value": ", ".join(f"{role}: {len(people)}" for role, people in crew.items())},
        {"field": "watchlist action", "value": str((detail.get("actions") or {}).get("watchlist") or "")},
    ]
    print_table(fields, ["field", "value"])
    return 0


def print_availability(availability: dict[str, Any], output_format: str) -> int:
    services = list(availability.get("services") or [])
    if output_format == "json":
        print(json.dumps(availability, indent=2, ensure_ascii=False))
        return 0

    rows = []
    for service in services:
        options = service.get("options") or []
        labels = [str(option.get("label") or option.get("type") or "") for option in options]
        rows.append(
            {
                "service": str(service.get("service") or ""),
                "locale": str(service.get("locale") or ""),
                "options": ", ".join(label for label in labels if label),
                "url": str(service.get("url") or ""),
            }
        )

    if output_format == "csv":
        writer = csv.DictWriter(sys.stdout, fieldnames=["service", "locale", "options", "url"], extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        return 0

    print_table(rows, ["service", "locale", "options", "url"])
    extras = availability.get("extras") or {}
    if extras.get("justwatch_url"):
        print(f"\nJustWatch: {extras['justwatch_url']}")
    return 0


def print_person_rows(rows: Iterable[dict[str, Any]], output_format: str) -> int:
    materialized = [enrich_person_display_row(dict(row)) for row in rows]
    if output_format == "json":
        print(
            json.dumps(
                [public_display_row(row, extra_fields=("poster_url", "person_role", "person_path")) for row in materialized],
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    if output_format == "csv":
        columns = ["kind", "name", "year", "rating", "date", "url", "poster_url", "person_role"]
        writer = csv.DictWriter(sys.stdout, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(materialized)
        return 0

    table_rows = [
        {
            "source": (row.get("_provenance") or {}).get("source") if isinstance(row.get("_provenance"), dict) else "",
            "title": title_with_year(row.get("name"), row.get("year")),
            "role": row.get("person_role") or "",
            "rating": format_rating(row.get("rating")) if row.get("rating") is not None else "",
            "poster": truncate(row.get("poster_url") or "", 36),
            "url": truncate(row.get("url") or "", 36),
        }
        for row in materialized
    ]
    print_table(table_rows, ["source", "title", "role", "rating", "poster", "url"])
    return 0


def print_recommendations(rows: Iterable[dict[str, Any]], output_format: str) -> int:
    materialized = [dict(row) for row in rows]
    if output_format == "json":
        print(json.dumps(materialized, indent=2, ensure_ascii=False))
        return 0
    if output_format == "csv":
        columns = ["name", "year", "score", "url", "poster_url", "reasons"]
        writer = csv.DictWriter(sys.stdout, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in materialized:
            row = dict(row)
            row["reasons"] = "; ".join(row.get("reasons") or [])
            writer.writerow(row)
        return 0

    table_rows = [
        {
            "source": row.get("candidate_source") or "",
            "title": title_with_year(row.get("name"), row.get("year")),
            "score": str(row.get("score") or ""),
            "why": truncate("; ".join(row.get("reasons") or []), 72),
            "url": truncate(row.get("url") or "", 36),
        }
        for row in materialized
    ]
    print_table(table_rows, ["source", "title", "score", "why", "url"])
    return 0


def enrich_person_display_row(row: dict[str, Any]) -> dict[str, Any]:
    row = ensure_provenance(row)
    raw: dict[str, Any] = {}
    try:
        raw = json.loads(str(row.get("raw_json") or "{}"))
    except json.JSONDecodeError:
        raw = {}
    poster_url = row.pop("_poster_url", None) or poster_url_from_attrs(raw)
    row["poster_url"] = poster_url
    row["person_role"] = raw.get("person_role")
    row["person_path"] = raw.get("person_path")
    return row


def poster_url_from_attrs(attrs: dict[str, Any]) -> str | None:
    direct = str(attrs.get("data-poster-url") or "").strip()
    if direct:
        return absolute_letterboxd_url(direct)

    resolvable = str(attrs.get("data-resolvable-poster-path") or "").strip()
    if not resolvable:
        return None
    if resolvable.startswith("/"):
        return absolute_letterboxd_url(resolvable)
    if resolvable.startswith("{"):
        try:
            payload = json.loads(resolvable)
        except json.JSONDecodeError:
            return None
        base_link = str(payload.get("posteredBaseLink") or "").rstrip("/")
        if base_link:
            return absolute_letterboxd_url(f"{base_link}/image-150/")
    return None


def first_poster_url(poster_urls: dict[str, str]) -> str | None:
    for key in ("image230", "poster_url", "poster", "og_image", "twitter_image", "image150", "image125"):
        if poster_urls.get(key):
            return poster_urls[key]
    return next(iter(poster_urls.values()), None)


def print_table(rows: list[dict[str, str]], columns: list[str]) -> None:
    if not rows:
        print("No rows.")
        return
    widths = {
        column: min(
            max(len(column), *(len(str(row.get(column, ""))) for row in rows)),
            80 if column == "review" else 36,
        )
        for column in columns
    }
    header = "  ".join(column.upper().ljust(widths[column]) for column in columns)
    print(header)
    print("  ".join("-" * widths[column] for column in columns))
    for row in rows:
        print("  ".join(str(row.get(column, ""))[: widths[column]].ljust(widths[column]) for column in columns))


def split_tags(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def clean_html(value: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", value or "", flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def title_with_year(name: str | None, year: int | None) -> str:
    if not name:
        return ""
    return f"{name} ({year})" if year else name


def format_rating(value: Any) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else str(number)


def truncate(value: str, width: int) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    return textwrap.shorten(value, width=width, placeholder="...") if len(value) > width else value
