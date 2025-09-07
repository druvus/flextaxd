"""Examples and tests demonstrating genome-taxonomy mapping capabilities.

This module provides comprehensive examples of how FlexTaxD handles:
1. Multiple genomes per taxonomic node
2. Multiple accession types tracking
3. NCBI datasets integration
4. Genome validation and quality control

These examples serve both as tests and as documentation for developers.
"""

import pytest
from unittest.mock import Mock, patch
from pathlib import Path

from flextaxd.core.models import GenomeInfo, TaxonomyTree, TaxonomyNode, TaxonomicRank
from flextaxd.database.sqlite import SQLiteTaxonomyRepository


class TestMultipleGenomesPerNode:
    """Demonstrate multiple genomes associated with the same taxonomic node."""

    def test_multiple_ecoli_strains_same_species(self):
        """Test multiple E. coli genomes under the same species node."""
        tree = TaxonomyTree()
        
        # Create E. coli species node
        ecoli_node = TaxonomyNode(
            tax_id=562,
            name="Escherichia coli",
            rank=TaxonomicRank.SPECIES
        )
        tree.add_node(ecoli_node)
        
        # Add multiple genome strains to the same species
        strains = [
            GenomeInfo(
                genome_id="ecoli_k12_mg1655",
                tax_id=562,
                assembly_accession="GCF_000005825.2",
                strain="K-12 substr. MG1655",
                source="NCBI",
                description="Laboratory reference strain"
            ),
            GenomeInfo(
                genome_id="ecoli_o157_sakai",
                tax_id=562,
                assembly_accession="GCF_000008865.2",
                strain="O157:H7 str. Sakai",
                source="NCBI",
                description="Enterohemorrhagic E. coli"
            ),
            GenomeInfo(
                genome_id="ecoli_clinical_2023",
                tax_id=562,
                assembly_accession="GCA_123456789.1",
                strain="Clinical isolate 2023-001",
                source="Hospital",
                description="MDR clinical isolate"
            )
        ]
        
        # Add all genomes to the tree
        for strain in strains:
            tree.add_genome(strain)
        
        # Verify multiple genomes are associated with the same node
        ecoli_genomes = tree.get_genomes_for_node(562)
        assert len(ecoli_genomes) == 3
        
        # Verify each genome has correct properties
        genome_ids = {g.genome_id for g in ecoli_genomes}
        expected_ids = {"ecoli_k12_mg1655", "ecoli_o157_sakai", "ecoli_clinical_2023"}
        assert genome_ids == expected_ids
        
        # Verify strain diversity
        strains_found = {g.strain for g in ecoli_genomes if g.strain}
        assert len(strains_found) == 3

    def test_hierarchical_genome_distribution(self):
        """Test genomes distributed across different taxonomic levels."""
        tree = TaxonomyTree()
        
        # Create taxonomic hierarchy
        nodes = [
            TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT),
            TaxonomyNode(tax_id=2, name="Bacteria", rank=TaxonomicRank.SUPERKINGDOM, parent_id=1),
            TaxonomyNode(tax_id=543, name="Enterobacteriaceae", rank=TaxonomicRank.FAMILY, parent_id=2),
            TaxonomyNode(tax_id=561, name="Escherichia", rank=TaxonomicRank.GENUS, parent_id=543),
            TaxonomyNode(tax_id=562, name="Escherichia coli", rank=TaxonomicRank.SPECIES, parent_id=561),
        ]
        
        for node in nodes:
            tree.add_node(node)
        
        # Add genomes at different taxonomic levels
        genomes = [
            GenomeInfo(genome_id="family_representative", tax_id=543, source="Reference"),  # Family level
            GenomeInfo(genome_id="genus_representative", tax_id=561, source="Reference"),   # Genus level
            GenomeInfo(genome_id="species_genome_1", tax_id=562, source="NCBI"),           # Species level
            GenomeInfo(genome_id="species_genome_2", tax_id=562, source="NCBI"),           # Species level
        ]
        
        for genome in genomes:
            tree.add_genome(genome)
        
        # Test genome retrieval at different levels
        family_genomes = tree.get_genomes_for_node(543)    # Family level
        genus_genomes = tree.get_genomes_for_node(561)     # Genus level  
        species_genomes = tree.get_genomes_for_node(562)   # Species level
        
        assert len(family_genomes) == 1   # Only direct associations
        assert len(genus_genomes) == 1    # Only direct associations
        assert len(species_genomes) == 2  # Two species genomes
        
        # Verify IDs
        assert family_genomes[0].genome_id == "family_representative"
        assert genus_genomes[0].genome_id == "genus_representative"
        species_ids = {g.genome_id for g in species_genomes}
        assert species_ids == {"species_genome_1", "species_genome_2"}


class TestAccessionTracking:
    """Demonstrate comprehensive accession number tracking."""

    def test_multiple_accession_types(self):
        """Test genome with multiple types of accessions."""
        genome = GenomeInfo(
            genome_id="comprehensive_example",
            tax_id=562,
            assembly_accession="GCF_000005825.2",      # RefSeq assembly
            nucleotide_accession="NC_000913.3",       # E. coli chromosome
            protein_accession="WP_000000001.1",       # Representative protein
            biosample_accession="SAMN02604091",       # Sample metadata
            strain="K-12 substr. MG1655",
            source="NCBI"
        )
        
        # Test accession access methods
        all_accessions = genome.all_accessions
        expected_accessions = {
            'assembly': 'GCF_000005825.2',
            'nucleotide': 'NC_000913.3',
            'protein': 'WP_000000001.1',
            'biosample': 'SAMN02604091'
        }
        assert all_accessions == expected_accessions
        
        # Test primary accession (should be assembly)
        assert genome.primary_accession == "GCF_000005825.2"
        
        # Test accession validation (should pass)
        validation_issues = genome.validate_accessions()
        assert len(validation_issues) == 0

    def test_accession_priority_system(self):
        """Test primary accession priority system."""
        # Test assembly priority (highest)
        genome_with_assembly = GenomeInfo(
            genome_id="test1", tax_id=562,
            assembly_accession="GCF_000005825.2",
            nucleotide_accession="NC_000913.3"
        )
        assert genome_with_assembly.primary_accession == "GCF_000005825.2"
        
        # Test nucleotide priority (when no assembly)
        genome_nucleotide_only = GenomeInfo(
            genome_id="test2", tax_id=562,
            nucleotide_accession="NC_000913.3",
            protein_accession="WP_000000001.1"
        )
        assert genome_nucleotide_only.primary_accession == "NC_000913.3"
        
        # Test protein priority (when no assembly/nucleotide)
        genome_protein_only = GenomeInfo(
            genome_id="test3", tax_id=562,
            protein_accession="WP_000000001.1",
            biosample_accession="SAMN02604091"
        )
        assert genome_protein_only.primary_accession == "WP_000000001.1"

    def test_accession_validation(self):
        """Test accession format validation."""
        # Valid accessions
        valid_genome = GenomeInfo(
            genome_id="valid_test",
            tax_id=562,
            assembly_accession="GCF_000005825.2",
            nucleotide_accession="NC_000913.3",
            protein_accession="WP_000000001.1",
            biosample_accession="SAMN02604091"
        )
        
        issues = valid_genome.validate_accessions()
        assert len(issues) == 0
        
        # Invalid accessions
        invalid_genome = GenomeInfo(
            genome_id="invalid_test",
            tax_id=562,
            assembly_accession="INVALID_FORMAT",     # Wrong format
            nucleotide_accession="NC_123",          # Missing version
            protein_accession="WP_123",             # Missing version
            biosample_accession="INVALID"           # Wrong format
        )
        
        issues = invalid_genome.validate_accessions()
        assert len(issues) == 4  # All accessions are invalid


class TestNCBIDatasetsIntegration:
    """Test NCBI datasets integration for automated genome discovery."""

    @patch('flextaxd.utils.ncbi_datasets.validate_command_exists')
    @patch('flextaxd.utils.ncbi_datasets.run_command_safely')
    def test_automated_genome_discovery(self, mock_run_command, mock_validate):
        """Test automated genome discovery from NCBI datasets."""
        from flextaxd.utils.ncbi_datasets import NCBIDatasetsManager
        
        # Mock datasets command availability
        mock_validate.return_value = True
        
        # Mock successful dataset download
        mock_result = Mock()
        mock_result.returncode = 0
        mock_run_command.return_value = mock_result
        
        # Create manager
        manager = NCBIDatasetsManager()
        
        # Test taxon validation
        mock_result.stdout = '{"valid": true, "taxon": "Escherichia coli"}'
        validation_result = manager.validate_taxon("Escherichia coli")
        
        assert validation_result["valid"] is True
        assert validation_result["taxon"] == "Escherichia coli"

    def test_assembly_level_filtering(self):
        """Test assembly level filtering capabilities."""
        from flextaxd.utils.ncbi_datasets import NCBIDatasetsManager
        
        with patch('flextaxd.utils.ncbi_datasets.validate_command_exists', return_value=True):
            manager = NCBIDatasetsManager()
            
            # Test available assembly levels
            levels = manager.get_available_assembly_levels()
            expected_levels = ["complete", "chromosome", "scaffold", "contig", "all"]
            assert levels == expected_levels


class TestGenomeValidation:
    """Test genome validation and quality control."""

    def test_comprehensive_genome_validation(self):
        """Test comprehensive validation of genome entries."""
        # Create a genome with various issues
        problematic_genome = GenomeInfo(
            genome_id="test_genome",
            tax_id=562,
            file_path="/nonexistent/path.fasta",  # Non-existent file
            assembly_accession="INVALID_FORMAT",   # Invalid accession
            source=""  # Empty source
        )
        
        # Test basic validation
        basic_issues = problematic_genome.validate()
        file_issues = [issue for issue in basic_issues if "does not exist" in issue]
        assert len(file_issues) > 0
        
        # Test accession validation
        accession_issues = problematic_genome.validate_accessions()
        assert len(accession_issues) > 0
        
        # Create a valid genome
        valid_genome = GenomeInfo(
            genome_id="valid_genome",
            tax_id=562,
            assembly_accession="GCF_000005825.2",
            strain="K-12 substr. MG1655",
            source="NCBI"
        )
        
        # Should have no validation issues
        assert len(valid_genome.validate()) == 0
        assert len(valid_genome.validate_accessions()) == 0

    def test_multi_source_integration(self):
        """Test integration of genomes from multiple sources."""
        tree = TaxonomyTree()
        
        # Add E. coli species node
        tree.add_node(TaxonomyNode(tax_id=562, name="Escherichia coli", rank=TaxonomicRank.SPECIES))
        
        # Add genomes from different sources
        sources = [
            GenomeInfo(
                genome_id="ncbi_refseq",
                tax_id=562,
                assembly_accession="GCF_000005825.2",
                source="NCBI_RefSeq",
                description="RefSeq reference genome"
            ),
            GenomeInfo(
                genome_id="gtdb_representative",
                tax_id=562,
                assembly_accession="GCA_000005825.2",
                source="GTDB",
                description="GTDB r207 representative"
            ),
            GenomeInfo(
                genome_id="lab_sequencing",
                tax_id=562,
                file_path="/data/lab_ecoli.fasta",
                source="Lab_Sequencing",
                strain="Lab strain 2023-A",
                description="In-house sequenced strain"
            )
        ]
        
        for genome in sources:
            tree.add_genome(genome)
        
        # Verify all sources integrated
        ecoli_genomes = tree.get_genomes_for_node(562)
        assert len(ecoli_genomes) == 3
        
        # Verify source diversity
        sources_found = {g.source for g in ecoli_genomes}
        assert sources_found == {"NCBI_RefSeq", "GTDB", "Lab_Sequencing"}


class TestDatabaseIntegration:
    """Test genome-taxonomy mapping in database context."""

    def test_database_genome_storage(self, tmp_path):
        """Test storing and retrieving genomes from database."""
        db_path = tmp_path / "test_genomes.ftd"
        
        # Create tree with genomes
        tree = TaxonomyTree()
        tree.add_node(TaxonomyNode(tax_id=562, name="Escherichia coli", rank=TaxonomicRank.SPECIES))
        
        # Add multiple genomes
        genomes = [
            GenomeInfo(
                genome_id=f"ecoli_genome_{i}",
                tax_id=562,
                assembly_accession=f"GCF_00000{i:04d}.1",
                strain=f"Strain {i}",
                source="Test"
            )
            for i in range(1, 6)  # 5 genomes
        ]
        
        for genome in genomes:
            tree.add_genome(genome)
        
        # Save to database
        with SQLiteTaxonomyRepository(db_path) as repo:
            repo.save_tree(tree)
        
        # Load from database and verify
        with SQLiteTaxonomyRepository(db_path) as repo:
            loaded_tree = repo.load_tree()
            loaded_genomes = loaded_tree.get_genomes_for_node(562)
            
            assert len(loaded_genomes) == 5
            
            # Verify genome properties preserved
            genome_ids = {g.genome_id for g in loaded_genomes}
            expected_ids = {f"ecoli_genome_{i}" for i in range(1, 6)}
            assert genome_ids == expected_ids
            
            # Verify accessions preserved
            accessions = {g.assembly_accession for g in loaded_genomes if g.assembly_accession}
            assert len(accessions) == 5


# Integration test fixtures and utilities
@pytest.fixture
def sample_ecoli_tree():
    """Create a sample E. coli taxonomy tree with multiple genomes."""
    tree = TaxonomyTree()
    
    # Add taxonomic nodes
    nodes = [
        TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT),
        TaxonomyNode(tax_id=561, name="Escherichia", rank=TaxonomicRank.GENUS, parent_id=1),
        TaxonomyNode(tax_id=562, name="Escherichia coli", rank=TaxonomicRank.SPECIES, parent_id=561),
    ]
    
    for node in nodes:
        tree.add_node(node)
    
    # Add sample genomes
    genomes = [
        GenomeInfo(
            genome_id="ecoli_k12",
            tax_id=562,
            assembly_accession="GCF_000005825.2",
            strain="K-12 substr. MG1655",
            source="NCBI"
        ),
        GenomeInfo(
            genome_id="ecoli_o157",
            tax_id=562,
            assembly_accession="GCF_000008865.2",
            strain="O157:H7 str. Sakai",
            source="NCBI"
        ),
    ]
    
    for genome in genomes:
        tree.add_genome(genome)
    
    return tree


def validate_genome_quality(genome: GenomeInfo) -> dict:
    """Utility function for comprehensive genome quality validation."""
    return {
        'basic_validation': genome.validate(),
        'accession_validation': genome.validate_accessions(),
        'has_primary_accession': genome.primary_accession is not None,
        'accession_count': len(genome.all_accessions),
        'has_file': genome.has_sequence_file,
        'quality_score': calculate_genome_quality_score(genome)
    }


def calculate_genome_quality_score(genome: GenomeInfo) -> float:
    """Calculate a quality score for a genome entry (0-1 scale)."""
    score = 0.0
    
    # Basic required fields
    if genome.genome_id and genome.tax_id > 0:
        score += 0.2
    
    # Accession information
    accession_count = len(genome.all_accessions)
    if accession_count > 0:
        score += min(0.4, accession_count * 0.1)
    
    # File availability
    if genome.has_sequence_file:
        score += 0.2
    
    # Metadata completeness
    metadata_fields = [genome.strain, genome.source, genome.description]
    filled_fields = sum(1 for field in metadata_fields if field)
    score += (filled_fields / len(metadata_fields)) * 0.2
    
    return min(1.0, score)


# Example usage and test patterns
if __name__ == "__main__":
    # Example: Create a comprehensive genome database
    tree = TaxonomyTree()
    
    # Add E. coli species
    tree.add_node(TaxonomyNode(tax_id=562, name="Escherichia coli", rank=TaxonomicRank.SPECIES))
    
    # Add multiple strains with comprehensive metadata
    strains = [
        {
            'genome_id': 'ecoli_k12_mg1655',
            'assembly_accession': 'GCF_000005825.2',
            'nucleotide_accession': 'NC_000913.3',
            'strain': 'K-12 substr. MG1655',
            'description': 'Laboratory reference strain'
        },
        {
            'genome_id': 'ecoli_o157_sakai',
            'assembly_accession': 'GCF_000008865.2',
            'strain': 'O157:H7 str. Sakai',
            'description': 'Enterohemorrhagic E. coli'
        }
    ]
    
    for strain_data in strains:
        genome = GenomeInfo(
            tax_id=562,
            source="NCBI",
            **strain_data
        )
        tree.add_genome(genome)
    
    # Verify the setup
    ecoli_genomes = tree.get_genomes_for_node(562)
    print(f"Created E. coli database with {len(ecoli_genomes)} genomes")
    
    for genome in ecoli_genomes:
        quality = validate_genome_quality(genome)
        print(f"  {genome.genome_id}: Quality score {quality['quality_score']:.2f}")