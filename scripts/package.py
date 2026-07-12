#!/usr/bin/env python3
"""Package LoomGraph for customer distribution.

Usage:
    python scripts/package.py --customer zcyl
    python scripts/package.py --customer pinbianyi
    python scripts/package.py --all
    python scripts/package.py --list
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

# Project root
PROJECT_ROOT = Path(__file__).parent.parent
CUSTOMERS_DIR = PROJECT_ROOT / "customers"
SKILLS_DIR = PROJECT_ROOT / "skills"
DIST_DIR = PROJECT_ROOT / "dist"

# Template and config files
README_TEMPLATE = CUSTOMERS_DIR / "README.template.md"
CUSTOMERS_CONFIG = CUSTOMERS_DIR / "customers.yaml"
VERSION_FILE = CUSTOMERS_DIR / "VERSION"
CHANGELOG_FILE = CUSTOMERS_DIR / "CHANGELOG.md"

# Files to include in the package
INCLUDE_FILES = [
    "pyproject.toml",
    "LICENSE",
]

INCLUDE_DIRS = [
    "src",
]


def get_version() -> str:
    """Get version from pyproject.toml (single source of truth)."""
    pyproject = PROJECT_ROOT / "pyproject.toml"
    content = pyproject.read_text()
    match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    if match:
        return match.group(1)
    return "0.0.0"


def load_customers_config() -> dict:
    """Load customers configuration from customers.yaml."""
    if not CUSTOMERS_CONFIG.exists():
        print(f"Warning: {CUSTOMERS_CONFIG} not found, using legacy mode")
        return {}

    with open(CUSTOMERS_CONFIG) as f:
        return yaml.safe_load(f) or {}


def render_template(template: str, variables: dict) -> str:
    """Render template with {{variable}} placeholders.

    Args:
        template: Template string with {{variable}} placeholders
        variables: Dict of variable name -> value

    Returns:
        Rendered string
    """
    result = template
    for key, value in variables.items():
        placeholder = "{{" + key + "}}"
        result = result.replace(placeholder, str(value))

    # Check for unreplaced placeholders
    unreplaced = re.findall(r"\{\{(\w+)\}\}", result)
    if unreplaced:
        print(f"  Warning: Unreplaced placeholders: {unreplaced}")

    return result


def generate_readme(customer: str, config: dict, version: str) -> str:
    """Generate customer-specific README from template.

    Args:
        customer: Customer key (e.g., "zcyl")
        config: Customer config dict from customers.yaml
        version: Current version string

    Returns:
        Rendered README content
    """
    if not README_TEMPLATE.exists():
        print(f"Warning: {README_TEMPLATE} not found")
        return ""

    template = README_TEMPLATE.read_text()

    variables = {
        "customer_name": config.get("name", customer),
        "language_hint": config.get("language_hint", "Python"),
        "version": version,
        "customer_key": customer,
    }

    return render_template(template, variables)


def build_wheel() -> Path | None:
    """Build wheel and return the path to the .whl file."""
    print("Building wheel...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "build", "--wheel", str(PROJECT_ROOT)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            print(f"  Warning: wheel build failed: {result.stderr}")
            return None

        # Find the built wheel
        wheels = list(DIST_DIR.glob("loomgraph-*.whl"))
        if wheels:
            newest = max(wheels, key=lambda p: p.stat().st_mtime)
            print(f"  Built: {newest.name}")
            return newest
        return None
    except Exception as e:
        print(f"  Error building wheel: {e}")
        return None


def find_codeindex_wheel() -> Path | None:
    """Find codeindex wheel from ../codeindex/dist/ directory.

    Returns:
        Path to codeindex wheel, or None if not found
    """
    # Look for codeindex in sibling directory
    codeindex_project = PROJECT_ROOT.parent / "codeindex"
    codeindex_dist = codeindex_project / "dist"

    if not codeindex_dist.exists():
        print(f"  Warning: codeindex dist directory not found: {codeindex_dist}")
        return None

    # Find newest codeindex wheel
    wheels = list(codeindex_dist.glob("ai_codeindex-*.whl"))
    if wheels:
        newest = max(wheels, key=lambda p: p.stat().st_mtime)
        print(f"  Found codeindex wheel: {newest.name}")
        return newest

    print(f"  Warning: No codeindex wheel found in {codeindex_dist}")
    return None


def get_cli_commands() -> set[str]:
    """Extract real CLI command names from Click group definitions.

    Scans `main.py` AND its submodules (`_*.py`) — commands are registered
    via `@main.command(...)` decorators across the cli package, not just in
    main.py itself. Returns the union so README.template validation can't
    false-positive on commands defined in submodules. Bare `@main.command()`
    decorators derive the command name from the function name.
    """
    cli_dir = PROJECT_ROOT / "src" / "loomgraph" / "cli"
    if not cli_dir.exists():
        return set()

    commands: set[str] = set()
    for py in cli_dir.glob("*.py"):
        content = py.read_text()
        # @main.command("name") — explicit name
        for match in re.finditer(r'@\w+\.command\(["\']([\w-]+)', content):
            commands.add(match.group(1))
        # bare @main.command() — derive from the def name. Click options may
        # span many lines between the decorator and the def, so match
        # non-greedily across lines until the `def`.
        for match in re.finditer(
            r'@\w+\.command\(\)\s*\n(?:.*\n)*?\s*def\s+(\w+)', content
        ):
            commands.add(match.group(1).replace("_", "-"))
        # cli.add_command(xxx, "name")
        for match in re.finditer(r'add_command\([^,]+,\s*"([\w-]+)"', content):
            commands.add(match.group(1))
        # add_command(xxx_group) — group name
        for match in re.finditer(r'add_command\((\w+)_group', content):
            commands.add(match.group(1).replace("_", "-"))
    return commands


def validate_docs(version: str) -> list[str]:
    """Pre-packaging validation: check for stale references in customer docs.

    Returns:
        List of warning messages (empty = all good)
    """
    warnings: list[str] = []

    # 1. Check README template for references to removed commands
    readme_template = README_TEMPLATE
    if readme_template.exists():
        content = readme_template.read_text()
        # Check for known deprecated command names. `search` was reclaimed in
        # EPIC-015 as a first-class semantic-search command, so it is NOT
        # deprecated; `query` was removed in v0.10 and must not resurface.
        deprecated = ["loomgraph query", "loomgraph scan"]
        for cmd in deprecated:
            if cmd in content:
                warnings.append(f"README.template.md references deprecated command: '{cmd}'")

        # Check CLI commands in template vs actual Click definitions
        cli_commands = get_cli_commands()
        if cli_commands:
            for match in re.finditer(r"`loomgraph (\w[\w-]*)`", content):
                cmd_name = match.group(1)
                # Skip meta-commands that aren't Click commands
                if cmd_name in {"--help", "--version"}:
                    continue
                if cmd_name not in cli_commands and cmd_name + "-" not in {c[:len(cmd_name)+1] for c in cli_commands}:
                    warnings.append(f"README.template.md references unknown CLI command: 'loomgraph {cmd_name}'")

    # 2. Check VERSION file matches pyproject.toml
    if VERSION_FILE.exists():
        file_version = VERSION_FILE.read_text().strip()
        if file_version != version:
            warnings.append(f"VERSION file ({file_version}) != pyproject.toml ({version})")

    # 3. Check quickstart.sh wheel filename patterns
    quickstart = PROJECT_ROOT / "scripts" / "quickstart.sh"
    if quickstart.exists():
        qs_content = quickstart.read_text()
        if "codeindex-*.whl" in qs_content and "ai_codeindex" not in qs_content:
            warnings.append("quickstart.sh uses wrong codeindex wheel pattern (should be ai_codeindex-*.whl)")

    # 4. Check INSTALL.md files for hardcoded old versions
    for install_md in CUSTOMERS_DIR.glob("*/INSTALL.md"):
        content = install_md.read_text()
        for match in re.finditer(r"v(\d+\.\d+\.\d+)", content):
            old_ver = match.group(1)
            if old_ver != version and old_ver not in ("0.20.0",):  # 0.20.0 is codeindex min version
                warnings.append(f"{install_md.relative_to(PROJECT_ROOT)} references old version v{old_ver}")

    return warnings


def package_customer(customer: str, customers_config: dict, mode: str = "demo") -> Path:
    """Package LoomGraph for a specific customer.

    Args:
        customer: Customer name (e.g., "zcyl", "pinbianyi")
        customers_config: Full customers.yaml config
        mode: Package mode - "demo" (first install) or "upgrade" (version update)

    Returns:
        Path to the created tarball
    """
    customer_dir = CUSTOMERS_DIR / customer
    if not customer_dir.exists():
        print(f"Error: Customer directory not found: {customer_dir}")
        sys.exit(1)

    version = get_version()

    # Pre-packaging validation
    doc_warnings = validate_docs(version)
    if doc_warnings:
        print(f"\n⚠️  Pre-packaging validation found {len(doc_warnings)} issue(s):")
        for w in doc_warnings:
            print(f"  - {w}")
        print()
        response = input("Continue packaging? [y/N] ").strip().lower()
        if response != "y":
            print("Aborted.")
            sys.exit(1)

    package_name = f"loomgraph-{mode}-{customer}-v{version}"

    # Create temp directory for packaging
    temp_dir = DIST_DIR / package_name
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True)

    print(f"Packaging for {customer} (v{version})...")

    # Get customer config
    customer_config = customers_config.get(customer, {})

    # Generate README from template (if template exists)
    if README_TEMPLATE.exists() and customer_config:
        readme_content = generate_readme(customer, customer_config, version)
        (temp_dir / "README.md").write_text(readme_content)
        print(f"  - README.md (generated from template)")
    else:
        # Fallback: copy customer-specific README
        customer_readme = customer_dir / "README.md"
        if customer_readme.exists():
            shutil.copy(customer_readme, temp_dir / "README.md")
            print(f"  - README.md (customer-specific, legacy)")

    # Copy shared CHANGELOG
    if CHANGELOG_FILE.exists():
        shutil.copy(CHANGELOG_FILE, temp_dir / "CHANGELOG.md")
        print(f"  - CHANGELOG.md")

    # Build and include LoomGraph wheel
    wheel_path = build_wheel()
    if wheel_path:
        shutil.copy(wheel_path, temp_dir / wheel_path.name)
        print(f"  - {wheel_path.name}")

    # Include codeindex wheel (required dependency)
    codeindex_wheel = find_codeindex_wheel()
    if codeindex_wheel:
        shutil.copy(codeindex_wheel, temp_dir / codeindex_wheel.name)
        print(f"  - {codeindex_wheel.name}")

    # Patterns to exclude
    def ignore_patterns(directory, files):
        return [
            f for f in files
            if f == "__pycache__"
            or f.endswith(".pyc")
            or f.endswith(".pyo")
            or f == ".DS_Store"
            or f == ".pytest_cache"
            or f == ".ruff_cache"
            or f == ".mypy_cache"
        ]

    # Copy source directories (as backup for source install)
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

    # Copy mode-specific files
    if mode == "demo":
        # Demo mode: first-time installation
        # Copy quickstart.sh
        quickstart_script = PROJECT_ROOT / "scripts" / "quickstart.sh"
        if quickstart_script.exists():
            shutil.copy(quickstart_script, temp_dir / "quickstart.sh")
            print(f"  - quickstart.sh (demo mode)")

        # Copy customer config.yaml (pre-configured service URLs)
        customer_config_file = customer_dir / "config.yaml"
        if customer_config_file.exists():
            shutil.copy(customer_config_file, temp_dir / "config.yaml")
            print(f"  - config.yaml (customer-specific)")

        # Copy VERSION file
        if VERSION_FILE.exists():
            shutil.copy(VERSION_FILE, temp_dir / "VERSION")
            print(f"  - VERSION")

    elif mode == "upgrade":
        # Upgrade mode: version update
        # Copy upgrade.sh
        upgrade_script = PROJECT_ROOT / "scripts" / "upgrade.sh"
        if upgrade_script.exists():
            shutil.copy(upgrade_script, temp_dir / "upgrade.sh")
            print(f"  - upgrade.sh (upgrade mode)")

        # Copy VERSION file
        if VERSION_FILE.exists():
            shutil.copy(VERSION_FILE, temp_dir / "VERSION")
            print(f"  - VERSION")

        # Copy UPGRADE_NOTES.md if exists
        upgrade_notes = PROJECT_ROOT / "UPGRADE_NOTES.md"
        if upgrade_notes.exists():
            shutil.copy(upgrade_notes, temp_dir / "UPGRADE_NOTES.md")
            print(f"  - UPGRADE_NOTES.md")

        # Copy config.yaml.new if config format changed
        customer_config_new = customer_dir / "config.yaml.new"
        if customer_config_new.exists():
            shutil.copy(customer_config_new, temp_dir / "config.yaml.new")
            print(f"  - config.yaml.new (config migration)")

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


def list_customers(customers_config: dict) -> list[str]:
    """List available customers."""
    # From customers.yaml
    if customers_config:
        return list(customers_config.keys())

    # Fallback: from directories
    if not CUSTOMERS_DIR.exists():
        return []
    return [
        d.name for d in CUSTOMERS_DIR.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    ]


def sync_version():
    """Sync customers/VERSION with pyproject.toml version."""
    version = get_version()
    VERSION_FILE.write_text(version + "\n")
    print(f"Synced VERSION to {version}")


def main():
    parser = argparse.ArgumentParser(description="Package LoomGraph for customers")
    parser.add_argument(
        "--customer", "-c",
        help="Customer name (e.g., zcyl, pinbianyi)"
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
    parser.add_argument(
        "--sync-version",
        action="store_true",
        help="Sync customers/VERSION with pyproject.toml"
    )
    parser.add_argument(
        "--mode", "-m",
        choices=["demo", "upgrade"],
        default="demo",
        help="Package mode: demo (first install) or upgrade (version update)"
    )

    args = parser.parse_args()

    # Load customers config
    customers_config = load_customers_config()

    if args.sync_version:
        sync_version()
        return

    if args.list:
        customers = list_customers(customers_config)
        print("Available customers:")
        for c in customers:
            config = customers_config.get(c, {})
            name = config.get("name", c)
            url = config.get("lightrag_url", "N/A")
            print(f"  - {c}: {name} ({url})")
        return

    if args.all:
        customers = list_customers(customers_config)
        if not customers:
            print("No customers found")
            sys.exit(1)

        print(f"Packaging for {len(customers)} customers (mode: {args.mode})...\n")
        for customer in customers:
            package_customer(customer, customers_config, mode=args.mode)
            print()

        print(f"\nAll packages created in {DIST_DIR}/")
        return

    if args.customer:
        package_customer(args.customer, customers_config, mode=args.mode)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
