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
