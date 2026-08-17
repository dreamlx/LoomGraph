"""Dependency check helpers for CLI status command."""

from __future__ import annotations

import subprocess
import sys
from typing import Any


def check_codeindex() -> dict[str, Any]:
    """Check if the codeindex loomgraph actually invokes is available.

    Uses ``sys.executable -m codeindex.cli`` — the SAME pinned-env path
    ``index`` / ``update`` / ``loomgraph codeindex`` run through
    (graph_export_ingest.py, _codeindex.py). A PATH-resolved ``codeindex``
    (the old ``shutil.which`` lookup) can be a different or stale install
    (e.g. pipx), so reporting it would describe an install loomgraph never
    runs — the reverse-direction sibling of the #76 PATH-bypass class.
    """
    try:
        result = subprocess.run(
            [sys.executable, "-m", "codeindex.cli", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except subprocess.TimeoutExpired:
        return {"installed": False, "error": "codeindex --version timed out"}
    except Exception as e:
        return {"installed": False, "error": str(e)}

    if result.returncode != 0:
        return {
            "installed": False,
            "error": result.stderr.strip() or f"exit {result.returncode}",
        }

    return {
        "installed": True,
        "version": result.stdout.strip(),
        "path": sys.executable,
    }


def check_storage(settings: Any) -> dict[str, Any]:
    """Check SQLite storage availability (parent dir writable, sqlite-vec loadable)."""
    try:
        import sqlite3
        from pathlib import Path

        import sqlite_vec  # noqa: F401  (verifies install)

        db_template = settings.storage.db_path
        parent = Path(db_template.split("{workspace}")[0]).expanduser()
        parent.mkdir(parents=True, exist_ok=True)
        # Smoke: open in-memory + load vec0
        conn = sqlite3.connect(":memory:")
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        version = conn.execute("SELECT vec_version()").fetchone()[0]
        conn.close()
        return {
            "connected": True,
            "backend": "sqlite",
            "vec_version": version,
            "db_path_template": db_template,
        }
    except Exception as e:
        return {"connected": False, "error": str(e)}


def check_embedding(settings: Any) -> dict[str, Any]:
    """Check embedding service availability.

    Honors `embedding.enabled` — when disabled (the v0.11.0 default),
    skip the network probe entirely. The status command no longer
    warns "embedding service not reachable" for a service the user
    explicitly turned off. Matches the runtime semantics where
    `maybe_embed_entities` short-circuits on the same flag.
    """
    if not settings.embedding.enabled:
        return {"enabled": False, "connected": False}

    try:
        import httpx

        # trust_env=False to bypass system proxy (H200 is internal)
        with httpx.Client(timeout=5.0, trust_env=False) as client:
            response = client.get(f"{settings.embedding.api_url}/health")
        if response.status_code == 200:
            return {
                "enabled": True,
                "connected": True,
                "model": settings.embedding.model,
                "url": settings.embedding.api_url,
            }
        return {
            "enabled": True,
            "connected": False,
            "error": f"HTTP {response.status_code}",
        }
    except ImportError:
        return {
            "enabled": True,
            "connected": False,
            "error": "httpx not installed",
        }
    except Exception as e:
        return {"enabled": True, "connected": False, "error": str(e)}
