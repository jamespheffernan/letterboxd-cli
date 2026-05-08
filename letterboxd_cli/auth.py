from __future__ import annotations

import argparse
import html
import json
import re
import sqlite3
import sys
import urllib.parse
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from letterboxd_cli.browser_cookies import load_browser_cookie_sources
from letterboxd_cli.web import (
    LetterboxdWebClient,
    is_letterboxd_origin,
    read_clipboard,
    validate_cookie_header,
    write_private_json,
)


def cmd_auth_save(db: sqlite3.Connection | None, args: argparse.Namespace) -> int:
    cookie = validate_cookie_header(args.cookie)
    if not is_letterboxd_origin(args.base_url):
        raise ValueError("Refusing to save a Letterboxd session for a non-Letterboxd base URL.")
    session_file = Path(args.session_file).expanduser()
    data = {
        "base_url": args.base_url.rstrip("/"),
        "cookie": cookie,
        "saved_at": now_iso(),
    }
    write_private_json(session_file, data)
    print(f"Saved Letterboxd session to {session_file}.")
    return 0


def cmd_login(db: sqlite3.Connection | None, args: argparse.Namespace) -> int:
    cookie = None if args.browser else args.cookie
    clipboard_error = None
    browser_source = None
    username = None
    if args.browser:
        sources = load_browser_cookie_sources(args.browser, profile=args.browser_profile)
        if not sources:
            target = "installed browsers" if args.browser == "auto" else args.browser
            raise ValueError(f"No signed-in Letterboxd cookies found in {target}.")
        if args.no_verify:
            browser_source = sources[0]
            cookie = browser_source.cookie_header
        else:
            for source in sources:
                candidate_username = detect_username(LetterboxdWebClient(args.base_url, source.cookie_header))
                if candidate_username:
                    browser_source = source
                    cookie = source.cookie_header
                    username = candidate_username
                    break
            if not cookie:
                raise ValueError(
                    "Found Letterboxd browser cookies, but Letterboxd did not accept any of them as signed in."
                )
    if not cookie and not args.no_input and not sys.stdin.isatty():
        cookie = sys.stdin.read()
    if not cookie and not args.no_input:
        clipboard_cookie = read_clipboard()
        if clipboard_cookie:
            try:
                cookie = validate_cookie_header(clipboard_cookie)
            except ValueError as exc:
                clipboard_error = exc
    if not cookie:
        if args.no_input:
            raise ValueError("No cookie provided. Pass --cookie when --no-input is set.")
        if clipboard_error:
            raise ValueError(f"Clipboard did not contain a valid Cookie header: {clipboard_error}")
        raise ValueError("Copy the Cookie header, then run lbd login or pass --cookie.")
    cookie = validate_cookie_header(cookie)
    if not args.no_verify:
        username = username or detect_username(LetterboxdWebClient(args.base_url, cookie))
        if not username:
            raise ValueError(
                "Letterboxd did not accept that Cookie header as a signed-in session. "
                "Copy the Request Headers > Cookie value from a signed-in letterboxd.com page, "
                "or pass --no-verify to save without checking."
            )
    args.cookie = cookie
    status = cmd_auth_save(db, args)
    if browser_source:
        print(f"Imported Letterboxd cookies from {browser_source.browser} profile {browser_source.profile}.")
    if username:
        print(f"Verified signed-in session as {username}.")
    return status


def cmd_auth_status(db: sqlite3.Connection | None, args: argparse.Namespace) -> int:
    client = LetterboxdWebClient.from_args(args)
    username = detect_username(client)
    if args.format == "json":
        print(json.dumps({"signed_in": bool(username), "username": username}, indent=2))
        return 0 if username else 1
    if username:
        print(f"Signed in as {username}.")
        return 0
    print("No signed-in Letterboxd session detected.")
    return 1


def cmd_auth_clear(db: sqlite3.Connection | None, args: argparse.Namespace) -> int:
    session_file = Path(args.session_file).expanduser()
    if session_file.exists():
        session_file.unlink()
        print(f"Deleted {session_file}.")
    else:
        print("No saved session file found.")
    return 0


def detect_username(client: LetterboxdWebClient) -> str | None:
    cookie_username = username_from_cookie(client.cookie)
    status = parse_web_person(client.get("/").text)
    username = status.get("username")
    if status.get("logged_in") and username:
        return str(username)

    if cookie_username:
        settings = client.get("/settings/")
        if settings.status < 400 and (
            "Account Settings" in settings.text
            or f"/{cookie_username}/" in settings.text
            or cookie_username in settings.text
        ):
            return cookie_username
    return None


def username_from_cookie(cookie: str | None) -> str | None:
    if not cookie:
        return None
    for part in cookie.split(";"):
        part = part.strip()
        if part.startswith("letterboxd.signed.in.as="):
            value = part.split("=", 1)[1].strip()
            return urllib.parse.unquote(value) if value else None
    return None


def parse_web_person(body: str) -> dict[str, Any]:
    logged_in = bool(re.search(r"\bloggedIn:\s*true\b", body))
    username_match = re.search(r"\busername:\s*['\"]([^'\"]+)['\"]", body)
    return {
        "logged_in": logged_in,
        "username": html.unescape(username_match.group(1)) if username_match else None,
    }


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
