# src/robot_optimizer_core/plugin.py
"""Plugin system for extending Robot Framework Optimizer Core.

This module provides the plugin infrastructure that allows the Pro version
and third parties to extend the Core functionality with custom analyzers,
parsers, and other components.

Example:
    Creating a custom analyzer plugin::
    
        from robot_optimizer_core import Plugin, PluginMetadata, BaseAnalyzer
        
        class CustomAnalyzer(BaseAnalyzer):
            def analyze(self, test_file):
                # Custom analysis logic
                return findings
        
        class CustomPlugin(Plugin):
            @property
            def metadata(self):
                return PluginMetadata(
                    name="custom-analyzer",
                    version="1.0.0",
                    description="Custom analysis plugin",
                    author="Your Name"
                )
            
            def activate(self):
                self.register_analyzer("custom", CustomAnalyzer)
"""
from __future__ import annotations

import importlib
import importlib.util
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar

from .exceptions import PluginError
from .logging import get_logger

T = TypeVar("T")

logger = get_logger(__name__)


@dataclass
class PluginMetadata:
    """Metadata for a plugin.
    
    This class contains information about a plugin that is used
    for registration and documentation.
    
    Attributes:
        name: Unique plugin identifier.
        version: Plugin version (semver format).
        description: Human-readable description.
        author: Plugin author name.
        email: Contact email (optional).
        url: Plugin homepage/repository URL (optional).
        requires: List of required dependencies.
        tags: List of tags for categorization.
    """
    name: str
    version: str
    description: str
    author: str
    email: Optional[str] = None
    url: Optional[str] = None
    requires: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    
    def __post_init__(self) -> None:
        """Validate metadata after initialization."""
        if not self.name or not self.name.replace("-", "").replace("_", "").isalnum():
            raise ValueError(f"Invalid plugin name: {self.name}")
        
        # Basic semver validation
        parts = self.version.split(".")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            raise ValueError(f"Invalid version format: {self.version}")


class PluginRegistry:
    """Registry for plugin components.
    
    This registry stores and manages plugin components like analyzers,
    parsers, and other extensions.
    
    Attributes:
        components: Dictionary of component types and their instances.
    """
    
    def __init__(self) -> None:
        """Initialize the plugin registry."""
        self.components: Dict[str, Dict[str, Any]] = {
            "analyzers": {},
            "parsers": {},
            "backends": {},
            "filters": {},
        }
    
    def register(
        self,
        component_type: str,
        name: str,
        component: Any,
        override: bool = False
    ) -> None:
        """Register a component.
        
        Args:
            component_type: Type of component (e.g., "analyzers").
            name: Unique name for the component.
            component: The component instance or class.
            override: Whether to override existing component.
            
        Raises:
            PluginError: If component already exists and override is False.
        """
        if component_type not in self.components:
            raise PluginError(
                f"Unknown component type: {component_type}",
                details={"valid_types": list(self.components.keys())}
            )
        
        if name in self.components[component_type] and not override:
            raise PluginError(
                f"Component already registered: {component_type}.{name}",
                details={"component_type": component_type, "name": name}
            )
        
        self.components[component_type][name] = component
        logger.info(
            "Component registered",
            extra={
                "component_type": component_type,
                "name": name,
                "override": override
            }
        )
    
    def get(self, component_type: str, name: str) -> Any:
        """Get a registered component.
        
        Args:
            component_type: Type of component.
            name: Component name.
            
        Returns:
            The registered component.
            
        Raises:
            PluginError: If component not found.
        """
        if component_type not in self.components:
            raise PluginError(f"Unknown component type: {component_type}")
        
        if name not in self.components[component_type]:
            raise PluginError(
                f"Component not found: {component_type}.{name}",
                details={
                    "component_type": component_type,
                    "name": name,
                    "available": list(self.components[component_type].keys())
                }
            )
        
        return self.components[component_type][name]
    
    def list_components(self, component_type: str) -> List[str]:
        """List all components of a given type.
        
        Args:
            component_type: Type of components to list.
            
        Returns:
            List of component names.
        """
        if component_type not in self.components:
            return []
        return list(self.components[component_type].keys())
    
    def unregister(self, component_type: str, name: str) -> None:
        """Unregister a component.
        
        Args:
            component_type: Type of component.
            name: Component name.
        """
        if component_type in self.components:
            self.components[component_type].pop(name, None)


class Plugin(ABC):
    """Base class for plugins.
    
    All plugins must inherit from this class and implement the required
    methods. Plugins can register analyzers, parsers, and other components.
    
    Attributes:
        registry: The plugin registry for component registration.
        is_active: Whether the plugin is currently active.
    """
    
    def __init__(self, registry: Optional[PluginRegistry] = None) -> None:
        """Initialize the plugin.
        
        Args:
            registry: Plugin registry to use (default: global registry).
        """
        self.registry = registry or get_plugin_registry()
        self.is_active = False
    
    @property
    @abstractmethod
    def metadata(self) -> PluginMetadata:
        """Get plugin metadata.
        
        Returns:
            Plugin metadata instance.
        """
        pass
    
    @abstractmethod
    def activate(self) -> None:
        """Activate the plugin.
        
        This method is called when the plugin is loaded. It should
        register all components provided by the plugin.
        """
        pass
    
    def deactivate(self) -> None:
        """Deactivate the plugin.
        
        This method is called when the plugin is unloaded. It should
        clean up any resources and unregister components.
        
        The default implementation does nothing.
        """
        pass
    
    def register_analyzer(
        self,
        name: str,
        analyzer_class: Type[Any],
        override: bool = False
    ) -> None:
        """Register an analyzer.
        
        Args:
            name: Unique name for the analyzer.
            analyzer_class: The analyzer class.
            override: Whether to override existing analyzer.
        """
        self.registry.register("analyzers", name, analyzer_class, override)
    
    def register_parser(
        self,
        name: str,
        parser_class: Type[Any],
        override: bool = False
    ) -> None:
        """Register a parser.
        
        Args:
            name: Unique name for the parser.
            parser_class: The parser class.
            override: Whether to override existing parser.
        """
        self.registry.register("parsers", name, parser_class, override)
    
    def register_metrics_backend(
        self,
        name: str,
        backend_class: Type[Any],
        override: bool = False
    ) -> None:
        """Register a metrics backend.
        
        Args:
            name: Unique name for the backend.
            backend_class: The backend class.
            override: Whether to override existing backend.
        """
        self.registry.register("backends", name, backend_class, override)
    
    def register_filter(
        self,
        name: str,
        filter_func: Callable[[str], bool],
        override: bool = False
    ) -> None:
        """Register a metrics filter.
        
        Args:
            name: Unique name for the filter.
            filter_func: The filter function.
            override: Whether to override existing filter.
        """
        self.registry.register("filters", name, filter_func, override)


class PluginManager:
    """Manager for loading and managing plugins.
    
    This class handles plugin discovery, loading, and lifecycle management.
    
    Attributes:
        registry: The plugin registry.
        plugins: Dictionary of loaded plugins.
    """
    
    def __init__(self, registry: Optional[PluginRegistry] = None) -> None:
        """Initialize the plugin manager.
        
        Args:
            registry: Plugin registry to use.
        """
        self.registry = registry or get_plugin_registry()
        self.plugins: Dict[str, Plugin] = {}
    
    def load_plugin(self, plugin_class: Type[Plugin]) -> None:
        """Load a plugin from a class.
        
        Args:
            plugin_class: The plugin class to load.
            
        Raises:
            PluginError: If plugin loading fails.
        """
        try:
            plugin = plugin_class(self.registry)
            metadata = plugin.metadata
            
            if metadata.name in self.plugins:
                raise PluginError(
                    f"Plugin already loaded: {metadata.name}",
                    plugin_name=metadata.name
                )
            
            plugin.activate()
            plugin.is_active = True
            self.plugins[metadata.name] = plugin
            
            logger.info(
                "Plugin loaded",
                extra={
                    "plugin": metadata.name,
                    "version": metadata.version
                }
            )
            
        except Exception as e:
            raise PluginError(
                f"Failed to load plugin: {e}",
                plugin_name=getattr(plugin_class, "__name__", "unknown")
            ) from e
    
    def load_plugin_from_module(self, module_path: str) -> None:
        """Load a plugin from a Python module.
        
        Args:
            module_path: Python module path (e.g., "mypackage.plugin").
            
        Raises:
            PluginError: If module loading fails.
        """
        try:
            module = importlib.import_module(module_path)
            
            # Find Plugin subclass in module
            plugin_class = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and 
                    issubclass(attr, Plugin) and 
                    attr is not Plugin):
                    plugin_class = attr
                    break
            
            if not plugin_class:
                raise PluginError(
                    f"No Plugin subclass found in module: {module_path}",
                    details={"module": module_path}
                )
            
            self.load_plugin(plugin_class)
            
        except ImportError as e:
            raise PluginError(
                f"Failed to import plugin module: {module_path}",
                details={"error": str(e)}
            ) from e
    
    def load_plugin_from_file(self, file_path: Path) -> None:
        """Load a plugin from a Python file.
        
        Args:
            file_path: Path to the plugin file.
            
        Raises:
            PluginError: If file loading fails.
        """
        if not file_path.exists():
            raise PluginError(
                f"Plugin file not found: {file_path}",
                details={"path": str(file_path)}
            )
        
        # Create module from file
        module_name = f"plugin_{file_path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        
        if not spec or not spec.loader:
            raise PluginError(f"Failed to load plugin spec from: {file_path}")
        
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # Find and load Plugin subclass
        plugin_class = None
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (isinstance(attr, type) and 
                issubclass(attr, Plugin) and 
                attr is not Plugin):
                plugin_class = attr
                break
        
        if not plugin_class:
            raise PluginError(
                f"No Plugin subclass found in file: {file_path}",
                details={"file": str(file_path)}
            )
        
        self.load_plugin(plugin_class)
    
    def unload_plugin(self, name: str) -> None:
        """Unload a plugin.
        
        Args:
            name: Plugin name to unload.
        """
        if name not in self.plugins:
            return
        
        plugin = self.plugins[name]
        plugin.deactivate()
        plugin.is_active = False
        del self.plugins[name]
        
        logger.info("Plugin unloaded", extra={"plugin": name})
    
    def get_plugin(self, name: str) -> Optional[Plugin]:
        """Get a loaded plugin.
        
        Args:
            name: Plugin name.
            
        Returns:
            Plugin instance or None if not found.
        """
        return self.plugins.get(name)
    
    def list_plugins(self) -> List[PluginMetadata]:
        """List all loaded plugins.
        
        Returns:
            List of plugin metadata.
        """
        return [plugin.metadata for plugin in self.plugins.values()]


# Global instances
_plugin_registry: Optional[PluginRegistry] = None
_plugin_manager: Optional[PluginManager] = None


def get_plugin_registry() -> PluginRegistry:
    """Get the global plugin registry.
    
    Returns:
        The global plugin registry instance.
    """
    global _plugin_registry
    if _plugin_registry is None:
        _plugin_registry = PluginRegistry()
    return _plugin_registry


def get_plugin_manager() -> PluginManager:
    """Get the global plugin manager.
    
    Returns:
        The global plugin manager instance.
    """
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager()
    return _plugin_manager