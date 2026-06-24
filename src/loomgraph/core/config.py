"""Configuration management for LoomGraph.

Configuration priority (highest to lowest):
1. Environment variables (LOOMGRAPH_*)
2. .loomgraph.yaml in current directory
3. ~/.config/loomgraph/config.yaml
4. Default values
"""

import os
from pathlib import Path
from typing import Any, Literal

import yaml
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
    # Default: H200 TEI Jina Code V2 service
    base_url: str = "http://internal.example.invalid:3002"
    batch_size: int = 32
    max_length: int = 8192
    dimension: int = 768
    timeout: float = 30.0


class LightRAGConfig(BaseSettings):
    """LightRAG connection configuration.

    LoomGraph delegates all storage to LightRAG via HTTP API.
    """

    # Default: H200 LightRAG API service
    api_url: str = "http://internal.example.invalid:3001"
    api_timeout: float = 30.0

    # Query settings
    default_query_mode: Literal["local", "global", "hybrid", "naive"] = "hybrid"


class StorageConfig(BaseSettings):
    """Storage backend selection (EPIC-011 / ADR-013).

    Phase 1 default remains `lightrag` so existing deployments are unaffected.
    Phase 2 flips the default to `sqlite`; Phase 5 removes the lightrag option.
    """

    backend: Literal["lightrag", "sqlite"] = "lightrag"
    # For sqlite: filesystem path template. `{workspace}` is substituted at
    # runtime with the resolved workspace name. `~` is expanded.
    db_path: str = "~/.loomgraph/{workspace}.db"


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
    storage: StorageConfig = Field(default_factory=StorageConfig)


# Global settings instance (lazy loaded)
_settings: Settings | None = None

# Config file locations (in priority order)
CONFIG_LOCATIONS = [
    Path(".loomgraph.yaml"),
    Path(".loomgraph.yml"),
    Path.home() / ".config" / "loomgraph" / "config.yaml",
    Path.home() / ".config" / "loomgraph" / "config.yml",
]


def load_yaml_config() -> dict[str, Any]:
    """Load configuration from YAML file.

    Searches for config files in priority order:
    1. .loomgraph.yaml in current directory
    2. .loomgraph.yml in current directory
    3. ~/.config/loomgraph/config.yaml
    4. ~/.config/loomgraph/config.yml

    Returns:
        Configuration dict, or empty dict if no config file found
    """
    for config_path in CONFIG_LOCATIONS:
        if config_path.exists():
            try:
                with open(config_path) as f:
                    config = yaml.safe_load(f) or {}
                return config
            except yaml.YAMLError:
                # Skip invalid YAML files
                continue
    return {}


def flatten_dict(d: dict[str, Any], parent_key: str = "", sep: str = "__") -> dict[str, Any]:
    """Flatten nested dict for pydantic-settings compatibility.

    Example:
        {"lightrag": {"api_url": "http://..."}}
        becomes
        {"lightrag__api_url": "http://..."}
    """
    items: list[tuple[str, Any]] = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)



def _remove_env_overrides(
    config: dict[str, Any], key_parts: list[str] | None = None
) -> dict[str, Any]:
    """Remove YAML config keys that have corresponding env var overrides.

    For nested configs, uses __ as delimiter to match pydantic-settings convention.
    E.g., yaml key lightrag.api_url → env var LOOMGRAPH_LIGHTRAG__API_URL

    Only leaf (non-dict) values are checked; dict values are recursed into.
    """
    if key_parts is None:
        key_parts = []

    result: dict[str, Any] = {}
    for key, value in config.items():
        current_parts = [*key_parts, key.upper()]
        env_name = "LOOMGRAPH_" + "__".join(current_parts)

        if isinstance(value, dict):
            filtered = _remove_env_overrides(value, current_parts)
            if filtered:
                result[key] = filtered
        else:
            if env_name not in os.environ:
                result[key] = value
    return result


def get_settings() -> Settings:
    """Get or create global settings instance.

    Configuration priority:
    1. Environment variables (LOOMGRAPH_*)
    2. YAML config file (.loomgraph.yaml)
    3. Default values

    YAML values are passed as init kwargs to Settings(), but any key
    that has a corresponding env var override is stripped first so that
    pydantic-settings resolves the env var instead.
    """
    global _settings
    if _settings is None:
        yaml_config = load_yaml_config()

        if yaml_config:
            # Strip YAML keys that have env var overrides
            filtered = _remove_env_overrides(yaml_config)
            _settings = Settings(**filtered)
        else:
            _settings = Settings()

    return _settings


def reset_settings() -> None:
    """Reset settings (useful for testing)."""
    global _settings
    _settings = None
