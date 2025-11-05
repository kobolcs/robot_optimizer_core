# tests/unit/domain/test_value_objects_coverage.py
"""Additional tests for value objects to reach 90% coverage."""
from datetime import datetime
from pathlib import Path

import pytest
from robot_optimizer_core.domain.value_objects import (
    Finding,
    Location,
    OptimizationSuggestion,
    OptimizationType,
    Pattern,
    PatternType,
    Severity,
)


class TestLocationCoverage:
    """Complete coverage for Location value object."""

    def test_location_contains_edge_cases(self):
        """Test all branches of contains method."""
        # Test with columns on end line
        outer = Location(
            file_path=Path("test.robot"),
            line=10,
            column=5,
            end_line=15,
            end_column=20
        )

        # Test point after end column on end line
        point = Location(
            file_path=Path("test.robot"),
            line=15,
            column=25
        )
        assert not outer.contains(point)

        # Test with no column info
        loc_no_col = Location(
            file_path=Path("test.robot"),
            line=12
        )
        assert outer.contains(loc_no_col)

    def test_location_range_str_variations(self):
        """Test all range_str format variations."""
        # With end line but no end column
        loc = Location(
            file_path=Path("test.robot"),
            line=10,
            column=5,
            end_line=15
        )
        assert loc.range_str == "test.robot:10:5-15:"


class TestFindingCoverage:
    """Complete coverage for Finding value object."""

    def test_finding_format_console_no_recommendation_diff(self):
        """Test format_console when recommendation equals message."""
        pattern = Pattern(
            type=PatternType.DUPLICATE_KEYWORD,
            name="Duplicate",
            description="Duplicate found",
            recommendation="Duplicate found"  # Same as message
        )

        finding = Finding.create(
            pattern=pattern,
            severity=Severity.ERROR,
            location=Location(Path("test.robot"), 10),
            message="Duplicate found"
        )

        output = finding.format_for_console()
        assert output.count("Duplicate found") == 1  # Should not repeat
        assert "💡" not in output  # No recommendation emoji

    def test_finding_to_dict_full(self):
        """Test to_dict with all fields populated."""
        pattern = Pattern.sleep_in_test("2s")
        finding = Finding.create(
            pattern=pattern,
            severity=Severity.WARNING,
            location=Location(Path("test.robot"), 10, 5),
            message="Sleep detected",
            duration="2s",
            line_text="Sleep    2s"
        )

        data = finding.to_dict()
        assert data["pattern_type"] == "SLEEP_IN_TEST"
        assert data["pattern_name"] == pattern.name
        assert data["recommendation"] == pattern.recommendation
        assert data["line_number"] == 10
        assert data["is_auto_fixable"] is True


class TestOptimizationSuggestionCoverage:
    """Complete coverage for OptimizationSuggestion."""

    def test_optimization_risk_levels(self):
        """Test all risk level calculations."""
        finding = Finding.create(
            pattern=Pattern.sleep_in_test("1s"),
            severity=Severity.WARNING,
            location=Location(Path("test.robot"), 1),
            message="Test"
        )

        # High risk (not safe)
        high_risk = OptimizationSuggestion(
            finding_id=str(finding.id),
            optimization_type=OptimizationType.REMOVE_DUPLICATE,
            description="Risky change",
            original_code="old",
            suggested_code="new",
            confidence=0.9,
            estimated_impact="High",
            is_safe=False
        )
        assert high_risk.risk_level == "high"

        # Medium risk (low confidence)
        medium_risk = OptimizationSuggestion(
            finding_id=str(finding.id),
            optimization_type=OptimizationType.REPLACE_SLEEP,
            description="Medium confidence",
            original_code="old",
            suggested_code="new",
            confidence=0.4,
            estimated_impact="Medium",
            is_safe=True
        )
        assert medium_risk.risk_level == "medium"

        # Low risk
        low_risk = OptimizationSuggestion(
            finding_id=str(finding.id),
            optimization_type=OptimizationType.SIMPLIFY_XPATH,
            description="Safe change",
            original_code="old",
            suggested_code="new",
            confidence=0.7,
            estimated_impact="Low",
            is_safe=True
        )
        assert low_risk.risk_level == "low"

        # Minimal risk
        minimal_risk = OptimizationSuggestion(
            finding_id=str(finding.id),
            optimization_type=OptimizationType.USE_VARIABLE,
            description="Very safe",
            original_code="old",
            suggested_code="new",
            confidence=0.9,
            estimated_impact="Low",
            is_safe=True
        )
        assert minimal_risk.risk_level == "minimal"

    def test_optimization_model_dump_json_mode(self):
        """Test model_dump includes computed fields in JSON mode."""
        finding = Finding.create(
            pattern=Pattern.sleep_in_test("1s"),
            severity=Severity.WARNING,
            location=Location(Path("test.robot"), 1),
            message="Test"
        )

        suggestion = OptimizationSuggestion(
            finding_id=str(finding.id),
            optimization_type=OptimizationType.REPLACE_SLEEP,
            description="Replace sleep",
            original_code="Sleep    1s",
            suggested_code="Wait Until",
            confidence=0.85,
            estimated_impact="High",
            prerequisites=["Import SeleniumLibrary"]
        )

        # JSON mode should include computed fields
        json_data = suggestion.model_dump(mode='json')
        assert json_data['is_high_confidence'] is True
        assert json_data['requires_prerequisites'] is True
        assert json_data['risk_level'] == "minimal"

        # Normal mode might not include them
        normal_data = suggestion.model_dump()
        assert 'finding_id' in normal_data


class TestPatternCoverage:
    """Complete coverage for Pattern value object."""

    def test_pattern_all_categories(self):
        """Ensure all PatternType values have proper categories."""
        # Test patterns that might return "Other"
        for pattern_type in PatternType:
            pattern = Pattern(
                type=pattern_type,
                name=f"Test {pattern_type.name}",
                description="Test description",
                recommendation="Test recommendation"
            )
            # All our pattern types should have defined categories
            assert pattern.category != "Other"

    def test_pattern_factory_with_custom_threshold(self):
        """Test factory method with custom parameters."""
        pattern = Pattern.long_test_case(100, threshold=75)
        assert "100 lines" in pattern.description
        assert "threshold: 75" in pattern.description


class TestFlakinessCoverage:
    """Additional tests for flakiness-related value objects."""

    def test_flakiness_stats_edge_cases(self):
        """Test FlakinessStats edge cases."""
        from robot_optimizer_core.domain.value_objects.flakiness_stats import FlakinessStats

        # Test with no failures but many runs
        stable = FlakinessStats(
            test_name="Stable Test",
            file_path=Path("test.robot"),
            total_runs=100,
            failures=0
        )
        assert stable.failure_rate == 0.0
        assert not stable.is_flaky  # 0% failure rate is not flaky
        assert stable.severity_level == "INFO"

        # Test 100% failure rate
        broken = FlakinessStats(
            test_name="Broken Test",
            file_path=Path("test.robot"),
            total_runs=10,
            failures=10
        )
        assert broken.failure_rate == 1.0
        assert not broken.is_flaky  # 100% failure rate is not flaky, it's broken

        # Test with too few runs
        insufficient = FlakinessStats(
            test_name="New Test",
            file_path=Path("test.robot"),
            total_runs=3,
            failures=1
        )
        assert not insufficient.is_flaky  # Less than 4 runs

        # Test severity boundaries
        low_flaky = FlakinessStats(
            test_name="Low Flaky",
            file_path=Path("test.robot"),
            total_runs=100,
            failures=3  # 3% failure rate
        )
        assert low_flaky.severity_level == "INFO"

        medium_flaky = FlakinessStats(
            test_name="Medium Flaky",
            file_path=Path("test.robot"),
            total_runs=100,
            failures=10  # 10% failure rate
        )
        assert medium_flaky.severity_level == "WARNING"


class TestTestResultCoverage:
    """Complete coverage for TestResult value object."""

    def test_test_result_skip_status(self):
        """Test SKIP status handling."""
        from robot_optimizer_core.domain.value_objects.test_result import TestResult

        result = TestResult(
            test_name="Skipped Test",
            file_path=Path("test.robot"),
            status="SKIP",
            execution_time=0.0,
            timestamp=datetime.now()
        )

        assert not result.is_failure
        assert not result.is_success

        # Test with error message on skip
        result_with_msg = TestResult(
            test_name="Skipped Test",
            file_path=Path("test.robot"),
            status="SKIP",
            execution_time=0.0,
            error_message="Skipped due to condition",
            timestamp=datetime.now()
        )
        assert result_with_msg.error_message == "Skipped due to condition"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
