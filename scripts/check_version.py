#!/usr/bin/env python3
"""Pre-commit hook: verify version consistency.

Install:
    ln -sf ../../scripts/check_version.py .git/hooks/pre-commit

Or add to .pre-commit-config.yaml:
    - repo: local
      hooks:
        - id: check-version
          name: Check version consistency
          entry: python scripts/check_version.py
          language: python
          pass_filenames: false
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = PROJECT_ROOT / "pyproject.toml"
CUSTOMERS_VERSION = PROJECT_ROOT / "customers" / "VERSION"
INIT_PY = PROJECT_ROOT / "src" / "loomgraph" / "__init__.py"


def main() -> int:
    errors: list[str] = []

    # Read source of truth
    content = PYPROJECT.read_text()
    match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    if not match:
        print("ERROR: No version found in pyproject.toml")
        return 1
    version = match.group(1)

    # Check customers/VERSION
    if CUSTOMERS_VERSION.exists():
        cv = CUSTOMERS_VERSION.read_text().strip()
        if cv != version:
            errors.append(
                f"customers/VERSION ({cv}) != pyproject.toml ({version})"
            )

    # Check no hardcoded version in __init__.py
    if INIT_PY.exists():
        init_content = INIT_PY.read_text()
        hardcoded = re.search(r'__version__\s*=\s*"([^"]+)"', init_content)
        if hardcoded:
            errors.append(
                f"__init__.py has hardcoded version '{hardcoded.group(1)}'"
            )

    if errors:
        print("Version consistency check FAILED:")
        for e in errors:
            print(f"  ✗ {e}")
        print(f"\nFix: python scripts/bump_version.py {version}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
