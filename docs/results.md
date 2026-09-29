### Retrieval (64 questions, any-gold-chunk recall)

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

### End to end (top-6 chunks to the generator)

| Configuration | Generator | n | Answer accuracy (95% CI) | Correct and cited a gold chunk | Cited any gold chunk | Abstained | s/question |
|---|---|---|---|---|---|---|---|
| fixed + dense | ollama:llama3.2 | 64 | 56% (44% to 68%) | 44% | 48% | 8% | 6.9 |
| oracle (fixed) | ollama:llama3.2 | 64 | 92% (83% to 97%) | 81% | 88% | 0% | 6.2 |
