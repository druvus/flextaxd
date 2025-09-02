"""Comprehensive tests for Memory Optimized Tree operations."""

import pytest
import tempfile
import sqlite3
import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from flextaxd.core.memory_optimized_tree import (
    LazyTaxonomyTree, StreamingTaxonomyTree, MemoryEfficientNodeProvider,
    NodeCacheEntry, NodeProvider
)
from flextaxd.core.models import TaxonomyNode, TaxonomicRank
from flextaxd.core.exceptions import ValidationError


class MockNodeProvider:
    """Mock node provider for testing."""
    
    def __init__(self, nodes_data: dict):
        self.nodes_data = nodes_data
        self.access_count = 0
    
    def get_node(self, tax_id: int) -> TaxonomyNode:
        self.access_count += 1
        if tax_id not in self.nodes_data:
            return None
        
        data = self.nodes_data[tax_id]
        return TaxonomyNode(
            tax_id=tax_id,
            name=data['name'],
            rank=data.get('rank', TaxonomicRank.CUSTOM),
            parent_id=data.get('parent_id')
        )
    
    def get_children_ids(self, tax_id: int) -> set:
        children = set()
        for node_id, data in self.nodes_data.items():
            if data.get('parent_id') == tax_id:
                children.add(node_id)
        return children
    
    def get_parent_id(self, tax_id: int) -> int:
        if tax_id not in self.nodes_data:
            return None
        return self.nodes_data[tax_id].get('parent_id')
    
    def node_exists(self, tax_id: int) -> bool:
        return tax_id in self.nodes_data
    
    def get_all_node_ids(self) -> set:
        return set(self.nodes_data.keys())


class TestNodeCacheEntry:
    """Test node cache entry functionality."""
    
    def test_cache_entry_creation(self):
        """Test creating cache entry."""
        node = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        entry = NodeCacheEntry(node=node)
        
        assert entry.node == node
        assert entry.children is None
        assert entry.last_accessed == 0.0
        assert entry.access_count == 0
    
    def test_cache_entry_with_children(self):
        """Test cache entry with children data."""
        node = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        children = {2, 3, 4}
        entry = NodeCacheEntry(node=node, children=children, access_count=5)
        
        assert entry.node == node
        assert entry.children == children
        assert entry.access_count == 5


class TestLazyTaxonomyTree:
    """Test lazy taxonomy tree with caching."""
    
    def setup_method(self):
        """Setup for each test method."""
        # Create sample tree data
        self.tree_data = {
            1: {'name': 'root', 'rank': TaxonomicRank.CUSTOM, 'parent_id': None},
            2: {'name': 'Bacteria', 'rank': TaxonomicRank.SUPERKINGDOM, 'parent_id': 1},
            3: {'name': 'Archaea', 'rank': TaxonomicRank.SUPERKINGDOM, 'parent_id': 1},
            4: {'name': 'Firmicutes', 'rank': TaxonomicRank.PHYLUM, 'parent_id': 2},
            5: {'name': 'Proteobacteria', 'rank': TaxonomicRank.PHYLUM, 'parent_id': 2},
        }
        self.provider = MockNodeProvider(self.tree_data)
        self.lazy_tree = LazyTaxonomyTree(self.provider, cache_size=3)
    
    def test_initialization(self):
        """Test lazy tree initialization."""
        tree = LazyTaxonomyTree(self.provider, cache_size=10)
        
        assert tree.node_provider == self.provider
        assert tree.cache_size == 10
        assert len(tree._node_cache) == 0
        assert tree._cache_hits == 0
        assert tree._cache_misses == 0
        assert tree.cache_hit_rate == 0.0
    
    def test_get_node_first_time(self):
        """Test getting node for the first time (cache miss)."""
        node = self.lazy_tree.get_node(2)
        
        assert node is not None
        assert node.name == "Bacteria"
        assert node.rank == TaxonomicRank.SUPERKINGDOM
        assert self.lazy_tree._cache_misses == 1
        assert self.lazy_tree._cache_hits == 0
        assert len(self.lazy_tree._node_cache) == 1
    
    def test_get_node_cached(self):
        """Test getting cached node (cache hit)."""
        # First access - cache miss
        node1 = self.lazy_tree.get_node(2)
        
        # Second access - cache hit
        node2 = self.lazy_tree.get_node(2)
        
        assert node1 == node2
        assert self.lazy_tree._cache_misses == 1
        assert self.lazy_tree._cache_hits == 1
        assert self.lazy_tree.cache_hit_rate == 50.0
    
    def test_cache_eviction(self):
        """Test LRU cache eviction when cache is full."""
        # Fill cache beyond capacity
        self.lazy_tree.get_node(1)  # Will be evicted
        self.lazy_tree.get_node(2) 
        self.lazy_tree.get_node(3)
        self.lazy_tree.get_node(4)  # Should trigger eviction
        
        # Node 1 should be evicted (assuming LRU implementation)
        assert len(self.lazy_tree._node_cache) <= self.lazy_tree.cache_size
    
    def test_get_children(self):
        """Test getting children of a node."""
        children = self.lazy_tree.get_children(1)  # root node
        
        assert 2 in children  # Bacteria
        assert 3 in children  # Archaea
        assert len(children) == 2
    
    def test_get_children_cached(self):
        """Test that children are cached."""
        # First call - loads from provider
        children1 = self.lazy_tree.get_children(1)
        
        # Second call - should use cache
        children2 = self.lazy_tree.get_children(1)
        
        assert children1 == children2
        # Provider should only be called once per node
    
    def test_node_exists(self):
        """Test checking if node exists via provider."""
        assert self.lazy_tree.node_provider.node_exists(1) is True
        assert self.lazy_tree.node_provider.node_exists(999) is False
    
    def test_get_parent_id(self):
        """Test getting parent ID via provider."""
        parent_id = self.lazy_tree.node_provider.get_parent_id(2)  # Bacteria
        assert parent_id == 1  # root
        
        # Root has no parent
        root_parent = self.lazy_tree.node_provider.get_parent_id(1)
        assert root_parent is None
    
    def test_memory_stats(self):
        """Test memory statistics."""
        # Load some nodes
        self.lazy_tree.get_node(1)
        self.lazy_tree.get_node(2)
        
        stats = self.lazy_tree.memory_stats
        
        assert 'cached_nodes' in stats
        assert 'cache_size_limit' in stats
        assert 'cache_hit_rate' in stats
        assert 'memory_efficiency' in stats  # Use actual field name
        
        assert stats['cached_nodes'] == 2
        assert stats['cache_hit_rate'] == 0.0  # All misses so far
    
    def test_clear_cache(self):
        """Test clearing the cache."""
        # Load some nodes
        self.lazy_tree.get_node(1)
        self.lazy_tree.get_node(2)
        
        assert len(self.lazy_tree._node_cache) > 0
        
        self.lazy_tree.clear_cache()
        
        assert len(self.lazy_tree._node_cache) == 0
        assert len(self.lazy_tree._children_cache) == 0
    
    def test_iteration_support(self):
        """Test tree iteration support via provider."""
        # Get all node IDs first
        all_ids = self.lazy_tree.node_provider.get_all_node_ids()
        
        # Then get all nodes
        nodes = [self.lazy_tree.get_node(node_id) for node_id in all_ids]
        nodes = [node for node in nodes if node is not None]
        
        # Should get all nodes
        assert len(nodes) == len(self.tree_data)
        
        # Check we got actual TaxonomyNode objects
        for node in nodes:
            assert isinstance(node, TaxonomyNode)
    
    def test_thread_safety(self):
        """Test thread-safe operations."""
        results = []
        errors = []
        
        def worker_thread():
            try:
                for i in range(1, 6):  # Access all nodes
                    node = self.lazy_tree.get_node(i)
                    if node:
                        results.append(node.tax_id)
            except Exception as e:
                errors.append(e)
        
        # Create multiple threads
        threads = []
        for _ in range(3):
            t = threading.Thread(target=worker_thread)
            threads.append(t)
            t.start()
        
        # Wait for completion
        for t in threads:
            t.join()
        
        # Check results
        assert len(errors) == 0, f"Errors in thread safety test: {errors}"
        assert len(results) > 0


class TestMemoryEfficientNodeProvider:
    """Test memory-efficient database-backed node provider."""
    
    def create_test_database(self) -> Path:
        """Create a test SQLite database with sample data."""
        temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        db_path = Path(temp_db.name)
        temp_db.close()
        
        conn = sqlite3.connect(db_path)
        
        # Create schema
        conn.execute("""
            CREATE TABLE nodes (
                tax_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                rank TEXT,
                parent_id INTEGER
            )
        """)
        
        # Insert test data
        test_data = [
            (1, "root", "no rank", None),
            (2, "Bacteria", "superkingdom", 1),
            (3, "Archaea", "superkingdom", 1),
            (4, "Firmicutes", "phylum", 2),
            (5, "Proteobacteria", "phylum", 2),
        ]
        
        conn.executemany("INSERT INTO nodes VALUES (?, ?, ?, ?)", test_data)
        conn.commit()
        conn.close()
        
        return db_path
    
    def test_provider_initialization(self):
        """Test provider initialization."""
        db_path = self.create_test_database()
        
        try:
            provider = MemoryEfficientNodeProvider(str(db_path))
            assert provider.database_path == str(db_path)
            assert provider._connection_cache is None
        finally:
            db_path.unlink()
    
    def test_get_node_from_database(self):
        """Test getting node from database."""
        db_path = self.create_test_database()
        
        try:
            provider = MemoryEfficientNodeProvider(str(db_path))
            node = provider.get_node(2)  # Bacteria
            
            assert node is not None
            assert node.name == "Bacteria"
            assert node.rank == TaxonomicRank.SUPERKINGDOM
            assert node.parent_id == 1
        finally:
            db_path.unlink()
    
    def test_get_nonexistent_node(self):
        """Test getting non-existent node."""
        db_path = self.create_test_database()
        
        try:
            provider = MemoryEfficientNodeProvider(str(db_path))
            node = provider.get_node(999)
            
            assert node is None
        finally:
            db_path.unlink()
    
    def test_lru_cache_functionality(self):
        """Test that LRU cache works for repeated access."""
        db_path = self.create_test_database()
        
        try:
            provider = MemoryEfficientNodeProvider(str(db_path))
            
            # First access
            node1 = provider.get_node(2)
            
            # Second access should hit cache (same object)
            node2 = provider.get_node(2)
            
            assert node1 == node2
            # Note: We can't easily test cache hits without internal access
            
        finally:
            db_path.unlink()
    
    def test_get_children_ids(self):
        """Test getting children IDs."""
        db_path = self.create_test_database()
        
        try:
            provider = MemoryEfficientNodeProvider(str(db_path))
            children = provider.get_children_ids(1)  # root
            
            assert 2 in children  # Bacteria
            assert 3 in children  # Archaea
            assert len(children) == 2
        finally:
            db_path.unlink()
    
    def test_get_parent_id(self):
        """Test getting parent ID."""
        db_path = self.create_test_database()
        
        try:
            provider = MemoryEfficientNodeProvider(str(db_path))
            parent_id = provider.get_parent_id(2)  # Bacteria
            
            assert parent_id == 1  # root
        finally:
            db_path.unlink()
    
    def test_node_exists(self):
        """Test checking if node exists."""
        db_path = self.create_test_database()
        
        try:
            provider = MemoryEfficientNodeProvider(str(db_path))
            
            assert provider.node_exists(1) is True
            assert provider.node_exists(999) is False
        finally:
            db_path.unlink()
    
    def test_get_all_node_ids(self):
        """Test getting all node IDs."""
        db_path = self.create_test_database()
        
        try:
            provider = MemoryEfficientNodeProvider(str(db_path))
            all_ids = provider.get_all_node_ids()
            
            expected_ids = {1, 2, 3, 4, 5}
            assert all_ids == expected_ids
        finally:
            db_path.unlink()
    
    def test_connection_caching(self):
        """Test that database connections are cached."""
        db_path = self.create_test_database()
        
        try:
            provider = MemoryEfficientNodeProvider(str(db_path))
            
            # First connection
            conn1 = provider._get_connection()
            
            # Second call should return same connection
            conn2 = provider._get_connection()
            
            assert conn1 is conn2
        finally:
            db_path.unlink()


class TestStreamingTaxonomyTree:
    """Test streaming taxonomy tree for memory-efficient processing."""
    
    def setup_method(self):
        """Setup for each test method."""
        self.tree_data = {
            1: {'name': 'root', 'rank': TaxonomicRank.CUSTOM, 'parent_id': None},
            2: {'name': 'Bacteria', 'rank': TaxonomicRank.SUPERKINGDOM, 'parent_id': 1},
            3: {'name': 'Archaea', 'rank': TaxonomicRank.SUPERKINGDOM, 'parent_id': 1},
            4: {'name': 'Firmicutes', 'rank': TaxonomicRank.PHYLUM, 'parent_id': 2},
            5: {'name': 'Proteobacteria', 'rank': TaxonomicRank.PHYLUM, 'parent_id': 2},
        }
        self.provider = MockNodeProvider(self.tree_data)
    
    def test_streaming_initialization(self):
        """Test streaming tree initialization."""
        streaming_tree = StreamingTaxonomyTree(self.provider, chunk_size=2)
        
        assert streaming_tree.node_provider == self.provider
        assert streaming_tree.chunk_size == 2
    
    def test_streaming_iteration(self):
        """Test streaming iteration through nodes."""
        streaming_tree = StreamingTaxonomyTree(self.provider, chunk_size=2)
        
        nodes = list(streaming_tree)
        
        # Should get all nodes
        assert len(nodes) == len(self.tree_data)
        
        # Check we got TaxonomyNode objects
        for node in nodes:
            assert isinstance(node, TaxonomyNode)
    
    def test_streaming_with_filter(self):
        """Test streaming with node filter."""
        def bacteria_filter(node: TaxonomyNode) -> bool:
            return node.rank == TaxonomicRank.SUPERKINGDOM
        
        streaming_tree = StreamingTaxonomyTree(
            self.provider, 
            chunk_size=2, 
            node_filter=bacteria_filter
        )
        
        filtered_nodes = list(streaming_tree)
        
        # Should only get superkingdom nodes
        assert len(filtered_nodes) == 2  # Bacteria and Archaea
        for node in filtered_nodes:
            assert node.rank == TaxonomicRank.SUPERKINGDOM
    
    def test_memory_bounded_processing(self):
        """Test that streaming maintains bounded memory usage."""
        streaming_tree = StreamingTaxonomyTree(self.provider, chunk_size=1)
        
        # Should be able to process without holding all nodes in memory
        node_count = 0
        for node in streaming_tree:
            node_count += 1
            # In real implementation, old nodes would be garbage collected
        
        assert node_count == len(self.tree_data)
    
    def test_streaming_statistics(self):
        """Test streaming processing statistics."""
        streaming_tree = StreamingTaxonomyTree(self.provider, chunk_size=2)
        
        # Process all nodes
        nodes = list(streaming_tree)
        
        stats = streaming_tree.get_processing_stats()
        
        assert 'nodes_processed' in stats
        assert 'chunks_processed' in stats
        assert 'memory_usage' in stats
        
        assert stats['nodes_processed'] == len(self.tree_data)


class TestMemoryOptimizationIntegration:
    """Integration tests for memory optimization features."""
    
    def test_lazy_tree_with_database_provider(self):
        """Test lazy tree with database-backed provider."""
        # Create test database
        temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        db_path = Path(temp_db.name)
        temp_db.close()
        
        try:
            # Setup database
            conn = sqlite3.connect(db_path)
            conn.execute("""
                CREATE TABLE nodes (
                    tax_id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    rank TEXT,
                    parent_id INTEGER
                )
            """)
            
            test_data = [
                (1, "root", "no rank", None),
                (2, "Bacteria", "superkingdom", 1),
                (3, "Firmicutes", "phylum", 2),
            ]
            conn.executemany("INSERT INTO nodes VALUES (?, ?, ?, ?)", test_data)
            conn.commit()
            conn.close()
            
            # Test lazy tree with database provider
            provider = MemoryEfficientNodeProvider(str(db_path))
            lazy_tree = LazyTaxonomyTree(provider, cache_size=5)
            
            # Test operations
            root = lazy_tree.get_node(1)
            assert root.name == "root"
            
            bacteria = lazy_tree.get_node(2)
            assert bacteria.name == "Bacteria"
            
            # Test caching works
            bacteria_cached = lazy_tree.get_node(2)
            assert bacteria == bacteria_cached
            assert lazy_tree.cache_hit_rate > 0
            
        finally:
            db_path.unlink()
    
    def test_memory_usage_comparison(self):
        """Test memory usage comparison between implementations."""
        # Create sample data
        tree_data = {i: {'name': f'Node_{i}', 'parent_id': i-1 if i > 1 else None} 
                    for i in range(1, 101)}
        provider = MockNodeProvider(tree_data)
        
        # Test lazy tree memory usage
        lazy_tree = LazyTaxonomyTree(provider, cache_size=10)
        
        # Load some nodes
        for i in range(1, 21):  # Load 20 nodes
            lazy_tree.get_node(i)
        
        stats = lazy_tree.memory_stats
        
        # Cache should be limited by cache_size
        assert stats['cached_nodes'] <= lazy_tree.cache_size
        assert stats['total_accesses'] >= 20
    
    def test_concurrent_memory_operations(self):
        """Test concurrent operations on memory-optimized structures."""
        tree_data = {i: {'name': f'Node_{i}', 'parent_id': i-1 if i > 1 else None} 
                    for i in range(1, 51)}
        provider = MockNodeProvider(tree_data)
        lazy_tree = LazyTaxonomyTree(provider, cache_size=20)
        
        results = []
        errors = []
        
        def worker():
            try:
                # Each worker accesses different nodes
                for i in range(1, 26):
                    node = lazy_tree.get_node(i)
                    if node:
                        results.append(node.tax_id)
                    time.sleep(0.001)  # Small delay to encourage race conditions
            except Exception as e:
                errors.append(e)
        
        # Run concurrent workers
        threads = []
        for _ in range(3):
            t = threading.Thread(target=worker)
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        # Check results
        assert len(errors) == 0, f"Concurrent access errors: {errors}"
        assert len(results) > 0
        
        # Verify cache statistics are consistent
        stats = lazy_tree.memory_stats
        assert stats['cached_nodes'] >= 0
        assert stats['total_accesses'] > 0