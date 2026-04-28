# tests/unit/test_listener.py
"""Unit tests for FlakinessListener (Robot Framework Listener V3)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from robot_optimizer_core.domain.repositories import TestResultRepository
from robot_optimizer_core.domain.value_objects import TestResult
from robot_optimizer_core.listener import FlakinessListener


class _FakeRepo(TestResultRepository):
    """In-memory repo for testing."""

    def __init__(self) -> None:
        self.saved: list[TestResult] = []

    def save_result(self, result: TestResult) -> None:
        self.saved.append(result)

    def get_results_for_file(self, file_path: Path, days_back: int = 30) -> list[TestResult]:
        return []

    def get_flakiness_stats(self, file_path: Path, days_back: int = 30):  # type: ignore[override]
        return []

    def get_total_results_count(self) -> int:
        return len(self.saved)


def _fake_test_data(name: str = "My Test", source: str = "tests/login.robot") -> MagicMock:
    data = MagicMock()
    data.name = name
    data.source = source
    data.parent = MagicMock()
    data.parent.source = source
    return data


def _fake_result(status: str = "PASS", elapsed_seconds: float = 1.5, message: str = "") -> MagicMock:
    result = MagicMock()
    result.status = status
    result.elapsed_time = timedelta(seconds=elapsed_seconds)
    result.message = message
    return result


@pytest.mark.unit
class TestFlakinessListenerAPIVersion:
    def test_api_version_is_3(self) -> None:
        assert FlakinessListener.ROBOT_LISTENER_API_VERSION == 3


@pytest.mark.unit
class TestFlakinessListenerEndTest:
    def test_passing_test_saved(self) -> None:
        repo = _FakeRepo()
        listener = FlakinessListener(repository=repo)
        listener.end_test(_fake_test_data(), _fake_result("PASS"))
        assert len(repo.saved) == 1
        assert repo.saved[0].status == "PASS"

    def test_failing_test_saved(self) -> None:
        repo = _FakeRepo()
        listener = FlakinessListener(repository=repo)
        listener.end_test(_fake_test_data(), _fake_result("FAIL", message="Assertion failed"))
        assert repo.saved[0].status == "FAIL"
        assert repo.saved[0].error_message == "Assertion failed"

    def test_test_name_stored(self) -> None:
        repo = _FakeRepo()
        listener = FlakinessListener(repository=repo)
        listener.end_test(_fake_test_data(name="Login Works"), _fake_result())
        assert repo.saved[0].test_name == "Login Works"

    def test_file_path_taken_from_data_source(self) -> None:
        repo = _FakeRepo()
        listener = FlakinessListener(repository=repo)
        listener.end_test(_fake_test_data(source="suite/login.robot"), _fake_result())
        assert repo.saved[0].file_path == Path("suite/login.robot")

    def test_execution_time_stored_from_timedelta(self) -> None:
        repo = _FakeRepo()
        listener = FlakinessListener(repository=repo)
        listener.end_test(_fake_test_data(), _fake_result(elapsed_seconds=3.5))
        assert abs(repo.saved[0].execution_time - 3.5) < 0.001

    def test_execution_time_stored_from_float(self) -> None:
        repo = _FakeRepo()
        listener = FlakinessListener(repository=repo)
        result = _fake_result()
        result.elapsed_time = 2.0
        listener.end_test(_fake_test_data(), result)
        assert abs(repo.saved[0].execution_time - 2.0) < 0.001

    def test_timestamp_is_timezone_aware(self) -> None:
        repo = _FakeRepo()
        listener = FlakinessListener(repository=repo)
        listener.end_test(_fake_test_data(), _fake_result())
        assert repo.saved[0].timestamp.tzinfo is not None

    def test_invalid_status_normalised_to_fail(self) -> None:
        repo = _FakeRepo()
        listener = FlakinessListener(repository=repo)
        result = _fake_result()
        result.status = "NOT_A_REAL_STATUS"
        listener.end_test(_fake_test_data(), result)
        assert repo.saved[0].status == "FAIL"

    def test_error_in_save_does_not_propagate(self) -> None:
        bad_repo = MagicMock(spec=TestResultRepository)
        bad_repo.save_result.side_effect = RuntimeError("disk full")
        listener = FlakinessListener(repository=bad_repo)
        listener.end_test(_fake_test_data(), _fake_result())  # must not raise

    def test_skip_status_saved(self) -> None:
        repo = _FakeRepo()
        listener = FlakinessListener(repository=repo)
        listener.end_test(_fake_test_data(), _fake_result("SKIP"))
        assert repo.saved[0].status == "SKIP"


@pytest.mark.unit
class TestFlakinessListenerStartSuite:
    def test_start_suite_sets_current_source(self) -> None:
        repo = _FakeRepo()
        listener = FlakinessListener(repository=repo)
        suite_data = MagicMock()
        suite_data.source = "suites/login.robot"
        listener.start_suite(suite_data, MagicMock())
        assert listener._current_source == Path("suites/login.robot")

    def test_source_falls_back_to_current_source_when_data_has_no_source(self) -> None:
        repo = _FakeRepo()
        listener = FlakinessListener(repository=repo)
        suite_data = MagicMock()
        suite_data.source = "suites/login.robot"
        listener.start_suite(suite_data, MagicMock())

        test_data = MagicMock()
        test_data.name = "T"
        test_data.source = None
        test_data.parent = MagicMock()
        test_data.parent.source = None
        listener.end_test(test_data, _fake_result())
        assert repo.saved[0].file_path == Path("suites/login.robot")

    def test_start_suite_without_source_attribute(self) -> None:
        repo = _FakeRepo()
        listener = FlakinessListener(repository=repo)
        suite_data = MagicMock(spec=[])  # no attributes
        listener.start_suite(suite_data, MagicMock())  # must not raise
