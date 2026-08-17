"""Factory tests — verify the GraphStore/LLMClient backend selection."""

from __future__ import annotations

from pathlib import Path

import pytest

from loomgraph.core.config import reset_settings
from loomgraph.llm.direct import DirectLLMClient
from loomgraph.storage.factory import (
    _resolve_db_path,
    create_graph_store,
    create_llm_client,
)
from loomgraph.storage.sqlite_store import SqliteGraphStore


@pytest.fixture(autouse=True)
def reset_global_settings() -> None:
    reset_settings()
    yield
    reset_settings()


class TestDBPathResolution:
    def test_expands_workspace_placeholder(self, tmp_path: Path) -> None:
        template = str(tmp_path / "{workspace}.db")
        resolved = _resolve_db_path(template, "myproj")
        assert resolved == tmp_path / "myproj.db"

    def test_expands_tilde(self) -> None:
        resolved = _resolve_db_path("~/x.db", None)
        assert "~" not in str(resolved)
        assert str(resolved).startswith(str(Path.home()))

    def test_no_workspace_no_substitution(self, tmp_path: Path) -> None:
        template = str(tmp_path / "fixed.db")
        resolved = _resolve_db_path(template, None)
        assert resolved == tmp_path / "fixed.db"

    def test_sanitizes_slash_in_workspace_name(self, tmp_path: Path) -> None:
        """A `/` in the branch (codex/foo) must not create a subdirectory —
        sanitize to a single filename component so the DB stays discoverable
        at the top level (#99)."""
        template = str(tmp_path / "{workspace}.db")
        resolved = _resolve_db_path(template, "internal-ts:codex/foo")
        assert resolved.parent == tmp_path
        assert resolved.name == "internal-ts:codex-foo.db"

    def test_sanitizes_backslash_in_workspace_name(self, tmp_path: Path) -> None:
        template = str(tmp_path / "{workspace}.db")
        resolved = _resolve_db_path(template, r"proj:bugfix\x")
        assert resolved.parent == tmp_path
        assert resolved.name == "proj:bugfix-x.db"

    def test_workspace_without_slash_unchanged(self, tmp_path: Path) -> None:
        """Existing workspace names (no slash) must round-trip untouched (#99
        regression guard)."""
        template = str(tmp_path / "{workspace}.db")
        resolved = _resolve_db_path(template, "loomgraph:main")
        assert resolved == tmp_path / "loomgraph:main.db"

    def test_placeholder_without_workspace_raises(self, tmp_path: Path) -> None:
        """#176: a falsy workspace with a {workspace} placeholder in the
        template must fail loud — silently proceeding created a literal
        ~/.loomgraph/{workspace}.db that every None-caller would silently
        share (and which then pollutes `workspace list`)."""
        template = str(tmp_path / "{workspace}.db")
        with pytest.raises(ValueError, match="workspace"):
            _resolve_db_path(template, None)
        with pytest.raises(ValueError, match="workspace"):
            _resolve_db_path(template, "")


class TestGraphStoreFactory:
    async def test_sqlite_backend_default(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv(
            "LOOMGRAPH_STORAGE__DB_PATH", str(tmp_path / "{workspace}.db")
        )
        store = await create_graph_store(workspace="proj1")
        try:
            assert isinstance(store, SqliteGraphStore)
            assert (tmp_path / "proj1.db").exists()
            assert await store.get_all_entities() == []
        finally:
            await store.close()

    async def test_discovery_handle_creates_no_db_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """#176: workspace=None is the discovery pattern (`workspace list`,
        `similar`) — it must not create a literal {workspace}.db on disk."""
        monkeypatch.setenv(
            "LOOMGRAPH_STORAGE__DB_PATH", str(tmp_path / "{workspace}.db")
        )
        store = await create_graph_store(workspace=None)
        try:
            assert await store.list_workspaces() == []
        finally:
            await store.close()
        assert list(tmp_path.glob("*.db")) == []

    async def test_sqlite_creates_parent_dir(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        nested = tmp_path / "deep" / "nested"
        monkeypatch.setenv(
            "LOOMGRAPH_STORAGE__DB_PATH", str(nested / "{workspace}.db")
        )
        store = await create_graph_store(workspace="x")
        try:
            assert (nested / "x.db").exists()
        finally:
            await store.close()


class TestLLMClientFactory:
    def test_default_provider_glm(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("LOOMGRAPH_LLM__PROVIDER", raising=False)
        llm = create_llm_client(workspace="ws1")
        assert isinstance(llm, DirectLLMClient)

    def test_glm_provider(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LOOMGRAPH_LLM__PROVIDER", "glm")
        monkeypatch.setenv("LOOMGRAPH_LLM__API_URL", "http://h200:3000")
        monkeypatch.setenv("LOOMGRAPH_LLM__MODEL", "glm-4-air")
        llm = create_llm_client()
        assert isinstance(llm, DirectLLMClient)
        assert llm.base_url == "http://h200:3000"
        assert llm.model == "glm-4-air"

    def test_openrouter_provider(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LOOMGRAPH_LLM__PROVIDER", "openrouter")
        monkeypatch.setenv(
            "LOOMGRAPH_LLM__API_URL", "https://openrouter.ai/api"
        )
        monkeypatch.setenv("LOOMGRAPH_LLM__API_KEY", "sk-test")
        llm = create_llm_client()
        assert isinstance(llm, DirectLLMClient)
        assert llm.api_key == "sk-test"

    def test_vllm_provider(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LOOMGRAPH_LLM__PROVIDER", "vllm")
        llm = create_llm_client()
        assert isinstance(llm, DirectLLMClient)
