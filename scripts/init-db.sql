-- LoomGraph Database Initialization
-- This script runs automatically when the PostgreSQL container starts

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- For text search

-- ============================================
-- Code Chunks Table
-- ============================================
CREATE TABLE IF NOT EXISTS code_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_path TEXT NOT NULL,
    chunk_type VARCHAR(50) NOT NULL,  -- 'function', 'class', 'method', 'module'
    name TEXT,                         -- Symbol name (e.g., 'UserService.login')
    signature TEXT,                    -- Full signature
    start_line INT NOT NULL,
    end_line INT NOT NULL,
    content TEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL, -- SHA256 for deduplication
    language VARCHAR(20) NOT NULL,     -- 'python', 'php', 'javascript'
    docstring TEXT,
    embedding vector(768),             -- Jina Code V2 dimension
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(file_path, content_hash)
);

-- ============================================
-- Entities Table (from AST extraction)
-- ============================================
CREATE TABLE IF NOT EXISTS entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,                -- Full qualified name
    entity_type VARCHAR(50) NOT NULL,  -- 'function', 'class', 'method', 'variable'
    description TEXT,                  -- From docstring
    file_path TEXT NOT NULL,           -- Source file path
    start_line INT,                    -- Start line number
    end_line INT,                      -- End line number
    chunk_id UUID REFERENCES code_chunks(id) ON DELETE CASCADE,
    embedding vector(768),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(name, entity_type, file_path)
);

-- ============================================
-- Relationships Table (from AST extraction)
-- ============================================
CREATE TABLE IF NOT EXISTS relationships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    target_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    relation_type VARCHAR(50) NOT NULL,  -- 'CALLS', 'INHERITS', 'IMPORTS', 'USES'
    weight FLOAT DEFAULT 1.0,
    line_number INT,                     -- Where the relationship occurs
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(source_id, target_id, relation_type)
);

-- ============================================
-- LightRAG KV Storage (for compatibility)
-- ============================================
CREATE TABLE IF NOT EXISTS lightrag_kv (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================
-- Indexes
-- ============================================

-- Vector indexes (IVFFlat for now, can switch to HNSW later)
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON code_chunks
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE INDEX IF NOT EXISTS idx_entities_embedding ON entities
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Text search indexes
CREATE INDEX IF NOT EXISTS idx_chunks_content_trgm ON code_chunks
    USING gin (content gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_chunks_name_trgm ON code_chunks
    USING gin (name gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_entities_name_trgm ON entities
    USING gin (name gin_trgm_ops);

-- Graph traversal indexes
CREATE INDEX IF NOT EXISTS idx_relationships_source ON relationships(source_id);
CREATE INDEX IF NOT EXISTS idx_relationships_target ON relationships(target_id);
CREATE INDEX IF NOT EXISTS idx_relationships_type ON relationships(relation_type);

-- File path indexes (for full rebuild: delete by repo)
CREATE INDEX IF NOT EXISTS idx_chunks_file_path ON code_chunks(file_path);
CREATE INDEX IF NOT EXISTS idx_entities_file_path ON entities(file_path);

-- ============================================
-- Helper Functions
-- ============================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers for updated_at
DROP TRIGGER IF EXISTS update_code_chunks_updated_at ON code_chunks;
CREATE TRIGGER update_code_chunks_updated_at
    BEFORE UPDATE ON code_chunks
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_lightrag_kv_updated_at ON lightrag_kv;
CREATE TRIGGER update_lightrag_kv_updated_at
    BEFORE UPDATE ON lightrag_kv
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- Useful Views
-- ============================================

-- View: Entity with its relationships
CREATE OR REPLACE VIEW entity_graph AS
SELECT
    e.id,
    e.name,
    e.entity_type,
    e.description,
    COALESCE(
        json_agg(
            json_build_object(
                'target', te.name,
                'type', r.relation_type,
                'weight', r.weight
            )
        ) FILTER (WHERE r.id IS NOT NULL),
        '[]'
    ) AS outgoing_relations
FROM entities e
LEFT JOIN relationships r ON e.id = r.source_id
LEFT JOIN entities te ON r.target_id = te.id
GROUP BY e.id, e.name, e.entity_type, e.description;

-- View: File statistics
CREATE OR REPLACE VIEW file_stats AS
SELECT
    file_path,
    language,
    COUNT(*) AS chunk_count,
    SUM(end_line - start_line + 1) AS total_lines,
    MAX(updated_at) AS last_indexed
FROM code_chunks
GROUP BY file_path, language;

-- ============================================
-- Helper Functions for Full Rebuild (MVP)
-- ============================================

-- Delete all data for a repository (by file path prefix)
-- Usage: SELECT delete_by_repo('/path/to/repo');
CREATE OR REPLACE FUNCTION delete_by_repo(repo_path TEXT)
RETURNS TABLE(deleted_chunks INT, deleted_entities INT, deleted_relationships INT) AS $$
DECLARE
    chunk_count INT;
    entity_count INT;
    rel_count INT;
BEGIN
    -- Delete relationships first (foreign key constraint)
    DELETE FROM relationships
    WHERE source_id IN (SELECT id FROM entities WHERE file_path LIKE repo_path || '%')
       OR target_id IN (SELECT id FROM entities WHERE file_path LIKE repo_path || '%');
    GET DIAGNOSTICS rel_count = ROW_COUNT;

    -- Delete entities
    DELETE FROM entities WHERE file_path LIKE repo_path || '%';
    GET DIAGNOSTICS entity_count = ROW_COUNT;

    -- Delete chunks
    DELETE FROM code_chunks WHERE file_path LIKE repo_path || '%';
    GET DIAGNOSTICS chunk_count = ROW_COUNT;

    RETURN QUERY SELECT chunk_count, entity_count, rel_count;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- Grant permissions
-- ============================================
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO loomgraph;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO loomgraph;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO loomgraph;
