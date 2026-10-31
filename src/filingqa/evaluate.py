"""The measurement harness.

1. Questions come from XBRL facts (see goldset.py); gold chunks are found per chunking strategy.
2. Retrieval metrics (recall@k, MRR) for every chunking x retriever. No LLM, deterministic.
3. End-to-end: the generator answers from the retrieved chunks; we score numeric accuracy
   and citation correctness. An "oracle" row feeds the generator gold chunks directly, which
   separates "retrieval missed it" from "the model could not read it".
4. Hand-written qualitative questions are run and shown, never scored.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from . import config
from .answer import Answer, answer_from_chunks, expand_context, select_context
from .chunking import Chunk
from .corpus import load_manifest
from .evidence import CANDIDATE_VERSION, SCORING_VERSION, load_reviewed_evidence
from .generate import make_generator
from .goldset import Question, build_questions, gold_chunk_ids
from .grounding import VERSION as ANSWERING_VERSION
from .index import Index, load_index
from .metrics import citation_correct, mean, recall_at_k, reciprocal_rank, wilson_interval
from .numfmt import numeric_match
from .qualitative import QUALITATIVE_QUESTIONS

KS = (1, 5, 10, 20)
DEPTH = 100  # retrieval depth used for MRR
E2E_K = 6  # chunks shown to the generator


class EvaluationError(ValueError):
    """Expected input/selection failure that the CLI can report without a traceback."""


@dataclass
class RetrievalRow:
    chunking: str
    retriever: str
    n: int
    recall: dict[int, float]
    recall_ci: dict[int, tuple[float, float]]
    mrr: float
    ranks: dict[str, int | None] = field(default_factory=dict)  # question id -> first gold rank


@dataclass
class E2ERow:
    label: str
    generator: str
    n: int
    accuracy: float
    accuracy_ci: tuple[float, float]
    citation: float  # share of all questions answered correctly AND citing a gold chunk
    cited_gold: float  # share of questions where any cited chunk is gold
    abstained: float
    seconds_per_question: float
    methods: dict[str, int] = field(default_factory=dict)
    model_calls: int = 0
    citation_by_method: dict[str, dict[str, int | float]] = field(default_factory=dict)


def fresh_output_dir() -> Path:
    """Choose a new run path without creating it or touching historical reports."""
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S.%fZ")
    return config.DATA_DIR / "runs" / f"{timestamp}-{uuid4().hex[:8]}"


def load_facts(tickers: set[str]) -> dict[str, dict]:
    out = {}
    for t in tickers:
        path = config.RAW_DIR / f"companyfacts_{t}.json"
        if not path.exists():
            raise SystemExit(f"Missing {path}. Run `filingqa ingest` first.")
        out[t] = json.loads(path.read_text())
    return out


def first_gold_rank(ranked: list[str], gold: set[str]) -> int | None:
    return next((i for i, cid in enumerate(ranked, 1) if cid in gold), None)


def eval_retrieval(
    index: Index, retriever_name: str, questions: list[Question], gold: dict[str, set[str]]
) -> RetrievalRow:
    retriever = index.retriever(retriever_name)
    per_k: dict[int, list[float]] = {k: [] for k in KS}
    rr, ranks = [], {}
    for q in questions:
        ranked = [cid for cid, _ in retriever.search(q.question, DEPTH)]
        g = gold[q.id]
        for k in KS:
            per_k[k].append(recall_at_k(ranked, g, k))
        rr.append(reciprocal_rank(ranked, g))
        ranks[q.id] = first_gold_rank(ranked, g)
    n = len(questions)
    return RetrievalRow(
        index.chunking, retriever_name, n,
        {k: mean(v) for k, v in per_k.items()},
        {k: wilson_interval(sum(v), n) for k, v in per_k.items()},
        mean(rr), ranks,
    )  # fmt: skip


def _score(q: Question, ans: Answer, gold: set[str]) -> dict:
    correct = numeric_match(ans.text, q.value) and not ans.not_found
    return {
        "id": q.id, "question": q.question, "expected_usd": q.value, "answer": ans.text,
        "cited": ans.cited, "correct": correct, "abstained": ans.not_found,
        "cited_gold": citation_correct(ans.cited, gold),
        "cited_gold_and_correct": correct and citation_correct(ans.cited, gold),
        "answer_method": ans.method, "source_evidence": ans.evidence,
        "grounding_note": ans.grounding_note,
    }  # fmt: skip


def _summarise(label: str, gen_name: str, rows: list[dict], seconds: float) -> E2ERow:
    n = len(rows)
    if not n:
        raise EvaluationError("cannot summarise an empty evaluation")
    ok = sum(r["correct"] for r in rows)
    methods = {}
    citation_by_method = {}
    for r in rows:
        method = r.get("answer_method", "model")
        methods[method] = methods.get(method, 0) + 1
        counts = citation_by_method.setdefault(
            method, {"n": 0, "cited_label": 0, "correct_and_cited_label": 0, "model_calls": 0}
        )
        counts["n"] += 1
        counts["cited_label"] += int(r["cited_gold"])
        counts["correct_and_cited_label"] += int(r["cited_gold_and_correct"])
        counts["model_calls"] += int(method in {"model", "model-fallback"})
    for counts in citation_by_method.values():
        counts["cited_label_rate"] = counts["cited_label"] / counts["n"]
        counts["correct_and_cited_label_rate"] = counts["correct_and_cited_label"] / counts["n"]
    model_calls = sum(
        count for method, count in methods.items() if method in {"model", "model-fallback"}
    )
    label_name = (
        gen_name
        if not any(m.startswith("source-") for m in methods)
        else f"{ANSWERING_VERSION}; fallback={gen_name}"
    )
    return E2ERow(
        label, label_name, n, ok / n, wilson_interval(ok, n),
        sum(r["cited_gold_and_correct"] for r in rows) / n,
        sum(r["cited_gold"] for r in rows) / n,
        sum(r["abstained"] for r in rows) / n,
        seconds / n, methods, model_calls, citation_by_method,
    )  # fmt: skip


def eval_e2e(
    index: Index, retriever_name: str, questions: list[Question], gold: dict[str, set[str]],
    backend: str, oracle: bool, log=print,
) -> tuple[E2ERow, list[dict]]:  # fmt: skip
    gen = make_generator(backend)
    retriever = None if oracle else index.retriever(retriever_name)
    rows, start = [], time.time()
    for i, q in enumerate(questions, 1):
        if oracle:
            # Gold chunks from the question's own filing first, then comparatives elsewhere.
            ids = sorted(
                gold[q.id], key=lambda c: (not c.startswith(f"{q.ticker}-FY{q.fiscal_year}"), c)
            )
            chunks: list[Chunk] = expand_context(index, [index.by_id[c] for c in ids[:E2E_K]])
        else:
            chunks = select_context(q.question, index, retriever, E2E_K)
        ans = answer_from_chunks(q.question, chunks, gen)
        rows.append(_score(q, ans, gold[q.id]))
        log(f"  [{i}/{len(questions)}] {q.id}: {'ok' if rows[-1]['correct'] else 'miss'}")
    label = f"oracle ({index.chunking})" if oracle else f"{index.chunking} + {retriever_name}"
    return _summarise(label, gen.name, rows, time.time() - start), rows


def run_qualitative(index: Index, retriever_name: str, backend: str, log=print) -> list[dict]:
    gen, retriever, out = make_generator(backend), index.retriever(retriever_name), []
    for q in QUALITATIVE_QUESTIONS:
        log(f"  qualitative: {q}")
        chunks = [index.by_id[c] for c, _ in retriever.search(q, E2E_K)]
        ans = answer_from_chunks(q, chunks, gen)
        out.append({
            "question": q, "answer": ans.text,
            "cited": [index.by_id[c].citation + f" [{c}]" for c in ans.cited],
            "retrieved": [index.by_id[c.id].citation for c in chunks],
        })  # fmt: skip
    return out


def _pct(x: float) -> str:
    return f"{100 * x:.0f}%"


def render_markdown(
    retrieval: list[RetrievalRow],
    e2e: list[E2ERow],
    n_questions: int,
    qualitative: list[dict],
    metadata: dict | None = None,
) -> str:
    metadata = metadata or {
        "scoring_version": SCORING_VERSION,
        "evidence_mode": "candidate",
        "evidence_version": CANDIDATE_VERSION,
    }
    label = "reviewed label" if metadata["evidence_mode"] == "reviewed" else "heuristic candidate"
    lines = [
        f"Scoring: `{metadata['scoring_version']}`. Evidence: `{metadata['evidence_mode']}` "
        f"(`{metadata['evidence_version']}`).",
        "",
        "Reviewed quotes rely on the annotation author's assessment of metric, period, sign and unit; "
        "the loader verifies identity and exact quote grounding."
        if label == "reviewed label"
        else "Candidate labels match company and number only. They are not claim-level verified citations.",
        "",
    ]
    if "selected_questions" in metadata:
        lines += [
            f"Questions: {metadata['generated_questions']} generated; "
            f"{metadata.get('annotated_questions', 0)} explicitly annotated; "
            f"{metadata['selected_questions']} selected; {metadata['excluded_questions']} excluded.",
            "",
        ]
    lines += [f"### Retrieval ({n_questions} questions, any-{label} recall)", ""]
    lines += [
        "| Chunking | Retriever | Recall@1 | Recall@5 | Recall@10 | Recall@20 | MRR |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in retrieval:
        cells = " | ".join(_pct(r.recall[k]) for k in KS)
        lines.append(f"| {r.chunking} | {r.retriever} | {cells} | {r.mrr:.3f} |")
    lines += ["", "95% Wilson intervals for Recall@5, per configuration:", ""]
    for r in retrieval:
        lo, hi = r.recall_ci[5]
        lines.append(
            f"- {r.chunking} + {r.retriever}: {_pct(r.recall[5])} ({_pct(lo)} to {_pct(hi)})"
        )
    if e2e:
        lines += ["", f"### End to end (top-{E2E_K} seeds plus adjacent source evidence)", ""]
        lines += [
            f"| Configuration | Generator | n | Answer accuracy (95% CI) | Correct and cited a {label} "
            f"| Cited any {label} | Abstained | s/question |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for e in e2e:
            lo, hi = e.accuracy_ci
            lines.append(
                f"| {e.label} | {e.generator} | {e.n} | {_pct(e.accuracy)} ({_pct(lo)} to {_pct(hi)}) "
                f"| {_pct(e.citation)} | {_pct(e.cited_gold)} | {_pct(e.abstained)} "
                f"| {e.seconds_per_question:.1f} |"
            )
        lines += [
            "",
            "Answer-method counts and actual model calls (source extraction is not model generation):",
            "",
        ]
        for e in e2e:
            lines.append(f"- {e.label}: {e.methods}; model calls={e.model_calls}.")
        lines += [
            "",
            "Source-extracted citations and quotes cover entire contiguous context groups. "
            "An any-label hit is not citation precision; in oracle runs it may follow from "
            "the supplied seed labels being included in the cited group. Aggregate citation "
            "columns combine these group citations with model-selected citations. "
            "The per-method counts below keep those measurements separate.",
            "",
        ]
        if any(e.citation_by_method for e in e2e):
            lines += [
                f"| Configuration | Answer method | n | Cited any {label} (count/rate) "
                f"| Correct and cited a {label} (count/rate) | Actual model calls |",
                "|---|---|---|---|---|---|",
            ]
            for e in e2e:
                for method, counts in sorted(e.citation_by_method.items()):
                    count = counts["n"]
                    lines.append(
                        f"| {e.label} | {method} | {count} "
                        f"| {counts['cited_label']}/{count} ({_pct(counts['cited_label_rate'])}) "
                        f"| {counts['correct_and_cited_label']}/{count} "
                        f"({_pct(counts['correct_and_cited_label_rate'])}) "
                        f"| {counts['model_calls']} |"
                    )
    return "\n".join(lines) + "\n"


def render_qualitative(items: list[dict], label: str) -> str:
    out = [
        f"# Qualitative questions ({label})",
        "",
        "Hand-written, run through the pipeline, and shown as-is. **Not scored**: there is no "
        "gold answer, so read them as examples of behaviour, not as a metric.",
        "",
    ]
    for i, it in enumerate(items, 1):
        out += [f"## {i}. {it['question']}", "", it["answer"], ""]
        out += ["Cited: " + ("; ".join(it["cited"]) or "none"), ""]
        out += ["Retrieved: " + "; ".join(it["retrieved"]), ""]
    return "\n".join(out)


def plot(
    retrieval: list[RetrievalRow], e2e: list[E2ERow], path: Path, metadata: dict | None = None
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors = {1: "#9ecae1", 5: "#4292c6", 10: "#08519c"}
    two = bool(e2e)
    fig, axes = plt.subplots(1, 2 if two else 1, figsize=(13 if two else 8, 4.6), squeeze=False)
    ax = axes[0][0]
    labels = [f"{r.chunking}\n{r.retriever}" for r in retrieval]
    width = 0.26
    for j, k in enumerate((1, 5, 10)):
        xs = [i + (j - 1) * width for i in range(len(retrieval))]
        vals = [r.recall[k] for r in retrieval]
        err = [
            [v - r.recall_ci[k][0] for v, r in zip(vals, retrieval, strict=True)],
            [r.recall_ci[k][1] - v for v, r in zip(vals, retrieval, strict=True)],
        ]
        ax.bar(xs, vals, width, yerr=err, color=colors[k], label=f"Recall@{k}", capsize=2,
               error_kw={"elinewidth": 0.8, "ecolor": "#444"})  # fmt: skip
    ax.plot(range(len(retrieval)), [r.mrr for r in retrieval], "D", color="#e6550d", label="MRR")
    ax.set_xticks(range(len(retrieval)), labels, fontsize=8)
    ax.set_ylim(0, 1.05)
    ax.set_title(f"Retrieval, n={retrieval[0].n} XBRL-derived questions", fontsize=10)
    ax.legend(fontsize=8, frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    if two:
        ax2 = axes[0][1]
        xs = range(len(e2e))
        for j, (attr, name, col) in enumerate(
            [("accuracy", "Answer accuracy", "#31a354"), ("cited_gold", "Cited an evidence label", "#756bb1"),
             ("abstained", "Said not found", "#bdbdbd")]
        ):  # fmt: skip
            ax2.bar([x + (j - 1) * width for x in xs], [getattr(e, attr) for e in e2e], width,
                    color=col, label=name)  # fmt: skip
        ax2.set_xticks(list(xs), [e.label.replace(" + ", "\n") for e in e2e], fontsize=8)
        ax2.set_ylim(0, 1.05)
        ax2.set_title(f"End to end, {e2e[0].generator}", fontsize=10)
        ax2.legend(fontsize=8, frameon=False)
        ax2.spines[["top", "right"]].set_visible(False)
    if metadata:
        fig.suptitle(
            f"{metadata['scoring_version']} / {metadata['evidence_mode']} evidence", fontsize=9
        )
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160)
    plt.close(fig)


def run_eval(
    chunkings: list[str], retrievers: list[str], e2e: bool, e2e_config: tuple[str, str],
    e2e_limit: int | None, backend: str, qualitative: bool, docs: Path | None = None,
    reviewed_evidence: Path | None = None,
) -> None:  # fmt: skip
    if not chunkings or not retrievers:
        raise EvaluationError("at least one chunking and retriever are required")
    if e2e_limit is not None and (type(e2e_limit) is not int or e2e_limit <= 0):
        raise EvaluationError("e2e_limit must be a positive integer")
    if e2e and (
        not isinstance(e2e_config, (tuple, list))
        or len(e2e_config) != 2
        or e2e_config[0] not in config.CHUNKINGS
        or e2e_config[1] not in config.RETRIEVERS
    ):
        raise EvaluationError(
            "e2e_config must be CHUNKING+RETRIEVER with chunking in "
            f"{', '.join(config.CHUNKINGS)} and retriever in {', '.join(config.RETRIEVERS)}"
        )
    filings = load_manifest()
    questions = build_questions(filings, load_facts({f.ticker for f in filings}))
    names = list(dict.fromkeys([*chunkings, *([e2e_config[0]] if e2e else [])]))
    indexes = {c: load_index(c) for c in names}
    if reviewed_evidence is not None:
        keep, gold, metadata = load_reviewed_evidence(
            Path(reviewed_evidence),
            questions,
            {c: idx.chunks for c, idx in indexes.items()},
        )
    else:
        gold = {
            c: {q.id: set(gold_chunk_ids(q, idx.chunks)) for q in questions}
            for c, idx in indexes.items()
        }
        # Every evaluated index needs candidates, including a separately selected
        # end-to-end index. The usual all-chunkings cohort remains unchanged.
        keep = [q for q in questions if all(gold[c][q.id] for c in names)]
        metadata = {
            "scoring_version": SCORING_VERSION,
            "evidence_mode": "candidate",
            "evidence_version": CANDIDATE_VERSION,
            "generated_questions": len(questions),
            "annotated_questions": 0,
            "selected_questions": len(keep),
            "excluded_questions": len(questions) - len(keep),
            "semantic_support": "not checked; same-company number-match candidates only",
        }
    if not keep:
        raise EvaluationError("no questions selected for evaluation")
    metadata.update(
        {
            "answering_version": ANSWERING_VERSION,
            "answer_policy": "company-filtered top-100 pool; top-6 seeds plus same-Item neighbours; source extraction then explicit model fallback",
            "source_citation_policy": "entire contiguous source-context groups, including seed labels and neighbours; not minimal supporting chunks",
            "citation_metric_limitations": "any-label hit is not citation precision; oracle source-group hits may follow from supplied seed labels; see citation_by_method for separated counts",
        }
    )
    print(
        f"{len(questions)} generated, {metadata['annotated_questions']} annotated, "
        f"{len(keep)} selected, {metadata['excluded_questions']} excluded; "
        f"evidence={metadata['evidence_mode']}"
    )

    retrieval = []
    for c in chunkings:
        for r in retrievers:
            print(f"retrieval: {c} + {r}")
            retrieval.append(eval_retrieval(indexes[c], r, keep, gold[c]))

    e2e_rows: list[E2ERow] = []
    details: dict[str, list[dict]] = {}
    qual: list[dict] = []
    if e2e:
        ec, er = e2e_config
        qs = keep[:: max(1, len(keep) // e2e_limit)][:e2e_limit] if e2e_limit else keep
        print(f"end to end: {ec} + {er}, {len(qs)} questions, backend={backend}")
        for oracle in (False, True):
            row, rows = eval_e2e(indexes[ec], er, qs, gold[ec], backend, oracle)
            e2e_rows.append(row)
            details[row.label] = rows
        if qualitative:
            qual = run_qualitative(indexes[ec], er, backend)

    metadata["e2e_questions"] = e2e_rows[0].n if e2e_rows else 0
    docs = Path(docs) if docs is not None else fresh_output_dir()
    docs.mkdir(parents=True, exist_ok=True)
    md = render_markdown(retrieval, e2e_rows, len(keep), qual, metadata)
    (docs / "results.md").write_text(md)
    plot(retrieval, e2e_rows, docs / "results.png", metadata)
    (docs / "results.json").write_text(json.dumps(
        {"evaluation": metadata, "n_questions": len(keep), "retrieval": [asdict(r) for r in retrieval],
         "e2e": [asdict(e) for e in e2e_rows], "e2e_details": details},
        indent=1))  # fmt: skip
    if qual:
        (docs / "qualitative.md").write_text(
            render_qualitative(qual, f"{e2e_config[0]} + {e2e_config[1]}, {backend}")
        )
    (docs / "goldset.json").write_text(json.dumps([q.to_dict() for q in keep], indent=1))
    print(md)
