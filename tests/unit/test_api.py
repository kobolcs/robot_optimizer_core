# tests/unit/test_api.py
"""Unit tests for the high-level API — focused on file-size enforcement."""

from __future__ import annotations

from pathlib import Path

import pytest

import robot_optimizer_core.api as _api_module
from robot_optimizer_core.api import (
    _analyze_one_file,
    _execute_directory_analysis,
    analyze_directory,
    analyze_file,
)
from robot_optimizer_core.config import Settings
from robot_optimizer_core.domain.value_objects import Finding
from robot_optimizer_core.exceptions import AnalysisError


@pytest.mark.unit
class TestAnalyzeFileMaxSizeEnforcement:
    def test_file_over_limit_raises_before_loading(self, tmp_path: Path) -> None:
        # 0.1 MB = 104857 bytes; write 150 000 bytes to exceed the limit
        robot_file = tmp_path / "large.robot"
        robot_file.write_bytes(b"x" * 150_000)

        settings = Settings(max_file_size_mb=0.1)

        with pytest.raises(AnalysisError, match=r"[Ee]xceeds maximum size"):
            analyze_file(robot_file, settings=settings)

    def test_file_error_includes_file_path(self, tmp_path: Path) -> None:
        robot_file = tmp_path / "large.robot"
        robot_file.write_bytes(b"x" * 150_000)

        settings = Settings(max_file_size_mb=0.1)

        with pytest.raises(AnalysisError) as exc_info:
            analyze_file(robot_file, settings=settings)

        assert exc_info.value.file_path == robot_file

    def test_normal_file_within_limit_analyzes_successfully(
        self, tmp_path: Path
    ) -> None:
        robot_file = tmp_path / "normal.robot"
        robot_file.write_bytes(b"*** Test Cases ***\nSample Test\n    Log    hello\n")

        settings = Settings(max_file_size_mb=10.0)
        findings = analyze_file(robot_file, settings=settings)

        assert isinstance(findings, list)

    def test_file_exactly_at_limit_is_not_rejected_by_size_check(
        self, tmp_path: Path
    ) -> None:
        # A file whose byte count equals the limit exactly must not be rejected
        # by the size guard (the check is strictly greater-than).
        settings = Settings(max_file_size_mb=0.1)
        limit = settings.max_file_size_bytes  # 104857

        robot_file = tmp_path / "edge.robot"
        base_content = "*** Test Cases ***\nSample Test\n    Log    hello\n"
        padding = "x" * (limit - len(base_content.encode("utf-8")))
        # Use write_bytes so the on-disk size is exactly `limit` bytes on every
        # platform (write_text in text mode adds \r on Windows, overshooting).
        robot_file.write_bytes((base_content + padding).encode("utf-8"))

        try:
            findings = analyze_file(robot_file, settings=settings)
        except AnalysisError as exc:
            pytest.fail(
                f"File at exactly the limit must analyze successfully without triggering the size guard, got: {exc}"
            )

        assert isinstance(findings, list)

    def test_size_error_not_double_wrapped(self, tmp_path: Path) -> None:
        """AnalysisError from the size guard must not be re-wrapped (fix 5b)."""
        robot_file = tmp_path / "large.robot"
        robot_file.write_bytes(b"x" * 150_000)
        settings = Settings(max_file_size_mb=0.1)

        with pytest.raises(AnalysisError) as exc_info:
            analyze_file(robot_file, settings=settings)

        # The message must be the original size-guard message, NOT 'Failed to load file:'
        assert "Failed to load file" not in str(exc_info.value)
        assert "exceeds maximum size" in str(exc_info.value).lower()
        # file_path must be preserved directly, not nested
        assert exc_info.value.file_path == robot_file


@pytest.mark.unit
def test_analyze_file_uses_container_settings_when_none_passed(
    tmp_path: Path,
) -> None:
    """analyze_file must resolve settings from the DI container, not a separate global."""
    from robot_optimizer_core.di import get_container, reset_container

    reset_container()
    container = get_container()
    restrictive = Settings(max_file_size_mb=0.1)  # 104 857 byte limit
    container.register_instance("settings", restrictive, override=True)

    robot_file = tmp_path / "toobig.robot"
    robot_file.write_bytes(b"x" * 150_000)  # 150 000 bytes > limit

    try:
        with pytest.raises(AnalysisError, match=r"[Ee]xceeds maximum size"):
            analyze_file(robot_file)  # no settings= passed — must use container
    finally:
        reset_container()


@pytest.mark.unit
def test_analyze_file_uses_safe_analyze(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    robot_file = tmp_path / "sample.robot"
    robot_file.write_bytes(b"*** Test Cases ***\nCase\n    Log    ok\n")

    calls: list[str] = []

    class HookedAnalyzer:
        name = "hooked"

        def safe_analyze(self, test_file: object) -> list[Finding]:
            calls.append("safe")
            return []

    monkeypatch.setattr(
        "robot_optimizer_core.api._get_analyzer_instances",
        lambda analyzers, settings: [HookedAnalyzer()],
    )

    analyze_file(robot_file)
    assert calls == ["safe"]


@pytest.mark.unit
def test_analyze_directory_parallel_is_deterministic(tmp_path: Path) -> None:
    one = tmp_path / "one.robot"
    two = tmp_path / "two.robot"
    one.write_bytes(b"*** Keywords ***\nAlpha\n    No Operation\n")
    two.write_bytes(b"*** Test Cases ***\nUse\n    Alpha\n")

    first = analyze_directory(tmp_path, analyzers=["dead_code"], max_workers=4)
    second = analyze_directory(tmp_path, analyzers=["dead_code"], max_workers=4)

    first_messages = {
        str(path): sorted(f.message for f in findings)
        for path, findings in first.findings.items()
    }
    second_messages = {
        str(path): sorted(f.message for f in findings)
        for path, findings in second.findings.items()
    }

    assert first_messages == second_messages


@pytest.mark.unit
def test_analyze_file_with_dead_code_analyzer_does_not_crash(tmp_path: Path) -> None:
    robot_file = tmp_path / "sample.robot"
    robot_file.write_bytes(b"*** Test Cases ***\nCase\n    Log    ok\n")

    findings = analyze_file(robot_file, analyzers=["dead_code"])

    assert isinstance(findings, list)


@pytest.mark.unit
def test_fail_fast_stops_on_first_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """fail_fast=True must stop after the first failing file, not process all files."""
    import warnings

    for i in range(3):
        (tmp_path / f"test_{i}.robot").write_bytes(
            b"*** Test Cases ***\nT\n    Log    ok\n"
        )

    call_count = 0

    def always_fail(path: Path, *args: object, **kwargs: object) -> list[Finding]:
        nonlocal call_count
        call_count += 1
        raise AnalysisError("forced failure", file_path=path)

    monkeypatch.setattr(_api_module, "analyze_file", always_fail)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        with pytest.raises(AnalysisError):
            analyze_directory(tmp_path, max_workers=4, fail_fast=True)

    assert call_count == 1, (
        f"fail_fast=True processed {call_count} files before stopping; expected 1"
    )


@pytest.mark.unit
def test_fail_fast_false_processes_all_files_and_collects_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """error_handling='warn' continues through all files and surfaces errors on the result."""
    for i in range(3):
        (tmp_path / f"test_{i}.robot").write_bytes(
            b"*** Test Cases ***\nT\n    Log    ok\n"
        )

    call_count = 0

    def always_fail(path: Path, *args: object, **kwargs: object) -> list[Finding]:
        nonlocal call_count
        call_count += 1
        raise AnalysisError("forced failure", file_path=path)

    monkeypatch.setattr(_api_module, "analyze_file", always_fail)

    result = analyze_directory(tmp_path, max_workers=1, error_handling="warn")
    assert call_count == 3
    assert len(result.errors) == 3


# ---------------------------------------------------------------------------
# _analyze_one_file
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAnalyzeOneFile:
    def test_returns_path_and_findings(self, tmp_path: Path) -> None:
        rf = tmp_path / "t.robot"
        rf.write_bytes(b"*** Test Cases ***\nT\n    Log    ok\n")
        path, findings = _analyze_one_file(rf, ["dead_code"], Settings(), None, None)
        assert path == rf
        assert isinstance(findings, list)

    def test_propagates_exception(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        rf = tmp_path / "t.robot"
        rf.write_bytes(b"*** Test Cases ***\nT\n    Log    ok\n")

        def raise_analysis_error(*a, **kw):
            raise AnalysisError("boom")

        monkeypatch.setattr(_api_module, "analyze_file", raise_analysis_error)
        with pytest.raises(AnalysisError):
            _analyze_one_file(rf, None, Settings(), None, None)


# ---------------------------------------------------------------------------
# _execute_directory_analysis
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExecuteDirectoryAnalysis:
    def _ok_fn(self, path: Path) -> tuple[Path, list[Finding]]:
        return path, []

    def _fail_fn(self, path: Path) -> tuple[Path, list[Finding]]:
        raise AnalysisError("forced", file_path=path)

    def test_sequential_returns_all_results(self, tmp_path: Path) -> None:
        files = [tmp_path / f"f{i}.robot" for i in range(3)]
        results, errors = _execute_directory_analysis(files, self._ok_fn, 1, fail_fast=False)
        assert len(results.findings) == 3
        assert errors == []

    def test_parallel_returns_all_results(self, tmp_path: Path) -> None:
        files = [tmp_path / f"f{i}.robot" for i in range(4)]
        results, errors = _execute_directory_analysis(files, self._ok_fn, 4, fail_fast=False)
        assert len(results.findings) == 4
        assert errors == []

    def test_sequential_error_collected_not_raised(self, tmp_path: Path) -> None:
        files = [tmp_path / "f.robot"]
        results, errors = _execute_directory_analysis(files, self._fail_fn, 1, fail_fast=False)
        assert len(errors) == 1
        assert len(results.findings) == 0

    def test_fail_fast_sequential_raises_immediately(self, tmp_path: Path) -> None:
        files = [tmp_path / f"f{i}.robot" for i in range(3)]
        call_count = 0

        def counting_fail(p: Path) -> tuple[Path, list[Finding]]:
            nonlocal call_count
            call_count += 1
            raise AnalysisError("forced", file_path=p)

        with pytest.raises(AnalysisError):
            _execute_directory_analysis(files, counting_fail, 1, fail_fast=True)
        assert call_count == 1

    def test_parallel_error_collected_not_raised(self, tmp_path: Path) -> None:
        files = [tmp_path / f"f{i}.robot" for i in range(3)]
        results, errors = _execute_directory_analysis(files, self._fail_fn, 4, fail_fast=False)
        assert len(errors) == 3
        assert len(results.findings) == 0


# ---------------------------------------------------------------------------
# analyze_file edge cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_analyze_file_raises_for_nonexistent_file(tmp_path: Path) -> None:
    from robot_optimizer_core.exceptions import RobotFileNotFoundError

    with pytest.raises(RobotFileNotFoundError):
        analyze_file(tmp_path / "missing.robot")


@pytest.mark.unit
def test_analyze_file_wraps_load_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    robot_file = tmp_path / "t.robot"
    robot_file.write_bytes(b"*** Test Cases ***\nT\n    Log    ok\n")

    def boom(*a, **kw):
        raise ValueError("parse kaboom")

    monkeypatch.setattr("robot_optimizer_core.api.TestFile.from_path", boom)

    with pytest.raises(AnalysisError, match="Failed to load file"):
        analyze_file(robot_file)


@pytest.mark.unit
def test_analyze_file_analyzer_failure_raises_analysis_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    robot_file = tmp_path / "t.robot"
    robot_file.write_bytes(b"*** Test Cases ***\nT\n    Log    ok\n")

    class ExplodingAnalyzer:
        name = "exploder"

        def safe_analyze(self, test_file: object) -> list:
            raise RuntimeError("analyzer boom")

    monkeypatch.setattr(
        "robot_optimizer_core.api._get_analyzer_instances",
        lambda *a, **kw: [ExplodingAnalyzer()],
    )

    with pytest.raises(AnalysisError, match="Analysis failed"):
        analyze_file(robot_file)


# ---------------------------------------------------------------------------
# _validate_directory_path
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_validate_directory_path_nonexistent(tmp_path: Path) -> None:
    from robot_optimizer_core.api import _validate_directory_path
    from robot_optimizer_core.exceptions import RobotFileNotFoundError

    with pytest.raises(RobotFileNotFoundError):
        _validate_directory_path(tmp_path / "nope")


@pytest.mark.unit
def test_validate_directory_path_file_raises(tmp_path: Path) -> None:
    f = tmp_path / "f.robot"
    f.write_bytes(b"x")
    with pytest.raises(AnalysisError, match="not a directory"):
        from robot_optimizer_core.api import _validate_directory_path

        _validate_directory_path(f)


# ---------------------------------------------------------------------------
# _handle_directory_analysis_errors
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_handle_errors_raise_mode(tmp_path: Path) -> None:
    from robot_optimizer_core.api import (
        DirectoryResults,
        _handle_directory_analysis_errors,
    )

    errors = [(tmp_path / "f.robot", AnalysisError("bad"))]
    dr = DirectoryResults()
    with pytest.raises(ExceptionGroup):
        _handle_directory_analysis_errors(errors, "raise", False, dr)


@pytest.mark.unit
def test_handle_errors_warn_mode_attaches_to_result(tmp_path: Path) -> None:
    from robot_optimizer_core.api import (
        DirectoryResults,
        _handle_directory_analysis_errors,
    )

    errors = [(tmp_path / "f.robot", AnalysisError("bad"))]
    dr = DirectoryResults()
    _handle_directory_analysis_errors(errors, "warn", False, dr)
    assert len(dr.errors) == 1


@pytest.mark.unit
def test_handle_errors_skip_mode_no_exception(tmp_path: Path) -> None:
    from robot_optimizer_core.api import (
        DirectoryResults,
        _handle_directory_analysis_errors,
    )

    errors = [(tmp_path / "f.robot", AnalysisError("bad"))]
    dr = DirectoryResults()
    _handle_directory_analysis_errors(errors, "skip", False, dr)
    # no exception, no errors attached
    assert dr.errors == []


@pytest.mark.unit
def test_handle_errors_no_op_for_empty(tmp_path: Path) -> None:
    from robot_optimizer_core.api import (
        DirectoryResults,
        _handle_directory_analysis_errors,
    )

    dr = DirectoryResults()
    _handle_directory_analysis_errors([], "raise", False, dr)  # must not raise


# ---------------------------------------------------------------------------
# analyze_suite
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_analyze_suite_single_file(tmp_path: Path) -> None:
    from robot_optimizer_core.api import analyze_suite

    f = tmp_path / "suite.robot"
    f.write_bytes(b"*** Test Cases ***\nT\n    Log    ok\n")
    result = analyze_suite(f)
    assert isinstance(result.findings, list)
    assert hasattr(result, "suite_info")
    assert hasattr(result, "statistics")


@pytest.mark.unit
def test_analyze_suite_directory(tmp_path: Path) -> None:
    from robot_optimizer_core.api import analyze_suite

    (tmp_path / "a.robot").write_bytes(b"*** Test Cases ***\nT\n    Log    ok\n")
    result = analyze_suite(tmp_path)
    assert isinstance(result.findings, list)


@pytest.mark.unit
def test_analyze_suite_with_dead_code_analyzer(tmp_path: Path) -> None:
    from robot_optimizer_core.api import analyze_suite

    f = tmp_path / "suite.robot"
    f.write_bytes(
        b"*** Keywords ***\nUsed KW\n    Log    ok\n"
        b"Unused KW\n    Log    never called\n"
        b"*** Test Cases ***\nT\n    Used KW\n"
    )
    result = analyze_suite(f, analyzers=["dead_code"])
    assert isinstance(result.findings, list)


@pytest.mark.unit
def test_load_test_files_logs_warning_on_bad_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import robot_optimizer_core.api as _api_mod

    monkeypatch.setattr(_api_mod.TestFile, "from_path", lambda p: (_ for _ in ()).throw(RuntimeError("bad")))
    from robot_optimizer_core.api import _load_test_files

    result = _load_test_files([tmp_path / "f.robot"])
    assert result == []


@pytest.mark.unit
def test_get_analyzer_instances_passes_through_instance(tmp_path: Path) -> None:
    from robot_optimizer_core.api import _get_analyzer_instances
    from robot_optimizer_core.config import Settings

    class FakeAnalyzer:
        name = "fake"

        def safe_analyze(self, tf: object) -> list:
            return []

    fake = FakeAnalyzer()
    result = _get_analyzer_instances([fake], Settings())
    assert fake in result


@pytest.mark.unit
def test_analyze_directory_with_metrics_passed(tmp_path: Path) -> None:
    from robot_optimizer_core.metrics import MetricsCollector

    f = tmp_path / "t.robot"
    f.write_bytes(b"*** Test Cases ***\nT\n    Log    ok\n")
    m = MetricsCollector(enabled=True)
    try:
        analyze_directory(tmp_path, metrics=m)
    finally:
        m.stop()
