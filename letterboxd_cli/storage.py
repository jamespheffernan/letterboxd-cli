from __future__ import annotations

import argparse
import sqlite3
import urllib.parse
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
KIND_ALIASES = {
    "diary": "diary",
    "history": "history",
    "watched": "watched",
    "watchlist": "watchlist",
    "ratings": "rating",
    "rating": "rating",
    "reviews": "review",
    "review": "review",
    "likes": "like",
    "like": "like",
    "feed": "feed",
}
ENTRY_COLUMN_MIGRATIONS = {
    "kind": "kind TEXT NOT NULL DEFAULT 'unknown'",
    "name": "name TEXT",
    "year": "year INTEGER",
    "letterboxd_uri": "letterboxd_uri TEXT",
    "rating": "rating REAL",
    "date": "date TEXT",
    "watched_date": "watched_date TEXT",
    "rewatch": "rewatch INTEGER",
    "tags": "tags TEXT",
    "review": "review TEXT",
    "like": "like INTEGER",
    "url": "url TEXT",
    "source_file": "source_file TEXT",
    "source_path": "source_path TEXT",
    "row_hash": "row_hash TEXT NOT NULL DEFAULT ''",
    "raw_json": "raw_json TEXT NOT NULL DEFAULT '{}'",
    "search_text": "search_text TEXT NOT NULL DEFAULT ''",
    "imported_at": "imported_at TEXT NOT NULL DEFAULT ''",
}


def connect(path: Path, *, readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        if not path.exists():
            raise ValueError(f"Database does not exist: {path}")
        db = sqlite3.connect(sqlite_readonly_uri(path), uri=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    return db


def sqlite_readonly_uri(path: Path) -> str:
    return "file:" + urllib.parse.quote(str(path.resolve()), safe="/:") + "?mode=ro"


def ensure_schema(db: sqlite3.Connection) -> None:
    db.executescript(
        """
        PRAGMA journal_mode = WAL;

        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            name TEXT,
            year INTEGER,
            letterboxd_uri TEXT,
            rating REAL,
            date TEXT,
            watched_date TEXT,
            rewatch INTEGER,
            tags TEXT,
            review TEXT,
            like INTEGER,
            url TEXT,
            source_file TEXT,
            source_path TEXT,
            row_hash TEXT NOT NULL,
            raw_json TEXT NOT NULL,
            search_text TEXT NOT NULL,
            imported_at TEXT NOT NULL,
            UNIQUE(kind, source_file, row_hash)
        );

        CREATE TABLE IF NOT EXISTS import_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_path TEXT NOT NULL,
            imported_at TEXT NOT NULL,
            rows_imported INTEGER NOT NULL,
            files_imported INTEGER NOT NULL
        );
        """
    )
    migrate_schema(db)
    db.executescript(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_entries_unique_source
            ON entries(kind, source_file, row_hash);

        CREATE INDEX IF NOT EXISTS idx_entries_kind ON entries(kind);
        CREATE INDEX IF NOT EXISTS idx_entries_name ON entries(name);
        CREATE INDEX IF NOT EXISTS idx_entries_year ON entries(year);
        CREATE INDEX IF NOT EXISTS idx_entries_date ON entries(date);
        CREATE INDEX IF NOT EXISTS idx_entries_rating ON entries(rating);
        CREATE INDEX IF NOT EXISTS idx_entries_search ON entries(search_text);

        PRAGMA user_version = {SCHEMA_VERSION};
        """
    )


def migrate_schema(db: sqlite3.Connection) -> None:
    existing = {row["name"] for row in db.execute("PRAGMA table_info(entries)").fetchall()}
    for column, ddl in ENTRY_COLUMN_MIGRATIONS.items():
        if column not in existing:
            db.execute(f"ALTER TABLE entries ADD COLUMN {ddl}")

    db.execute("UPDATE entries SET imported_at = ? WHERE imported_at IS NULL OR imported_at = ''", (now_iso(),))
    db.execute("UPDATE entries SET raw_json = '{}' WHERE raw_json IS NULL OR raw_json = ''")
    db.execute(
        """
        UPDATE entries
        SET search_text = lower(
            coalesce(kind, '') || ' ' ||
            coalesce(name, '') || ' ' ||
            coalesce(year, '') || ' ' ||
            coalesce(tags, '') || ' ' ||
            coalesce(review, '') || ' ' ||
            coalesce(url, '')
        )
        WHERE search_text IS NULL OR search_text = ''
        """
    )
    db.execute("UPDATE entries SET row_hash = 'migrated:' || id WHERE row_hash IS NULL OR row_hash = ''")


def insert_entry(db: sqlite3.Connection, data: dict[str, Any]) -> None:
    db.execute(
        """
        INSERT OR REPLACE INTO entries(
            kind, name, year, letterboxd_uri, rating, date, watched_date, rewatch,
            tags, review, like, url, source_file, source_path, row_hash, raw_json,
            search_text, imported_at
        )
        VALUES (
            :kind, :name, :year, :letterboxd_uri, :rating, :date, :watched_date,
            :rewatch, :tags, :review, :like, :url, :source_file, :source_path,
            :row_hash, :raw_json, :search_text, :imported_at
        )
        """,
        data,
    )


def select_entries(
    db: sqlite3.Connection,
    args: argparse.Namespace,
    *,
    kind: str | None = None,
    text: str | None = None,
) -> list[sqlite3.Row]:
    clauses: list[str] = []
    params: list[Any] = []

    kind = KIND_ALIASES.get(kind or "", kind)
    if kind == "history":
        clauses.append("kind IN ('diary', 'watched')")
    elif kind == "rating":
        clauses.append("(kind = 'rating' OR rating IS NOT NULL)")
    elif kind == "review":
        clauses.append("(kind = 'review' OR COALESCE(review, '') != '')")
    elif kind:
        clauses.append("kind = ?")
        params.append(kind)

    query_text = text or getattr(args, "query", None)
    if query_text:
        clauses.append("search_text LIKE ?")
        params.append(f"%{query_text.casefold()}%")

    if getattr(args, "year", None) is not None:
        clauses.append("year = ?")
        params.append(args.year)

    if getattr(args, "from_date", None):
        clauses.append("COALESCE(watched_date, date) >= ?")
        params.append(args.from_date)

    if getattr(args, "to_date", None):
        clauses.append("COALESCE(watched_date, date) <= ?")
        params.append(args.to_date)

    if getattr(args, "min_rating", None) is not None:
        clauses.append("rating >= ?")
        params.append(args.min_rating)

    if getattr(args, "max_rating", None) is not None:
        clauses.append("rating <= ?")
        params.append(args.max_rating)

    sort = getattr(args, "sort", "date")
    order_by = {
        "date": "COALESCE(watched_date, date)",
        "rating": "rating",
        "title": "name",
        "year": "year",
        "kind": "kind",
    }[sort]
    direction = "DESC" if getattr(args, "desc", False) else "ASC"
    limit = max(1, int(getattr(args, "limit", 50) or 50))

    sql = "SELECT * FROM entries"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += f" ORDER BY {order_by} {direction}, id {direction} LIMIT ?"
    params.append(limit)
    return db.execute(sql, params).fetchall()


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
