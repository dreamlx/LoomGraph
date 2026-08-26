"""Capture V8 model identity, including its persisted validity witness."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from evals.deepswe import claude_orientation as orientation  # noqa: E402

PROTOCOL = "temporal-review-v8-model-identity"
_MODEL_SURFACES = ("assistant", "session", "usage")
_IDENTITY_FIELDS = tuple(
    f"{surface}_models_{kind}" for surface in _MODEL_SURFACES for kind in ("raw", "canonical")
) + ("model_categories_valid",)
_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["ok"],
    "properties": {"ok": {"type": "boolean"}},
}


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _command(model: str, budget_usd: str) -> list[str]:
    return [
        "claude",
        "-p",
        "--model",
        model,
        "--effort",
        "low",
        "--output-format",
        "stream-json",
        "--verbose",
        "--setting-sources",
        "project,local",
        "--disable-slash-commands",
        "--permission-mode",
        "dontAsk",
        "--no-session-persistence",
        "--max-budget-usd",
        budget_usd,
        "--json-schema",
        json.dumps(_SCHEMA, separators=(",", ":"), sort_keys=True),
        "--strict-mcp-config",
        "--tools",
        "",
        "--mcp-config",
        '{"mcpServers":{}}',
        "--",
        "Return exactly the required JSON object.",
    ]


def _model_categories(events: list[dict[str, Any]]) -> dict[str, object]:
    return orientation._v7_model_categories(events)


def _categories_valid(categories: object, *, requested_model: str, identity_mode: str) -> bool:
    if not isinstance(categories, dict) or categories.get("model_categories_valid") is not True:
        return False
    for surface in _MODEL_SURFACES:
        raw, canonical = (
            categories.get(f"{surface}_models_raw"),
            categories.get(f"{surface}_models_canonical"),
        )
        if (
            not isinstance(raw, list)
            or not all(isinstance(value, str) and value for value in raw)
            or canonical != sorted(set(raw))
        ):
            return False
    return identity_mode != "model-specific" or categories["assistant_models_canonical"] == [
        requested_model
    ]


def run_preflight(
    *, output_dir: Path, model: str, identity_mode: str, max_budget_usd: str
) -> dict[str, object]:
    """Run one no-tool probe and retain unprojected stream evidence."""
    if identity_mode not in {"model-specific", "runtime-specific"}:
        raise ValueError("identity_mode must be model-specific or runtime-specific")
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise ValueError("output_dir must not already exist")
    output_dir.mkdir(parents=True)
    command = _command(model, max_budget_usd)
    version_run = subprocess.run(["claude", "--version"], cwd=_ROOT, capture_output=True, text=True)
    claude_version = {
        "command": ["claude", "--version"],
        "return_code": version_run.returncode,
        "stdout": version_run.stdout,
        "stderr": version_run.stderr,
    }
    events: list[dict[str, Any]] = []
    with (output_dir / "claude.stream.jsonl").open("w", encoding="utf-8") as stream:
        process = subprocess.Popen(
            command, cwd=_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        assert process.stdout is not None
        for line in process.stdout:
            stream.write(line)
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
        return_code = process.wait()
    categories = _model_categories(events)
    complete = (
        return_code == 0
        and orientation.summarize_stream(events).get("final_result_seen") is True
        and claude_version["return_code"] == 0
        and _categories_valid(categories, requested_model=model, identity_mode=identity_mode)
    )
    result: dict[str, object] = {
        "schema_version": 1,
        "protocol": PROTOCOL,
        "status": "complete" if complete else "failed",
        "identity_mode": identity_mode,
        "requested_model": model,
        **{field: categories.get(field) for field in _IDENTITY_FIELDS},
        "claude_version": claude_version,
        "return_code": return_code,
        "command": command,
        "command_sha256": hashlib.sha256(
            json.dumps(command, separators=(",", ":")).encode()
        ).hexdigest(),
    }
    _write(output_dir / "identity-preflight.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument(
        "--identity-mode", choices=("model-specific", "runtime-specific"), required=True
    )
    parser.add_argument("--max-budget-usd", default="0.05")
    args = parser.parse_args()
    result = run_preflight(
        output_dir=args.output_dir,
        model=args.model,
        identity_mode=args.identity_mode,
        max_budget_usd=args.max_budget_usd,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
