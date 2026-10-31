"""Keep group-citation label hits distinct from model-selected citation measurements."""

import json
from dataclasses import asdict
from types import SimpleNamespace

from filingqa import config, evaluate


def scored(method, correct, cited):
    row = {
        "correct": correct,
        "cited_gold": cited,
        "cited_gold_and_correct": correct and cited,
        "abstained": method == "source-abstained",
    }
    if method is not None:
        row["answer_method"] = method
    return row


def test_mixed_methods_retain_different_citation_counts_and_actual_model_calls():
    rows = [
        scored("source-extracted", True, True),
        scored("source-extracted", True, True),
        scored("model-fallback", True, True),
        scored("model-fallback", False, True),
        scored("model-fallback", True, False),
        scored("source-abstained", False, False),
        scored(None, True, False),
    ]
    summary = evaluate._summarise("fixed + dense", "test-model", rows, 7)
    # Existing aggregate fields retain their original all-answer denominators.
    assert summary.accuracy == 5 / 7
    assert summary.cited_gold == 4 / 7
    assert summary.citation == 3 / 7
    assert summary.model_calls == 4
    assert summary.methods == {
        "source-extracted": 2, "model-fallback": 3, "source-abstained": 1, "model": 1
    }
    methods = asdict(summary)["citation_by_method"]
    assert methods["source-extracted"] == {
        "n": 2, "cited_label": 2, "correct_and_cited_label": 2, "model_calls": 0,
        "cited_label_rate": 1, "correct_and_cited_label_rate": 1,
    }
    assert methods["model-fallback"] == {
        "n": 3, "cited_label": 2, "correct_and_cited_label": 1, "model_calls": 3,
        "cited_label_rate": 2 / 3, "correct_and_cited_label_rate": 1 / 3,
    }
    assert methods["source-abstained"]["cited_label_rate"] == 0
    assert methods["model"]["model_calls"] == 1


def test_markdown_discloses_source_groups_and_separates_the_method_denominators():
    summary = evaluate._summarise(
        "oracle (fixed)", "test-model",
        [scored("source-extracted", True, True),
         scored("model-fallback", True, False), scored("model-fallback", False, True)],
        3,
    )
    report = evaluate.render_markdown([], [summary], 3, [])
    assert "entire contiguous context groups" in report
    assert "not citation precision" in report
    assert "supplied seed labels being included" in report
    assert "| oracle (fixed) | source-extracted | 1 | 1/1 (100%) | 1/1 (100%) | 0 |" in report
    assert "| oracle (fixed) | model-fallback | 2 | 1/2 (50%) | 0/2 (0%) | 2 |" in report


def test_fresh_output_paths_are_unique_and_do_not_create_directories(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    first, second = evaluate.fresh_output_dir(), evaluate.fresh_output_dir()
    assert first.parent == second.parent == tmp_path / "data/runs"
    assert first != second
    assert not first.exists() and not second.exists()


def test_programmatic_default_preserves_historical_reports_and_writes_new_runs(monkeypatch, tmp_path):
    historical = tmp_path / "docs"
    historical.mkdir()
    originals = {}
    for name in ["results.json", "results.md", "results.png", "goldset.json"]:
        originals[name] = ("historical " + name).encode()
        (historical / name).write_bytes(originals[name])
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "DOCS_DIR", historical)
    question = SimpleNamespace(id="GLOBEX-FY2031:net_income", to_dict=lambda: {"id": "synthetic"})
    monkeypatch.setattr(evaluate, "load_manifest", lambda: [SimpleNamespace(ticker="GLOBEX")])
    monkeypatch.setattr(evaluate, "load_facts", lambda _: {})
    monkeypatch.setattr(evaluate, "build_questions", lambda *_: [question])
    monkeypatch.setattr(evaluate, "load_index", lambda _: SimpleNamespace(chunks=[]))
    monkeypatch.setattr(evaluate, "gold_chunk_ids", lambda *_: ["GLOBEX-FY2031#0000"])
    retrieval = evaluate.RetrievalRow(
        "fixed", "bm25", 1, {k: 1 for k in evaluate.KS},
        {k: (0.2, 1) for k in evaluate.KS}, 1,
    )
    monkeypatch.setattr(evaluate, "eval_retrieval", lambda *_: retrieval)
    monkeypatch.setattr(evaluate, "plot", lambda *_, **__: None)
    for _ in range(2):
        evaluate.run_eval(["fixed"], ["bm25"], False, ("fixed", "bm25"), None, "fake", False)
    runs = list((tmp_path / "data/runs").iterdir())
    assert len(runs) == 2
    for run in runs:
        result = json.loads((run / "results.json").read_text())
        metadata = result["evaluation"]
        assert "entire contiguous source-context groups" in metadata["source_citation_policy"]
        assert "not citation precision" in metadata["citation_metric_limitations"]
    assert {name: (historical / name).read_bytes() for name in originals} == originals
    explicit = tmp_path / "chosen-output"
    evaluate.run_eval(["fixed"], ["bm25"], False, ("fixed", "bm25"), None, "fake", False,
                      docs=explicit)
    assert (explicit / "results.json").is_file()
