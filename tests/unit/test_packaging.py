"""Guard tests for packaging metadata (pyproject.toml).

These read the source-of-truth pyproject directly so they hold regardless
of whether the package has been reinstalled in the dev env.
"""

from __future__ import annotations

import tomllib
from pathlib import Path


def _pyproject() -> dict[str, object]:
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    with pyproject.open("rb") as fh:
        return tomllib.load(fh)


def test_java_extra_declared() -> None:
    """#93: ``pipx install loomgraph[java]`` must surface Java grammar.

    A pure-Java repo otherwise indexes to 0 entities because the default
    install ships no ``tree-sitter-java``. The ``[java]`` extra is the
    customer-facing escape hatch — guard against accidental removal.
    """
    data = _pyproject()
    project = data.get("project", {})
    assert isinstance(project, dict)
    extras = project.get("optional-dependencies", {})
    assert isinstance(extras, dict)
    assert "java" in extras, (
        "[project.optional-dependencies] must declare a `java` extra "
        "(#93: pipx install loomgraph[java])"
    )
    joined = " ".join(extras["java"])
    assert "tree-sitter-java" in joined, (
        "`java` extra must pull tree-sitter-java (the grammar codeindex needs)"
    )


def test_swift_extra_declared() -> None:
    """#118: ``pipx install loomgraph[swift]`` must surface the Swift grammar.

    Parity with the ``[java]`` (#93) / ``[typescript]`` (#96) extras: a pure-Swift
    repo otherwise indexes to 0 entities because the default install ships no
    ``tree-sitter-swift`` and codeindex does not hard-depend on it. The
    ``[swift]`` extra is the customer-facing escape hatch.
    """
    data = _pyproject()
    project = data.get("project", {})
    assert isinstance(project, dict)
    extras = project.get("optional-dependencies", {})
    assert isinstance(extras, dict)
    assert "swift" in extras, (
        "[project.optional-dependencies] must declare a `swift` extra "
        "(#118: pipx install loomgraph[swift])"
    )
    joined = " ".join(extras["swift"])
    assert "tree-sitter-swift" in joined, (
        "`swift` extra must pull tree-sitter-swift (the grammar codeindex needs)"
    )


def test_typescript_extra_declared() -> None:
    """#96: ``pipx install loomgraph[typescript]`` must surface the TS grammar.

    Parity with the ``[java]`` extra (#93): a pure-TS repo otherwise indexes
    to 0 entities because the default install ships no ``tree-sitter-typescript``.
    The ``[typescript]`` extra is the customer-facing escape hatch.
    """
    data = _pyproject()
    project = data.get("project", {})
    assert isinstance(project, dict)
    extras = project.get("optional-dependencies", {})
    assert isinstance(extras, dict)
    assert "typescript" in extras, (
        "[project.optional-dependencies] must declare a `typescript` extra "
        "(#96: pipx install loomgraph[typescript])"
    )
    joined = " ".join(extras["typescript"])
    assert "tree-sitter-typescript" in joined, (
        "`typescript` extra must pull tree-sitter-typescript (the grammar codeindex needs)"
    )


def test_hook_template_lives_inside_package() -> None:
    """#128: the post-commit hook template must ship inside the package.

    Runtime resolves it via ``importlib.resources.files("loomgraph")``, so it
    must live under ``src/loomgraph/`` — hatchling includes package-dir files
    in the wheel automatically. If the template drifts back to ``scripts/hooks/``
    (its old home), it disappears from every wheel/pipx install and
    ``loomgraph hooks install`` fails silently again. This static guard catches
    that drift; the editable-vs-wheel behavioral guard is in test_hooks.py.
    """
    repo_root = Path(__file__).resolve().parents[2]
    template = repo_root / "src" / "loomgraph" / "_hooks_templates" / "post-commit"
    assert template.is_file(), (
        "post-commit template must live under src/loomgraph/_hooks_templates/ "
        "(#128): outside the package it won't ship in the wheel"
    )
    assert template.stat().st_mode & 0o111, (
        "post-commit template must have its executable bit set in source"
    )
