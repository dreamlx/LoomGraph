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
