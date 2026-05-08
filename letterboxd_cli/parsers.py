from __future__ import annotations

import html
import json
import re
import textwrap
import urllib.parse
from typing import Any, Iterable

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
)
from letterboxd_cli.web import LETTERBOXD_BASE_URL


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


def film_slug_search_query(slug: str) -> str:
    return re.sub(r"\s+\d{4}$", "", slug.replace("-", " ")).strip() or slug


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
        rows.append(
            {
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
        )
    return rows


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


def clean_html(value: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", value or "", flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def title_with_year(name: str | None, year: int | None) -> str:
    if not name:
        return ""
    return f"{name} ({year})" if year else name


def truncate(value: str, width: int) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    return textwrap.shorten(value, width=width, placeholder="...") if len(value) > width else value
