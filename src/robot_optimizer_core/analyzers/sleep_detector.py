# src/robot_optimizer_core/analyzers/sleep_detector.py
"""Sleep pattern detector for Robot Framework tests.

This analyzer detects usage of Sleep keywords that make tests slow
and fragile. It identifies various sleep patterns and suggests
better alternatives.

Example:
    Using the sleep detector::
    
        from robot_optimizer_core.analyzers import SleepDetector
        from robot_optimizer_core import TestFile
        
        analyzer = SleepDetector()
        test_file = TestFile.from_path("tests/login.robot")
        findings = analyzer.analyze(test_file)
        
        for finding in findings:
            duration = finding.context.get('duration_seconds')
            print(f"Sleep {duration}s at line {finding.line_number}")
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from ..config import get_settings
from ..domain.entities import TestFile
from ..domain.value_objects import Finding, Location, Pattern, Severity, SleepPattern
from .base import BaseAnalyzer


class SleepDetector(BaseAnalyzer):
    """Detects sleep usage in Robot Framework tests.
    
    This analyzer finds Sleep keyword usage and categorizes findings
    by severity based on duration. It suggests appropriate wait
    conditions as replacements.
    
    Configuration:
        severity_thresholds: Dict mapping duration to severity.
        suggest_alternatives: Whether to suggest replacements.
        check_builtin_sleep: Check BuiltIn.Sleep usage.
        check_custom_sleep: Check custom sleep implementations.
    """
    
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize the analyzer.
        
        Args:
            config: Analyzer configuration.
        """
        super().__init__(config)
        
        # Get severity thresholds from settings
        settings = get_settings()
        max_acceptable = settings.max_acceptable_sleep_seconds
        
        # Default thresholds
        self._severity_thresholds = self.get_config_value(
            "severity_thresholds",
            {
                "info": max_acceptable,  # <= 1s by default
                "warning": max_acceptable * 5,  # <= 5s
                "error": float('inf')  # > 5s
            }
        )
        
        # Configuration
        self._suggest_alternatives = self.get_config_value("suggest_alternatives", True)
        self._check_builtin = self.get_config_value("check_builtin_sleep", True)
        self._check_custom = self.get_config_value("check_custom_sleep", True)
        
        # Compile patterns
        self._sleep_patterns = self._compile_sleep_patterns()
    
    @property
    def name(self) -> str:
        """Get analyzer name.
        
        Returns:
            Analyzer name.
        """
        return "sleep_detector"
    
    @property
    def description(self) -> str:
        """Get analyzer description.
        
        Returns:
            Analyzer description.
        """
        return "Finds Sleep keyword usage that makes tests slow and fragile"
    
    @property
    def tags(self) -> list[str]:
        """Get analyzer tags.
        
        Returns:
            List of tags.
        """
        return ["performance", "stability", "wait-conditions"]
    
    @property
    def supports_auto_fix(self) -> bool:
        """Check if analyzer supports auto-fixing.
        
        Returns:
            True (sleep can be replaced with waits).
        """
        return True
    
    def analyze(self, test_file: TestFile) -> list[Finding]:
        """Find all sleep patterns in the test file.
        
        Args:
            test_file: The test file to analyze.
            
        Returns:
            List of findings.
        """
        findings = []
        lines = test_file.content.splitlines()
        
        for line_num, line in enumerate(lines, 1):
            if sleep_info := self._detect_sleep(line):
                if finding := self._create_finding(
                    sleep_info,
                    test_file,
                    line_num,
                    line.strip()
                ):
                    findings.append(finding)
        
        return findings
    
    def _compile_sleep_patterns(self) -> list[tuple[re.Pattern, str]]:
        """Compile regex patterns for sleep detection.
        
        Returns:
            List of (pattern, type) tuples.
        """
        patterns = []
        
        if self._check_builtin:
            # Standard Sleep keyword
            patterns.append((
                re.compile(
                    r'^\s*Sleep\s+(\d+(?:\.\d+)?)\s*(s|seconds?|m|minutes?|ms|milliseconds?)?',
                    re.IGNORECASE
                ),
                "builtin"
            ))
            
            # BuiltIn.Sleep format
            patterns.append((
                re.compile(
                    r'^\s*BuiltIn\.Sleep\s+(\d+(?:\.\d+)?)\s*(s|seconds?|m|minutes?|ms|milliseconds?)?',
                    re.IGNORECASE
                ),
                "builtin_qualified"
            ))
        
        if self._check_custom:
            # Custom sleep patterns (common variations)
            patterns.append((
                re.compile(
                    r'^\s*(?:Wait|Pause|Delay)\s+(\d+(?:\.\d+)?)\s*(s|seconds?|m|minutes?)?',
                    re.IGNORECASE
                ),
                "custom"
            ))
            
            # Sleep with variable
            patterns.append((
                re.compile(
                    r'^\s*Sleep\s+\$\{([^}]+)\}',
                    re.IGNORECASE
                ),
                "variable"
            ))
        
        return patterns
    
    def _detect_sleep(self, line: str) -> dict[str, Any] | None:
        """Detect sleep pattern in a line.
        
        Args:
            line: Line to check.
            
        Returns:
            Sleep information dict or None.
        """
        for pattern, sleep_type in self._sleep_patterns:
            if match := pattern.match(line):
                match sleep_type:
                    case "variable":
                        # Variable sleep - can't determine duration
                        return {
                            "type": sleep_type,
                            "variable": match.group(1),
                            "duration": None,
                            "unit": None
                        }
                    case _:
                        # Numeric sleep
                        duration_str = match.group(1)
                        unit = match.group(2) if match.lastindex >= 2 else 's'
                        
                        try:
                            duration = Decimal(duration_str)
                            return {
                                "type": sleep_type,
                                "duration": duration,
                                "unit": unit.lower() if unit else 's',
                                "duration_str": duration_str
                            }
                        except (ValueError, InvalidOperation):
                            self._logger.warning(
                                f"Invalid sleep duration: {duration_str}",
                                extra={"line": line}
                            )
                            return None
        
        return None
    
    def _create_finding(
        self,
        sleep_info: dict[str, Any],
        test_file: TestFile,
        line_num: int,
        original_text: str
    ) -> Finding | None:
        """Create a finding from sleep information.
        
        Args:
            sleep_info: Sleep detection information.
            test_file: The test file.
            line_num: Line number.
            original_text: Original line text.
            
        Returns:
            Finding object or None.
        """
        # Handle variable sleep
        if sleep_info["duration"] is None:
            pattern = Pattern(
                type=PatternType.SLEEP_IN_TEST,
                name="Variable Sleep",
                description=f"Sleep with variable duration: ${{{sleep_info['variable']}}}",
                recommendation="Replace with explicit wait condition",
                auto_fixable=False  # Can't auto-fix without knowing duration
            )
            
            return Finding.create(
                pattern=pattern,
                severity=Severity.WARNING,
                location=Location(file_path=test_file.path, line=line_num),
                message=f"Sleep with variable duration makes tests unpredictable",
                sleep_type=sleep_info["type"],
                variable_name=sleep_info["variable"],
                original_text=original_text
            )
        
        # Create sleep pattern value object
        try:
            sleep_pattern = SleepPattern(
                duration=sleep_info["duration"],
                unit=sleep_info["unit"],
                line_number=line_num,
                original_text=original_text
            )
        except ValueError as e:
            self._logger.error(f"Invalid sleep pattern: {e}")
            return None
        
        # Determine severity based on duration
        severity = self._determine_severity(sleep_pattern.duration_in_seconds)
        
        # Create pattern with duration
        pattern = Pattern.sleep_in_test(
            f"{sleep_info['duration']} {sleep_info['unit']}"
        )
        
        # Build message with suggestion
        message = f"Sleep {sleep_info['duration']} {sleep_info['unit']} makes tests slow and fragile"
        
        if self._suggest_alternatives:
            if suggestion := self._suggest_alternative(sleep_pattern, test_file, line_num):
                message += f". {suggestion}"
        
        return Finding.create(
            pattern=pattern,
            severity=severity,
            location=Location(file_path=test_file.path, line=line_num),
            message=message,
            duration=str(sleep_info["duration"]),
            unit=sleep_info["unit"],
            duration_seconds=sleep_pattern.duration_in_seconds,
            sleep_type=sleep_info["type"],
            original_text=original_text,
            auto_fixable=True
        )
    
    def _determine_severity(self, duration_seconds: float) -> Severity:
        """Determine severity based on sleep duration.
        
        Args:
            duration_seconds: Duration in seconds.
            
        Returns:
            Severity level.
        """
        match duration_seconds:
            case d if d <= self._severity_thresholds["info"]:
                return Severity.INFO
            case d if d <= self._severity_thresholds["warning"]:
                return Severity.WARNING
            case _:
                return Severity.ERROR
    
    def _suggest_alternative(
        self,
        sleep_pattern: SleepPattern,
        test_file: TestFile,
        line_num: int
    ) -> str | None:
        """Suggest alternative to sleep.
        
        Args:
            sleep_pattern: The sleep pattern.
            test_file: The test file.
            line_num: Line number of sleep.
            
        Returns:
            Suggestion text or None.
        """
        # Look at context to determine best alternative
        lines = test_file.content.splitlines()
        
        # Check what comes after sleep
        if line_num < len(lines):
            next_line = lines[line_num].strip()
            
            # Common patterns and their alternatives
            match next_line.lower():
                case line if any(kw in line for kw in ['click', 'element', 'button']):
                    return "Consider 'Wait Until Element Is Visible' or 'Wait Until Element Is Enabled'"
                case line if 'page' in line:
                    return "Consider 'Wait Until Page Contains' or 'Wait Until Page Does Not Contain'"
                case line if any(kw in line for kw in ['should', 'verify', 'check']):
                    return "Consider 'Wait Until Keyword Succeeds' with the verification"
        
        # Generic suggestion based on duration
        match sleep_pattern.duration_in_seconds:
            case d if d < 1:
                return "For sub-second waits, consider if this is really needed"
            case d if d < 5:
                return "Replace with explicit wait condition like 'Wait Until Element Is Visible'"
            case _:
                return "Long sleeps indicate missing synchronization - use proper wait conditions"
    
    def validate_config(self) -> None:
        """Validate analyzer configuration.
        
        Raises:
            ConfigurationError: If configuration is invalid.
        """
        # Validate severity thresholds
        thresholds = self._severity_thresholds
        
        if not isinstance(thresholds, dict):
            from ..exceptions import ConfigurationError
            raise ConfigurationError(
                "Severity thresholds must be a dictionary",
                config_key="severity_thresholds",
                provided_value=type(thresholds).__name__
            )
        
        required_keys = {"info", "warning", "error"}
        if missing := required_keys - set(thresholds.keys()):
            from ..exceptions import ConfigurationError
            raise ConfigurationError(
                f"Missing severity thresholds: {missing}",
                config_key="severity_thresholds",
                provided_value=list(thresholds.keys())
            )
        
        # Validate threshold values are numbers
        for key, value in thresholds.items():
            if not isinstance(value, (int, float)):
                from ..exceptions import ConfigurationError
                raise ConfigurationError(
                    f"Threshold '{key}' must be numeric",
                    config_key=f"severity_thresholds.{key}",
                    provided_value=value
                )