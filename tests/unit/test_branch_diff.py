"""EPIC-016 (#185) PR2:BranchDiffAnalyzer —— 两个 ref 快照的方向性深 diff。

对比 `CompareAnalyzer`(对称 name-set diff,只报双边实体的边),这里给
branch-diff 消费者要的**方向性框架**:base→head 的 added/removed,断链
(base 有 head 无的边且 src 实体存活——「调用方还在、被调方没了」),
新链(head 新边且 src 在 base 已存在),content_hash 语义层(L2),模块
耦合 delta。边 diff 只计两端都解析到实体的边(#149/#154 resolvable-graph
口径,unresolved 只进计数)。
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from loomgraph.core.branch_diff import BranchDiffAnalyzer


def _entity(name: str, source: str = "src/mod.py:1-20", h: str | None = "h1") -> dict:
    return {
        "entity_name": name, "entity_type": "function",
        "source_id": source, "content_hash": h,
    }


def _edge(src: str, tgt: str, kind: str = "CALLS") -> dict:
    return {"src_id": src, "tgt_id": tgt, "keywords": kind}


def _analyzer(
    base_entities: list[dict], base_relations: list[dict],
    head_entities: list[dict], head_relations: list[dict],
) -> BranchDiffAnalyzer:
    base = AsyncMock()
    base.get_all_entities = AsyncMock(return_value=base_entities)
    base.get_all_relations = AsyncMock(return_value=base_relations)
    head = AsyncMock()
    head.get_all_entities = AsyncMock(return_value=head_entities)
    head.get_all_relations = AsyncMock(return_value=head_relations)
    return BranchDiffAnalyzer(base_store=base, head_store=head)


@pytest.mark.asyncio
async def test_identical_graphs_all_zero() -> None:
    ents = [_entity("a"), _entity("b")]
    rels = [_edge("a", "b")]
    result = await _analyzer(ents, rels, ents, rels).analyze()

    assert result.summary["entities_added_total"] == 0
    assert result.summary["broken_chains_total"] == 0
    assert result.summary["content_hash_missing"] == 0
    assert result.entities_added == [] and result.entities_removed == []
    assert result.edges_added == [] and result.edges_removed == []
    assert result.broken_chains == [] and result.new_chains == []
    assert result.content_changed == [] and result.module_delta == []


@pytest.mark.asyncio
async def test_entity_added_and_removed() -> None:
    result = await _analyzer(
        [_entity("old")], [],
        [_entity("new")], [],
    ).analyze()

    assert [e["name"] for e in result.entities_removed] == ["old"]
    assert [e["name"] for e in result.entities_added] == ["new"]


@pytest.mark.asyncio
async def test_edge_added_and_removed() -> None:
    base_e = [_entity("a"), _entity("b"), _entity("c")]
    head_e = [_entity("a"), _entity("b"), _entity("c")]
    result = await _analyzer(
        base_e, [_edge("a", "b")],
        head_e, [_edge("a", "c")],
    ).analyze()

    assert result.edges_removed == [{"src": "a", "tgt": "b", "keywords": "CALLS"}]
    assert result.edges_added == [{"src": "a", "tgt": "c", "keywords": "CALLS"}]


@pytest.mark.asyncio
async def test_broken_chain_tgt_removed() -> None:
    """断链:b→foo 边在 base 有,head 里 foo 实体没了但 b 还在。"""
    result = await _analyzer(
        [_entity("b"), _entity("foo")], [_edge("b", "foo")],
        [_entity("b")], [],
    ).analyze()

    assert [e["name"] for e in result.entities_removed] == ["foo"]
    assert result.broken_chains == [{"src": "b", "tgt": "foo", "keywords": "CALLS"}]
    # 断链绝不进 new_chains(方向性)
    assert result.new_chains == []


@pytest.mark.asyncio
async def test_new_chain_from_surviving_src() -> None:
    """新链:head 新增 baz→bar 边,baz 在 base 已存在(改了 body 开始调人)。"""
    base_e = [_entity("baz"), _entity("bar")]
    result = await _analyzer(
        base_e, [],
        [_entity("baz"), _entity("bar")], [_edge("baz", "bar")],
    ).analyze()

    assert result.new_chains == [{"src": "baz", "tgt": "bar", "keywords": "CALLS"}]


@pytest.mark.asyncio
async def test_removed_edge_with_src_also_gone_not_broken() -> None:
    """整文件重写:src 也消失 → 边进 edges_removed 但不算断链。"""
    result = await _analyzer(
        [_entity("x"), _entity("y")], [_edge("x", "y")],
        [], [],
    ).analyze()

    assert result.edges_removed == [{"src": "x", "tgt": "y", "keywords": "CALLS"}]
    assert result.broken_chains == []


@pytest.mark.asyncio
async def test_unresolved_edges_excluded_but_counted() -> None:
    """tgt 不是实体(dst_raw 悬挂边)→ 不进边 diff,只进计数。"""
    base_e = [_entity("a")]
    result = await _analyzer(
        base_e, [_edge("a", "json.stringify")],
        [_entity("a")], [_edge("a", "json.stringify"), _edge("a", "ghost")],
    ).analyze()

    assert result.edges_added == [] and result.edges_removed == []
    assert result.summary["base_unresolved_edges"] == 1
    assert result.summary["head_unresolved_edges"] == 2


@pytest.mark.asyncio
async def test_content_changed_vs_hash_missing() -> None:
    """L2:同名实体 hash 不同 → content_changed;一侧 None → 只计数。"""
    result = await _analyzer(
        [_entity("changed", h="h1"), _entity("nohash", h=None), _entity("same", h="h3")],
        [],
        [_entity("changed", h="h2"), _entity("nohash", h="hX"), _entity("same", h="h3")],
        [],
    ).analyze()

    assert [c["name"] for c in result.content_changed] == ["changed"]
    assert result.summary["content_hash_missing"] == 1  # nohash 两侧 None/值 → 不可比


@pytest.mark.asyncio
async def test_module_delta_by_src_module() -> None:
    """模块 delta 按边 src 端模块聚合,排序按变动量降序。"""
    base_e = [
        _entity("m1.caller", source="src/mod1/a.py:1-10"),
        _entity("m2.helper", source="src/mod2/b.py:1-10"),
    ]
    head_e = [
        _entity("m1.caller", source="src/mod1/a.py:1-10"),
        _entity("m2.helper", source="src/mod2/b.py:1-10"),
        _entity("m3.new", source="src/mod3/c.py:1-10"),
    ]
    result = await _analyzer(
        base_e, [_edge("m1.caller", "m2.helper")],
        head_e, [_edge("m1.caller", "m3.new"), _edge("m3.new", "m2.helper")],
    ).analyze()

    delta = {d["module"]: d for d in result.module_delta}
    # 新边 m3.new→m2.helper 归 src 端 mod3;m1.caller→m3.new 归 mod1(added)
    assert delta["src/mod3"]["edges_added"] == 1
    assert delta["src/mod1"]["edges_added"] == 1
    assert delta["src/mod1"]["edges_removed"] == 1
    # mod1 (added 1 + removed 1 = 2) 排在 mod3 (1) 前
    assert result.module_delta[0]["module"] == "src/mod1"
    assert result.summary["module_changed"] == 2


@pytest.mark.asyncio
async def test_list_cap_with_totals() -> None:
    """60 个新增实体 → 列表截 50,summary total = 60(不静默丢)。"""
    added = [_entity(f"n{i:02d}") for i in range(60)]
    result = await _analyzer([], [], added, []).analyze()

    assert len(result.entities_added) == 50
    assert result.summary["entities_added_total"] == 60


@pytest.mark.asyncio
async def test_to_dict_round_trip() -> None:
    result = await _analyzer(
        [_entity("a"), _entity("b")], [_edge("a", "b")],
        [_entity("a", h="changed")], [],
    ).analyze()
    d = result.to_dict()

    assert isinstance(d, dict)
    assert d["summary"]["entities_removed_total"] == 1
    assert d["graph_sizes"]["base_entities"] == 2
    assert d["graph_sizes"]["head_entities"] == 1
    assert d["entities_removed"][0]["name"] == "b"
    assert d["broken_chains"][0]["tgt"] == "b"


@pytest.mark.asyncio
async def test_shared_entities_counted() -> None:
    result = await _analyzer(
        [_entity("a"), _entity("b")], [],
        [_entity("b"), _entity("c")], [],
    ).analyze()
    assert result.summary["entities_shared"] == 1


def test_caps_are_module_constants_not_config() -> None:
    """零 config knob(EPIC-016 renunciation):cap 是模块常量。"""
    from loomgraph.core import branch_diff as m

    assert m._LIST_CAP == 50
    assert m._MODULE_CAP == 20
    assert m._MODULE_DEPTH == 2
