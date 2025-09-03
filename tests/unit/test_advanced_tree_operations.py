"""Comprehensive unit tests for advanced tree operations."""

import pytest
from typing import Dict, Any

from flextaxd.core.models import TaxonomyTree, TaxonomyNode, TaxonomicRank, GenomeInfo
from flextaxd.core.exceptions import ValidationError


class TestLCAOperations:
    """Test Lowest Common Ancestor operations."""

    @pytest.fixture
    def complex_tree(self):
        r"""Create a complex tree for LCA testing.
        
        Structure:
              1 (root)
             / \
            2   3
           / \   \
          4   5   6
         /   / \   
        7   8   9   
        """
        tree = TaxonomyTree()

        # Add nodes
        nodes = [
            (1, "root", TaxonomicRank.ROOT, None),
            (2, "Bacteria", TaxonomicRank.SUPERKINGDOM, 1),
            (3, "Archaea", TaxonomicRank.SUPERKINGDOM, 1),
            (4, "Proteobacteria", TaxonomicRank.PHYLUM, 2),
            (5, "Firmicutes", TaxonomicRank.PHYLUM, 2),
            (6, "Euryarchaeota", TaxonomicRank.PHYLUM, 3),
            (7, "Gammaproteobacteria", TaxonomicRank.CLASS, 4),
            (8, "Bacilli", TaxonomicRank.CLASS, 5),
            (9, "Clostridia", TaxonomicRank.CLASS, 5),
        ]

        for tax_id, name, rank, parent_id in nodes:
            node = TaxonomyNode(
                tax_id=tax_id, name=name, rank=rank, parent_id=parent_id
            )
            tree.add_node(node)

        return tree

    def test_lca_same_node(self, complex_tree):
        """Test LCA of a node with itself."""
        lca = complex_tree.lowest_common_ancestor(5)
        assert lca is not None
        assert lca.tax_id == 5

    def test_lca_parent_child(self, complex_tree):
        """Test LCA of parent and child."""
        lca = complex_tree.lowest_common_ancestor(2, 4)
        assert lca is not None
        assert lca.tax_id == 2  # Parent should be LCA

    def test_lca_siblings(self, complex_tree):
        """Test LCA of sibling nodes."""
        lca = complex_tree.lowest_common_ancestor(4, 5)
        assert lca is not None
        assert lca.tax_id == 2  # Common parent

    def test_lca_cousins(self, complex_tree):
        """Test LCA of cousin nodes."""
        lca = complex_tree.lowest_common_ancestor(7, 8)
        assert lca is not None
        assert lca.tax_id == 2  # Common grandparent

    def test_lca_different_subtrees(self, complex_tree):
        """Test LCA of nodes in completely different subtrees."""
        lca = complex_tree.lowest_common_ancestor(7, 6)
        assert lca is not None
        assert lca.tax_id == 1  # Root should be LCA

    def test_lca_multiple_nodes(self, complex_tree):
        """Test LCA of multiple nodes."""
        lca = complex_tree.lowest_common_ancestor(7, 8, 9)
        assert lca is not None
        assert lca.tax_id == 2  # Common ancestor of all three

    def test_lca_nonexistent_node(self, complex_tree):
        """Test LCA with nonexistent node."""
        lca = complex_tree.lowest_common_ancestor(7, 999)
        assert lca is None

    def test_lca_empty_args(self, complex_tree):
        """Test LCA with no arguments."""
        lca = complex_tree.lowest_common_ancestor()
        assert lca is None


class TestTaxonomicDistance:
    """Test taxonomic distance calculations."""

    @pytest.fixture
    def linear_tree(self):
        """Create a linear tree for distance testing."""
        tree = TaxonomyTree()

        # Linear chain: 1->2->3->4->5
        nodes = [
            (1, "root", TaxonomicRank.ROOT, None),
            (2, "superkingdom", TaxonomicRank.SUPERKINGDOM, 1),
            (3, "phylum", TaxonomicRank.PHYLUM, 2),
            (4, "class", TaxonomicRank.CLASS, 3),
            (5, "order", TaxonomicRank.ORDER, 4),
        ]

        for tax_id, name, rank, parent_id in nodes:
            node = TaxonomyNode(
                tax_id=tax_id, name=name, rank=rank, parent_id=parent_id
            )
            tree.add_node(node)

        return tree

    def test_distance_same_node(self, linear_tree):
        """Test distance of a node to itself."""
        distance = linear_tree.taxonomic_distance(3, 3)
        assert distance == 0

    def test_distance_parent_child(self, linear_tree):
        """Test distance between parent and child."""
        distance = linear_tree.taxonomic_distance(2, 3)
        assert distance == 1

    def test_distance_grandparent_grandchild(self, linear_tree):
        """Test distance between grandparent and grandchild."""
        distance = linear_tree.taxonomic_distance(1, 3)
        assert distance == 2

    def test_distance_distant_nodes(self, linear_tree):
        """Test distance between distant nodes."""
        distance = linear_tree.taxonomic_distance(1, 5)
        assert distance == 4

    def test_distance_nonexistent_node(self, linear_tree):
        """Test distance with nonexistent node."""
        distance = linear_tree.taxonomic_distance(1, 999)
        assert distance is None


class TestSubtreeExtraction:
    """Test subtree extraction operations."""

    @pytest.fixture
    def source_tree(self):
        """Create a source tree for subtree extraction testing."""
        tree = TaxonomyTree()

        # Create tree with genomes
        nodes = [
            (1, "root", TaxonomicRank.ROOT, None),
            (2, "Bacteria", TaxonomicRank.SUPERKINGDOM, 1),
            (3, "Proteobacteria", TaxonomicRank.PHYLUM, 2),
            (4, "E.coli", TaxonomicRank.SPECIES, 3),
            (5, "Archaea", TaxonomicRank.SUPERKINGDOM, 1),
        ]

        for tax_id, name, rank, parent_id in nodes:
            node = TaxonomyNode(
                tax_id=tax_id, name=name, rank=rank, parent_id=parent_id
            )
            tree.add_node(node)

        # Add genomes
        genome = GenomeInfo(
            genome_id="NC_000913",
            tax_id=4,
            assembly_accession="GCF_000005825.2",
            file_path="/test/NC_000913.fna",
            source="NCBI",
        )
        tree.add_genome(genome)

        return tree

    def test_extract_subtree_preserve_ids(self, source_tree):
        """Test extracting subtree while preserving tax_ids."""
        subtree = source_tree.extract_subtree(2, preserve_tax_ids=True)

        # Should contain nodes 2, 3, 4 (but not 1, 5)
        assert subtree.node_count == 3
        assert 2 in subtree._nodes  # Bacteria
        assert 3 in subtree._nodes  # Proteobacteria
        assert 4 in subtree._nodes  # E.coli
        assert 1 not in subtree._nodes  # root
        assert 5 not in subtree._nodes  # Archaea

        # Check structure is preserved
        bacteria_node = subtree.get_node(2)
        assert bacteria_node.parent_id is None  # New root

        proteo_node = subtree.get_node(3)
        assert proteo_node.parent_id == 2

        ecoli_node = subtree.get_node(4)
        assert ecoli_node.parent_id == 3

    def test_extract_subtree_reassign_ids(self, source_tree):
        """Test extracting subtree with reassigned sequential IDs."""
        subtree = source_tree.extract_subtree(2, preserve_tax_ids=False)

        assert subtree.node_count == 3
        # Should have IDs 1, 2, 3 (sequential)
        assert 1 in subtree._nodes
        assert 2 in subtree._nodes
        assert 3 in subtree._nodes

        # Root of subtree should have parent_id None
        root_node = [n for n in subtree if n.parent_id is None][0]
        assert root_node.name == "Bacteria"

    def test_extract_subtree_with_genomes(self, source_tree):
        """Test that genomes are copied to subtree."""
        subtree = source_tree.extract_subtree(2, preserve_tax_ids=True)

        assert subtree.genome_count == 1
        genomes = subtree.get_genomes_for_node(4)
        assert len(genomes) == 1
        assert genomes[0].genome_id == "NC_000913"

    def test_extract_nonexistent_node(self, source_tree):
        """Test extracting subtree from nonexistent node."""
        with pytest.raises(ValueError):
            source_tree.extract_subtree(999)


class TestTreeMerging:
    """Test tree merging and grafting operations."""

    @pytest.fixture
    def base_tree(self):
        """Create base tree for merging tests."""
        tree = TaxonomyTree()

        nodes = [
            (1, "root", TaxonomicRank.ROOT, None),
            (2, "Bacteria", TaxonomicRank.SUPERKINGDOM, 1),
            (3, "Archaea", TaxonomicRank.SUPERKINGDOM, 1),
        ]

        for tax_id, name, rank, parent_id in nodes:
            node = TaxonomyNode(
                tax_id=tax_id, name=name, rank=rank, parent_id=parent_id
            )
            tree.add_node(node)

        return tree

    @pytest.fixture
    def subtree_to_graft(self):
        """Create subtree for grafting tests."""
        tree = TaxonomyTree()

        nodes = [
            (10, "Proteobacteria", TaxonomicRank.PHYLUM, None),
            (11, "Gammaproteobacteria", TaxonomicRank.CLASS, 10),
        ]

        for tax_id, name, rank, parent_id in nodes:
            node = TaxonomyNode(
                tax_id=tax_id, name=name, rank=rank, parent_id=parent_id
            )
            tree.add_node(node)

        return tree

    def test_graft_subtree(self, base_tree, subtree_to_graft):
        """Test grafting subtree onto base tree."""
        original_count = base_tree.node_count

        # Graft subtree onto Bacteria node (tax_id=2)
        id_mapping = base_tree.graft_subtree(subtree_to_graft, attachment_point=2)

        # Should have more nodes now
        assert base_tree.node_count == original_count + 2

        # Check ID mapping
        assert len(id_mapping) == 2
        assert 10 in id_mapping  # Old Proteobacteria ID
        assert 11 in id_mapping  # Old Gammaproteobacteria ID

        # Check that grafted nodes have correct parents
        proteo_new_id = id_mapping[10]
        gamma_new_id = id_mapping[11]

        proteo_node = base_tree.get_node(proteo_new_id)
        assert proteo_node.parent_id == 2  # Attached to Bacteria

        gamma_node = base_tree.get_node(gamma_new_id)
        assert gamma_node.parent_id == proteo_new_id  # Child of Proteobacteria

    def test_graft_at_nonexistent_point(self, base_tree, subtree_to_graft):
        """Test grafting at nonexistent attachment point."""
        with pytest.raises(ValueError):
            base_tree.graft_subtree(subtree_to_graft, attachment_point=999)

    def test_merge_trees_graft_at_root(self, base_tree, subtree_to_graft):
        """Test merging trees using graft_at_root strategy."""
        id_mapping = base_tree.merge_trees(
            subtree_to_graft, merge_strategy="graft_at_root"
        )

        # Should graft subtree at root
        assert len(id_mapping) == 2
        proteo_new_id = id_mapping[10]

        proteo_node = base_tree.get_node(proteo_new_id)
        assert proteo_node.parent_id == 1  # Attached to root

    def test_merge_trees_common_ancestors(self, base_tree):
        """Test merging trees using common ancestor strategy."""
        # Create another tree with some common nodes
        other_tree = TaxonomyTree()

        nodes = [
            (100, "root", TaxonomicRank.ROOT, None),  # Same name/rank as base
            (101, "Bacteria", TaxonomicRank.SUPERKINGDOM, 100),  # Same name/rank
            (102, "Firmicutes", TaxonomicRank.PHYLUM, 101),  # New node
        ]

        for tax_id, name, rank, parent_id in nodes:
            node = TaxonomyNode(
                tax_id=tax_id, name=name, rank=rank, parent_id=parent_id
            )
            other_tree.add_node(node)

        id_mapping = base_tree.merge_trees(
            other_tree, merge_strategy="merge_common_ancestors"
        )

        # Common nodes should be mapped to existing IDs
        assert id_mapping[100] == 1  # root mapped to existing root
        assert id_mapping[101] == 2  # Bacteria mapped to existing Bacteria

        # New node should get new ID
        firmicutes_new_id = id_mapping[102]
        firmicutes_node = base_tree.get_node(firmicutes_new_id)
        assert firmicutes_node.name == "Firmicutes"
        assert firmicutes_node.parent_id == 2  # Child of existing Bacteria


class TestTreeComparison:
    """Test tree comparison operations."""

    @pytest.fixture
    def tree1(self):
        """Create first tree for comparison."""
        tree = TaxonomyTree()

        nodes = [
            (1, "root", TaxonomicRank.ROOT, None),
            (2, "Bacteria", TaxonomicRank.SUPERKINGDOM, 1),
            (3, "Proteobacteria", TaxonomicRank.PHYLUM, 2),
        ]

        for tax_id, name, rank, parent_id in nodes:
            node = TaxonomyNode(
                tax_id=tax_id, name=name, rank=rank, parent_id=parent_id
            )
            tree.add_node(node)

        return tree

    @pytest.fixture
    def tree2(self):
        """Create second tree for comparison."""
        tree = TaxonomyTree()

        nodes = [
            (1, "root", TaxonomicRank.ROOT, None),
            (2, "Bacteria", TaxonomicRank.SUPERKINGDOM, 1),
            (4, "Archaea", TaxonomicRank.SUPERKINGDOM, 1),  # Different node
        ]

        for tax_id, name, rank, parent_id in nodes:
            node = TaxonomyNode(
                tax_id=tax_id, name=name, rank=rank, parent_id=parent_id
            )
            tree.add_node(node)

        return tree

    def test_compare_identical_trees(self, tree1):
        """Test comparison of identical trees."""
        comparison = tree1.compare_trees(tree1)

        assert len(comparison["nodes_only_in_self"]) == 0
        assert len(comparison["nodes_only_in_other"]) == 0
        assert len(comparison["nodes_in_both"]) == 3
        assert len(comparison["structural_differences"]) == 0
        assert len(comparison["rank_differences"]) == 0
        assert len(comparison["name_differences"]) == 0

    def test_compare_different_trees(self, tree1, tree2):
        """Test comparison of different trees."""
        comparison = tree1.compare_trees(tree2)

        # Node 3 only in tree1, node 4 only in tree2
        assert 3 in comparison["nodes_only_in_self"]
        assert 4 in comparison["nodes_only_in_other"]

        # Nodes 1 and 2 in both
        assert 1 in comparison["nodes_in_both"]
        assert 2 in comparison["nodes_in_both"]

    def test_compare_structural_differences(self):
        """Test detection of structural differences."""
        tree1 = TaxonomyTree()
        tree2 = TaxonomyTree()

        # Same nodes but different structure
        for tree in [tree1, tree2]:
            root = TaxonomyNode(
                tax_id=1, name="root", rank=TaxonomicRank.ROOT, parent_id=None
            )
            tree.add_node(root)

            bacteria = TaxonomyNode(
                tax_id=2, name="Bacteria", rank=TaxonomicRank.SUPERKINGDOM, parent_id=1
            )
            tree.add_node(bacteria)

            proteo = TaxonomyNode(
                tax_id=3,
                name="Proteobacteria",
                rank=TaxonomicRank.PHYLUM,
                parent_id=2 if tree is tree1 else 1,
            )  # Different parent!
            tree.add_node(proteo)

        comparison = tree1.compare_trees(tree2)

        assert len(comparison["structural_differences"]) == 1
        diff = comparison["structural_differences"][0]
        assert diff["tax_id"] == 3
        assert diff["self_parent"] == 2
        assert diff["other_parent"] == 1


class TestTreeStatistics:
    """Test tree statistics calculations."""

    @pytest.fixture
    def balanced_tree(self):
        """Create balanced tree for statistics testing."""
        tree = TaxonomyTree()

        # Create balanced binary tree
        nodes = [
            (1, "root", TaxonomicRank.ROOT, None),
            (2, "left", TaxonomicRank.SUPERKINGDOM, 1),
            (3, "right", TaxonomicRank.SUPERKINGDOM, 1),
            (4, "left-left", TaxonomicRank.PHYLUM, 2),
            (5, "left-right", TaxonomicRank.PHYLUM, 2),
            (6, "right-left", TaxonomicRank.PHYLUM, 3),
            (7, "right-right", TaxonomicRank.PHYLUM, 3),
        ]

        for tax_id, name, rank, parent_id in nodes:
            node = TaxonomyNode(
                tax_id=tax_id, name=name, rank=rank, parent_id=parent_id
            )
            tree.add_node(node)

        return tree

    def test_basic_statistics(self, balanced_tree):
        """Test basic tree statistics."""
        stats = balanced_tree.get_tree_statistics()

        assert stats["node_count"] == 7
        assert stats["max_depth"] == 2  # root -> superkingdom -> phylum
        assert stats["leaf_node_count"] == 4  # Nodes 4, 5, 6, 7
        assert stats["internal_node_count"] == 3  # Nodes 1, 2, 3

    def test_rank_distribution(self, balanced_tree):
        """Test rank distribution calculation."""
        stats = balanced_tree.get_tree_statistics()

        expected_ranks = {"root": 1, "superkingdom": 2, "phylum": 4}

        assert stats["rank_distribution"] == expected_ranks

    def test_branching_factor_stats(self, balanced_tree):
        """Test branching factor statistics."""
        stats = balanced_tree.get_tree_statistics()

        branching_stats = stats["branching_factor_stats"]

        assert (
            branching_stats["max"] == 2
        )  # Root and superkingdom nodes have 2 children
        assert branching_stats["min"] == 0  # Leaf nodes have 0 children
        assert (
            branching_stats["average"] == 6 / 7
        )  # Total children (2+2+2+0+0+0+0) / total nodes

    def test_empty_tree_statistics(self):
        """Test statistics for empty tree."""
        tree = TaxonomyTree()
        stats = tree.get_tree_statistics()

        assert stats["node_count"] == 0
        assert stats["genome_count"] == 0
        assert stats["max_depth"] == 0
        assert stats["leaf_node_count"] == 0
        assert stats["internal_node_count"] == 0


class TestAdvancedTreeIntegration:
    """Integration tests for advanced tree operations."""

    def test_extract_and_graft_workflow(self):
        """Test complete workflow: extract subtree, modify it, graft back."""
        # Create main tree
        main_tree = TaxonomyTree()

        nodes = [
            (1, "root", TaxonomicRank.ROOT, None),
            (2, "Bacteria", TaxonomicRank.SUPERKINGDOM, 1),
            (3, "Proteobacteria", TaxonomicRank.PHYLUM, 2),
            (4, "Archaea", TaxonomicRank.SUPERKINGDOM, 1),
        ]

        for tax_id, name, rank, parent_id in nodes:
            node = TaxonomyNode(
                tax_id=tax_id, name=name, rank=rank, parent_id=parent_id
            )
            main_tree.add_node(node)

        # Extract bacteria subtree
        bacteria_subtree = main_tree.extract_subtree(2, preserve_tax_ids=False)

        # Add new node to extracted subtree
        new_node = TaxonomyNode(
            tax_id=999, name="E.coli", rank=TaxonomicRank.SPECIES, parent_id=2
        )
        bacteria_subtree.add_node(new_node)

        # Graft modified subtree back onto Archaea
        id_mapping = main_tree.graft_subtree(bacteria_subtree, attachment_point=4)

        # Verify the workflow
        assert len(id_mapping) == 3  # 3 nodes in grafted subtree

        # Check that E.coli is now in the main tree under Archaea branch
        ecoli_new_id = id_mapping[999]
        ecoli_node = main_tree.get_node(ecoli_new_id)
        assert ecoli_node.name == "E.coli"

        # Verify hierarchy: root -> Archaea -> Bacteria -> Proteobacteria -> E.coli
        path = main_tree.get_path_to_root(ecoli_new_id)
        path_names = [node.name for node in path]
        assert "E.coli" in path_names
        assert "Archaea" in path_names

    def test_tree_comparison_and_statistics(self):
        """Test combining tree comparison with statistics."""
        tree1 = TaxonomyTree()
        tree2 = TaxonomyTree()

        # Create similar but different trees
        for i, tree in enumerate([tree1, tree2], 1):
            root = TaxonomyNode(
                tax_id=1, name="root", rank=TaxonomicRank.ROOT, parent_id=None
            )
            tree.add_node(root)

            bacteria = TaxonomyNode(
                tax_id=2, name="Bacteria", rank=TaxonomicRank.SUPERKINGDOM, parent_id=1
            )
            tree.add_node(bacteria)

            # Add different phyla to each tree
            phylum_id = 10 + i
            phylum = TaxonomyNode(
                tax_id=phylum_id,
                name=f"Phylum{i}",
                rank=TaxonomicRank.PHYLUM,
                parent_id=2,
            )
            tree.add_node(phylum)

        # Compare trees
        comparison = tree1.compare_trees(tree2)
        assert len(comparison["nodes_only_in_self"]) == 1  # Phylum1
        assert len(comparison["nodes_only_in_other"]) == 1  # Phylum2

        # Get statistics for each tree
        stats1 = tree1.get_tree_statistics()
        stats2 = tree2.get_tree_statistics()

        # Both should have same structure statistics
        assert stats1["node_count"] == stats2["node_count"]
        assert stats1["max_depth"] == stats2["max_depth"]
        assert stats1["rank_distribution"] == stats2["rank_distribution"]
