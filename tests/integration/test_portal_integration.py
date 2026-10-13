"""The portal page through the real application factory (Step 6).

These fail with a helpful message until the portal blueprint is registered in
``create_app``. Run ``python scripts/register_blueprints.py`` to do that.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from flask.testing import FlaskClient

from wbms import create_app

NOT_WIRED = (
    "GET /portal did not answer 200. Register the portal blueprint inside "
    "create_app: from wbms.web.portal import bp as portal_bp; "
    "app.register_blueprint(portal_bp)  "
    "(or run: python scripts/register_blueprints.py; see README, Step 6)."
)


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FlaskClient:
    monkeypatch.setenv("SECRET_KEY", "integration-test-only")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "wbms-test.sqlite3"))
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def test_portal_is_registered_in_the_real_app(client: FlaskClient) -> None:
    response = client.get("/portal?mac=AA:BB:CC:DD:EE:FF")
    assert response.status_code == 200, NOT_WIRED
    assert b"Choose a package" in response.data


def test_portal_assets_are_served_by_the_real_app(client: FlaskClient) -> None:
    for name in ("portal.js", "portal.css"):
        response = client.get(f"/portal-static/{name}")
        assert response.status_code == 200, f"{name} not served; {NOT_WIRED}"
        response.close()


def test_health_still_works_next_to_the_portal(client: FlaskClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}
