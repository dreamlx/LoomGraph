"""Tests for configuration module."""

import pytest

from loomgraph.core.config import (
    ASTExtractionConfig,
    DatabaseConfig,
    EmbeddingConfig,
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


class TestDatabaseConfig:
    """Tests for database configuration."""

    def test_connection_string(self) -> None:
        """Test connection string generation."""
        config = DatabaseConfig(
            host="localhost",
            port=5432,
            database="testdb",
            user="testuser",
            password="testpass",
        )

        assert "postgresql://testuser:testpass@localhost:5432/testdb" == config.connection_string

    def test_async_connection_string(self) -> None:
        """Test async connection string generation."""
        config = DatabaseConfig()

        assert "postgresql+asyncpg://" in config.async_connection_string


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

        # Database
        assert settings.database.database == "loomgraph"

        # Retrieval
        assert settings.retrieval.default_mode == "hybrid"
