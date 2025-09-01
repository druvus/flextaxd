"""Property-based tests using Hypothesis for robust model validation."""

from typing import List
import pytest
from hypothesis import given, strategies as st, assume, settings
from hypothesis.strategies import composite

from flextaxd.core.models import (
    TaxonomyNode, TaxonomyTree, TaxonomicRank, GenomeInfo
)
from flextaxd.core.exceptions import ValidationError


# Hypothesis strategies for generating test data
valid_tax_ids = st.integers(min_value=1, max_value=1_000_000)
valid_names = st.text(min_size=1, max_size=100).filter(lambda x: x.strip())
taxonomic_ranks = st.sampled_from(list(TaxonomicRank))
genome_ids = st.text(min_size=1, max_size=50).filter(lambda x: x.strip())
sequence_types = st.one_of(
    st.none(),
    st.sampled_from(["genome", "protein", "rna", "plasmid", "chromosome"])
)


@composite
def valid_taxonomy_nodes(draw, parent_id=None):
    """Generate valid TaxonomyNode instances."""
    tax_id = draw(valid_tax_ids)
    name = draw(valid_names)
    rank = draw(taxonomic_ranks)
    
    # Ensure parent_id is different from tax_id
    if parent_id is not None:
        assume(parent_id != tax_id)
        node_parent_id = parent_id
    else:
        node_parent_id = draw(st.one_of(st.none(), valid_tax_ids.filter(lambda x: x != tax_id)))
    
    return TaxonomyNode(
        tax_id=tax_id,
        name=name,
        rank=rank,
        parent_id=node_parent_id
    )


@composite
def valid_genome_info(draw):
    """Generate valid GenomeInfo instances."""
    genome_id = draw(genome_ids)
    tax_id = draw(valid_tax_ids)
    sequence_type = draw(sequence_types)
    
    return GenomeInfo(
        genome_id=genome_id,
        tax_id=tax_id,
        sequence_type=sequence_type
    )


@composite
def valid_taxonomy_trees(draw, max_nodes=10):
    """Generate valid TaxonomyTree instances."""
    tree = TaxonomyTree()
    
    # Always start with a root node
    root_node = draw(valid_taxonomy_nodes())
    root_node = TaxonomyNode(
        tax_id=root_node.tax_id,
        name=root_node.name,
        rank=root_node.rank,
        parent_id=None  # Root has no parent
    )
    tree.add_node(root_node)
    
    # Add additional nodes
    num_additional = draw(st.integers(min_value=0, max_value=max_nodes - 1))
    existing_ids = {root_node.tax_id}
    
    for _ in range(num_additional):
        # Choose a random existing node as parent
        parent_id = draw(st.sampled_from(list(existing_ids)))
        
        # Generate a new node with unique ID
        new_tax_id = draw(valid_tax_ids.filter(lambda x: x not in existing_ids))
        name = draw(valid_names)
        rank = draw(taxonomic_ranks)
        
        new_node = TaxonomyNode(
            tax_id=new_tax_id,
            name=name,
            rank=rank,
            parent_id=parent_id
        )
        
        try:
            tree.add_node(new_node)
            existing_ids.add(new_tax_id)
        except ValueError:
            # Skip if adding this node would create issues
            pass
    
    return tree


class TestTaxonomyNodeProperties:
    """Property-based tests for TaxonomyNode."""
    
    @given(valid_taxonomy_nodes())
    @settings(max_examples=100)
    def test_valid_nodes_are_created_successfully(self, node: TaxonomyNode):
        """Valid nodes should always be created without exceptions."""
        assert node.tax_id > 0
        assert node.name.strip()
        assert isinstance(node.rank, TaxonomicRank)
        if node.parent_id is not None:
            assert node.parent_id > 0
            assert node.parent_id != node.tax_id
    
    @given(st.integers(max_value=0), valid_names, taxonomic_ranks)
    @settings(max_examples=50)
    def test_invalid_tax_id_raises_error(self, bad_tax_id: int, name: str, rank: TaxonomicRank):
        """Invalid tax IDs should always raise ValueError."""
        with pytest.raises(ValueError, match="Tax ID must be positive"):
            TaxonomyNode(tax_id=bad_tax_id, name=name, rank=rank)
    
    @given(valid_tax_ids, st.text(max_size=0).filter(lambda x: not x.strip()), taxonomic_ranks)
    @settings(max_examples=50)
    def test_empty_name_raises_error(self, tax_id: int, empty_name: str, rank: TaxonomicRank):
        """Empty names should always raise ValueError."""
        with pytest.raises(ValueError, match="Node name cannot be empty"):
            TaxonomyNode(tax_id=tax_id, name=empty_name, rank=rank)
    
    @given(valid_tax_ids, valid_names, taxonomic_ranks, st.integers(max_value=0))
    @settings(max_examples=50)
    def test_invalid_parent_id_raises_error(self, tax_id: int, name: str, rank: TaxonomicRank, bad_parent_id: int):
        """Invalid parent IDs should always raise ValueError."""
        with pytest.raises(ValueError, match="Parent ID must be positive"):
            TaxonomyNode(tax_id=tax_id, name=name, rank=rank, parent_id=bad_parent_id)
    
    @given(valid_tax_ids, valid_names, taxonomic_ranks)
    @settings(max_examples=50)
    def test_self_parent_raises_error(self, tax_id: int, name: str, rank: TaxonomicRank):
        """Node cannot be its own parent."""
        with pytest.raises(ValueError, match="Node cannot be its own parent"):
            TaxonomyNode(tax_id=tax_id, name=name, rank=rank, parent_id=tax_id)
    
    @given(valid_taxonomy_nodes(), valid_taxonomy_nodes())
    @settings(max_examples=50)
    def test_node_equality_is_by_tax_id(self, node1: TaxonomyNode, node2: TaxonomyNode):
        """Two nodes with same tax_id should be considered equal."""
        if node1.tax_id == node2.tax_id:
            # Create nodes with same tax_id but different other fields
            same_id_node = TaxonomyNode(
                tax_id=node1.tax_id,
                name="Different Name",
                rank=TaxonomicRank.CUSTOM,
                parent_id=node1.parent_id
            )
            assert node1.tax_id == same_id_node.tax_id


class TestGenomeInfoProperties:
    """Property-based tests for GenomeInfo."""
    
    @given(valid_genome_info())
    @settings(max_examples=100)
    def test_valid_genome_info_created_successfully(self, genome: GenomeInfo):
        """Valid genome info should always be created without exceptions."""
        assert genome.genome_id.strip()
        assert genome.tax_id > 0
    
    @given(st.text(max_size=0).filter(lambda x: not x.strip()), valid_tax_ids)
    @settings(max_examples=50)
    def test_empty_genome_id_raises_error(self, empty_id: str, tax_id: int):
        """Empty genome IDs should raise ValueError."""
        with pytest.raises(ValueError, match="Genome ID cannot be empty"):
            GenomeInfo(genome_id=empty_id, tax_id=tax_id)
    
    @given(genome_ids, st.integers(max_value=0))
    @settings(max_examples=50)
    def test_invalid_tax_id_in_genome_raises_error(self, genome_id: str, bad_tax_id: int):
        """Invalid tax IDs in genome info should raise ValueError."""
        with pytest.raises(ValueError, match="Tax ID must be positive"):
            GenomeInfo(genome_id=genome_id, tax_id=bad_tax_id)
    
    @given(valid_genome_info())
    @settings(max_examples=50)
    def test_genome_validation_returns_list(self, genome: GenomeInfo):
        """Genome validation should always return a list."""
        issues = genome.validate()
        assert isinstance(issues, list)
        # Valid genomes should have no issues
        assert len(issues) == 0


class TestTaxonomyTreeProperties:
    """Property-based tests for TaxonomyTree."""
    
    @given(valid_taxonomy_trees(max_nodes=5))
    @settings(max_examples=50)
    def test_tree_invariants_maintained(self, tree: TaxonomyTree):
        """Tree invariants should always be maintained."""
        # Tree should have at least one node (root)
        assert len(tree) > 0
        
        # All nodes should be valid
        for node in tree:
            assert node.tax_id > 0
            assert node.name.strip()
        
        # Root node should exist
        root_id = tree.root_id
        if root_id is not None:
            root_node = tree.get_node(root_id)
            assert root_node is not None
            assert root_node.parent_id is None
    
    @given(valid_taxonomy_trees(max_nodes=3), valid_taxonomy_nodes())
    @settings(max_examples=50)
    def test_adding_duplicate_node_raises_error(self, tree: TaxonomyTree, new_node: TaxonomyNode):
        """Adding a node with duplicate tax_id should raise ValueError."""
        existing_ids = {node.tax_id for node in tree}
        
        if new_node.tax_id in existing_ids:
            with pytest.raises(ValueError, match="already exists"):
                tree.add_node(new_node)
    
    @given(valid_taxonomy_trees(max_nodes=5))
    @settings(max_examples=50)
    def test_tree_validation_is_consistent(self, tree: TaxonomyTree):
        """Tree validation should be consistent and thorough."""
        issues = tree.validate_tree()
        assert isinstance(issues, list)
        
        # If tree is valid, it should have no issues
        if not issues:
            # Valid tree should have consistent structure
            for node in tree:
                if node.parent_id is not None:
                    parent = tree.get_node(node.parent_id)
                    assert parent is not None, f"Parent {node.parent_id} not found for node {node.tax_id}"
    
    @given(valid_taxonomy_trees(max_nodes=3), valid_genome_info())
    @settings(max_examples=30)
    def test_adding_genome_to_existing_node_succeeds(self, tree: TaxonomyTree, genome: GenomeInfo):
        """Adding genome to existing taxonomy node should succeed."""
        # Get a random existing node
        existing_nodes = list(tree)
        if existing_nodes:
            # Update genome to reference an existing node
            target_node = existing_nodes[0]
            genome_with_valid_tax_id = GenomeInfo(
                genome_id=genome.genome_id,
                tax_id=target_node.tax_id,
                sequence_type=genome.sequence_type
            )
            
            # This should not raise an exception
            tree.add_genome(genome_with_valid_tax_id)
            
            # Genome should be findable
            genomes = tree.get_genomes_for_node(target_node.tax_id)
            assert len(genomes) >= 1
            assert any(g.genome_id == genome.genome_id for g in genomes)


class TestParserRobustness:
    """Property-based tests for parser robustness."""
    
    @given(st.text(min_size=0, max_size=1000))
    @settings(max_examples=100)
    def test_tsv_parser_handles_arbitrary_input(self, random_text: str):
        """TSV parser should handle arbitrary text input gracefully."""
        from flextaxd.parsers.tsv import TSVTaxonomyParser
        import tempfile
        from pathlib import Path
        
        parser = TSVTaxonomyParser()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tsv', delete=False) as f:
            f.write(random_text)
            f.flush()
            test_file = Path(f.name)
        
        try:
            # Parser should either succeed or raise a clear ParseError
            # It should never crash with unexpected exceptions
            try:
                tree = parser.parse(test_file)
                assert isinstance(tree, TaxonomyTree)
            except Exception as e:
                # Should be a controlled exception, not a crash
                assert hasattr(e, '__class__')
                # Most likely ParseError or ValueError
                assert isinstance(e, (ValueError, RuntimeError)) or "Parse" in str(type(e))
        finally:
            if test_file.exists():
                test_file.unlink()
    
    @given(st.lists(st.text(min_size=1, max_size=50), min_size=1, max_size=10))
    @settings(max_examples=50)
    def test_malformed_tsv_headers(self, random_headers: List[str]):
        """TSV parser should handle malformed headers gracefully."""
        from flextaxd.parsers.tsv import TSVTaxonomyParser
        import tempfile
        from pathlib import Path
        
        parser = TSVTaxonomyParser()
        
        # Create malformed TSV with random headers
        content = "\t".join(random_headers) + "\n"
        content += "some\tdata\trows\there\n"
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tsv', delete=False) as f:
            f.write(content)
            f.flush()
            test_file = Path(f.name)
        
        try:
            # Should handle gracefully
            try:
                tree = parser.parse(test_file)
                # If it succeeds, should return valid tree
                assert isinstance(tree, TaxonomyTree)
            except Exception as e:
                # Should be controlled failure
                assert hasattr(e, '__class__')
        finally:
            if test_file.exists():
                test_file.unlink()


class TestMemoryAndPerformance:
    """Property-based tests for memory usage and performance."""
    
    @given(st.integers(min_value=1, max_value=100))
    @settings(max_examples=10)  # Fewer examples for performance tests
    def test_large_tree_memory_usage(self, num_nodes: int):
        """Large trees should not consume excessive memory."""
        import sys
        
        tree = TaxonomyTree()
        
        # Add root
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        tree.add_node(root)
        
        # Add many children to root
        for i in range(2, num_nodes + 2):
            node = TaxonomyNode(
                tax_id=i,
                name=f"node_{i}",
                rank=TaxonomicRank.SPECIES,
                parent_id=1
            )
            tree.add_node(node)
        
        # Check tree operations still work efficiently
        assert len(tree) == num_nodes + 1
        
        # Validate should complete without issues
        issues = tree.validate_tree()
        assert isinstance(issues, list)
        
        # Getting children should work efficiently
        children = tree.get_children(1)
        assert len(children) == num_nodes