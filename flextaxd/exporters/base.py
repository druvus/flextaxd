"""Base classes and interfaces for taxonomy exporters."""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from pathlib import Path

from ..core.models import TaxonomyTree
from ..core.exceptions import ExportError


class TaxonomyExporter(ABC):
    """Abstract base class for all taxonomy exporters."""

    def __init__(self, **kwargs: Any):
        """Initialize the exporter with configuration options."""
        self.config = kwargs

    @abstractmethod
    def export(self, tree: TaxonomyTree, output_path: Path, **kwargs: Any) -> None:
        """Export a taxonomy tree to the specified output path."""
        pass

    @property
    @abstractmethod
    def exporter_name(self) -> str:
        """Human-readable name of this exporter."""
        pass

    @property
    @abstractmethod
    def file_extensions(self) -> list[str]:
        """List of file extensions this exporter produces."""
        pass

    @property
    @abstractmethod
    def requires_directory(self) -> bool:
        """Whether this exporter requires a directory or single file output."""
        pass

    def _validate_tree(self, tree: TaxonomyTree) -> None:
        """Validate that the tree is suitable for export."""
        if tree.node_count == 0:
            raise ExportError("Cannot export empty taxonomy tree")

        issues = tree.validate_tree()
        if issues:
            raise ExportError(f"Tree validation failed: {'; '.join(issues)}")
    
    def _validate_file(self, file_path: Path) -> None:
        """Validate that a file path exists and is readable."""
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        if not file_path.is_file():
            raise ExportError(f"Path is not a file: {file_path}")
        
        if not file_path.stat().st_size >= 0:  # Check if we can read file stats
            raise ExportError(f"Cannot access file: {file_path}")

    def _ensure_output_path(
        self, output_path: Path, is_directory: Optional[bool] = None
    ) -> None:
        """Ensure output path exists and is appropriate type."""
        if is_directory is None:
            is_directory = self.requires_directory

        if is_directory:
            try:
                output_path.mkdir(parents=True, exist_ok=True)
            except FileExistsError:
                # File exists with same name - this is an error for directory creation
                if not output_path.is_dir():
                    raise ExportError(f"Cannot create directory - file exists: {output_path}")
            if not output_path.is_dir():
                raise ExportError(f"Output path is not a directory: {output_path}")
        else:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if output_path.exists() and output_path.is_dir():
                raise ExportError(
                    f"Output path is a directory, expected file: {output_path}"
                )


class FileBasedExporter(TaxonomyExporter):
    """Base class for exporters that produce single files."""

    @property
    def requires_directory(self) -> bool:
        return False


class DirectoryBasedExporter(TaxonomyExporter):
    """Base class for exporters that produce multiple files in a directory."""

    @property
    def requires_directory(self) -> bool:
        return True
