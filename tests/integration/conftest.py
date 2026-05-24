from pathlib import Path

import pytest

from conftest import write_robot_file


@pytest.fixture
def large_robot_file(temp_dir: Path) -> Path:
    """Create a large robot file for performance and scale testing."""
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
