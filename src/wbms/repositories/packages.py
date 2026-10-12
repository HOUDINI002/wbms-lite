"""Repository for the ``packages`` table.

This module is the only place that knows how packages are stored. Everything
above it (services, routes) works with plain ``Package`` objects and never sees
SQL, rows or cursors.

Rules this file follows (slide 63):

* Every query uses ``?`` placeholders. Values are never formatted or joined
  into the SQL text, so a hostile package name can only ever be data.
* Rows become dataclasses in exactly one place: ``PackageRepository._to_package``.
* The repository never commits or rolls back. The caller owns the transaction;
  to make several changes succeed or fail together, wrap them in
  ``wbms.db.transaction()``.
"""

import sqlite3
from dataclasses import dataclass

# The columns we read, in the order ``_to_package`` unpacks them. Naming them
# explicitly (instead of ``SELECT *``) keeps this code working if a column is
# added to the table later.
_SELECT = (
    "SELECT id, name, price_kes, duration_minutes, data_limit_mb, "
    "speed_kbps, is_active FROM packages "
)


@dataclass(frozen=True, slots=True)
class Package:
    """A package as stored: what a customer can buy.

    ``data_limit_mb`` is ``None`` for unlimited data.
    """

    id: int
    name: str
    price_kes: int
    duration_minutes: int
    data_limit_mb: int | None
    speed_kbps: int
    is_active: bool


@dataclass(frozen=True, slots=True)
class PackageInput:
    """The editable fields of a package, used by ``create`` and ``update``.

    There is no ``id`` (the database assigns it) and no ``is_active`` (use
    ``PackageRepository.set_active``, so retiring a package is a deliberate act).
    """

    name: str
    price_kes: int
    duration_minutes: int
    speed_kbps: int
    data_limit_mb: int | None = None


class PackageNotFoundError(LookupError):
    """Raised when a package id does not exist and the caller cannot go on."""

    def __init__(self, package_id: int) -> None:
        super().__init__("No package with id " + str(package_id))
        self.package_id = package_id


class PackageRepository:
    """Reads and writes packages using one SQLite connection."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def list_active(self) -> list[Package]:
        """Return the packages on sale, cheapest first (ties broken by id)."""
        rows = self._conn.execute(
            _SELECT + "WHERE is_active = 1 ORDER BY price_kes, id"
        ).fetchall()
        return [self._to_package(row) for row in rows]

    def get(self, package_id: int) -> Package | None:
        """Return one package, active or not, or ``None`` if it does not exist."""
        row = self._conn.execute(_SELECT + "WHERE id = ?", (package_id,)).fetchone()
        return None if row is None else self._to_package(row)

    def create(self, data: PackageInput) -> Package:
        """Insert a new, active package and return it as stored.

        Raises ``sqlite3.IntegrityError`` if the database rejects it (duplicate
        name, negative price, and so on). Friendly messages are the service
        layer's job.
        """
        cursor = self._conn.execute(
            "INSERT INTO packages "
            "(name, price_kes, duration_minutes, data_limit_mb, speed_kbps) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                data.name,
                data.price_kes,
                data.duration_minutes,
                data.data_limit_mb,
                data.speed_kbps,
            ),
        )
        created = self.get(cursor.lastrowid)
        if created is None:  # pragma: no cover - cannot happen after an insert
            raise RuntimeError("package disappeared right after it was inserted")
        return created

    def update(self, package_id: int, data: PackageInput) -> Package | None:
        """Replace the editable fields of a package and return the new state.

        Returns ``None`` if there is no such package. The active flag is not
        touched; use ``set_active`` for that.
        """
        cursor = self._conn.execute(
            "UPDATE packages SET name = ?, price_kes = ?, duration_minutes = ?, "
            "data_limit_mb = ?, speed_kbps = ? WHERE id = ?",
            (
                data.name,
                data.price_kes,
                data.duration_minutes,
                data.data_limit_mb,
                data.speed_kbps,
                package_id,
            ),
        )
        if cursor.rowcount == 0:
            return None
        return self.get(package_id)

    def set_active(self, package_id: int, active: bool) -> None:
        """Put a package on sale (``True``) or retire it (``False``).

        Packages are retired, never deleted, because old transactions point at
        them. Raises ``PackageNotFoundError`` for an unknown id, so a typo does
        not silently do nothing.
        """
        cursor = self._conn.execute(
            "UPDATE packages SET is_active = ? WHERE id = ?",
            (1 if active else 0, package_id),
        )
        if cursor.rowcount == 0:
            raise PackageNotFoundError(package_id)

    @staticmethod
    def _to_package(row: tuple) -> Package:
        """Turn one database row into a ``Package``. The only place this happens.

        Unpacking by position works for ``sqlite3.Row`` and plain tuples alike.
        """
        (
            package_id,
            name,
            price_kes,
            duration_minutes,
            data_limit_mb,
            speed_kbps,
            is_active,
        ) = row
        return Package(
            id=package_id,
            name=name,
            price_kes=price_kes,
            duration_minutes=duration_minutes,
            data_limit_mb=data_limit_mb,
            speed_kbps=speed_kbps,
            is_active=bool(is_active),
        )
