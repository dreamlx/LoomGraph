"""Independent contract helpers for the temporal-review product pilot.

This module deliberately owns a small review-decision contract rather than
reusing the v1 path oracle or graph-resolution answer shape.  It only reads
the versioned manifest/instructions and validates already-produced JSON
objects; it never clones a repository, invokes a model, or runs LoomGraph.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TEMPORAL_REVIEW_SCHEMA_VERSION = 1
TEMPORAL_REVIEW_MANIFEST_ID = "loomgraph-temporal-review"
TEMPORAL_REVIEW_TASK_IDS = (
    "impact-low-resolution-review",
    "sparse-risk-review",
    "sparse-risk-codegraph-uncertainty",
)
TEMPORAL_REVIEW_MANIFEST_PATH = (
    Path(__file__).resolve().parent / "temporal-review-fixture-manifest.json"
)
TEMPORAL_REVIEW_INSTRUCTION_DIR = (
    Path(__file__).resolve().parent / "temporal-review-instructions"
)

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_ALLOWED_BACKENDS = {"codeindex", "codegraph"}
_ALLOWED_PROVISIONED = {"created", "reused", "rebuilt"}
_ALLOWED_CONTENT_STATUSES = {"available", "partial", "unavailable"}
_REQUIRED_EXCLUSION_GLOBS = {
    "CHANGELOG.md",
    "customers/CHANGELOG.md",
    "docs/evals/**",
    "tests/**",
    "evals/**",
}
_REQUIRED_TOP_LEVEL_FIELDS = {"decision", "review_loci", "trust"}
_REQUIRED_REVIEW_LOCUS_FIELDS = {"symbol", "change", "evidence"}
_REQUIRED_TRUST_FIELDS = {"availability", "comparison"}
_REQUIRED_COMPARISON_FIELDS = {
    "base_ref",
    "head_ref",
    "base_backend",
    "head_backend",
    "base_provisioned",
    "head_provisioned",
    "content_comparison",
}
_REQUIRED_CONTENT_FIELDS = {"status", "reason"}
_FORBIDDEN_INSTRUCTION_TERMS = (
    "oracle",
    "fixture-manifest",
    "CHANGELOG",
    "tests/",
    "evals/",
    "L2",
    "path oracle",
    "graph resolution",
    "graph-resolution",
)


class FixtureContractError(ValueError):
    """The reviewed temporal fixture or answer contract is malformed."""


@dataclass(frozen=True)
class OracleResult:
    """One contract outcome and its machine-readable failures."""

    passed: bool
    failures: tuple[str, ...]


@dataclass(frozen=True)
class TemporalReviewTask:
    """The validated, task-specific subset of the review manifest."""

    task_id: str
    task_class: str
    instruction_file: str
    refs: Mapping[str, Mapping[str, str]]
    backend: str
    expected_comparison: Mapping[str, Any]
    oracle: Mapping[str, Any]


@dataclass(frozen=True)
class TemporalReviewContract:
    """Runner-facing view of one frozen task contract."""

    task_id: str
    base_ref: str
    head_ref: str
    backend: str
    comparison_status: str
    comparison_reason: str | None
    task_class: str
    instruction_file: str
    refs: Mapping[str, Mapping[str, str]]
    expected_comparison: Mapping[str, Any]
    oracle: Mapping[str, Any]


def load_temporal_review_manifest() -> dict[str, Any]:
    """Load the versioned manifest without materializing or cloning a fixture."""
    try:
        value = json.loads(TEMPORAL_REVIEW_MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FixtureContractError("cannot load temporal-review manifest") from exc
    if not isinstance(value, dict):
        raise FixtureContractError("temporal-review manifest must be an object")
    return value


def validate_temporal_review_manifest(manifest: Mapping[str, Any]) -> None:
    """Validate all frozen refs, backend/L2 expectations, and oracle shape."""
    if not isinstance(manifest, Mapping):
        raise FixtureContractError("temporal-review manifest must be an object")
    if manifest.get("schema_version") != TEMPORAL_REVIEW_SCHEMA_VERSION:
        raise FixtureContractError("schema_version must be 1")
    if manifest.get("manifest_id") != TEMPORAL_REVIEW_MANIFEST_ID:
        raise FixtureContractError("manifest_id is not the frozen temporal-review manifest")
    if manifest.get("repository") != "loomgraph":
        raise FixtureContractError("repository must be loomgraph")
    if manifest.get("task_class") != "temporal-review":
        raise FixtureContractError("task_class must be temporal-review")

    answer_schema = _mapping(manifest.get("answer_schema"), "answer_schema")
    if set(answer_schema.get("top_level_fields", ())) != _REQUIRED_TOP_LEVEL_FIELDS:
        raise FixtureContractError("answer_schema top-level fields must be decision/review_loci/trust")
    if set(answer_schema.get("review_locus_fields", ())) != _REQUIRED_REVIEW_LOCUS_FIELDS:
        raise FixtureContractError("answer_schema review locus fields are malformed")
    if set(answer_schema.get("trust_fields", ())) != _REQUIRED_TRUST_FIELDS:
        raise FixtureContractError("answer_schema trust fields are malformed")

    exclusions = _string_sequence(manifest.get("fixture_exclusion_globs"))
    if exclusions is None:
        raise FixtureContractError("fixture_exclusion_globs must be a non-empty string list")
    if not _REQUIRED_EXCLUSION_GLOBS.issubset(exclusions):
        raise FixtureContractError("fixture exclusions must protect release, docs, tests, and evals")

    tasks = manifest.get("tasks")
    if not isinstance(tasks, list) or len(tasks) != len(TEMPORAL_REVIEW_TASK_IDS):
        raise FixtureContractError("manifest must freeze exactly three temporal-review tasks")
    observed_ids: list[str] = []
    for task_value in tasks:
        task = _mapping(task_value, "task")
        task_id = task.get("id")
        if not isinstance(task_id, str):
            raise FixtureContractError("task.id must be a string")
        observed_ids.append(task_id)
        _validate_task(task)
    if tuple(observed_ids) != TEMPORAL_REVIEW_TASK_IDS:
        raise FixtureContractError("tasks must remain in the frozen order")


def get_temporal_review_task(task_id: str) -> TemporalReviewTask:
    """Return one validated task from the frozen manifest."""
    manifest = load_temporal_review_manifest()
    validate_temporal_review_manifest(manifest)
    tasks = manifest["tasks"]
    assert isinstance(tasks, list)
    for value in tasks:
        task = _mapping(value, "task")
        if task.get("id") == task_id:
            refs = _mapping(task["refs"], f"{task_id}.refs")
            return TemporalReviewTask(
                task_id=task_id,
                task_class=task["task_class"],
                instruction_file=task["instruction_file"],
                refs=refs,
                backend=task["backend"],
                expected_comparison=task["expected_comparison"],
                oracle=task["oracle"],
            )
    raise FixtureContractError(f"unknown temporal-review task: {task_id}")


def load_temporal_review_contract(task_id: str) -> TemporalReviewContract:
    """Return the compact contract needed by a temporal-review runner.

    ``base_ref`` and ``head_ref`` are the model/tool aliases, while the frozen
    Git SHAs remain available under ``refs`` for raw-response validation and
    audit recording.
    """
    task = get_temporal_review_task(task_id)
    return TemporalReviewContract(
        task_id=task.task_id,
        base_ref=task.refs["base"]["alias"],
        head_ref=task.refs["head"]["alias"],
        backend=task.backend,
        comparison_status=task.expected_comparison["status"],
        comparison_reason=task.expected_comparison["reason"],
        task_class=task.task_class,
        instruction_file=task.instruction_file,
        refs=task.refs,
        expected_comparison=task.expected_comparison,
        oracle=task.oracle,
    )


def load_temporal_review_instruction(task_id: str) -> str:
    """Load a model-facing instruction after validating its leakage boundary."""
    task = get_temporal_review_task(task_id)
    relative = Path(task.instruction_file)
    if relative.is_absolute() or ".." in relative.parts:
        raise FixtureContractError("instruction_file must remain inside temporal-review-instructions")
    instruction_path = TEMPORAL_REVIEW_MANIFEST_PATH.parent / relative
    try:
        instruction = instruction_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise FixtureContractError(f"cannot load instruction for {task_id}") from exc
    _validate_instruction(task, instruction)
    return instruction


def task_instruction(task_id: str) -> str:
    """Compatibility alias for the model-facing task instruction."""
    return load_temporal_review_instruction(task_id)


def parse_temporal_review_raw_response(task_id: str, raw_response: object) -> dict[str, Any]:
    """Parse one raw branch-diff response against the task's frozen trust contract.

    The returned ``comparison`` is deliberately limited to the fields that may
    be copied into the structured answer.  Snapshot SHA/workspace values are
    retained separately as raw evidence, but are not answer fields.
    """
    task = get_temporal_review_task(task_id)
    raw = _decode_json_object(raw_response)
    if raw is None:
        return _invalid_raw("raw_response_malformed")
    if raw.get("success") is not True:
        return _invalid_raw("raw_response_not_success")
    data = raw.get("data")
    if not isinstance(data, Mapping):
        return _invalid_raw("raw_response_missing_data")

    snapshots: dict[str, Mapping[str, Any]] = {}
    for side in ("base", "head"):
        snapshot = data.get(side)
        if not isinstance(snapshot, Mapping):
            return _invalid_raw(f"{side}_snapshot_missing")
        expected_ref = task.refs[side]["alias"]
        if snapshot.get("ref") != expected_ref:
            return _invalid_raw(f"{side}_ref_mismatch")
        if snapshot.get("sha") != task.refs[side]["commit_sha"]:
            return _invalid_raw(f"{side}_sha_mismatch")
        if not _non_empty_string(snapshot.get("workspace")):
            return _invalid_raw(f"{side}_workspace_missing")
        if snapshot.get("provisioned") not in _ALLOWED_PROVISIONED:
            return _invalid_raw(f"{side}_provisioning_invalid")
        snapshots[side] = snapshot

    diff = data.get("diff")
    if not isinstance(diff, Mapping):
        return _invalid_raw("raw_response_missing_diff")
    content = diff.get("content_comparison")
    if not isinstance(content, Mapping):
        return _invalid_raw("content_comparison_missing")
    expected = task.expected_comparison
    if content.get("base_backend") != expected["base_backend"]:
        return _invalid_raw("base_backend_mismatch")
    if content.get("head_backend") != expected["head_backend"]:
        return _invalid_raw("head_backend_mismatch")
    if content.get("status") != expected["status"]:
        return _invalid_raw("content_comparison_status_mismatch")
    if content.get("reason") != expected["reason"]:
        return _invalid_raw("content_comparison_reason_mismatch")

    comparison = _comparison_from_raw(task, snapshots, content)
    return {
        "valid": True,
        "reason": None,
        "comparison": comparison,
        "base_sha": snapshots["base"]["sha"],
        "head_sha": snapshots["head"]["sha"],
        "base_workspace": snapshots["base"]["workspace"],
        "head_workspace": snapshots["head"]["workspace"],
        "broken_chains": diff.get("broken_chains", []),
        "duration_seconds": data.get("duration_seconds"),
    }


def evaluate_raw_temporal_review_response(task_id: str, raw_response: object) -> OracleResult:
    """Return a machine-readable result for one raw branch-diff response."""
    parsed = parse_temporal_review_raw_response(task_id, raw_response)
    if parsed["valid"]:
        return _passed()
    return _failed(str(parsed["reason"]))


def evaluate_raw_response(task_id: str, raw_response: object) -> OracleResult:
    """Short alias used by pilot runners and contract tests."""
    return evaluate_raw_temporal_review_response(task_id, raw_response)


def evaluate_baseline_answer(task_id: str, answer: object) -> OracleResult:
    """Validate a text-only answer with an explicitly unavailable comparison."""
    task = get_temporal_review_task(task_id)
    failures, trust = _validate_answer(task, answer)
    if trust is not None:
        if trust.get("availability") != "unavailable":
            failures.append("baseline trust.availability must be unavailable")
        if trust.get("comparison") is not None:
            failures.append("baseline trust.comparison must be null")
    return _outcome(failures)


def evaluate_treatment_answer(
    task_id: str,
    answer: object,
    raw_response: object | None = None,
) -> OracleResult:
    """Validate a treatment answer and align its trust fields with raw MCP evidence."""
    task = get_temporal_review_task(task_id)
    failures, trust = _validate_answer(task, answer)
    if trust is not None:
        if trust.get("availability") != "available":
            failures.append("treatment trust.availability must be available")
        comparison = trust.get("comparison")
        if not isinstance(comparison, Mapping):
            failures.append("treatment trust.comparison must be an object")
        elif raw_response is None:
            failures.append("treatment raw response is required")
        else:
            parsed = parse_temporal_review_raw_response(task_id, raw_response)
            if not parsed["valid"]:
                failures.append(f"raw response invalid: {parsed['reason']}")
            elif comparison != parsed["comparison"]:
                failures.append("treatment trust.comparison does not match raw response")
    return _outcome(failures)


def evaluate_review_answer(
    task_id: str,
    answer: object,
    *,
    condition: str,
    raw_response: object | None = None,
) -> OracleResult:
    """Evaluate a baseline or treatment answer under the explicit condition."""
    if condition == "baseline":
        return evaluate_baseline_answer(task_id, answer)
    if condition == "treatment":
        return evaluate_treatment_answer(task_id, answer, raw_response)
    return _failed("condition must be baseline or treatment")


def evaluate_temporal_review_answer(
    payload: object,
    condition: str,
    contract: TemporalReviewContract | str,
    raw_response: object | None = None,
) -> OracleResult:
    """Unified runner-facing evaluator.

    ``contract`` may be a value returned by
    :func:`load_temporal_review_contract` or a task id for convenience.
    ``raw_response`` is required for treatment and ignored for baseline.
    """
    task_id = contract.task_id if isinstance(contract, TemporalReviewContract) else contract
    return evaluate_review_answer(
        task_id,
        payload,
        condition=condition,
        raw_response=raw_response,
    )


def _validate_task(task: Mapping[str, Any]) -> None:
    task_id = task.get("id")
    if task_id not in TEMPORAL_REVIEW_TASK_IDS:
        raise FixtureContractError(f"unknown temporal-review task: {task_id}")
    if task.get("task_class") != "temporal-review":
        raise FixtureContractError(f"{task_id}.task_class must be temporal-review")

    instruction_file = task.get("instruction_file")
    if not isinstance(instruction_file, str):
        raise FixtureContractError(f"{task_id}.instruction_file must be a string")
    expected_instruction = f"temporal-review-instructions/{task_id}.txt"
    if instruction_file != expected_instruction:
        raise FixtureContractError(f"{task_id}.instruction_file is not frozen")

    refs = _mapping(task.get("refs"), f"{task_id}.refs")
    if set(refs) != {"base", "head"}:
        raise FixtureContractError(f"{task_id}.refs must contain base and head")
    for side in ("base", "head"):
        ref = _mapping(refs.get(side), f"{task_id}.refs.{side}")
        expected_alias = f"review-{side}"
        if ref.get("alias") != expected_alias:
            raise FixtureContractError(
                f"{task_id}.refs.{side}.alias must be {expected_alias}"
            )
        if not isinstance(ref.get("commit_sha"), str) or not _SHA_RE.fullmatch(ref["commit_sha"]):
            raise FixtureContractError(f"{task_id}.refs.{side}.commit_sha must be a Git SHA")

    backend = task.get("backend")
    if backend not in _ALLOWED_BACKENDS:
        raise FixtureContractError(f"{task_id}.backend is unsupported")
    expected = _mapping(task.get("expected_comparison"), f"{task_id}.expected_comparison")
    if set(expected) != {"status", "reason", "base_backend", "head_backend"}:
        raise FixtureContractError(f"{task_id}.expected_comparison fields are malformed")
    if expected["status"] not in _ALLOWED_CONTENT_STATUSES:
        raise FixtureContractError(f"{task_id}.expected_comparison.status is invalid")
    if expected["base_backend"] != backend or expected["head_backend"] != backend:
        raise FixtureContractError(f"{task_id} expected backends must match task backend")
    if expected["status"] == "available" and expected["reason"] is not None:
        raise FixtureContractError(f"{task_id} available comparison reason must be null")
    if expected["status"] == "unavailable" and not _non_empty_string(expected["reason"]):
        raise FixtureContractError(f"{task_id} unavailable comparison needs a reason")

    oracle = _mapping(task.get("oracle"), f"{task_id}.oracle")
    if set(oracle) != {"required_review_loci", "required_decision_phrases"}:
        raise FixtureContractError(f"{task_id}.oracle fields are malformed")
    loci = oracle["required_review_loci"]
    if not isinstance(loci, list) or not loci:
        raise FixtureContractError(f"{task_id}.oracle.required_review_loci must be non-empty")
    for locus_value in loci:
        locus = _mapping(locus_value, f"{task_id}.oracle.required_review_loci")
        if set(locus) != {"symbol", "change"}:
            raise FixtureContractError(f"{task_id} oracle locus fields are malformed")
        if not _non_empty_string(locus["symbol"]) or not _non_empty_string(locus["change"]):
            raise FixtureContractError(f"{task_id} oracle locus values must be non-empty")
    phrases = oracle["required_decision_phrases"]
    if _string_list(phrases) is None:
        raise FixtureContractError(f"{task_id}.oracle.required_decision_phrases must be a string list")


def _validate_instruction(task: TemporalReviewTask, instruction: str) -> None:
    if not instruction:
        raise FixtureContractError(f"{task.task_id} instruction is empty")
    for term in _FORBIDDEN_INSTRUCTION_TERMS:
        if term in instruction:
            raise FixtureContractError(f"{task.task_id} instruction leaks forbidden term {term!r}")
    if task.refs["base"]["alias"] not in instruction or task.refs["head"]["alias"] not in instruction:
        raise FixtureContractError(f"{task.task_id} instruction must expose base/head aliases")
    if task.backend not in instruction:
        raise FixtureContractError(f"{task.task_id} instruction must expose the backend")
    if any(
        locus["symbol"] in instruction
        for locus in task.oracle["required_review_loci"]
        if isinstance(locus, Mapping)
    ):
        raise FixtureContractError(f"{task.task_id} instruction leaks an oracle review locus")
    if task.refs["base"]["commit_sha"] in instruction or task.refs["head"]["commit_sha"] in instruction:
        raise FixtureContractError(f"{task.task_id} instruction leaks a frozen SHA")
    if set(_extract_top_level_schema_fields(instruction)) != _REQUIRED_TOP_LEVEL_FIELDS:
        raise FixtureContractError(f"{task.task_id} instruction must expose only the answer top-level fields")


def _validate_answer(task: TemporalReviewTask, answer: object) -> tuple[list[str], Mapping[str, Any] | None]:
    failures: list[str] = []
    if not isinstance(answer, Mapping):
        return ["answer must be an object"], None
    if set(answer) != _REQUIRED_TOP_LEVEL_FIELDS:
        failures.append("answer top-level fields must be exactly decision/review_loci/trust")

    decision = answer.get("decision")
    if not _non_empty_string(decision):
        failures.append("decision must be a non-empty string")
    else:
        phrases = task.oracle["required_decision_phrases"]
        for phrase in phrases:
            if phrase not in decision:
                failures.append(f"decision is missing required phrase: {phrase}")

    loci = answer.get("review_loci")
    if not isinstance(loci, list) or not loci:
        failures.append("review_loci must be a non-empty list")
    else:
        seen: set[str] = set()
        for index, value in enumerate(loci):
            if not isinstance(value, Mapping):
                failures.append(f"review_loci[{index}] must be an object")
                continue
            if set(value) != _REQUIRED_REVIEW_LOCUS_FIELDS:
                failures.append(f"review_loci[{index}] fields are malformed")
                continue
            if not all(_non_empty_string(value.get(field)) for field in _REQUIRED_REVIEW_LOCUS_FIELDS):
                failures.append(f"review_loci[{index}] values must be non-empty strings")
            symbol = value.get("symbol")
            if isinstance(symbol, str):
                seen.add(symbol)
        for required in task.oracle["required_review_loci"]:
            if required["symbol"] not in seen:
                failures.append(f"required review locus missing: {required['symbol']}")
            elif not any(
                value.get("symbol") == required["symbol"] and value.get("change") == required["change"]
                for value in loci
                if isinstance(value, Mapping)
            ):
                failures.append(f"required review locus change missing: {required['symbol']}")

    trust = answer.get("trust")
    if not isinstance(trust, Mapping):
        failures.append("trust must be an object")
        trust_result: Mapping[str, Any] | None = None
    else:
        trust_result = trust
        if set(trust) != _REQUIRED_TRUST_FIELDS:
            failures.append("trust fields must be exactly availability/comparison")
        availability = trust.get("availability")
        if availability not in {"available", "unavailable"}:
            failures.append("trust.availability must be available or unavailable")
        comparison = trust.get("comparison")
        if availability == "available":
            failures.extend(_validate_answer_comparison(task, comparison))
        elif availability == "unavailable" and comparison is not None:
            failures.append("unavailable trust.comparison must be null")
    return failures, trust_result


def _validate_answer_comparison(task: TemporalReviewTask, comparison: object) -> list[str]:
    if not isinstance(comparison, Mapping):
        return ["available trust.comparison must be an object"]
    failures: list[str] = []
    if set(comparison) != _REQUIRED_COMPARISON_FIELDS:
        failures.append("trust.comparison fields are malformed")
        return failures
    expected_refs = task.refs
    expected = {
        "base_ref": expected_refs["base"]["alias"],
        "head_ref": expected_refs["head"]["alias"],
        "base_backend": task.backend,
        "head_backend": task.backend,
    }
    for field, expected_value in expected.items():
        if comparison.get(field) != expected_value:
            failures.append(f"trust.comparison.{field} does not match the fixture")
    for field in ("base_provisioned", "head_provisioned"):
        if comparison.get(field) not in _ALLOWED_PROVISIONED:
            failures.append(f"trust.comparison.{field} is invalid")
    content = comparison.get("content_comparison")
    if not isinstance(content, Mapping):
        failures.append("trust.comparison.content_comparison must be an object")
    elif set(content) != _REQUIRED_CONTENT_FIELDS:
        failures.append("trust.comparison.content_comparison fields are malformed")
    else:
        expected_content = task.expected_comparison
        if content.get("status") != expected_content["status"]:
            failures.append("trust.comparison.content_comparison.status does not match the fixture")
        if content.get("reason") != expected_content["reason"]:
            failures.append("trust.comparison.content_comparison.reason does not match the fixture")
    return failures


def _comparison_from_raw(
    task: TemporalReviewTask,
    snapshots: Mapping[str, Mapping[str, Any]],
    content: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "base_ref": snapshots["base"]["ref"],
        "head_ref": snapshots["head"]["ref"],
        "base_backend": content["base_backend"],
        "head_backend": content["head_backend"],
        "base_provisioned": snapshots["base"]["provisioned"],
        "head_provisioned": snapshots["head"]["provisioned"],
        "content_comparison": {
            "status": content["status"],
            "reason": content.get("reason"),
        },
    }


def _decode_json_object(value: object) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return None
    return decoded if isinstance(decoded, dict) else None


def _extract_top_level_schema_fields(instruction: str) -> list[str]:
    # The instruction is intentionally plain text, so this checks the exact
    # schema keys without parsing prose or treating model output as trusted.
    return [field for field in _REQUIRED_TOP_LEVEL_FIELDS if f'"{field}"' in instruction]


def _mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise FixtureContractError(f"{field} must be an object")
    return value


def _string_sequence(value: object) -> list[str] | None:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) for item in value):
        return None
    return value


def _string_list(value: object) -> list[str] | None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None
    return value


def _non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _invalid_raw(reason: str) -> dict[str, Any]:
    return {"valid": False, "reason": reason}


def _failed(*failures: str) -> OracleResult:
    return OracleResult(passed=False, failures=tuple(failures))


def _passed() -> OracleResult:
    return OracleResult(passed=True, failures=())


def _outcome(failures: list[str]) -> OracleResult:
    return _passed() if not failures else OracleResult(False, tuple(failures))
