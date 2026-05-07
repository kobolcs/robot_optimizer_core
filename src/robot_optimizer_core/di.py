# src/robot_optimizer_core/di.py
"""Thread-safe dependency injection container."""

from __future__ import annotations

import inspect
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import StrEnum, auto
from typing import Any, TypeAlias, TypeVar

from .exceptions import ConfigurationError
from .logging import get_logger

__all__ = [
    "ServiceDescriptor",
    "ServiceLifetime",
    "ThreadSafeContainer",
    "get_container",
    "get_thread_safe_container",
    "reset_container",
]

ServiceFactory: TypeAlias = type[Any] | Callable[..., Any]
T = TypeVar("T")

logger = get_logger(__name__)


class ServiceLifetime(StrEnum):
    """Service lifetime options for dependency injection."""

    TRANSIENT = auto()  # New instance each time
    SINGLETON = auto()  # Single instance for container lifetime
    SCOPED = auto()  # Single instance per scope


@dataclass
class ServiceDescriptor:
    """Thread-safe service descriptor."""

    service_type: str
    implementation: ServiceFactory
    lifetime: ServiceLifetime = ServiceLifetime.TRANSIENT
    instance: Any | None = field(default=None, init=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False)

    def get_or_create_instance(self, factory: Callable[[], Any]) -> Any:
        """Thread-safe instance creation for singletons."""
        if self.lifetime != ServiceLifetime.SINGLETON:
            return factory()

        # Double-checked locking pattern
        if self.instance is not None:
            return self.instance

        with self._lock:
            # Check again inside lock
            if self.instance is not None:
                return self.instance

            # Create instance
            self.instance = factory()
            return self.instance


class ThreadSafeContainer:
    """Thread-safe dependency injection container.

    This container uses fine-grained locking to ensure thread safety
    while maintaining good performance.
    """

    def __init__(self, parent: ThreadSafeContainer | None = None) -> None:
        """Initialize the thread-safe container."""
        self.parent = parent
        self._services: dict[str, ServiceDescriptor] = {}
        self._services_lock = threading.RLock()
        self._resolution_stack_var: ContextVar[list[str] | None] = ContextVar(
            f"resolution_stack_{id(self)}", default=None
        )
        self._scope_instances_var: ContextVar[dict[str, Any] | None] = ContextVar(
            f"scope_instances_{id(self)}", default=None
        )

    @property
    def _resolution_stack(self) -> list[str]:
        stack = self._resolution_stack_var.get()
        if stack is None:
            stack = []
            self._resolution_stack_var.set(stack)
        return stack

    @property
    def _scope_instances(self) -> dict[str, Any]:
        instances = self._scope_instances_var.get()
        if instances is None:
            instances = {}
            self._scope_instances_var.set(instances)
        return instances

    def register(
        self,
        service_type: str,
        implementation: ServiceFactory,
        lifetime: ServiceLifetime = ServiceLifetime.TRANSIENT,
        override: bool = False,
    ) -> None:
        """Thread-safe service registration."""
        with self._services_lock:
            if service_type in self._services and not override:
                raise ConfigurationError(
                    f"Service already registered: {service_type}",
                    config_key="di.service",
                    provided_value=service_type,
                )

            descriptor = ServiceDescriptor(service_type, implementation, lifetime)
            self._services[service_type] = descriptor

        logger.debug(
            "Service registered",
            extra={
                "service": service_type,
                "lifetime": lifetime,
                "override": override,
                "thread_id": threading.get_ident(),
            },
        )

    def resolve(self, service_type: str) -> Any:
        """Thread-safe service resolution."""
        # Check for circular dependencies (thread-local)
        if service_type in self._resolution_stack:
            cycle = " -> ".join(self._resolution_stack + [service_type])
            raise ConfigurationError(
                f"Circular dependency detected: {cycle}",
                config_key="di.circular",
                provided_value=service_type,
            )

        # Try to find service descriptor
        descriptor = self._get_descriptor(service_type)

        if descriptor is None:
            available = self._list_all_services()
            raise ConfigurationError(
                f"Service not registered: {service_type}",
                config_key="di.service",
                provided_value=service_type,
                details={"available": available},
            )

        # Add to resolution stack
        self._resolution_stack.append(service_type)
        try:
            return self._create_instance_based_on_lifetime(descriptor)
        finally:
            # Always remove from stack
            self._resolution_stack.remove(service_type)

    def _get_descriptor(self, service_type: str) -> ServiceDescriptor | None:
        """Get service descriptor with locking."""
        # Check this container
        with self._services_lock:
            if service_type in self._services:
                return self._services[service_type]

        # Check parent container
        if self.parent:
            return self.parent._get_descriptor(service_type)

        return None

    def _list_all_services(self) -> list[str]:
        """List all available services across hierarchy."""
        services: set[str] = set()

        # This container's services
        with self._services_lock:
            services.update(self._services.keys())

        # Parent's services
        if self.parent:
            services.update(self.parent._list_all_services())

        return sorted(services)

    def _create_instance_based_on_lifetime(self, descriptor: ServiceDescriptor) -> Any:
        """Create instance based on service lifetime."""
        if descriptor.lifetime == ServiceLifetime.SINGLETON:
            return descriptor.get_or_create_instance(
                lambda: self._create_instance(descriptor)
            )
        if descriptor.lifetime == ServiceLifetime.SCOPED:
            # Check scoped instances
            if descriptor.service_type in self._scope_instances:
                return self._scope_instances[descriptor.service_type]

            # Create and cache in scope
            instance = self._create_instance(descriptor)
            self._scope_instances[descriptor.service_type] = instance
            return instance
        # TRANSIENT
        return self._create_instance(descriptor)

    def _create_instance(self, descriptor: ServiceDescriptor) -> Any:
        """Create an instance from a descriptor."""
        implementation = descriptor.implementation

        # If it's a callable (factory), call it
        if callable(implementation) and not inspect.isclass(implementation):
            return implementation()

        # If it's a class, try to auto-inject constructor parameters
        if inspect.isclass(implementation):
            return self._create_with_injection(implementation)

        # Otherwise, just return it
        return implementation

    def _create_with_injection(self, cls: type[T]) -> T:
        """Create instance with constructor injection."""
        signature = inspect.signature(cls.__init__)
        kwargs: dict[str, Any] = {}

        for param_name, param in signature.parameters.items():
            if param_name == "self":
                continue

            # Try to resolve by parameter name
            if self.has_service(param_name):
                kwargs[param_name] = self.resolve(param_name)
            # Try to resolve by type annotation
            elif param.annotation != param.empty:
                type_name = getattr(param.annotation, "__name__", str(param.annotation))
                if self.has_service(type_name):
                    kwargs[param_name] = self.resolve(type_name)
            # Use default if available
            elif param.default != param.empty:
                kwargs[param_name] = param.default
            # Skip if no default and can't resolve
            else:
                logger.debug(
                    f"Cannot resolve parameter: {param_name} for {cls.__name__}"
                )

        return cls(**kwargs)

    def has_service(self, service_type: str) -> bool:
        """Check if service is registered (thread-safe)."""
        with self._services_lock:
            if service_type in self._services:
                return True

        return self.parent.has_service(service_type) if self.parent else False

    @contextmanager
    def create_scope(self) -> Iterator[ThreadSafeContainer]:
        """Create a new resolution scope."""
        token = self._scope_instances_var.set({})
        try:
            yield self
        finally:
            self._scope_instances_var.reset(token)

    def register_singleton(
        self, service_type: str, implementation: ServiceFactory, override: bool = False
    ) -> None:
        """Register a singleton service."""
        self.register(service_type, implementation, ServiceLifetime.SINGLETON, override)

    def register_instance(
        self, service_type: str, instance: Any, override: bool = False
    ) -> None:
        """Register an existing instance as a singleton."""
        with self._services_lock:
            if service_type in self._services and not override:
                raise ConfigurationError(
                    f"Service already registered: {service_type}",
                    config_key="di.service",
                    provided_value=service_type,
                )

            # Create descriptor with pre-cached instance
            descriptor = ServiceDescriptor(
                service_type, lambda: instance, ServiceLifetime.SINGLETON
            )
            descriptor.instance = instance  # Pre-cache
            self._services[service_type] = descriptor

    def clear(self) -> None:
        """Clear all registrations and instances."""
        with self._services_lock:
            self._services.clear()

        self._resolution_stack_var.set(None)
        self._scope_instances_var.set(None)


# Global container with thread safety
_global_container: ThreadSafeContainer | None = None
_global_container_lock = threading.RLock()


def get_thread_safe_container() -> ThreadSafeContainer:
    """Get the global thread-safe container."""
    global _global_container

    if _global_container is None:
        with _global_container_lock:
            # Double-check pattern
            if _global_container is None:
                _global_container = ThreadSafeContainer()
                _register_defaults(_global_container)

    return _global_container


# Alias for backward compatibility
get_container = get_thread_safe_container


def reset_container() -> None:
    """Reset the global DI container to an uninitialised state.

    Primarily useful for tests and plugin reload scenarios.
    """
    global _global_container
    with _global_container_lock:
        _global_container = None


def _register_defaults(container: ThreadSafeContainer) -> None:
    """Register default services in the container."""
    from .analyzers.registry import get_analyzer_registry
    from .config import get_settings
    from .discovery import OptimizedFileDiscoveryService
    from .metrics import get_metrics
    from .parsers import RobotASTParser

    # Register core services as singletons
    container.register_singleton("settings", get_settings)
    container.register_singleton("metrics", get_metrics)
    container.register_singleton("analyzer_registry", get_analyzer_registry)
    container.register("parser", RobotASTParser)

    # Use optimized file discovery for better performance
    container.register("file_discovery", OptimizedFileDiscoveryService)

    logger.debug("Default services registered with optimized discovery")
