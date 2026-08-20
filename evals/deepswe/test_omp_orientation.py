"""Contract tests for the orientation packet parser."""

from __future__ import annotations

import base64
import json
from pathlib import Path

from omp_loomgraph import OmpWithLoomGraph, _tool_card
from omp_orientation import OmpWithOrientation


def _encoded_trace(
    response: str,
    *,
    commands: list[str] | None = None,
    command_results: list[dict[str, object]] | None = None,
    tool_call_count: int = 0,
) -> str:
    trace = {
        "response": response,
        "loomgraph_commands": commands or [],
        "loomgraph_command_results": command_results or [],
        "tool_call_count": tool_call_count,
    }
    return base64.b64encode(json.dumps(trace).encode()).decode()


def _response() -> str:
    return json.dumps(
        {
            "candidates": [
                {"path": "src/example.py", "symbol": "Example", "reason": "observed"}
            ],
            "evidence": [],
            "tooling": {"loomgraph": {}},
        }
    )


def test_raw_json_is_a_semantic_packet_and_raw_json_compliant() -> None:
    adapter = OmpWithOrientation.__new__(OmpWithOrientation)

    packet = adapter._packet_from_trace(_encoded_trace(_response()), source_mutated=False)

    assert packet["status"] == "complete"
    assert packet["response_format"] == "raw_json"
    assert packet["source_clean_scope"] == "model_phase"
    assert packet["instrumentation_cache_paths"] == []


def test_single_json_fence_is_a_semantic_packet_but_not_raw_json_compliant() -> None:
    adapter = OmpWithOrientation.__new__(OmpWithOrientation)

    packet = adapter._packet_from_trace(
        _encoded_trace(f"```json\n{_response()}\n```"), source_mutated=False
    )

    assert packet["status"] == "complete"
    assert packet["response_format"] == "markdown_fenced"


def test_prose_around_a_json_fence_remains_invalid() -> None:
    adapter = OmpWithOrientation.__new__(OmpWithOrientation)

    packet = adapter._packet_from_trace(
        _encoded_trace(f"Here is the packet:\n```json\n{_response()}\n```"),
        source_mutated=False,
    )

    assert packet["status"] == "missing_or_invalid_agent_response"
    assert packet["response_format"] == "invalid"


def test_orientation_template_ends_with_a_raw_json_checklist() -> None:
    template = Path(__file__).with_name("orientation-packet.j2").read_text()

    assert "Final response checklist" in template
    assert "must begin with `{` and end with `}`" in template
    assert "Do not precede it with" in template
    assert "explanation or a Markdown fence" in template


def test_example_candidate_is_not_a_production_orientation_packet() -> None:
    adapter = OmpWithOrientation.__new__(OmpWithOrientation)
    response = json.loads(_response())
    response["candidates"][0]["path"] = "examples/rich_log_follow_state.py"

    packet = adapter._packet_from_trace(
        _encoded_trace(json.dumps(response)), source_mutated=False
    )

    assert packet["status"] == "missing_or_invalid_agent_response"


def test_codegraph_cache_is_declared_as_instrumentation_not_source_change() -> None:
    adapter = OmpWithLoomGraph.__new__(OmpWithLoomGraph)
    adapter._loomgraph_backend = "codegraph"

    assert adapter._instrumentation_cache_paths() == [".codegraph/"]
    assert adapter._missing_packet()["instrumentation_cache_paths"] == [".codegraph/"]


def test_packet_records_observed_tool_budget() -> None:
    adapter = OmpWithOrientation.__new__(OmpWithOrientation)

    packet = adapter._packet_from_trace(
        _encoded_trace(_response(), tool_call_count=6), source_mutated=False
    )

    assert packet["tool_call_count"] == 6
    assert packet["tool_call_budget"] == 5
    assert packet["tool_call_budget_overrun"] is True


def test_backend_aware_tool_cards_separate_setup_from_retrieval() -> None:
    codeindex = _tool_card("codeindex", "assisted")
    codegraph = _tool_card("codegraph", "assisted", workspace="app:main")

    assert "index ." in codeindex
    assert "must run one structural retrieval" in codeindex
    assert "non-empty structural evidence" in codeindex
    assert "find <symbol>" in codeindex
    assert "Do not add `--format`" in codeindex
    assert "do not pipe or truncate its output" in codeindex
    assert "Do not run `loomgraph index` again" in codegraph
    assert "must run one structural retrieval" in codegraph
    assert "--workspace app:main" in codegraph
    assert "not `/app`" in codegraph
    assert "Do not add `--format`" in codegraph


def test_assisted_requirement_recognizes_quoted_loomgraph_binary() -> None:
    adapter = OmpWithLoomGraph.__new__(OmpWithLoomGraph)
    adapter._orientation_use_mode = "assisted"

    assert adapter._retrieval_requirement(
        ['"$HOME/.local/bin/loomgraph" find Vulture'], True, True
    ) == (True, True)


def test_failed_retrieval_attempt_is_not_an_assisted_success() -> None:
    adapter = OmpWithLoomGraph.__new__(OmpWithLoomGraph)
    adapter._loomgraph_backend = "codegraph"
    adapter._loomgraph_workspace = "app:main"
    adapter._orientation_use_mode = "assisted"

    packet = adapter._packet_from_trace(
        _encoded_trace(
            _response(),
            commands=["$HOME/.local/bin/loomgraph find match --workspace /app"],
            command_results=[
                {
                    "command": "$HOME/.local/bin/loomgraph find match --workspace /app",
                    "success": False,
                    "evidence_bearing": False,
                }
            ],
        ),
        source_mutated=False,
    )

    assert packet["tooling"]["loomgraph"]["retrieval_succeeded"] is False
    assert packet["tooling"]["loomgraph"]["retrieval_evidence_succeeded"] is False
    assert packet["retrieval_requirement_met"] is False


def test_empty_successful_find_is_not_assisted_retrieval_evidence() -> None:
    adapter = OmpWithLoomGraph.__new__(OmpWithLoomGraph)
    adapter._loomgraph_backend = "codeindex"
    adapter._orientation_use_mode = "assisted"

    packet = adapter._packet_from_trace(
        _encoded_trace(
            _response(),
            commands=["$HOME/.local/bin/loomgraph find BlendRanges"],
            command_results=[
                {
                    "command": "$HOME/.local/bin/loomgraph find BlendRanges",
                    "success": True,
                    "evidence_bearing": False,
                }
            ],
        ),
        source_mutated=False,
    )

    assert packet["tooling"]["loomgraph"]["retrieval_succeeded"] is True
    assert packet["tooling"]["loomgraph"]["retrieval_evidence_succeeded"] is False
    assert packet["retrieval_requirement_met"] is False


def test_codegraph_packet_uses_adapter_observed_backend_and_workspace() -> None:
    adapter = OmpWithLoomGraph.__new__(OmpWithLoomGraph)
    adapter._loomgraph_backend = "codegraph"
    adapter._loomgraph_workspace = "app:main"
    adapter._orientation_use_mode = "assisted"
    response = json.loads(_response())
    response["tooling"]["loomgraph"] = {
        "backend": "codeindex",
        "workspace": "wrong:workspace",
    }

    packet = adapter._packet_from_trace(
        _encoded_trace(
            json.dumps(response),
            commands=["$HOME/.local/bin/loomgraph find match"],
        ),
        source_mutated=False,
    )

    assert packet["tooling"]["loomgraph"]["backend"] == "codegraph"
    assert packet["tooling"]["loomgraph"]["workspace"] == "app:main"


def test_codegraph_setup_workspace_comes_from_index_result() -> None:
    assert OmpWithLoomGraph._workspace_from_index_output(
        '{"success":true,"data":{"workspace":"app:main"}}'
    ) == "app:main"
    assert OmpWithLoomGraph._workspace_from_index_output("not json") is None


def test_codegraph_setup_workspace_falls_back_to_observed_status() -> None:
    assert OmpWithLoomGraph._workspace_from_status_output(
        '{"success":true,"data":{"workspace":{"name":"app:main"}}}'
    ) == "app:main"
    assert OmpWithLoomGraph._workspace_from_status_output("not json") is None
