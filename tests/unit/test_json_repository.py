# tests/unit/test_json_repository.py
"""Unit tests for JsonTestResultRepository."""

from __future__ import annotations

import json
import unittest.mock as mock
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from robot_optimizer_core.domain.value_objects.test_result import TestResult
from robot_optimizer_core.exceptions import RepositoryError
from robot_optimizer_core.repositories.json_test_result_repository import (
    JsonTestResultRepository,
    _parse_ts,
)


@pytest.mark.unit
class TestParseTsFunction:
    def test_parses_iso_string(self) -> None:
        ts = _parse_ts("2024-01-15T10:00:00+00:00")
        assert ts.year == 2024

    def test_adds_utc_when_naive(self) -> None:
        ts = _parse_ts("2024-01-15T10:00:00")
        assert ts.tzinfo is not None

    def test_raises_for_non_string(self) -> None:
        with pytest.raises(ValueError):
            _parse_ts(12345)  # type: ignore[arg-type]

    def test_raises_for_none(self) -> None:
        with pytest.raises(ValueError):
            _parse_ts(None)  # type: ignore[arg-type]


@pytest.mark.unit
class TestJsonTestResultRepository:
    @pytest.fixture
    def repo(self, tmp_path: Path) -> JsonTestResultRepository:
        return JsonTestResultRepository(tmp_path / "results.jsonl")

    @pytest.fixture
    def result(self) -> TestResult:
        return TestResult(
            test_name="Login Test",
            file_path=Path("tests/login.robot"),
            status="FAIL",
            execution_time=1.5,
            error_message="Assertion failed",
            timestamp=datetime.now(tz=UTC),
        )

    def test_save_and_retrieve(
        self, repo: JsonTestResultRepository, result: TestResult
    ) -> None:
        repo.save_result(result)
        results = repo.get_results_for_file(Path("tests/login.robot"))
        assert len(results) == 1
        assert results[0].test_name == "Login Test"

    def test_get_results_returns_empty_when_no_file(
        self, repo: JsonTestResultRepository
    ) -> None:
        results = repo.get_results_for_file(Path("nonexistent.robot"))
        assert results == []

    def test_get_total_results_count(
        self, repo: JsonTestResultRepository, result: TestResult
    ) -> None:
        repo.save_result(result)
        repo.save_result(result)
        assert repo.get_total_results_count() == 2

    def test_skips_records_with_missing_key(
        self, repo: JsonTestResultRepository
    ) -> None:
        path = repo._path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"test_name": "x"}\n', encoding="utf-8")
        results = repo.get_results_for_file(Path("x.robot"))
        assert results == []

    def test_skips_malformed_json(self, repo: JsonTestResultRepository) -> None:
        path = repo._path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not json\n", encoding="utf-8")
        results = repo.get_results_for_file(Path("x.robot"))
        assert results == []

    def test_skips_empty_lines(self, repo: JsonTestResultRepository) -> None:
        path = repo._path
        path.parent.mkdir(parents=True, exist_ok=True)
        valid = {
            "test_name": "T",
            "file_path": "x.robot",
            "status": "PASS",
            "execution_time": 0.1,
            "error_message": None,
            "timestamp": datetime.now(tz=UTC).isoformat(),
        }
        path.write_text(f"\n{json.dumps(valid)}\n\n", encoding="utf-8")
        results = repo.get_results_for_file(Path("x.robot"))
        assert len(results) == 1

    def test_skips_non_object_json(self, repo: JsonTestResultRepository) -> None:
        path = repo._path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[1, 2, 3]\n", encoding="utf-8")
        results = repo.get_results_for_file(Path("x.robot"))
        assert results == []

    def test_read_records_raises_on_oserror(
        self, repo: JsonTestResultRepository
    ) -> None:
        path = repo._path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        with mock.patch.object(Path, "read_text", side_effect=OSError("disk error")):
            with pytest.raises(RepositoryError, match="disk error"):
                repo._read_records()

    def test_flakiness_stats_with_multiple_failures(
        self, repo: JsonTestResultRepository
    ) -> None:
        now = datetime.now(tz=UTC)
        for i in range(3):
            repo.save_result(
                TestResult(
                    test_name="Flaky",
                    file_path=Path("suite.robot"),
                    status="FAIL",
                    execution_time=0.5,
                    error_message="err",
                    timestamp=now + timedelta(seconds=i),
                )
            )
        stats = repo.get_flakiness_stats(Path("suite.robot"))
        assert len(stats) == 1
        assert stats[0].failures == 3
        assert stats[0].last_failure == now + timedelta(seconds=2)

    def test_save_result_raises_on_oserror(
        self, repo: JsonTestResultRepository, result: TestResult
    ) -> None:
        with mock.patch.object(Path, "open", side_effect=OSError("disk full")):
            with pytest.raises(RepositoryError):
                repo.save_result(result)
