"""Build numeric questions and heuristic source candidates from XBRL facts.

Every 10-K carries machine-readable facts (Revenues, NetIncomeLoss, Assets, ...) tagged with
the filing's accession number and period. That gives us (question, exact answer) pairs for
free. To score *retrieval* we also need the chunk that contains the answer: we render the
value the way a filing would print it ("391,035" in millions, "$391.0 billion" in prose) and
search the chunks for it. These candidate labels do not verify the metric, period or units.
Reviewed labels can be supplied separately through evidence.py.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date

from . import config
from .chunking import Chunk
from .edgar import Filing
from .numfmt import contains_value


@dataclass(frozen=True)
class Metric:
    key: str
    tags: tuple[str, ...]  # us-gaap tags, first one present wins
    instant: bool  # balance-sheet item (point in time) vs. income/cash-flow (a year)
    template: str  # {name}, {fy}


METRICS = [
    Metric(
        "revenue",
        ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"),
        False, "What was {name}'s total revenue for fiscal year {fy}?",
    ),
    Metric("net_income", ("NetIncomeLoss",), False,
           "What was {name}'s net income for fiscal year {fy}?"),
    Metric("total_assets", ("Assets",), True,
           "What were {name}'s total assets at the end of fiscal year {fy}?"),
    Metric("rd_expense", ("ResearchAndDevelopmentExpense",), False,
           "How much did {name} spend on research and development in fiscal year {fy}?"),
    Metric("operating_cash_flow", ("NetCashProvidedByUsedInOperatingActivities",), False,
           "What was {name}'s net cash provided by operating activities in fiscal year {fy}?"),
    Metric("operating_income", ("OperatingIncomeLoss",), False,
           "What was {name}'s operating income for fiscal year {fy}?"),
    Metric("equity", ("StockholdersEquity",), True,
           "What was {name}'s total stockholders' equity at the end of fiscal year {fy}?"),
]  # fmt: skip


@dataclass
class Question:
    id: str
    ticker: str
    fiscal_year: int
    metric: str
    tag: str
    question: str
    value: float  # USD, from XBRL
    accession: str

    def to_dict(self) -> dict:
        return asdict(self)


def _days(start: str, end: str) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def pick_fact(facts: dict, filing: Filing, metric: Metric) -> tuple[str, float] | None:
    """The (tag, USD value) the filing itself reports for its own fiscal period, if any.

    companyfacts repeats comparatives from later filings, and its `fy` field is the *filing's*
    fiscal year, not the period's. So we match on accession number and period end instead.
    """
    gaap = facts.get("facts", {}).get("us-gaap", {})
    for tag in metric.tags:
        for f in gaap.get(tag, {}).get("units", {}).get("USD", []):
            if f.get("accn") != filing.accession or f.get("end") != filing.period_end:
                continue
            if not metric.instant and not (340 <= _days(f.get("start", f["end"]), f["end"]) <= 380):
                continue  # a quarter or a cumulative stub, not the fiscal year
            return tag, float(f["val"])
    return None


def build_questions(
    filings: list[Filing], facts_by_ticker: dict[str, dict], metrics: list[Metric] = METRICS
) -> list[Question]:
    out = []
    for filing in sorted(filings, key=lambda f: (f.ticker, f.fiscal_year)):
        name = config.DISPLAY_NAMES.get(filing.ticker, filing.ticker)
        for metric in metrics:
            hit = pick_fact(facts_by_ticker[filing.ticker], filing, metric)
            if hit is None:
                continue
            tag, value = hit
            out.append(
                Question(
                    id=f"{filing.doc_id}:{metric.key}", ticker=filing.ticker,
                    fiscal_year=filing.fiscal_year, metric=metric.key, tag=tag,
                    question=metric.template.format(name=name, fy=filing.fiscal_year),
                    value=value, accession=filing.accession,
                )
            )  # fmt: skip
    return out


def gold_chunk_ids(question: Question, chunks: list[Chunk]) -> list[str]:
    """Heuristic candidate chunks of the same company containing the target magnitude.

    Any of the company's ingested filings counts: FY2025 figures legitimately appear as
    comparatives in the FY2026 10-K. The same number can also refer to another metric or
    period, so these candidates must not be described as verified claim-level evidence.
    """
    return [
        c.id
        for c in chunks
        if c.ticker == question.ticker and contains_value(c.text, question.value)
    ]
