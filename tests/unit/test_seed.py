"""Unit tests for scripts/seed.py (Step 3, prompt 2)."""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest
from werkzeug.security import check_password_hash

from wbms import config, create_app, db
from wbms.config import load_settings

SEED_PATH = Path(__file__).resolve().parents[2] / "scripts" / "seed.py"
PASSWORD = "correct horse battery"


@pytest.fixture(scope="module")
def seed():
    """Load scripts/seed.py by path (scripts/ is not a package)."""
    name = "wbms_seed_script"
    spec = importlib.util.spec_from_file_location(name, SEED_PATH)
    module = importlib.util.module_from_spec(spec)
    # Must be registered BEFORE exec_module: @dataclass looks the module up by name.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def conn():
    app = create_app(load_settings({"SECRET_KEY": "test", "DATABASE_PATH": ":memory:"}))
    with app.app_context():
        db.init_db()
        yield db.get_db()


def count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# --- seed_database --------------------------------------------------------


def test_first_run_creates_three_packages_and_one_admin(seed, conn):
    report = seed.seed_database(conn, "boss", PASSWORD)
    assert count(conn, "packages") == 3
    assert count(conn, "admins") == 1
    assert report.packages_created == ["1 Hour", "24 Hours", "7 Days"]
    assert report.packages_existing == []
    assert report.admin_created is True


def test_package_prices_durations_and_speeds_match_the_slide(seed, conn):
    seed.seed_database(conn, "boss", PASSWORD)
    rows = conn.execute(
        "SELECT name, price_kes, duration_minutes, speed_kbps, data_limit_mb"
        " FROM packages ORDER BY price_kes"
    ).fetchall()
    assert [tuple(r) for r in rows] == [
        ("1 Hour", 20, 60, 2048, None),
        ("24 Hours", 100, 1440, 4096, None),
        ("7 Days", 500, 10080, 8192, None),
    ]
    assert len({r["speed_kbps"] for r in rows}) == 3  # three different speeds


def test_running_twice_creates_no_duplicates(seed, conn):
    seed.seed_database(conn, "boss", PASSWORD)
    second = seed.seed_database(conn, "boss", PASSWORD)
    assert count(conn, "packages") == 3
    assert count(conn, "admins") == 1
    assert second.packages_created == []
    assert second.packages_existing == ["1 Hour", "24 Hours", "7 Days"]
    assert second.admin_created is False


def test_password_is_stored_as_a_verifiable_hash_not_plain_text(seed, conn):
    seed.seed_database(conn, "boss", PASSWORD)
    stored = conn.execute("SELECT password_hash FROM admins").fetchone()[0]
    assert PASSWORD not in stored
    assert stored != PASSWORD
    assert check_password_hash(stored, PASSWORD)
    assert not check_password_hash(stored, "wrong password")


def test_existing_admin_password_is_not_overwritten(seed, conn):
    seed.seed_database(conn, "boss", PASSWORD)
    before = conn.execute("SELECT password_hash FROM admins").fetchone()[0]
    seed.seed_database(conn, "boss", "a completely different one")
    after = conn.execute("SELECT password_hash FROM admins").fetchone()[0]
    assert before == after


def test_existing_package_is_not_modified(seed, conn):
    conn.execute(
        "INSERT INTO packages (name, price_kes, duration_minutes, speed_kbps)"
        " VALUES ('1 Hour', 35, 90, 512)"
    )
    report = seed.seed_database(conn, "boss", PASSWORD)
    row = conn.execute("SELECT price_kes, duration_minutes FROM packages WHERE name='1 Hour'").fetchone()
    assert tuple(row) == (35, 90)
    assert report.packages_existing == ["1 Hour"]
    assert count(conn, "packages") == 3


def test_a_failure_rolls_everything_back(seed, conn, monkeypatch):
    def explode(_password):
        raise RuntimeError("hashing failed")

    monkeypatch.setattr(seed, "generate_password_hash", explode)
    with pytest.raises(RuntimeError):
        seed.seed_database(conn, "boss", PASSWORD)
    assert count(conn, "packages") == 0
    assert count(conn, "admins") == 0


# --- password rules and report -------------------------------------------


@pytest.mark.parametrize("value", [None, ""])
def test_missing_password_is_a_clear_error(seed, value):
    with pytest.raises(seed.SeedError, match="ADMIN_PASSWORD is not set"):
        seed.validate_admin_password(value)


def test_short_password_is_rejected(seed):
    with pytest.raises(seed.SeedError, match="at least"):
        seed.validate_admin_password("short")


def test_good_password_is_returned_unchanged(seed):
    assert seed.validate_admin_password(PASSWORD) == PASSWORD


def test_report_text_never_contains_the_password(seed, conn):
    report = seed.seed_database(conn, "boss", PASSWORD)
    text = seed.format_report(report, "somewhere.sqlite3")
    assert PASSWORD not in text
    assert "3 created" in text
    assert "'boss' created" in text


def test_report_text_for_a_repeat_run(seed, conn):
    seed.seed_database(conn, "boss", PASSWORD)
    text = seed.format_report(seed.seed_database(conn, "boss", PASSWORD), "x.sqlite3")
    assert "0 created, 3 already present" in text
    assert "already exists" in text


# --- main() end to end ----------------------------------------------------


def isolate(monkeypatch, seed, tmp_path, **env):
    """Point the script at a temporary database and a non-existent .env file."""
    missing = tmp_path / "no.env"
    monkeypatch.setattr(seed, "ENV_FILE", missing)
    monkeypatch.setattr(config, "ENV_FILE", missing)
    base = {
        "SECRET_KEY": "test-secret",
        "DATABASE_PATH": str(tmp_path / "seed.sqlite3"),
        "ADMIN_USERNAME": "boss",
        "ADMIN_PASSWORD": PASSWORD,
    }
    base.update(env)
    for name in ("SECRET_KEY", "DATABASE_PATH", "ADMIN_USERNAME", "ADMIN_PASSWORD"):
        monkeypatch.setenv(name, "placeholder")  # records the original for restore
        monkeypatch.delenv(name)
    for name, value in base.items():
        if value is not None:
            monkeypatch.setenv(name, value)


def test_main_seeds_a_real_database_file_and_is_repeatable(seed, monkeypatch, tmp_path, capsys):
    isolate(monkeypatch, seed, tmp_path)
    assert seed.main() == 0
    assert seed.main() == 0
    output = capsys.readouterr().out
    assert "3 created" in output and "0 created, 3 already present" in output
    assert PASSWORD not in output
    check = sqlite3.connect(tmp_path / "seed.sqlite3")
    try:
        assert check.execute("SELECT COUNT(*) FROM packages").fetchone()[0] == 3
        assert check.execute("SELECT username FROM admins").fetchone()[0] == "boss"
    finally:
        check.close()


def test_main_defaults_the_admin_username(seed, monkeypatch, tmp_path):
    isolate(monkeypatch, seed, tmp_path, ADMIN_USERNAME=None)
    assert seed.main() == 0
    check = sqlite3.connect(tmp_path / "seed.sqlite3")
    try:
        assert check.execute("SELECT username FROM admins").fetchone()[0] == "admin"
    finally:
        check.close()


def test_main_without_a_password_fails_cleanly_and_creates_nothing(seed, monkeypatch, tmp_path, capsys):
    isolate(monkeypatch, seed, tmp_path, ADMIN_PASSWORD=None)
    assert seed.main() == 1
    assert "ADMIN_PASSWORD is not set" in capsys.readouterr().err
    assert not (tmp_path / "seed.sqlite3").exists()


def test_main_without_a_secret_key_reports_the_config_error(seed, monkeypatch, tmp_path, capsys):
    isolate(monkeypatch, seed, tmp_path, SECRET_KEY=None)
    assert seed.main() == 1
    assert "SECRET_KEY" in capsys.readouterr().err
