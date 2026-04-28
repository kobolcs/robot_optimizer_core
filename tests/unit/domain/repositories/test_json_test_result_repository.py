# tests/unit/domain/repositories/test_json_test_result_repository.py
"""Tests for JsonTestResultRepository."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from robot_optimizer_core.domain.value_objects.test_result import TestResult
from robot_optimizer_core.exceptions import RepositoryError
from robot_optimizer_core.repositories import JsonTestResultRepository


def _ts(days_ago: float = 0) -> datetime:
    return datetime.now(tz=timezone.utc) - timedelta(days=days_ago)


def _result(
    name: str = "My Test",
    file_path: Path = Path("suite.robot"),
    status: str = "PASS",
    days_ago: float = 0,
    error: str | None = None,
) -> TestResult:
    return TestResult(
        test_name=name,
        file_path=file_path,
        status=status,
        execution_time=1.0,
        error_message=error,
        timestamp=_ts(days_ago),
    )


# ---------------------------------------------------------------------------
# save_result / get_total_results_count
# ---------------------------------------------------------------------------


class TestSaveResult:
    def test_creates_file_on_first_save(self, tmp_path: Path) -> None:
        repo = JsonTestResultRepository(tmp_path / "results.jsonl")
        repo.save_result(_result())
        assert (tmp_path / "results.jsonl").exists()

    def test_appends_newline_delimited_json(self, tmp_path: Path) -> None:
        path = tmp_path / "results.jsonl"
        repo = JsonTestResultRepository(path)
        repo.save_result(_result("T1"))
        repo.save_result(_result("T2"))
        lines = path.read_text().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["test_name"] == "T1"
        assert json.loads(lines[1])["test_name"] == "T2"

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        repo = JsonTestResultRepository(tmp_path / "nested" / "dir" / "r.jsonl")
        repo.save_result(_result())
        assert (tmp_path / "nested" / "dir" / "r.jsonl").exists()

    def test_get_total_results_count(self, tmp_path: Path) -> None:
        repo = JsonTestResultRepository(tmp_path / "r.jsonl")
        assert repo.get_total_results_count() == 0
        repo.save_result(_result())
        repo.save_result(_result())
        assert repo.get_total_results_count() == 2

    def test_save_raises_repository_error_on_bad_path(self) -> None:
        repo = JsonTestResultRepository(Path("/no_permission/results.jsonl"))
        with pytest.raises(RepositoryError):
            repo.save_result(_result())

    def test_serialises_all_fields(self, tmp_path: Path) -> None:
        path = tmp_path / "r.jsonl"
        repo = JsonTestResultRepository(path)
        r = _result("T", Path("a.robot"), "FAIL", error="boom")
        repo.save_result(r)
        record = json.loads(path.read_text())
        assert record["status"] == "FAIL"
        assert record["error_message"] == "boom"
        assert record["file_path"] == "a.robot"


# ---------------------------------------------------------------------------
# get_results_for_file
# ---------------------------------------------------------------------------


class TestGetResultsForFile:
    def test_returns_empty_when_file_absent(self, tmp_path: Path) -> None:
        repo = JsonTestResultRepository(tmp_path / "missing.jsonl")
        assert repo.get_results_for_file(Path("suite.robot")) == []

    def test_filters_by_file_path(self, tmp_path: Path) -> None:
        repo = JsonTestResultRepository(tmp_path / "r.jsonl")
        repo.save_result(_result(file_path=Path("a.robot")))
        repo.save_result(_result(file_path=Path("b.robot")))
        results = repo.get_results_for_file(Path("a.robot"))
        assert len(results) == 1
        assert results[0].file_path == Path("a.robot")

    def test_filters_by_days_back(self, tmp_path: Path) -> None:
        repo = JsonTestResultRepository(tmp_path / "r.jsonl")
        repo.save_result(_result(days_ago=5))
        repo.save_result(_result(days_ago=40))  # outside 30-day window
        results = repo.get_results_for_file(Path("suite.robot"), days_back=30)
        assert len(results) == 1

    def test_returns_testresult_objects(self, tmp_path: Path) -> None:
        repo = JsonTestResultRepository(tmp_path / "r.jsonl")
        repo.save_result(_result("TC1", status="FAIL", error="err"))
        results = repo.get_results_for_file(Path("suite.robot"))
        assert isinstance(results[0], TestResult)
        assert results[0].test_name == "TC1"
        assert results[0].is_failure

    def test_skips_malformed_lines(self, tmp_path: Path) -> None:
        path = tmp_path / "r.jsonl"
        repo = JsonTestResultRepository(path)
        repo.save_result(_result("Good"))
        with path.open("a") as fh:
            fh.write("NOT JSON\n")
        results = repo.get_results_for_file(Path("suite.robot"))
        assert len(results) == 1

    def test_naive_timestamps_treated_as_utc(self, tmp_path: Path) -> None:
        path = tmp_path / "r.jsonl"
        naive_ts = datetime.now().isoformat()  # no tzinfo
        record = {
            "test_name": "T",
            "file_path": "suite.robot",
            "status": "PASS",
            "execution_time": 1.0,
            "error_message": None,
            "timestamp": naive_ts,
        }
        path.write_text(json.dumps(record) + "\n")
        repo = JsonTestResultRepository(path)
        results = repo.get_results_for_file(Path("suite.robot"), days_back=1)
        assert len(results) == 1


# ---------------------------------------------------------------------------
# get_flakiness_stats
# ---------------------------------------------------------------------------


class TestGetFlakinessStats:
    def test_empty_when_no_results(self, tmp_path: Path) -> None:
        repo = JsonTestResultRepository(tmp_path / "r.jsonl")
        assert repo.get_flakiness_stats(Path("suite.robot")) == []

    def test_aggregates_pass_and_fail(self, tmp_path: Path) -> None:
        repo = JsonTestResultRepository(tmp_path / "r.jsonl")
        for _ in range(3):
            repo.save_result(_result("Flaky", status="PASS"))
        repo.save_result(_result("Flaky", status="FAIL"))
        stats_list = repo.get_flakiness_stats(Path("suite.robot"))
        assert len(stats_list) == 1
        s = stats_list[0]
        assert s.total_runs == 4
        assert s.failures == 1
        assert s.failure_rate == pytest.approx(0.25)

    def test_separate_stats_per_test_name(self, tmp_path: Path) -> None:
        repo = JsonTestResultRepository(tmp_path / "r.jsonl")
        repo.save_result(_result("A", status="PASS"))
        repo.save_result(_result("B", status="FAIL"))
        stats = {s.test_name: s for s in repo.get_flakiness_stats(Path("suite.robot"))}
        assert stats["A"].failures == 0
        assert stats["B"].failures == 1

    def test_last_failure_is_most_recent(self, tmp_path: Path) -> None:
        repo = JsonTestResultRepository(tmp_path / "r.jsonl")
        repo.save_result(_result("T", status="FAIL", days_ago=10))
        repo.save_result(_result("T", status="FAIL", days_ago=2))
        repo.save_result(_result("T", status="PASS"))
        stats = repo.get_flakiness_stats(Path("suite.robot"))[0]
        assert stats.last_failure is not None
        assert stats.last_failure > _ts(days_ago=5)  # closer to "now" than 5 days ago

    def test_only_counts_within_days_back(self, tmp_path: Path) -> None:
        repo = JsonTestResultRepository(tmp_path / "r.jsonl")
        repo.save_result(_result("T", status="FAIL", days_ago=45))  # outside window
        stats = repo.get_flakiness_stats(Path("suite.robot"), days_back=30)
        assert stats == []


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


class TestThreadSafety:
    def test_concurrent_saves_all_persisted(self, tmp_path: Path) -> None:
        repo = JsonTestResultRepository(tmp_path / "r.jsonl")
        errors: list[Exception] = []

        def save_many() -> None:
            try:
                for _ in range(50):
                    repo.save_result(_result())
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=save_many) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert repo.get_total_results_count() == 200
