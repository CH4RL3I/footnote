"""Independent source contracts for the third review's seven correctness findings.

These are synthetic source excerpts, with no evaluation labels or benchmark values.
Qualified or ambiguous evidence must never receive a source-certified annual USD fact.
"""

import pytest

from filingqa.chunking import Chunk
from filingqa.grounding import extract_fact, numeric_intent

METRICS = [
    ("net income", "Net income"),
    ("total revenue", "Total revenue"),
    ("operating income", "Operating income"),
    ("total assets", "Total assets"),
    ("total stockholders' equity", "Total stockholders' equity"),
    ("research and development expense", "Research and development expense"),
    ("operating cash flow", "Net cash provided by operating activities"),
]
QUALIFIED_HEADINGS = [
    "Europe segment",
    "Parent Company Only",
    "Discontinued operations",
    "Guarantor financial information",
    "Condensed consolidating financial information",
]


def fact_for(text, metric="net income"):
    chunk = Chunk(
        "GLOBEX-FY2031#0000",
        "GLOBEX-FY2031",
        "GLOBEX",
        2031,
        "Item 8",
        1,
        "1",
        text,
        "GLOBEX FY2031",
    )
    intent = numeric_intent(f"What was GLOBEX {metric} for fiscal year 2030?", [chunk])
    assert intent is not None
    return extract_fact(intent, [chunk])[0]


def table(
    row="Net income",
    *,
    title="CONSOLIDATED STATEMENTS OF INCOME",
    caption="(In millions)",
    header="2031 | 2030",
):
    return f"{title}\n{caption}\n{header}\n{row} | $150 | $83"


def narrative(label, paired):
    if paired:
        return (
            f"{label} for fiscal years 2031 and 2030 were "
            "$150 million and $83 million, respectively."
        )
    return f"{label} for fiscal year 2030 was $83 million."


@pytest.mark.parametrize("metric,label", METRICS)
@pytest.mark.parametrize("paired", [False, True], ids=["single", "respectively"])
@pytest.mark.parametrize("heading", QUALIFIED_HEADINGS)
def test_governing_qualified_heading_prevents_company_narrative_fact(
    metric, label, paired, heading
):
    assert fact_for(heading + "\n" + narrative(label, paired), metric) is None


@pytest.mark.parametrize("metric,label", METRICS)
@pytest.mark.parametrize("paired", [False, True], ids=["single", "respectively"])
def test_unqualified_narrative_retains_all_supported_metrics(metric, label, paired):
    fact = fact_for(narrative(label, paired), metric)
    assert fact is not None and fact.value == 83_000_000


@pytest.mark.parametrize("heading", QUALIFIED_HEADINGS)
@pytest.mark.parametrize("gap", [1, 8])
def test_narrative_heading_scope_survives_intervening_accounting_notes(heading, gap):
    text = heading + "\n" + "Supplemental accounting information\n" * gap
    assert fact_for(text + narrative("Net income", False)) is None


@pytest.mark.parametrize(
    "new_title",
    [
        "Other data (units not specified)",
        "CONSOLIDATED BALANCE SHEETS",
        "Supplemental selected financial information",
    ],
)
def test_later_table_cannot_borrow_closed_prior_tables_scale_without_sentinel(new_title):
    text = (
        "CONSOLIDATED STATEMENTS OF INCOME\n(In millions)\n2031 | 2030\n"
        "Revenue | $150 | $83\n" + new_title + "\n2031 | 2030\nNet income | 71 | 42"
    )
    assert fact_for(text) is None


def test_prior_table_scope_cannot_qualify_new_uncaptioned_company_block():
    text = (
        "CONSOLIDATED STATEMENTS OF INCOME\n(In millions)\n2031 | 2030\n"
        "Revenue | $150 | $83\nOther data\n(In millions)\n2031 | 2030\n"
        "Net income | 71 | 42"
    )
    assert fact_for(text) is None


def test_independently_captioned_and_titled_second_table_is_supported():
    text = (
        "CONSOLIDATED STATEMENTS OF INCOME\n(In billions)\n2031 | 2030\n"
        "Revenue | $150 | $83\n"
        "CONSOLIDATED STATEMENTS OF INCOME\n(In millions)\n2031 | 2030\n"
        "Net income | $71 | $42"
    )
    fact = fact_for(text)
    assert fact is not None and fact.value == 42_000_000


@pytest.mark.parametrize(
    "boundary",
    [
        "The regional results follow.\nEurope | Americas",
        "Europe | Americas",
        "The regional results follow.",
    ],
)
def test_non_year_headers_or_prose_end_existing_year_columns(boundary):
    text = (
        "CONSOLIDATED STATEMENTS OF INCOME\n(In millions)\n2031 | 2030\n"
        "Revenue | $150 | $83\n" + boundary + "\nNet income | $40 | $20"
    )
    assert fact_for(text) is None


def test_cash_flow_lead_before_first_data_row_preserves_used_sign():
    text = (
        "CONSOLIDATED STATEMENTS OF CASH FLOWS\n(In millions)\n2031 | 2030\n"
        "Net cash used in:\nOperating activities | $150 | $83"
    )
    fact = fact_for(text, "operating cash flow")
    assert fact is not None and fact.value == -83_000_000


@pytest.mark.parametrize("rollup", ["Net sales by category", "Net sales by reportable segment"])
@pytest.mark.parametrize("order", ["before", "after"])
def test_sales_rollup_never_erases_specific_segment_qualification(rollup, order):
    headings = ["Europe segment", rollup] if order == "before" else [rollup, "Europe segment"]
    text = table("Total net sales", title="\n".join(headings))
    assert fact_for(text, "total revenue") is None


@pytest.mark.parametrize("rollup", ["Net sales by category", "Net sales by reportable segment"])
def test_unqualified_company_sales_rollup_remains_supported(rollup):
    fact = fact_for(table("Total net sales", title=rollup), "total revenue")
    assert fact is not None and fact.value == 83_000_000


@pytest.mark.parametrize("metric,label", METRICS)
@pytest.mark.parametrize("qualification", ["adjusted", "managed", "average", "nonrecurring"])
def test_semantic_parenthetical_row_qualifiers_are_not_footnotes(metric, label, qualification):
    title = (
        "CONSOLIDATED STATEMENTS OF CASH FLOWS"
        if metric == "operating cash flow"
        else "CONSOLIDATED STATEMENTS OF INCOME"
    )
    assert fact_for(table(f"{label} ({qualification})", title=title), metric) is None


@pytest.mark.parametrize("marker", ["a", "b", "1", "12"])
def test_short_parenthetical_footnote_markers_do_not_change_metric(marker):
    fact = fact_for(table(f"Net income ({marker})"))
    assert fact is not None and fact.value == 83_000_000


@pytest.mark.parametrize(
    "metric,label",
    [
        ("net income", "Net income (loss)"),
        ("operating income", "Operating income (loss)"),
    ],
)
def test_loss_is_preserved_as_supported_metric_semantics(metric, label):
    fact = fact_for(table(label).replace("$83", "($83)"), metric)
    assert fact is not None and fact.value == -83_000_000


@pytest.mark.parametrize(
    "caption",
    [
        "(In millions, Swiss francs)",
        "(In millions, Indian rupees)",
        "(In millions, Brazilian reais)",
        "(In millions, Korean won)",
        "(In millions, ₹)",
        "(In millions, unspecified currency)",
    ],
)
def test_plain_caption_rejects_unknown_or_foreign_currency_continuation(caption):
    assert fact_for(table(caption=caption)) is None


@pytest.mark.parametrize(
    "caption",
    [
        "(In millions)",
        "In millions",
        "(In millions, except per share data)",
        "(In millions, except shares in thousands)",
    ],
)
def test_plain_caption_accepts_closed_scale_and_known_share_notes(caption):
    fact = fact_for(table(caption=caption))
    assert fact is not None and fact.value == 83_000_000


@pytest.mark.parametrize(
    "header",
    [
        "Q4 2031 | Q4 2030",
        "Q1 2031 | Q1 2030",
        "H1 2031 | H1 2030",
        "H2 2031 | H2 2030",
        "First half 2031 | First half 2030",
        "Quarter ended 2031 | Quarter ended 2030",
    ],
)
def test_subannual_periods_in_year_header_are_not_annual_facts(header):
    assert fact_for(table(header=header)) is None


@pytest.mark.parametrize(
    "period",
    [
        "Fourth quarter",
        "1st quarter",
        "First half",
        "Half-year results",
        "13 weeks ended",
        "26 weeks ended",
        "39 weeks ended",
    ],
)
@pytest.mark.parametrize("gap", [0, 4])
def test_governing_subannual_period_is_respected_through_title_notes(period, gap):
    title = "CONSOLIDATED STATEMENTS OF INCOME\n" + period + "\n"
    title += "Supplemental accounting note\n" * gap
    assert fact_for(table(title=title.rstrip())) is None


@pytest.mark.parametrize(
    "period",
    [
        "Fiscal years ended",
        "52 weeks ended",
        "53 weeks ended",
        "52 and 53 weeks ended",
        "Fiscal years of 52 or 53 weeks",
    ],
)
def test_supported_annual_fiscal_periods_remain_source_extractable(period):
    fact = fact_for(table(title="CONSOLIDATED STATEMENTS OF INCOME\n" + period))
    assert fact is not None and fact.value == 83_000_000


@pytest.mark.parametrize(
    "header",
    [
        "Budget 2031 | Budget 2030",
        "2031 estimate | 2030 estimate",
        "Q 4 2031 | Q 4 2030",
        "2031 Qtr4 | 2030 Qtr4",
        "Interim 2031 | Interim 2030",
        "2031 | Budget 2030",
    ],
)
def test_year_number_inside_unrecognized_or_subannual_column_is_not_annual(header):
    assert fact_for(table(header=header)) is None


@pytest.mark.parametrize(
    "header",
    [
        "2031 | 2030",
        "FY2031 | FY2030",
        "FY 2031 | FY 2030",
        "December 31, 2031 | December 31, 2030",
        "Year ended December 31, 2031 | Year ended December 31, 2030",
        "Fiscal year ended December 31, 2031 | Fiscal year ended December 31, 2030",
        "52 weeks ended December 31, 2031 | 52 weeks ended December 31, 2030",
        "53 weeks ended December 31, 2031 | 53 weeks ended December 31, 2030",
    ],
)
def test_closed_annual_year_date_and_fiscal_week_column_forms(header):
    fact = fact_for(table(header=header))
    assert fact is not None and fact.value == 83_000_000


@pytest.mark.parametrize("cell", ["$(83)", "($83)"])
def test_standard_accounting_currency_parentheses_retain_negative_sign(cell):
    fact = fact_for(table().replace("$83", cell))
    assert fact is not None and fact.value == -83_000_000


@pytest.mark.parametrize("cell", ["$$83", "$($83)", "($$83)"])
def test_repeated_currency_symbols_are_not_source_certified(cell):
    assert fact_for(table().replace("$83", cell)) is None
