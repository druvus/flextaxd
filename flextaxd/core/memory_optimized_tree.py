"""Memory-optimized taxonomy tree implementations with lazy loading and streaming."""

from __future__ import annotations
from typing import Optional, Dict, Set, List, Iterator, Any, Protocol, Callable
from dataclasses import dataclass
from functools import lru_cache
from weakref import WeakValueDictionary
import threading
from abc import ABC, abstractmethod

from .models import TaxonomyNode, TaxonomicRank, GenomeInfo
from .exceptions import ValidationError


class NodeProvider(Protocol):
    """Protocol for providing nodes lazily from storage."""
    
    def get_node(self, tax_id: int) -> Optional[TaxonomyNode]:
        """Get a node by ID."""
        ...
    
    def get_children_ids(self, tax_id: int) -> Set[int]:
        """Get direct children IDs of a node."""
        ...
    
    def get_parent_id(self, tax_id: int) -> Optional[int]:
        """Get parent ID of a node."""
        ...
    
    def node_exists(self, tax_id: int) -> bool:
        """Check if node exists."""
        ...
    
    def get_all_node_ids(self) -> Set[int]:
        """Get all node IDs (for iteration)."""
        ...


@dataclass
class NodeCacheEntry:
    """Cache entry for a taxonomy node with metadata."""
    node: TaxonomyNode
    children: Optional[Set[int]] = None
    last_accessed: float = 0.0
    access_count: int = 0


class LazyTaxonomyTree:
    """Memory-optimized taxonomy tree with lazy loading and LRU cache."""
    
    def __init__(self, node_provider: NodeProvider, cache_size: int = 1000):
        """Initialize lazy tree with node provider and cache size."""
        self.node_provider = node_provider
        self.cache_size = cache_size
        
        # Thread-safe cache with weak references for automatic cleanup
        self._node_cache: Dict[int, NodeCacheEntry] = {}
        self._children_cache: Dict[int, Set[int]] = {}
        self._cache_lock = threading.RLock()
        
        # Statistics
        self._cache_hits = 0
        self._cache_misses = 0
        self._nodes_loaded = 0
        
        # Root node cache
        self._root_id: Optional[int] = None
        self._root_cached = False
    
    @property
    def cache_hit_rate(self) -> float:
        """Get cache hit rate as percentage."""
        total = self._cache_hits + self._cache_misses
        return (self._cache_hits / total * 100) if total > 0 else 0.0
    
    @property
    def memory_stats(self) -> Dict[str, Any]:
        """Get memory usage statistics."""
        return {
            'cached_nodes': len(self._node_cache),
            'cache_size_limit': self.cache_size,
            'cache_hit_rate': self.cache_hit_rate,
            'nodes_loaded': self._nodes_loaded,
            'memory_efficiency': len(self._node_cache) / max(1, self._nodes_loaded)
        }
    
    def _evict_cache_entries(self) -> None:
        """Evict least recently used cache entries if over limit."""
        while len(self._node_cache) > self.cache_size:
            # Sort by last accessed time and evict oldest
            sorted_entries = sorted(
                self._node_cache.items(),
                key=lambda x: (x[1].last_accessed, x[1].access_count)
            )
            
            # Remove the oldest entry
            if sorted_entries:
                tax_id, _ = sorted_entries[0]
                del self._node_cache[tax_id]
                if tax_id in self._children_cache:
                    del self._children_cache[tax_id]
    
    def get_node(self, tax_id: int) -> Optional[TaxonomyNode]:
        """Get node with caching and lazy loading."""
        import time
        
        with self._cache_lock:
            # Check cache first
            if tax_id in self._node_cache:
                entry = self._node_cache[tax_id]
                entry.last_accessed = time.time()
                entry.access_count += 1
                self._cache_hits += 1
                return entry.node
            
            # Cache miss - load from provider
            self._cache_misses += 1
            node = self.node_provider.get_node(tax_id)
            
            if node is not None:
                # Cache the node
                entry = NodeCacheEntry(
                    node=node,
                    last_accessed=time.time(),
                    access_count=1
                )
                self._node_cache[tax_id] = entry
                self._nodes_loaded += 1
                
                # Evict old entries if necessary
                self._evict_cache_entries()
            
            return node
    
    def get_children(self, tax_id: int) -> Set[int]:
        """Get children with caching."""
        with self._cache_lock:
            # Check cache first
            if tax_id in self._children_cache:
                self._cache_hits += 1
                return self._children_cache[tax_id].copy()
            
            # Load from provider
            self._cache_misses += 1
            children = self.node_provider.get_children_ids(tax_id)
            
            # Cache children
            self._children_cache[tax_id] = children.copy()
            
            return children
    
    def get_path_to_root(self, tax_id: int) -> List[TaxonomyNode]:
        """Get path to root with optimized caching."""
        path = []
        current_id: Optional[int] = tax_id
        visited = set()
        
        while current_id is not None:
            if current_id in visited:
                raise ValidationError(f"Circular reference detected at node {current_id}")
            visited.add(current_id)
            
            node = self.get_node(current_id)
            if node is None:
                break
            
            path.append(node)
            current_id = node.parent_id
        
        return path
    
    @property
    def root_id(self) -> Optional[int]:
        """Get root node ID with caching."""
        if not self._root_cached:
            # Find root by checking all nodes (expensive but cached)
            all_ids = self.node_provider.get_all_node_ids()
            for node_id in all_ids:
                parent_id = self.node_provider.get_parent_id(node_id)
                if parent_id is None:
                    self._root_id = node_id
                    break
            self._root_cached = True
        
        return self._root_id
    
    def lowest_common_ancestor(self, *tax_ids: int) -> Optional[TaxonomyNode]:
        """Optimized LCA with path caching."""
        if not tax_ids:
            return None
        
        if len(tax_ids) == 1:
            return self.get_node(tax_ids[0])
        
        # Get paths to root (cached)
        paths = []
        for tax_id in tax_ids:
            if not self.node_provider.node_exists(tax_id):
                return None
            path = self.get_path_to_root(tax_id)
            if not path:
                return None
            paths.append(path[::-1])  # Reverse for root-to-leaf
        
        # Find LCA efficiently
        min_length = min(len(path) for path in paths)
        lca_node = None
        
        for i in range(min_length):
            current_nodes = [path[i] for path in paths]
            if all(node.tax_id == current_nodes[0].tax_id for node in current_nodes):
                lca_node = current_nodes[0]
            else:
                break
        
        return lca_node
    
    def clear_cache(self) -> None:
        """Clear all caches."""
        with self._cache_lock:
            self._node_cache.clear()
            self._children_cache.clear()
            self._cache_hits = 0
            self._cache_misses = 0
            self._nodes_loaded = 0
            self._root_cached = False
            self._root_id = None
    
    def preload_subtree(self, root_tax_id: int, max_depth: int = 3) -> None:
        """Preload a subtree into cache for better performance."""
        def _preload_recursive(tax_id: int, current_depth: int) -> None:
            if current_depth > max_depth:
                return
            
            # Load node and children
            self.get_node(tax_id)
            children = self.get_children(tax_id)
            
            # Recursively preload children
            for child_id in children:
                _preload_recursive(child_id, current_depth + 1)
        
        _preload_recursive(root_tax_id, 0)


class StreamingTaxonomyTree:
    """Streaming taxonomy tree for memory-constrained environments."""
    
    def __init__(self, node_provider: NodeProvider):
        self.node_provider = node_provider
        self._visited_cache: Set[int] = set()
        self._current_path: List[int] = []
    
    def stream_subtree(self, root_tax_id: int) -> Iterator[TaxonomyNode]:
        """Stream nodes in a subtree depth-first."""
        self._visited_cache.clear()
        self._current_path.clear()
        
        yield from self._stream_recursive(root_tax_id)
    
    def _stream_recursive(self, tax_id: int) -> Iterator[TaxonomyNode]:
        """Recursively stream nodes."""
        if tax_id in self._visited_cache:
            return
        
        self._visited_cache.add(tax_id)
        self._current_path.append(tax_id)
        
        node = self.node_provider.get_node(tax_id)
        if node is not None:
            yield node
            
            # Stream children
            children = self.node_provider.get_children_ids(tax_id)
            for child_id in sorted(children):  # Deterministic order
                yield from self._stream_recursive(child_id)
        
        self._current_path.pop()
    
    def stream_by_rank(self, rank: TaxonomicRank) -> Iterator[TaxonomyNode]:
        """Stream all nodes of a specific rank."""
        all_ids = self.node_provider.get_all_node_ids()
        
        for tax_id in all_ids:
            node = self.node_provider.get_node(tax_id)
            if node and node.rank == rank:
                yield node
    
    def stream_leaves(self) -> Iterator[TaxonomyNode]:
        """Stream all leaf nodes (nodes with no children)."""
        all_ids = self.node_provider.get_all_node_ids()
        
        for tax_id in all_ids:
            children = self.node_provider.get_children_ids(tax_id)
            if not children:  # Leaf node
                node = self.node_provider.get_node(tax_id)
                if node:
                    yield node
    
    def estimate_memory_usage(self, max_concurrent_nodes: int = 100) -> Dict[str, int]:
        """Estimate memory usage for streaming operations."""
        import sys
        
        sample_node = self.node_provider.get_node(next(iter(self.node_provider.get_all_node_ids())))
        if sample_node is None:
            return {'estimated_bytes': 0, 'max_concurrent_nodes': 0}
        
        node_size = sys.getsizeof(sample_node)
        cache_overhead = sys.getsizeof(set()) + sys.getsizeof(list())
        
        return {
            'estimated_bytes': (node_size * max_concurrent_nodes) + cache_overhead,
            'max_concurrent_nodes': max_concurrent_nodes,
            'node_size_bytes': node_size
        }


class MemoryEfficientNodeProvider:
    """Memory-efficient node provider with database-backed storage."""
    
    def __init__(self, database_path: str):
        self.database_path = database_path
        self._connection_cache: Optional[Any] = None
        self._schema_cache: Dict[str, Any] = {}
    
    def _get_connection(self) -> Any:
        """Get database connection with lazy initialization."""
        if self._connection_cache is None:
            import sqlite3
            self._connection_cache = sqlite3.connect(self.database_path, check_same_thread=False)
            self._connection_cache.row_factory = sqlite3.Row
        return self._connection_cache
    
    @lru_cache(maxsize=500)
    def get_node(self, tax_id: int) -> Optional[TaxonomyNode]:
        """Get node from database with LRU cache."""
        conn = self._get_connection()
        cursor = conn.execute("""
            SELECT tax_id, name, rank, parent_id 
            FROM nodes 
            WHERE tax_id = ?
        """, (tax_id,))
        
        row = cursor.fetchone()
        if row is None:
            return None
        
        try:
            rank = TaxonomicRank(row['rank']) if row['rank'] else TaxonomicRank.CUSTOM
        except ValueError:
            rank = TaxonomicRank.CUSTOM
        
        return TaxonomyNode(
            tax_id=row['tax_id'],
            name=row['name'] or f"taxid_{tax_id}",
            rank=rank,
            parent_id=row['parent_id'] if row['parent_id'] != row['tax_id'] else None
        )
    
    @lru_cache(maxsize=200)
    def get_children_ids(self, tax_id: int) -> Set[int]:
        """Get children IDs from database with LRU cache."""
        conn = self._get_connection()
        cursor = conn.execute("""
            SELECT tax_id 
            FROM nodes 
            WHERE parent_id = ? AND parent_id != tax_id
        """, (tax_id,))
        
        return {row['tax_id'] for row in cursor.fetchall()}
    
    @lru_cache(maxsize=200)
    def get_parent_id(self, tax_id: int) -> Optional[int]:
        """Get parent ID from database with LRU cache."""
        conn = self._get_connection()
        cursor = conn.execute("""
            SELECT parent_id 
            FROM nodes 
            WHERE tax_id = ?
        """, (tax_id,))
        
        row = cursor.fetchone()
        if row and row['parent_id'] != tax_id:
            return int(row['parent_id'])
        return None
    
    @lru_cache(maxsize=1)
    def node_exists(self, tax_id: int) -> bool:
        """Check if node exists in database."""
        conn = self._get_connection()
        cursor = conn.execute("SELECT 1 FROM nodes WHERE tax_id = ?", (tax_id,))
        return cursor.fetchone() is not None
    
    @lru_cache(maxsize=1)
    def get_all_node_ids(self) -> Set[int]:
        """Get all node IDs from database (cached for iteration)."""
        conn = self._get_connection()
        cursor = conn.execute("SELECT tax_id FROM nodes")
        return {row['tax_id'] for row in cursor.fetchall()}
    
    def clear_cache(self) -> None:
        """Clear all LRU caches."""
        self.get_node.cache_clear()
        self.get_children_ids.cache_clear()
        self.get_parent_id.cache_clear()
        self.node_exists.cache_clear()
        self.get_all_node_ids.cache_clear()
    
    def cache_info(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            'get_node': self.get_node.cache_info(),
            'get_children_ids': self.get_children_ids.cache_info(),
            'get_parent_id': self.get_parent_id.cache_info(),
            'node_exists': self.node_exists.cache_info(),
            'get_all_node_ids': self.get_all_node_ids.cache_info()
        }
    
    def __del__(self) -> None:
        """Clean up database connection."""
        if self._connection_cache:
            self._connection_cache.close()


class MemoryOptimizedOperations:
    """Memory-optimized tree operations for large taxonomies."""
    
    def __init__(self, lazy_tree: LazyTaxonomyTree):
        self.tree = lazy_tree
    
    def batch_lca(self, node_pairs: List[tuple[int, int]], batch_size: int = 50) -> Iterator[tuple[tuple[int, int], Optional[TaxonomyNode]]]:
        """Compute LCA for multiple node pairs in memory-efficient batches."""
        for i in range(0, len(node_pairs), batch_size):
            batch = node_pairs[i:i + batch_size]
            
            # Process batch
            for pair in batch:
                lca = self.tree.lowest_common_ancestor(*pair)
                yield (pair, lca)
            
            # Optional: clear cache between batches for very large datasets
            if len(self.tree._node_cache) > self.tree.cache_size * 1.5:
                self.tree._evict_cache_entries()
    
    def streaming_distance_matrix(self, tax_ids: List[int]) -> Iterator[tuple[int, int, Optional[int]]]:
        """Compute distance matrix in streaming fashion."""
        for i, tax_id1 in enumerate(tax_ids):
            for tax_id2 in tax_ids[i+1:]:
                # Compute distance
                lca = self.tree.lowest_common_ancestor(tax_id1, tax_id2)
                if lca is None:
                    distance = None
                else:
                    path1 = self.tree.get_path_to_root(tax_id1)
                    path2 = self.tree.get_path_to_root(tax_id2)
                    
                    lca_pos1 = next((i for i, node in enumerate(path1) if node.tax_id == lca.tax_id), None)
                    lca_pos2 = next((i for i, node in enumerate(path2) if node.tax_id == lca.tax_id), None)
                    
                    distance = (lca_pos1 + lca_pos2) if lca_pos1 is not None and lca_pos2 is not None else None
                
                yield (tax_id1, tax_id2, distance)
    
    def memory_efficient_subtree_stats(self, root_tax_id: int) -> Dict[str, Any]:
        """Compute subtree statistics without loading entire subtree."""
        stats: Dict[str, Any] = {
            'node_count': 0,
            'max_depth': 0,
            'rank_distribution': {},
            'leaf_count': 0
        }
        
        def _count_recursive(tax_id: int, depth: int) -> None:
            node = self.tree.get_node(tax_id)
            if node is None:
                return
            
            stats['node_count'] += 1
            stats['max_depth'] = max(stats['max_depth'], depth)
            
            rank_name = node.rank.value
            rank_dist = stats['rank_distribution']
            rank_dist[rank_name] = rank_dist.get(rank_name, 0) + 1
            
            children = self.tree.get_children(tax_id)
            if not children:
                stats['leaf_count'] += 1
            else:
                for child_id in children:
                    _count_recursive(child_id, depth + 1)
        
        _count_recursive(root_tax_id, 0)
        return stats


# Example usage and factory functions
def create_memory_optimized_tree(database_path: str, cache_size: int = 1000) -> LazyTaxonomyTree:
    """Factory function to create memory-optimized tree."""
    provider = MemoryEfficientNodeProvider(database_path)
    return LazyTaxonomyTree(provider, cache_size)


def create_streaming_tree(database_path: str) -> StreamingTaxonomyTree:
    """Factory function to create streaming tree."""
    provider = MemoryEfficientNodeProvider(database_path)
    return StreamingTaxonomyTree(provider)