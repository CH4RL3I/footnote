"""A company sales rollup cannot waive segment scope for other financial totals."""

import pytest

from filingqa.chunking import Chunk
from filingqa.grounding import extract_fact, numeric_intent


def source(text):
    return Chunk("GLOBEX-FY2031#0000", "GLOBEX-FY2031", "GLOBEX", 2031,
                 "Item 8", 1, "1", text, "GLOBEX FY2031")


@pytest.mark.parametrize("heading", [
    "Reportable segments by category", "Operating segments by category",
    "Segment information by category",
])
@pytest.mark.parametrize("metric,row", [
    ("total revenue", "Revenue"), ("net income", "Net income"),
    ("total assets", "Total assets"), ("operating income", "Operating income"),
    ("total stockholders' equity", "Total stockholders' equity"),
    ("research and development expense", "Research and development"),
    ("operating cash flow", "Net cash provided by operating activities"),
])
def test_segment_by_category_is_not_a_company_scope_exception(heading, metric, row):
    c = source("CONSOLIDATED STATEMENTS OF INCOME\n" + heading
               + "\n(In millions)\n2031 | 2030\n" + row + " | $150 | $83")
    intent = numeric_intent(f"What was GLOBEX {metric} for fiscal year 2030?", [c])
    assert intent is not None
    assert extract_fact(intent, [c])[0] is None


@pytest.mark.parametrize("heading", ["Net sales by category", "Net sales by reportable segment"])
def test_explicit_company_total_sales_rollup_remains_supported(heading):
    c = source(heading + "\n(In millions)\n2031 | 2030\nTotal net sales | $150 | $83")
    fact, _ = extract_fact(numeric_intent("What was GLOBEX total revenue for fiscal year 2030?", [c]), [c])
    assert fact is not None and fact.value == 83_000_000


def test_segment_below_company_rollup_still_breaks_company_scope():
    c = source("Net sales by reportable segment\nEurope segment\n(In millions)\n"
               "2031 | 2030\nTotal net sales | $150 | $83")
    assert extract_fact(numeric_intent("What was GLOBEX total revenue for fiscal year 2030?", [c]), [c])[0] is None


def test_currency_declaration_in_governing_title_cannot_hide_behind_notes():
    c = source("CONSOLIDATED STATEMENTS OF INCOME\nCanadian dollars\n"
               "Supplemental note\nSupplemental note\nSupplemental note\n(In millions)\n"
               + "Supplemental note\n" * 10 + "2031 | 2030\nNet income | $150 | $83")
    assert extract_fact(numeric_intent("What was GLOBEX net income for fiscal year 2030?", [c]), [c])[0] is None
