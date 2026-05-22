from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .json_test_result_repository import JsonTestResultRepository

__all__ = ["JsonTestResultRepository"]


def __getattr__(name: str) -> object:
    if name == "JsonTestResultRepository":
        from .json_test_result_repository import JsonTestResultRepository
        return JsonTestResultRepository
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
