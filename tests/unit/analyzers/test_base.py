# tests/unit/analyzers/test_base.py
"""Unit tests for BaseAnalyzer abstract class.

Tests cover the base analyzer functionality including hooks, validation,
configuration, and error handling.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from robot_optimizer_core.analyzers.base import BaseAnalyzer
from robot_optimizer_core.domain.entities import TestFile
from robot_optimizer_core.domain.value_objects import (
    Finding,
    Location,
    Pattern,
    PatternType,
    Severity,
)
from robot_optimizer_core.exceptions import AnalysisError, ConfigurationError


class ConcreteAnalyzer(BaseAnalyzer):
    """Concrete implementation for testing."""

    @property
    def name(self) -> str:
        return "test_analyzer"

    @property
    def description(self) -> str:
        return "Test analyzer for unit tests"

    @property
    def version(self) -> str:
        return "2.0.0"

    @property
    def tags(self) -> list[str]:
        return ["test", "unit"]

    @property
    def supports_auto_fix(self) -> bool:
        return True

    def analyze(self, test_file: TestFile) -> list[Finding]:
        """Simple analysis that returns one finding."""
        return [
            Finding.create(
                pattern=Pattern.sleep_in_test("1s"),
                severity=Severity.WARNING,
                location=Location(test_file.path, 1),
                message="Test finding"
            )
        ]


class ErrorAnalyzer(BaseAnalyzer):
    """Analyzer that throws errors for testing."""

    @property
    def name(self) -> str:
        return "error_analyzer"

    @property
    def description(self) -> str:
        return "Analyzer that throws errors"

    def analyze(self, test_file: TestFile) -> list[Finding]:
        raise RuntimeError("Analysis failed!")


@pytest.mark.unit
class TestBaseAnalyzer:
    """Test the BaseAnalyzer abstract class."""

    @pytest.fixture
    def test_file(self) -> TestFile:
        """Create a test file."""
        return TestFile(
            path=Path("test.robot"),
            content="*** Test Cases ***\nTest\n    Sleep    1s",
            size_bytes=100,
            last_modified_utc=datetime.now(UTC)
        )

    def test_create_analyzer(self) -> None:
        """Test creating analyzer with default config."""
        analyzer = ConcreteAnalyzer()

        assert analyzer.name == "test_analyzer"
        assert analyzer.description == "Test analyzer for unit tests"
        assert analyzer.version == "2.0.0"
        assert analyzer.tags == ["test", "unit"]
        assert analyzer.supports_auto_fix is True
        assert analyzer.config == {}
        assert analyzer.metrics_enabled is True

    def test_create_analyzer_with_config(self) -> None:
        """Test creating analyzer with custom config."""
        config = {"threshold": 10, "enabled": True}
        analyzer = ConcreteAnalyzer(config=config, metrics_enabled=False)

        assert analyzer.config == config
        assert analyzer.metrics_enabled is False

    def test_analyze_method(self, test_file: TestFile) -> None:
        """Test basic analyze method."""
        analyzer = ConcreteAnalyzer()
        findings = analyzer.analyze(test_file)

        assert len(findings) == 1
        assert findings[0].pattern.type == PatternType.SLEEP_IN_TEST
        assert findings[0].severity == Severity.WARNING

    def test_safe_analyze_success(self, test_file: TestFile) -> None:
        """Test safe_analyze wrapper with successful analysis."""
        analyzer = ConcreteAnalyzer()

        with patch.object(analyzer, "_metrics") as mock_metrics:
            findings = analyzer.safe_analyze(test_file)

        assert len(findings) == 1

        # Check metrics were recorded
        if mock_metrics:
            mock_metrics.increment.assert_called_with("analyzer.test_analyzer.success")
            mock_metrics.gauge.assert_called_with("analyzer.test_analyzer.findings_count", 1)

    def test_safe_analyze_with_hooks(self, test_file: TestFile) -> None:
        """Test that hooks are called during safe_analyze."""
        analyzer = ConcreteAnalyzer()

        # Mock the hooks
        analyzer.pre_analyze = Mock()
        analyzer.post_analyze = Mock(side_effect=lambda tf, f: f)

        findings = analyzer.safe_analyze(test_file)

        # Verify hooks were called
        analyzer.pre_analyze.assert_called_once_with(test_file)
        analyzer.post_analyze.assert_called_once()
        assert len(findings) == 1

    def test_safe_analyze_error_handling(self, test_file: TestFile) -> None:
        """Test safe_analyze error handling."""
        analyzer = ErrorAnalyzer()

        with pytest.raises(AnalysisError) as exc_info:
            analyzer.safe_analyze(test_file)

        assert "Analysis failed in error_analyzer" in str(exc_info.value)
        assert exc_info.value.file_path == test_file.path
        assert exc_info.value.analyzer == "error_analyzer"

    def test_validate_findings(self, test_file: TestFile) -> None:
        """Test finding validation."""
        analyzer = ConcreteAnalyzer()

        # Valid finding
        valid_finding = Finding.create(
            pattern=Pattern.sleep_in_test("1s"),
            severity=Severity.WARNING,
            location=Location(test_file.path, 2),
            message="Valid"
        )

        # Finding with wrong file path
        wrong_path = Finding.create(
            pattern=Pattern.sleep_in_test("1s"),
            severity=Severity.WARNING,
            location=Location(Path("wrong.robot"), 10),
            message="Wrong path"
        )

        # Finding with invalid line number
        invalid_line = Finding.create(
            pattern=Pattern.sleep_in_test("1s"),
            severity=Severity.WARNING,
            location=Location(test_file.path, 999),
            message="Invalid line"
        )

        test_file.content = "Line 1\nLine 2\nLine 3"  # 3 lines
        findings = [valid_finding, wrong_path, invalid_line]

        validated = analyzer._validate_findings(findings, test_file)

        # Only valid finding should remain
        assert len(validated) == 1
        assert validated[0] == valid_finding

    def test_get_config_value(self) -> None:
        """Test configuration value retrieval."""
        config = {
            "threshold": 10,
            "name": "test",
            "options": {"nested": True}
        }
        analyzer = ConcreteAnalyzer(config=config)

        # Get existing value
        assert analyzer.get_config_value("threshold") == 10
        assert analyzer.get_config_value("name") == "test"
        assert analyzer.get_config_value("options") == {"nested": True}

        # Get with default
        assert analyzer.get_config_value("missing", default=42) == 42

        # Required value exists
        assert analyzer.get_config_value("threshold", required=True) == 10

        # Required value missing
        with pytest.raises(ConfigurationError) as exc_info:
            analyzer.get_config_value("missing_required", required=True)

        assert "Required configuration key missing" in str(exc_info.value)
        assert exc_info.value.config_key == "test_analyzer.missing_required"

    def test_pre_analyze_hook(self, test_file: TestFile) -> None:
        """Test pre_analyze hook."""
        class HookAnalyzer(ConcreteAnalyzer):
            def __init__(self):
                super().__init__()
                self.pre_called = False

            def pre_analyze(self, test_file: TestFile) -> None:
                self.pre_called = True

        analyzer = HookAnalyzer()
        analyzer.safe_analyze(test_file)

        assert analyzer.pre_called

    def test_post_analyze_hook(self, test_file: TestFile) -> None:
        """Test post_analyze hook."""
        class HookAnalyzer(ConcreteAnalyzer):
            def post_analyze(self, test_file: TestFile, findings: list[Finding]) -> list[Finding]:
                # Add extra finding
                extra = Finding.create(
                    pattern=Pattern.duplicate_keyword("Test"),
                    severity=Severity.ERROR,
                    location=Location(test_file.path, 2),
                    message="Added in post"
                )
                return findings + [extra]

        analyzer = HookAnalyzer()
        findings = analyzer.safe_analyze(test_file)

        assert len(findings) == 2
        assert findings[1].message == "Added in post"

    def test_validate_config(self) -> None:
        """Test config validation."""
        class ValidatingAnalyzer(ConcreteAnalyzer):
            def validate_config(self) -> None:
                threshold = self.get_config_value("threshold", required=True)
                if threshold < 0:
                    raise ConfigurationError("Threshold must be positive")

        # Valid config
        analyzer1 = ValidatingAnalyzer(config={"threshold": 10})
        analyzer1.validate_config()  # Should not raise

        # Invalid config
        analyzer2 = ValidatingAnalyzer(config={"threshold": -5})
        with pytest.raises(ConfigurationError) as exc_info:
            analyzer2.validate_config()
        assert "Threshold must be positive" in str(exc_info.value)

        # Missing required config
        analyzer3 = ValidatingAnalyzer(config={})
        with pytest.raises(ConfigurationError):
            analyzer3.validate_config()

    def test_analyzer_repr(self) -> None:
        """Test string representation."""
        analyzer = ConcreteAnalyzer()
        repr_str = repr(analyzer)

        assert "ConcreteAnalyzer" in repr_str
        assert "name='test_analyzer'" in repr_str
        assert "version='2.0.0'" in repr_str

    def test_abstract_methods(self) -> None:
        """Test that abstract methods must be implemented."""
        # Can't instantiate without implementing abstract methods
        with pytest.raises(TypeError) as exc_info:
            BaseAnalyzer()

        assert "Can't instantiate abstract class" in str(exc_info.value)

    def test_metrics_disabled(self, test_file: TestFile) -> None:
        """Test analyzer with metrics disabled."""
        analyzer = ConcreteAnalyzer(metrics_enabled=False)

        assert analyzer._metrics is None

        # Should still work without metrics
        findings = analyzer.safe_analyze(test_file)
        assert len(findings) == 1

    def test_analysis_error_reraised(self, test_file: TestFile) -> None:
        """Test that AnalysisError is re-raised as-is."""
        class RaisesAnalysisError(BaseAnalyzer):
            @property
            def name(self) -> str:
                return "analysis_error_analyzer"

            @property
            def description(self) -> str:
                return "Raises AnalysisError"

            def analyze(self, test_file: TestFile) -> list[Finding]:
                raise AnalysisError("Custom analysis error", file_path=test_file.path)

        analyzer = RaisesAnalysisError()

        with pytest.raises(AnalysisError) as exc_info:
            analyzer.safe_analyze(test_file)

        # Should be the original error, not wrapped
        assert exc_info.value.message == "Custom analysis error"

    def test_logger_with_context(self) -> None:
        """Test that logger includes analyzer context."""
        analyzer = ConcreteAnalyzer()

        # Logger should have analyzer name in context
        assert analyzer._logger.extra["analyzer"] == "test_analyzer"
