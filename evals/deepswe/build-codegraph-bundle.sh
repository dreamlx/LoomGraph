#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <output-archive>" >&2
  exit 2
fi

output=$1
version=${CODEGRAPH_VERSION:-1.5.0}
staging=$(mktemp -d /tmp/loomgraph-codegraph-build.XXXXXX)
trap 'rm -rf "$staging"' EXIT

npm pack --silent "@colbymchenry/codegraph-linux-x64@$version" \
  --pack-destination "$staging" >/dev/null
tarball=$(find "$staging" -maxdepth 1 -type f -name '*.tgz' -print -quit)
if [[ -z "$tarball" ]]; then
  echo "npm did not produce a codegraph package" >&2
  exit 1
fi

mkdir -p "$staging/unpacked"
tar -xzf "$tarball" -C "$staging/unpacked" --strip-components=1
if [[ ! -x "$staging/unpacked/bin/codegraph" ]]; then
  echo "codegraph package has no executable bin/codegraph" >&2
  exit 1
fi

mkdir -p "$(dirname "$output")"
tar --no-xattrs -C "$staging/unpacked" -czf "$output" .
printf 'Built %s (%s bytes)\n' "$output" "$(wc -c < "$output" | tr -d ' ')"
