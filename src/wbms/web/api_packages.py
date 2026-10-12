"""JSON routes for packages (Step 5).

The web layer only translates HTTP to service calls and back:

    GET  /api/packages        public, active packages only      -> 200
    POST /api/packages        admin, create a package           -> 201
    PUT  /api/packages/<id>   admin, replace a package          -> 200

Every error body has the same shape, so the portal and the tests can rely on it:

    {"error": {"code": "validation_error", "message": "...", "fields": {...}}}

400 means the input broke a rule, 404 means there is no such package or route.
``fields`` is present only for validation errors.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from functools import wraps
from typing import Any

from flask import Blueprint, Response, jsonify, request
from werkzeug.exceptions import HTTPException

from wbms.db import get_db, transaction
from wbms.repositories.packages import Package, PackageRepository
from wbms.services.packages import PackageService, UnknownPackageError, ValidationError

bp = Blueprint("api_packages", __name__)

BODY_HINT = (
    "Request body must be a JSON object "
    "(send the header Content-Type: application/json)."
)


def require_admin(view: Callable[..., Any]) -> Callable[..., Any]:
    """STUB. Today it lets everyone through; M5 makes it check the admin login.

    Until then the POST and PUT routes are OPEN. Run the app only on your own
    computer (127.0.0.1) and never expose it to a network.
    """

    @wraps(view)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        # TODO(M5): answer 401 unless a logged-in admin is on the session.
        return view(*args, **kwargs)

    return wrapper


def _service() -> PackageService:
    return PackageService(PackageRepository(get_db()))


def _serialize(package: Package) -> dict[str, Any]:
    return dataclasses.asdict(package)


def _error(
    code: str,
    message: str,
    status: int,
    fields: dict[str, str] | None = None,
) -> tuple[Response, int]:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if fields:
        body["error"]["fields"] = fields
    return jsonify(body), status


def _json_body() -> Any:
    """The parsed JSON body, or None when it is missing or not valid JSON."""
    return request.get_json(silent=True)


@bp.get("/api/packages")
def list_packages() -> tuple[Response, int]:
    """Public: the packages a customer may buy right now."""
    packages = _service().list_for_portal()
    return jsonify({"packages": [_serialize(p) for p in packages]}), 200


@bp.post("/api/packages")
@require_admin
def create_package() -> tuple[Response, int]:
    """Admin: create a package from a JSON object."""
    service = _service()
    with transaction():
        package = service.create(_json_body())
    return jsonify({"package": _serialize(package)}), 201


@bp.put("/api/packages/<int:package_id>")
@require_admin
def update_package(package_id: int) -> tuple[Response, int]:
    """Admin: replace all editable fields of one package."""
    service = _service()
    with transaction():
        package = service.update(package_id, _json_body())
    return jsonify({"package": _serialize(package)}), 200


@bp.errorhandler(ValidationError)
def _validation_failed(error: ValidationError) -> tuple[Response, int]:
    fields = dict(error.errors)
    if "body" in fields:
        fields["body"] = BODY_HINT
    return _error("validation_error", "Some fields are not valid.", 400, fields)


@bp.errorhandler(UnknownPackageError)
def _package_missing(error: UnknownPackageError) -> tuple[Response, int]:
    return _error("not_found", str(error), 404)


# The two handlers below are app-wide, so unknown URLs and wrong methods under
# /api/ also answer in JSON. Anything else keeps Flask's normal pages. When a
# second API blueprint arrives, move these to a shared web/errors.py.
@bp.app_errorhandler(404)
def _unknown_route(
    error: HTTPException,
) -> Response | tuple[Response, int] | HTTPException:
    if request.path.startswith("/api/"):
        return _error("not_found", "No such endpoint.", 404)
    return error


@bp.app_errorhandler(405)
def _wrong_method(
    error: HTTPException,
) -> Response | tuple[Response, int] | HTTPException:
    if request.path.startswith("/api/"):
        return _error("method_not_allowed", "That method is not allowed here.", 405)
    return error
