"""Synthetic evidence fixtures test evaluator behavior, not real financial accuracy."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import FIXTURES, make_chunk
from filingqa import cli, evaluate
from filingqa.answer import Answer
from filingqa.evidence import EvidenceError, load_reviewed_evidence
from filingqa.goldset import Question


@pytest.fixture
def setup_evidence(tmp_path):
    raw = json.loads((FIXTURES / "reviewed_evidence_synthetic.json").read_text())
    entry = raw["questions"][0]
    q = Question(entry["id"], "ACME", 2024, "net_income", "NetIncomeLoss",
                 "What was ACME's net income for fiscal year 2024?", -45e9, "synthetic-accession")
    other = Question("ACME-FY2024:revenue", "ACME", 2024, "revenue", "Revenues",
                     "What was ACME revenue in fiscal year 2024?", 100e6, "synthetic-accession")
    quote = entry["evidence"]["section"][0]["quote"]
    chunks = [
        make_chunk("ACME-FY2025#0001", quote, ticker="ACME", fy=2025),
        make_chunk("ACME-FY2024#0009", "Unrelated assets | 45,000", ticker="ACME"),
        make_chunk("MSFT-FY2024#0001", quote, ticker="MSFT"),
    ]
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(raw))
    return raw, [q, other], {"section": chunks}, path


def save(path, raw):
    path.write_text(json.dumps(raw))


def test_reviewed_labels_allow_comparative_year_and_exclude_unannotated(setup_evidence):
    _, questions, chunks, path = setup_evidence
    selected, gold, info = load_reviewed_evidence(path, questions, chunks)
    assert selected == questions[:1]
    assert gold == {"section": {questions[0].id: {"ACME-FY2025#0001"}}}
    assert info["generated_questions"] == 2
    assert info["annotated_questions"] == info["selected_questions"] == 1
    assert info["excluded_questions"] == 1
    assert len(info["manifest_sha256"]) == 64


@pytest.mark.parametrize("field,value", [
    ("ticker", "MSFT"), ("fiscal_year", 2023), ("fiscal_year", True),
    ("metric", "revenue"), ("value", 45e9), ("value", -45000),
    ("value", True), ("value", 10 ** 1000), ("value", float("nan")), ("unit", "EUR"),
])
def test_reviewed_metadata_must_match_question(setup_evidence, field, value):
    raw, questions, chunks, path = setup_evidence
    raw["questions"][0][field] = value
    save(path, raw)
    with pytest.raises(EvidenceError):
        load_reviewed_evidence(path, questions, chunks)


@pytest.mark.parametrize("change", ["empty", "duplicate", "unknown", "wrong_company",
                                    "quote", "blank_quote", "missing_chunking", "extra_chunking",
                                    "missing_labels", "duplicate_label", "unknown_chunk"])
def test_invalid_reviewed_labels_fail_closed(setup_evidence, change):
    raw, questions, chunks, path = setup_evidence
    entry = raw["questions"][0]
    labels = entry["evidence"]["section"]
    if change == "empty":
        raw["questions"] = []
    elif change == "duplicate":
        raw["questions"].append(copy.deepcopy(entry))
    elif change == "unknown":
        entry["id"] = "ACME-FY2024:missing"
    elif change == "wrong_company":
        labels[0]["chunk_id"] = "MSFT-FY2024#0001"
    elif change == "quote":
        labels[0]["quote"] = "Net income | (46,000)"
    elif change == "blank_quote":
        labels[0]["quote"] = " "
    elif change == "missing_chunking":
        entry["evidence"] = {}
    elif change == "extra_chunking":
        entry["evidence"]["fixed"] = copy.deepcopy(labels)
    elif change == "missing_labels":
        entry["evidence"]["section"] = []
    elif change == "duplicate_label":
        labels.append(copy.deepcopy(labels[0]))
    elif change == "unknown_chunk":
        labels[0]["chunk_id"] = "ACME-FY2024#9999"
    save(path, raw)
    with pytest.raises(EvidenceError):
        load_reviewed_evidence(path, questions, chunks)


def test_duplicate_json_key_and_unsupported_version_rejected(setup_evidence):
    raw, questions, chunks, path = setup_evidence
    path.write_text('{"version":1,"version":1,"questions":[]}')
    with pytest.raises(EvidenceError, match="duplicate JSON key"):
        load_reviewed_evidence(path, questions, chunks)
    raw["version"] = True
    save(path, raw)
    with pytest.raises(EvidenceError, match="version"):
        load_reviewed_evidence(path, questions, chunks)


class FakeIndex:
    chunking = "section"

    def __init__(self, chunks):
        self.chunks = chunks
        self.by_id = {c.id: c for c in chunks}

    def retriever(self, name):
        assert name == "bm25"
        # Same number, wrong row: automatic matching calls this a candidate, reviewed does not.
        return SimpleNamespace(search=lambda text, k: [("ACME-FY2024#0009", 1.0)])


class FakeGenerator:
    name = "synthetic-offline"

    def generate(self, system, prompt):
        cid = "ACME-FY2025#0001" if "Fiscal year | 2024" in prompt else "ACME-FY2024#0009"
        return f"-$45 billion [{cid}]"


def wire_evaluator(monkeypatch, questions, chunks):
    # Keep the original weak-label demonstration inside an explicit-period context.
    # The row remains the wrong metric and is never a reviewed source.
    chunks["section"][1].text = "Fiscal year 2024. Unrelated assets | 45,000"
    monkeypatch.setattr(evaluate, "load_manifest", lambda: [SimpleNamespace(ticker="ACME")])
    monkeypatch.setattr(evaluate, "load_facts", lambda tickers: {})
    monkeypatch.setattr(evaluate, "build_questions", lambda filings, facts: questions)
    monkeypatch.setattr(evaluate, "load_index", lambda name: FakeIndex(chunks["section"]))
    monkeypatch.setattr(evaluate, "make_generator", lambda backend: FakeGenerator())
    monkeypatch.setattr(evaluate, "plot", lambda *args: None)


def run(tmp_path, reviewed):
    docs = tmp_path / "results"
    evaluate.run_eval(["section"], ["bm25"], True, ("section", "bm25"), None,
                      "fake", False, docs, reviewed)
    return json.loads((docs / "results.json").read_text()), (docs / "results.md").read_text()


def test_reviewed_evaluator_has_no_number_match_fallback(monkeypatch, setup_evidence, tmp_path):
    _, questions, chunks, path = setup_evidence
    wire_evaluator(monkeypatch, questions, chunks)
    output, report = run(tmp_path, path)
    assert output["evaluation"]["evidence_mode"] == "reviewed"
    assert output["evaluation"]["scoring_version"] == "signed-usd-v2"
    assert output["n_questions"] == 1
    assert output["retrieval"][0]["recall"]["1"] == 0
    retrieved = output["e2e_details"]["section + bm25"][0]
    oracle = output["e2e_details"]["oracle (section)"][0]
    assert retrieved["correct"] and not retrieved["cited_gold_and_correct"]
    assert oracle["correct"] and oracle["cited_gold_and_correct"]
    assert "reviewed label" in report and "annotation author" in report
    assert len(json.loads((tmp_path / "results/goldset.json").read_text())) == 1


def test_default_evaluator_is_explicitly_candidate_mode(monkeypatch, setup_evidence, tmp_path):
    _, questions, chunks, _ = setup_evidence
    wire_evaluator(monkeypatch, questions, chunks)
    output, report = run(tmp_path, None)
    assert output["evaluation"]["evidence_mode"] == "candidate"
    assert output["retrieval"][0]["recall"]["1"] == 1
    assert output["e2e_details"]["section + bm25"][0]["cited_gold_and_correct"]
    assert "heuristic candidate" in report and "not claim-level verified" in report


def test_explicitly_unverified_model_fallback_does_not_change_reviewed_labels(monkeypatch, setup_evidence, tmp_path):
    _, questions, chunks, path = setup_evidence
    # Period is explicit but this is still the wrong metric, and is not a reviewed source.
    chunks["section"][1].text = "Fiscal year 2024. Unrelated assets | 45,000"
    wire_evaluator(monkeypatch, questions, chunks)
    output, _ = run(tmp_path, path)
    retrieved = output["e2e_details"]["section + bm25"][0]
    assert retrieved["correct"] and not retrieved["cited_gold_and_correct"]
    assert retrieved["answer_method"] == "model-fallback" and not retrieved["source_evidence"]
    assert output["e2e"][0]["model_calls"] == 1


def test_invalid_manifest_stops_before_generator_or_output(monkeypatch, setup_evidence, tmp_path):
    raw, questions, chunks, path = setup_evidence
    wire_evaluator(monkeypatch, questions, chunks)
    raw["questions"][0]["unit"] = "EUR"
    save(path, raw)
    monkeypatch.setattr(evaluate, "make_generator", lambda backend: pytest.fail("generator called"))
    with pytest.raises(EvidenceError):
        run(tmp_path, path)
    assert not (tmp_path / "results").exists()


def test_empty_default_set_fails_without_output(monkeypatch, setup_evidence, tmp_path):
    _, _, chunks, _ = setup_evidence
    wire_evaluator(monkeypatch, [], chunks)
    with pytest.raises(ValueError, match="no questions"):
        run(tmp_path, None)
    assert not (tmp_path / "results").exists()


def test_not_found_never_counts_as_correct(setup_evidence):
    _, questions, _, _ = setup_evidence
    ans = Answer(questions[0].question, "not found in the filings (-$45 billion)", [], [])
    scored = evaluate._score(questions[0], ans, {"ACME-FY2025#0001"})
    assert scored["abstained"] and not scored["correct"]


def test_cli_wires_manifest_path(monkeypatch):
    captured = {}
    monkeypatch.setattr(evaluate, "run_eval", lambda **kwargs: captured.update(kwargs))
    cli.main(["eval", "--chunking", "section", "--retriever", "bm25",
              "--reviewed-evidence", "reviewed.json", "--output-dir", "runs/reviewed"])
    assert captured["reviewed_evidence"] == Path("reviewed.json")
    assert captured["chunkings"] == ["section"]
    assert captured["docs"] == Path("runs/reviewed")


@pytest.mark.parametrize("limit", [0, -1])
def test_cli_expected_evaluation_validation_is_clean(monkeypatch, capsys, limit):
    with pytest.raises(SystemExit) as exc:
        cli.main(["eval", "--e2e-limit", str(limit)])
    assert str(exc.value) == "error: e2e_limit must be a positive integer"
    assert "Traceback" not in capsys.readouterr().err


def test_cli_empty_evaluation_is_clean(monkeypatch):
    def empty(**kwargs):
        raise evaluate.EvaluationError("no questions selected for evaluation")
    monkeypatch.setattr(evaluate, "run_eval", empty)
    with pytest.raises(SystemExit, match="error: no questions selected"):
        cli.main(["eval"])


def test_cli_does_not_hide_unexpected_value_error(monkeypatch):
    def unexpected(**kwargs):
        raise ValueError("unexpected implementation error")
    monkeypatch.setattr(evaluate, "run_eval", unexpected)
    with pytest.raises(ValueError, match="unexpected implementation error"):
        cli.main(["eval"])


@pytest.mark.parametrize("configuration", ["section", "section+bm25+x", "section+foo",
                                            "unknown+bm25", "", "+bm25", "section+", "+"])
def test_cli_rejects_bad_e2e_config_before_loading(monkeypatch, configuration):
    def forbidden(*args, **kwargs):
        pytest.fail("invalid config reached corpus/index/model/retrieval")
    monkeypatch.setattr(evaluate, "load_manifest", forbidden)
    monkeypatch.setattr(evaluate, "load_index", forbidden)
    monkeypatch.setattr(evaluate, "make_generator", forbidden)
    monkeypatch.setattr(evaluate, "eval_retrieval", forbidden)
    with pytest.raises(SystemExit, match=r"error: e2e_config must be CHUNKING\+RETRIEVER"):
        cli.main(["eval", "--e2e", "--e2e-config", configuration])
