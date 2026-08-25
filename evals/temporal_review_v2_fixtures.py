"""Independent v2 temporal-review preregistration contract.

This module deliberately does not import the v1 review oracle.  V2 evaluates
source identity as ``path + qualname`` and decision enums; free-form rationale
is retained for audit but never scored.
"""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MANIFEST_PATH = Path(__file__).with_name("temporal-review-v2-fixture-manifest.json")
INSTRUCTION_DIR = Path(__file__).with_name("temporal-review-v2-instructions")
TASK_IDS = (
    "impact-low-resolution-review",
    "sparse-risk-review",
    "sparse-risk-codegraph-uncertainty",
)
_SHA = re.compile(r"^[0-9a-f]{40}$")
_EVIDENCE_KINDS = {"source_text", "content_delta", "graph_delta", "graph_boundary"}
_PROVISIONED = {"created", "reused", "rebuilt"}
_TOP_FIELDS = {"decision", "review_loci", "trust"}
_DECISION_FIELDS = {"outcome", "boundary", "rationale"}
_LOCUS_FIELDS = {"path", "qualname", "evidence_kind", "rationale"}
_TRUST_FIELDS = {"availability", "comparison"}
_COMPARISON_FIELDS = {
    "base_ref", "head_ref", "base_backend", "head_backend", "base_provisioned", "head_provisioned",
    "content_comparison",
}


class V2ContractError(ValueError):
    """The separately registered v2 contract is malformed."""


@dataclass(frozen=True)
class Outcome:
    passed: bool
    failures: tuple[str, ...]


@dataclass(frozen=True)
class Contract:
    task_id: str
    refs: Mapping[str, Mapping[str, str]]
    backend: str
    expected_comparison: Mapping[str, Any]
    oracle: Mapping[str, Any]
    instruction_file: str

    @property
    def base_ref(self) -> str:
        return self.refs["base"]["alias"]

    @property
    def head_ref(self) -> str:
        return self.refs["head"]["alias"]


def load_manifest() -> dict[str, Any]:
    value = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise V2ContractError("v2 manifest must be an object")
    validate_manifest(value)
    return value


def validate_manifest(manifest: Mapping[str, Any]) -> None:
    if manifest.get("schema_version") != 2 or manifest.get("manifest_id") != "loomgraph-temporal-review-v2-reregistration":
        raise V2ContractError("not the frozen v2 temporal-review manifest")
    if manifest.get("task_class") != "temporal-review-v2" or manifest.get("repository") != "loomgraph":
        raise V2ContractError("v2 manifest identity is invalid")
    schema = _mapping(manifest.get("answer_schema"), "answer_schema")
    if set(schema.get("top_level_fields", ())) != _TOP_FIELDS:
        raise V2ContractError("v2 answer fields are invalid")
    if set(schema.get("decision_fields", ())) != _DECISION_FIELDS or set(schema.get("review_locus_fields", ())) != _LOCUS_FIELDS:
        raise V2ContractError("v2 semantic fields are invalid")
    if not _EVIDENCE_KINDS.issubset(set(schema.get("evidence_kinds", ()))):
        raise V2ContractError("v2 evidence enum is incomplete")
    tasks = manifest.get("tasks")
    if not isinstance(tasks, list) or tuple(task.get("id") for task in tasks if isinstance(task, dict)) != TASK_IDS:
        raise V2ContractError("v2 task ids or order changed")
    for task in tasks:
        _validate_task(_mapping(task, "task"), schema)


def contract(task_id: str) -> Contract:
    for task in load_manifest()["tasks"]:
        if task["id"] == task_id:
            return Contract(task_id, task["refs"], task["backend"], task["expected_comparison"], task["oracle"], task["instruction_file"])
    raise V2ContractError(f"unknown v2 task: {task_id}")


def load_instruction(task_id: str) -> str:
    item = contract(task_id)
    relative = Path(item.instruction_file)
    if relative.is_absolute() or ".." in relative.parts:
        raise V2ContractError("instruction escapes v2 directory")
    value = (MANIFEST_PATH.parent / relative).read_text(encoding="utf-8").strip()
    forbidden = ("oracle", "fixture-manifest", "CHANGELOG", "tests/", "evals/", "a961ab", "26cd69")
    if not value or any(term in value for term in forbidden):
        raise V2ContractError("v2 instruction leaks hidden contract material")
    if item.base_ref not in value or item.head_ref not in value or item.backend not in value:
        raise V2ContractError("v2 instruction lacks public task surface")
    return value


def canonical_head_identity(source_root: Path, path: str, qualname: str) -> tuple[str, str] | None:
    """Resolve a source tuple against the frozen head checkout's Python AST."""
    if not path.startswith("src/") or not path.endswith(".py") or not qualname or "::" in qualname:
        return None
    source = source_root / path
    try:
        tree = ast.parse(source.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return None
    names: set[str] = set()

    def visit(body: list[ast.stmt], prefix: str = "") -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = f"{prefix}.{node.name}" if prefix else node.name
                names.add(name)
                if isinstance(node, ast.ClassDef):
                    visit(node.body, name)

    visit(tree.body)
    return (path, qualname) if qualname in names else None


def parse_raw_response(task_id: str, raw_response: object) -> dict[str, Any]:
    item = contract(task_id)
    raw = _decode(raw_response)
    if raw is None or raw.get("success") is not True or not isinstance(raw.get("data"), Mapping):
        return _invalid("raw_response_invalid")
    data = raw["data"]
    snapshots: dict[str, Mapping[str, Any]] = {}
    for side in ("base", "head"):
        snapshot = data.get(side)
        if not isinstance(snapshot, Mapping) or snapshot.get("ref") != item.refs[side]["alias"] or snapshot.get("sha") != item.refs[side]["commit_sha"]:
            return _invalid(f"{side}_ref_or_sha_mismatch")
        if snapshot.get("provisioned") not in _PROVISIONED or not isinstance(snapshot.get("workspace"), str):
            return _invalid(f"{side}_snapshot_invalid")
        snapshots[side] = snapshot
    diff = data.get("diff")
    content = diff.get("content_comparison") if isinstance(diff, Mapping) else None
    expected = item.expected_comparison
    if not isinstance(content, Mapping) or any(content.get(key) != expected[key] for key in ("status", "reason", "base_backend", "head_backend")):
        return _invalid("content_comparison_mismatch")
    return {
        "valid": True,
        "reason": None,
        "comparison": {
            "base_ref": snapshots["base"]["ref"], "head_ref": snapshots["head"]["ref"],
            "base_backend": content["base_backend"], "head_backend": content["head_backend"],
            "base_provisioned": snapshots["base"]["provisioned"], "head_provisioned": snapshots["head"]["provisioned"],
            "content_comparison": {"status": content["status"], "reason": content.get("reason")},
        },
        "diff": diff,
    }


def evaluate_answer(task_id: str, answer: object, *, condition: str, source_root: Path, raw_response: object | None = None) -> Outcome:
    item = contract(task_id)
    failures: list[str] = []
    if condition not in {"baseline", "treatment"}:
        return _failed("condition must be baseline or treatment")
    if not isinstance(answer, Mapping) or set(answer) != _TOP_FIELDS:
        return _failed("answer top-level fields are invalid")
    decision = answer.get("decision")
    if not isinstance(decision, Mapping) or set(decision) != _DECISION_FIELDS:
        failures.append("decision fields are invalid")
    else:
        target = item.oracle["decision"]
        if decision.get("outcome") != target["outcome"] or decision.get("boundary") != target["boundary"]:
            failures.append("decision enum does not match the frozen rule")
        if not _non_empty(decision.get("rationale")):
            failures.append("decision rationale is required")
    loci = answer.get("review_loci")
    if not isinstance(loci, list) or not loci:
        failures.append("review_loci must be non-empty")
    else:
        observed: set[tuple[str, str, str]] = set()
        for locus in loci:
            if not isinstance(locus, Mapping) or set(locus) != _LOCUS_FIELDS:
                failures.append("review locus fields are invalid")
                continue
            path, qualname, evidence = locus.get("path"), locus.get("qualname"), locus.get("evidence_kind")
            if not isinstance(path, str) or not isinstance(qualname, str) or evidence not in _EVIDENCE_KINDS:
                failures.append("review locus values are invalid")
                continue
            if canonical_head_identity(source_root, path, qualname) is None:
                failures.append("review locus does not resolve in frozen head AST")
            if not _non_empty(locus.get("rationale")):
                failures.append("review locus rationale is required")
            observed.add((path, qualname, str(evidence)))
        for required in item.oracle["required_review_loci"]:
            expected_kind = required["evidence_kind"][condition]
            identity = (required["path"], required["qualname"], expected_kind)
            if identity not in observed:
                failures.append("required v2 review identity is missing")
    trust = answer.get("trust")
    if not isinstance(trust, Mapping) or set(trust) != _TRUST_FIELDS:
        failures.append("trust fields are invalid")
    elif condition == "baseline":
        if trust.get("availability") != "unavailable" or trust.get("comparison") is not None:
            failures.append("baseline must declare unavailable comparison")
    else:
        parsed = parse_raw_response(task_id, raw_response)
        if trust.get("availability") != "available" or not parsed["valid"] or trust.get("comparison") != parsed["comparison"]:
            failures.append("treatment trust must exactly match valid raw response")
        elif not _raw_supports_identities(parsed["diff"], item.oracle["required_review_loci"]):
            failures.append("raw response does not support frozen treatment identities")
    return _passed() if not failures else _failed(*failures)


def _raw_supports_identities(diff: object, required: object) -> bool:
    if not isinstance(diff, Mapping) or not isinstance(required, list):
        return False
    changed = diff.get("content_comparison", {}).get("changed", []) if isinstance(diff.get("content_comparison"), Mapping) else []
    chains = [*diff.get("edges_added", []), *diff.get("new_chains", []), *diff.get("broken_chains", [])]
    for locus in required:
        if not isinstance(locus, Mapping):
            return False
        expected = locus["evidence_kind"]["treatment"]
        path, qualname = locus["path"], locus["qualname"]
        if expected == "content_delta":
            if not any(isinstance(item, Mapping) and str(item.get("source_id", "")).split(":", 1)[0] == path and str(item.get("name", "")).endswith(qualname) for item in changed or []):
                return False
        elif expected in {"graph_delta", "graph_boundary"}:
            if not any(isinstance(chain, Mapping) and any(str(chain.get(side, "")).replace("::", ".").endswith(qualname) for side in ("src", "tgt")) for chain in chains):
                return False
        else:
            return False
    return True


def _validate_task(task: Mapping[str, Any], schema: Mapping[str, Any]) -> None:
    if task.get("id") not in TASK_IDS or task.get("task_class") != "temporal-review-v2":
        raise V2ContractError("v2 task identity is invalid")
    refs = _mapping(task.get("refs"), "refs")
    for side in ("base", "head"):
        ref = _mapping(refs.get(side), side)
        if ref.get("alias") != f"review-{side}" or not isinstance(ref.get("commit_sha"), str) or not _SHA.fullmatch(ref["commit_sha"]):
            raise V2ContractError("v2 refs are invalid")
    expected = _mapping(task.get("expected_comparison"), "expected_comparison")
    if task.get("backend") not in {"codeindex", "codegraph"} or expected.get("base_backend") != task.get("backend") or expected.get("head_backend") != task.get("backend"):
        raise V2ContractError("v2 comparison backend is invalid")
    oracle = _mapping(task.get("oracle"), "oracle")
    decision = _mapping(oracle.get("decision"), "oracle.decision")
    if decision.get("outcome") not in schema["decision_outcomes"] or decision.get("boundary") not in schema["decision_boundaries"]:
        raise V2ContractError("v2 hidden decision enum is invalid")
    loci = oracle.get("required_review_loci")
    if not isinstance(loci, list) or not loci:
        raise V2ContractError("v2 requires review identities")
    for locus in loci:
        value = _mapping(locus, "review identity")
        kinds = _mapping(value.get("evidence_kind"), "identity evidence")
        if not _non_empty(value.get("path")) or not _non_empty(value.get("qualname")) or set(kinds) != {"baseline", "treatment"} or any(kind not in schema["evidence_kinds"] for kind in kinds.values()):
            raise V2ContractError("v2 identity is invalid")


def _mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise V2ContractError(f"{name} must be an object")
    return value


def _decode(value: object) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return None
        return decoded if isinstance(decoded, dict) else None
    return None


def _invalid(reason: str) -> dict[str, Any]:
    return {"valid": False, "reason": reason}


def _non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _passed() -> Outcome:
    return Outcome(True, ())


def _failed(*failures: str) -> Outcome:
    return Outcome(False, tuple(failures))
