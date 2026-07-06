"""Tests for configuration module."""

from pathlib import Path
from unittest.mock import patch

from loomgraph.core.config import (
    ASTExtractionConfig,
    EmbeddingConfig,
    LLMConfig,
    SemanticEnhancementConfig,
    Settings,
    StorageConfig,
)


class TestASTExtractionConfig:
    """Tests for AST extraction configuration."""

    def test_default_values(self) -> None:
        config = ASTExtractionConfig()

        assert config.enabled is True
        assert config.chunking == "ast"
        assert config.extract_calls is True
        assert config.extract_inheritance is True


class TestSemanticEnhancementConfig:
    """Tests for semantic enhancement configuration."""

    def test_default_values(self) -> None:
        config = SemanticEnhancementConfig()

        assert config.enabled is False  # MVP
        assert config.description_generation is False
        assert config.pattern_recognition is False


class TestEmbeddingConfig:
    """Tests for embedding configuration (EPIC-012 / Phase 6)."""

    def test_default_values(self) -> None:
        config = EmbeddingConfig()

        assert config.enabled is False
        assert config.provider == "ollama"
        assert config.api_url == "http://localhost:11434/v1"
        assert config.model == "nomic-embed-text"
        assert config.dimension == 768
        assert config.batch_size == 32


class TestStorageConfig:
    """Tests for storage backend configuration (EPIC-011 Phase 5)."""

    def test_default_values(self) -> None:
        config = StorageConfig()

        assert config.backend == "sqlite"
        assert config.db_path == "~/.loomgraph/{workspace}.db"


class TestLLMConfig:
    """Tests for LLM provider configuration."""

    def test_default_provider_ollama(self) -> None:
        config = LLMConfig()

        assert config.provider == "ollama"
        assert config.api_url == "http://localhost:11434"
        assert config.model == "gemma3:12b-it-qat"


class TestSettings:
    """Tests for main settings."""

    def test_default_settings(self) -> None:
        settings = Settings()

        assert settings.app_name == "LoomGraph"
        assert settings.debug is False
        assert settings.indexing.ast_extraction.enabled is True
        assert settings.indexing.semantic_enhancement.enabled is False

    def test_nested_config_access(self) -> None:
        settings = Settings()

        assert settings.indexing.ast_extraction.chunking == "ast"
        assert settings.embedding.dimension == 768
        assert settings.storage.backend == "sqlite"
        assert settings.llm.provider == "ollama"
        assert settings.retrieval.default_mode == "hybrid"


class TestRemoveEnvOverrides:
    """Tests for _remove_env_overrides helper."""

    def test_strips_top_level_env_override(self) -> None:
        from loomgraph.core.config import _remove_env_overrides

        yaml_config = {"debug": True, "log_level": "DEBUG"}
        with patch.dict("os.environ", {"LOOMGRAPH_DEBUG": "false"}):
            result = _remove_env_overrides(yaml_config)

        assert "debug" not in result
        assert result["log_level"] == "DEBUG"

    def test_strips_nested_env_override(self) -> None:
        from loomgraph.core.config import _remove_env_overrides

        yaml_config = {"storage": {"db_path": "~/yaml.db", "backend": "sqlite"}}
        with patch.dict(
            "os.environ", {"LOOMGRAPH_STORAGE__DB_PATH": "~/env.db"}
        ):
            result = _remove_env_overrides(yaml_config)

        assert result["storage"]["backend"] == "sqlite"
        assert "db_path" not in result["storage"]

    def test_no_env_keeps_all_keys(self) -> None:
        from loomgraph.core.config import _remove_env_overrides

        yaml_config = {"storage": {"db_path": "~/yaml.db"}}
        with patch.dict("os.environ", {}, clear=False):
            import os

            os.environ.pop("LOOMGRAPH_STORAGE__DB_PATH", None)
            result = _remove_env_overrides(yaml_config)

        assert result == yaml_config

    def test_empty_nested_dict_removed(self) -> None:
        from loomgraph.core.config import _remove_env_overrides

        yaml_config = {"storage": {"db_path": "~/yaml.db"}}
        with patch.dict(
            "os.environ", {"LOOMGRAPH_STORAGE__DB_PATH": "~/env.db"}
        ):
            result = _remove_env_overrides(yaml_config)

        assert "storage" not in result


class TestGetSettingsEnvPriority:
    """Tests that env vars properly override YAML config."""

    def test_env_overrides_yaml(self, tmp_path: Path) -> None:
        from loomgraph.core.config import get_settings, reset_settings

        reset_settings()

        yaml_config = {"storage": {"db_path": "~/yaml.db"}}
        env_url = "~/env.db"

        with (
            patch(
                "loomgraph.core.config.load_yaml_config",
                return_value=yaml_config,
            ),
            patch.dict(
                "os.environ", {"LOOMGRAPH_STORAGE__DB_PATH": env_url}
            ),
        ):
            settings = get_settings()

        assert settings.storage.db_path == env_url
        reset_settings()

    def test_yaml_used_when_no_env(self) -> None:
        from loomgraph.core.config import get_settings, reset_settings

        reset_settings()

        yaml_config = {"storage": {"db_path": "~/yaml.db"}}

        with (
            patch(
                "loomgraph.core.config.load_yaml_config",
                return_value=yaml_config,
            ),
            patch.dict("os.environ", {}, clear=False),
        ):
            import os

            os.environ.pop("LOOMGRAPH_STORAGE__DB_PATH", None)
            settings = get_settings()

        assert settings.storage.db_path == "~/yaml.db"
        reset_settings()
