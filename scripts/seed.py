"""Create the database tables and insert starter data (Step 3, prompt 2).

Run from the project root with the virtual environment active::

    python scripts/seed.py

What it does
    1. Runs src/wbms/schema.sql (safe to repeat).
    2. Inserts three example packages, skipping any whose name already exists.
    3. Inserts one admin, skipping it if that username already exists.
    4. Prints a summary of what was created and what was already there.

The admin password is NEVER written in code. Put it in your .env file::

    ADMIN_USERNAME=admin          (optional, defaults to "admin")
    ADMIN_PASSWORD=<a strong password you choose>

Running the script twice creates no duplicates, and an existing admin's
password is left untouched. To change it, use the admin screens (a later step).
"""

from __future__ import annotations

import os
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402

from wbms import create_app, db  # noqa: E402
from wbms.config import ENV_FILE  # noqa: E402

DEFAULT_ADMIN_USERNAME = "admin"
MIN_PASSWORD_LENGTH = 10

# (name, price_kes, duration_minutes, data_limit_mb, speed_kbps)
# data_limit_mb None means unlimited data.
EXAMPLE_PACKAGES: tuple[tuple[str, int, int, int | None, int], ...] = (
    ("1 Hour", 20, 60, None, 2048),
    ("24 Hours", 100, 24 * 60, None, 4096),
    ("7 Days", 500, 7 * 24 * 60, None, 8192),
)


class SeedError(Exception):
    """Raised for problems the person running the script can fix."""


@dataclass
class SeedReport:
    """What a seed run did, for the printed summary and for tests."""

    packages_created: list[str] = field(default_factory=list)
    packages_existing: list[str] = field(default_factory=list)
    admin_created: bool = False
    admin_username: str = ""


def validate_admin_password(password: str | None) -> str:
    """Return the password if it is acceptable, otherwise raise SeedError."""
    if not password:
        raise SeedError(
            "ADMIN_PASSWORD is not set. Add a line ADMIN_PASSWORD=<your password> "
            "to your .env file, then run the script again."
        )
    if len(password) < MIN_PASSWORD_LENGTH:
        raise SeedError(
            f"ADMIN_PASSWORD must be at least {MIN_PASSWORD_LENGTH} characters long."
        )
    return password


def seed_database(
    conn: sqlite3.Connection, admin_username: str, admin_password: str
) -> SeedReport:
    """Insert the example packages and the admin; skip anything already there.

    Runs inside the caller's database context. Everything happens in one
    transaction, so a failure leaves the database exactly as it was.
    """
    report = SeedReport(admin_username=admin_username)
    with db.transaction():
        for name, price, minutes, data_mb, speed in EXAMPLE_PACKAGES:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO packages "
                "(name, price_kes, duration_minutes, data_limit_mb, speed_kbps) "
                "VALUES (?, ?, ?, ?, ?)",
                (name, price, minutes, data_mb, speed),
            )
            if cursor.rowcount:  # 1 row inserted; 0 means the name already existed
                report.packages_created.append(name)
            else:
                report.packages_existing.append(name)

        # Hash only when the admin is new: hashing is deliberately slow.
        exists = conn.execute(
            "SELECT 1 FROM admins WHERE username = ?", (admin_username,)
        ).fetchone()
        if exists is None:
            conn.execute(
                "INSERT INTO admins (username, password_hash) VALUES (?, ?)",
                (admin_username, generate_password_hash(admin_password)),
            )
            report.admin_created = True
    return report


def format_report(report: SeedReport, database: str) -> str:
    """Build the human-readable summary printed at the end of a run."""
    lines = [
        "WBMS-Lite seed summary",
        f"  Database : {database}",
        f"  Packages : {len(report.packages_created)} created, "
        f"{len(report.packages_existing)} already present",
    ]
    lines += [f"    + {name}" for name in report.packages_created]
    lines += [f"    = {name} (already there)" for name in report.packages_existing]
    if report.admin_created:
        lines.append(f"  Admin    : '{report.admin_username}' created")
    else:
        lines.append(
            f"  Admin    : '{report.admin_username}' already exists "
            "(password not changed)"
        )
    return "\n".join(lines)


def main() -> int:
    """Entry point. Returns the process exit code."""
    load_dotenv(ENV_FILE, override=False)
    try:
        password = validate_admin_password(os.environ.get("ADMIN_PASSWORD"))
        username = os.environ.get("ADMIN_USERNAME", "").strip() or DEFAULT_ADMIN_USERNAME
        app = create_app()
    except (SeedError, ValueError) as error:  # ConfigError is a ValueError
        print(f"Cannot seed: {error}", file=sys.stderr)
        return 1

    with app.app_context():
        db.init_db()
        report = seed_database(db.get_db(), username, password)
    print(format_report(report, app.config["DATABASE"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
