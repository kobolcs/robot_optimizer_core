    # src/robot_optimizer_core/discovery/secure_file_finder.py
"""Secure file discovery service that prevents path traversal attacks."""
from __future__ import annotations

import fnmatch
import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from ..config import get_settings
from ..exceptions import FileNotFoundError as RFFileNotFoundError, ValidationError
from ..logging import get_logger
from ..metrics import get_metrics


@dataclass(slots=True)
class FileStats:
    """Statistics about discovered files."""
    total_files: int = 0
    total_size_bytes: int = 0
    excluded_files: int = 0
    invalid_files: int = 0
    security_violations: int = 0

    @property
    def total_size_mb(self) -> float:
        """Get total size in megabytes."""
        return self.total_size_bytes / (1024 * 1024)


class PathSecurityValidator:
    """Validates paths to prevent security vulnerabilities."""
    
    # Dangerous path patterns
    DANGEROUS_PATTERNS = {
        '..',  # Parent directory traversal
        '~',   # Home directory expansion
        '$',   # Environment variable expansion
        '%',   # Windows environment variable
    }
    
    # Restricted directories (customize based on OS and requirements)
    RESTRICTED_PATHS = {
        '/etc',
        '/sys',
        '/proc',
        '/dev',
        '/var/log',
        '/root',
        '/home',
        'C:\\Windows',
        'C:\\Program Files',
    }
    
    @classmethod
    def validate_path(cls, path: Path, root_path: Path) -> tuple[bool, str | None]:
        """Validate a path for security issues.
        
        Args:
            path: Path to validate
            root_path: Allowed root directory
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Resolve to absolute paths
            abs_path = path.resolve()
            abs_root = root_path.resolve()
            
            # Check if path is under root
            try:
                abs_path.relative_to(abs_root)
            except ValueError:
                return False, f"Path '{path}' is outside allowed root '{root_path}'"
            
            # Check for dangerous patterns in path string
            path_str = str(path)
            for pattern in cls.DANGEROUS_PATTERNS:
                if pattern in path_str:
                    return False, f"Path contains dangerous pattern: {pattern}"
            
            # Check against restricted paths
            for restricted in cls.RESTRICTED_PATHS:
                if str(abs_path).startswith(restricted):
                    return False, f"Path is in restricted directory: {restricted}"
            
            # Check symlink attacks
            if path.exists() and path.is_symlink():
                link_target = path.readlink()
                if not cls._is_safe_symlink(path, link_target, abs_root):
                    return False, f"Unsafe symlink detected: {path} -> {link_target}"
            
            # Additional Windows-specific checks
            if os.name == 'nt':
                # Check for alternate data streams
                if ':' in path.name and not path.name.endswith(':'):
                    return False, "Path contains alternate data stream"
                
                # Check for reserved names
                reserved = {'CON', 'PRN', 'AUX', 'NUL', 'COM1', 'LPT1'}
                if path.stem.upper() in reserved:
                    return False, f"Path contains reserved name: {path.stem}"
            
            return True, None
            
        except Exception as e:
            return False, f"Path validation error: {e}"
    
    @classmethod
    def _is_safe_symlink(cls, symlink: Path, target: Path, root: Path) -> bool:
        """Check if a symlink is safe (doesn't escape root)."""
        try:
            if target.is_absolute():
                resolved = target.resolve()
            else:
                resolved = (symlink.parent / target).resolve()
            
            # Check if resolved path is under root
            resolved.relative_to(root)
            return True
        except ValueError:
            return False
    
    @classmethod
    def sanitize_pattern(cls, pattern: str) -> str:
        """Sanitize a file pattern to prevent injection."""
        # Remove path separators
        pattern = pattern.replace('/', '').replace('\\', '')
        
        # Remove dangerous characters
        dangerous_chars = ['..', '~', '$', '%', '\x00']
        for char in dangerous_chars:
            pattern = pattern.replace(char, '')
        
        return pattern


class SecureFileDiscoveryService:
    """Secure file discovery service with path traversal protection."""
    
    def __init__(self, settings=None):
        """Initialize the secure file discovery service."""
        self.settings = settings or get_settings()
        self.logger = get_logger(__name__)
        self.metrics = get_metrics()
        self._stats = FileStats()
        self.validator = PathSecurityValidator()
        
        # Whitelist of allowed file extensions
        self.allowed_extensions = {'.robot', '.resource', '.txt', '.py'}
        
        # Maximum path depth to prevent infinite recursion
        self.max_depth = 20
    
    def find_files(
        self,
        root_path: Path,
        patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
        recursive: bool = True,
        follow_symlinks: bool = False,
        max_depth: int | None = None
    ) -> list[Path]:
        """Securely find all matching files in a directory.
        
        Args:
            root_path: Root directory to search
            patterns: File patterns to match
            exclude_patterns: Patterns to exclude
            recursive: Whether to search subdirectories
            follow_symlinks: Whether to follow symbolic links (DANGEROUS!)
            max_depth: Maximum directory depth
            
        Returns:
            List of matching file paths
            
        Raises:
            ValidationError: If paths fail security validation
        """
        # Reset stats
        self._stats = FileStats()
        
        # Validate root path
        root_path = Path(root_path).resolve()
        is_valid, error = self.validator.validate_path(root_path, root_path)
        if not is_valid:
            raise ValidationError(
                f"Invalid root path: {error}",
                field_name="root_path",
                invalid_value=str(root_path)
            )
        
        if not root_path.exists():
            raise RFFileNotFoundError(root_path)
        
        if not root_path.is_dir():
            raise ValidationError(
                "Root path must be a directory",
                field_name="root_path",
                invalid_value=str(root_path)
            )
        
        # Sanitize patterns
        patterns = patterns or self.settings.file_patterns
        patterns = [self.validator.sanitize_pattern(p) for p in patterns]
        
        exclude_patterns = exclude_patterns or self.settings.exclude_patterns
        exclude_patterns = [self.validator.sanitize_pattern(p) for p in exclude_patterns]
        
        # Set max depth
        max_depth = max_depth or self.max_depth
        
        # Log security warning if following symlinks
        if follow_symlinks:
            self.logger.warning(
                "Following symlinks is enabled - this can be a security risk!",
                extra={"root": str(root_path)}
            )
        
        self.logger.info(
            "Starting secure file discovery",
            extra={
                "root": str(root_path),
                "patterns": patterns,
                "recursive": recursive,
                "follow_symlinks": follow_symlinks
            }
        )
        
        # Collect files
        with self.metrics.timer("discovery.duration"):
            files = list(self._discover_files_secure(
                root_path,
                root_path,  # Pass original root for validation
                patterns,
                exclude_patterns,
                recursive,
                follow_symlinks,
                max_depth,
                0
            ))
        
        # Sort for consistent ordering
        files.sort()
        
        self.logger.info(
            "Secure file discovery complete",
            extra={
                "root": str(root_path),
                "files_found": len(files),
                "security_violations": self._stats.security_violations,
                "stats": {
                    "total_size_mb": self._stats.total_size_mb,
                    "excluded": self._stats.excluded_files,
                    "invalid": self._stats.invalid_files
                }
            }
        )
        
        return files
    
    def _discover_files_secure(
        self,
        current_path: Path,
        root_path: Path,
        patterns: list[str],
        exclude_patterns: list[str],
        recursive: bool,
        follow_symlinks: bool,
        max_depth: int,
        current_depth: int
    ) -> Iterator[Path]:
        """Securely discover files with validation."""
        # Check depth limit
        if current_depth > max_depth:
            self.logger.warning(
                f"Maximum depth {max_depth} reached at: {current_path}"
            )
            return
        
        # Validate current path
        is_valid, error = self.validator.validate_path(current_path, root_path)
        if not is_valid:
            self._stats.security_violations += 1
            self.logger.error(
                f"Security violation: {error}",
                extra={"path": str(current_path)}
            )
            return
        
        try:
            entries = list(current_path.iterdir())
        except PermissionError:
            self.logger.warning(
                f"Permission denied: {current_path}",
                extra={"path": str(current_path)}
            )
            return
        except Exception as e:
            self.logger.error(
                f"Error accessing directory: {e}",
                extra={"path": str(current_path)}
            )
            return
        
        for entry in entries:
            # Validate each entry
            is_valid, error = self.validator.validate_path(entry, root_path)
            if not is_valid:
                self._stats.security_violations += 1
                self.logger.warning(f"Skipping invalid path: {error}")
                continue
            
            # Handle symlinks
            if entry.is_symlink():
                if not follow_symlinks:
                    continue
                
                # Extra validation for symlinks
                try:
                    target = entry.resolve()
                    is_valid, error = self.validator.validate_path(target, root_path)
                    if not is_valid:
                        self._stats.security_violations += 1
                        self.logger.warning(
                            f"Skipping unsafe symlink: {entry} -> {target}"
                        )
                        continue
                except Exception:
                    continue
            
            # Check exclusions
            if self._should_exclude(entry, exclude_patterns):
                self._stats.excluded_files += 1
                continue
            
            # Process files
            if entry.is_file():
                # Additional file validation
                if not self._is_safe_file(entry):
                    self._stats.invalid_files += 1
                    continue
                
                if self._matches_patterns(entry, patterns):
                    if self._is_valid_file(entry):
                        self._stats.total_files += 1
                        if stat := self._safe_stat(entry):
                            self._stats.total_size_bytes += stat.st_size
                        yield entry
                    else:
                        self._stats.invalid_files += 1
            
            # Process directories
            elif entry.is_dir() and recursive:
                yield from self._discover_files_secure(
                    entry,
                    root_path,
                    patterns,
                    exclude_patterns,
                    recursive,
                    follow_symlinks,
                    max_depth,
                    current_depth + 1
                )
    
    def _is_safe_file(self, path: Path) -> bool:
        """Additional file safety checks."""
        # Check extension whitelist if strict mode
        if hasattr(self.settings, 'strict_file_validation'):
            if self.settings.strict_file_validation:
                if path.suffix.lower() not in self.allowed_extensions:
                    return False
        
        # Check for suspicious file names
        suspicious_patterns = [
            'passwd', 'shadow', '.ssh', '.aws', '.git/config',
            'id_rsa', 'credentials', '.env', 'config.php'
        ]
        
        name_lower = path.name.lower()
        for pattern in suspicious_patterns:
            if pattern in name_lower:
                self.logger.warning(
                    f"Suspicious file name detected: {path.name}"
                )
                return False
        
        return True
    
    def _matches_patterns(self, path: Path, patterns: list[str]) -> bool:
        """Safely check if file matches patterns."""
        name = path.name
        
        for pattern in patterns:
            # Use fnmatch for safe pattern matching
            try:
                if fnmatch.fnmatch(name, pattern):
                    return True
                if fnmatch.fnmatch(name.lower(), pattern.lower()):
                    return True
            except Exception as e:
                self.logger.error(
                    f"Pattern matching error: {e}",
                    extra={"pattern": pattern, "file": name}
                )
        
        return False
    
    def _should_exclude(self, path: Path, exclude_patterns: list[str]) -> bool:
        """Safely check if path should be excluded."""
        path_str = str(path)
        
        for pattern in exclude_patterns:
            try:
                if fnmatch.fnmatch(path_str, pattern):
                    return True
                
                # Check path components
                for part in path.parts:
                    if fnmatch.fnmatch(part, pattern):
                        return True
            except Exception:
                continue
        
        return False
    
    def _is_valid_file(self, path: Path) -> bool:
        """Validate file for analysis."""
        # Size check
        if stat := self._safe_stat(path):
            max_size = self.settings.max_file_size_bytes
            if stat.st_size > max_size:
                self.logger.warning(
                    f"File too large: {path} ({stat.st_size} bytes)"
                )
                return False
        
        # Readability check
        if not os.access(path, os.R_OK):
            return False
        
        # Text file check
        return self._is_text_file(path)
    
    def _safe_stat(self, path: Path) -> os.stat_result | None:
        """Safely get file stats."""
        try:
            return path.stat()
        except Exception:
            return None
    
    def _is_text_file(self, path: Path) -> bool:
        """Check if file is a text file."""
        try:
            # Read limited bytes to check
            with open(path, 'rb') as f:
                chunk = f.read(512)  # Reduced from 1024
                
                # Check for null bytes
                if b'\x00' in chunk:
                    return False
                
                # Try UTF-8 decode
                try:
                    chunk.decode('utf-8')
                    return True
                except UnicodeDecodeError:
                    # Try other encodings
                    for encoding in ['latin-1', 'cp1252']:
                        try:
                            chunk.decode(encoding)
                            return True
                        except UnicodeDecodeError:
                            continue
            
            return False
        except Exception:
            return False
