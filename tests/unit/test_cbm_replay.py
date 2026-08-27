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
