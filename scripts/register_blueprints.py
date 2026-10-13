"""Register the WBMS-Lite blueprints inside ``create_app`` (safe to run twice).

Usage, from the project root::

    python scripts/register_blueprints.py            # edit src/wbms/__init__.py
    python scripts/register_blueprints.py --check    # only report, change nothing

It adds, just before the single ``return app`` line of ``create_app``::

    from wbms.web.api_packages import bp as api_packages_bp
    from wbms.web.portal import bp as portal_bp

    app.register_blueprint(api_packages_bp)
    app.register_blueprint(portal_bp)

Lines that are already present are skipped, so running it again changes
nothing. If the file does not look the way this script expects, it prints what
to do by hand and leaves the file alone.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

TARGET = Path("src") / "wbms" / "__init__.py"

# (import line, register line) pairs, in the order they are added.
BLUEPRINTS: list[tuple[str, str]] = [
    (
        "from wbms.web.api_packages import bp as api_packages_bp",
        "app.register_blueprint(api_packages_bp)",
    ),
    (
        "from wbms.web.portal import bp as portal_bp",
        "app.register_blueprint(portal_bp)",
    ),
]

_RETURN_APP = re.compile(r"^(?P<indent>[ \t]+)return app[ \t]*$")


def plan_edit(text: str) -> tuple[str, list[str]]:
    """Return ``(new_text, messages)`` for the given file contents.

    ``new_text`` equals ``text`` when nothing needs adding or the file cannot be
    edited safely; ``messages`` says which of those happened.
    """
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(newline)

    missing = [
        (imp, reg)
        for imp, reg in BLUEPRINTS
        if not any(line.strip() == reg for line in lines)
    ]
    if not missing:
        return text, ["Nothing to do: every blueprint is already registered."]

    positions = [i for i, line in enumerate(lines) if _RETURN_APP.match(line)]
    if len(positions) != 1:
        return text, [
            f"Found {len(positions)} lines reading 'return app' (expected exactly 1), "
            "so nothing was changed. Add these lines by hand, with 4 spaces of indent, "
            "just before the final 'return app' in create_app:",
            *[f"    {imp}" for imp, _ in missing],
            *[f"    {reg}" for _, reg in missing],
        ]

    index = positions[0]
    found = _RETURN_APP.match(lines[index])
    assert found is not None  # positions only holds lines that matched
    indent = found.group("indent")

    block: list[str] = []
    for imp, _ in missing:
        if not any(line.strip() == imp for line in lines):
            block.append(indent + imp)
    if block:
        block.append("")
    block.extend(indent + reg for _, reg in missing)
    block.append("")

    # Keep one blank line between earlier code and the new block.
    if index > 0 and lines[index - 1].strip() != "":
        block.insert(0, "")

    new_lines = lines[:index] + block + lines[index:]
    done = [f"Registered: {reg}" for _, reg in missing]
    return newline.join(new_lines), done


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="report only")
    parser.add_argument(
        "--file", type=Path, default=TARGET, help="file to edit (default: %(default)s)"
    )
    args = parser.parse_args(argv)

    if not args.file.is_file():
        print(f"Cannot find {args.file}. Run this from the project root.")
        return 2

    original = args.file.read_bytes().decode("utf-8")
    updated, messages = plan_edit(original)
    for message in messages:
        print(message)

    if updated == original:
        return 0 if messages[0].startswith("Nothing to do") else 1
    if args.check:
        print("(--check: file not changed)")
        return 1

    # newline="" style write: keep the file's own line endings untouched.
    args.file.write_bytes(updated.encode("utf-8"))
    print(f"Updated {args.file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
