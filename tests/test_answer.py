import pytest

from conftest import make_chunk
from filingqa.answer import NOT_FOUND, SYSTEM, answer_from_chunks, build_prompt, parse_citations

CHUNKS = [
    make_chunk("AAPL-FY2024#0001", "Net income | $93,736"),
    make_chunk("AAPL-FY2024#0002", "Other text"),
]


class Echo:
    name = "fake"

    def __init__(self, reply):
        self.reply, self.seen = reply, None

    def generate(self, system, prompt):
        self.seen = (system, prompt)
        return self.reply


def test_prompt_contains_ids_citations_and_question():
    prompt = build_prompt("What was net income?", CHUNKS)
    assert "[AAPL-FY2024#0001] (AAPL 10-K FY2024, Item 8, p.1)" in prompt
    assert prompt.endswith("Question: What was net income?")


def test_system_prompt_forces_grounding_and_citations():
    assert "ONLY" in SYSTEM and NOT_FOUND in SYSTEM and "square brackets" in SYSTEM


def test_citations_parsed_and_hallucinated_ids_dropped():
    text = (
        "It was $93,736 million [AAPL-FY2024#0001], also [AAPL-FY2024#0002] and [MSFT-FY2025#0099]."
    )
    assert parse_citations(text, CHUNKS) == ["AAPL-FY2024#0001", "AAPL-FY2024#0002"]


def test_not_found_detection_and_flow():
    gen = Echo("Not found in the filings")
    ans = answer_from_chunks("q", CHUNKS, gen)
    assert ans.not_found and ans.cited == []
    assert gen.seen[0] == SYSTEM


@pytest.mark.parametrize("text", ["[JPM-FY2024#177556]", "[JPM-FY2024#1775.6]",
                                  "[JPM-FY2024#1775x]", "[JPM-FY2024#1775_extra]",
                                  "[JPM-FY2024#1775-extra]", "[prefixJPM-FY2024#1775]",
                                  "[X.JPM-FY2024#1775]", "[JPM-FY2024#1775.]"])
def test_malformed_or_longer_ids_never_credit_an_allowed_prefix(text):
    chunks = [make_chunk("JPM-FY2024#1775", "Synthetic source", ticker="JPM")]
    assert parse_citations(text, chunks) == []


def test_full_long_ids_require_exact_context_membership_and_preserve_dedup():
    short = make_chunk("JPM-FY2024#1775", "Short source", ticker="JPM")
    long = make_chunk("JPM-FY2024#177556", "Long source", ticker="JPM")
    text = "[JPM-FY2024#177556, JPM-FY2024#1775; JPM-FY2024#177556]"
    assert parse_citations(text, [short]) == [short.id]
    assert parse_citations(text, [long]) == [long.id]
    assert parse_citations(text, [short, long]) == [long.id, short.id]


def test_embedded_long_id_cannot_match_a_short_context_ticker():
    chunks = [make_chunk("JPM-FY2024#0001", "Synthetic source", ticker="JPM")]
    assert parse_citations("[XXJPM-FY2024#0001]", chunks) == []
