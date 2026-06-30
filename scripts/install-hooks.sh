#!/usr/bin/env bash
# scripts/install-hooks.sh — point this repo's .git/hooks at .githooks/
#
# Idempotent. Run once per clone (or after `git init`).
#
# What it gives you:
#   - .githooks/pre-push   blocks `git push origin vX.Y.Z` when the tag
#                          doesn't match pyproject.toml's version.
#
# CI runs the same check as a fail-fast job in release.yml, so even if a
# contributor skips this hook the bad release still gets aborted before
# build/publish. The hook is just there to fail faster + locally.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_DIR="${REPO_ROOT}/.githooks"

if [ ! -d "${HOOKS_DIR}" ]; then
  echo "Expected ${HOOKS_DIR} to exist; aborting."
  exit 1
fi

# Make all hooks in .githooks executable (one-time chmod after clone).
chmod +x "${HOOKS_DIR}"/*

# Point git at .githooks/ for this repo. Survives across hook changes
# (we just edit the files inside .githooks/, no re-install needed).
git config core.hooksPath "${HOOKS_DIR}"

echo "✓ git core.hooksPath → ${HOOKS_DIR}"
echo "✓ hooks installed:"
ls -1 "${HOOKS_DIR}"
