"""Unit tests for wbms.repositories.packages (slide 63).

Each test gets a brand-new in-memory SQLite database built from the real
src/wbms/schema.sql, so these tests also prove the repository and the schema
agree on column names.
"""

import ast
import dataclasses
import inspect
import sqlite3
from pathlib import Path

import pytest

from wbms.repositories import packages as packages_module
from wbms.repositories.packages import (
    Package,
    PackageInput,
    PackageNotFoundError,
    PackageRepository,
)

SCHEMA = Path(__file__).resolve().parents[2] / "src" / "wbms" / "schema.sql"


@pytest.fixture
def conn():
    """An empty in-memory database that behaves like the app's connection."""
    connection = sqlite3.connect(":memory:", isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA.read_text(encoding="utf-8"))
    yield connection
    connection.close()


@pytest.fixture
def repo(conn):
    return PackageRepository(conn)


def make_input(**changes) -> PackageInput:
    """A valid PackageInput; override any field by keyword."""
    fields = {
        "name": "1 Hour",
        "price_kes": 20,
        "duration_minutes": 60,
        "speed_kbps": 2000,
        "data_limit_mb": None,
    }
    fields.update(changes)
    return PackageInput(**fields)


def count_rows(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM packages").fetchone()[0]


# ---------------------------------------------------------------- list_active


def test_list_active_is_empty_on_a_fresh_database(repo):
    assert repo.list_active() == []


def test_list_active_returns_package_objects_not_rows(repo):
    repo.create(make_input())
    result = repo.list_active()
    assert len(result) == 1
    assert isinstance(result[0], Package)


def test_list_active_orders_cheapest_first_not_alphabetically(repo):
    repo.create(make_input(name="Alpha Week", price_kes=500, duration_minutes=10080))
    repo.create(make_input(name="Zulu Hour", price_kes=20))
    repo.create(make_input(name="Mike Day", price_kes=100, duration_minutes=1440))
    names = [p.name for p in repo.list_active()]
    assert names == ["Zulu Hour", "Mike Day", "Alpha Week"]


def test_list_active_breaks_price_ties_by_id(repo):
    first = repo.create(make_input(name="Alpha", price_kes=50))
    second = repo.create(make_input(name="Beta", price_kes=50))
    assert [p.id for p in repo.list_active()] == [first.id, second.id]


def test_list_active_hides_retired_packages(repo):
    keep = repo.create(make_input(name="Keep"))
    retire = repo.create(make_input(name="Retire"))
    repo.set_active(retire.id, False)
    assert [p.id for p in repo.list_active()] == [keep.id]


# ------------------------------------------------------------------------ get


def test_get_returns_the_package_with_every_field(repo):
    created = repo.create(
        make_input(name="Data Bundle", price_kes=250, data_limit_mb=1024)
    )
    found = repo.get(created.id)
    assert found == Package(
        id=created.id,
        name="Data Bundle",
        price_kes=250,
        duration_minutes=60,
        data_limit_mb=1024,
        speed_kbps=2000,
        is_active=True,
    )


def test_get_unknown_id_returns_none(repo):
    assert repo.get(999) is None


def test_get_still_finds_a_retired_package(repo):
    created = repo.create(make_input())
    repo.set_active(created.id, False)
    found = repo.get(created.id)
    assert found is not None
    assert found.is_active is False


def test_is_active_is_a_real_bool_not_0_or_1(repo):
    created = repo.create(make_input())
    assert created.is_active is True


# --------------------------------------------------------------------- create


def test_create_returns_the_stored_package_with_a_new_id(repo):
    created = repo.create(make_input())
    assert isinstance(created.id, int)
    assert created.name == "1 Hour"
    assert created.price_kes == 20
    assert created.duration_minutes == 60
    assert created.speed_kbps == 2000
    assert created.is_active is True


def test_create_gives_each_package_a_different_id(repo):
    a = repo.create(make_input(name="A"))
    b = repo.create(make_input(name="B"))
    assert a.id != b.id


def test_create_without_data_limit_means_unlimited(repo):
    created = repo.create(make_input())
    assert created.data_limit_mb is None


def test_create_keeps_a_data_limit(repo):
    assert repo.create(make_input(data_limit_mb=500)).data_limit_mb == 500


def test_create_allows_a_free_package(repo):
    assert repo.create(make_input(name="Free", price_kes=0)).price_kes == 0


def test_created_package_can_be_read_back(repo):
    created = repo.create(make_input())
    assert repo.get(created.id) == created


def test_create_with_a_duplicate_name_raises_integrity_error(repo, conn):
    repo.create(make_input(name="Same"))
    with pytest.raises(sqlite3.IntegrityError):
        repo.create(make_input(name="Same", price_kes=99))
    assert count_rows(conn) == 1


@pytest.mark.parametrize(
    "bad",
    [
        {"price_kes": -1},
        {"duration_minutes": 0},
        {"duration_minutes": -5},
        {"data_limit_mb": 0},
        {"speed_kbps": 0},
    ],
)
def test_create_lets_the_database_reject_nonsense_numbers(repo, conn, bad):
    with pytest.raises(sqlite3.IntegrityError):
        repo.create(make_input(**bad))
    assert count_rows(conn) == 0


# --------------------------------------------------------------------- update


def test_update_changes_every_editable_field_and_returns_the_result(repo):
    created = repo.create(make_input())
    changed = repo.update(
        created.id,
        PackageInput(
            name="Renamed",
            price_kes=30,
            duration_minutes=90,
            speed_kbps=4000,
            data_limit_mb=2048,
        ),
    )
    assert changed == Package(
        id=created.id,
        name="Renamed",
        price_kes=30,
        duration_minutes=90,
        data_limit_mb=2048,
        speed_kbps=4000,
        is_active=True,
    )
    assert repo.get(created.id) == changed


def test_update_can_turn_a_data_limit_back_into_unlimited(repo):
    created = repo.create(make_input(data_limit_mb=500))
    changed = repo.update(created.id, make_input(data_limit_mb=None))
    assert changed is not None
    assert changed.data_limit_mb is None


def test_update_unknown_id_returns_none_and_changes_nothing(repo, conn):
    repo.create(make_input())
    assert repo.update(999, make_input(name="Ghost")) is None
    assert count_rows(conn) == 1
    assert [p.name for p in repo.list_active()] == ["1 Hour"]


def test_update_does_not_touch_the_active_flag(repo):
    created = repo.create(make_input())
    repo.set_active(created.id, False)
    changed = repo.update(created.id, make_input(price_kes=25))
    assert changed is not None
    assert changed.price_kes == 25
    assert changed.is_active is False


def test_update_only_changes_the_package_asked_for(repo):
    a = repo.create(make_input(name="A"))
    b = repo.create(make_input(name="B"))
    repo.update(a.id, make_input(name="A2"))
    assert repo.get(b.id) == b


def test_update_to_another_packages_name_is_rejected_and_nothing_changes(repo):
    repo.create(make_input(name="Taken"))
    other = repo.create(make_input(name="Other"))
    with pytest.raises(sqlite3.IntegrityError):
        repo.update(other.id, make_input(name="Taken"))
    assert repo.get(other.id) == other


def test_update_with_unchanged_values_still_returns_the_package(repo):
    created = repo.create(make_input())
    assert repo.update(created.id, make_input()) == created


# ----------------------------------------------------------------- set_active


def test_set_active_false_retires_the_package_but_keeps_the_row(repo, conn):
    created = repo.create(make_input())
    repo.set_active(created.id, False)
    assert repo.list_active() == []
    assert count_rows(conn) == 1


def test_set_active_true_puts_it_back_on_sale(repo):
    created = repo.create(make_input())
    repo.set_active(created.id, False)
    repo.set_active(created.id, True)
    assert [p.id for p in repo.list_active()] == [created.id]


def test_set_active_twice_is_harmless(repo):
    created = repo.create(make_input())
    repo.set_active(created.id, False)
    repo.set_active(created.id, False)
    assert repo.get(created.id).is_active is False


def test_set_active_returns_none(repo):
    created = repo.create(make_input())
    assert repo.set_active(created.id, False) is None


def test_set_active_unknown_id_raises_package_not_found(repo):
    with pytest.raises(PackageNotFoundError) as excinfo:
        repo.set_active(999, True)
    assert excinfo.value.package_id == 999
    assert "999" in str(excinfo.value)


def test_package_not_found_is_a_lookup_error():
    assert issubclass(PackageNotFoundError, LookupError)


# ---------------------------------------------------- plain objects, immutable


def test_package_is_frozen(repo):
    created = repo.create(make_input())
    with pytest.raises(dataclasses.FrozenInstanceError):
        created.price_kes = 1


def test_package_input_is_frozen():
    data = make_input()
    with pytest.raises(dataclasses.FrozenInstanceError):
        data.name = "changed"


def test_package_input_defaults_to_unlimited_data():
    data = PackageInput(name="X", price_kes=1, duration_minutes=1, speed_kbps=64)
    assert data.data_limit_mb is None


# --------------------------------------------------- SQL injection (slide 63)


def test_a_hostile_name_is_stored_as_plain_text_and_the_table_survives(repo, conn):
    nasty = "x'); DROP TABLE packages; --"
    created = repo.create(make_input(name=nasty))
    assert repo.get(created.id).name == nasty
    assert count_rows(conn) == 1


def test_a_hostile_name_in_update_is_also_just_data(repo, conn):
    created = repo.create(make_input())
    nasty = "a' OR '1'='1"
    assert repo.update(created.id, make_input(name=nasty)).name == nasty
    assert count_rows(conn) == 1


def test_an_injection_string_as_an_id_matches_nothing(repo):
    repo.create(make_input())
    assert repo.get("1 OR 1=1") is None


def test_the_module_builds_no_sql_with_f_strings_or_format():
    """Slide 63 exercise: search for an f-string that contains SQL. None allowed."""
    tree = ast.parse(inspect.getsource(packages_module))
    f_strings = [n for n in ast.walk(tree) if isinstance(n, ast.JoinedStr)]
    format_calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "format"
    ]
    percent_sql = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.BinOp)
        and isinstance(n.op, ast.Mod)
        and isinstance(n.left, ast.Constant)
        and isinstance(n.left.value, str)
    ]
    assert f_strings == []
    assert format_calls == []
    assert percent_sql == []


# ------------------------------------------------ works with the app's wiring


def test_the_repository_never_commits_so_a_caller_can_roll_back(repo, conn):
    conn.execute("BEGIN")
    repo.create(make_input())
    conn.execute("ROLLBACK")
    assert repo.list_active() == []


def test_changes_made_inside_a_caller_transaction_commit_with_it(repo, conn):
    conn.execute("BEGIN")
    repo.create(make_input())
    conn.execute("COMMIT")
    assert len(repo.list_active()) == 1


def test_it_also_works_with_plain_tuple_rows(conn):
    conn.row_factory = None
    repo = PackageRepository(conn)
    created = repo.create(make_input())
    assert repo.list_active() == [created]
