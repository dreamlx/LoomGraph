#!/usr/bin/env python3
"""Atomic version bump for LoomGraph.

Updates all version references in one step:
1. pyproject.toml (single source of truth)
2. customers/VERSION
3. CHANGELOG.md: [Unreleased] → [x.y.z] - date

Usage:
    python scripts/bump_version.py 0.2.5
    python scripts/bump_version.py 0.2.5 --tag    # also create git tag
    python scripts/bump_version.py --check         # verify consistency only
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
PYPROJECT = PROJECT_ROOT / "pyproject.toml"
CUSTOMERS_VERSION = PROJECT_ROOT / "customers" / "VERSION"
CHANGELOG = PROJECT_ROOT / "CHANGELOG.md"
INIT_PY = PROJECT_ROOT / "src" / "loomgraph" / "__init__.py"


def get_current_version() -> str:
    """Read current version from pyproject.toml."""
    content = PYPROJECT.read_text()
    match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    if match:
        return match.group(1)
    return "0.0.0"


def check_consistency() -> list[str]:
    """Check version consistency across all files.

    Returns list of error messages (empty = all consistent).
    """
    errors: list[str] = []
    version = get_current_version()

    # Check customers/VERSION
    if CUSTOMERS_VERSION.exists():
        cv = CUSTOMERS_VERSION.read_text().strip()
        if cv != version:
            errors.append(
                f"customers/VERSION = {cv}, expected {version}"
            )

    # Check __init__.py has no hardcoded version
    if INIT_PY.exists():
        content = INIT_PY.read_text()
        hardcoded = re.search(r'__version__\s*=\s*"([^"]+)"', content)
        if hardcoded:
            errors.append(
                f"__init__.py has hardcoded version '{hardcoded.group(1)}', "
                f"should use importlib.metadata"
            )

    return errors


def bump(new_version: str) -> None:
    """Bump version in all files."""
    old_version = get_current_version()

    if old_version == new_version:
        print(f"Already at version {new_version}")
        return

    print(f"Bumping {old_version} → {new_version}\n")

    # 1. pyproject.toml
    content = PYPROJECT.read_text()
    content = re.sub(
        r'^(version\s*=\s*)"[^"]+"',
        f'\\1"{new_version}"',
        content,
        count=1,
        flags=re.MULTILINE,
    )
    PYPROJECT.write_text(content)
    print("  ✓ pyproject.toml")

    # 2. customers/VERSION
    CUSTOMERS_VERSION.write_text(new_version + "\n")
    print("  ✓ customers/VERSION")

    # 3. CHANGELOG.md: convert [Unreleased] section to versioned
    if CHANGELOG.exists():
        content = CHANGELOG.read_text()
        today = date.today().isoformat()

        # Replace [Unreleased] header with version + add new empty [Unreleased]
        content = content.replace(
            "## [Unreleased]",
            f"## [Unreleased]\n\n## [{new_version}] - {today}",
            1,
        )

        # Update comparison links at bottom
        # [Unreleased]: ...compare/vOLD...HEAD → ...compare/vNEW...HEAD
        content = re.sub(
            r'(?m)^(\[Unreleased\]:\s*.+/compare/)v\d+\.\d+\.\d+\.\.\.HEAD$',
            f'\\1v{new_version}...HEAD',
            content,
        )

        # Add new version comparison link
        old_link_pattern = rf'\[{re.escape(old_version)}\]:'
        new_link = f"[{new_version}]: https://github.com/dreamlx/LoomGraph/compare/v{old_version}...v{new_version}"
        content = re.sub(
            old_link_pattern,
            f"{new_link}\n[{old_version}]:",
            content,
        )

        CHANGELOG.write_text(content)
        print(f"  ✓ CHANGELOG.md ([Unreleased] → [{new_version}] - {today})")

    print(f"\nVersion bumped to {new_version}")
    print("Next steps:")
    print("  git add pyproject.toml customers/VERSION CHANGELOG.md")
    print(f"  git commit -m 'chore: bump version to {new_version}'")
    print(f"  git tag v{new_version}")


def main():
    parser = argparse.ArgumentParser(
        description="Bump LoomGraph version atomically"
    )
    parser.add_argument(
        "version",
        nargs="?",
        help="New version (e.g., 0.2.5)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check version consistency only (no changes)",
    )
    parser.add_argument(
        "--tag",
        action="store_true",
        help="Create git tag after bumping version",
    )
    parser.add_argument(
        "--current",
        action="store_true",
        help="Show current version",
    )

    args = parser.parse_args()

    if args.current:
        print(get_current_version())
        return

    if args.check:
        errors = check_consistency()
        if errors:
            print("Version inconsistencies found:")
            for e in errors:
                print(f"  ✗ {e}")
            sys.exit(1)
        else:
            v = get_current_version()
            print(f"All version references consistent: {v}")
        return

    if not args.version:
        parser.print_help()
        return

    # Validate version format
    if not re.match(r'^\d+\.\d+\.\d+$', args.version):
        print(f"Error: Invalid version format '{args.version}'. Use X.Y.Z")
        sys.exit(1)

    bump(args.version)

    if args.tag:
        import subprocess

        tag_name = f"v{args.version}"
        result = subprocess.run(
            ["git", "tag", tag_name],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print(f"\n  Git tag created: {tag_name}")
            print("  Push with: git push origin develop --tags")
        else:
            print(f"\n  Warning: git tag failed: {result.stderr.strip()}")


if __name__ == "__main__":
    main()
