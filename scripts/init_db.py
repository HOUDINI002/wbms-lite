"""Create the database tables (no sample data).

    python scripts/init_db.py

Safe to run repeatedly: every table is created with IF NOT EXISTS, so existing
data is never touched. Use scripts/seed.py when you also want the example
packages and the admin account.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wbms import create_app, db  # noqa: E402


def main() -> int:
    """Entry point. Returns the process exit code."""
    try:
        app = create_app()
    except ValueError as error:  # ConfigError is a ValueError
        print(f"Cannot create the database: {error}", file=sys.stderr)
        return 1
    with app.app_context():
        db.init_db()
    print(f"Database ready: {app.config['DATABASE']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
