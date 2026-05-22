# src/robot_optimizer_core/domain/repositories/interfaces.py
"""Re-exports repository port interfaces from domain/ports/repository.py."""

from ..ports.repository import ITestFileRepository, ITestResultRepository

__all__ = ["ITestFileRepository", "ITestResultRepository"]
