# LoomGraph Skill

Use this skill when users ask about code search, code understanding, finding function callers/callees, or indexing a codebase for semantic search.

## Overview

LoomGraph is a code intelligence engine that provides:
- **Code Indexing**: Parse code → Generate embeddings → Build knowledge graph
- **Semantic Search**: Find code by natural language queries
- **Graph Queries**: Find callers, callees, inheritance relationships

## Prerequisites

Before using LoomGraph commands, ensure dependencies are installed:

```bash
# Check status
loomgraph status

# If codeindex is missing
pip install matrix-codeindex

# If database is not running
docker compose up -d postgres

# If embedding service is not running
docker compose up -d embedding
```

## Commands

### Index a Repository

**One-step (recommended for most cases)**:
```bash
loomgraph index /path/to/repo
```

**Step-by-step (for debugging or custom workflows)**:
```bash
# Step 1: Parse code with codeindex
codeindex scan /path/to/repo --output json > parse_results.json

# Step 2: Generate embeddings
loomgraph embed parse_results.json --output embeddings.json

# Step 3: Inject into graph database
loomgraph inject parse_results.json embeddings.json
```

### Search Code

```bash
# Semantic search
loomgraph search "user authentication logic"

# With specific mode
loomgraph search "login function" --mode semantic --limit 5
```

### Query Call Graph

```bash
# Find who calls a function
loomgraph graph "UserService.login" --direction callers

# Find what a function calls
loomgraph graph "UserService.login" --direction callees

# Find inheritance
loomgraph graph "UserService" --relation-type INHERITS
```

## Output Format

All commands output JSON for easy parsing:

```json
{
  "success": true,
  "data": { ... }
}
```

Or on error:
```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable message",
    "suggestion": "How to fix it"
  }
}
```

## Error Recovery

When a command fails, read the error message and follow the suggestion:

| Error Code | Action |
|------------|--------|
| `CODEINDEX_NOT_FOUND` | `pip install matrix-codeindex` |
| `DATABASE_CONNECTION_FAILED` | `docker compose up -d postgres` |
| `EMBEDDING_SERVICE_UNAVAILABLE` | `docker compose up -d embedding` |

## Example Workflow

User asks: "Find all functions that call the login method"

```bash
# 1. First, ensure the codebase is indexed
loomgraph status

# 2. If not indexed, index it
loomgraph index /path/to/repo

# 3. Query the call graph
loomgraph graph "login" --direction callers
```

## Documentation

- CLI Reference: `docs/api/CLI_DESIGN.md`
- System Design: `docs/architecture/SYSTEM_DESIGN.md`
- Data Contract: `docs/api/DATA_CONTRACT.md`
