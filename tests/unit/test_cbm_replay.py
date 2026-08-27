"""Offline-only contract tests for the ADR-017 CBM discovery spike."""

from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import subprocess
from pathlib import Path

from loomgraph.core.cbm_replay import load_cbm_replay, replay_cbm_capability

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "cbm-discovery-replay-v1.json"
SOURCE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "cbm-synthetic-source-v1.py"


def _replay() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _rehash_response(replay: dict[str, object]) -> None:
    response = replay["response"]
    replay["response_sha256"] = hashlib.sha256(
        json.dumps(response, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _write_replay_with_source(
    tmp_path: Path,
    *,
    fixture: str = "source.py",
    source_bytes: bytes | None = None,
) -> Path:
    source_bytes = SOURCE_PATH.read_bytes() if source_bytes is None else source_bytes
    source_path = tmp_path / fixture
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(source_bytes)

    replay = _replay()
    source = replay["source"]
    assert isinstance(source, dict)
    source["fixture"] = fixture
    source["input_sha256"] = hashlib.sha256(source_bytes).hexdigest()
    replay_path = tmp_path / "replay.json"
    replay_path.write_text(json.dumps(replay), encoding="utf-8")
    return replay_path


def _assert_native_unavailable(plan: dict[str, object], reason: str) -> None:
    assert plan["availability"] == "unavailable"
    assert plan["recommended_path"] == "native"
    assert plan["replay"] == {"mode": "offline", "execution": "provider_not_invoked"}
    fallback = plan["fallback"]
    assert isinstance(fallback, dict)
    assert fallback["reason"] == reason


def test_verified_synthetic_replay_declares_only_cbm_structural_candidates() -> None:
    plan = load_cbm_replay(FIXTURE_PATH)

    assert hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest() == plan["replay"]["input_sha256"]
    assert plan["recommended_path"] == "provider"
    assert plan["availability"] == "available"
    assert plan["provider"] == {
        "id": "cbm",
        "version": "0.10.8",
        "operation": "structural_navigation",
        "evidence_kind": "structural_candidate",
        "snapshot_scope": "provider_index",
        "snapshot_identity": None,
        "index_owner": "provider",
        "data_scope": "local",
        "write_authority": "none",
    }
    assert plan["replay"] == {
        "mode": "offline",
        "execution": "provider_not_invoked",
        "stratum": "claude-code-first/local-cbm-0.10.8/synthetic-fixture/read-only-structural-candidate/no-model",
        "input_sha256": "24236fb4009f65c693919c1ce569d632aac8b415e039f3d55b14b619711f9b79",
        "response_sha256": "f2a58f7f4c91396eac77425150eb7bd79a8ec6367fb60129d10325b5da57012f",
    }
    assert plan["execution_boundary"] == {
        "adapter": "offline_replay_only",
        "provider_routing": "not_enabled",
        "provider_owned_index": "not_created_or_rebuilt",
    }


def test_replay_never_calls_cbm_or_opens_a_database(monkeypatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("offline replay must have no process or database side effect")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)

    assert load_cbm_replay(FIXTURE_PATH)["availability"] == "available"


def test_replay_requires_an_artifact_path_to_verify_source_bytes() -> None:
    _assert_native_unavailable(replay_cbm_capability(_replay()), "source_fixture_unverified")


def test_unresolvable_replay_artifact_fails_closed(monkeypatch) -> None:
    def unresolvable(*args: object, **kwargs: object) -> Path:
        raise RuntimeError("symlink loop")

    monkeypatch.setattr(Path, "resolve", unresolvable)

    _assert_native_unavailable(
        replay_cbm_capability(_replay(), replay_path=FIXTURE_PATH), "replay_unreadable"
    )


def test_source_fixture_missing_or_outside_replay_fails_closed(tmp_path: Path) -> None:
    replay_path = _write_replay_with_source(tmp_path)
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    source = replay["source"]
    assert isinstance(source, dict)
    source["fixture"] = "missing.py"
    replay_path.write_text(json.dumps(replay), encoding="utf-8")
    _assert_native_unavailable(load_cbm_replay(replay_path), "source_fixture_missing")

    replay_path = _write_replay_with_source(tmp_path)
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    source = replay["source"]
    assert isinstance(source, dict)
    source["fixture"] = "../outside.py"
    replay_path.write_text(json.dumps(replay), encoding="utf-8")
    _assert_native_unavailable(load_cbm_replay(replay_path), "source_fixture_outside_replay")


def test_unreadable_source_fixture_fails_closed(tmp_path: Path) -> None:
    replay_path = _write_replay_with_source(tmp_path)
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    source = replay["source"]
    assert isinstance(source, dict)
    source["fixture"] = "bad\x00path"
    replay_path.write_text(json.dumps(replay), encoding="utf-8")

    _assert_native_unavailable(load_cbm_replay(replay_path), "source_fixture_unreadable")


def test_changed_source_or_declared_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    replay_path = _write_replay_with_source(tmp_path)
    (tmp_path / "source.py").write_text("replacement\n", encoding="utf-8")
    _assert_native_unavailable(load_cbm_replay(replay_path), "source_hash_mismatch")

    replay_path = _write_replay_with_source(tmp_path)
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    source = replay["source"]
    assert isinstance(source, dict)
    source["input_sha256"] = "0" * 64
    replay_path.write_text(json.dumps(replay), encoding="utf-8")
    _assert_native_unavailable(load_cbm_replay(replay_path), "source_hash_mismatch")


def test_missing_provider_version_timeout_empty_or_unknown_capability_fail_closed() -> None:
    replay = _replay()
    del replay["provider"]
    assert replay_cbm_capability(replay)["fallback"]["reason"] == "provider_unavailable"

    replay = _replay()
    response = replay["response"]
    assert isinstance(response, dict)
    response["provider_version"] = "9.9.9"
    _rehash_response(replay)
    assert replay_cbm_capability(replay)["fallback"]["reason"] == "provider_version_mismatch"

    replay = _replay()
    response = replay["response"]
    assert isinstance(response, dict)
    response["status"] = "timeout"
    _rehash_response(replay)
    assert replay_cbm_capability(replay)["fallback"]["reason"] == "provider_timeout"

    replay = _replay()
    response = replay["response"]
    assert isinstance(response, dict)
    response["capabilities"] = []
    _rehash_response(replay)
    assert replay_cbm_capability(replay)["fallback"]["reason"] == "provider_capability_unknown"


def test_red_team_rejects_drift_self_upgrade_missing_snapshot_and_unknown_schema() -> None:
    replay = _replay()
    response = replay["response"]
    assert isinstance(response, dict)
    response["capabilities"] = ["live_semantic"]
    _rehash_response(replay)
    assert replay_cbm_capability(replay)["fallback"]["reason"] == "provider_capability_unknown"

    replay = _replay()
    response = replay["response"]
    assert isinstance(response, dict)
    response["write_authority"] = "user_authorization"
    _rehash_response(replay)
    assert replay_cbm_capability(replay)["fallback"]["reason"] == "replay_schema_unknown"

    replay = _replay()
    source = replay["source"]
    assert isinstance(source, dict)
    del source["input_sha256"]
    assert replay_cbm_capability(replay)["fallback"]["reason"] == "source_snapshot_missing"

    replay = _replay()
    response = replay["response"]
    assert isinstance(response, dict)
    response["untrusted_field"] = True
    _rehash_response(replay)
    assert replay_cbm_capability(replay)["fallback"]["reason"] == "replay_schema_unknown"

    replay = _replay()
    response = replay["response"]
    assert isinstance(response, dict)
    response["index_owner"] = "loomgraph"
    assert replay_cbm_capability(replay)["fallback"]["reason"] == "replay_drift"


def test_replay_input_is_not_mutated() -> None:
    replay = _replay()
    before = copy.deepcopy(replay)

    replay_cbm_capability(replay)

    assert replay == before
