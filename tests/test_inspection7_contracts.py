"""Bounded seventh-inspection contracts for component and primary-statement scope.

Real excerpts below are static copied source, so these tests require no cached index or
private proof files. Original JPM scope is intentionally absent from the supplied context;
only the explicitly named subhead-removal variants edit that original source.
"""

from dataclasses import replace

import pytest

from filingqa.answer import answer_from_chunks
from filingqa.chunking import Chunk
from filingqa.grounding import extract_fact, numeric_intent

# Unmodified NVDA primary-table source from section chunks #0235 and #0236.
NVDA_PRIMARY = {
    "id": "NVDA-FY2025#0235",
    "doc_id": "NVDA-FY2025",
    "ticker": "NVDA",
    "fiscal_year": 2025,
    "section": "Item 8",
    "page": 52,
    "page_label": "52",
    "text": "NVIDIA Corporation and Subsidiaries\n"
    "Consolidated Statements of Income\n"
    "(In millions, except per share data)\n"
    "Year Ended\n"
    "Jan 26, 2025 | Jan 28, 2024 | Jan 29, 2023\n"
    "Revenue | $130,497 | $60,922 | $26,974\n"
    "Cost of revenue | 32,639 | 16,621 | 11,618\n"
    "Gross profit | 97,858 | 44,301 | 15,356\n"
    "Operating expenses\n"
    "Research and development | 12,914 | 8,675 | 7,339\n"
    "Sales, general and administrative | 3,491 | 2,654 | 2,440\n"
    "Acquisition termination cost | — | — | 1,353\n"
    "Total operating expenses | 16,405 | 11,329 | 11,132\n"
    "Operating income | 81,453 | 32,972 | 4,224\n"
    "Interest income | 1,786 | 866 | 267\n"
    "Interest expense | ( 247 ) | ( 257 ) | ( 262 )\n"
    "Other, net | 1,034 | 237 | ( 48 )\n"
    "Other income (expense), net | 2,573 | 846 | ( 43 )\n"
    "Income before income tax | 84,026 | 33,818 | 4,181\n"
    "Income tax expense (benefit) | 11,146 | 4,058 | ( 187 )\n"
    "Net income | $72,880 | $29,760 | $4,368\n"
    "Net income per share:\n"
    "Basic | $2.97 | $1.21 | $0.18\n"
    "Diluted | $2.94 | $1.19 | $0.17\n"
    "Weighted average shares used in per share computation:\n"
    "Basic | 24,555 | 24,690 | 24,870\n"
    "Diluted | 24,804 | 24,940 | 25,070",
    "header": "NVIDIA FY2025",
    "starts_at_line_boundary": True,
    "ends_at_line_boundary": True,
    "chunking_strategy": None,
}

# Exact expand_context(seed=#0949) order; parent-only heading #0947 is excluded.
JPM_NOTE_CONTEXT = [
    {
        "id": "JPM-FY2025#0949",
        "doc_id": "JPM-FY2025",
        "ticker": "JPM",
        "fiscal_year": 2025,
        "section": "Item 8",
        "page": 312,
        "page_label": "310",
        "text": "Other liabilities | 13,656 | 12,349\n"
        "Long-term debt (c)(d) | 254,633 | 239,626\n"
        "Total liabilities (d) | 347,606 | 324,856\n"
        "Total stockholders’ equity | 362,438 | 344,758\n"
        "Total liabilities and stockholders’ equity | $710,044 | $669,614\n"
        "310 | JPMorgan Chase & Co./2025 Form 10-K\n"
        "Statements of cash flows\n"
        "Year ended December 31, (in millions) | 2025 | 2024 | 2023\n"
        "Operating activities\n"
        "Net income | $57,048 | $58,471 | $49,552\n"
        "Less: Net income of subsidiaries and affiliates | 71,163 | 72,781 | 62,868\n"
        "Parent company net loss | ( 14,115 ) | ( 14,310 ) | ( 13,316 )\n"
        "Cash dividends from subsidiaries and affiliates | 50,000 | 37,000 | 61,000\n"
        "Other operating adjustments | 8,583 | ( 44,671 ) | 9,412\n"
        "Net cash provided by/(used in) operating activities | 44,468 | ( 21,981 ) | 57,096\n"
        "Investing activities\n"
        "Net change in:\n"
        "Advances to and investments in subsidiaries and affiliates, net | — | — | ( 25,000 )\n"
        "All other investing activities, net | 34 | 21 | 25\n"
        "Net cash provided by/(used in) investing activities | 34 | 21 | ( 24,975 )\n"
        "Financing activities\n"
        "Net change in:\n"
        "Borrowings from subsidiaries and affiliates | 1,246 | 49,902 | ( 2,249 )\n"
        "Short-term borrowings | — | ( 999 ) | —",
        "header": "JPMorgan Chase (JPM) 10-K FY2025, Item 8 Financial Statements and Supplementary Data",
        "starts_at_line_boundary": True,
        "ends_at_line_boundary": True,
        "chunking_strategy": "section",
    },
    {
        "id": "JPM-FY2025#0948",
        "doc_id": "JPM-FY2025",
        "ticker": "JPM",
        "fiscal_year": 2025,
        "section": "Item 8",
        "page": 312,
        "page_label": "310",
        "text": "Interest expense to subsidiaries and affiliates (a) | ( 16 ) | 7,433 | 2,258\n"
        "Other interest expense (a) | 15,106 | 8,068 | 11,714\n"
        "Noninterest expense | 3,883 | 3,280 | 3,431\n"
        "Total expense | 18,973 | 18,781 | 17,403\n"
        "Income before income tax benefit and undistributed net income of subsidiaries | 34,063 "
        "| 21,426 | 46,160\n"
        "Income tax benefit | 1,822 | 1,264 | 1,525\n"
        "Equity in undistributed net income of subsidiaries | 21,163 | 35,781 | 1,867\n"
        "Net income | $57,048 | $58,471 | $49,552\n"
        "Other comprehensive income/(loss), net | 8,166 | ( 2,013 ) | 6,898\n"
        "Comprehensive income | $65,214 | $56,458 | $56,450\n"
        "Balance sheets\n"
        "December 31, (in millions) | 2025 | 2024\n"
        "Assets\n"
        "Cash and due from banks | $39 | $38\n"
        "Deposits with banking subsidiaries (b) | 9,751 | 9,762\n"
        "Trading assets - intercompany | 14,885 | 43,214\n"
        "Advances to, and receivables from, subsidiaries:\n"
        "Bank and bank holding company | 136 | 142\n"
        "Non-bank | 24 | 79\n"
        "Investments (at equity) in subsidiaries and affiliates:\n"
        "Bank and bank holding company | 669,449 | 603,044\n"
        "Non-bank | 1,223 | 1,238\n"
        "Other assets | 14,537 | 12,097\n"
        "Total assets | $710,044 | $669,614\n"
        "Liabilities and stockholders’ equity\n"
        "Borrowings from, and payables to, subsidiaries and affiliates | $79,317 | $72,881\n"
        "Short-term borrowings | — | —",
        "header": "JPMorgan Chase (JPM) 10-K FY2025, Item 8 Financial Statements and Supplementary Data",
        "starts_at_line_boundary": True,
        "ends_at_line_boundary": True,
        "chunking_strategy": "section",
    },
    {
        "id": "JPM-FY2025#0950",
        "doc_id": "JPM-FY2025",
        "ticker": "JPM",
        "fiscal_year": 2025,
        "section": "Item 8",
        "page": 313,
        "page_label": "311",
        "text": "Proceeds from long-term borrowings | 30,042 | 44,997 | 19,398\n"
        "Payments of long-term borrowings | ( 25,702 ) | ( 29,753 ) | ( 25,105 )\n"
        "Proceeds from issuance of preferred stock | 3,000 | 2,500 | —\n"
        "Redemption of preferred stock | ( 3,000 ) | ( 9,850 ) | —\n"
        "Treasury stock repurchased | ( 31,591 ) | ( 18,830 ) | ( 9,824 )\n"
        "Dividends paid | ( 16,625 ) | ( 14,783 ) | ( 13,463 )\n"
        "All other financing activities, net | ( 1,882 ) | ( 1,270 ) | ( 879 )\n"
        "Net cash provided by/(used in) financing activities | ( 44,512 ) | 21,914 | ( 32,122 )\n"
        "Net increase/(decrease) in cash and due from banks and deposits with banking "
        "subsidiaries | ( 10 ) | ( 46 ) | ( 1 )\n"
        "Cash and due from banks and deposits with banking subsidiaries at the beginning of the "
        "year | 9,800 | 9,846 | 9,847\n"
        "Cash and due from banks and deposits with banking subsidiaries at the end of the year "
        "(b) | $9,790 | $9,800 | $9,846\n"
        "Cash interest paid | $12,399 | $14,851 | $13,742\n"
        "Cash income taxes paid, net (e) | 276 | 6,252 | 10,291",
        "header": "JPMorgan Chase (JPM) 10-K FY2025, Item 8 Financial Statements and Supplementary Data",
        "starts_at_line_boundary": True,
        "ends_at_line_boundary": True,
        "chunking_strategy": "section",
    },
]


RD_QUESTION = "How much did NVIDIA spend on research and development in fiscal year 2025?"
RD_COMPONENT_ROWS = (
    "Cost of revenue | $178 | $141\nResearch and development | 3,423 | 2,532\n"
    "Total | $4,737 | $3,549"
)
COMPONENT_LEADS = [
    "Stock-based compensation expense recorded within operating expenses was as follows:",
    "Restructuring expense recorded within operating expenses was as follows:",
    "Depreciation and amortization included in our Consolidated Statements of Income was as follows:",
]


class NoModel:
    name = "must-not-call-a-model"

    def generate(self, system, prompt):
        raise AssertionError("This source contract must not call a model")


def fact_for(question, chunks):
    intent = numeric_intent(question, chunks)
    assert intent is not None
    return extract_fact(intent, chunks)[0]


def nvda_component(lead, caption_inside_header):
    metadata = (
        "Year Ended (in millions) | Jan 26, 2025 | Jan 28, 2024"
        if caption_inside_header
        else "(In millions)\nYear Ended | Jan 26, 2025 | Jan 28, 2024"
    )
    return Chunk(
        "NVDA-FY2025#9000",
        "NVDA-FY2025",
        "NVDA",
        2025,
        "Item 8",
        52,
        "52",
        lead + "\n" + metadata + "\n" + RD_COMPONENT_ROWS,
        "NVIDIA FY2025",
    )


@pytest.mark.parametrize("lead", COMPONENT_LEADS)
@pytest.mark.parametrize("caption_inside_header", [False, True])
def test_rd_component_breakdown_does_not_certify_component_as_company_total(
    lead, caption_inside_header
):
    assert fact_for(RD_QUESTION, [nvda_component(lead, caption_inside_header)]) is None


@pytest.mark.parametrize("lead", COMPONENT_LEADS)
@pytest.mark.parametrize("caption_inside_header", [False, True])
def test_component_breakdown_does_not_conflict_with_real_primary_rd_total(
    lead, caption_inside_header
):
    chunks = [nvda_component(lead, caption_inside_header), Chunk(**NVDA_PRIMARY)]
    answer = answer_from_chunks(RD_QUESTION, chunks, NoModel())
    assert answer.method == "source-extracted"
    fact = fact_for(RD_QUESTION, chunks)
    assert fact is not None and fact.value == 12_914_000_000


def test_real_consolidated_income_statement_rd_control():
    fact = fact_for(RD_QUESTION, [Chunk(**NVDA_PRIMARY)])
    assert fact is not None and fact.value == 12_914_000_000


def test_closed_operating_expenses_title_supports_total_rd():
    component = nvda_component("Operating expenses", False)
    source = replace(
        component,
        text=component.text.replace(RD_COMPONENT_ROWS, "Research and development | 12,914 | 8,675"),
    )
    fact = fact_for(RD_QUESTION, [source])
    assert fact is not None and fact.value == 12_914_000_000


def globex_source(prefix="", title="Balance sheets"):
    text = prefix + title + "\n(In millions)\n2031 | 2030\nTotal assets | $900 | $800"
    return Chunk(
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


GLOBEX_QUESTION = "What were GLOBEX total assets at the end of fiscal year 2030?"


@pytest.mark.parametrize(
    "note_prefix",
    [
        "",
        "Notes to consolidated financial statements\n",
        "Note 12 — supplementary information\n",
        "Equity in undistributed net income of subsidiaries\n",
        "Dividends from subsidiaries\n",
    ],
)
def test_bare_item_8_balance_sheet_title_does_not_establish_company_scope(note_prefix):
    assert fact_for(GLOBEX_QUESTION, [globex_source(note_prefix)]) is None


@pytest.mark.parametrize(
    "prefix,title",
    [
        ("THE GLOBEX COMPANY AND SUBSIDIARIES\n", "Balance sheets"),
        ("", "CONSOLIDATED BALANCE SHEETS"),
        ("ITEM 8. FINANCIAL STATEMENTS AND SUPPLEMENTARY DATA\n", "Balance sheets"),
    ],
)
def test_explicit_company_or_actual_item_8_primary_scope_controls(prefix, title):
    fact = fact_for(GLOBEX_QUESTION, [globex_source(prefix, title)])
    assert fact is not None and fact.value == 800_000_000


def test_explicit_registrant_and_bare_statement_cannot_clear_parent_qualification():
    source = globex_source("Parent Company Only\nTHE GLOBEX COMPANY AND SUBSIDIARIES\n")
    assert fact_for(GLOBEX_QUESTION, [source]) is None


@pytest.mark.parametrize(
    "removed_subheads",
    [
        (),
        ("Advances to, and receivables from, subsidiaries:",),
        (
            "Advances to, and receivables from, subsidiaries:",
            "Investments (at equity) in subsidiaries and affiliates:",
        ),
    ],
    ids=["exact-original-safe", "single-removal-safe", "two-removal-regression"],
)
def test_jpm_parent_note_without_qualifier_neighbour_never_becomes_consolidated_assets(
    removed_subheads,
):
    chunks = [Chunk(**c) for c in JPM_NOTE_CONTEXT]
    assert {c.id for c in chunks} == {"JPM-FY2025#0948", "JPM-FY2025#0949", "JPM-FY2025#0950"}
    assert all("Note 33" not in c.text for c in chunks)
    for n, chunk in enumerate(chunks):
        if chunk.id == "JPM-FY2025#0948":
            for subhead in removed_subheads:
                assert chunk.text.splitlines().count(subhead) == 1
            chunks[n] = replace(
                chunk,
                text="\n".join(
                    line for line in chunk.text.splitlines() if line not in removed_subheads
                ),
            )
    question = "What were JPMorgan Chase's total assets at the end of fiscal year 2025?"
    # Both original and single-removal excerpts already fail closed; the two-removal
    # variant must also reject the parent-only $710,044M as consolidated company assets.
    assert fact_for(question, chunks) is None


@pytest.mark.parametrize(
    "earlier_title", ["Consolidated Statements of Income", "Operating expenses"]
)
@pytest.mark.parametrize("lead", COMPONENT_LEADS[:2])
def test_earlier_company_or_operating_title_cannot_authorize_later_component_breakdown(
    earlier_title, lead
):
    component = nvda_component(lead, False)
    component = replace(component, text=earlier_title + "\n" + component.text)
    assert fact_for(RD_QUESTION, [component]) is None


@pytest.mark.parametrize(
    "earlier_title", ["Consolidated Statements of Income", "Operating expenses"]
)
@pytest.mark.parametrize("lead", COMPONENT_LEADS[:2])
def test_earlier_title_component_breakdown_cannot_conflict_with_actual_primary(earlier_title, lead):
    component = nvda_component(lead, False)
    component = replace(component, text=earlier_title + "\n" + component.text)
    chunks = [component, Chunk(**NVDA_PRIMARY)]
    answer = answer_from_chunks(RD_QUESTION, chunks, NoModel())
    assert answer.method == "source-extracted"
    fact = fact_for(RD_QUESTION, chunks)
    assert fact is not None and fact.value == 12_914_000_000


def test_actual_item_8_anchor_does_not_authorize_later_bare_statement_inside_note():
    prefix = (
        "ITEM 8. FINANCIAL STATEMENTS AND SUPPLEMENTARY DATA\nNote 33 — Supplementary information\n"
    )
    assert fact_for(GLOBEX_QUESTION, [globex_source(prefix)]) is None


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Cash flows statements", None),
        ("Consolidated Statements of Cash Flows", 83_000_000),
    ],
)
def test_cash_flow_statement_needs_explicit_company_scope(title, expected):
    source = globex_source(title=title)
    source = replace(
        source,
        text=source.text.replace(
            "Total assets | $900 | $800", "Net cash provided by operating activities | $150 | $83"
        ),
    )
    question = "What was GLOBEX operating cash flow for fiscal year 2030?"
    fact = fact_for(question, [source])
    assert (fact.value if fact else None) == expected


@pytest.mark.parametrize(
    "title", ["Consolidated Balance Sheets", "Consolidated Statements of Cash Flows"]
)
def test_rd_row_in_wrong_statement_kind_is_not_total_rd_expense(title):
    component = nvda_component(title, False)
    component = replace(
        component,
        text=component.text.replace(RD_COMPONENT_ROWS, "Research and development | 12,914 | 8,675"),
    )
    assert fact_for(RD_QUESTION, [component]) is None


@pytest.mark.parametrize(
    "running_header,expected",
    [
        ("PART II\nItem 8\n", 800_000_000),
        ("Item 8\n", None),
        ("Note 33 — Supplementary information\nPART II\nItem 8\n", None),
        ("Parent Company Only\nPART II\nItem 8\n", None),
    ],
)
def test_closed_part_ii_item_8_primary_running_header_needs_unqualified_scope(
    running_header, expected
):
    source = globex_source(running_header, "STOCKHOLDERS’ EQUITY STATEMENTS")
    source = replace(source, text=source.text.replace("Total assets", "Total stockholders' equity"))
    question = "What was GLOBEX total stockholders' equity for fiscal year 2030?"
    fact = fact_for(question, [source])
    assert (fact.value if fact else None) == expected


CLOSED_FRAME_COMPONENT_LAYOUTS = [
    ("Equity-based compensation expense was as follows:", False),
    ("Stock-based compensation expense included in operating expenses", True),
    ("Share-based payment expense was as follows:", False),
    ("Severance expense included in operating expenses", True),
    ("Acquisition-related expense was as follows:", False),
    ("Acquisition-related expense included in operating expenses", True),
]


def expense_layout(declaration, in_header):
    metadata = (
        "(In millions)\n" + declaration + " | Jan 26, 2025 | Jan 28, 2024"
        if in_header
        else declaration + "\n(In millions)\nYear Ended | Jan 26, 2025 | Jan 28, 2024"
    )
    return replace(
        nvda_component("Operating expenses", False),
        text="Operating expenses\n" + metadata + "\n" + RD_COMPONENT_ROWS,
    )


@pytest.mark.parametrize("declaration,in_header", CLOSED_FRAME_COMPONENT_LAYOUTS)
def test_rd_closed_metadata_frame_rejects_component_declarations(declaration, in_header):
    assert fact_for(RD_QUESTION, [expense_layout(declaration, in_header)]) is None


@pytest.mark.parametrize("declaration,in_header", CLOSED_FRAME_COMPONENT_LAYOUTS)
def test_rejected_component_declarations_do_not_conflict_with_primary_rd(declaration, in_header):
    chunks = [expense_layout(declaration, in_header), Chunk(**NVDA_PRIMARY)]
    answer = answer_from_chunks(RD_QUESTION, chunks, NoModel())
    assert answer.method == "source-extracted"
    fact = fact_for(RD_QUESTION, chunks)
    assert fact is not None and fact.value == 12_914_000_000


@pytest.mark.parametrize(
    "note_context",
    [
        "Note 5 – Collaboration Arrangements\n",
        "Notes to consolidated financial statements\n",
        "Equity in undistributed net income of subsidiaries | 500 | 400\n",
    ],
)
def test_weak_operating_expenses_title_cannot_authorize_note_scoped_rd(note_context):
    source = replace(
        nvda_component("Operating expenses", False),
        text=note_context + "Operating expenses\n(In millions)\n"
        "Year Ended | Jan 26, 2025 | Jan 28, 2024\n"
        "Research and development | 300 | 250",
    )
    assert fact_for(RD_QUESTION, [source]) is None


@pytest.mark.parametrize(
    "note_context",
    [
        "Note 5 – Collaboration Arrangements\n",
        "Notes to consolidated financial statements\n",
        "Equity in undistributed net income of subsidiaries | 500 | 400\n",
    ],
)
def test_rejected_note_scoped_rd_table_does_not_conflict_with_primary(note_context):
    source = replace(
        nvda_component("Operating expenses", False),
        text=note_context + "Operating expenses\n(In millions)\n"
        "Year Ended | Jan 26, 2025 | Jan 28, 2024\n"
        "Research and development | 300 | 250",
    )
    chunks = [source, Chunk(**NVDA_PRIMARY)]
    answer = answer_from_chunks(RD_QUESTION, chunks, NoModel())
    assert answer.method == "source-extracted"
    fact = fact_for(RD_QUESTION, chunks)
    assert fact is not None and fact.value == 12_914_000_000


@pytest.mark.parametrize(
    "frame",
    [
        "Operating expenses\n(In millions)\nYear Ended\nJan 26, 2025 | Jan 28, 2024",
        "Consolidated Statements of Income\n(In millions)\nYear Ended January 26,\n2025 | 2024",
    ],
)
def test_closed_rd_metadata_frame_keeps_caption_period_date_and_year_controls(frame):
    source = replace(
        nvda_component("Operating expenses", False),
        text=frame + "\nResearch and development | 12,914 | 8,675",
    )
    fact = fact_for(RD_QUESTION, [source])
    assert fact is not None and fact.value == 12_914_000_000


@pytest.mark.parametrize(
    "declaration,in_header",
    [
        ("Additional financial data are presented in this table:", False),
        ("Selected expense allocations presented for the current period", True),
    ],
)
def test_unknown_rd_frame_prose_or_header_label_is_rejected_without_keyword_list(
    declaration, in_header
):
    assert fact_for(RD_QUESTION, [expense_layout(declaration, in_header)]) is None


@pytest.mark.parametrize(
    "declaration,in_header",
    [
        ("Additional financial data are presented in this table:", False),
        ("Selected expense allocations presented for the current period", True),
    ],
)
def test_unknown_rd_metadata_frame_does_not_conflict_with_primary(declaration, in_header):
    chunks = [expense_layout(declaration, in_header), Chunk(**NVDA_PRIMARY)]
    answer = answer_from_chunks(RD_QUESTION, chunks, NoModel())
    assert answer.method == "source-extracted"
    fact = fact_for(RD_QUESTION, chunks)
    assert fact is not None and fact.value == 12_914_000_000


@pytest.mark.parametrize(
    "notes_header",
    [
        "Notes to the Consolidated Financial Statements (Continued)",
        "Notes to the Condensed Consolidated Financial Statements (Continued)",
    ],
)
@pytest.mark.parametrize("include_primary", [False, True], ids=["alone", "with-primary"])
def test_common_notes_running_headers_cannot_authorize_note_scoped_rd(
    notes_header, include_primary
):
    note = replace(
        nvda_component("Consolidated Statements of Income", False),
        text=notes_header + "\nConsolidated Statements of Income\n(In millions)\n"
        "Year Ended | Jan 26, 2025 | Jan 28, 2024\n"
        "Research and development | 300 | 250",
    )
    chunks = [note] + ([Chunk(**NVDA_PRIMARY)] if include_primary else [])
    fact = fact_for(RD_QUESTION, chunks)
    if include_primary:
        answer = answer_from_chunks(RD_QUESTION, chunks, NoModel())
        assert answer.method == "source-extracted"
        assert fact is not None and fact.value == 12_914_000_000
    else:
        assert fact is None


@pytest.mark.parametrize(
    "caption_inside_header", [False, True], ids=["caption-before", "caption-in-header"]
)
@pytest.mark.parametrize("include_primary", [False, True], ids=["alone", "with-primary"])
def test_split_component_subtables_cannot_lend_company_scope_to_operating_expenses(
    caption_inside_header, include_primary
):
    metadata = (
        "(In millions) | Jan 26, 2025 | Jan 28, 2024"
        if caption_inside_header
        else "(In millions)\nYear Ended | Jan 26, 2025 | Jan 28, 2024"
    )
    text = (
        "Stock-based compensation expense was as follows:\n"
        + metadata
        + "\nCost of revenue | $178 | $141\nOperating expenses\n"
        + metadata
        + "\nResearch and development | 3,423 | 2,532"
    )
    component = replace(nvda_component("Operating expenses", False), text=text)
    chunks = [component] + ([Chunk(**NVDA_PRIMARY)] if include_primary else [])
    fact = fact_for(RD_QUESTION, chunks)
    if include_primary:
        answer = answer_from_chunks(RD_QUESTION, chunks, NoModel())
        assert answer.method == "source-extracted"
        assert fact is not None and fact.value == 12_914_000_000
    else:
        assert fact is None
