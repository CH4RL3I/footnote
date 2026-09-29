from conftest import make_chunk
from filingqa.edgar import Filing
from filingqa.goldset import METRICS, build_questions, gold_chunk_ids, pick_fact

FY24 = Filing("AAPL", 320193, "0000320193-24-000123", "2024-09-28", "2024-11-01", "a.htm")
FY25 = Filing("AAPL", 320193, "0000320193-25-000079", "2025-09-27", "2025-10-31", "b.htm")
BY_KEY = {m.key: m for m in METRICS}


def test_pick_fact_uses_filing_period_not_comparatives_or_quarters(facts):
    assert pick_fact(facts, FY24, BY_KEY["net_income"]) == ("NetIncomeLoss", 93736000000.0)


def test_pick_fact_requires_matching_accession_and_period(facts):
    # FY25 filing only has a fact whose period end is FY24's: nothing for its own period.
    assert pick_fact(facts, FY25, BY_KEY["net_income"]) is None


def test_instant_facts_have_no_duration_check(facts):
    assert pick_fact(facts, FY24, BY_KEY["total_assets"]) == ("Assets", 364980000000.0)


def test_tag_fallback_for_revenue(facts):
    tag, value = pick_fact(facts, FY24, BY_KEY["revenue"])
    assert tag.startswith("RevenueFromContract") and value == 391035000000.0


def test_build_questions_text_and_ids(facts):
    qs = build_questions([FY24, FY25], {"AAPL": facts})
    ids = {q.id for q in qs}
    assert ids == {"AAPL-FY2024:net_income", "AAPL-FY2024:total_assets", "AAPL-FY2024:revenue"}
    q = next(q for q in qs if q.metric == "net_income")
    assert q.question == "What was Apple's net income for fiscal year 2024?"
    assert q.value == 93736000000.0


def test_gold_chunks_found_by_number_and_company(facts):
    q = next(q for q in build_questions([FY24], {"AAPL": facts}) if q.metric == "net_income")
    chunks = [
        make_chunk("AAPL-FY2024#0001", "Net income | $93,736 | $96,995"),
        make_chunk("AAPL-FY2024#0002", "Net income was $95.0 billion"),  # different number
        make_chunk("AAPL-FY2024#0004", "Net income was $93.7 billion, down slightly"),  # prose form
        make_chunk("AAPL-FY2024#0003", "Gross margin | $180,683 | $169,148"),
        make_chunk("MSFT-FY2024#0001", "Net income | $93,736", ticker="MSFT"),  # other company
        make_chunk("AAPL-FY2025#0009", "Net income | $112,010 | $93,736", fy=2025),  # comparative
    ]
    assert gold_chunk_ids(q, chunks) == [
        "AAPL-FY2024#0001",
        "AAPL-FY2024#0004",
        "AAPL-FY2025#0009",
    ]
