import io
import json
import sqlite3
import tomllib
import urllib.error
import zipfile
from pathlib import Path

import letterboxd_cli
from letterboxd_cli.browser_cookies import BrowserCookieSource, source_from_cookie_pairs
from letterboxd_cli.cli import main
from letterboxd_cli.web import load_saved_cookie


FIXTURES = Path(__file__).parent / "fixtures"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class TtyStringIO(io.StringIO):
    def isatty(self):
        return True


def test_version_command_does_not_create_database(tmp_path: Path, capsys):
    db = tmp_path / "lbd.sqlite3"

    assert main(["--db", str(db), "version"]) == 0

    assert capsys.readouterr().out.strip().startswith("lbd ")
    assert not db.exists()


def test_global_json_forces_structured_output(tmp_path: Path, capsys):
    export = tmp_path / "letterboxd.zip"
    with zipfile.ZipFile(export, "w") as bundle:
        bundle.writestr(
            "watchlist.csv",
            "Date,Name,Year,Letterboxd URI\n"
            "2026-04-21,Heat,1995,https://boxd.it/def\n",
        )

    db = tmp_path / "lbd.sqlite3"
    assert main(["--db", str(db), "load", str(export)]) == 0
    capsys.readouterr()

    assert main(["--db", str(db), "--json", "watchlist"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["name"] == "Heat"


def test_version_matches_project_metadata():
    metadata = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert letterboxd_cli.__version__ == metadata["project"]["version"]


def test_doctor_json_reports_missing_optional_state(tmp_path: Path, capsys):
    db = tmp_path / "lbd.sqlite3"
    session = tmp_path / "session.json"

    assert main(["--db", str(db), "--session-file", str(session), "doctor", "--skip-network", "--format", "json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert {check["name"]: check["status"] for check in payload["checks"]} == {
        "version": "ok",
        "session": "warn",
        "database": "warn",
        "network": "warn",
    }
    assert not db.exists()


def test_doctor_fails_unreadable_database(tmp_path: Path, capsys):
    db = tmp_path / "lbd.sqlite3"
    db.write_text("not sqlite", encoding="utf-8")

    assert main(["--db", str(db), "doctor", "--skip-network", "--format", "json"]) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    checks = {check["name"]: check for check in payload["checks"]}
    assert checks["database"]["status"] == "fail"
    assert "Cannot read local database" in checks["database"]["detail"]


def test_global_plain_prefers_parseable_csv(tmp_path: Path, capsys):
    export = tmp_path / "letterboxd.zip"
    with zipfile.ZipFile(export, "w") as bundle:
        bundle.writestr(
            "watchlist.csv",
            "Date,Name,Year,Letterboxd URI\n"
            "2026-04-21,Heat,1995,https://boxd.it/def\n",
        )

    db = tmp_path / "lbd.sqlite3"
    assert main(["--db", str(db), "load", str(export)]) == 0
    capsys.readouterr()

    assert main(["--db", str(db), "--plain", "watchlist"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("source,kind,name,year,rating,date,watched_date,tags,review,url")
    assert "Heat" in out


def test_login_no_input_requires_explicit_cookie(tmp_path: Path, monkeypatch, capsys):
    db = tmp_path / "lbd.sqlite3"
    session = tmp_path / "session.json"
    monkeypatch.setattr("letterboxd_cli.auth.read_clipboard", lambda: "letterboxd_session=test-session")

    assert main(["--db", str(db), "--session-file", str(session), "--no-input", "login"]) == 1

    assert "No cookie provided" in capsys.readouterr().err
    assert not session.exists()


def test_login_rejects_placeholder_cookie(tmp_path: Path, capsys):
    session = tmp_path / "session.json"

    assert main(["--session-file", str(session), "login", "--cookie", "letterboxd_session=..."]) == 1

    assert "placeholder" in capsys.readouterr().err
    assert not session.exists()


def test_login_reports_invalid_clipboard(tmp_path: Path, monkeypatch, capsys):
    session = tmp_path / "session.json"
    monkeypatch.setattr("letterboxd_cli.auth.read_clipboard", lambda: "not a cookie")
    monkeypatch.setattr("sys.stdin", TtyStringIO(""))

    assert main(["--session-file", str(session), "login"]) == 1

    assert "Clipboard did not contain a valid Cookie header" in capsys.readouterr().err
    assert not session.exists()


def test_login_rejects_terminal_transcript_clipboard(tmp_path: Path, monkeypatch, capsys):
    session = tmp_path / "session.json"
    monkeypatch.setattr(
        "letterboxd_cli.auth.read_clipboard",
        lambda: "user@Mac Letterboxd CLI % lbd login\n"
        "Error: Cookie header should look like name=value; name2=value2.",
    )
    monkeypatch.setattr("sys.stdin", TtyStringIO(""))

    assert main(["--session-file", str(session), "login"]) == 1

    err = capsys.readouterr().err
    assert "Clipboard did not contain a valid Cookie header" in err
    assert "terminal output or other headers" in err
    assert not session.exists()


def test_login_rejects_unverified_cookie(tmp_path: Path, monkeypatch, capsys):
    session = tmp_path / "session.json"
    monkeypatch.setattr("letterboxd_cli.auth.detect_username", lambda client: None)

    assert main(["--session-file", str(session), "login", "--cookie", "letterboxd_session=test-session"]) == 1

    assert "did not accept that Cookie header" in capsys.readouterr().err
    assert not session.exists()


def test_browser_cookie_source_filters_to_letterboxd_auth_cookies():
    source = source_from_cookie_pairs(
        "Chrome",
        Path("/tmp/example/Chrome/Default/Cookies"),
        [
            ("_ga", "tracking-value"),
            ("cf_clearance", "clearance-value"),
            ("letterboxd.signed.in.as", "exampleuser"),
            ("letterboxd.user", "session-value"),
        ],
    )

    assert source is not None
    assert source.cookie_header == (
        "cf_clearance=clearance-value; "
        "letterboxd.signed.in.as=exampleuser; "
        "letterboxd.user=session-value"
    )
    assert "_ga" not in source.cookie_names


def test_login_imports_browser_cookie_source(tmp_path: Path, monkeypatch, capsys):
    session = tmp_path / "session.json"
    source = BrowserCookieSource(
        browser="Chrome",
        profile="Default",
        cookie_file=tmp_path / "Cookies",
        cookie_header="letterboxd.signed.in.as=exampleuser; letterboxd.user=session-value",
        cookie_names=("letterboxd.signed.in.as", "letterboxd.user"),
    )
    monkeypatch.setattr("letterboxd_cli.auth.load_browser_cookie_sources", lambda browser, profile=None: [source])
    monkeypatch.setattr("letterboxd_cli.auth.detect_username", lambda client: "exampleuser")

    assert main(["--session-file", str(session), "login", "--browser", "chrome"]) == 0

    saved = json.loads(session.read_text())
    assert saved["cookie"] == "letterboxd.signed.in.as=exampleuser; letterboxd.user=session-value"
    out = capsys.readouterr().out
    assert "Imported Letterboxd cookies from Chrome profile Default" in out
    assert "Verified signed-in session as exampleuser" in out


def test_invalid_saved_session_is_ignored(tmp_path: Path, capsys):
    session = tmp_path / "session.json"
    session.write_text(
        json.dumps(
            {
                "cookie": "user@Mac Letterboxd CLI % lbd login\n"
                "Error: Cookie header should look like name=value; name2=value2."
            }
        ),
        encoding="utf-8",
    )

    assert load_saved_cookie(session) is None

    assert "ignoring invalid saved session" in capsys.readouterr().err


def test_load_and_query_export(tmp_path: Path, capsys):
    export = tmp_path / "letterboxd.zip"
    with zipfile.ZipFile(export, "w") as bundle:
        bundle.writestr(
            "diary.csv",
            "Date,Name,Year,Letterboxd URI,Rating,Rewatch,Tags,Watched Date,Review\n"
            "2026-04-20,Past Lives,2023,https://boxd.it/abc,4.5,No,\"quiet,drama\",2026-04-20,Loved it\n",
        )
        bundle.writestr(
            "watchlist.csv",
            "Date,Name,Year,Letterboxd URI\n"
            "2026-04-21,Heat,1995,https://boxd.it/def\n",
        )

    db = tmp_path / "lbd.sqlite3"
    assert main(["--db", str(db), "load", str(export)]) == 0
    out = capsys.readouterr().out
    assert "Imported 2 rows" in out

    assert main(["--db", str(db), "search", "past lives", "--format", "json"]) == 0
    out = capsys.readouterr().out
    assert "Past Lives" in out
    assert "Loved it" in out

    assert main(["--db", str(db), "watchlist"]) == 0
    out = capsys.readouterr().out
    assert "Heat (1995)" in out

    assert main(["--db", str(db), "history"]) == 0
    out = capsys.readouterr().out
    assert "Past Lives (2023)" in out

    assert main(["--db", str(db), "reviews"]) == 0
    out = capsys.readouterr().out
    assert "Loved it" in out


def test_json_rows_do_not_leak_import_source_paths(tmp_path: Path, capsys):
    export = tmp_path / "private-export.zip"
    with zipfile.ZipFile(export, "w") as bundle:
        bundle.writestr(
            "watchlist.csv",
            "Date,Name,Year,Letterboxd URI\n"
            "2026-04-21,Heat,1995,https://boxd.it/def\n",
        )

    db = tmp_path / "lbd.sqlite3"
    assert main(["--db", str(db), "load", str(export)]) == 0
    capsys.readouterr()

    assert main(["--db", str(db), "watchlist", "--format", "json"]) == 0
    out = capsys.readouterr().out
    payload = json.loads(out)

    assert str(tmp_path) not in out
    assert "source_path" not in payload[0]
    assert "raw_json" not in payload[0]
    assert "search_text" not in payload[0]
    assert "cached_source_path" not in payload[0]["_provenance"]
    assert payload[0]["_provenance"]["cached_source"] == "watchlist.csv"


def test_feed_parser_via_custom_url(tmp_path: Path, monkeypatch, capsys):
    rss = fixture_text("letterboxd_rss.xml")

    class Response(io.BytesIO):
        headers = {"content-type": "application/rss+xml"}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    def fake_urlopen(_request, timeout=30):
        return Response(rss.encode())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    db = tmp_path / "lbd.sqlite3"

    assert main(["--db", str(db), "feed", "--url", "https://example.test/rss", "--format", "json"]) == 0
    out = capsys.readouterr().out
    assert "Heat" in out
    assert "5" in out

    with sqlite3.connect(db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM entries WHERE kind = 'feed'").fetchone()[0]
    assert count == 1


def test_sql_is_readonly_and_prints_generic_rows(tmp_path: Path, capsys):
    missing_db = tmp_path / "missing.sqlite3"

    assert main(["--db", str(missing_db), "sql", "SELECT 1 AS one", "--format", "json"]) == 1
    assert not missing_db.exists()
    assert "Database does not exist" in capsys.readouterr().err

    export = tmp_path / "letterboxd.zip"
    with zipfile.ZipFile(export, "w") as bundle:
        bundle.writestr(
            "watchlist.csv",
            "Date,Name,Year,Letterboxd URI\n"
            "2026-04-21,Heat,1995,https://boxd.it/def\n",
        )
    db = tmp_path / "lbd.sqlite3"
    assert main(["--db", str(db), "load", str(export)]) == 0
    capsys.readouterr()

    assert main(["--db", str(db), "sql", "SELECT 1 AS one", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out) == [{"one": 1}]


def test_existing_database_schema_is_migrated(tmp_path: Path, capsys):
    db = tmp_path / "old.sqlite3"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE entries (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, name TEXT)")
        conn.execute("INSERT INTO entries(kind, name) VALUES ('watchlist', 'Heat')")

    assert main(["--db", str(db), "stats"]) == 0
    assert "Rows: 1" in capsys.readouterr().out

    with sqlite3.connect(db) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(entries)").fetchall()}
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert {"source_path", "raw_json", "search_text", "imported_at"} <= columns
    assert user_version == 1


def test_auth_save_and_web_film_uses_cookie(tmp_path: Path, monkeypatch, capsys):
    db = tmp_path / "lbd.sqlite3"
    session = tmp_path / "session.json"

    assert (
        main(
            [
                "--db",
                str(db),
                "--session-file",
                str(session),
                "auth",
                "save",
                "--cookie",
                "letterboxd_session=test-session; other=test-value",
            ]
        )
        == 0
    )

    saved = json.loads(session.read_text())
    assert saved["cookie"] == "letterboxd_session=test-session; other=test-value"
    assert session.stat().st_mode & 0o777 == 0o600

    seen = {}

    class Response(io.BytesIO):
        url = "https://letterboxd.com/film/heat-1995/json/"
        status = 200

        def __init__(self, body: str):
            super().__init__(body.encode())
            self.headers = {"content-type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    def fake_urlopen(request, timeout=30):
        seen["url"] = request.full_url
        seen["cookie"] = request.get_header("Cookie")
        return Response(
            json.dumps(
                {
                    "result": True,
                    "csrf": "csrf-token",
                    "lid": "2bg8",
                    "uid": "film:51994",
                    "name": "Heat",
                    "releaseYear": 1995,
                    "slug": "heat-1995",
                    "watchlistAction": "/film/heat-1995/add-to-watchlist/",
                }
            )
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert (
        main(
            [
                "--db",
                str(db),
                "--session-file",
                str(session),
                "web",
                "film",
                "heat-1995",
                "--format",
                "json",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert '"name": "Heat"' in out
    assert seen["url"] == "https://letterboxd.com/film/heat-1995/json/"
    assert seen["cookie"] == "letterboxd_session=test-session; other=test-value"


def test_login_alias_saves_cookie(tmp_path: Path, monkeypatch, capsys):
    db = tmp_path / "lbd.sqlite3"
    session = tmp_path / "session.json"
    monkeypatch.setattr(
        "letterboxd_cli.auth.read_clipboard",
        lambda: "Cookie: letterboxd_session=test-session;\n letterboxd.signed.in.as=exampleuser",
    )
    monkeypatch.setattr("sys.stdin", TtyStringIO(""))
    monkeypatch.setattr("letterboxd_cli.auth.detect_username", lambda client: "exampleuser")

    assert main(["--db", str(db), "--session-file", str(session), "login"]) == 0

    saved = json.loads(session.read_text())
    assert saved["cookie"] == "letterboxd_session=test-session; letterboxd.signed.in.as=exampleuser"
    assert "Verified signed-in session as exampleuser" in capsys.readouterr().out


def test_auth_status_uses_settings_when_homepage_person_is_guest(tmp_path: Path, monkeypatch, capsys):
    db = tmp_path / "lbd.sqlite3"
    session = tmp_path / "session.json"
    session.write_text(
        json.dumps({"cookie": "letterboxd.signed.in.as=exampleuser; letterboxd.user=abc"}),
        encoding="utf-8",
    )

    class Response(io.BytesIO):
        status = 200

        def __init__(self, url: str, body: str):
            super().__init__(body.encode())
            self.url = url
            self.headers = {"content-type": "text/html"}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    def fake_urlopen(request, timeout=30):
        if request.full_url.endswith("/settings/"):
            return Response(request.full_url, "Account Settings for exampleuser")
        return Response(request.full_url, 'person = { username: "", loggedIn: false };')

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert main(["--db", str(db), "--session-file", str(session), "auth", "status"]) == 0
    assert "Signed in as exampleuser" in capsys.readouterr().out


def test_auth_status_json_does_not_create_database(tmp_path: Path, monkeypatch, capsys):
    db = tmp_path / "lbd.sqlite3"
    session = tmp_path / "session.json"
    session.write_text(json.dumps({"cookie": "letterboxd.signed.in.as=exampleuser"}), encoding="utf-8")

    class Response(io.BytesIO):
        status = 200
        url = "https://letterboxd.com/"

        def __init__(self):
            super().__init__(b'person = { username: "exampleuser", loggedIn: true };')
            self.headers = {"content-type": "text/html"}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout=30: Response())

    assert main(["--db", str(db), "--session-file", str(session), "auth", "status", "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"signed_in": True, "username": "exampleuser"}
    assert not db.exists()


def test_web_watchlist_dry_run_builds_private_action(tmp_path: Path, monkeypatch, capsys):
    db = tmp_path / "lbd.sqlite3"

    class Response(io.BytesIO):
        url = "https://letterboxd.com/film/heat-1995/json/"
        status = 200

        def __init__(self):
            super().__init__(
                json.dumps(
                    {
                        "result": True,
                        "csrf": "csrf-token",
                        "name": "Heat",
                        "slug": "heat-1995",
                        "watchlistAction": "/film/heat-1995/add-to-watchlist/",
                    }
                ).encode()
            )
            self.headers = {"content-type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout=30: Response())
    assert (
        main(
            [
                "--db",
                str(db),
                "web",
                "watchlist",
                "remove",
                "heat-1995",
                "--dry-run",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "remove-from-watchlist" in out
    assert "csrf-token" not in out
    assert '"csrf": "[redacted]"' in out
    assert '"__csrf": "[redacted]"' in out


def test_web_log_dry_run_builds_diary_payload(tmp_path: Path, monkeypatch, capsys):
    db = tmp_path / "lbd.sqlite3"

    class Response(io.BytesIO):
        url = "https://letterboxd.com/film/heat-1995/json/"
        status = 200

        def __init__(self):
            super().__init__(
                json.dumps(
                    {
                        "result": True,
                        "csrf": "csrf-token",
                        "name": "Heat",
                        "uid": "film:51994",
                        "lid": "2bg8",
                        "slug": "heat-1995",
                    }
                ).encode()
            )
            self.headers = {"content-type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout=30: Response())
    assert (
        main(
            [
                "--db",
                str(db),
                "web",
                "log",
                "heat-1995",
                "--date",
                "2026-04-24",
                "--rating",
                "4.5",
                "--review",
                "Still rips.",
                "--tags",
                "crime,la",
                "--like",
                "--dry-run",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "/api/v0/production-log-entries" in out
    assert '"productionId": "2bg8"' in out
    assert '"rating": 4.5' in out
    assert '"diaryDate": "2026-04-24"' in out
    assert '"review"' in out
    assert '"tags": [' in out


def test_action_commands_build_log_payloads(tmp_path: Path, monkeypatch, capsys):
    db = tmp_path / "lbd.sqlite3"

    class Response(io.BytesIO):
        status = 200

        def __init__(self, url: str):
            super().__init__(
                json.dumps(
                    {
                        "result": True,
                        "csrf": "csrf-token",
                        "name": "Heat",
                        "uid": "film:51994",
                        "lid": "2bg8",
                        "slug": "heat-1995",
                    }
                ).encode()
            )
            self.url = url
            self.headers = {"content-type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout=30: Response(request.full_url))

    assert main(["--db", str(db), "rate", "heat-1995", "5", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert '"rating": 5.0' in out

    assert main(["--db", str(db), "review", "heat-1995", "Still rips.", "--rating", "4.5", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert '"text": "Still rips."' in out
    assert '"rating": 4.5' in out

    assert main(["--db", str(db), "heart", "heat-1995", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert '"like": true' in out

    assert main(["--db", str(db), "diary", "heat-1995", "--date", "2026-04-26", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert '"diaryDate": "2026-04-26"' in out
    assert '"rewatch": false' in out


def test_web_log_posts_current_production_log_api(tmp_path: Path, monkeypatch, capsys):
    db = tmp_path / "lbd.sqlite3"
    seen = {}

    class Response(io.BytesIO):
        status = 200

        def __init__(self, url: str, body: str):
            super().__init__(body.encode())
            self.url = url
            self.headers = {"content-type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    def fake_urlopen(request, timeout=30):
        if request.full_url.endswith("/film/heat-1995/json/"):
            return Response(
                request.full_url,
                json.dumps(
                    {
                        "result": True,
                        "csrf": "csrf-token",
                        "name": "Heat",
                        "uid": "film:51994",
                        "lid": "2bg8",
                        "slug": "heat-1995",
                    }
                ),
            )
        seen["url"] = request.full_url
        seen["method"] = request.get_method()
        seen["content_type"] = request.get_header("Content-type")
        seen["csrf"] = request.get_header("X-csrf-token")
        seen["body"] = json.loads(request.data.decode())
        return Response(request.full_url, json.dumps({"result": True, "logEntry": {"id": "viewing:1"}}))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert (
        main(
            [
                "--db",
                str(db),
                "web",
                "log",
                "heat-1995",
                "--date",
                "2026-04-24",
                "--rating",
                "4.5",
                "--review",
                "Still rips.",
            ]
        )
        == 0
    )
    assert seen["url"] == "https://letterboxd.com/api/v0/production-log-entries"
    assert seen["method"] == "POST"
    assert seen["content_type"] == "application/json; charset=UTF-8"
    assert seen["csrf"] == "csrf-token"
    assert seen["body"]["productionId"] == "2bg8"
    assert seen["body"]["diaryDetails"]["diaryDate"] == "2026-04-24"
    assert seen["body"]["review"]["text"] == "Still rips."


def test_web_rejects_non_letterboxd_urls_before_sending_cookie(tmp_path: Path, monkeypatch, capsys):
    db = tmp_path / "lbd.sqlite3"
    session = tmp_path / "session.json"
    session.write_text(json.dumps({"cookie": "letterboxd_session=test-session"}), encoding="utf-8")
    session.chmod(0o600)

    def fake_urlopen(_request, timeout=30):
        raise AssertionError("external request should not be made")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    assert (
        main(
            [
                "--db",
                str(db),
                "--session-file",
                str(session),
                "web",
                "get",
                "https://example.test/film/heat-1995/json/",
            ]
        )
        == 1
    )
    err = capsys.readouterr().err
    assert "different origin" in err


def test_saved_cookie_rejected_for_non_letterboxd_base_url(tmp_path: Path, monkeypatch, capsys):
    session = tmp_path / "session.json"
    session.write_text(json.dumps({"cookie": "letterboxd_session=test-session"}), encoding="utf-8")
    called = False

    def fake_urlopen(_request, timeout=30):
        nonlocal called
        called = True
        raise AssertionError("external request should not be made")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    assert (
        main(
            [
                "--session-file",
                str(session),
                "--base-url",
                "https://example.test",
                "web",
                "get",
                "/anything",
            ]
        )
        == 1
    )
    assert not called
    assert "non-Letterboxd base URL" in capsys.readouterr().err


def test_web_post_dry_run_redacts_csrf_from_output(tmp_path: Path, monkeypatch, capsys):
    db = tmp_path / "lbd.sqlite3"

    class Response(io.BytesIO):
        url = "https://letterboxd.com/film/heat-1995/json/"
        status = 200

        def __init__(self):
            super().__init__(b'<input name="csrf" value="csrf-token">')
            self.headers = {"content-type": "text/html"}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout=30: Response())

    assert (
        main(
            [
                "--db",
                str(db),
                "web",
                "post",
                "/film/heat-1995/add-to-watchlist/",
                "--csrf-from",
                "/film/heat-1995/json/",
                "--dry-run",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "csrf-token" not in out
    assert '"csrf": "[redacted]"' in out
    assert '"__csrf": "[redacted]"' in out


def test_web_post_dry_run_previews_json_body(tmp_path: Path, capsys):
    assert (
        main(
            [
                "web",
                "post",
                "/api/test",
                "--json-body",
                '{"rating":5,"csrf":"secret"}',
                "--dry-run",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["content_type"] == "application/json"
    assert payload["headers"]["Content-Type"] == "application/json"
    assert payload["body"] == {"rating": 5, "csrf": "[redacted]"}


def test_live_watchlist_fetches_and_saves_page_rows(tmp_path: Path, monkeypatch, capsys):
    db = tmp_path / "lbd.sqlite3"
    html = fixture_text("live_watchlist.html")

    class Response(io.BytesIO):
        status = 200
        url = "https://letterboxd.com/example/watchlist/"

        def __init__(self):
            super().__init__(html.encode())
            self.headers = {"content-type": "text/html"}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout=30: Response())
    assert (
        main(
            [
                "--db",
                str(db),
                "live",
                "watchlist",
                "example",
                "--save",
                "--format",
                "json",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "Heat" in out
    assert "Past Lives" in out

    with sqlite3.connect(db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM entries WHERE kind = 'watchlist'").fetchone()[0]
    assert count == 2


def test_live_me_detects_signed_in_username(tmp_path: Path, monkeypatch, capsys):
    db = tmp_path / "lbd.sqlite3"
    html = "person = { username: \"exampleuser\", loggedIn: true };"

    class Response(io.BytesIO):
        status = 200
        url = "https://letterboxd.com/"

        def __init__(self):
            super().__init__(html.encode())
            self.headers = {"content-type": "text/html"}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout=30: Response())
    assert main(["--db", str(db), "live", "me"]) == 0
    assert capsys.readouterr().out.strip() == "exampleuser"


def test_live_search_displays_and_saves_results(tmp_path: Path, monkeypatch, capsys):
    db = tmp_path / "lbd.sqlite3"
    html = """
    <html><body>
      <div class="react-component"
        data-component-class="LazyPoster"
        data-item-name="Heat (1995)"
        data-item-slug="heat-1995"
        data-item-link="/film/heat-1995/"></div>
      <div class="react-component"
        data-component-class="LazyPoster"
        data-item-name="Heat 2"
        data-item-slug="heat-2"
        data-item-link="/film/heat-2/"></div>
    </body></html>
    """

    seen = {}

    class Response(io.BytesIO):
        status = 200
        url = "https://letterboxd.com/search/films/heat/"

        def __init__(self):
            super().__init__(html.encode())
            self.headers = {"content-type": "text/html"}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    def fake_urlopen(request, timeout=30):
        seen["url"] = request.full_url
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert (
        main(
            [
                "--db",
                str(db),
                "live",
                "search",
                "heat",
                "--save",
                "--format",
                "json",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "Heat" in out
    assert "Heat 2" in out
    assert seen["url"] == "https://letterboxd.com/s/search/heat/"

    with sqlite3.connect(db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM entries WHERE kind = 'film'").fetchone()[0]
    assert count == 2


def test_live_search_hydrates_film_json(tmp_path: Path, monkeypatch, capsys):
    db = tmp_path / "lbd.sqlite3"
    search_html = """
    <html><body>
      <div class="react-component"
        data-component-class="LazyPoster"
        data-item-name="Heat (1995)"
        data-item-slug="heat-1995"
        data-item-link="/film/heat-1995/"></div>
    </body></html>
    """

    class Response(io.BytesIO):
        status = 200

        def __init__(self, url: str, body: str, content_type: str = "text/html"):
            super().__init__(body.encode())
            self.url = url
            self.headers = {"content-type": content_type}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    def fake_urlopen(request, timeout=30):
        if request.full_url.endswith("/film/heat-1995/json/"):
            return Response(
                request.full_url,
                json.dumps(
                    {
                        "result": True,
                        "name": "Heat",
                        "releaseYear": 1995,
                        "slug": "heat-1995",
                        "url": "/film/heat-1995/",
                        "directors": [{"name": "Michael Mann"}],
                    }
                ),
                "application/json",
            )
        return Response(request.full_url, search_html)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert (
        main(
            [
                "--db",
                str(db),
                "live",
                "search",
                "heat",
                "--hydrate",
                "--format",
                "json",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "Michael Mann" in out


def test_live_search_hydrates_member_rating(tmp_path: Path, monkeypatch, capsys):
    db = tmp_path / "lbd.sqlite3"
    session = tmp_path / "session.json"
    session.write_text(json.dumps({"cookie": "letterboxd.signed.in.as=exampleuser"}), encoding="utf-8")
    search_html = """
    <html><body>
      <div class="react-component"
        data-component-class="LazyPoster"
        data-item-name="Star Wars (1977)"
        data-item-slug="star-wars"
        data-item-link="/film/star-wars/"></div>
    </body></html>
    """
    sidebar_html = """
    <li class="actions-row1">
      <a href="/exampleuser/film/star-wars/diary/" class="action -watch -on">logged</a>
      <span data-is-liked="true"></span>
    </li>
    """
    diary_html = """
    <table class="diary-table"><tbody>
      <tr class="diary-entry-row">
        <a class="month" href="/exampleuser/film/star-wars/diary/for/2025/02/">Feb</a>
        <a class="daydate" href="/exampleuser/film/star-wars/1/">12</a>
        <input class="rateit-field" type="range" min="0" max="10" step="1" value="10" />
      </tr>
    </tbody></table>
    """

    class Response(io.BytesIO):
        status = 200

        def __init__(self, url: str, body: str, content_type: str = "text/html"):
            super().__init__(body.encode())
            self.url = url
            self.headers = {"content-type": content_type}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    def fake_urlopen(request, timeout=30):
        if request.full_url.endswith("/film/star-wars/json/"):
            return Response(
                request.full_url,
                json.dumps(
                    {
                        "result": True,
                        "name": "Star Wars",
                        "releaseYear": 1977,
                        "slug": "star-wars",
                        "url": "/film/star-wars/",
                        "directors": [{"name": "George Lucas"}],
                    }
                ),
                "application/json",
            )
        if "/sidebar-user-actions/" in request.full_url:
            return Response(request.full_url, sidebar_html)
        if request.full_url.endswith("/exampleuser/film/star-wars/diary/"):
            return Response(request.full_url, diary_html)
        return Response(request.full_url, search_html)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert (
        main(
            [
                "--db",
                str(db),
                "--session-file",
                str(session),
                "q",
                "Star Wars",
                "--live",
                "--hydrate",
                "--format",
                "json",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert '"rating": 5.0' in out
    assert '"date": "2025-02-12"' in out
    assert '"like": 1' in out


def test_query_live_save_then_local_query(tmp_path: Path, monkeypatch, capsys):
    db = tmp_path / "lbd.sqlite3"
    html = """
    <html><body>
      <div class="react-component"
        data-component-class="LazyPoster"
        data-item-name="Heat (1995)"
        data-item-slug="heat-1995"
        data-item-link="/film/heat-1995/"></div>
    </body></html>
    """

    class Response(io.BytesIO):
        status = 200
        url = "https://letterboxd.com/search/films/heat/"

        def __init__(self):
            super().__init__(html.encode())
            self.headers = {"content-type": "text/html"}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout=30: Response())
    assert (
        main(
            [
                "--db",
                str(db),
                "q",
                "heat",
                "--source",
                "live",
                "--save",
                "--format",
                "json",
            ]
        )
        == 0
    )
    assert "Heat" in capsys.readouterr().out

    assert main(["--db", str(db), "q", "heat", "--local", "--format", "json"]) == 0
    out = capsys.readouterr().out
    assert "Heat" in out
    assert '"source": "cache"' in out

    with sqlite3.connect(db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM entries WHERE kind = 'film'").fetchone()[0]
    assert count == 1


def test_query_defaults_to_live_and_marks_provenance(tmp_path: Path, monkeypatch, capsys):
    db = tmp_path / "lbd.sqlite3"
    html = """
    <html><body>
      <div class="react-component"
        data-component-class="LazyPoster"
        data-item-name="Heat (1995)"
        data-item-slug="heat-1995"
        data-item-link="/film/heat-1995/"></div>
    </body></html>
    """

    class Response(io.BytesIO):
        status = 200

        def __init__(self, url: str):
            super().__init__(html.encode())
            self.url = url
            self.headers = {"content-type": "text/html"}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    seen = {}

    def fake_urlopen(request, timeout=30):
        seen["url"] = request.full_url
        return Response(request.full_url)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert main(["--db", str(db), "q", "heat", "--format", "json"]) == 0
    out = capsys.readouterr().out
    assert seen["url"] == "https://letterboxd.com/s/search/heat/"
    assert '"source": "live"' in out


def test_query_live_flag_and_live_whoami_alias(tmp_path: Path, monkeypatch, capsys):
    db = tmp_path / "lbd.sqlite3"
    search_html = """
    <html><body>
      <div class="react-component"
        data-component-class="LazyPoster"
        data-item-name="Star Wars (1977)"
        data-item-slug="star-wars"
        data-item-link="/film/star-wars/"></div>
    </body></html>
    """

    class Response(io.BytesIO):
        status = 200

        def __init__(self, url: str, body: str):
            super().__init__(body.encode())
            self.url = url
            self.headers = {"content-type": "text/html"}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    def fake_urlopen(request, timeout=30):
        if request.full_url.endswith("/settings/"):
            return Response(request.full_url, "Account Settings for exampleuser")
        if "/s/search/" in request.full_url:
            return Response(request.full_url, search_html)
        if request.full_url.endswith("/"):
            return Response(request.full_url, 'person = { username: "", loggedIn: false };')
        return Response(request.full_url, "")

    session = tmp_path / "session.json"
    session.write_text(json.dumps({"cookie": "letterboxd.signed.in.as=exampleuser"}), encoding="utf-8")
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    assert main(["--db", str(db), "--session-file", str(session), "live", "whoami"]) == 0
    assert "exampleuser" in capsys.readouterr().out

    assert main(["--db", str(db), "--session-file", str(session), "q", "Star Wars", "--live"]) == 0
    assert "Star Wars (1977)" in capsys.readouterr().out


def test_film_details_include_poster_cast_and_crew(tmp_path: Path, monkeypatch, capsys):
    db = tmp_path / "lbd.sqlite3"
    film_json = {
        "result": True,
        "name": "Heat",
        "releaseYear": 1995,
        "slug": "heat-1995",
        "url": "/film/heat-1995/",
        "uid": "film:51994",
        "lid": "2bg8",
        "image230": "/film/heat-1995/image-230/",
        "watchlistAction": "/film/heat-1995/add-to-watchlist/",
        "directors": [{"name": "Michael Mann"}],
    }
    film_html = """
    <html><head><meta property="og:image" content="https://a.ltrbxd.com/poster.jpg"></head><body>
      <div class="react-component" data-component-class="LazyPoster" data-poster-url="/film/heat-1995/image-150/"></div>
      <div class="cast-list text-sluglist">
        <a href="/actor/al-pacino/" title="Lt. Vincent Hanna">Al Pacino</a>
        <a href="/actor/robert-de-niro/" title="Neil McCauley">Robert De Niro</a>
      </div>
    </body></html>
    """
    crew_html = """
    <div id="tab-crew">
      <h3><span class="crewrole -full">Director</span></h3>
      <div class="text-sluglist"><a href="/director/michael-mann/">Michael Mann</a></div>
      <h3><span class="crewrole -full">Writer</span></h3>
      <div class="text-sluglist"><a href="/writer/michael-mann/">Michael Mann</a></div>
    </div>
    """

    class Response(io.BytesIO):
        status = 200

        def __init__(self, url: str, body: str, content_type: str = "text/html"):
            super().__init__(body.encode())
            self.url = url
            self.headers = {"content-type": content_type}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    def fake_urlopen(request, timeout=30):
        if request.full_url.endswith("/film/heat-1995/json/"):
            return Response(request.full_url, json.dumps(film_json), "application/json")
        if request.full_url.endswith("/film/heat-1995/crew/"):
            return Response(request.full_url, crew_html)
        return Response(request.full_url, film_html)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert main(["--db", str(db), "film", "heat-1995", "--format", "json"]) == 0
    out = capsys.readouterr().out
    assert '"name": "Heat"' in out
    assert '"image230": "https://letterboxd.com/film/heat-1995/image-230/"' in out
    assert '"name": "Al Pacino"' in out
    assert '"character": "Lt. Vincent Hanna"' in out
    assert '"Director"' in out


def test_watch_fetches_signed_in_availability_services(tmp_path: Path, monkeypatch, capsys):
    db = tmp_path / "lbd.sqlite3"
    session = tmp_path / "session.json"
    session.write_text(json.dumps({"cookie": "letterboxd.signed.in.as=exampleuser"}), encoding="utf-8")
    availability_html = """
    <section class="watch-panel js-watch-panel">
      <p class="trailer-link js-watch-panel-trailer">
        <a href="//www.youtube.com/embed/example"><span class="name">Trailer</span></a>
      </p>
      <div id="watch">
        <section class="services">
          <p id="source-netflix" class="service -netflix">
            <a href="https://click.justwatch.com/netflix" class="label track-event tooltip"
              title="View on Netflix" data-track-action="availability"
              data-track-params='{"service": "netflix"}' target="_blank">
              <span class="brand"><img src="https://example.test/netflix.png" title="Netflix GB" alt="Netflix GB" /></span>
              <span class="title"><span class="name">Netflix</span> <span class="locale">GB</span></span>
            </a>
            <span class="options js-film-availability-options">
              <a class="link -stream track-event" href="https://click.justwatch.com/netflix" title="Watch at Netflix GB">
                <span class="extended">Play</span>
              </a>
            </span>
          </p>
          <p id="source-apple-itunes" class="service -apple-itunes">
            <a href="https://click.justwatch.com/apple" class="label track-event tooltip" title="View on Apple TV Store">
              <span class="brand"><img src="/apple.png" title="Apple TV Store GB" alt="Apple TV Store GB" /></span>
              <span class="title"><span class="name">Apple TV Store</span> <span class="locale">GB</span></span>
            </a>
            <span class="options js-film-availability-options">
              <a class="link -rent track-event" href="https://click.justwatch.com/rent" title="Rent from Apple TV Store GB">
                <span class="extended">Rent</span>
              </a>
              <a class="link -buy track-event" href="https://click.justwatch.com/buy" title="Buy from Apple TV Store GB">
                <span class="extended">Buy</span>
              </a>
            </span>
          </p>
        </section>
        <div class="other">
          <a href="/film/heat-1995/watch/" data-availability-href="/csi/film/heat-1995/justwatch/?esiAllowUser=true"
            class="more track-event js-film-availability-link" data-url="/s/production-availabilities?productionUID=film:51994">
            All services
          </a>
          <a href="https://www.justwatch.com/uk/movie/heat" class="jw-branding">JustWatch</a>
        </div>
      </div>
    </section>
    """

    class Response(io.BytesIO):
        status = 200

        def __init__(self, url: str, body: str):
            super().__init__(body.encode())
            self.url = url
            self.headers = {"content-type": "text/html"}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    def fake_urlopen(request, timeout=30):
        if request.full_url == "https://letterboxd.com/":
            return Response(request.full_url, 'person = { username: "exampleuser", loggedIn: true };')
        if request.full_url.endswith("/csi/film/heat-1995/availability/?esiAllowUser=true&esiAllowCountry=true"):
            return Response(request.full_url, availability_html)
        return Response(request.full_url, "")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert main(["--db", str(db), "--session-file", str(session), "watch", "heat-1995", "--format", "json"]) == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["user"] == "exampleuser"
    assert payload["services"][0]["service"] == "Netflix"
    assert payload["services"][0]["option_types"] == ["stream"]
    assert payload["services"][1]["option_types"] == ["buy", "rent"]
    assert payload["extras"]["justwatch_url"] == "https://www.justwatch.com/uk/movie/heat"


def test_watch_recovers_from_noncanonical_year_slug(tmp_path: Path, monkeypatch, capsys):
    db = tmp_path / "lbd.sqlite3"
    session = tmp_path / "session.json"
    session.write_text(json.dumps({"cookie": "letterboxd.signed.in.as=exampleuser"}), encoding="utf-8")
    availability_html = """
    <section class="watch-panel js-watch-panel">
      <section class="services">
        <p id="source-amazon-prime" class="service -amazon-prime">
          <a href="https://click.justwatch.com/prime" class="label">
            <span class="title"><span class="name">Amazon Prime Video</span> <span class="locale">GB</span></span>
          </a>
          <span class="options"><a class="link -stream" href="https://click.justwatch.com/prime">Play</a></span>
        </p>
      </section>
    </section>
    """
    search_html = '<a href="/film/challengers/">Challengers (2024)</a>'

    class Response(io.BytesIO):
        def __init__(self, url: str, body: str, status: int = 200):
            super().__init__(body.encode())
            self.url = url
            self.status = status
            self.headers = {"content-type": "text/html"}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    def fake_urlopen(request, timeout=30):
        if request.full_url == "https://letterboxd.com/":
            return Response(request.full_url, 'person = { username: "exampleuser", loggedIn: true };')
        if request.full_url.endswith("/csi/film/challengers-2024/availability/?esiAllowUser=true&esiAllowCountry=true"):
            raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, io.BytesIO(b"missing"))
        if request.full_url.endswith("/s/search/challengers/"):
            return Response(request.full_url, search_html)
        if request.full_url.endswith("/csi/film/challengers/availability/?esiAllowUser=true&esiAllowCountry=true"):
            return Response(request.full_url, availability_html)
        return Response(request.full_url, "")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert main(["--db", str(db), "--session-file", str(session), "where-to-watch", "challengers-2024", "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["film"] == "challengers"
    assert payload["requested_slug"] == "challengers-2024"
    assert payload["services"][0]["service"] == "Amazon Prime Video"


def test_people_search_lists_contributors(tmp_path: Path, monkeypatch, capsys):
    db = tmp_path / "lbd.sqlite3"
    search_html = """
    <html><body>
      <li class="search-result -contributor -actor">
        <h2><a href="/actor/al-pacino/">Al Pacino</a></h2>
        <p class="film-metadata">Star of 117 films, including Heat</p>
      </li>
      <li class="search-result -contributor -director">
        <h2><a href="/director/al-pacino/">Al Pacino</a></h2>
        <p class="film-metadata">Director of 4 films</p>
      </li>
    </body></html>
    """

    class Response(io.BytesIO):
        status = 200

        def __init__(self, url: str):
            super().__init__(search_html.encode())
            self.url = url
            self.headers = {"content-type": "text/html"}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout=30: Response(request.full_url))
    assert main(["--db", str(db), "people", "al pacino", "--format", "json"]) == 0
    out = capsys.readouterr().out
    assert '"role": "actor"' in out
    assert '"url": "https://letterboxd.com/actor/al-pacino/"' in out
    assert "Star of 117 films" in out


def test_lists_search_finds_live_letterboxd_lists(tmp_path: Path, monkeypatch, capsys):
    db = tmp_path / "lbd.sqlite3"
    html = """
    <ul class="results">
      <li class="search-result -list">
        <article class="list-summary js-list-summary js-list" data-film-list-id="7652235" data-person="SeanFennessey">
          <a href="/seanfennessey/list/spread-em-erotic-thrillers-1980-2005/" class="poster-list-link">
            <div class="react-component"
              data-component-class="LazyPoster"
              data-item-name="Dressed to Kill (1980)"
              data-item-slug="dressed-to-kill-1980"
              data-item-link="/film/dressed-to-kill-1980/"></div>
          </a>
          <h2 class="name prettify">
            <a href="/seanfennessey/list/spread-em-erotic-thrillers-1980-2005/">Spread 'Em! Erotic Thrillers, 1980-2005</a>
          </h2>
          <a class="owner" href="/seanfennessey/"><strong class="displayname">Sean Fennessey</strong></a>
          <span class="value">63&nbsp;films</span>
          <a href="/seanfennessey/list/spread-em-erotic-thrillers-1980-2005/likes/" class="metadata"><span class="label">997</span></a>
          <div class="notes body-text"><p>Ringer list.</p></div>
        </article>
      </li>
    </ul>
    """

    class Response(io.BytesIO):
        status = 200

        def __init__(self, url: str):
            super().__init__(html.encode())
            self.url = url
            self.headers = {"content-type": "text/html"}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    seen = {}

    def fake_urlopen(request, timeout=30):
        seen["url"] = request.full_url
        return Response(request.full_url)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert (
        main(
            [
                "--db",
                str(db),
                "lists",
                "spread em erotic thrillers",
                "--user",
                "seanfennessey",
                "--format",
                "json",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert seen["url"] == "https://letterboxd.com/s/search/spread%20em%20erotic%20thrillers/"
    assert '"name": "Spread \'Em! Erotic Thrillers, 1980-2005"' in out
    assert '"owner_username": "SeanFennessey"' in out
    assert '"films": 63' in out
    assert '"detail_url": "https://letterboxd.com/seanfennessey/list/spread-em-erotic-thrillers-1980-2005/detail/"' in out
    assert '"source": "live"' in out


def test_lists_search_filters_low_quality_lists_by_default(tmp_path: Path, monkeypatch, capsys):
    db = tmp_path / "lbd.sqlite3"
    html = """
    <ul class="results">
      <li class="search-result -list">
        <article class="list-summary js-list-summary js-list" data-person="gooduser">
          <h2 class="name prettify"><a href="/gooduser/list/erotic-thrillers/">Erotic Thrillers</a></h2>
          <a class="owner" href="/gooduser/"><strong class="displayname">Good User</strong></a>
          <span class="value">42&nbsp;films</span>
          <a href="/gooduser/list/erotic-thrillers/likes/" class="metadata"><span class="label">150</span></a>
          <a href="/gooduser/list/erotic-thrillers/#comments" class="metadata"><span class="label">12</span></a>
          <div class="notes body-text"><p>Curated and ordered.</p></div>
        </article>
      </li>
      <li class="search-result -list">
        <article class="list-summary js-list-summary js-list" data-person="junkuser">
          <h2 class="name prettify"><a href="/junkuser/list/copy/">Copy</a></h2>
          <a class="owner" href="/junkuser/"><strong class="displayname">Junk User</strong></a>
          <span class="value">2&nbsp;films</span>
        </article>
      </li>
    </ul>
    """

    class Response(io.BytesIO):
        status = 200

        def __init__(self, url: str):
            super().__init__(html.encode())
            self.url = url
            self.headers = {"content-type": "text/html"}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout=30: Response(request.full_url))

    assert main(["--db", str(db), "lists", "erotic thrillers", "--format", "json"]) == 0
    out = capsys.readouterr().out
    assert "Erotic Thrillers" in out
    assert "Junk User" not in out
    assert '"quality_score":' in out

    assert main(["--db", str(db), "lists", "erotic thrillers", "--include-junk", "--format", "json"]) == 0
    out = capsys.readouterr().out
    assert "Junk User" in out
    assert '"quality_flags":' in out


def test_lists_search_boosts_followed_owners(tmp_path: Path, monkeypatch, capsys):
    db = tmp_path / "lbd.sqlite3"
    following_html = """
    <table>
      <tr>
        <td class="col-member table-person">
          <div class="person-summary">
            <h3><a href="/followeduser/" class="name">Followed User</a></h3>
          </div>
        </td>
        <td><div class="follow-button-wrapper" data-username="followeduser"></div></td>
      </tr>
    </table>
    """
    search_html = """
    <ul class="results">
      <li class="search-result -list">
        <article class="list-summary js-list-summary js-list" data-person="randomuser">
          <h2 class="name prettify"><a href="/randomuser/list/erotic-thrillers/">Erotic Thrillers</a></h2>
          <a class="owner" href="/randomuser/"><strong class="displayname">Random User</strong></a>
          <span class="value">120&nbsp;films</span>
          <a href="/randomuser/list/erotic-thrillers/likes/" class="metadata"><span class="label">900</span></a>
        </article>
      </li>
      <li class="search-result -list">
        <article class="list-summary js-list-summary js-list" data-person="followeduser">
          <h2 class="name prettify"><a href="/followeduser/list/erotic-thrillers/">Erotic Thrillers</a></h2>
          <a class="owner" href="/followeduser/"><strong class="displayname">Followed User</strong></a>
          <span class="value">30&nbsp;films</span>
          <a href="/followeduser/list/erotic-thrillers/likes/" class="metadata"><span class="label">3</span></a>
        </article>
      </li>
    </ul>
    """

    class Response(io.BytesIO):
        status = 200

        def __init__(self, url: str, body: str):
            super().__init__(body.encode())
            self.url = url
            self.headers = {"content-type": "text/html"}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    def fake_urlopen(request, timeout=30):
        if "/exampleuser/following/" in request.full_url:
            return Response(request.full_url, following_html)
        return Response(request.full_url, search_html)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert (
        main(
            [
                "--db",
                str(db),
                "--cookie",
                "letterboxd.signed.in.as=exampleuser",
                "lists",
                "erotic thrillers",
                "--format",
                "json",
            ]
        )
        == 0
    )
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["owner_username"] == "followeduser"
    assert rows[0]["owner_followed"] is True
    assert "owner is followed" in rows[0]["quality_reasons"]

    assert (
        main(
            [
                "--db",
                str(db),
                "--cookie",
                "letterboxd.signed.in.as=exampleuser",
                "lists",
                "erotic thrillers",
                "--only-following",
                "--format",
                "json",
            ]
        )
        == 0
    )
    rows = json.loads(capsys.readouterr().out)
    assert [row["owner_username"] for row in rows] == ["followeduser"]


def test_person_filmography_lists_films_with_posters(tmp_path: Path, monkeypatch, capsys):
    db = tmp_path / "lbd.sqlite3"
    person_html = """
    <html><body>
      <div class="react-component"
        data-component-class="LazyPoster"
        data-item-name="Heat (1995)"
        data-item-slug="heat-1995"
        data-item-link="/film/heat-1995/"
        data-poster-url="/film/heat-1995/image-150/"></div>
    </body></html>
    """

    class Response(io.BytesIO):
        status = 200

        def __init__(self, url: str):
            super().__init__(person_html.encode())
            self.url = url
            self.headers = {"content-type": "text/html"}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    seen = {}

    def fake_urlopen(request, timeout=30):
        seen["url"] = request.full_url
        return Response(request.full_url)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert (
        main(
            [
                "--db",
                str(db),
                "person",
                "Michael Mann",
                "--role",
                "director",
                "--format",
                "json",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert seen["url"] == "https://letterboxd.com/director/michael-mann/"
    assert '"name": "Heat"' in out
    assert '"person_role": "director"' in out
    assert '"poster_url": "https://letterboxd.com/film/heat-1995/image-150/"' in out


def test_films_uses_letterboxd_csi_filter_route(tmp_path: Path, monkeypatch, capsys):
    db = tmp_path / "lbd.sqlite3"
    html = """
    <html><body>
      <div class="react-component"
        data-component-class="LazyPoster"
        data-item-name="Heat (1995)"
        data-item-slug="heat-1995"
        data-item-link="/film/heat-1995/"
        data-poster-url="/film/heat-1995/image-150/"></div>
    </body></html>
    """

    class Response(io.BytesIO):
        status = 200

        def __init__(self, url: str):
            super().__init__(html.encode())
            self.url = url
            self.headers = {"content-type": "text/html"}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    seen = {}

    def fake_urlopen(request, timeout=30):
        seen["url"] = request.full_url
        return Response(request.full_url)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert (
        main(
            [
                "--db",
                str(db),
                "films",
                "--genre",
                "crime",
                "--decade",
                "1990",
                "--sort",
                "rating",
                "--format",
                "json",
            ]
        )
        == 0
    )
    assert seen["url"] == (
        "https://letterboxd.com/csi/films/films-browser-list/by/rating/decade/1990s/genre/crime/"
        "?esiAllowFilters=true"
    )
    out = capsys.readouterr().out
    assert '"name": "Heat"' in out
    assert '"poster_url": "https://letterboxd.com/film/heat-1995/image-150/"' in out


def test_person_filters_append_to_person_film_set(tmp_path: Path, monkeypatch, capsys):
    db = tmp_path / "lbd.sqlite3"
    html = """
    <html><body>
      <div class="react-component"
        data-component-class="LazyPoster"
        data-item-name="Heat (1995)"
        data-item-slug="heat-1995"
        data-item-link="/film/heat-1995/"></div>
    </body></html>
    """

    class Response(io.BytesIO):
        status = 200

        def __init__(self, url: str):
            super().__init__(html.encode())
            self.url = url
            self.headers = {"content-type": "text/html"}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    seen = {}

    def fake_urlopen(request, timeout=30):
        seen["url"] = request.full_url
        return Response(request.full_url)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert (
        main(
            [
                "--db",
                str(db),
                "person",
                "Michael Mann",
                "--role",
                "director",
                "--genre",
                "crime",
                "--year",
                "1995",
            ]
        )
        == 0
    )
    assert seen["url"] == "https://letterboxd.com/director/michael-mann/year/1995/genre/crime/"
    assert "Heat (1995)" in capsys.readouterr().out


def test_live_collection_filters_append_to_account_set(tmp_path: Path, monkeypatch, capsys):
    db = tmp_path / "lbd.sqlite3"
    html = """
    <html><body>
      <div class="react-component"
        data-component-class="LazyPoster"
        data-item-name="Heat (1995)"
        data-item-slug="heat-1995"
        data-item-link="/film/heat-1995/"></div>
    </body></html>
    """

    class Response(io.BytesIO):
        status = 200

        def __init__(self, url: str):
            super().__init__(html.encode())
            self.url = url
            self.headers = {"content-type": "text/html"}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    seen = {}

    def fake_urlopen(request, timeout=30):
        seen["url"] = request.full_url
        return Response(request.full_url)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert main(["--db", str(db), "live", "watchlist", "exampleuser", "--genre", "crime", "--decade", "1990s"]) == 0
    assert seen["url"] == "https://letterboxd.com/exampleuser/watchlist/decade/1990s/genre/crime/"
    assert "Heat (1995)" in capsys.readouterr().out


def test_recs_excludes_watched_and_scores_bias_people(tmp_path: Path, monkeypatch, capsys):
    db = tmp_path / "lbd.sqlite3"
    candidates_html = """
    <html><body>
      <div class="react-component"
        data-component-class="LazyPoster"
        data-item-name="Heat (1995)"
        data-item-slug="heat-1995"
        data-item-link="/film/heat-1995/"
        data-poster-url="/film/heat-1995/image-150/"></div>
      <div class="react-component"
        data-component-class="LazyPoster"
        data-item-name="Casino (1995)"
        data-item-slug="casino"
        data-item-link="/film/casino/"
        data-poster-url="/film/casino/image-150/"></div>
    </body></html>
    """
    watched_html = """
    <html><body>
      <div class="react-component"
        data-component-class="LazyPoster"
        data-item-name="Casino (1995)"
        data-item-slug="casino"
        data-item-link="/film/casino/"></div>
    </body></html>
    """
    heat_html = """
    <html><body>
      <div class="cast-list text-sluglist">
        <a href="/actor/al-pacino/" title="Lt. Vincent Hanna">Al Pacino</a>
      </div>
    </body></html>
    """
    heat_crew = """
    <h3><span class="crewrole -full">Director</span></h3>
    <div class="text-sluglist"><a href="/director/michael-mann/">Michael Mann</a></div>
    """
    heat_json = {
        "result": True,
        "name": "Heat",
        "releaseYear": 1995,
        "slug": "heat-1995",
        "url": "/film/heat-1995/",
        "image150": "/film/heat-1995/image-150/",
        "directors": [{"name": "Michael Mann"}],
    }

    class Response(io.BytesIO):
        status = 200

        def __init__(self, url: str, body: str, content_type: str = "text/html"):
            super().__init__(body.encode())
            self.url = url
            self.headers = {"content-type": content_type}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    def fake_urlopen(request, timeout=30):
        url = request.full_url
        if "/csi/films/films-browser-list/" in url:
            return Response(url, candidates_html)
        if url.endswith("/exampleuser/films/year/1995/genre/crime/"):
            return Response(url, watched_html)
        if url.endswith("/film/heat-1995/json/"):
            return Response(url, json.dumps(heat_json), "application/json")
        if url.endswith("/film/heat-1995/crew/"):
            return Response(url, heat_crew)
        if url.endswith("/film/heat-1995/"):
            return Response(url, heat_html)
        return Response(url, "<html></html>")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert (
        main(
            [
                "--db",
                str(db),
                "recs",
                "--username",
                "exampleuser",
                "--genre",
                "crime",
                "--year",
                "1995",
                "--bias-person",
                "Michael Mann",
                "--bias-person",
                "Al Pacino",
                "--no-taste-from-ratings",
                "--format",
                "json",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert '"name": "Heat"' in out
    assert "Casino" not in out
    assert '"director match: Michael Mann"' in out
    assert '"cast match: Al Pacino"' in out
    assert '"candidate_source": "live"' in out
    assert '"watched_exclusion"' in out
    assert '"source": "live"' in out


def test_recs_accepts_list_url_passed_as_query_for_compatibility(tmp_path: Path, monkeypatch, capsys):
    db = tmp_path / "lbd.sqlite3"
    list_html = """
    <html><body>
      <div class="react-component"
        data-component-class="LazyPoster"
        data-item-name="Body Heat (1981)"
        data-item-slug="body-heat"
        data-item-link="/film/body-heat/"
        data-poster-url="/film/body-heat/image-150/"></div>
    </body></html>
    """
    film_json = {
        "result": True,
        "name": "Body Heat",
        "releaseYear": 1981,
        "slug": "body-heat",
        "url": "/film/body-heat/",
        "image150": "/film/body-heat/image-150/",
        "directors": [{"name": "Lawrence Kasdan"}],
    }

    class Response(io.BytesIO):
        status = 200

        def __init__(self, url: str, body: str, content_type: str = "text/html"):
            super().__init__(body.encode())
            self.url = url
            self.headers = {"content-type": content_type}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    seen = []

    def fake_urlopen(request, timeout=30):
        url = request.full_url
        seen.append(url)
        if url.endswith("/film/body-heat/json/"):
            return Response(url, json.dumps(film_json), "application/json")
        if url.endswith("/film/body-heat/crew/") or url.endswith("/film/body-heat/"):
            return Response(url, "<html></html>")
        return Response(url, list_html)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert (
        main(
            [
                "--db",
                str(db),
                "recs",
                "--username",
                "exampleuser",
                "--query",
                "https://letterboxd.com/seanfennessey/list/spread-em-erotic-thrillers-1980-2005/detail/",
                "--decade",
                "1980",
                "--include-watched",
                "--no-taste-from-ratings",
                "--format",
                "json",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert seen[0] == "https://letterboxd.com/seanfennessey/list/spread-em-erotic-thrillers-1980-2005/detail/by/rating/decade/1980s/"
    assert '"name": "Body Heat"' in out
