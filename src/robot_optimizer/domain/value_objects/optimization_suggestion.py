# src/robot_optimizer/domain/value_objects/optimization_suggestion.py
"""Optimization suggestion value object for Robot Framework improvements.

100% Pydantic v2 compliant implementation.
"""
from enum import Enum
from typing import Dict, Any, List

from pydantic import Field, field_validator, computed_field, model_validator

from ..base import ValueObject
from .finding import Finding


class OptimizationType(str, Enum):
    """Types of optimizations that can be applied."""

    REPLACE_SLEEP = "replace_sleep"
    REMOVE_DUPLICATE = "remove_duplicate"
    SIMPLIFY_XPATH = "simplify_xpath"
    EXTRACT_KEYWORD = "extract_keyword"
    ADD_WAIT_CONDITION = "add_wait_condition"
    USE_VARIABLE = "use_variable"
    REMOVE_UNUSED = "remove_unused"


class OptimizationSuggestion(ValueObject):
    """Value object representing a suggested optimization.

    Encapsulates a specific optimization that can be applied to fix
    a finding, including the code changes and metadata about the optimization.
    """

    finding_id: str = Field(..., description="ID of the finding")
    optimization_type: OptimizationType = Field(
        ..., description="Type of optimization"
    )
    description: str = Field(
        ..., min_length=1, description="Human-readable description"
    )
    original_code: str = Field(..., description="Original code")
    suggested_code: str = Field(..., description="Suggested replacement")
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence score (0-1)"
    )
    estimated_impact: str = Field(
        ..., description="Estimated impact of the change"
    )
    is_safe: bool = Field(
        default=True, description="Whether this change is safe to apply"
    )
    prerequisites: List[str] = Field(
        default_factory=list, description="Prerequisites for this optimization"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )

    @field_validator('description', 'estimated_impact')
    @classmethod
    def validate_non_empty_string(cls, v: str) -> str:
        """Ensure string fields are not empty.

        Args:
            v: String to validate

        Returns:
            Validated string

        Raises:
            ValueError: If string is empty
        """
        if not v.strip():
            raise ValueError("Field cannot be empty")
        return v.strip()

    @model_validator(mode='after')
    def validate_code_difference(self) -> 'OptimizationSuggestion':
        """Ensure suggested code is different from original.

        Pydantic v2 model validator.
        """
        if self.suggested_code == self.original_code:
            raise ValueError("Suggested code must be different from original code")
        return self

    # Pydantic v2: computed fields for derived properties
    @computed_field  # type: ignore[misc]
    @property
    def is_high_confidence(self) -> bool:
        """Check if this is a high confidence suggestion (>= 0.8)."""
        return self.confidence >= 0.8

    @computed_field  # type: ignore[misc]
    @property
    def requires_prerequisites(self) -> bool:
        """Check if this optimization has prerequisites."""
        return len(self.prerequisites) > 0

    @computed_field  # type: ignore[misc]
    @property
    def code_diff_size(self) -> int:
        """Calculate the size difference between original and suggested code."""
        return abs(len(self.suggested_code) - len(self.original_code))

    @computed_field  # type: ignore[misc]
    @property
    def risk_level(self) -> str:
        """Determine risk level based on safety and confidence."""
        if not self.is_safe:
            return "high"
        if self.confidence < 0.5:
            return "medium"
        if self.confidence < 0.8:
            return "low"
        return "minimal"

    @classmethod
    def for_sleep_replacement(
        cls,
        finding: Finding,
        original: str,
        replacement: str,
        wait_keyword: str = "Wait Until Element Is Visible"
    ) -> 'OptimizationSuggestion':
        """Create suggestion for replacing sleep with explicit wait.

        Factory method using Pydantic v2 model_validate.

        Args:
            finding: The finding this suggestion addresses
            original: Original sleep code
            replacement: Suggested wait code
            wait_keyword: The wait keyword being used

        Returns:
            OptimizationSuggestion instance
        """
        # pylint: disable=no-member
        return cls.model_validate({
            'finding_id': str(finding.id),
            'optimization_type': OptimizationType.REPLACE_SLEEP,
            'description': f"Replace Sleep with {wait_keyword}",
            'original_code': original,
            'suggested_code': replacement,
            'confidence': 0.9,
            'estimated_impact': "Reduces test flakiness and execution time",
            'is_safe': True,
            'prerequisites': [f"Ensure {wait_keyword} is imported"],
            'metadata': {
                "wait_keyword": wait_keyword,
                "pattern_type": "SLEEP_IN_TEST"
            }
        })

    @classmethod
    def for_xpath_simplification(
        cls,
        finding: Finding,
        original_xpath: str,
        simplified_xpath: str,
        confidence: float = 0.7
    ) -> 'OptimizationSuggestion':
        """Create suggestion for simplifying XPath.

        Factory method using Pydantic v2 model_validate.

        Args:
            finding: The finding this suggestion addresses
            original_xpath: Complex XPath selector
            simplified_xpath: Simplified version
            confidence: Confidence in the simplification

        Returns:
            OptimizationSuggestion instance
        """
        # pylint: disable=no-member
        return cls.model_validate({
            'finding_id': str(finding.id),
            'optimization_type': OptimizationType.SIMPLIFY_XPATH,
            'description': "Simplify fragile XPath selector",
            'original_code': original_xpath,
            'suggested_code': simplified_xpath,
            'confidence': confidence,
            'estimated_impact': "Improves selector stability and readability",
            'is_safe': confidence >= 0.8,
            'prerequisites': [],
            'metadata': {
                "selector_type": "xpath",
                "pattern_type": "FRAGILE_XPATH"
            }
        })

    def __eq__(self, other: object) -> bool:
        """Check equality with another OptimizationSuggestion."""
        if not isinstance(other, OptimizationSuggestion):
            return False
        return (
            self.finding_id == other.finding_id and
            self.optimization_type == other.optimization_type and
            self.original_code == other.original_code and
            self.suggested_code == other.suggested_code
        )

    def __hash__(self) -> int:
        """Generate hash for the optimization suggestion."""
        return hash((
            self.finding_id,
            self.optimization_type,
            self.original_code,
            self.suggested_code
        ))

    def model_dump(self, **kwargs: Any) -> Dict[str, Any]:
        """Override to handle custom serialization.

        Pydantic v2 method.
        """
        data = super().model_dump(**kwargs)
        # Include computed fields in JSON mode
        if kwargs.get('mode') == 'json':
            data.update({
                'is_high_confidence': self.is_high_confidence,
                'requires_prerequisites': self.requires_prerequisites,
                'risk_level': self.risk_level,
            })
        return data
