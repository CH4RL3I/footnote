"""Company scope, real window fragments and public output disclosure contracts."""

import json
from types import SimpleNamespace

import pytest

from filingqa import answer, cli, config, generate, index
from filingqa.answer import Answer, answer_from_chunks
from filingqa.chunking import Chunk, fixed_chunks, section_chunks
from filingqa.grounding import extract_fact, numeric_intent
from filingqa.parse import Line, ParsedFiling


def chunk(text, **fields):
    return Chunk(
        "GLOBEX-FY2032#0001",
        "GLOBEX-FY2032",
        "GLOBEX",
        2032,
        "Item 8",
        1,
        "1",
        text,
        "GLOBEX FY2032",
        **fields,
    )


QUESTION = "What was GLOBEX net cash provided by operating activities in fiscal year 2030?"
HEADER = "Consolidated cash flows analysis\n(Dollars in millions)\n2030 | 2029\nNet cash provided by/ (used in)\n"


@pytest.mark.parametrize(
    "prefix,block,expected",
    [
        ("", "", -83_000_000),
        ("Parent Company Only\n", "", None),
        ("Guarantor financial information\n", "", None),
        ("", "Cash flows from discontinued operations\n", None),
        ("", "Parent Company Only\n", None),
        ("Condensed Consolidating Statements of Cash Flows\n", "", None),
    ],
)
def test_cash_flow_company_scope_and_nested_subblocks(prefix, block, expected):
    text = prefix + HEADER + block + "Operating activities | $ (83) | $77"
    source = chunk(text)
    fact, _ = extract_fact(numeric_intent(QUESTION, [source]), [source])
    assert (fact.value if fact else None) == expected


@pytest.mark.parametrize(
    "metric,row",
    [
        ("net income", "Net income"),
        ("total assets", "Total assets"),
        ("total stockholders' equity", "Total stockholders' equity"),
    ],
)
def test_parent_only_qualification_cannot_become_any_company_wide_total(metric, row):
    source = chunk(
        "Parent Company Only\nCONSOLIDATED STATEMENTS OF INCOME\n(In millions)\n2031 | 2030\n"
        + row
        + " | $150 | $83"
    )
    question = f"What was GLOBEX {metric} for fiscal year 2030?"
    assert extract_fact(numeric_intent(question, [source]), [source])[0] is None


@pytest.mark.parametrize("start", [False, None])
def test_a_leading_scope_fragment_cannot_certify_a_cash_flow(start):
    source = chunk(HEADER + "Operating activities | $ (83) | $77", starts_at_line_boundary=start)
    fact, _ = extract_fact(numeric_intent(QUESTION, [source]), [source])
    assert fact is None


@pytest.mark.parametrize("end", [False, None])
def test_truncated_last_value_is_not_a_complete_amount(end):
    source = chunk(
        "CONSOLIDATED STATEMENTS OF INCOME\n(In millions)\n2031 | 2030\nNet income | $150 | $8",
        ends_at_line_boundary=end,
    )
    question = "What was GLOBEX net income for fiscal year 2030?"
    assert extract_fact(numeric_intent(question, [source]), [source])[0] is None


def test_new_chunkers_record_both_line_boundaries():
    doc = ParsedFiling(
        "GLOBEX-FY2032",
        [
            Line("alpha beta gamma delta", 1, "Item 8", False),
            Line("omega psi chi theta", 1, "Item 8", False),
        ],
        {},
    )
    windows = fixed_chunks(doc, size=3, overlap=1)
    assert [(c.starts_at_line_boundary, c.ends_at_line_boundary) for c in windows] == [
        (True, False),
        (False, False),
        (True, False),
        (False, True),
    ]
    long = ParsedFiling(
        "GLOBEX-FY2032", [Line("alpha beta gamma delta epsilon zeta eta", 1, "Item 8", False)], {}
    )
    assert [
        (c.starts_at_line_boundary, c.ends_at_line_boundary) for c in section_chunks(long, size=3)
    ] == [(True, False), (False, False), (False, True)]


def test_legacy_fixed_overlap_does_not_turn_adjusted_row_into_plain_income(monkeypatch, tmp_path):
    lines = [
        "CONSOLIDATED STATEMENTS OF INCOME",
        "(In millions)",
        "2031 | 2030",
        " ".join(["padding"] * 170),
        "Adjusted operating income | $150 | $83",
        " ".join(["tail"] * 100),
    ]
    doc = ParsedFiling("GLOBEX-FY2032", [Line(s, 1, "Item 8", False) for s in lines], {})
    windows = fixed_chunks(doc)
    assert windows[1].text.startswith("operating income |")
    old = []
    for c in windows:
        data = c.to_dict()
        for key in ["starts_at_line_boundary", "ends_at_line_boundary", "chunking_strategy"]:
            data.pop(key)
        old.append(data)
    folder = tmp_path / "fixed"
    folder.mkdir()
    (folder / "chunks.jsonl").write_text("\n".join(json.dumps(d) for d in old))
    monkeypatch.setattr(config, "INDEX_DIR", tmp_path)
    loaded = index.load_index("fixed")
    assert loaded.chunks[1].starts_at_line_boundary is None
    question = "What was GLOBEX operating income for fiscal year 2030?"
    assert extract_fact(numeric_intent(question, loaded.chunks), loaded.chunks)[0] is None


def test_model_fallback_does_not_get_a_false_year_from_a_longer_number():
    source = chunk("Net income context. Reference number 12030; amount $83 million.")
    question = "What was GLOBEX net income for fiscal year 2030?"

    class Never:
        def generate(self, *args):
            pytest.fail("A substring in an unrelated number is not period evidence")

    result = answer_from_chunks(question, [source], Never())
    assert result.not_found and result.method == "source-abstained"


def test_non_numeric_model_context_is_capped_at_six():
    sources = [
        Chunk(**{**chunk("Full excerpt.").to_dict(), "id": f"GLOBEX-FY2032#{n:04d}"})
        for n in range(10)
    ]

    class Check:
        def generate(self, system, prompt):
            assert prompt.count("[GLOBEX-") == 6
            return "Qualitative response."

    assert len(answer_from_chunks("Explain the business.", sources, Check()).chunks) == 6


@pytest.mark.parametrize(
    "method,label",
    [
        ("source-extracted", "Source-derived answer"),
        ("model-fallback", "Model fallback: not source-verified"),
    ],
)
def test_cli_discloses_source_and_unverified_model_modes(monkeypatch, capsys, method, label):
    source = chunk("Supported source body.")
    result = Answer(
        "q",
        "$83,000,000 [GLOBEX-FY2032#0001]",
        [source],
        [source.id],
        method,
        [],
        "mode explanation",
    )
    monkeypatch.setattr(answer, "answer_question", lambda *args: result)
    monkeypatch.setattr(
        index, "load_index", lambda *args: SimpleNamespace(retriever=lambda _: object())
    )
    monkeypatch.setattr(generate, "make_generator", lambda *args: object())
    cli.main(["ask", "q", "--retriever", "bm25"])
    output = capsys.readouterr().out
    assert label in output and "mode explanation" in output and source.id in output
