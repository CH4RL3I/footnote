"""Currency text cannot hide outside a recognized monetary caption clause."""

import pytest

from filingqa.chunking import Chunk
from filingqa.grounding import extract_fact, numeric_intent


def fact_for(text, metric="net income"):
    chunk = Chunk(
        "GLOBEX-FY2031#0000", "GLOBEX-FY2031", "GLOBEX", 2031,
        "Item 8", 0, "1", text, "GLOBEX FY2031",
    )
    intent = numeric_intent(f"What was GLOBEX {metric} for fiscal year 2030?", [chunk])
    assert intent is not None
    return extract_fact(intent, [chunk])[0]


def income_table(caption):
    return (
        "CONSOLIDATED STATEMENTS OF INCOME\n" + caption
        + "\n2031 | 2030\nNet income | $170 | $91"
    )


@pytest.mark.parametrize("caption", [
    "Swiss francs (in millions)",
    "Indian rupees (in millions)",
    "Swiss francs; U.S. dollars in millions",
    "Swiss francs\n(In millions)",
    "Net income in millions, Swiss francs",
])
def test_unknown_currency_cannot_hide_before_or_outside_monetary_scale(caption):
    assert fact_for(income_table(caption)) is None


@pytest.mark.parametrize("caption", [
    "Net income in millions",
    "Shares in billions; U.S. dollars in millions",
    "Dollars in millions, except per share data",
])
def test_recognized_metric_share_and_exception_caption_clauses_remain_supported(caption):
    fact = fact_for(income_table(caption))
    assert fact is not None and fact.value == 91_000_000


def test_date_prefix_on_current_caption_header_remains_supported():
    text = (
        "Selected Consolidated balance sheets data (continued)\n"
        "December 31, (in millions) | 2031 | 2030 | Change\n"
        "Total assets | $170 | $91 | 87%"
    )
    fact = fact_for(text, "total assets")
    assert fact is not None and fact.value == 91_000_000


def test_explicit_consolidated_reconciliation_caption_remains_supported():
    text = (
        "A reconciliation to the Consolidated Statements of Operations follows (in millions):\n"
        "2031 | 2030\nSegment operating income | $190 | $110\n"
        "Corporate expense | (20) | (19)\nTotal operating income | $170 | $91"
    )
    fact = fact_for(text, "operating income")
    assert fact is not None and fact.value == 91_000_000


@pytest.mark.parametrize("currency", ["U.S. dollars", "USD"])
def test_closed_us_currency_declaration_governs_plain_scale(currency):
    fact = fact_for(income_table(currency + "\n(In millions)"))
    assert fact is not None and fact.value == 91_000_000


@pytest.mark.parametrize("gap", [0, 10])
def test_supplemental_accounting_notes_do_not_become_currency_declarations(gap):
    caption = "(In millions)\n" + "Supplemental accounting note\n" * gap
    fact = fact_for(income_table(caption))
    assert fact is not None and fact.value == 91_000_000


def test_split_caption_and_date_metadata_remain_supported():
    text = (
        "CONSOLIDATED STATEMENTS OF CASH FLOWS\n"
        "(in millions) | Year ended December 31,\n2031 | 2030\n"
        "Net cash provided by/ (used in)\nOperating activities | $170 | $(91)"
    )
    fact = fact_for(text, "operating cash flow")
    assert fact is not None and fact.value == -91_000_000


@pytest.mark.parametrize("currency", ["Swiss francs.", "₹"])
def test_unknown_standalone_currency_with_punctuation_or_symbol_is_rejected(currency):
    assert fact_for(income_table(currency + "\n(In millions)")) is None


@pytest.mark.parametrize("note", [
    "Refer to accompanying notes.", "See accompanying notes.",
])
def test_accompanying_financial_notes_before_consolidated_title_remain_supported(note):
    fact = fact_for(note + "\n" + income_table("(In millions)"))
    assert fact is not None and fact.value == 91_000_000
