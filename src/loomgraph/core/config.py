"""Configuration management for LoomGraph."""

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ASTExtractionConfig(BaseSettings):
    """AST extraction configuration."""

    enabled: bool = True
    chunking: Literal["ast", "token"] = "ast"
    extract_calls: bool = True
    extract_inheritance: bool = True


class SemanticEnhancementConfig(BaseSettings):
    """LLM semantic enhancement configuration (disabled in MVP)."""

    enabled: bool = False  # MVP default: disabled
    description_generation: bool = False
    pattern_recognition: bool = False


class IndexingConfig(BaseSettings):
    """Indexing pipeline configuration."""

    ast_extraction: ASTExtractionConfig = Field(default_factory=ASTExtractionConfig)
    semantic_enhancement: SemanticEnhancementConfig = Field(
        default_factory=SemanticEnhancementConfig
    )


class EmbeddingConfig(BaseSettings):
    """Jina Code V2 embedding configuration."""

    provider: Literal["jina", "openai", "local"] = "jina"
    model: str = "jinaai/jina-embeddings-v2-base-code"
    base_url: str = "http://localhost:8080"
    batch_size: int = 32
    max_length: int = 8192
    dimension: int = 768
    timeout: float = 30.0


class LightRAGConfig(BaseSettings):
    """LightRAG connection configuration.

    LoomGraph delegates all storage to LightRAG.
    These settings are passed to LightRAG for initialization.
    """

    # PostgreSQL (LightRAG storage backend)
    pg_host: str = "localhost"
    pg_port: int = 5432
    pg_database: str = "loomgraph"
    pg_user: str = "loomgraph"
    pg_password: str = "loomgraph_dev"

    # LightRAG storage backends
    graph_storage: str = "PGGraphStorage"
    vector_storage: str = "PGVectorStorage"
    kv_storage: str = "PGKVStorage"
    doc_status_storage: str = "PGDocStatusStorage"

    @property
    def pg_connection_string(self) -> str:
        """Generate PostgreSQL connection string for LightRAG."""
        return f"postgresql://{self.pg_user}:{self.pg_password}@{self.pg_host}:{self.pg_port}/{self.pg_database}"


class RetrievalConfig(BaseSettings):
    """Retrieval configuration."""

    modes: list[str] = ["keyword", "semantic", "graph"]
    default_mode: Literal["keyword", "semantic", "graph", "hybrid"] = "hybrid"
    top_k: int = 10
    similarity_threshold: float = 0.7


class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_prefix="LOOMGRAPH_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = "LoomGraph"
    debug: bool = False
    log_level: str = "INFO"

    # Working directory for index storage
    working_dir: Path = Path(".loomgraph")

    # Sub-configurations
    indexing: IndexingConfig = Field(default_factory=IndexingConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    lightrag: LightRAGConfig = Field(default_factory=LightRAGConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)

    def ensure_working_dir(self) -> Path:
        """Ensure working directory exists and return it."""
        self.working_dir.mkdir(parents=True, exist_ok=True)
        return self.working_dir


# Global settings instance (lazy loaded)
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get or create global settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
