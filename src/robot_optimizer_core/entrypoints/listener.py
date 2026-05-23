# src/robot_optimizer_core/entrypoints/listener.py
"""Robot Framework Listener V3 for real-time flakiness data capture.

Attach this listener to a Robot Framework run to automatically record
test results into a TestResultRepository so the FlakinessAnalyzer has
historical data to work with.

Usage (command line)::

    robot --listener robot_optimizer_core.entrypoints.listener.FlakinessListener:path/to/results.json tests/

Usage (Python)::

    from robot_optimizer_core.entrypoints.listener import FlakinessListener
    from robot_optimizer_core.infrastructure import JsonTestResultRepository

    repo = JsonTestResultRepository(Path("results.json"))
    listener = FlakinessListener(repository=repo)
    # pass to robot.run(..., listener=listener)
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..domain.repositories import TestResultRepository

from ..domain.value_objects import TestResult
from ..infrastructure.logging.adapter import get_logger

__all__ = ["FlakinessListener"]

logger = get_logger(__name__)


class FlakinessListener:
    """Robot Framework Listener V3 that persists test results for flakiness analysis.

    The listener captures ``end_test`` events and writes a :class:`TestResult`
    to the injected :class:`TestResultRepository` after every test.

    Attributes:
        ROBOT_LISTENER_API_VERSION: Must be 3 for the V3 listener protocol.
        repository: The repository used to persist results.
    """

    ROBOT_LISTENER_API_VERSION = 3

    def __init__(
        self,
        repository: TestResultRepository | None = None,
        results_path: str | Path | None = None,
    ) -> None:
        """Initialise the listener.

        Args:
            repository: Repository instance to use.  When omitted the listener
                looks in the DI container; if nothing is registered there it
                falls back to :class:`~robot_optimizer_core.infrastructure.JsonTestResultRepository`
                writing to *results_path* (default: ``flakiness_results.json`` in cwd).
            results_path: Path for the fallback JSON repository.  Ignored when
                *repository* is provided.
        """
        self.repository = repository or self._resolve_repository(results_path)
        # Tracks the source file path of the currently executing suite so that
        # end_test can record the correct file_path even when Robot does not
        # expose it directly on the test data object.
        self._current_source: Path | None = None

    # ------------------------------------------------------------------
    # Listener V3 protocol
    # ------------------------------------------------------------------

    def start_suite(self, data: Any, _result: Any) -> None:
        """Record the suite source so end_test knows which file a test belongs to."""
        source = getattr(data, "source", None)
        if source is not None:
            self._current_source = Path(source)

    def end_test(self, data: Any, result: Any) -> None:
        """Persist a test result after each test execution.

        Args:
            data: Robot Framework test data object (``robot.running.TestCase``).
            result: Robot Framework result object (``robot.result.TestCase``).
        """
        try:
            file_path = self._resolve_file_path(data)
            status = str(getattr(result, "status", "FAIL")).upper()
            if status not in {"PASS", "FAIL", "SKIP"}:
                status = "FAIL"

            elapsed = getattr(result, "elapsed_time", None)
            if elapsed is not None and hasattr(elapsed, "total_seconds"):
                execution_time = elapsed.total_seconds()
            elif isinstance(elapsed, (int, float)):
                execution_time = float(elapsed)
            else:
                execution_time = 0.0

            error_message: str | None = getattr(result, "message", None) or None

            test_result = TestResult(
                test_name=str(data.name),
                file_path=file_path,
                status=status,
                execution_time=execution_time,
                error_message=error_message,
                timestamp=datetime.now(tz=UTC),
            )
            self.repository.save_result(test_result)
            logger.debug(
                "Saved test result",
                extra={"test": data.name, "status": status, "file": str(file_path)},
            )
        except Exception as exc:
            # Never let listener errors abort the test run
            logger.warning(
                f"Failed to save test result for '{getattr(data, 'name', '?')}': {exc}",
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_file_path(self, data: Any) -> Path:
        """Return the .robot source file for the given test data object."""
        # Robot stores source on the parent Suite object; try both locations.
        source = (
            getattr(data, "source", None)
            or getattr(getattr(data, "parent", None), "source", None)
            or self._current_source
        )
        if source is not None:
            return Path(source)
        return Path("unknown.robot")

    @staticmethod
    def _resolve_repository(results_path: str | Path | None) -> TestResultRepository:
        """Return a repository from the DI container or build a JSON fallback."""
        try:
            from ..composition.container import get_container

            container = get_container()
            if container.has_service("test_result_repository"):
                repo: TestResultRepository = container.resolve("test_result_repository")
                return repo
        except Exception as exc:
            logger.debug("DI container unavailable, falling back to JSON repo: %s", exc)

        from ..infrastructure import JsonTestResultRepository

        path = Path(results_path) if results_path else Path("flakiness_results.json")
        return JsonTestResultRepository(path)
