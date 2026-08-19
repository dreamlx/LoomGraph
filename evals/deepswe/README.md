# DeepSWE evaluation smoke

This harness validates an agent-use claim, not task-solving performance.  It
runs the same DeepSWE task with a fixed OMP model and budget in two conditions:

- `baseline`: OMP plus the pre-edit orientation packet;
- `treatment`: the same packet plus an offline Linux/amd64 LoomGraph install
  and a small tool card.

The primary artifact is `artifacts/orientation.json`. A usable packet has
`status: "complete"`, `pre_edit: true`, up to five production-code candidates,
and records observed LoomGraph commands and trust signals. A task reward,
timeout, or patch is recorded separately and is never used as this harness's
capability metric. The agent runs only the orientation phase and is bounded by
OMP's `--max-time` (420 seconds by default). The adapter, rather than the
model, validates the final JSON response and writes the packet. A single
Markdown-fenced JSON object remains a semantic packet but is reported
separately as raw-JSON protocol non-compliance. Source changes during the model
phase make a packet invalid; any setup cache path is declared separately in the
packet.

## Local run

DeepSWE and Pier must already be available.  The runner obtains the DeepSeek
credential from the process or `$HOME/.hermes/.env`; it never writes that
credential to a repository file.

```bash
evals/deepswe/run-omp-smoke.sh baseline textual-richlog-follow-state
evals/deepswe/run-omp-smoke.sh treatment textual-richlog-follow-state
evals/deepswe/run-orientation-pilot.sh textual-richlog-follow-state 3
# Assisted-use is a separate treatment label; it requires one retrieval query.
evals/deepswe/run-orientation-pilot.sh textual-richlog-follow-state 3 /tmp/assisted assisted
```

The treatment builds a self-contained `linux/amd64` wheelhouse, uploads it to
the isolated agent container, installs it with `--no-index`, and verifies
`loomgraph --version` before the agent starts.  On Apple Silicon this still
uses Docker's `linux/amd64` emulation, matching the later x86 host shape.

The default treatment backend is `codeindex`.  To exercise the separate
codegraph capability gate, build the pinned Linux bundle and select it:

```bash
evals/deepswe/build-codegraph-bundle.sh /tmp/codegraph-linux-x64.tar.gz
LOOMGRAPH_BACKEND=codegraph \
CODEGRAPH_BUNDLE=/tmp/codegraph-linux-x64.tar.gz \
evals/deepswe/run-omp-smoke.sh treatment ts-pattern-match-each
```

The runner installs the bundle as the agent user and verifies
`codegraph --version` before OMP starts. For the codegraph backend it also
builds `.codegraph/codegraph.db` when absent and runs the LoomGraph index gate
before OMP starts; this ignored local index is declared as instrumentation and
the source-clean check begins only after setup. The bundle is intentionally
kept outside the repository; the package version is controlled by
`CODEGRAPH_VERSION` and defaults to `1.5.0`.

## Use modes

`voluntary` is the default: LoomGraph is available, but the model may choose
not to retrieve. `assisted` is a separately labelled treatment mode: it must
run one structural `find` or `graph` query before emitting its packet. They are
never pooled as one treatment. The tool card is backend-aware: codegraph has
already been indexed by setup and must not be indexed again; codeindex may be
indexed once before retrieval.

The adapter records observed `tool_call_count`, the five-call budget-overrun
flag, and both structural-retrieval attempts and confirmed successful
retrievals (from OMP tool-result events, not model self-report). Assisted mode
requires one successful structural retrieval. These are operational
measurements, not target-hit penalties.

The summary also reads Pier's sibling trial `result.json`: uncached input
tokens, cached input tokens, output tokens, model cost, agent navigation time,
cold setup time, and total trial time. It emits raw rows, only explicit
baseline/treatment replicate pairs, and per-task/stratum/mode delta summaries
with the inclusive median and IQR. Quality-invalid rows and unsuccessful
assisted treatment do not receive an efficiency delta.

Each output directory contains Pier's result plus:

- `artifacts/orientation.json` — pre-edit navigation evidence;
- `artifacts/agent/omp.txt` — agent trace and tool calls;
- `artifacts/model.patch` and verifier data — task-side evidence only.

Summarize a pilot with the frozen target manifest after all runs complete:

```bash
evals/deepswe/summarize-orientation-pilot.py /tmp/loomgraph-orientation-pilot
```

It writes `orientation-summary.json` alongside the run outputs and prints one
row per task/condition/use-mode. The rows separate invocation, structural
retrieval, and index-only use; target-hit, existing-file recall, new-path
nomination, tool-call budget, and assisted-use compliance are also distinct.
For N>1, the pilot runner alternates baseline-first and treatment-first by
replicate while preserving the explicit replicate number used for paired deltas.
The manifest remains host-only and is never mounted into the agent container.

## Evaluation v1 target set

The frozen 12-task target set is `target-manifest.json`; its protocol is
documented in [`docs/evals/evaluation-v1.md`](../../docs/evals/evaluation-v1.md).
To regenerate it from the pinned local DeepSWE checkout:

```bash
python evals/deepswe/build-target-manifest.py \
  --deep-swe-root /path/to/deep-swe \
  --output evals/deepswe/target-manifest.json
```

The generator reads patch headers and records patch hashes, but never copies
gold patch contents into the agent image. Do not mount the manifest, solution,
or verifier patch into an agent run. `target_hit@5` is only valid after the
codegraph installation/index gate passes for its two codegraph strata.

Do not pool the smoke runs into a benchmark or compare task rewards. The smoke
validates the adapter and artifact chain; the independent target set is the
boundary for the later orientation-quality measurement.
