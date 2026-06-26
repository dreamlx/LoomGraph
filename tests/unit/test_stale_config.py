"""Regression: stale `.loomgraph.yaml` (legacy lightrag / embedding.base_url)
should not crash the CLI with a pydantic stack trace (v0.11.2)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from loomgraph.core.config import ConfigSchemaError, get_settings, reset_settings


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_settings()
    yield
    reset_settings()


# ---------- model_config extra="ignore" ----------


class TestSilentlyDrops:
    """v0.9.x and v0.10.x sections that no longer exist should be ignored."""

    def test_legacy_top_level_lightrag_section_dropped(self) -> None:
        # Pre-v0.10.0 yaml had a top-level `lightrag:` block
        legacy = {
            "lightrag": {"api_url": "http://h200:3001", "api_timeout": 30.0},
        }
        with patch(
            "loomgraph.core.config.load_yaml_config", return_value=legacy
        ):
            s = get_settings()
        assert s.embedding.enabled is False  # untouched default
        assert s.storage.backend == "sqlite"

    def test_legacy_embedding_base_url_dropped(self) -> None:
        # v0.10.x → v0.11.0 renamed embedding.base_url → embedding.api_url
        legacy = {
            "embedding": {
                "base_url": "http://h200:3002",  # old field
                "model": "jinaai/jina-embeddings-v2-base-code",  # old default
            },
        }
        with patch(
            "loomgraph.core.config.load_yaml_config", return_value=legacy
        ):
            s = get_settings()
        # base_url dropped; api_url falls back to default
        assert s.embedding.api_url == "http://localhost:11434/v1"
        # model accepted as-is (it's just a string)
        assert s.embedding.model == "jinaai/jina-embeddings-v2-base-code"

    def test_known_fields_still_load(self) -> None:
        legacy_with_known = {
            "lightrag": {"api_url": "ignored"},  # ignored
            "embedding": {
                "base_url": "ignored",  # ignored (old name)
                "enabled": True,  # known
                "api_url": "http://localhost:1234/v1",  # known
            },
        }
        with patch(
            "loomgraph.core.config.load_yaml_config",
            return_value=legacy_with_known,
        ):
            s = get_settings()
        assert s.embedding.enabled is True
        assert s.embedding.api_url == "http://localhost:1234/v1"


# ---------- ConfigSchemaError on impossible values ----------


class TestSchemaError:
    """When a YAML value really can't be coerced (wrong type, bad Literal),
    we still raise — but as ConfigSchemaError with a migration hint."""

    def test_invalid_provider_literal_raises_friendly(self) -> None:
        bad = {"embedding": {"provider": "lightrag"}}  # removed value
        with patch(
            "loomgraph.core.config.load_yaml_config", return_value=bad
        ), pytest.raises(ConfigSchemaError) as exc:
            get_settings()
        message = str(exc.value)
        assert "Failed to load LoomGraph configuration" in message
        assert "migration-v0.10.md" in message

    def test_wrong_type_raises_friendly(self) -> None:
        bad = {"embedding": {"dimension": "not-a-number"}}
        with patch(
            "loomgraph.core.config.load_yaml_config", return_value=bad
        ), pytest.raises(ConfigSchemaError):
            get_settings()


# ---------- CLI entrypoint catches ConfigSchemaError ----------


class TestCLIEntrypoint:
    """`cli_entry()` should turn ConfigSchemaError into stderr + exit 2,
    not a pydantic traceback."""

    def test_entrypoint_catches_and_writes_friendly_stderr(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from loomgraph.cli.main import cli_entry

        # Mock click's main() to raise ConfigSchemaError as it would when a
        # command callback calls get_settings() with a stale YAML.
        with patch(
            "loomgraph.cli.main.main",
            side_effect=ConfigSchemaError(
                "Failed to load LoomGraph configuration.\n"
                "Migration guide: docs/guides/migration-v0.10.md"
            ),
        ), pytest.raises(SystemExit) as exc:
            cli_entry()

        assert exc.value.code == 2
        captured = capsys.readouterr()
        # Clean message on stderr, no traceback
        assert "loomgraph:" in captured.err
        assert "migration-v0.10.md" in captured.err
        assert "Traceback" not in captured.err
        assert "pydantic" not in captured.err.lower()
