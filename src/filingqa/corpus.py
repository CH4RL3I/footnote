"""Ingest: download 10-Ks, parse them, and persist the parsed text under data/parsed/."""

from __future__ import annotations

import json
from collections.abc import Callable

from . import config
from .edgar import EdgarClient, Filing
from .parse import Line, ParsedFiling, parse_filing

PARSED_DIR = config.DATA_DIR / "parsed"
MANIFEST = PARSED_DIR / "manifest.json"


def ingest(tickers: list[str], years: int, log: Callable[[str], None] = print) -> list[Filing]:
    PARSED_DIR.mkdir(parents=True, exist_ok=True)
    client = EdgarClient()
    filings: list[Filing] = []
    for ticker in tickers:
        found = client.filings(ticker, years)
        if not found:
            log(f"{ticker}: no 10-K found")
        for filing in found:
            log(f"{filing.doc_id}: {filing.url}")
            doc = parse_filing(filing.doc_id, client.primary_document(filing))
            save_parsed(doc)
            filings.append(filing)
        # Facts are fetched here too so `filingqa eval` needs no network.
        client.companyfacts(ticker, found[0].cik)
    MANIFEST.write_text(json.dumps([f.to_dict() for f in filings], indent=1))
    return filings


def save_parsed(doc: ParsedFiling) -> None:
    payload = {
        "doc_id": doc.doc_id,
        "printed_pages": doc.printed_pages,
        "lines": [[ln.text, ln.page, ln.section, ln.is_table] for ln in doc.lines],
    }
    (PARSED_DIR / f"{doc.doc_id}.json").write_text(json.dumps(payload))


def load_parsed(doc_id: str) -> ParsedFiling:
    raw = json.loads((PARSED_DIR / f"{doc_id}.json").read_text())
    return ParsedFiling(
        doc_id,
        [Line(t, p, s, tbl) for t, p, s, tbl in raw["lines"]],
        {int(k): v for k, v in raw["printed_pages"].items()},
    )


def load_manifest() -> list[Filing]:
    if not MANIFEST.exists():
        raise SystemExit("Nothing ingested yet. Run `filingqa ingest` first.")
    return [Filing(**row) for row in json.loads(MANIFEST.read_text())]


def load_corpus() -> list[ParsedFiling]:
    return [load_parsed(f.doc_id) for f in load_manifest()]
