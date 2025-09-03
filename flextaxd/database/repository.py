"""Abstract repository interface for taxonomy data persistence."""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, Iterator, Generator
from contextlib import contextmanager

from ..core.models import TaxonomyTree, TaxonomyNode, GenomeInfo
from ..core.exceptions import DatabaseError


class TaxonomyRepository(ABC):
    """Abstract base class for taxonomy data repositories."""

    @abstractmethod
    def save_tree(self, tree: TaxonomyTree) -> None:
        """Save a complete taxonomy tree to storage."""
        pass

    @abstractmethod
    def load_tree(self) -> TaxonomyTree:
        """Load the complete taxonomy tree from storage."""
        pass

    @abstractmethod
    def get_node(self, tax_id: int) -> Optional[TaxonomyNode]:
        """Get a single node by its taxonomic ID."""
        pass

    @abstractmethod
    def add_node(self, node: TaxonomyNode) -> None:
        """Add a new node to the repository."""
        pass

    @abstractmethod
    def update_node(self, node: TaxonomyNode) -> None:
        """Update an existing node in the repository."""
        pass

    @abstractmethod
    def delete_node(self, tax_id: int) -> None:
        """Delete a node from the repository."""
        pass

    @abstractmethod
    def get_children(self, tax_id: int) -> List[TaxonomyNode]:
        """Get all direct children of a node."""
        pass

    @abstractmethod
    def get_descendants(self, tax_id: int) -> List[TaxonomyNode]:
        """Get all descendants of a node."""
        pass

    @abstractmethod
    def get_path_to_root(self, tax_id: int) -> List[TaxonomyNode]:
        """Get the path from a node to the root."""
        pass

    @abstractmethod
    def add_genome(self, genome: GenomeInfo) -> None:
        """Add genome information to the repository."""
        pass

    @abstractmethod
    def get_genomes_for_node(self, tax_id: int) -> List[GenomeInfo]:
        """Get all genomes associated with a taxonomic node."""
        pass

    @abstractmethod
    def get_statistics(self) -> Dict[str, Any]:
        """Get repository statistics."""
        pass

    @abstractmethod
    def initialize(self) -> None:
        """Initialize the repository (create tables, etc.)."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Close the repository and clean up resources."""
        pass

    @contextmanager
    @abstractmethod
    def transaction(self) -> Generator[Any, None, None]:
        """Context manager for database transactions."""
        pass

    def __enter__(self) -> "TaxonomyRepository":
        """Enter context manager."""
        return self

    def __exit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[Exception],
        exc_tb: Optional[Any],
    ) -> None:
        """Exit context manager."""
        self.close()
