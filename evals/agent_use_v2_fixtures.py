"""Independent fixture and answer contracts for agent-use v2.

The implementation is intentionally introduced after the contract tests.  The
public names below are the v2 adapter boundary; v1 observation oracles are not
imported here.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evals.capability_fixtures import MaterializedFixture, materialize_fixture

V2_FIXTURE_ID = "python-history"
V2_TASK_ID = "python-history-branch-diff-contract"
_EVALS_DIR = Path(__file__).resolve().parent
_MANIFEST_PATH = _EVALS_DIR / "agent-use-v2-fixture-manifest.json"
_INSTRUCTION_PATH = _EVALS_DIR / "agent-use-v2-python-history-instruction.txt"
_EXPECTED_CONTENT_SHA = "52a552f4426ed6773b3711f63a8024e382b11eb2b70ff8e15c585763d94e7667"
_EXPECTED_BASE_SHA = "11d6876d51425f64ac97ce2a52644c840b629917"
_EXPECTED_HEAD_SHA = "a270de36ee2af15d13b37fc14395cfae0d3435aa"
_EXPECTED_FINDING = {
    "kind": "broken_chain",
    "src": "app.handlers.keep_legacy",
    "tgt": "app.auth.legacy_token",
    "relation": "CALLS",
}
_ALLOWED_PROVISIONED = {"created", "reused", "rebuilt"}


class FixtureContractError(ValueError):
    """The reviewed v2 fixture or answer contract is malformed."""


@dataclass(frozen=True)
class OracleResult:
    """One task-specific oracle outcome and its machine-readable failures."""

    passed: bool
    failures: tuple[str, ...]


def load_v2_fixture_manifest() -> dict[str, Any]:
    """Load the reviewed v2 fixture manifest without executing the fixture."""
    with _MANIFEST_PATH.open(encoding="utf-8") as manifest_file:
        value = json.load(manifest_file)
    if not isinstance(value, dict):
        raise FixtureContractError("v2 fixture manifest must be an object")
    return value


def validate_v2_fixture_manifest(manifest: dict[str, Any]) -> None:
    """Reject drift in the versioned fixture, task, and independent oracle."""
    if manifest.get("schema_version") != 1:
        raise FixtureContractError("schema_version must be 1")
    if manifest.get("fixture_id") != V2_FIXTURE_ID:
        raise FixtureContractError("fixture_id must be python-history")
    if manifest.get("materializer") != "evals.capability_fixtures.materialize_fixture":
        raise FixtureContractError("materializer must name capability_fixtures.materialize_fixture")
    if manifest.get("content_sha") != _EXPECTED_CONTENT_SHA:
        raise FixtureContractError("content SHA does not match the frozen fixture")

    refs = _mapping(manifest.get("refs"), "refs")
    _validate_ref(refs, "base", "base", _EXPECTED_BASE_SHA)
    _validate_ref(refs, "head", "head", _EXPECTED_HEAD_SHA)

    if manifest.get("backend") != "codeindex":
        raise FixtureContractError("backend must be codeindex")
    task = _mapping(manifest.get("task"), "task")
    if task.get("id") != V2_TASK_ID:
        raise FixtureContractError("task.id is not the frozen v2 task")
    if task.get("class") != "temporal-structural-comparison":
        raise FixtureContractError("task.class is not temporal-structural-comparison")
    if task.get("instruction_file") != _INSTRUCTION_PATH.name:
        raise FixtureContractError("task.instruction_file is not the frozen instruction")
    if task.get("server_allowlist") != ["loomgraph_branch_diff"]:
        raise FixtureContractError("task.server_allowlist must contain only branch diff")
    if task.get("rg_single_query") is not False:
        raise FixtureContractError("task.rg_single_query must be false")

    oracle = _mapping(manifest.get("oracle"), "oracle")
    finding = _mapping(oracle.get("finding"), "oracle.finding")
    if any(finding.get(key) != value for key, value in _EXPECTED_FINDING.items()):
        raise FixtureContractError("oracle.finding does not match the frozen task fact")
    content = _mapping(oracle.get("content_comparison"), "oracle.content_comparison")
    expected_content = {
        "status": "available",
        "reason": None,
        "base_backend": "codeindex",
        "head_backend": "codeindex",
    }
    if any(content.get(key) != value for key, value in expected_content.items()):
        raise FixtureContractError("oracle.content_comparison is not the available L2 contract")
    if oracle.get("unavailable_is_not_unchanged") is not True:
        raise FixtureContractError("oracle must distinguish unavailable from unchanged")

    recording = _mapping(manifest.get("recording"), "recording")
    for phase in ("cold", "warm"):
        value = recording.get(phase)
        if not isinstance(value, list) or not value or not all(isinstance(item, str) for item in value):
            raise FixtureContractError(f"recording.{phase} must be a non-empty string list")


def materialize_v2_fixture(path: Path) -> MaterializedFixture:
    """Materialize and verify the exact Git fixture used by v2."""
    manifest = load_v2_fixture_manifest()
    validate_v2_fixture_manifest(manifest)
    fixture = materialize_fixture(V2_FIXTURE_ID, path)
    current_sha = _content_sha(path)
    if fixture.sha != current_sha or current_sha != _EXPECTED_CONTENT_SHA:
        raise FixtureContractError("materialized fixture content SHA drifted")
    if fixture.refs != {"base", "head"}:
        raise FixtureContractError("materialized fixture must expose only base and head refs")
    refs = manifest["refs"]
    assert isinstance(refs, dict)
    for ref in ("base", "head"):
        expected = refs[ref]
        assert isinstance(expected, dict)
        actual_sha = _git_rev_parse(path, f"{ref}^{{commit}}")
        if actual_sha != expected["commit_sha"]:
            raise FixtureContractError(f"{ref} commit SHA drifted")
        if _git_rev_parse(path, f"refs/tags/{ref}") != actual_sha:
            raise FixtureContractError(f"{ref} tag drifted")
    return fixture


def task_instruction() -> str:
    """Return the model-facing instruction without fixture-oracle leakage."""
    return _INSTRUCTION_PATH.read_text(encoding="utf-8").strip()


def evaluate_finding_answer(answer: object) -> OracleResult:
    """Evaluate the v2 finding independently of v1 path-oracle code."""
    if not isinstance(answer, Mapping):
        return _failed("answer must be an object")
    findings = answer.get("findings")
    if not isinstance(findings, list) or len(findings) != 1:
        return _failed("finding must contain exactly one item")
    finding = findings[0]
    if not isinstance(finding, Mapping):
        return _failed("finding item must be an object")
    if any(finding.get(key) != value for key, value in _EXPECTED_FINDING.items()):
        return _failed("finding does not match the task-specific broken-chain oracle")
    evidence = finding.get("evidence")
    if not isinstance(evidence, str) or not evidence.strip():
        return _failed("finding evidence must be a non-empty string")
    return _passed()


def evaluate_treatment_answer(answer: object) -> OracleResult:
    """Require the finding plus evidence-backed available comparison trust."""
    finding_result = evaluate_finding_answer(answer)
    failures = list(finding_result.failures)
    trust, trust_failures = _trust_mapping(answer)
    failures.extend(trust_failures)
    if trust is not None and trust.get("availability") != "available":
        failures.append("treatment trust.availability must be available")
    if trust is not None:
        comparison, comparison_failures = _comparison_mapping(trust.get("comparison"))
        failures.extend(comparison_failures)
        if comparison is not None:
            failures.extend(_validate_available_comparison(comparison))
    return _outcome(failures)


def evaluate_baseline_answer(answer: object) -> OracleResult:
    """Require the same task finding but an explicitly unavailable baseline."""
    finding_result = evaluate_finding_answer(answer)
    failures = list(finding_result.failures)
    trust, trust_failures = _trust_mapping(answer)
    failures.extend(trust_failures)
    if trust is not None and trust.get("availability") != "unavailable":
        failures.append("baseline trust.availability must be unavailable")
    if trust is not None and (
        "comparison" not in trust or trust.get("comparison") is not None
    ):
        failures.append("baseline comparison must be explicitly null")
    return _outcome(failures)


def evaluate_raw_branch_diff_response(response: object) -> OracleResult:
    """Validate the raw MCP branch-diff envelope against the v2 fixture."""
    failures: list[str] = []
    if not isinstance(response, Mapping) or response.get("success") is not True:
        return _failed("raw branch-diff response must have success=true")
    data = response.get("data")
    if not isinstance(data, Mapping):
        return _failed("raw branch-diff response data must be an object")
    for field, ref, sha in (
        ("base", "base", _EXPECTED_BASE_SHA),
        ("head", "head", _EXPECTED_HEAD_SHA),
    ):
        snapshot = data.get(field)
        if not isinstance(snapshot, Mapping):
            failures.append(f"raw response {field} snapshot is missing")
            continue
        if snapshot.get("ref") != ref or snapshot.get("sha") != sha:
            failures.append(f"raw response {field} ref or SHA does not match fixture")
        if not isinstance(snapshot.get("workspace"), str) or not snapshot["workspace"]:
            failures.append(f"raw response {field}.workspace is required")
        if snapshot.get("provisioned") not in _ALLOWED_PROVISIONED:
            failures.append(f"raw response {field}.provisioned is invalid")

    diff = data.get("diff")
    if not isinstance(diff, Mapping):
        return _outcome([*failures, "raw response diff is missing"])
    broken = diff.get("broken_chains")
    expected_broken = {
        "src": _EXPECTED_FINDING["src"],
        "tgt": _EXPECTED_FINDING["tgt"],
        "keywords": _EXPECTED_FINDING["relation"],
    }
    if not isinstance(broken, list) or len(broken) != 1 or broken[0] != expected_broken:
        failures.append("raw broken_chains does not match the task-specific oracle")
    content = diff.get("content_comparison")
    if not isinstance(content, Mapping):
        failures.append("raw content_comparison is missing")
    else:
        if content.get("status") != "available":
            failures.append("raw content_comparison.status must be available")
        if content.get("base_backend") != "codeindex" or content.get("head_backend") != "codeindex":
            failures.append("raw content_comparison backends must both be codeindex")
        if "reason" in content and content.get("reason") is not None:
            failures.append("available content_comparison.reason must be null")
    return _outcome(failures)


def _mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise FixtureContractError(f"{field} must be an object")
    return value


def _validate_ref(refs: dict[str, Any], name: str, tag: str, commit_sha: str) -> None:
    value = _mapping(refs.get(name), f"refs.{name}")
    if value.get("tag") != tag or value.get("commit_sha") != commit_sha:
        raise FixtureContractError(f"refs.{name} is not frozen to {tag}")


def _content_sha(path: Path) -> str:
    digest = hashlib.sha256()
    for source in sorted(
        item for item in path.rglob("*") if item.is_file() and ".git" not in item.parts
    ):
        digest.update(source.relative_to(path).as_posix().encode())
        digest.update(b"\0")
        digest.update(source.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _git_rev_parse(path: Path, ref: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--verify", ref],
            cwd=path,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise FixtureContractError(f"cannot resolve fixture ref {ref}") from exc
    return completed.stdout.strip()


def _failed(*failures: str) -> OracleResult:
    return OracleResult(passed=False, failures=tuple(failures))


def _passed() -> OracleResult:
    return OracleResult(passed=True, failures=())


def _outcome(failures: list[str]) -> OracleResult:
    return _passed() if not failures else OracleResult(False, tuple(failures))


def _trust_mapping(answer: object) -> tuple[Mapping[str, Any] | None, list[str]]:
    if not isinstance(answer, Mapping):
        return None, ["trust must be an object"]
    trust = answer.get("trust")
    if not isinstance(trust, Mapping):
        return None, ["trust must be an object"]
    return trust, []


def _comparison_mapping(value: object) -> tuple[Mapping[str, Any] | None, list[str]]:
    if not isinstance(value, Mapping):
        return None, ["trust.comparison must be an object"]
    return value, []


def _validate_available_comparison(comparison: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    expected = {
        "base_ref": "base",
        "head_ref": "head",
        "base_backend": "codeindex",
        "head_backend": "codeindex",
    }
    for field, value in expected.items():
        if comparison.get(field) != value:
            failures.append(f"trust.comparison.{field} does not match fixture")
    for field in ("base_provisioned", "head_provisioned"):
        if comparison.get(field) not in _ALLOWED_PROVISIONED:
            failures.append(f"trust.comparison.{field} is invalid")
    content, content_failures = _comparison_mapping(comparison.get("content_comparison"))
    failures.extend(content_failures)
    if content is not None:
        if content.get("status") != "available":
            failures.append("trust.comparison.content_comparison.status must be available")
        if "reason" not in content or content.get("reason") is not None:
            failures.append("trust.comparison.content_comparison.reason must be null")
    return failures
