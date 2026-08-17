"""#161: 非 Python 仓无 `.codeindex.yaml` 时的语言指纹 warning。

场景(HEXFORCE-RN dogfood):RN 全 TS 仓,无 `.codeindex.yaml` → codeindex 默认
`languages=["python"]`,静默只抓到 Pods 里的零星 2 个 .py —— **7≠0 不触发
0-entity gate**,输出 success,用户拿到 0% 覆盖目标语言的残缺图,无任何信号。

修复是呈现层 warning(不阻断、exit code 不变,对齐 codeindex 的
"提醒+建议不自动 fallback" 哲学):repo 主语言文件数 >> 生效 languages 覆盖的
文件数时,提示把该语言加进 `.codeindex.yaml`。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from loomgraph.cli._indexing import _language_fingerprint_warning
from loomgraph.cli.main import main


def _make_repo(repo: Path, files: dict[str, int]) -> None:
    """files: {pattern: count} — write `f{i}.ext` under repo for each."""
    repo.mkdir(parents=True, exist_ok=True)
    for pattern, count in files.items():
        for i in range(count):
            p = repo / pattern.replace("{}", str(i))
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("// x\n")


# ─── 函数级:指纹检测 ───────────────────────────────────────────────────────


def test_warns_on_dominant_unindexed_language(tmp_path: Path) -> None:
    """TS 仓无 .codeindex.yaml(默认 languages=[python])→ 指名 typescript。"""
    repo = tmp_path / "repo"
    _make_repo(repo, {"src/f{}.ts": 30, "src/f{}.tsx": 5, "Pods/p{}.py": 2})
    warn = _language_fingerprint_warning(repo)
    assert warn is not None
    assert "typescript" in warn
    assert ".codeindex.yaml" in warn


def test_silent_when_language_already_configured(tmp_path: Path) -> None:
    """.codeindex.yaml languages 含 typescript → 已覆盖,不告警。"""
    repo = tmp_path / "repo"
    _make_repo(repo, {"src/f{}.ts": 30})
    (repo / ".codeindex.yaml").write_text("languages: [typescript]\n")
    assert _language_fingerprint_warning(repo) is None


def test_silent_on_pure_python_repo(tmp_path: Path) -> None:
    """纯 Python 仓无配置(默认 python)→ 正常,不告警。"""
    repo = tmp_path / "repo"
    _make_repo(repo, {"src/f{}.py": 40})
    assert _language_fingerprint_warning(repo) is None


def test_silent_below_file_threshold(tmp_path: Path) -> None:
    """少量工具脚本(<10)不是"主语言漏配"→ 不告警,避免小仓误报。"""
    repo = tmp_path / "repo"
    _make_repo(repo, {"src/f{}.py": 40, "tools/t{}.js": 5})
    assert _language_fingerprint_warning(repo) is None


def test_minority_language_not_dominant(tmp_path: Path) -> None:
    """非 dominant 的语言不告警:python 主导 + typescript 配置里,少量 .py
    不构成"漏配"(dominant 须超过 languages 覆盖的文件总数)。"""
    repo = tmp_path / "repo"
    _make_repo(repo, {"src/f{}.py": 40, "scripts/s{}.ts": 12})
    (repo / ".codeindex.yaml").write_text("languages: [python]\n")
    assert _language_fingerprint_warning(repo) is None


def test_vendored_dirs_excluded(tmp_path: Path) -> None:
    """node_modules/Pods 里的第三方代码不算 repo 语言指纹。"""
    repo = tmp_path / "repo"
    _make_repo(repo, {"src/f{}.py": 20, "node_modules/lib/l{}.js": 500})
    assert _language_fingerprint_warning(repo) is None


def test_unsupported_language_not_fingerprinted(tmp_path: Path) -> None:
    """codeindex 不解析的语言(kotlin/rust/go…)不进指纹集——告警它没有意义。"""
    repo = tmp_path / "repo"
    _make_repo(repo, {"app/F{}.kt": 25})
    assert _language_fingerprint_warning(repo) is None


def test_java_repo_without_config_warns(tmp_path: Path) -> None:
    """纯 Java 仓无配置(而非 0-entity 的混合场景)同样要告警。"""
    repo = tmp_path / "repo"
    _make_repo(repo, {"src/main/java/F{}.java": 20})
    warn = _language_fingerprint_warning(repo)
    assert warn is not None and "java" in warn


# ─── CLI 接线:index 输出携带 warning(可被 warnings.silence 静默)─────────


def _patch_index_env(monkeypatch: pytest.MonkeyPatch, repo: Path) -> None:
    from unittest.mock import AsyncMock, MagicMock

    from loomgraph.cli import _indexing
    from loomgraph.core.graph_export_ingest import ImportSummary
    from loomgraph.core.models import EntityData

    monkeypatch.chdir(repo)
    monkeypatch.setattr(
        _indexing, "check_codeindex", lambda: {"installed": True},
    )
    # 2 entities(>0,绕开 0-entity gate——指纹 warning 针对"有实体但覆盖错语言")
    monkeypatch.setattr(
        _indexing, "run_graph_export",
        lambda r: ([EntityData("a", {}), EntityData("b", {})], [],
                   ImportSummary(entity_count=2), []),
    )
    # Store with async set_meta (#152: _async_index now records extraction_backend).
    store = MagicMock()
    store.set_meta = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "loomgraph.storage.factory.create_graph_store",
        AsyncMock(return_value=store),
    )
    monkeypatch.setattr(
        _indexing, "ingest",
        AsyncMock(return_value={
            "cleared": True, "entities_created": 2, "relations_created": 0,
            "resolved_ratio": None, "embedded": 0, "store_stats": {},
        }),
    )


def test_index_output_carries_fingerprint_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """index JSON 的 warning 字段带上指纹提示(agent 可见,不阻断)。"""
    repo = tmp_path / "repo"
    _make_repo(repo, {"src/f{}.ts": 30, "Pods/p{}.py": 2})
    _patch_index_env(monkeypatch, repo)

    res = CliRunner().invoke(main, ["index", str(repo)])
    assert res.exit_code == 0, res.output
    data = json.loads(res.stdout)["data"]
    assert data.get("warning"), "fingerprint warning must reach the JSON output"
    assert "typescript" in data["warning"]


def test_fingerprint_warning_respects_silence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """指纹 warning 走 warnings.silence(与 codeindex stderr warnings 同管道)。"""
    from loomgraph.core.config import get_settings

    repo = tmp_path / "repo"
    _make_repo(repo, {"src/f{}.ts": 30})
    _patch_index_env(monkeypatch, repo)
    monkeypatch.setattr(
        get_settings().warnings, "silence", ["source files, none indexed"],
    )

    res = CliRunner().invoke(main, ["index", str(repo)])
    assert res.exit_code == 0, res.output
    data = json.loads(res.stdout)["data"]
    assert not data.get("warning"), (
        f"silenced pattern must drop the fingerprint warning, got {data.get('warning')!r}"
    )


# ─── #162: 极低 resolved_ratio 的解读提示(档位见 docs/guides/index-output.md)──


def test_index_hints_on_very_low_resolved_ratio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """resolved_ratio < 0.1(已知盲区档:PetClinic DI 4.9% / HEXFORCE TS 6.1%)
    → index 输出附解读提示,不阻断。"""
    from unittest.mock import AsyncMock

    from loomgraph.cli import _indexing

    repo = tmp_path / "repo"
    _make_repo(repo, {"src/f{}.py": 10})
    _patch_index_env(monkeypatch, repo)
    monkeypatch.setattr(
        _indexing, "ingest",
        AsyncMock(return_value={
            "cleared": True, "entities_created": 2, "relations_created": 100,
            "resolved_ratio": 0.0614, "embedded": 0, "store_stats": {},
        }),
    )

    res = CliRunner().invoke(main, ["index", str(repo)])
    assert res.exit_code == 0, res.output
    warning = json.loads(res.stdout)["data"].get("warning", "")
    assert "resolved_ratio 0.0614" in warning, (
        f"low-resolution hint missing from index output: {warning!r}"
    )


def test_index_no_hint_at_typical_ratio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """~0.2 是正常 Python 仓水平(loomgraph self 0.19)——不该刷屏提示。"""
    from unittest.mock import AsyncMock

    from loomgraph.cli import _indexing

    repo = tmp_path / "repo"
    _make_repo(repo, {"src/f{}.py": 10})
    _patch_index_env(monkeypatch, repo)
    monkeypatch.setattr(
        _indexing, "ingest",
        AsyncMock(return_value={
            "cleared": True, "entities_created": 2, "relations_created": 100,
            "resolved_ratio": 0.19, "embedded": 0, "store_stats": {},
        }),
    )

    res = CliRunner().invoke(main, ["index", str(repo)])
    assert res.exit_code == 0, res.output
    warning = json.loads(res.stdout)["data"].get("warning", "")
    assert "resolved_ratio" not in warning, (
        f"normal Python-level ratio must not trigger the hint: {warning!r}"
    )
