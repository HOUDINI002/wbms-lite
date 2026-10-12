"""Captive portal page: the customer-facing screen served at ``GET /portal``.

A MikroTik hotspot (or any captive-portal router) intercepts the first web
request of an unauthenticated phone and redirects it to this page, passing the
device MAC address as a query parameter, for example::

    http://<server>/portal?mac=AA:BB:CC:DD:EE:FF

Until Step 13 (the real router adapter) the redirect is simulated by typing
that address in a browser. The page itself only displays packages and collects
a phone number; the server validates everything again when the payment is
posted (Step 8), so nothing here is trusted.
"""

from __future__ import annotations

import re

from flask import Blueprint, Response, render_template, request

bp = Blueprint(
    "portal",
    __name__,
    template_folder="templates",
    static_folder="static",
    # Not the default "/static", which belongs to the Flask app itself.
    static_url_path="/portal-static",
)

_MAC_PATTERN = re.compile(r"[0-9A-Fa-f]{2}([:-])(?:[0-9A-Fa-f]{2}\1){4}[0-9A-Fa-f]{2}")

# The page has no inline scripts or styles, so a strict policy costs nothing.
_CONTENT_SECURITY_POLICY = (
    "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)


def normalize_mac(raw: str | None) -> str:
    """Return ``raw`` as ``AA:BB:CC:DD:EE:FF``, or ``""`` if it is not a MAC.

    Accepts colon or dash separators in any letter case. Anything else (empty,
    too short, markup, mixed separators) gives an empty string, so a hostile
    query string can never reach the page.
    """
    value = (raw or "").strip()
    if _MAC_PATTERN.fullmatch(value) is None:
        return ""
    return value.replace("-", ":").upper()


@bp.get("/portal")
def show_portal() -> Response:
    """Render the portal with the (validated) device MAC in a hidden field."""
    mac = normalize_mac(request.args.get("mac"))
    response = Response(render_template("portal.html", mac=mac))
    # The URL carries a device identifier: keep the page out of caches and do
    # not leak the address to other sites through the Referer header.
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = _CONTENT_SECURITY_POLICY
    return response
