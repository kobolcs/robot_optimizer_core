import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if str(item.fspath).replace("\\", "/").split("/tests/")[1].startswith("unit/"):
            item.add_marker(pytest.mark.unit)
