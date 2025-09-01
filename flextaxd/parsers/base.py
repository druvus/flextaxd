"""Base classes and interfaces for taxonomy parsers."""

import logging
from abc import ABC, abstractmethod
from typing import Iterator, Optional, Dict, Any
from pathlib import Path

from ..core.models import TaxonomyTree, TaxonomyNode, GenomeInfo
from ..core.exceptions import ParseError


class TaxonomyParser(ABC):
    """Abstract base class for all taxonomy parsers."""
    
    def __init__(self, **kwargs: Any):
        """Initialize the parser with configuration options."""
        self.config = kwargs
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    def can_parse(self, file_path: Path) -> bool:
        """Check if this parser can handle the given file."""
        pass
    
    @abstractmethod
    def parse(self, file_path: Path, **kwargs: Any) -> TaxonomyTree:
        """Parse a taxonomy file and return a TaxonomyTree."""
        pass
    
    @property
    @abstractmethod
    def supported_extensions(self) -> list[str]:
        """List of file extensions this parser supports."""
        pass
    
    @property
    @abstractmethod
    def parser_name(self) -> str:
        """Human-readable name of this parser."""
        pass
    
    def _validate_file(self, file_path: Path) -> None:
        """Validate that the file exists and is readable."""
        if not file_path.exists():
            raise ParseError(f"File does not exist: {file_path}")
        
        if not file_path.is_file():
            raise ParseError(f"Path is not a file: {file_path}")
        
        if not file_path.stat().st_size > 0:
            raise ParseError(f"File is empty: {file_path}")
        
        try:
            with open(file_path, 'r') as f:
                # Try to read the first line to check accessibility
                f.readline()
        except (IOError, OSError, PermissionError) as e:
            raise ParseError(f"Cannot read file {file_path}: {e}")
    
    def _parse_header(self, first_line: str) -> Optional[Dict[str, int]]:
        """Parse header line to determine column positions."""
        # This is a common pattern across multiple parsers
        if not first_line.strip():
            return None
            
        columns = [col.strip() for col in first_line.strip().split('\t')]
        return {col.lower(): idx for idx, col in enumerate(columns)}


class FileBasedParser(TaxonomyParser):
    """Base class for parsers that work with single files."""
    
    def _read_lines(self, file_path: Path) -> Iterator[str]:
        """Safely read lines from a file with proper error handling."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                line_num = 0
                for line in f:
                    line_num += 1
                    try:
                        yield line.rstrip('\n\r')
                    except UnicodeDecodeError as e:
                        raise ParseError(
                            f"Unicode decode error at line {line_num} in {file_path}: {e}"
                        )
        except (IOError, OSError) as e:
            raise ParseError(f"Error reading file {file_path}: {e}")


class DirectoryBasedParser(TaxonomyParser):
    """Base class for parsers that work with directory structures."""
    
    def _find_files_with_pattern(self, directory: Path, pattern: str) -> list[Path]:
        """Find files matching a pattern in a directory."""
        if not directory.is_dir():
            raise ParseError(f"Path is not a directory: {directory}")
        
        try:
            return list(directory.glob(pattern))
        except (OSError, PermissionError) as e:
            raise ParseError(f"Cannot access directory {directory}: {e}")