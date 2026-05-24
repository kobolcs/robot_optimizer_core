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
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from robot_optimizer_core import (
    Settings,
    TestFile,
    configure_logging,
    configure_metrics,
    reset_settings,
)
from robot_optimizer_core.domain.repositories import TestResultRepository

# Configure logging for tests
configure_logging(level="WARNING", format_json=False)
configure_metrics(enabled=False)  # Disable metrics in tests


def pytest_collection_modifyitems(config, items):
    """Modify test collection to skip certain patterns."""
    pass  # Keep for future use


def pytest_ignore_collect(collection_path, config):
    """Ignore certain files/patterns during collection."""
    if collection_path.suffix == ".skip":
        return True
    return False


def pytest_pycollect_makeitem(collector, name, obj):
    """Control which classes are collected as test classes.

    Prevent pytest from collecting domain model classes (TestFile, TestResult, etc.)
    that happen to start with 'Test' but aren't actually test classes.
    """
    ignored_classes = {"TestFile", "TestResult", "TZAwareTestFile"}
    if name in ignored_classes:
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
def mock_test_result_repository() -> Mock:
    """Provide a mock test result repository."""
    mock_repo = Mock(spec=TestResultRepository)
    mock_repo.get_flakiness_stats.return_value = []
    mock_repo.get_results_for_file.return_value = []
    mock_repo.get_total_results_count.return_value = 0
    return mock_repo


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


# Utilities for cross-platform file handling
def write_robot_file(path: Path, content: str) -> Path:
    """Write Robot Framework content to file with consistent line endings (LF only).

    This helper ensures files always have LF line endings regardless of platform,
    preventing CRLF issues on Windows that can cause size mismatches and content
    assertion failures.
    """
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    path.write_bytes(normalized.encode("utf-8"))
    return path
