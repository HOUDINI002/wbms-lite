"""Business rules for the package catalogue (Step 5).

The service sits between the web layer and the repository. It decides whether a
package is acceptable, and it turns database rule violations into messages a
person can act on. It never contains SQL and never commits: whoever calls it
wraps the work in ``wbms.db.transaction()``.

Rules (slide 64):

* ``name``             2 to 60 characters, surrounding spaces removed
* ``price_kes``        whole number, 0 to 100000
* ``duration_minutes`` whole number, 1 to 43200 (30 days)
* ``speed_kbps``       whole number, 64 to 100000
* ``data_limit_mb``    positive whole number, or ``None`` for unlimited data
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from wbms.repositories.packages import Package, PackageInput, PackageRepository

NAME_LENGTH = (2, 60)
PRICE_KES = (0, 100_000)
DURATION_MINUTES = (1, 43_200)
SPEED_KBPS = (64, 100_000)

REQUIRED = "This field is required."


class ValidationError(Exception):
    """The input broke one or more rules.

    ``errors`` maps a field name to a message, so a form (or a test) can show
    every problem at once instead of one per round trip. A body that is not a
    JSON object at all is reported under the field name ``"body"``.
    """

    def __init__(self, errors: Mapping[str, str]) -> None:
        self.errors: dict[str, str] = dict(errors)
        super().__init__(
            "; ".join(f"{field}: {message}" for field, message in self.errors.items())
        )


class UnknownPackageError(LookupError):
    """No package has the requested id."""

    def __init__(self, package_id: int) -> None:
        self.package_id = package_id
        super().__init__(f"Package {package_id} not found.")


def _is_whole_number(value: object) -> bool:
    # bool is a subclass of int in Python, so True would otherwise pass as 1.
    return isinstance(value, int) and not isinstance(value, bool)


def _whole_number(
    data: Mapping[str, Any],
    field: str,
    bounds: tuple[int, int],
    errors: dict[str, str],
) -> int:
    """Return ``data[field]`` if it is a whole number inside ``bounds``.

    On failure the message goes into ``errors`` and 0 is returned. That 0 is
    meaningless: the caller must check ``errors`` before using any value.
    """
    low, high = bounds
    value = data.get(field)
    if value is None:
        errors[field] = REQUIRED
    elif not _is_whole_number(value) or not low <= value <= high:
        errors[field] = f"Must be a whole number from {low} to {high}."
    else:
        return value
    return 0


def _name(data: Mapping[str, Any], errors: dict[str, str]) -> str:
    """Return the trimmed name, or ``""`` after recording an error."""
    low, high = NAME_LENGTH
    value = data.get("name")
    if value is None:
        errors["name"] = REQUIRED
    elif not isinstance(value, str):
        errors["name"] = "Must be text."
    elif not low <= len(value.strip()) <= high:
        errors["name"] = f"Must be {low} to {high} characters."
    else:
        return value.strip()
    return ""


def _data_limit(data: Mapping[str, Any], errors: dict[str, str]) -> int | None:
    """Missing or ``None`` means unlimited; anything else must be 1 or more."""
    value = data.get("data_limit_mb")
    if value is None:
        return None
    if not _is_whole_number(value) or value < 1:
        errors["data_limit_mb"] = (
            "Must be a positive whole number, or null for unlimited data."
        )
        return None
    return value


def validate_package_input(data: object) -> PackageInput:
    """Check ``data`` against every rule and return a ``PackageInput``.

    Raises ``ValidationError`` listing *all* problems found, not just the first.
    Keys that are not part of the rules (for example ``is_active``) are ignored,
    so a caller can never retire or revive a package through this path.
    """
    if not isinstance(data, Mapping):
        raise ValidationError({"body": "Request body must be a JSON object."})

    errors: dict[str, str] = {}
    name = _name(data, errors)
    price_kes = _whole_number(data, "price_kes", PRICE_KES, errors)
    duration_minutes = _whole_number(data, "duration_minutes", DURATION_MINUTES, errors)
    speed_kbps = _whole_number(data, "speed_kbps", SPEED_KBPS, errors)
    data_limit_mb = _data_limit(data, errors)

    if errors:
        raise ValidationError(errors)

    return PackageInput(
        name=name,
        price_kes=price_kes,
        duration_minutes=duration_minutes,
        speed_kbps=speed_kbps,
        data_limit_mb=data_limit_mb,
    )


def _friendly(error: sqlite3.IntegrityError) -> ValidationError | None:
    """Translate a known database rule violation, or return None if unknown."""
    if "UNIQUE constraint failed: packages.name" in str(error):
        return ValidationError({"name": "A package with this name already exists."})
    return None


class PackageService:
    """What the portal and the admin screens may do with packages."""

    def __init__(self, repo: PackageRepository) -> None:
        self._repo = repo

    def list_for_portal(self) -> list[Package]:
        """Active packages only, in the order the repository returns them."""
        return self._repo.list_active()

    def create(self, data: object) -> Package:
        """Validate ``data`` and store a new package.

        Raises ``ValidationError`` for broken rules, including a name that is
        already taken. Unknown database errors are not hidden.
        """
        package_input = validate_package_input(data)
        try:
            return self._repo.create(package_input)
        except sqlite3.IntegrityError as error:
            friendly = _friendly(error)
            if friendly is None:
                raise  # an unknown rule broke: do not hide it
            raise friendly from error

    def update(self, package_id: int, data: object) -> Package:
        """Replace every editable field of an existing package.

        Input is validated first, so bad data on an unknown id reports the
        validation problems, not the missing package. Raises
        ``UnknownPackageError`` for an unknown id. ``is_active`` is never
        changed here; retiring a package is a separate action.
        """
        package_input = validate_package_input(data)
        try:
            updated = self._repo.update(package_id, package_input)
        except sqlite3.IntegrityError as error:
            friendly = _friendly(error)
            if friendly is None:
                raise
            raise friendly from error
        if updated is None:
            raise UnknownPackageError(package_id)
        return updated
