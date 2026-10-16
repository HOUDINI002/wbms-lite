"""Customer repository: the only code that runs SQL on ``customers``."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class Customer:
    """A paying customer, identified by a normalized phone number."""

    id: int
    phone_number: str
    created_at: str


class CustomerRepository:
    """Reads and writes customers using one SQLite connection."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get_by_phone(self, phone_number: str) -> Customer | None:
        """Return the customer with this phone number, or None."""
        row = self._conn.execute(
            "SELECT id, phone_number, created_at FROM customers "
            "WHERE phone_number = ?",
            (phone_number,),
        ).fetchone()
        return self._to_customer(row) if row else None

    def upsert(self, phone_number: str, created_at: str) -> Customer:
        """Create the customer if new, then return the stored row.

        ``ON CONFLICT DO NOTHING`` leans on the UNIQUE constraint, so two
        requests for the same phone can never create two customers.
        """
        self._conn.execute(
            "INSERT INTO customers (phone_number, created_at) VALUES (?, ?) "
            "ON CONFLICT(phone_number) DO NOTHING",
            (phone_number, created_at),
        )
        customer = self.get_by_phone(phone_number)
        if customer is None:  # pragma: no cover - cannot happen after insert
            raise RuntimeError("customer upsert did not produce a row")
        return customer

    @staticmethod
    def _to_customer(row: sqlite3.Row) -> Customer:
        return Customer(
            id=row["id"],
            phone_number=row["phone_number"],
            created_at=row["created_at"],
        )
