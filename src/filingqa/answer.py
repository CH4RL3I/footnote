"""Grounded answering: retrieve, build a cited prompt, generate, and parse the citations."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .chunking import Chunk
from .generate import Generator
from .index import Index
from .retrieval import Retriever

NOT_FOUND = "not found in the filings"
CHUNK_ID = re.compile(r"[A-Z][A-Z.]{0,5}-FY\d{4}#\d{4}")

SYSTEM = f"""You answer questions about SEC 10-K filings using ONLY the numbered excerpts \
provided by the user.

Rules:
1. Use nothing but the excerpts. Do not use outside knowledge.
2. After every claim, cite the id of the excerpt that supports it in square brackets, \
for example [AAPL-FY2024#0123].
3. For a numeric question, give the figure with its unit exactly as the excerpt states it \
(financial statements are usually "in millions"), for example "$391,035 million".
4. Excerpts are tagged with company and fiscal year. Use only excerpts for the company and \
fiscal year asked about.
5. If the excerpts do not contain the answer, reply exactly: {NOT_FOUND}
Be brief."""


@dataclass
class Answer:
    question: str
    text: str
    chunks: list[Chunk]  # what the generator saw, in rank order
    cited: list[str]  # cited ids that were actually in the context

    @property
    def not_found(self) -> bool:
        return NOT_FOUND in self.text.lower()


def build_prompt(question: str, chunks: list[Chunk]) -> str:
    blocks = [f"[{c.id}] ({c.citation})\n{c.text}" for c in chunks]
    return "Excerpts:\n\n" + "\n\n---\n\n".join(blocks) + f"\n\nQuestion: {question}"


def parse_citations(text: str, chunks: list[Chunk]) -> list[str]:
    """Cited ids in order of appearance; ids not present in the context are dropped."""
    allowed = {c.id for c in chunks}
    seen: list[str] = []
    for cid in CHUNK_ID.findall(text):
        if cid in allowed and cid not in seen:
            seen.append(cid)
    return seen


def answer_from_chunks(question: str, chunks: list[Chunk], generator: Generator) -> Answer:
    text = generator.generate(SYSTEM, build_prompt(question, chunks))
    return Answer(question, text, chunks, parse_citations(text, chunks))


def answer_question(
    question: str, index: Index, retriever: Retriever, generator: Generator, k: int = 6
) -> Answer:
    hits = retriever.search(question, k)
    return answer_from_chunks(question, [index.by_id[cid] for cid, _ in hits], generator)
