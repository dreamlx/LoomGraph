"""Tests for loomgraph.cli._deps_check.

#76 PATH-bypass class (reverse direction): ``status`` must report the
codeindex loomgraph actually invokes (``sys.executable -m codeindex.cli``),
not a PATH ``codeindex`` (e.g. pipx) that may be a different/stale install.
graph_export_ingest and the ``loomgraph codeindex`` passthrough both invoke
via the pinned venv; status reporting anything else describes a different
install than the one ``index`` runs.
"""

from __future__ import annotations

import subprocess
import sys
from unittest.mock import MagicMock, patch

from loomgraph.cli._deps_check import check_codeindex


class TestCheckCodeindexInvocation:
    @patch("loomgraph.cli._deps_check.subprocess.run")
    def test_uses_sys_executable_m_not_path_lookup(self, mock_run: MagicMock) -> None:
        """Must invoke ``[sys.executable, -m, codeindex.cli, --version]``.

        A bare ``codeindex`` PATH lookup (the old impl via shutil.which) hits a
        different install than the one ``index`` runs, so status would lie
        about the version/path loomgraph depends on.
        """
        mock_run.return_value = MagicMock(
            returncode=0, stdout="codeindex, version 0.37.0", stderr=""
        )
        result = check_codeindex()

        cmd = mock_run.call_args[0][0]
        assert cmd[0] == sys.executable
        assert cmd[1:] == ["-m", "codeindex.cli", "--version"]
        assert result["installed"] is True
        assert "0.37.0" in result["version"]

    @patch("loomgraph.cli._deps_check.subprocess.run")
    def test_module_not_found_means_not_installed(self, mock_run: MagicMock) -> None:
        """A failing ``python -m codeindex.cli`` -> installed=False.

        Even with a codeindex on PATH, loomgraph cannot index without the venv
        dep; the gate in _indexing/_setup must fire CODEINDEX_NOT_FOUND and
        point the user at ``pip install ai-codeindex`` in THIS env.
        """
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="No module named codeindex"
        )
        result = check_codeindex()
        assert result["installed"] is False
        assert "error" in result

    @patch("loomgraph.cli._deps_check.subprocess.run")
    def test_timeout_means_not_installed(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=[], timeout=5)
        result = check_codeindex()
        assert result["installed"] is False
