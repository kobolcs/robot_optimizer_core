# src/robot_optimizer_core/boundaries.py
"""Error boundaries and transaction support for domain consistency."""
from __future__ import annotations

import functools
import traceback
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum, auto
from typing import Any, Callable, TypeVar, ParamSpec
from uuid import UUID, uuid4

from .exceptions import AnalysisError, RepositoryError
from .logging import get_logger

P = ParamSpec("P")
R = TypeVar("R")

logger = get_logger(__name__)


class TransactionState(StrEnum):
    """Transaction states."""
    PENDING = auto()
    COMMITTED = auto()
    ROLLED_BACK = auto()
    FAILED = auto()


@dataclass
class TransactionContext:
    """Context for a transaction with audit trail."""
    id: UUID = field(default_factory=uuid4)
    state: TransactionState = TransactionState.PENDING
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: datetime | None = None
    operations: list[dict[str, Any]] = field(default_factory=list)
    rollback_actions: list[Callable[[], None]] = field(default_factory=list)
    error: Exception | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_operation(self, operation: str, **details: Any) -> None:
        """Record an operation in the transaction."""
        self.operations.append({
            "operation": operation,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": details
        })

    def add_rollback(self, action: Callable[[], None]) -> None:
        """Add a rollback action."""
        self.rollback_actions.append(action)

    def commit(self) -> None:
        """Commit the transaction."""
        self.state = TransactionState.COMMITTED
        self.ended_at = datetime.now(timezone.utc)

    def rollback(self) -> None:
        """Rollback the transaction."""
        # Execute rollback actions in reverse order
        for action in reversed(self.rollback_actions):
            try:
                action()
            except Exception as e:
                logger.error(
                    f"Rollback action failed: {e}",
                    extra={"transaction_id": str(self.id)}
                )

        self.state = TransactionState.ROLLED_BACK
        self.ended_at = datetime.now(timezone.utc)

    @property
    def duration_ms(self) -> float | None:
        """Get transaction duration in milliseconds."""
        if self.ended_at:
            delta = self.ended_at - self.started_at
            return delta.total_seconds() * 1000
        return None


class ErrorBoundary:
    """Error boundary for consistent error handling and recovery."""

    def __init__(self, operation_name: str, fallback: Any = None):
        """Initialize error boundary.
        
        Args:
            operation_name: Name of the operation for logging
            fallback: Fallback value on error
        """
        self.operation_name = operation_name
        self.fallback = fallback
        self._error_handlers: dict[type[Exception], Callable] = {}
        self._finally_handlers: list[Callable] = []

    def handle(self, exception_type: type[Exception]) -> Callable:
        """Decorator to register error handler."""
        def decorator(handler: Callable) -> Callable:
            self._error_handlers[exception_type] = handler
            return handler
        return decorator

    def add_finally(self, handler: Callable) -> None:
        """Add a finally handler."""
        self._finally_handlers.append(handler)

    @contextmanager
    def guard(self, **context: Any):
        """Context manager for error boundary."""
        transaction = TransactionContext(
            metadata={"operation": self.operation_name, **context}
        )

        try:
            yield transaction
            transaction.commit()

        except Exception as e:
            transaction.error = e
            transaction.state = TransactionState.FAILED

            # Log error with context
            logger.error(
                f"Error in {self.operation_name}: {e}",
                extra={
                    "transaction_id": str(transaction.id),
                    "operation": self.operation_name,
                    "error_type": type(e).__name__,
                    "context": context,
                    "traceback": traceback.format_exc()
                }
            )

            # Try specific error handler
            handler = self._error_handlers.get(type(e))
            if handler:
                try:
                    result = handler(e, transaction)
                    if result is not None:
                        return result
                except Exception as handler_error:
                    logger.error(
                        f"Error handler failed: {handler_error}",
                        extra={"transaction_id": str(transaction.id)}
                    )

            # Rollback
            transaction.rollback()

            # Re-raise or return fallback
            if self.fallback is not None:
                return self.fallback
            raise

        finally:
            # Execute finally handlers
            for handler in self._finally_handlers:
                try:
                    handler(transaction)
                except Exception as e:
                    logger.error(f"Finally handler failed: {e}")


def transactional(
    operation_name: str | None = None,
    rollback_on: tuple[type[Exception], ...] = (Exception,),
    max_retries: int = 0,
    log_level: str = "ERROR"
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator for transactional operations with automatic rollback.
    
    Args:
        operation_name: Name for logging (defaults to function name)
        rollback_on: Exception types that trigger rollback
        max_retries: Number of retries on failure
        log_level: Logging level for errors
    """
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        op_name = operation_name or func.__name__

        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            retries = 0
            last_error = None

            while retries <= max_retries:
                transaction = TransactionContext(
                    metadata={
                        "operation": op_name,
                        "function": func.__name__,
                        "retry": retries
                    }
                )

                try:
                    # Record operation start
                    transaction.add_operation("start", args_count=len(args))

                    # Execute function
                    result = func(*args, **kwargs)

                    # Success - commit
                    transaction.commit()

                    if retries > 0:
                        logger.info(
                            f"Operation succeeded after {retries} retries",
                            extra={"operation": op_name}
                        )

                    return result

                except rollback_on as e:
                    last_error = e
                    transaction.error = e
                    transaction.state = TransactionState.FAILED

                    # Log based on level
                    log_method = getattr(logger, log_level.lower())
                    log_method(
                        f"Transaction failed in {op_name}: {e}",
                        extra={
                            "transaction_id": str(transaction.id),
                            "retry": retries,
                            "error_type": type(e).__name__
                        }
                    )

                    # Rollback
                    transaction.rollback()

                    # Check if we should retry
                    if retries < max_retries:
                        retries += 1
                        logger.info(f"Retrying {op_name} (attempt {retries + 1})")
                        continue

                    # Max retries exceeded
                    raise

                except Exception as e:
                    # Unexpected error - don't retry
                    transaction.error = e
                    transaction.state = TransactionState.FAILED
                    logger.error(
                        f"Unexpected error in {op_name}: {e}",
                        extra={"transaction_id": str(transaction.id)},
                        exc_info=True
                    )
                    raise

            # Should not reach here
            if last_error:
                raise last_error
            raise RuntimeError(f"Transaction failed after {max_retries} retries")

        return wrapper

    return decorator


class UnitOfWork:
    """Unit of Work pattern for managing aggregate transactions."""

    def __init__(self):
        """Initialize unit of work."""
        self._new: list[Any] = []
        self._dirty: list[Any] = []
        self._removed: list[Any] = []
        self._identity_map: dict[tuple[type, Any], Any] = {}
        self._transaction: TransactionContext | None = None
        self._repositories: dict[str, Any] = {}

    def register_new(self, entity: Any) -> None:
        """Register a new entity."""
        assert entity not in self._dirty, "Entity already marked as dirty"
        assert entity not in self._removed, "Entity already marked for removal"
        assert entity not in self._new, "Entity already registered as new"

        self._new.append(entity)
        self._add_to_identity_map(entity)

    def register_dirty(self, entity: Any) -> None:
        """Register a modified entity."""
        assert entity not in self._removed, "Entity already marked for removal"

        if entity not in self._dirty and entity not in self._new:
            self._dirty.append(entity)

    def register_removed(self, entity: Any) -> None:
        """Register an entity for removal."""
        if entity in self._new:
            self._new.remove(entity)
        else:
            self._dirty.remove(entity) if entity in self._dirty else None
            if entity not in self._removed:
                self._removed.append(entity)

        self._remove_from_identity_map(entity)

    def register_repository(self, name: str, repository: Any) -> None:
        """Register a repository for use in the unit of work."""
        self._repositories[name] = repository

    def get_repository(self, name: str) -> Any:
        """Get a registered repository."""
        if name not in self._repositories:
            raise ValueError(f"Repository '{name}' not registered")
        return self._repositories[name]

    @contextmanager
    def transaction(self):
        """Start a transaction context."""
        assert self._transaction is None, "Transaction already in progress"

        self._transaction = TransactionContext()

        try:
            yield self
            self.commit()
        except Exception:
            self.rollback()
            raise
        finally:
            self._transaction = None

    def commit(self) -> None:
        """Commit all changes."""
        if not self._transaction:
            raise RuntimeError("No transaction in progress")

        try:
            # Insert new entities
            for entity in self._new:
                repo_name = self._get_repository_name(entity)
                repo = self.get_repository(repo_name)
                repo.add(entity)
                self._transaction.add_operation("insert", entity_type=type(entity).__name__)

            # Update dirty entities
            for entity in self._dirty:
                repo_name = self._get_repository_name(entity)
                repo = self.get_repository(repo_name)
                repo.update(entity)
                self._transaction.add_operation("update", entity_type=type(entity).__name__)

            # Remove entities
            for entity in self._removed:
                repo_name = self._get_repository_name(entity)
                repo = self.get_repository(repo_name)
                repo.remove(entity)
                self._transaction.add_operation("delete", entity_type=type(entity).__name__)

            # Clear tracking
            self._new.clear()
            self._dirty.clear()
            self._removed.clear()

            self._transaction.commit()

        except Exception as e:
            self._transaction.error = e
            raise RepositoryError(
                f"Unit of work commit failed: {e}",
                operation="commit"
            ) from e

    def rollback(self) -> None:
        """Rollback all changes."""
        if self._transaction:
            self._transaction.rollback()

        # Clear all tracking
        self._new.clear()
        self._dirty.clear()
        self._removed.clear()
        self._identity_map.clear()

    def _add_to_identity_map(self, entity: Any) -> None:
        """Add entity to identity map."""
        key = (type(entity), entity.id)
        self._identity_map[key] = entity

    def _remove_from_identity_map(self, entity: Any) -> None:
        """Remove entity from identity map."""
        key = (type(entity), entity.id)
        self._identity_map.pop(key, None)

    def _get_repository_name(self, entity: Any) -> str:
        """Get repository name for entity type."""
        # Simple mapping - can be customized
        entity_type = type(entity).__name__.lower()
        return f"{entity_type}_repository"


# Example usage
def example_error_boundary_usage():
    """Example of using error boundaries."""
    # Create error boundary
    boundary = ErrorBoundary("file_analysis", fallback=[])

    # Register error handlers
    @boundary.handle(FileNotFoundError)
    def handle_file_not_found(e: FileNotFoundError, tx: TransactionContext) -> list:
        logger.warning(f"File not found: {e}")
        return []  # Return empty list as fallback

    @boundary.handle(PermissionError)
    def handle_permission(e: PermissionError, tx: TransactionContext) -> None:
        logger.error(f"Permission denied: {e}")
        # Re-raise with better error
        raise AnalysisError(f"Cannot access file: {e}") from e

    # Use boundary
    with boundary.guard(file="test.robot") as transaction:
        transaction.add_operation("open_file")
        # ... file operations ...
        transaction.add_operation("parse_file")
        # ... parsing ...

        # If error occurs, appropriate handler is called


@transactional(max_retries=3, rollback_on=(RepositoryError,))
def save_analysis_results(results: list[Any]) -> None:
    """Example of transactional operation with retries."""
    # This will automatically retry up to 3 times on RepositoryError
    # and rollback on failure
    pass


# Usage with unit of work
def example_unit_of_work():
    """Example of using unit of work pattern."""
    uow = UnitOfWork()

    # Register repositories
    uow.register_repository("testfile_repository", test_file_repo)
    uow.register_repository("finding_repository", finding_repo)

    # Use in transaction
    with uow.transaction():
        # Create new entities
        test_file = TestFile(...)
        uow.register_new(test_file)

        # Modify existing
        existing = test_file_repo.get(id)
        existing.content = "modified"
        uow.register_dirty(existing)

        # Remove
        old_file = test_file_repo.get(old_id)
        uow.register_removed(old_file)

        # All changes committed atomically at end of context
