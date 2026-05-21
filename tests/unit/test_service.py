# tests/unit/test_service.py
"""Unit tests for AnalysisService and related result types."""

from __future__ import annotations

from pathlib import Path

import pytest

from robot_optimizer_core.config import Settings
from robot_optimizer_core.di import reset_container
from robot_optimizer_core.domain.value_objects import Finding, Severity
from robot_optimizer_core.service import (
    AnalysisResult,
    AnalysisService,
    DirectoryAnalysisResult,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_finding(severity: Severity = Severity.WARNING) -> Finding:
    from uuid import uuid4

    from robot_optimizer_core.domain.value_objects import Location, Pattern

    return Finding(
        id=uuid4(),
        pattern=Pattern.sleep_in_test("1s"),
        severity=severity,
        location=Location(Path("test.robot"), 1),
        message="test finding",
        context={},
    )


# ---------------------------------------------------------------------------
# AnalysisResult
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAnalysisResult:
    def test_is_success_true_when_no_error(self) -> None:
        r = AnalysisResult(file_path=Path("f.robot"), findings=[])
        assert r.is_success is True

    def test_is_success_false_when_error(self) -> None:
        r = AnalysisResult(
            file_path=Path("f.robot"), findings=[], error=RuntimeError("oops")
        )
        assert r.is_success is False

    def test_error_count(self) -> None:
        findings = [
            _make_finding(Severity.ERROR),
            _make_finding(Severity.WARNING),
            _make_finding(Severity.ERROR),
        ]
        r = AnalysisResult(file_path=Path("f.robot"), findings=findings)
        assert r.error_count == 2

    def test_warning_count(self) -> None:
        findings = [_make_finding(Severity.WARNING), _make_finding(Severity.ERROR)]
        r = AnalysisResult(file_path=Path("f.robot"), findings=findings)
        assert r.warning_count == 1

    def test_info_count(self) -> None:
        findings = [_make_finding(Severity.INFO), _make_finding(Severity.INFO)]
        r = AnalysisResult(file_path=Path("f.robot"), findings=findings)
        assert r.info_count == 2

    def test_zero_counts_for_empty_findings(self) -> None:
        r = AnalysisResult(file_path=Path("f.robot"), findings=[])
        assert r.error_count == 0
        assert r.warning_count == 0
        assert r.info_count == 0


# ---------------------------------------------------------------------------
# DirectoryAnalysisResult
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDirectoryAnalysisResult:
    def _make_result(self) -> DirectoryAnalysisResult:
        p1 = Path("a.robot")
        p2 = Path("b.robot")
        findings = [_make_finding(Severity.WARNING), _make_finding(Severity.ERROR)]
        return DirectoryAnalysisResult(
            directory=Path("tests/"),
            results={p1: findings, p2: []},
            errors=[(Path("bad.robot"), RuntimeError("fail"))],
        )

    def test_all_findings(self) -> None:
        r = self._make_result()
        assert len(r.all_findings) == 2

    def test_success_count(self) -> None:
        r = self._make_result()
        assert r.success_count == 2

    def test_failed_file_count(self) -> None:
        r = self._make_result()
        assert r.failed_file_count == 1

    def test_total_findings(self) -> None:
        r = self._make_result()
        assert r.total_findings == 2

    def test_to_dict_keys(self) -> None:
        r = self._make_result()
        d = r.to_dict()
        assert "directory" in d
        assert "success_count" in d
        assert "failed_file_count" in d
        assert "total_findings" in d
        assert "errors" in d

    def test_to_dict_errors_serialized(self) -> None:
        r = self._make_result()
        d = r.to_dict()
        assert len(d["errors"]) == 1
        assert isinstance(d["errors"][0][0], str)


# ---------------------------------------------------------------------------
# AnalysisService
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAnalysisService:
    def setup_method(self) -> None:
        reset_container()

    def teardown_method(self) -> None:
        reset_container()

    def test_init_with_custom_settings(self) -> None:
        settings = Settings(max_file_size_mb=1.0)
        svc = AnalysisService(settings=settings)
        assert svc.settings.max_file_size_mb == 1.0

    def test_init_without_settings_uses_container(self) -> None:
        svc = AnalysisService()
        assert svc.settings is not None

    def test_analyze_file_success(self, tmp_path: Path) -> None:
        f = tmp_path / "t.robot"
        f.write_bytes(b"*** Test Cases ***\nT\n    Log    ok\n")
        svc = AnalysisService()
        result = svc.analyze_file(f)
        assert result.is_success
        assert isinstance(result.findings, list)

    def test_analyze_file_error_captured(self, tmp_path: Path) -> None:
        svc = AnalysisService()
        result = svc.analyze_file(tmp_path / "nonexistent.robot")
        assert not result.is_success
        assert result.error is not None

    def test_analyze_file_returns_path(self, tmp_path: Path) -> None:
        f = tmp_path / "t.robot"
        f.write_bytes(b"*** Test Cases ***\nT\n    Log    ok\n")
        svc = AnalysisService()
        result = svc.analyze_file(f)
        assert result.file_path == f

    def test_analyze_directory_returns_result(self, tmp_path: Path) -> None:
        f = tmp_path / "t.robot"
        f.write_bytes(b"*** Test Cases ***\nT\n    Log    ok\n")
        svc = AnalysisService()
        result = svc.analyze_directory(tmp_path)
        assert isinstance(result, DirectoryAnalysisResult)
        assert result.success_count >= 1

    def test_analyze_directory_string_path(self, tmp_path: Path) -> None:
        f = tmp_path / "t.robot"
        f.write_bytes(b"*** Test Cases ***\nT\n    Log    ok\n")
        svc = AnalysisService()
        result = svc.analyze_directory(str(tmp_path))
        assert isinstance(result, DirectoryAnalysisResult)

    def test_list_analyzers_returns_dict(self) -> None:
        svc = AnalysisService()
        analyzers = svc.list_analyzers()
        assert isinstance(analyzers, dict)
        assert len(analyzers) > 0

    def test_list_analyzers_has_known_analyzer(self) -> None:
        svc = AnalysisService()
        analyzers = svc.list_analyzers()
        assert "dead_code" in analyzers or "sleep_detector" in analyzers

    def test_analyze_file_with_severity_filter(self, tmp_path: Path) -> None:
        f = tmp_path / "t.robot"
        f.write_bytes(b"*** Test Cases ***\nT\n    Sleep    5s\n")
        svc = AnalysisService()
        result = svc.analyze_file(f, min_severity=Severity.ERROR)
        # Should succeed; findings filtered by severity
        assert result.is_success

    def test_analyze_file_with_specific_analyzers(self, tmp_path: Path) -> None:
        f = tmp_path / "t.robot"
        f.write_bytes(b"*** Test Cases ***\nT\n    Log    ok\n")
        svc = AnalysisService()
        result = svc.analyze_file(f, analyzers=["dead_code"])
        assert result.is_success
