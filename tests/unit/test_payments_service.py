"""Unit tests for PaymentService, normalize_phone and normalize_mac (Step 8)."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import wbms
from wbms.gateways.payments.base import GatewayError
from wbms.gateways.payments.mock import MockPaymentGateway
from wbms.repositories.customers import CustomerRepository
from wbms.repositories.packages import PackageRepository
from wbms.repositories.transactions import TransactionRepository, ensure_mac_column
from wbms.services.packages import ValidationError
from wbms.services.payments import PaymentService, normalize_mac, normalize_phone

GOOD_PHONE = "0712345671"
GOOD_MAC = "aa:bb:cc:dd:ee:ff"


class FakeClock:
    """Controllable clock: call it for 'now', advance() to move time."""

    def __init__(self) -> None:
        self.now = datetime(2026, 10, 13, 12, 0, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class RecordingGateway:
    """Gateway that records arguments and returns a pending receipt."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int, str]] = []

    def initiate(self, phone: str, amount_kes: int, reference: str):
        self.calls.append((phone, amount_kes, reference))
        return SimpleNamespace(checkout_id=f"ws_CO_{reference}", status="pending")


class FailingGateway:
    """Gateway that always raises the given exception."""

    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls = 0

    def initiate(self, phone: str, amount_kes: int, reference: str):
        self.calls += 1
        raise self.error


class RejectingGateway:
    """Gateway that answers, but with a failed status."""

    def initiate(self, phone: str, amount_kes: int, reference: str):
        return SimpleNamespace(checkout_id="x", status="failed")


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
    connection.execute(
        "INSERT INTO packages (id, name, price_kes, duration_minutes, speed_kbps,"
        " is_active) VALUES (2, '24 hours', 100, 1440, 2048, 1)"
    )
    connection.execute(
        "INSERT INTO packages (id, name, price_kes, duration_minutes, speed_kbps,"
        " is_active) VALUES (3, 'retired', 50, 120, 2048, 0)"
    )
    connection.commit()
    yield connection
    connection.close()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


def make_service(conn, gateway, clock, **kwargs) -> PaymentService:
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
        gateway,
        clock,
        tx_scope=scope,
        **kwargs,
    )


def count(conn, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# --- normalize_phone / normalize_mac ---------------------------------------


@pytest.mark.parametrize(
    "raw",
    ["0712345678", "+254712345678", "254712345678", "712345678", "0712 345-678"],
)
def test_normalize_phone_accepts_common_kenyan_formats(raw):
    assert normalize_phone(raw) == "254712345678"


def test_normalize_phone_accepts_01_prefix_numbers():
    assert normalize_phone("0112345678") == "254112345678"


@pytest.mark.parametrize(
    "raw",
    ["", "abc", "07123", "0812345678", "+255712345678", "07123456789", None, 712345678],
)
def test_normalize_phone_rejects_invalid_numbers(raw):
    with pytest.raises(ValidationError):
        normalize_phone(raw)


def test_normalize_mac_uppercases_and_uses_colons():
    assert normalize_mac(" aa-bb-cc-dd-ee-ff ") == "AA:BB:CC:DD:EE:FF"


@pytest.mark.parametrize("raw", ["", "AA:BB:CC", "GG:BB:CC:DD:EE:FF", None])
def test_normalize_mac_rejects_invalid_values(raw):
    with pytest.raises(ValidationError):
        normalize_mac(raw)


# --- start_payment ----------------------------------------------------------


def test_start_payment_happy_path_creates_pending_transaction(conn, clock):
    gateway = MockPaymentGateway()
    service = make_service(conn, gateway, clock)

    tx = service.start_payment(GOOD_PHONE, 1, GOOD_MAC)

    assert tx.status == "pending"
    assert tx.amount_kes == 20
    assert tx.package_id == 1
    assert tx.mac_address == "AA:BB:CC:DD:EE:FF"
    assert tx.gateway_ref
    assert len(gateway.calls) == 1
    stored = conn.execute(
        "SELECT * FROM transactions WHERE id = ?", (tx.id,)
    ).fetchone()
    assert stored["gateway_ref"] == tx.gateway_ref
    assert stored["status"] == "pending"


def test_start_payment_sends_normalized_phone_and_transaction_id_to_gateway(
    conn, clock
):
    gateway = RecordingGateway()
    service = make_service(conn, gateway, clock)

    tx = service.start_payment("+254 712 345 671", 2, GOOD_MAC)

    assert gateway.calls == [("254712345671", 100, str(tx.id))]
    assert tx.gateway_ref == f"ws_CO_{tx.id}"


def test_start_payment_upserts_customer_with_normalized_phone(conn, clock):
    service = make_service(conn, RecordingGateway(), clock)

    service.start_payment("0712345671", 1, GOOD_MAC)
    service.start_payment("+254712345671", 2, GOOD_MAC)

    assert count(conn, "customers") == 1
    phone = conn.execute("SELECT phone_number FROM customers").fetchone()[0]
    assert phone == "254712345671"
    assert count(conn, "transactions") == 2


@pytest.mark.parametrize("package_id", [999, 3, 0, -1])
def test_start_payment_unknown_or_inactive_package_is_rejected(conn, clock, package_id):
    gateway = RecordingGateway()
    service = make_service(conn, gateway, clock)

    with pytest.raises(ValidationError) as caught:
        service.start_payment(GOOD_PHONE, package_id, GOOD_MAC)

    assert "package_id" in caught.value.errors
    assert gateway.calls == []
    assert count(conn, "transactions") == 0
    assert count(conn, "customers") == 0


def test_start_payment_free_package_cannot_be_paid_for(conn, clock):
    conn.execute("UPDATE packages SET price_kes = 0 WHERE id = 1")
    service = make_service(conn, RecordingGateway(), clock)

    with pytest.raises(ValidationError):
        service.start_payment(GOOD_PHONE, 1, GOOD_MAC)


@pytest.mark.parametrize("phone", ["", "12345", "0812345678", "not a phone"])
def test_start_payment_invalid_phone_is_rejected_before_any_write(conn, clock, phone):
    gateway = RecordingGateway()
    service = make_service(conn, gateway, clock)

    with pytest.raises(ValidationError) as caught:
        service.start_payment(phone, 1, GOOD_MAC)

    assert "phone" in caught.value.errors
    assert gateway.calls == []
    assert count(conn, "transactions") == 0


def test_start_payment_invalid_mac_is_rejected(conn, clock):
    service = make_service(conn, RecordingGateway(), clock)

    with pytest.raises(ValidationError) as caught:
        service.start_payment(GOOD_PHONE, 1, "nope")

    assert "mac" in caught.value.errors
    assert count(conn, "transactions") == 0


def test_start_payment_gateway_error_marks_transaction_failed(conn, clock):
    gateway = FailingGateway(GatewayError("provider down"))
    service = make_service(conn, gateway, clock)

    with pytest.raises(GatewayError):
        service.start_payment(GOOD_PHONE, 1, GOOD_MAC)

    row = conn.execute("SELECT status, gateway_ref FROM transactions").fetchone()
    assert row["status"] == "failed"
    assert row["gateway_ref"] is None
    assert count(conn, "customers") == 1


def test_start_payment_unexpected_gateway_exception_still_marks_failed(conn, clock):
    service = make_service(conn, FailingGateway(TimeoutError("slow")), clock)

    with pytest.raises(TimeoutError):
        service.start_payment(GOOD_PHONE, 1, GOOD_MAC)

    assert conn.execute("SELECT status FROM transactions").fetchone()[0] == "failed"


def test_start_payment_gateway_failed_status_marks_transaction_failed(conn, clock):
    service = make_service(conn, RejectingGateway(), clock)

    with pytest.raises(GatewayError):
        service.start_payment(GOOD_PHONE, 1, GOOD_MAC)

    assert conn.execute("SELECT status FROM transactions").fetchone()[0] == "failed"


def test_start_payment_pending_row_is_committed_before_gateway_is_called(conn, clock):
    seen: dict[str, str] = {}

    class SpyGateway:
        def initiate(self, phone, amount_kes, reference):
            row = conn.execute(
                "SELECT status FROM transactions WHERE id = ?", (int(reference),)
            ).fetchone()
            seen["status"] = row["status"]
            return SimpleNamespace(checkout_id="ws_1", status="pending")

    make_service(conn, SpyGateway(), clock).start_payment(GOOD_PHONE, 1, GOOD_MAC)

    assert seen["status"] == "pending"


# --- repeated requests ------------------------------------------------------


def test_repeated_request_within_window_returns_same_transaction(conn, clock):
    gateway = RecordingGateway()
    service = make_service(conn, gateway, clock)
    first = service.start_payment("0712345671", 1, GOOD_MAC)

    clock.advance(30)
    second = service.start_payment("+254712345671", 1, GOOD_MAC)

    assert second.id == first.id
    assert len(gateway.calls) == 1
    assert count(conn, "transactions") == 1


def test_repeated_request_after_window_creates_new_transaction(conn, clock):
    gateway = RecordingGateway()
    service = make_service(conn, gateway, clock, dedupe_window_seconds=120)
    first = service.start_payment(GOOD_PHONE, 1, GOOD_MAC)

    clock.advance(121)
    second = service.start_payment(GOOD_PHONE, 1, GOOD_MAC)

    assert second.id != first.id
    assert len(gateway.calls) == 2


def test_repeated_request_for_different_package_is_a_new_payment(conn, clock):
    service = make_service(conn, RecordingGateway(), clock)

    first = service.start_payment(GOOD_PHONE, 1, GOOD_MAC)
    second = service.start_payment(GOOD_PHONE, 2, GOOD_MAC)

    assert second.id != first.id


def test_retry_after_gateway_failure_is_allowed_immediately(conn, clock):
    failing = make_service(conn, FailingGateway(GatewayError("down")), clock)
    with pytest.raises(GatewayError):
        failing.start_payment(GOOD_PHONE, 1, GOOD_MAC)

    working = make_service(conn, RecordingGateway(), clock)
    retry = working.start_payment(GOOD_PHONE, 1, GOOD_MAC)

    assert retry.status == "pending"
    assert count(conn, "transactions") == 2


def test_naive_clock_is_rejected(conn):
    service = make_service(conn, RecordingGateway(), lambda: datetime(2026, 1, 1))

    with pytest.raises(ValueError):
        service.start_payment(GOOD_PHONE, 1, GOOD_MAC)
