"""Base classes and interfaces for taxonomy exporters."""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Callable
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import concurrent.futures
import logging

from ..core.models import TaxonomyTree
from ..core.exceptions import ExportError

logger = logging.getLogger(__name__)


class TaxonomyExporter(ABC):
    """Abstract base class for all taxonomy exporters."""

    def __init__(self, max_workers: int = 4, **kwargs: Any):
        """Initialize the exporter with configuration options."""
        self.config = kwargs
        self.max_workers = max_workers

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

    def _process_parallel_tasks(self, tasks: List[Callable], task_description: str = "export tasks") -> List[Any]:
        """Process multiple export tasks in parallel."""
        if len(tasks) <= 1 or self.max_workers == 1:
            # Use sequential processing for single tasks or when parallel processing is disabled
            logger.debug(f"Using sequential processing for {len(tasks)} {task_description}")
            return [task() for task in tasks]
        
        logger.debug(f"Using parallel processing for {len(tasks)} {task_description} with {self.max_workers} workers")
        
        results = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_task = {executor.submit(task): i for i, task in enumerate(tasks)}
            
            for future in concurrent.futures.as_completed(future_to_task):
                task_idx = future_to_task[future]
                try:
                    result = future.result()
                    results.append((task_idx, result))
                    logger.debug(f"Completed {task_description} {task_idx}")
                except Exception as e:
                    logger.error(f"Error in {task_description} {task_idx}: {e}")
                    raise ExportError(f"Failed to complete {task_description}: {e}")
        
        # Sort results by task index to maintain order
        results.sort(key=lambda x: x[0])
        return [result for _, result in results]

    def _write_files_parallel(self, file_writers: Dict[Path, Callable]) -> None:
        """Write multiple files in parallel."""
        if len(file_writers) <= 1 or self.max_workers == 1:
            # Sequential processing
            logger.debug(f"Writing {len(file_writers)} files sequentially")
            for file_path, writer_func in file_writers.items():
                writer_func()
                logger.debug(f"Wrote file: {file_path}")
            return
            
        logger.debug(f"Writing {len(file_writers)} files in parallel with {self.max_workers} workers")
        
        # Create tasks for parallel execution
        tasks = []
        file_paths = []
        for file_path, writer_func in file_writers.items():
            tasks.append(writer_func)
            file_paths.append(file_path)
        
        # Execute file writing tasks in parallel
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_path = {executor.submit(task): file_paths[i] for i, task in enumerate(tasks)}
            
            for future in concurrent.futures.as_completed(future_to_path):
                file_path = future_to_path[future]
                try:
                    future.result()
                    logger.debug(f"Successfully wrote file: {file_path}")
                except Exception as e:
                    logger.error(f"Error writing file {file_path}: {e}")
                    raise ExportError(f"Failed to write file {file_path}: {e}")

    def _process_tree_chunks(self, tree: TaxonomyTree, chunk_processor: Callable, 
                           chunk_size: int = 1000, description: str = "tree nodes") -> List[Any]:
        """Process tree nodes in parallel chunks."""
        nodes = list(tree)
        
        if len(nodes) < 5000 or self.max_workers == 1:
            # Use sequential processing for smaller trees
            logger.debug(f"Processing {len(nodes)} {description} sequentially")
            return chunk_processor(nodes, 0)
        
        logger.debug(f"Processing {len(nodes)} {description} in parallel chunks with {self.max_workers} workers")
        
        # Split nodes into chunks
        chunks = [nodes[i:i + chunk_size] for i in range(0, len(nodes), chunk_size)]
        
        all_results = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_chunk = {
                executor.submit(chunk_processor, chunk, i): i 
                for i, chunk in enumerate(chunks)
            }
            
            for future in concurrent.futures.as_completed(future_to_chunk):
                chunk_idx = future_to_chunk[future]
                try:
                    chunk_results = future.result()
                    all_results.extend(chunk_results)
                    logger.debug(f"Processed {description} chunk {chunk_idx} with {len(chunk_results)} items")
                except Exception as e:
                    logger.error(f"Error processing {description} chunk {chunk_idx}: {e}")
                    raise ExportError(f"Failed to process {description} chunk: {e}")
        
        return all_results

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
