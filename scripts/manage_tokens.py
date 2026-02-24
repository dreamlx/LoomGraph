#!/usr/bin/env python3
"""GitHub Token 管理工具

功能:
- 检查即将过期的 token
- 生成安装命令
- 验证 token 有效性
- 列出所有客户 token 状态

用法:
    python scripts/manage_tokens.py --check-expiry
    python scripts/manage_tokens.py --generate-install customer --version v0.8.0
    python scripts/manage_tokens.py --list
    python scripts/manage_tokens.py --verify customer
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import yaml


class TokenManager:
    """GitHub Token 管理器"""

    def __init__(self, customers_file: Path = Path("customers/customers.yaml")):
        self.customers_file = customers_file
        self.customers = self._load_customers()

    def _load_customers(self) -> dict[str, Any]:
        """加载客户配置"""
        if not self.customers_file.exists():
            print(f"❌ 文件不存在: {self.customers_file}")
            print("💡 请先创建: cp customers/customers.yaml.example customers/customers.yaml")
            sys.exit(1)

        with open(self.customers_file) as f:
            return yaml.safe_load(f) or {}

    def check_expiry(self, warning_days: int = 30) -> None:
        """检查即将过期的 token

        Args:
            warning_days: 提前多少天预警
        """
        print(f"🔍 检查 GitHub Tokens 过期情况（预警阈值: {warning_days} 天）\n")

        today = datetime.now().date()
        warning_threshold = today + timedelta(days=warning_days)

        expiring_soon: list[tuple[str, str, int]] = []
        normal: list[tuple[str, str, int]] = []
        no_expiry_data: list[str] = []

        for customer_id, config in self.customers.items():
            if "github_token_expires" not in config:
                no_expiry_data.append(customer_id)
                continue

            expires_str = config["github_token_expires"]
            try:
                expires = datetime.strptime(expires_str, "%Y-%m-%d").date()
            except ValueError:
                print(f"⚠️  {customer_id}: 过期日期格式错误 ({expires_str})")
                continue

            days_left = (expires - today).days
            token_name = config.get("github_token_name", "未记录")

            if days_left < 0:
                print(f"❌ {customer_id} ({token_name}): 已过期 {abs(days_left)} 天")
            elif days_left <= warning_days:
                expiring_soon.append((customer_id, token_name, days_left))
            else:
                normal.append((customer_id, token_name, days_left))

        # 输出即将过期
        if expiring_soon:
            print("⚠️  即将过期（30 天内）:")
            for customer_id, token_name, days_left in sorted(expiring_soon, key=lambda x: x[2]):
                print(f"  - {customer_id} ({token_name}): {days_left} 天后过期")
            print()

        # 输出正常
        if normal:
            print("✅ 正常:")
            for customer_id, token_name, days_left in normal:
                print(f"  - {customer_id} ({token_name}): {days_left} 天后过期")
            print()

        # 输出缺失数据
        if no_expiry_data:
            print("⚠️  缺少过期日期:")
            for customer_id in no_expiry_data:
                print(f"  - {customer_id}: 请在 customers.yaml 中添加 github_token_expires")
            print()

        # 建议
        if expiring_soon:
            print("💡 建议: 为即将过期的客户创建新 token")
            print("   详见: docs/guides/TOKEN_MANAGEMENT.md")

    def generate_install_command(
        self,
        customer_id: str,
        version: str,
        token_placeholder: bool = True,
    ) -> None:
        """生成安装命令

        Args:
            customer_id: 客户 ID
            version: 版本号（如 v0.8.0）
            token_placeholder: 是否使用占位符（True）或从密码管理器获取（False）
        """
        if customer_id not in self.customers:
            print(f"❌ 未找到客户: {customer_id}")
            print(f"   已有客户: {', '.join(self.customers.keys())}")
            sys.exit(1)

        config = self.customers[customer_id]
        customer_name = config.get("name", customer_id)

        if token_placeholder:
            token = "YOUR_GITHUB_TOKEN"
            print(f"📋 {customer_name} - LoomGraph 安装命令\n")
            print("⚠️  请将 YOUR_GITHUB_TOKEN 替换为实际 token")
        else:
            token = "github_pat_xxxxxxxxxxxxx"
            print(f"📋 {customer_name} - LoomGraph 安装命令（实际 token 请从密码管理器获取）\n")

        print(f"# 方式 1: 直接安装（token 会留在 history）")
        print(f'pip install "loomgraph @ git+https://{token}@github.com/dreamlx/LoomGraph.git@{version}"\n')

        print(f"# 方式 2: 使用环境变量（推荐）")
        print(f'export LOOMGRAPH_TOKEN="{token}"')
        print(f'pip install "loomgraph @ git+https://${{LOOMGRAPH_TOKEN}}@github.com/dreamlx/LoomGraph.git@{version}"\n')

        # 显示客户配置摘要
        print(f"📌 客户配置:")
        print(f"  - LightRAG: {config.get('lightrag_url', 'N/A')}")
        print(f"  - 语言: {config.get('language_hint', 'N/A')}")
        if "github_token_expires" in config:
            print(f"  - Token 过期: {config['github_token_expires']}")

    def list_tokens(self) -> None:
        """列出所有客户的 token 状态"""
        print("📋 客户 Token 状态\n")
        print(f"{'客户ID':<15} {'名称':<15} {'Token名称':<35} {'创建日期':<12} {'过期日期':<12} {'状态'}")
        print("-" * 110)

        today = datetime.now().date()

        for customer_id, config in sorted(self.customers.items()):
            name = config.get("name", "N/A")[:14]
            token_name = config.get("github_token_name", "N/A")[:34]
            created = config.get("github_token_created", "N/A")
            expires = config.get("github_token_expires", "N/A")

            # 计算状态
            if expires == "N/A":
                status = "⚠️  缺失"
            else:
                try:
                    expires_date = datetime.strptime(expires, "%Y-%m-%d").date()
                    days_left = (expires_date - today).days
                    if days_left < 0:
                        status = f"❌ 已过期"
                    elif days_left <= 30:
                        status = f"⚠️  {days_left}天"
                    else:
                        status = f"✅ {days_left}天"
                except ValueError:
                    status = "⚠️  格式错误"

            print(f"{customer_id:<15} {name:<15} {token_name:<35} {created:<12} {expires:<12} {status}")

        print()
        print("💡 使用 --check-expiry 查看详细过期信息")
        print("💡 使用 --generate-install <客户ID> --version <版本> 生成安装命令")

    def verify_token(self, customer_id: str, token: str | None = None) -> None:
        """验证 token 是否有效（通过 GitHub API）

        Args:
            customer_id: 客户 ID
            token: GitHub token（如果为 None，则提示从密码管理器获取）
        """
        if customer_id not in self.customers:
            print(f"❌ 未找到客户: {customer_id}")
            sys.exit(1)

        if token is None:
            print(f"🔐 请从密码管理器获取 {customer_id} 的 token，然后运行:")
            print(f"   python scripts/manage_tokens.py --verify {customer_id} --token YOUR_TOKEN")
            return

        config = self.customers[customer_id]
        customer_name = config.get("name", customer_id)

        print(f"🔍 验证 {customer_name} 的 token...\n")

        # 测试 GitHub API
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    "https://api.github.com/repos/dreamlx/LoomGraph",
                    headers={"Authorization": f"Bearer {token}"},
                )

                if response.status_code == 200:
                    print("✅ Token 有效")
                    repo_data = response.json()
                    print(f"   仓库: {repo_data['full_name']}")
                    print(f"   描述: {repo_data['description']}")
                elif response.status_code == 401:
                    print("❌ Token 无效或已过期")
                    print("   请在 GitHub 上检查 token 状态或创建新 token")
                elif response.status_code == 403:
                    print("❌ Token 权限不足")
                    print("   需要 'Contents: Read' 权限")
                elif response.status_code == 404:
                    print("❌ 无法访问仓库")
                    print("   可能原因:")
                    print("   - Token 没有访问该仓库的权限")
                    print("   - 仓库路径错误")
                else:
                    print(f"⚠️  意外响应: {response.status_code}")
                    print(f"   {response.text}")

        except httpx.ConnectError:
            print("❌ 网络连接失败")
            print("   请检查网络连接或 GitHub 服务状态")
        except Exception as e:
            print(f"❌ 验证失败: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LoomGraph GitHub Token 管理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 检查即将过期的 token
  python scripts/manage_tokens.py --check-expiry

  # 生成安装命令
  python scripts/manage_tokens.py --generate-install customer --version v0.8.0

  # 列出所有 token
  python scripts/manage_tokens.py --list

  # 验证 token（需要实际 token）
  python scripts/manage_tokens.py --verify customer --token github_pat_xxxxx

详细文档: docs/guides/TOKEN_MANAGEMENT.md
        """,
    )

    parser.add_argument(
        "--check-expiry",
        action="store_true",
        help="检查即将过期的 token",
    )
    parser.add_argument(
        "--generate-install",
        metavar="CUSTOMER_ID",
        help="生成安装命令（如: customer）",
    )
    parser.add_argument(
        "--version",
        metavar="VERSION",
        default="v0.8.0",
        help="版本号（默认: v0.8.0）",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="列出所有客户 token 状态",
    )
    parser.add_argument(
        "--verify",
        metavar="CUSTOMER_ID",
        help="验证 token 是否有效（需配合 --token）",
    )
    parser.add_argument(
        "--token",
        help="用于验证的 GitHub token",
    )
    parser.add_argument(
        "--warning-days",
        type=int,
        default=30,
        help="过期预警天数（默认: 30）",
    )

    args = parser.parse_args()

    # 至少需要一个操作
    if not any([args.check_expiry, args.generate_install, args.list, args.verify]):
        parser.print_help()
        sys.exit(1)

    manager = TokenManager()

    if args.check_expiry:
        manager.check_expiry(warning_days=args.warning_days)

    if args.generate_install:
        manager.generate_install_command(args.generate_install, args.version)

    if args.list:
        manager.list_tokens()

    if args.verify:
        manager.verify_token(args.verify, args.token)


if __name__ == "__main__":
    main()
