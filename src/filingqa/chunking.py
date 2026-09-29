"""Two chunking strategies, compared head-to-head in the eval.

fixed    sliding windows of N whitespace-delimited words with overlap, blind to structure.
section  greedy packing of whole lines (paragraphs, table rows) that never crosses an Item
         boundary, and whose header names the Item.

Both prepend a one-line header (company, form, fiscal year) to the text that gets indexed, so
"Microsoft ... fiscal year 2025" can match a chunk whose body never repeats the company name.
Only the section strategy puts the Item in that header: that is part of what it buys you.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass

from . import config
from .parse import ITEM_TITLES, ParsedFiling

CHUNK_WORDS = 220
OVERLAP_WORDS = 40


@dataclass
class Chunk:
    id: str
    doc_id: str  # e.g. "AAPL-FY2024"
    ticker: str
    fiscal_year: int
    section: str
    page: int  # first page break index the chunk touches
    page_label: str  # printed page number when detected
    text: str
    header: str

    @property
    def index_text(self) -> str:
        return f"{self.header}\n{self.text}"

    @property
    def citation(self) -> str:
        return f"{self.ticker} 10-K FY{self.fiscal_year}, {self.section}, p.{self.page_label}"

    def to_dict(self) -> dict:
        return asdict(self)


def _company(ticker: str) -> str:
    return config.DISPLAY_NAMES.get(ticker, ticker)


def section_title(section: str) -> str:
    key = section.removeprefix("Item ")
    return f"{section} {ITEM_TITLES[key]}" if key in ITEM_TITLES and section != key else section


def _make(doc: ParsedFiling, n: int, section: str, page: int, text: str, with_section: bool):
    ticker, fy = doc.doc_id.split("-FY")
    head = f"{_company(ticker)} ({ticker}) 10-K FY{fy}"
    if with_section:
        head += f", {section_title(section)}"
    return Chunk(
        f"{doc.doc_id}#{n:04d}", doc.doc_id, ticker, int(fy), section, page,
        doc.page_label(page), text, head,
    )  # fmt: skip


def fixed_chunks(
    doc: ParsedFiling, size: int = CHUNK_WORDS, overlap: int = OVERLAP_WORDS
) -> list[Chunk]:
    words: list[tuple[str, bool, int, str]] = []  # word, starts_line, page, section
    for ln in doc.lines:
        for k, w in enumerate(ln.text.split()):
            words.append((w, k == 0, ln.page, ln.section))
    out, step = [], size - overlap
    for start in range(0, max(len(words), 1), step):
        window = words[start : start + size]
        if not window:
            break
        text = "".join(
            ("\n" if s and i else " " if i else "") + w for i, (w, s, _, _) in enumerate(window)
        )
        out.append(_make(doc, len(out), window[0][3], window[0][2], text, with_section=False))
        if start + size >= len(words):
            break
    return out


def section_chunks(doc: ParsedFiling, size: int = CHUNK_WORDS) -> list[Chunk]:
    out: list[Chunk] = []
    buf: list[str] = []
    buf_words, buf_page, buf_section = 0, 0, ""

    def flush() -> None:
        nonlocal buf, buf_words
        if buf:
            out.append(_make(doc, len(out), buf_section, buf_page, "\n".join(buf), True))
        buf, buf_words = [], 0

    for ln in doc.lines:
        if ln.section != buf_section:
            flush()
            buf_section = ln.section
        pieces = ln.text.split()
        if len(pieces) > size:  # one very long paragraph: cut it into windows
            flush()
            for i in range(0, len(pieces), size):
                buf, buf_words, buf_page = [" ".join(pieces[i : i + size])], size, ln.page
                flush()
            continue
        if buf_words + len(pieces) > size:
            flush()
        if not buf:
            buf_page = ln.page
        buf.append(ln.text)
        buf_words += len(pieces)
    flush()
    return out


CHUNKERS: dict[str, Callable[[ParsedFiling], list[Chunk]]] = {
    "fixed": fixed_chunks,
    "section": section_chunks,
}
