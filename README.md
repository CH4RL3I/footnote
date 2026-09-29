# footnote: SEC filings Q&A with citations, measured

[![CI](https://github.com/CH4RL3I/footnote/actions/workflows/ci.yml/badge.svg)](https://github.com/CH4RL3I/footnote/actions/workflows/ci.yml) ![Python](https://img.shields.io/badge/python-3.11%2B-blue) ![License: MIT](https://img.shields.io/badge/license-MIT-green)

Question answering over SEC 10-K filings with page-level citations, and a harness that measures how often it is actually right.

The chatbot is the small part. The point is the evaluation: a gold question set built automatically from XBRL data, retrieval metrics for every chunking and retrieval configuration, and end-to-end answer and citation scoring.

![Results](docs/results.png)

## Results

Corpus: the two latest 10-Ks for AAPL, MSFT, NVDA, JPM and KO (10 filings, about 4,700 chunks). Questions: 64, generated from XBRL facts (no human labelling). Full tables and per-question data are in [docs/results.md](docs/results.md) and [docs/results.json](docs/results.json).

**Retrieval.** Recall@k is the share of questions where at least one gold chunk is in the top k. No LLM involved, so it is deterministic.

| Chunking | Retriever | Recall@1 | Recall@5 | Recall@10 | Recall@20 | MRR |
|---|---|---|---|---|---|---|
| fixed | bm25 | 17% | 28% | 33% | 41% | 0.229 |
| fixed | dense | 23% | 64% | 81% | 86% | 0.406 |
| fixed | hybrid | 33% | 55% | 70% | 84% | 0.449 |
| section | bm25 | 6% | 19% | 33% | 45% | 0.141 |
| section | dense | 33% | 50% | 69% | 84% | 0.426 |
| section | hybrid | 30% | 53% | 59% | 72% | 0.403 |

With n=64 the 95% Wilson intervals are wide (Recall@5 for fixed + dense is 64%, 52% to 75%). Many of the differences between the middle rows are within noise.

**End to end** (llama3.2 3B via Ollama, top 6 chunks). "Oracle" hands the generator the gold chunks directly, which separates retrieval failures from reading failures.

| Configuration | Answer accuracy (95% CI) | Correct and cited a gold chunk | Cited any gold chunk | Said "not found" |
|---|---|---|---|---|
| fixed + dense | 56% (44% to 68%) | 44% | 48% | 8% |
| oracle (gold chunks given) | 92% (83% to 97%) | 81% | 88% | 0% |

I ran end to end for one configuration only: fixed + dense, chosen for the best Recall@5, which is closest to the 6 chunks the generator sees. Hybrid has the best MRR (0.449) but was not run end to end.

### What the numbers say

- **Naive beat clever.** Fixed windows with dense retrieval had the best recall at 5 and 10. Section-aware chunking did not help, and section + hybrid was worse than section + dense at k=10. I expected the opposite. A plausible reason, not tested: a numeric answer sits in a financial-statement row, and splitting on structure does not make that row any easier to match against a question.
- **BM25 alone is poor** (Recall@5 of 19% to 28%). A question such as "Apple's net income" shares most of its words with the same row in every company's filing, and only the company name and year differ.
- **Retrieval is the bottleneck, not the model.** Given the right chunks, llama3.2 answers 92% of questions. Given retrieved chunks it answers 56%. The gap comes from the retriever surfacing the wrong company, year or line item. Typical wrong answers are a plausible figure from the wrong year (Apple FY2024 total assets answered with $352,583 million, which is the FY2023 figure).
- **Citations are the weakest part.** Even with the gold chunks, the model cited a gold chunk on 88% of questions; with retrieved chunks, 48%. 5 of its 36 correct answers cited nothing, and some cited malformed ids (for example `[JPM-FY2024#177556]`), which are counted as not cited.
- **Retrieval is uneven by metric.** For fixed + dense, Recall@10 was 6/6 for R&D and 8/8 for operating income, but only 5/10 for total assets (the balance-sheet chunk is easy to confuse with the many other tables that carry assets).

## How the gold set is built

Every 10-K carries machine-readable XBRL facts. The SEC publishes them per company at `data.sec.gov/api/xbrl/companyfacts/CIK##########.json`. That is a free source of exact answers:

1. For each filing, pick the fact for the filing's own fiscal period (revenue, net income, total assets, R&D expense, operating cash flow, operating income, stockholders' equity). Facts are matched on the accession number and period end. The `fy` field in companyfacts is the filing's fiscal year, not the period's, and comparatives from later filings are repeated, so matching on `fy` gives wrong answers.
2. Generate the question ("What was Microsoft's net income for fiscal year 2025?"), keeping the raw value (`101832000000`).
3. Find gold chunks. XBRL says `391035000000`, the filing says `391,035` under an "(In millions)" caption, and the MD&A says "$391.0 billion". `numfmt.filing_forms` renders the value in each form a filing would print, and a boundary-aware regex searches the chunks (so `391,035` does not match inside `1,391,035`). Chunks of the same company that contain the number are gold. Gold is built separately for each chunking strategy, and only questions with a gold chunk under every strategy are kept (all 64 of 64 qualified).
4. Score answers by numeric match: "$391,035 million", "$391.0 billion" and "391035000000" all match 391035000000 within 0.1% relative tolerance. That rejects a transposed-digit near miss (13,137 for 13,107). Bare numbers are read as millions or dollars; years are ignored.

Gold is deliberately lenient in one way: any of the company's ingested filings counts, because the FY2025 figure legitimately appears as a comparative in the FY2026 10-K. So a chunk from the neighbouring year can be a gold chunk.

Per-question data is in [docs/goldset.json](docs/goldset.json).

### Qualitative questions (not scored)

[docs/qualitative.md](docs/qualitative.md) has ten hand-written questions (risk factors, segment commentary, cybersecurity governance) with the answers, citations and retrieved pages. They are **not scored**. There is no gold answer, so they only show behaviour. Reading them: some answers are grounded and readable (Microsoft cybersecurity governance, Coca-Cola health and wellness), some are shallow (NVIDIA export controls, one sentence and no citation), and one is off target (the Apple Services question retrieved a revenue-recognition note rather than segment commentary).

## Design

- `filingqa.edgar`: EDGAR client. Descriptive User-Agent from `SEC_USER_AGENT` (fails clearly if missing), at most about 6.5 requests per second, raw downloads cached in `data/raw/`.
- `filingqa.parse`: HTML to pages, table rows and Item sections. Pages are the filing's `page-break-after` breaks; citations show the printed page number where one is detected. Handles table-of-contents entries, running page headers, NVIDIA's statements under Item 15, and JPMorgan's annual-report layout (mapped from running headers to Items 7 and 8).
- `filingqa.chunking`: `fixed` (220-word windows, 40 overlap) and `section` (whole lines packed up to 220 words, never crossing an Item). Both prepend a company / form / fiscal-year header to the indexed text.
- `filingqa.retrieval`: BM25 (`rank_bm25`), dense (Ollama `nomic-embed-text`, vectors in numpy, embedding cache in SQLite) and hybrid via reciprocal rank fusion (k=60).
- `filingqa.generate`, `filingqa.answer`: Ollama `llama3.2` by default, Anthropic `claude-haiku-4-5-20251001` optional. The prompt restricts answers to the excerpts, requires chunk-id citations, and prescribes the reply "not found in the filings".
- `filingqa.evaluate`: the harness.

## Quickstart

```bash
uv sync --extra anthropic --group dev    # drop --extra anthropic if you only use Ollama
export SEC_USER_AGENT="your-project you@example.com"   # required by SEC, use your own contact
ollama pull nomic-embed-text && ollama pull llama3.2

uv run filingqa ingest                                  # AAPL MSFT NVDA JPM KO, latest 2 years
uv run filingqa index --chunking all --retriever all    # about 9 minutes for embeddings
uv run filingqa ask "What was NVIDIA's R&D expense for fiscal year 2025?" \
    --chunking fixed --retriever dense
uv run filingqa eval --e2e --e2e-config fixed+dense     # writes docs/results.*
```

`filingqa eval` without `--e2e` runs the retrieval metrics only (under a minute). For Anthropic, set `ANTHROPIC_API_KEY` and pass `--backend anthropic`.

Tests run offline in well under a second: `uv run pytest`. Tests that need the network or Ollama are marked `network` / `ollama` and skipped by default (`uv run pytest -m "network or ollama"`). CI runs ruff and the offline tests.

Reference run on an Apple-silicon laptop that was also heavily loaded: ingest and parse under a minute, embedding both chunkings about 8.5 minutes, retrieval eval 25 seconds, end to end (128 generations plus 10 qualitative) about 16 minutes.

## Limitations

- The gold questions are numeric only, and are all "find this one figure" questions. They say nothing about how well the system handles narrative questions.
- n=64, from 5 companies. Confidence intervals are wide; treat differences of under about 15 points as unproven.
- Tables are hard. Rows are flattened to text, so a chunk that starts mid-table loses its column headers and units, and the model can pick the wrong year's column.
- llama3.2 (3B) is small. It picks wrong-year figures, sometimes drops or malforms citation ids, and gives thin answers to qualitative questions. Results with a larger model will differ, and I did not run the Anthropic backend.
- End to end was measured for one retrieval configuration.
- Retrieval never filters by company or fiscal year, even though every question names both. A query-side entity filter is the obvious next experiment and would probably lift every row.
- "Fiscal year" is the calendar year of the period end, which matches how these five companies label theirs.
- Page numbers are the printed folio when detected, otherwise the index of the page break, so they can be off by a page or two.
- Scoring accepts a correct number anywhere in the answer, so an answer that lists several figures could match by luck.
- The numeric tolerance was tightened from 0.5% to 0.1% after I saw a near-miss counted correct. I rescored the stored answers rather than rerunning the generator.

## License

MIT, Emilio Gappa, 2026.
