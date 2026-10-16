"""Add transactions.mac_address to an existing WBMS-Lite database (Step 8).

Usage (from the project root, venv active):
    python scripts/add_mac_to_transactions.py            # default database
    python scripts/add_mac_to_transactions.py path\to\file.sqlite3

Safe to run more than once: it does nothing if the column already exists.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    default = os.environ.get("DATABASE_PATH", "instance/wbms.sqlite3")
    path = Path(argv[1] if len(argv) > 1 else default)
    if not path.exists():
        print(f"No database at {path}. Run scripts/seed.py first, or pass the path.")
        return 1
    conn = sqlite3.connect(path)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(transactions)")}
        if not columns:
            print("Table 'transactions' not found: is this the right database?")
            return 1
        if "mac_address" in columns:
            print("transactions.mac_address already exists. Nothing to do.")
            return 0
        conn.execute("ALTER TABLE transactions ADD COLUMN mac_address TEXT")
        conn.commit()
        print("Added transactions.mac_address.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
