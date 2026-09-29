"""Answer generators behind one interface: local Ollama (default) or Anthropic."""

from __future__ import annotations

import os
from typing import Protocol

import httpx

from . import config


class Generator(Protocol):
    name: str

    def generate(self, system: str, prompt: str) -> str: ...


class OllamaGenerator:
    def __init__(self, model: str = config.OLLAMA_CHAT_MODEL, url: str = config.OLLAMA_URL):
        self.model, self.url, self.name = model, url, f"ollama:{model}"

    def generate(self, system: str, prompt: str) -> str:
        resp = httpx.post(
            f"{self.url}/api/chat",
            json={
                "model": self.model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                # Ollama's default context is 2048 tokens and silently drops the overflow, which
                # would cut off retrieved excerpts. Six excerpts need more room.
                "options": {"temperature": 0, "num_ctx": 8192, "num_predict": 300},
            },
            timeout=600,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"].strip()


class AnthropicGenerator:
    def __init__(self, model: str = config.ANTHROPIC_MODEL):
        try:
            import anthropic
        except ImportError:
            raise SystemExit(
                "The anthropic backend needs the optional extra: pip install 'filingqa[anthropic]'"
            ) from None
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise SystemExit("ANTHROPIC_API_KEY is not set.")
        self.client, self.model, self.name = anthropic.Anthropic(), model, f"anthropic:{model}"

    def generate(self, system: str, prompt: str) -> str:
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=400,
            temperature=0,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in msg.content if b.type == "text").strip()


def make_generator(backend: str) -> Generator:
    if backend == "ollama":
        return OllamaGenerator()
    if backend == "anthropic":
        return AnthropicGenerator()
    raise ValueError(f"unknown backend {backend!r}")
