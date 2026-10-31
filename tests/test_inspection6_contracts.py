"""Independent contracts for final-inspection attribution, scope and cash-sign gaps."""

import pytest

from filingqa.chunking import Chunk
from filingqa.grounding import extract_fact, numeric_intent


def source(text, *, section="Item 8", ordinal=0, **boundaries):
    return Chunk(
        f"GLOBEX-FY2031#{ordinal:04d}",
        "GLOBEX-FY2031",
        "GLOBEX",
        2031,
        section,
        1,
        "1",
        text,
        "GLOBEX FY2031",
        **boundaries,
    )


def fact_from(chunks, metric="net income"):
    intent = numeric_intent(f"What was GLOBEX {metric} for fiscal year 2030?", chunks)
    assert intent is not None
    return extract_fact(intent, chunks)[0]


def fact_for(text, metric="net income", *, section="Item 8"):
    return fact_from([source(text, section=section)], metric)


def table(rows, *, title="CONSOLIDATED STATEMENTS OF INCOME", header="2031 | 2030"):
    return f"{title}\n(In millions)\n{header}\n{rows}"


def nci_table(parent_label=None, parent_amount="$96"):
    rows = (
        "Consolidated Net Income | $150 | $100\n"
        "Less: Net income (loss) attributable to noncontrolling interests | 5 | 4"
    )
    if parent_label:
        rows += "\n" + parent_label + " | $145 | " + parent_amount
    return table(rows)


@pytest.mark.parametrize("parent_label", [None, "Net income attributable to GLOBEX shareholders"])
def test_following_nci_row_prevents_certifying_inclusive_net_income(parent_label):
    fact = fact_for(nci_table(parent_label))
    assert fact is None or fact.value == 96_000_000


@pytest.mark.parametrize(
    "parent_label",
    [
        "Net income attributable to shareholders of GLOBEX",
        "Net income attributable to stockholders of GLOBEX Inc.",
        "Net income attributable to shareowners of The GLOBEX Company",
    ],
)
def test_closed_requested_company_shareholder_attribution_selects_parent_income(parent_label):
    fact = fact_for(nci_table(parent_label))
    assert fact is not None and fact.value == 96_000_000


def test_coca_cola_style_following_nci_and_shareowners_parent_rows():
    text = table(
        "Consolidated Net Income | 14,000 | 13,137\n"
        "Less: Net income (loss) attributable to noncontrolling interests | 20 | 30\n"
        "Net Income Attributable to Shareowners of The GLOBEX Company | $13,980 | $13,107"
    )
    fact = fact_for("THE GLOBEX COMPANY AND SUBSIDIARIES\n" + text)
    assert fact is not None and fact.value == 13_107_000_000


def test_recognized_parent_negative_income_keeps_its_sign():
    # Consolidated loss -100 less NCI loss -4 leaves parent loss -96.
    fact = fact_for(
        table(
            "Consolidated Net Income | ($150) | ($100)\n"
            "Less: Net income attributable to noncontrolling interests | ($5) | ($4)\n"
            "Net income attributable to shareholders of GLOBEX | ($145) | ($96)"
        )
    )
    assert fact is not None and fact.value == -96_000_000


@pytest.mark.parametrize(
    "parent_label",
    [
        "Net income attributable to shareholders of GLOBEX (adjusted)",
        "Net income attributable to shareholders of OTHERCO",
        "Net income attributable to shareholders of GLOBEX Foundation",
    ],
)
def test_unrecognized_or_adjusted_parent_row_does_not_certify_inclusive_net_income(parent_label):
    assert fact_for(nci_table(parent_label)) is None


@pytest.mark.parametrize(
    "metric,row,title",
    [
        ("total revenue", "Revenue", "CONSOLIDATED STATEMENTS OF INCOME"),
        ("net income", "Net income", "CONSOLIDATED STATEMENTS OF INCOME"),
        ("operating income", "Operating income", "CONSOLIDATED STATEMENTS OF INCOME"),
        ("total assets", "Total assets", "CONSOLIDATED BALANCE SHEETS"),
        ("total stockholders' equity", "Total stockholders' equity", "CONSOLIDATED BALANCE SHEETS"),
        (
            "research and development expense",
            "Research and development",
            "CONSOLIDATED STATEMENTS OF INCOME",
        ),
        (
            "operating cash flow",
            "Net cash provided by operating activities",
            "CONSOLIDATED STATEMENTS OF CASH FLOWS",
        ),
    ],
)
def test_exact_registrant_company_and_subsidiaries_line_supports_company_tables(metric, row, title):
    text = (
        "Table of contents\nConsolidated financial statements | 65\n"
        "THE GLOBEX COMPANY AND SUBSIDIARIES\n" + table(row + " | $150 | $83", title=title)
    )
    fact = fact_for(text, metric)
    assert fact is not None and fact.value == 83_000_000


def test_valid_registrant_line_cannot_clear_immediate_parent_only_scope():
    text = "Parent Company Only\nTHE GLOBEX COMPANY AND SUBSIDIARIES\n"
    assert fact_for(text + table("Net income | $150 | $83")) is None


def test_explicit_item_7a_to_item_8_transition_supports_primary_statement_in_old_chunk_section():
    text = (
        "ITEM 7A. QUANTITATIVE AND QUALITATIVE DISCLOSURES ABOUT MARKET RISK\n"
        "Interest Rate\nCredit\nEquity\nSENSITIVITY ANALYSIS\n"
        "Risk Categories | Hypothetical Change | June 30, 2031 | Impact\n"
        "Interest rate | 1% | $5 | $2\n49\nPART II\nItem 8\n"
        "ITEM 8. FINANCIAL STATEMENTS AND SUPPLEMENTARY DATA\n"
        + table("Research and development | $150 | $83", title="INCOME STATEMENTS")
    )
    fact = fact_for(text, "research and development expense", section="Item 7A")
    assert fact is not None and fact.value == 83_000_000


def test_repeated_same_item_8_heading_cannot_clear_parent_company_scope():
    text = (
        "ITEM 8. FINANCIAL STATEMENTS AND SUPPLEMENTARY DATA\nParent Company Only\n"
        + table("Other income | $20 | $10", title="INCOME STATEMENTS")
        + "\nITEM 8. FINANCIAL STATEMENTS AND SUPPLEMENTARY DATA\n"
        + table("Net income | $150 | $83", title="INCOME STATEMENTS")
    )
    assert fact_for(text) is None


@pytest.mark.parametrize("header_label", ["Year", "Fiscal Year", "As of", "For the years ended"])
def test_ordinary_year_header_metadata_is_not_an_entity_qualifier(header_label):
    fact = fact_for(table("Net income | $150 | $83", header=header_label + " | 2031 | 2030"))
    assert fact is not None and fact.value == 83_000_000


@pytest.mark.parametrize(
    "label",
    [
        "Operating activities (a)",
        "Operating activities:",
        "Operating activities (1)",
        "Operating activities (a):",
    ],
)
@pytest.mark.parametrize(
    "lead,expected",
    [
        ("Net cash used in", -83_000_000),
        ("Net cash provided by", 83_000_000),
        ("", None),
    ],
)
def test_normalized_operating_activities_label_requires_and_obeys_cash_lead(label, lead, expected):
    rows = (lead + "\n" if lead else "") + label + " | 150 | 83"
    fact = fact_for(table(rows, title="Consolidated cash flows analysis"), "operating cash flow")
    assert (fact.value if fact else None) == expected


def test_literal_end_of_table_source_text_cannot_clear_parent_scope():
    text = (
        "Parent Company Only\n"
        + table("Other income | $20 | $10", title="INCOME STATEMENTS")
        + "\nEND OF TABLE\n"
        + table("Total assets | $900 | $800", title="Balance sheets")
    )
    assert fact_for(text, "total assets") is None


def test_actual_unjoinable_chunk_gap_starts_independent_company_scope():
    first = source(
        "Parent Company Only\npreceding partial paragraph",
        ordinal=0,
        ends_at_line_boundary=False,
    )
    second = source(
        "GLOBEX\n" + table("Total assets | $900 | $800", title="Balance sheets"),
        ordinal=1,
        starts_at_line_boundary=True,
    )
    fact = fact_from([first, second], "total assets")
    assert fact is not None and fact.value == 800_000_000


@pytest.mark.parametrize(
    "following,expected",
    [
        (
            "Other Comprehensive Income:\n"
            "Less: Net income attributable to noncontrolling interests | 5 | 4",
            None,
        ),
        ("Other Comprehensive Income:", 100_000_000),
        (
            "CONSOLIDATED STATEMENTS OF COMPREHENSIVE INCOME\n(In millions)\n2031 | 2030\n"
            "Net income attributable to noncontrolling interests | 5 | 4",
            100_000_000,
        ),
    ],
)
def test_nci_lookahead_crosses_internal_subheadings_but_not_a_new_statement(following, expected):
    text = table("Net income | $150 | $100\n" + following)
    fact = fact_for(text)
    assert (fact.value if fact else None) == expected


def test_bare_item_8_cross_reference_does_not_clear_parent_company_scope():
    text = (
        "ITEM 7A. QUANTITATIVE AND QUALITATIVE DISCLOSURES ABOUT MARKET RISK\n"
        "Parent Company Only\nItem 8\n" + table("Total assets | $150 | $83", title="Balance sheets")
    )
    assert fact_for(text, "total assets", section="Item 7A") is None


def test_punctuated_item_8_boundary_allows_primary_statement_after_risk_headings():
    text = (
        "ITEM 7A. QUANTITATIVE AND QUALITATIVE DISCLOSURES ABOUT MARKET RISK\n"
        "Interest Rate\nCredit\nSENSITIVITY ANALYSIS\nITEM 8.\n"
        + table("Research and development | $150 | $83", title="INCOME STATEMENTS")
    )
    fact = fact_for(text, "research and development expense", section="Item 7A")
    assert fact is not None and fact.value == 83_000_000


@pytest.mark.parametrize("lead", ["Revenue:", "Cost of revenue:"])
def test_income_statement_revenue_section_leads_preserve_later_rd_row(lead):
    rows = lead + "\nProduct | $500 | $400\nResearch and development | $150 | $83"
    fact = fact_for("GLOBEX\n" + table(rows, title="INCOME STATEMENTS"),
                    "research and development expense")
    assert fact is not None and fact.value == 83_000_000


@pytest.mark.parametrize(
    "prefix,equity_heading,expected",
    [
        ("", "THE GLOBEX COMPANY SHAREOWNERS’ EQUITY", 96_000_000),
        ("", "THE OTHERCO COMPANY SHAREOWNERS’ EQUITY", None),
        ("Parent Company Only\n", "THE GLOBEX COMPANY SHAREOWNERS’ EQUITY", None),
    ],
)
def test_requested_company_equity_section_lead_is_local_and_cannot_override_scope(
    prefix, equity_heading, expected
):
    rows = (
        "Total assets | $170 | $120\n" + equity_heading + "\n"
        "Equity Attributable to Shareowners of The GLOBEX Company | $145 | $96\n"
        "Noncontrolling interests | 5 | 4\nTotal equity | $150 | $100"
    )
    fact = fact_for(
        prefix + table(rows, title="CONSOLIDATED BALANCE SHEETS"), "total stockholders' equity"
    )
    assert (fact.value if fact else None) == expected


def test_toc_page_number_row_cannot_clear_parent_qualification_before_company_registry():
    text = (
        "Parent Company Only\nTable of contents\nConsolidated financial statements | 65\n"
        "THE GLOBEX COMPANY AND SUBSIDIARIES\n" + table("Net income | $150 | $83")
    )
    assert fact_for(text) is None


@pytest.mark.parametrize("connective", ["largely offset by", "partly driven by"])
def test_prose_connective_before_cash_flow_statement_is_not_an_entity_heading(connective):
    text = (
        connective
        + "\n"
        + table(
            "Net cash used in\nOperating activities | 150 | 83",
            title="Consolidated cash flows analysis",
        )
    )
    fact = fact_for(text, "operating cash flow")
    assert fact is not None and fact.value == -83_000_000


@pytest.mark.parametrize(
    "toc_row", ["Note 19 | Restructuring | 115", "Note 20 | Operating Segments | 116"]
)
@pytest.mark.parametrize("parent_only", [False, True])
def test_note_toc_rows_are_not_date_headers_or_scope_resetting_financial_data(toc_row, parent_only):
    text = (
        ("Parent Company Only\n" if parent_only else "")
        + "Table of contents\n"
        + toc_row
        + "\nTHE GLOBEX COMPANY AND SUBSIDIARIES\n"
        + table("Net income | $150 | $83")
    )
    fact = fact_for(text)
    assert (fact.value if fact else None) == (None if parent_only else 83_000_000)
