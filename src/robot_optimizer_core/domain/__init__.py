# src/robot_optimizer_core/domain/__init__.py
"""Core domain models for Robot Framework Optimizer.

This module contains the essential domain models including:
- Base classes for DDD patterns
- Core entities and value objects
- Repository interfaces
"""

from .base import ValueObject, Entity, AggregateRoot, DomainEvent

__all__ = [
    "ValueObject",
    "Entity", 
    "AggregateRoot",
    "DomainEvent",
]
