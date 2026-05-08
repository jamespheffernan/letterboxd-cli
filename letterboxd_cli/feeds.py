from __future__ import annotations

import html
import json
import re
import urllib.request
from typing import Any
from xml.etree import ElementTree

from letterboxd_cli.normalization import (
    build_search_text,
    normalize_feed_date,
    now_iso,
    parse_rating_from_text,
    row_hash,
)
from letterboxd_cli.web import USER_AGENT


def fetch_url(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        headers = getattr(response, "headers", None)
        charset = headers.get_content_charset() if hasattr(headers, "get_content_charset") else None
        charset = charset or "utf-8"
        return response.read().decode(charset, errors="replace")


def parse_rss(body: str, source_url: str) -> list[dict[str, Any]]:
    root = ElementTree.fromstring(body)
    channel_items = root.findall("./channel/item")
    atom_items = root.findall("{http://www.w3.org/2005/Atom}entry")
    rows = []

    for item in channel_items:
        title = child_text(item, "title")
        link = child_text(item, "link")
        guid = child_text(item, "guid") or link or title
        description = clean_html(child_text(item, "description"))
        published = normalize_feed_date(child_text(item, "pubDate"))
        row = feed_row(guid, title, link, description, published, source_url)
        rows.append(row)

    for item in atom_items:
        title = namespaced_child_text(item, "title")
        link_el = item.find("{http://www.w3.org/2005/Atom}link")
        link = link_el.attrib.get("href") if link_el is not None else ""
        guid = namespaced_child_text(item, "id") or link or title
        summary = clean_html(namespaced_child_text(item, "summary") or namespaced_child_text(item, "content"))
        published = normalize_feed_date(
            namespaced_child_text(item, "published") or namespaced_child_text(item, "updated")
        )
        rows.append(feed_row(guid, title, link, summary, published, source_url))

    return rows


def feed_row(
    guid: str,
    title: str,
    link: str,
    description: str,
    published: str | None,
    source_url: str,
) -> dict[str, Any]:
    name, year = parse_feed_title(title)
    raw = {
        "guid": guid,
        "title": title,
        "link": link,
        "description": description,
        "published": published,
    }
    data = {
        "kind": "feed",
        "name": name or title,
        "year": year,
        "letterboxd_uri": link,
        "rating": parse_rating_from_text(description),
        "date": published,
        "watched_date": None,
        "rewatch": None,
        "tags": None,
        "review": description,
        "like": None,
        "url": link,
        "source_file": source_url,
        "source_path": source_url,
        "row_hash": row_hash(guid or json.dumps(raw, sort_keys=True)),
        "raw_json": json.dumps(raw, ensure_ascii=False, sort_keys=True),
        "imported_at": now_iso(),
    }
    data["search_text"] = build_search_text(data)
    data["_provenance"] = {
        "source": "rss",
        "fetched_at": data["imported_at"],
        "source_url": source_url,
    }
    return data


def parse_feed_title(title: str) -> tuple[str | None, int | None]:
    cleaned = re.sub(r"\s+", " ", title or "").strip()
    for marker in (" watched ", " reviewed ", " liked ", " rated ", " added "):
        marker_match = re.search(marker, f" {cleaned} ", flags=re.IGNORECASE)
        if marker_match:
            cleaned = f" {cleaned} "[marker_match.end() :].strip()
            break

    match = re.search(r"(.+?)\s+\((\d{4})\)", cleaned)
    if match:
        return match.group(1).strip(), int(match.group(2))
    match = re.search(r"(.+?),\s*(\d{4})(?:\s|$)", cleaned)
    if match:
        return match.group(1).strip(), int(match.group(2))
    return cleaned or None, None


def child_text(parent: ElementTree.Element, tag: str) -> str:
    child = parent.find(tag)
    return child.text.strip() if child is not None and child.text else ""


def namespaced_child_text(parent: ElementTree.Element, tag: str) -> str:
    child = parent.find(f"{{http://www.w3.org/2005/Atom}}{tag}")
    return child.text.strip() if child is not None and child.text else ""


def clean_html(value: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", value or "", flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
