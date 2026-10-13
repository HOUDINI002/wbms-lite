"""Deterministic fake payment gateway for development and tests.

Behavior is decided by the **last digit of the phone number**:

* ends in ``0``  -> the payment fails
* ends in ``9``  -> the payment stays pending
* anything else  -> the payment succeeds

``initiate`` always reports ``PENDING`` (the request was accepted, as with a
real STK push). The outcome above is what ``query`` returns afterwards.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

from wbms.gateways.payments.base import (
    GatewayError,
    GatewayReceipt,
    GatewayResult,
    GatewayStatus,
)

FAIL_DIGIT = "0"
PENDING_DIGIT = "9"


@dataclass(frozen=True, slots=True)
class MockCall:
    """One recorded call, so tests can assert on what the gateway received."""

    method: str
    args: dict[str, Any]


class MockPaymentGateway:
    """In-memory :class:`~wbms.gateways.payments.base.PaymentGateway`.

    Attributes:
        calls: Every ``initiate`` and ``query`` call, in order.
        fail_with: When set, ``initiate`` and ``query`` raise this error.
            Use it to test gateway outages.
    """

    def __init__(self) -> None:
        self.calls: list[MockCall] = []
        self.fail_with: GatewayError | None = None
        self._payments: dict[str, GatewayResult] = {}
        self._counter = 0
        self._lock = threading.Lock()

    # -- PaymentGateway interface -------------------------------------------------

    def initiate(self, phone: str, amount_kes: int, reference: str) -> GatewayReceipt:
        """Record the request and decide its eventual outcome from ``phone``."""
        with self._lock:
            self.calls.append(
                MockCall(
                    "initiate",
                    {"phone": phone, "amount_kes": amount_kes, "reference": reference},
                )
            )
            self._raise_if_failing()
            self._validate(phone, amount_kes, reference)
            self._counter += 1
            checkout_id = f"mock-checkout-{self._counter:06d}"
            self._payments[checkout_id] = self._outcome_for(phone, self._counter)
            return GatewayReceipt(checkout_id=checkout_id, status=GatewayStatus.PENDING)

    def query(self, checkout_id: str) -> GatewayResult:
        """Return the stored outcome for ``checkout_id``."""
        with self._lock:
            self.calls.append(MockCall("query", {"checkout_id": checkout_id}))
            self._raise_if_failing()
            try:
                return self._payments[checkout_id]
            except KeyError:
                raise GatewayError(f"unknown checkout_id: {checkout_id}") from None

    # -- test helpers -------------------------------------------------------------

    def settle(
        self,
        checkout_id: str,
        status: GatewayStatus,
        receipt_number: str | None = None,
    ) -> None:
        """Force the outcome of a payment (for example resolve a pending one).

        A successful payment without an explicit receipt gets a mock receipt.
        """
        with self._lock:
            if checkout_id not in self._payments:
                raise GatewayError(f"unknown checkout_id: {checkout_id}")
            if status is GatewayStatus.SUCCESS and receipt_number is None:
                receipt_number = f"MOCKRCPT{checkout_id[-6:]}"
            if status is not GatewayStatus.SUCCESS:
                receipt_number = None
            self._payments[checkout_id] = GatewayResult(status, receipt_number)

    def calls_to(self, method: str) -> list[MockCall]:
        """Return only the calls made to ``method`` (``"initiate"`` or ``"query"``)."""
        return [c for c in self.calls if c.method == method]

    # -- internals ----------------------------------------------------------------

    def _raise_if_failing(self) -> None:
        if self.fail_with is not None:
            raise self.fail_with

    @staticmethod
    def _validate(phone: str, amount_kes: int, reference: str) -> None:
        if not isinstance(phone, str) or not phone.isdigit():
            raise GatewayError("phone must be a string of digits")
        if isinstance(amount_kes, bool) or not isinstance(amount_kes, int) or amount_kes <= 0:
            raise GatewayError("amount_kes must be a positive integer")
        if not isinstance(reference, str) or not reference.strip():
            raise GatewayError("reference must not be empty")

    @staticmethod
    def _outcome_for(phone: str, serial: int) -> GatewayResult:
        last = phone[-1]
        if last == FAIL_DIGIT:
            return GatewayResult(GatewayStatus.FAILED, None)
        if last == PENDING_DIGIT:
            return GatewayResult(GatewayStatus.PENDING, None)
        return GatewayResult(GatewayStatus.SUCCESS, f"MOCKRCPT{serial:06d}")
