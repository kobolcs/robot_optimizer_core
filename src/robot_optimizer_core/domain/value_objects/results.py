# src/robot_optimizer_core/domain/value_objects/results.py
"""Typed result envelopes for file and directory analysis."""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from .finding import Finding

__all__ = ["AnalysisMeta", "FileAnalysisResult"]

RESULT_SCHEMA_VERSION = "1"


@dataclasses.dataclass(frozen=True, slots=True)
class AnalysisMeta:
    """Immutable metadata attached to every result envelope.

    Attributes:
        schema_version: Version of the result schema; increment only on
            incompatible serialisation changes.
        duration_ms: Wall-clock time for the analysis in milliseconds.
        analyzer_names: Names of analyzers that were run.
        cache_hits: Number of files served from the cache.
        cache_misses: Number of files that required full analysis.
    """

    schema_version: str = RESULT_SCHEMA_VERSION
    duration_ms: float = 0.0
    analyzer_names: tuple[str, ...] = ()
    cache_hits: int = 0
    cache_misses: int = 0


@dataclasses.dataclass(slots=True)
class FileAnalysisResult:
    """Result envelope for a single-file analysis.

    Replaces the bare ``list[Finding]`` returned by ``analyze_file`` in
    previous versions.  The class is iterable and has ``__len__`` so
    existing ``for finding in result`` and ``len(result)`` call-sites
    continue to work without modification.

    Attributes:
        file_path: The file that was analysed.
        findings: All findings produced for the file.
        meta: Timing and cache metadata for the analysis run.
    """

    file_path: Path
    findings: list[Finding] = dataclasses.field(default_factory=list)
    meta: AnalysisMeta = dataclasses.field(default_factory=AnalysisMeta)

    # Sequence-like helpers so code written against the old list[Finding]
    # continues to work without changes.
    def __iter__(self) -> Iterator[Finding]:
        return iter(self.findings)

    def __len__(self) -> int:
        return len(self.findings)

    def __bool__(self) -> bool:
        return bool(self.findings)
