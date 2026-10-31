# Source-grounded development evaluation, 2026-10-29

**Historical v4 measurement.** This snapshot could incorrectly certify some unsupported
entity, table, currency and period layouts. It is superseded by the
[latest evaluation](../evaluation-2026-10-31/README.md). These counts and source hashes
apply only to v4, and do not describe the current implementation.

Fresh execution on the same cached ten real SEC filings, 64 numeric questions, expected
values and indexes. The scorer is unchanged (`signed-usd-v2`). The answer pipeline is now
`source-grounded-usd-v4`: company-filtered retrieval, adjacent source context,
finite source extraction and an explicitly unverified Ollama fallback for unsupported layouts.
Neighbours may supply values as well as headings. Every model prompt contains at most six chunks.

| Evidence/cohort | Retrieved numeric correct | Oracle numeric correct | Source-extracted answers (retrieved/oracle) | Actual LLM calls (retrieved/oracle) |
|---|---:|---:|---:|---:|
| Candidate labels, all 64 | 43/64 (67%) | 63/64 (98%) | 18 / 56 | 46 / 8 |
| Reviewed labels, selected 20 | 17/20 (85%) | 20/20 (100%) | 4 / 11 | 16 / 9 |

Across both cohorts the system produced 168 new pipeline answers: 89
source-extracted, 79 actual model calls, and 0 source abstentions.
These totals **are not 168 new LLM generations**. Model-generated abstentions are
included in the actual model-call count; details preserve them individually.

The full 64-question pure-model run on 2026-10-28 scored 32/64 retrieved and 53/64 oracle.
The older saved answers under the same strict scorer score 33/64 and 56/64; those were
the frozen release floors. All four recorded correctness losses (KO FY2024 cash flow,
AAPL FY2024 operating income, JPM FY2025 equity and MSFT FY2026 equity) are corrected.
Both negative JPM cash-flow answers in the reviewed oracle are now signed correctly.
All six raw retrieval configurations reproduce their old metrics; the new numeric
answering policy changes company selection and adds source neighbours after retrieval.

## Remaining full-oracle errors

- `KO-FY2025:equity`: `$32,169 [KO-FY2025#0268]`; method `model-fallback`, expected USD 32,169,000,000.

Every retrieved-context miss, abstention, answer, citation and source quote is retained
in the per-question JSON. Unsupported layouts can still produce wrong years, scales or
signs through unverified model fallback. This is a finite source-extraction contract,
not general financial entailment or a claim that arbitrary fallbacks are safe unchecked.

## Interpretation

These are **development measurements**, not a held-out experiment. The implementation
used the old failures and source layouts during development. The 20 reviewed labels
were authored and cross-checked by agents against original SEC HTML before the earlier
run; they are not human-audited and are not an exhaustive list of supporting chunks.
Their label-hit rates therefore are not citation precision. Neither the selected
20-question cohort nor its oracle score should be compared to all 64 as the same test.

The pipeline changed, so these counts do not establish that the underlying model became
better. Results are from one final run with wide intervals (see generated reports);
latency was measured on a shared machine with overlapping runs and is not a controlled
benchmark. Source quotes collectively identify supplied contexts; they do not measure
citation minimality or prove every cited chunk independently contains the entire fact.
The generated reports and JSON separate citation counts/rates for source-extracted and
model answers. Oracle source-group label hits may follow from supplied seed labels being
included, so the aggregate citation figures must not be read as citation precision.

## Files

- [Full-cohort report](candidate/results.md), [all answers](candidate/results.json), [chart](candidate/results.png).
- [Reviewed-cohort report](reviewed/results.md), [all answers](reviewed/results.json), [chart](reviewed/results.png).
- [Frozen reviewed evidence](reviewed-evidence.json), [provenance](provenance.json), [validation](validation.json).

The historical `docs/results.*` artifacts remain byte-identical. Original raw SEC files,
parsed corpus and indexes remain cached locally; accessions, source URLs and SHA-256
hashes identify them in provenance. Large raw filings and model weights are not duplicated.

## Reproduction

Reproducing these historical v4 figures requires the exact v4 source snapshot identified
by the hashes in [provenance](provenance.json). That intermediate source snapshot is not
included in this repository. The commands below run the currently checked-out pipeline;
running them on current code does not reproduce the published v4 measurements.

To evaluate the current pipeline using the pinned corpus/index artifacts and the same
model digest from provenance:

```bash
uv run filingqa eval --chunking all --retriever all --e2e --e2e-config fixed+dense \
  --no-qualitative --output-dir data/runs/source-grounded-candidate
uv run filingqa eval --chunking all --retriever all --e2e --e2e-config fixed+dense \
  --no-qualitative --reviewed-evidence docs/evaluation-2026-10-29/reviewed-evidence.json \
  --output-dir data/runs/source-grounded-reviewed
```

Always use a separate output directory to preserve published historical measurements.
The source extractor never reads benchmark expected values or reviewed labels at runtime.
Evaluation alone uses those labels to score outputs and construct oracle contexts.
