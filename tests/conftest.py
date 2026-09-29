import json
from pathlib import Path

import numpy as np
import pytest

from filingqa.chunking import Chunk
from filingqa.parse import parse_filing

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_doc():
    return parse_filing(
        "ACME-FY2024",
        (FIXTURES / "sample_10k.html").read_text(),
        min_chars=1,
        min_items=1,
    )


@pytest.fixture
def facts():
    return json.loads((FIXTURES / "companyfacts_sample.json").read_text())


def make_chunk(cid: str, text: str, ticker="AAPL", fy=2024, section="Item 8") -> Chunk:
    return Chunk(cid, f"{ticker}-FY{fy}", ticker, fy, section, 1, "1", text, f"{ticker} 10-K")


class FakeEmbedder:
    """Deterministic bag-of-keywords embedder so dense retrieval can be tested offline."""

    name = "fake"
    vocab = ("revenue", "income", "risk", "cash", "assets")

    def embed(self, texts, kind):
        v = np.array([[t.lower().count(w) for w in self.vocab] for t in texts], dtype=np.float32)
        n = np.linalg.norm(v, axis=1, keepdims=True)
        return v / np.where(n == 0, 1, n)
