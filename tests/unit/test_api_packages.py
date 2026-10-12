"""Tests for the package JSON routes, using the Flask test client (Step 5, slide 64).

The routes are mounted on a tiny Flask app of their own and pointed at an
in-memory database, so these tests do not depend on how ``create_app`` is built.
``tests/integration/test_api_packages_integration.py`` checks the real wiring.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient

from wbms.repositories.packages import PackageInput, PackageRepository
from wbms.web import api_packages

SCHEMA = Path(__file__).resolve().parents[2] / "src" / "wbms" / "schema.sql"

PACKAGE_KEYS = {
    "id",
    "name",
    "price_kes",
    "duration_minutes",
    "speed_kbps",
    "data_limit_mb",
}


@pytest.fixture
def db() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA.read_text(encoding="utf-8"))
    yield connection
    connection.close()


@pytest.fixture
def client(db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch) -> FlaskClient:
    @contextmanager
    def transaction() -> Iterator[sqlite3.Connection]:
        # Same contract as wbms.db.transaction: commit on success, undo on error.
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise

    monkeypatch.setattr(api_packages, "get_db", lambda: db)
    monkeypatch.setattr(api_packages, "transaction", transaction)

    app = Flask(__name__)
    app.register_blueprint(api_packages.bp)
    return app.test_client()


def body_for(**changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "name": "2 Hours",
        "price_kes": 35,
        "duration_minutes": 120,
        "speed_kbps": 4000,
    }
    data.update(changes)
    return data


def add(db: sqlite3.Connection, name: str, price: int, *, active: bool = True) -> int:
    repo = PackageRepository(db)
    package = repo.create(
        PackageInput(name=name, price_kes=price, duration_minutes=60, speed_kbps=2000)
    )
    if not active:
        repo.set_active(package.id, False)
    db.commit()
    return package.id


def count(db: sqlite3.Connection) -> int:
    return db.execute("SELECT COUNT(*) FROM packages").fetchone()[0]


def assert_error_shape(response: Any, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status
    assert response.is_json
    error = response.get_json()["error"]
    assert error["code"] == code
    assert isinstance(error["message"], str) and error["message"]
    return error


# --- GET /api/packages --------------------------------------------------------


def test_list_is_empty_when_there_are_no_packages(client: FlaskClient) -> None:
    response = client.get("/api/packages")
    assert response.status_code == 200
    assert response.get_json() == {"packages": []}


def test_list_shows_only_active_packages_cheapest_first(
    client: FlaskClient, db: sqlite3.Connection
) -> None:
    add(db, "Week", 500)
    add(db, "Hour", 20)
    add(db, "Old offer", 5, active=False)

    packages = client.get("/api/packages").get_json()["packages"]

    assert [p["name"] for p in packages] == ["Hour", "Week"]


def test_list_items_carry_what_the_portal_needs(
    client: FlaskClient, db: sqlite3.Connection
) -> None:
    add(db, "Hour", 20)
    package = client.get("/api/packages").get_json()["packages"][0]
    assert package.keys() >= PACKAGE_KEYS
    assert package["data_limit_mb"] is None  # JSON null means unlimited


def test_list_needs_no_login(client: FlaskClient) -> None:
    assert client.get("/api/packages").status_code == 200


# --- POST /api/packages -------------------------------------------------------


def test_post_creates_a_package_and_answers_201(
    client: FlaskClient, db: sqlite3.Connection
) -> None:
    response = client.post(
        "/api/packages", json=body_for(name="  3 Hours  ", data_limit_mb=2048)
    )

    assert response.status_code == 201
    package = response.get_json()["package"]
    assert package.keys() >= PACKAGE_KEYS
    assert package["name"] == "3 Hours"
    assert package["data_limit_mb"] == 2048
    assert count(db) == 1
    assert [p["id"] for p in client.get("/api/packages").get_json()["packages"]] == [
        package["id"]
    ]


def test_post_is_saved_for_good(client: FlaskClient, db: sqlite3.Connection) -> None:
    client.post("/api/packages", json=body_for())
    db.rollback()  # throws away anything not committed
    assert count(db) == 1


def test_post_with_broken_rules_answers_400_with_field_messages(
    client: FlaskClient, db: sqlite3.Connection
) -> None:
    response = client.post("/api/packages", json={"name": "a", "price_kes": -1})

    error = assert_error_shape(response, 400, "validation_error")
    assert set(error["fields"]) == {
        "name",
        "price_kes",
        "duration_minutes",
        "speed_kbps",
    }
    assert error["fields"]["name"] == "Must be 2 to 60 characters."
    assert count(db) == 0


@pytest.mark.parametrize(
    "send",
    [
        pytest.param(lambda c: c.post("/api/packages"), id="no body"),
        pytest.param(
            lambda c: c.post(
                "/api/packages", data="{oops", content_type="application/json"
            ),
            id="broken json",
        ),
        pytest.param(
            lambda c: c.post("/api/packages", data="name=x", content_type="text/plain"),
            id="not json",
        ),
        pytest.param(lambda c: c.post("/api/packages", json=[body_for()]), id="array"),
        pytest.param(lambda c: c.post("/api/packages", json="text"), id="string"),
    ],
)
def test_post_without_a_json_object_answers_400(
    client: FlaskClient, db: sqlite3.Connection, send: Any
) -> None:
    error = assert_error_shape(send(client), 400, "validation_error")
    assert "JSON object" in error["fields"]["body"]
    assert count(db) == 0


def test_post_duplicate_name_answers_400_and_changes_nothing(
    client: FlaskClient, db: sqlite3.Connection
) -> None:
    add(db, "Hour", 20)

    response = client.post("/api/packages", json=body_for(name="Hour"))

    error = assert_error_shape(response, 400, "validation_error")
    assert error["fields"] == {"name": "A package with this name already exists."}
    assert count(db) == 1


def test_post_cannot_create_a_retired_package(client: FlaskClient) -> None:
    client.post("/api/packages", json=body_for(is_active=False))
    assert len(client.get("/api/packages").get_json()["packages"]) == 1


# --- PUT /api/packages/<id> ---------------------------------------------------


def test_put_replaces_the_package_and_answers_200(
    client: FlaskClient, db: sqlite3.Connection
) -> None:
    package_id = add(db, "Hour", 20)

    response = client.put(
        f"/api/packages/{package_id}", json=body_for(name="Hour", price_kes=25)
    )

    assert response.status_code == 200
    package = response.get_json()["package"]
    assert (package["id"], package["price_kes"]) == (package_id, 25)
    stored = db.execute(
        "SELECT price_kes FROM packages WHERE id = ?", (package_id,)
    ).fetchone()
    assert stored[0] == 25


def test_put_unknown_id_answers_404_in_the_standard_shape(client: FlaskClient) -> None:
    response = client.put("/api/packages/999", json=body_for())
    error = assert_error_shape(response, 404, "not_found")
    assert error["message"] == "Package 999 not found."
    assert "fields" not in error


def test_put_with_broken_rules_answers_400_and_changes_nothing(
    client: FlaskClient, db: sqlite3.Connection
) -> None:
    package_id = add(db, "Hour", 20)

    response = client.put(
        f"/api/packages/{package_id}", json=body_for(name="Hour", speed_kbps=1)
    )

    error = assert_error_shape(response, 400, "validation_error")
    assert list(error["fields"]) == ["speed_kbps"]
    stored = db.execute(
        "SELECT speed_kbps FROM packages WHERE id = ?", (package_id,)
    ).fetchone()
    assert stored[0] == 2000


def test_put_to_a_taken_name_answers_400(
    client: FlaskClient, db: sqlite3.Connection
) -> None:
    add(db, "Hour", 20)
    day = add(db, "Day", 100)
    response = client.put(f"/api/packages/{day}", json=body_for(name="Hour"))
    assert_error_shape(response, 400, "validation_error")


def test_put_without_a_body_answers_400(
    client: FlaskClient, db: sqlite3.Connection
) -> None:
    package_id = add(db, "Hour", 20)
    assert_error_shape(
        client.put(f"/api/packages/{package_id}"), 400, "validation_error"
    )


def test_put_cannot_revive_a_retired_package(
    client: FlaskClient, db: sqlite3.Connection
) -> None:
    package_id = add(db, "Old", 5, active=False)
    client.put(f"/api/packages/{package_id}", json=body_for(name="Old", is_active=True))
    assert client.get("/api/packages").get_json() == {"packages": []}


def test_put_with_a_non_numeric_id_is_a_404(client: FlaskClient) -> None:
    assert_error_shape(
        client.put("/api/packages/abc", json=body_for()), 404, "not_found"
    )


# --- errors outside the handlers ----------------------------------------------


def test_unknown_api_url_answers_json_404(client: FlaskClient) -> None:
    assert_error_shape(client.get("/api/nothing-here"), 404, "not_found")


def test_unknown_page_keeps_the_normal_html_404(client: FlaskClient) -> None:
    response = client.get("/nothing-here")
    assert response.status_code == 404
    assert not response.is_json


def test_wrong_method_on_the_api_answers_json_405(client: FlaskClient) -> None:
    assert_error_shape(client.delete("/api/packages"), 405, "method_not_allowed")


def test_wrong_method_on_a_page_keeps_the_normal_html_405(client: FlaskClient) -> None:
    response = client.post("/nothing-here")
    assert response.status_code in (404, 405)
    assert not response.is_json


# --- the admin stub -----------------------------------------------------------


def test_require_admin_stub_keeps_the_view_name_and_calls_it() -> None:
    # Placeholder until M5: today it lets everyone through. When the real login
    # arrives this test is replaced by "answers 401 without a login".
    @api_packages.require_admin
    def view(x: int) -> int:
        """doc"""
        return x + 1

    assert view(1) == 2
    assert view.__name__ == "view"
    assert view.__doc__ == "doc"


def test_post_and_put_routes_are_wrapped_by_require_admin() -> None:
    # Guards against dropping the decorator: wraps() leaves a __wrapped__ trail.
    assert hasattr(api_packages.create_package, "__wrapped__")
    assert hasattr(api_packages.update_package, "__wrapped__")
    assert not hasattr(api_packages.list_packages, "__wrapped__")
