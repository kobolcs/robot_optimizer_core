# src/robot_optimizer/infrastructure/repositories/batch_repository.py
"""Batch operations for performance."""
from typing import List, Dict, Any
import sqlite3
from contextlib import contextmanager

from ...domain.value_objects.test_result import TestResult
from ...domain.entities import Analysis


class BatchOperationMixin:
    """Mixin for batch database operations."""
    
    @contextmanager
    def batch_transaction(self):
        """Context manager for batch operations."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")  # Write-ahead logging
        conn.execute("PRAGMA synchronous=NORMAL")  # Faster writes
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def save_results_batch(self, results: List[TestResult]) -> None:
        """Bulk insert test results."""
        with self.batch_transaction() as conn:
            conn.executemany(
                """INSERT INTO test_results 
                   (test_name, file_path, status, execution_time, error_message, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [(r.test_name, str(r.file_path), r.status, r.execution_time, 
                  r.error_message, r.timestamp.isoformat()) for r in results]
            )
    
    def save_analyses_batch(self, analyses: List[Analysis]) -> None:
        """Bulk save analysis summaries."""
        summaries = [a.to_summary_dict() for a in analyses]
        
        with self.batch_transaction() as conn:
            conn.executemany(
                """INSERT OR REPLACE INTO analysis_summaries 
                   (id, file_path, started_at, completed_at, duration_seconds,
                    finding_count, error_count, warning_count, info_count,
                    auto_fixable_count, pattern_summary)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [(s['id'], s['file'], s['started_at'], s['completed_at'],
                  s['duration_seconds'], s['finding_count'], s['error_count'],
                  s['warning_count'], s['info_count'], s['auto_fixable_count'],
                  json.dumps(s['pattern_summary'])) for s in summaries]
            )


# Result type for better error handling
from typing import Union, Generic, TypeVar
from dataclasses import dataclass

T = TypeVar('T')


@dataclass
class Success(Generic[T]):
    """Successful result wrapper."""
    value: T


@dataclass
class Failure:
    """Failure result wrapper."""
    error: str
    exception: Optional[Exception] = None


Result = Union[Success[T], Failure]


def safe_analyze(file_path: Path) -> Result[Analysis]:
    """Safely analyze a file with error handling."""
    try:
        test_file = TestFile.from_path(file_path)
        analysis = analyze_file_use_case.execute(test_file)
        return Success(analysis)
    except FileNotFoundError as e:
        return Failure(f"File not found: {file_path}", e)
    except Exception as e:
        return Failure(f"Analysis failed: {str(e)}", e)