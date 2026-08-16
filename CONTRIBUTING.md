# Contributing

Thanks for considering a contribution.

## Setup

```bash
git clone https://github.com/dreamlx/LoomGraph.git
cd LoomGraph
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
```

## Workflow

- **Trunk-based**: short-lived `fix/<issue>-slug` / `feat/<issue>-slug` branches,
  squash-merged into `main` via PR. No develop branch.
- **TDD**: failing test first, minimal implementation, refactor. Core modules
  target ≥90% coverage; every feature ships unit + integration tests.
- Run the full gate before pushing:
  ```bash
  ruff check src/ tests/ && mypy src/ && pytest tests/
  ```
  (The full suite, not a marker subset — characterization tests often lack markers.)

## Conventions

- Commits: `<type>(<scope>): <subject>` (`feat` / `fix` / `docs` / `refactor` /
  `test` / `chore`), referenced issue in the footer (`Fixes #123`).
- Architecture decisions go through an ADR in `docs/adr/`; user-visible changes
  update both `CHANGELOG.md` and `customers/CHANGELOG.md`.
- Adding/changing a CLI command? Update the README command table and the project
  `CLAUDE.md` cheat-sheet in the same PR.

## Reporting bugs / proposing features

Open an issue first for anything non-trivial. For security issues see
[SECURITY.md](SECURITY.md) — please do not open public issues for those.
