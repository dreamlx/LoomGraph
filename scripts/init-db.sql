-- LoomGraph Database Initialization Script
-- This script runs when PostgreSQL container starts for the first time

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- Code Chunks Table
-- ============================================
CREATE TABLE IF NOT EXISTS code_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    file_path TEXT NOT NULL,
    chunk_type VARCHAR(50) NOT NULL,  -- 'function', 'class', 'module', 'method'
    name TEXT,                         -- Symbol name (function/class name)
    start_line INT NOT NULL,
    end_line INT NOT NULL,
    content TEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL, -- SHA256 for deduplication
    language VARCHAR(20) NOT NULL,     -- 'python', 'php', 'javascript', etc.
    embedding vector(768),             -- Jina Code V2 dimension
    metadata JSONB DEFAULT '{}',       -- Additional metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Unique constraint for deduplication
    CONSTRAINT uq_chunk_file_hash UNIQUE (file_path, content_hash)
);

-- ============================================
-- Entities Table (LightRAG extracted or codeindex symbols)
-- ============================================
CREATE TABLE IF NOT EXISTS entities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    entity_type VARCHAR(50) NOT NULL,  -- 'function', 'class', 'variable', 'module'
    description TEXT,                   -- Docstring or LLM-generated description
    chunk_id UUID REFERENCES code_chunks(id) ON DELETE CASCADE,
    embedding vector(768),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Unique constraint
    CONSTRAINT uq_entity_name_type_chunk UNIQUE (name, entity_type, chunk_id)
);

-- ============================================
-- Relationships Table
-- ============================================
CREATE TABLE IF NOT EXISTS relationships (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    target_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    relation_type VARCHAR(50) NOT NULL,  -- 'calls', 'imports', 'inherits', 'uses'
    weight FLOAT DEFAULT 1.0,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Unique constraint
    CONSTRAINT uq_relationship UNIQUE (source_id, target_id, relation_type)
);

-- ============================================
-- Indexes
-- ============================================

-- Vector indexes (IVFFlat for development, consider HNSW for production)
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON code_chunks
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE INDEX IF NOT EXISTS idx_entities_embedding ON entities
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- B-tree indexes for common queries
CREATE INDEX IF NOT EXISTS idx_chunks_file_path ON code_chunks(file_path);
CREATE INDEX IF NOT EXISTS idx_chunks_language ON code_chunks(language);
CREATE INDEX IF NOT EXISTS idx_chunks_chunk_type ON code_chunks(chunk_type);
CREATE INDEX IF NOT EXISTS idx_chunks_content_hash ON code_chunks(content_hash);

CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);
CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_entities_chunk ON entities(chunk_id);

CREATE INDEX IF NOT EXISTS idx_relationships_source ON relationships(source_id);
CREATE INDEX IF NOT EXISTS idx_relationships_target ON relationships(target_id);
CREATE INDEX IF NOT EXISTS idx_relationships_type ON relationships(relation_type);

-- GIN index for JSONB metadata queries
CREATE INDEX IF NOT EXISTS idx_chunks_metadata ON code_chunks USING GIN (metadata);
CREATE INDEX IF NOT EXISTS idx_entities_metadata ON entities USING GIN (metadata);

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

-- Trigger for code_chunks
DROP TRIGGER IF EXISTS update_code_chunks_updated_at ON code_chunks;
CREATE TRIGGER update_code_chunks_updated_at
    BEFORE UPDATE ON code_chunks
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- Sample Query Functions
-- ============================================

-- Search chunks by vector similarity
-- Usage: SELECT * FROM search_chunks_by_vector(query_vector, 10);
CREATE OR REPLACE FUNCTION search_chunks_by_vector(
    query_embedding vector(768),
    result_limit INT DEFAULT 10
)
RETURNS TABLE (
    id UUID,
    file_path TEXT,
    name TEXT,
    chunk_type VARCHAR(50),
    content TEXT,
    similarity FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.id,
        c.file_path,
        c.name,
        c.chunk_type,
        c.content,
        1 - (c.embedding <=> query_embedding) AS similarity
    FROM code_chunks c
    WHERE c.embedding IS NOT NULL
    ORDER BY c.embedding <=> query_embedding
    LIMIT result_limit;
END;
$$ LANGUAGE plpgsql;

-- Find callers of an entity (1-hop)
-- Usage: SELECT * FROM find_callers('UserService.login');
CREATE OR REPLACE FUNCTION find_callers(entity_name TEXT)
RETURNS TABLE (
    caller_name TEXT,
    caller_type VARCHAR(50),
    relation_type VARCHAR(50)
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        e_source.name AS caller_name,
        e_source.entity_type AS caller_type,
        r.relation_type
    FROM relationships r
    JOIN entities e_target ON r.target_id = e_target.id
    JOIN entities e_source ON r.source_id = e_source.id
    WHERE e_target.name = entity_name
      AND r.relation_type = 'calls';
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- Initial Data (optional)
-- ============================================

-- You can add seed data here if needed

COMMENT ON TABLE code_chunks IS 'Stores code chunks extracted from source files';
COMMENT ON TABLE entities IS 'Stores code entities (functions, classes, etc.)';
COMMENT ON TABLE relationships IS 'Stores relationships between entities';
