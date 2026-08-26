"""Independent v7 contract for one-locus temporal review evidence."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MANIFEST_PATH = Path(__file__).with_name("temporal-review-v7-fixture-manifest.json")
SELECTION_PREFLIGHT_PATH = Path(__file__).with_name("temporal-review-v7-selection-preflight.json")
TASK_IDS = (
    "v7-impact-caller-qualification-primary-navigation",
    "v7-working-tree-diff-default-primary-navigation",
)
_SHA = re.compile(r"^[0-9a-f]{40}$")
_PRIOR_SELECTION_RAW_SHA256 = {
    "3625423fe438acb6848d1618fa48fca5f361666a0354159197f3833222e97706",
    "e4252de94f7ba60612635282651724fb2db62d997f51f3acd7eb0ae1b806c687",
    "a0babfbedd1bb8b10ae5a490c295c8aa6bd73d9478ade87e305b8a72190519bc",
    "91b9c996d0b1080b71d87465c9a2a822c423fd93ec9c2f45a0dd105816d8f362",
}
_PROVISIONED = {"created", "reused", "rebuilt"}
_TOP_FIELDS = {"decision", "review_locus"}
_DECISION_FIELDS = {"boundary", "rationale"}
_LOCUS_FIELDS = {"path", "qualname", "rationale"}
_SCORED_MODEL_FIELDS = {"decision.boundary", "review_locus.path", "review_locus.qualname"}
_SOURCE_ONLY_EXCLUSIONS = {"CHANGELOG.md", "customers/CHANGELOG.md", "docs/evals/**", "tests/**", "evals/**"}


class V7ContractError(ValueError):
    """The independently registered v7 contract is malformed."""


@dataclass(frozen=True)
class Outcome:
    """Schema/identity/trust validity without a tool-use-count score."""

    passed: bool
    failures: tuple[str, ...]


@dataclass(frozen=True)
class Contract:
    """Frozen task data used by the v7 materializer and adapter."""

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
    """Load and validate the immutable independently registered v7 manifest."""
    try:
        value = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise V7ContractError("v7 manifest is unreadable") from exc
    if not isinstance(value, dict):
        raise V7ContractError("v7 manifest must be an object")
    validate_manifest(value)
    return value


def validate_manifest(manifest: Mapping[str, Any]) -> None:
    """Reject cohort pooling, multi-locus answers, and weak raw trust."""
    if (
        manifest.get("schema_version") != 7
        or manifest.get("manifest_id") != "loomgraph-temporal-review-v7-primary-navigation-evidence"
        or manifest.get("task_class") != "temporal-review-v7"
        or manifest.get("repository") != "loomgraph"
    ):
        raise V7ContractError("not the frozen v7 temporal-review manifest")
    if _mapping(manifest.get("cohort_lineage"), "cohort_lineage") != {
        "cohort_id": "temporal-review-v7",
        "independent_from": "loomgraph-temporal-review-v6-primary-navigation-evidence",
        "source_comparisons": "same_frozen_history_independent_same-source-contrast",
        "predecessor_evidence": "archive_only_not_rerun_rescored_or_pooled",
    }:
        raise V7ContractError("v7 cohort independence declaration is invalid")
    schema = _mapping(manifest.get("answer_schema"), "answer_schema")
    if (
        set(schema.get("top_level_fields", ())) != _TOP_FIELDS
        or set(schema.get("decision_fields", ())) != _DECISION_FIELDS
        or set(schema.get("review_locus_fields", ())) != _LOCUS_FIELDS
        or set(schema.get("scored_model_fields", ())) != _SCORED_MODEL_FIELDS
        or set(schema.get("decision_boundaries", ()))
        != {"comparison_not_observed", "content_comparison_available", "content_comparison_unavailable"}
    ):
        raise V7ContractError("v7 answer fields are invalid")
    if set(manifest.get("fixture_exclusion_globs", ())) != _SOURCE_ONLY_EXCLUSIONS:
        raise V7ContractError("v7 source-only exclusions are invalid")
    tasks = manifest.get("tasks")
    if not isinstance(tasks, list) or tuple(item.get("id") for item in tasks if isinstance(item, dict)) != TASK_IDS:
        raise V7ContractError("v7 task ids or order changed")
    for task in tasks:
        _validate_task(_mapping(task, "task"))
    digest = manifest.get("selection_preflight_sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest) or digest != selection_preflight_sha256(tasks):
        raise V7ContractError("v7 selection preflight is not frozen")


def selection_preflight_sha256(tasks: object | None = None) -> str:
    """Verify fresh no-model raw v7 selection evidence, never v5/v6 raw bytes."""
    try:
        value = json.loads(SELECTION_PREFLIGHT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise V7ContractError("v7 selection preflight is unreadable") from exc
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != 1
        or value.get("protocol") != "temporal-review-v7-selection-preflight"
        or value.get("model_execution") is not False
        or value.get("selection_method") != "fresh_independent_source_review_plus_raw_branch_diff"
        or not isinstance(value.get("captured_at_utc"), str)
        or not isinstance(value.get("toolchain"), Mapping)
        or not all(isinstance(value["toolchain"].get(key), str) for key in ("loomgraph_version", "claude_code_version"))
        or not isinstance(value.get("artifacts"), list)
    ):
        raise V7ContractError("v7 selection preflight is invalid")
    if tasks is None:
        try:
            manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise V7ContractError("v7 manifest is unreadable for selection validation") from exc
        tasks = manifest.get("tasks") if isinstance(manifest, dict) else None
    if not isinstance(tasks, list):
        raise V7ContractError("v7 selection manifest tasks are invalid")
    artifacts = value["artifacts"]
    if [item.get("task_id") for item in artifacts if isinstance(item, dict)] != list(TASK_IDS):
        raise V7ContractError("v7 selection preflight task order changed")
    for artifact in artifacts:
        _validate_selection_artifact(_mapping(artifact, "selection artifact"), tasks)
    return hashlib.sha256(SELECTION_PREFLIGHT_PATH.read_bytes()).hexdigest()


def contract(task_id: str) -> Contract:
    """Return one frozen v7 task without accepting prior cohort identifiers."""
    return _contract_from_tasks(task_id, load_manifest()["tasks"])


def _contract_from_tasks(task_id: str, tasks: list[object]) -> Contract:
    for task in tasks:
        if isinstance(task, dict) and task.get("id") == task_id:
            return Contract(task_id, task["refs"], task["backend"], task["expected_comparison"], task["oracle"], task["instruction_file"])
    raise V7ContractError(f"unknown v7 task: {task_id}")


def load_instruction(task_id: str) -> str:
    """Load a public task prompt while rejecting hidden-oracle leakage."""
    item = contract(task_id)
    relative = Path(item.instruction_file)
    if relative.is_absolute() or ".." in relative.parts:
        raise V7ContractError("instruction escapes v7 directory")
    try:
        value = (MANIFEST_PATH.parent / relative).read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise V7ContractError("v7 instruction is unreadable") from exc
    forbidden = ("oracle", "fixture-manifest", "CHANGELOG", "tests/", "evals/", "8e49e0", "d6ae4e", "a2f7c1", "e87b1e", "ImpactAnalyzer", "get_changed_files", "src/loomgraph/")
    if not value or any(term in value for term in forbidden):
        raise V7ContractError("v7 instruction leaks hidden contract material")
    if item.base_ref not in value or item.head_ref not in value or item.backend not in value:
        raise V7ContractError("v7 instruction lacks public task surface")
    return value


def canonical_head_identity(source_root: Path, path: str, qualname: str) -> tuple[str, str] | None:
    """Resolve one dotted Python class/function identity in frozen head."""
    if not path.startswith("src/") or not path.endswith(".py") or not qualname or "::" in qualname:
        return None
    try:
        tree = ast.parse((source_root / path).read_text(encoding="utf-8"))
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
    """Validate adapter-owned raw MCP comparison without normalizing it."""
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
    if not isinstance(content, Mapping) or any(content.get(key) != expected[key] for key in ("version", "scope", "status", "reason", "base_backend", "head_backend")):
        return _invalid("content_comparison_mismatch")
    return {"valid": True, "reason": None, "comparison": {"base_ref": snapshots["base"]["ref"], "head_ref": snapshots["head"]["ref"], "base_backend": content["base_backend"], "head_backend": content["head_backend"], "base_provisioned": snapshots["base"]["provisioned"], "head_provisioned": snapshots["head"]["provisioned"], "content_comparison": {"status": content["status"], "reason": content.get("reason")}}, "diff": diff}


def evaluate_answer(task_id: str, answer: object, *, condition: str, source_root: Path, raw_response: object | None = None) -> Outcome:
    """Evaluate schema, one AST identity, and adapter-owned raw trust."""
    item = contract(task_id)
    if condition not in {"baseline", "treatment"}:
        return _failed("condition must be baseline or treatment")
    if not isinstance(answer, Mapping) or set(answer) != _TOP_FIELDS:
        return _failed("answer top-level fields are invalid")
    failures: list[str] = []
    decision = answer.get("decision")
    if not isinstance(decision, Mapping) or set(decision) != _DECISION_FIELDS:
        failures.append("decision fields are invalid")
    elif decision.get("boundary") != item.oracle["boundary"][condition]:
        failures.append("decision boundary does not match the public condition rule")
    elif not _non_empty(decision.get("rationale")):
        failures.append("decision rationale is required")
    locus = answer.get("review_locus")
    if not isinstance(locus, Mapping) or set(locus) != _LOCUS_FIELDS:
        failures.append("review locus fields are invalid")
    else:
        path, qualname = locus.get("path"), locus.get("qualname")
        identity = canonical_head_identity(source_root, path, qualname) if isinstance(path, str) and isinstance(qualname, str) else None
        if identity is None:
            failures.append("review locus does not resolve in frozen head AST")
        expected = item.oracle["required_review_locus"]
        if identity != (expected["path"], expected["qualname"]):
            failures.append("v7 review identity is missing")
        if not _non_empty(locus.get("rationale")):
            failures.append("review locus rationale is required")
    if condition == "treatment":
        parsed = parse_raw_response(task_id, raw_response)
        if not parsed["valid"]:
            failures.append(f"treatment raw response is invalid: {parsed['reason']}")
        elif isinstance(decision, Mapping) and decision.get("boundary") != _boundary_for_raw(parsed):
            failures.append("decision boundary does not match selected raw response")
        elif not _raw_supports_identity(parsed["diff"], item.oracle["required_review_locus"]):
            failures.append("raw response does not support frozen treatment identity")
    return _passed() if not failures else _failed(*failures)


def _validate_task(task: Mapping[str, Any]) -> None:
    if task.get("id") not in TASK_IDS or task.get("task_class") != "temporal-review-v7":
        raise V7ContractError("v7 task identity is invalid")
    refs = _mapping(task.get("refs"), "refs")
    for side in ("base", "head"):
        ref = _mapping(refs.get(side), side)
        if ref.get("alias") != f"v7-{side}" or not isinstance(ref.get("commit_sha"), str) or not _SHA.fullmatch(ref["commit_sha"]):
            raise V7ContractError("v7 refs are invalid")
    expected = _mapping(task.get("expected_comparison"), "expected_comparison")
    expected_values = (("version", 1), ("scope", "same_backend_only"), ("status", "available"), ("reason", None), ("base_backend", "codeindex"), ("head_backend", "codeindex"))
    if task.get("backend") != "codeindex" or any(expected.get(key) != value for key, value in expected_values):
        raise V7ContractError("v7 comparison contract is invalid")
    oracle = _mapping(task.get("oracle"), "oracle")
    if _mapping(oracle.get("boundary"), "oracle.boundary") != {"baseline": "comparison_not_observed", "treatment": "content_comparison_available"}:
        raise V7ContractError("v7 public boundary rule is invalid")
    locus = _mapping(oracle.get("required_review_locus"), "review identity")
    if not _non_empty(locus.get("path")) or not _non_empty(locus.get("qualname")) or _mapping(locus.get("evidence_kind"), "identity evidence") != {"baseline": "source_text", "treatment": "content_delta"}:
        raise V7ContractError("v7 review identity evidence is invalid")


def _validate_selection_artifact(artifact: Mapping[str, Any], tasks: list[object]) -> None:
    task_id, relative, digest = artifact.get("task_id"), artifact.get("raw_response_path"), artifact.get("raw_sha256")
    if not isinstance(task_id, str) or not isinstance(relative, str) or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest) or digest in _PRIOR_SELECTION_RAW_SHA256 or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise V7ContractError("v7 selection preflight artifact metadata is invalid")
    raw_path = MANIFEST_PATH.parent / relative
    if not raw_path.is_file() or hashlib.sha256(raw_path.read_bytes()).hexdigest() != digest:
        raise V7ContractError("v7 selection preflight raw artifact hash mismatch")
    item = _contract_from_tasks(task_id, tasks)
    raw = _decode(raw_path.read_text(encoding="utf-8"))
    if raw is None or raw.get("success") is not True or not isinstance(raw.get("data"), Mapping):
        raise V7ContractError("v7 selection raw response is invalid")
    data = raw["data"]
    for side in ("base", "head"):
        snapshot = data.get(side)
        if not isinstance(snapshot, Mapping) or snapshot.get("ref") != item.refs[side]["commit_sha"] or snapshot.get("sha") != item.refs[side]["commit_sha"]:
            raise V7ContractError("v7 selection raw ref mismatch")
    diff = data.get("diff")
    content = diff.get("content_comparison") if isinstance(diff, Mapping) else None
    if not isinstance(content, Mapping) or any(content.get(key) != item.expected_comparison[key] for key in ("version", "scope", "status", "reason", "base_backend", "head_backend")) or not _raw_supports_identity(diff, item.oracle["required_review_locus"]):
        raise V7ContractError("v7 selection raw comparison or identity support mismatch")


def _raw_supports_identity(diff: object, locus: object) -> bool:
    if not isinstance(diff, Mapping) or not isinstance(locus, Mapping):
        return False
    content = diff.get("content_comparison")
    changed = content.get("changed", []) if isinstance(content, Mapping) else []
    return locus.get("evidence_kind", {}).get("treatment") == "content_delta" and any(isinstance(item, Mapping) and str(item.get("source_id", "")).split(":", 1)[0] == locus.get("path") and str(item.get("name", "")).endswith(str(locus.get("qualname"))) for item in changed or [])


def _boundary_for_raw(parsed: Mapping[str, Any]) -> str:
    return "content_comparison_available" if parsed["comparison"]["content_comparison"]["status"] == "available" else "content_comparison_unavailable"


def _mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise V7ContractError(f"{name} must be an object")
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
