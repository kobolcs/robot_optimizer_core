# tests/unit/test_version.py
"""Unit tests for VersionInfo."""

from __future__ import annotations

import pytest

from robot_optimizer_core.__version__ import VersionInfo


@pytest.mark.unit
class TestVersionInfo:
    def test_str_final_release(self) -> None:
        v = VersionInfo(1, 2, 3, "final", 0)
        assert str(v) == "1.2.3"

    def test_str_beta_release(self) -> None:
        v = VersionInfo(1, 0, 0, "b", 2)
        assert str(v) == "1.0.0b2"

    def test_str_alpha_release(self) -> None:
        v = VersionInfo(0, 9, 0, "alpha", 1)
        assert str(v) == "0.9.0alpha1"

    def test_lt_different_major(self) -> None:
        assert VersionInfo(1, 0, 0) < VersionInfo(2, 0, 0)
        assert not (VersionInfo(2, 0, 0) < VersionInfo(1, 0, 0))

    def test_lt_different_minor(self) -> None:
        assert VersionInfo(1, 0, 0) < VersionInfo(1, 1, 0)

    def test_lt_different_patch(self) -> None:
        assert VersionInfo(1, 0, 0) < VersionInfo(1, 0, 1)

    def test_lt_release_order_alpha_to_beta(self) -> None:
        assert VersionInfo(1, 0, 0, "alpha", 1) < VersionInfo(1, 0, 0, "beta", 1)

    def test_lt_release_order_beta_to_rc(self) -> None:
        assert VersionInfo(1, 0, 0, "beta", 1) < VersionInfo(1, 0, 0, "rc", 1)

    def test_lt_release_order_rc_to_final(self) -> None:
        assert VersionInfo(1, 0, 0, "rc", 1) < VersionInfo(1, 0, 0, "final", 0)

    def test_lt_serial_order(self) -> None:
        assert VersionInfo(1, 0, 0, "alpha", 1) < VersionInfo(1, 0, 0, "alpha", 2)

    def test_lt_equal_versions_not_less(self) -> None:
        v = VersionInfo(1, 0, 0, "final", 0)
        assert not (v < v)

    def test_lt_returns_not_implemented_for_non_version(self) -> None:
        v = VersionInfo(1, 0, 0)
        result = v.__lt__("not a version")
        assert result is NotImplemented

    def test_is_compatible_with_greater_version(self) -> None:
        current = VersionInfo(2, 0, 0)
        required = VersionInfo(1, 0, 0)
        assert current.is_compatible_with(required) is True

    def test_is_compatible_with_equal_version(self) -> None:
        v = VersionInfo(1, 0, 0)
        assert v.is_compatible_with(v) is True

    def test_is_compatible_with_higher_required(self) -> None:
        current = VersionInfo(1, 0, 0)
        required = VersionInfo(2, 0, 0)
        assert current.is_compatible_with(required) is False

    def test_is_prerelease_true(self) -> None:
        assert VersionInfo(1, 0, 0, "b", 1).is_prerelease is True
        assert VersionInfo(1, 0, 0, "alpha", 1).is_prerelease is True
        assert VersionInfo(1, 0, 0, "rc", 1).is_prerelease is True

    def test_is_prerelease_false(self) -> None:
        assert VersionInfo(1, 0, 0, "final", 0).is_prerelease is False

    def test_version_tuple(self) -> None:
        v = VersionInfo(3, 4, 5)
        assert v.version_tuple == (3, 4, 5)

    def test_equality(self) -> None:
        v1 = VersionInfo(1, 0, 0)
        v2 = VersionInfo(1, 0, 0)
        assert v1 == v2

    def test_total_ordering_greater_than(self) -> None:
        assert VersionInfo(2, 0, 0) > VersionInfo(1, 0, 0)

    def test_total_ordering_less_or_equal(self) -> None:
        assert VersionInfo(1, 0, 0) <= VersionInfo(1, 0, 0)
        assert VersionInfo(1, 0, 0) <= VersionInfo(2, 0, 0)
