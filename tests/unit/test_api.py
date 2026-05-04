# tests/unit/test_api.py
"""Unit tests for the high-level API — focused on file-size enforcement."""

from __future__ import annotations

from pathlib import Path

import pytest

from robot_optimizer_core.api import analyze_directory, analyze_file
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

        with pytest.raises(AnalysisError, match="[Ee]xceeds maximum size"):
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
        robot_file.write_text("*** Test Cases ***\nSample Test\n    Log    hello\n")

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
        robot_file.write_text(base_content + padding)

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
def test_analyze_file_uses_safe_analyze(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    robot_file = tmp_path / "sample.robot"
    robot_file.write_text("*** Test Cases ***\nCase\n    Log    ok\n")

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
    """
    Verifies that analyze_directory produces deterministic findings when run in parallel.
    
    Runs analyze_directory twice on the same directory with multiple workers and asserts that, for each file, the sorted lists of finding messages are identical between runs.
    """
    one = tmp_path / "one.robot"
    two = tmp_path / "two.robot"
    one.write_text("*** Keywords ***\nAlpha\n    No Operation\n")
    two.write_text("*** Test Cases ***\nUse\n    Alpha\n")

    first = analyze_directory(tmp_path, analyzers=["dead_code"], max_workers=4)
    second = analyze_directory(tmp_path, analyzers=["dead_code"], max_workers=4)

    first_messages = {
        str(path): sorted(f.message for f in findings)
        for path, findings in first.items()
    }
    second_messages = {
        str(path): sorted(f.message for f in findings)
        for path, findings in second.items()
    }

    assert first_messages == second_messages


@pytest.mark.unit
def test_analyze_file_with_dead_code_analyzer_does_not_crash(tmp_path: Path) -> None:
    robot_file = tmp_path / "sample.robot"
    robot_file.write_text("*** Test Cases ***\nCase\n    Log    ok\n")

    findings = analyze_file(robot_file, analyzers=["dead_code"])

    assert isinstance(findings, list)
