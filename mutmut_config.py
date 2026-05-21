# mutmut_config.py
"""Configuration for mutmut mutation testing.

Scope: analyzers only, tested by tests/unit/analyzers/ for fast CI feedback.
"""


def pre_mutation(context):
    """Set the focused test command before each mutation."""
    context.config.test_command = (
        "pytest -x -q --tb=no --no-cov tests/unit/analyzers/"
    )


def post_mutation(context):
    pass


# Mutate only the analyzer layer.
paths_to_mutate = [
    "src/robot_optimizer_core/analyzers/",
]

# Exclude package init files (no logic to mutate).
paths_to_exclude = [
    "src/robot_optimizer_core/analyzers/__init__.py",
]

# Fallback test command (overridden per-mutation in pre_mutation above).
test_command = "pytest -x -q --tb=no --no-cov tests/unit/analyzers/"

runner = "pytest"
tests_dir = "tests/unit/analyzers/"


def skip_mutant(context, mutation):
    """Skip equivalent mutants with no observable effect."""
    # Type-annotation-only lines have no runtime effect.
    if " -> " in context.current_line and "return" not in context.current_line:
        return True
    # Docstrings carry no logic.
    if context.current_line.strip().startswith(('"""', "'''")):
        return True
    return False
