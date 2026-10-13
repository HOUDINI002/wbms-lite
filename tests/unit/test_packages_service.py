"""Tests for PackageService, the business rules for packages (Step 5, slide 64).

They use an in-memory SQLite database built from the real ``schema.sql``, so no
file is written and no Flask app is needed.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from wbms.repositories.packages import PackageInput, PackageRepository
from wbms.services.packages import (
    REQUIRED,
    PackageService,
    UnknownPackageError,
    ValidationError,
    validate_package_input,
)

SCHEMA = Path(__file__).resolve().parents[2] / "src" / "wbms" / "schema.sql"

# (field, lowest allowed, highest allowed), straight from slide 64.
NUMERIC_RULES = [
    ("price_kes", 0, 100_000),
    ("duration_minutes", 1, 43_200),
    ("speed_kbps", 64, 100_000),
]


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA.read_text(encoding="utf-8"))
    yield connection
    connection.close()


@pytest.fixture
def repo(conn: sqlite3.Connection) -> PackageRepository:
    return PackageRepository(conn)


@pytest.fixture
def service(repo: PackageRepository) -> PackageService:
    return PackageService(repo)


def good(**changes: Any) -> dict[str, Any]:
    """A valid request body, with any fields overridden."""
    data: dict[str, Any] = {
        "name": "2 Hours",
        "price_kes": 35,
        "duration_minutes": 120,
        "speed_kbps": 4000,
        "data_limit_mb": None,
    }
    data.update(changes)
    return data


def errors_of(data: object) -> dict[str, str]:
    with pytest.raises(ValidationError) as caught:
        validate_package_input(data)
    return caught.value.errors


def stored_is_active(conn: sqlite3.Connection, package_id: int) -> int:
    return conn.execute(
        "SELECT is_active FROM packages WHERE id = ?", (package_id,)
    ).fetchone()[0]


# --- validation: name ---------------------------------------------------------


@pytest.mark.parametrize("name", ["ab", "x" * 60, "1 Hour", "  ab  "])
def test_valid_names_are_accepted(name: str) -> None:
    assert validate_package_input(good(name=name)).name == name.strip()


@pytest.mark.parametrize("name", ["", "a", "   ", "  a  ", "x" * 61, 123, ["ab"], True])
def test_bad_names_are_rejected(name: object) -> None:
    errors = errors_of(good(name=name))
    assert list(errors) == ["name"]


def test_name_length_message_states_the_limits() -> None:
    assert errors_of(good(name="a"))["name"] == "Must be 2 to 60 characters."


def test_missing_or_null_name_is_required() -> None:
    assert (
        errors_of({k: v for k, v in good().items() if k != "name"})["name"] == REQUIRED
    )
    assert errors_of(good(name=None))["name"] == REQUIRED


# --- validation: numbers ------------------------------------------------------

EDGE_OK = [(field, edge) for field, low, high in NUMERIC_RULES for edge in (low, high)]
EDGE_BAD = [
    (field, edge) for field, low, high in NUMERIC_RULES for edge in (low - 1, high + 1)
]


@pytest.mark.parametrize(("field", "value"), EDGE_OK, ids=lambda v: str(v))
def test_numbers_on_the_boundary_are_accepted(field: str, value: int) -> None:
    result = validate_package_input(good(**{field: value}))
    assert getattr(result, field) == value


@pytest.mark.parametrize(("field", "value"), EDGE_BAD, ids=lambda v: str(v))
def test_numbers_just_outside_the_boundary_are_rejected(field: str, value: int) -> None:
    assert list(errors_of(good(**{field: value}))) == [field]


@pytest.mark.parametrize("field", [f for f, _, _ in NUMERIC_RULES])
@pytest.mark.parametrize("value", ["20", 20.5, 20.0, True, False, [20], {"v": 20}])
def test_numbers_must_be_real_whole_numbers(field: str, value: object) -> None:
    # Text, decimals (even 20.0) and booleans are all refused. True is not 1.
    assert list(errors_of(good(**{field: value}))) == [field]


@pytest.mark.parametrize("field", [f for f, _, _ in NUMERIC_RULES])
def test_missing_or_null_number_is_required(field: str) -> None:
    assert errors_of({k: v for k, v in good().items() if k != field})[field] == REQUIRED
    assert errors_of(good(**{field: None}))[field] == REQUIRED


def test_number_message_states_the_range() -> None:
    assert (
        errors_of(good(price_kes=-1))["price_kes"]
        == "Must be a whole number from 0 to 100000."
    )
    assert (
        errors_of(good(speed_kbps=63))["speed_kbps"]
        == "Must be a whole number from 64 to 100000."
    )


# --- validation: data limit ---------------------------------------------------


@pytest.mark.parametrize("value", [None, 1, 500, 10**9])
def test_data_limit_none_or_positive_is_accepted(value: int | None) -> None:
    assert validate_package_input(good(data_limit_mb=value)).data_limit_mb == value


def test_data_limit_may_be_left_out_meaning_unlimited() -> None:
    data = good()
    del data["data_limit_mb"]
    assert validate_package_input(data).data_limit_mb is None


@pytest.mark.parametrize("value", [0, -1, -500, 1.5, "100", True, False, [1]])
def test_data_limit_must_be_positive_whole_number_or_none(value: object) -> None:
    assert list(errors_of(good(data_limit_mb=value))) == ["data_limit_mb"]


# --- validation: the whole body -----------------------------------------------


def test_every_problem_is_reported_at_once() -> None:
    errors = errors_of({"data_limit_mb": 0})
    assert set(errors) == {
        "name",
        "price_kes",
        "duration_minutes",
        "speed_kbps",
        "data_limit_mb",
    }


@pytest.mark.parametrize("body", [None, [], "text", 5, [good()]])
def test_body_that_is_not_an_object_is_one_body_error(body: object) -> None:
    assert errors_of(body) == {"body": "Request body must be a JSON object."}


def test_unknown_keys_are_ignored() -> None:
    result = validate_package_input(good(is_active=False, id=99, colour="red"))
    assert result == PackageInput(
        name="2 Hours",
        price_kes=35,
        duration_minutes=120,
        speed_kbps=4000,
        data_limit_mb=None,
    )


def test_validation_error_carries_field_messages_and_a_readable_text() -> None:
    error = ValidationError({"name": "bad", "price_kes": "worse"})
    assert error.errors == {"name": "bad", "price_kes": "worse"}
    assert "name: bad" in str(error)
    assert "price_kes: worse" in str(error)


def test_validation_error_keeps_its_own_copy_of_the_messages() -> None:
    source = {"name": "bad"}
    error = ValidationError(source)
    source["extra"] = "added later"
    assert error.errors == {"name": "bad"}


# --- list_for_portal ----------------------------------------------------------


def test_portal_list_is_empty_without_packages(service: PackageService) -> None:
    assert service.list_for_portal() == []


def test_portal_list_shows_only_active_packages_cheapest_first(
    service: PackageService, repo: PackageRepository
) -> None:
    dear = service.create(good(name="Week", price_kes=500))
    cheap = service.create(good(name="Hour", price_kes=20))
    retired = service.create(good(name="Old offer", price_kes=5))
    repo.set_active(retired.id, False)

    assert [p.name for p in service.list_for_portal()] == [cheap.name, dear.name]


# --- create -------------------------------------------------------------------


def test_create_stores_and_returns_the_package(service: PackageService) -> None:
    created = service.create(good(name="  3 Hours  ", data_limit_mb=2048))

    assert created.id > 0
    assert created.name == "3 Hours"  # trimmed
    assert created.data_limit_mb == 2048
    assert [p.id for p in service.list_for_portal()] == [created.id]


def test_create_with_invalid_data_stores_nothing(service: PackageService) -> None:
    with pytest.raises(ValidationError):
        service.create(good(price_kes=-5))
    assert service.list_for_portal() == []


def test_create_cannot_make_a_retired_package(
    service: PackageService, conn: sqlite3.Connection
) -> None:
    created = service.create(good(is_active=False))
    assert stored_is_active(conn, created.id) == 1


def test_duplicate_name_becomes_a_field_message_not_a_database_error(
    service: PackageService,
) -> None:
    service.create(good(name="Hour"))
    with pytest.raises(ValidationError) as caught:
        service.create(good(name="Hour"))
    assert caught.value.errors == {"name": "A package with this name already exists."}
    assert isinstance(caught.value.__cause__, sqlite3.IntegrityError)


def test_connection_is_still_usable_after_a_duplicate_name(
    service: PackageService,
) -> None:
    service.create(good(name="Hour"))
    with pytest.raises(ValidationError):
        service.create(good(name="Hour"))
    service.create(good(name="Day"))
    assert len(service.list_for_portal()) == 2


def test_unknown_database_errors_are_not_hidden(
    service: PackageService, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(_: PackageInput) -> None:
        raise sqlite3.IntegrityError("CHECK constraint failed: something_else")

    monkeypatch.setattr(service._repo, "create", explode)
    with pytest.raises(sqlite3.IntegrityError):
        service.create(good())


def test_service_never_commits(
    service: PackageService, conn: sqlite3.Connection
) -> None:
    # The caller owns the transaction (wbms.db.transaction), so a rollback must
    # be able to undo everything the service did.
    service.create(good())
    conn.rollback()
    assert service.list_for_portal() == []


# --- update -------------------------------------------------------------------


def test_update_replaces_every_editable_field(service: PackageService) -> None:
    original = service.create(good(name="Hour", price_kes=20, data_limit_mb=500))

    changed = service.update(
        original.id,
        good(name="One Hour", price_kes=25, duration_minutes=60, speed_kbps=2000),
    )

    assert changed.id == original.id
    assert (changed.name, changed.price_kes, changed.duration_minutes) == (
        "One Hour",
        25,
        60,
    )
    assert changed.speed_kbps == 2000
    assert (
        changed.data_limit_mb is None
    )  # replaced, so an omitted limit means unlimited


def test_update_keeping_the_same_name_is_not_a_duplicate(
    service: PackageService,
) -> None:
    original = service.create(good(name="Hour", price_kes=20))
    changed = service.update(original.id, good(name="Hour", price_kes=30))
    assert changed.price_kes == 30


def test_update_unknown_id_raises_unknown_package_error(
    service: PackageService,
) -> None:
    with pytest.raises(UnknownPackageError) as caught:
        service.update(999, good())
    assert caught.value.package_id == 999
    assert str(caught.value) == "Package 999 not found."


def test_update_with_invalid_data_leaves_the_package_unchanged(
    service: PackageService,
) -> None:
    original = service.create(good(name="Hour", price_kes=20))
    with pytest.raises(ValidationError):
        service.update(original.id, good(name="Hour", price_kes=-1))
    assert service.list_for_portal() == [original]


def test_update_validates_before_looking_up_the_id(service: PackageService) -> None:
    with pytest.raises(ValidationError):
        service.update(999, good(price_kes=-1))


def test_update_to_a_name_that_is_taken_is_a_field_message(
    service: PackageService,
) -> None:
    service.create(good(name="Hour"))
    day = service.create(good(name="Day"))
    with pytest.raises(ValidationError) as caught:
        service.update(day.id, good(name="Hour"))
    assert list(caught.value.errors) == ["name"]
    assert service.update(day.id, good(name="Day")).name == "Day"  # still usable


def test_update_never_changes_is_active(
    service: PackageService, repo: PackageRepository, conn: sqlite3.Connection
) -> None:
    original = service.create(good(name="Hour"))
    repo.set_active(original.id, False)

    service.update(original.id, good(name="Hour", price_kes=99, is_active=True))

    assert stored_is_active(conn, original.id) == 0  # a retired package stays retired
    assert service.list_for_portal() == []
