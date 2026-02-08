#!/usr/bin/env python3
"""Package LoomGraph for customer distribution.

Usage:
    python scripts/package.py --customer customer
    python scripts/package.py --customer customer
    python scripts/package.py --all
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).parent.parent
CUSTOMERS_DIR = PROJECT_ROOT / "customers"
SKILLS_DIR = PROJECT_ROOT / "skills"
DIST_DIR = PROJECT_ROOT / "dist"

# Files to include in the package
INCLUDE_FILES = [
    "pyproject.toml",
    "LICENSE",
]

INCLUDE_DIRS = [
    "src",
]


def get_version() -> str:
    """Get version from pyproject.toml."""
    pyproject = PROJECT_ROOT / "pyproject.toml"
    content = pyproject.read_text()
    for line in content.splitlines():
        if line.strip().startswith("version"):
            # version = "0.1.0"
            return line.split("=")[1].strip().strip('"')
    return "0.0.0"


def package_customer(customer: str) -> Path:
    """Package LoomGraph for a specific customer.

    Args:
        customer: Customer name (e.g., "customer", "customer")

    Returns:
        Path to the created tarball
    """
    customer_dir = CUSTOMERS_DIR / customer
    if not customer_dir.exists():
        print(f"Error: Customer directory not found: {customer_dir}")
        sys.exit(1)

    version = get_version()
    package_name = f"loomgraph-{customer}-v{version}"

    # Create temp directory for packaging
    temp_dir = DIST_DIR / package_name
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True)

    print(f"Packaging for {customer}...")

    # Copy customer-specific README
    customer_readme = customer_dir / "README.md"
    if customer_readme.exists():
        shutil.copy(customer_readme, temp_dir / "README.md")
        print(f"  - README.md (customer-specific)")

    # Copy customer-specific config
    customer_config = customer_dir / "config.yaml"
    if customer_config.exists():
        shutil.copy(customer_config, temp_dir / "config.yaml")
        print(f"  - config.yaml")

    # Patterns to exclude
    def ignore_patterns(directory, files):
        return [
            f for f in files
            if f == "__pycache__"
            or f.endswith(".pyc")
            or f.endswith(".pyo")
            or f == ".DS_Store"
        ]

    # Copy source directories
    for dir_name in INCLUDE_DIRS:
        src_dir = PROJECT_ROOT / dir_name
        if src_dir.exists():
            shutil.copytree(src_dir, temp_dir / dir_name, ignore=ignore_patterns)
            print(f"  - {dir_name}/")

    # Copy individual files
    for file_name in INCLUDE_FILES:
        src_file = PROJECT_ROOT / file_name
        if src_file.exists():
            shutil.copy(src_file, temp_dir / file_name)
            print(f"  - {file_name}")

    # Copy skills directory
    if SKILLS_DIR.exists():
        shutil.copytree(SKILLS_DIR, temp_dir / "skills")
        print(f"  - skills/")

    # Create tarball
    tarball = DIST_DIR / f"{package_name}.tar.gz"
    if tarball.exists():
        tarball.unlink()

    subprocess.run(
        ["tar", "-czf", tarball.name, package_name],
        cwd=DIST_DIR,
        check=True,
    )

    # Clean up temp directory
    shutil.rmtree(temp_dir)

    print(f"\nCreated: {tarball}")
    print(f"Size: {tarball.stat().st_size / 1024:.1f} KB")

    return tarball


def list_customers() -> list[str]:
    """List available customers."""
    if not CUSTOMERS_DIR.exists():
        return []
    return [d.name for d in CUSTOMERS_DIR.iterdir() if d.is_dir()]


def main():
    parser = argparse.ArgumentParser(description="Package LoomGraph for customers")
    parser.add_argument(
        "--customer", "-c",
        help="Customer name (e.g., customer, customer)"
    )
    parser.add_argument(
        "--all", "-a",
        action="store_true",
        help="Package for all customers"
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List available customers"
    )

    args = parser.parse_args()

    if args.list:
        customers = list_customers()
        print("Available customers:")
        for c in customers:
            print(f"  - {c}")
        return

    if args.all:
        customers = list_customers()
        if not customers:
            print("No customers found in customers/")
            sys.exit(1)

        print(f"Packaging for {len(customers)} customers...\n")
        for customer in customers:
            package_customer(customer)
            print()

        print(f"\nAll packages created in {DIST_DIR}/")
        return

    if args.customer:
        package_customer(args.customer)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
