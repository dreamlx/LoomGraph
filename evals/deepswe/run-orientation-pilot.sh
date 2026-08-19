#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 4 ]]; then
  echo "usage: $0 <task-id> [runs-per-condition] [output-dir] [voluntary|assisted]" >&2
  exit 2
fi

task_id=$1
runs=${2:-3}
output_dir=${3:-$(mktemp -d /tmp/loomgraph-orientation-pilot.XXXXXX)}
use_mode=${4:-voluntary}
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
wheelhouse=${LOOMGRAPH_WHEELHOUSE:-"$output_dir/loomgraph-wheelhouse.tar.gz"}

if ! [[ "$runs" =~ ^[1-9][0-9]*$ ]]; then
  echo "runs-per-condition must be a positive integer" >&2
  exit 2
fi
if [[ "$use_mode" != "voluntary" && "$use_mode" != "assisted" ]]; then
  echo "use mode must be voluntary or assisted" >&2
  exit 2
fi

mkdir -p "$output_dir"
if [[ -z ${LOOMGRAPH_WHEELHOUSE:-} ]]; then
  "$repo_root/evals/deepswe/build-wheelhouse.sh" "$wheelhouse"
fi
if [[ ! -f "$wheelhouse" ]]; then
  echo "LoomGraph wheelhouse not found: $wheelhouse" >&2
  exit 2
fi

for run in $(seq 1 "$runs"); do
  if (( run % 2 )); then
    conditions=(baseline treatment)
  else
    conditions=(treatment baseline)
  fi
  for condition in "${conditions[@]}"; do
    LOOMGRAPH_WHEELHOUSE="$wheelhouse" \
      "$repo_root/evals/deepswe/run-omp-smoke.sh" \
      "$condition" "$task_id" "$output_dir/$condition-$use_mode-$run" "$use_mode"
  done
done

"$repo_root/evals/deepswe/summarize-orientation-pilot.py" "$output_dir"
