"""Unit tests for PaymentService.apply_callback (Step 9)."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import wbms
from wbms.repositories.customers import CustomerRepository
from wbms.repositories.packages import PackageRepository
from wbms.repositories.transactions import TransactionRepository, ensure_mac_column
from wbms.services.payments import CallbackOutcome, PaymentService

MAC = "AA:BB:CC:DD:EE:FF"


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


class FakeSessions:
    """Records start_session calls; can be told to fail."""

    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[tuple[object, str]] = []
        self.error = error

    def start_session(self, transaction, mac):
        if self.error:
            raise self.error
        self.calls.append((transaction, mac))


def stk(checkout_id: str, code=0, amount=20, receipt="QJK1ABC23", desc="ok") -> dict:
    callback: dict = {
        "MerchantRequestID": "m-1",
        "CheckoutRequestID": checkout_id,
        "ResultCode": code,
        "ResultDesc": desc,
    }
    if code == 0:
        items = []
        if amount is not None:
            items.append({"Name": "Amount", "Value": amount})
        if receipt is not None:
            items.append({"Name": "MpesaReceiptNumber", "Value": receipt})
        items.append({"Name": "PhoneNumber", "Value": 254712345671})
        callback["CallbackMetadata"] = {"Item": items}
    return {"Body": {"stkCallback": callback}}


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
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


@pytest.fixture
def sessions() -> FakeSessions:
    return FakeSessions()


@pytest.fixture
def service(conn, clock, sessions) -> PaymentService:
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
        clock,
        tx_scope=scope,
        session_starter=sessions,
    )


def row(conn, tx_id: int):
    return conn.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()


def test_callback_success_marks_transaction_success_with_receipt_and_paid_at(
    service, conn, clock
):
    tx = service.start_payment("0712345671", 1, MAC)
    clock.advance(25)

    outcome = service.apply_callback(stk(tx.gateway_ref))

    assert outcome is CallbackOutcome.SUCCESS
    saved = row(conn, tx.id)
    assert saved["status"] == "success"
    assert saved["receipt"] == "QJK1ABC23"
    assert saved["paid_at"] == "2026-10-13T12:00:25Z"


def test_callback_success_starts_exactly_one_session_for_the_device(
    service, sessions
):
    tx = service.start_payment("0712345671", 1, MAC)

    service.apply_callback(stk(tx.gateway_ref))

    assert len(sessions.calls) == 1
    started, mac = sessions.calls[0]
    assert started.id == tx.id and started.status == "success"
    assert mac == MAC


@pytest.mark.parametrize("amount", [20, 20.0, "20", "20.00"])
def test_callback_success_accepts_amount_in_any_numeric_form(service, amount):
    tx = service.start_payment("0712345671", 1, MAC)

    outcome = service.apply_callback(stk(tx.gateway_ref, amount=amount))

    assert outcome is CallbackOutcome.SUCCESS


def test_callback_success_accepts_result_code_sent_as_text(service):
    tx = service.start_payment("0712345671", 1, MAC)
    payload = stk(tx.gateway_ref)
    payload["Body"]["stkCallback"]["ResultCode"] = "0"

    assert service.apply_callback(payload) is CallbackOutcome.SUCCESS


@pytest.mark.parametrize("code", [1, 1032, 1037, 2001])
def test_callback_failure_marks_transaction_failed_and_grants_nothing(
    service, conn, sessions, code
):
    tx = service.start_payment("0712345671", 1, MAC)

    outcome = service.apply_callback(stk(tx.gateway_ref, code=code, desc="declined"))

    assert outcome is CallbackOutcome.FAILED
    saved = row(conn, tx.id)
    assert saved["status"] == "failed"
    assert saved["paid_at"] is None and saved["receipt"] is None
    assert sessions.calls == []


def test_callback_duplicate_changes_nothing_and_keeps_one_session(
    service, conn, clock, sessions
):
    tx = service.start_payment("0712345671", 1, MAC)
    service.apply_callback(stk(tx.gateway_ref))
    before = tuple(row(conn, tx.id))
    clock.advance(600)

    outcome = service.apply_callback(stk(tx.gateway_ref, receipt="OTHER999"))

    assert outcome is CallbackOutcome.DUPLICATE
    assert tuple(row(conn, tx.id)) == before
    assert len(sessions.calls) == 1


def test_callback_failure_after_success_changes_nothing(service, conn, sessions):
    tx = service.start_payment("0712345671", 1, MAC)
    service.apply_callback(stk(tx.gateway_ref))

    outcome = service.apply_callback(stk(tx.gateway_ref, code=1032))

    assert outcome is CallbackOutcome.DUPLICATE
    assert row(conn, tx.id)["status"] == "success"
    assert len(sessions.calls) == 1


def test_callback_success_after_failure_grants_no_access(service, conn, sessions):
    tx = service.start_payment("0712345671", 1, MAC)
    service.apply_callback(stk(tx.gateway_ref, code=1032))

    outcome = service.apply_callback(stk(tx.gateway_ref))

    assert outcome is CallbackOutcome.DUPLICATE
    assert row(conn, tx.id)["status"] == "failed"
    assert sessions.calls == []


def test_callback_unknown_reference_is_ignored(service, conn, sessions):
    tx = service.start_payment("0712345671", 1, MAC)

    outcome = service.apply_callback(stk("ws_CO_does_not_exist"))

    assert outcome is CallbackOutcome.IGNORED
    assert row(conn, tx.id)["status"] == "pending"
    assert sessions.calls == []


@pytest.mark.parametrize("amount", [1, 19, 21, 200, "abc", None])
def test_callback_amount_mismatch_does_not_grant_access(
    service, conn, sessions, amount
):
    tx = service.start_payment("0712345671", 1, MAC)

    outcome = service.apply_callback(stk(tx.gateway_ref, amount=amount))

    assert outcome in (CallbackOutcome.AMOUNT_MISMATCH, CallbackOutcome.INVALID)
    saved = row(conn, tx.id)
    assert saved["status"] == "pending" and saved["paid_at"] is None
    assert sessions.calls == []


def test_callback_amount_mismatch_is_reported_as_amount_mismatch(service):
    tx = service.start_payment("0712345671", 1, MAC)

    assert service.apply_callback(stk(tx.gateway_ref, amount=19)) is (
        CallbackOutcome.AMOUNT_MISMATCH
    )


def test_callback_success_without_receipt_is_invalid_and_changes_nothing(
    service, conn, sessions
):
    tx = service.start_payment("0712345671", 1, MAC)

    outcome = service.apply_callback(stk(tx.gateway_ref, receipt=None))

    assert outcome is CallbackOutcome.INVALID
    assert row(conn, tx.id)["status"] == "pending"
    assert sessions.calls == []


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        "text",
        {},
        {"Body": {}},
        {"Body": {"stkCallback": {}}},
        {"Body": {"stkCallback": {"CheckoutRequestID": "", "ResultCode": 0}}},
        {"Body": {"stkCallback": {"CheckoutRequestID": "x", "ResultCode": True}}},
        {"Body": {"stkCallback": {"CheckoutRequestID": "x", "ResultCode": "ok"}}},
        {"Body": {"stkCallback": {"CheckoutRequestID": 5, "ResultCode": 0}}},
    ],
)
def test_callback_malformed_payload_is_invalid_and_changes_nothing(
    service, conn, sessions, payload
):
    tx = service.start_payment("0712345671", 1, MAC)

    outcome = service.apply_callback(payload)

    assert outcome is CallbackOutcome.INVALID
    assert row(conn, tx.id)["status"] == "pending"
    assert sessions.calls == []


def test_callback_only_changes_the_transaction_it_refers_to(service, conn):
    first = service.start_payment("0712345671", 1, MAC)
    second = service.start_payment("0712345672", 1, MAC)

    service.apply_callback(stk(second.gateway_ref))

    assert row(conn, first.id)["status"] == "pending"
    assert row(conn, second.id)["status"] == "success"


def test_callback_session_start_failure_rolls_back_the_payment(
    service, conn, clock
):
    tx = service.start_payment("0712345671", 1, MAC)
    service._session_starter = FakeSessions(error=RuntimeError("router down"))

    with pytest.raises(RuntimeError):
        service.apply_callback(stk(tx.gateway_ref))

    saved = row(conn, tx.id)
    assert saved["status"] == "pending"
    assert saved["paid_at"] is None and saved["receipt"] is None


def test_callback_after_rollback_can_be_applied_again(service, conn):
    tx = service.start_payment("0712345671", 1, MAC)
    sessions = FakeSessions()
    failing = FakeSessions(error=RuntimeError("router down"))
    service._session_starter = failing
    with pytest.raises(RuntimeError):
        service.apply_callback(stk(tx.gateway_ref))
    service._session_starter = sessions

    outcome = service.apply_callback(stk(tx.gateway_ref))

    assert outcome is CallbackOutcome.SUCCESS
    assert len(sessions.calls) == 1


def test_mark_success_only_wins_once(conn):
    repo = TransactionRepository(conn)
    customer = CustomerRepository(conn).upsert("254712345671", "2026-10-13T12:00:00Z")
    tx = repo.insert_pending(customer.id, 1, 20, MAC, "2026-10-13T12:00:00Z")

    first = repo.mark_success(tx.id, "R1", "2026-10-13T12:01:00Z")
    second = repo.mark_success(tx.id, "R2", "2026-10-13T12:02:00Z")

    assert (first, second) == (True, False)
    assert repo.get(tx.id).receipt == "R1"


def test_get_by_gateway_ref_returns_none_for_unknown_reference(conn):
    assert TransactionRepository(conn).get_by_gateway_ref("nope") is None


def test_callback_for_a_finished_payment_is_duplicate_even_if_amount_differs(
    service, sessions
):
    tx = service.start_payment("0712345671", 1, MAC)
    service.apply_callback(stk(tx.gateway_ref))

    outcome = service.apply_callback(stk(tx.gateway_ref, amount=1))

    assert outcome is CallbackOutcome.DUPLICATE
    assert len(sessions.calls) == 1
