"""Paths and defaults."""

from __future__ import annotations

import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("FILINGQA_DATA", "data"))
RAW_DIR = DATA_DIR / "raw"
INDEX_DIR = DATA_DIR / "index"
CACHE_DIR = DATA_DIR / "cache"
RUNS_DIR = DATA_DIR / "runs"
DOCS_DIR = Path("docs")

DEFAULT_TICKERS = ["AAPL", "MSFT", "NVDA", "JPM", "KO"]
DEFAULT_YEARS = 2

# Names used in questions and chunk headers (users say "Microsoft", not "MICROSOFT CORP").
DISPLAY_NAMES = {
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "NVDA": "NVIDIA",
    "JPM": "JPMorgan Chase",
    "KO": "Coca-Cola",
}

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
EMBED_MODEL = "nomic-embed-text"
OLLAMA_CHAT_MODEL = "llama3.2"
ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"

CHUNKINGS = ("fixed", "section")
RETRIEVERS = ("bm25", "dense", "hybrid")
