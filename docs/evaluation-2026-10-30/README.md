# Source-grounded development evaluation, 2026-10-30

**Historical v10 measurement.** These counts and source hashes apply only to
`source-grounded-usd-v10`. Later review found that a weak operating-expenses title could
lose an earlier component declaration across an intervening table. This report is
superseded by the [latest evaluation](../evaluation-2026-10-31/README.md) and does not
describe the current implementation.

Fresh execution on the same cached ten real SEC filings, 64 numeric questions, expected
values and indexes. The scorer is unchanged (`signed-usd-v2`). The answer pipeline is now
`source-grounded-usd-v10`: company-filtered retrieval, adjacent source context,
finite source extraction and an explicitly unverified Ollama fallback for unsupported layouts.
Neighbours may supply values as well as headings. Every model prompt contains at most six chunks.

| Evidence/cohort | Retrieved numeric correct | Oracle numeric correct | Source-extracted answers (retrieved/oracle) | Actual LLM calls (retrieved/oracle) |
|---|---:|---:|---:|---:|
| Candidate labels, all 64 | 38/64 (59%) | 63/64 (98%) | 10 / 35 | 54 / 29 |
| Reviewed labels, selected 20 | 16/20 (80%) | 20/20 (100%) | 3 / 6 | 17 / 14 |

Across both cohorts the system produced 168 new pipeline answers: 54
source-extracted, 114 actual model calls, and 0 source abstentions.
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
in the per-question JSON. A model-fallback label records a routing decision: errors can
come from missing context, extraction-coverage bugs or model mistakes on supported
statements. It does not establish that the financial-statement layout was unsupported.
This finite extractor is not a general financial-entailment engine.

## Interpretation

The earlier v4 implementation scored 43/64 retrieved
and 63/64 oracle, with 89 source
extractions and 79 actual model calls across both cohorts. Subsequent source
contracts exposed unsupported entity, table, currency and period layouts that it could
incorrectly certify. Later snapshots also introduced coverage bugs in supported financial
statements. The new measurement's accuracy, source-answer count and actual model calls
are reported above; they measure the changed pipeline, not a controlled improvement in
the underlying model. Known implementation regressions are attributed separately below.
The [v4 measurement](../evaluation-2026-10-29/README.md) is retained as versioned history.

The intermediate v6 run scored 38/64 retrieved
and 58/64 oracle. Review found both remaining
entity-scope defects and a regression in its table row limits: standard balance-sheet
section headings stopped extraction before valid Apple assets/equity totals. Those
particular v6 fallback errors were caused by the new scan rule, not by ambiguity in the
financial statements. V7 restored closed standard section leads and dash-row continuation,
while carrying entity qualifications across tables.

The v7 run scored 38/64 retrieved and
60/64 oracle. Its Coca-Cola legal-name grammar omitted
`Company`, which blocked canonical consolidated statements, including KO FY2024 equity
and KO FY2025 net income. Microsoft's FY2025 R&D extraction was blocked by market-risk
headings carrying across the explicit Item 7A-to-Item 8 boundary. These were extraction-
coverage bugs in supported statements, rather than unsupported financial layouts.

The v8 host changes addressed those coverage paths together with noncontrolling-
interest and parent-attribution checks on the recorded Coca-Cola layout. Footnoted
cash-flow labels and literal boundary-marker collisions also received regression
controls. The fresh current oracle outcomes for those recorded coverage cases are:

- `KO-FY2024:equity`: current method `source-extracted`, numeric answer correct.
- `KO-FY2025:net_income`: current method `source-extracted`, numeric answer correct.
- `MSFT-FY2025:rd_expense`: current method `source-extracted`, numeric answer correct.

The v8 run scored 38/64 retrieved
and 63/64 oracle, with
54 source answers and 114 actual model calls across both cohorts.
Later review and bounded host probes exposed two scope gaps outside the 64-question
benchmark: R&D component breakdowns could be treated as total company R&D, and a bare
Item 8 statement title could establish company scope inside a parent-only note when the
qualifying heading was outside the selected window. The original JPM cached layout
remained blocked; the confirmed variant required removing two intervening subheads.

V9 narrows those R&D/title scope routes and adds positive and negative controls. Stricter
source selection can change coverage and model-fallback routing; the current counts
above report the actual outcome. Passing the reused benchmark does not establish
exhaustive correctness, and this is not a controlled improvement in the underlying model.
Candidate selection now requires labels for every loaded retrieval/e2e chunking; the
fixed+section/fixed-e2e measurement here retains the same 64 questions. Historical v4
reproduction also requires the matching archived v4 source snapshot, as its page explains.

V9 narrowed those scope routes but its R&D protection still depended on a component
phrase list and could miss declarations in intervening prose or the header label cell.
Its standalone expense-title route also lacked the shared note-prefix veto. The final
v10 changes require a closed positive metadata frame between an accepted R&D title and
the table header, including non-year header cells, and apply the shared note/parent-
prefix veto to the weak expense-title route. A subsequent preflight exposed common
article/condensed/continued forms of the Notes running header that the initial negative
prefix missed. The final prefix recognizes those Notes-to-financial-statements forms;
this is a broader negative header check alongside the closed positive metadata frame,
not a new component-word deny-list. These conservative rules can change coverage and
model routing; the fresh table above records the actual result.

**Focused fix-cycle proof:** 1,982 offline tests passed, 3 deselected; Ruff and diff checks passed. This cycle adds 71 source-scope contracts and 5 candidate-selection tests. 6 earlier host-generated positive inputs gained explicit GLOBEX company anchors while their $800 million, $83 million and $91 million expectations stayed fixed. The original 37 + 42 JSON fixtures remain byte-identical.

The original 39 scope controls were run
against the frozen v8 copy: 20 failed and
19 passed. Another
4 running-header
controls were added after the Microsoft source preflight exposed the coverage gap.
Another 24 scope controls were added
after inspection 8 during the final authorized host-fix round. Then
4 common Notes-header
controls were added: against the frozen initial v10 copy,
4 failed and
67 passed across the complete
71-case scope set. The final
v10 source/proofs and actual runs were regenerated after that correction.
The candidate-selection baseline had 2
failures and 3 passes after an
initial fixture-format mistake was preserved and corrected. These are development
controls. The full 71-case scope set was completed
during implementation; none of these results is a held-out evaluation.

These changes have software and real-source checks; those checks do not constitute
independent approval of the final code. The table above is the fresh current measurement.

These are **development measurements**, not a held-out experiment. The implementation
used the old failures and source layouts during development. The 20 reviewed labels
were authored and cross-checked by agents against original SEC HTML before the earlier
run; they are not human-audited and are not an exhaustive list of supporting chunks.
Their label-hit rates therefore are not citation precision. Neither the selected
20-question cohort nor its oracle score should be compared to all 64 as the same test.

The pipeline changed, so these counts do not establish that the underlying model became
better. Results are from one final run with wide intervals (see generated reports);
latency was measured on a shared machine and is not a controlled
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

Reproducing these historical v10 figures requires the exact v10 source snapshot
identified by the hashes in [provenance](provenance.json). That intermediate source
snapshot is not included in this repository. The commands below run the currently
checked-out pipeline; running them on current code does not reproduce the published
v10 measurements.

With the matching v10 source snapshot, use the pinned corpus/index artifacts and the
same model digest from provenance:

```bash
uv run filingqa eval --chunking all --retriever all --e2e --e2e-config fixed+dense \
  --no-qualitative --output-dir data/runs/source-grounded-candidate
uv run filingqa eval --chunking all --retriever all --e2e --e2e-config fixed+dense \
  --no-qualitative --reviewed-evidence docs/evaluation-2026-10-30/reviewed-evidence.json \
  --output-dir data/runs/source-grounded-reviewed
```

Always use a separate output directory to preserve published historical measurements.
The source extractor never reads benchmark expected values or reviewed labels at runtime.
Evaluation alone uses those labels to score outputs and construct oracle contexts.
