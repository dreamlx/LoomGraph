"""`loomgraph branch-diff <A>..<B>` — 两个 ref 的结构性 diff(EPIC-016 #185)。

一条命令:自动 provision 缺失 ref 的快照(`git worktree add --detach` 临时
目录 + 冷索引成独立 workspace),再跑 `BranchDiffAnalyzer` 的方向性深 diff。
不复用当前 checkout 的 workspace——refresh 进去的未提交编辑绝不能漏进 ref
diff(same-input-same-output)。

provisioned workspace 是一次性 cache(#185 决策表):meta 打标
``provisioned_by="branch-diff"``;同 ref 同 sha → reused,同 ref 分支移动 →
原地 rebuilt(tag 过的 cache 可弃,陈旧 diff = 静默错误输出);非 tag 的库
(用户自己的 / sanitize 碰撞)永不 clobber → fallback 名带 short sha。
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import click

from loomgraph.cli._common import ErrorCode, output_error, output_success
from loomgraph.cli._deps_check import check_codeindex
from loomgraph.cli._indexing import _async_index, _run_export
from loomgraph.cli.main import main
from loomgraph.core.git import (
    GitError,
    is_git_repository,
    resolve_ref,
    worktree_add,
    worktree_remove,
)
from loomgraph.core.graph_export_ingest import (
    GraphExportEmptyError,
    GraphExportError,
    assess_export,
)


def _parse_ref_range(value: str) -> tuple[str, str] | None:
    """``A..B`` → (base, head);恰好一个 ``..`` 且两侧非空。

    git 的三点 ``A...B`` 是对称 diff 语法,不在本命令语义内 → 拒绝。
    """
    if "..." in value or value.count("..") != 1:
        return None
    base, head = value.split("..")
    if not base.strip() or not head.strip():
        return None
    return base.strip(), head.strip()


@contextmanager
def _worktree_at(repo: Path, sha: str) -> Iterator[Path]:
    """临时 worktree(repo 外),退出时 best-effort 清理。

    mkdtemp 只用来占一个唯一名——git worktree add 要求目标目录不存在。
    """
    tmp = Path(tempfile.mkdtemp(prefix="loomgraph-bd-"))
    tmp.rmdir()
    try:
        worktree_add(repo, tmp, sha)
        yield tmp
    finally:
        try:
            worktree_remove(repo, tmp)
        except Exception:
            shutil.rmtree(tmp, ignore_errors=True)


async def _decide_workspace(repo_dir: str, ref: str, sha: str) -> tuple[str, str]:
    """provisioning 决策表(#185):返回 (workspace 名, created|reused|rebuilt)。

    先试候选名 ``<repo>:<ref>``(db-path 同款 sanitize),被占则试 fallback
    ``<名>-<sha[:7]>``。只自动管理打了 ``provisioned_by`` 标的库;非 tag 的
    非空库(用户自己的 workspace)绝不触碰。
    """
    from loomgraph.storage.factory import create_graph_store

    candidate = f"{repo_dir}:{ref}".replace("\\", "/").replace("/", "-")
    names = (candidate, f"{candidate}-{sha[:7]}")
    for name in names:
        store = await create_graph_store(workspace=name)
        try:
            get_meta = getattr(store, "get_meta", None)
            stats = await store.get_graph_stats()
            by = tagged_ref = None
            if get_meta is not None:
                by = await get_meta("provisioned_by")
                tagged_ref = await get_meta("provisioned_ref")
                tagged_sha = await get_meta("provisioned_sha")
            if by == "branch-diff":
                if tagged_ref == ref:
                    return name, ("reused" if tagged_sha == sha else "rebuilt")
                # 我们另一个 ref 的 cache(sanitize 碰撞)→ 不互相 clobber,试 fallback
            elif stats.get("entity_count", 0) == 0:
                # 非 tag 且空:fresh(本调用刚开出来)或中断残留 → 认领
                return name, "created"
            # 非 tag 且非空:用户库 → 试 fallback
        finally:
            close = getattr(store, "close", None)
            if close is not None:
                await close()
    raise ValueError(
        f"workspace names {list(names)} are both occupied by non-provisioned "
        f"workspaces; refusing to clobber (delete one or rename the ref)"
    )


def _provision_ref(repo: Path, repo_dir: str, ref: str, sha: str) -> dict[str, Any]:
    """Provision 一个 ref 的快照 workspace;reused 时零成本短路。"""
    start = time.time()
    name, action = asyncio.run(_decide_workspace(repo_dir, ref, sha))
    info: dict[str, Any] = {
        "ref": ref, "sha": sha, "workspace": name, "provisioned": action,
    }
    if action == "reused":
        return info
    with _worktree_at(repo, sha) as wt:
        entities, relations, summary, warnings = _run_export("codeindex", wt)
        safe, warning = assess_export(summary, warnings)
        if not safe:
            raise GraphExportEmptyError(
                warning or f"graph-export returned 0 entities for ref {ref!r}"
            )
        asyncio.run(_async_index(
            entities, relations, name, clear=True, backend="codeindex",
            summary=summary,
            extra_meta={
                "provisioned_by": "branch-diff",
                "provisioned_ref": ref,
                "provisioned_sha": sha,
            },
        ))
    info["duration_seconds"] = round(time.time() - start, 2)
    return info


async def _async_branch_diff(base_ws: str, head_ws: str) -> dict[str, Any]:
    """开两个 store 跑方向性 diff,finally 真 close(#172)。"""
    from loomgraph.core.branch_diff import BranchDiffAnalyzer
    from loomgraph.storage.factory import create_graph_store

    base_store = await create_graph_store(workspace=base_ws)
    head_store = await create_graph_store(workspace=head_ws)
    try:
        result = await BranchDiffAnalyzer(
            base_store=base_store, head_store=head_store,
            base=base_ws, head=head_ws,
        ).analyze()
        return result.to_dict()
    finally:
        close_b = getattr(base_store, "close", None)
        close_h = getattr(head_store, "close", None)
        if close_b is not None:
            await close_b()
        if close_h is not None:
            await close_h()


@main.command()
@click.argument("ref_range")
def branch_diff(ref_range: str) -> None:
    """Structural diff between two git refs (REF_RANGE = "base..head").

    Auto-provisions snapshot workspaces for missing refs (worktree + cold
    index), then diffs: entity/edge added+removed, broken chains, new chains,
    content_hash changes, module coupling delta.
    """
    start = time.time()
    repo = Path.cwd().resolve()
    if not is_git_repository(repo):
        output_error(
            code=ErrorCode.GIT_ERROR,
            message=f"Not a git repository: {repo}",
            suggestion="Run branch-diff from inside a git repository.",
        )
        return

    parsed = _parse_ref_range(ref_range)
    if parsed is None:
        output_error(
            code=ErrorCode.INVALID_INPUT,
            message=f"Invalid ref range {ref_range!r}",
            suggestion='Use "base..head" — exactly one ".." (git diff direction).',
        )
        return
    base_ref, head_ref = parsed

    codeindex_status = check_codeindex()
    if not codeindex_status.get("installed"):
        output_error(
            code=ErrorCode.CODEINDEX_NOT_FOUND,
            message="codeindex not found in the loomgraph environment",
            suggestion="Install codeindex: pip install ai-codeindex",
        )
        return

    try:
        base_sha = resolve_ref(repo, base_ref)
        head_sha = resolve_ref(repo, head_ref)
    except GitError as e:
        output_error(code=ErrorCode.GIT_ERROR, message=str(e))
        return

    repo_dir = repo.name.lower()
    try:
        click.echo(
            f"[1/2] Provisioning base '{base_ref}' ({base_sha[:7]})...", err=True
        )
        base_info = _provision_ref(repo, repo_dir, base_ref, base_sha)
        click.echo(
            f"[2/2] Provisioning head '{head_ref}' ({head_sha[:7]})...", err=True
        )
        head_info = _provision_ref(repo, repo_dir, head_ref, head_sha)
        click.echo("Diffing snapshots...", err=True)
        diff = asyncio.run(
            _async_branch_diff(base_info["workspace"], head_info["workspace"])
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
        return
    except GraphExportError as e:
        output_error(code=ErrorCode.CODEINDEX_FAILED, message=str(e))
        return
    except GitError as e:
        output_error(code=ErrorCode.GIT_ERROR, message=str(e))
        return

    output_success({
        "base": base_info,
        "head": head_info,
        "diff": diff,
        "duration_seconds": round(time.time() - start, 2),
    })
