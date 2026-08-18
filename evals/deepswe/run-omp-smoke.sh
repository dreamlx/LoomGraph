#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "usage: $0 <baseline|treatment> <task-id> [jobs-dir]" >&2
  exit 2
fi

condition=$1
task_id=$2
jobs_dir=${3:-$(mktemp -d /tmp/loomgraph-eval-omp.XXXXXX)}
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
deepswe_dir=${DEEPSWE_DIR:-"$HOME/Projects/opensource/deep-swe"}
hermes_env=${HERMES_ENV_FILE:-"$HOME/.hermes/.env"}

if [[ ! -d "$deepswe_dir/tasks/$task_id" ]]; then
  echo "DeepSWE task not found: $deepswe_dir/tasks/$task_id" >&2
  exit 2
fi
if [[ -z ${DEEPSEEK_API_KEY:-} && -f "$hermes_env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$hermes_env"
  set +a
fi
if [[ -z ${DEEPSEEK_API_KEY:-} ]]; then
  echo "DEEPSEEK_API_KEY is unavailable; configure it in the process or Hermes env." >&2
  exit 2
fi

common_args=(
  -p "tasks/$task_id"
  -m deepseek/deepseek-v4-flash
  --ak binary_x64=.cache/omp-linux-x64
  --ak binary_arm64=.cache/omp-linux-arm64
  --ak "prompt_template_path=$repo_root/evals/deepswe/orientation-packet.j2"
  --n-concurrent 1
  --agent-timeout-multiplier "${AGENT_TIMEOUT_MULTIPLIER:-0.05}"
  --verifier-timeout-multiplier "${VERIFIER_TIMEOUT_MULTIPLIER:-0.15}"
  --artifact /logs/artifacts
  --artifact /logs/agent
  --artifact /logs/verifier
  --jobs-dir "$jobs_dir"
)

case "$condition" in
  baseline)
    agent_args=(--agent-import-path omp_orientation:OmpWithOrientation)
    ;;
  treatment)
    wheelhouse="$jobs_dir/loomgraph-wheelhouse.tar.gz"
    "$repo_root/evals/deepswe/build-wheelhouse.sh" "$wheelhouse"
    agent_args=(
      --agent-import-path omp_loomgraph:OmpWithLoomGraph
      --ak "loomgraph_wheelhouse=$wheelhouse"
    )
    ;;
  *)
    echo "condition must be baseline or treatment" >&2
    exit 2
    ;;
esac

cd "$deepswe_dir"
PYTHONPATH="$repo_root/evals/deepswe:$deepswe_dir/agents${PYTHONPATH:+:$PYTHONPATH}" \
  pier run "${common_args[@]}" "${agent_args[@]}" \
  --job-name "loomgraph-eval-$condition-$task_id"

echo "Results: $jobs_dir"
