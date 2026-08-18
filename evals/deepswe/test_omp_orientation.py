"""Contract tests for the orientation packet parser."""

from __future__ import annotations

import base64
import json

from omp_loomgraph import OmpWithLoomGraph, _tool_card
from omp_orientation import OmpWithOrientation


def _encoded_trace(
    response: str, *, commands: list[str] | None = None, tool_call_count: int = 0
) -> str:
    trace = {
        "response": response,
        "loomgraph_commands": commands or [],
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
    codegraph = _tool_card("codegraph", "assisted")

    assert "index ." in codeindex
    assert "must run one structural retrieval" in codeindex
    assert "Do not run `loomgraph index` again" in codegraph
    assert "must run one structural retrieval" in codegraph
