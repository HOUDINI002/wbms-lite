"""Payment service: start a mobile-money payment (Step 8).

Flow of ``apply_callback`` (Step 9) is described on that method.

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
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Protocol

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


class CallbackOutcome(str, Enum):
    """What ``apply_callback`` did with a gateway callback."""

    SUCCESS = "success"  # payment confirmed, transaction now success
    FAILED = "failed"  # gateway reported failure, transaction now failed
    DUPLICATE = "duplicate"  # transaction already final, nothing changed
    IGNORED = "ignored"  # unknown checkout id, nothing changed
    AMOUNT_MISMATCH = "amount_mismatch"  # paid amount differs, nothing changed
    INVALID = "invalid"  # payload missing required fields, nothing changed


class SessionStarter(Protocol):
    """What the payment service needs from SessionService (built in Step 11)."""

    def start_session(self, transaction: Transaction, mac: str) -> object:
        """Grant access for a paid transaction."""


class NoopSessionStarter:
    """Placeholder until Step 11: records the payment but grants no access."""

    def start_session(self, transaction: Transaction, mac: str) -> None:
        logger.info("session_start_skipped tx=%s (no SessionService)", transaction.id)


@dataclass(frozen=True)
class _ParsedCallback:
    checkout_id: str
    result_code: int
    result_desc: str
    receipt: str | None
    amount: Decimal | None


def _parse_callback(payload: object) -> _ParsedCallback | None:
    """Read a Daraja-style STK callback; None if required fields are missing."""
    if not isinstance(payload, dict):
        return None
    body = payload.get("Body")
    callback = body.get("stkCallback") if isinstance(body, dict) else None
    if not isinstance(callback, dict):
        return None
    checkout_id = callback.get("CheckoutRequestID")
    code = callback.get("ResultCode")
    if isinstance(code, str) and code.strip().lstrip("-").isdigit():
        code = int(code)
    if (
        not isinstance(checkout_id, str)
        or not checkout_id
        or isinstance(code, bool)
        or not isinstance(code, int)
    ):
        return None
    receipt: str | None = None
    amount: Decimal | None = None
    metadata = callback.get("CallbackMetadata")
    items = metadata.get("Item") if isinstance(metadata, dict) else None
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        if item.get("Name") == "MpesaReceiptNumber" and isinstance(
            item.get("Value"), str
        ):
            receipt = item["Value"].strip() or None
        elif item.get("Name") == "Amount":
            try:
                amount = Decimal(str(item.get("Value")))
            except InvalidOperation:
                amount = None
    desc = str(callback.get("ResultDesc", ""))[:200]
    return _ParsedCallback(checkout_id, code, desc, receipt, amount)


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
        session_starter: SessionStarter | None = None,
    ) -> None:
        self._tx_repo = tx_repo
        self._customer_repo = customer_repo
        self._package_repo = package_repo
        self._gateway = gateway
        self._clock = clock
        self._tx_scope = tx_scope or _default_tx_scope
        self._dedupe_window = timedelta(seconds=dedupe_window_seconds)
        self._session_starter: SessionStarter = session_starter or NoopSessionStarter()

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

    def apply_callback(self, payload: dict[str, Any]) -> CallbackOutcome:
        """Apply a Daraja-style STK callback to its transaction, exactly once.

        Everything happens in ONE database transaction, so the status change
        and the session start commit together or not at all:

        1. Parse the payload; missing fields give INVALID (nothing changes).
        2. Find the transaction by ``gateway_ref``; unknown gives IGNORED.
        3. Not pending any more gives DUPLICATE (nothing changes).
        4. ResultCode != 0: mark failed (reason is logged) and return FAILED.
        5. ResultCode 0: the receipt must be present and the amount must equal
           the transaction amount, else AMOUNT_MISMATCH / INVALID and the
           transaction stays pending for review. Otherwise mark success with
           receipt and paid_at, then start the session.

        The UPDATE only matches rows still ``pending``, so two callbacks racing
        for the same payment cannot both win: the loser gets DUPLICATE.
        Exceptions (for example a failing session start) roll everything back
        and propagate; the transaction stays pending for reconciliation.
        """
        parsed = _parse_callback(payload)
        if parsed is None:
            logger.warning("callback_invalid reason=malformed_payload")
            return CallbackOutcome.INVALID
        now = self._clock()
        with self._tx_scope():
            tx = self._tx_repo.get_by_gateway_ref(parsed.checkout_id)
            if tx is None:
                logger.info("callback_ignored reason=unknown_reference")
                return CallbackOutcome.IGNORED
            if tx.status != "pending":
                logger.info("callback_duplicate tx=%s status=%s", tx.id, tx.status)
                return CallbackOutcome.DUPLICATE
            if parsed.result_code != 0:
                if not self._tx_repo.mark_failed(tx.id):
                    return CallbackOutcome.DUPLICATE
                logger.info(
                    "callback_failed tx=%s code=%s reason=%s",
                    tx.id,
                    parsed.result_code,
                    parsed.result_desc,
                )
                return CallbackOutcome.FAILED
            if parsed.receipt is None or parsed.amount is None:
                logger.warning("callback_invalid tx=%s reason=missing_metadata", tx.id)
                return CallbackOutcome.INVALID
            if parsed.amount != Decimal(tx.amount_kes):
                logger.warning(
                    "callback_amount_mismatch tx=%s expected=%s received=%s",
                    tx.id,
                    tx.amount_kes,
                    parsed.amount,
                )
                return CallbackOutcome.AMOUNT_MISMATCH
            if not self._tx_repo.mark_success(tx.id, parsed.receipt, iso_utc(now)):
                return CallbackOutcome.DUPLICATE
            paid = self._tx_repo.get(tx.id)
            if paid is None:  # pragma: no cover - row was just updated
                raise RuntimeError("transaction vanished during callback")
            self._session_starter.start_session(paid, paid.mac_address or "")
            logger.info("callback_success tx=%s", tx.id)
            return CallbackOutcome.SUCCESS
