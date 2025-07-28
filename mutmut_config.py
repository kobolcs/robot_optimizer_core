# mutmut_config.py
"""Configuration for mutmut mutation testing.

This ensures our test suite can detect code mutations,
proving the tests actually verify the implementation.
"""


def pre_mutation(context):
    """Setup before mutations."""
    # Skip slow tests during mutation testing
    context.config.test_command = "pytest -x -q --tb=no -m 'not slow'"


def post_mutation(context):
    """Cleanup after mutations."""
    pass


# Files to mutate
paths_to_mutate = [
    "src/robot_optimizer_core/analyzers/",
    "src/robot_optimizer_core/domain/",
    "src/robot_optimizer_core/discovery/",
    "src/robot_optimizer_core/parsers/",
]

# Files to exclude from mutation
paths_to_exclude = [
    "src/robot_optimizer_core/__init__.py",
    "src/robot_optimizer_core/__version__.py",
    "src/robot_optimizer_core/exceptions.py",  # Just error classes
    "src/robot_optimizer_core/logging.py",     # Side effects
    "src/robot_optimizer_core/metrics.py",     # Side effects
]

# Test command
test_command = "pytest -x -q --tb=no"

# Runner settings
runner = "pytest"
tests_dir = "tests/"

# Coverage threshold
coverage_threshold = 0.95

# Mutation operators to use
mutation_types = [
    "AOR",  # Arithmetic Operator Replacement
    "ASR",  # Assignment Operator Replacement
    "BCR",  # Break Continue Replacement
    "COI",  # Conditional Operator Insertion
    "CRP",  # Constant Replacement
    "DDL",  # Decorator Deletion
    "EHD",  # Exception Handler Deletion
    "EXD",  # Exception Swallowing Deletion
    "IHD",  # Hiding Variable Deletion
    "IOD",  # Overriding Method Deletion
    "LCR",  # Logical Connector Replacement
    "LOD",  # Logical Operator Deletion
    "LOR",  # Logical Operator Replacement
    "ROR",  # Relational Operator Replacement
    "SCD",  # Super Calling Deletion
    "SCI",  # Super Calling Insertion
    "SIR",  # Slice Index Replacement
]

# Equivalent mutants to skip (false positives)
def skip_mutant(context, mutation):
    """Skip known equivalent mutants."""
    # Skip mutations in __repr__ methods
    if "__repr__" in context.filename and "return" in mutation:
        return True
    
    # Skip mutations in type annotations
    if " -> " in context.current_line:
        return True
    
    # Skip mutations in docstrings
    if '"""' in context.current_line or "'''" in context.current_line:
        return True
    
    return False