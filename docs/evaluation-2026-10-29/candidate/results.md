Scoring: `signed-usd-v2`. Evidence: `candidate` (`company-number-candidates-v1`).

Candidate labels match company and number only. They are not claim-level verified citations.

Questions: 64 generated; 0 explicitly annotated; 64 selected; 0 excluded.

### Retrieval (64 questions, any-heuristic candidate recall)

| Chunking | Retriever | Recall@1 | Recall@5 | Recall@10 | Recall@20 | MRR |
|---|---|---|---|---|---|---|
| fixed | bm25 | 17% | 28% | 33% | 41% | 0.229 |
| fixed | dense | 23% | 64% | 81% | 86% | 0.406 |
| fixed | hybrid | 33% | 55% | 70% | 84% | 0.449 |
| section | bm25 | 6% | 19% | 33% | 45% | 0.141 |
| section | dense | 33% | 50% | 69% | 84% | 0.426 |
| section | hybrid | 30% | 53% | 59% | 72% | 0.403 |

95% Wilson intervals for Recall@5, per configuration:

- fixed + bm25: 28% (19% to 40%)
- fixed + dense: 64% (52% to 75%)
- fixed + hybrid: 55% (43% to 66%)
- section + bm25: 19% (11% to 30%)
- section + dense: 50% (38% to 62%)
- section + hybrid: 53% (41% to 65%)

### End to end (top-6 seeds plus adjacent source evidence)

| Configuration | Generator | n | Answer accuracy (95% CI) | Correct and cited a heuristic candidate | Cited any heuristic candidate | Abstained | s/question |
|---|---|---|---|---|---|---|---|
| fixed + dense | source-grounded-usd-v4; fallback=ollama:llama3.2 | 64 | 67% (55% to 77%) | 55% | 58% | 6% | 4.6 |
| oracle (fixed) | source-grounded-usd-v4; fallback=ollama:llama3.2 | 64 | 98% (92% to 100%) | 98% | 98% | 0% | 0.8 |

Answer-method counts and actual model calls (source extraction is not model generation):

- fixed + dense: {'model-fallback': 46, 'source-extracted': 18}; model calls=46.
- oracle (fixed): {'source-extracted': 56, 'model-fallback': 8}; model calls=8.

Source-extracted citations and quotes cover entire contiguous context groups. An any-label hit is not citation precision; in oracle runs it may follow from the supplied seed labels being included in the cited group. Aggregate citation columns combine these group citations with model-selected citations. The per-method counts below keep those measurements separate.

| Configuration | Answer method | n | Cited any heuristic candidate (count/rate) | Correct and cited a heuristic candidate (count/rate) | Actual model calls |
|---|---|---|---|---|---|
| fixed + dense | model-fallback | 46 | 19/46 (41%) | 17/46 (37%) | 46 |
| fixed + dense | source-extracted | 18 | 18/18 (100%) | 18/18 (100%) | 0 |
| oracle (fixed) | model-fallback | 8 | 7/8 (88%) | 7/8 (88%) | 8 |
| oracle (fixed) | source-extracted | 56 | 56/56 (100%) | 56/56 (100%) | 0 |
