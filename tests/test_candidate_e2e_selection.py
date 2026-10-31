"""Candidate cohorts must have oracle evidence in every evaluated chunking."""

import json
from types import SimpleNamespace

import pytest

from conftest import make_chunk
from filingqa import evaluate
from filingqa.goldset import Question


def wire_candidate_cohorts(monkeypatch, all_supported=False):
    questions = [
        Question(
            "ACME-FY2030:net_income", "ACME", 2030, "net_income", "NetIncomeLoss",
            "What was ACME net income for fiscal year 2030?", 45_000_000,
            "synthetic-accession",
        ),
        Question(
            "ACME-FY2030:revenue", "ACME", 2030, "revenue", "Revenues",
            "What was ACME total revenue for fiscal year 2030?", 100_000_000,
            "synthetic-accession",
        ),
        Question(
            "ACME-FY2030:total_assets", "ACME", 2030, "total_assets", "Assets",
            "What were ACME total assets for fiscal year 2030?", 300_000_000,
            "synthetic-accession",
        ),
    ]
    by_metric = {
        "net_income": make_chunk(
            "ACME-FY2030#0000",
            "CONSOLIDATED STATEMENTS OF INCOME\n(In thousands)\n2030 | 2029\n"
            "Net income | 45,000 | 42,000",
            ticker="ACME", fy=2030,
        ),
        "revenue": make_chunk(
            "ACME-FY2030#0002",
            "CONSOLIDATED STATEMENTS OF INCOME\n(In thousands)\n2030 | 2029\n"
            "Revenue | 100,000 | 90,000",
            ticker="ACME", fy=2030,
        ),
        "total_assets": make_chunk(
            "ACME-FY2030#0004",
            "CONSOLIDATED BALANCE SHEETS\n(In thousands)\n2030 | 2029\n"
            "Total assets | 300,000 | 275,000",
            ticker="ACME", fy=2030,
        ),
    }
    if all_supported:
        contents = {name: list(by_metric.values()) for name in ["fixed", "section"]}
    else:
        contents = {
            "fixed": [by_metric["net_income"], by_metric["total_assets"]],
            "section": [by_metric["net_income"], by_metric["revenue"]],
        }
    indexes = {
        name: SimpleNamespace(chunking=name, chunks=chunks)
        for name, chunks in contents.items()
    }
    loaded, retrieval_cohorts, e2e_cohorts = [], [], []

    def load_index(name):
        loaded.append(name)
        return indexes[name]

    def retrieval(index, retriever, cohort, gold):
        retrieval_cohorts.append([q.id for q in cohort])
        return evaluate.RetrievalRow(
            index.chunking, retriever, len(cohort),
            {k: 1.0 for k in evaluate.KS}, {k: (0.0, 1.0) for k in evaluate.KS}, 1.0,
        )

    def end_to_end(index, retriever, cohort, gold, backend, oracle):
        e2e_cohorts.append({
            "oracle": oracle, "ids": [q.id for q in cohort],
            "missing_oracle_candidates": [q.id for q in cohort if not gold[q.id]],
        })
        label = f"oracle ({index.chunking})" if oracle else f"{index.chunking} + {retriever}"
        return evaluate.E2ERow(
            label, "offline-cohort-probe", len(cohort), 0.0, (0.0, 1.0),
            0.0, 0.0, 0.0, 0.0,
        ), [{"id": q.id} for q in cohort]

    monkeypatch.setattr(evaluate, "load_manifest", lambda: [SimpleNamespace(ticker="ACME")])
    monkeypatch.setattr(evaluate, "load_facts", lambda tickers: {})
    monkeypatch.setattr(evaluate, "build_questions", lambda filings, facts: questions)
    monkeypatch.setattr(evaluate, "load_index", load_index)
    monkeypatch.setattr(evaluate, "eval_retrieval", retrieval)
    monkeypatch.setattr(evaluate, "eval_e2e", end_to_end)
    monkeypatch.setattr(evaluate, "plot", lambda *args: None)
    monkeypatch.setattr(
        evaluate, "make_generator", lambda *args: pytest.fail("cohort test must not call a model")
    )
    return questions, loaded, retrieval_cohorts, e2e_cohorts


@pytest.mark.parametrize("chunkings,e2e_config", [
    (["section"], ("fixed", "dense")),
    (["fixed"], ("section", "bm25")),
    (["fixed", "section"], ("fixed", "dense")),
])
def test_every_evaluated_chunking_has_candidates_for_selected_questions(
    monkeypatch, tmp_path, capsys, chunkings, e2e_config
):
    questions, loaded, retrieval, e2e = wire_candidate_cohorts(monkeypatch)
    docs = tmp_path / "isolated-unit-report"
    evaluate.run_eval(chunkings, ["bm25"], True, e2e_config, None, "fake", False, docs)

    output = json.loads((docs / "results.json").read_text())
    expected = [questions[0].id]
    assert retrieval and all(cohort == expected for cohort in retrieval)
    assert [run["ids"] for run in e2e] == [expected, expected]
    assert not any(run["missing_oracle_candidates"] for run in e2e)
    assert set(loaded) == set(chunkings) | {e2e_config[0]}
    assert output["evaluation"]["selected_questions"] == output["n_questions"] == 1
    assert output["evaluation"]["excluded_questions"] == 2
    assert [q["id"] for q in json.loads((docs / "goldset.json").read_text())] == expected
    assert "1 selected, 2 excluded" in capsys.readouterr().out


def test_all_chunkings_with_complete_candidates_preserve_every_question(monkeypatch, tmp_path):
    questions, _, retrieval, e2e = wire_candidate_cohorts(monkeypatch, all_supported=True)
    docs = tmp_path / "isolated-unit-report"
    evaluate.run_eval(
        ["fixed", "section"], ["bm25"], True, ("fixed", "dense"),
        None, "fake", False, docs,
    )

    expected = [q.id for q in questions]
    assert all(cohort == expected for cohort in retrieval)
    assert all(run["ids"] == expected and not run["missing_oracle_candidates"] for run in e2e)
    metadata = json.loads((docs / "results.json").read_text())["evaluation"]
    assert metadata["generated_questions"] == metadata["selected_questions"] == 3
    assert metadata["excluded_questions"] == 0
    assert json.loads((docs / "goldset.json").read_text()) == [q.to_dict() for q in questions]


def test_retrieval_only_does_not_require_candidates_in_unused_e2e_chunking(
    monkeypatch, tmp_path
):
    questions, loaded, retrieval, e2e = wire_candidate_cohorts(monkeypatch)
    docs = tmp_path / "isolated-unit-report"
    evaluate.run_eval(
        ["section"], ["bm25"], False, ("fixed", "dense"), None, "fake", False, docs
    )

    assert loaded == ["section"]
    assert retrieval == [[questions[0].id, questions[1].id]]
    assert e2e == []
    metadata = json.loads((docs / "results.json").read_text())["evaluation"]
    assert metadata["selected_questions"] == 2 and metadata["excluded_questions"] == 1
