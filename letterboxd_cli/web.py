from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


LETTERBOXD_BASE_URL = "https://letterboxd.com"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36 letterboxd-cli/0.1"
)
COOKIE_NAME_RE = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")


@dataclass(frozen=True)
class WebResponse:
    url: str
    status: int
    content_type: str
    text: str


class LetterboxdWebError(ValueError):
    def __init__(self, message: str, *, status: int, url: str) -> None:
        super().__init__(message)
        self.status = status
        self.url = url


class LetterboxdWebClient:
    def __init__(self, base_url: str, cookie: str | None = None) -> None:
        self.base_url = normalize_base_url(base_url)
        self.cookie = validate_cookie_header(cookie) if cookie else None
        if self.cookie and not is_letterboxd_origin(self.base_url):
            raise ValueError(
                "Refusing to attach a Letterboxd session to a non-Letterboxd base URL: "
                f"{origin_label(self.base_url)}"
            )

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "LetterboxdWebClient":
        cookie = args.cookie or load_saved_cookie(Path(args.session_file).expanduser())
        return cls(args.base_url, cookie)

    def url(self, path: str) -> str:
        text = path.strip()
        parsed = urllib.parse.urlparse(text)
        if parsed.scheme.casefold() in ("http", "https"):
            if not same_origin(text, self.base_url):
                raise ValueError(
                    "Refusing to use the saved Letterboxd session with a different origin: "
                    f"{parsed.scheme}://{parsed.netloc}"
                )
            if self.cookie and not is_letterboxd_origin(text):
                raise ValueError(
                    "Refusing to attach a Letterboxd session to a non-Letterboxd URL: "
                    f"{parsed.scheme}://{parsed.netloc}"
                )
            return text
        if parsed.scheme or parsed.netloc:
            raise ValueError(f"Unsupported Letterboxd URL: {path!r}")
        return f"{self.base_url}/{text.lstrip('/')}"

    def get(self, path: str) -> WebResponse:
        return self.request("GET", path)

    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> WebResponse:
        url = self.url(path)
        if self.cookie and not is_letterboxd_origin(url):
            raise ValueError(
                "Refusing to attach a Letterboxd session to a non-Letterboxd URL: "
                f"{origin_label(url)}"
            )

        request_headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": self.base_url,
            "Referer": self.base_url + "/",
        }
        if self.cookie:
            request_headers["Cookie"] = self.cookie
        if headers:
            request_headers.update(headers)

        request = urllib.request.Request(
            url,
            data=body,
            headers=request_headers,
            method=method,
        )
        return open_request_with_retry(request)


def open_request_with_retry(request: urllib.request.Request) -> WebResponse:
    last_error: urllib.error.URLError | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                text = decode_response_body(response)
                return WebResponse(
                    url=response.url,
                    status=response.status,
                    content_type=response.headers.get("content-type", ""),
                    text=text,
                )
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            if exc.code not in {429, 500, 502, 503, 504} or attempt == 2:
                return WebResponse(
                    url=exc.geturl(),
                    status=exc.code,
                    content_type=exc.headers.get("content-type", ""),
                    text=text,
                )
            time.sleep(0.4 * (attempt + 1))
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt == 2:
                raise
            time.sleep(0.4 * (attempt + 1))
    if last_error:
        raise last_error
    raise RuntimeError("unreachable request retry state")


def normalize_base_url(base_url: str) -> str:
    parsed = urllib.parse.urlparse(base_url.strip())
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.netloc:
        raise ValueError("--base-url must be an http(s) URL.")
    return base_url.rstrip("/")


def load_saved_cookie(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        cookie = data.get("cookie")
        return validate_cookie_header(cookie) if cookie else None
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Warning: ignoring invalid saved session in {path}: {exc}", file=sys.stderr)
        return None


def write_private_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
    path.chmod(0o600)


def validate_cookie_header(cookie: str | None) -> str:
    if not cookie:
        raise ValueError("Cookie header is empty.")
    normalized = " ".join(line.strip() for line in cookie.strip().splitlines() if line.strip())
    first_pair = normalized.split(";", 1)[0]
    colon_index = first_pair.find(":")
    equals_index = first_pair.find("=")
    if colon_index >= 0 and (equals_index < 0 or colon_index < equals_index):
        prefix, rest = normalized.split(":", 1)
        if prefix.strip().casefold() == "cookie":
            normalized = rest.strip()
        else:
            raise ValueError("Paste only the Cookie request header, not terminal output or other headers.")

    pairs: list[tuple[str, str]] = []
    for part in normalized.split(";"):
        item = part.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError("Cookie header should look like name=value; name2=value2.")
        name, value = item.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name or not value:
            raise ValueError("Cookie header should look like name=value; name2=value2.")
        if not COOKIE_NAME_RE.fullmatch(name):
            raise ValueError("Cookie names may not contain whitespace or header text; paste only the Cookie request header.")
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("Cookie values may not contain control characters.")
        if looks_like_placeholder(name) or looks_like_placeholder(value):
            raise ValueError("Cookie header contains a placeholder value; paste the real Cookie header from your browser.")
        pairs.append((name, value))

    if not pairs:
        raise ValueError("Cookie header should look like name=value; name2=value2.")
    return "; ".join(f"{name}={value}" for name, value in pairs)


def looks_like_placeholder(value: str) -> bool:
    text = value.strip().strip("'\"").casefold()
    if not text:
        return True
    if text in {"...", "…", "your-cookie", "your_cookie", "replace-me", "replace_me", "changeme", "todo"}:
        return True
    if text.startswith("<") and text.endswith(">"):
        return True
    if text.startswith("{") and text.endswith("}"):
        return True
    if re.fullmatch(r"[.·…]+", text):
        return True
    if re.fullmatch(r"x{3,}|_{3,}|-{3,}", text):
        return True
    return False


def same_origin(url: str, base_url: str) -> bool:
    requested = urllib.parse.urlparse(url)
    base = urllib.parse.urlparse(base_url)
    return origin_tuple(requested) == origin_tuple(base)


def is_letterboxd_origin(url: str) -> bool:
    return same_origin(url, LETTERBOXD_BASE_URL)


def origin_label(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def origin_tuple(parsed: urllib.parse.ParseResult) -> tuple[str, str, int | None]:
    scheme = parsed.scheme.casefold()
    port = parsed.port
    if port is None and scheme == "https":
        port = 443
    elif port is None and scheme == "http":
        port = 80
    return scheme, (parsed.hostname or "").casefold(), port


def redact_sensitive_values(value: Any) -> Any:
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            key_text = str(key).casefold()
            if any(marker in key_text for marker in ("csrf", "cookie", "token", "secret", "password", "session")):
                redacted[key] = "[redacted]"
            else:
                redacted[key] = redact_sensitive_values(item)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive_values(item) for item in value]
    return value


def read_clipboard() -> str | None:
    try:
        result = subprocess.run(
            ["pbpaste"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = result.stdout.strip()
    return text or None


def decode_response_body(response: Any) -> str:
    headers = getattr(response, "headers", None)
    charset = headers.get_content_charset() if hasattr(headers, "get_content_charset") else None
    charset = charset or "utf-8"
    return response.read().decode(charset, errors="replace")


def print_web_response(response: WebResponse, output_format: str) -> int:
    if response.status >= 400:
        print(f"HTTP {response.status} for {response.url}", file=sys.stderr)

    if output_format in ("auto", "json"):
        try:
            payload = json.loads(response.text)
        except json.JSONDecodeError:
            if output_format == "json":
                raise ValueError("Response was not JSON.")
        else:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return 0 if response.status < 400 else 1

    print(response.text)
    return 0 if response.status < 400 else 1


def parse_json_response(response: WebResponse) -> dict[str, Any]:
    try:
        payload = json.loads(response.text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Expected JSON from {response.url}, got {response.content_type or 'unknown content type'}.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object.")
    return payload
