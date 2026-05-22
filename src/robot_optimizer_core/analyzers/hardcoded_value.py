# src/robot_optimizer_core/analyzers/hardcoded_value.py
"""Hardcoded value analyzer for Robot Framework test suites.

Flags literals that should be variables or settings — especially URLs,
IP addresses, credential-like strings, and common environment-specific tokens.
"""

from __future__ import annotations

import re
import sys

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

from ..domain.entities import TestFile
from ..domain.value_objects import Finding, Location, Pattern, PatternType, Severity
from ..infrastructure.parsers.robot_ast_parser import RobotASTParser
from .base import BaseAnalyzer, ConfigValue

__all__ = ["HardcodedValueAnalyzer"]

# URL patterns (http/https/ftp with host)
_URL_RE = re.compile(
    r"""(?x)
    (?<!\$\{)                   # not inside a variable
    (https?|ftp)://             # scheme
    [\w.\-]+(:\d+)?             # host + optional port
    (/[^\s,'"]*)?               # optional path
    """,
    re.IGNORECASE,
)

# IP address (v4) — not inside a variable
_IP_RE = re.compile(r"(?<!\$\{)(?<!\w)\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?!\w)")

# Credential-like key=value or bare tokens
_CRED_RE = re.compile(
    r"""(?xi)
    (?:password|passwd|secret|token|api[_\-]?key|auth[_\-]?token|
       access[_\-]?key|private[_\-]?key)
    \s*[=:]\s*
    [^\s$\{][^\s,'"]{3,}       # non-empty non-variable value ≥ 4 chars
    """,
    re.IGNORECASE,
)

# Localhost shorthand
_LOCALHOST_RE = re.compile(r"(?<!\$\{)\blocalhost\b", re.IGNORECASE)

# Port-only string that looks like a direct port reference e.g. ":8080" or "8080"
# only if it is surrounded by quotes or appears as a standalone argument
_PORT_RE = re.compile(r"(?<!\$\{)\b(8080|8443|3000|4200|5000|5432|3306|6379|27017)\b")


class HardcodedValueAnalyzer(BaseAnalyzer):
    """Detects hardcoded environment-specific values in Robot Framework files.

    Flags:
    - Hardcoded URLs (http://..., https://...)
    - Hardcoded IP addresses (e.g. 192.168.1.1)
    - Credential-like tokens (password=..., api_key=...)
    - ``localhost`` references
    - Common hardcoded port numbers

    Configuration:
        check_urls: Check for hardcoded URLs (default: True).
        check_ips: Check for hardcoded IP addresses (default: True).
        check_credentials: Check for credential patterns (default: True).
        check_localhost: Check for localhost references (default: True).
        check_ports: Check for common hardcoded ports (default: False).
        ignore_patterns: List of regex patterns to ignore.
    """

    def __init__(self, config: dict[str, ConfigValue] | None = None) -> None:
        super().__init__(config)
        self._check_urls = bool(self.get_config_value("check_urls", True))
        self._check_ips = bool(self.get_config_value("check_ips", True))
        self._check_creds = bool(self.get_config_value("check_credentials", True))
        self._check_localhost = bool(self.get_config_value("check_localhost", True))
        self._check_ports = bool(self.get_config_value("check_ports", False))
        ignore_raw = self.get_list_config("ignore_patterns", [])
        self._ignore: list[re.Pattern[str]] = [
            re.compile(str(p), re.IGNORECASE) for p in ignore_raw
        ]

    @property
    @override
    def name(self) -> str:
        return "hardcoded_value"

    @property
    @override
    def description(self) -> str:
        return "Flags hardcoded URLs, IPs, credentials, and environment-specific values"

    @property
    @override
    def tags(self) -> list[str]:
        return ["variables", "maintainability", "security"]

    @override
    def analyze(self, test_file: TestFile) -> list[Finding]:
        findings: list[Finding] = []
        suite = RobotASTParser().parse_suite(test_file)

        for call in suite.all_keyword_calls:
            if not call.arguments:
                continue
            line_num = call.location.line
            arg_text = " ".join(call.arguments)
            if self._is_ignored(arg_text):
                continue
            findings.extend(self._check_line(arg_text, line_num, test_file))

        return findings

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _check_line(
        self, line: str, line_num: int, test_file: TestFile
    ) -> list[Finding]:
        results: list[Finding] = []

        if self._check_urls:
            results.extend(self._check_urls_in_line(line, line_num, test_file))

        if self._check_localhost:
            results.extend(self._check_localhost_in_line(line, line_num, test_file))

        if self._check_ips:
            results.extend(self._check_ips_in_line(line, line_num, test_file))

        if self._check_creds:
            results.extend(self._check_creds_in_line(line, line_num, test_file))

        if self._check_ports:
            results.extend(self._check_ports_in_line(line, line_num, test_file))

        return results

    def _check_urls_in_line(
        self, line: str, line_num: int, test_file: TestFile
    ) -> list[Finding]:
        """Check for hardcoded URLs."""
        results: list[Finding] = []
        for m in _URL_RE.finditer(line):
            url = m.group(0)
            results.append(
                self._make_finding(
                    line_num,
                    test_file,
                    f"Hardcoded URL '{url}'",
                    "Replace with a variable, e.g. ${BASE_URL}",
                    value=url,
                    value_type="url",
                )
            )
        return results

    def _check_localhost_in_line(
        self, line: str, line_num: int, test_file: TestFile
    ) -> list[Finding]:
        """Check for hardcoded localhost references."""
        if not _LOCALHOST_RE.search(line):
            return []
        if self._check_urls and _URL_RE.search(line):
            return []
        return [
            self._make_finding(
                line_num,
                test_file,
                "Hardcoded 'localhost' reference",
                "Replace with ${HOST} or ${BASE_URL} variable",
                value="localhost",
                value_type="localhost",
            )
        ]

    def _check_ips_in_line(
        self, line: str, line_num: int, test_file: TestFile
    ) -> list[Finding]:
        """Check for hardcoded IP addresses."""
        results: list[Finding] = []
        for m in _IP_RE.finditer(line):
            ip = m.group(0)
            results.append(
                self._make_finding(
                    line_num,
                    test_file,
                    f"Hardcoded IP address '{ip}'",
                    "Replace with a variable, e.g. ${SERVER_IP}",
                    value=ip,
                    value_type="ip_address",
                )
            )
        return results

    def _check_creds_in_line(
        self, line: str, line_num: int, test_file: TestFile
    ) -> list[Finding]:
        """Check for credential-like patterns."""
        results: list[Finding] = []
        for m in _CRED_RE.finditer(line):
            token = m.group(0)
            display = token[:40] + "..." if len(token) > 40 else token
            results.append(
                self._make_finding(
                    line_num,
                    test_file,
                    f"Possible hardcoded credential: '{display}'",
                    "Replace with a secret variable or vault reference",
                    value=display,
                    value_type="credential",
                    severity=Severity.ERROR,
                )
            )
        return results

    def _check_ports_in_line(
        self, line: str, line_num: int, test_file: TestFile
    ) -> list[Finding]:
        """Check for hardcoded port numbers."""
        results: list[Finding] = []
        for m in _PORT_RE.finditer(line):
            port = m.group(0)
            results.append(
                self._make_finding(
                    line_num,
                    test_file,
                    f"Hardcoded port number '{port}'",
                    "Replace with a variable, e.g. ${APP_PORT}",
                    value=port,
                    value_type="port",
                    severity=Severity.INFO,
                )
            )
        return results

    def _make_finding(
        self,
        line_num: int,
        test_file: TestFile,
        description: str,
        recommendation: str,
        *,
        value: str,
        value_type: str,
        severity: Severity = Severity.WARNING,
    ) -> Finding:
        pattern = Pattern(
            pattern_type=PatternType.HARDCODED_VALUE,
            name="Hardcoded Value",
            description=description,
            recommendation=recommendation,
            documentation_url=None,
            auto_fixable=False,
        )
        return Finding.create(
            pattern=pattern,
            severity=severity,
            location=Location(file_path=test_file.path, line=line_num),
            message=description,
            value=value,
            value_type=value_type,
        )

    def _is_ignored(self, line: str) -> bool:
        return any(p.search(line) for p in self._ignore)
