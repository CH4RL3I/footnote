"""Fourth-inspection contracts for governing entity, title and table-row scope."""

import pytest

from filingqa.chunking import Chunk
from filingqa.grounding import extract_fact, numeric_intent

METRICS = [
    ("total revenue", "Revenue", "Income statements"),
    ("net income", "Net income", "Income statements"),
    ("total assets", "Total assets", "Balance sheets"),
    ("operating income", "Operating income", "Income statements"),
    ("total stockholders' equity", "Total stockholders' equity", "Balance sheets"),
    ("research and development expense", "Research and development", "Operating expenses"),
    ("operating cash flow", "Net cash provided by operating activities", "Cash flows statements"),
]
QUALIFIED_HEADINGS = [
    "Parent Company Only",
    "Discontinued operations",
    "Guarantor financial information",
    "Condensed consolidating financial information",
    "Europe segment",
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


def table(row="Net income", title="CONSOLIDATED STATEMENTS OF INCOME", prefix=""):
    return f"{title}\n(In millions)\n2031 | 2030\n{prefix}{row} | $170 | $91"


def old_table(heading):
    return (
        heading + "\nStatements of income\n(In millions)\n2031 | 2030\nOther income | $20 | $10\n"
    )


@pytest.mark.parametrize("metric,row,title", METRICS)
@pytest.mark.parametrize("qualification", QUALIFIED_HEADINGS)
def test_qualified_entity_scope_survives_intervening_table_for_every_metric(
    metric, row, title, qualification
):
    assert fact_for(old_table(qualification) + table(row, title), metric) is None


@pytest.mark.parametrize("qualification", QUALIFIED_HEADINGS)
def test_genuine_consolidated_heading_after_prior_table_restores_company_scope(qualification):
    fact = fact_for(old_table(qualification) + table())
    assert fact is not None and fact.value == 91_000_000


def test_immediate_parent_heading_still_qualifies_consolidated_title():
    assert fact_for("Parent Company Only\n" + table()) is None


@pytest.mark.parametrize(
    "heading",
    [
        "Europe Segment Results",
        "European segments:",
        "Europe segment (continued)",
        "Parent-only financial information",
        "Registrant financial information",
        "Unaudited pro forma results",
    ],
)
@pytest.mark.parametrize("paired", [False, True], ids=["single", "respectively"])
def test_narrative_governing_entity_suffixes_plurals_and_colons_are_qualified(heading, paired):
    sentence = (
        "Net income for fiscal years 2031 and 2030 were $170 million and $91 million, respectively."
        if paired
        else "Net income for fiscal year 2030 was $91 million."
    )
    assert fact_for(heading + "\n" + sentence) is None


@pytest.mark.parametrize(
    "heading",
    [
        "Europe Segment Results",
        "European segments:",
        "Parent-only financial information",
        "Unaudited pro forma results",
    ],
)
def test_qualified_heading_survives_prior_table_and_generic_sales_rollup(heading):
    assert (
        fact_for(
            old_table(heading) + table("Total net sales", "Net sales by category"), "total revenue"
        )
        is None
    )


@pytest.mark.parametrize(
    "title",
    [
        "Consolidated statements of income — Europe segment (unaudited)",
        "Consolidated statements of income (Europe segment results)",
        "Consolidated results of operations for the Europe segment are summarized below:",
        "Consolidated statements of income of Globex Bottling Holdings LLC",
        "Consolidated statements of income of OTHERCO Inc.",
        "Consolidated statements of income are presented below:",
        "Selected consolidated statements of income — pro forma 2030",
    ],
)
def test_company_title_requires_a_closed_requested_company_form(title):
    assert fact_for(table(title=title)) is None


@pytest.mark.parametrize(
    "title",
    [
        "Consolidated statements of income",
        "Consolidated statements of income (continued)",
        "Consolidated statements of income of GLOBEX",
        "Consolidated statements of income of GLOBEX Inc. and Subsidiaries",
        "Consolidated statements of income for fiscal year 2030",
    ],
)
def test_closed_company_statement_heading_controls(title):
    fact = fact_for(table(title=title))
    assert fact is not None and fact.value == 91_000_000


@pytest.mark.parametrize(
    "lead,metric,row,title",
    [
        ("Non-current assets:", "total assets", "Total assets", "CONSOLIDATED BALANCE SHEETS"),
        (
            "Non-current liabilities:",
            "total stockholders' equity",
            "Total stockholders' equity",
            "CONSOLIDATED BALANCE SHEETS",
        ),
        (
            "Liabilities and shareholders’ equity:",
            "total stockholders' equity",
            "Total shareholders’ equity",
            "CONSOLIDATED BALANCE SHEETS",
        ),
        (
            "Liabilities and shareowners’ equity:",
            "total stockholders' equity",
            "Total shareowners’ equity",
            "CONSOLIDATED BALANCE SHEETS",
        ),
        (
            "Shareholders’ equity:",
            "total stockholders' equity",
            "Total shareholders’ equity",
            "CONSOLIDATED BALANCE SHEETS",
        ),
        (
            "Commitments and contingencies:",
            "total stockholders' equity",
            "Total stockholders' equity",
            "CONSOLIDATED BALANCE SHEETS",
        ),
        (
            "Operating activities:",
            "operating cash flow",
            "Net cash provided by operating activities",
            "CONSOLIDATED STATEMENTS OF CASH FLOWS",
        ),
        (
            "Cash flows from operating activities:",
            "operating cash flow",
            "Net cash provided by operating activities",
            "CONSOLIDATED STATEMENTS OF CASH FLOWS",
        ),
    ],
)
def test_standard_structural_financial_leads_preserve_table_year_alignment(
    lead, metric, row, title
):
    fact = fact_for(table(row, title, "Other item | $20 | $10\n" + lead + "\n"), metric)
    assert fact is not None and fact.value == 91_000_000


@pytest.mark.parametrize("dash", ["—", "–", "-"])
def test_dash_zero_rows_do_not_terminate_consolidated_table(dash):
    fact = fact_for(
        table(
            "Total assets",
            "CONSOLIDATED BALANCE SHEETS",
            f"Short-term borrowings | {dash} | {dash}\n",
        ),
        "total assets",
    )
    assert fact is not None and fact.value == 91_000_000


@pytest.mark.parametrize(
    "boundary",
    [
        "The regional results follow.",
        "Europe | Americas",
        "Regional financial summary:",
    ],
)
def test_unknown_prose_or_non_year_header_still_ends_column_scope(boundary):
    assert fact_for(table(prefix="Revenue | $20 | $10\n" + boundary + "\n")) is None


@pytest.mark.parametrize(
    "period",
    [
        "4Q results",
        "3Q25 results",
        "2Q26 results",
        "1H results",
        "2H results",
        "YTD results",
        "Year-to-date results",
    ],
)
def test_digit_first_quarter_half_and_year_to_date_titles_are_subannual(period):
    assert fact_for(table(title="CONSOLIDATED STATEMENTS OF INCOME\n" + period)) is None


def test_annual_52_week_title_remains_supported():
    fact = fact_for(table(title="CONSOLIDATED STATEMENTS OF INCOME\n52 weeks ended"))
    assert fact is not None and fact.value == 91_000_000


@pytest.mark.parametrize("lead", ["Operations", "Financing", "Investing"])
def test_cash_flow_section_leads_do_not_qualify_later_primary_equity_table(lead):
    preceding = (
        "CONSOLIDATED STATEMENTS OF CASH FLOWS\n(In millions)\n2031 | 2030\n"
        + lead
        + "\nOther cash flows | $20 | $10\n"
    )
    fact = fact_for(
        preceding + "GLOBEX\n" + table("Total stockholders' equity", "Balance sheets"),
        "total stockholders' equity",
    )
    assert fact is not None and fact.value == 91_000_000


@pytest.mark.parametrize(
    "period,expected", [("4Q results", None), ("1H results", None), ("", 71_000_000)]
)
def test_governing_subannual_period_survives_prior_table_and_company_title(period, expected):
    text = (
        (period + "\n" if period else "")
        + "CONSOLIDATED STATEMENTS OF INCOME\n(In millions)\n2031 | 2030\n"
        "Revenue | $150 | $83\nCONSOLIDATED STATEMENTS OF INCOME\n(In millions)\n"
        "2031 | 2030\nNet income | $97 | $71"
    )
    fact = fact_for(text)
    assert (fact.value if fact else None) == expected


@pytest.mark.parametrize(
    "header,row,expected",
    [
        ("4Q results | 2031 | 2030", "Revenue", None),
        ("1H results | 2031 | 2030", "Revenue", None),
        ("2031 | 2030", "Q4 revenue", 71_000_000),
    ],
)
def test_period_header_metadata_and_row_specific_period_have_distinct_scope(header, row, expected):
    text = (
        "CONSOLIDATED STATEMENTS OF INCOME\n(In millions)\n"
        + header
        + "\n"
        + row
        + " | $150 | $83\n"
        "CONSOLIDATED STATEMENTS OF INCOME\n(In millions)\n2031 | 2030\n"
        "Net income | $97 | $71"
    )
    fact = fact_for(text)
    assert (fact.value if fact else None) == expected


@pytest.mark.parametrize(
    "metadata,header,expected",
    [
        ("", "Europe Segment | 2031 | 2030", None),
        ("", "Parent Company Only | 2031 | 2030", None),
        ("", "Swiss francs | 2031 | 2030", None),
        ("", "Year ended | 2031 | 2030", 83_000_000),
        ("Swiss francs | Year ended\n", "2031 | 2030", None),
        ("Europe Segment | Year ended\n", "2031 | 2030", None),
    ],
)
def test_non_data_pipe_metadata_retains_entity_and_currency_qualifications(
    metadata, header, expected
):
    text = (
        "CONSOLIDATED STATEMENTS OF INCOME\n(In millions)\n"
        + metadata
        + header
        + "\nNet income | $150 | $83"
    )
    fact = fact_for(text)
    assert (fact.value if fact else None) == expected
