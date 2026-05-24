# tests/unit/test_service.py
"""Unit tests for AnalysisService and related result types."""

from __future__ import annotations

from pathlib import Path

import pytest

from robot_optimizer_core.application.services.analysis_service import (
    AnalysisResult,
    AnalysisService,
    DirectoryAnalysisResult,
)
from robot_optimizer_core.composition.container import reset_container
from robot_optimizer_core.domain.value_objects import Finding, Severity
from robot_optimizer_core.infrastructure.config import Settings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


from unit.helpers import _SIMPLE_ROBOT, make_finding as _make_finding


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
            _make_finding(severity=Severity.ERROR),
            _make_finding(severity=Severity.WARNING),
            _make_finding(severity=Severity.ERROR),
        ]
        r = AnalysisResult(file_path=Path("f.robot"), findings=findings)
        assert r.error_count == 2

    def test_warning_count(self) -> None:
        findings = [_make_finding(severity=Severity.WARNING), _make_finding(severity=Severity.ERROR)]
        r = AnalysisResult(file_path=Path("f.robot"), findings=findings)
        assert r.warning_count == 1

    def test_info_count(self) -> None:
        findings = [_make_finding(severity=Severity.INFO), _make_finding(severity=Severity.INFO)]
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
        findings = [_make_finding(severity=Severity.WARNING), _make_finding(severity=Severity.ERROR)]
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
        base = AnalysisService.from_container()
        settings = Settings(max_file_size_mb=1.0)
        svc = AnalysisService(
            settings=settings,
            metrics=base._metrics,
            file_discovery=base._file_discovery,
            registry=base._registry,
            cache=base._cache,
        )
        assert svc.settings.max_file_size_mb == 1.0

    def test_init_without_settings_uses_container(self) -> None:
        svc = AnalysisService.from_container()
        assert svc.settings is not None

    def test_analyze_file_success(self, tmp_path: Path) -> None:
        f = tmp_path / "t.robot"
        f.write_bytes(_SIMPLE_ROBOT)
        svc = AnalysisService.from_container()
        result = svc.analyze_file(f)
        assert result.is_success
        assert isinstance(result.findings, list)

    def test_analyze_file_error_captured(self, tmp_path: Path) -> None:
        svc = AnalysisService.from_container()
        result = svc.analyze_file(tmp_path / "nonexistent.robot")
        assert not result.is_success
        assert result.error is not None

    def test_analyze_file_returns_path(self, tmp_path: Path) -> None:
        f = tmp_path / "t.robot"
        f.write_bytes(_SIMPLE_ROBOT)
        svc = AnalysisService.from_container()
        result = svc.analyze_file(f)
        assert result.file_path == f

    def test_analyze_directory_returns_result(self, tmp_path: Path) -> None:
        f = tmp_path / "t.robot"
        f.write_bytes(_SIMPLE_ROBOT)
        svc = AnalysisService.from_container()
        result = svc.analyze_directory(tmp_path)
        assert isinstance(result, DirectoryAnalysisResult)
        assert result.success_count >= 1

    def test_analyze_directory_string_path(self, tmp_path: Path) -> None:
        f = tmp_path / "t.robot"
        f.write_bytes(_SIMPLE_ROBOT)
        svc = AnalysisService.from_container()
        result = svc.analyze_directory(str(tmp_path))
        assert isinstance(result, DirectoryAnalysisResult)

    def test_list_analyzers_returns_dict(self) -> None:
        svc = AnalysisService.from_container()
        analyzers = svc.list_analyzers()
        assert isinstance(analyzers, dict)
        assert len(analyzers) > 0

    def test_list_analyzers_has_known_analyzer(self) -> None:
        svc = AnalysisService.from_container()
        analyzers = svc.list_analyzers()
        assert "dead_code" in analyzers or "sleep_detector" in analyzers

    def test_analyze_file_with_severity_filter(self, tmp_path: Path) -> None:
        f = tmp_path / "t.robot"
        f.write_bytes(b"*** Test Cases ***\nT\n    Sleep    5s\n")
        svc = AnalysisService.from_container()
        result = svc.analyze_file(f, min_severity=Severity.ERROR)
        # Should succeed; findings filtered by severity
        assert result.is_success

    def test_analyze_file_with_specific_analyzers(self, tmp_path: Path) -> None:
        f = tmp_path / "t.robot"
        f.write_bytes(_SIMPLE_ROBOT)
        svc = AnalysisService.from_container()
        result = svc.analyze_file(f, analyzers=["dead_code"])
        assert result.is_success

    def test_run_file_analysis_with_instance_analyzer(self, tmp_path: Path) -> None:
        """_get_analyzer_instances case _: branch — pass a pre-built instance."""
        from robot_optimizer_core.application.analyzers.dead_code import (
            DeadCodeAnalyzer,
        )

        f = tmp_path / "t.robot"
        f.write_bytes(_SIMPLE_ROBOT)
        svc = AnalysisService.from_container()
        findings, names = svc._run_file_analysis(
            f, analyzers=[DeadCodeAnalyzer()], settings=None,
            min_severity=None, pattern_filter=None,
        )
        assert isinstance(findings, list)
        assert isinstance(names, tuple)

    def test_run_file_analysis_max_size_raises(self, tmp_path: Path) -> None:
        """_run_file_analysis raises AnalysisError when file exceeds size limit."""
        from robot_optimizer_core.exceptions import AnalysisError

        f = tmp_path / "big.robot"
        f.write_bytes(b"x" * 150_000)
        settings = Settings(max_file_size_mb=0.1)
        base = AnalysisService.from_container()
        svc = AnalysisService(
            settings=settings,
            metrics=base._metrics,
            file_discovery=base._file_discovery,
            registry=base._registry,
            cache=base._cache,
        )

        with pytest.raises(AnalysisError, match="exceeds maximum size"):
            svc._run_file_analysis(
                f, analyzers=None, settings=settings,
                min_severity=None, pattern_filter=None,
            )

    def test_run_directory_analysis_no_cache(self, tmp_path: Path) -> None:
        """run_directory_analysis with use_cache=False skips cache branches."""

        f = tmp_path / "t.robot"
        f.write_bytes(_SIMPLE_ROBOT)

        svc = AnalysisService.from_container()

        def _noop(fp: Path) -> tuple[Path, list[Finding]]:
            return fp, []

        from robot_optimizer_core.application.services.analysis_service import DirectoryAnalysisOptions

        opts = DirectoryAnalysisOptions(
            patterns=["*.robot"],
            recursive=False,
            error_handling="warn",
            max_workers=1,
            use_cache=False,
        )
        result = svc.run_directory_analysis(
            directory_path=tmp_path,
            analyze_fn=_noop,
            options=opts,
            settings=svc.settings,
            metrics=svc._metrics,
        )
        assert result is not None

    def test_run_file_analysis_pattern_filter_skips_analyzers(self, tmp_path: Path) -> None:
        """pattern_filter that matches nothing should return empty findings."""
        f = tmp_path / "t.robot"
        f.write_bytes(b"*** Test Cases ***\nT\n    Sleep    5s\n")
        svc = AnalysisService.from_container()
        findings, names = svc._run_file_analysis(
            f, analyzers=None, settings=None,
            min_severity=None, pattern_filter=["nonexistent_analyzer"],
        )
        assert findings == []
        assert names == ()

    def test_run_file_analysis_binary_file_raises_analysis_error(self, tmp_path: Path) -> None:
        """Binary file triggers the generic except-Exception path in file loading."""
        from robot_optimizer_core.exceptions import AnalysisError

        f = tmp_path / "binary.robot"
        f.write_bytes(b"\x00\x01\x02binary content")
        svc = AnalysisService.from_container()
        with pytest.raises(AnalysisError, match="Failed to load file"):
            svc._run_file_analysis(
                f, analyzers=None, settings=None,
                min_severity=None, pattern_filter=None,
            )

    def test_run_file_analysis_analyzer_raises_analysis_error(self, tmp_path: Path) -> None:
        """except AnalysisError in per-analyzer loop re-raises (lines 422-424)."""
        from robot_optimizer_core.application.analyzers.base import BaseAnalyzer
        from robot_optimizer_core.domain.entities import TestFile
        from robot_optimizer_core.exceptions import AnalysisError

        class _RaisingAnalyzer(BaseAnalyzer):
            @property
            def name(self) -> str:
                return "raising_analyzer"

            @property
            def description(self) -> str:
                return "always raises"

            def analyze(self, test_file: TestFile) -> list[Finding]:
                raise AnalysisError("deliberate", file_path=test_file.path)

        f = tmp_path / "t.robot"
        f.write_bytes(_SIMPLE_ROBOT)
        svc = AnalysisService.from_container()
        with pytest.raises(AnalysisError, match="deliberate"):
            svc._run_file_analysis(
                f, analyzers=[_RaisingAnalyzer()], settings=None,
                min_severity=None, pattern_filter=None,
            )

    def test_list_analyzers_error_path(self) -> None:
        """list_analyzers returns error entry when get_info raises."""
        from robot_optimizer_core.infrastructure.config import get_settings
        from robot_optimizer_core.infrastructure.metrics.collector import get_metrics

        class _BrokenRegistry:
            def list(self) -> list[str]:
                return ["dead_code"]

            def get_info(self, _name: str) -> dict:
                raise RuntimeError("boom")

        base = AnalysisService.from_container()
        svc = AnalysisService(
            settings=get_settings(),
            metrics=get_metrics(),
            file_discovery=base._file_discovery,
            registry=_BrokenRegistry(),
        )
        result = svc.list_analyzers()
        assert "dead_code" in result
        assert "error" in result["dead_code"]


# ---------------------------------------------------------------------------
# Cache correctness: severity filter and analyzer scope (regression tests)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCacheKeyCorrectness:
    """Regression tests for the cache-key bug where:
    - min_severity was ignored for cache hits (stale filtered results served)
    - analyzer scope was not encoded in the key (wrong scope could be returned)
    """

    _SLEEP_ROBOT = b"*** Test Cases ***\nMy Test\n    Sleep    5\n"

    def _make_service(self, cache_dir: Path) -> AnalysisService:
        from robot_optimizer_core.infrastructure.cache.analysis_cache import (
            AnalysisCache,
        )
        from robot_optimizer_core.infrastructure.metrics.collector import get_metrics

        base = AnalysisService.from_container()
        return AnalysisService(
            settings=Settings(),
            metrics=get_metrics(),
            file_discovery=base._file_discovery,
            registry=base._registry,
            cache=AnalysisCache(cache_dir=cache_dir),
        )

    def test_severity_filter_applied_to_cache_hits(self, tmp_path: Path) -> None:
        """A second run with min_severity must filter even when results come from cache."""
        robot_file = tmp_path / "suite.robot"
        robot_file.write_bytes(self._SLEEP_ROBOT)
        cache_dir = tmp_path / "cache"

        svc = self._make_service(cache_dir)
        # First run: cache is populated with full findings (WARNING + INFO)
        result1 = svc.analyze_directory(tmp_path, min_severity=None)
        total = sum(len(fs) for fs in result1.results.values())
        assert total > 0

        # Second run: same file (cache hit), but filtered to WARNING+
        svc2 = self._make_service(cache_dir)
        result2 = svc2.analyze_directory(tmp_path, min_severity=Severity.WARNING)
        for findings in result2.results.values():
            assert all(f.severity <= Severity.WARNING for f in findings)

    def test_cache_stores_full_findings_not_filtered(self, tmp_path: Path) -> None:
        """Running with min_severity must not pollute the cache with partial results."""
        robot_file = tmp_path / "suite.robot"
        robot_file.write_bytes(self._SLEEP_ROBOT)
        cache_dir = tmp_path / "cache"

        svc1 = self._make_service(cache_dir)
        # First run: filtered — should NOT store only WARNING findings
        svc1.analyze_directory(tmp_path, min_severity=Severity.WARNING)

        svc2 = self._make_service(cache_dir)
        # Second run: no filter — must return full set from cache, not filtered set
        result = svc2.analyze_directory(tmp_path, min_severity=None)
        all_findings = [f for fs in result.results.values() for f in fs]
        has_info = any(f.severity == Severity.INFO for f in all_findings)
        assert has_info, "Cache must store full findings; INFO findings should be present"

    def test_different_analyzer_scopes_are_independent_in_cache(
        self, tmp_path: Path
    ) -> None:
        """A sleep_detector-only run must not be served cached full-run results."""
        robot_file = tmp_path / "suite.robot"
        robot_file.write_bytes(self._SLEEP_ROBOT)
        cache_dir = tmp_path / "cache"

        # First run: all analyzers (populates __all__ scope)
        svc1 = self._make_service(cache_dir)
        result_all = svc1.analyze_directory(tmp_path, min_severity=None)
        all_types = {
            f.pattern.type.name
            for fs in result_all.results.values()
            for f in fs
        }

        # Second run: sleep_detector only (different scope key → cache miss → fresh)
        svc2 = self._make_service(cache_dir)
        result_scoped = svc2.analyze_directory(
            tmp_path, analyzers=["sleep_detector"], min_severity=None
        )
        scoped_types = {
            f.pattern.type.name
            for fs in result_scoped.results.values()
            for f in fs
        }

        # The scoped run must ONLY contain sleep findings
        assert scoped_types == {"SLEEP_IN_TEST"}
        # And the full run must have had more types
        assert len(all_types) >= len(scoped_types)
