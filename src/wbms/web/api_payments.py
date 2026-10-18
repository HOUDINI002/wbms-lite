"""POST /api/payments: start a payment (Step 8).

Responses
    202 {"transaction_id": 12, "status": "pending"}
    400 validation errors (bad JSON, missing or invalid fields)
    429 more than 5 requests per minute from one IP (Retry-After header)
    502 the payment provider failed; the transaction is recorded as failed
"""

from __future__ import annotations

import hmac
import logging
from collections.abc import Callable
from typing import Any

from flask import Blueprint, Response, current_app, jsonify, request

from wbms.gateways.payments.base import GatewayError
from wbms.repositories.customers import CustomerRepository
from wbms.repositories.packages import PackageRepository
from wbms.repositories.transactions import TransactionRepository
from wbms.services.packages import ValidationError
from wbms.services.payments import PaymentService
from wbms.web.rate_limit import RateLimiter, utc_now

logger = logging.getLogger(__name__)

bp = Blueprint("api_payments", __name__)

# Keys under app.extensions. Tests replace them with fakes.
SERVICE_FACTORY_KEY = "wbms_payment_service_factory"
LIMITER_KEY = "wbms_payments_limiter"
GATEWAY_KEY = "wbms_payment_gateway"
SESSION_STARTER_KEY = "wbms_session_starter"  # Step 11 stores SessionService here
CALLBACK_SECRET_KEY = "wbms_callback_secret"  # tests override; else Settings

RATE_LIMIT = 5
RATE_WINDOW_SECONDS = 60


def _error(
    code: str, message: str, status: int, fields: dict[str, str] | None = None
) -> tuple[Response, int]:
    body: dict[str, Any] = {"error": code, "message": message}
    if fields:
        body["fields"] = fields
    return jsonify(body), status


def _find_settings() -> Any:
    """Find the Settings object that create_app stored on app.extensions."""
    for value in current_app.extensions.values():
        if hasattr(value, "PAYMENT_GATEWAY"):
            return value
    raise RuntimeError("Settings not found in app.extensions")


def _default_service() -> PaymentService:
    """Build the service for this request from the real wiring."""
    from wbms.db import get_db
    from wbms.gateways.payments.factory import get_gateway

    # One gateway per app, so the mock keeps its recorded calls between requests.
    gateway = current_app.extensions.get(GATEWAY_KEY)
    if gateway is None:
        gateway = get_gateway(_find_settings())
        current_app.extensions[GATEWAY_KEY] = gateway
    conn = get_db()
    return PaymentService(
        TransactionRepository(conn),
        CustomerRepository(conn),
        PackageRepository(conn),
        gateway,
        utc_now,
        session_starter=current_app.extensions.get(SESSION_STARTER_KEY),
    )


def _get_service() -> PaymentService:
    factory: Callable[[], PaymentService] = current_app.extensions.get(
        SERVICE_FACTORY_KEY, _default_service
    )
    return factory()


def _get_limiter() -> RateLimiter:
    limiter = current_app.extensions.get(LIMITER_KEY)
    if limiter is None:
        limiter = RateLimiter(RATE_LIMIT, RATE_WINDOW_SECONDS)
        current_app.extensions[LIMITER_KEY] = limiter
    return limiter


def _package_id(value: object) -> int | None:
    """Accept 3 or "3" (form-style JSON); reject bool, float, text."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _validation_fields(exc: ValidationError) -> dict[str, str]:
    """Read field messages from the project's ValidationError."""
    fields = getattr(exc, "errors", None) or getattr(exc, "fields", None)
    return dict(fields) if isinstance(fields, dict) else {"_": str(exc)}


@bp.post("/api/payments")
def start_payment() -> tuple[Response, int]:
    """Validate the JSON body and start a payment."""
    # request.remote_addr is the direct peer. Behind a reverse proxy, wrap the
    # app in werkzeug's ProxyFix so this is the real client IP; never trust
    # a raw X-Forwarded-For header.
    decision = _get_limiter().hit(request.remote_addr or "unknown")
    if not decision.allowed:
        response, status = _error(
            "rate_limited", "Too many requests. Try again shortly.", 429
        )
        response.headers["Retry-After"] = str(decision.retry_after_s)
        return response, status

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error("invalid_json", "Send a JSON object.", 400)

    phone = data.get("phone")
    mac = data.get("mac")
    package_id = _package_id(data.get("package_id"))
    problems: dict[str, str] = {}
    if not isinstance(phone, str) or not phone.strip():
        problems["phone"] = "Phone number is required."
    if not isinstance(mac, str) or not mac.strip():
        problems["mac"] = "Device address (MAC) is required."
    if package_id is None:
        problems["package_id"] = "Choose a package."
    if problems:
        return _error(
            "validation_error", "Check the highlighted fields.", 400, problems
        )

    try:
        tx = _get_service().start_payment(str(phone), int(package_id or 0), str(mac))
    except ValidationError as exc:
        return _error(
            "validation_error",
            "Check the highlighted fields.",
            400,
            _validation_fields(exc),
        )
    except GatewayError:
        return _error(
            "gateway_error", "Payment provider unavailable. Please try again.", 502
        )
    return jsonify({"transaction_id": tx.id, "status": tx.status}), 202


def _callback_secret() -> str:
    override = current_app.extensions.get(CALLBACK_SECRET_KEY)
    return str(override if override is not None else _find_settings().CALLBACK_SECRET)


@bp.post("/api/payments/callback/<secret>")
def payment_callback(secret: str) -> tuple[Response, int]:
    """Receive the gateway's result for a payment.

    A wrong secret gets 403 and changes nothing. With the right secret the
    gateway always gets 200 {"ResultCode": 0, "ResultDesc": "Accepted"}, even
    for unknown, duplicate or malformed callbacks, so it never retries them
    forever. What actually happened is in the log and in the transaction.
    """
    expected = _callback_secret()
    # compare_digest takes the same time wherever the strings differ; an empty
    # configured secret is refused outright so a missing setting is not a hole.
    if not expected or not hmac.compare_digest(
        secret.encode("utf-8"), expected.encode("utf-8")
    ):
        logger.warning("callback_rejected reason=bad_secret ip=%s", request.remote_addr)
        return _error("forbidden", "Forbidden.", 403)

    try:
        outcome = _get_service().apply_callback(request.get_json(silent=True))
        logger.info("callback_outcome outcome=%s", outcome.value)
    except Exception:
        # The database change was rolled back; the transaction stays pending
        # and Step 10's reconcile job will ask the gateway about it.
        logger.exception("callback_error")
    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"}), 200
