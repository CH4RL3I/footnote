"""Independent inspection-1 contracts; separate from the unchanged 37 prior cases."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from filingqa import grounding
from filingqa.chunking import Chunk
from filingqa.numfmt import numeric_match

FIXTURE = Path(__file__).parent / "fixtures/source_review_regressions.json"
DATA = json.loads(FIXTURE.read_text())
CASES = DATA["cases"]


def check_case(case: dict) -> dict:
    chunks = [Chunk(**c) for c in case["chunks"]]
    intent = grounding.numeric_intent(case["question"], chunks)
    if case["no_intent"]:
        assert intent is None, f"unsupported question certified numeric: {intent}"
        return {"intent": None}
    assert intent is not None, "supported company-wide annual question not recognized"
    assert intent.ticker == "GLOBEX" and intent.year == 2030
    fact, reason = grounding.extract_fact(intent, chunks)
    allowed = case.get("allowed_values", [case["expected"]])
    values = {Decimal(value) if value is not None else None for value in allowed}
    observed = fact.value if fact is not None else None
    assert observed in values, (
        f"expected one of {allowed}; certified {observed}; "
        f"reason={reason}; kind={getattr(fact, 'kind', None)}"
    )
    if fact is None:
        return {"fact": None, "reason": reason}
    assert fact.citations and set(fact.citations) <= {c.id for c in chunks}
    assert fact.evidence
    for evidence in fact.evidence:
        source = next(c for c in chunks if c.id == evidence["chunk_id"])
        assert evidence["quote"] in source.text, "quote not grounded in cited source"
    assert numeric_match(fact.render(), float(observed)), "rendered output loses value/sign/unit"
    return {"value": str(fact.value), "kind": fact.kind, "rendered": fact.render()}


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_independent_reviewer_contract(case):
    check_case(case)
