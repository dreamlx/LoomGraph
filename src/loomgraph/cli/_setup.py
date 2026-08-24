"""CLI commands for status, setup, and utility operations."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Any

import click

from loomgraph import __version__
from loomgraph.cli._common import (
    ErrorCode,
    get_auto_workspace,
    output_error,
    output_partial_error,
    output_success,
)
from loomgraph.cli._deps_check import check_codeindex, check_embedding, check_storage
from loomgraph.cli.main import main
from loomgraph.core.config import get_settings

# Languages where codegraph (@colbymchenry/codegraph, 33-lang TS+Rust) is the
# stronger extraction backend (codeindex has historical blind spots: TS alias
# #139/#140, Java caller naming #76, and only 7 languages total). Kept as a
# named set for the recommendation message + future status detail, even though
# _backend_recommendation currently keys off the #161 fingerprint directly.
_CODEGRAPH_STRONG_LANGS = {
    "typescript", "javascript", "java", "swift", "objc",
}

_PROJECT_GUIDANCE_HEADING = "## LoomGraph navigation policy"
_PROJECT_GUIDANCE = f"""{_PROJECT_GUIDANCE_HEADING}

- Use ordinary text navigation for exact text, string, or single-file lookup.
- For cross-file relationships, caller/callee or change impact, module dependencies
  or topology, and branch/history comparison, use LoomGraph first.
- Resolve an entity with `loomgraph_find` before `loomgraph_graph`.
- Check index freshness when the working tree may have changed. Do not treat an
  empty, failed, stale, or partial graph result as proof that no relationship exists.
"""


def _backend_recommendation() -> dict[str, Any] | None:
    """Non-enforcing extraction-backend hint based on the repo's language
    fingerprint (#152, reuses #161 helpers). Returns None when nothing
    actionable surfaces (Python/PHP repo, or not in a repo)."""
    from loomgraph.cli._indexing import (
        _effective_languages,
        _language_fingerprint_warning,
    )

    try:
        repo = Path.cwd()
    except Exception:
        return None
    # Reuse the #161 fingerprint: it already counts source files per language
    # (vendored dirs excluded) and knows the effective languages. When it
    # fires, the repo's dominant language is misconfigured-for-codeindex —
    # exactly the codegraph-recommendation trigger.
    fp = _language_fingerprint_warning(repo)
    if not fp:
        return None
    langs = _effective_languages(repo)
    return {
        "recommended_backend": "codegraph",
        "reason": (
            "codegraph (33 langs) extracts TS/Java/mobile/multi-language "
            "repos more completely than codeindex (7 langs)"
        ),
        "detected_signal": fp,
        "current_effective_languages": sorted(langs),
        "install": "npm i -g @colbymchenry/codegraph && codegraph init",
    }


@main.command()
def status() -> None:
    """Check system status and dependencies.

    Returns status of all required dependencies:
    - codeindex: Code parsing tool
    - storage: SQLite + sqlite-vec local backend
    - embedding: OpenAI-compatible embedding provider (optional, default local
      Ollama; only needed for vec0 semantic search)
    """
    settings = get_settings()

    codeindex_status = check_codeindex()
    storage_status = check_storage(settings)
    embedding_status = check_embedding(settings)

    dependencies = {
        "codeindex": codeindex_status,
        "storage": storage_status,
        "embedding": embedding_status,
    }

    suggestions: list[str] = []
    if not codeindex_status.get("installed"):
        suggestions.append("Install codeindex: pip install ai-codeindex")
    if not storage_status.get("connected"):
        suggestions.append(
            "Storage backend unavailable; check sqlite-vec install"
        )
    # Only warn when the user opted into embedding and the service is down.
    # `enabled: false` is a deliberate choice (the v0.11.0 default), not a
    # problem worth surfacing.
    if (
        embedding_status.get("enabled", True)
        and not embedding_status.get("connected")
    ):
        suggestions.append(
            "Embedding service not reachable (semantic search vec0 will be empty)"
        )

    # Workspace context: pull stats from local SqliteGraphStore if available.
    current_ws = get_auto_workspace(None)
    ws_context: dict[str, Any] = {"name": current_ws}
    if storage_status.get("connected"):
        try:
            import asyncio

            from loomgraph.storage.factory import create_graph_store

            async def _stats() -> dict[str, Any]:
                store = await create_graph_store(workspace=current_ws)
                try:
                    return await store.get_graph_stats()
                finally:
                    close = getattr(store, "close", None)
                    if close is not None:
                        await close()

            stats = asyncio.run(_stats())
            ws_context["entities"] = stats.get("entity_count", 0)
            ws_context["relations"] = stats.get("relation_count", 0)
        except Exception:
            ws_context["entities"] = "unknown"

    data: dict[str, Any] = {
        "version": __version__,
        "workspace": ws_context,
        "config": {
            "storage_backend": settings.storage.backend,
            "db_path_template": settings.storage.db_path,
            "embedding_url": settings.embedding.api_url,
            "llm_provider": settings.llm.provider,
        },
        "dependencies": dependencies,
    }

    # #152: extraction-backend recommendation (non-enforcing). codegraph
    # (@colbymchenry/codegraph, 33 langs) outperforms codeindex on TS/Java/
    # multi-language/mobile; codeindex (7 langs) stays the default for
    # Python/PHP. Reuses the #161 language fingerprint to detect the repo's
    # dominant languages without re-walking the tree.
    rec = _backend_recommendation()
    if rec:
        data["backend_recommendation"] = rec

    if not storage_status.get("connected"):
        output_partial_error(
            code=ErrorCode.DEPENDENCIES_MISSING,
            message="Storage backend unavailable",
            suggestions=suggestions,
            data=data,
        )
    elif suggestions:
        data["warnings"] = suggestions
        output_success(data)
    else:
        output_success(data)


@main.command("install-skills")
def install_skills() -> None:
    """Install LoomGraph skills to ~/.claude/skills/.

    Copies bundled skills from the wheel package to the Claude Code
    skills directory. Safe to run multiple times (overwrites existing).
    """
    # Locate bundled _skills directory
    skills_src = Path(__file__).parent.parent / "_skills"
    if not skills_src.exists():
        output_error(
            code=ErrorCode.FILE_NOT_FOUND,
            message="Bundled skills not found in package",
            suggestion="Reinstall loomgraph: pip install --force-reinstall loomgraph",
        )
        return

    skills_dest = Path.home() / ".claude" / "skills"
    skills_dest.mkdir(parents=True, exist_ok=True)

    installed: list[str] = []
    for skill_dir in skills_src.iterdir():
        if skill_dir.is_dir() and not skill_dir.name.startswith("."):
            dest = skills_dest / skill_dir.name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(skill_dir, dest)
            installed.append(skill_dir.name)

    output_success({
        "skills_installed": installed,
        "skills_dir": str(skills_dest),
        "count": len(installed),
    })


@main.command("init")
@click.option(
    "--path",
    type=click.Path(path_type=Path),
    default=Path("CLAUDE.md"),
    show_default=True,
    help="Project instruction file to add LoomGraph navigation guidance to.",
)
def init_guidance(path: Path) -> None:
    """Add opt-in LoomGraph tool-selection guidance to a project instruction file."""
    path = path.resolve()
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if _PROJECT_GUIDANCE_HEADING in existing:
        output_success({"path": str(path), "updated": False})
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    separator = "" if not existing or existing.endswith("\n\n") else "\n\n"
    path.write_text(f"{existing}{separator}{_PROJECT_GUIDANCE}\n", encoding="utf-8")
    output_success({"path": str(path), "updated": True})


@main.command("setup-config")
@click.option(
    "--lightrag-url",
    default=None,
    help="(deprecated) Ignored — LightRAG was removed in v0.10. Kept for back-compat.",
)
@click.option(
    "--embedding-url",
    default=None,
    help="(deprecated) Embedding provider is now configured via .loomgraph.yaml.",
)
def setup_config(lightrag_url: str | None, embedding_url: str | None) -> None:
    """(deprecated) Generate a LoomGraph configuration file.

    LoomGraph is zero-config by default (local SQLite, embedding off). This
    command now writes a minimal `.loomgraph.yaml` stub documenting the
    opt-in embedding/LLM providers. Most users never need it — just
    `pipx install loomgraph && loomgraph index .`.
    """
    # #114: deprecate setup-config. It dates from the LightRAG era and still
    # generated `lightrag.api_url` config, contradicting the v0.11+ SQLite
    # default. Kept registered so existing scripts/docs don't break, but emits
    # a stderr warning and writes a SQLite-era stub instead.
    click.echo(
        "warning: `setup-config` is deprecated since v0.16. LoomGraph is "
        "zero-config by default (local SQLite, embedding off). This writes a "
        "minimal config stub only — for most users, `pipx install loomgraph "
        "&& loomgraph index .` is enough. See .loomgraph.yaml docs for "
        "embedding/LLM provider config.",
        err=True,
    )

    import yaml as _yaml

    config: dict[str, Any] = {
        "storage": {
            "backend": "sqlite",
        },
        "embedding": {
            "enabled": False,  # opt-in: set true + provider for semantic search
        },
    }

    config_dir = Path.home() / ".config" / "loomgraph"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.yaml"

    with open(config_path, "w") as f:
        f.write(
            "# Generated by `loomgraph setup-config` (deprecated).\n"
            "# LoomGraph is zero-config by default — this file is optional.\n"
            "# Turn on semantic search by setting embedding.enabled: true\n"
            "# and provider (ollama | openai | voyage | glm | custom).\n"
        )
        _yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

    output_success({
        "config_path": str(config_path),
        "deprecated": True,
        "note": "Zero-config default; edit this file only to enable embedding/LLM.",
    })


@main.command()
def version() -> None:
    """Show version information."""
    output_success({
        "version": __version__,
        "python": sys.version.split()[0],
    })
