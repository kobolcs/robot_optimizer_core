# src/robot_optimizer/domain/value_objects/cross_file_reference.py
"""Value object for cross-file references."""
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import Field

from ..base import ValueObject
from .location import Location


class ReferenceType(str, Enum):
    """Type of reference."""
    DEFINITION = "definition"
    USAGE = "usage"
    IMPORT = "import"


class CrossFileReference(ValueObject):
    """Represents a reference to a keyword or resource across files."""
    
    name: str = Field(..., description="Name of the referenced item")
    source_file: Path = Field(..., description="File containing the reference")
    location: Location = Field(..., description="Location in the file")
    reference_type: ReferenceType = Field(..., description="Type of reference")
    context_test: Optional[str] = Field(None, description="Test case context")
    context_keyword: Optional[str] = Field(None, description="Keyword context")
