"""Pier adapter for a bounded, read-only OMP orientation phase."""

from __future__ import annotations

import base64
import json
from typing import Any

from omp_pier import Omp
from pier.agents.installed.base import CliFlag
from pier.environments.base import BaseEnvironment
from pier.models.agent.context import AgentContext

_PACKET_PATH = "/logs/artifacts/orientation.json"
_READ_ONLY_TOOLS = "read,grep,glob,lsp,bash"
_TRACE_SUMMARY_COMMAND = r'''python3 - <<'PY'
import base64
import json

last_text = ""
loomgraph_commands = []
with open("/logs/agent/omp.txt", encoding="utf-8", errors="replace") as trace:
    for raw in trace:
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "message_end":
            continue
        message = event.get("message") or {}
        if message.get("role") != "assistant":
            continue
        for part in message.get("content") or []:
            if part.get("type") == "text" and isinstance(part.get("text"), str):
                last_text = part["text"]
            if part.get("type") != "toolCall" or part.get("name") != "bash":
                continue
            command = (part.get("arguments") or {}).get("command")
            if isinstance(command, str) and "loomgraph" in command:
                loomgraph_commands.append(command)

payload = {"response": last_text, "loomgraph_commands": loomgraph_commands}
print(base64.b64encode(json.dumps(payload).encode()).decode())
PY'''


class OmpWithOrientation(Omp):
    """Persist a validated pre-edit packet from OMP's final JSON response."""

    CLI_FLAGS = [
        *Omp.CLI_FLAGS,
        CliFlag("orientation_max_time", cli="--max-time", type="str", default="420s"),
        CliFlag("orientation_tools", cli="--tools", type="str", default=_READ_ONLY_TOOLS),
        CliFlag("orientation_no_skills", cli="--no-skills", type="bool", default=True),
        CliFlag("orientation_no_rules", cli="--no-rules", type="bool", default=True),
    ]

    @staticmethod
    def name() -> str:
        return "omp-orientation"

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        before = await self._repo_state(environment)
        await self._write_packet(environment, self._missing_packet())
        await super().run(instruction, environment, context)
        after = await self._repo_state(environment)
        trace = await self.exec_as_agent(environment, command=_TRACE_SUMMARY_COMMAND)
        packet = self._packet_from_trace(trace.stdout, before != after)
        await self._write_packet(environment, packet)

    async def _repo_state(self, environment: BaseEnvironment) -> str:
        result = await self.exec_as_agent(
            environment,
            command="git rev-parse HEAD && git status --porcelain --untracked-files=all",
        )
        if result.return_code != 0:
            return "repo-state-unavailable"
        return result.stdout

    async def _write_packet(
        self,
        environment: BaseEnvironment,
        packet: dict[str, Any],
    ) -> None:
        encoded = base64.b64encode(json.dumps(packet, separators=(",", ":")).encode()).decode()
        await self.exec_as_agent(
            environment,
            command=(
                "mkdir -p /logs/artifacts; "
                f"printf %s {encoded} | base64 -d > {_PACKET_PATH}"
            ),
        )

    def _packet_from_trace(self, encoded_trace: str, source_mutated: bool) -> dict[str, Any]:
        try:
            trace = json.loads(base64.b64decode(encoded_trace.strip()))
            response, response_format = self._decode_response(trace["response"])
            commands = trace["loomgraph_commands"]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return self._missing_packet()

        if not self._response_is_valid(response):
            return self._missing_packet()

        return {
            "schema_version": 1,
            "status": "invalid_source_mutation" if source_mutated else "complete",
            "pre_edit": not source_mutated,
            "source_clean_scope": "model_phase",
            "instrumentation_cache_paths": self._instrumentation_cache_paths(),
            "response_format": response_format,
            "candidates": response["candidates"],
            "evidence": response["evidence"],
            "tooling": {
                "loomgraph": {
                    "used": bool(commands),
                    "commands": commands,
                    "workspace": response["tooling"]["loomgraph"].get("workspace"),
                    "backend": response["tooling"]["loomgraph"].get("backend"),
                    "trust": response["tooling"]["loomgraph"].get("trust"),
                }
            },
        }

    @staticmethod
    def _decode_response(text: object) -> tuple[object, str]:
        """Decode the one JSON object OMP returned, retaining format compliance."""
        if not isinstance(text, str):
            raise ValueError("agent response is not text")

        stripped = text.strip()
        for prefix in ("```json\n", "```\n"):
            if stripped.startswith(prefix) and stripped.endswith("\n```"):
                return json.loads(stripped[len(prefix) : -3]), "markdown_fenced"
        return json.loads(stripped), "raw_json"

    @staticmethod
    def _response_is_valid(response: object) -> bool:
        if not isinstance(response, dict):
            return False
        candidates = response.get("candidates")
        if not isinstance(candidates, list) or not 1 <= len(candidates) <= 5:
            return False
        if any(
            not isinstance(candidate, dict)
            or not isinstance(candidate.get("path"), str)
            or candidate["path"].startswith(("docs/", "examples/", "tests/"))
            for candidate in candidates
        ):
            return False
        return isinstance(response.get("evidence"), list) and isinstance(
            response.get("tooling", {}).get("loomgraph"), dict
        )

    def _missing_packet(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "status": "missing_or_invalid_agent_response",
            "pre_edit": None,
            "source_clean_scope": "model_phase",
            "instrumentation_cache_paths": self._instrumentation_cache_paths(),
            "response_format": "invalid",
            "candidates": [],
            "evidence": [],
            "tooling": {"loomgraph": {"used": False, "commands": []}},
        }

    def _instrumentation_cache_paths(self) -> list[str]:
        return []
