"""Selected consolidated tables need explicit scope and closed monetary captions."""

import pytest

from filingqa.chunking import Chunk
from filingqa.grounding import extract_fact, numeric_intent


def source(text):
    return Chunk(
        "GLOBEX-FY2034#0000", "GLOBEX-FY2034", "GLOBEX", 2034,
        "Item 8", 0, "1", text, "GLOBEX FY2034",
    )


def fact_for(text, metric):
    chunk = source(text)
    intent = numeric_intent(f"What was GLOBEX {metric} for fiscal year 2034?", [chunk])
    assert intent is not None
    return extract_fact(intent, [chunk])[0]


SELECTED_METRICS = [
    ("total assets", "Total assets", "Selected Consolidated balance sheets data (continued)"),
    (
        "total stockholders' equity", "Total stockholders' equity",
        "Selected Consolidated balance sheets data (continued)",
    ),
    ("net income", "Net income", "Selected Consolidated statements of income data"),
    ("total revenue", "Revenue", "Selected Consolidated statements of income data"),
    ("operating income", "Operating income", "Selected Consolidated statements of income data"),
]


@pytest.mark.parametrize("metric,row,heading", SELECTED_METRICS)
def test_anchored_selected_consolidated_table_supports_company_total(metric, row, heading):
    text = f"{heading}\n(In millions)\n2034 | 2033\n{row} | $141 | $97"
    fact = fact_for(text, metric)
    assert fact is not None and fact.value == 141_000_000
    assert fact.citations == ["GLOBEX-FY2034#0000"]


@pytest.mark.parametrize("metric,row,heading", SELECTED_METRICS)
@pytest.mark.parametrize("qualification", [
    "refer", "prose", "segment", "parent_before", "parent_after",
])
def test_selected_phrase_does_not_override_missing_or_qualified_company_scope(
    metric, row, heading, qualification
):
    title = {
        "refer": "Refer to " + heading + " for additional details.",
        "prose": "The following discussion refers to " + heading + ".",
        "segment": heading + "\nEurope segment",
        "parent_before": "Parent Company Only\n" + heading,
        "parent_after": heading + "\nParent Company Only",
    }[qualification]
    text = f"{title}\n(In millions)\n2034 | 2033\n{row} | $141 | $97"
    assert fact_for(text, metric) is None


@pytest.mark.parametrize("caption", [
    "Cdn$ in millions",
    "(Cdn$ in millions)",
    "B$ in millions",
    "Bahamian dollars in millions",
    "(Bahamian dollars in millions)",
    "Barbadian dollars in millions",
    "Shares in billions; Cdn$ in millions",
    "(Shares in thousands, Bahamian dollars in millions)",
    "Dollars in millions; Cdn$ in billions",
    "U.S. dollars in millions, Bahamian dollars in millions",
    "U.S.$ in millions; Cdn$ in millions",
    "USD in millions (Bahamian dollars)",
    "Amounts stated in Cdn$ (in millions)",
    "Bahamian dollars (In millions)",
])
def test_unknown_dollar_currency_cannot_be_certified_as_usd_from_suffix(caption):
    text = (
        "CONSOLIDATED BALANCE SHEETS\n" + caption
        + "\n2034 | 2033\nTotal assets | $141 | $97"
    )
    assert fact_for(text, "total assets") is None


@pytest.mark.parametrize("caption", [
    "(In millions)", "Dollars in millions", "U.S. dollars in millions",
    "US dollars in millions", "USD in millions", "US$ in millions",
    "U.S.$ in millions", "$ in millions", "Shares in billions; U.S. dollars in millions",
])
def test_closed_usd_clause_keeps_supported_plain_and_us_captions(caption):
    text = (
        "CONSOLIDATED BALANCE SHEETS\n" + caption
        + "\n2034 | 2033\nTotal assets | $141 | $97"
    )
    fact = fact_for(text, "total assets")
    assert fact is not None and fact.value == 141_000_000


@pytest.mark.parametrize("declaration,expected", [
    ("Cdn$", None), ("Bahamian dollars", None), ("(Bahamian dollars)", None),
    ("U.S. dollars", 141_000_000), ("US$", 141_000_000), ("U.S.$", 141_000_000),
    ("Dollars", 141_000_000), ("$", 141_000_000),
])
@pytest.mark.parametrize("header_gap", [0, 10])
def test_standalone_currency_declaration_governs_following_plain_scale(
    declaration, expected, header_gap
):
    lines = ["CONSOLIDATED BALANCE SHEETS", declaration, "(In millions)"]
    lines += ["Supplemental accounting note"] * header_gap
    lines += ["2034 | 2033", "Total assets | $141 | $97"]
    fact = fact_for("\n".join(lines), "total assets")
    assert (fact.value if fact else None) == expected
