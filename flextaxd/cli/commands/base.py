"""Base class for CLI commands."""

import argparse
from abc import ABC, abstractmethod
from typing import Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import _SubParsersAction

from ...utils.logging_config import get_logger


class BaseCommand(ABC):
    """Abstract base class for all CLI commands."""
    
    def __init__(self) -> None:
        self.logger = get_logger(self.__class__.__name__.lower())
    
    @classmethod
    @abstractmethod
    def register_parser(cls, subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> argparse.ArgumentParser:
        """Register this command's argument parser."""
        pass
    
    @abstractmethod
    def execute(self, args: argparse.Namespace) -> Optional[int]:
        """Execute the command with parsed arguments."""
        pass
    
    def _validate_database_path(self, database_path: str, must_exist: bool = True) -> None:
        """Validate database path argument."""
        from pathlib import Path
        from ...core.exceptions import ValidationError
        
        path = Path(database_path)
        
        if must_exist and not path.exists():
            raise ValidationError(f"Database file does not exist: {database_path}")
        
        if must_exist and not path.is_file():
            raise ValidationError(f"Database path is not a file: {database_path}")
        
        if not must_exist:
            # Ensure parent directory exists for new database
            path.parent.mkdir(parents=True, exist_ok=True)
    
    def _validate_input_file(self, file_path: str) -> None:
        """Validate input file path."""
        from pathlib import Path
        from ...core.exceptions import ValidationError
        
        path = Path(file_path)
        
        if not path.exists():
            raise ValidationError(f"Input file does not exist: {file_path}")
        
        if not path.is_file():
            raise ValidationError(f"Input path is not a file: {file_path}")
        
        if path.stat().st_size == 0:
            raise ValidationError(f"Input file is empty: {file_path}")
    
    def _validate_output_directory(self, output_path: str, create: bool = True) -> None:
        """Validate output directory path."""
        from pathlib import Path
        from ...core.exceptions import ValidationError
        
        path = Path(output_path)
        
        if path.exists() and not path.is_dir():
            raise ValidationError(f"Output path exists but is not a directory: {output_path}")
        
        if create and not path.exists():
            try:
                path.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                raise ValidationError(f"Cannot create output directory {output_path}: {e}")