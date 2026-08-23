"""Versioned, materialized repositories for capability observations (#206)."""

from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MaterializedFixture:
    """An isolated Git repository built from version-controlled fixture text."""

    fixture_id: str
    path: Path
    sha: str
    refs: set[str]


def _git(path: Path, *args: str, env: dict[str, str] | None = None) -> str:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    proc = subprocess.run(
        ["git", *args], cwd=path, env=merged_env, check=True, capture_output=True, text=True
    )
    return proc.stdout.strip()


def _write(path: Path, relative: str, content: str) -> None:
    target = path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)


def _commit(path: Path, message: str, timestamp: str) -> None:
    _git(path, "add", "-A")
    _git(
        path,
        "commit",
        "-qm",
        message,
        env={"GIT_AUTHOR_DATE": timestamp, "GIT_COMMITTER_DATE": timestamp},
    )


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    for source in sorted(p for p in path.rglob("*") if p.is_file() and ".git" not in p.parts):
        digest.update(source.relative_to(path).as_posix().encode())
        digest.update(b"\0")
        digest.update(source.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _init(path: Path) -> None:
    path.mkdir(parents=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "capability-fixture@example.test")
    _git(path, "config", "user.name", "Capability Fixture")
    _write(path, ".codeindex.yaml", "languages:\n  - python\n")


def _python_history(path: Path) -> set[str]:
    _init(path)
    _write(
        path,
        "app/auth.py",
        "class AuthService:\n"
        "    def validate(self, token: str) -> bool:\n"
        "        return validate_token(token)\n\n"
        "def validate_token(token: str) -> bool:\n"
        "    return token == 'ok'\n\n"
        "def legacy_token(token: str) -> bool:\n"
        "    return token == 'legacy'\n",
    )
    _write(
        path,
        "app/handlers.py",
        "from app.auth import legacy_token, validate_token\n\n"
        "def handle_login(token: str) -> bool:\n"
        "    return validate_token(token)\n\n"
        "def keep_legacy(token: str) -> bool:\n"
        "    return legacy_token(token)\n",
    )
    _commit(path, "base", "2024-01-01T00:00:00+00:00")
    _git(path, "tag", "base")
    _write(
        path,
        "app/auth.py",
        "class AuthService:\n"
        "    def validate(self, token: str) -> bool:\n"
        "        return validate_token(token)\n\n"
        "def validate_token(token: str) -> bool:\n"
        "    return token == 'ok'\n\n"
        "def validate_token_v2(token: str) -> bool:\n"
        "    return validate_token(token)\n",
    )
    _commit(path, "head", "2024-01-02T00:00:00+00:00")
    _git(path, "tag", "head")
    return {"base", "head"}


def _factory_receiver(path: Path) -> set[str]:
    _init(path)
    _write(
        path,
        "store.py",
        "class Store:\n"
        "    async def create_entity(self) -> None:\n"
        "        pass\n",
    )
    _write(
        path,
        "factory.py",
        "from store import Store\n\n"
        "async def create_store() -> Store:\n"
        "    return Store()\n",
    )
    _write(
        path,
        "consumer.py",
        "from factory import create_store\n\n"
        "async def run() -> None:\n"
        "    store = await create_store()\n"
        "    await store.create_entity()\n",
    )
    _commit(path, "factory receiver", "2024-01-03T00:00:00+00:00")
    _git(path, "tag", "head")
    return {"head"}


def _topology_debt_git(path: Path) -> set[str]:
    _init(path)
    _write(
        path,
        "app/hub.py",
        "def HubFunc(value: str) -> str:\n"
        "    revision = 0\n"
        "    return f'{revision}:{value}'\n",
    )
    for number in range(1, 9):
        _write(
            path,
            f"app/consumer_{number}.py",
            "from app.hub import HubFunc\n\n"
            f"def use_{number}(value: str) -> str:\n"
            "    return HubFunc(value)\n",
        )
    _commit(path, "seed hub", "2024-02-01T00:00:00+00:00")
    for revision in range(1, 13):
        _write(
            path,
            "app/hub.py",
            "def HubFunc(value: str) -> str:\n"
            f"    revision = {revision}\n"
            "    return f'{revision}:{value}'\n",
        )
        _commit(path, f"hub revision {revision}", f"2024-02-{revision + 1:02d}T00:00:00+00:00")
    _git(path, "tag", "head")
    return {"head"}


def _ts_barrel_alias(path: Path) -> set[str]:
    _init(path)
    _write(path, ".codeindex.yaml", "languages:\n  - typescript\n")
    _write(
        path,
        "tsconfig.json",
        '{\n'
        '  "compilerOptions": {\n'
        '    "baseUrl": ".",\n'
        '    "paths": {"@models/*": ["src/*"]}\n'
        "  }\n"
        "}\n",
    )
    _write(path, "src/models.ts", "export class Session {}\n")
    _write(path, "src/index.ts", 'export { Session } from "./models";\n')
    _write(
        path,
        "src/consumer.ts",
        'import { Session } from "./index";\n\n'
        "export const useSession = (session: Session) => session;\n",
    )
    _write(
        path,
        "src/alias_consumer.ts",
        'import { Session } from "@models/models";\n\n'
        "export const useAliasSession = (session: Session) => session;\n",
    )
    _commit(path, "barrel", "2024-01-04T00:00:00+00:00")
    _git(path, "tag", "head")
    return {"head"}


def materialize_fixture(fixture_id: str, path: Path) -> MaterializedFixture:
    """Create one deterministic fixture repository at ``path``."""
    builders = {
        "python-core": _python_history,
        "python-history": _python_history,
        "factory-receiver": _factory_receiver,
        "topology-debt-git": _topology_debt_git,
        "ts-barrel-alias": _ts_barrel_alias,
    }
    try:
        refs = builders[fixture_id](path)
    except KeyError as exc:
        raise ValueError(f"unknown capability fixture: {fixture_id}") from exc
    return MaterializedFixture(fixture_id=fixture_id, path=path, sha=_sha(path), refs=refs)
