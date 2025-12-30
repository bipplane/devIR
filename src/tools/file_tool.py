"""
File Reader Tool

Provides safe file reading capabilities for the agent to audit code.
Includes safety checks to prevent reading sensitive files.
"""

import os
from pathlib import Path
from typing import List, Optional, Set
from dataclasses import dataclass


@dataclass
class FileContent:
    """Represents the content of a read file."""
    path: str
    content: str
    language: str
    line_count: int


class FileReaderTool:
    """
    Safe file reading tool for code auditing.
    
    Features:
    - Configurable base directory (sandboxing)
    - Extension filtering (only read code files)
    - Sensitive file protection (.env, secrets, etc.)
    - Line limiting to prevent huge file reads
    """
    
    # File extensions we consider safe to read
    ALLOWED_EXTENSIONS: Set[str] = {
        ".py", ".js", ".ts", ".jsx", ".tsx",  # Scripts
        ".java", ".go", ".rs", ".cpp", ".c", ".h",  # Compiled languages
        ".yaml", ".yml", ".json", ".toml",  # Config
        ".md", ".txt", ".rst",  # Documentation
        ".html", ".css", ".scss",  # Web
        ".sql",  # Database
        ".sh", ".bash", ".zsh",  # Shell scripts
        ".dockerfile", ".containerfile",  # Container
    }
    
    # Files we should never read (security)
    BLOCKED_PATTERNS: Set[str] = {
        ".env", ".env.local", ".env.production",
        "secrets", "credentials", "password",
        ".pem", ".key", ".crt", ".pfx",
        "id_rsa", "id_ed25519",
        ".aws/credentials",
    }
    
    def __init__(
        self,
        base_directory: Optional[str] = None,
        max_lines: int = 500,
        allowed_extensions: Optional[Set[str]] = None
    ):
        """
        Initialise the file reader tool.
        
        Args:
            base_directory: Root directory for all file operations (sandbox)
            max_lines: Maximum lines to read from any single file
            allowed_extensions: Override default allowed extensions
        """
        self.base_directory = Path(base_directory) if base_directory else Path.cwd()
        self.max_lines = max_lines
        self.allowed_extensions = allowed_extensions or self.ALLOWED_EXTENSIONS
        
    def _is_safe_path(self, file_path: Path) -> bool:
        """
        Check if a file path is safe to read.
        
        Args:
            file_path: Path to validate
            
        Returns:
            True if safe, False if blocked
        """
        # Resolve to absolute path
        try:
            resolved = file_path.resolve()
        except (OSError, ValueError):
            return False
            
        # Check if within base directory (prevent directory traversal)
        try:
            resolved.relative_to(self.base_directory.resolve())
        except ValueError:
            return False
            
        # Check against blocked patterns
        path_str = str(resolved).lower()
        for blocked in self.BLOCKED_PATTERNS:
            if blocked.lower() in path_str:
                return False
                
        return True
    
    def _detect_language(self, file_path: Path) -> str:
        """Detect programming language from file extension."""
        ext_to_lang = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".jsx": "javascript",
            ".tsx": "typescript",
            ".java": "java",
            ".go": "go",
            ".rs": "rust",
            ".cpp": "cpp",
            ".c": "c",
            ".h": "c",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".json": "json",
            ".toml": "toml",
            ".md": "markdown",
            ".html": "html",
            ".css": "css",
            ".sql": "sql",
            ".sh": "bash",
            ".dockerfile": "dockerfile",
        }
        return ext_to_lang.get(file_path.suffix.lower(), "text")
    
    def read_file(self, file_path: str) -> FileContent:
        """
        Read a file and return its content.
        
        Args:
            file_path: Path to the file (relative to base_directory or absolute)
            
        Returns:
            FileContent object with the file's content
            
        Raises:
            ValueError: If the file is blocked or outside sandbox
            FileNotFoundError: If the file doesn't exist
        """
        path = Path(file_path)
        
        # Handle relative paths
        if not path.is_absolute():
            path = self.base_directory / path
            
        # Security check
        if not self._is_safe_path(path):
            raise ValueError(f"Access denied: {file_path} is blocked for security reasons")
            
        # Check extension
        if path.suffix.lower() not in self.allowed_extensions:
            raise ValueError(f"File type not allowed: {path.suffix}")
            
        # Read file with line limit
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
            
        lines = []
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for i, line in enumerate(f):
                    if i >= self.max_lines:
                        lines.append(f"\n... [Truncated at {self.max_lines} lines] ...")
                        break
                    lines.append(line)
        except Exception as e:
            raise IOError(f"Error reading file: {e}")
            
        content = "".join(lines)
        
        return FileContent(
            path=str(path),
            content=content,
            language=self._detect_language(path),
            line_count=len(lines)
        )
    
    def find_files(
        self,
        patterns: List[str],
        exclude_dirs: Optional[List[str]] = None
    ) -> List[str]:
        """
        Find files matching given patterns.
        
        Args:
            patterns: List of glob patterns (e.g., ["*.py", "docker-compose*.yml"])
            exclude_dirs: Directories to skip (e.g., ["node_modules", ".git"])
            
        Returns:
            List of matching file paths
        """
        excluded_set = set(exclude_dirs or ["node_modules", ".git", "__pycache__", "venv", ".venv"])
        matches = []
        
        for pattern in patterns:
            for match in self.base_directory.rglob(pattern):
                # Skip excluded directories
                if any(excluded in match.parts for excluded in excluded_set):
                    continue
                    
                # Only include safe files
                if self._is_safe_path(match) and match.is_file():
                    matches.append(str(match.relative_to(self.base_directory)))
                    
        return sorted(set(matches))
    
    def read_multiple(self, file_paths: List[str]) -> List[FileContent]:
        """
        Read multiple files and return their contents.
        
        Args:
            file_paths: List of file paths to read
            
        Returns:
            List of FileContent objects (skips files that can't be read)
        """
        results = []
        for path in file_paths:
            try:
                content = self.read_file(path)
                results.append(content)
            except (ValueError, FileNotFoundError, IOError) as e:
                # Log but continue with other files
                print(f"Warning: Could not read {path}: {e}")
                
        return results
    
    def format_file_content(self, file_content: FileContent) -> str:
        """
        Format file content for LLM consumption.
        
        Args:
            file_content: FileContent object to format
            
        Returns:
            Formatted string with file path and content
        """
        return f"""
--- File: {file_content.path} ---
Language: {file_content.language}
Lines: {file_content.line_count}

```{file_content.language}
{file_content.content}
```
"""
