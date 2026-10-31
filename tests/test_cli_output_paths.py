"""Bare evaluation runs preserve committed historical measurements."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from filingqa import cli, config, evaluate
from filingqa.goldset import Question


@pytest.fixture
def local_evaluation(monkeypatch, tmp_path):
    """Exercise real report writes with one synthetic, retrieval-only question."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    question = Question(
        "ACME-FY2030:net_income", "ACME", 2030, "net_income", "NetIncomeLoss",
        "What was ACME net income for fiscal year 2030?", 45e6, "synthetic-accession",
    )
    monkeypatch.setattr(evaluate, "load_manifest", lambda: [SimpleNamespace(ticker="ACME")])
    monkeypatch.setattr(evaluate, "load_facts", lambda tickers: {})
    monkeypatch.setattr(evaluate, "build_questions", lambda filings, facts: [question])
    monkeypatch.setattr(
        evaluate, "load_index", lambda name: SimpleNamespace(chunking=name, chunks=[])
    )
    monkeypatch.setattr(evaluate, "gold_chunk_ids", lambda q, chunks: ["ACME-FY2030#0001"])
    monkeypatch.setattr(
        evaluate,
        "eval_retrieval",
        lambda idx, retriever, questions, gold: evaluate.RetrievalRow(
            idx.chunking, retriever, 1, {k: 1.0 for k in evaluate.KS},
            {k: (0.2, 1.0) for k in evaluate.KS}, 1.0,
        ),
    )
    monkeypatch.setattr(evaluate, "plot", lambda rows, e2e, path, metadata: path.write_bytes(b"plot"))
    return tmp_path


def test_bare_cli_and_programmatic_evaluations_get_separate_runs(local_evaluation):
    root = local_evaluation
    historical = root / "docs"
    historical.mkdir()
    saved = {name: f"historical {name}".encode() for name in
             ["results.json", "results.md", "results.png", "goldset.json"]}
    for name, content in saved.items():
        (historical / name).write_bytes(content)

    cli.main(["eval"])
    cli.main(["eval"])
    evaluate.run_eval(["section"], ["bm25"], False, ("section", "bm25"), None, "ollama", False)

    runs = sorted((root / "data/runs").iterdir())
    assert len(runs) == 3
    assert all(run.is_dir() for run in runs)
    for run in runs:
        assert {path.name for path in run.iterdir()} == set(saved)
        assert json.loads((run / "results.json").read_text())["n_questions"] == 1
    assert {name: (historical / name).read_bytes() for name in saved} == saved


def test_cli_explicit_output_directory_is_preserved(local_evaluation):
    cli.main(["eval", "--output-dir", "selected-results"])
    assert (Path("selected-results") / "results.json").is_file()
    assert not Path("data/runs").exists()
    assert not Path("docs").exists()


def test_eval_help_describes_new_timestamped_default(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["eval", "--help"])
    assert exc.value.code == 0
    help_text = " ".join(capsys.readouterr().out.split())
    assert "new timestamped directory" in help_text
    assert str(config.DATA_DIR / "runs") in help_text
