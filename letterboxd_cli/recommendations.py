from __future__ import annotations

import math
import re
import time
from typing import Any

from letterboxd_cli.parsers import film_slug, first_poster_url


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
