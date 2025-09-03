"""High-performance taxonomy tree optimized for NCBI-scale datasets (2M+ nodes)."""

from __future__ import annotations
import struct
import mmap
import threading
import multiprocessing as mp
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Set, List, Optional, Tuple, Iterator, Any, Protocol
from dataclasses import dataclass
from pathlib import Path
import sqlite3
import time
import numpy as np
from collections import defaultdict, deque
import heapq

from .models import TaxonomyNode, TaxonomicRank, GenomeInfo
from .exceptions import ValidationError


@dataclass
class CompressedNode:
    """Memory-optimized node representation using bit packing."""

    # Pack tax_id (32-bit), parent_id (32-bit), rank (8-bit) into 9 bytes
    # Name stored separately in string intern pool
    tax_id: int
    parent_id: Optional[int]
    rank_id: int  # Index into rank enum
    name_id: int  # Index into string intern pool

    def pack(self) -> bytes:
        """Pack node into 13 bytes: tax_id(4) + parent_id(4) + rank_id(1) + name_id(4)."""
        parent = self.parent_id if self.parent_id is not None else 0
        return struct.pack("<IIBI", self.tax_id, parent, self.rank_id, self.name_id)

    @classmethod
    def unpack(cls, data: bytes) -> CompressedNode:
        """Unpack node from bytes."""
        tax_id, parent_id, rank_id, name_id = struct.unpack("<IIBI", data)
        return cls(
            tax_id=tax_id,
            parent_id=parent_id if parent_id != 0 else None,
            rank_id=rank_id,
            name_id=name_id,
        )


class StringInternPool:
    """Memory-efficient string storage using interning."""

    def __init__(self) -> None:
        self._strings: List[str] = []
        self._string_to_id: Dict[str, int] = {}

    def intern(self, string: str) -> int:
        """Add string to pool and return ID."""
        if string in self._string_to_id:
            return self._string_to_id[string]

        string_id = len(self._strings)
        self._strings.append(string)
        self._string_to_id[string] = string_id
        return string_id

    def get_string(self, string_id: int) -> str:
        """Get string by ID."""
        return self._strings[string_id]

    def memory_usage(self) -> int:
        """Estimate memory usage in bytes."""
        return sum(len(s.encode("utf-8")) for s in self._strings)


class RangeMinimumQuery:
    """Sparse table for O(1) LCA queries on large trees."""

    def __init__(self, depths: List[int]):
        """Initialize RMQ structure."""
        n = len(depths)
        if n == 0:
            self.table: List[List[int]] = [[]]
            return

        # Build sparse table for range minimum queries
        k = 0
        while (1 << k) <= n:
            k += 1

        self.table = [[0] * n for _ in range(k)]
        self.depths = depths

        # Fill first row
        for i in range(n):
            self.table[0][i] = i

        # Fill remaining rows
        j = 1
        while (1 << j) <= n:
            i = 0
            while i + (1 << j) - 1 < n:
                left_idx = self.table[j - 1][i]
                right_idx = self.table[j - 1][i + (1 << (j - 1))]

                if depths[left_idx] <= depths[right_idx]:
                    self.table[j][i] = left_idx
                else:
                    self.table[j][i] = right_idx
                i += 1
            j += 1

    def query(self, left: int, right: int) -> int:
        """Get index of minimum element in range [left, right]."""
        if left > right or left < 0 or right >= len(self.depths):
            return -1

        length = right - left + 1
        k = 0
        while (1 << (k + 1)) <= length:
            k += 1

        left_idx = self.table[k][left]
        right_idx = self.table[k][right - (1 << k) + 1]

        if self.depths[left_idx] <= self.depths[right_idx]:
            return left_idx
        else:
            return right_idx


class HighPerformanceTaxonomyTree:
    """Ultra-high performance taxonomy tree for NCBI-scale datasets."""

    def __init__(
        self, db_path: Optional[str] = None, memory_map_size: int = 1024 * 1024 * 1024
    ):  # 1GB default
        """Initialize high-performance tree."""

        # Core data structures
        self.db_path = db_path
        self.memory_map_size = memory_map_size

        # Compressed storage
        self.string_pool = StringInternPool()
        self.rank_to_id = {rank: i for i, rank in enumerate(TaxonomicRank)}
        self.id_to_rank = {i: rank for rank, i in self.rank_to_id.items()}

        # Memory-mapped storage for massive datasets
        self._mmap_file: Optional[mmap.mmap] = None
        self._node_data: Optional[bytearray] = None

        # High-performance indexes
        self._nodes: Dict[int, CompressedNode] = {}  # In-memory for active nodes
        self._children_index: Dict[int, List[int]] = defaultdict(list)
        self._parent_index: Dict[int, int] = {}

        # LCA optimization structures
        self._euler_tour: List[int] = []
        self._first_occurrence: Dict[int, int] = {}
        self._depth_array: List[int] = []
        self._rmq: Optional[RangeMinimumQuery] = None
        self._lca_preprocessed = False

        # Multi-threading support
        self._lock = threading.RLock()
        self._thread_pool: Optional[ThreadPoolExecutor] = None

        # Statistics
        self._stats = {
            "nodes_loaded": 0,
            "lca_queries": 0,
            "cache_hits": 0,
            "db_queries": 0,
            "memory_usage_bytes": 0,
        }

        # Connection pool for database operations
        self._db_connections: Dict[int, sqlite3.Connection] = {}
        self._max_connections = min(32, mp.cpu_count() * 2)

    def __enter__(self) -> HighPerformanceTaxonomyTree:
        """Context manager entry."""
        self._thread_pool = ThreadPoolExecutor(max_workers=mp.cpu_count())
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        if self._thread_pool:
            self._thread_pool.shutdown()
        self._cleanup_connections()
        if self._mmap_file:
            self._mmap_file.close()

    def _get_db_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        thread_id = threading.get_ident()

        if thread_id not in self._db_connections:
            if len(self._db_connections) >= self._max_connections:
                # Remove oldest connection
                oldest_thread = next(iter(self._db_connections))
                self._db_connections[oldest_thread].close()
                del self._db_connections[oldest_thread]

            conn = sqlite3.connect(self.db_path or "", check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=10000")
            conn.execute("PRAGMA temp_store=MEMORY")
            self._db_connections[thread_id] = conn

        return self._db_connections[thread_id]

    def _cleanup_connections(self) -> None:
        """Close all database connections."""
        for conn in self._db_connections.values():
            conn.close()
        self._db_connections.clear()

    def load_from_database(self, batch_size: int = 10000) -> None:
        """Load tree from database with optimized bulk operations."""
        if not self.db_path:
            raise ValueError("Database path not provided")

        conn = self._get_db_connection()

        # Create optimized indexes if they don't exist
        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_parent_id ON nodes(parent_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rank ON nodes(rank)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_name ON nodes(name)")
            conn.commit()
        except sqlite3.Error:
            pass

        # Load nodes in batches for memory efficiency
        cursor = conn.execute(
            """
            SELECT tax_id, name, rank, parent_id 
            FROM nodes 
            ORDER BY tax_id
        """
        )

        batch = []
        total_loaded = 0

        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break

            batch.extend(rows)

            # Process batch
            if len(batch) >= batch_size:
                self._process_node_batch(batch)
                total_loaded += len(batch)
                batch.clear()

                if total_loaded % 100000 == 0:
                    print(f"Loaded {total_loaded:,} nodes...")

        # Process remaining nodes
        if batch:
            self._process_node_batch(batch)
            total_loaded += len(batch)

        print(f"Loaded {total_loaded:,} nodes total")

        # Preprocess for fast LCA queries
        self._preprocess_lca()
        self._stats["nodes_loaded"] = total_loaded

    def _process_node_batch(
        self, batch: List[Tuple[int, str, str, Optional[int]]]
    ) -> None:
        """Process a batch of nodes efficiently."""
        with self._lock:
            for tax_id, name, rank, parent_id in batch:
                # Intern strings
                name_id = self.string_pool.intern(name)

                # Convert rank
                try:
                    taxonomic_rank = (
                        TaxonomicRank(rank) if rank else TaxonomicRank.CUSTOM
                    )
                except ValueError:
                    taxonomic_rank = TaxonomicRank.CUSTOM
                rank_id = self.rank_to_id[taxonomic_rank]

                # Handle self-referencing root
                if parent_id == tax_id:
                    parent_id = None

                # Create compressed node
                node = CompressedNode(
                    tax_id=tax_id, parent_id=parent_id, rank_id=rank_id, name_id=name_id
                )

                self._nodes[tax_id] = node

                # Build indexes
                if parent_id is not None:
                    self._children_index[parent_id].append(tax_id)
                    self._parent_index[tax_id] = parent_id

    def _preprocess_lca(self) -> None:
        """Preprocess tree for O(1) LCA queries using RMQ."""
        if self._lca_preprocessed:
            return

        print("Preprocessing tree for fast LCA queries...")

        # Find root
        root_id = None
        for tax_id, node in self._nodes.items():
            if node.parent_id is None:
                root_id = tax_id
                break

        if root_id is None:
            raise ValidationError("No root node found")

        # Build Euler tour and depth arrays
        self._euler_tour.clear()
        self._first_occurrence.clear()
        self._depth_array.clear()

        def dfs(node_id: int, depth: int) -> None:
            # Record first occurrence
            if node_id not in self._first_occurrence:
                self._first_occurrence[node_id] = len(self._euler_tour)

            self._euler_tour.append(node_id)
            self._depth_array.append(depth)

            # Visit children
            for child_id in self._children_index.get(node_id, []):
                dfs(child_id, depth + 1)
                # Add current node again (Euler tour property)
                self._euler_tour.append(node_id)
                self._depth_array.append(depth)

        dfs(root_id, 0)

        # Build RMQ structure
        self._rmq = RangeMinimumQuery(self._depth_array)
        self._lca_preprocessed = True

        print(
            f"LCA preprocessing complete. Euler tour length: {len(self._euler_tour):,}"
        )

    def get_node_uncompressed(self, tax_id: int) -> Optional[TaxonomyNode]:
        """Get full TaxonomyNode object (slower but compatible)."""
        compressed = self._nodes.get(tax_id)
        if not compressed:
            return None

        name = self.string_pool.get_string(compressed.name_id)
        rank = self.id_to_rank[compressed.rank_id]

        return TaxonomyNode(
            tax_id=compressed.tax_id,
            name=name,
            rank=rank,
            parent_id=compressed.parent_id,
        )

    def get_children(self, tax_id: int) -> List[int]:
        """Get children IDs of a node."""
        return self._children_index.get(tax_id, []).copy()

    def lowest_common_ancestor(self, tax_id1: int, tax_id2: int) -> Optional[int]:
        """O(1) LCA query using RMQ preprocessing."""
        if not self._lca_preprocessed:
            raise RuntimeError("LCA not preprocessed. Call _preprocess_lca() first.")

        self._stats["lca_queries"] += 1

        # Get first occurrences in Euler tour
        if (
            tax_id1 not in self._first_occurrence
            or tax_id2 not in self._first_occurrence
        ):
            return None

        idx1 = self._first_occurrence[tax_id1]
        idx2 = self._first_occurrence[tax_id2]

        # Ensure idx1 <= idx2
        if idx1 > idx2:
            idx1, idx2 = idx2, idx1

        # Query RMQ for minimum depth in range
        if self._rmq is None:
            return None
        min_idx = self._rmq.query(idx1, idx2)
        if min_idx == -1:
            return None

        return self._euler_tour[min_idx]

    def batch_lca(
        self, pairs: List[Tuple[int, int]], max_workers: Optional[int] = None
    ) -> Iterator[Tuple[Tuple[int, int], Optional[int]]]:
        """Parallel batch LCA computation."""
        if not self._lca_preprocessed:
            self._preprocess_lca()

        max_workers = max_workers or min(len(pairs), mp.cpu_count())

        def compute_lca_chunk(
            chunk: List[Tuple[int, int]],
        ) -> List[Tuple[Tuple[int, int], Optional[int]]]:
            results = []
            for pair in chunk:
                lca = self.lowest_common_ancestor(pair[0], pair[1])
                results.append((pair, lca))
            return results

        # Split pairs into chunks
        chunk_size = max(1, len(pairs) // max_workers)
        chunks = [pairs[i : i + chunk_size] for i in range(0, len(pairs), chunk_size)]

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(compute_lca_chunk, chunk) for chunk in chunks]

            for future in as_completed(futures):
                for result in future.result():
                    yield result

    def get_path_to_root(self, tax_id: int) -> List[int]:
        """Get path from node to root (tax_ids only for performance)."""
        path = []
        current = tax_id
        visited = set()

        while current is not None:
            if current in visited:
                raise ValidationError(f"Circular reference detected at {current}")
            visited.add(current)
            path.append(current)
            parent = self._parent_index.get(current)
            if parent is None:
                break
            current = parent

        return path

    def parallel_distance_matrix(
        self, node_ids: List[int], max_workers: Optional[int] = None
    ) -> np.ndarray[Any, np.dtype[np.int32]]:
        """Compute distance matrix in parallel."""
        n = len(node_ids)
        distances = np.zeros((n, n), dtype=np.int32)

        # Generate all pairs
        pairs = []
        for i in range(n):
            for j in range(i + 1, n):
                pairs.append((i, j, node_ids[i], node_ids[j]))

        def compute_distance_chunk(
            chunk: List[Tuple[int, int, int, int]],
        ) -> List[Tuple[int, int, int]]:
            results = []
            for i, j, node1, node2 in chunk:
                lca = self.lowest_common_ancestor(node1, node2)
                if lca is not None:
                    # Distance = depth(node1) + depth(node2) - 2*depth(lca)
                    path1 = self.get_path_to_root(node1)
                    path2 = self.get_path_to_root(node2)
                    path_lca = self.get_path_to_root(lca)

                    dist = len(path1) + len(path2) - 2 * len(path_lca)
                    results.append((i, j, dist))
                else:
                    results.append((i, j, -1))  # No path
            return results

        # Process in parallel
        max_workers = max_workers or mp.cpu_count()
        chunk_size = max(1, len(pairs) // max_workers)
        chunks = [pairs[i : i + chunk_size] for i in range(0, len(pairs), chunk_size)]

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(compute_distance_chunk, chunk) for chunk in chunks
            ]

            for future in as_completed(futures):
                for i, j, dist in future.result():
                    distances[i, j] = dist
                    distances[j, i] = dist  # Symmetric

        return distances

    def streaming_subtree_nodes(
        self, root_id: int, max_depth: Optional[int] = None
    ) -> Iterator[int]:
        """Stream subtree nodes without loading entire subtree into memory."""
        queue = deque([(root_id, 0)])
        visited = set()

        while queue:
            node_id, depth = queue.popleft()

            if node_id in visited:
                continue
            if max_depth is not None and depth > max_depth:
                continue

            visited.add(node_id)
            yield node_id

            # Add children to queue
            for child_id in self.get_children(node_id):
                if child_id not in visited:
                    queue.append((child_id, depth + 1))

    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive tree statistics."""
        stats = self._stats.copy()
        stats.update(
            {
                "total_nodes": len(self._nodes),
                "string_pool_size": len(self.string_pool._strings),
                "string_pool_memory": self.string_pool.memory_usage(),
                "lca_preprocessed": self._lca_preprocessed,
                "euler_tour_length": len(self._euler_tour),
                "memory_mapped": self._mmap_file is not None,
                "db_connections": len(self._db_connections),
            }
        )

        # Estimate total memory usage
        node_memory = len(self._nodes) * 13  # 13 bytes per compressed node
        index_memory = sum(
            len(children) * 4 for children in self._children_index.values()
        )
        euler_memory = len(self._euler_tour) * 8  # 2 arrays of ints

        stats["estimated_memory_bytes"] = (
            node_memory + index_memory + euler_memory + stats["string_pool_memory"]
        )

        return stats

    def memory_usage_mb(self) -> float:
        """Get estimated memory usage in MB."""
        stats = self.get_statistics()
        memory_bytes = stats["estimated_memory_bytes"]
        if isinstance(memory_bytes, (int, float)):
            return float(memory_bytes) / (1024 * 1024)
        return 0.0


def create_high_performance_tree(
    db_path: str, memory_map_size: int = 1024 * 1024 * 1024
) -> HighPerformanceTaxonomyTree:
    """Factory function to create optimized tree."""
    tree = HighPerformanceTaxonomyTree(db_path, memory_map_size)
    tree.load_from_database()
    return tree


def benchmark_performance(
    tree: HighPerformanceTaxonomyTree, num_samples: int = 1000
) -> Dict[str, float]:
    """Benchmark tree performance."""
    import random

    node_ids = list(tree._nodes.keys())
    if len(node_ids) < num_samples:
        num_samples = len(node_ids)

    # Sample random nodes
    sample_nodes = random.sample(node_ids, num_samples)

    # Benchmark LCA queries
    start_time = time.time()
    for i in range(0, num_samples - 1, 2):
        tree.lowest_common_ancestor(sample_nodes[i], sample_nodes[i + 1])
    lca_time = time.time() - start_time

    # Benchmark path queries
    start_time = time.time()
    for node_id in sample_nodes[:100]:  # Smaller sample for paths
        tree.get_path_to_root(node_id)
    path_time = time.time() - start_time

    return {
        "lca_queries_per_second": (num_samples // 2) / lca_time if lca_time > 0 else 0,
        "path_queries_per_second": 100 / path_time if path_time > 0 else 0,
        "memory_usage_mb": tree.memory_usage_mb(),
        "total_nodes": len(tree._nodes),
    }
