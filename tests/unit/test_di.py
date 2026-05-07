# tests/unit/test_di.py
"""Tests for the DI container, including reset behaviour."""

from __future__ import annotations

import pytest

from robot_optimizer_core.di import (
    get_container,
    get_thread_safe_container,
    reset_container,
)


@pytest.mark.unit
class TestResetContainer:
    def test_reset_returns_fresh_container(self) -> None:
        c1 = get_container()
        reset_container()
        c2 = get_container()
        assert c1 is not c2

    def test_reset_clears_custom_registrations(self) -> None:
        container = get_container()
        container.register("_test_probe", lambda: object(), override=True)
        assert container.has_service("_test_probe")
        reset_container()
        assert not get_container().has_service("_test_probe")

    def test_double_reset_is_safe(self) -> None:
        reset_container()
        reset_container()
        assert get_container() is not None

    def test_default_services_re_registered_after_reset(self) -> None:
        reset_container()
        container = get_container()
        assert container.has_service("settings")
        assert container.has_service("file_discovery")
        assert container.has_service("parser")
        assert container.has_service("analyzer_registry")
        assert container.has_service("metrics")

    def test_get_container_alias_works_after_reset(self) -> None:
        reset_container()
        assert get_container() is get_thread_safe_container()
