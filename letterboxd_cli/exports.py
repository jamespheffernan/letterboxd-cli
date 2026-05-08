from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from letterboxd_cli.normalization import (
    build_search_text,
    first_value,
    key_for,
    normalize_date,
    now_iso,
    parse_bool,
    parse_int,
    parse_rating,
    parse_rating10,
    row_hash,
)
from letterboxd_cli.storage import KIND_ALIASES


@dataclass(frozen=True)
class CsvSource:
    name: str
    source_path: str
    text: str


def read_csv_sources(path: Path) -> Iterable[CsvSource]:
    resolved = str(path.resolve())
    if path.is_file() and path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as bundle:
            for info in bundle.infolist():
                if info.is_dir() or not info.filename.lower().endswith(".csv"):
                    continue
                with bundle.open(info) as handle:
                    text = decode_csv_bytes(handle.read())
                yield CsvSource(Path(info.filename).name, resolved, text)
        return

    if path.is_file() and path.suffix.lower() == ".csv":
        yield CsvSource(path.name, resolved, decode_csv_bytes(path.read_bytes()))
        return

    if path.is_dir():
        for csv_path in sorted(path.rglob("*.csv")):
            yield CsvSource(csv_path.name, resolved, decode_csv_bytes(csv_path.read_bytes()))
        return

    raise ValueError("Expected a .zip file, .csv file, or folder containing CSV files.")


def decode_csv_bytes(data: bytes) -> str:
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig")
    return data.decode("utf-8")


def normalize_csv_row(row: dict[str, str], source: CsvSource) -> dict[str, Any]:
    keyed = {key_for(k): (v.strip() if isinstance(v, str) else v) for k, v in row.items() if k}
    kind = infer_kind(source.name, keyed)
    name = first_value(keyed, "name", "title", "film", "filmname")
    raw_year = first_value(keyed, "year", "released", "releaseyear")
    rating = parse_rating(first_value(keyed, "rating", "rating10"))
    watched_date = first_value(keyed, "watcheddate", "datewatched")
    row_date = first_value(keyed, "date", "created", "published", "addeddate")
    review = first_value(keyed, "review", "body", "text", "notes", "note")

    if "rating10" in keyed and "rating" not in keyed:
        rating = parse_rating10(keyed.get("rating10"))

    data = {
        "kind": kind,
        "name": name,
        "year": parse_int(raw_year),
        "letterboxd_uri": first_value(keyed, "letterboxduri", "url", "uri"),
        "rating": rating,
        "date": normalize_date(row_date or watched_date),
        "watched_date": normalize_date(watched_date),
        "rewatch": parse_bool(first_value(keyed, "rewatch", "rewatched")),
        "tags": first_value(keyed, "tags", "tag"),
        "review": review,
        "like": parse_bool(first_value(keyed, "like", "liked")),
        "url": first_value(keyed, "letterboxduri", "url", "uri"),
        "source_file": source.name,
        "source_path": source.source_path,
        "raw_json": json.dumps(row, ensure_ascii=False, sort_keys=True),
    }
    data["row_hash"] = row_hash(data["raw_json"])
    data["search_text"] = build_search_text(data)
    data["imported_at"] = now_iso()
    data["_provenance"] = {
        "source": "export",
        "imported_at": data["imported_at"],
        "source_file": source.name,
        "source_path": source.source_path,
    }
    return data


def infer_kind(file_name: str, keyed: dict[str, str]) -> str:
    stem = Path(file_name).stem.lower()
    if stem in ("diary", "watched", "watchlist", "ratings", "reviews", "likes"):
        return KIND_ALIASES.get(stem, stem)
    if "watcheddate" in keyed:
        return "diary"
    if "review" in keyed:
        return "review"
    if "rating" in keyed:
        return "rating"
    return stem or "csv"
