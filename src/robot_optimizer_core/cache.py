# src/robot_optimizer_core/cache.py
"""SHA-256 content-addressed cache for per-file analysis results.

Cache entries are keyed by ``{absolute_path}#{sha256_hex}`` and stored in
``~/.cache/robot-optimizer/cache.json``.  The cache is intentionally simple:
it is loaded once at the start of a directory analysis run, consulted for each
discovered file, and flushed once at the end.  All reads happen before the
parallel thread-pool is started, and all writes happen after it finishes, so no
locking is required.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .domain.value_objects import Finding

logger = logging.getLogger(__name__)

_DEFAULT_CACHE_DIR = Path.home() / ".cache" / "robot-optimizer"
_CACHE_FILENAME = "cache.json"


def _get_package_version() -> str:
    """Return the installed package version used as part of the cache key."""
    try:
        return importlib.metadata.version("robot-framework-optimizer-core")
    except importlib.metadata.PackageNotFoundError:
        return "dev"


def _finding_to_dict(f: Finding) -> dict[str, Any]:
    """Serialize a Finding to a JSON-safe dict for cache storage."""
    return {
        "severity": f.severity.value,
        "message": f.message,
        "context": f.context,
        "location": {
            "file_path": str(f.location.file_path),
            "line": f.location.line,
            "column": f.location.column,
            "end_line": f.location.end_line,
            "end_column": f.location.end_column,
        },
        "pattern": {
            "type": f.pattern.type.value,
            "name": f.pattern.name,
            "description": f.pattern.description,
            "recommendation": f.pattern.recommendation,
            "documentation_url": f.pattern.documentation_url,
            "auto_fixable": f.pattern.auto_fixable,
        },
    }


def _finding_from_dict(d: dict[str, Any]) -> Finding:
    """Reconstruct a Finding from a cache dict."""
    from .domain.value_objects import Finding

    return Finding.model_validate(
        {
            "severity": d["severity"],
            "message": d["message"],
            "context": d.get("context"),
            "location": d["location"],
            "pattern": d["pattern"],
        }
    )


_DEFAULT_MAX_CACHE_ENTRIES = 10_000


class AnalysisCache:
    """Persistent SHA-256 content-addressed cache for per-file analysis results.

    Usage::

        cache = AnalysisCache()
        file_hash = cache.file_hash(path)
        cached = cache.get(path, file_hash)
        if cached is None:
            findings = run_analysis(path)
            cache.put(path, file_hash, findings)
        cache.flush()       # write to disk once when done
    """

    def __init__(
        self,
        cache_dir: Path | None = None,
        max_entries: int = _DEFAULT_MAX_CACHE_ENTRIES,
    ) -> None:
        self._cache_dir = cache_dir or _DEFAULT_CACHE_DIR
        self._cache_path = self._cache_dir / _CACHE_FILENAME
        self._data: dict[str, list[dict[str, Any]]] | None = None
        self._dirty = False
        self._max_entries = max_entries
        # Include the package version so cache entries are automatically
        # invalidated when the package is upgraded (new analyzer logic).
        self._version_key = _get_package_version()

    @property
    def path(self) -> Path:
        """Path to the on-disk cache file."""
        return self._cache_path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> dict[str, list[dict[str, Any]]]:
        if self._data is None:
            if self._cache_path.exists():
                try:
                    raw = self._cache_path.read_text(encoding="utf-8")
                    self._data = json.loads(raw)
                    if not isinstance(self._data, dict):
                        logger.debug("Cache file has unexpected format; starting fresh")
                        self._data = {}
                except Exception:
                    logger.debug("Cache file unreadable; starting fresh", exc_info=True)
                    self._data = {}
            else:
                self._data = {}
        return self._data

    def _cache_key(self, file_path: Path, file_hash: str) -> str:
        return f"{file_path.resolve()}#{file_hash}#{self._version_key}"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def file_hash(file_path: Path) -> str:
        """Return the SHA-256 hex digest of *file_path*'s contents."""
        h = hashlib.sha256()
        h.update(file_path.read_bytes())
        return h.hexdigest()

    def get(self, file_path: Path, file_hash: str) -> list[Finding] | None:
        """Return cached findings for *file_path* or ``None`` on a miss.

        Returns ``None`` when the entry is absent or cannot be deserialised.
        """
        data = self._load()
        key = self._cache_key(file_path, file_hash)
        raw = data.get(key)
        if raw is None:
            return None
        try:
            return [_finding_from_dict(d) for d in raw]
        except Exception:
            logger.debug(
                "Cache entry invalid for %s; treating as miss", file_path, exc_info=True
            )
            return None

    def put(
        self, file_path: Path, file_hash: str, findings: list[Finding]
    ) -> None:
        """Store *findings* for *file_path* in the in-memory cache.

        Evicts the oldest entry when the in-memory cap is reached.
        Call :meth:`flush` once when the analysis run is complete to persist.
        """
        data = self._load()
        key = self._cache_key(file_path, file_hash)
        if key not in data and len(data) >= self._max_entries:
            # Remove the oldest key (insertion-order is preserved in Python 3.7+)
            data.pop(next(iter(data)))
        data[key] = [_finding_to_dict(f) for f in findings]
        self._dirty = True

    def flush(self) -> None:
        """Persist the in-memory cache to disk if any entries were added."""
        if not self._dirty:
            return
        data = self._load()
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_text(
                json.dumps(data, separators=(",", ":")),
                encoding="utf-8",
            )
            self._dirty = False
        except OSError:
            logger.debug("Failed to write cache to %s", self._cache_path, exc_info=True)

    def clear(self) -> None:
        """Remove all cached entries from memory and disk."""
        self._data = {}
        self._dirty = False
        if self._cache_path.exists():
            try:
                self._cache_path.unlink()
            except OSError:
                logger.debug(
                    "Failed to remove cache file %s", self._cache_path, exc_info=True
                )
