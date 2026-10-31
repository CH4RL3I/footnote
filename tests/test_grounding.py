"""Source grounding regression contracts, independent of evaluation answers."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from filingqa import evaluate
from filingqa.answer import NOT_FOUND, answer_from_chunks, expand_context, select_context
from filingqa.chunking import Chunk
from filingqa.goldset import Question
from filingqa.grounding import extract_fact, numeric_intent
from filingqa.index import Index
from filingqa.numfmt import numeric_match

CASES = json.loads(
    (Path(__file__).parent / "fixtures/source_grounding_synthetic.json").read_text()
)["cases"]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_independent_source_contract(case):
    chunks = [Chunk(**c) for c in case["chunks"]]
    intent = numeric_intent(case["question"], chunks)
    if case["no_intent"]:
        assert intent is None
        return
    assert intent is not None
    fact, _ = extract_fact(intent, chunks)
    if case["expected"] is None:
        assert fact is None
        return
    assert fact is not None
    assert fact.value == Decimal(case["expected"])
    assert numeric_match(fact.render(), float(case["expected"]))
    assert fact.citations
    assert all(
        e["quote"] in next(c.text for c in chunks if c.id == e["chunk_id"]) for e in fact.evidence
    )


class NoModel:
    name = "must-not-be-called"

    def generate(self, system, prompt):
        raise AssertionError("Explicit source extraction must not call or credit a model")


def test_complete_numeric_source_bypasses_model_and_preserves_accounting_sign():
    case = next(c for c in CASES if c["name"] == "split_cashflow_heading_and_accounting_negative")
    chunks = [Chunk(**c) for c in case["chunks"]]
    answer = answer_from_chunks(case["question"], chunks, NoModel())
    assert answer.method == "source-extracted"
    assert answer.text.startswith("-$83,000,000 ")
    assert answer.evidence and answer.cited == [chunks[0].id]


def test_conflicting_sources_abstain_without_model_or_number_selection():
    case = next(c for c in CASES if c["name"] == "conflicting_complete_tables_do_not_select_first")
    answer = answer_from_chunks(case["question"], [Chunk(**c) for c in case["chunks"]], NoModel())
    assert answer.text == NOT_FOUND and answer.method == "source-abstained"
    assert not answer.cited


def test_context_company_filter_preserves_comparative_year_and_local_headers():
    case = next(c for c in CASES if c["name"] == "newer_filing_explicit_comparative_column")
    seed = Chunk(**case["chunks"][0])
    neighbour = Chunk(
        **{**seed.to_dict(), "id": seed.doc_id + "#0002", "text": "source continuation"}
    )
    other_item = Chunk(**{**seed.to_dict(), "id": seed.doc_id + "#0000", "section": "Item 7"})
    wrong = Chunk(
        **{**seed.to_dict(), "id": "OMNI-FY2032#0001", "doc_id": "OMNI-FY2032", "ticker": "OMNI"}
    )
    chunks = [seed, neighbour, other_item, wrong]
    index = Index("fixed", chunks, None, {c.id: c for c in chunks})

    class Ranked:
        def search(self, query, k):
            assert k == 100
            return [(wrong.id, 1.0), (seed.id, 0.9)]

    selected = select_context(case["question"], index, Ranked(), 1)
    assert [c.id for c in selected] == [seed.id, neighbour.id]
    assert [c.id for c in expand_context(index, [seed])] == [seed.id, neighbour.id]


def test_missing_period_cannot_be_inferred_from_a_filing_header_or_model():
    case = next(c for c in CASES if c["name"] == "explicit_one_period_narrative")
    source = Chunk(**case["chunks"][0])
    source.text = "Net income was $83 million; no period stated."
    answer = answer_from_chunks(case["question"], [source], NoModel())
    assert answer.not_found
    assert answer.method == "source-abstained" and not answer.cited


def test_evaluation_does_not_credit_source_extraction_as_model_generation(monkeypatch):
    case = next(c for c in CASES if c["name"] == "split_cashflow_heading_and_accounting_negative")
    source = Chunk(**case["chunks"][0])
    index = Index("fixed", [source], None, {source.id: source})
    q = Question(
        "GLOBEX-FY2030:operating_cash_flow",
        "GLOBEX",
        2030,
        "operating_cash_flow",
        "SyntheticCashFlow",
        case["question"],
        -83e6,
        "synthetic-only",
    )
    monkeypatch.setattr(evaluate, "make_generator", lambda _: NoModel())
    summary, details = evaluate.eval_e2e(index, "bm25", [q], {q.id: {source.id}}, "unused", False)
    assert summary.accuracy == 1 and summary.citation == 1
    assert summary.methods == {"source-extracted": 1} and summary.model_calls == 0
    assert "source-grounded-usd-v11" in summary.generator
    assert details[0]["source_evidence"][0]["quote"] == source.text
