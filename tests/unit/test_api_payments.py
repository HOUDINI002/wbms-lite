"""Unit tests for POST /api/payments using the Flask test client (Step 8)."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask

import wbms
from wbms.gateways.payments.base import GatewayError
from wbms.repositories.customers import CustomerRepository
from wbms.repositories.packages import PackageRepository
from wbms.repositories.transactions import TransactionRepository, ensure_mac_column
from wbms.services.payments import PaymentService
from wbms.web import api_payments
from wbms.web.rate_limit import RateLimiter

GOOD = {"phone": "0712345671", "package_id": 1, "mac": "AA:BB:CC:DD:EE:FF"}


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 13, 12, 0, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class OkGateway:
    def initiate(self, phone, amount_kes, reference):
        return SimpleNamespace(checkout_id=f"ws_CO_{reference}", status="pending")


class DownGateway:
    def initiate(self, phone, amount_kes, reference):
        raise GatewayError("provider down")


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(Path(wbms.__file__).with_name("schema.sql").read_text())
    ensure_mac_column(connection)
    connection.execute(
        "INSERT INTO packages (id, name, price_kes, duration_minutes, speed_kbps,"
        " is_active) VALUES (1, '1 hour', 20, 60, 2048, 1)"
    )
    connection.commit()
    yield connection
    connection.close()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


def make_client(conn, clock, gateway=None):
    @contextmanager
    def scope():
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    service = PaymentService(
        TransactionRepository(conn),
        CustomerRepository(conn),
        PackageRepository(conn),
        gateway or OkGateway(),
        clock,
        tx_scope=scope,
    )
    app = Flask(__name__)
    app.register_blueprint(api_payments.bp)
    app.extensions[api_payments.SERVICE_FACTORY_KEY] = lambda: service
    app.extensions[api_payments.LIMITER_KEY] = RateLimiter(5, 60, clock)
    return app.test_client()


def rows(conn, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_post_payment_valid_request_returns_202_and_pending_transaction(conn, clock):
    client = make_client(conn, clock)

    response = client.post("/api/payments", json=GOOD)

    assert response.status_code == 202
    body = response.get_json()
    assert body["status"] == "pending"
    stored = conn.execute("SELECT * FROM transactions").fetchone()
    assert stored["id"] == body["transaction_id"]
    assert stored["gateway_ref"] == f"ws_CO_{body['transaction_id']}"


def test_post_payment_accepts_package_id_sent_as_digit_string(conn, clock):
    client = make_client(conn, clock)

    response = client.post("/api/payments", json={**GOOD, "package_id": "1"})

    assert response.status_code == 202


@pytest.mark.parametrize("package_id", [True, 1.5, "abc", None, [1]])
def test_post_payment_bad_package_id_type_returns_400(conn, clock, package_id):
    client = make_client(conn, clock)

    response = client.post("/api/payments", json={**GOOD, "package_id": package_id})

    assert response.status_code == 400
    assert "package_id" in response.get_json()["fields"]
    assert rows(conn, "transactions") == 0


def test_post_payment_missing_fields_returns_400_with_each_field(conn, clock):
    client = make_client(conn, clock)

    response = client.post("/api/payments", json={})

    assert response.status_code == 400
    assert set(response.get_json()["fields"]) == {"phone", "mac", "package_id"}


@pytest.mark.parametrize("payload", [b"not json", b"[1, 2]", b'"text"'])
def test_post_payment_non_object_body_returns_400(conn, clock, payload):
    client = make_client(conn, clock)

    response = client.post(
        "/api/payments", data=payload, content_type="application/json"
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_json"


def test_post_payment_invalid_phone_returns_400_with_field_error(conn, clock):
    client = make_client(conn, clock)

    response = client.post("/api/payments", json={**GOOD, "phone": "12345"})

    assert response.status_code == 400
    assert "phone" in response.get_json()["fields"]
    assert rows(conn, "transactions") == 0


def test_post_payment_unknown_package_returns_400(conn, clock):
    client = make_client(conn, clock)

    response = client.post("/api/payments", json={**GOOD, "package_id": 99})

    assert response.status_code == 400
    assert "package_id" in response.get_json()["fields"]


def test_post_payment_gateway_failure_returns_502_and_marks_failed(conn, clock):
    client = make_client(conn, clock, DownGateway())

    response = client.post("/api/payments", json=GOOD)

    assert response.status_code == 502
    assert response.get_json()["error"] == "gateway_error"
    assert "provider down" not in response.get_data(as_text=True)
    assert conn.execute("SELECT status FROM transactions").fetchone()[0] == "failed"


def test_post_payment_sixth_request_in_a_minute_returns_429(conn, clock):
    client = make_client(conn, clock)
    for _ in range(5):
        assert client.post("/api/payments", json=GOOD).status_code == 202

    response = client.post("/api/payments", json=GOOD)

    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) >= 1
    assert response.get_json()["error"] == "rate_limited"


def test_post_payment_allowed_again_after_the_window(conn, clock):
    client = make_client(conn, clock)
    for _ in range(6):
        client.post("/api/payments", json=GOOD)

    clock.advance(60)

    assert client.post("/api/payments", json=GOOD).status_code == 202


def test_post_payment_rate_limit_is_per_ip(conn, clock):
    client = make_client(conn, clock)
    for _ in range(6):
        client.post(
            "/api/payments", json=GOOD, environ_overrides={"REMOTE_ADDR": "1.1.1.1"}
        )

    other = client.post(
        "/api/payments", json=GOOD, environ_overrides={"REMOTE_ADDR": "2.2.2.2"}
    )

    assert other.status_code == 202


def test_post_payment_invalid_requests_also_count_toward_the_limit(conn, clock):
    client = make_client(conn, clock)
    for _ in range(5):
        assert client.post("/api/payments", json={}).status_code == 400

    assert client.post("/api/payments", json=GOOD).status_code == 429
