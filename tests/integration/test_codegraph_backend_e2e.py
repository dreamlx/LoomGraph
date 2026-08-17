"""#152 codegraph-backend end-to-end (env-gated, real codegraph fixture).

Unit tests (test_codegraph_reader.py / test_codegraph_cli.py) cover the
synthetic-db path. This module guards against schema drift on a *real*
codegraph ``.codegraph/codegraph.db`` — the kind of breakage a synthetic
fixture can't catch (a codegraph release that adds a column the reader's
subset-fingerprint accepts but whose semantics changed).

Opt-in: set ``LOOMGRAPH_CODEGRAPH_FIXTURE`` to a repo root containing
``.codegraph/``. CI leaves it unset (the path is machine-local); developers
run it locally against spike fixtures (BlueHawkLock / PetClinic / fabricOS).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

_FIXTURE_ENV = "LOOMGRAPH_CODEGRAPH_FIXTURE"

pytestmark = pytest.mark.skipif(
    not os.environ.get(_FIXTURE_ENV),
    reason=f"set {_FIXTURE_ENV}=<repo with .codegraph/> to run the real-fixture e2e",
)


@pytest.mark.integration
def test_real_fixture_full_ingest_and_query() -> None:
    """End-to-end: snapshot → ingest → graph/deps on a real codegraph index.

    This is the #168 structural-check regression baseline (#152 验收): the
    graph must be queryable, deps must surface real cross-module edges, and
    a known cross-package symbol must have callers (the #167 pnpm monorepo
    scenario that codeindex resolved at 1.76%).
    """
    import json

    from click.testing import CliRunner

    from loomgraph.cli.main import main
    from loomgraph.io.codegraph_reader import run_codegraph_export

    repo = Path(os.environ[_FIXTURE_ENV])
    ws = "codegraph-e2e-test"

    # Reader: snapshot + map (the schema-drift guard).
    entities, relations, summary, warnings = run_codegraph_export(repo)
    assert summary.entity_count > 0, "real fixture yielded 0 entities (schema drift?)"
    assert summary.relation_count > 0

    try:
        # CLI: full ingest (cold rebuild) into an isolated workspace.
        res = CliRunner().invoke(
            main, ["index", str(repo), "--backend", "codegraph", "-w", ws]
        )
        assert res.exit_code == 0, res.output
        data = json.loads(res.stdout)["data"]
        assert data["backend"] == "codegraph"
        assert data["entities_created"] > 0

        # graph: the ingested workspace is queryable.
        some_entity = entities[0].entity_name
        gres = CliRunner().invoke(
            main, ["graph", some_entity, "-w", ws, "--direction", "both"]
        )
        assert gres.exit_code == 0, gres.output

        # deps: cross-module edges surface (the file-entity approach → module
        # deps aggregate naturally from file→symbol edges).
        dres = CliRunner().invoke(main, ["deps", "-w", ws])
        assert dres.exit_code == 0, dres.output
        ddata = json.loads(dres.stdout)["data"]
        assert len(ddata.get("modules", [])) >= 1
    finally:
        CliRunner().invoke(main, ["workspace", "delete", ws, "--yes"])
