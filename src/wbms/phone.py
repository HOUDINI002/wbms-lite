"""Phone number normalisation for the WiFi billing system."""

import re

# Characters people commonly type between digit groups: 0712 345 678, 0712-345-678, (0712) 345.678
_SEPARATORS = re.compile(r"[\s\-().]")

# Accepted prefixes: +254, 254, 00254 or a leading 0, followed by a 9-digit
# subscriber number starting with 7 or 1 (07xx and 01xx mobile ranges).
# [0-9] is used instead of \d so non-ASCII digits (e.g. Arabic-Indic) are rejected.
_KENYAN_MOBILE = re.compile(r"(?:\+?254|00254|0)([17][0-9]{8})")


def normalize_phone(raw: str) -> str:
    """Normalise a Kenyan mobile number to the ``254XXXXXXXXX`` format.

    Accepted inputs (spaces, dashes, dots and parentheses are ignored):

    * ``0712345678``      (local format)
    * ``+254712345678``   (international with plus)
    * ``254712345678``    (international without plus)
    * ``00254712345678``  (international with 00 dial prefix)

    Args:
        raw: The phone number as typed or imported.

    Returns:
        The number as 12 digits starting with ``254``, e.g. ``"254712345678"``.

    Raises:
        ValueError: If ``raw`` is not a string, is empty or blank, or is not a
            valid Kenyan mobile number.

    Examples:
        >>> normalize_phone("0712 345 678")
        '254712345678'
        >>> normalize_phone("+254712345678")
        '254712345678'
    """
    if not isinstance(raw, str):
        raise ValueError(f"Phone number must be a string, got {type(raw).__name__}")

    cleaned = _SEPARATORS.sub("", raw.strip())
    if not cleaned:
        raise ValueError("Phone number is empty")

    match = _KENYAN_MOBILE.fullmatch(cleaned)
    if match is None:
        raise ValueError(f"Invalid Kenyan phone number: {raw!r}")

    return f"254{match.group(1)}"
