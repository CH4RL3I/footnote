import pytest

from filingqa.numfmt import contains_value, extract_numbers, filing_forms, numeric_match

APPLE_REVENUE = 391035000000


def test_millions_wording_matches_xbrl_raw_value():
    assert numeric_match("Net sales were $391,035 million.", APPLE_REVENUE)
    assert numeric_match("about $391.0 billion", APPLE_REVENUE)
    assert numeric_match("391,035", APPLE_REVENUE)  # bare figure: filings print in millions
    assert numeric_match("391035000000", APPLE_REVENUE)


def test_tolerance_and_mismatch():
    assert numeric_match("$391,100 million", APPLE_REVENUE, tol=0.005)
    assert not numeric_match("$391,100 million", APPLE_REVENUE, tol=0.0001)
    assert not numeric_match("$93,736 million", APPLE_REVENUE)
    assert not numeric_match("not found in the filings", APPLE_REVENUE)


def test_years_are_not_mistaken_for_values():
    assert extract_numbers("fiscal year 2024") == []
    assert numeric_match("In fiscal 2024 it was $2,024 million", 2024e6)


def test_units_parse():
    assert extract_numbers("$1.5 trillion") == [1.5e12]
    assert extract_numbers("$12 billion and $3,400 thousand") == [12e9, 3.4e6]


def test_negative_in_parentheses_matches_by_magnitude():
    assert numeric_match("net loss of $(45) million", -45e6)


def test_filing_forms():
    forms = filing_forms(APPLE_REVENUE)
    assert forms[0] == "391,035"
    assert "391.0 billion" in forms
    assert "500" not in filing_forms(500e6)  # too ambiguous to search for bare


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Net sales | $391,035 | $383,285", True),
        ("Net sales | $1,391,035", False),  # glued to another digit group
        ("Net sales | $391,0355", False),
        ("Revenue was $391.0 billion this year", True),
        ("Revenue was 391,035.5", False),
        ("unrelated 12,345", False),
    ],
)
def test_contains_value(text, expected):
    assert contains_value(text, APPLE_REVENUE) is expected
