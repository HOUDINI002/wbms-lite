import pytest

from wbms.phone import normalize_phone

# --- Valid inputs -----------------------------------------------------------

def test_local_format_with_leading_zero():
    assert normalize_phone("0712345678") == "254712345678"


def test_international_format_with_plus():
    assert normalize_phone("+254712345678") == "254712345678"


def test_international_format_without_plus():
    assert normalize_phone("254712345678") == "254712345678"


def test_separators_and_surrounding_whitespace_are_ignored():
    assert normalize_phone("  +254 712-345-678 ") == "254712345678"
    assert normalize_phone("(0712) 345.678") == "254712345678"


def test_01_range_numbers_are_accepted():
    assert normalize_phone("0112345678") == "254112345678"


# --- Invalid inputs ---------------------------------------------------------

@pytest.mark.parametrize(
    "raw",
    [
        "071234567",        # too short (8 digits after 0)
        "07123456789",      # too long (10 digits after 0)
        "+2547123456",      # too short in international form
        "+255712345678",    # Tanzania, wrong country code
        "0212345678",       # landline-style prefix, not a mobile range
        "07123abc78",       # letters
        "+25471234567+8",   # stray plus sign mid-number
        "٠٧١٢٣٤٥٦٧٨",       # non-ASCII digits
    ],
)
def test_invalid_numbers_raise_value_error(raw):
    with pytest.raises(ValueError, match="Invalid Kenyan phone number"):
        normalize_phone(raw)


# --- Empty inputs -----------------------------------------------------------

@pytest.mark.parametrize("raw", ["", "   ", "\t\n", "+", "- -"])
def test_empty_or_blank_input_raises_value_error(raw):
    with pytest.raises(ValueError):
        normalize_phone(raw)


def test_non_string_input_raises_value_error():
    with pytest.raises(ValueError, match="must be a string"):
        normalize_phone(None)  # type: ignore[arg-type]
