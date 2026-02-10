"""Tests for configuration module."""

import pytest

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

        assert config.api_url == "http://internal.example.invalid:3001"
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
        assert settings.lightrag.api_url == "http://internal.example.invalid:3001"

        # Retrieval
        assert settings.retrieval.default_mode == "hybrid"
