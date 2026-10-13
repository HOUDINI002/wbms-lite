"""Tests for the captive portal page (Step 6).

These build a tiny Flask app that registers only the portal blueprint, so they
do not depend on ``create_app``, the database or any other fixture.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient

from wbms.web.portal import bp, normalize_mac


@pytest.fixture
def client() -> FlaskClient:
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY="test-only")
    app.register_blueprint(bp)
    return app.test_client()


def hidden_mac_value(html: str) -> str:
    match = re.search(r'<input type="hidden" name="mac" id="mac" value="([^"]*)"', html)
    assert match is not None, "hidden mac field not found"
    return match.group(1)


# ---------------------------------------------------------------- normalize_mac


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("AA:BB:CC:DD:EE:FF", "AA:BB:CC:DD:EE:FF"),
        ("aa:bb:cc:dd:ee:ff", "AA:BB:CC:DD:EE:FF"),
        ("aa-bb-cc-dd-ee-ff", "AA:BB:CC:DD:EE:FF"),
        ("  00:1A:2b:3C:4d:5E  ", "00:1A:2B:3C:4D:5E"),
        ("AA:BB:CC:DD:EE:FF\n", "AA:BB:CC:DD:EE:FF"),  # surrounding space is trimmed
    ],
)
def test_normalize_mac_accepts_valid_forms(raw: str, expected: str) -> None:
    assert normalize_mac(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "   ",
        "AA:BB:CC:DD:EE",  # too short
        "AA:BB:CC:DD:EE:FF:00",  # too long
        "AA:BB:CC:DD:EE:GG",  # not hex
        "AA:BB-CC:DD-EE:FF",  # mixed separators
        "AABBCCDDEEFF",  # no separators
        '"><script>alert(1)</script>',
    ],
)
def test_normalize_mac_rejects_everything_else(raw: str | None) -> None:
    assert normalize_mac(raw) == ""


# ------------------------------------------------------------------ GET /portal


def test_portal_returns_html(client: FlaskClient) -> None:
    response = client.get("/portal?mac=AA:BB:CC:DD:EE:FF")
    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert b"Buy Wi-Fi time" in response.data


def test_valid_mac_goes_into_the_hidden_field(client: FlaskClient) -> None:
    html = client.get("/portal?mac=aa-bb-cc-dd-ee-ff").get_data(as_text=True)
    assert hidden_mac_value(html) == "AA:BB:CC:DD:EE:FF"
    assert "mac-notice" not in html


def test_missing_mac_shows_the_notice_and_an_empty_field(client: FlaskClient) -> None:
    html = client.get("/portal").get_data(as_text=True)
    assert hidden_mac_value(html) == ""
    assert 'id="mac-notice"' in html
    assert 'data-mac-present="false"' in html


def test_invalid_mac_is_dropped_not_echoed(client: FlaskClient) -> None:
    hostile = '"><script>alert(1)</script>'
    html = client.get("/portal", query_string={"mac": hostile}).get_data(as_text=True)
    assert hidden_mac_value(html) == ""
    assert "alert(1)" not in html
    assert 'id="mac-notice"' in html


def test_page_marks_mac_present_for_a_valid_mac(client: FlaskClient) -> None:
    html = client.get("/portal?mac=AA:BB:CC:DD:EE:FF").get_data(as_text=True)
    assert 'data-mac-present="true"' in html


# ---------------------------------------------------------------- page contents


def test_page_points_javascript_at_the_json_api(client: FlaskClient) -> None:
    html = client.get("/portal").get_data(as_text=True)
    assert 'data-packages-url="/api/packages"' in html
    assert 'data-payments-url="/api/payments"' in html


def test_page_has_an_accessible_phone_field(client: FlaskClient) -> None:
    html = client.get("/portal").get_data(as_text=True)
    assert '<label for="phone">' in html
    assert 'id="phone"' in html
    assert 'type="tel"' in html
    assert 'aria-describedby="phone-hint phone-error"' in html
    assert 'id="phone-error"' in html


def test_page_has_a_pay_button_and_live_regions(client: FlaskClient) -> None:
    html = client.get("/portal").get_data(as_text=True)
    assert 'id="pay-button"' in html
    assert 'type="submit"' in html
    assert 'role="status"' in html
    assert 'aria-live="polite"' in html


def test_page_has_language_viewport_and_title(client: FlaskClient) -> None:
    html = client.get("/portal").get_data(as_text=True)
    assert '<html lang="en">' in html
    assert 'name="viewport"' in html
    assert "<title>" in html


def test_page_loads_its_own_css_and_js_from_the_portal_static_path(
    client: FlaskClient,
) -> None:
    html = client.get("/portal").get_data(as_text=True)
    assert 'href="/portal-static/portal.css"' in html
    assert 'src="/portal-static/portal.js"' in html


def test_page_has_no_inline_script_or_style(client: FlaskClient) -> None:
    html = client.get("/portal").get_data(as_text=True)
    assert not re.search(r"<script(?![^>]*\bsrc=)", html), "inline <script> found"
    assert "<style" not in html
    assert " style=" not in html


# ----------------------------------------------------------------- static files


@pytest.mark.parametrize(
    ("name", "expected_type"),
    [("portal.js", "javascript"), ("portal.css", "text/css")],
)
def test_static_files_are_served(
    client: FlaskClient, name: str, expected_type: str
) -> None:
    response = client.get(f"/portal-static/{name}")
    assert response.status_code == 200
    assert expected_type in response.mimetype
    assert len(response.data) > 100
    response.close()


def test_the_default_static_route_is_not_taken_over(client: FlaskClient) -> None:
    response = client.get("/static/portal.js")
    assert response.status_code == 404


def test_javascript_never_assigns_innerhtml() -> None:
    source = Path(bp.root_path, "static", "portal.js").read_text(encoding="utf-8")
    assert "innerHTML" not in source
    assert "document.write" not in source
    assert "eval(" not in source


# --------------------------------------------------------------------- headers


def test_security_headers_are_set(client: FlaskClient) -> None:
    response = client.get("/portal?mac=AA:BB:CC:DD:EE:FF")
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    policy = response.headers["Content-Security-Policy"]
    assert "default-src 'self'" in policy
    assert "frame-ancestors 'none'" in policy
    assert "unsafe-inline" not in policy


# --------------------------------------------------------------------- methods


@pytest.mark.parametrize("method", ["post", "put", "delete", "patch"])
def test_only_get_is_allowed(client: FlaskClient, method: str) -> None:
    response = getattr(client, method)("/portal")
    assert response.status_code == 405
