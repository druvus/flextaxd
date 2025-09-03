"""Unit tests for core domain models."""

import pytest
from pathlib import Path
from tempfile import NamedTemporaryFile

from flextaxd.core.models import TaxonomyNode, TaxonomyTree, TaxonomicRank, GenomeInfo


class TestTaxonomicRank:
    """Test TaxonomicRank enum."""

    def test_all_ranks_have_string_values(self):
        """All taxonomic ranks should have string values."""
        for rank in TaxonomicRank:
            assert isinstance(rank.value, str)
            assert len(rank.value) > 0

    def test_standard_ranks_exist(self):
        """Standard taxonomic ranks should exist."""
        expected_ranks = [
            "root",
            "superkingdom",
            "kingdom",
            "phylum",
            "class",
            "order",
            "family",
            "genus",
            "species",
            "subspecies",
            "strain",
            "custom",
        ]

        actual_ranks = [rank.value for rank in TaxonomicRank]
        for expected in expected_ranks:
            assert expected in actual_ranks


class TestTaxonomyNode:
    """Test TaxonomyNode model."""

    def test_create_valid_node(self):
        """Test creating a valid taxonomy node."""
        node = TaxonomyNode(
            tax_id=123,
            name="Escherichia coli",
            rank=TaxonomicRank.SPECIES,
            parent_id=122,
        )

        assert node.tax_id == 123
        assert node.name == "Escherichia coli"
        assert node.rank == TaxonomicRank.SPECIES
        assert node.parent_id == 122

    def test_node_validation_invalid_id(self):
        """Test that invalid tax_id raises ValueError."""
        with pytest.raises(ValueError, match="Tax ID must be positive"):
            TaxonomyNode(tax_id=0, name="Test")

        with pytest.raises(ValueError, match="Tax ID must be positive"):
            TaxonomyNode(tax_id=-1, name="Test")

    def test_node_validation_empty_name(self):
        """Test that empty name raises ValueError."""
        with pytest.raises(ValueError, match="Node name cannot be empty"):
            TaxonomyNode(tax_id=1, name="")

        with pytest.raises(ValueError, match="Node name cannot be empty"):
            TaxonomyNode(tax_id=1, name="   ")

    def test_node_validation_invalid_parent_id(self):
        """Test that invalid parent_id raises ValueError."""
        with pytest.raises(ValueError, match="Parent ID must be positive"):
            TaxonomyNode(tax_id=1, name="Test", parent_id=0)

        with pytest.raises(ValueError, match="Parent ID must be positive"):
            TaxonomyNode(tax_id=1, name="Test", parent_id=-1)

    def test_node_validation_self_parent(self):
        """Test that node cannot be its own parent."""
        with pytest.raises(ValueError, match="Node cannot be its own parent"):
            TaxonomyNode(tax_id=1, name="Test", parent_id=1)

    def test_node_immutability(self):
        """Test that nodes are immutable (frozen dataclass)."""
        node = TaxonomyNode(tax_id=1, name="Test")

        with pytest.raises(AttributeError):
            node.name = "New Name"


class TestTaxonomyTree:
    """Test TaxonomyTree model."""

    def test_create_empty_tree(self):
        """Test creating an empty tree."""
        tree = TaxonomyTree()
        assert tree.node_count == 0
        assert tree.genome_count == 0
        assert tree.root_id is None

    def test_add_root_node(self):
        """Test adding a root node."""
        tree = TaxonomyTree()
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT)

        tree.add_node(root)

        assert tree.node_count == 1
        assert tree.root_id == 1
        assert tree.get_node(1) == root

    def test_add_child_node(self):
        """Test adding a child node."""
        tree = TaxonomyTree()
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT)
        child = TaxonomyNode(tax_id=2, name="child", parent_id=1)

        tree.add_node(root)
        tree.add_node(child)

        assert tree.node_count == 2
        assert tree.get_children(1) == {2}
        assert tree.get_node(2) == child

    def test_add_duplicate_node_fails(self):
        """Test that adding duplicate node fails."""
        tree = TaxonomyTree()
        node1 = TaxonomyNode(tax_id=1, name="First")
        node2 = TaxonomyNode(tax_id=1, name="Second")

        tree.add_node(node1)

        with pytest.raises(ValueError, match="Node with ID 1 already exists"):
            tree.add_node(node2)

    def test_add_node_with_missing_parent_fails(self):
        """Test that adding node with missing parent fails."""
        tree = TaxonomyTree()
        child = TaxonomyNode(tax_id=2, name="child", parent_id=1)

        with pytest.raises(ValueError, match="Parent node 1 does not exist"):
            tree.add_node(child)

    def test_multiple_roots_not_allowed(self):
        """Test that multiple root nodes are not allowed."""
        tree = TaxonomyTree()
        root1 = TaxonomyNode(tax_id=1, name="root1")
        root2 = TaxonomyNode(tax_id=2, name="root2")

        tree.add_node(root1)

        with pytest.raises(ValueError, match="Tree already has a root node"):
            tree.add_node(root2)

    def test_get_descendants(self):
        """Test getting all descendants of a node."""
        tree = TaxonomyTree()

        # Build tree: 1 -> 2 -> 3, 1 -> 4
        root = TaxonomyNode(tax_id=1, name="root")
        child1 = TaxonomyNode(tax_id=2, name="child1", parent_id=1)
        child2 = TaxonomyNode(tax_id=3, name="grandchild", parent_id=2)
        child3 = TaxonomyNode(tax_id=4, name="child2", parent_id=1)

        for node in [root, child1, child2, child3]:
            tree.add_node(node)

        descendants = tree.get_descendants(1)
        assert descendants == {2, 3, 4}

        descendants = tree.get_descendants(2)
        assert descendants == {3}

        descendants = tree.get_descendants(3)
        assert descendants == set()

    def test_get_path_to_root(self):
        """Test getting path from node to root."""
        tree = TaxonomyTree()

        # Build tree: 1 -> 2 -> 3
        root = TaxonomyNode(tax_id=1, name="root")
        child = TaxonomyNode(tax_id=2, name="child", parent_id=1)
        grandchild = TaxonomyNode(tax_id=3, name="grandchild", parent_id=2)

        for node in [root, child, grandchild]:
            tree.add_node(node)

        path = tree.get_path_to_root(3)
        assert len(path) == 3
        assert [n.tax_id for n in path] == [3, 2, 1]

    def test_remove_node(self):
        """Test removing a node."""
        tree = TaxonomyTree()
        root = TaxonomyNode(tax_id=1, name="root")
        child = TaxonomyNode(tax_id=2, name="child", parent_id=1)

        tree.add_node(root)
        tree.add_node(child)

        tree.remove_node(2)

        assert tree.node_count == 1
        assert tree.get_node(2) is None
        assert tree.get_children(1) == set()

    def test_add_genome(self):
        """Test adding genome information."""
        tree = TaxonomyTree()
        node = TaxonomyNode(tax_id=1, name="species")
        genome = GenomeInfo(genome_id="GCF_123", tax_id=1)

        tree.add_node(node)
        tree.add_genome(genome)

        assert tree.genome_count == 1
        genomes = tree.get_genomes_for_node(1)
        assert len(genomes) == 1
        assert genomes[0].genome_id == "GCF_123"

    def test_validate_tree(self):
        """Test tree validation."""
        tree = TaxonomyTree()
        root = TaxonomyNode(tax_id=1, name="root")
        tree.add_node(root)

        # Valid tree should have no issues
        issues = tree.validate_tree()
        assert issues == []

    def test_tree_iteration(self):
        """Test iterating over tree nodes."""
        tree = TaxonomyTree()
        root = TaxonomyNode(tax_id=1, name="root")
        child = TaxonomyNode(tax_id=2, name="child", parent_id=1)

        tree.add_node(root)
        tree.add_node(child)

        nodes = list(tree)
        assert len(nodes) == 2
        node_ids = {n.tax_id for n in nodes}
        assert node_ids == {1, 2}

    def test_tree_contains(self):
        """Test membership testing."""
        tree = TaxonomyTree()
        root = TaxonomyNode(tax_id=1, name="root")
        tree.add_node(root)

        assert 1 in tree
        assert 2 not in tree


class TestGenomeInfo:
    """Test GenomeInfo model."""

    def test_create_valid_genome(self):
        """Test creating valid genome info."""
        genome = GenomeInfo(
            genome_id="GCF_123456.1",
            tax_id=12345,
            file_path="/path/to/genome.fasta",
            assembly_accession="GCF_123456.1",
            source="NCBI",
        )

        assert genome.genome_id == "GCF_123456.1"
        assert genome.tax_id == 12345
        assert genome.file_path == "/path/to/genome.fasta"

    def test_genome_validation_empty_id(self):
        """Test that empty genome ID raises ValueError."""
        with pytest.raises(ValueError, match="Genome ID cannot be empty"):
            GenomeInfo(genome_id="", tax_id=123)

        with pytest.raises(ValueError, match="Genome ID cannot be empty"):
            GenomeInfo(genome_id="   ", tax_id=123)

    def test_genome_validation_invalid_tax_id(self):
        """Test that invalid tax_id raises ValueError."""
        with pytest.raises(ValueError, match="Tax ID must be positive"):
            GenomeInfo(genome_id="test", tax_id=0)

        with pytest.raises(ValueError, match="Tax ID must be positive"):
            GenomeInfo(genome_id="test", tax_id=-1)

    def test_genome_validate_method_valid(self):
        """Test validate method with valid genome."""
        genome = GenomeInfo(genome_id="test", tax_id=123)
        issues = genome.validate()

        assert isinstance(issues, list)
        assert len(issues) == 0

    def test_genome_validate_method_missing_file(self):
        """Test validate method with missing file."""
        genome = GenomeInfo(
            genome_id="test", tax_id=123, file_path="/nonexistent/file.fasta"
        )

        issues = genome.validate()
        assert len(issues) == 1
        assert "does not exist" in issues[0]

    def test_has_sequence_file_property(self):
        """Test has_sequence_file property."""
        # No file path
        genome1 = GenomeInfo(genome_id="test1", tax_id=123)
        assert not genome1.has_sequence_file

        # Nonexistent file
        genome2 = GenomeInfo(
            genome_id="test2", tax_id=123, file_path="/nonexistent.fasta"
        )
        assert not genome2.has_sequence_file

        # Create temporary file to test existing file
        with NamedTemporaryFile(delete=False, suffix=".fasta") as tmp:
            tmp.write(b">test\nACGT\n")
            tmp_path = tmp.name

        try:
            genome3 = GenomeInfo(genome_id="test3", tax_id=123, file_path=tmp_path)
            assert genome3.has_sequence_file
        finally:
            Path(tmp_path).unlink()

    def test_file_size_property(self):
        """Test file_size property."""
        # No file path
        genome1 = GenomeInfo(genome_id="test1", tax_id=123)
        assert genome1.file_size is None

        # Create temporary file to test file size
        test_content = b">test sequence\nACGTACGT\n"
        with NamedTemporaryFile(delete=False, suffix=".fasta") as tmp:
            tmp.write(test_content)
            tmp_path = tmp.name

        try:
            genome2 = GenomeInfo(genome_id="test2", tax_id=123, file_path=tmp_path)
            assert genome2.file_size == len(test_content)
        finally:
            Path(tmp_path).unlink()

    def test_genome_immutability(self):
        """Test that genome info is immutable."""
        genome = GenomeInfo(genome_id="test", tax_id=123)

        with pytest.raises(AttributeError):
            genome.genome_id = "changed"  # type: ignore
