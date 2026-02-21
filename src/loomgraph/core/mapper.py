"""Mapping layer between codeindex and LightRAG.

This module implements the data contract defined in docs/api/DATA_CONTRACT.md.
It transforms codeindex ParseResult into LightRAG entity/relation format.

**LightRAG API Convention (confirmed 2025-02-04)**:
- entity_data: entity_type, description (concat signature+language), source_id, file_path
- edge_data: keywords (relation_type), description, weight, source_id
- embedding: Let LightRAG auto-generate (do not pass)
"""

from pathlib import Path
from typing import Any

from .models import (
    Call,
    EntityData,
    Inheritance,
    Import,
    RelationData,
    Symbol,
)

# Language detection mapping
EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".swift": "swift",
    ".scala": "scala",
    ".lua": "lua",
    ".r": "r",
    ".R": "r",
    ".sql": "sql",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "zsh",
}


def detect_language(file_path: str | Path) -> str:
    """Detect programming language from file extension.

    Args:
        file_path: Path to the source file

    Returns:
        Language identifier (e.g., "python", "javascript")
    """
    path = Path(file_path) if isinstance(file_path, str) else file_path
    suffix = path.suffix.lower()
    return EXTENSION_TO_LANGUAGE.get(suffix, "unknown")


def map_symbol_to_entity(
    symbol: Symbol,
    file_path: str,
    language: str,
) -> EntityData:
    """Map codeindex Symbol to LightRAG entity data.

    **LightRAG Convention**:
    - description: Concatenate signature + language + file:line for semantic search
    - source_id: file:line_start-line_end for linking
    - Do NOT pass embedding (let LightRAG auto-generate)

    Args:
        symbol: Symbol from codeindex ParseResult
        file_path: Path to the source file
        language: Programming language identifier

    Returns:
        EntityData ready for LightRAG acreate_entity()

    Example:
        >>> symbol = Symbol(
        ...     name="UserService.login",
        ...     kind="method",
        ...     signature="def login(self, username: str, password: str) -> bool",
        ...     docstring="Authenticate user with credentials.",
        ...     line_start=12,
        ...     line_end=25
        ... )
        >>> entity = map_symbol_to_entity(symbol, "src/auth/service.py", "python")
        >>> entity.entity_name
        'UserService.login'
        >>> "Python" in entity.entity_data["description"]
        True
    """
    entity_name = symbol.name

    # Build description: kind: name | signature | docstring (truncated) | Language | file:line
    # kind prefix improves semantic search; docstring truncation prevents bloated descriptions
    description_parts = [f"{symbol.kind}: {symbol.name}"]
    if symbol.signature:
        description_parts.append(symbol.signature)
    if symbol.docstring:
        description_parts.append(symbol.docstring[:200])
    description_parts.append(f"{language.capitalize()} | {file_path}:{symbol.line_start}-{symbol.line_end}")

    entity_data: dict[str, Any] = {
        # LightRAG standard fields (per API convention)
        "entity_type": symbol.kind,
        "description": " | ".join(description_parts),
        "source_id": f"{file_path}:{symbol.line_start}-{symbol.line_end}",
        "file_path": file_path,
        # Note: Do NOT include embedding - let LightRAG auto-generate
    }

    return EntityData(entity_name=entity_name, entity_data=entity_data)


def map_call_to_relation(call: Call, file_path: str) -> RelationData:
    """Map codeindex Call to LightRAG relation data.

    **LightRAG Convention**:
    - keywords: Use for relation_type (e.g., "CALLS")
    - description: Human-readable relation context

    Args:
        call: Call relationship from codeindex ParseResult
        file_path: Path to the source file

    Returns:
        RelationData ready for LightRAG acreate_relation()

    Example:
        >>> call = Call(
        ...     caller="UserService.login",
        ...     callee="db.find_user",
        ...     line=15,
        ...     is_method=True
        ... )
        >>> rel = map_call_to_relation(call, "src/auth/service.py")
        >>> rel.src_id
        'UserService.login'
        >>> rel.edge_data["keywords"]
        'CALLS'
    """
    edge_data: dict[str, Any] = {
        # LightRAG convention: use keywords for relation_type
        "keywords": "CALLS",
        "description": f"{call.caller} calls {call.callee} at line {call.line}",
        "weight": 1.0,
        "source_id": f"{file_path}:{call.line}",
    }

    return RelationData(src_id=call.caller, tgt_id=call.callee, edge_data=edge_data)


def map_inheritance_to_relation(inh: Inheritance, file_path: str) -> RelationData:
    """Map codeindex Inheritance to LightRAG relation data.

    **LightRAG Convention**:
    - keywords: Use for relation_type (e.g., "INHERITS")
    - description: Human-readable relation context

    Args:
        inh: Inheritance relationship from codeindex ParseResult
        file_path: Path to the source file

    Returns:
        RelationData ready for LightRAG acreate_relation()

    Example:
        >>> inh = Inheritance(child="UserService", parent="BaseService")
        >>> rel = map_inheritance_to_relation(inh, "src/auth/service.py")
        >>> rel.src_id
        'UserService'
        >>> rel.edge_data["keywords"]
        'INHERITS'
    """
    edge_data: dict[str, Any] = {
        # LightRAG convention: use keywords for relation_type
        "keywords": "INHERITS",
        "description": f"{inh.child} inherits from {inh.parent}",
        "weight": 1.0,
        "source_id": file_path,
    }

    return RelationData(src_id=inh.child, tgt_id=inh.parent, edge_data=edge_data)


def map_import_to_relation(
    imp: Import,
    importer_name: str,
    file_path: str,
) -> list[RelationData]:
    """Map codeindex Import to LightRAG relation data.

    Creates IMPORTS relations from the importing module/file to the imported module.

    **LightRAG Convention**:
    - keywords: Use for relation_type (e.g., "IMPORTS")
    - description: Human-readable import statement

    Args:
        imp: Import statement from codeindex ParseResult
        importer_name: Name of the importing entity (usually module name)
        file_path: Path to the source file

    Returns:
        List of RelationData (one per imported name, or one for the module)

    Example:
        >>> imp = Import(module="os.path", alias=None, names=["join", "exists"])
        >>> rels = map_import_to_relation(imp, "src.utils", "src/utils.py")
        >>> len(rels)
        2
        >>> rels[0].edge_data["keywords"]
        'IMPORTS'
    """
    relations: list[RelationData] = []

    if imp.names:
        # from X import a, b, c
        for name in imp.names:
            target = f"{imp.module}.{name}"
            alias_str = f" as {imp.alias}" if imp.alias else ""
            edge_data: dict[str, Any] = {
                # LightRAG convention: use keywords for relation_type
                "keywords": "IMPORTS",
                "description": f"from {imp.module} import {name}{alias_str}",
                "weight": 1.0,
                "source_id": file_path,
            }
            relations.append(RelationData(src_id=importer_name, tgt_id=target, edge_data=edge_data))
    else:
        # import X or import X as Y
        alias_str = f" as {imp.alias}" if imp.alias else ""
        edge_data = {
            # LightRAG convention: use keywords for relation_type
            "keywords": "IMPORTS",
            "description": f"import {imp.module}{alias_str}",
            "weight": 1.0,
            "source_id": file_path,
        }
        relations.append(RelationData(src_id=importer_name, tgt_id=imp.module, edge_data=edge_data))

    return relations
