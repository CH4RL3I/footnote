import pytest

from filingqa.metrics import citation_correct, mean, recall_at_k, reciprocal_rank, wilson_interval


def test_recall_at_k_is_any_gold_in_top_k():
    ranked = ["a", "b", "c", "d"]
    assert recall_at_k(ranked, {"c"}, 2) == 0.0
    assert recall_at_k(ranked, {"c"}, 3) == 1.0
    assert recall_at_k(ranked, {"x", "d"}, 4) == 1.0
    assert recall_at_k(ranked, set(), 4) == 0.0


def test_reciprocal_rank_uses_first_gold_hit():
    assert reciprocal_rank(["a", "b", "c"], {"b", "c"}) == 0.5
    assert reciprocal_rank(["a", "b", "c"], {"a"}) == 1.0
    assert reciprocal_rank(["a", "b"], {"z"}) == 0.0


def test_mean_mrr_over_queries():
    rrs = [
        reciprocal_rank(r, g) for r, g in [(["a", "b"], {"a"}), (["a", "b"], {"b"}), (["a"], {"z"})]
    ]
    assert mean(rrs) == pytest.approx((1 + 0.5 + 0) / 3)


def test_wilson_interval_bounds():
    lo, hi = wilson_interval(8, 10)
    assert 0.44 < lo < 0.50 and 0.94 < hi < 0.97
    assert wilson_interval(0, 0) == (0.0, 0.0)
    assert wilson_interval(10, 10)[1] == 1.0


def test_citation_correct_needs_overlap_with_gold():
    assert citation_correct(["a", "b"], {"b"})
    assert not citation_correct([], {"b"})
    assert not citation_correct(["a"], {"b"})
