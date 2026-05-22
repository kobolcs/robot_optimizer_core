# tests/unit/domain/test_ports.py
"""Unit tests for domain port interfaces."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from robot_optimizer_core.domain.ports import (
    FileProvider,
    IAnalyzer,
    IMetrics,
    IParser,
    ISuiteAnalyzer,
    ITestFileRepository,
    ITestResultRepository,
)
from robot_optimizer_core.domain.ports.repository import (
    ITestFileRepository,
    ITestResultRepository,
)
from robot_optimizer_core.domain.repositories.interfaces import (
    ITestFileRepository as ITestFileRepo2,
    ITestResultRepository as ITestResultRepo2,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _ConcreteMetrics:
    def increment(self, metric: str, value: int = 1, tags: dict | None = None) -> None:
        pass

    def gauge(self, metric: str, value: float, tags: dict | None = None) -> None:
        pass

    def timing(self, metric: str, value: float, tags: dict | None = None) -> None:
        pass

    def timer(self, metric: str, tags: dict | None = None):
        @contextmanager
        def _cm():
            yield
        return _cm()

    def get_metrics(self) -> dict[str, Any]:
        return {}

    def reset(self) -> None:
        pass


class _ConcreteAnalyzer:
    @property
    def name(self) -> str:
        return "test"

    @property
    def description(self) -> str:
        return "test analyzer"

    def analyze(self, test_file) -> list:
        return []


class _ConcreteSuiteAnalyzer:
    def analyze_suite(self, files) -> list:
        return []


class _ConcreteParser:
    def parse_suite(self, test_file):
        return MagicMock()


class _ConcreteFileProvider:
    def load(self, file_path: Path) -> str:
        return ""

    def exists(self, file_path: Path) -> bool:
        return True


class _ConcreteTestResultRepo(ITestResultRepository):
    def save_result(self, result) -> None:
        pass

    def get_results_for_file(self, file_path: Path, days_back: int = 30) -> list:
        return []

    def get_flakiness_stats(self, file_path: Path, days_back: int = 30) -> list:
        return []

    def get_total_results_count(self) -> int:
        return 0


class _ConcreteTestFileRepo(ITestFileRepository):
    def find_files(self, directory: Path) -> list[Path]:
        return []

    def get_content(self, file_path: Path) -> str:
        return ""


# ---------------------------------------------------------------------------
# IMetrics
# ---------------------------------------------------------------------------

class TestIMetrics:
    def test_runtime_checkable(self):
        assert isinstance(_ConcreteMetrics(), IMetrics)

    def test_non_conforming_not_instance(self):
        assert not isinstance(object(), IMetrics)

    def test_methods_callable(self):
        m = _ConcreteMetrics()
        m.increment("hits")
        m.increment("hits", 2, {"env": "test"})
        m.gauge("cpu", 0.5)
        m.timing("latency", 1.2)
        with m.timer("op"):
            pass
        assert m.get_metrics() == {}
        m.reset()


# ---------------------------------------------------------------------------
# IAnalyzer
# ---------------------------------------------------------------------------

class TestIAnalyzer:
    def test_runtime_checkable(self):
        assert isinstance(_ConcreteAnalyzer(), IAnalyzer)

    def test_non_conforming_not_instance(self):
        assert not isinstance(object(), IAnalyzer)

    def test_properties_and_analyze(self):
        a = _ConcreteAnalyzer()
        assert a.name == "test"
        assert a.description == "test analyzer"
        assert a.analyze(MagicMock()) == []


# ---------------------------------------------------------------------------
# ISuiteAnalyzer
# ---------------------------------------------------------------------------

class TestISuiteAnalyzer:
    def test_runtime_checkable(self):
        assert isinstance(_ConcreteSuiteAnalyzer(), ISuiteAnalyzer)

    def test_non_conforming_not_instance(self):
        assert not isinstance(object(), ISuiteAnalyzer)

    def test_analyze_suite(self):
        sa = _ConcreteSuiteAnalyzer()
        assert sa.analyze_suite([]) == []


# ---------------------------------------------------------------------------
# IParser
# ---------------------------------------------------------------------------

class TestIParser:
    def test_runtime_checkable(self):
        assert isinstance(_ConcreteParser(), IParser)

    def test_non_conforming_not_instance(self):
        assert not isinstance(object(), IParser)

    def test_parse_suite_called(self):
        p = _ConcreteParser()
        result = p.parse_suite(MagicMock())
        assert result is not None


# ---------------------------------------------------------------------------
# FileProvider
# ---------------------------------------------------------------------------

class TestFileProvider:
    def test_runtime_checkable(self):
        assert isinstance(_ConcreteFileProvider(), FileProvider)

    def test_non_conforming_not_instance(self):
        assert not isinstance(object(), FileProvider)

    def test_load_and_exists(self):
        fp = _ConcreteFileProvider()
        assert fp.load(Path("x")) == ""
        assert fp.exists(Path("x")) is True


# ---------------------------------------------------------------------------
# ITestResultRepository (ABC)
# ---------------------------------------------------------------------------

class TestITestResultRepository:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            ITestResultRepository()  # type: ignore[abstract]

    def test_concrete_impl(self):
        repo = _ConcreteTestResultRepo()
        repo.save_result(MagicMock())
        assert repo.get_results_for_file(Path("f.robot")) == []
        assert repo.get_flakiness_stats(Path("f.robot")) == []
        assert repo.get_total_results_count() == 0

    def test_isinstance_of_abc(self):
        repo = _ConcreteTestResultRepo()
        assert isinstance(repo, ITestResultRepository)

    def test_re_export_alias_is_same_class(self):
        assert ITestResultRepo2 is ITestResultRepository


# ---------------------------------------------------------------------------
# ITestFileRepository (ABC)
# ---------------------------------------------------------------------------

class TestITestFileRepository:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            ITestFileRepository()  # type: ignore[abstract]

    def test_concrete_impl(self):
        repo = _ConcreteTestFileRepo()
        assert repo.find_files(Path(".")) == []
        assert repo.get_content(Path("f.robot")) == ""

    def test_isinstance_of_abc(self):
        repo = _ConcreteTestFileRepo()
        assert isinstance(repo, ITestFileRepository)

    def test_re_export_alias_is_same_class(self):
        assert ITestFileRepo2 is ITestFileRepository
