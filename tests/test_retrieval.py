import pytest

from conftest import FakeEmbedder, make_chunk
from filingqa.retrieval import (
    BM25Retriever,
    DenseRetriever,
    HybridRetriever,
    rrf,
    tokenize,
)


def test_rrf_formula_exact():
    fused = dict(rrf([["a", "b", "c"], ["b", "a", "d"]], k=60))
    assert fused["a"] == pytest.approx(1 / 61 + 1 / 62)
    assert fused["b"] == pytest.approx(1 / 62 + 1 / 61)
    assert fused["c"] == pytest.approx(1 / 63)
    assert fused["d"] == pytest.approx(1 / 63)


def test_rrf_rewards_agreement_over_a_single_first_place():
    # "x" is first in one list only; "y" is second in both. Agreement should win.
    order = [d for d, _ in rrf([["x", "y", "z"], ["w", "y", "z"]], k=60)]
    assert order[0] == "y"


def test_rrf_is_deterministic_on_ties():
    assert [d for d, _ in rrf([["b"], ["a"]])] == ["a", "b"]


def test_tokenize_keeps_numbers_whole_and_drops_possessives():
    assert tokenize("Microsoft's net income: $93,736 million.") == [
        "microsoft", "net", "income", "93,736", "million",
    ]  # fmt: skip


CHUNKS = [
    make_chunk("c1", "risk factors supply chain risk risk"),
    make_chunk("c2", "revenue and net income for the year"),
    make_chunk("c3", "total assets and cash"),
]


def test_bm25_ranks_the_matching_chunk_first():
    hits = BM25Retriever(CHUNKS).search("what was net income", 3)
    assert hits[0][0] == "c2"
    assert len(hits) == 3


def test_dense_ranks_by_cosine():
    emb = FakeEmbedder()
    vectors = emb.embed([c.text for c in CHUNKS], "document")
    hits = DenseRetriever(CHUNKS, vectors, emb).search("risk", 2)
    assert hits[0][0] == "c1"


def test_hybrid_fuses_both_rankings():
    class Fixed:
        def __init__(self, ids):
            self.ids = ids

        def search(self, query, k):
            return [(i, 1.0) for i in self.ids][:k]

    hybrid = HybridRetriever([Fixed(["a", "b", "c"]), Fixed(["c", "b", "d"])], depth=10)
    # c: 1/63 + 1/61 narrowly beats b: 2/62; a and d appear once each.
    assert [i for i, _ in hybrid.search("q", 4)] == ["c", "b", "a", "d"]
