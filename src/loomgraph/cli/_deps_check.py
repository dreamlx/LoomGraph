"""Dependency check helpers for CLI status command."""

from __future__ import annotations

import shutil
import subprocess
from typing import Any


def check_codeindex() -> dict[str, Any]:
    """Check if codeindex CLI is available."""
    codeindex_path = shutil.which("codeindex")
    if not codeindex_path:
        return {"installed": False, "error": "command not found"}

    try:
        result = subprocess.run(
            ["codeindex", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        version = result.stdout.strip() if result.returncode == 0 else "unknown"
        return {"installed": True, "version": version, "path": codeindex_path}
    except subprocess.TimeoutExpired:
        return {"installed": True, "version": "unknown", "path": codeindex_path}
    except Exception as e:
        return {"installed": False, "error": str(e)}


def check_lightrag_api(settings: Any) -> dict[str, Any]:
    """Check LightRAG API connectivity."""
    try:
        import httpx

        # trust_env=False to bypass system proxy (H200 is internal)
        with httpx.Client(timeout=5.0, trust_env=False) as client:
            response = client.get(f"{settings.lightrag.api_url}/health")
        if response.status_code == 200:
            data = response.json()
            return {
                "connected": True,
                "status": data.get("status", "unknown"),
                "version": data.get("core_version", "unknown"),
                "url": settings.lightrag.api_url,
            }
        return {"connected": False, "error": f"HTTP {response.status_code}"}
    except ImportError:
        return {"connected": False, "error": "httpx not installed"}
    except Exception as e:
        return {"connected": False, "error": str(e)}


def check_embedding(settings: Any) -> dict[str, Any]:
    """Check embedding service availability."""
    try:
        import httpx

        # trust_env=False to bypass system proxy (H200 is internal)
        with httpx.Client(timeout=5.0, trust_env=False) as client:
            response = client.get(f"{settings.embedding.base_url}/health")
        if response.status_code == 200:
            return {
                "connected": True,
                "model": settings.embedding.model,
                "url": settings.embedding.base_url,
            }
        return {"connected": False, "error": f"HTTP {response.status_code}"}
    except ImportError:
        return {"connected": False, "error": "httpx not installed"}
    except Exception as e:
        return {"connected": False, "error": str(e)}
