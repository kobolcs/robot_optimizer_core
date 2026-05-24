from pathlib import Path

import pytest

import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).parent.parent))
from conftest import write_robot_file  # noqa: E402


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if str(item.fspath).replace("\\", "/").split("/tests/")[1].startswith("integration/"):
            item.add_marker(pytest.mark.integration)


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
