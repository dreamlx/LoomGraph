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
