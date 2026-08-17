"""CLI commands for indexing and updating the knowledge graph."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

import click

from loomgraph.cli._common import ErrorCode, get_auto_workspace, output_error, output_success
from loomgraph.cli._deps_check import check_codeindex
from loomgraph.cli.main import main
from loomgraph.core.git import (
    get_changed_files,
    get_working_tree_files,
    is_git_repository,
)
from loomgraph.core.graph_export_ingest import (
    GraphExportEmptyError,
    GraphExportError,
    assess_export,
    ingest,
    ingest_incremental,
    run_graph_export,
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
@click.argument("repo_path", type=click.Path(exists=True))
@click.option("--clear/--no-clear", default=True, help="Clear old data before indexing")
@click.option("--workspace", "-w", default=None, help="Workspace name (default: current directory name)")
def index(repo_path: str, clear: bool, workspace: str | None) -> None:
    """Index a code repository (one-step pipeline).

    Calls: codeindex graph-export → embed → inject (module-qualified entity
    ids — fixes the cross-module same-name collision, #66).

    REPO_PATH: Directory path to index
    """
    import time

    start_time = time.time()
    repo = Path(repo_path).resolve()

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

    # Step 2: Run codeindex graph-export (qualified entity ids + edges)
    click.echo(f"[2/3] Exporting {repo.name}/ with codeindex graph-export...", err=True)
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

    # codeindex's partial-graph warnings (#131) — e.g. a non-Python repo
    # indexed with default languages:[python] yields a few stray entities and
    # a "WARNING: partial graph" line. Surface it so a misconfigured repo
    # doesn't index as a silent success (#108).
    raw_warnings = warnings
    # #161: >0 entities can still be a partial graph (stray .py only) — the
    # language fingerprint names the dominant language the config missed.
    # Appended BEFORE silence so it's filterable like codeindex's own warnings.
    if summary.entity_count > 0:
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
        click.echo(f"⚠️  WARNING: {zero_warning}", err=True)
        output_error(
            code=ErrorCode.GRAPH_EXPORT_EMPTY,
            message=zero_warning,
        )

    # Step 3: Embed + inject asynchronously
    click.echo("[3/3] Injecting into knowledge graph...", err=True)
    try:
        result = asyncio.run(_async_index(entities, relations, workspace, clear))
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

    output_success(result)


async def _async_index(
    entities: list[Any],
    relations: list[Any],
    workspace: str | None,
    clear: bool,
) -> dict[str, Any]:
    """Resolve workspace, build the store, run the shared ingest pipeline.

    Receives already-mapped entities/relations from ``run_graph_export``
    (module-qualified ids — fixes the cross-module same-name collision, #66).
    Delegates embed + insert to :func:`ingest`.
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
def update(
    since: str,
    workspace: str | None,
    files: str | None,
    embedding_url: str | None,
    use_affected: bool,
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
    raw_warnings = warnings
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

    output_success(result)


async def _async_update(
    entities: list[Any],
    relations: list[Any],
    workspace: str | None,
    repo: Path,
    since: str,
    forced_whole_tree: bool,
    config_rebuild: bool = False,
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

    Branching:

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

    if force_full:
        entities, relations, summary, warnings = run_graph_export(repo)
        # #120: a 0-entity export is almost always a languages/grammar mismatch
        # — clearing on top of it would silently wipe the whole workspace.
        # Hard-stop before ingest(clear=True); surface the diagnosis instead.
        safe, warning = assess_export(summary, warnings)
        if not safe:
            # #141: surface as an error (CLI exit 1 / MCP error envelope), not
            # a silent success. assess_export's warning carries the root cause.
            raise GraphExportEmptyError(warning or "graph-export returned 0 entities")
        result = await ingest(entities, relations, store, clear=True)
        result["mode"] = "cold_rebuild"
        result["workspace"] = ws
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
    safe, warning = assess_export(summary, warnings)
    if not safe:
        # #141: surface as an error (CLI exit 1 / MCP error envelope), not a
        # silent success. assess_export's warning carries the root cause.
        raise GraphExportEmptyError(warning or "graph-export returned 0 entities")
    if strategy == "incremental":
        result = await ingest_incremental(
            entities, relations, store, changed_files=changed_files
        )
        result["mode"] = "warm_incremental"
    else:
        result = await ingest(entities, relations, store, clear=False)
        result["mode"] = "whole_tree_upsert"

    result["workspace"] = ws
    return result
