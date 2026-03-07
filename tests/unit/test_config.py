"""Tests for configuration module."""

from pathlib import Path
from unittest.mock import patch

from loomgraph.core.config import (
    ASTExtractionConfig,
    EmbeddingConfig,
    LightRAGConfig,
    SemanticEnhancementConfig,
    Settings,
)


class TestASTExtractionConfig:
    """Tests for AST extraction configuration."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = ASTExtractionConfig()

        assert config.enabled is True
        assert config.chunking == "ast"
        assert config.extract_calls is True
        assert config.extract_inheritance is True


class TestSemanticEnhancementConfig:
    """Tests for semantic enhancement configuration."""

    def test_mvp_default_disabled(self) -> None:
        """Test that semantic enhancement is disabled by default (MVP)."""
        config = SemanticEnhancementConfig()

        assert config.enabled is False
        assert config.description_generation is False
        assert config.pattern_recognition is False


class TestEmbeddingConfig:
    """Tests for embedding configuration."""

    def test_jina_defaults(self) -> None:
        """Test Jina Code V2 default settings."""
        config = EmbeddingConfig()

        assert config.provider == "jina"
        assert "jina-embeddings-v2-base-code" in config.model
        assert config.dimension == 768
        assert config.max_length == 8192
        assert config.batch_size == 32


class TestLightRAGConfig:
    """Tests for LightRAG HTTP API configuration."""

    def test_default_api_url(self) -> None:
        """Test default API URL (H200 enterprise service)."""
        config = LightRAGConfig()

        assert config.api_url == "http://117.131.45.179:3001"
        assert config.api_timeout == 30.0

    def test_default_query_mode(self) -> None:
        """Test default query mode."""
        config = LightRAGConfig()

        assert config.default_query_mode == "hybrid"


class TestSettings:
    """Tests for main settings."""

    def test_default_settings(self) -> None:
        """Test default settings creation."""
        settings = Settings()

        assert settings.app_name == "LoomGraph"
        assert settings.debug is False
        assert settings.indexing.ast_extraction.enabled is True
        assert settings.indexing.semantic_enhancement.enabled is False  # MVP

    def test_nested_config_access(self) -> None:
        """Test accessing nested configuration."""
        settings = Settings()

        # Indexing
        assert settings.indexing.ast_extraction.chunking == "ast"

        # Embedding
        assert settings.embedding.dimension == 768

        # LightRAG API (H200 enterprise service)
        assert settings.lightrag.api_url == "http://117.131.45.179:3001"

        # Retrieval
        assert settings.retrieval.default_mode == "hybrid"


class TestRemoveEnvOverrides:
    """Tests for _remove_env_overrides helper."""

    def test_strips_top_level_env_override(self) -> None:
        """Env var LOOMGRAPH_DEBUG should strip 'debug' from YAML."""
        from loomgraph.core.config import _remove_env_overrides

        yaml_config = {"debug": True, "log_level": "DEBUG"}
        with patch.dict("os.environ", {"LOOMGRAPH_DEBUG": "false"}):
            result = _remove_env_overrides(yaml_config)

        assert "debug" not in result
        assert result["log_level"] == "DEBUG"

    def test_strips_nested_env_override(self) -> None:
        """Env var LOOMGRAPH_LIGHTRAG__API_URL should strip nested key."""
        from loomgraph.core.config import _remove_env_overrides

        yaml_config = {"lightrag": {"api_url": "http://yaml:3001", "api_timeout": 30.0}}
        with patch.dict("os.environ", {"LOOMGRAPH_LIGHTRAG__API_URL": "http://env:9999"}):
            result = _remove_env_overrides(yaml_config)

        # api_url stripped, api_timeout remains
        assert result["lightrag"]["api_timeout"] == 30.0
        assert "api_url" not in result["lightrag"]

    def test_no_env_keeps_all_keys(self) -> None:
        """Without env vars, all YAML keys are preserved."""
        from loomgraph.core.config import _remove_env_overrides

        yaml_config = {"lightrag": {"api_url": "http://yaml:3001"}}
        # Ensure the specific env var is NOT set
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("LOOMGRAPH_LIGHTRAG__API_URL", None)
            result = _remove_env_overrides(yaml_config)

        assert result == yaml_config

    def test_empty_nested_dict_removed(self) -> None:
        """If all keys in a nested dict are stripped, the parent key is omitted."""
        from loomgraph.core.config import _remove_env_overrides

        yaml_config = {"lightrag": {"api_url": "http://yaml:3001"}}
        with patch.dict("os.environ", {"LOOMGRAPH_LIGHTRAG__API_URL": "http://env:9999"}):
            result = _remove_env_overrides(yaml_config)

        assert "lightrag" not in result


class TestGetSettingsEnvPriority:
    """Tests that env vars properly override YAML config."""

    def test_env_overrides_yaml(self, tmp_path: Path) -> None:
        """Env var should take precedence over YAML value."""
        from loomgraph.core.config import get_settings, reset_settings

        reset_settings()

        yaml_config = {"lightrag": {"api_url": "http://yaml-server:3001"}}
        env_url = "http://env-override:9999"

        with (
            patch("loomgraph.core.config.load_yaml_config", return_value=yaml_config),
            patch.dict("os.environ", {"LOOMGRAPH_LIGHTRAG__API_URL": env_url}),
        ):
            settings = get_settings()

        assert settings.lightrag.api_url == env_url
        reset_settings()

    def test_yaml_used_when_no_env(self) -> None:
        """YAML value should be used when no env var is set."""
        from loomgraph.core.config import get_settings, reset_settings

        reset_settings()

        yaml_config = {"lightrag": {"api_url": "http://yaml-server:3001"}}

        with (
            patch("loomgraph.core.config.load_yaml_config", return_value=yaml_config),
            patch.dict("os.environ", {}, clear=False),
        ):
            import os
            os.environ.pop("LOOMGRAPH_LIGHTRAG__API_URL", None)
            settings = get_settings()

        assert settings.lightrag.api_url == "http://yaml-server:3001"
        reset_settings()
