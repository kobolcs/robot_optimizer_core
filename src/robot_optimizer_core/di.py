# src/robot_optimizer_core/di.py
"""Basic dependency injection container for Robot Framework Optimizer Core.

This module provides a simple DI container that can be extended by the
Pro version with more advanced features like scopes, decorators, and
automatic injection.

Example:
    Using the DI container::
    
        from robot_optimizer_core import Container, get_container
        
        # Register dependencies
        container = get_container()
        container.register("parser", RobotASTParser)
        container.register_singleton("logger", lambda: get_logger(__name__))
        
        # Resolve dependencies
        parser = container.resolve("parser")
        logger = container.resolve("logger")
"""
from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum, auto
from typing import Any, TypeAlias, TypeVar

from .exceptions import ConfigurationError
from .logging import get_logger

T = TypeVar("T")
ServiceFactory: TypeAlias = type[Any] | Callable[..., Any]

logger = get_logger(__name__)


class ServiceLifetime(StrEnum):
    """Service lifetime options for dependency injection."""
    TRANSIENT = auto()  # New instance each time
    SINGLETON = auto()  # Single instance for container lifetime
    SCOPED = auto()     # Single instance per scope (Pro feature)


@dataclass
class ServiceDescriptor:
    """Describes a registered service.
    
    Attributes:
        service_type: The service interface or key.
        implementation: The implementation class or factory.
        lifetime: Service lifetime (transient, singleton, scoped).
        instance: Cached instance for singletons.
    """
    service_type: str
    implementation: ServiceFactory
    lifetime: ServiceLifetime = ServiceLifetime.TRANSIENT
    instance: Any | None = field(default=None, init=False)


class Container:
    """Simple dependency injection container.
    
    This container supports basic registration and resolution of dependencies
    with transient and singleton lifetimes. The Pro version can extend this
    with additional features.
    
    Attributes:
        services: Registered service descriptors.
        resolving: Stack to detect circular dependencies.
    """

    __slots__ = ('parent', 'resolving', 'services')

    def __init__(self, parent: Container | None = None) -> None:
        """Initialize the container.
        
        Args:
            parent: Parent container for hierarchical resolution.
        """
        self.services: dict[str, ServiceDescriptor] = {}
        self.parent = parent
        self.resolving: list[str] = []

    def register(
        self,
        service_type: str,
        implementation: ServiceFactory,
        lifetime: ServiceLifetime = ServiceLifetime.TRANSIENT,
        override: bool = False
    ) -> None:
        """Register a service.
        
        Args:
            service_type: Service key or interface name.
            implementation: Implementation class or factory.
            lifetime: Service lifetime.
            override: Whether to override existing registration.
            
        Raises:
            ConfigurationError: If service already registered and override is False.
            
        Example:
            >>> container.register("analyzer", DeadCodeAnalyzer)
            >>> container.register("logger", lambda: get_logger(__name__))
        """
        if service_type in self.services and not override:
            raise ConfigurationError(
                f"Service already registered: {service_type}",
                config_key="di.service",
                provided_value=service_type
            )

        descriptor = ServiceDescriptor(service_type, implementation, lifetime)
        self.services[service_type] = descriptor

        logger.debug(
            "Service registered",
            extra={
                "service": service_type,
                "lifetime": lifetime,
                "override": override
            }
        )

    def register_singleton(
        self,
        service_type: str,
        implementation: ServiceFactory,
        override: bool = False
    ) -> None:
        """Register a singleton service.
        
        Convenience method for registering singletons.
        
        Args:
            service_type: Service key or interface name.
            implementation: Implementation class or factory.
            override: Whether to override existing registration.
        """
        self.register(service_type, implementation, ServiceLifetime.SINGLETON, override)

    def register_instance(
        self,
        service_type: str,
        instance: Any,
        override: bool = False
    ) -> None:
        """Register an existing instance as a singleton.
        
        Args:
            service_type: Service key or interface name.
            instance: The instance to register.
            override: Whether to override existing registration.
        """
        self.register(service_type, lambda: instance, ServiceLifetime.SINGLETON, override)
        # Pre-cache the instance
        if service_type in self.services:
            self.services[service_type].instance = instance

    def resolve[T](self, service_type: str) -> T:
        """Resolve a service with type safety.
        
        Uses PEP 695 type parameters for better type inference.
        
        Args:
            service_type: Service key to resolve.
            
        Returns:
            Service instance.
            
        Raises:
            ConfigurationError: If service not found or circular dependency detected.
            
        Example:
            >>> analyzer = container.resolve[BaseAnalyzer]("analyzer")
        """
        # Check for circular dependencies
        if service_type in self.resolving:
            cycle = " -> ".join(self.resolving + [service_type])
            raise ConfigurationError(
                f"Circular dependency detected: {cycle}",
                config_key="di.circular",
                provided_value=service_type
            )

        # Try to find service in this container
        descriptor = self.services.get(service_type)

        # If not found, try parent container
        if descriptor is None and self.parent:
            return self.parent.resolve(service_type)

        if descriptor is None:
            available = list(self.services.keys())
            if self.parent:
                available.extend(self.parent.list_services())

            raise ConfigurationError(
                f"Service not registered: {service_type}",
                config_key="di.service",
                provided_value=service_type,
                details={"available": available}
            )

        # Return cached singleton
        if descriptor.lifetime == ServiceLifetime.SINGLETON and descriptor.instance is not None:
            return descriptor.instance

        # Create new instance
        self.resolving.append(service_type)
        try:
            instance = self._create_instance(descriptor)

            # Cache singleton
            if descriptor.lifetime == ServiceLifetime.SINGLETON:
                descriptor.instance = instance

            return instance

        finally:
            self.resolving.remove(service_type)

    def resolve_optional[T](self, service_type: str, default: T | None = None) -> T | None:
        """Resolve a service or return default if not found.
        
        Args:
            service_type: Service key to resolve.
            default: Default value if service not found.
            
        Returns:
            Service instance or default value.
        """
        try:
            return self.resolve(service_type)
        except ConfigurationError:
            return default

    def has_service(self, service_type: str) -> bool:
        """Check if a service is registered.
        
        Args:
            service_type: Service key to check.
            
        Returns:
            True if service is registered.
        """
        if service_type in self.services:
            return True
        return self.parent.has_service(service_type) if self.parent else False

    def list_services(self) -> list[str]:
        """List all registered services.
        
        Returns:
            List of service keys.
        """
        services = list(self.services.keys())
        if self.parent:
            services.extend(self.parent.list_services())
        return sorted(set(services))

    def create_scope(self) -> Container:
        """Create a child container scope.
        
        The child container inherits registrations from the parent
        but can override them without affecting the parent.
        
        Returns:
            Child container.
            
        Example:
            >>> child = container.create_scope()
            >>> child.register("logger", CustomLogger)
        """
        return Container(parent=self)

    def _create_instance(self, descriptor: ServiceDescriptor) -> Any:
        """Create an instance from a descriptor.
        
        Args:
            descriptor: Service descriptor.
            
        Returns:
            Service instance.
        """
        implementation = descriptor.implementation

        # If it's a callable (factory), call it
        if callable(implementation) and not inspect.isclass(implementation):
            return implementation()

        # If it's a class, try to auto-inject constructor parameters
        if inspect.isclass(implementation):
            return self._create_with_injection(implementation)

        # Otherwise, just return it
        return implementation

    def _create_with_injection[T](self, cls: type[T]) -> T:
        """Create an instance with constructor injection.
        
        This is a basic implementation that tries to resolve
        constructor parameters from the container.
        
        Args:
            cls: Class to instantiate.
            
        Returns:
            Class instance.
        """
        # Get constructor signature
        signature = inspect.signature(cls.__init__)
        kwargs = {}

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


# Global container instance
_container: Container | None = None


def get_container() -> Container:
    """Get the global DI container.
    
    Returns:
        The global container instance.
        
    Example:
        >>> container = get_container()
        >>> container.register("parser", RobotASTParser)
    """
    global _container
    if _container is None:
        _container = Container()
        _register_defaults(_container)
    return _container


def _register_defaults(container: Container) -> None:
    """Register default services in the container.
    
    Args:
        container: Container to configure.
    """
    from .config import get_settings
    from .discovery import FileDiscoveryService
    from .metrics import get_metrics
    from .parsers import RobotASTParser

    # Register core services
    container.register_singleton("settings", get_settings)
    container.register_singleton("metrics", get_metrics)
    container.register("parser", RobotASTParser)
    container.register("file_discovery", FileDiscoveryService)

    logger.debug("Default services registered")
