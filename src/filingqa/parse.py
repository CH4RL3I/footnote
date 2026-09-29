"""Turn an EDGAR 10-K HTML document into pages of clean text lines with section labels.

EDGAR inline-XBRL filings mark printed page boundaries with
``<hr style="page-break-after:always">``, which is what gives us page-level citations.
Tables are flattened one row per line ("Net income | 93,736 | 96,995") so a number stays next
to its row label. Sections are the standard 10-K "Item N" headings.
"""

from __future__ import annotations

import re
import sys
import warnings
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, NavigableString, Tag, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

PAGE_BREAK = re.compile(r"<hr[^>]*page-break-after\s*:\s*always[^>]*>", re.I)
BLOCK_TAGS = {
    "div", "p", "li", "ul", "ol", "br", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section",
}  # fmt: skip

ITEM_RE = re.compile(
    r"^item\s+(\d{1,2}[abc]?)\s*[.:–—-]?\s*(.{0,110})$", re.I
)  # "Item 7. Management's Discussion ..."

ITEM_TITLES = {
    "1": "Business",
    "1A": "Risk Factors",
    "1B": "Unresolved Staff Comments",
    "1C": "Cybersecurity",
    "2": "Properties",
    "3": "Legal Proceedings",
    "4": "Mine Safety Disclosures",
    "5": "Market for Registrant's Common Equity",
    "6": "Reserved",
    "7": "Management's Discussion and Analysis (MD&A)",
    "7A": "Quantitative and Qualitative Disclosures About Market Risk",
    "8": "Financial Statements and Supplementary Data",
    "9": "Changes in and Disagreements with Accountants",
    "9A": "Controls and Procedures",
    "9B": "Other Information",
    "9C": "Foreign Jurisdictions that Prevent Inspections",
    "10": "Directors and Executive Officers",
    "11": "Executive Compensation",
    "12": "Security Ownership",
    "13": "Certain Relationships",
    "14": "Principal Accountant Fees",
    "15": "Exhibits and Financial Statement Schedules",
    "16": "Form 10-K Summary",
}
PREAMBLE = "Front matter"


@dataclass
class Line:
    text: str
    page: int  # 1-based index of the HTML page break the line sits on
    section: str = PREAMBLE
    is_table: bool = False


@dataclass
class ParsedFiling:
    doc_id: str
    lines: list[Line] = field(default_factory=list)
    printed_pages: dict[int, str] = field(default_factory=dict)  # page index -> printed number

    def page_label(self, page: int) -> str:
        return self.printed_pages.get(page, str(page))


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip()


def _table_lines(table: Tag) -> list[str]:
    out = []
    for tr in table.find_all("tr"):
        cells = [_clean(td.get_text(" ")) for td in tr.find_all(["td", "th"])]
        merged: list[str] = []
        for c in cells:
            if not c:
                continue
            if merged and merged[-1] in ("$", "(", "$(") and c:
                merged[-1] = (merged[-1] + c).replace("$(", "$ (")
            elif merged and c in (")", "%", ")%", "%)"):
                merged[-1] += c
            else:
                merged.append(c)
        if merged:
            out.append(" | ".join(merged))
    return out


def _html_to_lines(html: str) -> list[tuple[str, bool]]:
    """Returns (text, is_table_row) tuples for one page of HTML."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(["ix:header", "script", "style"]):
        tag.decompose()
    for tag in soup.find_all(style=re.compile(r"display\s*:\s*none", re.I)):
        tag.decompose()
    out: list[tuple[str, bool]] = []
    buf: list[str] = []

    def flush() -> None:
        text = _clean("".join(buf))
        buf.clear()
        if text:
            out.append((text, False))

    def walk(node) -> None:
        for child in node.children:
            if isinstance(child, NavigableString):
                buf.append(str(child))
            elif isinstance(child, Tag):
                if child.name == "table":
                    flush()
                    out.extend((line, True) for line in _table_lines(child))
                elif child.name in BLOCK_TAGS:
                    flush()
                    walk(child)
                    flush()
                else:
                    walk(child)

    walk(soup.body or soup)
    flush()
    return out


PRINTED_PAGE = re.compile(r"^(?:.*\|\s*)?(?:page\s+)?([A-Z]?-?\d{1,3})$", re.I)
PRINTED_PAGE_FIRST = re.compile(r"^(\d{1,3})\s*\|")


def detect_printed_page(page_lines: list[str]) -> str | None:
    """The printed folio is the last short line on the page ('42' or 'Apple Inc. | 2025 | 42')."""
    for text in reversed(page_lines[-3:]):
        m = PRINTED_PAGE.match(text) or PRINTED_PAGE_FIRST.match(text)
        if m and len(text) < 80:
            return m.group(1)
    return None


ITEM_ORDER = {k: n for n, k in enumerate(ITEM_TITLES)}

# JPMorgan's 10-K is a full annual report with no "Item N" headings in the body, only running
# page headers. Map those headers onto the Items the filing's own cross-reference index uses.
RUNNING_HEADERS = {
    "part i": "Part I (Items 1-4)",
    "parts ii and iii": "Parts II-III (Items 5-14)",
    "part iv": "Part IV (Items 15-16)",
    "management\u2019s discussion and analysis": "Item 7",
    "management's discussion and analysis": "Item 7",
    "report of independent registered public accounting firm": "Item 8",
    "consolidated financial statements": "Item 8",
    "notes to consolidated financial statements": "Item 8",
}


def _item_candidates(lines: list[Line]) -> list[tuple[int, str]]:
    cands = []
    for i, ln in enumerate(lines):
        if len(ln.text) > 140:
            continue
        m = ITEM_RE.match(ln.text.replace(" | ", " "))
        # A real heading has a title ("Item 7. Management's..."); running page headers
        # ("Item 7") and cross-references ("Item 1B, 1C") do not.
        if m and m.group(1).upper() in ITEM_ORDER and re.match(r"[A-Za-z\[]", m.group(2)):
            cands.append((i, m.group(1).upper()))
    return cands


def _pick_headings(lines: list[Line], cands: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Choose one heading per Item, in canonical order, maximising the text they own.

    The table of contents also contains "Item N" lines, but each of its entries owns almost
    no text, whereas a real heading owns its whole section. A weighted longest-increasing-
    subsequence over (document position, Item order) picks the real chain.
    """
    weights = []
    for n, (i, _) in enumerate(cands):
        end = cands[n + 1][0] if n + 1 < len(cands) else len(lines)
        weights.append(sum(len(x.text) for x in lines[i:end]))
    best: list[float] = []
    prev: list[int] = []
    for n, (_, key) in enumerate(cands):
        score, back = weights[n], -1
        for m in range(n):
            if ITEM_ORDER[cands[m][1]] < ITEM_ORDER[key] and best[m] + weights[n] > score:
                score, back = best[m] + weights[n], m
        best.append(score)
        prev.append(back)
    if not cands:
        return []
    n = max(range(len(cands)), key=lambda k: best[k])
    chain = []
    while n != -1:
        chain.append(cands[n])
        n = prev[n]
    return chain[::-1]


def _label(lines: list[Line], starts: list[tuple[int, str]]) -> None:
    current, nxt = PREAMBLE, 0
    for i, ln in enumerate(lines):
        while nxt < len(starts) and starts[nxt][0] == i:
            current = starts[nxt][1]
            nxt += 1
        ln.section = current


def _section_sizes(lines: list[Line]) -> dict[str, int]:
    sizes: dict[str, int] = {}
    for ln in lines:
        sizes[ln.section] = sizes.get(ln.section, 0) + len(ln.text)
    return sizes


def assign_sections(lines: list[Line], min_chars: int = 5000, min_items: int = 4) -> None:
    """Label every line with its 10-K Item, in place.

    If fewer than `min_items` Items own at least `min_chars` characters, or one Item owns
    more than 60% of the filing, the Item headings are not trustworthy and we fall back to
    running page headers.
    """
    starts = [(i, f"Item {k}") for i, k in _pick_headings(lines, _item_candidates(lines))]
    _label(lines, starts)
    sizes = _section_sizes(lines)
    item_sizes = {k: v for k, v in sizes.items() if k.startswith("Item")}
    total = sum(sizes.values())
    if sum(v >= min_chars for v in item_sizes.values()) < min_items or max(
        item_sizes.values(), default=0
    ) > (0.6 * total):
        # No usable Item headings (JPMorgan): fall back to running page headers.
        starts, seen_page = [], 0
        for i, ln in enumerate(lines):
            if ln.page != seen_page:
                seen_page = ln.page
                label = RUNNING_HEADERS.get(ln.text.strip().lower())
                if label:
                    starts.append((i, label))
        _label(lines, starts)
        return
    if sizes.get("Item 8", 0) < 5000:
        # NVIDIA puts the financial statements under Item 15; normalise them to Item 8.
        first = next(
            (
                i
                for i, ln in enumerate(lines)
                if ln.section == "Item 15" and ln.text.lower().startswith("report of independent")
            ),
            None,
        )
        if first is not None:
            for ln in lines[first:]:
                if ln.section != "Item 15":
                    break
                ln.section = "Item 8"


def parse_filing(doc_id: str, html: str, **section_opts) -> ParsedFiling:
    sys.setrecursionlimit(20000)
    parsed = ParsedFiling(doc_id)
    for page_no, chunk in enumerate(PAGE_BREAK.split(html), start=1):
        rows = _html_to_lines(chunk)
        if not rows:
            continue
        printed = detect_printed_page([t for t, _ in rows])
        if printed:
            parsed.printed_pages[page_no] = printed
        parsed.lines.extend(Line(t, page_no, is_table=is_t) for t, is_t in rows)
    assign_sections(parsed.lines, **section_opts)
    return parsed
