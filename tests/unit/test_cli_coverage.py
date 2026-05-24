# tests/unit/test_cli_coverage.py
"""Coverage tests for cli/_commands.py branches not exercised by test_cli.py."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from robot_optimizer_core.entrypoints.cli import main

# ---------------------------------------------------------------------------
# ExceptionGroup in _analyze_path
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExceptionGroupInAnalyzePath:
    def test_exception_group_prints_each_sub_error(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        robot_file = tmp_path / "t.robot"
        robot_file.write_text("*** Test Cases ***\nT\n    Log    hi\n")
        eg = ExceptionGroup("multi", [ValueError("err1"), RuntimeError("err2")])
        with patch("robot_optimizer_core.entrypoints.cli._commands.analyze_file", side_effect=eg):
            with pytest.raises(SystemExit) as exc:
                main(["analyze", str(robot_file)])
        assert exc.value.code == 2
        err = capsys.readouterr().err
        assert "err1" in err
        assert "err2" in err


# ---------------------------------------------------------------------------
# --clear-cache flag
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestClearCacheFlag:
    def test_clear_cache_flag_invokes_cache_clear(self, tmp_path: Path) -> None:
        robot_file = tmp_path / "t.robot"
        robot_file.write_text("*** Test Cases ***\nT\n    Log    hi\n")
        mock_service = MagicMock()
        mock_service.clear_cache = MagicMock()
        mock_service.analyze_file_with_meta.return_value = ([], ())
        with patch(
            "robot_optimizer_core.composition.context.get_analysis_service",
            return_value=mock_service,
        ), pytest.raises(SystemExit):
            main(["analyze", "--clear-cache", str(robot_file)])
        mock_service.clear_cache.assert_called_once()


# ---------------------------------------------------------------------------
# --watch dispatches to _run_watch_mode
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWatchModeDispatch:
    def test_watch_flag_calls_watch_mode(self, tmp_path: Path) -> None:
        robot_file = tmp_path / "t.robot"
        robot_file.write_text("*** Test Cases ***\nT\n    Log    hi\n")
        with patch(
            "robot_optimizer_core.entrypoints.cli._commands._run_watch_mode", return_value=0
        ) as mock_watch, pytest.raises(SystemExit) as exc:
            main(["analyze", "--watch", str(robot_file)])
        mock_watch.assert_called_once()
        assert exc.value.code == 0


# ---------------------------------------------------------------------------
# _run_watch_mode: missing watchdog
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWatchModeWatchdogMissing:
    def test_missing_watchdog_prints_install_hint(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        robot_file = tmp_path / "t.robot"
        robot_file.write_text("*** Test Cases ***\nT\n    Log    hi\n")
        broken = {"watchdog": None, "watchdog.events": None, "watchdog.observers": None}
        with patch.dict(sys.modules, broken), pytest.raises(SystemExit) as exc:
            main(["analyze", "--watch", str(robot_file)])
        assert exc.value.code == 2
        err = capsys.readouterr().err
        assert "watchdog" in err.lower() or "watch" in err.lower()


# ---------------------------------------------------------------------------
# _run_watch_mode: happy path (mocked watchdog)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWatchModeHappyPath:
    def test_watch_mode_runs_and_exits_on_signal(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import signal as signal_module

        robot_file = tmp_path / "t.robot"
        robot_file.write_text("*** Test Cases ***\nT\n    Log    hi\n")

        captured: dict = {}

        def fake_signal(sig: int, handler: object) -> None:
            captured[sig] = handler

        sleep_calls: list[int] = []

        def fake_sleep(t: float) -> None:
            sleep_calls.append(1)
            # After first sleep, fire the SIGINT handler to exit the loop.
            handler = captured.get(signal_module.SIGINT)
            if handler and callable(handler):
                handler(signal_module.SIGINT, None)

        mock_observer = MagicMock()
        mock_observer_cls = MagicMock(return_value=mock_observer)

        mock_events = MagicMock()
        mock_events.FileSystemEventHandler = object
        mock_events.FileModifiedEvent = MagicMock
        mock_events.DirModifiedEvent = MagicMock

        mock_observers_mod = MagicMock()
        mock_observers_mod.Observer = mock_observer_cls

        fake_watchdog_modules = {
            "watchdog": MagicMock(),
            "watchdog.events": mock_events,
            "watchdog.observers": mock_observers_mod,
        }

        with patch.dict(sys.modules, fake_watchdog_modules), \
             patch("robot_optimizer_core.entrypoints.cli._commands.signal.signal", side_effect=fake_signal), \
             patch("robot_optimizer_core.entrypoints.cli._commands.time.sleep", side_effect=fake_sleep), \
             patch(
                 "robot_optimizer_core.entrypoints.cli._commands._analyze_path",
                 return_value=([], False),
             ):
            with pytest.raises(SystemExit) as exc:
                main(["analyze", "--watch", str(tmp_path)])

        assert exc.value.code == 0
        mock_observer.start.assert_called_once()
        mock_observer.stop.assert_called_once()
        mock_observer.join.assert_called_once()
        assert sleep_calls  # loop executed at least once


# ---------------------------------------------------------------------------
# _run_upgrade: premium installed branch
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUpgradePremiumInstalled:
    def test_premium_installed_shows_tick(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with patch("robot_optimizer_core.premium.is_premium_installed", return_value=True):
            with pytest.raises(SystemExit) as exc:
                main(["upgrade"])
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "installed" in out.lower()


# ---------------------------------------------------------------------------
# diagnose subcommand
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDiagnoseCommand:
    def test_diagnose_exits_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exc:
            main(["diagnose"])
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert out.strip().startswith("{")

    def test_ensure_utf8_streams_skips_non_reconfigurable_stream(self) -> None:
        from robot_optimizer_core.entrypoints.cli import _ensure_utf8_streams

        class _NoReconfigure:
            pass

        original_stdout = sys.stdout
        original_stderr = sys.stderr
        try:
            sys.stdout = _NoReconfigure()  # type: ignore[assignment]
            sys.stderr = _NoReconfigure()  # type: ignore[assignment]
            _ensure_utf8_streams()  # must not raise
        finally:
            sys.stdout = original_stdout
            sys.stderr = original_stderr


# ---------------------------------------------------------------------------
# _run_list_analyzers: error path and no-tags branch
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestListAnalyzersErrorPath:
    def test_broken_analyzer_info_prints_error_line(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        mock_registry = MagicMock()
        mock_registry.list.return_value = ["fake_analyzer"]
        mock_registry.get_info.side_effect = KeyError("missing")

        with patch(
            "robot_optimizer_core.application.analyzers.get_analyzer_registry",
            return_value=mock_registry,
        ), pytest.raises(SystemExit) as exc:
            main(["list-analyzers"])
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "error loading info" in out


@pytest.mark.unit
class TestListAnalyzersNoTagsPath:
    def test_no_tags_branch_skips_tags_line(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        mock_registry = MagicMock()
        mock_registry.list.return_value = ["fake_analyzer"]
        mock_registry.get_info.return_value = {
            "description": "A description",
            "version": "1.0",
            "tags": "",
        }

        with patch(
            "robot_optimizer_core.application.analyzers.get_analyzer_registry",
            return_value=mock_registry,
        ), pytest.raises(SystemExit) as exc:
            main(["list-analyzers"])
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "A description" in out
