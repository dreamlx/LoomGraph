# 🧶 LoomGraph: Enterprise Code Intelligence Engine (H200 Optimized)

**让 TB 级代码资产在 H200 算力巅峰上复活。**

LoomGraph 是一款专为企业私有化部署设计的超大规模代码智能理解与搜索引擎。它通过结合 NVIDIA H200 的极致算力与 GraphRAG 拓扑技术，解决大型上市公司在面对“超大项目、复杂依赖、技术债务”时的代码理解成本问题。

## 🚀 核心愿景
将软件工程从“片段式检索”提升至“全局逻辑理解”。利用 H200 的 141GB 显存，我们让原本只能在云端运行的百亿级代码大模型，物理隔绝地运行在企业机房。

## 🛠 技术栈
- **Compute:** NVIDIA H200 (Optimized for FP8 Inference & Batch Embedding)
- **Model:** Jina Code Embeddings V2 (8k Long Context)
- **RAG Architecture:** LightRAG + Graph Extraction
- **Intelligence:** DeepSeek-Coder-V2 / Llama-3.1 (State-of-the-art Code LLMs)
- **Database:** Postgres (pgvector) + Schema-based Graph Storage
- **Protocol:** MCP (Model Context Protocol) 

## 🌟 核心特性
- **Hybrid Search:** 结合 Keyword (精准变量名)、Semantic (意图理解) 与 Graph (依赖关系) 的三路索引。
- **Incremental Indexing:** 针对 H200 优化的增量图谱构建，保存代码即更新，无需全量重跑。
- **AST-Aware Chunking:** 基于 Tree-sitter 的代码解析，尊重函数与类的逻辑边界。
- **Privacy First:** 100% 私有化部署，代码不出柜，模型不出机房。

## 📂 模块规划 (Claude Code 开发路线)

### Phase 1: 基建层 (Core Engine)
- [ ] 基于 TensorRT-LLM 封装 H200 推理加速模块。
- [ ] 集成 Jina Code V2 实现 8k 长度的代码向量化。
- [ ] 基于 Postgres 建立 Vector + Edge 混合存储。

### Phase 2: 图谱层 (Graph Brain)
- [ ] 开发 AST 代码切片器 (Tree-sitter Python/JS/C++)。
- [ ] 实现 LightRAG 核心逻辑：Entity 提取与关系映射。
- [ ] 针对 H200 显存优化并行图谱构建任务。

### Phase 3: 应用层 (Interface)
- [ ] 开发 MCP Server 接口，对接 Claude Desktop / Cursor。
- [ ] 实现增量更新 File Watcher 逻辑。
- [ ] (可选) 企业级权限管理 (RBAC) 模块。

## 💻 快速启动 (开发者预览)
```bash
# 1. 配置 H200 环境
pip install vllm mcp lightrag-h200

# 2. 注入代码库
loomgraph index --path /path/to/massive-repo

# 3. 开启 MCP 服务
loomgraph serve --port 8080 --model-path /models/deepseek-coder-v2