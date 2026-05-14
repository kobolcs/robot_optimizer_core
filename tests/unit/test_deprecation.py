# tests/unit/test_deprecation.py
"""Unit tests for the deprecation utilities."""

from __future__ import annotations

import warnings

import pytest

from robot_optimizer_core.deprecation import (
    RobotOptimizerDeprecationWarning,
    check_deprecated,
    deprecated,
    deprecated_parameter,
    deprecation_warning,
    get_deprecation_info,
    renamed_parameter,
)


@pytest.mark.unit
class TestDeprecatedDecorator:
    def test_warns_on_call(self) -> None:
        @deprecated(since="1.0.0")
        def old_fn() -> str:
            return "result"

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = old_fn()
            assert result == "result"
            assert len(w) == 1
            assert issubclass(w[0].category, RobotOptimizerDeprecationWarning)
            assert "1.0.0" in str(w[0].message)

    def test_message_includes_removed_in(self) -> None:
        @deprecated(since="1.0.0", removed_in="2.0.0")
        def old_fn() -> None:
            # Intentionally empty; tests the decorator, not the function behavior.
            pass

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            old_fn()
            assert "2.0.0" in str(w[0].message)

    def test_message_includes_replacement(self) -> None:
        @deprecated(since="1.0.0", replacement="new_fn")
        def old_fn() -> None:
            # Intentionally empty; tests the decorator, not the function behavior.
            pass

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            old_fn()
            assert "new_fn" in str(w[0].message)

    def test_preserves_function_metadata(self) -> None:
        @deprecated(since="1.0.0")
        def my_func() -> None:
            """My docstring."""

        assert my_func.__name__ == "my_func"

    def test_deprecated_class_warns_on_instantiation(self) -> None:
        @deprecated(since="1.0.0", replacement="NewClass")
        class OldClass:
            pass

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            OldClass()
            assert len(w) == 1
            assert "NewClass" in str(w[0].message)


@pytest.mark.unit
class TestDeprecationWarning:
    def test_issues_warning(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            deprecation_warning("'old_thing' is deprecated since 1.0.0.")
            assert len(w) == 1
            assert issubclass(w[0].category, RobotOptimizerDeprecationWarning)

    def test_stacklevel_param(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            deprecation_warning("'old' is deprecated.", stacklevel=2)
            assert len(w) == 1


@pytest.mark.unit
class TestDeprecatedParameter:
    def test_issues_warning(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            deprecated_parameter("old_param", since="1.0.0", replacement="new_param")
            assert len(w) == 1
            assert "old_param" in str(w[0].message)


@pytest.mark.unit
class TestCheckAndGetDeprecationInfo:
    def test_check_deprecated_on_decorated(self) -> None:
        @deprecated(since="1.0.0")
        def old() -> None:
            # Intentionally empty; tests the decorator, not the function behavior.
            pass

        assert check_deprecated(old) is True

    def test_check_deprecated_on_normal(self) -> None:
        def normal() -> None:
            # Intentionally empty; tests that non-decorated functions are not flagged.
            pass

        assert check_deprecated(normal) is False

    def test_get_info_on_decorated(self) -> None:
        @deprecated(since="1.5.0", replacement="better")
        def old() -> None:
            # Intentionally empty; tests the decorator, not the function behavior.
            pass

        info = get_deprecation_info(old)
        assert info is not None
        assert info["since"] == "1.5.0"
        assert info["replacement"] == "better"

    def test_get_info_on_normal_returns_none(self) -> None:
        def normal() -> None:
            # Intentionally empty; tests that non-decorated functions return no info.
            pass

        assert get_deprecation_info(normal) is None


@pytest.mark.unit
class TestRenamedParameter:
    def test_remaps_old_param_to_new(self) -> None:
        @renamed_parameter(old_name="new_name")
        def fn(*, new_name: str = "") -> str:
            return new_name

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = fn(old_name="hello")
            assert result == "hello"
            assert len(w) == 1
