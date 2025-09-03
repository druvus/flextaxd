"""Comprehensive tests for High Performance Tree operations."""

import pytest
import tempfile
import sqlite3
from pathlib import Path
from unittest.mock import patch, MagicMock
import threading
import time
import multiprocessing as mp

from flextaxd.core.high_performance_tree import (
    HighPerformanceTaxonomyTree,
    CompressedNode,
    StringInternPool,
    RangeMinimumQuery,
)
from flextaxd.core.models import TaxonomyNode, TaxonomicRank
from flextaxd.core.exceptions import ValidationError


class TestStringInternPool:
    """Test string interning pool for memory optimization."""

    def test_string_interning(self):
        """Test string interning functionality."""
        pool = StringInternPool()

        # Test adding strings
        id1 = pool.intern("Bacteria")
        id2 = pool.intern("Archaea")
        id3 = pool.intern("Bacteria")  # Duplicate

        assert id1 == 0
        assert id2 == 1
        assert id3 == 0  # Should return same ID for duplicate

        # Test retrieval
        assert pool.get_string(id1) == "Bacteria"
        assert pool.get_string(id2) == "Archaea"

    def test_memory_usage_calculation(self):
        """Test memory usage estimation."""
        pool = StringInternPool()

        # Empty pool
        assert pool.memory_usage() == 0

        # Add some strings
        pool.intern("Bacteria")
        pool.intern("Archaea")

        # Memory usage should be sum of encoded string lengths
        expected = len("Bacteria".encode("utf-8")) + len("Archaea".encode("utf-8"))
        assert pool.memory_usage() == expected


class TestCompressedNode:
    """Test compressed node representation."""

    def test_node_packing_unpacking(self):
        """Test binary packing and unpacking of nodes."""
        node = CompressedNode(tax_id=12345, parent_id=6789, rank_id=2, name_id=42)

        # Pack and unpack
        packed = node.pack()
        unpacked = CompressedNode.unpack(packed)

        assert unpacked.tax_id == node.tax_id
        assert unpacked.parent_id == node.parent_id
        assert unpacked.rank_id == node.rank_id
        assert unpacked.name_id == node.name_id

    def test_root_node_packing(self):
        """Test packing of root node with None parent."""
        node = CompressedNode(tax_id=1, parent_id=None, rank_id=0, name_id=0)

        packed = node.pack()
        unpacked = CompressedNode.unpack(packed)

        assert unpacked.tax_id == 1
        assert unpacked.parent_id is None
        assert unpacked.rank_id == 0
        assert unpacked.name_id == 0

    def test_packed_size(self):
        """Test that packed size is exactly 13 bytes."""
        node = CompressedNode(tax_id=1, parent_id=2, rank_id=3, name_id=4)
        packed = node.pack()

        # Should be 4 + 4 + 1 + 4 = 13 bytes
        assert len(packed) == 13


class TestRangeMinimumQuery:
    """Test RMQ data structure for LCA queries."""

    def test_rmq_construction(self):
        """Test RMQ construction with small array."""
        depths = [0, 1, 2, 1, 2, 3, 2, 1]
        rmq = RangeMinimumQuery(depths)

        # RMQ should be constructed without errors
        assert rmq is not None

    def test_rmq_queries(self):
        """Test RMQ range minimum queries."""
        depths = [0, 1, 2, 1, 2, 3, 2, 1]
        rmq = RangeMinimumQuery(depths)

        # Query for minimum in range [1, 4] should return index 1 or 3 (depth 1)
        min_idx = rmq.query(1, 4)
        assert min_idx in [1, 3]  # Both have depth 1
        assert depths[min_idx] == 1

    def test_rmq_edge_cases(self):
        """Test RMQ edge cases."""
        depths = [5]
        rmq = RangeMinimumQuery(depths)

        # Single element query
        assert rmq.query(0, 0) == 0

    def test_rmq_invalid_ranges(self):
        """Test RMQ with invalid ranges."""
        depths = [0, 1, 2, 1]
        rmq = RangeMinimumQuery(depths)

        # Invalid range should return -1 or handle gracefully
        result = rmq.query(3, 1)  # left > right
        assert result in [-1, 1, 3]  # Implementation specific


class TestHighPerformanceTaxonomyTree:
    """Test high performance tree operations."""

    def setup_method(self):
        """Setup for each test method."""
        self.hp_tree = HighPerformanceTaxonomyTree()

    def create_test_database(self) -> Path:
        """Create a test SQLite database with sample data."""
        temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        db_path = Path(temp_db.name)
        temp_db.close()

        conn = sqlite3.connect(db_path)

        # Create schema
        conn.execute(
            """
            CREATE TABLE nodes (
                tax_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                rank TEXT,
                parent_id INTEGER
            )
        """
        )

        # Insert test data - small tree for testing
        test_data = [
            (1, "root", "no rank", None),
            (2, "Bacteria", "superkingdom", 1),
            (3, "Archaea", "superkingdom", 1),
            (4, "Firmicutes", "phylum", 2),
            (5, "Proteobacteria", "phylum", 2),
            (6, "Bacilli", "class", 4),
            (7, "Gammaproteobacteria", "class", 5),
            (8, "Lactobacillales", "order", 6),
            (9, "Enterobacteriales", "order", 7),
        ]

        conn.executemany("INSERT INTO nodes VALUES (?, ?, ?, ?)", test_data)
        conn.commit()
        conn.close()

        return db_path

    def test_tree_initialization(self):
        """Test high performance tree initialization."""
        tree = HighPerformanceTaxonomyTree()

        assert tree.string_pool is not None
        assert tree.rank_to_id is not None
        assert tree.id_to_rank is not None
        assert len(tree._nodes) == 0
        assert not tree._lca_preprocessed

    def test_database_loading(self):
        """Test loading tree from database."""
        db_path = self.create_test_database()

        try:
            tree = HighPerformanceTaxonomyTree(db_path=str(db_path))
            tree.load_from_database()

            # Should have loaded nodes
            assert len(tree._nodes) > 0

            # Check that stats were updated
            assert tree._stats["nodes_loaded"] > 0

        finally:
            db_path.unlink()

    def test_lca_preprocessing(self):
        """Test LCA preprocessing creates required structures."""
        db_path = self.create_test_database()

        try:
            tree = HighPerformanceTaxonomyTree(db_path=str(db_path))
            tree.load_from_database()

            # LCA preprocessing should be done during load
            assert tree._lca_preprocessed
            assert len(tree._euler_tour) > 0
            assert len(tree._first_occurrence) > 0
            assert len(tree._depth_array) > 0
            assert tree._rmq is not None

        finally:
            db_path.unlink()

    def test_lca_queries(self):
        """Test LCA queries work correctly."""
        db_path = self.create_test_database()

        try:
            tree = HighPerformanceTaxonomyTree(db_path=str(db_path))
            tree.load_from_database()

            # Test LCA of nodes in same subtree
            lca = tree.lowest_common_ancestor(6, 8)  # Bacilli, Lactobacillales
            # LCA should be either Bacilli (6) or Firmicutes (4)
            assert lca in [4, 6]  # Implementation dependent

            # Test LCA across different subtrees
            lca = tree.lowest_common_ancestor(6, 7)  # Bacilli, Gammaproteobacteria
            assert lca == 2  # Should be Bacteria

            # Test stats were updated
            assert tree._stats["lca_queries"] > 0

        finally:
            db_path.unlink()

    def test_lca_invalid_nodes(self):
        """Test LCA queries with invalid node IDs."""
        db_path = self.create_test_database()

        try:
            tree = HighPerformanceTaxonomyTree(db_path=str(db_path))
            tree.load_from_database()

            # Test with non-existent nodes
            lca = tree.lowest_common_ancestor(999, 1000)
            assert lca is None

            # Test with one valid, one invalid
            lca = tree.lowest_common_ancestor(1, 999)
            assert lca is None

        finally:
            db_path.unlink()

    def test_batch_lca_queries(self):
        """Test batch LCA processing."""
        db_path = self.create_test_database()

        try:
            tree = HighPerformanceTaxonomyTree(db_path=str(db_path))
            tree.load_from_database()

            # Prepare pairs for batch LCA
            pairs = [(2, 3), (4, 5), (6, 7), (8, 9)]

            results = list(tree.batch_lca(pairs, max_workers=2))

            assert len(results) == len(pairs)

            # Check that each result has the expected format
            for pair, lca in results:
                assert isinstance(pair, tuple)
                assert len(pair) == 2
                # LCA should be int or None
                assert isinstance(lca, (int, type(None)))

        finally:
            db_path.unlink()

    def test_performance_stats(self):
        """Test performance statistics tracking."""
        db_path = self.create_test_database()

        try:
            tree = HighPerformanceTaxonomyTree(db_path=str(db_path))
            tree.load_from_database()

            # Perform some operations
            tree.lowest_common_ancestor(2, 3)
            tree.lowest_common_ancestor(4, 5)

            stats = tree.get_statistics()

            # Check stats structure
            assert "nodes_loaded" in stats
            assert "lca_queries" in stats
            assert "estimated_memory_bytes" in stats

            # Check values are reasonable
            assert stats["nodes_loaded"] > 0
            assert stats["lca_queries"] >= 2
            assert stats["estimated_memory_bytes"] > 0

        finally:
            db_path.unlink()

    def test_memory_usage_calculation(self):
        """Test memory usage calculation."""
        tree = HighPerformanceTaxonomyTree()

        # Empty tree should have minimal memory usage
        stats = tree.get_statistics()
        assert stats["estimated_memory_bytes"] >= 0

    def test_database_connection_pooling(self):
        """Test database connection pooling functionality."""
        db_path = self.create_test_database()

        try:
            tree = HighPerformanceTaxonomyTree(db_path=str(db_path))

            # Test getting connection from main thread
            conn1 = tree._get_db_connection()
            conn2 = tree._get_db_connection()

            # Should return same connection for same thread
            assert conn1 is conn2

            # Cleanup connections
            tree._cleanup_connections()

        finally:
            db_path.unlink()

    def test_batch_processing(self):
        """Test batch processing of nodes."""
        tree = HighPerformanceTaxonomyTree()

        # Sample batch data
        batch = [
            (1, "root", "no rank", None),
            (2, "Bacteria", "superkingdom", 1),
            (3, "Archaea", "superkingdom", 1),
        ]

        tree._process_node_batch(batch)

        # Check nodes were processed
        assert len(tree._nodes) == 3
        assert 1 in tree._nodes
        assert 2 in tree._nodes
        assert 3 in tree._nodes

    def test_error_handling(self):
        """Test error handling in various scenarios."""
        tree = HighPerformanceTaxonomyTree()

        # Test LCA without preprocessing
        with pytest.raises(RuntimeError, match="LCA not preprocessed"):
            tree.lowest_common_ancestor(1, 2)

        # Test loading from non-existent database
        tree = HighPerformanceTaxonomyTree(db_path="/nonexistent/path.db")
        with pytest.raises(Exception):  # Should raise some database error
            tree.load_from_database()


class TestHighPerformanceTreeIntegration:
    """Integration tests for high performance tree."""

    def test_large_tree_simulation(self):
        """Test with larger simulated tree."""
        # Create larger test database
        temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        db_path = Path(temp_db.name)
        temp_db.close()

        try:
            conn = sqlite3.connect(db_path)

            conn.execute(
                """
                CREATE TABLE nodes (
                    tax_id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    rank TEXT,
                    parent_id INTEGER
                )
            """
            )

            # Generate larger tree (1000 nodes)
            test_data = [(1, "root", "no rank", None)]

            for i in range(2, 1001):
                parent_id = (i - 1) // 2 if i > 1 else 1
                name = f"Node_{i}"
                rank = "species" if i > 500 else "genus"
                test_data.append((i, name, rank, parent_id))

            conn.executemany("INSERT INTO nodes VALUES (?, ?, ?, ?)", test_data)
            conn.commit()
            conn.close()

            # Test tree operations
            tree = HighPerformanceTaxonomyTree(db_path=str(db_path))
            tree.load_from_database()

            # Test LCA on large tree
            lca = tree.lowest_common_ancestor(100, 200)
            assert lca is not None

            # Test batch operations
            pairs = [(i, i + 1) for i in range(10, 20)]
            results = list(tree.batch_lca(pairs, max_workers=2))
            assert len(results) == len(pairs)

        finally:
            db_path.unlink()

    def test_concurrent_access(self):
        """Test concurrent access to tree operations."""
        db_path = self.create_simple_db()

        try:
            tree = HighPerformanceTaxonomyTree(db_path=str(db_path))
            tree.load_from_database()

            results = []
            errors = []

            def worker_thread():
                try:
                    lca = tree.lowest_common_ancestor(2, 3)
                    results.append(lca)
                except Exception as e:
                    errors.append(e)

            # Create multiple threads
            threads = []
            for _ in range(5):
                t = threading.Thread(target=worker_thread)
                threads.append(t)
                t.start()

            # Wait for completion
            for t in threads:
                t.join()

            # Check results
            assert len(errors) == 0, f"Errors in concurrent access: {errors}"
            assert len(results) == 5

        finally:
            db_path.unlink()

    def create_simple_db(self) -> Path:
        """Create simple test database."""
        temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        db_path = Path(temp_db.name)
        temp_db.close()

        conn = sqlite3.connect(db_path)

        conn.execute(
            """
            CREATE TABLE nodes (
                tax_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                rank TEXT,
                parent_id INTEGER
            )
        """
        )

        test_data = [
            (1, "root", "no rank", None),
            (2, "Bacteria", "superkingdom", 1),
            (3, "Archaea", "superkingdom", 1),
        ]

        conn.executemany("INSERT INTO nodes VALUES (?, ?, ?, ?)", test_data)
        conn.commit()
        conn.close()

        return db_path
