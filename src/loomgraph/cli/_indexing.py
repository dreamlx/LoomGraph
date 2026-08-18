"""CLI commands for indexing and updating the knowledge graph."""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path
from typing import Any

import click

from loomgraph.cli._common import ErrorCode, get_auto_workspace, output_error, output_success
from loomgraph.cli._deps_check import check_codeindex
from loomgraph.cli.main import main
from loomgraph.core.git import (
    GitError,
    get_changed_files,
    get_working_tree_files,
    is_git_repository,
    resolve_ref,
)
from loomgraph.core.graph_export_ingest import (
    GraphExportEmptyError,
    GraphExportError,
    assess_export,
    ingest,
    ingest_incremental,
    run_graph_export,
)
from loomgraph.io.codegraph_reader import (
    CodegraphDbMissingError,
    CodegraphSchemaError,
    run_codegraph_export,
)

# Extensions codeindex can parse (any configured language). `update` skips the
# whole-tree re-export when the git diff touches none of them (#165) — the
# post-commit hook makes every docs/config/CI commit pay the full export
# otherwise. Deliberately conservative:宁可多跑一次 export,不可漏更新.
SUPPORTED_SOURCE_EXTS = {
    ".py", ".php", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".swift", ".java", ".m", ".h",
}

# Config files whose content changes what the graph contains (or how it is
# built) without any source-file diff — they always trigger a re-export.
_GRAPH_AFFECTING_CONFIGS = {
    ".codeindex.yaml", ".codeindex.yml",
    ".loomgraph.yaml", ".loomgraph.yml",
}

# Extraction backends (#152). codeindex is the default (unchanged); codegraph
# (@colbymchenry/codegraph, 33-language TS+Rust) is opt-in via `--backend`.
# Each backend produces the SAME (entities, relations, summary, warnings)
# 4-tuple so the shared `ingest()` pipeline is reused. Per-workspace single
# source — the backend is recorded in workspace meta so `update` without an
# explicit flag routes to the same one (a bare `update` must not silently
# swap a codegraph workspace's graph for a codeindex one).
DEFAULT_BACKEND = "codeindex"
SUPPORTED_BACKENDS = ("codeindex", "codegraph")
# MCP/CLI hint when codegraph isn't installed but the repo needs it.
CODEGRAPH_INSTALL_HINT = (
    "codegraph not found — install with `npm i -g @colbymchenry/codegraph` "
    "then run `codegraph init`"
)


async def _workspace_backend(store: Any, explicit: str | None) -> str:
    """Resolve the extraction backend for a workspace.

    Explicit ``--backend`` always wins and is recorded. Without it, the
    workspace's recorded ``extraction_backend`` meta is honored (so `update`
    on a codegraph workspace stays codegraph). Falls back to codeindex
    (default, backward-compatible) when no meta is recorded — a fresh
    workspace or a pre-#152 workspace.
    """
    if explicit:
        return explicit
    get_meta = getattr(store, "get_meta", None)
    if get_meta is not None:
        recorded = await get_meta("extraction_backend")
        if recorded:
            return str(recorded)
    return DEFAULT_BACKEND


def _run_export(
    backend: str, repo: Path
) -> tuple[list[Any], list[Any], Any, list[str]]:
    """Dispatch to the configured backend's export function."""
    if backend == "codegraph":
        return run_codegraph_export(repo)
    return run_graph_export(repo)


def _silence_warnings(warnings: list[str]) -> list[str]:
    """Drop warnings matching a `warnings.silence` substring (#166)."""
    from loomgraph.core.config import get_settings

    silence = [
        s.lower() for s in get_settings().warnings.silence if s.strip()
    ]
    if not silence:
        return warnings
    return [w for w in warnings if not any(s in w.lower() for s in silence)]


# codeindex's FILE_EXTENSIONS mapping — used only for the #161 language
# fingerprint (files codeindex *would* parse if the language were configured).
_LANG_EXTS = {
    ".py": "python", ".php": "php", ".java": "java",
    ".ts": "typescript", ".tsx": "typescript",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
    ".cjs": "javascript",
    ".swift": "swift", ".h": "objc", ".m": "objc",
}
# Third-party/generated trees don't count as the repo's language fingerprint
# (they're also where the stray .py files that mask this case come from).
_FINGERPRINT_SKIP_DIRS = {
    ".git", "node_modules", "Pods", "vendor", "dist", "build",
    ".venv", "venv", "__pycache__",
}
# Below this many files a language isn't "the repo's main language missed by
# config" — just stray tool scripts. Keeps small repos warning-free.
_FINGERPRINT_MIN_FILES = 10
_PARSER_MISSING_RE = re.compile(r"Parser library not installed for ([^:\s]+):")
_GRAMMAR_EXTRAS = {
    "typescript": "typescript",
    "javascript": "javascript",
    "swift": "swift",
    "java": "java",
    "objc": "objc",
}


def _is_partial_graph_warning(w: str) -> bool:
    """#184: 「图缺符号」类 warning(parser-missing / language-fingerprint)。

    区别于 advisory 类(resolved_ratio hint、test 污染提示是质量信号,图不缺
    符号)——它们照常进 `warning` 字段,但不置 `partial`。
    """
    return "Parser library not installed" in w or w.startswith("language fingerprint:")


def _grammar_remediation_hints(warnings: list[str]) -> list[str]:
    """Return one copyable LoomGraph install hint per missing parser language."""
    hints: list[str] = []
    seen: set[str] = set()
    for warning in warnings:
        match = _PARSER_MISSING_RE.search(warning)
        if match is None:
            continue
        language = match.group(1)
        if language in seen:
            continue
        seen.add(language)
        extra = _GRAMMAR_EXTRAS.get(language)
        if extra is not None:
            hints.append(
                f'Install support: pipx install "loomgraph[{extra}]"; then add '
                f'`{language}` to `languages:` in .codeindex.yaml.'
            )
        else:
            hints.append(
                f"Install the required tree-sitter grammar for `{language}`; then add "
                f"`{language}` to `languages:` in .codeindex.yaml."
            )
    return hints


def _append_grammar_remediation(message: str, warnings: list[str]) -> str:
    hints = _grammar_remediation_hints(warnings)
    if not hints:
        return message
    return f"{message.rstrip('.')}. {' '.join(hints)}"


def _effective_languages(repo: Path) -> set[str]:
    """codeindex 的生效 languages:无 `.codeindex.yaml`(或缺 languages 键)→ python。"""
    for name in (".codeindex.yaml", ".codeindex.yml"):
        cfg = repo / name
        if not cfg.exists():
            continue
        try:
            import yaml

            data = yaml.safe_load(cfg.read_text()) or {}
            langs = data.get("languages")
            if isinstance(langs, list) and langs:
                return {str(x) for x in langs}
        except Exception:
            pass  # unreadable config → codeindex falls back to its default too
    return {"python"}


def _language_fingerprint_warning(repo: Path) -> str | None:
    """#161: repo 主语言不在生效 languages 里 → partial-graph warning。

    全 TS/Java/Swift 仓无 `.codeindex.yaml` 时 codeindex 默认
    `languages=["python"]`,静默只抓到零星 .py(Pods/node_modules 残留)——
    实体数 7≠0 不触发 0-entity gate,输出 success,用户拿到 0% 覆盖目标
    语言的残缺图。呈现层提醒(不阻断 exit code,对齐 codeindex
    "提醒+建议不自动 fallback" 哲学):dominant 语言文件数 ≥ 阈值且超过
    生效 languages 覆盖的文件总数 → 提示补 languages 配置。
    """
    from collections import Counter

    counts: Counter[str] = Counter()
    for _, dirnames, filenames in os.walk(repo):
        dirnames[:] = [d for d in dirnames if d not in _FINGERPRINT_SKIP_DIRS]
        for fn in filenames:
            lang = _LANG_EXTS.get(Path(fn).suffix)
            if lang:
                counts[lang] += 1
    if not counts:
        return None

    langs = _effective_languages(repo)
    covered = sum(counts.get(lang, 0) for lang in langs)
    for lang, n in counts.most_common():
        if lang in langs or n < _FINGERPRINT_MIN_FILES or n <= covered:
            continue
        return (
            f"language fingerprint: detected {n} {lang} source files, none "
            f"indexed — add '{lang}' to `languages` in .codeindex.yaml "
            f"(effective languages: {', '.join(sorted(langs))})"
        )
    return None


def _diff_names_with_deletions(since: str, repo: Path) -> list[str] | None:
    """Diff names INCLUDING deletions (ACMRD), or None when git fails.

    The shared ``get_changed_files`` filters ACMR — a deleted file never
    appears, so a deleted ``.codeindex.yaml`` would read as an empty diff
    and the update would skip, silently keeping a graph built under the
    deleted config (codex re-review on #165).
    """
    import subprocess as _sp

    try:
        r = _sp.run(
            ["git", "diff", "--name-only", "--diff-filter=ACMRD", since],
            cwd=str(repo), capture_output=True, text=True, timeout=30,
            check=True,
        )
    except Exception:
        return None  # non-git / bad ref: caller falls through to export
    return [line.strip() for line in r.stdout.splitlines() if line.strip()]


@main.command()
@click.argument("repo_path", type=click.Path(exists=True), required=False, default=".")
@click.option("--clear/--no-clear", default=True, help="Clear old data before indexing")
@click.option("--workspace", "-w", default=None, help="Workspace name (default: current directory name)")
@click.option(
    "--at-ref",
    default=None,
    metavar="REF",
    help=(
        "Index a git ref in an isolated snapshot workspace (default: "
        "<repo>:<ref>); use -w to choose the workspace explicitly"
    ),
)
@click.option(
    "--backend",
    type=click.Choice(SUPPORTED_BACKENDS),
    default=DEFAULT_BACKEND,
    help=(
        "Extraction backend: codeindex (default, 7 langs, README_AI nav) or "
        "codegraph (@colbymchenry/codegraph, 33 langs, TS/Java/multi-lang #152)"
    ),
)
def index(
    repo_path: str,
    clear: bool,
    workspace: str | None,
    at_ref: str | None,
    backend: str,
) -> None:
    """Index a code repository (one-step pipeline).

    Backend dispatch (#152): codeindex graph-export (default) or codegraph
    snapshot. Both produce the same (entities, relations) 4-tuple that the
    shared embed→inject pipeline consumes.

    REPO_PATH: Directory path to index (default: current directory)
    """
    import time

    start_time = time.time()
    repo = Path(repo_path).resolve()

    if at_ref is not None:
        if backend != DEFAULT_BACKEND:
            output_error(
                code=ErrorCode.INVALID_INPUT,
                message="index --at-ref currently supports only the codeindex backend",
                suggestion=(
                    "Use 'loomgraph index <repo> --backend codegraph' for a "
                    "working-tree codegraph snapshot"
                ),
            )
            return
        if not clear:
            output_error(
                code=ErrorCode.INVALID_INPUT,
                message=(
                    "index --at-ref always performs a cold snapshot; "
                    "--no-clear is not supported"
                ),
                suggestion=(
                    "Remove --no-clear (or use 'loomgraph index <repo> "
                    "--no-clear' for a working-tree update)"
                ),
            )
            return
        result = _index_at_ref(repo, at_ref, workspace)
        if result is not None:
            result["duration_seconds"] = round(time.time() - start_time, 2)
            output_success(result)
        return

    # #152: backend branch BEFORE the codeindex gate — a codegraph workspace
    # on a machine without codeindex would otherwise die with
    # CODEINDEX_NOT_FOUND before meta routing ever runs.
    if backend == "codeindex":
        click.echo("[1/3] Checking codeindex installation...", err=True)
        codeindex_status = check_codeindex()
        if not codeindex_status.get("installed"):
            output_error(
                code=ErrorCode.CODEINDEX_NOT_FOUND,
                message="codeindex command not found in PATH",
                suggestion="Install codeindex: pip install ai-codeindex",
                docs="https://github.com/dreamlx/codeindex#installation",
            )
            return
        click.echo(f"[2/3] Exporting {repo.name}/ with codeindex graph-export...", err=True)
    else:
        click.echo(f"[1/2] Snapshotting {repo.name}/.codegraph/...", err=True)

    try:
        entities, relations, summary, warnings = _run_export(backend, repo)
    except CodegraphDbMissingError as e:
        output_error(
            code=ErrorCode.INVALID_INPUT,
            message=str(e),
            suggestion=CODEGRAPH_INSTALL_HINT,
        )
        return
    except CodegraphSchemaError as e:
        output_error(
            code=ErrorCode.STORAGE_ERROR,
            message=f"codegraph schema mismatch: {e}",
            suggestion="Re-run `codegraph index` to rebuild, or upgrade loomgraph",
        )
        return
    except GraphExportError as e:
        output_error(
            code=ErrorCode.CODEINDEX_FAILED,
            message=str(e),
            suggestion="Check codeindex logs; ensure ai-codeindex >= 0.28.0",
        )
        return
    click.echo(
        f"       Export complete: {summary.entity_count} entities, "
        f"{summary.relation_count} relations.",
        err=True,
    )

    # codeindex's partial-graph warnings (#131) — e.g. a non-Python repo
    # indexed with default languages:[python] yields a few stray entities and
    # a "WARNING: partial graph" line. Surface it so a misconfigured repo
    # doesn't index as a silent success (#108).
    raw_warnings = list(warnings)
    warnings = _silence_warnings(warnings)
    warnings.extend(_grammar_remediation_hints(warnings))
    # #161: >0 entities can still be a partial graph (stray .py only) — the
    # language fingerprint names the dominant language the config missed.
    # Appended BEFORE silence so it's filterable like codeindex's own warnings.
    if backend == "codeindex" and summary.entity_count > 0:
        fingerprint = _language_fingerprint_warning(repo)
        if fingerprint:
            warnings.append(fingerprint)
    warnings = _silence_warnings(warnings)
    for line in warnings:
        click.echo(f"⚠️  {line}", err=True)

    # 0 entities is almost always a languages/grammar mismatch (#93, #142) —
    # fail loud (exit 1) so a misconfigured repo (missing grammar / languages
    # mismatch) doesn't silently build an empty graph. Consistent with
    # `update`/`refresh`. An empty repo also exits 1: safe — the user checks
    # why there's nothing to index, rather than a silent success.
    # The gate consumes the RAW warnings — a silence pattern must not eat
    # the 0-entity diagnosis (codex review on #166).
    zero_warning = (
        _zero_entities_warning(repo, raw_warnings) if summary.entity_count == 0 else None
    )
    if zero_warning is not None:
        zero_warning = _append_grammar_remediation(zero_warning, raw_warnings)
        click.echo(f"⚠️  WARNING: {zero_warning}", err=True)
        output_error(
            code=ErrorCode.GRAPH_EXPORT_EMPTY,
            message=zero_warning,
        )

    # Step 3: Embed + inject asynchronously
    click.echo("[3/3] Injecting into knowledge graph...", err=True)
    try:
        result = asyncio.run(
            _async_index(entities, relations, workspace, clear, backend, summary)
        )
    except Exception as e:
        output_error(
            code=ErrorCode.STORAGE_ERROR,
            message=f"Pipeline error: {e}",
        )
        return

    duration = time.time() - start_time
    result["duration_seconds"] = round(duration, 2)
    result["repo_path"] = str(repo)
    click.echo(f"       Done in {result['duration_seconds']}s.", err=True)

    # #162: <0.1 is the known-blind-spot tier (PetClinic Java DI 4.9%,
    # HEXFORCE-RN TS aliases 6.1%) where topology/debt orphan counts stop
    # being dead-code evidence. ~0.2 is normal (self: 0.19 — third-party
    # calls never resolve), so no hint there. Reading guide:
    # docs/guides/index-output.md
    ratio = result.get("resolved_ratio")
    if ratio is not None and ratio < 0.1:
        hint = (
            f"resolved_ratio {ratio}: almost no edges join two stored entities "
            "(TS path-alias / Java DI / dynamic dispatch blind spots at this "
            "level) — topology orphan counts are NOT dead-code evidence here; "
            "see docs/guides/index-output.md"
        )
        click.echo(f"⚠️  {hint}", err=True)
        warnings.append(hint)

    if warnings:
        result["warning"] = "; ".join(warnings)
    # #184: machine-readable partial flag — post-silence warnings (a silenced
    # pattern must not keep `partial` True: silencing = user said "I know").
    result["partial"] = any(_is_partial_graph_warning(w) for w in warnings)

    output_success(result)


def _index_at_ref(
    repo: Path, ref: str, workspace: str | None
) -> dict[str, Any] | None:
    """Provision a historical ref using branch-diff's snapshot kernel."""
    from loomgraph.cli._branch_diff import _provision_ref

    if not is_git_repository(repo):
        output_error(
            code=ErrorCode.GIT_ERROR,
            message=f"Not a git repository: {repo}",
            suggestion="Run index --at-ref from inside a git repository.",
        )
        return None

    click.echo("[1/2] Checking codeindex installation...", err=True)
    codeindex_status = check_codeindex()
    if not codeindex_status.get("installed"):
        output_error(
            code=ErrorCode.CODEINDEX_NOT_FOUND,
            message="codeindex command not found in PATH",
            suggestion="Install codeindex: pip install ai-codeindex",
            docs="https://github.com/dreamlx/codeindex#installation",
        )
        return None

    try:
        sha = resolve_ref(repo, ref)
    except GitError as e:
        output_error(code=ErrorCode.GIT_ERROR, message=str(e))
        return None

    repo_dir = repo.name.lower()
    click.echo(f"[2/2] Provisioning ref '{ref}' ({sha[:7]})...", err=True)
    try:
        info = _provision_ref(
            repo,
            repo_dir,
            ref,
            sha,
            workspace_name=workspace,
        )
    except GraphExportEmptyError as e:
        output_error(
            code=ErrorCode.GRAPH_EXPORT_EMPTY,
            message=str(e),
            suggestion=(
                "The ref exported 0 entities — check .codeindex.yaml at that "
                "commit (languages config travels with the ref, not the cwd)."
            ),
        )
        return None
    except GraphExportError as e:
        output_error(code=ErrorCode.CODEINDEX_FAILED, message=str(e))
        return None
    except GitError as e:
        output_error(code=ErrorCode.GIT_ERROR, message=str(e))
        return None

    return {
        "ref": info["ref"],
        "sha": info["sha"],
        "workspace": info["workspace"],
        "provisioned": info["provisioned"],
        "mode": "at_ref",
        "repo_path": str(repo),
    }


async def _async_index(
    entities: list[Any],
    relations: list[Any],
    workspace: str | None,
    clear: bool,
    backend: str = DEFAULT_BACKEND,
    summary: Any = None,
    extra_meta: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Resolve workspace, build the store, run the shared ingest pipeline.

    Receives already-mapped entities/relations (codeindex graph-export or a
    codegraph snapshot, #152 — both produce the same 4-tuple). Records the
    extraction backend + codegraph provenance into workspace meta so `update`
    routes to the same backend without an explicit flag. ``extra_meta`` adds
    caller provenance keys (branch-diff's provisioned_by/ref/sha, EPIC-016).
    """
    from loomgraph.storage.factory import create_graph_store

    ws = get_auto_workspace(workspace)
    store = await create_graph_store(workspace=ws)

    def _progress(phase: str, n_entities: int, n_relations: int) -> None:
        click.echo(
            f"       {phase}: {n_entities} entities, {n_relations} relations",
            err=True,
        )

    result = await ingest(
        entities, relations, store, clear=clear, on_progress=_progress
    )
    result["workspace"] = ws
    result["mode"] = "cold_rebuild" if clear else "append"
    result["backend"] = backend

    # #152: record backend + provenance so update routes correctly and the
    # graph's source is auditable. codegraph db has no git sha — record HEAD.
    set_meta = getattr(store, "set_meta", None)
    if set_meta is not None:
        await set_meta("extraction_backend", backend)
        if backend == "codegraph" and summary is not None:
            meta = summary.meta or {}
            if (fp := meta.get("codegraph_fingerprint")):
                await set_meta("codegraph_fingerprint", fp)
            if (iv := meta.get("indexed_with_version")):
                await set_meta("codegraph_indexed_with_version", iv)
            if (ev := meta.get("indexed_with_extraction_version")):
                await set_meta("codegraph_extraction_version", ev)
            await set_meta("codegraph_head", _git_head_safe())
        if extra_meta:
            for key, value in extra_meta.items():
                await set_meta(key, value)
    return result


def _git_head_safe() -> str:
    """``git rev-parse HEAD`` at snapshot time, or '' when not a git repo.

    codegraph's db carries no git provenance — loomgraph records the HEAD the
    snapshot was taken at so the graph's source revision is auditable (#152).
    """
    import subprocess as _sp

    try:
        r = _sp.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
            timeout=10, check=True,
        )
        return r.stdout.strip()
    except Exception:
        return ""


def _update_codegraph(
    workspace: str | None, repo: Path, ws_name: str | None
) -> dict[str, Any] | None:
    """codegraph backend update path (#152).

    codegraph has no per-symbol content_hash → no incremental. Instead:
    re-snapshot, compare the content fingerprint to the workspace's recorded
    one; unchanged → noop (graph already current for this snapshot); changed
    → clear rebuild. loomgraph never runs ``codegraph sync`` itself (the
    user's tool to refresh the snapshot), so a noop also carries a hint to
    run it when the working tree has moved ahead.

    Returns the result dict, or None when output_error was already emitted.
    """
    import time

    start_time = time.time()
    click.echo("[1/2] Snapshotting .codegraph/...", err=True)
    try:
        entities, relations, summary, warnings = run_codegraph_export(repo)
    except CodegraphDbMissingError as e:
        output_error(
            code=ErrorCode.INVALID_INPUT, message=str(e),
            suggestion=CODEGRAPH_INSTALL_HINT,
        )
        return None
    except CodegraphSchemaError as e:
        output_error(
            code=ErrorCode.STORAGE_ERROR,
            message=f"codegraph schema mismatch: {e}",
            suggestion="Re-run `codegraph index` to rebuild, or upgrade loomgraph",
        )
        return None

    # 0-entity gate (same fail-loud contract as codeindex, #142).
    safe, zero_warning = assess_export(summary, warnings)
    if not safe:
        click.echo(f"⚠️  WARNING: {zero_warning}", err=True)
        output_error(
            code=ErrorCode.GRAPH_EXPORT_EMPTY,
            message=zero_warning or "codegraph snapshot returned 0 entities",
        )
        return None

    # Fingerprint noop (#152): skip the clear-rebuild when the snapshot is
    # unchanged. loomgraph never refreshes the codegraph db itself, so an
    # unchanged snapshot means the post-commit hook is re-ingesting identical
    # data — visible noop beats silent stale-graph-as-success.
    new_fp = (summary.meta or {}).get("codegraph_fingerprint", "")
    recorded_fp = ""

    async def _peek_fingerprint() -> str:
        from loomgraph.storage.factory import create_graph_store as _cgs

        store = await _cgs(workspace=ws_name)
        try:
            get_meta = getattr(store, "get_meta", None)
            if get_meta is None:
                return ""
            rec = await get_meta("codegraph_fingerprint")
            return str(rec) if rec else ""
        finally:
            close = getattr(store, "close", None)
            if close is not None:
                await close()

    try:
        recorded_fp = asyncio.run(_peek_fingerprint())
    except Exception:
        recorded_fp = ""
    if new_fp and recorded_fp and new_fp == recorded_fp:
        click.echo(
            "       codegraph snapshot unchanged — skipping rebuild. "
            "Run `codegraph sync` if the working tree moved ahead.",
            err=True,
        )
        return {
            "skipped": True,
            "reason": "codegraph_snapshot_unchanged",
            "workspace": ws_name,
            "mode": "codegraph_noop",
            "fingerprint": new_fp,
        }

    click.echo("[2/2] Rebuilding knowledge graph...", err=True)
    result = asyncio.run(
        _async_index(entities, relations, workspace, clear=True,
                     backend="codegraph", summary=summary)
    )
    duration = time.time() - start_time
    result["duration_seconds"] = round(duration, 2)
    result["repo_path"] = str(repo)
    result["mode"] = "codegraph_rebuild"
    click.echo(
        f"       Done in {result['duration_seconds']}s ({result['mode']}).",
        err=True,
    )
    if warnings:
        result["warning"] = "; ".join(warnings)
    return result


def _zero_entities_warning(repo: Path, warnings: list[str] | None = None) -> str:
    """Diagnose a 0-entity graph-export for the user/agent (#93, #96, #118).

    ``codeindex graph-export`` returned nothing — almost always a
    ``.codeindex.yaml`` languages mismatch (codeindex defaults to python)
    or a missing tree-sitter grammar. Return an actionable hint rather than
    a bare count. Java/TypeScript/Swift get a specific pointer to their
    extra; the general case points at the languages config or — when
    codeindex reported a grammar/parser problem on stderr — surfaces that.
    """
    if warnings:
        # codeindex already told us the root cause on stderr (#118): a missing
        # tree-sitter grammar (``Parser library not installed for <lang>``) or a
        # languages-mismatch (``no indexable directories`` + ``Top extensions``).
        # Prefer the codeindex diagnostic over file-suffix guessing — it names
        # the exact missing language even for PHP/objc/JS (no extra / no suffix
        # branch here yet) and cites the config vs file-extension gap directly.
        # The raw WARNING lines are already echoed verbatim above; fold the
        # multi-line hint into its leading sentence (keep the missing-language
        # name + file-extension evidence, drop the per-file path noise).
        first_lines: list[str] = []
        for w in warnings:
            first_lines.append(w.split("\n")[0].rstrip())
        joined = "; ".join(first_lines)
        return (
            f"graph-export returned 0 entities; codeindex reports: {joined}. "
            "Install the matching `loomgraph[<lang>]` extra and ensure that "
            "language is listed under `languages` in .codeindex.yaml"
        )
    if next(repo.rglob("*.java"), None) is not None:
        return (
            "graph-export returned 0 entities; found .java files — install "
            "Java support with `pipx install loomgraph[java]` and ensure "
            "'java' is listed under languages in .codeindex.yaml"
        )
    if next(repo.rglob("*.tsx"), None) is not None or next(repo.rglob("*.ts"), None) is not None:
        return (
            "graph-export returned 0 entities; found .ts/.tsx files — install "
            "TypeScript support with `pipx install loomgraph[typescript]` and "
            "ensure 'typescript' is listed under languages in .codeindex.yaml"
        )
    if next(repo.rglob("*.swift"), None) is not None:
        return (
            "graph-export returned 0 entities; found .swift files — install "
            "Swift support with `pipx install loomgraph[swift]` and ensure "
            "'swift' is listed under languages in .codeindex.yaml"
        )
    return (
        "graph-export returned 0 entities; check that .codeindex.yaml "
        "languages matches this repository's code"
    )


@main.command()
@click.option("--since", default="HEAD~1", help="Git ref to compare from (default: HEAD~1)")
@click.option("--workspace", "-w", default=None, help="Workspace name (default: current directory name)")
@click.option("--files", default=None, help="Comma-separated list of files to update (skips git detection)")
@click.option("--embedding-url", default=None, help="Override embedding API URL from config")
@click.option("--use-affected", is_flag=True, help="Use 'codeindex affected' instead of 'git diff' (smarter detection)")
@click.option(
    "--backend",
    type=click.Choice(SUPPORTED_BACKENDS),
    default=None,
    help="Extraction backend override (default: workspace's recorded backend, #152)",
)
def update(
    since: str,
    workspace: str | None,
    files: str | None,
    embedding_url: str | None,
    use_affected: bool,
    backend: str | None,
) -> None:
    """Update the knowledge graph (per-file warm-diff via git, 路 B).

    In a git repo: re-export the whole tree, then re-embed/re-inject only
    the files that changed since ``--since`` (default ``HEAD~1``) and
    garbage-collect symbols deleted since the last index. Unchanged files
    cost zero embed calls (the expensive part, per codeindex#110).

    Non-git repo, or ``--files`` set: falls back to whole-tree upsert
    (``clear=False``) — additions/modifications converge, but deleted
    symbols are NOT GC'd; run ``index --clear .`` for a fully clean state.

    ``--use-affected`` / ``--embedding-url`` are accepted but inert (kept
    for CI-script / muscle-memory compat). ``--files`` path-existence is
    validated (CI scripts may gate on the exit code) and forces the
    whole-tree fallback.
    """
    import time

    start_time = time.time()

    # Inert flags (compat) — note: --since is now ACTIVE (git diff ref).
    inert: list[str] = []
    if use_affected:
        inert.append("--use-affected")
    if embedding_url:
        inert.append("--embedding-url=…")
    if inert:
        click.echo(f"note: ignoring inert flags ({', '.join(inert)}).", err=True)

    # --files path validation (CI gate compat) → forces whole-tree fallback.
    forced_whole_tree = False
    if files:
        for f in [s.strip() for s in files.split(",") if s.strip()]:
            if not Path(f).exists():
                output_error(
                    code=ErrorCode.INVALID_INPUT,
                    message=f"File not found: {f}",
                    suggestion="Check file paths and ensure they exist",
                )
                return
        forced_whole_tree = True

    repo = Path(".").resolve()

    # #152: resolve the workspace's backend BEFORE the codeindex gate — a
    # codegraph workspace must not die with CODEINDEX_NOT_FOUND, and a bare
    # `update` (no --backend) must route to the workspace's recorded backend.
    ws_name = get_auto_workspace(workspace)
    resolved_backend = backend or DEFAULT_BACKEND
    if backend is None:
        # Peek the workspace meta for a recorded backend (one-shot open +
        # close). Runs in a worker thread so the close (an async WAL
        # checkpoint) actually executes — the old `_peek_store.close()`
        # produced an un-awaited coroutine, leaking the connection and
        # skipping the checkpoint (codex review #172).
        async def _peek_backend() -> str | None:
            from loomgraph.storage.factory import create_graph_store as _cgs

            store = await _cgs(workspace=ws_name)
            try:
                get_meta = getattr(store, "get_meta", None)
                if get_meta is None:
                    return None
                recorded = await get_meta("extraction_backend")
                return str(recorded) if recorded else None
            finally:
                close = getattr(store, "close", None)
                if close is not None:
                    await close()

        try:
            recorded = asyncio.run(_peek_backend())
            if recorded:
                resolved_backend = recorded
        except Exception:
            pass  # fresh workspace / non-existent: fall through to default

    # codegraph backend takes a separate path (snapshot + fingerprint noop).
    if resolved_backend == "codegraph":
        result = _update_codegraph(workspace, repo, ws_name)
        if result is not None:
            output_success(result)
        return

    # Step 1: Check codeindex
    click.echo("[1/3] Checking codeindex installation...", err=True)
    codeindex_status = check_codeindex()
    if not codeindex_status.get("installed"):
        output_error(
            code=ErrorCode.CODEINDEX_NOT_FOUND,
            message="codeindex command not found in PATH",
            suggestion="Install codeindex: pip install ai-codeindex",
            docs="https://github.com/dreamlx/codeindex#installation",
        )
        return

    # #165: short-circuit before the whole-tree export when the diff touches
    # no parsable source file — the export is the multi-second bulk of update,
    # and the post-commit hook pays it on every docs/config/CI-only commit.
    config_rebuild = False
    if not forced_whole_tree:
        diff_names = _diff_names_with_deletions(since, repo)
        # A diff is skippable only when NOTHING in it can affect the graph.
        # Config changes (.codeindex.yaml languages:, .loomgraph.yaml, their
        # deletions included) don't just prevent the skip — they demand a
        # CLEAR REBUILD: re-export alone is a no-op, because the incremental
        # ingest only touches entities whose source_id is in changed_files,
        # and a config file is no entity's source. Without the rebuild the
        # command would return success over a stale graph (codex re-review
        # BLOCKER on #165).
        if diff_names is not None:
            paths = [Path(n) for n in diff_names]
            config_touched = any(
                p.name in _GRAPH_AFFECTING_CONFIGS for p in paths
            )
            source_touched = any(
                p.suffix in SUPPORTED_SOURCE_EXTS for p in paths
            )
            if config_touched:
                config_rebuild = True
                click.echo(
                    "       Graph-affecting config changed — full rebuild.",
                    err=True,
                )
            elif not source_touched:
                # Nothing in the diff can affect the graph (docs/shell/CI
                # only — an empty diff is the degenerate case).
                click.echo(
                    "       No supported-language files in diff — skipping update.",
                    err=True,
                )
                output_success({
                    "skipped": True,
                    "reason": "no_supported_source_files_in_diff",
                    "since": since,
                    "workspace": get_auto_workspace(workspace),
                })
                return
            # else: source-only diff → normal incremental path below.

    # Step 2: Run codeindex graph-export (whole tree)
    click.echo("[2/3] Exporting whole tree with codeindex graph-export...", err=True)
    try:
        entities, relations, summary, warnings = run_graph_export(repo)
    except GraphExportError as e:
        output_error(
            code=ErrorCode.CODEINDEX_FAILED,
            message=str(e),
            suggestion="Check codeindex logs; ensure ai-codeindex >= 0.28.0",
        )
        return
    click.echo(
        f"       Export complete: {summary.entity_count} entities, "
        f"{summary.relation_count} relations.",
        err=True,
    )
    # Surface codeindex partial-graph warnings (#108) — same as `index`.
    # The zero-export safety gate below consumes the RAW warnings: a user
    # silence pattern must not degrade the 0-entity diagnosis (codex review).
    raw_warnings = list(warnings)
    warnings = _silence_warnings(warnings)
    warnings.extend(_grammar_remediation_hints(warnings))
    # #161: language fingerprint (same treatment as `index`).
    if summary.entity_count > 0:
        fingerprint = _language_fingerprint_warning(repo)
        if fingerprint:
            warnings.append(fingerprint)
    warnings = _silence_warnings(warnings)
    for line in warnings:
        click.echo(f"⚠️  {line}", err=True)

    # #120: a 0-entity whole-tree export is almost always a languages/grammar
    # mismatch. Letting it through to ingest_incremental would GC the changed
    # files' symbols (treated as "removed"); letting it through to the whole-
    # tree upsert writes an empty graph. Hard-stop with a diagnosis instead.
    safe, zero_warning = assess_export(summary, raw_warnings)
    if not safe:
        zero_warning = _append_grammar_remediation(
            zero_warning or "graph-export returned 0 entities", raw_warnings
        )
        click.echo(f"⚠️  WARNING: {zero_warning}", err=True)
        # #141: a 0-entity export is a config/grammar mismatch, not a success —
        # fail loud (exit 1) so the post-commit hook / CI detect the graph was
        # never updated, instead of a silent success:true.
        output_error(
            code=ErrorCode.GRAPH_EXPORT_EMPTY,
            message=zero_warning or "graph-export returned 0 entities",
        )

    # Step 3: Incremental (git) or whole-tree upsert (non-git / --files)
    click.echo("[3/3] Updating knowledge graph...", err=True)
    try:
        result = asyncio.run(
            _async_update(
                entities, relations, workspace, repo, since,
                forced_whole_tree, config_rebuild=config_rebuild,
                backend="codeindex",
            )
        )
    except Exception as e:
        output_error(
            code=ErrorCode.STORAGE_ERROR,
            message=f"Pipeline error: {e}",
        )
        return

    duration = time.time() - start_time
    result["duration_seconds"] = round(duration, 2)
    result["repo_path"] = str(repo)
    click.echo(f"       Done in {result['duration_seconds']}s ({result['mode']}).", err=True)

    if warnings:
        result["warning"] = "; ".join(warnings)
    result["partial"] = any(_is_partial_graph_warning(w) for w in warnings)  # #184

    output_success(result)


async def _async_update(
    entities: list[Any],
    relations: list[Any],
    workspace: str | None,
    repo: Path,
    since: str,
    forced_whole_tree: bool,
    config_rebuild: bool = False,
    backend: str = DEFAULT_BACKEND,
) -> dict[str, Any]:
    """Branch update into per-file incremental (git) or whole-tree upsert.

    - ``config_rebuild`` (graph-affecting config in the diff, #165): a CLEAR
      rebuild — languages changes reshape the whole graph, and the
      incremental path would ingest nothing (a config file is no entity's
      source_id).
    - git repo and not ``forced_whole_tree``: ``ingest_incremental`` over the
      ``get_changed_files(since)`` subset (路 B).
    - otherwise: ``ingest(clear=False)`` whole-tree upsert (non-git fallback,
      or explicit ``--files``).
    """
    from loomgraph.storage.factory import create_graph_store

    ws = get_auto_workspace(workspace)
    store = await create_graph_store(workspace=ws)

    def _progress(phase: str, n_entities: int, n_relations: int) -> None:
        click.echo(
            f"       {phase}: {n_entities} entities, {n_relations} relations",
            err=True,
        )

    if config_rebuild:
        result = await ingest(
            entities, relations, store, clear=True, on_progress=_progress
        )
        result["mode"] = "config_rebuild"
    elif (not forced_whole_tree) and is_git_repository(repo):
        changed_paths = get_changed_files(since=since, repo_path=repo)
        changed_files = {p.as_posix() for p in changed_paths}
        result = await ingest_incremental(
            entities,
            relations,
            store,
            changed_files=changed_files,
            on_progress=_progress,
        )
        result["mode"] = "warm_incremental"
    else:
        result = await ingest(
            entities, relations, store, clear=False, on_progress=_progress
        )
        result["mode"] = "whole_tree_upsert"

    result["workspace"] = ws
    return result


def _expand_path(path: str, repo: Path) -> set[str]:
    """Expand a path arg (file or dir prefix) to repo-relative posix paths.

    - file → ``{that file}``
    - dir  → all existing files under it (rglob)
    - missing → ``ValueError`` (the MCP handle's ``safe_call`` surfaces this
      as a ``REFRESH_FAILED`` envelope)
    """
    target = (repo / path).resolve()
    base = repo.resolve()
    if target.is_file():
        return {target.relative_to(base).as_posix()}
    if target.is_dir():
        return {
            f.relative_to(base).as_posix()
            for f in target.rglob("*")
            if f.is_file()
        }
    raise ValueError(f"path not found: {path}")


async def _async_refresh(
    workspace: str | None,
    repo: Path,
    path: str | None,
    force_full: bool,
) -> dict[str, Any]:
    """MCP-driven reactive re-index of the working tree (pull-mode).

    Complementary to :func:`_async_update` (committed ``HEAD~1..HEAD`` via the
    git hook): refresh targets the **working tree** — uncommitted edits
    including untracked new files — so an agent that just edited a file can
    see it in the graph without committing first.

    Backend routing (#152): a codegraph workspace's recorded
    ``extraction_backend`` meta is honored — refresh otherwise shells
    codeindex into a codegraph workspace and ``ingest_incremental`` would GC
    every codegraph symbol in changed files (graph destruction). On a
    codegraph workspace, ``force_full`` re-snapshots + clear-rebuilds;
    incremental refresh is not supported (codegraph has no content_hash) and
    fails loud with a "use CLI update" hint.

    codeindex branching:

    - ``force_full=True`` → ``ingest(clear=True)`` cold rebuild (like
      ``index --clear``).
    - ``path`` given → ``ingest_incremental`` over the expanded path set.
    - git repo, no path → ``ingest_incremental`` over ``get_working_tree_files``.
    - non-git, no path → ``ingest(clear=False)`` whole-tree upsert.
    - incremental resolves to zero changed files → ``{"mode": "noop"}``,
      skipping the codeindex export entirely.
    """
    from loomgraph.storage.factory import create_graph_store

    ws = get_auto_workspace(workspace)
    store = await create_graph_store(workspace=ws)

    # #152: route by the workspace's recorded backend. A codegraph workspace
    # has no content_hash → incremental refresh would GC codegraph symbols.
    get_meta = getattr(store, "get_meta", None)
    recorded_backend = None
    if get_meta is not None:
        recorded_backend = await get_meta("extraction_backend")
    if recorded_backend == "codegraph":
        return await _async_refresh_codegraph(
            store, ws, repo, path, force_full
        )

    if force_full:
        entities, relations, summary, warnings = run_graph_export(repo)
        # #120: a 0-entity export is almost always a languages/grammar mismatch
        # — clearing on top of it would silently wipe the whole workspace.
        # Hard-stop before ingest(clear=True); surface the diagnosis instead.
        raw_warnings = list(warnings)
        warnings.extend(_grammar_remediation_hints(raw_warnings))
        safe, warning = assess_export(summary, raw_warnings)
        if not safe:
            # #141: surface as an error (CLI exit 1 / MCP error envelope), not
            # a silent success. assess_export's warning carries the root cause.
            raise GraphExportEmptyError(_append_grammar_remediation(
                warning or "graph-export returned 0 entities", raw_warnings
            ))
        result = await ingest(entities, relations, store, clear=True)
        result["mode"] = "cold_rebuild"
        result["workspace"] = ws
        # #184: MCP has no stderr contract — partial-graph warnings must ride
        # the result or they're dropped entirely (silent partial on the
        # primary agent surface). Same `warning`/`partial` fields as the CLI.
        if warnings:
            result["warning"] = "; ".join(warnings)
        result["partial"] = any(_is_partial_graph_warning(w) for w in warnings)
        return result

    # Determine the changed-files set + strategy.
    if path is not None:
        changed_files = _expand_path(path, repo)
        strategy = "incremental"
    elif is_git_repository(repo):
        changed_files = {
            p.as_posix() for p in get_working_tree_files(repo_path=repo)
        }
        strategy = "incremental"
    else:
        changed_files = set()
        strategy = "whole_tree"

    if strategy == "incremental" and not changed_files:
        return {"mode": "noop", "changed_files": [], "workspace": ws}

    entities, relations, summary, warnings = run_graph_export(repo)
    # #120: same gate on the incremental/whole-tree path — ingest_incremental's
    # symbol GC would treat a 0-entity export as "all symbols removed" and
    # delete them. Hard-stop before any write.
    raw_warnings = list(warnings)
    warnings.extend(_grammar_remediation_hints(raw_warnings))
    safe, warning = assess_export(summary, raw_warnings)
    if not safe:
        # #141: surface as an error (CLI exit 1 / MCP error envelope), not a
        # silent success. assess_export's warning carries the root cause.
        raise GraphExportEmptyError(_append_grammar_remediation(
            warning or "graph-export returned 0 entities", raw_warnings
        ))
    if strategy == "incremental":
        result = await ingest_incremental(
            entities, relations, store, changed_files=changed_files
        )
        result["mode"] = "warm_incremental"
    else:
        result = await ingest(entities, relations, store, clear=False)
        result["mode"] = "whole_tree_upsert"

    result["workspace"] = ws
    if warnings:  # #184: same treatment as the force_full leg above
        result["warning"] = "; ".join(warnings)
    result["partial"] = any(_is_partial_graph_warning(w) for w in warnings)
    return result


async def _async_refresh_codegraph(
    store: Any,
    ws: str | None,
    repo: Path,
    path: str | None,
    force_full: bool,
) -> dict[str, Any]:
    """codegraph refresh (#152): re-snapshot + clear-rebuild on force_full.

    codegraph has no per-symbol content_hash, so per-file incremental refresh
    is impossible — ``ingest_incremental`` would GC codegraph symbols in the
    changed set. Incremental refresh (path or working-tree) fails loud with a
    "use CLI update" hint instead of silently destroying the graph.
    """
    if not force_full:
        raise GraphExportEmptyError(
            "incremental refresh is not supported on a codegraph workspace "
            "(no per-symbol content_hash) — use `loomgraph update` (full "
            "rebuild) or `force_full=true`"
        )
    entities, relations, summary, warnings = run_codegraph_export(repo)
    safe, warning = assess_export(summary, warnings)
    if not safe:
        raise GraphExportEmptyError(
            warning or "codegraph snapshot returned 0 entities"
        )
    result = await ingest(entities, relations, store, clear=True)
    # Record backend + provenance (mirror _async_index — all fields, so a
    # force_full refresh produces the same meta as a fresh index; codex review
    # #172: the initial index records indexed_with_version/extraction_version
    # too, and refresh must not drop them).
    set_meta = getattr(store, "set_meta", None)
    if set_meta is not None:
        meta = summary.meta or {}
        await set_meta("extraction_backend", "codegraph")
        if (fp := meta.get("codegraph_fingerprint")):
            await set_meta("codegraph_fingerprint", fp)
        if (iv := meta.get("indexed_with_version")):
            await set_meta("codegraph_indexed_with_version", iv)
        if (ev := meta.get("indexed_with_extraction_version")):
            await set_meta("codegraph_extraction_version", ev)
        await set_meta("codegraph_head", _git_head_safe())
    result["mode"] = "codegraph_rebuild"
    result["workspace"] = ws
    result["backend"] = "codegraph"
    return result
