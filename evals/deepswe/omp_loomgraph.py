"""Pier adapter that makes offline LoomGraph and codegraph assets available.

The base ``omp_pier.Omp`` adapter belongs to the DeepSWE checkout and is left
untouched. This subclass uploads a Linux wheelhouse, optionally uploads a
Linux/amd64 codegraph bundle, installs both as the agent user, and lets the
orientation adapter own the result artifact.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from omp_orientation import OmpWithOrientation
from pier.environments.base import BaseEnvironment
from pier.models.agent.context import AgentContext

_WHEELHOUSE_ARCHIVE = "/tmp/loomgraph-wheelhouse.tar.gz"
_WHEELHOUSE_DIR = "/tmp/loomgraph-wheelhouse"
_LOOMGRAPH_BIN = "$HOME/.local/bin/loomgraph"
_CODEGRAPH_ARCHIVE = "/tmp/codegraph-linux-x64.tar.gz"
_CODEGRAPH_DIR = "$HOME/.local/share/codegraph-linux-x64"
_CODEGRAPH_BIN = "$HOME/.local/bin/codegraph"


def _tool_card(backend: str, use_mode: str, workspace: str | None = None) -> str:
    retrieval = (
        "You must run one structural retrieval command (`find` or `graph`) that "
        "returns `success:true` and non-empty structural evidence before your final JSON response."
        if use_mode == "assisted"
        else "You may run one structural retrieval command (`find` or `graph`) if useful."
    )
    if backend == "codegraph":
        setup = (
            "The codegraph database and LoomGraph graph are ready from adapter setup. "
            "Do not run `loomgraph index` again; query the ready graph instead. "
            f"Use `$HOME/.local/bin/loomgraph find <symbol> --workspace {workspace}` "
            "with this exact workspace name, not `/app`."
        )
    else:
        setup = (
            "For this codeindex graph, run `$HOME/.local/bin/loomgraph index .` once "
            "before a retrieval command. Then query from `/app` without passing `/app` "
            "as a `--workspace` value: `$HOME/.local/bin/loomgraph find <symbol>`."
        )
    return f"""This is the LoomGraph treatment condition. The CLI is available at
`$HOME/.local/bin/loomgraph`. {setup} {retrieval} A lone index is setup evidence,
not navigation evidence. Run the retrieval command directly. Do not add `--format`,
and do not pipe or truncate its output: LoomGraph already emits JSON and the adapter
needs the complete response to verify success and structural evidence. Do not infer that an unavailable, partial, or
non-comparable result means no change; record the actual command and trust
signal in your final JSON response."""


class OmpWithLoomGraph(OmpWithOrientation):
    """Install LoomGraph after OMP's regular setup without changing DeepSWE."""

    def __init__(
        self,
        *args: object,
        loomgraph_wheelhouse: str,
        loomgraph_backend: str = "codeindex",
        codegraph_bundle: str | None = None,
        **kwargs: object,
    ) -> None:
        self._loomgraph_wheelhouse = Path(loomgraph_wheelhouse).expanduser().resolve()
        if loomgraph_backend not in {"codeindex", "codegraph"}:
            raise ValueError(f"unsupported LoomGraph backend: {loomgraph_backend}")
        self._loomgraph_backend = loomgraph_backend
        self._loomgraph_workspace: str | None = None
        self._codegraph_bundle = (
            Path(codegraph_bundle).expanduser().resolve() if codegraph_bundle else None
        )
        if self._loomgraph_backend == "codegraph" and self._codegraph_bundle is None:
            raise ValueError("codegraph backend requires a Linux bundle")
        super().__init__(*args, **kwargs)

    @staticmethod
    def name() -> str:
        return "omp-loomgraph"

    def _instrumentation_cache_paths(self) -> list[str]:
        return [".codegraph/"] if self._loomgraph_backend == "codegraph" else []

    def _retrieval_requirement(
        self,
        commands: list[str],
        retrieval_succeeded: bool | None,
        retrieval_evidence_succeeded: bool | None,
    ) -> tuple[bool, bool | None]:
        required = self._orientation_use_mode == "assisted"
        return required, retrieval_evidence_succeeded if required else None

    @staticmethod
    def _workspace_from_index_output(stdout: str) -> str | None:
        """Read the workspace reported by adapter-owned LoomGraph setup."""
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            return None
        workspace = payload.get("data", {}).get("workspace")
        return workspace if isinstance(workspace, str) else None

    @staticmethod
    def _workspace_from_status_output(stdout: str) -> str | None:
        """Read the current workspace from LoomGraph's adapter-owned status call."""
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            return None
        workspace = payload.get("data", {}).get("workspace", {}).get("name")
        return workspace if isinstance(workspace, str) else None

    def _packet_from_trace(self, encoded_trace: str, source_mutated: bool) -> dict[str, Any]:
        """Prefer adapter-observed setup identity over model self-reporting."""
        packet = super()._packet_from_trace(encoded_trace, source_mutated)
        tooling = packet["tooling"]["loomgraph"]
        tooling["backend"] = self._loomgraph_backend
        workspace = getattr(self, "_loomgraph_workspace", None)
        if workspace is not None:
            tooling["workspace"] = workspace
        return packet

    async def setup(self, environment: BaseEnvironment) -> None:
        if not self._loomgraph_wheelhouse.is_file():
            raise FileNotFoundError(
                f"LoomGraph wheelhouse archive not found: {self._loomgraph_wheelhouse}"
            )
        if self._codegraph_bundle is not None and not self._codegraph_bundle.is_file():
            raise FileNotFoundError(
                f"codegraph bundle archive not found: {self._codegraph_bundle}"
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
                f"--find-links {_WHEELHOUSE_DIR} loomgraph; "
                f"{_LOOMGRAPH_BIN} --version"
            ),
        )
        if result.return_code != 0:
            raise RuntimeError(
                "offline LoomGraph install failed: "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
        if self._codegraph_bundle is not None:
            await environment.upload_file(str(self._codegraph_bundle), _CODEGRAPH_ARCHIVE)
            result = await self.exec_as_agent(
                environment,
                command=(
                    f"rm -rf {_CODEGRAPH_DIR}; "
                    f"mkdir -p {_CODEGRAPH_DIR} $HOME/.local/bin; "
                    f"tar -xzf {_CODEGRAPH_ARCHIVE} -C {_CODEGRAPH_DIR}; "
                    f"ln -sf {_CODEGRAPH_DIR}/bin/codegraph {_CODEGRAPH_BIN}; "
                    f"CODEGRAPH_TELEMETRY=0 {_CODEGRAPH_BIN} --version"
                ),
            )
            if result.return_code != 0:
                raise RuntimeError(
                    "offline codegraph install failed: "
                    f"{result.stderr.strip() or result.stdout.strip()}"
                )
            result = await self.exec_as_agent(
                environment,
                cwd="/app",
                command=(
                    "if [ ! -f .codegraph/codegraph.db ]; then "
                    f"CODEGRAPH_TELEMETRY=0 CODEGRAPH_NO_WATCH=1 "
                    f"{_CODEGRAPH_BIN} init .; "
                    "fi"
                ),
            )
            if result.return_code != 0:
                raise RuntimeError(
                    "codegraph init gate failed: "
                    f"{result.stderr.strip() or result.stdout.strip()}"
                )
            result = await self.exec_as_agent(
                environment,
                cwd="/app",
                command=(
                    f"CODEGRAPH_TELEMETRY=0 CODEGRAPH_NO_WATCH=1 "
                    f"{_LOOMGRAPH_BIN} index . --backend codegraph"
                ),
            )
            if result.return_code != 0:
                raise RuntimeError(
                    "LoomGraph codegraph index gate failed: "
                    f"{result.stderr.strip() or result.stdout.strip()}"
                )
            self._loomgraph_workspace = self._workspace_from_index_output(result.stdout)
            if self._loomgraph_workspace is None:
                result = await self.exec_as_agent(
                    environment,
                    cwd="/app",
                    command=f"{_LOOMGRAPH_BIN} status",
                )
                if result.return_code != 0:
                    raise RuntimeError(
                        "LoomGraph status gate failed: "
                        f"{result.stderr.strip() or result.stdout.strip()}"
                    )
                self._loomgraph_workspace = self._workspace_from_status_output(result.stdout)

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        await super().run(
            f"{_tool_card(self._loomgraph_backend, self._orientation_use_mode, self._loomgraph_workspace)}\n\n{instruction}",
            environment,
            context,
        )
