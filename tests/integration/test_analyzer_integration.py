# tests/integration/test_analyzer_integration.py
"""Integration tests for analyzer components.

These tests verify that analyzers work correctly together and with
the infrastructure components like parsers and file discovery.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from robot_optimizer_core import (
    Container,
    DeadCodeAnalyzer,
    FileDiscoveryService,
    Finding,
    FlakinessAnalyzer,
    Settings,
    SleepDetector,
    TestFile,
    analyze_directory,
    analyze_file,
    get_analyzer_registry,
    register_analyzer,
)
from robot_optimizer_core.analyzers import BaseAnalyzer
from robot_optimizer_core.domain.repositories import TestResultRepository
from robot_optimizer_core.domain.value_objects import (
    FlakinessStats,
    Location,
    Pattern,
    Severity,
)


@pytest.mark.integration
class TestAnalyzerIntegration:
    """Test analyzer integration with other components."""

    def test_multiple_analyzers_on_same_file(self, sample_robot_file: Path) -> None:
        """Test running multiple analyzers on the same file."""
        # Load file once
        test_file = TestFile.from_path(sample_robot_file)

        # Run different analyzers
        dead_code = DeadCodeAnalyzer()
        sleep_detector = SleepDetector()

        dead_findings = dead_code.analyze(test_file)
        sleep_findings = sleep_detector.analyze(test_file)

        # Verify findings
        assert len(dead_findings) >= 2  # Unused + duplicate
        assert len(sleep_findings) >= 1  # Sleep usage

        # Check no interference between analyzers
        dead_patterns = {f.pattern.type for f in dead_findings}
        sleep_patterns = {f.pattern.type for f in sleep_findings}
        assert dead_patterns.isdisjoint(sleep_patterns)

    def test_analyzer_with_file_discovery(self, temp_dir: Path) -> None:
        """Test analyzers with file discovery service."""
        # Create multiple test files
        files = []
        for i in range(3):
            file_path = temp_dir / f"test_{i}.robot"
            content = f"""*** Test Cases ***
Test Case {i}
    Sleep    {i + 1} seconds

*** Keywords ***
Unused Keyword {i}
    Log    Never called
"""
            file_path.write_bytes(content.encode("utf-8"))
            files.append(file_path)

        # Discover files
        discovery = FileDiscoveryService()
        found_files = discovery.find_files(temp_dir, patterns=["*.robot"])

        assert len(found_files) == 3

        # Analyze each discovered file
        analyzer = SleepDetector()
        all_findings = []

        for file_path in found_files:
            test_file = TestFile.from_path(file_path)
            findings = analyzer.analyze(test_file)
            all_findings.extend(findings)

        # Verify findings from all files
        assert len(all_findings) == 3
        durations = [f.context["duration_seconds"] for f in all_findings]
        assert sorted(durations) == [1.0, 2.0, 3.0]

    def test_analyzer_registry_integration(self) -> None:
        """Test analyzer registration and retrieval."""
        registry = get_analyzer_registry()

        # Get built-in analyzers
        dead_code = registry.get("dead_code")
        sleep = registry.get("sleep_detector")

        assert isinstance(dead_code, DeadCodeAnalyzer)
        assert isinstance(sleep, SleepDetector)

        # Register custom analyzer
        class TestAnalyzer(BaseAnalyzer):
            @property
            def name(self) -> str:
                return "test_analyzer"

            @property
            def description(self) -> str:
                return "Test analyzer"

            def analyze(self, test_file: TestFile) -> list[Finding]:
                return []

        register_analyzer("test", TestAnalyzer)

        # Verify registration
        test_analyzer = registry.get("test")
        assert isinstance(test_analyzer, TestAnalyzer)
        assert "test" in registry.list()

    def test_analyzer_with_dependency_injection(
        self, mock_test_result_repository: TestResultRepository
    ) -> None:
        """Test analyzer with DI container."""
        # Set up container
        container = Container()
        container.register_instance(
            "test_result_repository", mock_test_result_repository
        )

        # Configure mock
        mock_test_result_repository.get_flakiness_stats.return_value = [
            FlakinessStats(
                test_name="Flaky Test",
                file_path=Path("test.robot"),
                total_runs=100,
                failures=10,
            )
        ]

        # Create analyzer with DI
        with container.create_scope() as scope:
            repo = scope.resolve("test_result_repository")
            analyzer = FlakinessAnalyzer(test_result_repository=repo)

            # Test file
            test_file = TestFile(
                path=Path("test.robot"),
                content="*** Test Cases ***\nFlaky Test\n    Log    test",
                size_bytes=100,
                last_modified_utc=datetime.now(UTC),
            )

            findings = analyzer.analyze(test_file)

            assert len(findings) == 1
            assert findings[0].context["failure_rate"] == 0.1

    def test_analyze_file_integration(
        self, sample_robot_file: Path, settings: Settings
    ) -> None:
        """Test high-level analyze_file function."""
        # Analyze with all default analyzers
        findings = analyze_file(sample_robot_file)

        # Should have findings from multiple analyzers
        pattern_types = {f.pattern.type for f in findings}
        assert len(pattern_types) >= 2  # Different types of issues

        # Analyze with specific analyzers
        findings = analyze_file(
            sample_robot_file, analyzers=["dead_code", "sleep_detector"]
        )

        # Verify only requested analyzers ran
        for finding in findings:
            assert finding.pattern.type.name in [
                "UNUSED_KEYWORD",
                "DUPLICATE_KEYWORD",
                "SLEEP_IN_TEST",
            ]

        # Analyze with custom settings
        strict_settings = Settings(
            max_acceptable_sleep_seconds=0.1  # Very strict
        )

        findings = analyze_file(
            sample_robot_file, analyzers=["sleep_detector"], settings=strict_settings
        )

        # All sleeps should be high severity now
        sleep_findings = [f for f in findings if "sleep" in f.message.lower()]
        assert all(
            f.severity in [Severity.WARNING, Severity.ERROR] for f in sleep_findings
        )

    def test_analyzer_error_handling_integration(self, temp_dir: Path) -> None:
        """Test error handling across analyzer components."""
        # Create invalid file
        invalid_file = temp_dir / "invalid.robot"
        invalid_file.write_bytes(b"\x00\x01\x02\x03")  # Binary content

        # File discovery should skip it
        discovery = FileDiscoveryService()
        files = discovery.find_files(temp_dir)
        assert invalid_file not in files

        # Direct analysis should fail gracefully
        with pytest.raises(Exception, match=r".+"):  # noqa: B017  # various exception types possible
            TestFile.from_path(invalid_file)

        # Create file with invalid encoding
        bad_encoding = temp_dir / "bad_encoding.robot"
        bad_encoding.write_bytes(
            "*** Test Cases ***\nTest\n    Log    Ã¢Ã¢".encode("latin-1")
        )

        # Should handle encoding issues
        try:
            test_file = TestFile.from_path(bad_encoding)
            # If it loads, analyzers should handle it
            analyzer = DeadCodeAnalyzer()
            findings = analyzer.analyze(test_file)
            # Should complete without crashing
            assert isinstance(findings, list)
        except Exception:
            # If encoding fails, that's also acceptable
            pass


@pytest.mark.integration
class TestAnalyzerChaining:
    """Test chaining multiple analyzers together."""

    def test_analyzer_pipeline(self, sample_robot_file: Path) -> None:
        """Test building an analyzer pipeline."""
        # Create a pipeline of analyzers
        analyzers = [
            DeadCodeAnalyzer(),
            SleepDetector(),
        ]

        # Load file once
        test_file = TestFile.from_path(sample_robot_file)

        # Run all analyzers and collect findings
        all_findings = []
        for analyzer in analyzers:
            findings = analyzer.safe_analyze(test_file)
            all_findings.extend(findings)

        # Group by severity
        by_severity = {}
        for finding in all_findings:
            severity = finding.severity.name
            by_severity.setdefault(severity, []).append(finding)

        # Should have findings at different severity levels
        assert len(by_severity) >= 2

        # Group by file location
        by_location = {}
        for finding in all_findings:
            line = finding.location.line
            by_location.setdefault(line, []).append(finding)

        # Findings should retain usable file-location grouping.
        assert by_location
        assert all(line >= 1 for line in by_location)

    def test_custom_analyzer_integration(self) -> None:
        """Test integrating custom analyzer with built-ins."""

        class KeywordNamingAnalyzer(BaseAnalyzer):
            """Check keyword naming conventions."""

            @property
            def name(self) -> str:
                return "keyword_naming"

            @property
            def description(self) -> str:
                return "Check keyword naming conventions"

            def analyze(self, test_file: TestFile) -> list[Finding]:
                findings = []
                lines = test_file.content.splitlines()

                for i, line in enumerate(lines, 1):
                    # Simple check for lowercase keywords
                    if line.strip() and not line.startswith((" ", "\t", "*")):
                        if any(c.islower() for c in line) and "***" not in line:
                            # Potential keyword definition
                            if line[0].islower():
                                finding = Finding.create(
                                    pattern=Pattern(
                                        type=Pattern.PatternType.MISSING_DOCUMENTATION,
                                        name="Keyword Naming",
                                        description="Keyword should start with capital",
                                        recommendation="Use CamelCase for keywords",
                                        auto_fixable=True,
                                    ),
                                    severity=Severity.INFO,
                                    location=Location(test_file.path, i),
                                    message=f"Keyword '{line.strip()}' should start with capital",
                                )
                                findings.append(finding)

                return findings

        # Register and use with other analyzers
        register_analyzer("keyword_naming", KeywordNamingAnalyzer, override=True)

        # Create test content
        content = """*** Keywords ***
login with credentials
    [Arguments]    ${user}    ${pass}
    Log    Login

Proper Keyword Name
    Log    Good

unused keyword
    Log    Never called
"""

        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="wb", suffix=".robot", delete=False) as f:
            f.write(content.encode("utf-8"))
            temp_path = Path(f.name)

        try:
            # Analyze with all registered analyzers
            findings = analyze_file(temp_path)

            # Should have findings from different analyzers
            finding_types = {f.pattern.name for f in findings}
            assert "Keyword Naming" in finding_types
            assert "Unused Keyword" in finding_types

        finally:
            temp_path.unlink()


@pytest.mark.integration
class TestRegistryResetIntegration:
    """Integration tests for reset_registry across the full stack."""

    def test_reset_then_analyze_file_works(self, tmp_path: Path) -> None:
        """After reset_registry the analysis pipeline must fully reconstruct."""
        from robot_optimizer_core.analyzers.registry import reset_registry

        f = tmp_path / "sample.robot"
        f.write_bytes(b"*** Test Cases ***\nT\n    Log    ok\n")

        reset_registry()
        findings = analyze_file(f, analyzers=["dead_code"])
        assert isinstance(findings, list)

    def test_reset_restores_all_builtins_at_integration_level(self) -> None:
        from robot_optimizer_core.analyzers.registry import (
            get_analyzer_registry,
            reset_registry,
        )

        reset_registry()
        registry = get_analyzer_registry()
        expected = {
            "dead_code",
            "sleep_detector",
            "hardcoded_value",
            "naming_convention",
            "setup_teardown",
            "tag_consistency",
            "test_documentation",
        }
        missing = expected - set(registry.list())
        assert not missing, f"Missing after reset: {missing}"


@pytest.mark.integration
class TestDeadCodeASTIntegration:
    """Integration tests for AST-based dead-code detection on real files."""

    def test_setup_teardown_no_false_positives(self, temp_dir: Path) -> None:
        content = (
            "*** Test Cases ***\n"
            "Suite Test\n"
            "    [Setup]    Suite Prepare\n"
            "    Log    body\n"
            "    [Teardown]    Suite Cleanup\n"
            "\n"
            "*** Keywords ***\n"
            "Suite Prepare\n"
            "    Log    prepare\n"
            "\n"
            "Suite Cleanup\n"
            "    Log    cleanup\n"
        )
        f = temp_dir / "ast_test.robot"
        f.write_bytes(content.encode("utf-8"))

        findings = analyze_file(f, analyzers=["dead_code"])
        unused_names = [
            finding.context["keyword_name"]
            for finding in findings
            if finding.pattern.type.name == "UNUSED_KEYWORD"
        ]
        assert "Suite Prepare" not in unused_names
        assert "Suite Cleanup" not in unused_names

    def test_nested_if_keyword_no_false_positive(self, temp_dir: Path) -> None:
        content = (
            "*** Test Cases ***\n"
            "Branch Test\n"
            "    IF    ${env} == 'prod'\n"
            "        Production Step\n"
            "    ELSE\n"
            "        Development Step\n"
            "    END\n"
            "\n"
            "*** Keywords ***\n"
            "Production Step\n"
            "    Log    prod\n"
            "\n"
            "Development Step\n"
            "    Log    dev\n"
        )
        f = temp_dir / "if_test.robot"
        f.write_bytes(content.encode("utf-8"))

        findings = analyze_file(f, analyzers=["dead_code"])
        unused_names = [
            finding.context["keyword_name"]
            for finding in findings
            if finding.pattern.type.name == "UNUSED_KEYWORD"
        ]
        assert "Production Step" not in unused_names
        assert "Development Step" not in unused_names


@pytest.mark.integration
class TestFailFastIntegration:
    """Integration tests verifying fail_fast behaviour with real files."""

    def test_fail_fast_with_unreadable_content(self, temp_dir: Path) -> None:
        """fail_fast=True should surface the first error and stop."""
        # Create a valid file and a binary file that will fail parsing
        valid = temp_dir / "a_valid.robot"
        valid.write_bytes(b"*** Test Cases ***\nT\n    Log    hi\n")
        bad = temp_dir / "b_bad.robot"
        bad.write_bytes(b"\x00\x01\x02\x03\xff")  # binary → parse error

        with pytest.raises(Exception, match=r".+"):
            analyze_directory(temp_dir, analyzers=["dead_code"], fail_fast=True)


@pytest.mark.integration
@pytest.mark.slow
class TestAnalyzerPerformance:
    """Test analyzer performance with larger files."""

    def test_analyzer_performance_large_file(
        self, large_robot_file: Path, settings: Settings
    ) -> None:
        """Test analyzer performance on large files."""
        from time import time

        # Time file loading
        start = time()
        test_file = TestFile.from_path(large_robot_file)
        load_time = time() - start

        assert load_time < 1.0  # Should load in under 1 second
        assert test_file.line_count == len(test_file.content.split("\n"))

        # Time analysis
        analyzer = SleepDetector()

        start = time()
        findings = analyzer.analyze(test_file)
        analyze_time = time() - start

        assert analyze_time < 2.0  # Should analyze in under 2 seconds
        assert len(findings) == 1000  # One sleep per test case

        # Test memory efficiency
        import sys

        findings_size = sys.getsizeof(findings)
        avg_size_per_finding = findings_size / len(findings)

        # Each finding should be reasonably sized
        assert avg_size_per_finding < 10_000  # Less than 10KB per finding


# ---------------------------------------------------------------------------
# reset_container integration
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestResetContainerIntegration:
    def test_get_container_after_reset_returns_new_instance(self) -> None:
        from robot_optimizer_core.di import get_container, reset_container

        c1 = get_container()
        reset_container()
        c2 = get_container()
        assert c1 is not c2

    def test_reset_container_idempotent(self) -> None:
        from robot_optimizer_core.di import reset_container
        reset_container()
        reset_container()

    def test_get_container_after_double_reset_is_usable(self) -> None:
        from robot_optimizer_core.di import get_container, reset_container
        reset_container()
        reset_container()
        c = get_container()
        assert c is not None


# ---------------------------------------------------------------------------
# SleepDetectorAnalyzer rename integration
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestSleepDetectorAnalyzerIntegration:
    def test_alias_and_canonical_produce_same_findings(self, sample_robot_file: Path) -> None:
        from robot_optimizer_core.analyzers.sleep_detector import (
            SleepDetector,
            SleepDetectorAnalyzer,
        )

        tf = TestFile.from_path(sample_robot_file)
        f1 = SleepDetector().safe_analyze(tf)
        f2 = SleepDetectorAnalyzer().safe_analyze(tf)
        assert len(f1) == len(f2)
        for a, b in zip(f1, f2, strict=True):
            assert a.pattern == b.pattern
            assert a.location == b.location
            assert a.severity == b.severity

    def test_explicit_config_uses_provided_thresholds(self) -> None:
        from robot_optimizer_core.analyzers.sleep_detector import SleepDetectorAnalyzer

        cfg = {'severity_thresholds': {'info': 0.5, 'warning': 2.0, 'error': float('inf')}}
        analyzer = SleepDetectorAnalyzer(config=cfg)
        assert analyzer._severity_thresholds['info'] == 0.5
        assert analyzer._severity_thresholds['warning'] == 2.0
