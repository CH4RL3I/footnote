"""Independent variants of third-review scope, label, caption and period failures."""

import pytest

from filingqa.chunking import Chunk
from filingqa.grounding import extract_fact, numeric_intent


def fact_for(text, metric="total revenue"):
    chunk = Chunk(
        "GLOBEX-FY2031#0000", "GLOBEX-FY2031", "GLOBEX", 2031,
        "Item 8", 0, "1", text, "GLOBEX FY2031",
    )
    intent = numeric_intent(f"What was GLOBEX {metric} for fiscal year 2030?", [chunk])
    assert intent is not None
    return extract_fact(intent, [chunk])[0]


def company_table(row="Revenue", caption="(In millions)", period=""):
    return (
        "CONSOLIDATED STATEMENTS OF INCOME\n" + period + "\n" + caption
        + "\n2031 | 2030\n" + row + " | $170 | $91"
    )


@pytest.mark.parametrize("rollup", ["Net sales by category", "Net sales by reportable segment"])
@pytest.mark.parametrize("new_company_statement", [False, True])
def test_specific_segment_scope_survives_prior_table_rows_until_company_boundary(
    rollup, new_company_statement
):
    text = (
        "Europe segment\n(In millions)\n2031 | 2030\nNet income | $150 | $83\n"
        + ("CONSOLIDATED STATEMENTS OF INCOME\n" if new_company_statement else "")
        + rollup + "\n(In millions)\n2031 | 2030\nTotal net sales | $170 | $91"
    )
    fact = fact_for(text)
    if new_company_statement:
        assert fact is not None and fact.value == 91_000_000
    else:
        assert fact is None


@pytest.mark.parametrize("period", [
    "13-week periods ended", "Three-month periods ended",
    "26-week periods ended", "Nine-month periods ended",
])
def test_hyphenated_subannual_durations_are_not_annual_facts(period):
    assert fact_for(company_table(period=period)) is None


@pytest.mark.parametrize("period", [
    "52-week fiscal years ended", "53-week fiscal years ended",
    "Fifty-two-week fiscal years ended", "Twelve-month fiscal years ended",
])
def test_hyphenated_full_year_durations_remain_supported(period):
    fact = fact_for(company_table(period=period))
    assert fact is not None and fact.value == 91_000_000


@pytest.mark.parametrize("metric,label", [
    ("net income", "Net income attributable to"),
    ("total stockholders' equity", "Equity attributable to"),
])
@pytest.mark.parametrize("qualifier", ["adjusted", "managed", "average", "nonrecurring"])
def test_parent_attributable_row_cannot_bypass_semantic_qualifier_exclusion(
    metric, label, qualifier
):
    assert fact_for(company_table(f"{label} GLOBEX ({qualifier})"), metric) is None


@pytest.mark.parametrize("metric,label", [
    ("net income", "Net income attributable to"),
    ("total stockholders' equity", "Equity attributable to"),
])
@pytest.mark.parametrize("suffix", ["", " (a)", " (1)", " (12)"])
def test_exact_parent_name_and_short_footnotes_remain_supported(metric, label, suffix):
    fact = fact_for(company_table(f"{label} GLOBEX{suffix}"), metric)
    assert fact is not None and fact.value == 91_000_000


@pytest.mark.parametrize("entity", ["GLOBEX Foundation", "Other GLOBEX Holdings"])
def test_parent_name_substring_does_not_identify_the_requested_company(entity):
    assert fact_for(company_table("Net income attributable to " + entity), "net income") is None


@pytest.mark.parametrize("caption", [
    "U.S. dollars in millions, Swiss francs",
    "USD in millions, Indian rupees",
    "$ in millions, unspecified currency",
])
def test_explicit_usd_caption_does_not_hide_an_unknown_currency_tail(caption):
    assert fact_for(company_table(caption=caption)) is None


@pytest.mark.parametrize("caption", [
    "U.S. dollars in millions",
    "U.S. dollars in millions, except per share data",
    "Shares in billions; U.S. dollars in millions",
])
def test_closed_explicit_usd_caption_and_share_notes_remain_supported(caption):
    fact = fact_for(company_table(caption=caption))
    assert fact is not None and fact.value == 91_000_000
