# src/robot_optimizer/domain/value_objects/robot_ast.py
"""Value objects for Robot Framework AST representation."""
from pathlib import Path
from typing import Any

from pydantic import Field

from ..base import ValueObject
from .location import Location


class RobotArgument(ValueObject):
    """Represents a keyword argument."""
    name: str | None = Field(None, description="Argument name")
    default_value: str | None = Field(None, description="Default value")
    is_varargs: bool = Field(False, description="Is *args style")
    is_kwargs: bool = Field(False, description="Is **kwargs style")


class KeywordCall(ValueObject):
    """Represents a keyword call/usage."""
    keyword_name: str = Field(..., description="Name of keyword being called")
    arguments: list[str] = Field(default_factory=list, description="Arguments passed")
    location: Location = Field(..., description="Where the call occurs")
    parent_keyword: str | None = Field(None, description="Keyword containing this call")
    parent_test: str | None = Field(None, description="Test case containing this call")

    @property
    def is_builtin(self) -> bool:
        """Check if this is a built-in keyword."""
        builtins = {'log', 'set variable', 'should be equal', 'run keyword'}
        return self.keyword_name.lower() in builtins

    @property
    def is_library_keyword(self) -> bool:
        """Check if this appears to be a library keyword (has dot notation)."""
        return '.' in self.keyword_name


class RobotKeyword(ValueObject):
    """Represents a keyword definition."""
    name: str = Field(..., description="Keyword name")
    arguments: list[RobotArgument] = Field(default_factory=list)
    documentation: str | None = Field(None)
    tags: list[str] = Field(default_factory=list)
    location: Location = Field(..., description="Definition location")
    body_calls: list[KeywordCall] = Field(
        default_factory=list,
        description="Keyword calls within this keyword"
    )
    return_value: str | None = Field(None)

    @property
    def argument_names(self) -> list[str]:
        """Get list of argument names."""
        return [arg.name for arg in self.arguments if arg.name]

    @property
    def has_documentation(self) -> bool:
        """Check if keyword has documentation."""
        return bool(self.documentation and self.documentation.strip())

    @property
    def calls_other_keywords(self) -> list[str]:
        """Get list of keywords called by this keyword."""
        return [call.keyword_name for call in self.body_calls]


class RobotTestCase(ValueObject):
    """Represents a test case."""
    name: str = Field(..., description="Test case name")
    documentation: str | None = Field(None)
    tags: list[str] = Field(default_factory=list)
    setup: KeywordCall | None = Field(None)
    teardown: KeywordCall | None = Field(None)
    location: Location = Field(..., description="Test case location")
    body_calls: list[KeywordCall] = Field(
        default_factory=list,
        description="Keyword calls in test body"
    )

    @property
    def all_keyword_calls(self) -> list[KeywordCall]:
        """Get all keyword calls including setup/teardown."""
        calls = list(self.body_calls)
        if self.setup:
            calls.insert(0, self.setup)
        if self.teardown:
            calls.append(self.teardown)
        return calls

    @property
    def line_count(self) -> int:
        """Estimate line count of test case."""
        if self.location.end_line:
            return self.location.end_line - self.location.line + 1
        return len(self.body_calls) + 2  # Rough estimate


class RobotImport(ValueObject):
    """Represents an import statement."""
    import_type: str = Field(..., pattern="^(Library|Resource|Variables)$")
    name: str = Field(..., description="What is being imported")
    alias: str | None = Field(None, description="Import alias")
    arguments: list[str] = Field(default_factory=list)
    location: Location = Field(...)

    @property
    def is_library(self) -> bool:
        """Check if this is a library import."""
        return self.import_type == "Library"

    @property
    def is_resource(self) -> bool:
        """Check if this is a resource import."""
        return self.import_type == "Resource"

    @property
    def resolved_path(self) -> Path | None:
        """Get resolved path for resource imports."""
        if self.is_resource and not self.name.startswith('${'):
            return Path(self.name)
        return None


class RobotVariable(ValueObject):
    """Represents a variable definition."""
    name: str = Field(..., description="Variable name")
    value: Any = Field(..., description="Variable value")
    location: Location = Field(...)
    scope: str = Field("test", pattern="^(test|suite|global)$")

    @property
    def is_scalar(self) -> bool:
        """Check if this is a scalar variable."""
        return self.name.startswith('${') and self.name.endswith('}')

    @property
    def is_list(self) -> bool:
        """Check if this is a list variable."""
        return self.name.startswith('@{') and self.name.endswith('}')

    @property
    def is_dict(self) -> bool:
        """Check if this is a dictionary variable."""
        return self.name.startswith('&{') and self.name.endswith('}')


class RobotSuite(ValueObject):
    """Represents a complete Robot Framework suite/file."""
    name: str = Field(..., description="Suite name")
    source: Path = Field(..., description="Source file path")
    documentation: str | None = Field(None)
    metadata: dict[str, str] = Field(default_factory=dict)
    imports: list[RobotImport] = Field(default_factory=list)
    variables: list[RobotVariable] = Field(default_factory=list)
    keywords: list[RobotKeyword] = Field(default_factory=list)
    test_cases: list[RobotTestCase] = Field(default_factory=list)

    @property
    def imported_libraries(self) -> list[str]:
        """Get list of imported library names."""
        return [imp.name for imp in self.imports if imp.is_library]

    @property
    def imported_resources(self) -> list[Path]:
        """Get list of imported resource paths."""
        return [
            imp.resolved_path for imp in self.imports
            if imp.is_resource and imp.resolved_path
        ]

    @property
    def keyword_names(self) -> Set[str]:
        """Get set of all keyword names defined in this suite."""
        return {kw.name for kw in self.keywords}

    @property
    def test_names(self) -> Set[str]:
        """Get set of all test case names."""
        return {tc.name for tc in self.test_cases}

    @property
    def all_keyword_calls(self) -> list[KeywordCall]:
        """Get all keyword calls in the entire suite."""
        calls = []

        # From test cases
        for test in self.test_cases:
            calls.extend(test.all_keyword_calls)

        # From keywords
        for keyword in self.keywords:
            calls.extend(keyword.body_calls)

        return calls

    @property
    def has_documentation(self) -> bool:
        """Check if suite has documentation."""
        return bool(self.documentation and self.documentation.strip())
