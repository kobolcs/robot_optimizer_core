# src/robot_optimizer_core/parsers/robot_ast_parser.py
"""Robot Framework AST parser using official robot.parsing library."""
from io import StringIO
from pathlib import Path
from typing import Any

from robot.parsing import get_model
from robot.parsing.model import (
    KeywordSection,
    TestCaseSection,
    VariableSection,
)

from ..domain.entities import TestFile
from ..domain.repositories.robot_parser_repository import RobotParserRepository
from ..domain.value_objects import Location
from ..domain.value_objects.robot_ast import (
    KeywordCall,
    RobotArgument,
    RobotImport,
    RobotKeyword,
    RobotSuite,
    RobotTestCase,
    RobotVariable,
)


class RobotASTParser(RobotParserRepository):
    """AST-based parser for Robot Framework files."""

    def parse_suite(self, test_file: TestFile) -> RobotSuite:
        """Parse a test file into a RobotSuite using AST."""
        try:
            # Parse using robot.parsing
            model = get_model(StringIO(test_file.content), source=str(test_file.path))

            # Extract components
            keywords = self._extract_keywords(model, test_file.path)
            test_cases = self._extract_test_cases(model, test_file.path)
            variables = self._extract_variables(model, test_file.path)
            imports = self._extract_imports(model, test_file.path)

            # Get metadata
            suite_name = test_file.path.stem
            documentation = self._get_suite_documentation(model)
            metadata = self._get_suite_metadata(model)

            return RobotSuite(
                name=suite_name,
                source=test_file.path,
                documentation=documentation,
                metadata=metadata,
                imports=imports,
                variables=variables,
                keywords=keywords,
                test_cases=test_cases
            )

        except Exception as e:
            # Fallback to empty suite on parse error
            return RobotSuite(
                name=test_file.path.stem,
                source=test_file.path,
                documentation=f"Parse error: {e!s}",
                metadata={},
                imports=[],
                variables=[],
                keywords=[],
                test_cases=[]
            )

    def _extract_keywords(self, model: Any, file_path: Path) -> list[RobotKeyword]:
        """Extract keyword definitions from AST."""
        keywords = []

        for section in model.sections:
            if isinstance(section, KeywordSection):
                for keyword in section.body:
                    if hasattr(keyword, "name") and keyword.name:
                        kw = self._parse_keyword(keyword, file_path)
                        keywords.append(kw)

        return keywords

    def _parse_keyword(self, keyword: Any, file_path: Path) -> RobotKeyword:
        """Parse a single keyword from AST."""
        # Extract location
        location = Location(
            file_path=file_path,
            line=keyword.lineno,
            end_line=keyword.end_lineno if hasattr(keyword, "end_lineno") else None
        )

        # Extract arguments
        arguments = []
        if hasattr(keyword, "args") and keyword.args:
            for arg in keyword.args:
                arguments.append(RobotArgument(
                    name=arg.name if hasattr(arg, "name") else str(arg),
                    default_value=arg.default if hasattr(arg, "default") else None
                ))

        # Extract documentation
        documentation = None
        tags = []
        for item in keyword.body:
            if hasattr(item, "type"):
                if item.type == "DOCUMENTATION":
                    documentation = " ".join(item.values[1:]) if len(item.values) > 1 else ""
                elif item.type == "TAGS":
                    tags = list(item.values[1:]) if len(item.values) > 1 else []

        # Extract keyword calls
        body_calls = self._extract_keyword_calls(keyword.body, file_path, parent_keyword=keyword.name)

        # Extract return value
        return_value = None
        for item in keyword.body:
            if hasattr(item, "type") and item.type == "RETURN":
                return_value = " ".join(item.values[1:]) if len(item.values) > 1 else ""

        return RobotKeyword(
            name=keyword.name,
            arguments=arguments,
            documentation=documentation,
            tags=tags,
            location=location,
            body_calls=body_calls,
            return_value=return_value
        )

    def _extract_test_cases(self, model: Any, file_path: Path) -> list[RobotTestCase]:
        """Extract test cases from AST."""
        test_cases = []

        for section in model.sections:
            if isinstance(section, TestCaseSection):
                for test in section.body:
                    if hasattr(test, "name") and test.name:
                        tc = self._parse_test_case(test, file_path)
                        test_cases.append(tc)

        return test_cases

    def _parse_test_case(self, test: Any, file_path: Path) -> RobotTestCase:
        """Parse a single test case from AST."""
        location = Location(
            file_path=file_path,
            line=test.lineno,
            end_line=test.end_lineno if hasattr(test, "end_lineno") else None
        )

        documentation = None
        tags = []
        setup = None
        teardown = None

        for item in test.body:
            if hasattr(item, "type"):
                if item.type == "DOCUMENTATION":
                    documentation = " ".join(item.values[1:]) if len(item.values) > 1 else ""
                elif item.type == "TAGS":
                    tags = list(item.values[1:]) if len(item.values) > 1 else []
                elif item.type == "SETUP":
                    setup = self._parse_keyword_call(item, file_path, parent_test=test.name)
                elif item.type == "TEARDOWN":
                    teardown = self._parse_keyword_call(item, file_path, parent_test=test.name)

        body_calls = self._extract_keyword_calls(test.body, file_path, parent_test=test.name)

        return RobotTestCase(
            name=test.name,
            documentation=documentation,
            tags=tags,
            setup=setup,
            teardown=teardown,
            location=location,
            body_calls=body_calls
        )

    def _extract_keyword_calls(self, body: list[Any], file_path: Path,
                              parent_test: str | None = None,
                              parent_keyword: str | None = None) -> list[KeywordCall]:
        """Extract keyword calls from a body."""
        calls = []

        for item in body:
            if hasattr(item, "type") and item.type == "KEYWORD":
                call = self._parse_keyword_call(item, file_path, parent_test, parent_keyword)
                if call:
                    calls.append(call)

        return calls

    def _parse_keyword_call(self, item: Any, file_path: Path,
                           parent_test: str | None = None,
                           parent_keyword: str | None = None) -> KeywordCall | None:
        """Parse a keyword call from AST."""
        if not hasattr(item, "values") or not item.values:
            return None

        keyword_name = item.values[0]
        arguments = list(item.values[1:]) if len(item.values) > 1 else []

        location = Location(
            file_path=file_path,
            line=item.lineno
        )

        return KeywordCall(
            keyword_name=keyword_name,
            arguments=arguments,
            location=location,
            parent_keyword=parent_keyword,
            parent_test=parent_test
        )

    def _extract_variables(self, model: Any, file_path: Path) -> list[RobotVariable]:
        """Extract variable definitions from AST."""
        variables = []

        for section in model.sections:
            if isinstance(section, VariableSection):
                for var in section.body:
                    if hasattr(var, "type") and var.type == "VARIABLE" and var.values:
                        name = var.values[0]
                        value = var.values[1] if len(var.values) > 1 else None

                        location = Location(
                            file_path=file_path,
                            line=var.lineno
                        )

                        variables.append(RobotVariable(
                            name=name,
                            value=value,
                            location=location,
                            scope="suite"
                        ))

        return variables

    def _extract_imports(self, model: Any, file_path: Path) -> list[RobotImport]:
        """Extract imports from AST."""
        imports = []

        for section in model.sections:
            if hasattr(section, "header") and section.header:
                if section.header.type == "SETTING HEADER":
                    for item in section.body:
                        if hasattr(item, "type") and item.type in ["LIBRARY", "RESOURCE", "VARIABLES"]:
                            if item.values and len(item.values) > 1:
                                import_type = item.type.title()
                                name = item.values[1]
                                arguments = list(item.values[2:]) if len(item.values) > 2 else []

                                location = Location(
                                    file_path=file_path,
                                    line=item.lineno
                                )

                                imports.append(RobotImport(
                                    import_type=import_type,
                                    name=name,
                                    alias=None,  # Robot doesn't support import aliases
                                    arguments=arguments,
                                    location=location
                                ))

        return imports

    def _get_suite_documentation(self, model: Any) -> str | None:
        """Extract suite documentation."""
        for section in model.sections:
            if hasattr(section, "header") and section.header:
                if section.header.type == "SETTING HEADER":
                    for item in section.body:
                        if hasattr(item, "type") and item.type == "DOCUMENTATION":
                            return " ".join(item.values[1:]) if len(item.values) > 1 else None
        return None

    def _get_suite_metadata(self, model: Any) -> dict[str, str]:
        """Extract suite metadata."""
        metadata = {}

        for section in model.sections:
            if hasattr(section, "header") and section.header:
                if section.header.type == "SETTING HEADER":
                    for item in section.body:
                        if hasattr(item, "type") and item.type == "METADATA" and len(item.values) > 2:
                            key = item.values[1]
                            value = " ".join(item.values[2:])
                            metadata[key] = value

        return metadata
