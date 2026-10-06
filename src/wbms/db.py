"""SQLite access for WBMS-Lite (Step 2).

Design in one paragraph: each request (or CLI command) gets exactly one
connection, created lazily by ``get_db()`` and stored on ``flask.g``. It is
closed automatically when the application context ends. Multi-statement work
goes through ``with transaction():`` so it either fully happens or does not
happen at all, which matters for billing.

Modes: connections run in *autocommit* mode (``isolation_level=None``), so
Python never opens hidden transactions behind your back. A single statement
outside ``transaction()`` is saved immediately; ``transaction()`` is the only
place that issues BEGIN, COMMIT and ROLLBACK.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from flask import Flask, current_app, g

from wbms.config import DEFAULT_DATABASE_PATH, PROJECT_ROOT

SCHEMA_PATH: Path = Path(__file__).with_name("schema.sql")
IN_MEMORY = ":memory:"

_CONN_KEY = "wbms_db"
_TX_KEY = "wbms_db_in_transaction"


def resolve_database_path(raw: str) -> str:
    """Turn the DATABASE_PATH setting into a path SQLite can open.

    ``:memory:`` is passed through (used by tests). Relative paths are anchored
    at the project root, so the database lands in the same place no matter
    which folder the app was started from. Absolute paths are kept as they are.
    """
    if raw == IN_MEMORY:
        return raw
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return str(path)


def get_db() -> sqlite3.Connection:
    """Return this request's connection, creating it on first use.

    Must be called inside an application context (a request, a CLI command, or
    ``with app.app_context():``). Rows come back as ``sqlite3.Row``, so columns
    can be read by name: ``row["price_kes"]``.
    """
    conn: sqlite3.Connection | None = g.get(_CONN_KEY)
    if conn is None:
        database = current_app.config["DATABASE"]
        if database != IN_MEMORY:
            Path(database).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(database, isolation_level=None)
        conn.row_factory = sqlite3.Row
        # Foreign-key enforcement is OFF by default in SQLite, and it is a
        # setting of the *connection*, not of the database file. Nothing in the
        # file remembers it, so every new connection starts with it off and
        # must switch it on. Without this line a customer_id pointing at no
        # customer would be accepted silently and orphaned rows would pile up.
        conn.execute("PRAGMA foreign_keys = ON")
        setattr(g, _CONN_KEY, conn)
        g.pop(_TX_KEY, None)
    return conn


def close_db(error: BaseException | None = None) -> None:
    """Close this context's connection, if one was opened.

    Registered with ``teardown_appcontext`` so it runs after every request, even
    when the view raised. The ``error`` argument is supplied by Flask and unused.
    """
    conn: sqlite3.Connection | None = g.pop(_CONN_KEY, None)
    g.pop(_TX_KEY, None)
    if conn is not None:
        conn.close()


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    """Run a block atomically: commit if it finishes, roll back if it raises.

    Usage::

        with transaction() as db:
            db.execute("INSERT INTO ...", (...))
            db.execute("UPDATE ...", (...))

    Uses ``BEGIN IMMEDIATE``, which takes the write lock up front. Two
    callbacks for the same payment then queue one behind the other instead of
    both reading "not yet applied". Blocks may be nested: the inner one joins
    the outer transaction, and only the outermost block commits or rolls back.
    """
    conn = get_db()
    if g.get(_TX_KEY, False):
        yield conn  # joined an outer transaction; it decides the outcome
        return

    conn.execute("BEGIN IMMEDIATE")
    setattr(g, _TX_KEY, True)
    try:
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        setattr(g, _TX_KEY, False)


def init_db(schema_path: Path | None = None) -> None:
    """Create the tables by running the schema script on this connection.

    Args:
        schema_path: SQL file to run. Defaults to ``src/wbms/schema.sql``.

    Raises:
        FileNotFoundError: if the schema file does not exist.
    """
    sql = (schema_path or SCHEMA_PATH).read_text(encoding="utf-8")
    get_db().executescript(sql)


def init_app(app: Flask) -> None:
    """Wire the database into ``app``; called once from ``create_app``.

    Sets ``app.config["DATABASE"]`` from the settings stored on the app (unless
    a test already set it) and registers :func:`close_db` for teardown.
    """
    settings = app.extensions.get("wbms_settings")
    raw = settings.DATABASE_PATH if settings is not None else DEFAULT_DATABASE_PATH
    app.config.setdefault("DATABASE", resolve_database_path(raw))
    app.teardown_appcontext(close_db)
