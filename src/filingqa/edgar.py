"""Minimal SEC EDGAR client: submissions -> 10-K filings, primary documents, XBRL companyfacts.

SEC fair-access rules: a descriptive User-Agent with contact info and at most 10 requests
per second. Everything downloaded is cached under data/raw/ so re-runs cost nothing.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

from . import config

MIN_INTERVAL = 0.15  # seconds between requests, ~6.5 req/s, safely under the 10 req/s limit


class MissingUserAgent(RuntimeError):
    pass


def user_agent() -> str:
    ua = os.environ.get("SEC_USER_AGENT", "").strip()
    if not ua or "@" not in ua:
        raise MissingUserAgent(
            "SEC_USER_AGENT is not set. SEC EDGAR requires a descriptive User-Agent with contact "
            'info, e.g.  export SEC_USER_AGENT="your-project you@example.com"'
        )
    return ua


@dataclass(frozen=True)
class Filing:
    ticker: str
    cik: int
    accession: str
    period_end: str  # YYYY-MM-DD, the balance-sheet date
    filed: str
    primary_document: str

    @property
    def fiscal_year(self) -> int:
        # Convention used throughout: fiscal year = calendar year of the period end.
        # (Matches how AAPL, MSFT, NVDA, JPM and KO label their own fiscal years.)
        return int(self.period_end[:4])

    @property
    def doc_id(self) -> str:
        return f"{self.ticker}-FY{self.fiscal_year}"

    @property
    def url(self) -> str:
        return (
            f"https://www.sec.gov/Archives/edgar/data/{self.cik}/"
            f"{self.accession.replace('-', '')}/{self.primary_document}"
        )

    def to_dict(self) -> dict:
        return asdict(self)


def select_10k_filings(submissions: dict, ticker: str, cik: int, n: int) -> list[Filing]:
    """Pick the n most recent 10-K filings (by period end) from a submissions JSON."""
    return _select(submissions["filings"]["recent"], ticker, cik, n)


def _select(recent: dict, ticker: str, cik: int, n: int) -> list[Filing]:
    rows = zip(
        recent["form"],
        recent["accessionNumber"],
        recent["reportDate"],
        recent["filingDate"],
        recent["primaryDocument"],
        strict=True,
    )
    filings = [
        Filing(ticker, cik, acc, report, filed, doc)
        for form, acc, report, filed, doc in rows
        if form == "10-K" and report
    ]
    filings.sort(key=lambda f: f.period_end, reverse=True)
    return filings[:n]


class EdgarClient:
    def __init__(self, raw_dir: Path | None = None):
        self.raw_dir = raw_dir or config.RAW_DIR
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self._http = httpx.Client(
            headers={"User-Agent": user_agent(), "Accept-Encoding": "gzip, deflate"},
            timeout=60,
            follow_redirects=True,
        )
        self._last = 0.0

    def _get(self, url: str) -> httpx.Response:
        wait = MIN_INTERVAL - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        resp = self._http.get(url)
        resp.raise_for_status()
        return resp

    def _cached(self, name: str, url: str) -> bytes:
        path = self.raw_dir / name
        if path.exists():
            return path.read_bytes()
        content = self._get(url).content
        path.write_bytes(content)
        return content

    def cik_for(self, ticker: str) -> int:
        data = json.loads(
            self._cached("company_tickers.json", "https://www.sec.gov/files/company_tickers.json")
        )
        for row in data.values():
            if row["ticker"].upper() == ticker.upper():
                return int(row["cik_str"])
        raise KeyError(f"unknown ticker {ticker}")

    def filings(self, ticker: str, n: int) -> list[Filing]:
        cik = self.cik_for(ticker)
        subs = json.loads(
            self._cached(
                f"submissions_{ticker}.json",
                f"https://data.sec.gov/submissions/CIK{cik:010d}.json",
            )
        )
        found = select_10k_filings(subs, ticker.upper(), cik, n)
        # "recent" holds only the last ~1000 filings; prolific filers (JPM) push older 10-Ks
        # into paged side files, so fall back to those when we came up short.
        for extra in subs["filings"].get("files", []):
            if len(found) >= n:
                break
            page = json.loads(
                self._cached(
                    f"submissions_{ticker}_{extra['name']}",
                    f"https://data.sec.gov/submissions/{extra['name']}",
                )
            )
            found = sorted(
                {f.accession: f for f in found + _select(page, ticker.upper(), cik, n)}.values(),
                key=lambda f: f.period_end,
                reverse=True,
            )[:n]
        return found

    def primary_document(self, filing: Filing) -> str:
        name = f"{filing.doc_id}_{filing.accession}.htm"
        return self._cached(name, filing.url).decode("utf-8", errors="replace")

    def companyfacts(self, ticker: str, cik: int) -> dict:
        return json.loads(
            self._cached(
                f"companyfacts_{ticker}.json",
                f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json",
            )
        )


def safe_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", s)
