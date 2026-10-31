"""Grounded answering: retrieve, build a cited prompt, generate, and parse the citations."""

from __future__ import annotations

from dataclasses import dataclass, field

from .chunking import Chunk
from .citations import CITATION_ID as CHUNK_ID
from .generate import Generator
from .grounding import YEAR, extract_fact, numeric_intent
from .index import Index
from .retrieval import Retriever

NOT_FOUND = "not found in the filings"

SYSTEM = f"""You answer questions about SEC 10-K filings using ONLY the numbered excerpts \
provided by the user.

Rules:
1. Use nothing but the excerpts. Do not use outside knowledge.
2. After every claim, cite the id of the excerpt that supports it in square brackets, \
for example [AAPL-FY2024#0123].
3. For a numeric question, give the figure with its unit exactly as the excerpt states it \
(financial statements are usually "in millions"), for example "$391,035 million". Preserve \
negative signs/accounting parentheses: a negative figure must be written with an explicit \
minus attached to `$` or the digits, or accounting sign, for example "-$45 million" \
or "$(45) million". Give one plain numeric amount and its citation on a single line, \
without a Markdown list marker, label separator or parenthesized restatement.
4. Use only the requested company and fiscal period. A newer filing may support an older \
period when its comparative column explicitly identifies that period. Do not substitute the \
filing year or a different metric merely because its number matches.
5. If the excerpts do not contain the answer, reply exactly: {NOT_FOUND}
Be brief."""


@dataclass
class Answer:
    question: str
    text: str
    chunks: list[Chunk]  # what the generator saw, in rank order
    cited: list[str]  # cited ids that were actually in the context
    method: str = "model"
    evidence: list[dict] = field(default_factory=list)
    grounding_note: str = ""

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
    intent = numeric_intent(question, chunks)
    if intent:
        relevant = [c for c in chunks if c.ticker == intent.ticker]
        if not relevant:
            return Answer(
                question,
                NOT_FOUND,
                chunks,
                [],
                "source-abstained",
                [],
                "no requested company in context",
            )
        fact, reason = extract_fact(intent, relevant)
        if fact:
            return Answer(
                question,
                fact.render(),
                chunks,
                fact.citations,
                "source-extracted",
                fact.evidence,
                reason,
            )
        if reason == "conflicting source facts":
            return Answer(question, NOT_FOUND, chunks, [], "source-abstained", [], reason)
        if not any(str(intent.year) in YEAR.findall(c.text) for c in relevant):
            return Answer(
                question,
                NOT_FOUND,
                chunks,
                [],
                "source-abstained",
                [],
                "requested period is not explicit in the source body",
            )
        # Unsupported layouts remain visibly unverified, rather than inventing scale/sign.
        chunks = relevant[:6]
    chunks = chunks[:6]
    text = generator.generate(SYSTEM, build_prompt(question, chunks))
    return Answer(
        question,
        text,
        chunks,
        parse_citations(text, chunks),
        "model-fallback" if intent else "model",
        [],
        "unsupported source layout; model answer not source-verified" if intent else "",
    )


def select_context(question: str, index: Index, retriever: Retriever, k: int = 6) -> list[Chunk]:
    """Company-filter the ranked pool, then include adjacent source/header chunks.

    Filing years are never filtered: an explicit comparative column can answer an older FY.
    Adjacent chunks come only from the same filing and Item, without consulting answer labels.
    """
    intent = numeric_intent(question, index.chunks)
    ticker = intent.ticker if intent else None
    hits = retriever.search(question, max(k, 100) if ticker else k)
    selected = [
        index.by_id[cid] for cid, _ in hits if ticker is None or index.by_id[cid].ticker == ticker
    ][:k]
    return expand_context(index, selected) if numeric_intent(question, selected) else selected


def expand_context(index: Index, chunks: list[Chunk]) -> list[Chunk]:
    out = list(chunks)
    seen = {c.id for c in out}
    for c in chunks:
        prefix, suffix = c.id.rsplit("#", 1)
        for n in (int(suffix) - 1, int(suffix) + 1):
            neighbour = index.by_id.get(f"{prefix}#{n:04d}")
            if neighbour and neighbour.section == c.section and neighbour.id not in seen:
                out.append(neighbour)
                seen.add(neighbour.id)
    return out


def answer_question(
    question: str, index: Index, retriever: Retriever, generator: Generator, k: int = 6
) -> Answer:
    return answer_from_chunks(question, select_context(question, index, retriever, k), generator)
