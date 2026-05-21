# tests/unit/domain/entities/test_timezone_helpers.py
"""Tests for timezone helpers and domain events in test_file module."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from robot_optimizer_core.domain.entities.test_file import (
    TestFile,
    TZAwareTestFile,
    TimezoneAwareDomainEvent,
    TimezoneAwareTestResult,
    format_datetime_local,
    parse_datetime_safe,
)


class TestTestFileTimestampValidator:
    def test_unix_timestamp_as_float(self) -> None:
        ts = datetime.now(UTC).timestamp()
        tf = TestFile.model_validate(
            {
                "path": Path("t.robot"),
                "content": "",
                "size_bytes": 0,
                "last_modified_utc": ts,
            }
        )
        assert tf.last_modified_utc.tzinfo is not None

    def test_iso_string_timestamp(self) -> None:
        iso = "2024-01-15T12:00:00+00:00"
        tf = TestFile.model_validate(
            {
                "path": Path("t.robot"),
                "content": "",
                "size_bytes": 0,
                "last_modified_utc": iso,
            }
        )
        assert tf.last_modified_utc.year == 2024

    def test_naive_iso_string_gets_utc(self) -> None:
        iso = "2024-06-01T00:00:00"
        tf = TestFile.model_validate(
            {
                "path": Path("t.robot"),
                "content": "",
                "size_bytes": 0,
                "last_modified_utc": iso,
            }
        )
        assert tf.last_modified_utc.tzinfo is not None

    def test_invalid_type_raises(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            TestFile.model_validate(
                {
                    "path": Path("t.robot"),
                    "content": "",
                    "size_bytes": 0,
                    "last_modified_utc": ["not", "a", "datetime"],
                }
            )

    def test_invalid_timezone_falls_back_to_utc(self) -> None:
        tf = TestFile.model_validate(
            {
                "path": Path("t.robot"),
                "content": "",
                "size_bytes": 0,
                "last_modified_utc": datetime.now(UTC),
                "display_timezone": "Not/A/Timezone",
            }
        )
        assert tf.display_timezone == "UTC"


class TestParseFromPathBinaryDetection:
    def test_binary_file_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "bin.robot"
        p.write_bytes(b"hello\x00world")
        with pytest.raises(ValueError, match="binary"):
            TestFile.from_path(p)


class TestParseDatetimeSafe:
    def test_iso_with_tz(self) -> None:
        dt = parse_datetime_safe("2024-03-15T10:30:00+02:00")
        assert dt.year == 2024

    def test_iso_with_z(self) -> None:
        dt = parse_datetime_safe("2024-03-15T10:30:00Z")
        assert dt.tzinfo is not None

    def test_iso_naive_gets_default_tz(self) -> None:
        dt = parse_datetime_safe("2024-03-15T10:30:00")
        assert dt.tzinfo is not None

    def test_non_iso_format_yyyy_mm_dd(self) -> None:
        dt = parse_datetime_safe("2024-03-15")
        assert dt.year == 2024

    def test_non_iso_with_time(self) -> None:
        dt = parse_datetime_safe("2024-03-15 10:30:00")
        assert dt.hour == 10

    def test_unrecognized_format_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid datetime"):
            parse_datetime_safe("not-a-date")

    def test_custom_default_tz(self) -> None:
        dt = parse_datetime_safe("2024-03-15T10:30:00", default_tz=UTC)
        assert dt.tzinfo is not None


class TestFormatDatetimeLocal:
    def test_formats_in_utc(self) -> None:
        dt = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        result = format_datetime_local(dt, "UTC")
        assert "2024-06-01" in result
        assert "12:00:00" in result

    def test_invalid_tz_falls_back_to_utc(self) -> None:
        dt = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        result = format_datetime_local(dt, "Not/A/Zone")
        assert "UTC" in result


class TestTimezoneAwareDomainEvent:
    def test_create_event_with_utc_timestamp(self) -> None:
        event = TimezoneAwareDomainEvent()
        assert event.occurred_at.tzinfo is not None

    def test_occurred_at_iso_property(self) -> None:
        event = TimezoneAwareDomainEvent()
        iso = event.occurred_at_iso
        assert "T" in iso

    def test_to_message_includes_event_fields(self) -> None:
        event = TimezoneAwareDomainEvent()
        msg = event.to_message()
        assert "event_id" in msg
        assert "occurred_at" in msg
        assert "occurred_at_unix" in msg

    def test_naive_datetime_gets_utc(self) -> None:
        naive = datetime(2024, 1, 1, 0, 0, 0)
        event = TimezoneAwareDomainEvent(occurred_at=naive)
        assert event.occurred_at.tzinfo is not None


class TestTimezoneAwareTestResult:
    def _make_result(self, **kwargs: object) -> TimezoneAwareTestResult:
        defaults = {
            "test_name": "T",
            "file_path": Path("s.robot"),
            "status": "PASS",
            "execution_time": 1.0,
            "timestamp": datetime.now(UTC),
        }
        defaults.update(kwargs)
        return TimezoneAwareTestResult.model_validate(defaults)

    def test_create_with_utc_timestamp(self) -> None:
        r = self._make_result()
        assert r.timestamp.tzinfo is not None

    def test_unix_timestamp_input(self) -> None:
        r = self._make_result(timestamp=datetime.now(UTC).timestamp())
        assert r.timestamp.tzinfo is not None

    def test_iso_string_input(self) -> None:
        r = self._make_result(timestamp="2024-01-01T00:00:00Z")
        assert r.timestamp.year == 2024

    def test_age_days_property(self) -> None:
        r = self._make_result()
        assert r.age_days >= 0

    def test_timestamp_iso_property(self) -> None:
        r = self._make_result()
        assert "T" in r.timestamp_iso

    def test_invalid_type_raises(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            self._make_result(timestamp={"not": "valid"})


@pytest.mark.unit
class TestTZAwareTestFileValidateTimezone:
    """Tests for TZAwareTestFile.validate_timezone explicit field coverage."""

    def _make_tf(self, **kwargs: object) -> TZAwareTestFile:
        defaults: dict[str, object] = {
            "path": Path("x.robot"),
            "content": "*** Test Cases ***\nT\n    Log    ok\n",
            "size_bytes": 30,
            "last_modified_utc": datetime.now(UTC),
        }
        defaults.update(kwargs)
        return TZAwareTestFile.model_validate(defaults)

    def test_valid_explicit_timezone_accepted(self) -> None:
        tf = self._make_tf(display_timezone="Europe/London")
        assert tf.display_timezone == "Europe/London"

    def test_invalid_timezone_falls_back_to_utc(self) -> None:
        tf = self._make_tf(display_timezone="Not/A/Real/Zone")
        assert tf.display_timezone == "UTC"

    def test_last_modified_local_with_valid_timezone(self) -> None:
        tf = self._make_tf(display_timezone="America/New_York")
        local = tf.last_modified_local
        assert local.tzinfo is not None


@pytest.mark.unit
class TestTimezoneAwareDomainEventNonDatetime:
    """Test ensure_utc validator with non-datetime values."""

    def test_non_datetime_occurred_at_passes_through(self) -> None:
        from pydantic import ValidationError

        with pytest.raises((ValidationError, Exception)):
            TimezoneAwareDomainEvent.model_validate(
                {"event_name": "E", "event_version": "1", "occurred_at": {"bad": True}}
            )
