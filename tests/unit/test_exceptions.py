# tests/unit/test_exceptions.py
"""Unit tests for custom exception hierarchy."""
from __future__ import annotations

from pathlib import Path

import pytest

from robot_optimizer_core.exceptions import (
    AnalysisError,
    ConfigurationError,
    FileNotFoundError,
    ParsingError,
    PluginError,
    RepositoryError,
    RobotOptimizerError,
    ValidationError,
    create_error,
)


@pytest.mark.unit
class TestRobotOptimizerError:
    def test_basic_message(self) -> None:
        err = RobotOptimizerError("something went wrong")
        assert str(err) == "something went wrong"
        assert err.message == "something went wrong"

    def test_details_default_empty(self) -> None:
        assert RobotOptimizerError("msg").details == {}

    def test_str_includes_details(self) -> None:
        err = RobotOptimizerError("error", details={"key": "value"})
        assert "key=value" in str(err)

    def test_str_without_details_is_message_only(self) -> None:
        assert str(RobotOptimizerError("just a message")) == "just a message"

    def test_is_exception(self) -> None:
        with pytest.raises(RobotOptimizerError):
            raise RobotOptimizerError("raised")

    def test_caller_details_preserved(self) -> None:
        err = RobotOptimizerError("msg", details={"extra": "data"})
        assert err.details["extra"] == "data"


@pytest.mark.unit
class TestAnalysisError:
    def test_defaults(self) -> None:
        err = AnalysisError("analysis failed")
        assert err.file_path is None
        assert err.analyzer is None

    def test_with_file_path(self) -> None:
        path = Path("tests/login.robot")
        assert AnalysisError("failed", file_path=path).file_path == path

    def test_with_analyzer(self) -> None:
        assert AnalysisError("failed", analyzer="DeadCodeAnalyzer").analyzer == "DeadCodeAnalyzer"

    def test_slots_not_mirrored_to_details(self) -> None:
        err = AnalysisError("msg", file_path=Path("a.robot"), analyzer="X")
        assert "file_path" not in err.details
        assert "analyzer" not in err.details

    def test_caller_details_preserved(self) -> None:
        err = AnalysisError("msg", details={"extra": "info"})
        assert err.details["extra"] == "info"

    def test_inherits_from_base(self) -> None:
        assert isinstance(AnalysisError("msg"), RobotOptimizerError)


@pytest.mark.unit
class TestParsingError:
    def test_defaults(self) -> None:
        err = ParsingError("syntax error", file_path=Path("test.robot"))
        assert err.file_path == Path("test.robot")
        assert err.line_number is None
        assert err.column is None

    def test_with_location(self) -> None:
        err = ParsingError("error", file_path=Path("f.robot"), line_number=42, column=8)
        assert err.line_number == 42
        assert err.column == 8

    def test_slots_not_mirrored_to_details(self) -> None:
        err = ParsingError("msg", file_path=Path("f.robot"), line_number=5, column=3)
        assert "line_number" not in err.details
        assert "column" not in err.details

    def test_inherits_from_analysis_error(self) -> None:
        assert isinstance(ParsingError("msg", file_path=Path("f.robot")), AnalysisError)


@pytest.mark.unit
class TestConfigurationError:
    def test_defaults(self) -> None:
        err = ConfigurationError("bad config")
        assert err.config_key is None
        assert err.provided_value is None

    def test_with_key_and_value(self) -> None:
        err = ConfigurationError("invalid", config_key="max_size", provided_value=-1)
        assert err.config_key == "max_size"
        assert err.provided_value == -1

    def test_slots_not_mirrored_to_details(self) -> None:
        err = ConfigurationError("msg", config_key="k", provided_value="v")
        assert "config_key" not in err.details
        assert "provided_value" not in err.details

    def test_inherits_from_base(self) -> None:
        assert isinstance(ConfigurationError("msg"), RobotOptimizerError)


@pytest.mark.unit
class TestPluginError:
    def test_defaults(self) -> None:
        err = PluginError("load failed")
        assert err.plugin_name is None
        assert err.plugin_type is None

    def test_with_plugin_info(self) -> None:
        err = PluginError("failed", plugin_name="my-plugin", plugin_type="analyzer")
        assert err.plugin_name == "my-plugin"
        assert err.plugin_type == "analyzer"

    def test_slots_not_mirrored_to_details(self) -> None:
        err = PluginError("msg", plugin_name="p", plugin_type="t")
        assert "plugin_name" not in err.details
        assert "plugin_type" not in err.details

    def test_caller_details_preserved(self) -> None:
        err = PluginError("msg", details={"violations": ["bad import"]})
        assert err.details["violations"] == ["bad import"]


@pytest.mark.unit
class TestValidationError:
    def test_defaults(self) -> None:
        err = ValidationError("invalid value")
        assert err.field_name is None
        assert err.invalid_value is None
        assert err.validation_rule is None

    def test_with_all_fields(self) -> None:
        err = ValidationError(
            "too small",
            field_name="size_bytes",
            invalid_value=-1,
            validation_rule="must be >= 0",
        )
        assert err.field_name == "size_bytes"
        assert err.invalid_value == -1
        assert err.validation_rule == "must be >= 0"

    def test_slots_not_mirrored_to_details(self) -> None:
        err = ValidationError("msg", field_name="f", invalid_value=0, validation_rule="r")
        assert "field_name" not in err.details
        assert "invalid_value" not in err.details
        assert "validation_rule" not in err.details


@pytest.mark.unit
class TestFileNotFoundError:
    def test_auto_message_includes_path(self) -> None:
        err = FileNotFoundError(Path("missing.robot"))
        assert "missing.robot" in str(err)

    def test_file_path_attribute(self) -> None:
        assert FileNotFoundError(Path("missing.robot")).file_path == Path("missing.robot")

    def test_inherits_from_analysis_error(self) -> None:
        assert isinstance(FileNotFoundError(Path("x.robot")), AnalysisError)


@pytest.mark.unit
class TestRepositoryError:
    def test_defaults(self) -> None:
        err = RepositoryError("db failed")
        assert err.repository_name is None
        assert err.operation is None

    def test_with_context(self) -> None:
        err = RepositoryError("failed", repository_name="TestResultRepo", operation="save")
        assert err.repository_name == "TestResultRepo"
        assert err.operation == "save"

    def test_slots_not_mirrored_to_details(self) -> None:
        err = RepositoryError("msg", repository_name="R", operation="load")
        assert "repository_name" not in err.details
        assert "operation" not in err.details


@pytest.mark.unit
class TestCreateError:
    def test_creates_correct_type(self) -> None:
        err = create_error(AnalysisError, "msg", file_path=Path("f.robot"))
        assert isinstance(err, AnalysisError)
        assert err.file_path == Path("f.robot")

    def test_passes_kwargs(self) -> None:
        err = create_error(PluginError, "msg", plugin_name="p", plugin_type="t")
        assert err.plugin_name == "p"
        assert err.plugin_type == "t"

    def test_base_error_creation(self) -> None:
        err = create_error(RobotOptimizerError, "base error")
        assert err.message == "base error"
