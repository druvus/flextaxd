"""Advanced tests for SQLite database functionality to improve coverage."""

import tempfile
import sqlite3
from pathlib import Path
from unittest.mock import patch, Mock
import pytest

from flextaxd.database.sqlite import SQLiteTaxonomyRepository
from flextaxd.core.models import TaxonomyNode, GenomeInfo, TaxonomyTree, TaxonomicRank
from flextaxd.core.exceptions import DatabaseError


class TestSQLiteAdvancedFeatures:
    """Test advanced SQLite functionality for better coverage."""
    
    @pytest.fixture
    def temp_db(self):
        """Create temporary database."""
        with tempfile.NamedTemporaryFile(suffix='.ftd', delete=False) as f:
            temp_path = Path(f.name)
        
        yield temp_path
        
        # Cleanup
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
    
    @pytest.fixture
    def populated_repository(self, temp_db):
        """Create repository with test data."""
        repo = SQLiteTaxonomyRepository(temp_db)
        repo.initialize()
        
        # Add test nodes
        nodes = [
            TaxonomyNode(1, "root", TaxonomicRank.ROOT, None),
            TaxonomyNode(2, "Bacteria", TaxonomicRank.SUPERKINGDOM, 1),
            TaxonomyNode(3, "Proteobacteria", TaxonomicRank.PHYLUM, 2),
            TaxonomyNode(4, "Gammaproteobacteria", TaxonomicRank.CLASS, 3),
            TaxonomyNode(5, "Enterobacteriales", TaxonomicRank.ORDER, 4),
            TaxonomyNode(6, "Enterobacteriaceae", TaxonomicRank.FAMILY, 5),
            TaxonomyNode(7, "Escherichia", TaxonomicRank.GENUS, 6),
            TaxonomyNode(8, "Escherichia coli", TaxonomicRank.SPECIES, 7),
        ]
        
        for node in nodes:
            repo.add_node(node)
            
        # Add test genomes
        genomes = [
            GenomeInfo("genome1", 8, "/path/genome1.fna", 4641652, "genome", "NCBI"),
            GenomeInfo("genome2", 8, "/path/genome2.fna", 4639221, "genome", "GTDB"),
        ]
        
        for genome in genomes:
            repo.add_genome(genome)
        
        return repo
    
    def test_transaction_context_manager_success(self, populated_repository):
        """Test successful transaction."""
        repo = populated_repository
        
        with repo.transaction() as conn:
            # Add a new node within transaction
            conn.execute(
                "INSERT INTO nodes (tax_id, name, rank, parent_id) VALUES (?, ?, ?, ?)",
                (999, "Test Node", TaxonomicRank.SPECIES.value, 7)
            )
            
            # Verify it exists within transaction
            cursor = conn.execute("SELECT name FROM nodes WHERE tax_id = ?", (999,))
            result = cursor.fetchone()
            assert result[0] == "Test Node"
        
        # Verify it was committed
        node = repo.get_node(999)
        assert node is not None
        assert node.name == "Test Node"
    
    def test_transaction_context_manager_rollback(self, populated_repository):
        """Test transaction rollback on exception."""
        repo = populated_repository
        
        with pytest.raises(DatabaseError):
            with repo.transaction() as conn:
                # Add a new node
                conn.execute(
                    "INSERT INTO nodes (tax_id, name, rank, parent_id) VALUES (?, ?, ?, ?)",
                    (888, "Test Node", TaxonomicRank.SPECIES.value, 7)
                )
                
                # Verify it exists within transaction
                cursor = conn.execute("SELECT name FROM nodes WHERE tax_id = ?", (888,))
                result = cursor.fetchone()
                assert result[0] == "Test Node"
                
                # Raise an exception to trigger rollback
                raise DatabaseError("Test rollback")
        
        # Verify it was rolled back
        node = repo.get_node(888)
        assert node is None
    
    def test_validate_schema_valid(self, populated_repository):
        """Test schema validation with valid database."""
        repo = populated_repository
        
        assert repo.validate_schema() is True
    
    def test_validate_schema_missing_table(self, temp_db):
        """Test schema validation with missing table."""
        repo = SQLiteTaxonomyRepository(temp_db)
        # Don't initialize to create incomplete schema
        
        conn = repo._get_connection()
        # Create only nodes table, missing genomes table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS nodes (
                tax_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                rank TEXT NOT NULL,  
                parent_id INTEGER
            )
        """)
        conn.close()
        
        assert repo.validate_schema() is False
    
    def test_validate_schema_missing_column(self, populated_repository):
        """Test schema validation with missing column."""
        repo = populated_repository
        
        # Drop index first, then the column to simulate schema mismatch
        with repo.transaction() as conn:
            try:
                conn.execute("DROP INDEX IF EXISTS idx_nodes_rank")
                conn.execute("ALTER TABLE nodes DROP COLUMN rank")
            except Exception:
                # SQLite might not support DROP COLUMN in older versions
                # Create a new table without the rank column
                conn.execute("""
                    CREATE TABLE nodes_temp (
                        tax_id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        parent_id INTEGER
                    )
                """)
                conn.execute("INSERT INTO nodes_temp (tax_id, name, parent_id) SELECT tax_id, name, parent_id FROM nodes")
                conn.execute("DROP TABLE nodes")
                conn.execute("ALTER TABLE nodes_temp RENAME TO nodes")
        
        assert repo.validate_schema() is False
    
    def test_remove_subtree_single_node(self, populated_repository):
        """Test removing subtree with single leaf node."""
        repo = populated_repository
        
        # Remove leaf node
        removed_count = repo.remove_subtree(8)  # Escherichia coli
        
        assert removed_count == 1
        assert repo.get_node(8) is None
        # Parent should still exist
        assert repo.get_node(7) is not None
    
    def test_remove_subtree_multiple_nodes(self, populated_repository):
        """Test removing subtree with multiple descendants."""
        repo = populated_repository
        
        # Add more nodes under Escherichia
        more_nodes = [
            TaxonomyNode(9, "Escherichia albertii", TaxonomicRank.SPECIES, 7),
            TaxonomyNode(10, "Escherichia fergusonii", TaxonomicRank.SPECIES, 7),
            TaxonomyNode(11, "E. coli strain K12", TaxonomicRank.STRAIN, 8),
            TaxonomyNode(12, "E. coli strain O157", TaxonomicRank.STRAIN, 8),
        ]
        
        for node in more_nodes:
            repo.add_node(node)
        
        # Remove Escherichia genus (should remove all descendants)
        removed_count = repo.remove_subtree(7)  # Escherichia
        
        assert removed_count == 6  # Genus + 3 species + 2 strains
        
        # Verify all were removed
        for tax_id in [7, 8, 9, 10, 11, 12]:
            assert repo.get_node(tax_id) is None
        
        # Parent should still exist
        assert repo.get_node(6) is not None  # Enterobacteriaceae
    
    def test_remove_subtree_nonexistent_node(self, populated_repository):
        """Test removing nonexistent node."""
        repo = populated_repository
        
        with pytest.raises(DatabaseError) as exc_info:
            repo.remove_subtree(999)
        
        assert "not found" in str(exc_info.value).lower()
    
    def test_remove_subtree_with_genomes(self, populated_repository):
        """Test removing subtree that contains genomes."""
        repo = populated_repository
        
        # Should remove genomes with the nodes
        removed_count = repo.remove_subtree(8)  # E. coli with genomes
        
        assert removed_count == 1
        assert repo.get_node(8) is None
        
        # Genomes should be removed too (cascading delete)
        genomes = repo.get_genomes_for_node(8)
        assert len(genomes) == 0
    
    def test_optimize_connection_settings(self, temp_db):
        """Test database connection optimization."""
        repo = SQLiteTaxonomyRepository(temp_db)
        
        conn = repo._get_connection()
        
        # Test that optimization settings are applied
        cursor = conn.execute("PRAGMA journal_mode")
        journal_mode = cursor.fetchone()[0]
        assert journal_mode.upper() == "WAL"
        
        cursor = conn.execute("PRAGMA synchronous")
        sync_mode = cursor.fetchone()[0]
        assert sync_mode == 1  # NORMAL
        
        cursor = conn.execute("PRAGMA cache_size")
        cache_size = cursor.fetchone()[0]
        assert cache_size == 10000  # 10MB
    
    def test_batch_insert_nodes_large_tree(self, temp_db):
        """Test batch insertion with large tree."""
        repo = SQLiteTaxonomyRepository(temp_db)
        repo.initialize()
        
        # Create large tree
        tree = TaxonomyTree()
        
        # Root
        root = TaxonomyNode(1, "root", TaxonomicRank.ROOT, None)
        tree.add_node(root)
        
        # Generate many nodes
        for i in range(2, 1002):  # 1000 nodes
            parent_id = max(1, (i - 1) // 10)  # Create hierarchy
            node = TaxonomyNode(i, f"node_{i}", TaxonomicRank.SPECIES, parent_id)
            tree.add_node(node)
        
        # Save tree (tests batch insertion)
        repo.save_tree(tree)
        
        # Verify all nodes were inserted
        stats = repo.get_statistics(validate_files=False)
        assert stats["node_count"] == 1001
    
    def test_get_detailed_genome_statistics_optimized(self, populated_repository):
        """Test optimized genome statistics method."""
        repo = populated_repository
        
        # Test with file validation disabled for optimized path
        stats = repo.get_statistics(validate_files=False)
        
        # Check genome-related stats in flat structure
        assert "genome_count" in stats
        assert stats["genome_count"] == 2
        assert "genomes_with_files" in stats
        assert stats["genomes_with_files"] == 2
        assert "source_distribution" in stats
        assert "sequence_type_breakdown" in stats
    
    @patch('pathlib.Path.exists')
    def test_validate_files_batch_missing_files(self, mock_exists, populated_repository):
        """Test file validation with missing files."""
        mock_exists.return_value = False  # All files missing
        
        repo = populated_repository
        
        # Test file validation
        file_paths = ["/path/genome1.fna", "/path/genome2.fna"]
        results = repo._validate_files_batch(file_paths)
        
        assert len(results) == 2
        for path in file_paths:
            assert results[path]["exists"] is False
            assert results[path]["accessible"] is False
    
    @patch('pathlib.Path.stat')
    @patch('pathlib.Path.is_file')
    @patch('pathlib.Path.exists')
    @patch('os.access')
    def test_validate_files_batch_mixed_results(self, mock_access, mock_exists, mock_is_file, mock_stat, populated_repository):
        """Test file validation with mixed results."""
        # First file exists and is accessible, second doesn't
        mock_exists.side_effect = [True, False]
        mock_access.return_value = True
        mock_is_file.return_value = True
        
        # Mock stat to return a stat object with size > 0
        mock_stat_obj = Mock()
        mock_stat_obj.st_size = 1000
        mock_stat.return_value = mock_stat_obj
        
        repo = populated_repository
        
        file_paths = ["/path/genome1.fna", "/path/genome2.fna"]
        results = repo._validate_files_batch(file_paths)
        
        assert results["/path/genome1.fna"]["exists"] is True
        assert results["/path/genome1.fna"]["accessible"] is True
        assert results["/path/genome2.fna"]["exists"] is False
        assert results["/path/genome2.fna"]["accessible"] is False
    
    @patch('pathlib.Path.mkdir')
    def test_connection_error_handling(self, mock_mkdir, temp_db):
        """Test connection error handling."""
        repo = SQLiteTaxonomyRepository(temp_db)
        
        # Mock mkdir to prevent actual directory creation
        mock_mkdir.return_value = None
        
        # Should handle connection errors gracefully during construction
        with pytest.raises((DatabaseError, sqlite3.OperationalError)):
            bad_repo = SQLiteTaxonomyRepository("/nonexistent/path/to/database.ftd")
    
    def test_schema_migration_checksum_column(self, temp_db):
        """Test schema migration for checksum column."""
        # Create a repository without initializing (to create old schema manually)
        repo = SQLiteTaxonomyRepository(temp_db)
        
        # Reset connection to None so we can create the old schema fresh
        repo._connection = None
        
        # Create database with old schema (without checksum)
        conn = repo._get_connection()
        conn.execute("DROP TABLE IF EXISTS genomes")
        conn.execute("DROP TABLE IF EXISTS nodes")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS nodes (
                tax_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                rank TEXT NOT NULL,
                parent_id INTEGER,
                FOREIGN KEY (parent_id) REFERENCES nodes (tax_id)
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS genomes (
                genome_id TEXT PRIMARY KEY,
                tax_id INTEGER NOT NULL,
                file_path TEXT,
                sequence_length INTEGER,
                sequence_type TEXT,
                assembly_accession TEXT,
                description TEXT,
                source TEXT,
                FOREIGN KEY (tax_id) REFERENCES nodes (tax_id)
            )
        """)
        # Don't close the connection - let the repo manage it
        
        # Initialize should add missing columns
        repo.initialize()
        
        # Verify checksum column was added
        with repo.transaction() as conn:
            cursor = conn.execute("PRAGMA table_info(genomes)")
            columns = [row[1] for row in cursor.fetchall()]
            assert "file_checksum" in columns
    
    def test_concurrent_access_simulation(self, populated_repository):
        """Test concurrent access patterns."""
        repo = populated_repository
        
        # Simulate concurrent reads
        results = []
        
        # Multiple read operations
        for i in range(10):
            node = repo.get_node(8)
            results.append(node)
            
            stats = repo.get_statistics(validate_files=False)
            results.append(stats)
        
        # All operations should succeed
        assert len(results) == 20
        
        # All nodes should be identical
        nodes = [r for r in results if isinstance(r, TaxonomyNode)]
        assert len(nodes) == 10
        assert all(node.tax_id == 8 for node in nodes)
    
    def test_large_transaction_rollback(self, populated_repository):
        """Test rollback of large transaction."""
        repo = populated_repository
        
        initial_count = repo.load_tree().node_count
        
        try:
            with repo.transaction() as conn:
                # Add many nodes
                for i in range(1000, 2000):
                    conn.execute(
                        "INSERT INTO nodes (tax_id, name, rank, parent_id) VALUES (?, ?, ?, ?)",
                        (i, f"node_{i}", TaxonomicRank.SPECIES.value, 8)
                    )
                
                # Force rollback
                raise Exception("Test rollback")
                
        except Exception:
            pass
        
        # Verify rollback worked
        final_count = repo.load_tree().node_count
        assert final_count == initial_count
    
    def test_database_integrity_after_operations(self, populated_repository):
        """Test database integrity after various operations."""
        repo = populated_repository
        
        # Perform various operations
        repo.add_node(TaxonomyNode(100, "Test Species", TaxonomicRank.SPECIES, 7))
        repo.update_node(TaxonomyNode(100, "Updated Species", TaxonomicRank.SPECIES, 7))
        repo.add_genome(GenomeInfo("test_genome", 100, "/test/path.fna"))
        
        # Remove subtree
        repo.remove_subtree(100)
        
        # Verify database is still consistent
        assert repo.validate_schema() is True
        
        # Can still perform operations
        stats = repo.get_statistics(validate_files=False)
        assert stats["node_count"] > 0
        
        tree = repo.load_tree()
        assert tree.node_count > 0
    
    def test_error_recovery_after_constraint_violation(self, populated_repository):
        """Test error recovery after constraint violations."""
        repo = populated_repository
        
        # Try to add duplicate tax_id (should fail)
        with pytest.raises(DatabaseError):
            repo.add_node(TaxonomyNode(8, "Duplicate", TaxonomicRank.SPECIES, 7))
        
        # Database should still be functional
        node = repo.get_node(8)
        assert node is not None
        assert node.name == "Escherichia coli"  # Original name
        
        # Can still add valid nodes
        repo.add_node(TaxonomyNode(200, "Valid Node", TaxonomicRank.SPECIES, 7))
        assert repo.get_node(200) is not None


class TestSQLitePerformance:
    """Test performance-related functionality."""
    
    @pytest.fixture
    def temp_db(self):
        """Create temporary database."""
        with tempfile.NamedTemporaryFile(suffix='.ftd', delete=False) as f:
            temp_path = Path(f.name)
        
        yield temp_path
        
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
    
    def test_connection_pooling_behavior(self, temp_db):
        """Test connection reuse behavior."""
        repo = SQLiteTaxonomyRepository(temp_db)
        repo.initialize()
        
        # Multiple operations should reuse connection
        conn1 = repo._get_connection()
        conn2 = repo._get_connection()
        
        # Should be the same connection object
        assert conn1 is conn2
    
    def test_large_query_performance(self, temp_db):
        """Test performance with large queries."""
        repo = SQLiteTaxonomyRepository(temp_db)
        repo.initialize()
        
        # Create large dataset
        nodes = []
        for i in range(1, 5001):  # 5000 nodes
            parent_id = 1 if i <= 1 else ((i - 2) // 10) + 1
            if parent_id >= i:
                parent_id = None
            node = TaxonomyNode(i, f"node_{i}", TaxonomicRank.SPECIES, parent_id)
            nodes.append(node)
            repo.add_node(node)
        
        # Test large queries
        all_nodes = list(repo.load_tree()._nodes.values())
        assert len(all_nodes) == 5000
        
        # Test descendants query on node with many children
        descendants = repo.get_descendants(1)
        assert len(descendants) > 1000


if __name__ == "__main__":
    pytest.main([__file__])