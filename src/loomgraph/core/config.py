"""Configuration management using pydantic-settings."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """PostgreSQL database configuration."""

    model_config = SettingsConfigDict(env_prefix="LOOMGRAPH_DB_")

    host: str = Field(default="localhost", description="Database host")
    port: int = Field(default=5432, description="Database port")
    name: str = Field(default="loomgraph", description="Database name")
    user: str = Field(default="loomgraph", description="Database user")
    password: str = Field(default="", description="Database password")
    pool_min_size: int = Field(default=5, description="Minimum pool size")
    pool_max_size: int = Field(default=20, description="Maximum pool size")

    @property
    def dsn(self) -> str:
        """Generate PostgreSQL DSN."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


class EmbeddingSettings(BaseSettings):
    """Jina Code V2 embedding service configuration."""

    model_config = SettingsConfigDict(env_prefix="LOOMGRAPH_EMBEDDING_")

    base_url: str = Field(
        default="http://localhost:8080",
        description="Embedding service base URL (TEI)",
    )
    model_name: str = Field(
        default="jinaai/jina-embeddings-v2-base-code",
        description="Embedding model name",
    )
    dimension: int = Field(default=768, description="Embedding dimension")
    max_length: int = Field(default=8192, description="Maximum input length")
    batch_size: int = Field(default=32, description="Batch size for embedding")
    timeout: float = Field(default=30.0, description="Request timeout in seconds")


class LLMSettings(BaseSettings):
    """vLLM service configuration for graph extraction."""

    model_config = SettingsConfigDict(env_prefix="LOOMGRAPH_LLM_")

    base_url: str = Field(
        default="http://localhost:8000/v1",
        description="vLLM OpenAI-compatible API base URL",
    )
    model_name: str = Field(
        default="deepseek-ai/deepseek-coder-v2-lite-instruct",
        description="LLM model name",
    )
    api_key: str = Field(default="EMPTY", description="API key (EMPTY for local)")
    max_tokens: int = Field(default=4096, description="Maximum output tokens")
    temperature: float = Field(default=0.1, description="Sampling temperature")
    timeout: float = Field(default=120.0, description="Request timeout in seconds")


class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_prefix="LOOMGRAPH_",
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
    )

    # Application
    debug: bool = Field(default=False, description="Debug mode")
    working_dir: str = Field(default=".loomgraph", description="Working directory")

    # Sub-settings
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)


# Global settings instance
settings = Settings()
