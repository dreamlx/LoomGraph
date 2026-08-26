"""Independent v5 contract for temporal navigation evidence.

V5 scores only a model-visible comparison boundary and canonical review
identities.  Raw branch-diff trust belongs to the adapter.  Tool invocation
counts are intentionally not part of this contract or its validity outcome.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MANIFEST_PATH = Path(__file__).with_name("temporal-review-v5-fixture-manifest.json")
SELECTION_PREFLIGHT_PATH = Path(__file__).with_name("temporal-review-v5-selection-preflight.json")
TASK_IDS = (
    "v5-impact-caller-qualification-navigation",
    "v5-working-tree-diff-default-navigation",
)
_SHA = re.compile(r"^[0-9a-f]{40}$")
_V4_SELECTION_RAW_SHA256 = {
    "7bff9453d6c9bf84a2cb7ea3bbe4f73baec0eb1b470f9098db5d0a711b7da5d3",
    "e61690b254657e706073749cf675598ad6c9a7c9b760b7fce3ff16c1bd2aa2be",
}
_PROVISIONED = {"created", "reused", "rebuilt"}
_TOP_FIELDS = {"decision", "review_loci"}
_DECISION_FIELDS = {"boundary", "rationale"}
_LOCUS_FIELDS = {"path", "qualname", "rationale"}
_SCORED_MODEL_FIELDS = {
    "decision.boundary",
    "review_loci.path",
    "review_loci.qualname",
}
_SOURCE_ONLY_EXCLUSIONS = {
    "CHANGELOG.md",
    "customers/CHANGELOG.md",
    "docs/evals/**",
    "tests/**",
    "evals/**",
}


class V5ContractError(ValueError):
    """The independently registered v5 contract is malformed."""


@dataclass(frozen=True)
class Outcome:
    """Schema/identity/trust validity, without a tool-use-count score."""

    passed: bool
    failures: tuple[str, ...]


@dataclass(frozen=True)
class Contract:
    """Frozen task data used by the v5 materializer and adapter."""

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
    """Load and validate the immutable, independently registered v5 manifest."""
    value = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise V5ContractError("v5 manifest must be an object")
    validate_manifest(value)
    return value


def validate_manifest(manifest: Mapping[str, Any]) -> None:
    """Reject accidental pooling with v4 or extra model scoring dimensions."""
    if (
        manifest.get("schema_version") != 5
        or manifest.get("manifest_id") != "loomgraph-temporal-review-v5-navigation-evidence"
        or manifest.get("task_class") != "temporal-review-v5"
        or manifest.get("repository") != "loomgraph"
    ):
        raise V5ContractError("not the frozen v5 temporal-review manifest")
    lineage = _mapping(manifest.get("cohort_lineage"), "cohort_lineage")
    if lineage != {
        "cohort_id": "temporal-review-v5",
        "independent_from": "loomgraph-temporal-review-v4-navigation-evidence",
        "predecessor_evidence": "archive_only_not_pooled_or_rescored",
    }:
        raise V5ContractError("v5 cohort independence declaration is invalid")
    schema = _mapping(manifest.get("answer_schema"), "answer_schema")
    if (
        set(schema.get("top_level_fields", ())) != _TOP_FIELDS
        or set(schema.get("decision_fields", ())) != _DECISION_FIELDS
        or set(schema.get("review_locus_fields", ())) != _LOCUS_FIELDS
        or set(schema.get("scored_model_fields", ())) != _SCORED_MODEL_FIELDS
        or set(schema.get("decision_boundaries", ()))
        != {
            "comparison_not_observed",
            "content_comparison_available",
            "content_comparison_unavailable",
        }
    ):
        raise V5ContractError("v5 answer fields are invalid")
    if set(manifest.get("fixture_exclusion_globs", ())) != _SOURCE_ONLY_EXCLUSIONS:
        raise V5ContractError("v5 source-only exclusions are invalid")
    tasks = manifest.get("tasks")
    if (
        not isinstance(tasks, list)
        or tuple(task.get("id") for task in tasks if isinstance(task, dict)) != TASK_IDS
    ):
        raise V5ContractError("v5 task ids or order changed")
    for task in tasks:
        _validate_task(_mapping(task, "task"))
    selection_hash = manifest.get("selection_preflight_sha256")
    if (
        not isinstance(selection_hash, str)
        or not re.fullmatch(r"[0-9a-f]{64}", selection_hash)
        or selection_hash != selection_preflight_sha256(tasks)
    ):
        raise V5ContractError("v5 selection preflight is not frozen")


def selection_preflight_sha256(tasks: object | None = None) -> str:
    """Verify independently retained no-model raw branch-diff selection data."""
    try:
        value = json.loads(SELECTION_PREFLIGHT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise V5ContractError("v5 selection preflight is unreadable") from exc
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != 1
        or value.get("protocol") != "temporal-review-v5-selection-preflight"
        or value.get("model_execution") is not False
        or value.get("selection_method") != "independent_source_review_plus_fresh_raw_branch_diff"
        or not isinstance(value.get("captured_at_utc"), str)
        or not isinstance(value.get("toolchain"), Mapping)
        or not all(isinstance(value["toolchain"].get(key), str) for key in ("loomgraph_version", "claude_code_version"))
        or not isinstance(value.get("artifacts"), list)
    ):
        raise V5ContractError("v5 selection preflight is invalid")
    if tasks is None:
        try:
            manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise V5ContractError("v5 manifest is unreadable for selection validation") from exc
        tasks = manifest.get("tasks") if isinstance(manifest, dict) else None
    if not isinstance(tasks, list):
        raise V5ContractError("v5 selection manifest tasks are invalid")
    artifacts = value["artifacts"]
    if [artifact.get("task_id") for artifact in artifacts if isinstance(artifact, dict)] != list(TASK_IDS):
        raise V5ContractError("v5 selection preflight task order changed")
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise V5ContractError("v5 selection preflight artifact is invalid")
        relative = artifact.get("raw_response_path")
        digest = artifact.get("raw_sha256")
        if (
            not isinstance(relative, str)
            or not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or digest in _V4_SELECTION_RAW_SHA256
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
        ):
            raise V5ContractError("v5 selection preflight artifact metadata is invalid")
        raw_path = MANIFEST_PATH.parent / relative
        if not raw_path.is_file() or hashlib.sha256(raw_path.read_bytes()).hexdigest() != digest:
            raise V5ContractError("v5 selection preflight raw artifact hash mismatch")
        _validate_selection_raw(artifact["task_id"], raw_path, _contract_from_tasks(artifact["task_id"], tasks))
    return hashlib.sha256(SELECTION_PREFLIGHT_PATH.read_bytes()).hexdigest()


def contract(task_id: str) -> Contract:
    """Return one frozen v5 task without accepting any v4 identifier."""
    return _contract_from_tasks(task_id, load_manifest()["tasks"])


def _contract_from_tasks(task_id: str, tasks: list[object]) -> Contract:
    for task in tasks:
        if not isinstance(task, dict):
            continue
        if task["id"] == task_id:
            return Contract(
                task_id=task_id,
                refs=task["refs"],
                backend=task["backend"],
                expected_comparison=task["expected_comparison"],
                oracle=task["oracle"],
                instruction_file=task["instruction_file"],
            )
    raise V5ContractError(f"unknown v5 task: {task_id}")


def load_instruction(task_id: str) -> str:
    """Load a public task prompt while rejecting hidden-oracle leakage."""
    item = contract(task_id)
    relative = Path(item.instruction_file)
    if relative.is_absolute() or ".." in relative.parts:
        raise V5ContractError("instruction escapes v5 directory")
    value = (MANIFEST_PATH.parent / relative).read_text(encoding="utf-8").strip()
    forbidden = (
        "oracle",
        "fixture-manifest",
        "CHANGELOG",
        "tests/",
        "evals/",
        "8e49e0",
        "d6ae4e",
        "a2f7c1",
        "e87b1e",
        "ImpactAnalyzer",
        "get_changed_files",
        "src/loomgraph/",
    )
    if not value or any(term in value for term in forbidden):
        raise V5ContractError("v5 instruction leaks hidden contract material")
    if item.base_ref not in value or item.head_ref not in value or item.backend not in value:
        raise V5ContractError("v5 instruction lacks public task surface")
    return value


def canonical_head_identity(source_root: Path, path: str, qualname: str) -> tuple[str, str] | None:
    """Resolve exactly one dotted Python class/function identity in frozen head."""
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
        if (
            not isinstance(snapshot, Mapping)
            or snapshot.get("ref") != item.refs[side]["alias"]
            or snapshot.get("sha") != item.refs[side]["commit_sha"]
        ):
            return _invalid(f"{side}_ref_or_sha_mismatch")
        if snapshot.get("provisioned") not in _PROVISIONED or not isinstance(snapshot.get("workspace"), str):
            return _invalid(f"{side}_snapshot_invalid")
        snapshots[side] = snapshot
    diff = data.get("diff")
    content = diff.get("content_comparison") if isinstance(diff, Mapping) else None
    expected = item.expected_comparison
    if not isinstance(content, Mapping) or any(
        content.get(key) != expected[key]
        for key in ("version", "scope", "status", "reason", "base_backend", "head_backend")
    ):
        return _invalid("content_comparison_mismatch")
    return {
        "valid": True,
        "reason": None,
        "comparison": {
            "base_ref": snapshots["base"]["ref"],
            "head_ref": snapshots["head"]["ref"],
            "base_backend": content["base_backend"],
            "head_backend": content["head_backend"],
            "base_provisioned": snapshots["base"]["provisioned"],
            "head_provisioned": snapshots["head"]["provisioned"],
            "content_comparison": {"status": content["status"], "reason": content.get("reason")},
        },
        "diff": diff,
    }


def evaluate_answer(
    task_id: str,
    answer: object,
    *,
    condition: str,
    source_root: Path,
    raw_response: object | None = None,
) -> Outcome:
    """Evaluate only schema, public boundary, AST identities, and raw trust.

    This deliberately has no parameter or branch for invocation counts.  They
    may be retained by a runner as trace metadata, but cannot make an otherwise
    valid v5 observation invalid or stop this contract's evaluation.
    """
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
        if decision.get("boundary") != item.oracle["boundary"][condition]:
            failures.append("decision boundary does not match the public condition rule")
        if not _non_empty(decision.get("rationale")):
            failures.append("decision rationale is required")
    loci = answer.get("review_loci")
    if not isinstance(loci, list) or not loci or len(loci) > 3:
        failures.append("review_loci must contain one to three entries")
    else:
        observed: set[tuple[str, str]] = set()
        for locus in loci:
            if not isinstance(locus, Mapping) or set(locus) != _LOCUS_FIELDS:
                failures.append("review locus fields are invalid")
                continue
            path, qualname = locus.get("path"), locus.get("qualname")
            if not isinstance(path, str) or not isinstance(qualname, str):
                failures.append("review locus values are invalid")
                continue
            identity = canonical_head_identity(source_root, path, qualname)
            if identity is None:
                failures.append("review locus does not resolve in frozen head AST")
            elif identity in observed:
                failures.append("duplicate review locus")
            else:
                observed.add(identity)
            if not _non_empty(locus.get("rationale")):
                failures.append("review locus rationale is required")
        for required in item.oracle["required_review_loci"]:
            if (required["path"], required["qualname"]) not in observed:
                failures.append("required v5 review identity is missing")
    if condition == "treatment":
        parsed = parse_raw_response(task_id, raw_response)
        if not parsed["valid"]:
            failures.append(f"treatment raw response is invalid: {parsed['reason']}")
        elif isinstance(decision, Mapping) and decision.get("boundary") != _boundary_for_raw(parsed):
            failures.append("decision boundary does not match selected raw response")
        elif not _raw_supports_identities(parsed["diff"], item.oracle["required_review_loci"]):
            failures.append("raw response does not support frozen treatment identities")
    return _passed() if not failures else _failed(*failures)


def _raw_supports_identities(diff: object, required: object) -> bool:
    if not isinstance(diff, Mapping) or not isinstance(required, list):
        return False
    content = diff.get("content_comparison")
    changed = content.get("changed", []) if isinstance(content, Mapping) else []
    for locus in required:
        if not isinstance(locus, Mapping) or locus.get("evidence_kind", {}).get("treatment") != "content_delta":
            return False
        if not any(
            isinstance(item, Mapping)
            and str(item.get("source_id", "")).split(":", 1)[0] == locus["path"]
            and str(item.get("name", "")).endswith(locus["qualname"])
            for item in changed or []
        ):
            return False
    return True


def _boundary_for_raw(parsed: Mapping[str, Any]) -> str:
    status = parsed["comparison"]["content_comparison"]["status"]
    return "content_comparison_available" if status == "available" else "content_comparison_unavailable"


def _validate_task(task: Mapping[str, Any]) -> None:
    if task.get("id") not in TASK_IDS or task.get("task_class") != "temporal-review-v5":
        raise V5ContractError("v5 task identity is invalid")
    refs = _mapping(task.get("refs"), "refs")
    for side in ("base", "head"):
        ref = _mapping(refs.get(side), side)
        if ref.get("alias") != f"v5-{side}" or not isinstance(ref.get("commit_sha"), str) or not _SHA.fullmatch(ref["commit_sha"]):
            raise V5ContractError("v5 refs are invalid")
    expected = _mapping(task.get("expected_comparison"), "expected_comparison")
    if task.get("backend") != "codeindex" or any(
        expected.get(key) != value
        for key, value in (
            ("version", 1),
            ("scope", "same_backend_only"),
            ("status", "available"),
            ("reason", None),
            ("base_backend", "codeindex"),
            ("head_backend", "codeindex"),
        )
    ):
        raise V5ContractError("v5 comparison contract is invalid")
    oracle = _mapping(task.get("oracle"), "oracle")
    boundary = _mapping(oracle.get("boundary"), "oracle.boundary")
    if boundary != {"baseline": "comparison_not_observed", "treatment": "content_comparison_available"}:
        raise V5ContractError("v5 public boundary rule is invalid")
    loci = oracle.get("required_review_loci")
    if not isinstance(loci, list) or not loci:
        raise V5ContractError("v5 requires review identities")
    for locus in loci:
        value = _mapping(locus, "review identity")
        kinds = _mapping(value.get("evidence_kind"), "identity evidence")
        if (
            not _non_empty(value.get("path"))
            or not _non_empty(value.get("qualname"))
            or kinds != {"baseline": "source_text", "treatment": "content_delta"}
        ):
            raise V5ContractError("v5 identity evidence is invalid")


def _validate_selection_raw(task_id: str, raw_path: Path, item: Contract) -> None:
    """Bind each no-model source selection response to its v5 oracle.

    Selection invokes the command with immutable commit SHAs; cell execution
    invokes it through v5-base/v5-head tags, so these artifacts deliberately
    validate SHAs rather than later cell aliases.
    """
    raw = _decode(raw_path.read_text(encoding="utf-8"))
    if raw is None or raw.get("success") is not True or not isinstance(raw.get("data"), Mapping):
        raise V5ContractError("v5 selection raw response is invalid")
    data = raw["data"]
    for side in ("base", "head"):
        snapshot = data.get(side)
        if not isinstance(snapshot, Mapping) or snapshot.get("ref") != item.refs[side]["commit_sha"]:
            raise V5ContractError("v5 selection raw ref mismatch")
        if snapshot.get("sha") != item.refs[side]["commit_sha"]:
            raise V5ContractError("v5 selection raw sha mismatch")
    diff = data.get("diff")
    content = diff.get("content_comparison") if isinstance(diff, Mapping) else None
    expected = item.expected_comparison
    if not isinstance(content, Mapping) or any(
        content.get(key) != expected[key]
        for key in ("version", "scope", "status", "reason", "base_backend", "head_backend")
    ):
        raise V5ContractError("v5 selection raw comparison mismatch")
    if not _raw_supports_identities(diff, item.oracle["required_review_loci"]):
        raise V5ContractError("v5 selection raw identity support mismatch")


def _mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise V5ContractError(f"{name} must be an object")
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
