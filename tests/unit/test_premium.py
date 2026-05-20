# tests/unit/test_premium.py
"""Unit tests for the premium feature boundary."""

from __future__ import annotations

import pytest

from robot_optimizer_core.premium import (
    PREMIUM_PACKAGE_NAME,
    PremiumFeatureError,
    fire_telemetry_event,
    is_premium_installed,
    register_telemetry_handler,
    requires_premium,
)


@pytest.mark.unit
class TestPremiumFeatureError:
    def test_message_contains_feature_name(self) -> None:
        err = PremiumFeatureError("html_reports")
        assert "html_reports" in str(err)

    def test_feature_name_attribute(self) -> None:
        err = PremiumFeatureError("export_pdf")
        assert err.feature_name == "export_pdf"

    def test_upgrade_url_attribute(self) -> None:
        err = PremiumFeatureError("x")
        assert err.upgrade_url is not None
        assert "http" in err.upgrade_url

    def test_message_contains_package_name(self) -> None:
        err = PremiumFeatureError("x")
        assert PREMIUM_PACKAGE_NAME in str(err)

    def test_is_exception(self) -> None:
        with pytest.raises(PremiumFeatureError):
            raise PremiumFeatureError("test_feature")


@pytest.mark.unit
class TestIsPremiumInstalled:
    def test_returns_bool(self) -> None:
        result = is_premium_installed()
        assert isinstance(result, bool)

    def test_returns_false_without_pro(self) -> None:
        # Pro package is not installed in the test environment
        assert is_premium_installed() is False


@pytest.mark.unit
class TestRequiresPremium:
    def test_raises_when_premium_not_installed(self) -> None:
        @requires_premium("fancy_feature")
        def fancy() -> str:
            return "fancy"

        with pytest.raises(PremiumFeatureError, match="fancy_feature"):
            fancy()

    def test_preserves_function_name(self) -> None:
        @requires_premium("feat")
        def my_func() -> None:
            pass

        assert my_func.__name__ == "my_func"

    def test_calls_function_when_premium_installed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import robot_optimizer_core.premium as _prem

        monkeypatch.setattr(_prem, "is_premium_installed", lambda: True)

        @requires_premium("feat")
        def real_fn() -> str:
            return "called"

        assert real_fn() == "called"


@pytest.mark.unit
class TestTelemetry:
    def test_fire_telemetry_no_op_without_handler(self) -> None:
        # Should not raise even with no handler registered
        fire_telemetry_event("some_event", key="value")

    def test_register_handler_is_called(self) -> None:
        import robot_optimizer_core.config.settings as settings_mod
        import robot_optimizer_core.premium as prem_mod
        from robot_optimizer_core.config import Settings

        calls: list[tuple[str, dict]] = []

        def handler(event: str, props: dict) -> None:
            calls.append((event, props))

        prem_mod._telemetry_handler = handler
        old_settings = settings_mod._settings
        settings_mod._settings = Settings(enable_telemetry=True)
        try:
            fire_telemetry_event("test_event", x=1)
            assert any(e == "test_event" for e, _ in calls)
        finally:
            prem_mod._telemetry_handler = None
            settings_mod._settings = old_settings

    def test_handler_exception_does_not_propagate(self) -> None:
        import robot_optimizer_core.config.settings as settings_mod
        import robot_optimizer_core.premium as prem_mod
        from robot_optimizer_core.config import Settings

        def bad_handler(event: str, props: dict) -> None:
            raise RuntimeError("handler exploded")

        prem_mod._telemetry_handler = bad_handler
        old_settings = settings_mod._settings
        settings_mod._settings = Settings(enable_telemetry=True)
        try:
            fire_telemetry_event("boom_event")  # must not raise
        finally:
            prem_mod._telemetry_handler = None
            settings_mod._settings = old_settings

    def test_fire_no_op_when_telemetry_disabled(self) -> None:
        import robot_optimizer_core.premium as prem_mod

        called = False

        def handler(event: str, props: dict) -> None:
            nonlocal called
            called = True

        prem_mod._telemetry_handler = handler
        try:
            # Default settings have enable_telemetry=False
            fire_telemetry_event("silent_event")
            assert not called
        finally:
            prem_mod._telemetry_handler = None

    def test_fire_no_op_when_settings_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import robot_optimizer_core.premium as prem_mod

        called = False

        def handler(event: str, props: dict) -> None:
            nonlocal called
            called = True

        prem_mod._telemetry_handler = handler

        def raise_error():
            raise RuntimeError("boom")

        # Simulate get_settings raising
        import robot_optimizer_core.config as conf_mod

        monkeypatch.setattr(conf_mod, "get_settings", raise_error)
        try:
            fire_telemetry_event("err_event")  # must not raise
            assert not called
        finally:
            prem_mod._telemetry_handler = None
            monkeypatch.undo()

    def test_register_telemetry_handler_sets_handler(self) -> None:
        import robot_optimizer_core.premium as prem_mod

        def my_handler(event: str, props: dict) -> None:
            pass

        old = prem_mod._telemetry_handler
        try:
            register_telemetry_handler(my_handler)
            assert prem_mod._telemetry_handler is my_handler
        finally:
            prem_mod._telemetry_handler = old

    def test_fire_no_op_when_telemetry_enabled_but_handler_none(self) -> None:
        import robot_optimizer_core.config.settings as settings_mod
        import robot_optimizer_core.premium as prem_mod
        from robot_optimizer_core.config import Settings

        old_handler = prem_mod._telemetry_handler
        old_settings = settings_mod._settings
        prem_mod._telemetry_handler = None
        settings_mod._settings = Settings(enable_telemetry=True)
        try:
            fire_telemetry_event("no_handler_event")  # must not raise, no handler
        finally:
            prem_mod._telemetry_handler = old_handler
            settings_mod._settings = old_settings
