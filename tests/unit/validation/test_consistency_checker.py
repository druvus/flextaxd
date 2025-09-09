"""Test suite for consistency checker module."""

import pytest
from unittest.mock import Mock, MagicMock
from dataclasses import dataclass
from typing import List, Dict, Any

from flextaxd.validation.consistency_checker import ConsistencyChecker, ConsistencyIssue
from flextaxd.core.models import TaxonomyTree, TaxonomyNode, GenomeInfo
from flextaxd.database.repository import TaxonomyRepository
from flextaxd.core.exceptions import ValidationError


class TestConsistencyIssue:
    """Test ConsistencyIssue dataclass."""
    
    def test_basic_initialization(self):
        """Test basic issue creation."""
        issue = ConsistencyIssue(
            category="test",
            severity="error", 
            description="Test issue"
        )
        
        assert issue.category == "test"
        assert issue.severity == "error"
        assert issue.description == "Test issue"
        assert issue.affected_items == []
    
    def test_initialization_with_items(self):
        """Test issue creation with affected items."""
        issue = ConsistencyIssue(
            category="taxonomy",
            severity="warning",
            description="Duplicate names",
            affected_items=["123", "456"]
        )
        
        assert issue.affected_items == ["123", "456"]


class TestConsistencyChecker:
    """Test ConsistencyChecker functionality."""
    
    @pytest.fixture
    def mock_repository(self):
        """Create a mock repository."""
        return Mock(spec=TaxonomyRepository)
    
    @pytest.fixture
    def checker(self, mock_repository):
        """Create consistency checker instance."""
        return ConsistencyChecker(mock_repository)
    
    @pytest.fixture
    def simple_tree(self):
        """Create a simple valid taxonomy tree."""
        tree = TaxonomyTree()
        
        # Root node
        root = TaxonomyNode(tax_id=1, name="root", rank="root", parent_id=None)
        tree.add_node(root)
        
        # Domain  
        bacteria = TaxonomyNode(tax_id=2, name="Bacteria", rank="domain", parent_id=1)
        tree.add_node(bacteria)
        
        # Phylum
        proteobacteria = TaxonomyNode(tax_id=3, name="Proteobacteria", rank="phylum", parent_id=2)
        tree.add_node(proteobacteria)
        
        # Class
        gamma = TaxonomyNode(tax_id=4, name="Gammaproteobacteria", rank="class", parent_id=3)
        tree.add_node(gamma)
        
        return tree
    
    @pytest.fixture  
    def cyclic_tree(self):
        """Create a tree with circular reference using mock."""
        tree = Mock()
        
        # Create nodes for circular dependency
        node1 = TaxonomyNode(tax_id=1, name="Node1", rank="genus", parent_id=2)
        node2 = TaxonomyNode(tax_id=2, name="Node2", rank="species", parent_id=1)
        
        # Mock tree methods to simulate circular dependency
        nodes = [node1, node2]
        tree.__iter__ = Mock(side_effect=lambda: iter(nodes))
        tree.get_node = Mock(side_effect=lambda tid: node1 if tid == 1 else node2 if tid == 2 else None)
        
        return tree
    
    @pytest.fixture
    def orphaned_tree(self):
        """Create a tree with orphaned nodes using mock."""
        tree = Mock()
        
        # Root node
        root = TaxonomyNode(tax_id=1, name="root", rank="root", parent_id=None)
        # Orphaned node (parent doesn't exist)
        orphan = TaxonomyNode(tax_id=2, name="Orphan", rank="species", parent_id=999)
        
        # Mock tree methods
        nodes = [root, orphan]
        tree.__iter__ = Mock(side_effect=lambda: iter(nodes))
        tree.get_node = Mock(side_effect=lambda tid: root if tid == 1 else orphan if tid == 2 else None)
        
        return tree
    
    @pytest.fixture
    def sample_genomes(self):
        """Create sample genome data."""
        return [
            GenomeInfo(
                genome_id="genome1",
                tax_id=1,
                file_path="/path/to/genome1.fna",
                sequence_length=1000000,
                sequence_type="genome",
                source="NCBI"
            ),
            GenomeInfo(
                genome_id="genome2", 
                tax_id=2,
                file_path="/path/to/genome2.fna",
                sequence_length=2000000,
                sequence_type="genome", 
                source="GTDB"
            ),
            GenomeInfo(
                genome_id="genome3",
                tax_id=999,  # Non-existent taxonomy node
                file_path="/path/to/genome3.fna",
                sequence_length=3000000,
                sequence_type="genome",
                source="NCBI"
            )
        ]
    
    def test_initialization(self, mock_repository):
        """Test checker initialization."""
        checker = ConsistencyChecker(mock_repository)
        assert checker.repository == mock_repository
        assert hasattr(checker, 'logger')
    
    def test_check_full_consistency_valid_tree(self, checker, simple_tree, sample_genomes):
        """Test full consistency check on valid data."""
        # Setup mocks
        checker.repository.load_tree = Mock(return_value=simple_tree)
        checker.repository.get_all_genomes = Mock(return_value=sample_genomes[:2])  # Only valid genomes
        
        # Run consistency check
        result = checker.check_full_consistency()
        
        # Verify structure
        assert isinstance(result, dict)
        assert "total_nodes" in result
        assert "total_genomes" in result
        assert "issues_by_category" in result
        assert "issues_by_severity" in result
        assert "summary" in result
        assert "consistency_score" in result
        
        # Should have minimal issues for valid data
        assert result["total_nodes"] == 4
        assert result["total_genomes"] == 2
    
    def test_check_taxonomy_integrity_cycles(self, checker, cyclic_tree):
        """Test detection of circular references."""
        issues = checker._check_taxonomy_integrity(cyclic_tree)
        
        # Should detect circular reference
        cycle_issues = [i for i in issues if "circular reference" in i.description.lower()]
        assert len(cycle_issues) > 0
        assert all(issue.severity == "error" for issue in cycle_issues)
        assert all(issue.category == "taxonomy" for issue in cycle_issues)
    
    def test_check_taxonomy_integrity_orphans(self, checker, orphaned_tree):
        """Test detection of orphaned nodes."""
        issues = checker._check_taxonomy_integrity(orphaned_tree)
        
        # Should detect orphaned node
        orphan_issues = [i for i in issues if "non-existent parent" in i.description]
        assert len(orphan_issues) == 1
        assert orphan_issues[0].severity == "error"
        assert "999" in orphan_issues[0].description
    
    def test_check_taxonomy_integrity_multiple_roots(self, checker):
        """Test detection of multiple root nodes.""" 
        tree = Mock()
        
        # Create nodes that simulate multiple roots  
        root1 = TaxonomyNode(tax_id=1, name="Root1", rank="root", parent_id=None)
        root2 = TaxonomyNode(tax_id=2, name="Root2", rank="root", parent_id=None)
        
        # Mock tree iteration - CRITICAL: must support both iteration and filtering
        # Must return a fresh iterator each time
        nodes = [root1, root2]
        tree.__iter__ = Mock(side_effect=lambda: iter(nodes))
        tree.get_node = Mock(side_effect=lambda tid: root1 if tid == 1 else root2 if tid == 2 else None)
        
        issues = checker._check_taxonomy_integrity(tree)
        
        # Should detect multiple roots
        root_issues = [i for i in issues if "multiple root nodes" in i.description.lower()]
        assert len(root_issues) == 1
        assert root_issues[0].severity == "warning"
        assert "2" in root_issues[0].description  # Should mention count
    
    def test_check_taxonomy_integrity_no_root(self, checker):
        """Test detection of missing root node."""
        tree = Mock()
        
        # Add nodes but no root (all have parent_id)
        node1 = TaxonomyNode(tax_id=1, name="Node1", rank="genus", parent_id=2)
        node2 = TaxonomyNode(tax_id=2, name="Node2", rank="species", parent_id=3)
        
        # Mock tree methods
        nodes = [node1, node2]
        tree.__iter__ = Mock(side_effect=lambda: iter(nodes))
        tree.get_node = Mock(side_effect=lambda tid: node1 if tid == 1 else node2 if tid == 2 else None)
        
        issues = checker._check_taxonomy_integrity(tree)
        
        # Should detect missing root
        no_root_issues = [i for i in issues if "no root node" in i.description.lower()]
        assert len(no_root_issues) == 1
        assert no_root_issues[0].severity == "error"
    
    def test_check_taxonomy_integrity_duplicate_names(self, checker):
        """Test detection of duplicate names under same parent."""
        tree = TaxonomyTree()
        
        # Root
        root = TaxonomyNode(tax_id=1, name="root", rank="root", parent_id=None)
        tree.add_node(root)
        
        # Two nodes with same name under same parent
        node1 = TaxonomyNode(tax_id=2, name="Duplicate", rank="species", parent_id=1)
        node2 = TaxonomyNode(tax_id=3, name="Duplicate", rank="species", parent_id=1) 
        tree.add_node(node1)
        tree.add_node(node2)
        
        issues = checker._check_taxonomy_integrity(tree)
        
        # Should detect duplicate names
        dup_issues = [i for i in issues if "duplicate name" in i.description.lower()]
        assert len(dup_issues) == 1
        assert dup_issues[0].severity == "warning"
        assert "Duplicate" in dup_issues[0].description
    
    def test_check_genome_taxonomy_links_valid(self, checker, simple_tree, sample_genomes):
        """Test genome-taxonomy links validation with valid data."""
        valid_genomes = sample_genomes[:2]  # Only genomes with valid tax_ids
        
        issues = checker._check_genome_taxonomy_links(valid_genomes, simple_tree)
        
        # Should have no issues for valid links
        link_issues = [i for i in issues if i.category == "genome_taxonomy"]
        assert len(link_issues) == 0
    
    def test_check_genome_taxonomy_links_invalid(self, checker, simple_tree, sample_genomes):
        """Test genome-taxonomy links validation with invalid data."""
        issues = checker._check_genome_taxonomy_links(sample_genomes, simple_tree)
        
        # Should detect genome with invalid tax_id (999)
        link_issues = [i for i in issues if i.category == "genome_taxonomy"]
        assert len(link_issues) == 1
        assert link_issues[0].severity == "error"
        assert "999" in link_issues[0].description
    
    def test_check_duplicate_genomes(self, checker):
        """Test duplicate genome detection."""
        # Create genomes with duplicate IDs
        duplicate_genomes = [
            GenomeInfo(genome_id="dup1", tax_id=1, file_path="/path1.fna"),
            GenomeInfo(genome_id="dup1", tax_id=2, file_path="/path2.fna"),
            GenomeInfo(genome_id="unique1", tax_id=3, file_path="/path3.fna")
        ]
        
        issues = checker._check_duplicate_genomes(duplicate_genomes)
        
        # Should detect duplicate genome IDs
        dup_issues = [i for i in issues if i.category == "genome_duplicates"]
        assert len(dup_issues) == 1
        assert dup_issues[0].severity == "error"
        assert "dup1" in dup_issues[0].description
    
    def test_check_orphaned_genomes(self, checker, simple_tree):
        """Test detection of taxonomy nodes without genome data."""
        # Only provide genomes for some nodes, leaving others orphaned
        genomes = [
            GenomeInfo(genome_id="valid", tax_id=1, file_path="/valid.fna"),
            # tax_id=2 and tax_id=3 from simple_tree will be orphaned (no genomes)
        ]
        
        issues = checker._check_orphaned_genomes(genomes, simple_tree)
        
        # Should detect taxonomy nodes without genomes
        orphan_issues = [i for i in issues if i.category == "orphaned_data"]
        assert len(orphan_issues) == 1
        assert orphan_issues[0].severity == "info"
        assert "leaf taxonomy nodes without genome data" in orphan_issues[0].description
    
    def test_check_sequence_type_consistency(self, checker):
        """Test sequence type validation."""
        genomes = [
            GenomeInfo(genome_id="g1", tax_id=1, sequence_type="genome"),
            GenomeInfo(genome_id="g2", tax_id=2, sequence_type="invalid_type"),  # Invalid type
            GenomeInfo(genome_id="g3", tax_id=3, sequence_type=None),  # Missing type
            GenomeInfo(genome_id="g4", tax_id=4, sequence_type="plasmid")   # Valid type
        ]
        
        issues = checker._check_sequence_type_consistency(genomes)
        
        # Should detect invalid sequence types and missing types
        type_issues = [i for i in issues if i.category == "sequence_types"]
        assert len(type_issues) == 2  # One for invalid type, one for missing type
        
        # Check for invalid type warning
        invalid_issues = [i for i in type_issues if "non-standard sequence types" in i.description.lower()]
        assert len(invalid_issues) == 1
        assert invalid_issues[0].severity == "warning"
        
        # Check for missing type info
        missing_issues = [i for i in type_issues if "unknown/missing sequence type" in i.description]
        assert len(missing_issues) == 1
        assert missing_issues[0].severity == "info"
    
    def test_check_source_consistency(self, checker):
        """Test source validation."""
        genomes = [
            GenomeInfo(genome_id="g1", tax_id=1, source="NCBI"),
            GenomeInfo(genome_id="g2", tax_id=2, source="invalid_source"),  # Invalid source
            GenomeInfo(genome_id="g3", tax_id=3, source=None),  # Missing source
            GenomeInfo(genome_id="g4", tax_id=4, source="GTDB")   # Valid source
        ]
        
        issues = checker._check_source_consistency(genomes)
        
        # Should detect invalid sources and missing sources
        source_issues = [i for i in issues if i.category == "genome_sources"]
        assert len(source_issues) == 2  # One for invalid source, one for missing source
        
        # Check for invalid source info
        invalid_issues = [i for i in source_issues if "non-standard genome sources" in i.description.lower()]
        assert len(invalid_issues) == 1
        assert invalid_issues[0].severity == "info"
        
        # Check for missing source info
        missing_issues = [i for i in source_issues if "unknown/missing source" in i.description]
        assert len(missing_issues) == 1
        assert missing_issues[0].severity == "info"
    
    def test_generate_consistency_report(self, checker):
        """Test consistency report generation."""
        issues = [
            ConsistencyIssue("taxonomy", "error", "Error 1"),
            ConsistencyIssue("taxonomy", "warning", "Warning 1"), 
            ConsistencyIssue("genome_taxonomy", "error", "Error 2"),
            ConsistencyIssue("genome_taxonomy", "info", "Info 1")
        ]
        
        report = checker._generate_consistency_report(issues)
        
        # Check report structure
        assert "issues_by_category" in report
        assert "issues_by_severity" in report
        assert "summary" in report
        assert "consistency_score" in report
        
        # Check categorization (returns lists of issue dicts, not counts)
        assert len(report["issues_by_category"]["taxonomy"]) == 2
        assert len(report["issues_by_category"]["genome_taxonomy"]) == 2
        
        assert len(report["issues_by_severity"]["errors"]) == 2
        assert len(report["issues_by_severity"]["warnings"]) == 1
        assert len(report["issues_by_severity"]["info"]) == 1
        
        # Check summary
        assert report["summary"]["total_issues"] == 4
        assert report["summary"]["errors"] == 2
        assert report["summary"]["warnings"] == 1
        assert report["summary"]["info"] == 1
        
        # Check consistency score
        assert isinstance(report["consistency_score"], float)
        assert 0.0 <= report["consistency_score"] <= 100.0
    
    def test_generate_consistency_report_empty(self, checker):
        """Test consistency report with no issues."""
        report = checker._generate_consistency_report([])
        
        assert report["summary"]["total_issues"] == 0
        assert report["summary"]["errors"] == 0
        assert report["summary"]["warnings"] == 0
        assert report["summary"]["info"] == 0
        assert report["consistency_score"] == 100.0


class TestConsistencyCheckerIntegration:
    """Integration tests with real-like scenarios."""
    
    @pytest.fixture
    def complex_tree(self):
        """Create a more complex taxonomy tree."""
        tree = TaxonomyTree()
        
        # Build a realistic bacterial taxonomy
        root = TaxonomyNode(1, "root", "root", None)
        bacteria = TaxonomyNode(2, "Bacteria", "superkingdom", 1)
        proteobacteria = TaxonomyNode(3, "Proteobacteria", "phylum", 2)
        gamma = TaxonomyNode(4, "Gammaproteobacteria", "class", 3)
        enterobacteriales = TaxonomyNode(5, "Enterobacteriales", "order", 4)
        enterobacteriaceae = TaxonomyNode(6, "Enterobacteriaceae", "family", 5)
        escherichia = TaxonomyNode(7, "Escherichia", "genus", 6)
        ecoli = TaxonomyNode(8, "Escherichia coli", "species", 7)
        
        for node in [root, bacteria, proteobacteria, gamma, enterobacteriales, 
                    enterobacteriaceae, escherichia, ecoli]:
            tree.add_node(node)
        
        return tree
    
    def test_realistic_consistency_check(self, complex_tree):
        """Test consistency check on realistic data."""
        # Create mock repository
        mock_repo = Mock(spec=TaxonomyRepository)
        mock_repo.load_tree = Mock(return_value=complex_tree)
        
        # Add some genomes
        genomes = [
            GenomeInfo("GCF_000005825", 8, "/data/ecoli.fna", 4641652, "genome", "NCBI"),
            GenomeInfo("GCF_000006945", 8, "/data/ecoli2.fna", 4639221, "genome", "NCBI"),
        ]
        mock_repo.get_all_genomes = Mock(return_value=genomes)
        
        # Run check
        checker = ConsistencyChecker(mock_repo)
        result = checker.check_full_consistency()
        
        # Should pass with minimal issues
        assert result["summary"]["total_issues"] < 5  # Allow for minor warnings
        assert result["summary"]["errors"] == 0  # No errors expected
        assert result["total_nodes"] == 8
        assert result["total_genomes"] == 2


if __name__ == "__main__":
    pytest.main([__file__])