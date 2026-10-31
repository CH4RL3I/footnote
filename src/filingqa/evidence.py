"""Load explicitly reviewed citation labels; never infer semantic support from a number.

The reviewer is responsible for the metric, period, unit and sign represented by a quote.
Validation checks label identity and verbatim quote grounding, not financial entailment.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path

from .chunking import Chunk
from .goldset import Question

EVIDENCE_VERSION = "reviewed-quotes-v1"
CANDIDATE_VERSION = "company-number-candidates-v1"
SCORING_VERSION = "signed-usd-v2"


class EvidenceError(ValueError):
    """A reviewed manifest cannot be safely used for this evaluation."""


def _object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise EvidenceError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _fields(value, required: set[str], where: str, optional: set[str] | None = None):
    if not isinstance(value, dict):
        raise EvidenceError(f"{where} must be an object")
    if not required <= value.keys() or value.keys() - required - (optional or set()):
        raise EvidenceError(f"{where} must contain exactly {sorted(required)}")


def load_reviewed_evidence(
    path: Path, questions: Sequence[Question], chunks: Mapping[str, Sequence[Chunk]],
) -> tuple[list[Question], dict[str, dict[str, set[str]]], dict]:
    """Return only annotated questions and grounded labels for every requested chunking.

    Manifests are scoped to the requested strategies. Requiring an exact strategy set makes
    stale/unused annotations fail visibly rather than escaping source validation.
    """
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise EvidenceError(f"cannot read evidence manifest: {exc}") from exc
    try:
        manifest = json.loads(raw, object_pairs_hook=_object)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise EvidenceError(f"invalid evidence JSON: {exc}") from exc
    _fields(manifest, {"version", "questions"}, "manifest", {"description"})
    if type(manifest["version"]) is not int or manifest["version"] != 1:
        raise EvidenceError("unsupported evidence manifest version; expected 1")
    entries = manifest["questions"]
    if not isinstance(entries, list) or not entries:
        raise EvidenceError("manifest questions must be a nonempty list")
    known = {q.id: q for q in questions}
    if len(known) != len(questions):
        raise EvidenceError("generated question IDs are not unique")
    by_chunking = {name: {c.id: c for c in items} for name, items in chunks.items()}
    if not by_chunking:
        raise EvidenceError("at least one chunking is required")
    for name, items in chunks.items():
        if len(by_chunking[name]) != len(items):
            raise EvidenceError(f"duplicate chunk IDs in {name}")
    gold: dict[str, dict[str, set[str]]] = {name: {} for name in chunks}
    seen: set[str] = set()
    for entry in entries:
        _fields(entry, {"id", "ticker", "fiscal_year", "metric", "value", "unit", "evidence"}, "question")
        qid = entry["id"]
        if not isinstance(qid, str) or qid not in known:
            raise EvidenceError(f"unknown question ID: {qid!r}")
        if qid in seen:
            raise EvidenceError(f"duplicate question ID: {qid}")
        seen.add(qid)
        q = known[qid]
        if (entry["ticker"] != q.ticker or type(entry["fiscal_year"]) is not int
                or entry["fiscal_year"] != q.fiscal_year or entry["metric"] != q.metric):
            raise EvidenceError(f"question metadata mismatch: {qid}")
        value = entry["value"]
        try:
            finite = type(value) in (int, float) and math.isfinite(value)
        except OverflowError:
            finite = False
        if (not finite or value != q.value or entry["unit"] != "USD"):
            raise EvidenceError(f"signed USD value/unit mismatch: {qid}")
        evidence = entry["evidence"]
        if not isinstance(evidence, dict) or set(evidence) != set(chunks):
            raise EvidenceError(f"{qid}: evidence must cover exactly chunkings {sorted(chunks)}")
        for name, labels in evidence.items():
            if not isinstance(labels, list) or not labels:
                raise EvidenceError(f"{qid}/{name}: evidence must be a nonempty list")
            ids: set[str] = set()
            for label in labels:
                _fields(label, {"chunk_id", "quote"}, f"{qid}/{name} label")
                cid, quote = label["chunk_id"], label["quote"]
                if not isinstance(cid, str) or cid not in by_chunking[name]:
                    raise EvidenceError(f"{qid}/{name}: unknown chunk ID {cid!r}")
                if cid in ids:
                    raise EvidenceError(f"{qid}/{name}: duplicate chunk ID {cid}")
                chunk = by_chunking[name][cid]
                if chunk.ticker != q.ticker:
                    raise EvidenceError(f"{qid}/{name}: wrong-company chunk {cid}")
                if not isinstance(quote, str) or not quote.strip() or quote not in chunk.text:
                    raise EvidenceError(f"{qid}/{name}: quote is not a nonempty exact source span")
                ids.add(cid)
            gold[name][qid] = ids
    selected = [q for q in questions if q.id in seen]
    metadata = {
        "scoring_version": SCORING_VERSION, "evidence_mode": "reviewed",
        "evidence_version": EVIDENCE_VERSION, "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "generated_questions": len(questions), "annotated_questions": len(entries),
        "selected_questions": len(selected), "excluded_questions": len(questions) - len(selected),
        "semantic_support": "asserted by annotation author; identity and exact quote grounding checked",
    }
    return selected, gold, metadata
