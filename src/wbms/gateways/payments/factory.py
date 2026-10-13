"""Choose the payment gateway from settings."""

from __future__ import annotations

from typing import Any

from wbms.gateways.payments.base import GatewayConfigError, PaymentGateway
from wbms.gateways.payments.mock import MockPaymentGateway


def get_gateway(settings: Any) -> PaymentGateway:
    """Build the gateway named by ``settings.PAYMENT_GATEWAY``.

    Args:
        settings: Any object with a ``PAYMENT_GATEWAY`` attribute
            (``"mock"`` or ``"daraja"``); normally ``wbms.config.Settings``.
            The Daraja adapter receives the whole object and reads the
            ``DARAJA_*`` fields itself.

    Raises:
        GatewayConfigError: Unknown gateway name, or ``daraja`` was selected
            before the Daraja adapter exists.
    """
    name = str(getattr(settings, "PAYMENT_GATEWAY", "mock")).strip().lower()

    if name == "mock":
        return MockPaymentGateway()

    if name == "daraja":
        try:
            from wbms.gateways.payments.daraja import DarajaGateway
        except ModuleNotFoundError as exc:
            if exc.name != "wbms.gateways.payments.daraja":
                raise
            raise GatewayConfigError(
                "PAYMENT_GATEWAY=daraja but the Daraja adapter is not built yet. "
                "Set PAYMENT_GATEWAY=mock in .env."
            ) from exc
        return DarajaGateway(settings)

    raise GatewayConfigError(f"Unknown PAYMENT_GATEWAY {name!r}; expected 'mock' or 'daraja'.")
