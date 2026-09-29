"""Tests that need the network or a local Ollama server. Skipped by the default run.

SEC_USER_AGENT="you you@example.com" uv run pytest -m "network or ollama"
"""

import httpx
import pytest

from filingqa.edgar import EdgarClient
from filingqa.embeddings import OllamaEmbedder
from filingqa.generate import OllamaGenerator


@pytest.mark.network
def test_edgar_lists_apple_10k(tmp_path):
    client = EdgarClient(raw_dir=tmp_path)
    filings = client.filings("AAPL", 1)
    assert filings and filings[0].primary_document.endswith(".htm")


@pytest.mark.ollama
def test_ollama_embeddings_are_normalised():
    vecs = OllamaEmbedder().embed(["net income", "total assets"], "document")
    assert vecs.shape[0] == 2 and abs((vecs[0] ** 2).sum() - 1) < 1e-3


@pytest.mark.ollama
def test_ollama_generator_answers():
    try:
        out = OllamaGenerator().generate("Reply with one word.", "Say: ok")
    except httpx.HTTPError:
        pytest.skip("ollama not reachable")
    assert out
