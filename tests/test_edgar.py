import pytest

from filingqa import edgar

SUBMISSIONS = {
    "filings": {
        "recent": {
            "form": ["8-K", "10-K", "10-Q", "10-K", "10-K"],
            "accessionNumber": ["a1", "a2", "a3", "a4", "a5"],
            "reportDate": ["2025-01-01", "2024-09-28", "2025-03-29", "2025-09-27", "2023-09-30"],
            "filingDate": ["x"] * 5,
            "primaryDocument": ["d1", "d2.htm", "d3", "d4.htm", "d5.htm"],
        }
    }
}


def test_selects_latest_10ks_by_period_end():
    got = edgar.select_10k_filings(SUBMISSIONS, "AAPL", 320193, 2)
    assert [f.accession for f in got] == ["a4", "a2"]
    assert [f.fiscal_year for f in got] == [2025, 2024]
    assert got[0].doc_id == "AAPL-FY2025"
    assert got[0].url == "https://www.sec.gov/Archives/edgar/data/320193/a4/d4.htm"


def test_missing_user_agent_fails_clearly(monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    with pytest.raises(edgar.MissingUserAgent, match="SEC_USER_AGENT"):
        edgar.user_agent()
    monkeypatch.setenv("SEC_USER_AGENT", "no contact info here")
    with pytest.raises(edgar.MissingUserAgent):
        edgar.user_agent()


def test_user_agent_read_from_env(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "proj me@example.com")
    assert edgar.user_agent() == "proj me@example.com"
