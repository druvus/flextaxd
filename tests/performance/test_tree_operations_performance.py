"""Performance tests for advanced tree operations."""

import time
import pytest
from typing import List

from flextaxd.core.models import (
    TaxonomyTree, TaxonomyNode, TaxonomicRank, GenomeInfo
)


class TestTreePerformance:
    """Performance benchmarks for tree operations."""
    
    @pytest.fixture
    def large_tree(self) -> TaxonomyTree:
        """Create a large tree for performance testing."""
        tree = TaxonomyTree()
        
        # Create tree with ~1000 nodes in structured hierarchy
        # Root -> 10 superkingdoms -> 10 phyla each -> 10 classes each
        
        # Add root
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT, parent_id=None)
        tree.add_node(root)
        
        node_id = 2
        
        # Add superkingdoms
        for sk in range(10):
            sk_node = TaxonomyNode(
                tax_id=node_id, 
                name=f"Superkingdom_{sk}", 
                rank=TaxonomicRank.SUPERKINGDOM, 
                parent_id=1
            )
            tree.add_node(sk_node)
            sk_id = node_id
            node_id += 1
            
            # Add phyla
            for p in range(10):
                p_node = TaxonomyNode(
                    tax_id=node_id,
                    name=f"Phylum_{sk}_{p}",
                    rank=TaxonomicRank.PHYLUM,
                    parent_id=sk_id
                )
                tree.add_node(p_node)
                p_id = node_id
                node_id += 1
                
                # Add classes
                for c in range(10):
                    c_node = TaxonomyNode(
                        tax_id=node_id,
                        name=f"Class_{sk}_{p}_{c}",
                        rank=TaxonomicRank.CLASS,
                        parent_id=p_id
                    )
                    tree.add_node(c_node)
                    node_id += 1
        
        return tree
    
    def test_lca_performance(self, large_tree: TaxonomyTree):
        """Benchmark LCA operations on large tree."""
        # Test LCA with various node pairs
        test_pairs = [
            (50, 150),   # Same superkingdom
            (50, 550),   # Different superkingdoms
            (100, 200),  # Adjacent phyla
            (999, 1001)  # Distant leaf nodes
        ]
        
        start_time = time.time()
        
        for _ in range(100):  # Multiple iterations
            for node1, node2 in test_pairs:
                lca = large_tree.lowest_common_ancestor(node1, node2)
                assert lca is not None
        
        end_time = time.time()
        elapsed = end_time - start_time
        
        print(f"LCA operations: {elapsed:.4f}s for 400 queries on {large_tree.node_count} nodes")
        
        # Should complete in reasonable time (< 1 second)
        assert elapsed < 1.0
    
    def test_distance_calculation_performance(self, large_tree: TaxonomyTree):
        """Benchmark taxonomic distance calculations."""
        # Test distance with various node pairs
        test_pairs = [(i, i + 100) for i in range(50, 150, 10)]  # 10 pairs
        
        start_time = time.time()
        
        for _ in range(50):  # Multiple iterations
            for node1, node2 in test_pairs:
                distance = large_tree.taxonomic_distance(node1, node2)
                assert distance is not None
        
        end_time = time.time()
        elapsed = end_time - start_time
        
        print(f"Distance calculations: {elapsed:.4f}s for 500 queries")
        
        # Should complete in reasonable time
        assert elapsed < 1.0
    
    def test_subtree_extraction_performance(self, large_tree: TaxonomyTree):
        """Benchmark subtree extraction operations."""
        # Extract subtrees at different levels
        extraction_points = [12, 23, 34, 45, 56]  # Various phylum nodes
        
        start_time = time.time()
        
        for point in extraction_points:
            subtree = large_tree.extract_subtree(point, preserve_tax_ids=True)
            # Each subtree should have 1 phylum + 10 classes = 11 nodes
            assert subtree.node_count == 11
        
        end_time = time.time()
        elapsed = end_time - start_time
        
        print(f"Subtree extraction: {elapsed:.4f}s for 5 extractions")
        
        # Should complete quickly
        assert elapsed < 0.5
    
    def test_tree_comparison_performance(self, large_tree: TaxonomyTree):
        """Benchmark tree comparison operations."""
        # Create a modified copy of the tree
        tree_copy = large_tree.extract_subtree(1, preserve_tax_ids=True)
        
        # Add a few different nodes to the copy
        for i in range(10):
            new_node = TaxonomyNode(
                tax_id=2000 + i,
                name=f"NewNode_{i}",
                rank=TaxonomicRank.SPECIES,
                parent_id=50 + i  # Various parents
            )
            tree_copy.add_node(new_node)
        
        start_time = time.time()
        
        # Compare trees
        comparison = large_tree.compare_trees(tree_copy)
        
        end_time = time.time()
        elapsed = end_time - start_time
        
        print(f"Tree comparison: {elapsed:.4f}s for {large_tree.node_count} vs {tree_copy.node_count} nodes")
        
        # Verify comparison results
        assert len(comparison['nodes_only_in_other']) == 10  # The new nodes
        assert len(comparison['nodes_in_both']) == large_tree.node_count
        
        # Should complete quickly even for large trees
        assert elapsed < 0.5
    
    def test_tree_statistics_performance(self, large_tree: TaxonomyTree):
        """Benchmark tree statistics calculation."""
        start_time = time.time()
        
        # Calculate statistics multiple times
        for _ in range(10):
            stats = large_tree.get_tree_statistics()
            assert stats['node_count'] == large_tree.node_count
            assert 'rank_distribution' in stats
            assert 'branching_factor_stats' in stats
        
        end_time = time.time()
        elapsed = end_time - start_time
        
        print(f"Statistics calculation: {elapsed:.4f}s for 10 calculations")
        
        # Should complete quickly
        assert elapsed < 0.5
    
    def test_memory_efficiency(self, large_tree: TaxonomyTree):
        """Test memory efficiency of tree operations."""
        import sys
        
        # Measure memory usage of tree
        initial_size = sys.getsizeof(large_tree)
        
        # Extract multiple subtrees (should not significantly increase memory)
        subtrees = []
        for i in range(5):
            subtree = large_tree.extract_subtree(50 + i * 10, preserve_tax_ids=False)
            subtrees.append(subtree)
        
        # Memory usage should be reasonable
        total_subtree_size = sum(sys.getsizeof(st) for st in subtrees)
        
        print(f"Original tree size: {initial_size} bytes")
        print(f"Total subtrees size: {total_subtree_size} bytes")
        
        # Subtrees should be much smaller than original
        assert total_subtree_size < initial_size
    
    @pytest.mark.slow
    def test_large_scale_operations(self):
        """Test operations on very large trees."""
        # Create an even larger tree (5000+ nodes)
        tree = TaxonomyTree()
        
        # Root
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT, parent_id=None)
        tree.add_node(root)
        
        node_id = 2
        
        # Create deeper hierarchy: 50 superkingdoms -> 20 phyla -> 5 classes
        for sk in range(50):
            sk_node = TaxonomyNode(
                tax_id=node_id, 
                name=f"SK_{sk}", 
                rank=TaxonomicRank.SUPERKINGDOM, 
                parent_id=1
            )
            tree.add_node(sk_node)
            sk_id = node_id
            node_id += 1
            
            for p in range(20):
                p_node = TaxonomyNode(
                    tax_id=node_id,
                    name=f"P_{sk}_{p}",
                    rank=TaxonomicRank.PHYLUM,
                    parent_id=sk_id
                )
                tree.add_node(p_node)
                p_id = node_id
                node_id += 1
                
                for c in range(5):
                    c_node = TaxonomyNode(
                        tax_id=node_id,
                        name=f"C_{sk}_{p}_{c}",
                        rank=TaxonomicRank.CLASS,
                        parent_id=p_id
                    )
                    tree.add_node(c_node)
                    node_id += 1
        
        print(f"Created large tree with {tree.node_count} nodes")
        
        # Test that operations still complete in reasonable time
        start_time = time.time()
        
        # LCA of distant nodes
        lca = tree.lowest_common_ancestor(1000, 4000)
        assert lca is not None
        
        # Distance calculation
        distance = tree.taxonomic_distance(2000, 3000)
        assert distance is not None
        
        # Statistics
        stats = tree.get_tree_statistics()
        assert stats['node_count'] == tree.node_count
        
        end_time = time.time()
        elapsed = end_time - start_time
        
        print(f"Large scale operations: {elapsed:.4f}s on {tree.node_count} nodes")
        
        # Should still complete in reasonable time
        assert elapsed < 2.0  # Allow more time for very large trees


class TestTreeOperationsScalability:
    """Test scalability characteristics of tree operations."""
    
    def create_balanced_tree(self, depth: int, branching_factor: int) -> TaxonomyTree:
        """Create a balanced tree with specified depth and branching factor."""
        tree = TaxonomyTree()
        
        # Add root
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT, parent_id=None)
        tree.add_node(root)
        
        current_level = [1]
        node_id = 2
        
        ranks = [TaxonomicRank.SUPERKINGDOM, TaxonomicRank.PHYLUM, 
                TaxonomicRank.CLASS, TaxonomicRank.ORDER, TaxonomicRank.FAMILY]
        
        for level in range(depth - 1):
            next_level = []
            rank = ranks[level] if level < len(ranks) else TaxonomicRank.SPECIES
            
            for parent_id in current_level:
                for _ in range(branching_factor):
                    child_node = TaxonomyNode(
                        tax_id=node_id,
                        name=f"Node_{node_id}",
                        rank=rank,
                        parent_id=parent_id
                    )
                    tree.add_node(child_node)
                    next_level.append(node_id)
                    node_id += 1
            
            current_level = next_level
        
        return tree
    
    def test_depth_vs_lca_performance(self):
        """Test how tree depth affects LCA performance."""
        depths = [3, 4, 5]
        branching_factor = 3
        
        for depth in depths:
            tree = self.create_balanced_tree(depth, branching_factor)
            
            # Test LCA on leaf nodes (worst case)
            leaf_nodes = [node.tax_id for node in tree if len(tree.get_children(node.tax_id)) == 0]
            
            start_time = time.time()
            
            # Test 10 LCA operations
            for i in range(0, min(10, len(leaf_nodes) - 1)):
                lca = tree.lowest_common_ancestor(leaf_nodes[i], leaf_nodes[i + 1])
                assert lca is not None
            
            end_time = time.time()
            elapsed = end_time - start_time
            
            print(f"Depth {depth}: {elapsed:.4f}s for LCA on {tree.node_count} nodes")
    
    def test_branching_factor_vs_performance(self):
        """Test how branching factor affects performance."""
        depth = 4
        branching_factors = [2, 3, 5]
        
        for bf in branching_factors:
            tree = self.create_balanced_tree(depth, bf)
            
            start_time = time.time()
            
            # Test multiple operations
            stats = tree.get_tree_statistics()
            
            # Test LCA
            lca = tree.lowest_common_ancestor(5, 10)
            
            # Test distance
            distance = tree.taxonomic_distance(3, 8)
            
            end_time = time.time()
            elapsed = end_time - start_time
            
            print(f"Branching factor {bf}: {elapsed:.4f}s on {tree.node_count} nodes")
            
            # Verify correctness
            assert stats['node_count'] == tree.node_count
            assert lca is not None
            assert distance is not None