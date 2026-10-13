"""Payment gateway contract.

Everything the rest of WBMS-Lite needs from a payment provider is described
here, independent of the provider. The mock (``mock.py``) and the future
Daraja adapter both satisfy :class:`PaymentGateway`, so services never import
a concrete gateway.

Lifecycle (mirrors M-Pesa STK push):

1. ``initiate`` asks the provider to prompt the customer. The provider
   accepts the request and the payment is ``PENDING``.
2. The final outcome arrives later, either as a callback or by calling
   ``query``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable


class GatewayStatus(StrEnum):
    """Outcome of a payment as the gateway reports it."""

    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class GatewayError(Exception):
    """The gateway could not be reached or rejected the request.

    Raised for network problems, timeouts, provider errors and invalid
    arguments. The payment service maps it to a failed transaction and the
    API maps it to HTTP 502.
    """


class GatewayConfigError(Exception):
    """The configured gateway cannot be built (bad name or missing adapter)."""


@dataclass(frozen=True, slots=True)
class GatewayReceipt:
    """Returned by :meth:`PaymentGateway.initiate`.

    Attributes:
        checkout_id: Provider reference; store it as ``gateway_ref``.
        status: Status when the request was accepted (normally PENDING).
    """

    checkout_id: str
    status: GatewayStatus


@dataclass(frozen=True, slots=True)
class GatewayResult:
    """Returned by :meth:`PaymentGateway.query`.

    Attributes:
        status: Current status of the payment.
        receipt_number: Provider receipt (for example the M-Pesa receipt)
            when the payment succeeded, otherwise ``None``.
    """

    status: GatewayStatus
    receipt_number: str | None = None


@runtime_checkable
class PaymentGateway(Protocol):
    """What WBMS-Lite requires from any payment provider."""

    def initiate(self, phone: str, amount_kes: int, reference: str) -> GatewayReceipt:
        """Ask the provider to collect ``amount_kes`` from ``phone``.

        Args:
            phone: Normalized Kenyan number, ``2547XXXXXXXX`` or ``2541XXXXXXXX``.
            amount_kes: Whole Kenyan shillings, greater than zero.
            reference: Our reference, normally the transaction id.

        Raises:
            GatewayError: The request could not be made or was rejected.
        """
        ...

    def query(self, checkout_id: str) -> GatewayResult:
        """Return the current status of a previously initiated payment.

        Raises:
            GatewayError: The provider could not be reached or the id is unknown.
        """
        ...
