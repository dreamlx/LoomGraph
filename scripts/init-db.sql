-- ============================================
-- LoomGraph Database Initialization
-- ============================================
--
-- NOTE: LoomGraph 使用 LightRAG 内置的 PostgreSQL 存储
--
-- LightRAG 提供的存储组件:
--   - PGKVStorage (Key-Value 存储)
--   - PGVectorStorage (向量存储)
--   - PGGraphStorage (图存储, 使用 Apache AGE)
--   - PGDocStatusStorage (文档状态追踪)
--
-- 本文件仅用于开发环境的基础设置和辅助视图。
-- 生产环境请使用 LightRAG 的初始化流程。
--
-- ============================================

-- 启用必要的扩展
CREATE EXTENSION IF NOT EXISTS vector;       -- pgvector (向量相似度)
CREATE EXTENSION IF NOT EXISTS pg_trgm;      -- 文本模糊搜索
-- CREATE EXTENSION IF NOT EXISTS age;       -- Apache AGE (图数据库) - 由 LightRAG 管理

-- ============================================
-- 辅助视图 (基于 LightRAG 的表结构)
-- ============================================

-- 注意：以下视图假设 LightRAG 已初始化其表结构
-- 如果表不存在，这些视图创建会失败（可忽略）

-- 代码实体统计视图
-- CREATE OR REPLACE VIEW code_entity_stats AS
-- SELECT
--     (properties->>'entity_type') as entity_type,
--     (properties->>'language') as language,
--     COUNT(*) as count
-- FROM lightrag_graph_nodes  -- LightRAG 的节点表
-- WHERE properties->>'file_path' IS NOT NULL
-- GROUP BY entity_type, language;

-- ============================================
-- 开发用辅助函数
-- ============================================

-- 健康检查函数
CREATE OR REPLACE FUNCTION health_check()
RETURNS TABLE(component TEXT, status TEXT) AS $$
BEGIN
    -- 检查 pgvector
    RETURN QUERY SELECT 'pgvector'::TEXT,
        CASE WHEN EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')
             THEN 'OK' ELSE 'MISSING' END;

    -- 检查 pg_trgm
    RETURN QUERY SELECT 'pg_trgm'::TEXT,
        CASE WHEN EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm')
             THEN 'OK' ELSE 'MISSING' END;
END;
$$ LANGUAGE plpgsql;

-- 使用示例：SELECT * FROM health_check();

-- ============================================
-- 权限设置
-- ============================================
-- 注意：LightRAG 会创建自己的用户和权限
-- 以下仅用于开发环境

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'loomgraph') THEN
        CREATE ROLE loomgraph WITH LOGIN PASSWORD 'loomgraph_dev';
    END IF;
END $$;

GRANT ALL PRIVILEGES ON DATABASE loomgraph TO loomgraph;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO loomgraph;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO loomgraph;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO loomgraph;
