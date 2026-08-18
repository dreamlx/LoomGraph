#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <output-archive.tar.gz>" >&2
  exit 2
fi

archive_path=$1
archive_dir=$(dirname "$archive_path")
archive_name=$(basename "$archive_path")
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)

mkdir -p "$archive_dir"
docker run --rm --platform linux/amd64 \
  --user "$(id -u):$(id -g)" \
  -e HOME=/tmp \
  -e ARCHIVE_NAME="$archive_name" \
  -v "$repo_root:/src:ro" \
  -v "$archive_dir:/output" \
  python:3.12-slim \
  sh -c '
    set -eu
    mkdir -p /tmp/wheelhouse
    python -m pip wheel --wheel-dir /tmp/wheelhouse /src
    cd /tmp/wheelhouse
    tar -czf "/output/$ARCHIVE_NAME" -- ./*.whl
  '
