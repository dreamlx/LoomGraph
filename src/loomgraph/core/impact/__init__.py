"""Impact analysis module for LoomGraph.

This module provides tools for analyzing the impact of code changes
by combining git diff parsing with knowledge graph queries.
"""

from loomgraph.core.impact.models import (
    ChangeType,
    ChangedFile,
    ChangedSymbol,
    Caller,
    ImpactResult,
    RiskAssessment,
)
from loomgraph.core.impact.git_parser import GitDiffParser
from loomgraph.core.impact.extractor import ChangedSymbolExtractor
from loomgraph.core.impact.analyzer import ImpactAnalyzer
from loomgraph.core.impact.risk import RiskAssessor

__all__ = [
    # Models
    "ChangeType",
    "ChangedFile",
    "ChangedSymbol",
    "Caller",
    "ImpactResult",
    "RiskAssessment",
    # Classes
    "GitDiffParser",
    "ChangedSymbolExtractor",
    "ImpactAnalyzer",
    "RiskAssessor",
]
