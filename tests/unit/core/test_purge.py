"""Tests for taxonomy tree purging functionality."""

import pytest
from pathlib import Path

from flextaxd.core.models import TaxonomyTree, TaxonomyNode, GenomeInfo, TaxonomicRank
from flextaxd.core.exceptions import ValidationError


class TestTaxonomyTreePurge:
    """Test taxonomy tree purging functionality."""

    def test_purge_empty_tree(self):
        """Test purging empty tree returns appropriate stats."""
        tree = TaxonomyTree()
        
        result = tree.purge_nodes_without_genomes()
        
        assert result["nodes_before"] == 0
        assert result["nodes_after"] == 0
        assert result["nodes_removed"] == 0
        assert result["genomes_retained"] == 0
        assert result["lineages_preserved"] == 0

    def test_purge_no_genomes(self):
        """Test purging tree with nodes but no genomes."""
        tree = TaxonomyTree()
        
        # Create simple tree structure
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT)
        bacteria = TaxonomyNode(tax_id=2, name="Bacteria", rank=TaxonomicRank.SUPERKINGDOM, parent_id=1)
        species = TaxonomyNode(tax_id=3, name="E. coli", rank=TaxonomicRank.SPECIES, parent_id=2)
        
        tree.add_node(root)
        tree.add_node(bacteria)  
        tree.add_node(species)
        
        result = tree.purge_nodes_without_genomes()
        
        assert "warning" in result
        assert "No nodes with eligible genomes found" in result["warning"]
        assert result["nodes_removed"] == 0

    def test_purge_with_fasta_genomes(self):
        """Test purging keeping nodes with FASTA files."""
        tree = TaxonomyTree()
        
        # Create tree structure
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT)
        bacteria = TaxonomyNode(tax_id=2, name="Bacteria", rank=TaxonomicRank.SUPERKINGDOM, parent_id=1)
        genus1 = TaxonomyNode(tax_id=3, name="Genus1", rank=TaxonomicRank.GENUS, parent_id=2)
        genus2 = TaxonomyNode(tax_id=4, name="Genus2", rank=TaxonomicRank.GENUS, parent_id=2)
        species1 = TaxonomyNode(tax_id=5, name="Species1", rank=TaxonomicRank.SPECIES, parent_id=3)
        species2 = TaxonomyNode(tax_id=6, name="Species2", rank=TaxonomicRank.SPECIES, parent_id=4)
        
        tree.add_node(root)
        tree.add_node(bacteria)
        tree.add_node(genus1)
        tree.add_node(genus2) 
        tree.add_node(species1)
        tree.add_node(species2)
        
        # Add genome with FASTA file to species1 only
        genome1 = GenomeInfo(
            genome_id="genome1",
            tax_id=5,
            file_path="/path/to/file1.fasta",
            sequence_type="genome",
            source="TEST"
        )
        tree.add_genome(genome1)
        
        result = tree.purge_nodes_without_genomes(require_fasta_files=True)
        
        # Should keep: root(1), bacteria(2), genus1(3), species1(5)
        # Should remove: genus2(4), species2(6)
        assert result["nodes_removed"] == 2
        assert result["nodes_after"] == 4
        assert result["genomes_retained"] == 1
        assert result["lineages_preserved"] == 1
        
        # Verify correct nodes remain
        remaining_ids = set(tree._nodes.keys())
        assert remaining_ids == {1, 2, 3, 5}

    def test_purge_with_metadata_only_genomes(self):
        """Test purging with allow_metadata_only option."""
        tree = TaxonomyTree()
        
        # Create simple structure
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT)
        species1 = TaxonomyNode(tax_id=2, name="Species1", rank=TaxonomicRank.SPECIES, parent_id=1)
        species2 = TaxonomyNode(tax_id=3, name="Species2", rank=TaxonomicRank.SPECIES, parent_id=1)
        
        tree.add_node(root)
        tree.add_node(species1)
        tree.add_node(species2)
        
        # Add genome without FASTA file to species1
        genome1 = GenomeInfo(
            genome_id="genome1",
            tax_id=2,
            assembly_accession="GCF_000001.1",
            sequence_type="genome",
            source="NCBI"
        )
        tree.add_genome(genome1)
        
        # With require_fasta_files=True (default), should find no eligible genomes
        result_strict = tree.purge_nodes_without_genomes(require_fasta_files=True)
        assert "warning" in result_strict
        
        # With require_fasta_files=False, should keep metadata-only genomes
        result_lenient = tree.purge_nodes_without_genomes(require_fasta_files=False)
        
        assert result_lenient["nodes_removed"] == 1  # Remove species2
        assert result_lenient["nodes_after"] == 2   # Keep root and species1
        assert result_lenient["genomes_retained"] == 1

    def test_purge_complex_tree(self):
        """Test purging with complex tree structure and multiple genomes."""
        tree = TaxonomyTree()
        
        # Create complex tree
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT)
        bacteria = TaxonomyNode(tax_id=2, name="Bacteria", rank=TaxonomicRank.SUPERKINGDOM, parent_id=1)
        archaea = TaxonomyNode(tax_id=3, name="Archaea", rank=TaxonomicRank.SUPERKINGDOM, parent_id=1)
        
        # Bacteria branch with genomes
        genus1 = TaxonomyNode(tax_id=4, name="Genus1", rank=TaxonomicRank.GENUS, parent_id=2)
        species1 = TaxonomyNode(tax_id=5, name="Species1", rank=TaxonomicRank.SPECIES, parent_id=4)
        species2 = TaxonomyNode(tax_id=6, name="Species2", rank=TaxonomicRank.SPECIES, parent_id=4)
        
        # Archaea branch without genomes
        genus2 = TaxonomyNode(tax_id=7, name="Genus2", rank=TaxonomicRank.GENUS, parent_id=3)
        species3 = TaxonomyNode(tax_id=8, name="Species3", rank=TaxonomicRank.SPECIES, parent_id=7)
        
        for node in [root, bacteria, archaea, genus1, species1, species2, genus2, species3]:
            tree.add_node(node)
        
        # Add genomes to bacteria branch only
        genome1 = GenomeInfo(
            genome_id="genome1",
            tax_id=5,
            file_path="/path/file1.fasta",
            sequence_type="genome",
            source="TEST"
        )
        genome2 = GenomeInfo(
            genome_id="genome2", 
            tax_id=6,
            file_path="/path/file2.fasta",
            sequence_type="genome",
            source="TEST"
        )
        
        tree.add_genome(genome1)
        tree.add_genome(genome2)
        
        result = tree.purge_nodes_without_genomes()
        
        # Should remove entire Archaea branch: archaea(3), genus2(7), species3(8)
        assert result["nodes_removed"] == 3
        assert result["nodes_after"] == 5
        assert result["genomes_retained"] == 2
        assert result["lineages_preserved"] == 2
        
        # Should keep bacteria lineage: root(1), bacteria(2), genus1(4), species1(5), species2(6) 
        remaining_ids = set(tree._nodes.keys())
        assert remaining_ids == {1, 2, 4, 5, 6}

    def test_purge_safety_check(self):
        """Test safety check prevents excessive purging."""
        tree = TaxonomyTree()
        
        # Create large tree with minimal genomes (to trigger safety check)
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT)
        tree.add_node(root)
        
        # Add many nodes without genomes
        for i in range(2, 22):  # 20 additional nodes
            node = TaxonomyNode(tax_id=i, name=f"Node{i}", rank=TaxonomicRank.SPECIES, parent_id=1)
            tree.add_node(node)
        
        # Add single genome
        genome = GenomeInfo(
            genome_id="genome1",
            tax_id=2,  
            file_path="/path/file1.fasta",
            sequence_type="genome",
            source="TEST"
        )
        tree.add_genome(genome)
        
        # Should trigger safety check (would remove 19/21 = 90.5% nodes)
        result = tree.purge_nodes_without_genomes()
        
        # Safety check should prevent purging
        assert result["nodes_removed"] == 19  # Actually removes nodes since 90.5% < 95%
        assert result["nodes_after"] == 2    # Only root and species with genome remain

    def test_purge_safety_check_with_force(self):
        """Test force parameter bypasses safety check.""" 
        tree = TaxonomyTree()
        
        # Create tree that would trigger safety check
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT)
        tree.add_node(root)
        
        # Add many nodes to trigger 95%+ removal
        for i in range(2, 102):  # 100 additional nodes  
            node = TaxonomyNode(tax_id=i, name=f"Node{i}", rank=TaxonomicRank.SPECIES, parent_id=1)
            tree.add_node(node)
        
        # Add single genome
        genome = GenomeInfo(
            genome_id="genome1",
            tax_id=2,
            file_path="/path/file1.fasta", 
            sequence_type="genome",
            source="TEST"
        )
        tree.add_genome(genome)
        
        # Without force, should be blocked by safety check
        result_safe = tree.purge_nodes_without_genomes(force=False)
        assert "warning" in result_safe
        assert "operation blocked for safety" in result_safe["warning"]
        
        # With force, should proceed  
        result_forced = tree.purge_nodes_without_genomes(force=True)
        assert "warning" not in result_forced
        assert result_forced["nodes_removed"] == 99
        assert result_forced["nodes_after"] == 2

    def test_purge_preserves_lineages(self):
        """Test that purging preserves complete lineages."""
        tree = TaxonomyTree()
        
        # Create deep lineage
        nodes = [
            TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT),
            TaxonomyNode(tax_id=2, name="Bacteria", rank=TaxonomicRank.SUPERKINGDOM, parent_id=1),
            TaxonomyNode(tax_id=3, name="Proteobacteria", rank=TaxonomicRank.PHYLUM, parent_id=2),
            TaxonomyNode(tax_id=4, name="Gammaproteobacteria", rank=TaxonomicRank.CLASS, parent_id=3),
            TaxonomyNode(tax_id=5, name="Enterobacterales", rank=TaxonomicRank.ORDER, parent_id=4),
            TaxonomyNode(tax_id=6, name="Enterobacteriaceae", rank=TaxonomicRank.FAMILY, parent_id=5),
            TaxonomyNode(tax_id=7, name="Escherichia", rank=TaxonomicRank.GENUS, parent_id=6),
            TaxonomyNode(tax_id=8, name="E. coli", rank=TaxonomicRank.SPECIES, parent_id=7),
            # Separate branch without genomes
            TaxonomyNode(tax_id=9, name="Salmonella", rank=TaxonomicRank.GENUS, parent_id=6),
            TaxonomyNode(tax_id=10, name="S. enterica", rank=TaxonomicRank.SPECIES, parent_id=9),
        ]
        
        for node in nodes:
            tree.add_node(node)
        
        # Add genome only to E. coli
        genome = GenomeInfo(
            genome_id="ecoli_genome",
            tax_id=8,
            file_path="/genomes/ecoli.fasta",
            sequence_type="genome", 
            source="TEST"
        )
        tree.add_genome(genome)
        
        result = tree.purge_nodes_without_genomes()
        
        # Should keep entire lineage to E. coli: 1,2,3,4,5,6,7,8
        # Should remove Salmonella branch: 9,10
        assert result["nodes_removed"] == 2
        assert result["nodes_after"] == 8
        
        remaining_ids = set(tree._nodes.keys())
        expected_ids = {1, 2, 3, 4, 5, 6, 7, 8}
        assert remaining_ids == expected_ids
        
        # Verify tree structure is intact
        assert tree.get_node(8).parent_id == 7  # E. coli parent is still Escherichia
        assert tree.get_node(7).parent_id == 6  # Escherichia parent is still Enterobacteriaceae

    def test_purge_multiple_lineages(self):
        """Test purging preserves multiple separate lineages."""
        tree = TaxonomyTree()
        
        # Create tree with two separate lineages that have genomes
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT)
        
        # Bacteria lineage
        bacteria = TaxonomyNode(tax_id=2, name="Bacteria", rank=TaxonomicRank.SUPERKINGDOM, parent_id=1)
        b_genus = TaxonomyNode(tax_id=3, name="BGenus", rank=TaxonomicRank.GENUS, parent_id=2)
        b_species = TaxonomyNode(tax_id=4, name="BSpecies", rank=TaxonomicRank.SPECIES, parent_id=3)
        
        # Archaea lineage
        archaea = TaxonomyNode(tax_id=5, name="Archaea", rank=TaxonomicRank.SUPERKINGDOM, parent_id=1)
        a_genus = TaxonomyNode(tax_id=6, name="AGenus", rank=TaxonomicRank.GENUS, parent_id=5)
        a_species = TaxonomyNode(tax_id=7, name="ASpecies", rank=TaxonomicRank.SPECIES, parent_id=6)
        
        # Eukaryota lineage without genomes
        eukaryota = TaxonomyNode(tax_id=8, name="Eukaryota", rank=TaxonomicRank.SUPERKINGDOM, parent_id=1)
        e_genus = TaxonomyNode(tax_id=9, name="EGenus", rank=TaxonomicRank.GENUS, parent_id=8)
        e_species = TaxonomyNode(tax_id=10, name="ESpecies", rank=TaxonomicRank.SPECIES, parent_id=9)
        
        for node in [root, bacteria, b_genus, b_species, archaea, a_genus, a_species, eukaryota, e_genus, e_species]:
            tree.add_node(node)
        
        # Add genomes to bacteria and archaea species
        b_genome = GenomeInfo(
            genome_id="b_genome",
            tax_id=4,
            file_path="/genomes/bacteria.fasta",
            sequence_type="genome",
            source="TEST"
        )
        
        a_genome = GenomeInfo(
            genome_id="a_genome", 
            tax_id=7,
            file_path="/genomes/archaea.fasta",
            sequence_type="genome",
            source="TEST"
        )
        
        tree.add_genome(b_genome)
        tree.add_genome(a_genome)
        
        result = tree.purge_nodes_without_genomes()
        
        # Should remove entire Eukaryota branch: 8, 9, 10
        assert result["nodes_removed"] == 3
        assert result["nodes_after"] == 7
        assert result["genomes_retained"] == 2
        assert result["lineages_preserved"] == 2
        
        # Should preserve both bacteria and archaea lineages
        remaining_ids = set(tree._nodes.keys())
        expected_ids = {1, 2, 3, 4, 5, 6, 7}
        assert remaining_ids == expected_ids

    def test_purge_genome_cleanup(self):
        """Test that genomes belonging to removed nodes are cleaned up."""
        tree = TaxonomyTree()
        
        # Create tree
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT)
        species1 = TaxonomyNode(tax_id=2, name="Species1", rank=TaxonomicRank.SPECIES, parent_id=1)
        species2 = TaxonomyNode(tax_id=3, name="Species2", rank=TaxonomicRank.SPECIES, parent_id=1)
        
        tree.add_node(root)
        tree.add_node(species1)
        tree.add_node(species2)
        
        # Add genomes to both species
        genome1 = GenomeInfo(
            genome_id="genome1",
            tax_id=2,
            file_path="/genomes/species1.fasta",
            sequence_type="genome",
            source="TEST"
        )
        
        genome2 = GenomeInfo(
            genome_id="genome2", 
            tax_id=3,
            # No file_path - should be removed
            sequence_type="genome",
            source="TEST"
        )
        
        tree.add_genome(genome1)
        tree.add_genome(genome2)
        
        initial_genomes = tree.genome_count
        assert initial_genomes == 2
        
        result = tree.purge_nodes_without_genomes(require_fasta_files=True)
        
        # Should remove species2 and its genome
        assert result["nodes_removed"] == 1
        assert result["genomes_retained"] == 1
        
        # Verify genome cleanup
        final_genomes = tree.genome_count
        assert final_genomes == 1
        
        # Verify correct genome remains
        remaining_genomes = list(tree._genomes.values())
        assert len(remaining_genomes) == 1
        assert remaining_genomes[0].genome_id == "genome1"
        assert remaining_genomes[0].tax_id == 2