# tests/unit/test_cache.py
"""Unit tests for the file-hash analysis cache."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from robot_optimizer_core.cache import (
    AnalysisCache,
    _finding_from_dict,
    _finding_to_dict,
)
from robot_optimizer_core.domain.value_objects import Finding, Severity
from robot_optimizer_core.domain.value_objects.location import Location
from robot_optimizer_core.domain.value_objects.pattern import Pattern, PatternType

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_pattern() -> Pattern:
    return Pattern(
        type=PatternType.SLEEP_IN_TEST,
        name="sleep_in_test",
        description="A sleep was found in a test",
        recommendation="Replace sleep with an explicit wait",
    )


def _make_finding(file_path: Path, line: int = 10) -> Finding:
    return Finding.create(
        pattern=_make_pattern(),
        severity=Severity.WARNING,
        location=Location(file_path, line),
        message="Sleep detected",
    )


# ---------------------------------------------------------------------------
# _finding_to_dict / _finding_from_dict round-trip
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFindingSerialisation:
    def test_round_trip_preserves_key_fields(self, tmp_path: Path) -> None:
        fp = tmp_path / "suite.robot"
        original = _make_finding(fp)

        restored = _finding_from_dict(_finding_to_dict(original))

        assert restored.message == original.message
        assert restored.severity == original.severity
        assert restored.location.file_path == original.location.file_path
        assert restored.location.line == original.location.line
        assert restored.pattern.name == original.pattern.name
        assert restored.pattern.type == original.pattern.type
        assert restored.pattern.recommendation == original.pattern.recommendation

    def test_round_trip_with_context(self, tmp_path: Path) -> None:
        fp = tmp_path / "suite.robot"
        finding = Finding.create(
            pattern=_make_pattern(),
            severity=Severity.ERROR,
            location=Location(fp, 5),
            message="With context",
            keyword_name="My Keyword",
        )

        restored = _finding_from_dict(_finding_to_dict(finding))

        assert restored.context is not None
        assert restored.context.get("keyword_name") == "My Keyword"

    def test_to_dict_produces_json_serialisable_output(self, tmp_path: Path) -> None:
        fp = tmp_path / "suite.robot"
        finding = _make_finding(fp)
        d = _finding_to_dict(finding)
        # Must not raise
        json.dumps(d)

    def test_round_trip_no_context(self, tmp_path: Path) -> None:
        fp = tmp_path / "suite.robot"
        finding = _make_finding(fp)
        assert finding.context is None

        restored = _finding_from_dict(_finding_to_dict(finding))
        assert restored.context is None

    def test_all_severity_levels_round_trip(self, tmp_path: Path) -> None:
        fp = tmp_path / "suite.robot"
        for sev in (Severity.ERROR, Severity.WARNING, Severity.INFO):
            finding = Finding.create(
                pattern=_make_pattern(),
                severity=sev,
                location=Location(fp, 1),
                message="test",
            )
            assert _finding_from_dict(_finding_to_dict(finding)).severity == sev


# ---------------------------------------------------------------------------
# AnalysisCache.file_hash
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFileHash:
    def test_same_content_same_hash(self, tmp_path: Path) -> None:
        f = tmp_path / "f.robot"
        f.write_bytes(b"content")
        assert AnalysisCache.file_hash(f) == AnalysisCache.file_hash(f)

    def test_different_content_different_hash(self, tmp_path: Path) -> None:
        a = tmp_path / "a.robot"
        b = tmp_path / "b.robot"
        a.write_bytes(b"alpha")
        b.write_bytes(b"beta")
        assert AnalysisCache.file_hash(a) != AnalysisCache.file_hash(b)

    def test_hash_is_64_hex_chars(self, tmp_path: Path) -> None:
        f = tmp_path / "f.robot"
        f.write_bytes(b"x")
        h = AnalysisCache.file_hash(f)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


# ---------------------------------------------------------------------------
# AnalysisCache get / put / flush
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAnalysisCacheGetPut:
    def test_miss_on_empty_cache(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "cache"
        cache = AnalysisCache(cache_dir=cache_dir)
        fp = tmp_path / "suite.robot"
        fp.write_bytes(b"*** Test Cases ***\n")
        assert cache.get(fp, "any_hash") is None

    def test_hit_after_put_and_flush(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "cache"
        cache = AnalysisCache(cache_dir=cache_dir)
        fp = tmp_path / "suite.robot"
        fp.write_bytes(b"*** Test Cases ***\n")
        h = cache.file_hash(fp)

        findings = [_make_finding(fp)]
        cache.put(fp, h, findings)
        cache.flush()

        cache2 = AnalysisCache(cache_dir=cache_dir)
        result = cache2.get(fp, h)
        assert result is not None
        assert len(result) == 1
        assert result[0].message == findings[0].message

    def test_miss_on_different_hash(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "cache"
        cache = AnalysisCache(cache_dir=cache_dir)
        fp = tmp_path / "suite.robot"
        fp.write_bytes(b"v1")
        h1 = cache.file_hash(fp)

        cache.put(fp, h1, [_make_finding(fp)])
        cache.flush()

        fp.write_bytes(b"v2")
        h2 = cache.file_hash(fp)

        assert cache.get(fp, h2) is None

    def test_flush_not_dirty_does_not_create_file(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "cache"
        cache = AnalysisCache(cache_dir=cache_dir)
        cache.flush()
        assert not (cache_dir / "cache.json").exists()

    def test_cache_persists_empty_findings_list(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "cache"
        cache = AnalysisCache(cache_dir=cache_dir)
        fp = tmp_path / "suite.robot"
        fp.write_bytes(b"x")
        h = cache.file_hash(fp)

        cache.put(fp, h, [])
        cache.flush()

        result = AnalysisCache(cache_dir=cache_dir).get(fp, h)
        assert result == []


# ---------------------------------------------------------------------------
# AnalysisCache.clear
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAnalysisCacheClear:
    def test_clear_removes_cache_file(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "cache"
        cache = AnalysisCache(cache_dir=cache_dir)
        fp = tmp_path / "suite.robot"
        fp.write_bytes(b"x")
        h = cache.file_hash(fp)

        cache.put(fp, h, [_make_finding(fp)])
        cache.flush()
        assert cache.path.exists()

        cache.clear()
        assert not cache.path.exists()

    def test_clear_results_in_miss(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "cache"
        cache = AnalysisCache(cache_dir=cache_dir)
        fp = tmp_path / "suite.robot"
        fp.write_bytes(b"x")
        h = cache.file_hash(fp)

        cache.put(fp, h, [_make_finding(fp)])
        cache.flush()
        cache.clear()

        assert cache.get(fp, h) is None

    def test_clear_on_nonexistent_cache_does_not_raise(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "no_such_dir"
        cache = AnalysisCache(cache_dir=cache_dir)
        cache.clear()  # must not raise


# ---------------------------------------------------------------------------
# Corrupt / invalid cache file resilience
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCacheResilience:
    def test_corrupt_cache_file_treated_as_empty(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        (cache_dir / "cache.json").write_text("NOT JSON {{", encoding="utf-8")

        cache = AnalysisCache(cache_dir=cache_dir)
        fp = tmp_path / "f.robot"
        fp.write_bytes(b"x")
        assert cache.get(fp, "any") is None

    def test_wrong_type_cache_file_treated_as_empty(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        (cache_dir / "cache.json").write_text("[1, 2, 3]", encoding="utf-8")

        cache = AnalysisCache(cache_dir=cache_dir)
        fp = tmp_path / "f.robot"
        fp.write_bytes(b"x")
        assert cache.get(fp, "any") is None

    def test_invalid_entry_treated_as_miss(self, tmp_path: Path) -> None:
        fp = tmp_path / "suite.robot"
        fp.write_bytes(b"x")
        h = "deadbeef"

        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        bad_entry: dict = {f"{fp.resolve()}#{h}": [{"broken": True}]}
        (cache_dir / "cache.json").write_text(json.dumps(bad_entry), encoding="utf-8")

        cache = AnalysisCache(cache_dir=cache_dir)
        assert cache.get(fp, h) is None


# ---------------------------------------------------------------------------
# max_entries eviction
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCacheEviction:
    def test_put_respects_max_entries_cap(self, tmp_path: Path) -> None:
        """Adding beyond max_entries evicts the oldest entry."""
        cache = AnalysisCache(cache_dir=tmp_path / "cache", max_entries=2)

        fp1 = tmp_path / "a.robot"
        fp2 = tmp_path / "b.robot"
        fp3 = tmp_path / "c.robot"
        for fp in (fp1, fp2, fp3):
            fp.write_bytes(b"x")

        h1, h2, h3 = "aaa", "bbb", "ccc"
        cache.put(fp1, h1, [])
        cache.put(fp2, h2, [])
        # Third put exceeds cap — fp1 should be evicted
        cache.put(fp3, h3, [])

        assert cache.get(fp1, h1) is None  # evicted
        assert cache.get(fp2, h2) is not None
        assert cache.get(fp3, h3) is not None

    def test_put_updates_existing_key_without_eviction(self, tmp_path: Path) -> None:
        """Updating an existing key does not cause spurious eviction."""
        cache = AnalysisCache(cache_dir=tmp_path / "cache", max_entries=2)

        fp = tmp_path / "a.robot"
        fp.write_bytes(b"x")
        h = "aaa"

        cache.put(fp, h, [])
        cache.put(fp, h, [])  # update — no new key, no eviction

        data = cache._load()
        assert len(data) == 1

    def test_get_returns_none_on_deserialize_error(self, tmp_path: Path) -> None:
        """An invalid cache entry (bad data) is treated as a miss."""
        cache = AnalysisCache(cache_dir=tmp_path / "cache")
        fp = tmp_path / "f.robot"
        fp.write_bytes(b"*** Test Cases ***\nT\n    Log    ok\n")

        h = AnalysisCache.file_hash(fp)
        # Write a correctly-keyed but unparseable entry
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir(exist_ok=True)
        key = cache._cache_key(fp, h)
        bad_data = {key: [{"broken_field": True}]}
        (cache_dir / "cache.json").write_text(json.dumps(bad_data), encoding="utf-8")

        # Reload the cache so it reads from disk
        fresh = AnalysisCache(cache_dir=cache_dir)
        result = fresh.get(fp, h)
        assert result is None


@pytest.mark.unit
class TestCacheOsErrors:
    """Tests that OSError paths in flush/clear are handled gracefully."""

    def test_flush_oserror_is_swallowed(self, tmp_path: Path) -> None:
        """An OSError while writing the cache file is silently swallowed."""
        from unittest.mock import patch

        cache = AnalysisCache(cache_dir=tmp_path / "cache")
        fp = tmp_path / "x.robot"
        fp.write_bytes(b"x")
        cache.put(fp, "abc", [])

        with patch("pathlib.Path.write_text", side_effect=OSError("disk full")):
            cache.flush()  # must not raise

    def test_clear_oserror_is_swallowed(self, tmp_path: Path) -> None:
        """An OSError while removing the cache file is silently swallowed."""
        from unittest.mock import patch

        cache = AnalysisCache(cache_dir=tmp_path / "cache")
        fp = tmp_path / "x.robot"
        fp.write_bytes(b"x")
        cache.put(fp, "abc", [])
        cache.flush()

        with patch("pathlib.Path.unlink", side_effect=OSError("permission denied")):
            cache.clear()  # must not raise
