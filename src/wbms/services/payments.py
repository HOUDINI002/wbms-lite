"""Payment service: start a mobile-money payment (Step 8).

Flow of ``start_payment``:

1. Clean and validate the inputs (phone, MAC, package).
2. In one short database transaction: upsert the customer and insert a
   *pending* transaction. This commits before any network call, so the
   payment is on record even if the process dies mid-request.
3. Call the gateway outside the database transaction (a slow network call
   must never hold the SQLite write lock).
4. In a second short transaction: store the gateway's checkout id in
   ``gateway_ref``, or mark the transaction ``failed`` if the gateway errors.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime, timedelta

from wbms.gateways.payments.base import GatewayError, PaymentGateway
from wbms.repositories.customers import CustomerRepository
from wbms.repositories.packages import PackageRepository
from wbms.repositories.transactions import (
    Transaction,
    TransactionRepository,
    iso_utc,
)
from wbms.services.packages import ValidationError

logger = logging.getLogger(__name__)

Clock = Callable[[], datetime]
TxScope = Callable[[], AbstractContextManager[object]]

_MAC_RE = re.compile(r"^[0-9A-Fa-f]{2}([:-][0-9A-Fa-f]{2}){5}$")
_KE_MOBILE_RE = re.compile(r"^254[17]\d{8}$")


def _invalid(field: str, message: str) -> ValidationError:
    """Build a ValidationError with one field-level message."""
    return ValidationError({field: message})


def normalize_phone(raw: str) -> str:
    """Return a Kenyan mobile number as ``2547XXXXXXXX`` (or ``2541XXXXXXXX``).

    Accepts ``0712 345 678``, ``+254712345678``, ``254712345678`` and
    ``712345678``. Raises ValidationError for anything else.
    """
    if not isinstance(raw, str):
        raise _invalid("phone", "Enter a valid Kenyan phone number.")
    digits = re.sub(r"[\s\-().]", "", raw)
    if digits.startswith("+"):
        digits = digits[1:]
    if not digits.isdigit():
        raise _invalid("phone", "Enter a valid Kenyan phone number.")
    if digits.startswith("0") and len(digits) == 10:
        digits = "254" + digits[1:]
    elif len(digits) == 9 and digits[0] in "17":
        digits = "254" + digits
    if not _KE_MOBILE_RE.match(digits):
        raise _invalid("phone", "Enter a valid Kenyan phone number.")
    return digits


def normalize_mac(raw: str) -> str:
    """Return a MAC address as upper-case ``AA:BB:CC:DD:EE:FF``."""
    if not isinstance(raw, str) or not _MAC_RE.match(raw.strip()):
        raise _invalid("mac", "Device address (MAC) is not valid.")
    return raw.strip().replace("-", ":").upper()


def _mask(phone: str) -> str:
    """Keep only the last three digits for logs (no full numbers in logs)."""
    return "*" * (len(phone) - 3) + phone[-3:]


def _default_tx_scope() -> AbstractContextManager[object]:
    """Use the project's ``transaction()`` context manager from ``db.py``."""
    from wbms.db import transaction

    return transaction()


class PaymentService:
    """Business rules for starting a payment."""

    def __init__(
        self,
        tx_repo: TransactionRepository,
        customer_repo: CustomerRepository,
        package_repo: PackageRepository,
        gateway: PaymentGateway,
        clock: Clock,
        *,
        tx_scope: TxScope | None = None,
        dedupe_window_seconds: int = 120,
    ) -> None:
        self._tx_repo = tx_repo
        self._customer_repo = customer_repo
        self._package_repo = package_repo
        self._gateway = gateway
        self._clock = clock
        self._tx_scope = tx_scope or _default_tx_scope
        self._dedupe_window = timedelta(seconds=dedupe_window_seconds)

    def start_payment(self, phone: str, package_id: int, mac: str) -> Transaction:
        """Create a pending transaction and ask the gateway to prompt the phone.

        Returns the transaction (status ``pending``, ``gateway_ref`` set).
        Raises ValidationError for bad input and GatewayError when the
        gateway fails; in that case the transaction is left ``failed``.
        """
        phone = normalize_phone(phone)
        mac = normalize_mac(mac)
        package = self._package_repo.get(package_id)
        if package is None or not package.is_active:
            # Same message for unknown and inactive: do not reveal which.
            raise _invalid("package_id", "Package is not available.")
        if package.price_kes <= 0:
            raise _invalid("package_id", "Package cannot be paid for.")

        now = self._clock()
        with self._tx_scope():
            customer = self._customer_repo.upsert(phone, iso_utc(now))
            existing = self._tx_repo.find_recent_pending(
                customer.id, package.id, iso_utc(now - self._dedupe_window)
            )
            if existing is not None:
                logger.info("payment_repeat tx=%s", existing.id)
                return existing
            tx = self._tx_repo.insert_pending(
                customer.id, package.id, package.price_kes, mac, iso_utc(now)
            )

        try:
            receipt = self._gateway.initiate(phone, tx.amount_kes, str(tx.id))
            if str(getattr(receipt.status, "value", receipt.status)).lower() == (
                "failed"
            ):
                raise GatewayError("gateway rejected the payment request")
        except Exception as exc:
            self._fail(tx.id)
            logger.warning(
                "payment_gateway_error tx=%s phone=%s error=%s",
                tx.id,
                _mask(phone),
                type(exc).__name__,
            )
            raise

        with self._tx_scope():
            self._tx_repo.set_gateway_ref(tx.id, receipt.checkout_id)
        started = self._tx_repo.get(tx.id)
        if started is None:  # pragma: no cover - row was just written
            raise RuntimeError("transaction vanished after gateway call")
        logger.info("payment_started tx=%s phone=%s", tx.id, _mask(phone))
        return started

    def _fail(self, transaction_id: int) -> None:
        """Mark a pending transaction failed in its own database transaction."""
        with self._tx_scope():
            self._tx_repo.mark_failed(transaction_id)
