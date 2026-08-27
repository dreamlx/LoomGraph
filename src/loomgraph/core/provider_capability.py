"""Read-only provider capability and evidence-boundary contract (#287)."""

from __future__ import annotations

import json
from collections.abc import Set
from pathlib import Path
from typing import Literal, TypedDict, cast

Availability = Literal["available", "conditional", "unavailable"]
Operation = Literal[
    "structural_navigation",
    "live_semantic",
    "live_edit",
    "temporal_comparison",
]
EvidenceKind = Literal["structural_candidate", "live_semantic", "temporal_comparison"]
SnapshotScope = Literal["workspace", "provider_index", "working_tree", "pinned_comparison"]
IndexOwner = Literal["loomgraph", "provider", "none"]
DataScope = Literal["local", "unknown"]
WriteAuthority = Literal["none", "user_authorization"]


class ProviderCapabilityContractError(ValueError):
    """Raised when a declared provider capability crosses a trust boundary."""


class SnapshotIdentity(TypedDict):
    base_ref: str
    base_sha: str
    head_ref: str
    head_sha: str


class ProviderCapability(TypedDict):
    provider_id: str
    provider_version: str
    operation: Operation
    availability: Availability
    reason: str | None
    evidence_kind: EvidenceKind
    snapshot_scope: SnapshotScope
    snapshot_identity: SnapshotIdentity | None
    index_owner: IndexOwner
    data_scope: DataScope
    write_authority: WriteAuthority


class ProviderCapabilityManifest(TypedDict):
    schema_version: int
    capabilities: list[ProviderCapability]


_OPERATION_EVIDENCE: dict[Operation, EvidenceKind] = {
    "structural_navigation": "structural_candidate",
    "live_semantic": "live_semantic",
    "live_edit": "live_semantic",
    "temporal_comparison": "temporal_comparison",
}
_OPERATIONS = set(_OPERATION_EVIDENCE)
_AVAILABILITY = {"available", "conditional", "unavailable"}
_EVIDENCE_KINDS = set(_OPERATION_EVIDENCE.values())
_SNAPSHOT_SCOPES = {"workspace", "provider_index", "working_tree", "pinned_comparison"}
_INDEX_OWNERS = {"loomgraph", "provider", "none"}
_DATA_SCOPES = {"local", "unknown"}
_WRITE_AUTHORITIES = {"none", "user_authorization"}


def _mapping(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ProviderCapabilityContractError(f"{field} must be an object")
    return value


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProviderCapabilityContractError(f"{field} must be a non-empty string")
    return value


def _literal(value: object, allowed: Set[str], field: str) -> str:
    text = _string(value, field)
    if text not in allowed:
        raise ProviderCapabilityContractError(f"{field} is unsupported: {text}")
    return text


def _snapshot_identity(value: object) -> SnapshotIdentity:
    raw = _mapping(value, "snapshot_identity")
    required = {"base_ref", "base_sha", "head_ref", "head_sha"}
    if set(raw) != required:
        raise ProviderCapabilityContractError("pinned snapshot identity must contain base/head refs and SHAs")
    identity = {key: _string(raw[key], f"snapshot_identity.{key}") for key in required}
    if any(
        len(identity[key]) != 40
        or any(character not in "0123456789abcdefABCDEF" for character in identity[key])
        for key in ("base_sha", "head_sha")
    ):
        raise ProviderCapabilityContractError("pinned snapshot identity must use full hexadecimal Git SHAs")
    return cast(SnapshotIdentity, identity)


def _parse_capability(raw: object) -> ProviderCapability:
    value = _mapping(raw, "capability")
    required = {
        "provider_id",
        "provider_version",
        "operation",
        "availability",
        "reason",
        "evidence_kind",
        "snapshot_scope",
        "snapshot_identity",
        "index_owner",
        "data_scope",
        "write_authority",
    }
    if set(value) != required:
        raise ProviderCapabilityContractError("capability fields do not match schema v1")

    operation = cast(Operation, _literal(value["operation"], _OPERATIONS, "operation"))
    evidence_kind = cast(
        EvidenceKind, _literal(value["evidence_kind"], _EVIDENCE_KINDS, "evidence_kind")
    )
    if evidence_kind != _OPERATION_EVIDENCE[operation]:
        raise ProviderCapabilityContractError("operation cannot claim a stronger evidence kind")

    provider_version = _string(value["provider_version"], "provider_version")
    availability = cast(
        Availability, _literal(value["availability"], _AVAILABILITY, "availability")
    )
    raw_reason = value["reason"]
    if availability == "available":
        if raw_reason is not None:
            raise ProviderCapabilityContractError("available capability must not declare a reason")
        reason: str | None = None
    else:
        reason = _string(raw_reason, "reason")

    data_scope = cast(DataScope, _literal(value["data_scope"], _DATA_SCOPES, "data_scope"))

    snapshot_scope = cast(
        SnapshotScope, _literal(value["snapshot_scope"], _SNAPSHOT_SCOPES, "snapshot_scope")
    )
    snapshot_identity = value["snapshot_identity"]
    if operation == "temporal_comparison":
        if snapshot_scope != "pinned_comparison" or snapshot_identity is None:
            raise ProviderCapabilityContractError("temporal comparison requires a pinned snapshot identity")
        parsed_identity: SnapshotIdentity | None = _snapshot_identity(snapshot_identity)
    else:
        if snapshot_scope == "pinned_comparison" or snapshot_identity is not None:
            raise ProviderCapabilityContractError("only temporal comparison may declare a pinned snapshot")
        parsed_identity = None

    if availability == "available" and provider_version.strip().casefold() == "unknown":
        raise ProviderCapabilityContractError("available capability requires a known provider version")
    if availability == "available" and data_scope != "local":
        raise ProviderCapabilityContractError("available capability requires local data scope")

    write_authority = cast(
        WriteAuthority,
        _literal(value["write_authority"], _WRITE_AUTHORITIES, "write_authority"),
    )
    if operation == "live_edit" and write_authority != "user_authorization":
        raise ProviderCapabilityContractError("live edit requires explicit user authorization")
    if operation != "live_edit" and write_authority != "none":
        raise ProviderCapabilityContractError("read-only operations cannot require write authority")

    return {
        "provider_id": _string(value["provider_id"], "provider_id"),
        "provider_version": provider_version,
        "operation": operation,
        "availability": availability,
        "reason": reason,
        "evidence_kind": evidence_kind,
        "snapshot_scope": snapshot_scope,
        "snapshot_identity": parsed_identity,
        "index_owner": cast(
            IndexOwner, _literal(value["index_owner"], _INDEX_OWNERS, "index_owner")
        ),
        "data_scope": data_scope,
        "write_authority": write_authority,
    }


def parse_manifest(raw: object) -> ProviderCapabilityManifest:
    """Validate a static v1 manifest without probing or invoking a provider."""
    value = _mapping(raw, "manifest")
    if set(value) != {"schema_version", "capabilities"} or value["schema_version"] != 1:
        raise ProviderCapabilityContractError("manifest must use schema_version 1")
    capabilities = value["capabilities"]
    if not isinstance(capabilities, list) or not capabilities:
        raise ProviderCapabilityContractError("manifest capabilities must be a non-empty list")
    parsed = [_parse_capability(item) for item in capabilities]
    keys = {(item["provider_id"], item["operation"]) for item in parsed}
    if len(keys) != len(parsed):
        raise ProviderCapabilityContractError("manifest cannot declare a provider operation twice")
    return {"schema_version": 1, "capabilities": parsed}


def load_manifest(path: Path) -> ProviderCapabilityManifest:
    """Read and validate a manifest without creating or changing any files."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProviderCapabilityContractError(f"cannot read provider capability manifest: {exc}") from exc
    return parse_manifest(raw)


def build_evidence_envelope(capability: ProviderCapability) -> dict[str, object]:
    """Return an orientation-safe envelope; never auto-select unavailable or write paths."""
    provider = {
        "id": capability["provider_id"],
        "version": capability["provider_version"],
        "operation": capability["operation"],
        "evidence_kind": capability["evidence_kind"],
        "snapshot_scope": capability["snapshot_scope"],
        "snapshot_identity": capability["snapshot_identity"],
        "index_owner": capability["index_owner"],
        "data_scope": capability["data_scope"],
        "write_authority": capability["write_authority"],
    }
    if capability["write_authority"] != "none":
        return {
            "schema_version": 1,
            "recommended_path": "native",
            "availability": "conditional",
            "provider": provider,
            "fallback": {
                "path": "native",
                "reason": "provider_requires_user_authorization",
                "limitation": "provider operation may modify source and is not auto-selected",
            },
        }
    if capability["availability"] != "available":
        return {
            "schema_version": 1,
            "recommended_path": "native",
            "availability": capability["availability"],
            "provider": provider,
            "fallback": {
                "path": "native",
                "reason": capability["reason"],
                "limitation": "provider capability is declared but not runtime-verified",
            },
        }
    return {
        "schema_version": 1,
        "recommended_path": "provider",
        "availability": "available",
        "provider": provider,
        "fallback": None,
    }


def provider_plan(
    manifest: ProviderCapabilityManifest, provider_id: str, operation: Operation
) -> dict[str, object]:
    """Select one declared capability or return a native fallback without inference."""
    capability = next(
        (
            item
            for item in manifest["capabilities"]
            if item["provider_id"] == provider_id and item["operation"] == operation
        ),
        None,
    )
    if capability is not None:
        return build_evidence_envelope(capability)
    return {
        "schema_version": 1,
        "recommended_path": "native",
        "availability": "unavailable",
        "provider": {"id": provider_id, "operation": operation},
        "fallback": {
            "path": "native",
            "reason": "provider_capability_unknown",
            "limitation": "no declared provider capability matches this request",
        },
    }
