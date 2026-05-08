from __future__ import annotations

import hashlib
import platform
import shutil
import sqlite3
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from letterboxd_cli.web import validate_cookie_header


LETTERBOXD_COOKIE_HOSTS = ("letterboxd.com", ".letterboxd.com")
AUTH_COOKIE_NAMES = {
    "__cf_bm",
    "cf_clearance",
    "letterboxd.signed.in.as",
    "letterboxd.user",
    "letterboxd_session",
}


@dataclass(frozen=True)
class BrowserConfig:
    key: str
    label: str
    roots: tuple[Path, ...]
    keychain_services: tuple[str, ...] = ()
    firefox: bool = False


@dataclass(frozen=True)
class BrowserCookieSource:
    browser: str
    profile: str
    cookie_file: Path
    cookie_header: str
    cookie_names: tuple[str, ...]


class BrowserCookieError(ValueError):
    pass


def browser_choices() -> tuple[str, ...]:
    return ("auto",) + tuple(BROWSER_CONFIGS)


def load_browser_cookie_sources(browser: str = "auto", profile: str | None = None) -> list[BrowserCookieSource]:
    configs = selected_browser_configs(browser)
    sources: list[BrowserCookieSource] = []
    errors: list[str] = []

    for config in configs:
        try:
            if config.firefox:
                sources.extend(load_firefox_sources(config, profile))
            else:
                sources.extend(load_chromium_sources(config, profile))
        except BrowserCookieError as exc:
            errors.append(f"{config.label}: {exc}")

    if not sources and errors:
        raise BrowserCookieError("; ".join(errors))
    return sources


def selected_browser_configs(browser: str) -> tuple[BrowserConfig, ...]:
    if browser == "auto":
        return tuple(BROWSER_CONFIGS.values())
    try:
        return (BROWSER_CONFIGS[browser],)
    except KeyError as exc:
        raise BrowserCookieError(f"Unknown browser {browser!r}.") from exc


def load_chromium_sources(config: BrowserConfig, profile: str | None) -> list[BrowserCookieSource]:
    if platform.system() != "Darwin":
        raise BrowserCookieError("Chromium browser cookie import currently supports macOS.")

    cookie_files = list(iter_chromium_cookie_files(config.roots, profile))
    if not cookie_files:
        return []

    safe_storage_key = chromium_keychain_password(config)
    sources: list[BrowserCookieSource] = []
    for cookie_file in cookie_files:
        cookies = read_chromium_cookies(cookie_file, safe_storage_key)
        source = source_from_cookie_pairs(config.label, cookie_file, cookies)
        if source:
            sources.append(source)
    return sources


def load_firefox_sources(config: BrowserConfig, profile: str | None) -> list[BrowserCookieSource]:
    sources: list[BrowserCookieSource] = []
    for cookie_file in iter_firefox_cookie_files(config.roots, profile):
        cookies = read_firefox_cookies(cookie_file)
        source = source_from_cookie_pairs(config.label, cookie_file, cookies)
        if source:
            sources.append(source)
    return sources


def source_from_cookie_pairs(
    browser: str,
    cookie_file: Path,
    cookies: Iterable[tuple[str, str]],
) -> BrowserCookieSource | None:
    filtered: dict[str, str] = {}
    for name, value in cookies:
        if not value:
            continue
        if name in AUTH_COOKIE_NAMES or name.startswith("supermodel.user.device."):
            filtered[name] = value

    if not signed_in_cookie_names(filtered):
        return None

    names = tuple(sorted(filtered))
    header = validate_cookie_header("; ".join(f"{name}={filtered[name]}" for name in names))
    return BrowserCookieSource(
        browser=browser,
        profile=profile_name_from_cookie_file(cookie_file),
        cookie_file=cookie_file,
        cookie_header=header,
        cookie_names=names,
    )


def signed_in_cookie_names(cookies: dict[str, str]) -> tuple[str, ...]:
    return tuple(name for name in ("letterboxd_session", "letterboxd.user", "letterboxd.signed.in.as") if cookies.get(name))


def iter_chromium_cookie_files(roots: Iterable[Path], profile: str | None) -> Iterable[Path]:
    seen: set[Path] = set()
    for root in roots:
        expanded = root.expanduser()
        if not expanded.exists():
            continue
        candidates = [
            expanded / "Cookies",
            expanded / "Network" / "Cookies",
        ]
        candidates.extend(expanded.glob("*/Cookies"))
        candidates.extend(expanded.glob("*/Network/Cookies"))
        candidates.extend(expanded.glob("*/*/Cookies"))
        candidates.extend(expanded.glob("*/*/Network/Cookies"))
        for cookie_file in candidates:
            if not cookie_file.is_file():
                continue
            if profile and profile.casefold() not in profile_name_from_cookie_file(cookie_file).casefold():
                continue
            resolved = cookie_file.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            yield cookie_file


def iter_firefox_cookie_files(roots: Iterable[Path], profile: str | None) -> Iterable[Path]:
    seen: set[Path] = set()
    for root in roots:
        expanded = root.expanduser()
        if not expanded.exists():
            continue
        candidates = [expanded / "cookies.sqlite"]
        candidates.extend(expanded.glob("*/cookies.sqlite"))
        for cookie_file in candidates:
            if not cookie_file.is_file():
                continue
            if profile and profile.casefold() not in profile_name_from_cookie_file(cookie_file).casefold():
                continue
            resolved = cookie_file.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            yield cookie_file


def read_chromium_cookies(cookie_file: Path, password: bytes) -> list[tuple[str, str]]:
    rows = query_cookie_db(
        cookie_file,
        """
        SELECT host_key, name, value, encrypted_value
        FROM cookies
        WHERE host_key IN (?, ?)
        ORDER BY host_key, name, path
        """,
        LETTERBOXD_COOKIE_HOSTS,
    )
    cookies: list[tuple[str, str]] = []
    for host_key, name, value, encrypted_value in rows:
        cookie_value = value or decrypt_chromium_value(str(host_key), bytes(encrypted_value or b""), password)
        if cookie_value:
            cookies.append((str(name), cookie_value))
    return cookies


def read_firefox_cookies(cookie_file: Path) -> list[tuple[str, str]]:
    rows = query_cookie_db(
        cookie_file,
        """
        SELECT name, value
        FROM moz_cookies
        WHERE host IN (?, ?)
        ORDER BY host, name, path
        """,
        LETTERBOXD_COOKIE_HOSTS,
    )
    return [(str(name), str(value)) for name, value in rows if value]


def query_cookie_db(cookie_file: Path, query: str, params: tuple[str, ...]) -> list[tuple]:
    with tempfile.NamedTemporaryFile(prefix="lbd-cookies-", suffix=".sqlite3", delete=False) as handle:
        temp_path = Path(handle.name)
    try:
        shutil.copy2(cookie_file, temp_path)
        with sqlite3.connect(temp_path) as db:
            return list(db.execute(query, params))
    except sqlite3.Error as exc:
        raise BrowserCookieError(f"could not read {cookie_file}: {exc}") from exc
    finally:
        temp_path.unlink(missing_ok=True)


def chromium_keychain_password(config: BrowserConfig) -> bytes:
    errors: list[str] = []
    for service in config.keychain_services:
        try:
            result = subprocess.run(
                ["security", "find-generic-password", "-w", "-s", service],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            errors.append(f"{service}: {exc}")
            continue
        if result.returncode == 0 and result.stdout:
            return result.stdout.rstrip(b"\r\n")
        message = result.stderr.decode("utf-8", errors="replace").strip() or f"exit {result.returncode}"
        errors.append(f"{service}: {message}")
    raise BrowserCookieError("could not read the browser safe-storage key from Keychain. " + "; ".join(errors))


def decrypt_chromium_value(host_key: str, encrypted_value: bytes, password: bytes) -> str:
    if not encrypted_value:
        return ""
    if not (encrypted_value.startswith(b"v10") or encrypted_value.startswith(b"v11")):
        return encrypted_value.decode("utf-8", errors="replace")

    key = hashlib.pbkdf2_hmac("sha1", password, b"saltysalt", 1003, 16)
    decryptor = Cipher(algorithms.AES(key), modes.CBC(b" " * 16)).decryptor()
    plaintext = decryptor.update(encrypted_value[3:]) + decryptor.finalize()
    plaintext = strip_pkcs7_padding(plaintext)

    host_digest = hashlib.sha256(host_key.encode("utf-8")).digest()
    if plaintext.startswith(host_digest):
        plaintext = plaintext[len(host_digest) :]
    return plaintext.decode("utf-8", errors="replace")


def strip_pkcs7_padding(value: bytes) -> bytes:
    if not value:
        return value
    padding = value[-1]
    if padding < 1 or padding > 16:
        return value
    if value[-padding:] != bytes([padding]) * padding:
        return value
    return value[:-padding]


def profile_name_from_cookie_file(cookie_file: Path) -> str:
    if cookie_file.name == "Cookies":
        parent = cookie_file.parent
        if parent.name == "Network":
            return parent.parent.name
        return parent.name
    if cookie_file.name == "cookies.sqlite":
        return cookie_file.parent.name
    return cookie_file.parent.name


BROWSER_CONFIGS = {
    "chrome": BrowserConfig(
        key="chrome",
        label="Chrome",
        roots=(
            Path("~/Library/Application Support/Google/Chrome"),
            Path("~/Library/Application Support/Google/Chrome for Testing"),
        ),
        keychain_services=("Chrome Safe Storage",),
    ),
    "arc": BrowserConfig(
        key="arc",
        label="Arc",
        roots=(Path("~/Library/Application Support/Arc/User Data"),),
        keychain_services=("Arc Safe Storage",),
    ),
    "comet": BrowserConfig(
        key="comet",
        label="Comet",
        roots=(Path("~/Library/Application Support/Comet"),),
        keychain_services=("Comet Safe Storage",),
    ),
    "edge": BrowserConfig(
        key="edge",
        label="Edge",
        roots=(Path("~/Library/Application Support/Microsoft Edge"),),
        keychain_services=("Microsoft Edge Safe Storage",),
    ),
    "brave": BrowserConfig(
        key="brave",
        label="Brave",
        roots=(Path("~/Library/Application Support/BraveSoftware/Brave-Browser"),),
        keychain_services=("Brave Safe Storage",),
    ),
    "vivaldi": BrowserConfig(
        key="vivaldi",
        label="Vivaldi",
        roots=(Path("~/Library/Application Support/Vivaldi"),),
        keychain_services=("Vivaldi Safe Storage",),
    ),
    "chromium": BrowserConfig(
        key="chromium",
        label="Chromium",
        roots=(Path("~/Library/Application Support/Chromium"),),
        keychain_services=("Chromium Safe Storage",),
    ),
    "firefox": BrowserConfig(
        key="firefox",
        label="Firefox",
        roots=(Path("~/Library/Application Support/Firefox/Profiles"),),
        firefox=True,
    ),
}
