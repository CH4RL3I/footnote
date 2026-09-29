from filingqa.parse import Line, assign_sections, detect_printed_page, parse_filing


def test_pages_split_on_page_break_hr(sample_doc):
    pages = sorted({ln.page for ln in sample_doc.lines})
    assert pages == [1, 2, 3, 4]


def test_table_rows_keep_numbers_next_to_labels(sample_doc):
    rows = [ln.text for ln in sample_doc.lines if ln.is_table]
    assert "Net sales | $1,250 | $1,100" in rows
    assert "Net loss | $ (45) | $12" in rows or "Net loss | $(45) | $12" in rows


def test_hidden_text_is_dropped(sample_doc):
    assert not any("hidden text" in ln.text for ln in sample_doc.lines)


def test_toc_entries_do_not_become_sections(sample_doc):
    by_text = {ln.text: ln.section for ln in sample_doc.lines}
    # The real Item 7 heading owns the MD&A paragraph, not the table-of-contents row.
    mdna = next(ln for ln in sample_doc.lines if ln.text.startswith("Net sales were"))
    assert mdna.section == "Item 7"
    assert by_text["Item 8. Financial Statements and Supplementary Data"] == "Item 8"
    biz = next(ln for ln in sample_doc.lines if ln.text.startswith("Acme makes"))
    assert biz.section == "Item 1"


def test_printed_page_number_detected(sample_doc):
    assert sample_doc.page_label(4) == "4"
    assert detect_printed_page(["text", "Apple Inc. | 2025 Form 10-K | 24"]) == "24"
    assert detect_printed_page(["text", "58 | JPMorgan Chase & Co./2025 Form 10-K"]) == "58"
    assert detect_printed_page(["a long sentence without any folio at all"]) is None


def test_running_headers_are_not_headings():
    # MSFT prints "Item 1A" at the top of every page; only "Item 1A. Risk Factors" is a heading.
    lines = [Line("Item 1A", 1)] * 3 + [Line("Item 1A. Risk Factors", 1), Line("x" * 9000, 2)]
    for k in ("2", "3", "5"):
        lines += [Line(f"Item {k}. Title", 3), Line("y" * 4000, 3)]
    assign_sections(lines, min_chars=1, min_items=1)
    assert lines[3].section == "Item 1A"
    assert lines[0].section != "Item 1A"


def test_running_header_fallback_for_annual_report_style_filings():
    lines = [Line("cover", 1), Line("Part I", 2), Line("y" * 6000, 2)]
    lines += [Line("Management’s discussion and analysis", 3), Line("z" * 6000, 3)]
    lines += [Line("Notes to consolidated financial statements", 4), Line("w" * 6000, 4)]
    assign_sections(lines)
    assert [ln.section for ln in lines] == [
        "Front matter", "Part I (Items 1-4)", "Part I (Items 1-4)", "Item 7", "Item 7",
        "Item 8", "Item 8",
    ]  # fmt: skip


def test_parse_filing_returns_doc_id():
    assert parse_filing("X-FY2024", "<html><body><div>hi</div></body></html>").doc_id == "X-FY2024"
