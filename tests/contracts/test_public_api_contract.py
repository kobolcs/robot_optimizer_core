# tests/contracts/test_public_api_contract.py
"""Public API contract tests — pin the stable surface exposed to library consumers.

These tests must NEVER be changed to make a failing test pass.
If a signature change is intentional, bump the version and document the break.
A failure here means a backward-incompatible change reached the test suite.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import robot_optimizer_core
from robot_optimizer_core.entrypoints.public_api import (
    analyze_directory,
    analyze_file,
    analyze_suite,
)


@pytest.mark.contract
class TestPublicModuleExports:
    """The top-level __all__ must not lose any symbol between releases."""

    REQUIRED_EXPORTS = {
        "analyze_file",
        "analyze_directory",
        "analyze_suite",
        "Settings",
        "Finding",
        "Severity",
        "PatternType",
        "TestFile",
    }

    def test_required_symbols_present_in_package(self) -> None:
        missing = {name for name in self.REQUIRED_EXPORTS if not hasattr(robot_optimizer_core, name)}
        assert not missing, f"Public API symbols removed: {missing}"


@pytest.mark.contract
class TestAnalyzeFileSignature:
    """analyze_file parameter names and defaults are stable."""

    def test_parameter_names_unchanged(self) -> None:
        sig = inspect.signature(analyze_file)
        params = list(sig.parameters.keys())
        assert params == ["file_path", "analyzers", "settings", "min_severity", "pattern_filter", "metrics"]

    def test_optional_params_have_none_default(self) -> None:
        sig = inspect.signature(analyze_file)
        for name in ["analyzers", "settings", "min_severity", "pattern_filter", "metrics"]:
            assert sig.parameters[name].default is None, f"{name} default changed"

    def test_returns_file_analysis_result(self, tmp_path: Path) -> None:
        from robot_optimizer_core.domain.value_objects.results import FileAnalysisResult

        f = tmp_path / "t.robot"
        f.write_text("*** Test Cases ***\nT\n    Log    hi\n")
        result = analyze_file(f)
        assert isinstance(result, FileAnalysisResult)

    def test_result_has_findings_and_meta(self, tmp_path: Path) -> None:
        f = tmp_path / "t.robot"
        f.write_text("*** Test Cases ***\nT\n    Log    hi\n")
        result = analyze_file(f)
        assert hasattr(result, "findings")
        assert hasattr(result, "meta")
        assert hasattr(result.meta, "duration_ms")
        assert hasattr(result.meta, "analyzer_names")

    def test_result_is_iterable(self, tmp_path: Path) -> None:
        f = tmp_path / "t.robot"
        f.write_text("*** Test Cases ***\nT\n    Log    hi\n")
        result = analyze_file(f)
        assert list(result) == result.findings

    def test_result_supports_len(self, tmp_path: Path) -> None:
        f = tmp_path / "t.robot"
        f.write_text("*** Test Cases ***\nT\n    Log    hi\n")
        result = analyze_file(f)
        assert len(result) == len(result.findings)


@pytest.mark.contract
class TestAnalyzeDirectorySignature:
    """analyze_directory parameter names and defaults are stable."""

    def test_parameter_names_unchanged(self) -> None:
        sig = inspect.signature(analyze_directory)
        params = list(sig.parameters.keys())
        assert params == [
            "directory_path", "patterns", "exclude_patterns", "recursive",
            "analyzers", "settings", "error_handling", "min_severity",
            "pattern_filter", "max_workers", "metrics", "use_cache",
        ]

    def test_recursive_defaults_true(self) -> None:
        sig = inspect.signature(analyze_directory)
        assert sig.parameters["recursive"].default is True

    def test_error_handling_defaults_to_raise(self) -> None:
        sig = inspect.signature(analyze_directory)
        assert sig.parameters["error_handling"].default == "raise"

    def test_use_cache_defaults_true(self) -> None:
        sig = inspect.signature(analyze_directory)
        assert sig.parameters["use_cache"].default is True

    def test_returns_directory_results(self, tmp_path: Path) -> None:
        from robot_optimizer_core.application.services.analysis_service import DirectoryResults

        (tmp_path / "t.robot").write_text("*** Test Cases ***\nT\n    Log    hi\n")
        result = analyze_directory(tmp_path)
        assert isinstance(result, DirectoryResults)
        assert hasattr(result, "findings")
        assert hasattr(result, "errors")


@pytest.mark.contract
class TestAnalyzeSuiteSignature:
    """analyze_suite parameter names and defaults are stable."""

    def test_parameter_names_unchanged(self) -> None:
        sig = inspect.signature(analyze_suite)
        params = list(sig.parameters.keys())
        assert params == ["suite_path", "analyzers", "settings", "min_severity", "pattern_filter"]

    def test_returns_suite_analysis_result(self, tmp_path: Path) -> None:
        from robot_optimizer_core.entrypoints.public_api import SuiteAnalysisResult

        (tmp_path / "t.robot").write_text("*** Test Cases ***\nT\n    Log    hi\n")
        result = analyze_suite(tmp_path)
        assert isinstance(result, SuiteAnalysisResult)

    def test_suite_result_has_required_fields(self, tmp_path: Path) -> None:
        (tmp_path / "t.robot").write_text("*** Test Cases ***\nT\n    Log    hi\n")
        result = analyze_suite(tmp_path)
        assert hasattr(result, "findings")
        assert hasattr(result, "file_findings")
        assert hasattr(result, "suite_info")
        assert hasattr(result, "statistics")
        assert hasattr(result, "errors")

    def test_suite_info_has_required_fields(self, tmp_path: Path) -> None:
        (tmp_path / "t.robot").write_text("*** Test Cases ***\nT\n    Log    hi\n")
        result = analyze_suite(tmp_path)
        assert hasattr(result.suite_info, "files")
        assert hasattr(result.suite_info, "keywords")
        assert hasattr(result.suite_info, "test_cases")
        assert hasattr(result.suite_info, "imports")

    def test_statistics_has_required_fields(self, tmp_path: Path) -> None:
        (tmp_path / "t.robot").write_text("*** Test Cases ***\nT\n    Log    hi\n")
        result = analyze_suite(tmp_path)
        assert hasattr(result.statistics, "total_findings")
        assert hasattr(result.statistics, "findings_by_severity")
        assert hasattr(result.statistics, "findings_by_type")


@pytest.mark.contract
class TestErrorTypes:
    """Exception types exported in the public API are stable."""

    def test_robot_file_not_found_error_exported(self) -> None:
        from robot_optimizer_core.exceptions import RobotFileNotFoundError
        assert issubclass(RobotFileNotFoundError, Exception)

    def test_analysis_error_exported(self) -> None:
        from robot_optimizer_core.exceptions import AnalysisError
        assert issubclass(AnalysisError, Exception)

    def test_analysis_error_has_file_path_attribute(self, tmp_path: Path) -> None:
        from robot_optimizer_core.exceptions import AnalysisError

        f = tmp_path / "big.robot"
        f.write_bytes(b"x" * 200_000)
        from robot_optimizer_core.infrastructure.config import Settings
        with pytest.raises(AnalysisError) as exc_info:
            analyze_file(f, settings=Settings(max_file_size_mb=0.1))
        assert hasattr(exc_info.value, "file_path")
