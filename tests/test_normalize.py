import pytest

from fritz_callhistory.sync.normalize import ANONYMOUS_NUMBER, normalize_number


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_missing_number_is_anonymous(raw):
    number, is_anonymous = normalize_number(raw)
    assert number == ANONYMOUS_NUMBER
    assert is_anonymous is True


def test_national_and_international_formats_normalize_to_same_number():
    national, _ = normalize_number("030 1234567")
    international, _ = normalize_number("+49 30 1234567")
    assert national == international
    assert national.startswith("+49")


def test_mobile_number_normalizes():
    number, is_anonymous = normalize_number("0171 2345678")
    assert number == "+491712345678"
    assert is_anonymous is False


def test_short_number_is_parsed_within_region():
    # phonenumbers behandelt kurze nationale Nummern als "möglich" innerhalb der Region.
    number, is_anonymous = normalize_number("112")
    assert number == "+49112"
    assert is_anonymous is False


def test_unparseable_number_falls_back_to_digits_only():
    number, is_anonymous = normalize_number("*123#")
    assert number == "123"
    assert is_anonymous is False


def test_garbage_input_without_digits_is_anonymous():
    number, is_anonymous = normalize_number("---")
    assert number == ANONYMOUS_NUMBER
    assert is_anonymous is True
