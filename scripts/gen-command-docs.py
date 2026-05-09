from __future__ import annotations

import argparse
import contextlib
import io
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from letterboxd_cli.cli import build_parser


DOC_WIDTH = 120


class StableHelpFormatter(argparse.HelpFormatter):
    def __init__(self, prog: str) -> None:
        super().__init__(prog, width=DOC_WIDTH, max_help_position=28)


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if len(argv) != 1:
        print("usage: gen-command-docs.py <output-path>", file=sys.stderr)
        return 2

    parser = build_parser()
    configure_formatters(parser)
    output_path = Path(argv[0])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_command_docs(parser), encoding="utf-8")
    return 0


def render_command_docs(parser: argparse.ArgumentParser) -> str:
    chunks = [
        "# Command Reference",
        "",
        "Generated from the current argparse parser. Regenerate with:",
        "",
        "```bash",
        "make docs",
        "```",
        "",
        "## Usage Notes",
        "",
        "- Global flags such as `--json`, `--plain`, `--db`, `--session-file`, and `--no-input` go before the command: `lbd --json q \"Heat\"`.",
        "- Per-command output flags go after the command: `lbd q \"Heat\" --format json`.",
        "- Commands under `web`, `login`, `auth`, `whoami`, and signed-in availability/actions use the saved or provided browser session.",
        "- State-changing commands support `--dry-run` where available and redact CSRF/session-style values in previews.",
        "- `live sync` and account collection commands need either an explicit username or a signed-in session that can reveal the username.",
        "- `sql` opens the local database read-only and never creates a missing database.",
        "",
        "## `lbd`",
        "",
        "```text",
        help_text(parser).strip(),
        "```",
    ]

    for command, subparser in iter_commands(parser):
        chunks.extend(
            [
                "",
                f"## `lbd {' '.join(command)}`",
                "",
                "```text",
                help_text(subparser).strip(),
                "```",
            ]
        )

    return "\n".join(chunks) + "\n"


def iter_commands(
    parser: argparse.ArgumentParser,
    prefix: tuple[str, ...] = (),
) -> list[tuple[tuple[str, ...], argparse.ArgumentParser]]:
    commands: list[tuple[tuple[str, ...], argparse.ArgumentParser]] = []
    for action in parser._actions:
        if not isinstance(action, argparse._SubParsersAction):
            continue

        seen: set[int] = set()
        for name, subparser in action.choices.items():
            if id(subparser) in seen:
                continue
            seen.add(id(subparser))
            command = (*prefix, name)
            commands.append((command, subparser))
            commands.extend(iter_commands(subparser, command))
    return commands


def help_text(parser: argparse.ArgumentParser) -> str:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        parser.print_help()
    return normalize_help_text(buffer.getvalue())


def configure_formatters(parser: argparse.ArgumentParser) -> None:
    parser.formatter_class = StableHelpFormatter
    for _, subparser in iter_commands(parser):
        subparser.formatter_class = StableHelpFormatter


def normalize_help_text(text: str) -> str:
    # Python 3.13 changed how argparse renders options with both long and short
    # forms. Keep generated docs stable across the supported Python matrix.
    text = re.sub(r"--([a-z0-9][a-z0-9-]*) ([A-Z][A-Z0-9_-]*), -([a-z]) \2", r"--\1, -\3 \2", text)
    text = re.sub(r"(\{[^\n{}]+\})\n(\s+)\.\.\.", r"\1 ...", text)
    return re.sub(
        r"^(  --[a-z0-9][a-z0-9-]*, -[a-z] [A-Z][A-Z0-9_-]*)(\s+)(\S.*)$",
        align_option_description,
        text,
        flags=re.MULTILINE,
    )


def align_option_description(match: re.Match[str]) -> str:
    option = match.group(1)
    description = match.group(3)
    return f"{option}{' ' * max(1, 28 - len(option))}{description}"


if __name__ == "__main__":
    raise SystemExit(main())
