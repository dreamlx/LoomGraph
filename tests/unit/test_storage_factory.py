"""Factory tests — verify the GraphStore/LLMClient backend selection."""

from __future__ import annotations

from pathlib import Path

import pytest

from loomgraph.core.config import reset_settings
from loomgraph.llm.lightrag_llm import LightRAGLLMClient
from loomgraph.storage.factory import (
    _resolve_db_path,
    create_graph_store,
    create_llm_client,
)
from loomgraph.storage.lightrag_store import LightRAGGraphStore
from loomgraph.storage.sqlite_store import SqliteGraphStore


@pytest.fixture(autouse=True)
def reset_global_settings() -> None:
    """Each test gets a fresh settings instance (env-var-driven)."""
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


class TestGraphStoreFactory:
    async def test_default_backend_is_lightrag(self) -> None:
        store = await create_graph_store(workspace="ws1")
        assert isinstance(store, LightRAGGraphStore)

    async def test_lightrag_backend_carries_workspace(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LOOMGRAPH_STORAGE__BACKEND", "lightrag")
        store = await create_graph_store(workspace="my_ws")
        assert isinstance(store, LightRAGGraphStore)
        assert store.client.workspace == "my_ws"

    async def test_sqlite_backend(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("LOOMGRAPH_STORAGE__BACKEND", "sqlite")
        monkeypatch.setenv(
            "LOOMGRAPH_STORAGE__DB_PATH",
            str(tmp_path / "{workspace}.db"),
        )
        store = await create_graph_store(workspace="proj1")
        try:
            assert isinstance(store, SqliteGraphStore)
            # DB file was created and is queryable
            assert (tmp_path / "proj1.db").exists()
            assert await store.get_all_entities() == []
        finally:
            await store.close()  # type: ignore[union-attr]

    async def test_sqlite_creates_parent_dir(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        nested = tmp_path / "deep" / "nested"
        monkeypatch.setenv("LOOMGRAPH_STORAGE__BACKEND", "sqlite")
        monkeypatch.setenv(
            "LOOMGRAPH_STORAGE__DB_PATH", str(nested / "{workspace}.db")
        )
        store = await create_graph_store(workspace="x")
        try:
            assert (nested / "x.db").exists()
        finally:
            await store.close()  # type: ignore[union-attr]

    async def test_unknown_backend_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LOOMGRAPH_STORAGE__BACKEND", "lightrag")
        # Direct override after settings load — patch in the config object.
        from loomgraph.core.config import get_settings

        settings = get_settings()
        settings.storage.backend = "bogus"  # type: ignore[assignment]
        with pytest.raises(ValueError, match="Unknown storage.backend"):
            await create_graph_store(workspace="x")


class TestLLMClientFactory:
    def test_returns_lightrag_adapter(self) -> None:
        llm = create_llm_client(workspace="ws1")
        assert isinstance(llm, LightRAGLLMClient)
        assert llm.client.workspace == "ws1"

    def test_no_workspace(self) -> None:
        llm = create_llm_client()
        assert isinstance(llm, LightRAGLLMClient)
        assert llm.client.workspace is None
