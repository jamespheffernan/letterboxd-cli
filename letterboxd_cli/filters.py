from __future__ import annotations

import argparse
import re
import urllib.parse
from dataclasses import dataclass


LETTERBOXD_SORTS = {
    "popular": "popular",
    "name": "by/name",
    "release": "by/release",
    "release-earliest": "by/release-earliest",
    "rating": "by/rating",
    "rating-lowest": "by/rating-lowest",
    "your-rating": "by/your-rating",
    "your-rating-lowest": "by/your-rating-lowest",
    "shortest": "by/shortest",
    "longest": "by/longest",
}


@dataclass(frozen=True)
class LetterboxdFilters:
    year: int | None = None
    decade: str | None = None
    genres: tuple[str, ...] = ()
    exclude_genres: tuple[str, ...] = ()
    raw_segments: tuple[str, ...] = ()
    sort: str = "popular"


def filters_from_args(args: argparse.Namespace) -> LetterboxdFilters:
    year = getattr(args, "year", None)
    decade = normalize_decade(getattr(args, "decade", None))
    if year and decade:
        raise ValueError("Use either --year or --decade, not both.")
    sort = getattr(args, "sort", "popular") or "popular"
    if sort not in LETTERBOXD_SORTS:
        sort = "popular"
    return LetterboxdFilters(
        year=year,
        decade=decade,
        genres=tuple(normalize_filter_values(getattr(args, "genre", []), allow_negative=False)),
        exclude_genres=tuple(normalize_filter_values(getattr(args, "exclude_genre", []), allow_negative=False)),
        raw_segments=tuple(normalize_raw_filter_segments(getattr(args, "filter", []))),
        sort=sort,
    )


def filters_have_values(filters: LetterboxdFilters) -> bool:
    return bool(filters.year or filters.decade or filters.genres or filters.exclude_genres or filters.raw_segments)


def normalize_filter_values(values: list[str], *, allow_negative: bool) -> list[str]:
    normalized: list[str] = []
    for value in values or []:
        for part in str(value).split(","):
            text = slugify_filter_token(part)
            if not text:
                continue
            if text.startswith("-") and not allow_negative:
                text = text[1:]
            normalized.append(text)
    return normalized


def slugify_filter_token(value: str) -> str:
    text = value.strip().casefold()
    text = re.sub(r"['’]", "", text)
    text = re.sub(r"[^a-z0-9+-]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text


def normalize_raw_filter_segments(values: list[str]) -> list[str]:
    segments: list[str] = []
    for value in values or []:
        text = str(value).strip().strip("/")
        if not text:
            continue
        if "://" in text or ".." in text or "?" in text or "#" in text:
            raise ValueError(f"Unsafe Letterboxd filter segment: {value!r}.")
        parts = [slugify_filter_token(part) for part in text.split("/") if part.strip()]
        if not parts:
            continue
        segments.append("/".join(parts))
    return segments


def normalize_decade(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).strip().casefold()
    match = re.fullmatch(r"(\d{4})s?", text)
    if not match:
        raise ValueError("Decade should look like 1990s or 1990.")
    decade = int(match.group(1))
    if decade % 10:
        decade = (decade // 10) * 10
    return f"{decade}s"


def letterboxd_filter_segments(filters: LetterboxdFilters, *, include_sort: bool) -> list[str]:
    segments: list[str] = []
    if include_sort:
        segments.extend(LETTERBOXD_SORTS.get(filters.sort, "popular").split("/"))
    if filters.year:
        segments.extend(["year", str(filters.year)])
    elif filters.decade:
        segments.extend(["decade", filters.decade])
    if filters.genres or filters.exclude_genres:
        genre_values = [*filters.genres, *(f"-{genre}" for genre in filters.exclude_genres)]
        segments.extend(["genre", "+".join(genre_values)])
    for raw in filters.raw_segments:
        segments.extend(part for part in raw.split("/") if part)
    return segments


def filtered_path(base: str, filters: LetterboxdFilters, page: int, *, global_browser: bool) -> str:
    if global_browser:
        segments = letterboxd_filter_segments(filters, include_sort=True)
        path = "/csi/films/films-browser-list/" + "/".join(segments).strip("/") + "/"
        if page > 1:
            path += f"page/{page}/"
        return path + "?esiAllowFilters=true"

    base_path = normalize_letterboxd_path(base)
    include_sort = getattr(filters, "sort", "popular") != "popular"
    segments = letterboxd_filter_segments(filters, include_sort=include_sort)
    path = base_path.rstrip("/") + "/"
    if segments:
        path += "/".join(segments).strip("/") + "/"
    if page > 1:
        path += f"page/{page}/"
    return path


def normalize_letterboxd_path(value: str) -> str:
    text = value.strip()
    parsed = urllib.parse.urlparse(text)
    path = parsed.path if parsed.scheme else text
    path = "/" + path.strip("/") + "/"
    if "://" in path or ".." in path or "?" in path or "#" in path:
        raise ValueError(f"Unsafe Letterboxd path: {value!r}.")
    return path


def is_global_films_base(value: str) -> bool:
    return normalize_letterboxd_path(value) == "/films/"


def looks_like_letterboxd_film_set(value: str) -> bool:
    if not value:
        return False
    try:
        path = normalize_letterboxd_path(value)
    except ValueError:
        return False
    return any(part in path for part in ("/list/", "/watchlist/", "/films/", "/actor/", "/director/", "/writer/"))
