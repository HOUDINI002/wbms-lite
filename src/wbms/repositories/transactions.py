"""Transaction repository: the only code that runs SQL on ``transactions``.

Allowed status moves (slide 56): pending -> success, pending -> failed.
Every UPDATE below is guarded with ``AND status = 'pending'`` so an illegal
move changes nothing instead of corrupting a finished payment.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


def iso_utc(moment: datetime) -> str:
    """Format an aware datetime as ``2026-10-13T12:00:00Z`` (UTC).

    One fixed format keeps string comparison in SQL equal to time order.
    """
    if moment.tzinfo is None:
        raise ValueError("naive datetime: clocks must return timezone-aware UTC")
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class Transaction:
    """One payment attempt."""

    id: int
    customer_id: int
    package_id: int
    amount_kes: int
    status: str
    gateway_ref: str | None
    receipt: str | None
    created_at: str
    paid_at: str | None
    mac_address: str | None


def ensure_mac_column(conn: sqlite3.Connection) -> None:
    """Add ``transactions.mac_address`` if the table does not have it yet.

    The device MAC must survive from "start payment" until the callback
    starts the session (Step 9), so it is stored on the transaction.
    Safe to run any number of times.
    """
    columns = {row[1] for row in conn.execute("PRAGMA table_info(transactions)")}
    if "mac_address" not in columns:
        conn.execute("ALTER TABLE transactions ADD COLUMN mac_address TEXT")
        conn.commit()


class TransactionRepository:
    """Reads and writes transactions using one SQLite connection."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, transaction_id: int) -> Transaction | None:
        """Return one transaction by id, or None."""
        row = self._conn.execute(
            "SELECT * FROM transactions WHERE id = ?", (transaction_id,)
        ).fetchone()
        return self._to_transaction(row) if row else None

    def get_by_gateway_ref(self, gateway_ref: str) -> Transaction | None:
        """Return the transaction the gateway knows as ``gateway_ref``, or None."""
        row = self._conn.execute(
            "SELECT * FROM transactions WHERE gateway_ref = ?", (gateway_ref,)
        ).fetchone()
        return self._to_transaction(row) if row else None

    def insert_pending(
        self,
        customer_id: int,
        package_id: int,
        amount_kes: int,
        mac_address: str,
        created_at: str,
    ) -> Transaction:
        """Insert a new transaction in the ``pending`` state."""
        cursor = self._conn.execute(
            "INSERT INTO transactions "
            "(customer_id, package_id, amount_kes, status, mac_address, created_at) "
            "VALUES (?, ?, ?, 'pending', ?, ?)",
            (customer_id, package_id, amount_kes, mac_address, created_at),
        )
        created = self.get(int(cursor.lastrowid))
        if created is None:  # pragma: no cover - cannot happen after insert
            raise RuntimeError("transaction insert did not produce a row")
        return created

    def find_recent_pending(
        self, customer_id: int, package_id: int, since: str
    ) -> Transaction | None:
        """Newest pending transaction for this customer and package since ``since``."""
        row = self._conn.execute(
            "SELECT * FROM transactions "
            "WHERE customer_id = ? AND package_id = ? AND status = 'pending' "
            "AND created_at >= ? ORDER BY id DESC LIMIT 1",
            (customer_id, package_id, since),
        ).fetchone()
        return self._to_transaction(row) if row else None

    def set_gateway_ref(self, transaction_id: int, gateway_ref: str) -> bool:
        """Store the gateway's checkout id. True if a pending row was updated."""
        cursor = self._conn.execute(
            "UPDATE transactions SET gateway_ref = ? "
            "WHERE id = ? AND status = 'pending'",
            (gateway_ref, transaction_id),
        )
        return cursor.rowcount == 1

    def mark_success(self, transaction_id: int, receipt: str, paid_at: str) -> bool:
        """Move pending -> success with receipt and paid_at, in one statement.

        The schema ties ``status = 'success'`` to ``paid_at IS NOT NULL``, so both
        are written together. Returns False if the row was no longer pending,
        which is how a duplicate or concurrent callback is detected.
        """
        cursor = self._conn.execute(
            "UPDATE transactions SET status = 'success', receipt = ?, paid_at = ? "
            "WHERE id = ? AND status = 'pending'",
            (receipt, paid_at, transaction_id),
        )
        return cursor.rowcount == 1

    def mark_failed(self, transaction_id: int) -> bool:
        """Move pending -> failed. False if the row was not pending."""
        cursor = self._conn.execute(
            "UPDATE transactions SET status = 'failed' "
            "WHERE id = ? AND status = 'pending'",
            (transaction_id,),
        )
        return cursor.rowcount == 1

    @staticmethod
    def _to_transaction(row: sqlite3.Row) -> Transaction:
        return Transaction(
            id=row["id"],
            customer_id=row["customer_id"],
            package_id=row["package_id"],
            amount_kes=row["amount_kes"],
            status=row["status"],
            gateway_ref=row["gateway_ref"],
            receipt=row["receipt"],
            created_at=row["created_at"],
            paid_at=row["paid_at"],
            mac_address=row["mac_address"],
        )
