"""Contract tests for the frozen DeepSWE target-set policy."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_MODULE_PATH = Path(__file__).with_name("build-target-manifest.py")
_SPEC = importlib.util.spec_from_file_location("build_target_manifest", _MODULE_PATH)
assert _SPEC and _SPEC.loader
_module = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_module)


def test_production_path_filter_keeps_config_and_excludes_non_production(tmp_path: Path) -> None:
    patch = tmp_path / "solution.patch"
    patch.write_text(
        "\n".join(
            (
                "diff --git a/src/feature.py b/src/feature.py",
                "diff --git a/config/runtime.yaml b/config/runtime.yaml",
                "diff --git a/examples/demo.py b/examples/demo.py",
                "diff --git a/tests/test_feature.py b/tests/test_feature.py",
                "diff --git a/docs/guide.md b/docs/guide.md",
            )
        )
    )

    assert _module._production_paths(patch) == [
        "src/feature.py",
        "config/runtime.yaml",
    ]


def test_frozen_manifest_has_three_strata_and_no_forbidden_targets() -> None:
    manifest = json.loads(Path(__file__).with_name("target-manifest.json").read_text())
    tasks = manifest["tasks"]

    assert len(tasks) == 12
    assert {task["stratum"] for task in tasks} == set(_module.STRATA)
    assert all(
        not any(part in _module.NON_PRODUCTION_PARTS for part in Path(path).parts)
        for task in tasks
        for path in task["gold_production_paths"]
    )
