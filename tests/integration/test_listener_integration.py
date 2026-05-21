# tests/integration/test_listener_integration.py
"""Integration tests for FlakinessListener callback sequences.

These tests drive the listener as Robot Framework would: calling start_suite,
end_test, and other protocol methods in realistic sequences, then asserting on
the accumulated repository state.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from robot_optimizer_core.domain.repositories import TestResultRepository
from robot_optimizer_core.domain.value_objects import TestResult
from robot_optimizer_core.listener import FlakinessListener

# ---------------------------------------------------------------------------
# Minimal in-memory repository (same contract as unit tests, no mocking)
# ---------------------------------------------------------------------------


class _InMemoryRepo(TestResultRepository):
    def __init__(self) -> None:
        self.saved: list[TestResult] = []

    def save_result(self, result: TestResult) -> None:
        self.saved.append(result)

    def get_results_for_file(
        self, file_path: Path, days_back: int = 30
    ) -> list[TestResult]:
        return [r for r in self.saved if r.file_path == file_path]

    def get_flakiness_stats(self, file_path: Path, days_back: int = 30):  # type: ignore[override]
        return []

    def get_total_results_count(self) -> int:
        return len(self.saved)


# ---------------------------------------------------------------------------
# Helpers that mimic Robot Framework data/result objects
# ---------------------------------------------------------------------------


def _suite_data(source: str = "tests/suite.robot") -> MagicMock:
    data = MagicMock()
    data.source = source
    return data


def _test_data(
    name: str,
    source: str | None = None,
    parent_source: str | None = None,
) -> MagicMock:
    data = MagicMock()
    data.name = name
    data.source = source
    data.parent = MagicMock()
    data.parent.source = parent_source
    return data


def _test_result(
    status: str = "PASS",
    elapsed_seconds: float = 1.0,
    message: str = "",
) -> MagicMock:
    result = MagicMock()
    result.status = status
    result.elapsed_time = timedelta(seconds=elapsed_seconds)
    result.message = message
    return result


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestNormalPassSequence:
    """Listener correctly records a simple passing test run."""

    def test_single_passing_test_saved(self) -> None:
        repo = _InMemoryRepo()
        listener = FlakinessListener(repository=repo)

        listener.start_suite(_suite_data("tests/smoke.robot"), MagicMock())
        listener.end_test(
            _test_data("Login Works", source="tests/smoke.robot"),
            _test_result("PASS", elapsed_seconds=0.8),
        )

        assert len(repo.saved) == 1
        r = repo.saved[0]
        assert r.test_name == "Login Works"
        assert r.status == "PASS"
        assert abs(r.execution_time - 0.8) < 1e-6
        assert r.file_path == Path("tests/smoke.robot")
        assert r.error_message is None

    def test_multiple_passing_tests_all_saved(self) -> None:
        repo = _InMemoryRepo()
        listener = FlakinessListener(repository=repo)

        listener.start_suite(_suite_data("tests/smoke.robot"), MagicMock())
        for name in ("Test A", "Test B", "Test C"):
            listener.end_test(
                _test_data(name, source="tests/smoke.robot"),
                _test_result("PASS"),
            )

        assert len(repo.saved) == 3
        assert [r.test_name for r in repo.saved] == ["Test A", "Test B", "Test C"]
        assert all(r.status == "PASS" for r in repo.saved)

    def test_timestamps_are_utc_aware(self) -> None:
        repo = _InMemoryRepo()
        listener = FlakinessListener(repository=repo)

        listener.start_suite(_suite_data(), MagicMock())
        listener.end_test(_test_data("T"), _test_result())

        assert repo.saved[0].timestamp.tzinfo is not None


@pytest.mark.integration
class TestNormalFailSequence:
    """Listener correctly records a failing test with error details."""

    def test_failing_test_saved_with_message(self) -> None:
        repo = _InMemoryRepo()
        listener = FlakinessListener(repository=repo)

        listener.start_suite(_suite_data("tests/login.robot"), MagicMock())
        listener.end_test(
            _test_data("Login Fails", source="tests/login.robot"),
            _test_result("FAIL", elapsed_seconds=2.5, message="Element not found"),
        )

        assert len(repo.saved) == 1
        r = repo.saved[0]
        assert r.status == "FAIL"
        assert r.error_message == "Element not found"
        assert abs(r.execution_time - 2.5) < 1e-6

    def test_pass_then_fail_both_recorded(self) -> None:
        repo = _InMemoryRepo()
        listener = FlakinessListener(repository=repo)

        listener.start_suite(_suite_data("tests/login.robot"), MagicMock())
        listener.end_test(
            _test_data("Login Test", source="tests/login.robot"),
            _test_result("PASS", elapsed_seconds=1.0),
        )
        listener.end_test(
            _test_data("Login Test", source="tests/login.robot"),
            _test_result("FAIL", elapsed_seconds=3.0, message="Timeout"),
        )

        assert len(repo.saved) == 2
        assert repo.saved[0].status == "PASS"
        assert repo.saved[1].status == "FAIL"
        assert repo.saved[1].error_message == "Timeout"


@pytest.mark.integration
class TestFlakyPattern:
    """Listener records alternating pass/fail sequences for the same test name."""

    def test_alternating_pass_fail_all_recorded(self) -> None:
        repo = _InMemoryRepo()
        listener = FlakinessListener(repository=repo)
        source = "tests/flaky_suite.robot"

        listener.start_suite(_suite_data(source), MagicMock())
        statuses = ["PASS", "FAIL", "PASS", "FAIL", "PASS"]
        for status in statuses:
            listener.end_test(
                _test_data("Flaky Login", source=source),
                _test_result(status, message="Boom" if status == "FAIL" else ""),
            )

        assert len(repo.saved) == len(statuses)
        assert [r.status for r in repo.saved] == statuses

    def test_flaky_test_results_retrievable_by_file(self) -> None:
        repo = _InMemoryRepo()
        listener = FlakinessListener(repository=repo)
        source = "tests/flaky_suite.robot"
        other = "tests/other_suite.robot"

        listener.start_suite(_suite_data(source), MagicMock())
        listener.end_test(_test_data("Flaky Test", source=source), _test_result("PASS"))
        listener.end_test(_test_data("Flaky Test", source=source), _test_result("FAIL"))

        listener.start_suite(_suite_data(other), MagicMock())
        listener.end_test(_test_data("Stable Test", source=other), _test_result("PASS"))

        flaky_results = repo.get_results_for_file(Path(source))
        assert len(flaky_results) == 2
        assert all(r.file_path == Path(source) for r in flaky_results)

        other_results = repo.get_results_for_file(Path(other))
        assert len(other_results) == 1

    def test_mixed_tests_in_same_suite_independent(self) -> None:
        repo = _InMemoryRepo()
        listener = FlakinessListener(repository=repo)
        source = "tests/mixed.robot"

        listener.start_suite(_suite_data(source), MagicMock())
        listener.end_test(_test_data("Stable", source=source), _test_result("PASS"))
        listener.end_test(_test_data("Flaky", source=source), _test_result("FAIL"))
        listener.end_test(_test_data("Stable", source=source), _test_result("PASS"))
        listener.end_test(_test_data("Flaky", source=source), _test_result("PASS"))

        stable = [r for r in repo.saved if r.test_name == "Stable"]
        flaky = [r for r in repo.saved if r.test_name == "Flaky"]

        assert all(r.status == "PASS" for r in stable)
        assert [r.status for r in flaky] == ["FAIL", "PASS"]


@pytest.mark.integration
class TestSuiteLevelEvents:
    """start_suite context propagates correctly to end_test calls."""

    def test_suite_source_used_when_test_has_no_source(self) -> None:
        repo = _InMemoryRepo()
        listener = FlakinessListener(repository=repo)

        listener.start_suite(_suite_data("suites/auth.robot"), MagicMock())
        # Test data carries no source — listener must fall back to suite source.
        listener.end_test(
            _test_data("Auth Test", source=None, parent_source=None),
            _test_result("PASS"),
        )

        assert repo.saved[0].file_path == Path("suites/auth.robot")

    def test_second_suite_overwrites_source_context(self) -> None:
        repo = _InMemoryRepo()
        listener = FlakinessListener(repository=repo)

        listener.start_suite(_suite_data("suites/login.robot"), MagicMock())
        listener.end_test(
            _test_data("T1", source=None, parent_source=None),
            _test_result("PASS"),
        )

        listener.start_suite(_suite_data("suites/logout.robot"), MagicMock())
        listener.end_test(
            _test_data("T2", source=None, parent_source=None),
            _test_result("PASS"),
        )

        assert repo.saved[0].file_path == Path("suites/login.robot")
        assert repo.saved[1].file_path == Path("suites/logout.robot")

    def test_start_suite_without_source_does_not_clear_previous_context(self) -> None:
        repo = _InMemoryRepo()
        listener = FlakinessListener(repository=repo)

        listener.start_suite(_suite_data("suites/first.robot"), MagicMock())

        # Second suite has no source attribute at all.
        sourceless = MagicMock(spec=[])
        listener.start_suite(sourceless, MagicMock())

        listener.end_test(
            _test_data("T", source=None, parent_source=None),
            _test_result("PASS"),
        )

        # The first suite's source should still be active.
        assert repo.saved[0].file_path == Path("suites/first.robot")

    def test_nested_suite_teardown_does_not_break_recording(self) -> None:
        """Simulate outer suite → inner suite → test → suite teardown sequence."""
        repo = _InMemoryRepo()
        listener = FlakinessListener(repository=repo)

        outer = _suite_data("suites/outer.robot")
        inner = _suite_data("suites/inner.robot")

        listener.start_suite(outer, MagicMock())
        listener.start_suite(inner, MagicMock())
        listener.end_test(
            _test_data("Inner Test", source="suites/inner.robot"),
            _test_result("PASS"),
        )
        # Simulate end_suite being called (listener has no end_suite handler,
        # but calling it should not raise AttributeError via RF internals).
        if hasattr(listener, "end_suite"):
            listener.end_suite(inner, MagicMock())

        assert len(repo.saved) == 1
        assert repo.saved[0].file_path == Path("suites/inner.robot")


@pytest.mark.integration
class TestRepositoryErrorIsolation:
    """Listener errors must never propagate to the caller (RF run continues)."""

    def test_save_failure_does_not_raise(self) -> None:
        broken_repo = MagicMock(spec=TestResultRepository)
        broken_repo.save_result.side_effect = OSError("disk full")
        listener = FlakinessListener(repository=broken_repo)

        listener.start_suite(_suite_data(), MagicMock())
        # Must not raise.
        listener.end_test(_test_data("T"), _test_result("PASS"))

    def test_subsequent_tests_saved_after_earlier_error(self) -> None:
        call_count = 0

        class _PartiallyBrokenRepo(_InMemoryRepo):
            def save_result(self, result: TestResult) -> None:
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise RuntimeError("transient error")
                super().save_result(result)

        repo = _PartiallyBrokenRepo()
        listener = FlakinessListener(repository=repo)

        listener.start_suite(_suite_data(), MagicMock())
        listener.end_test(_test_data("Fails To Save"), _test_result("PASS"))
        listener.end_test(_test_data("Saves OK"), _test_result("PASS"))

        # First call raised, second succeeded.
        assert len(repo.saved) == 1
        assert repo.saved[0].test_name == "Saves OK"


@pytest.mark.integration
class TestSkipStatus:
    """SKIP status passes through correctly."""

    def test_skipped_test_recorded(self) -> None:
        repo = _InMemoryRepo()
        listener = FlakinessListener(repository=repo)

        listener.start_suite(_suite_data(), MagicMock())
        listener.end_test(_test_data("Skipped Test"), _test_result("SKIP"))

        assert repo.saved[0].status == "SKIP"

    def test_skip_among_pass_and_fail(self) -> None:
        repo = _InMemoryRepo()
        listener = FlakinessListener(repository=repo)

        listener.start_suite(_suite_data(), MagicMock())
        for status in ("PASS", "SKIP", "FAIL"):
            listener.end_test(_test_data(f"T-{status}"), _test_result(status))

        assert [r.status for r in repo.saved] == ["PASS", "SKIP", "FAIL"]
