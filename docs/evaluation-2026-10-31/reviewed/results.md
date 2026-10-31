Scoring: `signed-usd-v2`. Evidence: `reviewed` (`reviewed-quotes-v1`).

Reviewed quotes rely on the annotation author's assessment of metric, period, sign and unit; the loader verifies identity and exact quote grounding.

Questions: 64 generated; 20 explicitly annotated; 20 selected; 44 excluded.

### Retrieval (20 questions, any-reviewed label recall)

| Chunking | Retriever | Recall@1 | Recall@5 | Recall@10 | Recall@20 | MRR |
|---|---|---|---|---|---|---|
| fixed | bm25 | 15% | 15% | 25% | 25% | 0.166 |
| fixed | dense | 15% | 40% | 60% | 70% | 0.271 |
| fixed | hybrid | 20% | 35% | 35% | 40% | 0.278 |
| section | bm25 | 10% | 10% | 20% | 25% | 0.120 |
| section | dense | 0% | 10% | 35% | 80% | 0.092 |
| section | hybrid | 5% | 20% | 25% | 40% | 0.127 |

95% Wilson intervals for Recall@5, per configuration:

- fixed + bm25: 15% (5% to 36%)
- fixed + dense: 40% (22% to 61%)
- fixed + hybrid: 35% (18% to 57%)
- section + bm25: 10% (3% to 30%)
- section + dense: 10% (3% to 30%)
- section + hybrid: 20% (8% to 42%)

### End to end (top-6 seeds plus adjacent source evidence)

| Configuration | Generator | n | Answer accuracy (95% CI) | Correct and cited a reviewed label | Cited any reviewed label | Abstained | s/question |
|---|---|---|---|---|---|---|---|
| fixed + dense | source-grounded-usd-v11; fallback=ollama:llama3.2 | 20 | 80% (58% to 92%) | 30% | 30% | 0% | 13.0 |
| oracle (fixed) | source-grounded-usd-v11; fallback=ollama:llama3.2 | 20 | 100% (84% to 100%) | 100% | 100% | 0% | 3.4 |

Answer-method counts and actual model calls (source extraction is not model generation):

- fixed + dense: {'model-fallback': 17, 'source-extracted': 3}; model calls=17.
- oracle (fixed): {'model-fallback': 14, 'source-extracted': 6}; model calls=14.

Source-extracted citations and quotes cover entire contiguous context groups. An any-label hit is not citation precision; in oracle runs it may follow from the supplied seed labels being included in the cited group. Aggregate citation columns combine these group citations with model-selected citations. The per-method counts below keep those measurements separate.

| Configuration | Answer method | n | Cited any reviewed label (count/rate) | Correct and cited a reviewed label (count/rate) | Actual model calls |
|---|---|---|---|---|---|
| fixed + dense | model-fallback | 17 | 3/17 (18%) | 3/17 (18%) | 17 |
| fixed + dense | source-extracted | 3 | 3/3 (100%) | 3/3 (100%) | 0 |
| oracle (fixed) | model-fallback | 14 | 14/14 (100%) | 14/14 (100%) | 14 |
| oracle (fixed) | source-extracted | 6 | 6/6 (100%) | 6/6 (100%) | 0 |
