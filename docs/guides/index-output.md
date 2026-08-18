# `loomgraph index` 输出字段解读

**适用**: `loomgraph index` / `loomgraph update` 的 JSON 输出。回答"这个数字正常吗、
和那个数字为什么对不上"——字段语义以本文为准,快照性描述,代码是最终权威。

---

## 示例输出

```json
{
  "entities_created": 667,
  "relations_created": 8937,
  "resolved_ratio": 0.0614,
  "embedded": 667,
  "store_stats": {
    "entity_count": 667,
    "relation_count": 4541,
    "cross_module_relations": 127,
    "intra_module_relations": 71,
    "coupling_density": 0.6414
  }
}
```

## 字段表

| 字段 | 含义 |
|------|------|
| `entities_created` | 本次 codeindex export 产出的实体数(符号:class/function/method…) |
| `relations_created` | 本次 export 产出的**边事件数**——同一对符号间的 N 次调用计 N 条 |
| `resolved_ratio` | 本次产出的边中,**两端都 join 到已索引实体**的占比 |
| `embedded` | 实际写入向量的实体数(embedding 关闭时为 0) |
| `store_stats.entity_count` | 落库后的实体存量 |
| `store_stats.relation_count` | 落库后的**去重边数** |
| `store_stats.cross_module_relations` | 两端都解析到实体的边中,跨模块的数量 |
| `store_stats.intra_module_relations` | 同上口径,同模块的数量 |
| `store_stats.coupling_density` | `cross / (cross + intra)` —— 参与模块统计的边里跨模块的占比 |
| `warning` | 汇总的告警(partial-graph / 语言指纹 / 极低 resolve),可配 `warnings.silence` 静默 |
| `partial` | **`true` = 图缺符号**(有 parser grammar 缺失,或 repo 主语言不在索引语言里)。区别于 `warning` 里的质量 advisory(resolved_ratio / test 污染提示——图不缺符号,只是解读要打折)。`index`/`update`/MCP `refresh` 的成功 payload 都带此字段;被 `warnings.silence` 静默的告警不再置 true。exit code 不变——缺 1 门语言的图仍好过没有图,修复方式见 warning 文本(装 extra / 补 `languages:` 配置) |

## 三个常见"对不上"

### 1. `relations_created`(8937)≫ `relation_count`(4541)

不是丢失。store 按 `(src_id, tgt_id, keywords)` 去重合并:同一对符号之间的
多次调用/引用,`relations_created` 按事件计 N 次,落库合并成 1 行。
**前者是"发生了多少次",后者是"存在多少条不同的边"。**

### 2. `cross + intra`(198)≠ `relation_count`(4541)

模块统计只计入**两端都解析到实体**的边(`src`/`tgt` 能在实体表按名字 join 到,
且该实体有 `source_id`)。差额 4343 条是至少一端 unresolved 的边——典型如
`x.json()` 动态分发、第三方库调用(`os.environ.get` 这类目标不在本仓库)。
这与第 3 点直接相关。

### 3. `resolved_ratio` 怎么读

它衡量"边两端都落在**本仓库已索引实体**上"的占比。第三方/内置调用天然不解析,
所以**普遍偏低是常态**,不是故障:

| 档位 | 典型场景 |
|------|----------|
| `~0.2` | 正常 Python 仓(loomgraph 自身 0.19) |
| `< 0.1` | 已知盲区档:TS `@/` path-alias、Java Spring DI、重动态分发语言。index 会附 warning 提示;`topology` 的孤儿数在这个水平**不是死代码证据**(输出自带 caveat) |
| → `1.0` | 只会出现在封闭代码(所有依赖都在索引范围内) |

**什么时候该行动**:`resolved_ratio` 低 + `graph <实体>` 查询返回空 callers/callees,
而你确信调用关系存在 → 先查语言配置(见下),再看是否命中 codeindex 的解析盲区
(TS alias / Java DI 有专门修复历史,见根 CHANGELOG)。

## 健康度自查

```bash
loomgraph index . && loomgraph topology   # topology 的 resolution 块携带同样口径
loomgraph status                          # workspace 实体/关系数
```

- 实体数远小于仓库规模(如 TS 仓只有个位数)→ 大概率语言指纹问题:index 会打
  `language fingerprint: detected N typescript files, none indexed` 警告,按提示
  在 `.codeindex.yaml` 的 `languages:` 补上该语言
- `relation_count` 为 0 但实体正常 → 调用边全 unresolved,检查动态分发占比,
  或该语言是否在 codeindex 的边解析覆盖内(python/php/java/ts/js/swift/objc)
