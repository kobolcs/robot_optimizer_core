# src/robot_optimizer_core/parsers/robot_ast_parser.py
"""Robot Framework AST parser using official robot.parsing library."""

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


def _argument_values(item: Any) -> list[str]:
    """Return values from ARGUMENT-type data tokens."""
    return [str(t.value) for t in item.data_tokens if t.type == "ARGUMENT"]


def _name_value(item: Any) -> str | None:
    """Return value of first NAME-type data token, or None."""
    for t in item.data_tokens:
        if t.type == "NAME":
            return str(t.value)
    return None


class RobotASTParser(RobotParserRepository):
    """AST-based parser for Robot Framework files."""

    def parse_suite(self, test_file: TestFile) -> RobotSuite:
        """Parse a test file into a RobotSuite using AST."""
        try:
            # robot.parsing accepts a Unicode string directly as content
            model = get_model(test_file.content)

            keywords = self._extract_keywords(model, test_file.path)
            test_cases = self._extract_test_cases(model, test_file.path)
            variables = self._extract_variables(model, test_file.path)
            imports = self._extract_imports(model, test_file.path)

            return RobotSuite(
                name=test_file.path.stem,
                source=test_file.path,
                documentation=self._get_suite_documentation(model),
                metadata=self._get_suite_metadata(model),
                imports=imports,
                variables=variables,
                keywords=keywords,
                test_cases=test_cases,
            )

        except Exception as e:
            return RobotSuite(
                name=test_file.path.stem,
                source=test_file.path,
                documentation=f"Parse error: {e!s}",
                metadata={},
                imports=[],
                variables=[],
                keywords=[],
                test_cases=[],
            )

    # ------------------------------------------------------------------
    # Keywords
    # ------------------------------------------------------------------

    def _extract_keywords(self, model: Any, file_path: Path) -> list[RobotKeyword]:
        keywords = []
        for section in model.sections:
            if isinstance(section, KeywordSection):
                for keyword in section.body:
                    if hasattr(keyword, "name") and keyword.name:
                        keywords.append(self._parse_keyword(keyword, file_path))
        return keywords

    def _parse_keyword(self, keyword: Any, file_path: Path) -> RobotKeyword:
        location = Location(
            file_path=file_path,
            line=keyword.lineno,
            end_line=keyword.end_lineno if hasattr(keyword, "end_lineno") else None,
        )

        arguments: list[RobotArgument] = []
        documentation: str | None = None
        tags: list[str] = []
        return_value: str | None = None

        for item in keyword.body:
            item_type = getattr(item, "type", None)
            if item_type == "ARGUMENTS":
                arguments = self._parse_arguments(item)
            elif item_type == "DOCUMENTATION":
                documentation = self._parse_documentation(item)
            elif item_type == "TAGS":
                tags = self._parse_tags(item)
            elif item_type == "RETURN":
                return_value = self._parse_return_value(item)

        body_calls = self._extract_keyword_calls(
            keyword.body, file_path, parent_keyword=keyword.name
        )

        return RobotKeyword(
            name=keyword.name,
            arguments=arguments,
            documentation=documentation,
            tags=tags,
            location=location,
            body_calls=body_calls,
            return_value=return_value,
        )

    def _parse_arguments(self, item: Any) -> list[RobotArgument]:
        """Parse arguments from an ARGUMENTS item."""
        arguments: list[RobotArgument] = []
        for arg_name in getattr(item, "values", ()):
            default = None
            name = arg_name
            if "=" in arg_name:
                name, default = arg_name.split("=", 1)
            arguments.append(
                RobotArgument(
                    name=name,
                    default_value=default,
                    is_varargs=False,
                    is_kwargs=False,
                )
            )
        return arguments

    def _parse_documentation(self, item: Any) -> str | None:
        """Parse documentation from a DOCUMENTATION item."""
        args = _argument_values(item)
        return " ".join(args) if args else ""

    def _parse_tags(self, item: Any) -> list[str]:
        """Parse tags from a TAGS item."""
        return list(getattr(item, "values", ()))

    def _parse_return_value(self, item: Any) -> str | None:
        """Parse return value from a RETURN item."""
        vals = list(getattr(item, "values", ()))
        return " ".join(vals) if vals else ""

    # ------------------------------------------------------------------
    # Test cases
    # ------------------------------------------------------------------

    def _extract_test_cases(self, model: Any, file_path: Path) -> list[RobotTestCase]:
        test_cases = []
        for section in model.sections:
            if isinstance(section, TestCaseSection):
                for test in section.body:
                    if hasattr(test, "name") and test.name:
                        test_cases.append(self._parse_test_case(test, file_path))
        return test_cases

    def _parse_test_case(self, test: Any, file_path: Path) -> RobotTestCase:
        location = Location(
            file_path=file_path,
            line=test.lineno,
            end_line=test.end_lineno if hasattr(test, "end_lineno") else None,
        )

        documentation: str | None = None
        tags: list[str] = []
        setup: KeywordCall | None = None
        teardown: KeywordCall | None = None

        for item in test.body:
            item_type = getattr(item, "type", None)
            if item_type == "DOCUMENTATION":
                documentation = self._parse_documentation(item)
            elif item_type == "TAGS":
                tags = self._parse_tags(item)
            elif item_type == "SETUP":
                setup = self._parse_setup_teardown(
                    item, file_path, parent_test=test.name
                )
            elif item_type == "TEARDOWN":
                teardown = self._parse_setup_teardown(
                    item, file_path, parent_test=test.name
                )

        body_calls = self._extract_keyword_calls(
            test.body, file_path, parent_test=test.name
        )

        return RobotTestCase(
            name=test.name,
            documentation=documentation,
            tags=tags,
            setup=setup,
            teardown=teardown,
            location=location,
            body_calls=body_calls,
        )

    # ------------------------------------------------------------------
    # Keyword calls
    # ------------------------------------------------------------------

    def _extract_keyword_calls(
        self,
        body: list[Any],
        file_path: Path,
        parent_test: str | None = None,
        parent_keyword: str | None = None,
    ) -> list[KeywordCall]:
        calls = []
        for item in body:
            if getattr(item, "type", None) == "KEYWORD":
                call = self._parse_keyword_call(
                    item, file_path, parent_test, parent_keyword
                )
                if call:
                    calls.append(call)
        return calls

    def _parse_keyword_call(
        self,
        item: Any,
        file_path: Path,
        parent_test: str | None = None,
        parent_keyword: str | None = None,
    ) -> KeywordCall | None:
        keyword_name = getattr(item, "keyword", None)
        if not keyword_name:
            return None
        return KeywordCall(
            keyword_name=keyword_name,
            arguments=list(getattr(item, "args", ())),
            location=Location(file_path=file_path, line=item.lineno),
            parent_keyword=parent_keyword,
            parent_test=parent_test,
        )

    def _parse_setup_teardown(
        self,
        item: Any,
        file_path: Path,
        parent_test: str | None = None,
        parent_keyword: str | None = None,
    ) -> KeywordCall | None:
        name = _name_value(item)
        if not name:
            return None
        arguments = _argument_values(item)
        return KeywordCall(
            keyword_name=name,
            arguments=arguments,
            location=Location(file_path=file_path, line=item.lineno),
            parent_keyword=parent_keyword,
            parent_test=parent_test,
        )

    # ------------------------------------------------------------------
    # Variables
    # ------------------------------------------------------------------

    def _extract_variables(self, model: Any, file_path: Path) -> list[RobotVariable]:
        variables = []
        for section in model.sections:
            if isinstance(section, VariableSection):
                for var in section.body:
                    if getattr(var, "type", None) != "VARIABLE":
                        continue
                    name = var.name
                    if not name:
                        continue
                    value_tuple = getattr(var, "value", ())
                    value = value_tuple[0] if value_tuple else None
                    variables.append(
                        RobotVariable(
                            name=name,
                            value=value,
                            location=Location(file_path=file_path, line=var.lineno),
                            scope="suite",
                        )
                    )
        return variables

    # ------------------------------------------------------------------
    # Imports
    # ------------------------------------------------------------------

    def _extract_imports(self, model: Any, file_path: Path) -> list[RobotImport]:
        imports = []
        for section in model.sections:
            header = getattr(section, "header", None)
            if not (header and header.type == "SETTING HEADER"):
                continue
            for item in section.body:
                item_type = getattr(item, "type", None)
                if item_type not in ("LIBRARY", "RESOURCE", "VARIABLES"):
                    continue
                name = _name_value(item)
                if not name:
                    continue
                arguments = _argument_values(item)
                imports.append(
                    RobotImport(
                        import_type=item_type.title(),
                        name=name,
                        alias=None,
                        arguments=arguments,
                        location=Location(file_path=file_path, line=item.lineno),
                    )
                )
        return imports

    # ------------------------------------------------------------------
    # Suite-level metadata
    # ------------------------------------------------------------------

    def _get_suite_documentation(self, model: Any) -> str | None:
        for section in model.sections:
            header = getattr(section, "header", None)
            if not (header and header.type == "SETTING HEADER"):
                continue
            for item in section.body:
                if getattr(item, "type", None) == "DOCUMENTATION":
                    args = _argument_values(item)
                    return " ".join(args) if args else None
        return None

    def _get_suite_metadata(self, model: Any) -> dict[str, str]:
        metadata: dict[str, str] = {}
        for section in model.sections:
            header = getattr(section, "header", None)
            if not (header and header.type == "SETTING HEADER"):
                continue
            for item in section.body:
                if getattr(item, "type", None) != "METADATA":
                    continue
                tokens = [t for t in item.data_tokens if t.type in ("NAME", "ARGUMENT")]
                if len(tokens) >= 2:
                    key = tokens[0].value
                    value = " ".join(t.value for t in tokens[1:])
                    metadata[key] = value
        return metadata
