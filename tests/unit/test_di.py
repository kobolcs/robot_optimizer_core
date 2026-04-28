# tests/unit/test_di.py
"""Unit tests for the thread-safe DI container."""

from __future__ import annotations

import pytest

from robot_optimizer_core.di import ServiceLifetime, ThreadSafeContainer
from robot_optimizer_core.exceptions import ConfigurationError


@pytest.mark.unit
class TestThreadSafeContainer:
    @pytest.fixture
    def container(self) -> ThreadSafeContainer:
        return ThreadSafeContainer()

    # --- Transient lifetime ---

    def test_transient_returns_new_instances_each_time(
        self, container: ThreadSafeContainer
    ) -> None:
        container.register("svc", list, ServiceLifetime.TRANSIENT)
        a = container.resolve("svc")
        b = container.resolve("svc")
        assert a is not b

    def test_transient_is_default_lifetime(
        self, container: ThreadSafeContainer
    ) -> None:
        container.register("svc", list)
        a = container.resolve("svc")
        b = container.resolve("svc")
        assert a is not b

    # --- Singleton lifetime ---

    def test_singleton_returns_same_instance(
        self, container: ThreadSafeContainer
    ) -> None:
        container.register("svc", list, ServiceLifetime.SINGLETON)
        a = container.resolve("svc")
        b = container.resolve("svc")
        assert a is b

    def test_register_singleton_convenience(
        self, container: ThreadSafeContainer
    ) -> None:
        container.register_singleton("svc", list)
        a = container.resolve("svc")
        b = container.resolve("svc")
        assert a is b

    # --- Scoped lifetime ---

    def test_scoped_same_within_scope(self, container: ThreadSafeContainer) -> None:
        container.register("svc", list, ServiceLifetime.SCOPED)
        with container.create_scope():
            a = container.resolve("svc")
            b = container.resolve("svc")
        assert a is b

    def test_scoped_different_across_scopes(
        self, container: ThreadSafeContainer
    ) -> None:
        container.register("svc", list, ServiceLifetime.SCOPED)
        with container.create_scope():
            a = container.resolve("svc")
        with container.create_scope():
            b = container.resolve("svc")
        assert a is not b

    # --- register_instance ---

    def test_register_instance_returns_exact_object(
        self, container: ThreadSafeContainer
    ) -> None:
        my_obj = object()
        container.register_instance("obj", my_obj)
        assert container.resolve("obj") is my_obj

    def test_register_instance_repeated_resolve_returns_same(
        self, container: ThreadSafeContainer
    ) -> None:
        my_obj = object()
        container.register_instance("obj", my_obj)
        assert container.resolve("obj") is container.resolve("obj")

    # --- Error cases ---

    def test_missing_service_raises_configuration_error(
        self, container: ThreadSafeContainer
    ) -> None:
        with pytest.raises(ConfigurationError, match="Service not registered"):
            container.resolve("nonexistent")

    def test_duplicate_registration_raises(
        self, container: ThreadSafeContainer
    ) -> None:
        container.register("svc", list)
        with pytest.raises(ConfigurationError, match="already registered"):
            container.register("svc", dict)

    def test_duplicate_registration_with_override_allowed(
        self, container: ThreadSafeContainer
    ) -> None:
        container.register("svc", list)
        container.register("svc", dict, override=True)
        assert isinstance(container.resolve("svc"), dict)

    def test_circular_dependency_raises_configuration_error(
        self, container: ThreadSafeContainer
    ) -> None:
        def factory_a() -> object:
            return container.resolve("a")

        container.register("a", factory_a, ServiceLifetime.TRANSIENT)
        with pytest.raises(ConfigurationError, match="[Cc]ircular dependency"):
            container.resolve("a")

    # --- has_service ---

    def test_has_service_true_when_registered(
        self, container: ThreadSafeContainer
    ) -> None:
        container.register("svc", list)
        assert container.has_service("svc") is True

    def test_has_service_false_when_not_registered(
        self, container: ThreadSafeContainer
    ) -> None:
        assert container.has_service("nonexistent") is False

    # --- clear ---

    def test_clear_removes_all_registrations(
        self, container: ThreadSafeContainer
    ) -> None:
        container.register("svc", list)
        container.clear()
        assert container.has_service("svc") is False

    def test_clear_allows_re_registration(self, container: ThreadSafeContainer) -> None:
        container.register("svc", list)
        container.clear()
        container.register("svc", dict)
        assert isinstance(container.resolve("svc"), dict)

    # --- Parent container hierarchy ---

    def test_child_resolves_from_parent(self) -> None:
        parent = ThreadSafeContainer()
        parent.register("svc", list)
        child = ThreadSafeContainer(parent=parent)
        assert isinstance(child.resolve("svc"), list)

    def test_child_registration_shadows_parent(self) -> None:
        parent = ThreadSafeContainer()
        parent.register("svc", list)
        child = ThreadSafeContainer(parent=parent)
        child.register("svc", dict)
        assert isinstance(child.resolve("svc"), dict)

    def test_parent_has_service_visible_to_child(self) -> None:
        parent = ThreadSafeContainer()
        parent.register("svc", list)
        child = ThreadSafeContainer(parent=parent)
        assert child.has_service("svc") is True

    # --- register_instance duplicate ---

    def test_register_instance_duplicate_raises(
        self, container: ThreadSafeContainer
    ) -> None:
        container.register_instance("obj", object())
        with pytest.raises(ConfigurationError, match="already registered"):
            container.register_instance("obj", object())

    def test_register_instance_with_override(
        self, container: ThreadSafeContainer
    ) -> None:
        first = object()
        second = object()
        container.register_instance("obj", first)
        container.register_instance("obj", second, override=True)
        assert container.resolve("obj") is second
