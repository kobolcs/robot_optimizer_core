# tests/unit/config/test_settings.py
"""Unit tests for Settings configuration."""

from __future__ import annotations

from pathlib import Path

import pydantic
import pytest

from robot_optimizer_core.exceptions import ConfigurationError
from robot_optimizer_core.infrastructure.config.settings import (
    Settings,
    configure_settings,
    get_settings,
    reset_settings,
)


@pytest.fixture(autouse=True)
def _reset_settings():
    """Reset global settings before and after each test."""
    reset_settings()
    yield
    reset_settings()


@pytest.mark.unit
class TestSettingsDefaults:
    def test_default_max_file_size(self) -> None:
        s = Settings()
        assert s.max_file_size_mb == 10.0

    def test_default_file_patterns(self) -> None:
        s = Settings()
        assert "*.robot" in s.file_patterns

    def test_max_file_size_bytes(self) -> None:
        s = Settings(max_file_size_mb=1.0)
        assert s.max_file_size_bytes == 1024 * 1024

    def test_to_dict(self) -> None:
        s = Settings()
        d = s.to_dict()
        assert isinstance(d, dict)
        assert "max_file_size_mb" in d


@pytest.mark.unit
class TestSettingsValidators:
    def test_empty_file_patterns_raises(self) -> None:
        with pytest.raises(pydantic.ValidationError):
            Settings(file_patterns=[])

    def test_empty_exclude_patterns_raises(self) -> None:
        with pytest.raises(pydantic.ValidationError):
            Settings(exclude_patterns=[])

    def test_log_level_validator_runs(self) -> None:
        s = Settings(log_level="WARNING")
        assert s.log_level == "WARNING"

    def test_plugin_dirs_nonexistent_skipped(self, tmp_path: Path) -> None:
        s = Settings(plugin_dirs=[str(tmp_path / "nonexistent")])
        assert s.plugin_dirs == []

    def test_plugin_dirs_file_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "notadir.txt"
        f.write_text("x")
        with pytest.raises(Exception, match="not a directory"):
            Settings(plugin_dirs=[str(f)])

    def test_plugin_dirs_valid_dir(self, tmp_path: Path) -> None:
        s = Settings(plugin_dirs=[str(tmp_path)])
        assert tmp_path in s.plugin_dirs

    def test_pattern_overlap_raises(self) -> None:
        with pytest.raises(ConfigurationError, match="overlap"):
            Settings(
                file_patterns=["*.robot"],
                exclude_patterns=["*.robot"],
            )


@pytest.mark.unit
class TestCustomSettings:
    def test_get_custom_setting_returns_default(self) -> None:
        s = Settings()
        assert s.get_custom_setting("missing_key", default=42) == 42

    def test_get_custom_setting_returns_value(self) -> None:
        s = Settings(custom_settings={"my_key": "my_value"})
        assert s.get_custom_setting("my_key") == "my_value"

    def test_get_custom_setting_type_valid(self) -> None:
        s = Settings(custom_settings={"count": 5})
        assert s.get_custom_setting("count", setting_type=int) == 5

    def test_get_custom_setting_type_mismatch_raises(self) -> None:
        s = Settings(custom_settings={"count": "not_an_int"})
        with pytest.raises(ConfigurationError):
            s.get_custom_setting("count", setting_type=int)

    def test_set_custom_setting(self) -> None:
        s = Settings()
        s.set_custom_setting("dynamic_key", "dynamic_value")
        assert s.get_custom_setting("dynamic_key") == "dynamic_value"


@pytest.mark.unit
class TestGetSettings:
    def test_get_settings_returns_instance(self) -> None:
        s = get_settings()
        assert isinstance(s, Settings)

    def test_get_settings_returns_same_instance(self) -> None:
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_configure_settings_overrides(self) -> None:
        s = configure_settings(max_file_size_mb=20.0)
        assert s.max_file_size_mb == 20.0

    def test_configure_settings_updates_global(self) -> None:
        configure_settings(max_file_size_mb=5.0)
        assert get_settings().max_file_size_mb == 5.0

    def test_reset_settings_clears_global(self) -> None:
        get_settings()
        reset_settings()
        # Next call should create a fresh instance
        s = get_settings()
        assert s is not None
