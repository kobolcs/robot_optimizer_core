"""File discovery services."""

from .file_finder import OptimizedFileDiscoveryService

# Alias for backward compatibility
FileDiscoveryService = OptimizedFileDiscoveryService

__all__ = ["FileDiscoveryService", "OptimizedFileDiscoveryService"]
