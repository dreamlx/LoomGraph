"""Pier adapter that makes an offline LoomGraph wheelhouse available to OMP.

The base ``omp_pier.Omp`` adapter belongs to the DeepSWE checkout and is left
untouched. This subclass uploads a Linux wheelhouse, installs it as the agent
user, and creates a non-result orientation artifact before the model runs.
"""

from __future__ import annotations

from pathlib import Path

from omp_orientation import OmpWithOrientation
from pier.environments.base import BaseEnvironment
from pier.models.agent.context import AgentContext

_WHEELHOUSE_ARCHIVE = "/tmp/loomgraph-wheelhouse.tar.gz"
_WHEELHOUSE_DIR = "/tmp/loomgraph-wheelhouse"
_LOOMGRAPH_BIN = "$HOME/.local/bin/loomgraph"
_TOOL_CARD = """This is the LoomGraph treatment condition. The CLI is available at
`$HOME/.local/bin/loomgraph`. For structural navigation, you may run
`$HOME/.local/bin/loomgraph index .` and then `find` or `graph`. Do not infer
that an unavailable, partial, or non-comparable result means no change; record
the actual command and trust signal in the orientation packet."""


class OmpWithLoomGraph(OmpWithOrientation):
    """Install LoomGraph after OMP's regular setup without changing DeepSWE."""

    def __init__(self, *args: object, loomgraph_wheelhouse: str, **kwargs: object) -> None:
        self._loomgraph_wheelhouse = Path(loomgraph_wheelhouse).expanduser().resolve()
        super().__init__(*args, **kwargs)

    @staticmethod
    def name() -> str:
        return "omp-loomgraph"

    async def setup(self, environment: BaseEnvironment) -> None:
        if not self._loomgraph_wheelhouse.is_file():
            raise FileNotFoundError(
                f"LoomGraph wheelhouse archive not found: {self._loomgraph_wheelhouse}"
            )

        await super().setup(environment)
        await environment.upload_file(str(self._loomgraph_wheelhouse), _WHEELHOUSE_ARCHIVE)
        result = await self.exec_as_agent(
            environment,
            command=(
                f"rm -rf {_WHEELHOUSE_DIR}; "
                f"mkdir -p {_WHEELHOUSE_DIR}; "
                f"tar -xzf {_WHEELHOUSE_ARCHIVE} -C {_WHEELHOUSE_DIR}; "
                "python -m pip install --user --no-index "
                f"--find-links {_WHEELHOUSE_DIR} loomgraph==0.21.0; "
                f"{_LOOMGRAPH_BIN} --version"
            ),
        )
        if result.return_code != 0:
            raise RuntimeError(
                "offline LoomGraph install failed: "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        await super().run(f"{_TOOL_CARD}\n\n{instruction}", environment, context)
