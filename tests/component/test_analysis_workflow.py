# tests/component/test_analysis_workflow.py
"""Component tests for multi-step analysis workflows.

These tests exercise several components together (analyzer, api, registry,
settings) without relying on external services.  They validate that the
cross-cutting changes (fix 1-5) behave correctly end-to-end at the
component boundary.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from robot_optimizer_core.analyzers.registry import (
    get_analyzer_registry,
    reset_registry,
)
from robot_optimizer_core.api import analyze_directory, analyze_file
from robot_optimizer_core.context import create_test_application
from robot_optimizer_core.domain.value_objects import PatternType
from robot_optimizer_core.exceptions import AnalysisError

# ---------------------------------------------------------------------------
# Fix 1: ApplicationContext registers all 8 built-in analyzers
# ---------------------------------------------------------------------------

@pytest.mark.component
class TestApplicationContextAnalyzerCoverage:
    """All 8 built-in analyzers must be available through ApplicationContext."""

    EXPECTED = {
        "dead_code",
        "sleep_detector",
        "flakiness",
        "hardcoded_value",
        "naming_convention",
        "setup_teardown",
        "tag_consistency",
        "test_documentation",
    }

    def test_context_registry_has_all_builtins(self) -> None:
        with create_test_application() as ctx:
            registered = set(ctx.analyzer_registry.list())
        missing = self.EXPECTED - registered
        assert not missing, f"ApplicationContext missing analyzers: {missing}"

    def test_context_registry_analyzers_are_instantiable(self) -> None:
        with create_test_application() as ctx:
            for name in self.EXPECTED - {"flakiness"}:  # flakiness needs external repo
                instance = ctx.analyzer_registry.create(name)
                assert instance is not None, f"Could not instantiate {name}"


# ---------------------------------------------------------------------------
# Fix 2: reset_registry allows re-initialisation of the global registry
# ---------------------------------------------------------------------------

@pytest.mark.component
class TestRegistryReset:
    """reset_registry must give a fresh, fully-populated global registry."""

    def test_reset_then_all_builtins_available(self) -> None:
        reset_registry()
        registry = get_analyzer_registry()
        for name in ["dead_code", "sleep_detector", "hardcoded_value"]:
            assert name in registry.list()

    def test_custom_analyzer_not_present_after_reset(self) -> None:
        from robot_optimizer_core.analyzers import BaseAnalyzer
        from robot_optimizer_core.domain.entities import TestFile
        from robot_optimizer_core.domain.value_objects import Finding

        class _Probe(BaseAnalyzer):
            @property
            def name(self) -> str:
                return "_probe"

            @property
            def description(self) -> str:
                return "probe"

            def analyze(self, test_file: TestFile) -> list[Finding]:
                return []

        registry = get_analyzer_registry()
        registry.register("_probe", _Probe, override=True)
        assert "_probe" in registry.list()
        reset_registry()
        assert "_probe" not in get_analyzer_registry().list()


# ---------------------------------------------------------------------------
# Fix 3: Settings extra="forbid" catches typos in configuration keys
# ---------------------------------------------------------------------------

@pytest.mark.component
class TestSettingsStrictness:
    def test_unknown_key_raises_at_settings_construction(self) -> None:
        from pydantic import ValidationError

        from robot_optimizer_core.config import Settings

        with pytest.raises((ValidationError, TypeError)):
            Settings(this_key_does_not_exist="boom")

    def test_valid_keys_construct_without_error(self) -> None:
        from robot_optimizer_core.config import Settings

        s = Settings(max_file_size_mb=2.0, log_level="WARNING")
        assert s.max_file_size_mb == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# Fix 4: AST-based dead-code extraction — setup/teardown and IF blocks
# ---------------------------------------------------------------------------

@pytest.mark.component
class TestDeadCodeASTWorkflow:
    """End-to-end dead-code analysis using the AST extraction path."""

    def _analyze(self, tmp_path: Path, content: str) -> list:
        f = tmp_path / "suite.robot"
        f.write_bytes(content.encode("utf-8"))
        return analyze_file(f, analyzers=["dead_code"])

    def test_setup_keyword_no_false_positive(self, tmp_path: Path) -> None:
        content = (
            "*** Test Cases ***\n"
            "My Test\n"
            "    [Setup]    Prepare Environment\n"
            "    Log    running\n"
            "\n"
            "*** Keywords ***\n"
            "Prepare Environment\n"
            "    Log    ready\n"
        )
        findings = self._analyze(tmp_path, content)
        unused = [f for f in findings if f.pattern.type == PatternType.UNUSED_KEYWORD]
        names = [f.context["keyword_name"] for f in unused]
        assert "Prepare Environment" not in names

    def test_teardown_keyword_no_false_positive(self, tmp_path: Path) -> None:
        content = (
            "*** Test Cases ***\n"
            "My Test\n"
            "    Log    running\n"
            "    [Teardown]    Clean Up\n"
            "\n"
            "*** Keywords ***\n"
            "Clean Up\n"
            "    Log    cleaned\n"
        )
        findings = self._analyze(tmp_path, content)
        unused = [f for f in findings if f.pattern.type == PatternType.UNUSED_KEYWORD]
        names = [f.context["keyword_name"] for f in unused]
        assert "Clean Up" not in names

    def test_if_branch_keyword_no_false_positive(self, tmp_path: Path) -> None:
        content = (
            "*** Test Cases ***\n"
            "My Test\n"
            "    IF    ${flag}\n"
            "        Branch Action\n"
            "    END\n"
            "\n"
            "*** Keywords ***\n"
            "Branch Action\n"
            "    Log    branch\n"
        )
        findings = self._analyze(tmp_path, content)
        unused = [f for f in findings if f.pattern.type == PatternType.UNUSED_KEYWORD]
        assert len(unused) == 0

    def test_genuinely_unused_keyword_still_detected(self, tmp_path: Path) -> None:
        content = (
            "*** Test Cases ***\n"
            "My Test\n"
            "    [Setup]    Used Keyword\n"
            "\n"
            "*** Keywords ***\n"
            "Used Keyword\n"
            "    Log    ok\n"
            "\n"
            "Dead Weight\n"
            "    Log    never\n"
        )
        findings = self._analyze(tmp_path, content)
        unused = [f for f in findings if f.pattern.type == PatternType.UNUSED_KEYWORD]
        assert len(unused) == 1
        assert unused[0].context["keyword_name"] == "Dead Weight"


# ---------------------------------------------------------------------------
# Fix 5: fail_fast is honoured even with max_workers > 1
# ---------------------------------------------------------------------------

@pytest.mark.component
class TestFailFastBehaviour:
    def test_fail_fast_stops_after_first_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import robot_optimizer_core.api as api_mod

        for i in range(4):
            (tmp_path / f"t{i}.robot").write_bytes(
                b"*** Test Cases ***\nT\n    Log    hi\n"
            )

        call_count = 0

        def fail_all(path: Path, *a: object, **kw: object) -> list:
            nonlocal call_count
            call_count += 1
            raise AnalysisError("forced", file_path=path)

        monkeypatch.setattr(api_mod, "analyze_file", fail_all)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            with pytest.raises(AnalysisError):
                analyze_directory(tmp_path, max_workers=4, fail_fast=True)

        assert call_count == 1

    def test_no_fail_fast_processes_all_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import robot_optimizer_core.api as api_mod

        for i in range(3):
            (tmp_path / f"t{i}.robot").write_bytes(
                b"*** Test Cases ***\nT\n    Log    hi\n"
            )

        call_count = 0

        def fail_all(path: Path, *a: object, **kw: object) -> list:
            nonlocal call_count
            call_count += 1
            raise AnalysisError("forced", file_path=path)

        monkeypatch.setattr(api_mod, "analyze_file", fail_all)

        result = analyze_directory(tmp_path, max_workers=1, error_handling="warn")
        assert call_count == 3
        assert len(result.errors) == 3  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Pattern type integrity across the full analyzer workflow
# ---------------------------------------------------------------------------

@pytest.mark.component
class TestPatternTypeIntegrity:
    def test_naming_convention_emits_camel_case_type(self, tmp_path: Path) -> None:
        from datetime import UTC, datetime

        from robot_optimizer_core.analyzers.naming_convention import (
            NamingConventionAnalyzer,
        )
        from robot_optimizer_core.domain.entities import TestFile

        content = '*** Test Cases ***\nLoginPage\n    Log    hi\n'
        f = tmp_path / 't.robot'
        f.write_bytes(content.encode())
        tf = TestFile(path=f, content=content, size_bytes=len(content), last_modified_utc=datetime.now(UTC))
        findings = NamingConventionAnalyzer().analyze(tf)
        assert any(fi.pattern.type == PatternType.CAMEL_CASE_NAME for fi in findings)

    def test_tag_consistency_emits_semantic_types(self, tmp_path: Path) -> None:
        from datetime import UTC, datetime

        from robot_optimizer_core.analyzers.tag_consistency import (
            TagConsistencyAnalyzer,
        )
        from robot_optimizer_core.domain.entities import TestFile

        def _tf(name: str, content: str) -> TestFile:
            f = tmp_path / name
            f.write_bytes(content.encode())
            return TestFile(path=f, content=content, size_bytes=len(content), last_modified_utc=datetime.now(UTC))

        findings = TagConsistencyAnalyzer(config={'singleton_threshold': 2}).analyze(
            _tf('a.robot', '*** Test Cases ***\nMy Test\n    [Tags]    unique_xyz\n'))
        assert any(fi.pattern.type == PatternType.SINGLETON_TAG for fi in findings)

        findings2 = TagConsistencyAnalyzer().analyze(
            _tf('b.robot', '*** Test Cases ***\nMy Test\n    [Tags]    Robot:Skip\n'))
        assert any(fi.pattern.type == PatternType.RESERVED_TAG for fi in findings2)

        findings3 = TagConsistencyAnalyzer().analyze(
            _tf('c.robot', '*** Test Cases ***\nMy Test\n    Log    hi\n'))
        assert any(fi.pattern.type == PatternType.NO_TAGS for fi in findings3)


# ---------------------------------------------------------------------------
# Global state isolation
# ---------------------------------------------------------------------------

@pytest.mark.component
class TestGlobalStateIsolation:
    def test_reset_registry_produces_fresh_registry(self) -> None:
        r1 = get_analyzer_registry()
        reset_registry()
        r2 = get_analyzer_registry()
        assert r1 is not r2
        assert len(r2.list()) > 0

    def test_reset_container_produces_fresh_container(self) -> None:
        from robot_optimizer_core.di import get_container, reset_container

        c1 = get_container()
        reset_container()
        c2 = get_container()
        assert c1 is not c2

    def test_sleep_detector_alias_identity(self) -> None:
        from robot_optimizer_core.analyzers.sleep_detector import (
            SleepDetector,
            SleepDetectorAnalyzer,
        )
        assert SleepDetector is SleepDetectorAnalyzer
        assert SleepDetector().name == 'sleep_detector'
