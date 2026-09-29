from filingqa.chunking import fixed_chunks, section_chunks
from filingqa.parse import Line, ParsedFiling


def _doc(n_words: int, sections=("Item 1",)) -> ParsedFiling:
    lines = []
    per = n_words // len(sections)
    for s in sections:
        for i in range(per // 10):
            lines.append(Line(" ".join(f"w{s[-1]}{i}_{j}" for j in range(10)), 1, s))
    return ParsedFiling("ACME-FY2024", lines, {1: "7"})


def test_fixed_windows_overlap_by_configured_amount():
    chunks = fixed_chunks(_doc(1000), size=100, overlap=20)
    a, b = chunks[0].text.split(), chunks[1].text.split()
    assert len(a) == 100
    assert a[-20:] == b[:20]


def test_fixed_chunks_cover_every_word():
    doc = _doc(1000)
    covered = set(w for c in fixed_chunks(doc, size=100, overlap=20) for w in c.text.split())
    assert covered == set(w for ln in doc.lines for w in ln.text.split())


def test_section_chunks_never_cross_sections():
    doc = _doc(1000, sections=("Item 1", "Item 7"))
    chunks = section_chunks(doc, size=100)
    assert {c.section for c in chunks} == {"Item 1", "Item 7"}
    for c in chunks:
        marker = c.section[-1]
        assert all(w.startswith(f"w{marker}") for w in c.text.split())


def test_section_chunks_respect_size_and_keep_rows_whole():
    chunks = section_chunks(_doc(1000), size=100)
    assert all(len(c.text.split()) <= 100 for c in chunks)
    assert all(len(line.split()) == 10 for c in chunks for line in c.text.split("\n"))


def test_oversized_paragraph_is_split():
    doc = ParsedFiling("ACME-FY2024", [Line(" ".join(["x"] * 500), 1, "Item 1")])
    assert [len(c.text.split()) for c in section_chunks(doc, size=200)] == [200, 200, 100]


def test_headers_and_citations():
    doc = _doc(100)
    fixed, sect = fixed_chunks(doc)[0], section_chunks(doc)[0]
    assert "Item" not in fixed.header  # fixed chunks are structure-blind
    assert "Item 1 Business" in sect.header
    assert sect.header.startswith("ACME (ACME) 10-K FY2024")
    assert sect.citation == "ACME 10-K FY2024, Item 1, p.7"
    assert sect.id == "ACME-FY2024#0000"
