"""Capture a no-fixture model identity before any V5 cohort cell is created."""

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

PROTOCOL = "temporal-review-v5-model-identity"
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
    assistant_models = summary.get("assistant_models")
    observed_stack = [summary.get(key) for key in ("session_models", "usage_models")]
    complete = (
        return_code == 0
        and summary.get("final_result_seen") is True
        and isinstance(assistant_models, list)
        and bool(assistant_models)
        and all(isinstance(item, str) and item for item in assistant_models)
        and all(isinstance(models, list) and all(isinstance(item, str) and item for item in models) for models in observed_stack)
        and claude_version["return_code"] == 0
        and (identity_mode != "model-specific" or assistant_models == [model])
    )
    result: dict[str, object] = {
        "schema_version": 1,
        "protocol": PROTOCOL,
        "status": "complete" if complete else "failed",
        "identity_mode": identity_mode,
        "requested_model": model,
        "assistant_models": assistant_models if isinstance(assistant_models, list) else [],
        "session_models": summary.get("session_models", []),
        "usage_models": summary.get("usage_models", []),
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
