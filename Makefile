# LoomGraph Makefile
# Unified command interface for development, testing, and release workflows

.PHONY: help install test lint docs-check format clean
.PHONY: release bump
.PHONY: run-index run-status run-find run-graph

# Default target
.DEFAULT_GOAL := help

# Colors for output
BOLD := \033[1m
GREEN := \033[32m
YELLOW := \033[33m
BLUE := \033[34m
RESET := \033[0m

# Python interpreter
PYTHON := .venv/bin/python
PIP := .venv/bin/pip
PYTEST := .venv/bin/pytest
RUFF := .venv/bin/ruff
MYPY := .venv/bin/mypy

# Project paths
SCRIPTS := scripts
CUSTOMERS := customers
DIST := dist

##@ General

help: ## Display this help message
	@echo "$(BOLD)LoomGraph - Available Commands$(RESET)"
	@echo ""
	@awk 'BEGIN {FS = ":.*##"; printf "Usage: make $(BLUE)<target>$(RESET)\n\n"} \
		/^[a-zA-Z_-]+:.*?##/ { printf "  $(GREEN)%-20s$(RESET) %s\n", $$1, $$2 } \
		/^##@/ { printf "\n$(BOLD)%s$(RESET)\n", substr($$0, 5) }' $(MAKEFILE_LIST)

##@ Development

install: ## Install dependencies (dev + prod)
	@echo "$(BOLD)Installing dependencies...$(RESET)"
	uv pip install -e ".[dev]"
	@echo "$(GREEN)✓ Dependencies installed$(RESET)"

install-prod: ## Install production dependencies only
	@echo "$(BOLD)Installing production dependencies...$(RESET)"
	uv pip install -e .
	@echo "$(GREEN)✓ Production dependencies installed$(RESET)"

test: ## Run all tests
	@echo "$(BOLD)Running tests...$(RESET)"
	$(PYTEST) tests/ -v
	@echo "$(GREEN)✓ All tests passed$(RESET)"

test-unit: ## Run unit tests only
	@echo "$(BOLD)Running unit tests...$(RESET)"
	$(PYTEST) tests/unit/ -v
	@echo "$(GREEN)✓ Unit tests passed$(RESET)"

test-integration: ## Run integration tests only
	@echo "$(BOLD)Running integration tests...$(RESET)"
	$(PYTEST) tests/integration/ -v
	@echo "$(GREEN)✓ Integration tests passed$(RESET)"

test-cov: ## Run tests with coverage report
	@echo "$(BOLD)Running tests with coverage...$(RESET)"
	$(PYTEST) tests/ -v --cov=src/loomgraph --cov-report=html --cov-report=term
	@echo "$(GREEN)✓ Coverage report generated: htmlcov/index.html$(RESET)"

lint: ## Run linting checks (ruff + mypy)
	@echo "$(BOLD)Running lint checks...$(RESET)"
	$(RUFF) check src/ tests/
	$(MYPY) src/
	@echo "$(GREEN)✓ Lint checks passed$(RESET)"

docs-check: ## Docs consistency gate (command tables, links, artifacts, versions)
	@$(PYTHON) $(SCRIPTS)/docs_check.py

lint-fix: ## Auto-fix linting issues
	@echo "$(BOLD)Fixing lint issues...$(RESET)"
	$(RUFF) check src/ tests/ --fix
	@echo "$(GREEN)✓ Lint issues fixed$(RESET)"

format: ## Format code with ruff
	@echo "$(BOLD)Formatting code...$(RESET)"
	$(RUFF) format src/ tests/
	@echo "$(GREEN)✓ Code formatted$(RESET)"

clean: ## Clean temporary files and build artifacts
	@echo "$(BOLD)Cleaning temporary files...$(RESET)"
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true
	rm -rf $(DIST)/*.tar.gz $(DIST)/loomgraph-* 2>/dev/null || true
	@echo "$(GREEN)✓ Cleaned$(RESET)"

##@ Release Management

release: ## Full release workflow (VERSION=x.y.z required)
	@if [ -z "$(VERSION)" ]; then \
		echo "$(YELLOW)Error: VERSION is required$(RESET)"; \
		echo "Usage: make release VERSION=0.8.0"; \
		exit 1; \
	fi
	@echo "$(BOLD)Starting release workflow for v$(VERSION)...$(RESET)"
	@echo ""
	@echo "$(BOLD)Step 1/6:$(RESET) Bumping version..."
	$(PYTHON) $(SCRIPTS)/bump_version.py $(VERSION)
	@echo ""
	@echo "$(BOLD)Step 2/6:$(RESET) Running tests..."
	$(MAKE) test
	@echo ""
	@echo "$(BOLD)Step 3/6:$(RESET) Running lint checks..."
	$(MAKE) lint
	@echo ""
	@echo "$(BOLD)Step 4/6:$(RESET) Committing version bump..."
	git add pyproject.toml $(CUSTOMERS)/VERSION CHANGELOG.md
	git commit -m "chore: bump version to $(VERSION)"
	@echo ""
	@echo "$(BOLD)Step 5/6:$(RESET) Creating tag v$(VERSION)..."
	git tag v$(VERSION)
	@echo ""
	@echo "$(BOLD)Step 6/6:$(RESET) Pushing to GitHub..."
	git push origin main --tags
	@echo ""
	@echo "$(GREEN)✓ Release v$(VERSION) pushed to GitHub$(RESET)"
	@echo "$(YELLOW)⏳ GitHub Actions is building the release...$(RESET)"
	@echo ""
	@echo "$(BOLD)Next steps:$(RESET)"
	@echo "  1. Wait for GitHub Actions (release.yml) to complete (~1-2 min)"
	@echo "  2. PyPI + GitHub Release are auto-published by CI"

bump: ## Bump version only (VERSION=x.y.z required)
	@if [ -z "$(VERSION)" ]; then \
		echo "$(YELLOW)Error: VERSION is required$(RESET)"; \
		echo "Usage: make bump VERSION=0.8.0"; \
		exit 1; \
	fi
	@echo "$(BOLD)Bumping version to $(VERSION)...$(RESET)"
	$(PYTHON) $(SCRIPTS)/bump_version.py $(VERSION)
	@echo "$(GREEN)✓ Version bumped to $(VERSION)$(RESET)"
	@echo "$(YELLOW)⚠ Don't forget to commit and tag!$(RESET)"

##@ CLI Quick Commands

run-status: ## Run loomgraph status
	@$(PYTHON) -m loomgraph.cli.main status

run-index: ## Index current directory (PATH=. optional)
	@if [ -z "$(PATH)" ]; then \
		$(PYTHON) -m loomgraph.cli.main index .; \
	else \
		$(PYTHON) -m loomgraph.cli.main index $(PATH); \
	fi

run-find: ## Search for entity (QUERY required)
	@if [ -z "$(QUERY)" ]; then \
		echo "$(YELLOW)Error: QUERY is required$(RESET)"; \
		echo "Usage: make run-find QUERY=\"ClassName\""; \
		exit 1; \
	fi
	@$(PYTHON) -m loomgraph.cli.main find "$(QUERY)"

run-graph: ## Show call graph (ENTITY required)
	@if [ -z "$(ENTITY)" ]; then \
		echo "$(YELLOW)Error: ENTITY is required$(RESET)"; \
		echo "Usage: make run-graph ENTITY=\"ClassName\""; \
		exit 1; \
	fi
	@$(PYTHON) -m loomgraph.cli.main graph "$(ENTITY)"

##@ Git Workflows

git-status: ## Show git status with customer files
	@git status

git-check: ## Check for uncommitted changes
	@if ! git diff-index --quiet HEAD --; then \
		echo "$(YELLOW)⚠ You have uncommitted changes$(RESET)"; \
		git status --short; \
		exit 1; \
	fi
	@echo "$(GREEN)✓ Working directory clean$(RESET)"

git-sync: ## Pull latest changes from main
	@echo "$(BOLD)Syncing with remote...$(RESET)"
	git checkout main
	git pull origin main
	@echo "$(GREEN)✓ Synced with origin/main$(RESET)"
