"""Performance and stress tests for purge functionality."""

import pytest
import time
import tempfile
import shutil
from pathlib import Path
import random
import string
from memory_profiler import profile
import psutil
import os

from flextaxd.database.sqlite import SQLiteTaxonomyRepository
from flextaxd.core.models import TaxonomyTree, TaxonomyNode, GenomeInfo, TaxonomicRank


class TestPurgePerformance:
    """Performance and stress tests for purge functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        
    def teardown_method(self):
        """Clean up test fixtures."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def _generate_random_string(self, length=10):
        """Generate random string for names."""
        return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

    def _create_large_tree(self, num_nodes=10000, genome_probability=0.1):
        """Create large taxonomy tree for performance testing."""
        tree = TaxonomyTree()
        
        # Create root
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT)
        tree.add_node(root)
        
        # Create nodes in breadth-first manner for realistic tree structure
        nodes_to_create = [(1, 2)]  # (parent_id, start_child_id)
        current_id = 2
        nodes_created = 1
        
        ranks = [
            TaxonomicRank.SUPERKINGDOM, TaxonomicRank.PHYLUM, TaxonomicRank.CLASS,
            TaxonomicRank.ORDER, TaxonomicRank.FAMILY, TaxonomicRank.GENUS,
            TaxonomicRank.SPECIES
        ]
        
        while nodes_created < num_nodes and nodes_to_create:
            parent_id, child_start = nodes_to_create.pop(0)
            parent_node = tree.get_node(parent_id)
            parent_rank_idx = ranks.index(parent_node.rank) if parent_node.rank in ranks else 0
            
            # Create 2-8 children per node, ensuring valid range
            max_children = max(2, min(8, (num_nodes - nodes_created)))
            num_children = random.randint(2, max_children) if max_children > 2 else 2
            
            for i in range(num_children):
                if nodes_created >= num_nodes:
                    break
                    
                child_id = current_id
                current_id += 1
                nodes_created += 1
                
                # Select appropriate rank for child
                if parent_rank_idx < len(ranks) - 1:
                    child_rank = ranks[parent_rank_idx + 1]
                else:
                    child_rank = TaxonomicRank.SPECIES
                
                child_name = f"Node_{child_id}_{self._generate_random_string(8)}"
                child_node = TaxonomyNode(
                    tax_id=child_id,
                    name=child_name,
                    rank=child_rank,
                    parent_id=parent_id
                )
                
                tree.add_node(child_node)
                
                # Add to queue for further expansion (if not at species level)
                if child_rank != TaxonomicRank.SPECIES and nodes_created < num_nodes:
                    nodes_to_create.append((child_id, current_id))
                
                # Randomly add genomes
                if random.random() < genome_probability:
                    has_file = random.random() < 0.7  # 70% chance of having file
                    
                    genome = GenomeInfo(
                        genome_id=f"genome_{child_id}_{self._generate_random_string(6)}",
                        tax_id=child_id,
                        file_path=f"/genomes/genome_{child_id}.fasta" if has_file else None,
                        sequence_length=random.randint(500000, 10000000),
                        sequence_type=random.choice(["genome", "16S", "plasmid", "chromosome"]),
                        assembly_accession=f"GCF_{child_id:09d}.1" if random.random() < 0.8 else None,
                        source=random.choice(["NCBI", "GTDB", "SILVA", "TEST"])
                    )
                    tree.add_genome(genome)
        
        return tree

    def test_purge_performance_10k_nodes(self):
        """Test purge performance with 10,000 nodes."""
        tree = self._create_large_tree(num_nodes=10000, genome_probability=0.05)
        
        print(f"Created tree with {len(tree._nodes)} nodes and {len(tree._genomes)} genomes")
        
        # Measure purge performance
        start_time = time.time()
        result = tree.purge_nodes_without_genomes(require_fasta_files=True)
        end_time = time.time()
        
        purge_time = end_time - start_time
        print(f"Purge completed in {purge_time:.3f} seconds")
        print(f"Nodes removed: {result['nodes_removed']}")
        print(f"Nodes remaining: {result['nodes_after']}")
        print(f"Genomes retained: {result['genomes_retained']}")
        
        # Performance requirements
        assert purge_time < 10.0, f"Purge took {purge_time:.3f}s, expected < 10s"
        assert result["nodes_before"] == len(tree._nodes) + result["nodes_removed"]
        assert result["nodes_after"] == len(tree._nodes)

    def test_purge_performance_50k_nodes(self):
        """Test purge performance with 50,000 nodes (stress test)."""
        if os.environ.get('SKIP_STRESS_TESTS'):
            pytest.skip("Stress tests disabled")
            
        tree = self._create_large_tree(num_nodes=50000, genome_probability=0.02)
        
        print(f"Created large tree with {len(tree._nodes)} nodes and {len(tree._genomes)} genomes")
        
        # Measure memory before
        process = psutil.Process()
        memory_before = process.memory_info().rss / 1024 / 1024  # MB
        
        start_time = time.time()
        result = tree.purge_nodes_without_genomes(require_fasta_files=True)
        end_time = time.time()
        
        # Measure memory after
        memory_after = process.memory_info().rss / 1024 / 1024  # MB
        
        purge_time = end_time - start_time
        print(f"Large purge completed in {purge_time:.3f} seconds")
        print(f"Memory usage: {memory_before:.1f}MB -> {memory_after:.1f}MB")
        print(f"Nodes removed: {result['nodes_removed']}")
        print(f"Nodes remaining: {result['nodes_after']}")
        
        # Performance requirements for large dataset
        assert purge_time < 30.0, f"Large purge took {purge_time:.3f}s, expected < 30s"
        assert memory_after < memory_before + 500, "Memory usage increased too much"

    def test_purge_performance_deep_tree(self):
        """Test purge performance with very deep tree (1000 levels)."""
        tree = TaxonomyTree()
        
        # Create linear deep tree
        parent_id = None
        for i in range(1, 1001):
            node = TaxonomyNode(
                tax_id=i,
                name=f"Level_{i}",
                rank=TaxonomicRank.SPECIES if i > 100 else TaxonomicRank.GENUS,
                parent_id=parent_id
            )
            tree.add_node(node)
            parent_id = i
        
        # Add genome only to deepest node
        genome = GenomeInfo(
            genome_id="deep_genome",
            tax_id=1000,
            file_path="/deep/genome.fasta",
            sequence_type="genome",
            source="TEST"
        )
        tree.add_genome(genome)
        
        print(f"Created deep tree with {len(tree._nodes)} nodes")
        
        start_time = time.time()
        result = tree.purge_nodes_without_genomes(require_fasta_files=True)
        end_time = time.time()
        
        purge_time = end_time - start_time
        print(f"Deep tree purge completed in {purge_time:.3f} seconds")
        
        # Should keep entire lineage (no removal)
        assert result["nodes_removed"] == 0
        assert result["nodes_after"] == 1000
        assert purge_time < 5.0, f"Deep tree purge took {purge_time:.3f}s, expected < 5s"

    def test_purge_performance_wide_tree(self):
        """Test purge performance with very wide tree (10,000 siblings)."""
        tree = TaxonomyTree()
        
        # Create root
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT)
        tree.add_node(root)
        
        # Create 10,000 direct children
        genome_nodes = set()
        for i in range(2, 10002):
            node = TaxonomyNode(
                tax_id=i,
                name=f"Child_{i}",
                rank=TaxonomicRank.SPECIES,
                parent_id=1
            )
            tree.add_node(node)
            
            # Add genomes to every 100th node
            if i % 100 == 0:
                genome_nodes.add(i)
                genome = GenomeInfo(
                    genome_id=f"genome_{i}",
                    tax_id=i,
                    file_path=f"/genomes/{i}.fasta",
                    sequence_type="genome",
                    source="TEST"
                )
                tree.add_genome(genome)
        
        print(f"Created wide tree with {len(tree._nodes)} nodes and {len(tree._genomes)} genomes")
        
        start_time = time.time()
        result = tree.purge_nodes_without_genomes(require_fasta_files=False, force=True)
        end_time = time.time()
        
        purge_time = end_time - start_time
        print(f"Wide tree purge completed in {purge_time:.3f} seconds")
        
        # Should keep root + nodes with genomes
        expected_remaining = len(genome_nodes) + 1  # +1 for root
        assert result["nodes_after"] == expected_remaining
        assert result["nodes_removed"] == 10001 - expected_remaining
        assert purge_time < 5.0, f"Wide tree purge took {purge_time:.3f}s, expected < 5s"

    def test_purge_performance_many_genomes_per_node(self):
        """Test purge performance with many genomes per node."""
        tree = TaxonomyTree()
        
        # Create small tree
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT)
        tree.add_node(root)
        
        for i in range(2, 102):  # 100 species
            species = TaxonomyNode(tax_id=i, name=f"Species_{i}", rank=TaxonomicRank.SPECIES, parent_id=1)
            tree.add_node(species)
            
            # Add many genomes to each species (100 genomes each)
            for j in range(100):
                genome = GenomeInfo(
                    genome_id=f"genome_{i}_{j}",
                    tax_id=i,
                    file_path=f"/genomes/species_{i}/genome_{j}.fasta" if j % 2 == 0 else None,
                    sequence_length=random.randint(1000000, 8000000),
                    sequence_type=random.choice(["genome", "plasmid", "16S"]),
                    source="TEST"
                )
                tree.add_genome(genome)
        
        print(f"Created tree with {len(tree._nodes)} nodes and {len(tree._genomes)} genomes")
        
        start_time = time.time()
        result = tree.purge_nodes_without_genomes(require_fasta_files=True)
        end_time = time.time()
        
        purge_time = end_time - start_time
        print(f"Many genomes purge completed in {purge_time:.3f} seconds")
        
        # All species should be kept (each has at least some genomes with files)
        assert result["nodes_removed"] == 0
        assert result["nodes_after"] == 101  # root + 100 species
        assert purge_time < 3.0, f"Many genomes purge took {purge_time:.3f}s, expected < 3s"

    def test_purge_database_performance(self):
        """Test purge performance with actual database operations."""
        db_path = self.temp_dir / "perf_test.ftd"
        
        # Create moderately large tree
        tree = self._create_large_tree(num_nodes=5000, genome_probability=0.08)
        
        # Save to database
        save_start = time.time()
        with SQLiteTaxonomyRepository(str(db_path)) as repo:
            repo.save_tree(tree)
        save_time = time.time() - save_start
        
        print(f"Database save time: {save_time:.3f} seconds")
        
        # Load and purge
        load_start = time.time()
        with SQLiteTaxonomyRepository(str(db_path)) as repo:
            loaded_tree = repo.load_tree()
            load_time = time.time() - load_start
            
            purge_start = time.time()
            result = loaded_tree.purge_nodes_without_genomes(require_fasta_files=True)
            purge_time = time.time() - purge_start
            
            save_start = time.time()
            repo.save_tree(loaded_tree)
            save_back_time = time.time() - save_start
        
        print(f"Database load time: {load_time:.3f} seconds")
        print(f"Purge time: {purge_time:.3f} seconds") 
        print(f"Save back time: {save_back_time:.3f} seconds")
        print(f"Total time: {load_time + purge_time + save_back_time:.3f} seconds")
        
        # Performance requirements
        assert load_time < 10.0, f"Database load took {load_time:.3f}s"
        assert purge_time < 10.0, f"Purge took {purge_time:.3f}s"
        assert save_back_time < 10.0, f"Save took {save_back_time:.3f}s"

    def test_purge_memory_efficiency(self):
        """Test purge memory efficiency with large dataset."""
        if os.environ.get('SKIP_MEMORY_TESTS'):
            pytest.skip("Memory tests disabled")
            
        tree = self._create_large_tree(num_nodes=20000, genome_probability=0.03)
        
        process = psutil.Process()
        memory_before = process.memory_info().rss / 1024 / 1024
        
        # Force garbage collection before test
        import gc
        gc.collect()
        
        result = tree.purge_nodes_without_genomes(require_fasta_files=True)
        
        # Force garbage collection after purge
        gc.collect()
        
        memory_after = process.memory_info().rss / 1024 / 1024
        memory_delta = memory_after - memory_before
        
        print(f"Memory usage: {memory_before:.1f}MB -> {memory_after:.1f}MB (Δ{memory_delta:+.1f}MB)")
        print(f"Nodes purged: {result['nodes_removed']} of {result['nodes_before']}")
        
        # Memory should not increase dramatically during purge
        assert memory_delta < 200, f"Memory increased by {memory_delta:.1f}MB during purge"

    def test_purge_concurrent_safety(self):
        """Test purge behavior under concurrent-like conditions."""
        tree = self._create_large_tree(num_nodes=1000, genome_probability=0.1)
        
        # Simulate concurrent modifications by calling purge multiple times
        results = []
        for i in range(5):
            # Create copy for each purge attempt
            import copy
            tree_copy = copy.deepcopy(tree)
            
            start_time = time.time()
            result = tree_copy.purge_nodes_without_genomes(require_fasta_files=True)
            end_time = time.time()
            
            results.append((result, end_time - start_time))
        
        # All results should be identical (deterministic)
        base_result = results[0][0]
        for result, time_taken in results[1:]:
            assert result["nodes_removed"] == base_result["nodes_removed"]
            assert result["nodes_after"] == base_result["nodes_after"]
            assert result["genomes_retained"] == base_result["genomes_retained"]
            assert time_taken < 5.0  # Should be consistently fast

    def test_purge_edge_case_performance(self):
        """Test purge performance with edge cases."""
        # Test 1: All nodes have genomes (no removal)
        tree1 = TaxonomyTree()
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT)
        tree1.add_node(root)
        
        for i in range(2, 1002):  # 1000 nodes
            node = TaxonomyNode(tax_id=i, name=f"Node_{i}", rank=TaxonomicRank.SPECIES, parent_id=1)
            tree1.add_node(node)
            
            genome = GenomeInfo(
                genome_id=f"genome_{i}",
                tax_id=i,
                file_path=f"/genomes/{i}.fasta",
                sequence_type="genome",
                source="TEST"
            )
            tree1.add_genome(genome)
        
        start_time = time.time()
        result1 = tree1.purge_nodes_without_genomes()
        time1 = time.time() - start_time
        
        assert result1["nodes_removed"] == 0
        assert time1 < 2.0, f"No-removal case took {time1:.3f}s"
        
        # Test 2: Almost all nodes removed (single survivor)
        tree2 = TaxonomyTree()
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT)
        tree2.add_node(root)
        
        survivor_id = 2
        survivor = TaxonomyNode(tax_id=survivor_id, name="Survivor", rank=TaxonomicRank.SPECIES, parent_id=1)
        tree2.add_node(survivor)
        
        genome = GenomeInfo(
            genome_id="survivor_genome",
            tax_id=survivor_id,
            file_path="/survivor.fasta",
            sequence_type="genome",
            source="TEST"
        )
        tree2.add_genome(genome)
        
        # Add 1000 nodes without genomes
        for i in range(3, 1003):
            node = TaxonomyNode(tax_id=i, name=f"Victim_{i}", rank=TaxonomicRank.SPECIES, parent_id=1)
            tree2.add_node(node)
        
        start_time = time.time()
        result2 = tree2.purge_nodes_without_genomes(force=True)
        time2 = time.time() - start_time
        
        assert result2["nodes_removed"] == 1000
        assert result2["nodes_after"] == 2  # root + survivor
        assert time2 < 3.0, f"Mass-removal case took {time2:.3f}s"
        
        print(f"Edge case performance: no-removal={time1:.3f}s, mass-removal={time2:.3f}s")