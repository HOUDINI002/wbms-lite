"""Unit tests for src/wbms/schema.sql (Step 3, prompt 1).

Each test proves one rule the database itself enforces, because the database is
the last line of defence when application code has a bug.
"""

from __future__ import annotations

import re
import sqlite3

import pytest

from wbms import create_app, db
from wbms.config import load_settings

TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
T0 = "2026-10-05T10:00:00Z"
T1 = "2026-10-05T11:00:00Z"


@pytest.fixture
def conn():
    app = create_app(load_settings({"SECRET_KEY": "test", "DATABASE_PATH": ":memory:"}))
    with app.app_context():
        db.init_db()
        yield db.get_db()


def run(conn, sql, params=()):
    """Execute one statement and return its cursor."""
    return conn.execute(sql, params)


def rejected(conn, sql, params=(), match=None):
    """Assert that the database refuses this statement."""
    with pytest.raises(sqlite3.IntegrityError, match=match):
        conn.execute(sql, params)


def add_package(conn, name="1 Hour", price=20, minutes=60, data=None, speed=2048):
    return run(
        conn,
        "INSERT INTO packages (name, price_kes, duration_minutes, data_limit_mb, speed_kbps)"
        " VALUES (?, ?, ?, ?, ?)",
        (name, price, minutes, data, speed),
    ).lastrowid


def add_customer(conn, phone="254712345678"):
    return run(conn, "INSERT INTO customers (phone_number) VALUES (?)", (phone,)).lastrowid


def add_transaction(conn, package_id, customer_id, status="pending", paid_at=None, ref=None):
    return run(
        conn,
        "INSERT INTO transactions (customer_id, package_id, amount_kes, status, paid_at,"
        " gateway_ref) VALUES (?, ?, 20, ?, ?, ?)",
        (customer_id, package_id, status, paid_at, ref),
    ).lastrowid


def add_paid_transaction(conn):
    return add_transaction(
        conn, add_package(conn), add_customer(conn), status="success", paid_at=T0
    )


def add_session(conn, transaction_id, started=T0, expires=T1, status="active", used=0):
    return run(
        conn,
        "INSERT INTO sessions (transaction_id, mac_address, started_at, expires_at,"
        " data_used_mb, status) VALUES (?, 'AA:BB:CC:DD:EE:FF', ?, ?, ?, ?)",
        (transaction_id, started, expires, used, status),
    ).lastrowid


# --- structure ------------------------------------------------------------


def test_all_six_tables_exist(conn):
    names = {r["name"] for r in run(conn, "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"packages", "customers", "transactions", "sessions", "vouchers", "admins"} <= names


def index_columns(conn, index_name):
    return [r["name"] for r in run(conn, f"PRAGMA index_info({index_name})")]


def test_required_indexes_exist_with_the_right_columns(conn):
    assert index_columns(conn, "idx_sessions_status_expires") == ["status", "expires_at"]
    assert index_columns(conn, "idx_transactions_status") == ["status"]


def test_overdue_session_query_uses_the_status_expires_index(conn):
    plan = " ".join(
        str(tuple(r))
        for r in run(
            conn,
            "EXPLAIN QUERY PLAN SELECT id FROM sessions"
            " WHERE status = 'active' AND expires_at <= ?",
            (T1,),
        )
    )
    assert "idx_sessions_status_expires" in plan


def test_running_the_schema_twice_keeps_existing_data(conn):
    add_package(conn)
    db.init_db()
    db.init_db()
    assert run(conn, "SELECT COUNT(*) FROM packages").fetchone()[0] == 1


def test_created_at_defaults_to_utc_iso_text(conn):
    add_customer(conn)
    value = run(conn, "SELECT created_at FROM customers").fetchone()[0]
    assert TIMESTAMP.match(value), value


# --- packages -------------------------------------------------------------


def test_free_package_is_allowed(conn):
    assert add_package(conn, price=0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"price": -1},
        {"minutes": 0},
        {"minutes": -5},
        {"data": 0},
        {"data": -10},
        {"speed": 0},
    ],
)
def test_package_numbers_must_be_in_range(conn, kwargs):
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        add_package(conn, **kwargs)


def test_unlimited_data_is_stored_as_null(conn):
    pid = add_package(conn, data=None)
    assert run(conn, "SELECT data_limit_mb FROM packages WHERE id=?", (pid,)).fetchone()[0] is None


def test_package_is_active_by_default_and_only_accepts_zero_or_one(conn):
    pid = add_package(conn)
    assert run(conn, "SELECT is_active FROM packages WHERE id=?", (pid,)).fetchone()[0] == 1
    rejected(conn, "UPDATE packages SET is_active = 2", match="CHECK constraint failed")


def test_package_names_are_unique_and_not_blank(conn):
    add_package(conn, name="1 Hour")
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint failed: packages.name"):
        add_package(conn, name="1 Hour")
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        add_package(conn, name="   ")


# --- customers ------------------------------------------------------------


def test_duplicate_phone_number_is_rejected(conn):
    add_customer(conn, "254712345678")
    with pytest.raises(sqlite3.IntegrityError, match="customers.phone_number"):
        add_customer(conn, "254712345678")


def test_blank_phone_number_is_rejected(conn):
    rejected(conn, "INSERT INTO customers (phone_number) VALUES ('  ')", match="CHECK")


# --- transactions ---------------------------------------------------------


def test_transaction_defaults(conn):
    tid = add_transaction(conn, add_package(conn), add_customer(conn))
    row = run(conn, "SELECT status, method, gateway_ref, paid_at FROM transactions WHERE id=?", (tid,)).fetchone()
    assert (row["status"], row["method"], row["gateway_ref"], row["paid_at"]) == (
        "pending",
        "mpesa",
        None,
        None,
    )


def test_unknown_transaction_status_is_rejected(conn):
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        add_transaction(conn, add_package(conn), add_customer(conn), status="refunded")


def test_unknown_payment_method_is_rejected(conn):
    pid, cid = add_package(conn), add_customer(conn)
    rejected(
        conn,
        "INSERT INTO transactions (customer_id, package_id, method, amount_kes)"
        " VALUES (?, ?, 'cash', 20)",
        (cid, pid),
        match="CHECK constraint failed",
    )


def test_negative_amount_is_rejected(conn):
    pid, cid = add_package(conn), add_customer(conn)
    rejected(
        conn,
        "INSERT INTO transactions (customer_id, package_id, amount_kes) VALUES (?, ?, -1)",
        (cid, pid),
        match="CHECK constraint failed",
    )


def test_mpesa_transaction_needs_a_customer(conn):
    rejected(
        conn,
        "INSERT INTO transactions (customer_id, package_id, amount_kes) VALUES (NULL, ?, 20)",
        (add_package(conn),),
        match="CHECK constraint failed",
    )


def test_voucher_transaction_may_have_no_customer(conn):
    pid = add_package(conn)
    run(
        conn,
        "INSERT INTO transactions (customer_id, package_id, method, amount_kes, status, paid_at)"
        " VALUES (NULL, ?, 'voucher', 0, 'success', ?)",
        (pid, T0),
    )


def test_success_requires_paid_at_and_pending_forbids_it(conn):
    pid, cid = add_package(conn), add_customer(conn)
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        add_transaction(conn, pid, cid, status="success", paid_at=None)
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        add_transaction(conn, pid, cid, status="pending", paid_at=T0)
    assert add_transaction(conn, pid, cid, status="success", paid_at=T0)


def test_gateway_ref_is_unique_but_may_be_null_many_times(conn):
    pid, cid = add_package(conn), add_customer(conn)
    add_transaction(conn, pid, cid, ref=None)
    add_transaction(conn, pid, cid, ref=None)  # two NULLs are fine
    add_transaction(conn, pid, cid, ref="ws_CO_1")
    with pytest.raises(sqlite3.IntegrityError, match="transactions.gateway_ref"):
        add_transaction(conn, pid, cid, ref="ws_CO_1")


def test_transaction_must_point_at_real_package_and_customer(conn):
    pid, cid = add_package(conn), add_customer(conn)
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        add_transaction(conn, 999, cid)
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        add_transaction(conn, pid, 999)


# --- sessions -------------------------------------------------------------


def test_only_one_session_per_transaction(conn):
    tid = add_paid_transaction(conn)
    add_session(conn, tid)
    with pytest.raises(sqlite3.IntegrityError, match="sessions.transaction_id"):
        add_session(conn, tid)


@pytest.mark.parametrize("status", ["pending_activation", "active", "expired", "revoked"])
def test_every_documented_session_status_is_accepted(conn, status):
    assert add_session(conn, add_paid_transaction(conn), status=status)


def test_unknown_session_status_is_rejected(conn):
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        add_session(conn, add_paid_transaction(conn), status="paused")


@pytest.mark.parametrize("started, expires", [(T1, T0), (T0, T0)])
def test_session_must_expire_after_it_starts(conn, started, expires):
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        add_session(conn, add_paid_transaction(conn), started=started, expires=expires)


def test_negative_data_used_is_rejected(conn):
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        add_session(conn, add_paid_transaction(conn), used=-1)


def test_session_must_point_at_a_real_transaction(conn):
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        add_session(conn, 999)


def test_timestamps_compare_correctly_as_text(conn):
    tid = add_paid_transaction(conn)
    add_session(conn, tid, started=T0, expires=T1)
    due = run(conn, "SELECT COUNT(*) FROM sessions WHERE status='active' AND expires_at <= ?", ("2026-10-05T11:00:00Z",)).fetchone()[0]
    not_due = run(conn, "SELECT COUNT(*) FROM sessions WHERE status='active' AND expires_at <= ?", ("2026-10-05T10:59:59Z",)).fetchone()[0]
    assert (due, not_due) == (1, 0)


# --- vouchers -------------------------------------------------------------


def add_voucher(conn, code="WBK7M2QX9P", status="unused", redeemed_at=None, package_id=None):
    package_id = package_id or add_package(conn, name=f"pkg-{code}")
    return run(
        conn,
        "INSERT INTO vouchers (code, package_id, status, batch_id, redeemed_at)"
        " VALUES (?, ?, ?, 'batch-1', ?)",
        (code, package_id, status, redeemed_at),
    ).lastrowid


def test_voucher_codes_are_unique(conn):
    pid = add_package(conn)
    add_voucher(conn, "AAAA", package_id=pid)
    with pytest.raises(sqlite3.IntegrityError, match="vouchers.code"):
        add_voucher(conn, "AAAA", package_id=pid)


def test_unknown_voucher_status_is_rejected(conn):
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        add_voucher(conn, status="expired")


def test_redeemed_voucher_needs_redeemed_at_and_unused_forbids_it(conn):
    pid = add_package(conn)
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        add_voucher(conn, "R1", status="redeemed", redeemed_at=None, package_id=pid)
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        add_voucher(conn, "U1", status="unused", redeemed_at=T0, package_id=pid)
    assert add_voucher(conn, "R2", status="redeemed", redeemed_at=T0, package_id=pid)
    assert add_voucher(conn, "V1", status="void", package_id=pid)


def test_voucher_must_point_at_a_real_package(conn):
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        add_voucher(conn, package_id=999)


# --- admins ---------------------------------------------------------------


def test_admin_usernames_are_unique(conn):
    sql = "INSERT INTO admins (username, password_hash) VALUES (?, 'hash')"
    run(conn, sql, ("boss",))
    with pytest.raises(sqlite3.IntegrityError, match="admins.username"):
        run(conn, sql, ("boss",))


def test_admin_needs_a_password_hash(conn):
    rejected(conn, "INSERT INTO admins (username, password_hash) VALUES ('x', '')", match="CHECK")
    rejected(conn, "INSERT INTO admins (username) VALUES ('y')", match="NOT NULL")


# --- ON DELETE RESTRICT ---------------------------------------------------


def test_a_package_that_has_been_sold_cannot_be_deleted(conn):
    pid = add_package(conn)
    add_transaction(conn, pid, add_customer(conn))
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        run(conn, "DELETE FROM packages WHERE id = ?", (pid,))


def test_a_package_with_vouchers_cannot_be_deleted(conn):
    pid = add_package(conn)
    add_voucher(conn, package_id=pid)
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        run(conn, "DELETE FROM packages WHERE id = ?", (pid,))


def test_a_customer_with_transactions_cannot_be_deleted(conn):
    cid = add_customer(conn)
    add_transaction(conn, add_package(conn), cid)
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        run(conn, "DELETE FROM customers WHERE id = ?", (cid,))


def test_a_transaction_with_a_session_cannot_be_deleted(conn):
    tid = add_paid_transaction(conn)
    add_session(conn, tid)
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        run(conn, "DELETE FROM transactions WHERE id = ?", (tid,))


def test_unused_rows_can_still_be_deleted(conn):
    pid = add_package(conn)
    run(conn, "DELETE FROM packages WHERE id = ?", (pid,))
    assert run(conn, "SELECT COUNT(*) FROM packages").fetchone()[0] == 0
