from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Any


def key_for(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def first_value(mapping: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def parse_int(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    match = re.search(r"\d{4}", str(value))
    return int(match.group(0)) if match else None


def parse_rating(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return parse_rating_from_text(str(value))


def parse_rating10(value: str | None) -> float | None:
    rating = parse_rating(value)
    if rating is None:
        return None
    return rating / 2


def parse_bool(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    normalized = str(value).strip().casefold()
    if normalized in {"true", "yes", "y", "1", "liked"}:
        return 1
    if normalized in {"false", "no", "n", "0"}:
        return 0
    return None


def normalize_date(value: str | None) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    for fmt in ("%Y-%m-%d %H:%M:%S", "%d %b %Y", "%b %d, %Y", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return text


def normalize_feed_date(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
    ):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return normalize_date(text)


def parse_rating_from_text(value: str) -> float | None:
    if not value:
        return None
    star_count = value.count("★")
    half = "½" in value
    if star_count or half:
        return star_count + (0.5 if half else 0)
    match = re.search(r"\b([0-5](?:\.5)?)\s*/\s*5\b", value)
    return float(match.group(1)) if match else None


def row_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_search_text(data: dict[str, Any]) -> str:
    return " ".join(
        str(data.get(key) or "")
        for key in ("kind", "name", "year", "rating", "date", "watched_date", "tags", "review", "url")
    ).casefold()


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today_iso() -> str:
    return datetime.now().date().isoformat()
