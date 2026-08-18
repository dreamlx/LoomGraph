"""Pier adapter that guarantees an orientation-artifact placeholder for OMP."""

from __future__ import annotations

import base64
import json

from omp_pier import Omp
from pier.environments.base import BaseEnvironment
from pier.models.agent.context import AgentContext


class OmpWithOrientation(Omp):
    """Create a non-result packet before the model starts, including timeouts."""

    @staticmethod
    def name() -> str:
        return "omp-orientation"

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        placeholder = base64.b64encode(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "agent_not_completed",
                    "pre_edit": None,
                    "candidates": [],
                    "evidence": [],
                    "tooling": {"loomgraph": {"used": False}},
                }
            ).encode()
        ).decode()
        await self.exec_as_agent(
            environment,
            command=(
                "mkdir -p /logs/artifacts; "
                f"printf %s {placeholder} | base64 -d > /logs/artifacts/orientation.json"
            ),
        )
        await super().run(instruction, environment, context)
