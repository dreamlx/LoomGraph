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

## Claude Code native-MCP orientation

`claude_orientation.py` is a host-side, read-only orientation runner. It is a
separate runtime label from OMP/Pier: do not pool their timing, token, or
quality rows. It retains the full `stream-json` trace, final `result` event,
command, pre/post Git state, final run record, and adapter-owned
`orientation.json` in an empty output directory. The source directory must
start clean; any model-phase change makes the packet invalid.

The two conditions share the same instruction file and JSON Schema. Baseline
is `text-only` with `Read`, `Glob`, and `Grep`. Treatment defaults to
`mcp-only`, a compatibility boundary with no built-in navigation tools and a
server-side allowlist containing only native `loomgraph_find` and
`loomgraph_graph`. Pass `--treatment-surface additive` for the development-use
condition: it retains `Read`, `Glob`, and `Grep` and adds the same allowlisted
MCP tools. Claude adds its required `StructuredOutput` tool when the JSON
Schema is active. `--allowedTools` auto-allows the MCP calls; the server
allowlist is the availability boundary.

```bash
python evals/deepswe/claude_orientation.py \
  --condition baseline \
  --task-id psd-tools-blend-range-api \
  --source-dir /tmp/task-source \
  --instruction-file /tmp/orientation.txt \
  --output-dir /tmp/claude-baseline-1

python evals/deepswe/claude_orientation.py \
  --condition treatment \
  --treatment-surface additive \
  --task-id psd-tools-blend-range-api \
  --source-dir /tmp/task-source \
  --instruction-file /tmp/orientation.txt \
  --output-dir /tmp/claude-treatment-1
```

`--use-mode assisted` adds the same requirement to both arms to use at least
one available navigation tool. It is not pooled with `voluntary`. Run an
alternating baseline-first / treatment-first pair before calculating any
efficiency delta. A Claude Code host run against the exact task source is not
evidence that the Claude binary itself ran inside a DeepSWE container.

## Use modes

`voluntary` is the default: LoomGraph is available, but the model may choose
not to retrieve. `assisted` is a separately labelled treatment mode: it must
complete one evidence-bearing structural `find` or `graph` query before
emitting its packet. They are never pooled as one treatment. The tool card is
backend-aware: codegraph has already been indexed by setup and must not be
indexed again; codeindex may be indexed once before retrieval.

For the shared five-call budget, the assisted instruction reserves one call for
Claude's required `StructuredOutput`; it therefore directs the agent to use at
most four navigation calls. The adapter remains the enforcing authority and
marks any overflow invalid.

`mcp-only` and `additive` are different treatment surfaces and are never
pooled. Only an `additive` treatment paired with the same-task `text-only`
baseline answers whether normal development navigation changes when LoomGraph
is available and used; `mcp-only` answers only whether the native MCP surface
can stand alone.

The adapter records the requested model identifier plus separate assistant,
session-event, and aggregated-usage model identifiers. `observed` remains their
backward-compatible union; only `assistant_observed` identifies models attached
to assistant events. This prevents session initialization or auxiliary usage
telemetry from being misreported as the reasoning model. It also records
`tool_call_count`, raw `agent_execution_seconds`, structural retrieval evidence,
and any unexpected MCP tool. A raw duration is not an efficiency claim: compare
only predeclared, valid, same-task pairs with separately declared cold setup.

For a trust-required treatment, the adapter accepts resolution ratios only when
they exactly match a successful native `loomgraph_graph` response retained in
the stream. A well-formed but unmatched model-reported ratio is marked
`unverified_treatment_trust_resolution`; it cannot become a valid trust result.
An overrun of the configured tool-call budget, unexpected MCP tool, or
assisted treatment without evidence-bearing retrieval makes the packet invalid.
A successful `find` needs
a non-empty match set and a `graph` needs a resolved entity. These are
operational measurements, not target-hit penalties.

For a `task-id` declared in `agent-use-fixtures.json`, the adapter also records
the frozen path oracle, recall, missing/unexpected paths, and exact path-set
match in `fixture_observation`. This is an observation only: it never changes
the protocol-valid packet status or creates a performance claim.

The runner loads Claude Code's `project,local` setting sources so a fixture's
project `CLAUDE.md` is part of the evaluated integration. `--strict-mcp-config`
still confines MCP availability to the adapter-owned configuration.

The summary also reads Pier's sibling trial `result.json`: uncached input
tokens, cached input tokens, output tokens, model cost, agent navigation time,
cold setup time, and total trial time. It emits raw rows, only explicit
baseline/treatment replicate pairs, and per-task/stratum/mode delta summaries
with the inclusive median and IQR. Quality-invalid rows, either side exceeding
the configured tool-call budget, and assisted treatment without evidence-bearing retrieval
do not receive an efficiency delta.

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
