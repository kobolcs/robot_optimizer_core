# tests/conftest.py
"""Pytest configuration and shared fixtures for Robot Framework Optimizer Core tests.

This module provides common fixtures and configuration for all test levels:
- Unit tests: Fast, isolated tests with mocks
- Integration tests: Component interaction tests
- Component tests: End-to-end workflow tests
"""

from __future__ import annotations

# Prevent pytest from collecting imported domain model classes as test classes.
try:
    from robot_optimizer_core.domain.entities import TestFile as _DomainTestFile

    _DomainTestFile.__test__ = False
except Exception:
    pass

try:
    from robot_optimizer_core.domain.value_objects import (
        TestResult as _DomainTestResult,
    )

    _DomainTestResult.__test__ = False
except Exception:
    pass


import tempfile
from collections.abc import Generator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import Mock
from uuid import uuid4

import pytest

from robot_optimizer_core import (
    Settings,
    TestFile,
    configure_logging,
    configure_metrics,
    reset_settings,
)
from robot_optimizer_core.composition.container import ThreadSafeContainer as Container
from robot_optimizer_core.domain.repositories import TestResultRepository
from robot_optimizer_core.domain.value_objects import FlakinessStats, TestResult

# Configure logging for tests
configure_logging(level="WARNING", format_json=False)
configure_metrics(enabled=False)  # Disable metrics in tests

# Test file paths
_TEST_LOGIN_FILE = "tests/login.robot"


def pytest_collection_modifyitems(config, items):
    """Modify test collection to skip certain patterns."""
    pass  # Keep for future use


def pytest_ignore_collect(collection_path, config):
    """Ignore certain files/patterns during collection."""
    # Ignore .skip files
    if collection_path.suffix == ".skip":
        return True
    return False


def pytest_pycollect_makeitem(collector, name, obj):
    """Control which classes are collected as test classes.

    Prevent pytest from collecting domain model classes (TestFile, TestResult, etc.)
    that happen to start with 'Test' but aren't actually test classes.
    """
    # List of class names to ignore (domain models, not test classes)
    ignored_classes = {"TestFile", "TestResult", "TZAwareTestFile"}

    if name in ignored_classes:
        # Return None to tell pytest not to collect this
        return


# Test data constants
SAMPLE_ROBOT_CONTENT = """*** Settings ***
Documentation    Sample test suite for testing
Library          SeleniumLibrary

*** Variables ***
${URL}           https://example.com
${BROWSER}       chrome

*** Test Cases ***
Valid Login Test
    [Documentation]    Test valid user login
    Open Browser    ${URL}    ${BROWSER}
    Input Text      id=username    testuser
    Input Text      id=password    testpass
    Click Button    id=login
    Page Should Contain    Welcome
    Close Browser

Test With Sleep
    [Documentation]    Test that uses sleep
    Open Browser    ${URL}    ${BROWSER}
    Sleep    5 seconds
    Click Element    id=submit
    Close Browser

*** Keywords ***
Login With Credentials
    [Arguments]    ${username}    ${password}
    Input Text     id=username    ${username}
    Input Text     id=password    ${password}
    Click Button   id=login

Unused Keyword
    [Documentation]    This keyword is never used
    Log    This is unused

Login With Credentials
    [Documentation]    Duplicate keyword definition
    Log    Duplicate implementation
"""


# Fixtures
@pytest.fixture
def settings() -> Generator[Settings, None, None]:
    """Provide test settings and reset after test."""
    test_settings = Settings(
        max_file_size_mb=5.0,
        log_level="DEBUG",
        enable_metrics=False,
        plugins_enabled=False,
    )
    yield test_settings
    reset_settings()


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Provide a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_robot_file(temp_dir: Path) -> Path:
    """Create a sample robot file for testing."""
    file_path = temp_dir / "test_suite.robot"
    return write_robot_file(file_path, SAMPLE_ROBOT_CONTENT)


@pytest.fixture
def test_file(sample_robot_file: Path) -> TestFile:
    """Create a TestFile instance from sample content."""
    return TestFile.from_path(sample_robot_file)


@pytest.fixture
def empty_robot_file(temp_dir: Path) -> Path:
    """Create an empty robot file."""
    file_path = temp_dir / "empty.robot"
    return write_robot_file(file_path, "")


@pytest.fixture
def large_robot_file(temp_dir: Path) -> Path:
    """Create a large robot file for performance testing."""
    content = "*** Test Cases ***\n"
    for i in range(1000):
        content += f"""
Test Case {i}
    Log    Test case {i}
    Sleep    {(i % 10) + 1} seconds
    Should Be Equal    ${i}    ${i}
"""

    file_path = temp_dir / "large_suite.robot"
    return write_robot_file(file_path, content)


@pytest.fixture
def di_container() -> Container:
    """Provide a fresh DI container for testing."""
    return Container()


@pytest.fixture
def mock_test_result_repository() -> Mock:
    """Provide a mock test result repository."""
    mock_repo = Mock(spec=TestResultRepository)

    # Default behavior
    mock_repo.get_flakiness_stats.return_value = []
    mock_repo.get_results_for_file.return_value = []
    mock_repo.get_total_results_count.return_value = 0

    return mock_repo


@pytest.fixture
def flaky_test_stats() -> list[FlakinessStats]:
    """Provide sample flakiness statistics."""
    return [
        FlakinessStats(
            test_name="Flaky Login Test",
            file_path=Path(_TEST_LOGIN_FILE),
            total_runs=100,
            failures=15,
            last_failure=datetime.now() - timedelta(days=1),
        ),
        FlakinessStats(
            test_name="Very Flaky Test",
            file_path=Path(_TEST_LOGIN_FILE),
            total_runs=50,
            failures=25,
            last_failure=datetime.now() - timedelta(hours=6),
        ),
        FlakinessStats(
            test_name="Stable Test",
            file_path=Path(_TEST_LOGIN_FILE),
            total_runs=200,
            failures=0,
            last_failure=None,
        ),
    ]


@pytest.fixture
def test_results() -> list[TestResult]:
    """Provide sample test results."""
    base_time = datetime.now()
    return [
        TestResult(
            test_name="Login Test",
            file_path=Path(_TEST_LOGIN_FILE),
            status="PASS",
            execution_time=1.5,
            timestamp=base_time,
        ),
        TestResult(
            test_name="Login Test",
            file_path=Path(_TEST_LOGIN_FILE),
            status="FAIL",
            execution_time=2.1,
            error_message="Element not found",
            timestamp=base_time - timedelta(hours=1),
        ),
        TestResult(
            test_name="Logout Test",
            file_path=Path(_TEST_LOGIN_FILE),
            status="PASS",
            execution_time=0.8,
            timestamp=base_time - timedelta(hours=2),
        ),
    ]


# Markers
def pytest_configure(config: Any) -> None:
    """Configure custom pytest markers."""
    config.addinivalue_line("markers", "unit: Unit tests - fast and isolated")
    config.addinivalue_line(
        "markers", "integration: Integration tests - component interactions"
    )
    config.addinivalue_line(
        "markers", "component: Component tests - end-to-end workflows"
    )
    config.addinivalue_line("markers", "slow: Slow tests that should be run separately")
    config.addinivalue_line("markers", "performance: Performance tests")


# Test helpers
class TestData:
    """Container for common test data."""

    @staticmethod
    def create_robot_content(
        test_cases: list[str],
        keywords: list[str],
        variables: dict[str, str] | None = None,
    ) -> str:
        """Create robot file content from components."""
        content = "*** Settings ***\nDocumentation    Test suite\n\n"

        if variables:
            content += "*** Variables ***\n"
            for var, value in variables.items():
                content += f"{var}    {value}\n"
            content += "\n"

        if test_cases:
            content += "*** Test Cases ***\n"
            for test in test_cases:
                content += f"{test}\n"
            content += "\n"

        if keywords:
            content += "*** Keywords ***\n"
            for keyword in keywords:
                content += f"{keyword}\n"

        return content

    @staticmethod
    def create_test_file(path: Path, content: str, encoding: str = "utf-8") -> TestFile:
        """Create a test file with given content."""
        write_robot_file(path, content)
        return TestFile.from_path(path)


# Performance tracking
class PerformanceTimer:
    """Context manager for timing operations in tests."""

    def __init__(self, name: str, threshold_seconds: float = 1.0):
        """Initialize timer."""
        self.name = name
        self.threshold = threshold_seconds
        self.start_time = None
        self.duration = None

    def __enter__(self) -> PerformanceTimer:
        """Start timing."""
        import time

        self.start_time = time.time()
        return self

    def __exit__(self, *args: Any) -> None:
        """Stop timing and check threshold."""
        import time

        self.duration = time.time() - self.start_time

        if self.duration > self.threshold:
            pytest.fail(
                f"{self.name} took {self.duration:.2f}s (threshold: {self.threshold}s)"
            )


# Mock factories
class MockFactory:
    """Factory for creating mock objects."""

    @staticmethod
    def create_finding(**kwargs: Any) -> Mock:
        """Create a mock finding."""
        from robot_optimizer_core import Finding, Location, Pattern, Severity

        defaults = {
            "id": uuid4(),
            "pattern": Pattern.sleep_in_test("5s"),
            "severity": Severity.WARNING,
            "location": Location(Path("test.robot"), 10),
            "message": "Test finding",
            "context": {},
        }
        defaults.update(kwargs)

        finding = Mock(spec=Finding)
        for key, value in defaults.items():
            setattr(finding, key, value)

        return finding


# Utilities for cross-platform file handling
def write_robot_file(path: Path, content: str) -> Path:
    """Write Robot Framework content to file with consistent line endings (LF only).

    This helper ensures files always have LF line endings regardless of platform,
    preventing CRLF issues on Windows that can cause size mismatches and content
    assertion failures.

    Args:
        path: File path to write to.
        content: String content to write.

    Returns:
        The path that was written.
    """
    # Normalize to LF only before writing
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    path.write_bytes(normalized.encode("utf-8"))
    return path
