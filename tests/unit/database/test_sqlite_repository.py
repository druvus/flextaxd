"""Comprehensive unit tests for database layer."""

import pytest
import tempfile
import sqlite3
from pathlib import Path
from unittest.mock import Mock, patch

from flextaxd.core.models import TaxonomyTree, TaxonomyNode, TaxonomicRank, GenomeInfo
from flextaxd.core.exceptions import DatabaseError, ValidationError
from flextaxd.database.sqlite import SQLiteTaxonomyRepository
from flextaxd.database.repository import TaxonomyRepository


class TestTaxonomyRepositoryInterface:
    """Test TaxonomyRepository abstract interface."""

    def test_abstract_repository_cannot_be_instantiated(self):
        """Test that abstract repository cannot be instantiated."""
        with pytest.raises(TypeError):
            TaxonomyRepository()


class TestSQLiteTaxonomyRepository:
    """Comprehensive tests for SQLite repository implementation."""

    def test_repository_creation_new_database(self):
        """Test creating repository with new database file."""
        with tempfile.NamedTemporaryFile(suffix=".ftd", delete=False) as f:
            db_path = Path(f.name)

        # Remove the file so we test creation
        db_path.unlink()

        try:
            with SQLiteTaxonomyRepository(db_path) as repo:
                assert isinstance(repo, SQLiteTaxonomyRepository)
                assert db_path.exists()
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_repository_opening_existing_database(self):
        """Test opening existing database file."""
        with tempfile.NamedTemporaryFile(suffix=".ftd", delete=False) as f:
            db_path = Path(f.name)

        try:
            # Create and populate database first
            with SQLiteTaxonomyRepository(db_path) as repo:
                root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
                repo.add_node(root)

            # Reopen and verify data persists
            with SQLiteTaxonomyRepository(db_path) as repo:
                node = repo.get_node(1)
                assert node is not None
                assert node.name == "root"
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_repository_context_manager(self):
        """Test repository as context manager."""
        with tempfile.NamedTemporaryFile(suffix=".ftd", delete=False) as f:
            db_path = Path(f.name)

        db_path.unlink()  # Remove file for clean test

        try:
            repo_instance = None
            with SQLiteTaxonomyRepository(db_path) as repo:
                repo_instance = repo
                assert repo._connection is not None

            # Connection should be closed after exiting context
            # Note: Testing internal state, but important for resource management
            assert repo_instance._connection is None
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_add_node_basic(self):
        """Test adding a basic node."""
        with tempfile.NamedTemporaryFile(suffix=".ftd", delete=False) as f:
            db_path = Path(f.name)

        db_path.unlink()

        try:
            with SQLiteTaxonomyRepository(db_path) as repo:
                node = TaxonomyNode(
                    tax_id=1, name="root", rank=TaxonomicRank.CUSTOM, parent_id=None
                )

                repo.add_node(node)

                # Verify node was added
                retrieved = repo.get_node(1)
                assert retrieved is not None
                assert retrieved.tax_id == 1
                assert retrieved.name == "root"
                assert retrieved.rank == TaxonomicRank.CUSTOM
                assert retrieved.parent_id is None
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_add_node_with_parent(self):
        """Test adding node with parent relationship."""
        with tempfile.NamedTemporaryFile(suffix=".ftd", delete=False) as f:
            db_path = Path(f.name)

        db_path.unlink()

        try:
            with SQLiteTaxonomyRepository(db_path) as repo:
                # Add root first
                root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
                repo.add_node(root)

                # Add child
                bacteria = TaxonomyNode(
                    tax_id=2,
                    name="Bacteria",
                    rank=TaxonomicRank.SUPERKINGDOM,
                    parent_id=1,
                )
                repo.add_node(bacteria)

                # Verify relationship
                bacteria_node = repo.get_node(2)
                assert bacteria_node is not None
                assert bacteria_node.parent_id == 1

                # Test parent-child relationship
                children = repo.get_children(1)
                assert len(children) == 1
                assert children[0].tax_id == 2
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_add_node_duplicate_tax_id(self):
        """Test adding node with duplicate tax_id."""
        with tempfile.NamedTemporaryFile(suffix=".ftd", delete=False) as f:
            db_path = Path(f.name)

        db_path.unlink()

        try:
            with SQLiteTaxonomyRepository(db_path) as repo:
                node1 = TaxonomyNode(tax_id=1, name="first", rank=TaxonomicRank.CUSTOM)
                repo.add_node(node1)

                # Try to add another node with same tax_id
                node2 = TaxonomyNode(tax_id=1, name="second", rank=TaxonomicRank.CUSTOM)

                with pytest.raises(DatabaseError, match="already exists"):
                    repo.add_node(node2)
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_add_node_invalid_parent(self):
        """Test adding node with non-existent parent."""
        with tempfile.NamedTemporaryFile(suffix=".ftd", delete=False) as f:
            db_path = Path(f.name)

        db_path.unlink()

        try:
            with SQLiteTaxonomyRepository(db_path) as repo:
                # Try to add node with non-existent parent
                node = TaxonomyNode(
                    tax_id=2,
                    name="orphan",
                    rank=TaxonomicRank.SPECIES,
                    parent_id=999,  # Non-existent
                )

                with pytest.raises(
                    DatabaseError, match="Parent node .* does not exist"
                ):
                    repo.add_node(node)
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_get_node_nonexistent(self):
        """Test getting non-existent node returns None."""
        with tempfile.NamedTemporaryFile(suffix=".ftd", delete=False) as f:
            db_path = Path(f.name)

        db_path.unlink()

        try:
            with SQLiteTaxonomyRepository(db_path) as repo:
                node = repo.get_node(999)
                assert node is None
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_get_all_nodes(self):
        """Test getting all nodes."""
        with tempfile.NamedTemporaryFile(suffix=".ftd", delete=False) as f:
            db_path = Path(f.name)

        db_path.unlink()

        try:
            with SQLiteTaxonomyRepository(db_path) as repo:
                # Add multiple nodes
                nodes = [
                    TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM),
                    TaxonomyNode(
                        tax_id=2,
                        name="Bacteria",
                        rank=TaxonomicRank.SUPERKINGDOM,
                        parent_id=1,
                    ),
                    TaxonomyNode(
                        tax_id=562,
                        name="E. coli",
                        rank=TaxonomicRank.SPECIES,
                        parent_id=2,
                    ),
                ]

                for node in nodes:
                    repo.add_node(node)

                tree = repo.load_tree()
                assert len(tree) == 3  # Should have 3 nodes

                # Verify nodes exist
                assert repo.get_node(1) is not None
                assert repo.get_node(2) is not None
                assert repo.get_node(562) is not None
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_get_children(self):
        """Test getting child nodes."""
        with tempfile.NamedTemporaryFile(suffix=".ftd", delete=False) as f:
            db_path = Path(f.name)

        db_path.unlink()

        try:
            with SQLiteTaxonomyRepository(db_path) as repo:
                # Create hierarchy: root -> bacteria -> (e.coli, salmonella)
                root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
                bacteria = TaxonomyNode(
                    tax_id=2,
                    name="Bacteria",
                    rank=TaxonomicRank.SUPERKINGDOM,
                    parent_id=1,
                )
                ecoli = TaxonomyNode(
                    tax_id=562, name="E. coli", rank=TaxonomicRank.SPECIES, parent_id=2
                )
                salmonella = TaxonomyNode(
                    tax_id=590, name="Salmonella", rank=TaxonomicRank.GENUS, parent_id=2
                )

                for node in [root, bacteria, ecoli, salmonella]:
                    repo.add_node(node)

                # Test getting children
                bacteria_children = repo.get_children(2)
                assert len(bacteria_children) == 2

                child_names = [child.name for child in bacteria_children]
                assert "E. coli" in child_names
                assert "Salmonella" in child_names

                # Test node with no children
                ecoli_children = repo.get_children(562)
                assert len(ecoli_children) == 0
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_get_descendants(self):
        """Test getting all descendants of a node."""
        with tempfile.NamedTemporaryFile(suffix=".ftd", delete=False) as f:
            db_path = Path(f.name)

        db_path.unlink()

        try:
            with SQLiteTaxonomyRepository(db_path) as repo:
                # Create hierarchy: root -> bacteria -> genus -> species -> strain
                nodes = [
                    TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM),
                    TaxonomyNode(
                        tax_id=2,
                        name="Bacteria",
                        rank=TaxonomicRank.SUPERKINGDOM,
                        parent_id=1,
                    ),
                    TaxonomyNode(
                        tax_id=561,
                        name="Escherichia",
                        rank=TaxonomicRank.GENUS,
                        parent_id=2,
                    ),
                    TaxonomyNode(
                        tax_id=562,
                        name="E. coli",
                        rank=TaxonomicRank.SPECIES,
                        parent_id=561,
                    ),
                    TaxonomyNode(
                        tax_id=1000,
                        name="K-12",
                        rank=TaxonomicRank.STRAIN,
                        parent_id=562,
                    ),
                ]

                for node in nodes:
                    repo.add_node(node)

                # Test getting all descendants of Bacteria (should include genus, species, strain)
                bacteria_descendants = repo.get_descendants(2)
                assert len(bacteria_descendants) == 3  # genus, species, strain

                descendant_names = [desc.name for desc in bacteria_descendants]
                assert "Escherichia" in descendant_names
                assert "E. coli" in descendant_names
                assert "K-12" in descendant_names

                # Test getting descendants of species (should include only strain)
                species_descendants = repo.get_descendants(562)
                assert len(species_descendants) == 1
                assert species_descendants[0].name == "K-12"
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_get_path_to_root(self):
        """Test getting path from node to root."""
        with tempfile.NamedTemporaryFile(suffix=".ftd", delete=False) as f:
            db_path = Path(f.name)

        db_path.unlink()

        try:
            with SQLiteTaxonomyRepository(db_path) as repo:
                # Create hierarchy
                nodes = [
                    TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM),
                    TaxonomyNode(
                        tax_id=2,
                        name="Bacteria",
                        rank=TaxonomicRank.SUPERKINGDOM,
                        parent_id=1,
                    ),
                    TaxonomyNode(
                        tax_id=561,
                        name="Escherichia",
                        rank=TaxonomicRank.GENUS,
                        parent_id=2,
                    ),
                    TaxonomyNode(
                        tax_id=562,
                        name="E. coli",
                        rank=TaxonomicRank.SPECIES,
                        parent_id=561,
                    ),
                ]

                for node in nodes:
                    repo.add_node(node)

                # Get path from E. coli to root
                path = repo.get_path_to_root(562)
                assert len(path) == 4  # E. coli -> Escherichia -> Bacteria -> root

                # Path should be ordered from node to root
                path_names = [node.name for node in path]
                assert path_names == ["E. coli", "Escherichia", "Bacteria", "root"]
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_delete_node_leaf(self):
        """Test deleting leaf node."""
        with tempfile.NamedTemporaryFile(suffix=".ftd", delete=False) as f:
            db_path = Path(f.name)

        db_path.unlink()

        try:
            with SQLiteTaxonomyRepository(db_path) as repo:
                # Create parent-child relationship
                root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
                leaf = TaxonomyNode(
                    tax_id=2, name="leaf", rank=TaxonomicRank.SPECIES, parent_id=1
                )

                repo.add_node(root)
                repo.add_node(leaf)

                # Verify both exist
                assert repo.get_node(1) is not None
                assert repo.get_node(2) is not None

                # Delete leaf node
                repo.delete_node(2)

                # Verify deletion
                assert repo.get_node(1) is not None  # Parent should still exist
                assert repo.get_node(2) is None  # Leaf should be gone
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_delete_node_with_children_fails(self):
        """Test deleting node with children fails."""
        with tempfile.NamedTemporaryFile(suffix=".ftd", delete=False) as f:
            db_path = Path(f.name)

        db_path.unlink()

        try:
            with SQLiteTaxonomyRepository(db_path) as repo:
                root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
                child = TaxonomyNode(
                    tax_id=2, name="child", rank=TaxonomicRank.SPECIES, parent_id=1
                )

                repo.add_node(root)
                repo.add_node(child)

                # Try to delete parent with children
                with pytest.raises(DatabaseError, match="has child nodes"):
                    repo.delete_node(1)
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_delete_nonexistent_node(self):
        """Test deleting non-existent node raises error."""
        with tempfile.NamedTemporaryFile(suffix=".ftd", delete=False) as f:
            db_path = Path(f.name)

        db_path.unlink()

        try:
            with SQLiteTaxonomyRepository(db_path) as repo:
                with pytest.raises(DatabaseError, match="Node .* not found"):
                    repo.delete_node(999)
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_add_genome_basic(self):
        """Test adding genome information."""
        with tempfile.NamedTemporaryFile(suffix=".ftd", delete=False) as f:
            db_path = Path(f.name)

        db_path.unlink()

        try:
            with SQLiteTaxonomyRepository(db_path) as repo:
                # Add taxonomy node first
                ecoli = TaxonomyNode(
                    tax_id=562, name="E. coli", rank=TaxonomicRank.SPECIES
                )
                repo.add_node(ecoli)

                # Add genome
                genome = GenomeInfo(
                    genome_id="NC_000913",
                    tax_id=562,
                    sequence_type="genome",
                    source="NCBI",
                )
                repo.add_genome(genome)

                # Verify genome was added
                genomes = repo.get_genomes_for_node(562)
                assert len(genomes) == 1

                genome_info = genomes[0]
                assert genome_info.genome_id == "NC_000913"
                assert genome_info.tax_id == 562
                assert genome_info.sequence_type == "genome"
                assert genome_info.source == "NCBI"
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_add_genome_invalid_tax_id(self):
        """Test adding genome with invalid tax_id fails."""
        with tempfile.NamedTemporaryFile(suffix=".ftd", delete=False) as f:
            db_path = Path(f.name)

        db_path.unlink()

        try:
            with SQLiteTaxonomyRepository(db_path) as repo:
                genome = GenomeInfo(
                    genome_id="NC_000913",
                    tax_id=999,  # Non-existent
                    sequence_type="genome",
                )

                with pytest.raises(DatabaseError, match="Taxonomy node .* not found"):
                    repo.add_genome(genome)
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_add_genome_duplicate(self):
        """Test adding duplicate genome fails."""
        with tempfile.NamedTemporaryFile(suffix=".ftd", delete=False) as f:
            db_path = Path(f.name)

        db_path.unlink()

        try:
            with SQLiteTaxonomyRepository(db_path) as repo:
                # Add taxonomy node
                ecoli = TaxonomyNode(
                    tax_id=562, name="E. coli", rank=TaxonomicRank.SPECIES
                )
                repo.add_node(ecoli)

                # Add genome first time
                genome1 = GenomeInfo(
                    genome_id="NC_000913", tax_id=562, sequence_type="genome"
                )
                repo.add_genome(genome1)

                # Try to add same genome again
                genome2 = GenomeInfo(
                    genome_id="NC_000913",  # Same ID
                    tax_id=562,
                    sequence_type="protein",  # Different type, but same ID
                )

                with pytest.raises(DatabaseError, match="already exists"):
                    repo.add_genome(genome2)
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_get_genomes_for_node_empty(self):
        """Test getting genomes for node with no genomes."""
        with tempfile.NamedTemporaryFile(suffix=".ftd", delete=False) as f:
            db_path = Path(f.name)

        db_path.unlink()

        try:
            with SQLiteTaxonomyRepository(db_path) as repo:
                # Add node without genomes
                root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
                repo.add_node(root)

                genomes = repo.get_genomes_for_node(1)
                assert len(genomes) == 0
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_get_genomes_for_nonexistent_node(self):
        """Test getting genomes for non-existent node."""
        with tempfile.NamedTemporaryFile(suffix=".ftd", delete=False) as f:
            db_path = Path(f.name)

        db_path.unlink()

        try:
            with SQLiteTaxonomyRepository(db_path) as repo:
                genomes = repo.get_genomes_for_node(999)
                assert len(genomes) == 0
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_get_statistics_empty_database(self):
        """Test getting statistics from empty database."""
        with tempfile.NamedTemporaryFile(suffix=".ftd", delete=False) as f:
            db_path = Path(f.name)

        db_path.unlink()

        try:
            with SQLiteTaxonomyRepository(db_path) as repo:
                stats = repo.get_statistics()

                assert stats["node_count"] == 0
                assert stats["genome_count"] == 0
                assert stats["rank_distribution"] == {}
                assert stats["root_nodes"] == []
                assert stats["leaf_nodes"] == []
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_get_statistics_populated_database(self):
        """Test getting statistics from populated database."""
        with tempfile.NamedTemporaryFile(suffix=".ftd", delete=False) as f:
            db_path = Path(f.name)

        db_path.unlink()

        try:
            with SQLiteTaxonomyRepository(db_path) as repo:
                # Create hierarchy with different ranks
                nodes = [
                    TaxonomyNode(
                        tax_id=1, name="root", rank=TaxonomicRank.CUSTOM
                    ),  # Root
                    TaxonomyNode(
                        tax_id=2,
                        name="Bacteria",
                        rank=TaxonomicRank.SUPERKINGDOM,
                        parent_id=1,
                    ),
                    TaxonomyNode(
                        tax_id=562,
                        name="E. coli",
                        rank=TaxonomicRank.SPECIES,
                        parent_id=2,
                    ),  # Leaf
                    TaxonomyNode(
                        tax_id=590,
                        name="Salmonella",
                        rank=TaxonomicRank.SPECIES,
                        parent_id=2,
                    ),  # Leaf
                ]

                for node in nodes:
                    repo.add_node(node)

                # Add some genomes
                genomes = [
                    GenomeInfo("NC_000913", 562, "genome"),
                    GenomeInfo("NC_003197", 590, "genome"),
                ]

                for genome in genomes:
                    repo.add_genome(genome)

                stats = repo.get_statistics()

                assert stats["node_count"] == 4
                assert stats["genome_count"] == 2

                # Check rank distribution
                rank_dist = stats["rank_distribution"]
                assert rank_dist[TaxonomicRank.CUSTOM] == 1  # root
                assert rank_dist[TaxonomicRank.SUPERKINGDOM] == 1  # Bacteria
                assert rank_dist[TaxonomicRank.SPECIES] == 2  # E. coli + Salmonella

                # Check root and leaf identification
                assert len(stats["root_nodes"]) == 1
                assert stats["root_nodes"][0] == 1  # root node

                assert len(stats["leaf_nodes"]) == 2
                assert 562 in stats["leaf_nodes"]  # E. coli
                assert 590 in stats["leaf_nodes"]  # Salmonella
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_enhanced_genome_statistics_no_genomes(self):
        """Test enhanced genome statistics with no genomes."""
        with tempfile.NamedTemporaryFile(suffix=".ftd", delete=False) as f:
            db_path = Path(f.name)

        db_path.unlink()

        try:
            with SQLiteTaxonomyRepository(db_path) as repo:
                # Add just nodes, no genomes
                root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
                repo.add_node(root)

                stats = repo.get_statistics()

                assert stats["node_count"] == 1
                assert stats["genome_count"] == 0
                
                # Enhanced genome stats should not be present when no genomes
                assert "genomes_with_files" not in stats
                assert "genomes_metadata_only" not in stats
                assert "genome_size_distribution" not in stats
                assert "sequence_type_breakdown" not in stats
                assert "source_distribution" not in stats
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_enhanced_genome_statistics_with_files(self):
        """Test enhanced genome statistics with genome files."""
        with tempfile.NamedTemporaryFile(suffix=".ftd", delete=False) as f:
            db_path = Path(f.name)

        db_path.unlink()

        # Create temporary test files
        test_files = []
        for i in range(3):
            temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.fasta', delete=False)
            temp_file.write(f">seq{i}\nATCGATCG\n")
            temp_file.close()
            test_files.append(Path(temp_file.name))

        try:
            with SQLiteTaxonomyRepository(db_path) as repo:
                # Add nodes
                root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
                bacteria = TaxonomyNode(tax_id=2, name="Bacteria", rank=TaxonomicRank.SUPERKINGDOM, parent_id=1)
                ecoli = TaxonomyNode(tax_id=562, name="E. coli", rank=TaxonomicRank.SPECIES, parent_id=2)
                
                for node in [root, bacteria, ecoli]:
                    repo.add_node(node)

                # Add genomes with different scenarios
                genomes = [
                    GenomeInfo(
                        genome_id="NC_000913",
                        tax_id=562,
                        file_path=str(test_files[0]),  # Existing file
                        sequence_length=4641652,
                        sequence_type="genome",
                        assembly_accession="GCF_000005825.2",
                        source="NCBI"
                    ),
                    GenomeInfo(
                        genome_id="NC_003197", 
                        tax_id=562,
                        file_path="/nonexistent/path.fasta",  # Missing file
                        sequence_length=4857432,
                        sequence_type="genome",
                        source="NCBI"
                    ),
                    GenomeInfo(
                        genome_id="metadata_only",
                        tax_id=562,
                        file_path=None,  # No file path
                        sequence_length=None,
                        sequence_type="16S",
                        assembly_accession="GCA_123456789.1",
                        source="GTDB"
                    ),
                ]

                for genome in genomes:
                    repo.add_genome(genome)

                # Test with file validation
                stats = repo.get_statistics(validate_files=True)

                assert stats["node_count"] == 3
                assert stats["genome_count"] == 3
                assert stats["genomes_with_files"] == 2
                assert stats["genomes_metadata_only"] == 1

                # File validation results
                validation = stats["genome_file_validation"]
                assert validation["accessible"] == 1  # test_files[0]
                assert validation["missing"] == 1     # /nonexistent/path.fasta
                assert validation["invalid"] == 0

                # Genome size distribution
                size_dist = stats["genome_size_distribution"]
                assert size_dist["count"] == 2  # Two genomes have size data
                assert size_dist["min"] == 4641652
                assert size_dist["max"] == 4857432
                assert size_dist["avg"] == (4641652 + 4857432) / 2

                # Sequence type breakdown
                seq_types = stats["sequence_type_breakdown"]
                assert seq_types["genome"] == 2
                assert seq_types["16S"] == 1

                # Source distribution
                sources = stats["source_distribution"]
                assert sources["NCBI"] == 2
                assert sources["GTDB"] == 1

        finally:
            # Cleanup
            if db_path.exists():
                db_path.unlink()
            for temp_file in test_files:
                if temp_file.exists():
                    temp_file.unlink()

    def test_enhanced_genome_statistics_skip_validation(self):
        """Test enhanced genome statistics without file validation."""
        with tempfile.NamedTemporaryFile(suffix=".ftd", delete=False) as f:
            db_path = Path(f.name)

        db_path.unlink()

        try:
            with SQLiteTaxonomyRepository(db_path) as repo:
                # Add nodes and genomes
                root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
                bacteria = TaxonomyNode(tax_id=2, name="Bacteria", rank=TaxonomicRank.SUPERKINGDOM, parent_id=1)
                
                for node in [root, bacteria]:
                    repo.add_node(node)

                genome = GenomeInfo(
                    genome_id="test_genome",
                    tax_id=2,
                    file_path="/some/path.fasta",
                    sequence_length=1000000,
                    sequence_type="genome",
                    source="TEST"
                )
                repo.add_genome(genome)

                # Test without file validation
                stats = repo.get_statistics(validate_files=False)

                assert stats["genome_count"] == 1
                assert stats["genomes_with_files"] == 1
                assert stats["genomes_metadata_only"] == 0
                
                # File validation should not be present
                assert "genome_file_validation" not in stats
                
                # Other stats should still be present
                assert "genome_size_distribution" in stats
                assert "sequence_type_breakdown" in stats
                assert "source_distribution" in stats

        finally:
            if db_path.exists():
                db_path.unlink()

    def test_transaction_rollback_on_error(self):
        """Test transaction rollback on error."""
        with tempfile.NamedTemporaryFile(suffix=".ftd", delete=False) as f:
            db_path = Path(f.name)

        db_path.unlink()

        try:
            with SQLiteTaxonomyRepository(db_path) as repo:
                # Add valid node first
                root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
                repo.add_node(root)

                # Start transaction and try to add invalid node
                with pytest.raises(DatabaseError):
                    with repo.transaction():
                        bacteria = TaxonomyNode(
                            tax_id=2,
                            name="Bacteria",
                            rank=TaxonomicRank.SUPERKINGDOM,
                            parent_id=1,
                        )
                        repo.add_node(bacteria)

                        # This should fail and rollback the transaction
                        invalid_node = TaxonomyNode(
                            tax_id=3,
                            name="Invalid",
                            rank=TaxonomicRank.SPECIES,
                            parent_id=999,
                        )
                        repo.add_node(invalid_node)

                # Verify that Bacteria node was not added due to rollback
                bacteria_node = repo.get_node(2)
                assert bacteria_node is None  # Should be None due to rollback

                # Root should still exist
                root_node = repo.get_node(1)
                assert root_node is not None
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_database_schema_validation(self):
        """Test that database schema is properly created."""
        with tempfile.NamedTemporaryFile(suffix=".ftd", delete=False) as f:
            db_path = Path(f.name)

        db_path.unlink()

        try:
            with SQLiteTaxonomyRepository(db_path) as repo:
                # Check that required tables exist
                conn = repo._get_connection()
                cursor = conn.cursor()

                # Get table names
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall()]

                # Expected tables (using actual schema)
                expected_tables = ["nodes", "genomes"]

                for table in expected_tables:
                    assert table in tables, f"Table {table} not found in database"

                # Test that schema validation passes
                assert repo.validate_schema() == True

                # Test foreign key constraints are enabled
                cursor.execute("PRAGMA foreign_keys")
                fk_enabled = cursor.fetchone()[0]
                assert fk_enabled == 1, "Foreign keys should be enabled"
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_concurrent_access_simulation(self):
        """Test simulation of concurrent access (single-threaded simulation)."""
        with tempfile.NamedTemporaryFile(suffix=".ftd", delete=False) as f:
            db_path = Path(f.name)

        db_path.unlink()

        try:
            # Simulate two "concurrent" operations
            with SQLiteTaxonomyRepository(db_path) as repo1:
                # First connection adds root
                root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
                repo1.add_node(root)

            with SQLiteTaxonomyRepository(db_path) as repo2:
                # Second connection should see the root and can add child
                root_node = repo2.get_node(1)
                assert root_node is not None

                bacteria = TaxonomyNode(
                    tax_id=2,
                    name="Bacteria",
                    rank=TaxonomicRank.SUPERKINGDOM,
                    parent_id=1,
                )
                repo2.add_node(bacteria)

            # Third connection verifies both nodes exist
            with SQLiteTaxonomyRepository(db_path) as repo3:
                assert repo3.get_node(1) is not None
                assert repo3.get_node(2) is not None
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_large_tree_performance(self):
        """Test performance with moderately large tree (not exhaustive)."""
        with tempfile.NamedTemporaryFile(suffix=".ftd", delete=False) as f:
            db_path = Path(f.name)

        db_path.unlink()

        try:
            with SQLiteTaxonomyRepository(db_path) as repo:
                # Add root
                root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
                repo.add_node(root)

                # Add 100 children under root
                for i in range(2, 102):  # tax_ids 2-101
                    node = TaxonomyNode(
                        tax_id=i,
                        name=f"species_{i}",
                        rank=TaxonomicRank.SPECIES,
                        parent_id=1,
                    )
                    repo.add_node(node)

                # Test operations still work efficiently
                all_nodes = repo.get_all_nodes()
                assert len(all_nodes) == 101  # root + 100 species

                children = repo.get_children(1)
                assert len(children) == 100

                stats = repo.get_statistics()
                assert stats["node_count"] == 101
        finally:
            if db_path.exists():
                db_path.unlink()


class TestDatabaseErrorHandling:
    """Test database error handling and edge cases."""

    def test_database_file_permissions(self):
        """Test handling of database file permission issues."""
        # Create a read-only directory
        with tempfile.TemporaryDirectory() as tmp_dir:
            readonly_dir = Path(tmp_dir) / "readonly"
            readonly_dir.mkdir()
            readonly_dir.chmod(0o444)  # Read-only

            readonly_db = readonly_dir / "test.ftd"

            try:
                # This should raise an exception due to permissions
                with pytest.raises((DatabaseError, PermissionError, OSError)):
                    with SQLiteTaxonomyRepository(readonly_db) as repo:
                        pass
            finally:
                # Restore permissions for cleanup
                readonly_dir.chmod(0o755)

    def test_corrupted_database_handling(self):
        """Test handling of corrupted database file."""
        with tempfile.NamedTemporaryFile(suffix=".ftd", delete=False) as f:
            db_path = Path(f.name)
            # Write invalid data to create a corrupted "database"
            f.write(b"This is not a valid SQLite database")
            f.flush()

        try:
            # Attempting to open corrupted database should raise DatabaseError
            with pytest.raises(DatabaseError):
                with SQLiteTaxonomyRepository(db_path) as repo:
                    pass
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_disk_space_simulation(self):
        """Test simulation of disk space issues (mocked)."""
        with tempfile.NamedTemporaryFile(suffix=".ftd", delete=False) as f:
            db_path = Path(f.name)

        db_path.unlink()

        try:
            with SQLiteTaxonomyRepository(db_path) as repo:
                # Mock disk full error during write operation
                with patch.object(
                    repo._get_connection(),
                    "execute",
                    side_effect=sqlite3.OperationalError("database or disk is full"),
                ):
                    with pytest.raises(
                        DatabaseError, match="Database operation failed"
                    ):
                        root = TaxonomyNode(
                            tax_id=1, name="root", rank=TaxonomicRank.CUSTOM
                        )
                        repo.add_node(root)
        finally:
            if db_path.exists():
                db_path.unlink()
