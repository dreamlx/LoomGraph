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

# Every sub-config uses `extra="ignore"` so a stale YAML carried over from
# v0.9.x or v0.10.x doesn't crash the CLI with a pydantic stack trace.
# Removed fields (e.g. `lightrag.api_url`, `embedding.base_url`) are silently
# dropped; user is reminded once via `get_settings()` (see below).
_IGNORE_EXTRA = SettingsConfigDict(extra="ignore")


class ASTExtractionConfig(BaseSettings):
    """AST extraction configuration."""

    model_config = _IGNORE_EXTRA

    enabled: bool = True
    chunking: Literal["ast", "token"] = "ast"
    extract_calls: bool = True
    extract_inheritance: bool = True


class SemanticEnhancementConfig(BaseSettings):
    """LLM semantic enhancement configuration (disabled in MVP)."""

    model_config = _IGNORE_EXTRA

    enabled: bool = False  # MVP default: disabled
    description_generation: bool = False
    pattern_recognition: bool = False


class IndexingConfig(BaseSettings):
    """Indexing pipeline configuration."""

    model_config = _IGNORE_EXTRA

    ast_extraction: ASTExtractionConfig = Field(default_factory=ASTExtractionConfig)
    semantic_enhancement: SemanticEnhancementConfig = Field(
        default_factory=SemanticEnhancementConfig
    )


class EmbeddingConfig(BaseSettings):
    """Embedding provider configuration (EPIC-012 / Phase 6).

    Default off — pipx install gives you a usable LoomGraph without any
    external embedding service. Turn on by setting `enabled: true` and
    pointing `api_url` at any OpenAI-compatible `/v1/embeddings` endpoint.

    Built-in provider conventions (just defaults for api_url + model):
    - `auto`    — sticky resolution (#158): probe ollama → else builtin
    - `builtin` — zero-config local CodeRankEmbed-137M int8 ONNX, 768d,
                  needs `loomgraph[embed]`; model auto-downloads on first use
    - `ollama`  — local Ollama on `http://localhost:11434/v1`, `nomic-embed-text`
    - `openai`  — `https://api.openai.com/v1`, `text-embedding-3-small`
    - `voyage`  — `https://api.voyageai.com/v1`, `voyage-code-2`
    - `glm`     — H200 `:3000`, `embedding-3`
    - `custom`  — caller fills api_url / model

    Vector dimension must match the model. If you change it after indexing,
    SqliteGraphStore will refuse to open the existing `.db` and instruct
    you to `loomgraph index --clear`.
    """

    model_config = _IGNORE_EXTRA

    enabled: bool = False
    # `auto` resolves once per workspace (config > ollama-probe > builtin)
    # and persists the choice — embedding spaces are provider-specific and
    # must never silently mix (#158).
    provider: Literal["auto", "builtin", "ollama", "openai", "voyage", "glm", "custom"] = "auto"
    api_url: str = "http://localhost:11434/v1"
    api_key: str = ""
    model: str = "nomic-embed-text"
    dimension: int = 768
    batch_size: int = 32
    max_length: int = 8192
    timeout: float = 30.0


class StorageConfig(BaseSettings):
    """Storage backend selection (EPIC-011 / ADR-013).

    Phase 5: only `sqlite` is supported. The legacy `lightrag` value was
    removed in v0.10.0 along with the LightRAG client and adapter.
    """

    model_config = _IGNORE_EXTRA

    backend: Literal["sqlite"] = "sqlite"
    # Filesystem path template. `{workspace}` is substituted at runtime with
    # the resolved workspace name. `~` is expanded.
    db_path: str = "~/.loomgraph/{workspace}.db"


class LLMConfig(BaseSettings):
    """LLM provider configuration (EPIC-011 Phase 4 / ADR-013).

    Phase 5: `lightrag` option dropped together with the storage backend.
    `DirectLLMClient` (OpenAI-compatible chat completions) is the only
    transport; `provider` chooses default model + endpoint conventions.

    Provider conventions (defaults for api_url + model; H200 retired 2026-07,
    local Ollama is now the default):
    - `ollama`     — local Ollama on `http://localhost:11434`, `gemma3:12b-it-qat`
    - `glm`        — self-hosted GLM (caller sets api_url / model)
    - `openrouter` — `https://openrouter.ai` (caller sets model + api_key)
    - `vllm`       — vLLM OpenAI-compatible server (caller sets api_url / model)
    """

    model_config = _IGNORE_EXTRA

    provider: Literal["ollama", "glm", "openrouter", "vllm"] = "ollama"
    # OpenAI-compatible endpoint base URL (DirectLLMClient appends
    # `/v1/chat/completions`). Default points at local Ollama.
    api_url: str = "http://localhost:11434"
    api_key: str = ""  # Required for OpenRouter; optional for self-hosted
    model: str = "gemma3:12b-it-qat"
    timeout: float = 60.0
    max_tokens: int = 1024
    temperature: float = 0.7


class RetrievalConfig(BaseSettings):
    """Retrieval configuration."""

    model_config = _IGNORE_EXTRA

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
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)


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
        {"storage": {"db_path": "~/.loomgraph/{workspace}.db"}}
        becomes
        {"storage__db_path": "~/.loomgraph/{workspace}.db"}
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
    E.g., yaml key storage.db_path → env var LOOMGRAPH_STORAGE__DB_PATH

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


class ConfigSchemaError(RuntimeError):
    """User-facing config-load failure (clearer than a pydantic stack trace)."""


def _format_validation_error(exc: Exception) -> str:
    """Render a pydantic ValidationError as a friendly migration hint."""
    lines = [
        "Failed to load LoomGraph configuration.",
        "",
        "Field problems:",
    ]
    errors = getattr(exc, "errors", None)
    if callable(errors):
        for err in exc.errors():  # type: ignore[attr-defined]
            loc = ".".join(str(p) for p in err.get("loc", []))
            msg = err.get("msg", "")
            lines.append(f"  - {loc}: {msg}")
    else:
        lines.append(f"  - {exc}")
    lines.extend(
        [
            "",
            "This usually means your .loomgraph.yaml or "
            "~/.config/loomgraph/config.yaml was written for an older release.",
            "v0.10.0 dropped the `lightrag` section; v0.11.0 renamed "
            "`embedding.base_url` to `embedding.api_url` and gated "
            "embedding behind `embedding.enabled`.",
            "Migration guide: "
            "https://github.com/dreamlx/LoomGraph/blob/main/docs/guides/migration-v0.10.md",
        ]
    )
    return "\n".join(lines)


def get_settings() -> Settings:
    """Get or create global settings instance.

    Configuration priority:
    1. Environment variables (LOOMGRAPH_*)
    2. YAML config file (.loomgraph.yaml)
    3. Default values

    YAML values are passed as init kwargs to Settings(), but any key
    that has a corresponding env var override is stripped first so that
    pydantic-settings resolves the env var instead. Unknown / removed
    sub-fields are silently ignored (sub-configs use `extra="ignore"`)
    so an older YAML doesn't crash the CLI; only impossible values
    (wrong type, invalid Literal) raise ConfigSchemaError.
    """
    global _settings
    if _settings is None:
        yaml_config = load_yaml_config()

        try:
            if yaml_config:
                filtered = _remove_env_overrides(yaml_config)
                _settings = Settings(**filtered)
            else:
                _settings = Settings()
        except Exception as exc:
            # ValidationError is a pydantic_core.ValidationError; catch broadly
            # to avoid a hard import dependency on the private module path.
            raise ConfigSchemaError(_format_validation_error(exc)) from exc

    return _settings


def reset_settings() -> None:
    """Reset settings (useful for testing)."""
    global _settings
    _settings = None
