"""v0.11.3 regression: `embedding.enabled: false` must not produce a
"service not reachable" warning or attempt a network probe.

The runtime path (`maybe_embed_entities`) already honors the flag; this
fixes the parallel gap in `check_embedding` so `loomgraph status`
matches.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from loomgraph.cli._deps_check import check_embedding


def _settings(*, enabled: bool, api_url: str = "http://localhost:11434/v1") -> SimpleNamespace:
    return SimpleNamespace(
        embedding=SimpleNamespace(
            enabled=enabled,
            api_url=api_url,
            model="nomic-embed-text",
        )
    )


class TestEnabledFlag:
    def test_disabled_skips_network_probe(self) -> None:
        with patch("httpx.Client") as mock_client_class:
            result = check_embedding(_settings(enabled=False))
        assert result == {"enabled": False, "connected": False}
        mock_client_class.assert_not_called()

    def test_enabled_probes_url(self) -> None:
        mock_response = MagicMock(status_code=200)
        mock_http = MagicMock()
        mock_http.get.return_value = mock_response
        mock_http.__enter__ = MagicMock(return_value=mock_http)
        mock_http.__exit__ = MagicMock(return_value=False)

        with patch("httpx.Client", return_value=mock_http):
            result = check_embedding(_settings(enabled=True))

        assert result["enabled"] is True
        assert result["connected"] is True
        assert result["url"] == "http://localhost:11434/v1"
        mock_http.get.assert_called_once_with("http://localhost:11434/v1/health")

    def test_enabled_but_unreachable_carries_enabled_flag(self) -> None:
        mock_http = MagicMock()
        mock_http.get.side_effect = Exception("connection refused")
        mock_http.__enter__ = MagicMock(return_value=mock_http)
        mock_http.__exit__ = MagicMock(return_value=False)

        with patch("httpx.Client", return_value=mock_http):
            result = check_embedding(_settings(enabled=True))

        assert result == {
            "enabled": True,
            "connected": False,
            "error": "connection refused",
        }


class TestStatusWarning:
    """Status command must NOT emit the 'embedding not reachable' suggestion
    when the user explicitly turned embedding off."""

    def test_no_warning_when_disabled(self) -> None:
        import json

        from click.testing import CliRunner

        from loomgraph.cli.main import main

        with (
            patch("loomgraph.cli._setup.check_codeindex", return_value={"installed": True, "version": "1.0"}),
            patch("loomgraph.cli._setup.check_storage", return_value={"connected": True, "backend": "sqlite", "vec_version": "v0.1.9"}),
            patch("loomgraph.cli._setup.check_embedding", return_value={"enabled": False, "connected": False}),
            patch("loomgraph.cli._setup.get_auto_workspace", return_value="proj:main"),
        ):
            result = CliRunner().invoke(main, ["status"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        warnings = data["data"].get("warnings", [])
        assert not any("Embedding" in w for w in warnings), warnings

    def test_warning_when_enabled_and_unreachable(self) -> None:
        import json

        from click.testing import CliRunner

        from loomgraph.cli.main import main

        with (
            patch("loomgraph.cli._setup.check_codeindex", return_value={"installed": True, "version": "1.0"}),
            patch("loomgraph.cli._setup.check_storage", return_value={"connected": True, "backend": "sqlite", "vec_version": "v0.1.9"}),
            patch("loomgraph.cli._setup.check_embedding", return_value={"enabled": True, "connected": False, "error": "HTTP 404"}),
            patch("loomgraph.cli._setup.get_auto_workspace", return_value="proj:main"),
        ):
            result = CliRunner().invoke(main, ["status"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        warnings = data["data"].get("warnings", [])
        assert any("Embedding" in w for w in warnings), warnings
