"""
LoomGraph: Enterprise Code Intelligence Engine

A high-performance code understanding and retrieval system optimized for
NVIDIA H200, combining LightRAG graph technology with Jina Code V2 embeddings.

Usage:
    from loomgraph import Settings, index_repository
    from loomgraph.embedding import JinaEmbeddingClient

    settings = Settings()
    embedding_client = JinaEmbeddingClient(settings.embedding)
    result = await index_repository(repo_path, rag, embedding_client, parse_file)
"""

__version__ = "0.2.1"
__author__ = "DreamLinx"

from loomgraph.core.config import Settings, get_settings
from loomgraph.core.indexer import index_file, index_repository, scan_code_files
from loomgraph.core.injector import inject_parse_result
from loomgraph.core.models import IndexResult, InjectResult, ParseResult

__all__ = [
    # Version
    "__version__",
    # Config
    "Settings",
    "get_settings",
    # Indexing
    "scan_code_files",
    "index_repository",
    "index_file",
    "inject_parse_result",
    # Models
    "ParseResult",
    "InjectResult",
    "IndexResult",
]
