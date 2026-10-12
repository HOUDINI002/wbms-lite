#!/usr/bin/env python3
"""Scaffold the WBMS-Lite project tree (slide 25 of the teaching deck).

Creates the folder and file structure for the ``wbms-lite`` project:

* empty ``__init__.py`` files in every Python package,
* placeholder ``README.md`` files in ``docs/`` and ``tests/``,
* a ``.env.example`` containing keys only, with fake values,
* a one-line placeholder in every other file, pointing at the deck slide
  that fills it in.

Safe by design: it NEVER overwrites a file that already exists, it prints
what was created and what was skipped, and ``--dry-run`` shows the plan
without touching the disk.

Usage. Keep this file at <project>/scripts/scaffold.py; the project root is
then the folder above scripts/. If the file lives anywhere else it refuses
to guess and asks for --root:

    python scripts/scaffold.py --dry-run
    python scripts/scaffold.py
    python scaffold.py --root . --dry-run     (file not inside scripts/)
"""

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

class StrEnum(str, Enum):
    def __str__(self):
        return str(self.value)
from pathlib import Path  # noqa: E402

PROJECT_NAME = "wbms-lite"
PACKAGE_NAME = "wbms"

# Content of .env.example: keys only, fake values. Names come from the deck:
# Settings (slide 60), seed admin password (slide 62), MikroTik (slide 72),
# sandbox testing callback URL (slide 93).
ENV_EXAMPLE = """\
# Copy to .env and fill in real values. NEVER commit .env (only this file).
# Every value below is a fake placeholder.

# --- Core ---
SECRET_KEY=change-me-to-a-long-random-string
DATABASE_PATH=instance/wbms.sqlite3

# --- Adapters: mock or real ---
PAYMENT_GATEWAY=mock
ROUTER_ADAPTER=mock

# --- Payment callback protection ---
CALLBACK_SECRET=change-me-callback-secret
CALLBACK_URL=https://example.ngrok.app/api/payments/callback/change-me-callback-secret

# --- Daraja (M-Pesa) sandbox: only used when PAYMENT_GATEWAY=daraja ---
DARAJA_CONSUMER_KEY=fake-consumer-key
DARAJA_CONSUMER_SECRET=fake-consumer-secret
DARAJA_SHORTCODE=174379
DARAJA_PASSKEY=fake-passkey
DARAJA_BASE_URL=https://sandbox.safaricom.co.ke

# --- MikroTik: only used when ROUTER_ADAPTER=mikrotik ---
MIKROTIK_HOST=192.0.2.1
MIKROTIK_PORT=8729
MIKROTIK_USERNAME=fake-api-user
MIKROTIK_PASSWORD=fake-router-password
MIKROTIK_USE_SSL=true

# --- Seed script (scripts/seed.py) ---
ADMIN_PASSWORD=change-me-admin-password
"""

# Directories that exist even if they end up holding no file of their own.
# Leaf directories with no files get a .gitkeep so Git tracks them.
DIRECTORIES: tuple[str, ...] = (
    "docs/adr",
    "scripts",
    "src/wbms/repositories",
    "src/wbms/services",
    "src/wbms/gateways/payments",
    "src/wbms/gateways/routers",
    "src/wbms/web/templates",
    "src/wbms/web/static",
    "tests/unit",
    "tests/integration",
)

# Python packages (get an empty __init__.py).
PACKAGES: tuple[str, ...] = (
    "src/wbms",
    "src/wbms/repositories",
    "src/wbms/services",
    "src/wbms/gateways",
    "src/wbms/gateways/payments",
    "src/wbms/gateways/routers",
    "src/wbms/web",
)

# Files with real starter content (the rest are one-line PLACEHOLDERS below).
FILE_CONTENT: dict[str, str] = {
    ".env.example": ENV_EXAMPLE,
    "docs/README.md": "# Docs\n\nDesign notes, diagrams and API docs for WBMS-Lite.\n",
    "docs/adr/README.md": (
        "# Architecture decision records\n\n"
        "One short note per decision (why Flask, why SQLite, ...).\n"
    ),
    "tests/README.md": (
        "# Tests\n\n"
        "- `unit/`: fast tests, no network, no real database file.\n"
        "- `integration/`: several layers together (Flask test client, temp SQLite).\n"
    ),
}

# Placeholder files: path -> one-line comment (written in the file's own syntax).
PLACEHOLDERS: dict[str, str] = {
    "README.md": "# wbms-lite\n\nWiFi Billing System (WBMS-Lite). Fill in: what, why, setup, run, test.\n",
    "Makefile": "# Task runner: see deck slide 45.\n",
    "pyproject.toml": (
        '# Project metadata and tool settings. Full pytest settings arrive in deck slide 84.\n'
        '[project]\n'
        'name = "wbms-lite"\n'
        'version = "0.1.0"\n'
        'requires-python = ">=3.12"\n'
        '\n'
        '[tool.pytest.ini_options]\n'
        '# Lets tests write "from wbms.x import y" with the src/ layout.\n'
        'pythonpath = ["src"]\n'
    ),
    "requirements.txt": "# Runtime dependencies: see deck slide 41.\n",
    "requirements-dev.txt": "-r requirements.txt\n# Dev tools: see deck slide 41.\n",
    "Dockerfile": "# Container image: see deck slide 96.\n",
    "docker-compose.yml": "# Compose services: see deck slide 96.\n",
    "docs/architecture.md": "# Architecture\n\nLayers diagram and data flow (deck slides 16 and 17).\n",
    "docs/api.md": "# API\n\nEndpoints with sample requests and responses (deck slide 55).\n",
    "scripts/init_db.py": '"""Create the SQLite database from schema.sql (deck slide 61)."""\n',
    "scripts/seed.py": '"""Insert example packages and an admin user, idempotently (deck slide 62)."""\n',
    "src/wbms/config.py": '"""Settings loaded from environment variables (deck slide 60)."""\n',
    "src/wbms/db.py": '"""SQLite connection helpers (deck slide 61)."""\n',
    "src/wbms/schema.sql": "-- WBMS-Lite database schema (deck slide 62).\n",
    "src/wbms/cli.py": '"""Voucher command-line tool (deck slide 77)."""\n',
    "tests/conftest.py": '"""Shared pytest fixtures (deck slide 84)."""\n',
}


class Status(StrEnum):
    """What happened (or, in a dry run, would happen) to one path."""

    CREATED = "created"
    SKIPPED = "skipped"
    WOULD_CREATE = "would create"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class Result:
    """Outcome for one path, relative to the project root."""

    path: str
    is_dir: bool
    status: Status
    note: str = ""


def build_manifest() -> tuple[tuple[str, ...], dict[str, str]]:
    """Return ``(directories, files)`` for the whole tree.

    ``directories`` is sorted parents-first and includes every directory that
    appears in the tree; ``files`` maps relative POSIX paths to file content.
    """
    files: dict[str, str] = {}
    files.update(PLACEHOLDERS)
    files.update(FILE_CONTENT)
    for package in PACKAGES:
        files[f"{package}/__init__.py"] = ""

    dirs: set[str] = set(DIRECTORIES) | set(PACKAGES)
    for rel in files:
        parent = Path(rel).parent.as_posix()
        if parent != ".":
            dirs.add(parent)
    # Add all ancestors so parents are always listed before children.
    for d in list(dirs):
        dirs.update(p.as_posix() for p in Path(d).parents if p.as_posix() != ".")

    # A directory that holds no file (directly) and has no sub-directory
    # would vanish from Git, so give it a .gitkeep.
    for d in sorted(dirs):
        has_file = any(Path(f).parent.as_posix() == d for f in files)
        has_child = any(Path(o).parent.as_posix() == d for o in dirs)
        if not has_file and not has_child:
            files[f"{d}/.gitkeep"] = ""

    return tuple(sorted(dirs, key=lambda p: (p.count("/"), p))), files


def _blocking_ancestor(root: Path, rel: str) -> str | None:
    """Return the first ancestor of ``rel`` that exists but is not a directory."""
    for parent in reversed(Path(rel).parents):
        name = parent.as_posix()
        if name != "." and (root / name).exists() and not (root / name).is_dir():
            return name
    return None


def _make_dir(root: Path, rel: str, dry_run: bool) -> Result:
    """Create one directory (idempotent) and report the outcome."""
    target = root / rel
    blocker = _blocking_ancestor(root, rel)
    if blocker:
        return Result(rel, True, Status.CONFLICT, f"{blocker} is a file")
    if target.is_dir():
        return Result(rel, True, Status.SKIPPED, "already exists")
    if target.exists() or target.is_symlink():
        return Result(rel, True, Status.CONFLICT, "a file with this name exists")
    if dry_run:
        return Result(rel, True, Status.WOULD_CREATE)
    target.mkdir(parents=True, exist_ok=True)
    return Result(rel, True, Status.CREATED)


def _make_file(root: Path, rel: str, content: str, dry_run: bool) -> Result:
    """Create one file without ever overwriting, and report the outcome."""
    target = root / rel
    blocker = _blocking_ancestor(root, rel)
    if blocker:
        return Result(rel, False, Status.CONFLICT, f"{blocker} is a file")
    if target.exists() or target.is_symlink():
        note = "already exists" if target.is_file() else "a directory with this name exists"
        status = Status.SKIPPED if target.is_file() else Status.CONFLICT
        return Result(rel, False, status, note)
    if not target.parent.is_dir():
        # Parent is missing (dry run) or blocked by a conflict: nothing to write.
        status = Status.WOULD_CREATE if dry_run else Status.CONFLICT
        note = "" if dry_run else "parent directory could not be created"
        return Result(rel, False, status, note)
    if dry_run:
        return Result(rel, False, Status.WOULD_CREATE)
    try:
        # Mode "x" fails if the file appeared since the check above:
        # this is what guarantees we never overwrite anything.
        with target.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
    except FileExistsError:
        return Result(rel, False, Status.SKIPPED, "already exists")
    return Result(rel, False, Status.CREATED)


def scaffold(root: Path, *, dry_run: bool = False) -> list[Result]:
    """Create the WBMS-Lite tree under ``root`` and return one Result per path.

    Args:
        root: Project root folder (created if missing, unless ``dry_run``).
        dry_run: Report what would be created without touching the disk.

    Returns:
        Results for the root, then every directory, then every file.
    """
    directories, files = build_manifest()
    results: list[Result] = []

    if root.is_dir():
        results.append(Result(".", True, Status.SKIPPED, "already exists"))
    elif dry_run:
        results.append(Result(".", True, Status.WOULD_CREATE))
    else:
        root.mkdir(parents=True, exist_ok=True)
        results.append(Result(".", True, Status.CREATED))

    for rel in directories:
        results.append(_make_dir_in(root, rel, dry_run))
    for rel in sorted(files):
        results.append(_make_file(root, rel, files[rel], dry_run))
    return results


def _make_dir_in(root: Path, rel: str, dry_run: bool) -> Result:
    """Like _make_dir, but tolerates a root that a dry run did not create."""
    if dry_run and not root.is_dir():
        return Result(rel, True, Status.WOULD_CREATE)
    return _make_dir(root, rel, dry_run)


def format_result(result: Result) -> str:
    """Render one Result as a single ASCII line (safe for any console)."""
    suffix = "/" if result.is_dir and result.path != "." else ""
    note = f" ({result.note})" if result.note else ""
    return f"[{result.status.value}] {result.path}{suffix}{note}"


def default_root() -> Path | None:
    """Project root = the folder that contains scripts/.

    Returns None when this file is not inside a folder named ``scripts``;
    guessing the parent folder there could scaffold into the wrong place
    (for example your Documents folder), so the caller must pass --root.
    """
    script_dir = Path(__file__).resolve().parent
    return script_dir.parent if script_dir.name == "scripts" else None


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=f"Create the {PROJECT_NAME} folder and file structure. "
        "Existing files are never overwritten."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="project root to populate (default: the folder above scripts/; "
        "required if this file is not inside a scripts/ folder)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would be created without writing anything",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns 0 on success, 1 if any path had a conflict."""
    args = parse_args(argv)
    chosen = args.root or default_root()
    if chosen is None:
        print(
            "error: scaffold.py is not inside a scripts/ folder, so the project root is unclear.\n"
            "Either move it to <project>/scripts/ or pass the root explicitly, e.g.:\n"
            "    python scaffold.py --root . --dry-run",
            file=sys.stderr,
        )
        return 2
    root: Path = chosen.resolve()
    dry_run: bool = args.dry_run

    print(f"Project root: {root}")
    if dry_run:
        print("DRY RUN: nothing will be written.")

    results = scaffold(root, dry_run=dry_run)
    for result in results:
        print(format_result(result))

    created = sum(r.status in (Status.CREATED, Status.WOULD_CREATE) for r in results)
    skipped = sum(r.status is Status.SKIPPED for r in results)
    conflicts = sum(r.status is Status.CONFLICT for r in results)
    verb = "Would create" if dry_run else "Created"
    print(f"\n{verb}: {created} | Skipped (already existed): {skipped} | Conflicts: {conflicts}")
    if conflicts:
        print("Resolve the conflicts above (a file and a folder share a name) and run again.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
