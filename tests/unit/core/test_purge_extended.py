"""Extended tests for taxonomy tree purging functionality - comprehensive edge cases and robustness."""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch, mock_open

from flextaxd.core.models import TaxonomyTree, TaxonomyNode, GenomeInfo, TaxonomicRank
from flextaxd.core.exceptions import ValidationError


class TestTaxonomyTreePurgeExtended:
    """Extended test cases for purge functionality robustness."""

    def test_purge_single_root_node(self):
        """Test purging tree with only root node."""
        tree = TaxonomyTree()
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT)
        tree.add_node(root)
        
        # No genomes - should get warning
        result = tree.purge_nodes_without_genomes()
        assert "warning" in result
        assert "No nodes with eligible genomes found" in result["warning"]
        
        # Add genome to root
        genome = GenomeInfo(
            genome_id="root_genome",
            tax_id=1,
            file_path="/root.fasta",
            sequence_type="genome",
            source="TEST"
        )
        tree.add_genome(genome)
        
        # Should keep just the root
        result = tree.purge_nodes_without_genomes()
        assert result["nodes_removed"] == 0
        assert result["nodes_after"] == 1
        assert result["genomes_retained"] == 1

    def test_purge_with_intermediate_genome_nodes(self):
        """Test purging when intermediate (non-leaf) nodes have genomes."""
        tree = TaxonomyTree()
        
        # Create lineage: root -> genus -> species1, species2
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT)
        genus = TaxonomyNode(tax_id=2, name="Genus", rank=TaxonomicRank.GENUS, parent_id=1)
        species1 = TaxonomyNode(tax_id=3, name="Species1", rank=TaxonomicRank.SPECIES, parent_id=2)
        species2 = TaxonomyNode(tax_id=4, name="Species2", rank=TaxonomicRank.SPECIES, parent_id=2)
        # Orphan branch
        orphan = TaxonomyNode(tax_id=5, name="Orphan", rank=TaxonomicRank.SPECIES, parent_id=1)
        
        for node in [root, genus, species1, species2, orphan]:
            tree.add_node(node)
        
        # Add genome to genus (intermediate node) only
        genome = GenomeInfo(
            genome_id="genus_genome",
            tax_id=2,  # Genus has the genome
            file_path="/genus.fasta",
            sequence_type="16S",
            source="TEST"
        )
        tree.add_genome(genome)
        
        result = tree.purge_nodes_without_genomes()
        
        # Should keep: root(1), genus(2) (and children are removed when parent is reassigned)
        # Should remove: species1(3), species2(4), orphan(5) since they don't have genomes
        assert result["nodes_removed"] == 3
        assert result["nodes_after"] == 2
        remaining_ids = set(tree._nodes.keys())
        assert remaining_ids == {1, 2}

    def test_purge_with_invalid_genome_tax_ids(self):
        """Test purging with genomes pointing to non-existent nodes."""
        tree = TaxonomyTree()
        
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT)
        species = TaxonomyNode(tax_id=2, name="Species", rank=TaxonomicRank.SPECIES, parent_id=1)
        tree.add_node(root)
        tree.add_node(species)
        
        # Add valid genome
        valid_genome = GenomeInfo(
            genome_id="valid",
            tax_id=2,
            file_path="/valid.fasta",
            sequence_type="genome", 
            source="TEST"
        )
        
        # Add genome with invalid tax_id (node doesn't exist)
        invalid_genome = GenomeInfo(
            genome_id="invalid",
            tax_id=999,  # Non-existent node
            file_path="/invalid.fasta", 
            sequence_type="genome",
            source="TEST"
        )
        
        tree.add_genome(valid_genome)
        # Manually add invalid genome to bypass validation
        tree._genomes[invalid_genome.genome_id] = invalid_genome
        
        # Should only consider valid genome
        result = tree.purge_nodes_without_genomes()
        
        # Should keep root(1) and species(2) based on valid genome
        assert result["nodes_removed"] == 0
        assert result["nodes_after"] == 2
        assert result["genomes_retained"] == 1  # Only valid genome counted
        
        # Invalid genome should be cleaned up
        assert len(tree._genomes) == 1
        assert "valid" in tree._genomes
        assert "invalid" not in tree._genomes

    def test_purge_with_empty_and_whitespace_file_paths(self):
        """Test handling of empty, None, and whitespace-only file paths."""
        tree = TaxonomyTree()
        
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT)
        species1 = TaxonomyNode(tax_id=2, name="Species1", rank=TaxonomicRank.SPECIES, parent_id=1)
        species2 = TaxonomyNode(tax_id=3, name="Species2", rank=TaxonomicRank.SPECIES, parent_id=1)
        species3 = TaxonomyNode(tax_id=4, name="Species3", rank=TaxonomicRank.SPECIES, parent_id=1)
        species4 = TaxonomyNode(tax_id=5, name="Species4", rank=TaxonomicRank.SPECIES, parent_id=1)
        
        for node in [root, species1, species2, species3, species4]:
            tree.add_node(node)
        
        genomes = [
            GenomeInfo(genome_id="valid", tax_id=2, file_path="/valid.fasta", sequence_type="genome", source="TEST"),
            GenomeInfo(genome_id="none_path", tax_id=3, file_path=None, sequence_type="genome", source="TEST"), 
            GenomeInfo(genome_id="empty_path", tax_id=4, file_path="", sequence_type="genome", source="TEST"),
            GenomeInfo(genome_id="whitespace", tax_id=5, file_path="   \t\n  ", sequence_type="genome", source="TEST"),
        ]
        
        for genome in genomes:
            tree.add_genome(genome)
        
        # With require_fasta_files=True, only valid file should count
        result = tree.purge_nodes_without_genomes(require_fasta_files=True)
        
        # Should keep root(1) and species1(2) only
        assert result["nodes_removed"] == 3
        assert result["nodes_after"] == 2
        assert result["genomes_retained"] == 1
        
        # With require_fasta_files=False, should keep all nodes with genomes
        tree = TaxonomyTree()
        for node in [root, species1, species2, species3, species4]:
            tree.add_node(node)
        for genome in genomes:
            tree.add_genome(genome)
            
        result = tree.purge_nodes_without_genomes(require_fasta_files=False)
        
        # Should remove no nodes (all species have genome data)
        assert result["nodes_removed"] == 0
        assert result["nodes_after"] == 5
        assert result["genomes_retained"] == 4

    def test_purge_very_deep_tree(self):
        """Test purging with very deep tree structure (performance/recursion)."""
        tree = TaxonomyTree()
        
        # Create deep linear tree (50 levels)
        nodes = []
        ranks = list(TaxonomicRank)
        
        for i in range(50):
            rank = ranks[i % len(ranks)]
            parent_id = i if i > 0 else None
            node = TaxonomyNode(tax_id=i+1, name=f"Node{i+1}", rank=rank, parent_id=parent_id)
            nodes.append(node)
            tree.add_node(node)
        
        # Add genome only to deepest node
        genome = GenomeInfo(
            genome_id="deep_genome",
            tax_id=50,  # Deepest node
            file_path="/deep.fasta",
            sequence_type="genome",
            source="TEST"
        )
        tree.add_genome(genome)
        
        result = tree.purge_nodes_without_genomes()
        
        # Should keep entire lineage (all 50 nodes)
        assert result["nodes_removed"] == 0
        assert result["nodes_after"] == 50
        assert result["genomes_retained"] == 1
        
        # Verify lineage integrity
        current_node = tree.get_node(50)
        path_length = 0
        while current_node:
            path_length += 1
            current_node = tree.get_node(current_node.parent_id) if current_node.parent_id else None
        assert path_length == 50

    def test_purge_wide_tree_structure(self):
        """Test purging with very wide tree (many siblings)."""
        tree = TaxonomyTree()
        
        # Create tree with 1 root and 100 direct children
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT)
        tree.add_node(root)
        
        for i in range(2, 102):  # 100 children
            child = TaxonomyNode(tax_id=i, name=f"Child{i}", rank=TaxonomicRank.SPECIES, parent_id=1)
            tree.add_node(child)
        
        # Add genomes to every 10th child
        for i in range(10, 102, 10):  # children 10, 20, 30, ..., 100
            genome = GenomeInfo(
                genome_id=f"genome_{i}",
                tax_id=i,
                file_path=f"/genome_{i}.fasta",
                sequence_type="genome",
                source="TEST"
            )
            tree.add_genome(genome)
        
        result = tree.purge_nodes_without_genomes()
        
        # Should keep root + 10 children with genomes = 11 nodes
        assert result["nodes_removed"] == 90
        assert result["nodes_after"] == 11
        assert result["genomes_retained"] == 10
        assert result["lineages_preserved"] == 10
        
        # Verify correct nodes remain
        remaining_ids = set(tree._nodes.keys())
        expected_ids = {1}  # root
        expected_ids.update(range(10, 102, 10))  # every 10th child
        assert remaining_ids == expected_ids

    def test_purge_mixed_sequence_types_and_sources(self):
        """Test purging with diverse genome metadata."""
        tree = TaxonomyTree()
        
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT)
        tree.add_node(root)
        
        # Create nodes for different sequence types
        nodes_data = [
            (2, "GenomeSpecies", TaxonomicRank.SPECIES),
            (3, "rRNASpecies", TaxonomicRank.SPECIES),  
            (4, "PlasmidSpecies", TaxonomicRank.SPECIES),
            (5, "ChloroplastSpecies", TaxonomicRank.SPECIES),
            (6, "MixedSpecies", TaxonomicRank.SPECIES),
        ]
        
        for tax_id, name, rank in nodes_data:
            node = TaxonomyNode(tax_id=tax_id, name=name, rank=rank, parent_id=1)
            tree.add_node(node)
        
        # Create diverse genomes
        genomes_data = [
            ("genome1", 2, "/genomes/complete.fasta", "genome", "NCBI"),
            ("16s1", 3, "/rrna/16s.fasta", "16S", "SILVA"), 
            ("plasmid1", 4, "/plasmids/p1.fasta", "plasmid", "NCBI"),
            ("chloroplast1", 5, "/organelles/cp.fasta", "chloroplast", "GTDB"),
            ("mixed1", 6, "/mixed/genome.fasta", "genome", "NCBI"),
            ("mixed2", 6, "/mixed/16s.fasta", "16S", "SILVA"),  # Same node, different type
        ]
        
        for genome_id, tax_id, file_path, seq_type, source in genomes_data:
            genome = GenomeInfo(
                genome_id=genome_id,
                tax_id=tax_id,
                file_path=file_path,
                sequence_type=seq_type,
                source=source
            )
            tree.add_genome(genome)
        
        result = tree.purge_nodes_without_genomes()
        
        # Should keep root + all species (all have genomes)
        assert result["nodes_removed"] == 0
        assert result["nodes_after"] == 6
        assert result["genomes_retained"] == 6

    def test_purge_exact_safety_threshold(self):
        """Test purging at exact 95% removal threshold."""
        tree = TaxonomyTree()
        
        # Create tree with 100 nodes to make percentage calculation clear
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT)
        tree.add_node(root)
        
        for i in range(2, 101):  # 99 additional nodes
            node = TaxonomyNode(tax_id=i, name=f"Node{i}", rank=TaxonomicRank.SPECIES, parent_id=1)
            tree.add_node(node)
        
        # Add genome to one node only (would result in 98/100 = 98% removal > 95%)
        genome = GenomeInfo(
            genome_id="genome",
            tax_id=2,
            file_path="/genome.fasta",
            sequence_type="genome",
            source="TEST"
        )
        tree.add_genome(genome)
        
        # Without force - should trigger safety check
        result = tree.purge_nodes_without_genomes(force=False)
        assert "warning" in result
        assert "98.0%" in result["warning"]
        assert "operation blocked for safety" in result["warning"]
        
        # With force - should proceed
        result = tree.purge_nodes_without_genomes(force=True)
        assert "warning" not in result
        assert result["nodes_removed"] == 98  # Removes 98, keeps root + species with genome
        assert result["nodes_after"] == 2

    def test_purge_boundary_conditions(self):
        """Test various boundary conditions."""
        # Test with 94.9% removal (should pass)
        tree = TaxonomyTree()
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT)
        tree.add_node(root)
        
        # Add 1000 nodes, keep 51 -> 94.9% removal
        for i in range(2, 1001):
            node = TaxonomyNode(tax_id=i, name=f"Node{i}", rank=TaxonomicRank.SPECIES, parent_id=1)
            tree.add_node(node)
        
        # Add genomes to 50 nodes (plus root lineage = 51 total kept)
        for i in range(2, 52):
            genome = GenomeInfo(
                genome_id=f"genome_{i}",
                tax_id=i,
                file_path=f"/genome_{i}.fasta",
                sequence_type="genome",
                source="TEST"
            )
            tree.add_genome(genome)
        
        result = tree.purge_nodes_without_genomes(force=False)
        
        # Should proceed (94.9% < 95%)
        assert "warning" not in result
        assert result["nodes_removed"] == 949  # 1000 - 51
        assert result["nodes_after"] == 51

    def test_purge_unicode_and_special_paths(self):
        """Test handling of Unicode and special characters in file paths."""
        tree = TaxonomyTree()
        
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT)
        species1 = TaxonomyNode(tax_id=2, name="Species1", rank=TaxonomicRank.SPECIES, parent_id=1)
        species2 = TaxonomyNode(tax_id=3, name="Species2", rank=TaxonomicRank.SPECIES, parent_id=1)
        species3 = TaxonomyNode(tax_id=4, name="Species3", rank=TaxonomicRank.SPECIES, parent_id=1)
        
        for node in [root, species1, species2, species3]:
            tree.add_node(node)
        
        # Unicode and special character paths
        genomes = [
            GenomeInfo(genome_id="unicode", tax_id=2, file_path="/genomes/species_ñáme.fasta", sequence_type="genome", source="TEST"),
            GenomeInfo(genome_id="spaces", tax_id=3, file_path="/genomes/species with spaces.fasta", sequence_type="genome", source="TEST"),
            GenomeInfo(genome_id="special", tax_id=4, file_path="/genomes/species-name_v2.0[final].fasta", sequence_type="genome", source="TEST"),
        ]
        
        for genome in genomes:
            tree.add_genome(genome)
        
        result = tree.purge_nodes_without_genomes()
        
        # All should be kept (valid file paths regardless of special characters)
        assert result["nodes_removed"] == 0
        assert result["nodes_after"] == 4
        assert result["genomes_retained"] == 3

    def test_purge_tree_integrity_after_complex_removal(self):
        """Test that tree maintains proper parent-child relationships after complex purging."""
        tree = TaxonomyTree()
        
        # Create complex tree with mixed genome distribution
        #     root(1)
        #    /   |   \
        #   A(2) B(3) C(4) 
        #   |    |    |
        #  A1(5) B1(6) C1(7)
        #  |     |     |
        # A2(8) B2(9) C2(10)  <- only B2 has genome
        
        nodes = [
            (1, "root", TaxonomicRank.ROOT, None),
            (2, "A", TaxonomicRank.PHYLUM, 1),
            (3, "B", TaxonomicRank.PHYLUM, 1),
            (4, "C", TaxonomicRank.PHYLUM, 1),
            (5, "A1", TaxonomicRank.GENUS, 2),
            (6, "B1", TaxonomicRank.GENUS, 3),
            (7, "C1", TaxonomicRank.GENUS, 4),
            (8, "A2", TaxonomicRank.SPECIES, 5),
            (9, "B2", TaxonomicRank.SPECIES, 6),
            (10, "C2", TaxonomicRank.SPECIES, 7),
        ]
        
        for tax_id, name, rank, parent_id in nodes:
            node = TaxonomyNode(tax_id=tax_id, name=name, rank=rank, parent_id=parent_id)
            tree.add_node(node)
        
        # Only B2 has genome
        genome = GenomeInfo(
            genome_id="b2_genome",
            tax_id=9,
            file_path="/b2.fasta",
            sequence_type="genome",
            source="TEST"
        )
        tree.add_genome(genome)
        
        result = tree.purge_nodes_without_genomes()
        
        # Should keep: root(1) -> B(3) -> B1(6) -> B2(9)
        # Should remove: A(2), A1(5), A2(8), C(4), C1(7), C2(10)
        expected_kept = {1, 3, 6, 9}
        remaining_ids = set(tree._nodes.keys())
        assert remaining_ids == expected_kept
        assert result["nodes_removed"] == 6
        assert result["nodes_after"] == 4
        
        # Verify parent-child relationships
        assert tree.get_node(1).parent_id is None  # root
        assert tree.get_node(3).parent_id == 1     # B -> root
        assert tree.get_node(6).parent_id == 3     # B1 -> B
        assert tree.get_node(9).parent_id == 6     # B2 -> B1
        
        # Verify children relationships
        assert tree.get_children(1) == {3}    # root has only B
        assert tree.get_children(3) == {6}    # B has only B1
        assert tree.get_children(6) == {9}    # B1 has only B2
        assert tree.get_children(9) == set()  # B2 has no children

    def test_purge_with_orphaned_genomes_cleanup(self):
        """Test that genomes pointing to removed nodes are properly cleaned up."""
        tree = TaxonomyTree()
        
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT)
        keep_species = TaxonomyNode(tax_id=2, name="KeepMe", rank=TaxonomicRank.SPECIES, parent_id=1)
        remove_species = TaxonomyNode(tax_id=3, name="RemoveMe", rank=TaxonomicRank.SPECIES, parent_id=1)
        
        tree.add_node(root)
        tree.add_node(keep_species)
        tree.add_node(remove_species)
        
        # Create genomes for both species
        keep_genome = GenomeInfo(
            genome_id="keep_genome",
            tax_id=2,
            file_path="/keep.fasta",
            sequence_type="genome",
            source="TEST"
        )
        
        remove_genome1 = GenomeInfo(
            genome_id="remove_genome1",
            tax_id=3,  # Will be removed
            sequence_type="genome",
            source="TEST"  # No file path
        )
        
        remove_genome2 = GenomeInfo(
            genome_id="remove_genome2", 
            tax_id=3,  # Will be removed
            assembly_accession="GCF_123",
            sequence_type="16S",
            source="TEST"
        )
        
        tree.add_genome(keep_genome)
        tree.add_genome(remove_genome1) 
        tree.add_genome(remove_genome2)
        
        assert len(tree._genomes) == 3
        
        result = tree.purge_nodes_without_genomes(require_fasta_files=True)
        
        # Should remove species without FASTA files
        assert result["nodes_removed"] == 1  # remove_species removed
        assert result["genomes_retained"] == 1  # only keep_genome retained
        
        # Verify genome cleanup
        assert len(tree._genomes) == 1
        assert "keep_genome" in tree._genomes
        assert "remove_genome1" not in tree._genomes
        assert "remove_genome2" not in tree._genomes
        
        # Remaining genome should still point to valid node
        remaining_genome = list(tree._genomes.values())[0]
        assert remaining_genome.tax_id == 2
        assert tree.get_node(2) is not None

    def test_purge_performance_with_large_dataset(self):
        """Test purge performance with reasonably large dataset."""
        tree = TaxonomyTree()
        
        # Create a simpler tree structure that we can control better
        # Root with 100 direct children, only add genome to one child
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT)
        tree.add_node(root)
        
        # Create 999 children of root (total 1000 nodes)
        for i in range(2, 1001):
            node = TaxonomyNode(
                tax_id=i,
                name=f"Species_{i}",
                rank=TaxonomicRank.SPECIES,
                parent_id=1
            )
            tree.add_node(node)
        
        # Add genome to only one species (node 100)
        genome = GenomeInfo(
            genome_id="genome_100",
            tax_id=100,
            file_path="/genomes/100.fasta", 
            sequence_type="genome",
            source="TEST"
        )
        tree.add_genome(genome)
        genome_count = 1
        
        initial_nodes = len(tree._nodes)  # Should be 1000
        
        # Measure performance (should complete quickly)
        import time
        start_time = time.time()
        result = tree.purge_nodes_without_genomes(force=True)  # Use force to bypass 95% safety check
        end_time = time.time()
        
        # Should complete in reasonable time (less than 5 seconds for this size)
        assert end_time - start_time < 5.0
        
        # Verify results make sense - should keep root + one species = 2 nodes
        assert result["nodes_before"] == initial_nodes
        assert result["genomes_retained"] == genome_count
        assert result["nodes_after"] == 2  # root + species with genome
        assert result["nodes_removed"] == 998  # all other species removed
        assert len(tree._nodes) == result["nodes_after"]

    def test_purge_with_multiple_genomes_per_node(self):
        """Test purging when nodes have multiple genomes."""
        tree = TaxonomyTree()
        
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT)
        species1 = TaxonomyNode(tax_id=2, name="MultiGenome", rank=TaxonomicRank.SPECIES, parent_id=1)
        species2 = TaxonomyNode(tax_id=3, name="SingleGenome", rank=TaxonomicRank.SPECIES, parent_id=1)
        species3 = TaxonomyNode(tax_id=4, name="NoGenome", rank=TaxonomicRank.SPECIES, parent_id=1)
        
        for node in [root, species1, species2, species3]:
            tree.add_node(node)
        
        # Add multiple genomes to species1
        genomes_species1 = [
            GenomeInfo(genome_id="multi1", tax_id=2, file_path="/multi1.fasta", sequence_type="genome", source="NCBI"),
            GenomeInfo(genome_id="multi2", tax_id=2, file_path="/multi2.fasta", sequence_type="plasmid", source="NCBI"),
            GenomeInfo(genome_id="multi3", tax_id=2, assembly_accession="GCF_001", sequence_type="16S", source="SILVA"),
        ]
        
        # Add single genome to species2
        genome_species2 = GenomeInfo(
            genome_id="single1", 
            tax_id=3,
            file_path="/single1.fasta", 
            sequence_type="genome",
            source="GTDB"
        )
        
        for genome in genomes_species1:
            tree.add_genome(genome)
        tree.add_genome(genome_species2)
        
        result = tree.purge_nodes_without_genomes()
        
        # Should keep root, species1, species2; remove species3
        assert result["nodes_removed"] == 1
        assert result["nodes_after"] == 3
        assert result["genomes_retained"] == 3  # Only genomes with files count
        
        # Verify all genomes for kept nodes remain
        remaining_genome_ids = set(tree._genomes.keys())
        assert remaining_genome_ids == {"multi1", "multi2", "multi3", "single1"}

    def test_purge_root_node_handling(self):
        """Test various scenarios with root node handling.""" 
        # Test 1: Root node gets removed during purging (shouldn't happen)
        tree = TaxonomyTree()
        
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT)
        species = TaxonomyNode(tax_id=2, name="species", rank=TaxonomicRank.SPECIES, parent_id=1)
        tree.add_node(root)
        tree.add_node(species)
        
        # Add genome to species
        genome = GenomeInfo(
            genome_id="species_genome",
            tax_id=2,
            file_path="/species.fasta",
            sequence_type="genome",
            source="TEST"
        )
        tree.add_genome(genome)
        
        result = tree.purge_nodes_without_genomes()
        
        # Root should always be preserved (part of essential lineage)
        assert 1 in tree._nodes  # Root still exists
        assert tree._root_id == 1  # Root ID unchanged
        assert tree.get_node(1).parent_id is None  # Root has no parent
        
        # Test 2: Multiple potential roots (disconnected tree)
        tree2 = TaxonomyTree()
        
        # This shouldn't normally happen, but test robustness
        root1 = TaxonomyNode(tax_id=1, name="root1", rank=TaxonomicRank.ROOT)
        root2 = TaxonomyNode(tax_id=2, name="root2", rank=TaxonomicRank.ROOT) 
        child1 = TaxonomyNode(tax_id=3, name="child1", rank=TaxonomicRank.SPECIES, parent_id=1)
        
        tree2.add_node(root1)
        tree2.add_node(child1) 
        
        # Manually add disconnected root (bypass normal validation)
        tree2._nodes[2] = root2
        
        # Add genome to child1
        genome2 = GenomeInfo(
            genome_id="child_genome",
            tax_id=3,
            file_path="/child.fasta", 
            sequence_type="genome",
            source="TEST"
        )
        tree2.add_genome(genome2)
        
        result2 = tree2.purge_nodes_without_genomes()
        
        # Should keep root1 and child1, remove disconnected root2
        assert 1 in tree2._nodes
        assert 3 in tree2._nodes 
        assert 2 not in tree2._nodes
        assert result2["nodes_removed"] == 1