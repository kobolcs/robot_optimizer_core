# src/robot_optimizer_core/infrastructure/json_test_result_repository.py
"""JSON file-backed TestResultRepository implementation."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path

from ..domain.repositories import TestResultRepository
from ..domain.value_objects.flakiness_stats import FlakinessStats
from ..domain.value_objects.test_result import TestResult
from ..exceptions import RepositoryError
from ..logging import get_logger

__all__ = ["JsonTestResultRepository"]

logger = get_logger(__name__)


def _parse_ts(value: str | float | None) -> datetime:
    """Parse an ISO-8601 string into a timezone-aware datetime.

    Raises ValueError for None or non-ISO values so callers can skip the record.
    """
    if not isinstance(value, str):
        raise ValueError(f"Expected ISO-8601 string for timestamp, got {value!r}")
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


# Each line in the file is one JSON object (newline-delimited JSON).
# Schema: {"test_name": str, "file_path": str, "status": str,
#          "execution_time": float, "error_message": str|null,
#          "timestamp": str (ISO-8601)}


class JsonTestResultRepository(TestResultRepository):
    """Persists test results as newline-delimited JSON.

    Thread-safe for concurrent saves; reads acquire the same lock so a
    write in progress is never partially observed.

    Args:
        storage_path: Path to the .jsonl file.  Created on first save.
    """

    def __init__(self, storage_path: Path | str = Path("test_results.jsonl")) -> None:
        self._path = Path(storage_path)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # TestResultRepository interface
    # ------------------------------------------------------------------

    def save_result(self, result: TestResult) -> None:
        """Append one result record to the storage file."""
        record = {
            "test_name": result.test_name,
            "file_path": str(result.file_path),
            "status": result.status,
            "execution_time": result.execution_time,
            "error_message": result.error_message,
            "timestamp": result.timestamp.isoformat(),
        }
        try:
            with self._lock:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with self._path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(record) + "\n")
        except OSError as exc:
            raise RepositoryError(
                f"Failed to save test result to {self._path}: {exc}"
            ) from exc

    def get_results_for_file(
        self, file_path: Path, days_back: int = 30
    ) -> list[TestResult]:
        """Return all results for *file_path* within the last *days_back* days."""
        cutoff = self._cutoff(days_back)
        results: list[TestResult] = []
        for record in self._read_records():
            try:
                record_path = Path(str(record["file_path"]))
                if record_path != file_path:
                    continue
                ts = _parse_ts(record["timestamp"])
                if ts < cutoff:
                    continue
                err = record.get("error_message")
                results.append(
                    TestResult(
                        test_name=str(record["test_name"]),
                        file_path=record_path,
                        status=str(record["status"]),
                        execution_time=float(record["execution_time"] or 0.0),
                        error_message=str(err) if err is not None else None,
                        timestamp=ts,
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning(
                    "Skipping invalid test result record",
                    extra={"record": record, "error": str(exc)},
                )
        return results

    def get_flakiness_stats(
        self, file_path: Path, days_back: int = 30
    ) -> list[FlakinessStats]:
        """Aggregate per-test flakiness stats for *file_path*."""
        results = self.get_results_for_file(file_path, days_back)

        # Group by test name
        totals: dict[str, int] = {}
        failures: dict[str, int] = {}
        last_failure: dict[str, datetime] = {}

        for r in results:
            totals[r.test_name] = totals.get(r.test_name, 0) + 1
            if r.is_failure:
                failures[r.test_name] = failures.get(r.test_name, 0) + 1
                prev = last_failure.get(r.test_name)
                if prev is None or r.timestamp > prev:
                    last_failure[r.test_name] = r.timestamp

        return [
            FlakinessStats(
                test_name=name,
                file_path=file_path,
                total_runs=totals[name],
                failures=failures.get(name, 0),
                last_failure=last_failure.get(name),
            )
            for name in totals
        ]

    def get_total_results_count(self) -> int:
        """Return the total number of stored records."""
        return sum(1 for _ in self._read_records())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_records(self) -> list[dict[str, str | float | None]]:
        """Read all valid JSON records from storage (returns empty list if file absent)."""
        if not self._path.exists():
            return []
        records: list[dict[str, str | float | None]] = []
        try:
            with self._lock:
                lines = self._path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise RepositoryError(
                f"Failed to read test results from {self._path}: {exc}"
            ) from exc
        for lineno, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                logger.warning(
                    "Skipping malformed JSON record",
                    extra={"path": str(self._path), "line": lineno},
                )
                continue
            if not isinstance(parsed, dict):
                logger.warning(
                    "Skipping non-object JSON record",
                    extra={"path": str(self._path), "line": lineno},
                )
                continue
            records.append(parsed)
        return records

    @staticmethod
    def _cutoff(days_back: int) -> datetime:
        from datetime import timedelta

        return datetime.now(tz=UTC) - timedelta(days=days_back)
