#!/usr/bin/env python3
"""
Migration script to restructure robot-optimizer to proper Core/Pro split.
Preserves all code while moving to correct locations.
"""
import os
import shutil
from pathlib import Path
import json

# Define what stays in Core vs moves to Pro
CORE_STRUCTURE = {
    "src/robot_optimizer_core": {
        "domain": {
            "__init__.py": "keep",
            "base.py": "keep",
            "entities": {
                "__init__.py": "simplified",  # Remove Analysis
                "test_file.py": "keep",
            },
            "value_objects": {
                "__init__.py": "simplified",  # Remove Pro value objects
                "severity.py": "keep",
                "location.py": "keep", 
                "pattern.py": "keep",
                "finding.py": "keep",
                "sleep_pattern.py": "keep",
                "test_result.py": "keep",
                "flakiness_stats.py": "keep",
                "robot_ast.py": "keep",
                # These move to Pro:
                # "optimization_suggestion.py": "pro",
                # "cross_file_reference.py": "pro",
            },
            "repositories": {
                "__init__.py": "keep",
                "test_result_repository.py": "keep",
                "robot_parser_repository.py": "keep",
            },
            # "events.py": "pro",  # Most events move to Pro
            # "services": "remove",  # Services pattern not in Core
        },
        "analyzers": {
            "__init__.py": "create",
            "base_analyzer.py": "create",
            "dead_code.py": "simplified",  # Basic implementation only
            "sleep_detector.py": "create",  # Extract from current code
            "flakiness.py": "simplified",
        },
        "parsers": {
            "__init__.py": "keep",
            "robot_ast_parser.py": "keep",
            "robot_parser_interface.py": "create",
        },
        "discovery": {
            "__init__.py": "create",
            "file_finder.py": "move",  # from infrastructure/services
        },
        "config": {
            "__init__.py": "create",
            "settings.py": "move",  # from infrastructure
        },
    }
}

PRO_STRUCTURE = {
    "robot-optimizer-pro": {
        "src/robot_optimizer_pro": {
            "analyzers": {
                "advanced_dead_code.py": "from:dead_code_analyzer.py",
                "impact_analyzer.py": "new",
                "complexity_analyzer.py": "extract",
            },
            "models": {
                "optimization_suggestion.py": "move",
                "cross_file_reference.py": "move", 
                "analysis.py": "move",  # Analysis entity is Pro
                "dependency_graph.py": "new",
            },
            "strategies": {
                "parser_strategies.py": "move",
                "auto_fixer.py": "new",
            },
            "events": {
                "__init__.py": "move",
                "events.py": "move",
            },
            "infrastructure": {
                "performance.py": "move",
                "batch_repository.py": "move",
            }
        }
    }
}

def create_directory_structure():
    """Create the new directory structure."""
    print("🏗️  Creating directory structure...")
    
    # Create Core directories
    for path in [
        "src/robot_optimizer_core/domain/entities",
        "src/robot_optimizer_core/domain/value_objects", 
        "src/robot_optimizer_core/domain/repositories",
        "src/robot_optimizer_core/analyzers",
        "src/robot_optimizer_core/parsers",
        "src/robot_optimizer_core/discovery", 
        "src/robot_optimizer_core/config",
    ]:
        Path(path).mkdir(parents=True, exist_ok=True)
        print(f"  ✅ Created {path}")

def move_core_files():
    """Move files that belong in Core."""
    print("\n📦 Moving Core files...")
    
    moves = [
        # Domain base
        ("src/robot_optimizer/domain/base.py", "src/robot_optimizer_core/domain/base.py"),
        
        # Entities (only TestFile for Core)
        ("src/robot_optimizer/domain/entities/test_file.py", "src/robot_optimizer_core/domain/entities/test_file.py"),
        
        # Value objects for Core
        ("src/robot_optimizer/domain/value_objects/severity.py", "src/robot_optimizer_core/domain/value_objects/severity.py"),
        ("src/robot_optimizer/domain/value_objects/location.py", "src/robot_optimizer_core/domain/value_objects/location.py"),
        ("src/robot_optimizer/domain/value_objects/pattern.py", "src/robot_optimizer_core/domain/value_objects/pattern.py"),
        ("src/robot_optimizer/domain/value_objects/finding.py", "src/robot_optimizer_core/domain/value_objects/finding.py"),
        ("src/robot_optimizer/domain/value_objects/sleep_pattern.py", "src/robot_optimizer_core/domain/value_objects/sleep_pattern.py"),
        ("src/robot_optimizer/domain/value_objects/test_result.py", "src/robot_optimizer_core/domain/value_objects/test_result.py"),
        ("src/robot_optimizer/domain/value_objects/flakiness_stats.py", "src/robot_optimizer_core/domain/value_objects/flakiness_stats.py"),
        ("src/robot_optimizer/domain/value_objects/robot_ast.py", "src/robot_optimizer_core/domain/value_objects/robot_ast.py"),
        
        # Repositories
        ("src/robot_optimizer/domain/repositories/test_result_repository.py", "src/robot_optimizer_core/domain/repositories/test_result_repository.py"),
        ("src/robot_optimizer/domain/repositories/robot_parser_repository.py", "src/robot_optimizer_core/domain/repositories/robot_parser_repository.py"),
        
        # Parser
        ("src/robot_optimizer/infrastructure/parsers/robot_ast_parser.py", "src/robot_optimizer_core/parsers/robot_ast_parser.py"),
        
        # Discovery (from infrastructure)
        ("src/robot_optimizer/infrastructure/services/file_discovery.py", "src/robot_optimizer_core/discovery/file_finder.py"),
        
        # Config
        ("src/robot_optimizer/infrastructure/config.py", "src/robot_optimizer_core/config/settings.py"),
    ]
    
    for src, dst in moves:
        if Path(src).exists():
            Path(dst).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            print(f"  ✅ Moved {src} → {dst}")

def create_simplified_analyzers():
    """Create simplified analyzers for Core."""
    print("\n🔧 Creating simplified Core analyzers...")
    
    # Base analyzer
    base_analyzer = '''"""Base analyzer interface for Robot Framework analysis."""
from abc import ABC, abstractmethod
from typing import List

from ..domain.entities import TestFile
from ..domain.value_objects import Finding


class BaseAnalyzer(ABC):
    """Abstract base class for all analyzers."""
    
    @abstractmethod
    def analyze(self, test_file: TestFile) -> List[Finding]:
        """Analyze a test file and return findings.
        
        Args:
            test_file: The test file to analyze
            
        Returns:
            List of findings discovered
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Get the analyzer name."""
        pass
    
    @property 
    @abstractmethod
    def description(self) -> str:
        """Get the analyzer description."""
        pass
'''
    
    # Simplified dead code analyzer
    dead_code = '''"""Basic dead code analyzer for Robot Framework tests."""
import re
from typing import List, Dict, Set

from .base_analyzer import BaseAnalyzer
from ..domain.entities import TestFile
from ..domain.value_objects import Finding, Pattern, PatternType, Severity, Location


class DeadCodeAnalyzer(BaseAnalyzer):
    """Basic analyzer for finding unused keywords.
    
    This is the Core version with basic regex-based detection.
    The Pro version extends this with AST parsing and advanced features.
    """
    
    @property
    def name(self) -> str:
        return "Dead Code Analyzer"
    
    @property
    def description(self) -> str:
        return "Finds unused keywords and duplicate definitions"
    
    def analyze(self, test_file: TestFile) -> List[Finding]:
        """Analyze test file for dead code using basic regex approach."""
        findings = []
        
        # Basic keyword detection patterns
        self.section_pattern = re.compile(r'^\*+\s*(Test Cases?|Keywords?)\s*\*+', re.IGNORECASE)
        self.keyword_def_pattern = re.compile(r'^([A-Za-z][A-Za-z0-9 _]*[A-Za-z0-9])\s*$')
        self.keyword_usage_pattern = re.compile(r'^\s+([\w\s\.]+?)(?:\s{2,}|$)')
        
        findings.extend(self._find_unused_keywords(test_file))
        findings.extend(self._find_duplicate_keywords(test_file))
        
        return findings
    
    def _find_unused_keywords(self, test_file: TestFile) -> List[Finding]:
        """Find unused keywords using basic pattern matching."""
        lines = test_file.content.splitlines()
        
        # Track definitions and usage
        keyword_definitions: Dict[str, int] = {}
        keyword_usages: Set[str] = set()
        in_keyword_section = False
        
        for line_num, line in enumerate(lines, 1):
            # Check section headers
            if self.section_pattern.match(line):
                in_keyword_section = 'keyword' in line.lower()
                continue
            
            # Skip empty lines and comments
            if not line.strip() or line.strip().startswith('#'):
                continue
            
            # In keywords section - track definitions
            if in_keyword_section and not line.startswith((' ', '\t')):
                match = self.keyword_def_pattern.match(line)
                if match:
                    keyword_name = match.group(1)
                    keyword_definitions[keyword_name] = line_num
            
            # Track keyword usage
            elif line.startswith((' ', '\t')):
                match = self.keyword_usage_pattern.match(line)
                if match:
                    potential_keyword = match.group(1).strip()
                    if not self._is_builtin_keyword(potential_keyword):
                        keyword_usages.add(potential_keyword)
        
        # Find unused keywords
        findings = []
        for keyword_name, line_num in keyword_definitions.items():
            if keyword_name not in keyword_usages:
                pattern = Pattern(
                    type=PatternType.UNUSED_KEYWORD,
                    name="Unused Keyword",
                    description=f"Keyword '{keyword_name}' is defined but never used",
                    recommendation="Remove unused keyword to reduce maintenance burden",
                    auto_fixable=True
                )
                
                finding = Finding.create(
                    pattern=pattern,
                    severity=Severity.WARNING,
                    location=Location(file_path=test_file.path, line=line_num),
                    message=f"Unused keyword '{keyword_name}' - can be safely removed",
                    keyword_name=keyword_name
                )
                findings.append(finding)
        
        return findings
    
    def _find_duplicate_keywords(self, test_file: TestFile) -> List[Finding]:
        """Find duplicate keyword definitions."""
        lines = test_file.content.splitlines()
        keyword_definitions: Dict[str, List[int]] = {}
        in_keyword_section = False
        
        for line_num, line in enumerate(lines, 1):
            if self.section_pattern.match(line):
                in_keyword_section = 'keyword' in line.lower()
                continue
            
            if in_keyword_section and not line.startswith((' ', '\t')):
                match = self.keyword_def_pattern.match(line)
                if match:
                    keyword_name = match.group(1)
                    if keyword_name not in keyword_definitions:
                        keyword_definitions[keyword_name] = []
                    keyword_definitions[keyword_name].append(line_num)
        
        # Create findings for duplicates
        findings = []
        for keyword_name, locations in keyword_definitions.items():
            if len(locations) > 1:
                pattern = Pattern.duplicate_keyword(keyword_name)
                
                finding = Finding.create(
                    pattern=pattern,
                    severity=Severity.ERROR,
                    location=Location(file_path=test_file.path, line=locations[0]),
                    message=f"Keyword '{keyword_name}' defined {len(locations)} times",
                    keyword_name=keyword_name,
                    occurrences=locations,
                    duplicate_count=len(locations)
                )
                findings.append(finding)
        
        return findings
    
    def _is_builtin_keyword(self, keyword_name: str) -> bool:
        """Check if keyword is a built-in Robot Framework keyword."""
        builtins = {
            'log', 'log to console', 'set variable', 'should be equal',
            'should contain', 'should be true', 'should be false',
            'run keyword', 'run keyword if', 'sleep', 'comment',
            'no operation', 'fail', 'pass execution'
        }
        return keyword_name.lower() in builtins or '.' in keyword_name
'''
    
    # Sleep detector
    sleep_detector = '''"""Sleep pattern detector for Robot Framework tests."""
import re
from decimal import Decimal
from typing import List

from .base_analyzer import BaseAnalyzer
from ..domain.entities import TestFile
from ..domain.value_objects import Finding, Pattern, Severity, Location, SleepPattern


class SleepDetector(BaseAnalyzer):
    """Detects sleep usage in Robot Framework tests."""
    
    @property
    def name(self) -> str:
        return "Sleep Pattern Detector"
    
    @property
    def description(self) -> str:
        return "Finds Sleep keyword usage that makes tests slow and fragile"
    
    def analyze(self, test_file: TestFile) -> List[Finding]:
        """Find all sleep patterns in the test file."""
        findings = []
        lines = test_file.content.splitlines()
        
        # Pattern to match Sleep keyword usage
        sleep_pattern = re.compile(
            r'^\s*Sleep\s+(\d+(?:\.\d+)?)\s*(s|seconds?|m|minutes?|ms|milliseconds?)?',
            re.IGNORECASE
        )
        
        for line_num, line in enumerate(lines, 1):
            match = sleep_pattern.match(line)
            if match:
                duration = Decimal(match.group(1))
                unit = match.group(2) or 's'  # Default to seconds
                
                try:
                    sleep = SleepPattern(
                        duration=duration,
                        unit=unit.lower(),
                        line_number=line_num,
                        original_text=line.strip()
                    )
                    
                    # Determine severity based on duration
                    if sleep.duration_in_seconds < 1:
                        severity = Severity.INFO
                    elif sleep.duration_in_seconds < 5:
                        severity = Severity.WARNING
                    else:
                        severity = Severity.ERROR
                    
                    pattern = Pattern.sleep_in_test(f"{duration} {unit}")
                    
                    finding = Finding.create(
                        pattern=pattern,
                        severity=severity,
                        location=Location(file_path=test_file.path, line=line_num),
                        message=f"Sleep {duration} {unit} makes tests slow and fragile",
                        duration=str(duration),
                        unit=unit,
                        duration_seconds=sleep.duration_in_seconds
                    )
                    findings.append(finding)
                    
                except ValueError:
                    # Skip invalid sleep patterns
                    pass
        
        return findings
'''
    
    # Flakiness analyzer
    flakiness = '''"""Basic flakiness analyzer for Robot Framework tests."""
from typing import List

from .base_analyzer import BaseAnalyzer
from ..domain.entities import TestFile
from ..domain.value_objects import Finding, Pattern, PatternType, Severity, Location
from ..domain.repositories import TestResultRepository


class FlakinessAnalyzer(BaseAnalyzer):
    """Basic analyzer for detecting flaky tests.
    
    This Core version provides basic flakiness detection.
    The Pro version adds trend analysis and root cause detection.
    """
    
    def __init__(self, test_result_repository: TestResultRepository):
        self.test_result_repository = test_result_repository
    
    @property
    def name(self) -> str:
        return "Flakiness Analyzer"
    
    @property
    def description(self) -> str:
        return "Detects tests that fail intermittently"
    
    def analyze(self, test_file: TestFile) -> List[Finding]:
        """Analyze test file for flaky tests."""
        findings = []
        
        # Get flakiness statistics
        stats_list = self.test_result_repository.get_flakiness_stats(
            test_file.path, days_back=30
        )
        
        for stats in stats_list:
            if stats.is_flaky and stats.failure_rate > 0.05:
                severity = self._determine_severity(stats.failure_rate)
                
                pattern = Pattern(
                    type=PatternType.INEFFICIENT_WAIT,
                    name="Flaky Test",
                    description=f"Test '{stats.test_name}' fails inconsistently",
                    recommendation="Add explicit waits or fix race conditions",
                    auto_fixable=False
                )
                
                finding = Finding.create(
                    pattern=pattern,
                    severity=severity,
                    location=Location(file_path=test_file.path, line=1),
                    message=f"Flaky test: {stats.failure_rate:.1%} failure rate",
                    test_name=stats.test_name,
                    failure_rate=stats.failure_rate,
                    total_runs=stats.total_runs
                )
                findings.append(finding)
        
        return findings
    
    def _determine_severity(self, failure_rate: float) -> Severity:
        """Determine severity based on failure rate."""
        if failure_rate > 0.15:
            return Severity.ERROR
        elif failure_rate > 0.05:
            return Severity.WARNING
        else:
            return Severity.INFO
'''
    
    # Write files
    files = {
        "src/robot_optimizer_core/analyzers/__init__.py": '''"""Core analyzers for Robot Framework optimization."""
from .base_analyzer import BaseAnalyzer
from .dead_code import DeadCodeAnalyzer
from .sleep_detector import SleepDetector
from .flakiness import FlakinessAnalyzer

__all__ = [
    "BaseAnalyzer",
    "DeadCodeAnalyzer", 
    "SleepDetector",
    "FlakinessAnalyzer",
]
''',
        "src/robot_optimizer_core/analyzers/base_analyzer.py": base_analyzer,
        "src/robot_optimizer_core/analyzers/dead_code.py": dead_code,
        "src/robot_optimizer_core/analyzers/sleep_detector.py": sleep_detector,
        "src/robot_optimizer_core/analyzers/flakiness.py": flakiness,
    }
    
    for path, content in files.items():
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(content)
        print(f"  ✅ Created {path}")

def create_simplified_inits():
    """Create simplified __init__.py files for Core."""
    print("\n📝 Creating simplified __init__.py files...")
    
    inits = {
        "src/robot_optimizer_core/__init__.py": '''"""Robot Framework Optimizer Core - Shared analysis engine."""
__version__ = "0.1.0"
''',
        
        "src/robot_optimizer_core/domain/__init__.py": '''"""Core domain models."""
''',
        
        "src/robot_optimizer_core/domain/entities/__init__.py": '''"""Core domain entities."""
from .test_file import TestFile

__all__ = ["TestFile"]
''',
        
        "src/robot_optimizer_core/domain/value_objects/__init__.py": '''"""Core value objects."""
from .severity import Severity
from .location import Location
from .pattern import Pattern, PatternType
from .finding import Finding
from .sleep_pattern import SleepPattern
from .test_result import TestResult
from .flakiness_stats import FlakinessStats

__all__ = [
    "Severity",
    "Location",
    "Pattern",
    "PatternType", 
    "Finding",
    "SleepPattern",
    "TestResult",
    "FlakinessStats",
]
''',
        
        "src/robot_optimizer_core/domain/repositories/__init__.py": '''"""Core repository interfaces."""
from .test_result_repository import TestResultRepository
from .robot_parser_repository import RobotParserRepository

__all__ = [
    "TestResultRepository",
    "RobotParserRepository",
]
''',
        
        "src/robot_optimizer_core/parsers/__init__.py": '''"""Core parsers for Robot Framework."""
from .robot_ast_parser import RobotASTParser

__all__ = ["RobotASTParser"]
''',
        
        "src/robot_optimizer_core/discovery/__init__.py": '''"""File discovery services."""
from .file_finder import FileDiscoveryService

__all__ = ["FileDiscoveryService"]
''',
        
        "src/robot_optimizer_core/config/__init__.py": '''"""Core configuration."""
from .settings import Settings

__all__ = ["Settings"]
''',
    }
    
    for path, content in inits.items():
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(content)
        print(f"  ✅ Created {path}")

def save_pro_files():
    """Save files that will move to Pro package."""
    print("\n💾 Saving Pro files for later...")
    
    pro_files = {
        "pro_files/analyzers/advanced_dead_code.py": "src/robot_optimizer/domain/services/dead_code_analyzer.py",
        "pro_files/strategies/parser_strategies.py": "src/robot_optimizer/application/services/parser_strategies.py",
        "pro_files/models/optimization_suggestion.py": "src/robot_optimizer/domain/value_objects/optimization_suggestion.py",
        "pro_files/models/cross_file_reference.py": "src/robot_optimizer/domain/value_objects/cross_file_reference.py",
        "pro_files/models/analysis.py": "src/robot_optimizer/domain/entities/analysis.py",
        "pro_files/events/events.py": "src/robot_optimizer/domain/events.py",
        "pro_files/infrastructure/performance.py": "src/robot_optimizer/infrastructure/performance.py",
        "pro_files/infrastructure/batch_repository.py": "src/robot_optimizer/infrastructure/repositories/batch_repository.py",
    }
    
    for dst, src in pro_files.items():
        if Path(src).exists():
            Path(dst).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            print(f"  💾 Saved {src} → {dst}")

def update_imports():
    """Update import statements in Core files."""
    print("\n🔄 Updating import statements...")
    
    # This would be more complex in reality, but here's the basic idea
    replacements = [
        ("from robot_optimizer.", "from robot_optimizer_core."),
        ("from ..application.", "from .."),
        ("from ..infrastructure.", "from .."),
        ("from ...domain.", "from ..domain."),
    ]
    
    for root, dirs, files in os.walk("src/robot_optimizer_core"):
        for file in files:
            if file.endswith(".py"):
                path = Path(root) / file
                content = path.read_text()
                
                for old, new in replacements:
                    content = content.replace(old, new)
                
                path.write_text(content)
    
    print("  ✅ Updated imports")

def create_migration_summary():
    """Create a summary of the migration."""
    summary = {
        "core_files": {
            "domain": {
                "base.py": "✅ Kept",
                "entities/test_file.py": "✅ Kept", 
                "entities/analysis.py": "➡️ Moved to Pro",
                "value_objects": "✅ Basic ones kept, advanced moved to Pro",
                "repositories": "✅ Interfaces kept",
                "events.py": "➡️ Moved to Pro",
            },
            "analyzers": {
                "base_analyzer.py": "✅ Created",
                "dead_code.py": "✅ Simplified",
                "sleep_detector.py": "✅ Created",
                "flakiness.py": "✅ Simplified",
            },
            "parsers": "✅ Basic AST parser kept",
            "discovery": "✅ File finder moved from infrastructure",
            "config": "✅ Settings moved from infrastructure",
        },
        "pro_files_saved": "✅ All advanced features saved in pro_files/",
        "tests": "⚠️ Need to update test imports after migration"
    }
    
    with open("migration_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    
    print("\n📊 Migration summary saved to migration_summary.json")

def main():
    """Run the migration."""
    print("🚀 Starting Robot Framework Optimizer Core migration...\n")
    
    # Check if source exists
    if not Path("src/robot_optimizer").exists():
        print("❌ Source directory src/robot_optimizer not found!")
        return
    
    # Create backup
    print("💾 Creating backup...")
    if Path("src/robot_optimizer_backup").exists():
        shutil.rmtree("src/robot_optimizer_backup")
    shutil.copytree("src/robot_optimizer", "src/robot_optimizer_backup")
    print("  ✅ Backup created at src/robot_optimizer_backup")
    
    # Run migration
    create_directory_structure()
    move_core_files()
    create_simplified_analyzers()
    create_simplified_inits()
    save_pro_files()
    update_imports()
    create_migration_summary()
    
    print("\n✅ Migration complete!")
    print("\n📋 Next steps:")
    print("1. Review the migrated Core structure in src/robot_optimizer_core")
    print("2. Update test imports to use robot_optimizer_core")
    print("3. Test that Core package works independently")
    print("4. Pro files are saved in pro_files/ for future use")
    print("\n⚠️  Remember to:")
    print("- Update pyproject.toml if needed")
    print("- Run tests to ensure everything works")
    print("- The original code is backed up in src/robot_optimizer_backup")

if __name__ == "__main__":
    main()