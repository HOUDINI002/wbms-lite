"""Unit tests for the customer and transaction repositories (Step 8)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import wbms
from wbms.repositories.customers import CustomerRepository
from wbms.repositories.transactions import (
    TransactionRepository,
    ensure_mac_column,
    iso_utc,
)

NOW = "2026-10-13T12:00:00Z"


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


def test_iso_utc_formats_in_utc():
    eat = timezone(timedelta(hours=3))
    assert iso_utc(datetime(2026, 10, 13, 15, 0, tzinfo=eat)) == NOW


def test_iso_utc_rejects_naive_datetimes():
    with pytest.raises(ValueError):
        iso_utc(datetime(2026, 10, 13, 12, 0))


def test_ensure_mac_column_is_idempotent(conn):
    ensure_mac_column(conn)
    ensure_mac_column(conn)

    columns = [row[1] for row in conn.execute("PRAGMA table_info(transactions)")]
    assert columns.count("mac_address") == 1


def test_customer_upsert_returns_same_row_for_same_phone(conn):
    repo = CustomerRepository(conn)

    first = repo.upsert("254712345671", NOW)
    second = repo.upsert("254712345671", "2026-10-14T00:00:00Z")

    assert second.id == first.id
    assert second.created_at == NOW


def test_customer_get_by_phone_returns_none_when_missing(conn):
    assert CustomerRepository(conn).get_by_phone("254700000000") is None


def test_insert_pending_creates_pending_row_without_gateway_ref(conn):
    customer = CustomerRepository(conn).upsert("254712345671", NOW)

    tx = TransactionRepository(conn).insert_pending(
        customer.id, 1, 20, "AA:BB:CC:DD:EE:FF", NOW
    )

    assert tx.status == "pending"
    assert tx.gateway_ref is None
    assert tx.receipt is None and tx.paid_at is None


def test_mark_failed_only_moves_pending_transactions(conn):
    customer = CustomerRepository(conn).upsert("254712345671", NOW)
    repo = TransactionRepository(conn)
    tx = repo.insert_pending(customer.id, 1, 20, "AA:BB:CC:DD:EE:FF", NOW)
    conn.execute(
        "UPDATE transactions SET status = 'success', receipt = 'R1', paid_at = ? "
        "WHERE id = ?",
        (NOW, tx.id),
    )

    assert repo.mark_failed(tx.id) is False
    assert repo.get(tx.id).status == "success"


def test_set_gateway_ref_refuses_finished_transactions(conn):
    customer = CustomerRepository(conn).upsert("254712345671", NOW)
    repo = TransactionRepository(conn)
    tx = repo.insert_pending(customer.id, 1, 20, "AA:BB:CC:DD:EE:FF", NOW)
    repo.mark_failed(tx.id)

    assert repo.set_gateway_ref(tx.id, "ws_1") is False
    assert repo.get(tx.id).gateway_ref is None


def test_gateway_ref_must_be_unique(conn):
    customer = CustomerRepository(conn).upsert("254712345671", NOW)
    repo = TransactionRepository(conn)
    a = repo.insert_pending(customer.id, 1, 20, "AA:BB:CC:DD:EE:FF", NOW)
    b = repo.insert_pending(customer.id, 1, 20, "AA:BB:CC:DD:EE:FF", NOW)
    repo.set_gateway_ref(a.id, "ws_1")

    with pytest.raises(sqlite3.IntegrityError):
        repo.set_gateway_ref(b.id, "ws_1")


def test_find_recent_pending_ignores_old_and_finished_transactions(conn):
    customer = CustomerRepository(conn).upsert("254712345671", NOW)
    repo = TransactionRepository(conn)
    old = repo.insert_pending(
        customer.id, 1, 20, "AA:BB:CC:DD:EE:FF", "2026-10-13T11:00:00Z"
    )
    done = repo.insert_pending(customer.id, 1, 20, "AA:BB:CC:DD:EE:FF", NOW)
    repo.mark_failed(done.id)

    assert repo.find_recent_pending(customer.id, 1, "2026-10-13T11:59:00Z") is None
    assert repo.find_recent_pending(customer.id, 1, "2026-10-13T10:00:00Z").id == old.id
