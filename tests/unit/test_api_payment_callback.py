"""Unit tests for POST /api/payments/callback/<secret> (Step 9)."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask

import wbms
from wbms.repositories.customers import CustomerRepository
from wbms.repositories.packages import PackageRepository
from wbms.repositories.transactions import TransactionRepository, ensure_mac_column
from wbms.services.payments import PaymentService
from wbms.web import api_payments

SECRET = "s3cret-token"
ACCEPTED = {"ResultCode": 0, "ResultDesc": "Accepted"}


def stk(checkout_id: str, code: int = 0, amount: int = 20) -> dict:
    callback: dict = {"CheckoutRequestID": checkout_id, "ResultCode": code}
    if code == 0:
        callback["CallbackMetadata"] = {
            "Item": [
                {"Name": "Amount", "Value": amount},
                {"Name": "MpesaReceiptNumber", "Value": "QJK1ABC23"},
            ]
        }
    return {"Body": {"stkCallback": callback}}


class OkGateway:
    def initiate(self, phone, amount_kes, reference):
        return SimpleNamespace(checkout_id=f"ws_CO_{reference}", status="pending")


class FakeSessions:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def start_session(self, transaction, mac):
        self.calls.append(transaction)


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
def sessions() -> FakeSessions:
    return FakeSessions()


@pytest.fixture
def service(conn, sessions) -> PaymentService:
    @contextmanager
    def scope():
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    return PaymentService(
        TransactionRepository(conn),
        CustomerRepository(conn),
        PackageRepository(conn),
        OkGateway(),
        lambda: datetime(2026, 10, 13, 12, 0, 0, tzinfo=timezone.utc),
        tx_scope=scope,
        session_starter=sessions,
    )


def make_client(service, secret: str = SECRET):
    app = Flask(__name__)
    app.register_blueprint(api_payments.bp)
    app.extensions[api_payments.SERVICE_FACTORY_KEY] = lambda: service
    app.extensions[api_payments.CALLBACK_SECRET_KEY] = secret
    return app.test_client()


def status_of(conn, tx_id: int) -> str:
    return conn.execute(
        "SELECT status FROM transactions WHERE id = ?", (tx_id,)
    ).fetchone()[0]


def test_callback_success_returns_accepted_and_confirms_the_payment(
    service, conn, sessions
):
    tx = service.start_payment("0712345671", 1, "AA:BB:CC:DD:EE:FF")
    client = make_client(service)

    response = client.post(
        f"/api/payments/callback/{SECRET}", json=stk(tx.gateway_ref)
    )

    assert response.status_code == 200
    assert response.get_json() == ACCEPTED
    assert status_of(conn, tx.id) == "success"
    assert len(sessions.calls) == 1


def test_callback_failure_returns_accepted_and_marks_failed(service, conn):
    tx = service.start_payment("0712345671", 1, "AA:BB:CC:DD:EE:FF")
    client = make_client(service)

    response = client.post(
        f"/api/payments/callback/{SECRET}", json=stk(tx.gateway_ref, code=1032)
    )

    assert response.get_json() == ACCEPTED
    assert status_of(conn, tx.id) == "failed"


def test_callback_wrong_secret_returns_403_and_changes_nothing(
    service, conn, sessions
):
    tx = service.start_payment("0712345671", 1, "AA:BB:CC:DD:EE:FF")
    client = make_client(service)

    response = client.post("/api/payments/callback/wrong", json=stk(tx.gateway_ref))

    assert response.status_code == 403
    assert "ResultCode" not in response.get_json()
    assert status_of(conn, tx.id) == "pending"
    assert sessions.calls == []


@pytest.mark.parametrize("guess", [SECRET[:-1], SECRET + "x", SECRET.upper(), "é"])
def test_callback_near_miss_secrets_are_rejected(service, guess):
    client = make_client(service)

    response = client.post(f"/api/payments/callback/{guess}", json=stk("x"))

    assert response.status_code == 403


def test_callback_is_refused_when_no_secret_is_configured(service):
    client = make_client(service, secret="")

    response = client.post("/api/payments/callback/anything", json=stk("x"))

    assert response.status_code == 403


def test_callback_duplicate_returns_accepted_and_keeps_one_session(
    service, conn, sessions
):
    tx = service.start_payment("0712345671", 1, "AA:BB:CC:DD:EE:FF")
    client = make_client(service)
    url = f"/api/payments/callback/{SECRET}"

    first = client.post(url, json=stk(tx.gateway_ref))
    second = client.post(url, json=stk(tx.gateway_ref))

    assert first.get_json() == second.get_json() == ACCEPTED
    assert len(sessions.calls) == 1


def test_callback_unknown_reference_still_returns_accepted(service):
    client = make_client(service)

    response = client.post(f"/api/payments/callback/{SECRET}", json=stk("nope"))

    assert response.status_code == 200 and response.get_json() == ACCEPTED


@pytest.mark.parametrize("body", [b"not json", b"[]", b""])
def test_callback_bad_body_with_right_secret_returns_accepted(service, body):
    client = make_client(service)

    response = client.post(
        f"/api/payments/callback/{SECRET}", data=body, content_type="application/json"
    )

    assert response.status_code == 200 and response.get_json() == ACCEPTED


def test_callback_internal_error_still_returns_accepted_and_changes_nothing(
    service, conn
):
    tx = service.start_payment("0712345671", 1, "AA:BB:CC:DD:EE:FF")

    class Broken(FakeSessions):
        def start_session(self, transaction, mac):
            raise RuntimeError("router down")

    service._session_starter = Broken()
    client = make_client(service)

    response = client.post(
        f"/api/payments/callback/{SECRET}", json=stk(tx.gateway_ref)
    )

    assert response.status_code == 200 and response.get_json() == ACCEPTED
    assert status_of(conn, tx.id) == "pending"


def test_callback_amount_mismatch_returns_accepted_but_grants_nothing(
    service, conn, sessions
):
    tx = service.start_payment("0712345671", 1, "AA:BB:CC:DD:EE:FF")
    client = make_client(service)

    response = client.post(
        f"/api/payments/callback/{SECRET}", json=stk(tx.gateway_ref, amount=1)
    )

    assert response.get_json() == ACCEPTED
    assert status_of(conn, tx.id) == "pending"
    assert sessions.calls == []
