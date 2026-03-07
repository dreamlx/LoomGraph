#!/usr/bin/env python3
"""Generate customer delivery summary for online installation (GitHub + Token).

This script generates a formatted summary document containing:
- Install commands for each customer (pip/pipx with GitHub Token)
- Service configuration details
- Release highlights
- Delivery instructions

Usage:
    # Generate summary for current version
    python scripts/generate_delivery_summary.py

    # Generate for specific version
    python scripts/generate_delivery_summary.py --version v0.8.0

    # Output to custom file
    python scripts/generate_delivery_summary.py --output /path/to/summary.txt
"""

from __future__ import annotations

import argparse
import re
from datetime import datetime
from pathlib import Path

import yaml

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
CUSTOMERS_DIR = PROJECT_ROOT / "customers"
CUSTOMERS_CONFIG = CUSTOMERS_DIR / "customers.yaml"
CHANGELOG = PROJECT_ROOT / "CHANGELOG.md"
PYPROJECT = PROJECT_ROOT / "pyproject.toml"


def get_version_from_pyproject() -> str:
    """Get version from pyproject.toml."""
    content = PYPROJECT.read_text()
    match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    if match:
        return match.group(1)
    return "0.0.0"


def load_customers_config() -> dict:
    """Load customers configuration."""
    if not CUSTOMERS_CONFIG.exists():
        return {}
    with open(CUSTOMERS_CONFIG) as f:
        return yaml.safe_load(f) or {}


def extract_release_highlights(version: str) -> list[str]:
    """Extract release highlights from CHANGELOG.md.

    Args:
        version: Version string (e.g., "0.8.0")

    Returns:
        List of highlight strings
    """
    if not CHANGELOG.exists():
        return []

    content = CHANGELOG.read_text()

    # Find section for this version: ## [X.Y.Z] - YYYY-MM-DD
    pattern = rf"## \[{re.escape(version)}\] - \d{{4}}-\d{{2}}-\d{{2}}"
    match = re.search(pattern, content)

    if not match:
        return []

    # Extract content until next version header or end
    start = match.end()
    next_version = re.search(r"\n## \[", content[start:])
    end = start + next_version.start() if next_version else len(content)

    section = content[start:end].strip()

    # Extract Added/Changed/Fixed sections with their first item
    highlights = []

    for category in ["Added", "Changed", "Fixed"]:
        pattern = rf"### {category}\s*\n-\s*\*\*(.+?)\*\*:?\s*(.+?)(?:\n|$)"
        matches = re.findall(pattern, section, re.DOTALL)

        for feature, description in matches:
            # Clean up description (take first sentence only)
            desc = description.split("\n")[0].strip()
            # Remove list item markers
            desc = re.sub(r"^\s*-\s*", "", desc)
            highlights.append(f"**{feature}**: {desc}")

    return highlights[:5]  # Top 5 highlights


def generate_customer_section(
    customer_id: str,
    config: dict,
    version: str,
    emoji: str
) -> str:
    """Generate formatted section for a single customer.

    Args:
        customer_id: Customer ID (e.g., "zcyl")
        config: Customer config dict
        version: Version string
        emoji: Section number emoji (e.g., "1️⃣")

    Returns:
        Formatted section string
    """
    name = config.get("name", customer_id)
    token_name = config.get("github_token_name", "N/A")
    token_expires = config.get("github_token_expires", "N/A")
    lightrag_url = config.get("lightrag_url", "http://localhost:3001")
    language = config.get("language_hint", "Python")

    # Calculate days until expiry
    expiry_note = ""
    if token_expires != "N/A":
        try:
            expiry_date = datetime.strptime(token_expires, "%Y-%m-%d")
            days_left = (expiry_date - datetime.now()).days
            expiry_note = f"（{days_left} 天后）"
        except ValueError:
            pass

    # Read token from INSTALL.md
    install_md = CUSTOMERS_DIR / customer_id / "INSTALL.md"
    token = "TOKEN_NOT_FOUND"
    if install_md.exists():
        content = install_md.read_text()
        # Extract token from: export LOOMGRAPH_TOKEN="github_pat_..."
        match = re.search(r'export LOOMGRAPH_TOKEN="(github_pat_[^"]+)"', content)
        if match:
            token = match.group(1)

    section = f"""───────────────────────────────────────────────────────────────
{emoji}  {name}（{customer_id}）
───────────────────────────────────────────────────────────────

📂 文件位置:
   customers/{customer_id}/INSTALL.md
   customers/{customer_id}/config.yaml

📋 安装命令（复制发送给客户）:

export LOOMGRAPH_TOKEN="{token}"

# 方式 1: pip（推荐）
pip install "loomgraph @ git+https://${{LOOMGRAPH_TOKEN}}@github.com/dreamlx/LoomGraph.git@v{version}"

# 方式 2: pipx（隔离环境）
pipx install "loomgraph @ git+https://${{LOOMGRAPH_TOKEN}}@github.com/dreamlx/LoomGraph.git@v{version}"

📌 配置: LightRAG {lightrag_url} | 语言: {language}
🔐 Token 过期: {token_expires}{expiry_note}
🆕 版本: v{version}（最新）
"""
    return section


def generate_summary(version: str | None = None, output_path: Path | None = None) -> str:
    """Generate complete delivery summary.

    Args:
        version: Version string (default: from pyproject.toml)
        output_path: Optional output file path

    Returns:
        Generated summary content
    """
    if version is None:
        version = get_version_from_pyproject()

    # Remove 'v' prefix if present
    version = version.lstrip("v")

    customers = load_customers_config()

    if not customers:
        return "Error: No customers found in customers.yaml"

    # Header
    lines = [
        "═" * 63,
        f"  LoomGraph v{version} 客户交付包 - 就绪",
        "═" * 63,
        "",
        "📦 3 个客户安装包已准备完毕，每个包含：",
        "   ✅ INSTALL.md - 完整安装说明（含 Token）",
        "   ✅ config.yaml - 服务配置文件",
        "",
    ]

    # Customer sections
    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    for idx, (customer_id, config) in enumerate(customers.items()):
        emoji = emojis[idx] if idx < len(emojis) else "▪️"
        lines.append(generate_customer_section(customer_id, config, version, emoji))
        lines.append("")

    # Release highlights
    highlights = extract_release_highlights(version)
    if highlights:
        lines.extend([
            "═" * 63,
            f"  v{version} 新功能亮点",
            "═" * 63,
            "",
        ])

        for highlight in highlights:
            # Add emoji based on keyword
            if "Token" in highlight or "管理" in highlight:
                emoji = "🔑"
            elif "Workspace" in highlight or "自动" in highlight:
                emoji = "🔄"
            elif "代理" in highlight or "兼容" in highlight:
                emoji = "🔧"
            elif "命令" in highlight or "CLI" in highlight:
                emoji = "⚡"
            else:
                emoji = "✨"

            lines.append(f"{emoji} {highlight}")
        lines.append("")

    # Delivery instructions
    lines.extend([
        "═" * 63,
        "  交付方式",
        "═" * 63,
        "",
        "✅ 推荐: 企业微信密聊 / 钉钉密聊",
        "✅ 备选: 加密邮件（ProtonMail）",
        "❌ 禁止: 明文邮件 / 公开聊天",
        "",
        "═" * 63,
        "  快速访问",
        "═" * 63,
        "",
        "📖 完整交付指南: customers/DELIVERY_GUIDE.md",
        "🛠️  Token 管理工具: python scripts/manage_tokens.py --list",
        "📋 交付检查清单: 见 DELIVERY_GUIDE.md",
        f"🎉 GitHub Release: https://github.com/dreamlx/LoomGraph/releases/tag/v{version}",
        "",
        "═" * 63,
    ])

    content = "\n".join(lines)

    # Write to file if specified
    if output_path:
        output_path.write_text(content)
        print(f"✅ Delivery summary written to: {output_path}")

    return content


def main():
    parser = argparse.ArgumentParser(
        description="Generate customer delivery summary for online installation"
    )
    parser.add_argument(
        "--version", "-v",
        help="Version string (default: from pyproject.toml)"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path("/tmp/customer_delivery_summary.txt"),
        help="Output file path (default: /tmp/customer_delivery_summary.txt)"
    )
    parser.add_argument(
        "--print",
        action="store_true",
        help="Print to stdout instead of file"
    )

    args = parser.parse_args()

    # Generate summary
    summary = generate_summary(
        version=args.version,
        output_path=None if args.print else args.output
    )

    # Print to stdout if requested
    if args.print:
        print(summary)
    else:
        print(f"\n📋 查看完整交付信息:")
        print(f"   cat {args.output}")
        print(f"\n📦 或查看单个客户的安装说明:")
        print(f"   cat customers/zcyl/INSTALL.md")
        print(f"   cat customers/pinbianyi/INSTALL.md")
        print(f"   cat customers/demo/INSTALL.md")


if __name__ == "__main__":
    main()
