"""Performance tests for production-scale datasets optimization."""

import pytest
import time
import tempfile
import sqlite3
from pathlib import Path
from typing import List

from flextaxd.core.models import TaxonomyTree, TaxonomyNode, TaxonomicRank, GenomeInfo
from flextaxd.database.sqlite import SQLiteTaxonomyRepository


class TestProductionScalePerformance:
    """Test performance optimizations for production-scale datasets."""

    @pytest.fixture
    def large_scale_tree(self) -> TaxonomyTree:
        """Create a large tree simulating production dataset (10K nodes, 1K genomes)."""
        tree = TaxonomyTree()
        
        # Add root
        root = TaxonomyNode(
            tax_id=1, 
            name="root", 
            rank=TaxonomicRank.ROOT, 
            parent_id=None
        )
        tree.add_node(root)
        
        node_id = 2
        
        # Create deeper hierarchy: 100 kingdoms -> 10 phyla each -> 10 classes each = 10K nodes
        for kingdom in range(100):
            kingdom_node = TaxonomyNode(
                tax_id=node_id,
                name=f"Kingdom_{kingdom}",
                rank=TaxonomicRank.KINGDOM,
                parent_id=1
            )
            tree.add_node(kingdom_node)
            kingdom_id = node_id
            node_id += 1
            
            for phylum in range(10):
                phylum_node = TaxonomyNode(
                    tax_id=node_id,
                    name=f"Phylum_{kingdom}_{phylum}",
                    rank=TaxonomicRank.PHYLUM,
                    parent_id=kingdom_id
                )
                tree.add_node(phylum_node)
                phylum_id = node_id
                node_id += 1
                
                for class_num in range(10):
                    class_node = TaxonomyNode(
                        tax_id=node_id,
                        name=f"Class_{kingdom}_{phylum}_{class_num}",
                        rank=TaxonomicRank.CLASS,
                        parent_id=phylum_id
                    )
                    tree.add_node(class_node)
                    class_id = node_id
                    node_id += 1
                    
                    # Add genome to some nodes (simulate 10% having genomes = ~1000 genomes)
                    if node_id % 10 == 0:  # Every 10th node gets a genome
                        genome = GenomeInfo(
                            genome_id=f"genome_{class_id}",
                            tax_id=class_id,
                            file_path=f"/data/genomes/genome_{class_id}.fna",
                            sequence_length=2500000,  # 2.5MB typical bacterial genome
                            sequence_type="genome",
                            assembly_accession=f"GCF_{class_id:09d}.1",
                            description=f"Genome for {class_node.name}",
                            source="simulated"
                        )
                        tree.add_genome(genome)
        
        return tree

    def test_optimized_save_performance(self, large_scale_tree):
        """Test optimized batch save performance."""
        with tempfile.NamedTemporaryFile(suffix=".ftd", delete=False) as f:
            db_path = Path(f.name)
        
        try:
            # Test save performance
            repository = SQLiteTaxonomyRepository(db_path)
            
            start_time = time.time()
            repository.save_tree(large_scale_tree)
            save_time = time.time() - start_time
            
            # Performance assertions for production scale
            assert save_time < 30.0, f"Save took {save_time:.2f}s, should be < 30s for 10K nodes"
            
            # Verify data integrity
            stats = repository.get_statistics(validate_files=False)  # Skip file validation for performance
            assert stats["node_count"] == large_scale_tree.node_count
            assert stats["genome_count"] == large_scale_tree.genome_count
            
            print(f"✅ Saved {large_scale_tree.node_count} nodes and {large_scale_tree.genome_count} genomes in {save_time:.2f}s")
            
        finally:
            db_path.unlink(missing_ok=True)

    def test_optimized_load_performance(self, large_scale_tree):
        """Test optimized bulk load performance."""
        with tempfile.NamedTemporaryFile(suffix=".ftd", delete=False) as f:
            db_path = Path(f.name)
        
        try:
            # Save first
            repository = SQLiteTaxonomyRepository(db_path)
            repository.save_tree(large_scale_tree)
            
            # Test load performance
            start_time = time.time()
            loaded_tree = repository.load_tree()
            load_time = time.time() - start_time
            
            # Performance assertions
            assert load_time < 15.0, f"Load took {load_time:.2f}s, should be < 15s for 10K nodes"
            
            # Verify data integrity
            assert loaded_tree.node_count == large_scale_tree.node_count
            assert loaded_tree.genome_count == large_scale_tree.genome_count
            
            print(f"✅ Loaded {loaded_tree.node_count} nodes and {loaded_tree.genome_count} genomes in {load_time:.2f}s")
            
        finally:
            db_path.unlink(missing_ok=True)

    def test_database_optimizations_applied(self):
        """Test that database performance optimizations are applied."""
        with tempfile.NamedTemporaryFile(suffix=".ftd", delete=False) as f:
            db_path = Path(f.name)
        
        try:
            repository = SQLiteTaxonomyRepository(db_path)
            conn = repository._get_connection()
            
            # Check that performance PRAGMA settings are applied
            pragmas_to_check = {
                'synchronous': 1,         # NORMAL = 1 (was FULL = 2 by default)
                'cache_size': 10000,      # 10MB cache
                'temp_store': 2,          # MEMORY = 2 (FILE = 1, DEFAULT = 0)
                'journal_mode': 'wal',    # WAL mode for concurrency
                'foreign_keys': 1         # ON = 1
            }
            
            for pragma, expected in pragmas_to_check.items():
                cursor = conn.execute(f"PRAGMA {pragma}")
                actual = cursor.fetchone()[0]
                
                if pragma == 'cache_size':
                    # Cache size should be >= our target (allows for different page sizes)
                    assert abs(actual) >= abs(expected) / 2, f"Cache size {actual} should be >= {expected/2}"
                elif pragma == 'synchronous':
                    # NORMAL = 1, FULL = 2, OFF = 0
                    assert actual <= 1, f"Synchronous should be NORMAL(1) or OFF(0), got {actual}"
                elif pragma == 'journal_mode':
                    # String comparison for journal mode
                    assert str(actual).upper() == str(expected).upper(), f"PRAGMA {pragma}: expected {expected}, got {actual}"
                else:
                    # Numeric comparison for other pragmas
                    assert actual == expected, f"PRAGMA {pragma}: expected {expected}, got {actual}"
            
            print("✅ All database optimizations properly applied")
            
        finally:
            db_path.unlink(missing_ok=True)

    def test_memory_usage_efficiency(self, large_scale_tree):
        """Test memory efficiency during operations."""
        try:
            import psutil
        except ImportError:
            pytest.skip("psutil not available for memory testing")
        
        with tempfile.NamedTemporaryFile(suffix=".ftd", delete=False) as f:
            db_path = Path(f.name)
        
        try:
            process = psutil.Process()
            initial_memory = process.memory_info().rss / 1024 / 1024  # MB
            
            repository = SQLiteTaxonomyRepository(db_path)
            
            # Test memory usage during save
            memory_before_save = process.memory_info().rss / 1024 / 1024
            repository.save_tree(large_scale_tree)
            memory_after_save = process.memory_info().rss / 1024 / 1024
            
            save_memory_increase = memory_after_save - memory_before_save
            
            # Test memory usage during load
            memory_before_load = process.memory_info().rss / 1024 / 1024
            loaded_tree = repository.load_tree()
            memory_after_load = process.memory_info().rss / 1024 / 1024
            
            load_memory_increase = memory_after_load - memory_before_load
            
            # Memory usage assertions (should be reasonable for 10K nodes + 1K genomes)
            assert save_memory_increase < 200, f"Save used {save_memory_increase:.1f}MB, should be < 200MB"
            assert load_memory_increase < 100, f"Load used {load_memory_increase:.1f}MB, should be < 100MB"
            
            print(f"✅ Memory efficient: Save +{save_memory_increase:.1f}MB, Load +{load_memory_increase:.1f}MB")
            
        finally:
            db_path.unlink(missing_ok=True)

    def test_concurrent_read_performance(self, large_scale_tree):
        """Test performance under concurrent read operations."""
        import threading
        import queue
        
        with tempfile.NamedTemporaryFile(suffix=".ftd", delete=False) as f:
            db_path = Path(f.name)
        
        try:
            # Setup database
            repository = SQLiteTaxonomyRepository(db_path)
            repository.save_tree(large_scale_tree)
            
            # Test concurrent reads
            results_queue = queue.Queue()
            num_threads = 4
            
            def concurrent_read():
                start_time = time.time()
                repo = SQLiteTaxonomyRepository(db_path)  # New connection per thread
                loaded_tree = repo.load_tree()
                load_time = time.time() - start_time
                results_queue.put(load_time)
                
            # Start concurrent reads
            threads = []
            start_time = time.time()
            
            for _ in range(num_threads):
                thread = threading.Thread(target=concurrent_read)
                thread.start()
                threads.append(thread)
            
            # Wait for completion
            for thread in threads:
                thread.join()
            
            total_time = time.time() - start_time
            
            # Collect results
            load_times = []
            while not results_queue.empty():
                load_times.append(results_queue.get())
            
            avg_load_time = sum(load_times) / len(load_times)
            max_load_time = max(load_times)
            
            # Performance assertions for concurrent access
            assert total_time < 45, f"Concurrent reads took {total_time:.2f}s, should be < 45s"
            assert max_load_time < 30, f"Slowest read took {max_load_time:.2f}s, should be < 30s"
            
            print(f"✅ Concurrent reads: {num_threads} threads, avg {avg_load_time:.2f}s, max {max_load_time:.2f}s")
            
        finally:
            db_path.unlink(missing_ok=True)