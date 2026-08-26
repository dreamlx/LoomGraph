"""Capture a no-fixture model identity before any V7 cohort cell is created."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from evals.deepswe import claude_orientation as orientation  # noqa: E402

PROTOCOL = "temporal-review-v7-model-identity"
_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["ok"],
    "properties": {"ok": {"type": "boolean"}},
}


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _claude_version() -> dict[str, object]:
    result = subprocess.run(
        ["claude", "--version"], cwd=_REPOSITORY_ROOT, capture_output=True, text=True
    )
    return {
        "command": ["claude", "--version"],
        "return_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _command(model: str, budget_usd: str) -> list[str]:
    return [
        "claude", "-p", "--model", model, "--effort", "low", "--output-format", "stream-json",
        "--verbose", "--setting-sources", "project,local", "--disable-slash-commands",
        "--permission-mode", "dontAsk", "--no-session-persistence", "--max-budget-usd", budget_usd,
        "--json-schema", json.dumps(_SCHEMA, separators=(",", ":"), sort_keys=True),
        "--strict-mcp-config", "--tools", "", "--mcp-config", '{"mcpServers":{}}', "--",
        "Return exactly the required JSON object.",
    ]


_MODEL_SURFACES = ("assistant", "session", "usage")


def _model_categories(events: list[dict[str, Any]]) -> dict[str, object]:
    """Rebuild V7's raw and canonical model-label evidence from one stream."""
    return orientation._v7_model_categories(events)


def _categories_valid(categories: object, *, requested_model: str, identity_mode: str) -> bool:
    if not isinstance(categories, dict) or categories.get("model_categories_valid") is not True:
        return False
    for surface in _MODEL_SURFACES:
        raw = categories.get(f"{surface}_models_raw")
        canonical = categories.get(f"{surface}_models_canonical")
        if (
            not isinstance(raw, list)
            or not all(isinstance(label, str) and label for label in raw)
            or canonical != sorted(set(raw))
        ):
            return False
    return identity_mode != "model-specific" or categories["assistant_models_canonical"] == [requested_model]


def run_preflight(*, output_dir: Path, model: str, identity_mode: str, max_budget_usd: str) -> dict[str, object]:
    """Run one no-tool probe and retain its complete stream before cohort materialization."""
    if identity_mode not in {"model-specific", "runtime-specific"}:
        raise ValueError("identity_mode must be model-specific or runtime-specific")
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise ValueError("output_dir must not already exist")
    output_dir.mkdir(parents=True)
    command = _command(model, max_budget_usd)
    claude_version = _claude_version()
    events: list[dict[str, Any]] = []
    with (output_dir / "claude.stream.jsonl").open("w", encoding="utf-8") as stream:
        process = subprocess.Popen(
            command, cwd=_REPOSITORY_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
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
    summary = orientation.summarize_stream(events)
    categories = _model_categories(events)
    complete = (
        return_code == 0
        and summary.get("final_result_seen") is True
        and _categories_valid(categories, requested_model=model, identity_mode=identity_mode)
        and claude_version["return_code"] == 0
    )
    result: dict[str, object] = {
        "schema_version": 1,
        "protocol": PROTOCOL,
        "status": "complete" if complete else "failed",
        "identity_mode": identity_mode,
        "requested_model": model,
        **{key: categories.get(key, []) for key in (
            "assistant_models_raw", "session_models_raw", "usage_models_raw",
            "assistant_models_canonical", "session_models_canonical", "usage_models_canonical",
        )},
        "claude_version": claude_version,
        "return_code": return_code,
        "command": command,
        "command_sha256": hashlib.sha256(json.dumps(command, separators=(",", ":")).encode()).hexdigest(),
    }
    _write(output_dir / "identity-preflight.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--identity-mode", choices=("model-specific", "runtime-specific"), required=True)
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
