"""Performance benchmarks for memory optimization features."""

import pytest
import time
import tempfile
import sqlite3
from pathlib import Path
import psutil
import os
from typing import List

from flextaxd.core.memory_optimized_tree import (
    LazyTaxonomyTree, StreamingTaxonomyTree, MemoryEfficientNodeProvider,
    MemoryOptimizedOperations, create_memory_optimized_tree, create_streaming_tree
)
from flextaxd.core.models import TaxonomyNode, TaxonomicRank, TaxonomyTree


class TestMemoryOptimizationPerformance:
    """Performance benchmarks for memory optimization."""
    
    @pytest.fixture
    def large_test_database(self):
        """Create large test database for performance testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create schema
        cursor.execute("""
            CREATE TABLE nodes (
                tax_id INTEGER PRIMARY KEY,
                name TEXT,
                rank TEXT,
                parent_id INTEGER
            )
        """)
        
        # Create indices for performance
        cursor.execute("CREATE INDEX idx_parent_id ON nodes(parent_id)")
        cursor.execute("CREATE INDEX idx_rank ON nodes(rank)")
        
        # Generate hierarchical test data: 10 kingdoms -> 50 phyla each -> 20 classes each
        node_id = 1
        
        # Root
        cursor.execute(
            "INSERT INTO nodes (tax_id, name, rank, parent_id) VALUES (?, ?, ?, ?)",
            (1, "root", "root", 1)
        )
        node_id = 2
        
        # Kingdoms
        kingdom_ids = []
        for k in range(10):
            cursor.execute(
                "INSERT INTO nodes (tax_id, name, rank, parent_id) VALUES (?, ?, ?, ?)",
                (node_id, f"Kingdom_{k}", "kingdom", 1)
            )
            kingdom_ids.append(node_id)
            node_id += 1
        
        # Phyla under each kingdom
        phylum_ids = []
        for kingdom_id in kingdom_ids:
            for p in range(50):
                cursor.execute(
                    "INSERT INTO nodes (tax_id, name, rank, parent_id) VALUES (?, ?, ?, ?)",
                    (node_id, f"Phylum_{kingdom_id}_{p}", "phylum", kingdom_id)
                )
                phylum_ids.append(node_id)
                node_id += 1
        
        # Classes under each phylum
        for phylum_id in phylum_ids:
            for c in range(20):
                cursor.execute(
                    "INSERT INTO nodes (tax_id, name, rank, parent_id) VALUES (?, ?, ?, ?)",
                    (node_id, f"Class_{phylum_id}_{c}", "class", phylum_id)
                )
                node_id += 1
        
        conn.commit()
        conn.close()
        
        print(f"Created test database with {node_id-1} nodes")
        
        yield db_path
        Path(db_path).unlink()
    
    def create_regular_tree(self, db_path: str) -> TaxonomyTree:
        """Create regular (non-optimized) tree by loading all nodes."""
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT tax_id, name, rank, parent_id FROM nodes")
        
        tree = TaxonomyTree()
        
        # Load all nodes
        for row in cursor:
            tax_id, name, rank, parent_id = row
            
            try:
                taxonomic_rank = TaxonomicRank(rank) if rank else TaxonomicRank.CUSTOM
            except ValueError:
                taxonomic_rank = TaxonomicRank.CUSTOM
            
            # Handle root node special case
            if parent_id == tax_id:
                parent_id = None
            
            node = TaxonomyNode(
                tax_id=tax_id,
                name=name,
                rank=taxonomic_rank,
                parent_id=parent_id
            )
            tree.add_node(node)
        
        conn.close()
        return tree
    
    def get_process_memory_mb(self) -> float:
        """Get current process memory usage in MB."""
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024
    
    def test_memory_usage_comparison(self, large_test_database):
        """Compare memory usage between regular and optimized trees."""
        print("\\n=== Memory Usage Comparison ===")
        
        # Measure baseline memory
        baseline_memory = self.get_process_memory_mb()
        
        # Test regular tree (loads everything)
        start_memory = self.get_process_memory_mb()
        regular_tree = self.create_regular_tree(large_test_database)
        regular_memory = self.get_process_memory_mb() - start_memory
        
        print(f"Regular tree memory usage: {regular_memory:.2f} MB")
        print(f"Regular tree nodes: {regular_tree.node_count}")
        
        # Clear regular tree
        del regular_tree
        
        # Test memory-optimized tree
        start_memory = self.get_process_memory_mb()
        optimized_tree = create_memory_optimized_tree(large_test_database, cache_size=100)
        
        # Access some nodes to trigger loading
        for i in range(1, 101):  # Access first 100 nodes
            optimized_tree.get_node(i)
        
        optimized_memory = self.get_process_memory_mb() - start_memory
        
        print(f"Optimized tree memory usage: {optimized_memory:.2f} MB")
        print(f"Optimized tree cached nodes: {len(optimized_tree._node_cache)}")
        print(f"Memory reduction: {((regular_memory - optimized_memory) / regular_memory * 100):.1f}%")
        
        # Optimized tree should use significantly less memory
        assert optimized_memory < regular_memory * 0.3  # At least 70% reduction
    
    def test_cache_performance(self, large_test_database):
        """Test cache performance characteristics."""
        print("\\n=== Cache Performance Test ===")
        
        tree = create_memory_optimized_tree(large_test_database, cache_size=200)
        
        # Test cache warming
        start_time = time.time()
        for i in range(1, 201):
            tree.get_node(i)
        cache_warm_time = time.time() - start_time
        
        # Test cached access
        start_time = time.time()
        for i in range(1, 201):
            tree.get_node(i)
        cached_access_time = time.time() - start_time
        
        print(f"Cache warming time: {cache_warm_time:.4f}s")
        print(f"Cached access time: {cached_access_time:.4f}s")
        print(f"Cache speedup: {cache_warm_time / cached_access_time:.1f}x")
        
        stats = tree.memory_stats
        print(f"Cache hit rate: {stats['cache_hit_rate']:.1f}%")
        print(f"Memory efficiency: {stats['memory_efficiency']:.2f}")
        
        # Cached access should be much faster
        assert cached_access_time < cache_warm_time * 0.1  # At least 10x faster
        assert stats['cache_hit_rate'] > 95  # Very high hit rate
    
    def test_lca_performance_comparison(self, large_test_database):
        """Compare LCA performance between regular and optimized trees."""
        print("\\n=== LCA Performance Comparison ===")
        
        # Create both trees
        regular_tree = self.create_regular_tree(large_test_database)
        optimized_tree = create_memory_optimized_tree(large_test_database, cache_size=500)
        
        # Test nodes at different depths
        test_pairs = [
            (12, 13),      # Same kingdom
            (62, 312),     # Different kingdoms, same depth  
            (5000, 8000),  # Deep nodes in different subtrees
            (100, 5000)    # Shallow vs deep
        ]
        
        # Test regular tree LCA
        start_time = time.time()
        for _ in range(10):  # Multiple iterations for stable timing
            for node1, node2 in test_pairs:
                lca = regular_tree.lowest_common_ancestor(node1, node2)
                assert lca is not None
        regular_lca_time = time.time() - start_time
        
        # Test optimized tree LCA
        start_time = time.time()
        for _ in range(10):
            for node1, node2 in test_pairs:
                lca = optimized_tree.lowest_common_ancestor(node1, node2)
                assert lca is not None
        optimized_lca_time = time.time() - start_time
        
        print(f"Regular tree LCA time: {regular_lca_time:.4f}s")
        print(f"Optimized tree LCA time: {optimized_lca_time:.4f}s")
        
        if optimized_lca_time > 0:
            ratio = regular_lca_time / optimized_lca_time
            print(f"Performance ratio: {ratio:.1f}x")
        
        # Print cache statistics
        stats = optimized_tree.memory_stats
        print(f"Final cache hit rate: {stats['cache_hit_rate']:.1f}%")
    
    def test_streaming_memory_efficiency(self, large_test_database):
        """Test streaming operations for memory efficiency."""
        print("\\n=== Streaming Memory Efficiency ===")
        
        streaming_tree = create_streaming_tree(large_test_database)
        
        # Measure memory during streaming
        start_memory = self.get_process_memory_mb()
        
        # Stream all nodes by rank
        species_count = 0
        phylum_count = 0
        
        for node in streaming_tree.stream_by_rank(TaxonomicRank.PHYLUM):
            phylum_count += 1
        
        streaming_memory = self.get_process_memory_mb() - start_memory
        
        print(f"Streaming memory usage: {streaming_memory:.2f} MB")
        print(f"Phyla found: {phylum_count}")
        
        # Estimate memory usage
        usage = streaming_tree.estimate_memory_usage(max_concurrent_nodes=50)
        print(f"Estimated usage for 50 nodes: {usage['estimated_bytes']} bytes")
        
        # Streaming should use minimal memory
        assert streaming_memory < 10  # Should use less than 10MB
    
    def test_batch_operations_performance(self, large_test_database):
        """Test performance of batch operations."""
        print("\\n=== Batch Operations Performance ===")
        
        optimized_tree = create_memory_optimized_tree(large_test_database, cache_size=300)
        memory_ops = MemoryOptimizedOperations(optimized_tree)
        
        # Generate many LCA pairs
        test_pairs = []
        for i in range(50, 150):
            for j in range(i + 100, i + 150):
                test_pairs.append((i, j))
        
        print(f"Testing {len(test_pairs)} LCA pairs")
        
        # Test batch LCA
        start_time = time.time()
        results = list(memory_ops.batch_lca(test_pairs, batch_size=25))
        batch_time = time.time() - start_time
        
        print(f"Batch LCA time: {batch_time:.4f}s")
        print(f"LCAs per second: {len(results) / batch_time:.0f}")
        
        # Verify results
        successful_lcas = sum(1 for (_, lca) in results if lca is not None)
        print(f"Successful LCAs: {successful_lcas}/{len(results)}")
        
        assert len(results) == len(test_pairs)
        assert successful_lcas > 0
    
    def test_distance_matrix_streaming(self, large_test_database):
        """Test streaming distance matrix computation."""
        print("\\n=== Distance Matrix Streaming ===")
        
        optimized_tree = create_memory_optimized_tree(large_test_database, cache_size=200)
        memory_ops = MemoryOptimizedOperations(optimized_tree)
        
        # Select nodes from different kingdoms
        test_nodes = [12, 13, 62, 112, 162, 212, 262]  # 7 nodes = 21 pairs
        
        start_memory = self.get_process_memory_mb()
        start_time = time.time()
        
        distances = list(memory_ops.streaming_distance_matrix(test_nodes))
        
        end_time = time.time()
        end_memory = self.get_process_memory_mb()
        
        print(f"Distance matrix computation time: {end_time - start_time:.4f}s")
        print(f"Memory usage during computation: {end_memory - start_memory:.2f} MB")
        print(f"Distances computed: {len(distances)}")
        
        # Verify results
        valid_distances = [d for (_, _, d) in distances if d is not None]
        print(f"Valid distances: {len(valid_distances)}/{len(distances)}")
        
        expected_pairs = len(test_nodes) * (len(test_nodes) - 1) // 2
        assert len(distances) == expected_pairs
    
    def test_subtree_stats_efficiency(self, large_test_database):
        """Test memory-efficient subtree statistics."""
        print("\\n=== Subtree Statistics Efficiency ===")
        
        optimized_tree = create_memory_optimized_tree(large_test_database, cache_size=150)
        memory_ops = MemoryOptimizedOperations(optimized_tree)
        
        # Test on different subtree sizes
        test_roots = [2, 12, 62]  # Kingdom, phylum roots
        
        for root_id in test_roots:
            start_memory = self.get_process_memory_mb()
            start_time = time.time()
            
            stats = memory_ops.memory_efficient_subtree_stats(root_id)
            
            end_time = time.time()
            end_memory = self.get_process_memory_mb()
            
            print(f"\\nSubtree {root_id} statistics:")
            print(f"  Nodes: {stats['node_count']}")
            print(f"  Max depth: {stats['max_depth']}")
            print(f"  Leaves: {stats['leaf_count']}")
            print(f"  Computation time: {end_time - start_time:.4f}s")
            print(f"  Memory usage: {end_memory - start_memory:.2f} MB")
            
            # Verify statistics make sense
            assert stats['node_count'] > 0
            assert stats['max_depth'] >= 0
            assert stats['leaf_count'] >= 0
    
    @pytest.mark.slow
    def test_large_scale_memory_optimization(self, large_test_database):
        """Test memory optimization on very large operations."""
        print("\\n=== Large Scale Memory Optimization ===")
        
        # Test with small cache on large tree
        tree = create_memory_optimized_tree(large_test_database, cache_size=50)
        
        # Perform many random accesses
        import random
        node_ids = list(range(1, 1001))  # First 1000 nodes
        random.shuffle(node_ids)
        
        start_time = time.time()
        start_memory = self.get_process_memory_mb()
        
        for node_id in node_ids:
            tree.get_node(node_id)
        
        end_time = time.time()
        end_memory = self.get_process_memory_mb()
        
        print(f"Random access time: {end_time - start_time:.4f}s")
        print(f"Memory usage: {end_memory - start_memory:.2f} MB")
        
        stats = tree.memory_stats
        print(f"Cache efficiency: {stats['memory_efficiency']:.3f}")
        print(f"Cache hit rate: {stats['cache_hit_rate']:.1f}%")
        print(f"Nodes loaded: {stats['nodes_loaded']}")
        
        # Should maintain reasonable performance with limited memory
        assert end_memory - start_memory < 20  # Less than 20MB
        assert stats['cached_nodes'] <= 50  # Respects cache limit


class TestMemoryOptimizationScalability:
    """Test how memory optimizations scale with tree size."""
    
    def create_scalable_database(self, depth: int, branching_factor: int) -> str:
        """Create database with specific structure for scalability testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE nodes (
                tax_id INTEGER PRIMARY KEY,
                name TEXT,
                rank TEXT,
                parent_id INTEGER
            )
        """)
        
        # Create tree level by level
        node_id = 1
        current_level = [1]
        
        # Root
        cursor.execute(
            "INSERT INTO nodes (tax_id, name, rank, parent_id) VALUES (1, 'root', 'root', 1)"
        )
        node_id = 2
        
        ranks = ['kingdom', 'phylum', 'class', 'order', 'family', 'genus', 'species']
        
        for level in range(depth - 1):
            next_level = []
            rank = ranks[level] if level < len(ranks) else 'species'
            
            for parent_id in current_level:
                for _ in range(branching_factor):
                    cursor.execute(
                        "INSERT INTO nodes (tax_id, name, rank, parent_id) VALUES (?, ?, ?, ?)",
                        (node_id, f"Node_{node_id}", rank, parent_id)
                    )
                    next_level.append(node_id)
                    node_id += 1
            
            current_level = next_level
        
        conn.commit()
        conn.close()
        
        return db_path
    
    def test_cache_size_vs_performance(self):
        """Test how cache size affects performance."""
        print("\\n=== Cache Size vs Performance ===")
        
        # Create test database
        db_path = self.create_scalable_database(depth=5, branching_factor=3)
        
        try:
            cache_sizes = [10, 50, 100, 200]
            results = []
            
            for cache_size in cache_sizes:
                tree = create_memory_optimized_tree(db_path, cache_size=cache_size)
                
                # Test random access pattern
                start_time = time.time()
                for i in range(1, 101):  # Access first 100 nodes
                    tree.get_node(i)
                end_time = time.time()
                
                stats = tree.memory_stats
                results.append({
                    'cache_size': cache_size,
                    'time': end_time - start_time,
                    'hit_rate': stats['cache_hit_rate'],
                    'efficiency': stats['memory_efficiency']
                })
                
                print(f"Cache size {cache_size}: {end_time - start_time:.4f}s, "
                      f"hit rate: {stats['cache_hit_rate']:.1f}%")
            
            # Verify that larger caches generally perform better
            assert results[-1]['hit_rate'] >= results[0]['hit_rate']
            
        finally:
            Path(db_path).unlink()
    
    def test_depth_vs_memory_usage(self):
        """Test how tree depth affects memory optimization."""
        print("\\n=== Tree Depth vs Memory Usage ===")
        
        depths = [3, 4, 5]
        branching_factor = 4
        
        for depth in depths:
            db_path = self.create_scalable_database(depth, branching_factor)
            
            try:
                tree = create_memory_optimized_tree(db_path, cache_size=100)
                
                # Test path to root on deepest nodes
                start_memory = self.get_process_memory_mb()
                
                # Find leaf nodes and test paths
                leaf_count = 0
                for i in range(2, min(500, 4**depth)):  # Sample of nodes
                    if not tree.get_children(i):  # Leaf node
                        path = tree.get_path_to_root(i)
                        assert len(path) == depth
                        leaf_count += 1
                        if leaf_count >= 10:  # Test 10 leaves
                            break
                
                end_memory = self.get_process_memory_mb()
                stats = tree.memory_stats
                
                print(f"Depth {depth}: {end_memory - start_memory:.2f} MB, "
                      f"efficiency: {stats['memory_efficiency']:.3f}")
                
            finally:
                Path(db_path).unlink()
    
    def get_process_memory_mb(self) -> float:
        """Get current process memory usage in MB."""
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024