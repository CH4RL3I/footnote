"""Independent currency and second-review source contracts on unseen values/years."""

from decimal import Decimal

import pytest

from filingqa.chunking import Chunk
from filingqa.grounding import extract_fact, numeric_intent


def source(text, number=0, **fields):
    return Chunk(
        f"GLOBEX-FY2031#{number:04d}",
        "GLOBEX-FY2031",
        "GLOBEX",
        2031,
        "Item 8",
        number,
        "1",
        text,
        "GLOBEX FY2031",
        **fields,
    )


def extract(question, chunks):
    intent = numeric_intent(question, chunks)
    assert intent is not None, "contract requires a recognized annual company-wide question"
    fact, reason = extract_fact(intent, chunks)
    if fact:
        assert fact.citations and set(fact.citations) <= {c.id for c in chunks}
        assert fact.evidence
        for evidence in fact.evidence:
            chunk = next(c for c in chunks if c.id == evidence["chunk_id"])
            assert evidence["quote"] in chunk.text
    return fact, reason


FOREIGN_CAPTIONS = [
    "C$ in millions",
    "Canadian dollars in millions",
    "A$ in millions",
    "Australian dollars in millions",
    "HK$ in millions",
    "Hong Kong dollars in millions",
    "NZ$ in millions",
    "New Zealand dollars in millions",
    "S$ in millions",
    "Singapore dollars in millions",
    "CAD in millions",
    "AUD in millions",
    "EUR in millions",
    "Dollars in millions (Canadian dollars)",
    "Shares in millions; Canadian dollars in billions",
    "Canadian dollars in millions; U.S. dollars in millions",
    "U.S. dollars in millions; C$ in billions",
]
USD_CAPTIONS = [
    "(In millions)",
    "Dollars in millions",
    "U.S. dollars in millions",
    "US dollars in millions",
    "USD in millions",
    "US$ in millions",
    "U.S.$ in millions",
    "$ in millions",
    "Shares in billions; U.S. dollars in millions",
]
CURRENCY_CASES = (
    [(c, "", None) for c in FOREIGN_CAPTIONS]
    + [(c, "", Decimal(45_000_000)) for c in USD_CAPTIONS]
    + [("(In millions)", c.split(" in ")[0], None) for c in FOREIGN_CAPTIONS[:9]]
    + [("(In millions)", "U.S. dollars", Decimal(45_000_000))]
)


@pytest.mark.parametrize("caption,declaration,expected", CURRENCY_CASES)
@pytest.mark.parametrize("header_gap", [0, 10])
def test_governing_currency_caption_is_usd_before_source_certification(
    caption, declaration, expected, header_gap
):
    lines = ["CONSOLIDATED STATEMENTS OF INCOME"]
    if declaration:
        lines.append(declaration)
    lines += [caption] + ["Supplemental accounting note"] * header_gap
    lines += ["2031 | 2030", "Net income | $45 | $38"]
    fact, _ = extract(
        "What was GLOBEX net income for fiscal year 2031?", [source("\n".join(lines))]
    )
    assert (fact.value if fact else None) == expected


@pytest.mark.parametrize(
    "lead,cell,expected",
    [
        ("Net cash used in", "$83", -83_000_000),
        ("Net cash used in", "$(83)", -83_000_000),
        ("Net cash used in", "-$83", -83_000_000),
        ("Net cash provided by/ (used in)", "$83", 83_000_000),
        ("Net cash provided by/ (used in)", "$(83)", -83_000_000),
        ("Net cash provided by/ (used in)", "-$83", -83_000_000),
        ("Net cash from (used in)", "$83", 83_000_000),
        ("Net cash from (used in)", "$(83)", -83_000_000),
    ],
)
def test_cash_flow_sign_uses_governing_lead_without_double_negation(lead, cell, expected):
    text = (
        "CONSOLIDATED CASH FLOW STATEMENTS\n(In millions)\n2031 | 2030\n"
        + lead
        + "\nOperating activities | $97 | "
        + cell
    )
    fact, _ = extract(
        "What was GLOBEX net cash provided by operating activities in fiscal year 2030?",
        [source(text)],
    )
    assert fact is not None
    assert fact.value == expected


METRICS = [
    ("total revenue", "Revenue", "CONSOLIDATED STATEMENTS OF INCOME"),
    ("net income", "Net income", "CONSOLIDATED STATEMENTS OF INCOME"),
    ("total assets", "Total assets", "CONSOLIDATED BALANCE SHEETS"),
    ("total stockholders' equity", "Total stockholders' equity", "CONSOLIDATED BALANCE SHEETS"),
    ("operating income", "Operating income", "CONSOLIDATED STATEMENTS OF INCOME"),
    ("research and development expense", "Research and development", "CONSOLIDATED STATEMENTS OF INCOME"),
    (
        "net cash provided by operating activities",
        "Net cash provided by operating activities",
        "CONSOLIDATED CASH FLOW STATEMENTS",
    ),
]


@pytest.mark.parametrize("metric,row,heading", METRICS)
@pytest.mark.parametrize("segment", ["Europe segment", "Segment information", "Reportable segments"])
@pytest.mark.parametrize("consolidated", ["heading", "phrase"])
def test_segment_scope_above_caption_breaks_earlier_consolidated_scope(
    metric, row, heading, segment, consolidated
):
    lead = (
        heading
        if consolidated == "heading"
        else "Segment results are reconciled to consolidated results in Note 18."
    )
    text = f"{lead}\n{segment}\n(In millions)\n2031 | 2030\n{row} | $150 | $83"
    fact, _ = extract(f"What was GLOBEX {metric} for fiscal year 2030?", [source(text)])
    assert fact is None


@pytest.mark.parametrize("metric,row,heading", METRICS)
@pytest.mark.parametrize("gap_kind", ["literal_table_end", "unjoinable"])
def test_table_end_or_unproved_gap_cannot_lend_a_company_title(metric, row, heading, gap_kind):
    table = f"(In millions)\n2031 | 2030\n{row} | $150 | $83"
    if gap_kind == "literal_table_end":
        chunks = [source(heading + "\nEND OF TABLE\n" + table)]
    else:
        # The unknown exterior lines are discarded. The complete interior table survives,
        # but its governing company heading is in a different unjoinable source block.
        fields = {
            "starts_at_line_boundary": None,
            "ends_at_line_boundary": None,
            "chunking_strategy": "section",
        }
        chunks = [
            source("unknown leading fragment\n" + heading + "\nunknown trailing fragment", **fields),
            source("unknown leading fragment\n" + table + "\nunknown trailing fragment", 1, **fields),
        ]
    fact, _ = extract(f"What was GLOBEX {metric} for fiscal year 2030?", chunks)
    assert fact is None


@pytest.mark.parametrize("metric,row,heading", METRICS)
def test_complete_new_block_has_its_own_scope_without_inheriting_prior_qualification(
    metric, row, heading
):
    # A proven independent block is represented by actual boundary provenance,
    # never by special text that could also occur in an ordinary source excerpt.
    chunks = [
        source("Parent Company Only\nCONSOLIDATED STATEMENTS OF INCOME\npartial tail",
               ends_at_line_boundary=False),
        source(heading + f"\n(In millions)\n2031 | 2030\n{row} | $150 | $83", 1,
               starts_at_line_boundary=True),
    ]
    fact, _ = extract(f"What was GLOBEX {metric} for fiscal year 2030?", chunks)
    assert fact is not None
    assert fact.value == 83_000_000


@pytest.mark.parametrize(
    "cell,narrative_amount,expected",
    [
        ("$83", "$91 million", None),
        ("$83.4", "$83 million", Decimal(83_400_000)),
        ("$83.5", "$83 million", Decimal(83_500_000)),
        ("$83.6", "$83 million", None),
        ("$(83.4)", "-$83 million", Decimal(-83_400_000)),
        ("$(83.6)", "-$83 million", None),
        ("$83.4", "$83.4 million", Decimal(83_400_000)),
        ("$83.4", "$83.3 million", None),
    ],
)
def test_cross_priority_complete_facts_agree_within_narrative_stated_precision(
    cell, narrative_amount, expected
):
    text = (
        "CONSOLIDATED STATEMENTS OF INCOME\n(In millions)\n2031 | 2030\n"
        + f"Net income | $150 | {cell}\nEND OF TABLE\n"
        + f"Net income for fiscal year 2030 was {narrative_amount}."
    )
    fact, reason = extract("What was GLOBEX net income for fiscal year 2030?", [source(text)])
    assert (fact.value if fact else None) == expected
    if expected is None:
        assert reason == "conflicting source facts"
