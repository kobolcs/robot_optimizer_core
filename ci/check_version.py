#!/usr/bin/env python3
"""Verify pyproject.toml version matches __version__.py before building."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

toml_text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
toml_match = re.search(r'^version\s*=\s*"([^"]+)"', toml_text, re.MULTILINE)
if not toml_match:
    print("ERROR: Could not find version in pyproject.toml", file=sys.stderr)
    sys.exit(1)
toml_version = toml_match.group(1)

ver_text = (ROOT / "src" / "robot_optimizer_core" / "__version__.py").read_text(encoding="utf-8")
major = int(re.search(r"major=(\d+)", ver_text).group(1))
minor = int(re.search(r"minor=(\d+)", ver_text).group(1))
patch = int(re.search(r"patch=(\d+)", ver_text).group(1))
py_version = f"{major}.{minor}.{patch}"

if toml_version != py_version:
    print(
        f"ERROR: Version mismatch — pyproject.toml={toml_version!r} but __version__.py={py_version!r}",
        file=sys.stderr,
    )
    sys.exit(1)

print(f"OK: version={toml_version}")
