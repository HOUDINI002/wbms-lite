"""Unit tests for wbms.db (Step 2). Most use an in-memory database."""

from __future__ import annotations

import sqlite3

import pytest

from wbms import create_app, db
from wbms.config import PROJECT_ROOT, load_settings

PARENT_CHILD = """
CREATE TABLE parent (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE child (
    id INTEGER PRIMARY KEY,
    parent_id INTEGER NOT NULL REFERENCES parent(id) ON DELETE RESTRICT
);
"""


def make_app(database: str = ":memory:"):
    settings = load_settings({"SECRET_KEY": "test", "DATABASE_PATH": database})
    return create_app(settings)


@pytest.fixture
def app():
    return make_app()


@pytest.fixture
def conn(app):
    """An open connection inside an app context, with parent/child tables."""
    with app.app_context():
        connection = db.get_db()
        connection.executescript(PARENT_CHILD)
        yield connection


def count(connection, table):
    return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# --- get_db / close_db ----------------------------------------------------


def test_get_db_returns_a_connection_with_row_access_by_name(conn):
    assert isinstance(conn, sqlite3.Connection)
    conn.execute("INSERT INTO parent (name) VALUES ('a')")
    row = conn.execute("SELECT id, name FROM parent").fetchone()
    assert isinstance(row, sqlite3.Row)
    assert row["name"] == "a"


def test_get_db_returns_the_same_connection_within_one_context(app):
    with app.app_context():
        assert db.get_db() is db.get_db()


def test_each_app_context_gets_its_own_connection(app):
    with app.app_context():
        first = db.get_db()
    with app.app_context():
        assert db.get_db() is not first


def test_foreign_keys_are_on_for_every_new_connection(app):
    for _ in range(2):  # the setting is per connection, so check twice
        with app.app_context():
            assert db.get_db().execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_connection_is_closed_when_the_context_ends(app):
    with app.app_context():
        connection = db.get_db()
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")


def test_close_db_without_a_connection_does_nothing(app):
    with app.app_context():
        db.close_db()  # nothing opened yet: must not raise


def test_close_db_is_registered_for_teardown(app):
    assert db.close_db in app.teardown_appcontext_funcs


def test_connection_is_closed_after_a_request(app):
    seen = []

    @app.get("/probe")
    def probe():
        seen.append(db.get_db())
        return "ok"

    assert app.test_client().get("/probe").status_code == 200
    with pytest.raises(sqlite3.ProgrammingError):
        seen[0].execute("SELECT 1")


def test_get_db_outside_an_app_context_raises_runtime_error():
    with pytest.raises(RuntimeError):
        db.get_db()


# --- transaction() --------------------------------------------------------


def test_transaction_commits_on_success(conn):
    with db.transaction() as tx:
        tx.execute("INSERT INTO parent (name) VALUES ('kept')")
    assert not conn.in_transaction
    assert count(conn, "parent") == 1


def test_transaction_rolls_back_and_reraises_on_error(conn):
    with pytest.raises(RuntimeError, match="boom"):
        with db.transaction() as tx:
            tx.execute("INSERT INTO parent (name) VALUES ('lost')")
            raise RuntimeError("boom")
    assert not conn.in_transaction
    assert count(conn, "parent") == 0


def test_transaction_is_all_or_nothing_across_statements(conn):
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaction() as tx:
            tx.execute("INSERT INTO parent (id, name) VALUES (1, 'ok')")
            tx.execute("INSERT INTO child (parent_id) VALUES (999)")  # no such parent
    assert count(conn, "parent") == 0
    assert count(conn, "child") == 0


def test_database_is_usable_after_a_failed_transaction(conn):
    with pytest.raises(ValueError):
        with db.transaction():
            raise ValueError("first fails")
    with db.transaction() as tx:
        tx.execute("INSERT INTO parent (name) VALUES ('second works')")
    assert count(conn, "parent") == 1


def test_nested_transaction_joins_the_outer_one(conn):
    with pytest.raises(RuntimeError):
        with db.transaction():
            with db.transaction() as inner:
                inner.execute("INSERT INTO parent (name) VALUES ('inner')")
            # inner block ended cleanly but must NOT have committed yet
            assert conn.in_transaction
            raise RuntimeError("outer fails")
    assert count(conn, "parent") == 0


def test_nested_transaction_commits_with_the_outer_one(conn):
    with db.transaction():
        with db.transaction() as inner:
            inner.execute("INSERT INTO parent (name) VALUES ('inner')")
        assert conn.in_transaction
    assert not conn.in_transaction
    assert count(conn, "parent") == 1


def test_statement_outside_a_transaction_is_saved_immediately(conn):
    conn.execute("INSERT INTO parent (name) VALUES ('auto')")
    assert not conn.in_transaction


def test_committed_data_is_visible_to_another_connection(tmp_path):
    path = tmp_path / "durable.sqlite3"
    app = make_app(str(path))
    with app.app_context():
        db.get_db().executescript(PARENT_CHILD)
        with db.transaction() as tx:
            tx.execute("INSERT INTO parent (name) VALUES ('durable')")
    other = sqlite3.connect(path)
    try:
        assert other.execute("SELECT name FROM parent").fetchone() == ("durable",)
    finally:
        other.close()


def test_rolled_back_data_is_invisible_to_another_connection(tmp_path):
    path = tmp_path / "rollback.sqlite3"
    app = make_app(str(path))
    with app.app_context():
        db.get_db().executescript(PARENT_CHILD)
        with pytest.raises(RuntimeError):
            with db.transaction() as tx:
                tx.execute("INSERT INTO parent (name) VALUES ('gone')")
                raise RuntimeError
    other = sqlite3.connect(path)
    try:
        assert other.execute("SELECT COUNT(*) FROM parent").fetchone() == (0,)
    finally:
        other.close()


# --- foreign keys ---------------------------------------------------------


def test_insert_with_missing_parent_raises_integrity_error(conn):
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        conn.execute("INSERT INTO child (parent_id) VALUES (42)")


def test_insert_with_existing_parent_succeeds(conn):
    conn.execute("INSERT INTO parent (id, name) VALUES (1, 'p')")
    conn.execute("INSERT INTO child (parent_id) VALUES (1)")
    assert count(conn, "child") == 1


def test_deleting_a_parent_that_has_children_is_restricted(conn):
    conn.execute("INSERT INTO parent (id, name) VALUES (1, 'p')")
    conn.execute("INSERT INTO child (parent_id) VALUES (1)")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM parent WHERE id = 1")


# --- init_db --------------------------------------------------------------


def test_init_db_runs_the_given_schema_file(app, tmp_path):
    schema = tmp_path / "schema.sql"
    schema.write_text("CREATE TABLE demo (id INTEGER PRIMARY KEY);", encoding="utf-8")
    with app.app_context():
        db.init_db(schema)
        names = [
            r["name"]
            for r in db.get_db().execute("SELECT name FROM sqlite_master")
        ]
    assert "demo" in names


def test_init_db_is_safe_to_run_twice_with_if_not_exists(app, tmp_path):
    schema = tmp_path / "schema.sql"
    schema.write_text(
        "CREATE TABLE IF NOT EXISTS demo (id INTEGER PRIMARY KEY);", encoding="utf-8"
    )
    with app.app_context():
        db.init_db(schema)
        db.init_db(schema)


def test_init_db_with_missing_file_raises(app, tmp_path):
    with app.app_context():
        with pytest.raises(FileNotFoundError):
            db.init_db(tmp_path / "nope.sql")


def test_the_project_schema_file_exists_and_runs_cleanly(app):
    # Guards Step 3: whatever is written into schema.sql must stay valid SQL.
    assert db.SCHEMA_PATH.is_file()
    with app.app_context():
        db.init_db()


# --- paths and wiring -----------------------------------------------------


def test_relative_database_path_is_anchored_at_the_project_root():
    resolved = db.resolve_database_path("instance/wbms.sqlite3")
    assert resolved == str(PROJECT_ROOT / "instance" / "wbms.sqlite3")


def test_absolute_and_memory_paths_are_left_alone(tmp_path):
    absolute = str(tmp_path / "x.db")
    assert db.resolve_database_path(absolute) == absolute
    assert db.resolve_database_path(":memory:") == ":memory:"


def test_database_setting_reaches_the_app_config(tmp_path):
    target = str(tmp_path / "from_settings.sqlite3")
    assert make_app(target).config["DATABASE"] == target


def test_missing_database_folder_is_created_on_first_use(tmp_path):
    path = tmp_path / "new_folder" / "wbms.sqlite3"
    app = make_app(str(path))
    with app.app_context():
        db.get_db()
    assert path.is_file()
