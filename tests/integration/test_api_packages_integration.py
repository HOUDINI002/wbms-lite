"""Packages API through the real application factory (Step 5, slide 64).

Unlike the unit tests, nothing is replaced here: the real ``create_app``, the
real ``get_db`` and ``transaction`` and a real SQLite file in a temporary folder.
It also proves the blueprint is registered in ``create_app``.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from flask.testing import FlaskClient

from wbms import create_app

SCHEMA = Path(__file__).resolve().parents[2] / "src" / "wbms" / "schema.sql"

NOT_WIRED = (
    "GET /api/packages did not answer 200. Register the blueprint inside create_app: "
    "from wbms.web.api_packages import bp as api_packages_bp; "
    "app.register_blueprint(api_packages_bp)  (see README, Step 5)."
)


@pytest.fixture
def database_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "wbms-test.sqlite3"
    with closing(sqlite3.connect(path)) as setup:
        setup.executescript(SCHEMA.read_text(encoding="utf-8"))
    monkeypatch.setenv("SECRET_KEY", "pytest-only-secret-key-not-for-real-use")
    monkeypatch.setenv("DATABASE_PATH", str(path))
    return path


@pytest.fixture
def client(database_file: Path) -> FlaskClient:
    return create_app().test_client()


def rows_in(path: Path) -> list[tuple[str, int]]:
    with closing(sqlite3.connect(path)) as check:
        return check.execute(
            "SELECT name, price_kes FROM packages ORDER BY id"
        ).fetchall()


def test_blueprint_is_registered_in_the_real_app(client: FlaskClient) -> None:
    response = client.get("/api/packages")
    assert response.status_code == 200, NOT_WIRED
    assert response.get_json() == {"packages": []}


def test_create_list_update_round_trip_is_saved_in_the_file(
    client: FlaskClient, database_file: Path
) -> None:
    created = client.post(
        "/api/packages",
        json={
            "name": "1 Hour",
            "price_kes": 20,
            "duration_minutes": 60,
            "speed_kbps": 2000,
        },
    )
    assert created.status_code == 201
    package_id = created.get_json()["package"]["id"]
    assert rows_in(database_file) == [
        ("1 Hour", 20)
    ]  # committed by the real transaction()

    updated = client.put(
        f"/api/packages/{package_id}",
        json={
            "name": "1 Hour",
            "price_kes": 25,
            "duration_minutes": 60,
            "speed_kbps": 2000,
        },
    )
    assert updated.status_code == 200
    assert rows_in(database_file) == [("1 Hour", 25)]

    listed = client.get("/api/packages").get_json()["packages"]
    assert [(p["name"], p["price_kes"]) for p in listed] == [("1 Hour", 25)]


def test_a_rejected_request_leaves_the_file_untouched(
    client: FlaskClient, database_file: Path
) -> None:
    good = {
        "name": "1 Hour",
        "price_kes": 20,
        "duration_minutes": 60,
        "speed_kbps": 2000,
    }
    assert client.post("/api/packages", json=good).status_code == 201

    duplicate = client.post("/api/packages", json=good)
    invalid = client.post("/api/packages", json={**good, "name": "x", "price_kes": -1})

    assert duplicate.status_code == 400
    assert invalid.status_code == 400
    assert rows_in(database_file) == [("1 Hour", 20)]


def test_unknown_package_is_a_json_404_through_the_real_app(
    client: FlaskClient,
) -> None:
    response = client.put(
        "/api/packages/12345",
        json={"name": "Ghost", "price_kes": 1, "duration_minutes": 1, "speed_kbps": 64},
    )
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "not_found"


def test_health_still_works_with_the_new_blueprint(client: FlaskClient) -> None:
    assert client.get("/health").status_code == 200
