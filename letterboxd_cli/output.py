from __future__ import annotations

import urllib.parse
from pathlib import Path
from typing import Any


PUBLIC_ENTRY_FIELDS = [
    "source",
    "kind",
    "name",
    "year",
    "letterboxd_uri",
    "rating",
    "date",
    "watched_date",
    "rewatch",
    "tags",
    "review",
    "like",
    "url",
]


def ensure_provenance(row: dict[str, Any]) -> dict[str, Any]:
    if isinstance(row.get("_provenance"), dict):
        row.setdefault("source", row["_provenance"].get("source"))
        return row
    row["_provenance"] = {
        "source": "cache",
        "cached_at": row.get("imported_at"),
        "cached_source": safe_source_label(row.get("source_file") or row.get("source_path")),
        "note": "Local lbd cache; not live Letterboxd account truth.",
    }
    row["source"] = "cache"
    return row


def public_display_row(row: dict[str, Any], *, extra_fields: tuple[str, ...] = ()) -> dict[str, Any]:
    row = ensure_provenance(dict(row))
    provenance = sanitize_provenance(row.get("_provenance"))
    public = {field: row.get(field) for field in (*PUBLIC_ENTRY_FIELDS, *extra_fields) if field in row}
    public["source"] = provenance.get("source") or public.get("source") or row.get("source")
    public["_provenance"] = provenance
    return public


def sanitize_provenance(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    sanitized: dict[str, Any] = {}
    for key, item in value.items():
        if key in {"source_path", "cached_source_path"}:
            continue
        if key in {"source_file", "cached_source"}:
            sanitized[key] = safe_source_label(item)
        else:
            sanitized[key] = item
    return sanitized


def safe_source_label(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    parsed = urllib.parse.urlparse(text)
    if parsed.scheme in {"http", "https"}:
        return text
    return Path(text).name
