# DeepSWE evaluation smoke

This harness validates an agent-use claim, not task-solving performance.  It
runs the same DeepSWE task with a fixed OMP model and budget in two conditions:

- `baseline`: OMP plus the pre-edit orientation packet;
- `treatment`: the same packet plus an offline Linux/amd64 LoomGraph install
  and a small tool card.

The primary artifact is `artifacts/orientation.json`. A usable packet has
`status: "complete"`, `pre_edit: true`, up to five production-code candidates,
and records whether LoomGraph was used and its trust signals.  A task reward,
timeout, or patch is recorded separately and is never used as this harness's
capability metric. The agent runs only the orientation phase and is bounded by
OMP's `--max-time` (420 seconds by default). The adapter, rather than the
model, validates the final JSON response and writes the packet. A single
Markdown-fenced JSON object remains a semantic packet but is reported
separately as raw-JSON protocol non-compliance. Source changes make a packet
invalid.

## Local run

DeepSWE and Pier must already be available.  The runner obtains the DeepSeek
credential from the process or `$HOME/.hermes/.env`; it never writes that
credential to a repository file.

```bash
evals/deepswe/run-omp-smoke.sh baseline textual-richlog-follow-state
evals/deepswe/run-omp-smoke.sh treatment textual-richlog-follow-state
evals/deepswe/run-orientation-pilot.sh textual-richlog-follow-state 3
```

The treatment builds a self-contained `linux/amd64` wheelhouse, uploads it to
the isolated agent container, installs it with `--no-index`, and verifies
`loomgraph --version` before the agent starts.  On Apple Silicon this still
uses Docker's `linux/amd64` emulation, matching the later x86 host shape.

Each output directory contains Pier's result plus:

- `artifacts/orientation.json` — pre-edit navigation evidence;
- `artifacts/agent/omp.txt` — agent trace and tool calls;
- `artifacts/model.patch` and verifier data — task-side evidence only.

Do not pool these smoke runs into a benchmark or compare task rewards.  A
future Evaluation v1 run must use the reviewed task set and human-adjudicated
candidate targets defined in LoomGraph issue #206.
