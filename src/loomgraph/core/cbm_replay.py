"""Offline-only CBM capability replay for the ADR-017 discovery spike.

The adapter accepts an already reviewed replay record.  It never starts CBM,
creates an index, opens LoomGraph storage, or enables provider routing.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

from loomgraph.core.provider_capability import ProviderCapability, build_evidence_envelope

_STRATUM = (
    "claude-code-first/local-cbm-0.10.8/synthetic-fixture/"
    "read-only-structural-candidate/no-model"
)
_PROVIDER = {
    "id": "cbm",
    "version": "0.10.8",
    "operation": "structural_navigation",
    "evidence_kind": "structural_candidate",
    "snapshot_scope": "provider_index",
    "snapshot_identity": None,
    "index_owner": "provider",
    "data_scope": "unknown",
    "write_authority": "none",
}


class CBMReplayError(ValueError):
    """Marks an untrusted replay with its fail-closed fallback reason."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


def _mapping(value: object, reason: str, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise CBMReplayError(reason, f"{field} must be an object")
    return value


def _string(value: object, reason: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CBMReplayError(reason, f"{field} must be a non-empty string")
    return value


def _sha256(value: object, reason: str, field: str) -> str:
    text = _string(value, reason, field)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise CBMReplayError(reason, f"{field} must be a lowercase SHA-256")
    return text


def _native_fallback(reason: str) -> dict[str, object]:
    """Return the only safe result for an unreadable or untrusted replay."""
    return {
        "schema_version": 1,
        "recommended_path": "native",
        "availability": "unavailable",
        "provider": dict(_PROVIDER),
        "fallback": {
            "path": "native",
            "reason": reason,
            "limitation": "CBM replay is unavailable; no structural candidate is asserted",
        },
        "replay": {"mode": "offline", "execution": "provider_not_invoked"},
        "execution_boundary": {
            "adapter": "offline_replay_only",
            "provider_routing": "not_enabled",
            "provider_owned_index": "not_created_or_rebuilt",
        },
    }


def _parse_replay(raw: object) -> tuple[ProviderCapability, dict[str, str]]:
    replay = _mapping(raw, "replay_schema_unknown", "replay")
    required = {"schema_version", "stratum", "provider", "source", "response_sha256", "response"}
    if set(replay) == required - {"provider"}:
        raise CBMReplayError("provider_unavailable", "replay does not identify a provider")
    if set(replay) != required or replay["schema_version"] != 1:
        raise CBMReplayError("replay_schema_unknown", "replay must use schema version 1")
    if replay["stratum"] != _STRATUM:
        raise CBMReplayError("replay_stratum_mismatch", "replay stratum is not approved for this spike")

    provider = _mapping(replay["provider"], "provider_unavailable", "provider")
    if set(provider) != {"id", "version"} or provider.get("id") != "cbm":
        raise CBMReplayError("provider_unavailable", "replay must identify CBM")
    provider_version = _string(provider.get("version"), "provider_unavailable", "provider.version")
    if provider_version != _PROVIDER["version"]:
        raise CBMReplayError("provider_version_mismatch", "replay provider version is not pinned")

    source = _mapping(replay["source"], "source_snapshot_missing", "source")
    if set(source) != {"fixture", "input_sha256", "data_scope", "snapshot_scope"}:
        raise CBMReplayError("source_snapshot_missing", "source fields do not identify a fixture snapshot")
    _string(source["fixture"], "source_snapshot_missing", "source.fixture")
    input_sha256 = _sha256(source["input_sha256"], "source_snapshot_missing", "source.input_sha256")
    if source["data_scope"] != "local" or source["snapshot_scope"] != "provider_index":
        raise CBMReplayError("source_snapshot_missing", "source scope is not a local provider index")

    response = _mapping(replay["response"], "replay_schema_unknown", "response")
    response_fields = {
        "capabilities",
        "index_owner",
        "provider_version",
        "snapshot_identity",
        "snapshot_scope",
        "status",
        "write_authority",
    }
    if set(response) != response_fields:
        raise CBMReplayError("replay_schema_unknown", "response fields do not match replay schema v1")
    response_sha256 = _sha256(replay["response_sha256"], "replay_schema_unknown", "response_sha256")
    actual_sha256 = hashlib.sha256(
        json.dumps(response, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if actual_sha256 != response_sha256:
        raise CBMReplayError("replay_drift", "response hash does not match the reviewed replay")

    if response["status"] == "timeout":
        raise CBMReplayError("provider_timeout", "provider timed out in the saved response")
    if response["status"] != "ready":
        raise CBMReplayError("provider_unavailable", "provider was not ready in the saved response")
    if response["provider_version"] != provider_version:
        raise CBMReplayError("provider_version_mismatch", "response version differs from provider identity")
    if response["capabilities"] != ["structural_navigation"]:
        raise CBMReplayError("provider_capability_unknown", "CBM did not declare the pinned capability")
    if (
        response["index_owner"] != "provider"
        or response["snapshot_scope"] != "provider_index"
        or response["snapshot_identity"] is not None
        or response["write_authority"] != "none"
    ):
        raise CBMReplayError("replay_schema_unknown", "response crosses the structural read-only boundary")

    capability = cast(
        ProviderCapability,
        {
            "provider_id": "cbm",
            "provider_version": provider_version,
            "operation": "structural_navigation",
            "availability": "available",
            "reason": None,
            "evidence_kind": "structural_candidate",
            "snapshot_scope": "provider_index",
            "snapshot_identity": None,
            "index_owner": "provider",
            "data_scope": "local",
            "write_authority": "none",
        },
    )
    return capability, {"input_sha256": input_sha256, "response_sha256": response_sha256}


def replay_cbm_capability(raw: object) -> dict[str, object]:
    """Replay one reviewed CBM response, failing closed on every mismatch."""
    try:
        capability, hashes = _parse_replay(raw)
    except CBMReplayError as error:
        return _native_fallback(error.reason)

    plan = build_evidence_envelope(capability)
    plan["replay"] = {
        "mode": "offline",
        "execution": "provider_not_invoked",
        "stratum": _STRATUM,
        **hashes,
    }
    plan["execution_boundary"] = {
        "adapter": "offline_replay_only",
        "provider_routing": "not_enabled",
        "provider_owned_index": "not_created_or_rebuilt",
    }
    return plan


def load_cbm_replay(path: Path) -> dict[str, object]:
    """Read a saved replay without writing files or invoking a provider."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _native_fallback("replay_unreadable")
    return replay_cbm_capability(raw)
