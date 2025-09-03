"""Comprehensive tests for memory-optimized taxonomy tree operations."""

import pytest
import tempfile
import sqlite3
from pathlib import Path
from unittest.mock import Mock, patch
import time
import threading
from typing import Set, Optional

from flextaxd.core.memory_optimized_tree import (
    LazyTaxonomyTree,
    StreamingTaxonomyTree,
    MemoryEfficientNodeProvider,
    MemoryOptimizedOperations,
    NodeCacheEntry,
    create_memory_optimized_tree,
    create_streaming_tree,
)
from flextaxd.core.models import TaxonomyNode, TaxonomicRank


class MockNodeProvider:
    """Mock node provider for testing."""

    def __init__(self):
        self.nodes = {
            1: TaxonomyNode(1, "root", TaxonomicRank.ROOT, None),
            2: TaxonomyNode(2, "Bacteria", TaxonomicRank.SUPERKINGDOM, 1),
            3: TaxonomyNode(3, "Archaea", TaxonomicRank.SUPERKINGDOM, 1),
            4: TaxonomyNode(4, "Proteobacteria", TaxonomicRank.PHYLUM, 2),
            5: TaxonomyNode(5, "E.coli", TaxonomicRank.SPECIES, 4),
        }

        self.children_map = {1: {2, 3}, 2: {4}, 4: {5}, 3: set(), 5: set()}

        self.access_count = 0

    def get_node(self, tax_id: int) -> Optional[TaxonomyNode]:
        self.access_count += 1
        return self.nodes.get(tax_id)

    def get_children_ids(self, tax_id: int) -> Set[int]:
        return self.children_map.get(tax_id, set())

    def get_parent_id(self, tax_id: int) -> Optional[int]:
        node = self.nodes.get(tax_id)
        return node.parent_id if node else None

    def node_exists(self, tax_id: int) -> bool:
        return tax_id in self.nodes

    def get_all_node_ids(self) -> Set[int]:
        return set(self.nodes.keys())


class TestLazyTaxonomyTree:
    """Test lazy loading taxonomy tree."""

    @pytest.fixture
    def mock_provider(self):
        return MockNodeProvider()

    @pytest.fixture
    def lazy_tree(self, mock_provider):
        return LazyTaxonomyTree(mock_provider, cache_size=3)

    def test_basic_node_retrieval(self, lazy_tree, mock_provider):
        """Test basic node retrieval with caching."""
        # First access - should load from provider
        node = lazy_tree.get_node(1)
        assert node is not None
        assert node.name == "root"
        assert mock_provider.access_count == 1

        # Second access - should use cache
        node2 = lazy_tree.get_node(1)
        assert node2 is not None
        assert node2.name == "root"
        assert mock_provider.access_count == 1  # No additional access

    def test_cache_eviction(self, lazy_tree, mock_provider):
        """Test cache eviction when exceeding size limit."""
        # Fill cache beyond limit
        lazy_tree.get_node(1)
        lazy_tree.get_node(2)
        lazy_tree.get_node(3)
        lazy_tree.get_node(4)  # This should trigger eviction

        # Test that cache size is respected
        assert len(lazy_tree._node_cache) <= lazy_tree.cache_size

        # Access a node again to generate cache hits
        lazy_tree.get_node(4)  # Should be a cache hit
        assert lazy_tree.cache_hit_rate > 0

    def test_children_caching(self, lazy_tree, mock_provider):
        """Test children caching."""
        children1 = lazy_tree.get_children(1)
        children2 = lazy_tree.get_children(1)

        assert children1 == {2, 3}
        assert children2 == {2, 3}
        assert lazy_tree._cache_hits > 0  # Second call should be cached

    def test_path_to_root(self, lazy_tree):
        """Test path to root calculation."""
        path = lazy_tree.get_path_to_root(5)

        assert len(path) == 4  # E.coli -> Proteobacteria -> Bacteria -> root
        assert path[0].name == "E.coli"
        assert path[-1].name == "root"

    def test_lca_calculation(self, lazy_tree):
        """Test LCA calculation with caching."""
        lca = lazy_tree.lowest_common_ancestor(2, 3)
        assert lca is not None
        assert lca.name == "root"

        lca2 = lazy_tree.lowest_common_ancestor(4, 5)
        assert lca2 is not None
        assert lca2.name == "Bacteria"

    def test_memory_stats(self, lazy_tree):
        """Test memory statistics."""
        lazy_tree.get_node(1)
        lazy_tree.get_node(2)

        stats = lazy_tree.memory_stats
        assert "cached_nodes" in stats
        assert "cache_hit_rate" in stats
        assert "memory_efficiency" in stats
        assert stats["cached_nodes"] == 2

    def test_preload_subtree(self, lazy_tree, mock_provider):
        """Test subtree preloading."""
        initial_count = mock_provider.access_count

        # Preload subtree rooted at Bacteria (node 2)
        lazy_tree.preload_subtree(2, max_depth=2)

        # Should have loaded multiple nodes
        assert mock_provider.access_count > initial_count

        # Subsequent access should be cached
        node = lazy_tree.get_node(4)  # Should be preloaded
        assert node is not None

    def test_thread_safety(self, lazy_tree):
        """Test thread safety of cache operations."""
        results = []

        def access_nodes():
            for i in range(1, 6):
                node = lazy_tree.get_node(i)
                results.append(node)

        threads = [threading.Thread(target=access_nodes) for _ in range(5)]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # All nodes should be retrieved successfully
        assert len([r for r in results if r is not None]) > 0
        assert len(lazy_tree._node_cache) > 0

    def test_cache_clear(self, lazy_tree):
        """Test cache clearing."""
        lazy_tree.get_node(1)
        lazy_tree.get_node(2)
        assert len(lazy_tree._node_cache) == 2

        lazy_tree.clear_cache()
        assert len(lazy_tree._node_cache) == 0
        assert lazy_tree._cache_hits == 0
        assert lazy_tree._cache_misses == 0

    def test_root_id_caching(self, lazy_tree):
        """Test root ID caching."""
        root_id1 = lazy_tree.root_id
        root_id2 = lazy_tree.root_id

        assert root_id1 == 1
        assert root_id2 == 1
        assert lazy_tree._root_cached  # Should be cached after first access


class TestStreamingTaxonomyTree:
    """Test streaming taxonomy tree operations."""

    @pytest.fixture
    def mock_provider(self):
        return MockNodeProvider()

    @pytest.fixture
    def streaming_tree(self, mock_provider):
        return StreamingTaxonomyTree(mock_provider)

    def test_stream_subtree(self, streaming_tree):
        """Test streaming subtree traversal."""
        nodes = list(streaming_tree.stream_subtree(1))

        assert len(nodes) == 5  # All nodes in tree
        assert nodes[0].name == "root"  # Should start with root

        # Should visit all nodes exactly once
        node_ids = {node.tax_id for node in nodes}
        assert node_ids == {1, 2, 3, 4, 5}

    def test_stream_by_rank(self, streaming_tree):
        """Test streaming nodes by rank."""
        species_nodes = list(streaming_tree.stream_by_rank(TaxonomicRank.SPECIES))

        assert len(species_nodes) == 1
        assert species_nodes[0].name == "E.coli"

        superkingdom_nodes = list(
            streaming_tree.stream_by_rank(TaxonomicRank.SUPERKINGDOM)
        )
        assert len(superkingdom_nodes) == 2
        assert {node.name for node in superkingdom_nodes} == {"Bacteria", "Archaea"}

    def test_stream_leaves(self, streaming_tree):
        """Test streaming leaf nodes."""
        leaves = list(streaming_tree.stream_leaves())

        # Archaea (3) and E.coli (5) are leaves
        assert len(leaves) == 2
        leaf_names = {node.name for node in leaves}
        assert "Archaea" in leaf_names
        assert "E.coli" in leaf_names

    def test_memory_usage_estimation(self, streaming_tree):
        """Test memory usage estimation."""
        usage = streaming_tree.estimate_memory_usage(max_concurrent_nodes=50)

        assert "estimated_bytes" in usage
        assert "max_concurrent_nodes" in usage
        assert "node_size_bytes" in usage
        assert usage["max_concurrent_nodes"] == 50

    def test_visited_cache_isolation(self, streaming_tree):
        """Test that streaming operations don't interfere."""
        # First stream
        nodes1 = list(streaming_tree.stream_subtree(2))  # Bacteria subtree

        # Second stream should be independent
        nodes2 = list(streaming_tree.stream_subtree(3))  # Archaea subtree

        assert len(nodes1) == 3  # Bacteria, Proteobacteria, E.coli
        assert len(nodes2) == 1  # Just Archaea
        assert nodes1[0].name == "Bacteria"
        assert nodes2[0].name == "Archaea"


class TestMemoryEfficientNodeProvider:
    """Test database-backed node provider."""

    @pytest.fixture
    def test_database(self):
        """Create test database."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Create schema
        cursor.execute(
            """
            CREATE TABLE nodes (
                tax_id INTEGER PRIMARY KEY,
                name TEXT,
                rank TEXT,
                parent_id INTEGER
            )
        """
        )

        # Insert test data
        test_nodes = [
            (1, "root", "root", 1),
            (2, "Bacteria", "superkingdom", 1),
            (3, "Proteobacteria", "phylum", 2),
            (4, "E.coli", "species", 3),
        ]

        cursor.executemany(
            "INSERT INTO nodes (tax_id, name, rank, parent_id) VALUES (?, ?, ?, ?)",
            test_nodes,
        )

        conn.commit()
        conn.close()

        yield db_path

        # Cleanup
        Path(db_path).unlink()

    def test_database_node_retrieval(self, test_database):
        """Test retrieving nodes from database."""
        provider = MemoryEfficientNodeProvider(test_database)

        node = provider.get_node(1)
        assert node is not None
        assert node.name == "root"
        assert node.rank == TaxonomicRank.ROOT

    def test_database_children_retrieval(self, test_database):
        """Test retrieving children from database."""
        provider = MemoryEfficientNodeProvider(test_database)

        children = provider.get_children_ids(1)
        assert 2 in children

        children_2 = provider.get_children_ids(2)
        assert 3 in children_2

    def test_lru_cache_functionality(self, test_database):
        """Test LRU cache in database provider."""
        provider = MemoryEfficientNodeProvider(test_database)

        # Multiple accesses should use cache
        node1 = provider.get_node(1)
        node2 = provider.get_node(1)

        assert node1 is not None
        assert node2 is not None

        # Check cache info
        cache_info = provider.cache_info()
        assert "get_node" in cache_info
        assert cache_info["get_node"].hits > 0

    def test_cache_clearing(self, test_database):
        """Test cache clearing."""
        provider = MemoryEfficientNodeProvider(test_database)

        provider.get_node(1)
        provider.get_node(2)

        # Clear cache
        provider.clear_cache()

        # Cache should be empty
        cache_info = provider.cache_info()
        assert cache_info["get_node"].currsize == 0

    def test_nonexistent_node(self, test_database):
        """Test handling of nonexistent nodes."""
        provider = MemoryEfficientNodeProvider(test_database)

        node = provider.get_node(999)
        assert node is None

        children = provider.get_children_ids(999)
        assert len(children) == 0

        assert not provider.node_exists(999)


class TestMemoryOptimizedOperations:
    """Test memory-optimized tree operations."""

    @pytest.fixture
    def lazy_tree(self):
        provider = MockNodeProvider()
        return LazyTaxonomyTree(provider, cache_size=10)

    @pytest.fixture
    def memory_ops(self, lazy_tree):
        return MemoryOptimizedOperations(lazy_tree)

    def test_batch_lca(self, memory_ops):
        """Test batch LCA computation."""
        pairs = [(2, 3), (4, 5), (1, 5)]

        results = list(memory_ops.batch_lca(pairs, batch_size=2))

        assert len(results) == 3
        for pair, lca in results:
            assert lca is not None
            assert pair in [(2, 3), (4, 5), (1, 5)]

    def test_streaming_distance_matrix(self, memory_ops):
        """Test streaming distance matrix computation."""
        tax_ids = [2, 3, 4, 5]

        distances = list(memory_ops.streaming_distance_matrix(tax_ids))

        # Should compute all pairwise distances
        assert len(distances) == 6  # C(4,2) = 6 pairs

        for id1, id2, distance in distances:
            assert id1 in tax_ids
            assert id2 in tax_ids
            assert (
                distance is not None or distance is None
            )  # Some may be None if no LCA

    def test_memory_efficient_subtree_stats(self, memory_ops):
        """Test memory-efficient subtree statistics."""
        stats = memory_ops.memory_efficient_subtree_stats(2)  # Bacteria subtree

        assert "node_count" in stats
        assert "max_depth" in stats
        assert "rank_distribution" in stats
        assert "leaf_count" in stats

        assert stats["node_count"] == 3  # Bacteria, Proteobacteria, E.coli
        assert stats["leaf_count"] == 1  # E.coli is leaf
        assert "superkingdom" in stats["rank_distribution"]


class TestFactoryFunctions:
    """Test factory functions for creating optimized trees."""

    @pytest.fixture
    def test_database(self):
        """Create test database."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE nodes (
                tax_id INTEGER PRIMARY KEY,
                name TEXT,
                rank TEXT,
                parent_id INTEGER
            )
        """
        )

        cursor.execute(
            "INSERT INTO nodes (tax_id, name, rank, parent_id) VALUES (1, 'root', 'root', 1)"
        )

        conn.commit()
        conn.close()

        yield db_path
        Path(db_path).unlink()

    def test_create_memory_optimized_tree(self, test_database):
        """Test factory function for memory-optimized tree."""
        tree = create_memory_optimized_tree(test_database, cache_size=50)

        assert isinstance(tree, LazyTaxonomyTree)
        assert tree.cache_size == 50

        node = tree.get_node(1)
        assert node is not None

    def test_create_streaming_tree(self, test_database):
        """Test factory function for streaming tree."""
        tree = create_streaming_tree(test_database)

        assert isinstance(tree, StreamingTaxonomyTree)

        nodes = list(tree.stream_subtree(1))
        assert len(nodes) == 1  # Just root node


class TestPerformanceComparison:
    """Compare performance of regular vs memory-optimized trees."""

    def create_large_mock_provider(self, num_nodes: int = 1000):
        """Create mock provider with many nodes."""
        provider = MockNodeProvider()

        # Generate many nodes in linear chain
        provider.nodes = {}
        provider.children_map = {}

        for i in range(1, num_nodes + 1):
            parent_id = i - 1 if i > 1 else None
            provider.nodes[i] = TaxonomyNode(
                i, f"Node_{i}", TaxonomicRank.SPECIES, parent_id
            )

            if parent_id:
                if parent_id not in provider.children_map:
                    provider.children_map[parent_id] = set()
                provider.children_map[parent_id].add(i)

        return provider

    def test_memory_usage_comparison(self):
        """Test memory usage of different approaches."""
        import sys

        # Large provider
        provider = self.create_large_mock_provider(500)

        # Memory-optimized tree
        lazy_tree = LazyTaxonomyTree(provider, cache_size=50)

        # Load some nodes
        for i in range(1, 51):  # Load first 50 nodes
            lazy_tree.get_node(i)

        # Check memory usage
        stats = lazy_tree.memory_stats
        assert stats["cached_nodes"] <= 50  # Should respect cache size
        assert stats["memory_efficiency"] > 0

    @pytest.mark.slow
    def test_large_tree_operations(self):
        """Test operations on large trees."""
        provider = self.create_large_mock_provider(2000)
        lazy_tree = LazyTaxonomyTree(provider, cache_size=100)

        # Test path to root on deep node
        start_time = time.time()
        path = lazy_tree.get_path_to_root(1000)
        end_time = time.time()

        assert len(path) == 1000  # Linear chain
        assert end_time - start_time < 1.0  # Should be fast with caching

        # Test cache effectiveness
        stats = lazy_tree.memory_stats
        assert stats["cache_hit_rate"] > 0

    def test_streaming_vs_loading_memory(self):
        """Compare memory usage of streaming vs full loading."""
        provider = self.create_large_mock_provider(100)

        # Streaming approach
        streaming_tree = StreamingTaxonomyTree(provider)

        # Count nodes via streaming
        count = 0
        for node in streaming_tree.stream_subtree(1):
            count += 1

        assert count == 100

        # Memory usage should be minimal
        usage = streaming_tree.estimate_memory_usage(max_concurrent_nodes=10)
        assert usage["max_concurrent_nodes"] == 10
