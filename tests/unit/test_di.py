# tests/unit/test_di.py
"""Tests for the DI container, including reset behaviour."""

from __future__ import annotations

import pytest

from robot_optimizer_core.composition.container import (
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


@pytest.mark.unit
class TestThreadSafeContainerRegister:
    def test_register_duplicate_raises(self) -> None:
        from robot_optimizer_core.composition.container import ThreadSafeContainer
        from robot_optimizer_core.exceptions import ConfigurationError

        c = ThreadSafeContainer()
        c.register("svc", lambda: object())
        with pytest.raises(ConfigurationError, match="already registered"):
            c.register("svc", lambda: object())

    def test_register_duplicate_override_ok(self) -> None:
        from robot_optimizer_core.composition.container import ThreadSafeContainer

        c = ThreadSafeContainer()
        c.register("svc", lambda: 1)
        c.register("svc", lambda: 2, override=True)
        assert c.resolve("svc") == 2

    def test_resolve_unregistered_raises(self) -> None:
        from robot_optimizer_core.composition.container import ThreadSafeContainer
        from robot_optimizer_core.exceptions import ConfigurationError

        c = ThreadSafeContainer()
        with pytest.raises(ConfigurationError, match="not registered"):
            c.resolve("unknown_service")

    def test_circular_dependency_raises(self) -> None:
        from robot_optimizer_core.composition.container import ThreadSafeContainer
        from robot_optimizer_core.exceptions import ConfigurationError

        c = ThreadSafeContainer()

        def factory_a() -> object:
            return c.resolve("a")

        c.register("a", factory_a)
        with pytest.raises(ConfigurationError, match="[Cc]ircular"):
            c.resolve("a")

    def test_singleton_returns_same_instance(self) -> None:
        from robot_optimizer_core.composition.container import ServiceLifetime, ThreadSafeContainer

        c = ThreadSafeContainer()
        c.register("svc", lambda: object(), ServiceLifetime.SINGLETON)
        assert c.resolve("svc") is c.resolve("svc")

    def test_transient_returns_different_instances(self) -> None:
        from robot_optimizer_core.composition.container import ServiceLifetime, ThreadSafeContainer

        c = ThreadSafeContainer()
        c.register("svc", lambda: object(), ServiceLifetime.TRANSIENT)
        assert c.resolve("svc") is not c.resolve("svc")

    def test_scoped_returns_same_instance_within_scope(self) -> None:
        from robot_optimizer_core.composition.container import ServiceLifetime, ThreadSafeContainer

        c = ThreadSafeContainer()
        c.register("svc", lambda: object(), ServiceLifetime.SCOPED)
        with c.create_scope():
            i1 = c.resolve("svc")
            i2 = c.resolve("svc")
        assert i1 is i2

    def test_parent_container_resolution(self) -> None:
        from robot_optimizer_core.composition.container import ThreadSafeContainer

        parent = ThreadSafeContainer()
        parent.register("parent_svc", lambda: "from_parent")
        child = ThreadSafeContainer(parent=parent)
        assert child.resolve("parent_svc") == "from_parent"

    def test_list_all_services_includes_parent(self) -> None:
        from robot_optimizer_core.composition.container import ThreadSafeContainer

        parent = ThreadSafeContainer()
        parent.register("parent_svc", lambda: None)
        child = ThreadSafeContainer(parent=parent)
        child.register("child_svc", lambda: None)
        services = child._list_all_services()
        assert "parent_svc" in services
        assert "child_svc" in services

    def test_register_instance_stores_value(self) -> None:
        from robot_optimizer_core.composition.container import ThreadSafeContainer

        c = ThreadSafeContainer()
        obj = object()
        c.register_instance("my_obj", obj)
        assert c.resolve("my_obj") is obj

    def test_register_instance_duplicate_raises(self) -> None:
        from robot_optimizer_core.composition.container import ThreadSafeContainer
        from robot_optimizer_core.exceptions import ConfigurationError

        c = ThreadSafeContainer()
        c.register_instance("obj", object())
        with pytest.raises(ConfigurationError, match="already registered"):
            c.register_instance("obj", object())

    def test_register_singleton_shortcut(self) -> None:
        from robot_optimizer_core.composition.container import ThreadSafeContainer

        c = ThreadSafeContainer()
        c.register_singleton("svc", lambda: "val")
        assert c.resolve("svc") == "val"

    def test_has_service_false_for_unknown(self) -> None:
        from robot_optimizer_core.composition.container import ThreadSafeContainer

        c = ThreadSafeContainer()
        assert c.has_service("nope") is False

    def test_clear_removes_all(self) -> None:
        from robot_optimizer_core.composition.container import ThreadSafeContainer

        c = ThreadSafeContainer()
        c.register("svc", lambda: None)
        c.clear()
        assert not c.has_service("svc")

    def test_create_with_injection_uses_defaults(self) -> None:
        from robot_optimizer_core.composition.container import ThreadSafeContainer

        class MyService:
            def __init__(self, value: int = 42) -> None:
                self.value = value

        c = ThreadSafeContainer()
        c.register("svc", MyService)
        instance = c.resolve("svc")
        assert instance.value == 42

    def test_create_with_injection_resolves_by_name(self) -> None:
        from robot_optimizer_core.composition.container import ThreadSafeContainer

        class Dep:
            pass

        class MyService:
            def __init__(self, dep: Dep) -> None:
                self.dep = dep

        c = ThreadSafeContainer()
        dep_instance = Dep()
        c.register_instance("dep", dep_instance)
        c.register("svc", MyService)
        instance = c.resolve("svc")
        assert instance.dep is dep_instance

    def test_service_descriptor_non_singleton_does_not_cache(self) -> None:
        from robot_optimizer_core.composition.container import ServiceDescriptor, ServiceLifetime

        calls = 0

        def factory() -> object:
            nonlocal calls
            calls += 1
            return object()

        d = ServiceDescriptor("svc", factory, ServiceLifetime.TRANSIENT)
        d.get_or_create_instance(factory)
        d.get_or_create_instance(factory)
        assert calls == 2

    def test_service_descriptor_singleton_caches(self) -> None:
        from robot_optimizer_core.composition.container import ServiceDescriptor, ServiceLifetime

        calls = 0

        def factory() -> object:
            nonlocal calls
            calls += 1
            return object()

        d = ServiceDescriptor("svc", factory, ServiceLifetime.SINGLETON)
        i1 = d.get_or_create_instance(factory)
        i2 = d.get_or_create_instance(factory)
        assert i1 is i2
        assert calls == 1

    def test_resolve_raw_non_callable_implementation(self) -> None:
        from robot_optimizer_core.composition.container import (
            ServiceDescriptor,
            ServiceLifetime,
            ThreadSafeContainer,
        )

        c = ThreadSafeContainer()
        raw_value = {"key": "value"}
        descriptor = ServiceDescriptor("raw_svc", raw_value, ServiceLifetime.TRANSIENT)  # type: ignore[arg-type]
        c._services["raw_svc"] = descriptor
        result = c.resolve("raw_svc")
        assert result == raw_value

    def test_scope_instances_initializes_from_none(self) -> None:
        from robot_optimizer_core.composition.container import ServiceLifetime, ThreadSafeContainer

        c = ThreadSafeContainer()
        c.register("scoped_svc", lambda: object(), ServiceLifetime.SCOPED)
        # Resolve SCOPED outside create_scope() — _scope_instances starts as None → initializes to {}
        _ = c.resolve("scoped_svc")
        assert c._scope_instances is not None

    def test_create_with_injection_resolves_by_type_annotation(self) -> None:
        from robot_optimizer_core.composition.container import ThreadSafeContainer

        class Dep:
            pass

        class MyService:
            def __init__(self, the_dep: Dep) -> None:
                self.dep = the_dep

        c = ThreadSafeContainer()
        dep_instance = Dep()
        # Register under the type name "Dep" (not the param name "the_dep")
        c.register_instance("Dep", dep_instance)
        c.register("svc", MyService)
        instance = c.resolve("svc")
        assert instance.dep is dep_instance

    def test_create_with_injection_logs_unresolvable_param(self) -> None:
        from robot_optimizer_core.composition.container import ThreadSafeContainer

        class MyService:
            def __init__(self, unresolvable_param_xyz) -> None:  # type: ignore[no-untyped-def]
                self.val = unresolvable_param_xyz

        c = ThreadSafeContainer()
        c.register("svc", MyService)
        # The debug log is emitted, then cls(**{}) raises TypeError
        with pytest.raises(TypeError):
            c.resolve("svc")
