"""Test CreateTaxDB compatible exporters."""

import pytest
import sqlite3
from pathlib import Path
from unittest.mock import Mock

from flextaxd.core.models import TaxonomyTree, TaxonomyNode, TaxonomicRank, GenomeInfo
from flextaxd.exporters.accession2taxid import Accession2TaxidExporter
from flextaxd.exporters.nucl2taxid import Nucl2TaxidExporter
from flextaxd.exporters.prot2taxid import Prot2TaxidExporter
from flextaxd.exporters.genome_sizes import GenomeSizesExporter
from flextaxd.exporters.malt_mapdb import MALTMapDBExporter


class TestAccession2TaxidExporter:
    """Test Accession2Taxid format exporter."""
    
    @pytest.fixture
    def tree_with_genomes(self):
        """Create a test tree with genome information."""
        tree = TaxonomyTree()
        
        # Add nodes
        root = TaxonomyNode(1, "root", TaxonomicRank.CUSTOM, None)
        bacteria = TaxonomyNode(2, "Bacteria", TaxonomicRank.SUPERKINGDOM, 1)
        ecoli = TaxonomyNode(562, "Escherichia coli", TaxonomicRank.SPECIES, 2)
        
        tree.add_node(root)
        tree.add_node(bacteria)
        tree.add_node(ecoli)
        
        # Add genome information
        genome1 = GenomeInfo(
            genome_id="GCF_000005825.2",
            tax_id=562,
            assembly_accession="GCF_000005825.2",
            file_path="/path/to/genome1.fna",
            sequence_type="genome"
        )
        tree.add_genome(genome1)
        
        return tree
    
    def test_export_with_genomes(self, tmp_path, tree_with_genomes):
        """Test exporting accession2taxid with genome data."""
        output_file = tmp_path / "accession2taxid.txt"
        exporter = Accession2TaxidExporter()
        
        exporter.export(tree_with_genomes, output_file, include_genomes=True)
        
        assert output_file.exists()
        content = output_file.read_text()
        lines = content.strip().split('\n')
        
        # Check header
        assert lines[0] == "accession\taccession.version\ttaxid\tgi"
        
        # Check data line
        assert len(lines) == 2
        parts = lines[1].split('\t')
        assert parts[0] == "GCF_000005825"  # Base accession
        assert parts[1] == "GCF_000005825.2"  # Version
        assert parts[2] == "562"  # Taxonomy ID
        assert parts[3] == "0"   # GI placeholder
    
    def test_export_without_genomes(self, tmp_path, tree_with_genomes):
        """Test exporting accession2taxid without genome data."""
        output_file = tmp_path / "accession2taxid.txt"
        exporter = Accession2TaxidExporter()
        
        exporter.export(tree_with_genomes, output_file, include_genomes=False)
        
        assert output_file.exists()
        content = output_file.read_text()
        lines = content.strip().split('\n')
        
        # Should only have header
        assert len(lines) == 1
        assert lines[0] == "accession\taccession.version\ttaxid\tgi"


class TestNucl2TaxidExporter:
    """Test Nucl2Taxid format exporter."""
    
    @pytest.fixture
    def tree_with_mixed_genomes(self):
        """Create a test tree with mixed sequence types."""
        tree = TaxonomyTree()
        
        root = TaxonomyNode(1, "root", TaxonomicRank.CUSTOM, None)
        bacteria = TaxonomyNode(2, "Bacteria", TaxonomicRank.SUPERKINGDOM, 1)
        
        tree.add_node(root)
        tree.add_node(bacteria)
        
        # Add nucleotide genome
        nucl_genome = GenomeInfo(
            genome_id="NC_000913",
            tax_id=2,
            sequence_type="genome"
        )
        tree.add_genome(nucl_genome)
        
        # Add protein genome
        prot_genome = GenomeInfo(
            genome_id="WP_000001",
            tax_id=2,
            sequence_type="protein"
        )
        tree.add_genome(prot_genome)
        
        return tree
    
    def test_export_nucleotide_filter(self, tmp_path, tree_with_mixed_genomes):
        """Test exporting nucl2taxid with nucleotide filter."""
        output_file = tmp_path / "nucl2taxid.txt"
        exporter = Nucl2TaxidExporter()
        
        exporter.export(tree_with_mixed_genomes, output_file, 
                       sequence_filter='nucleotide', include_genomes=True)
        
        assert output_file.exists()
        content = output_file.read_text()
        lines = [line for line in content.strip().split('\n') if line]
        
        # Should only include nucleotide sequences
        assert len(lines) == 1
        assert "NC_000913\t2" in lines[0]
    
    def test_export_all_sequences(self, tmp_path, tree_with_mixed_genomes):
        """Test exporting nucl2taxid with all sequences."""
        output_file = tmp_path / "nucl2taxid.txt"
        exporter = Nucl2TaxidExporter()
        
        exporter.export(tree_with_mixed_genomes, output_file,
                       sequence_filter='all', include_genomes=True)
        
        assert output_file.exists()
        content = output_file.read_text()
        lines = [line for line in content.strip().split('\n') if line]
        
        # Should include both sequences
        assert len(lines) == 2


class TestProt2TaxidExporter:
    """Test Prot2Taxid format exporter."""
    
    @pytest.fixture
    def tree_with_genomes(self):
        """Create a test tree with genome information."""
        tree = TaxonomyTree()
        
        # Add nodes
        root = TaxonomyNode(1, "root", TaxonomicRank.CUSTOM, None)
        bacteria = TaxonomyNode(2, "Bacteria", TaxonomicRank.SUPERKINGDOM, 1)
        ecoli = TaxonomyNode(562, "Escherichia coli", TaxonomicRank.SPECIES, 2)
        
        tree.add_node(root)
        tree.add_node(bacteria)
        tree.add_node(ecoli)
        
        # Add genome information
        genome1 = GenomeInfo(
            genome_id="GCF_000005825.2",
            tax_id=562,
            assembly_accession="GCF_000005825.2",
            file_path="/path/to/genome1.fna",
            sequence_type="genome"
        )
        tree.add_genome(genome1)
        
        return tree
    
    def test_export_with_header(self, tmp_path, tree_with_genomes):
        """Test that prot2taxid exports with header."""
        output_file = tmp_path / "prot2taxid.txt"
        exporter = Prot2TaxidExporter()
        
        exporter.export(tree_with_genomes, output_file, include_genomes=True, sequence_filter='all')
        
        assert output_file.exists()
        content = output_file.read_text()
        lines = content.strip().split('\n')
        
        # Check header exists
        assert lines[0] == "sequence_id\ttaxid"
        
        # Check data
        assert len(lines) == 2
        assert "GCF_000005825.2\t562" in lines[1]


class TestGenomeSizesExporter:
    """Test Genome Sizes format exporter."""
    
    @pytest.fixture
    def tree_with_size_info(self):
        """Create a test tree with genome size information."""
        tree = TaxonomyTree()
        
        root = TaxonomyNode(1, "root", TaxonomicRank.CUSTOM, None)
        bacteria = TaxonomyNode(2, "Bacteria", TaxonomicRank.SUPERKINGDOM, 1)
        species = TaxonomyNode(562, "Escherichia coli", TaxonomicRank.SPECIES, 2)
        
        tree.add_node(root)
        tree.add_node(bacteria)
        tree.add_node(species)
        
        # Mock genome with size info
        genome = Mock()
        genome.genome_id = "GCF_000005825.2"
        genome.assembly_accession = "GCF_000005825.2"
        genome.genome_size = 4641652
        genome.sequence_length = None
        genome.file_path = None
        
        # Add to tree
        tree.add_genome(GenomeInfo(
            genome_id="GCF_000005825.2",
            tax_id=562,
            assembly_accession="GCF_000005825.2"
        ))
        
        return tree
    
    def test_export_genome_sizes(self, tmp_path, tree_with_size_info):
        """Test exporting genome sizes format."""
        output_file = tmp_path / "genome_sizes.txt"
        exporter = GenomeSizesExporter()
        
        exporter.export(tree_with_size_info, output_file, include_genomes=True)
        
        assert output_file.exists()
        content = output_file.read_text()
        lines = content.strip().split('\n')
        
        # Check header
        expected_header = "taxid\tassembly_accession\tspecies_taxid\torganism_name\tassembly_level\tgenome_size"
        assert lines[0] == expected_header
        
        # Check data
        assert len(lines) == 2
        parts = lines[1].split('\t')
        assert parts[0] == "562"  # taxid
        assert parts[1] == "GCF_000005825.2"  # assembly_accession
        assert parts[2] == "562"  # species_taxid
        assert parts[3] == "Escherichia coli"  # organism_name
        assert parts[4] == "Complete Genome"  # assembly_level
        # genome_size will be default since mock doesn't have it


class TestMALTMapDBExporter:
    """Test MALT MapDB format exporter."""
    
    @pytest.fixture
    def tree_with_genomes(self):
        """Create a test tree with genome information."""
        tree = TaxonomyTree()
        
        # Add nodes
        root = TaxonomyNode(1, "root", TaxonomicRank.CUSTOM, None)
        bacteria = TaxonomyNode(2, "Bacteria", TaxonomicRank.SUPERKINGDOM, 1)
        ecoli = TaxonomyNode(562, "Escherichia coli", TaxonomicRank.SPECIES, 2)
        
        tree.add_node(root)
        tree.add_node(bacteria)
        tree.add_node(ecoli)
        
        # Add genome information
        genome1 = GenomeInfo(
            genome_id="GCF_000005825.2",
            tax_id=562,
            assembly_accession="GCF_000005825.2",
            file_path="/path/to/genome1.fna",
            sequence_type="genome"
        )
        tree.add_genome(genome1)
        
        return tree
    
    def test_export_malt_database(self, tmp_path, tree_with_genomes):
        """Test exporting MALT MapDB SQLite database."""
        output_file = tmp_path / "taxonomy.db"
        exporter = MALTMapDBExporter()
        
        exporter.export(tree_with_genomes, output_file, include_genomes=True)
        
        assert output_file.exists()
        
        # Validate database structure
        validation = exporter.validate_database(output_file)
        assert validation['valid']
        assert 'info' in validation['tables']
        assert 'mappings' in validation['tables']
        assert validation['mappings_count'] > 0
        
        # Check database content
        with sqlite3.connect(output_file) as conn:
            # Check info table
            info_data = dict(conn.execute("SELECT key, value FROM info").fetchall())
            assert 'version' in info_data
            assert 'type' in info_data
            assert 'created_by' in info_data
            assert info_data['created_by'] == 'FlexTaxD'
            
            # Check mappings table
            mappings = conn.execute("SELECT sequence_id, taxonomy_id FROM mappings").fetchall()
            assert len(mappings) > 0
            
            # Verify specific mapping
            found_mapping = False
            for seq_id, tax_id in mappings:
                if seq_id == "GCF_000005825.2" and tax_id == 562:
                    found_mapping = True
                    break
            assert found_mapping
    
    def test_export_empty_database(self, tmp_path):
        """Test exporting empty MALT MapDB when no genomes."""
        tree = TaxonomyTree()
        root = TaxonomyNode(1, "root", TaxonomicRank.CUSTOM, None)
        tree.add_node(root)
        
        output_file = tmp_path / "empty_taxonomy.db"
        exporter = MALTMapDBExporter()
        
        exporter.export(tree, output_file, include_genomes=False)
        
        assert output_file.exists()
        
        # Validate empty database
        validation = exporter.validate_database(output_file)
        assert validation['valid']
        assert validation['mappings_count'] == 0


class TestCreateTaxDBIntegration:
    """Integration tests for all CreateTaxDB exporters."""
    
    @pytest.fixture
    def tree_with_genomes(self):
        """Create a test tree with genome information."""
        tree = TaxonomyTree()
        
        # Add nodes
        root = TaxonomyNode(1, "root", TaxonomicRank.CUSTOM, None)
        bacteria = TaxonomyNode(2, "Bacteria", TaxonomicRank.SUPERKINGDOM, 1)
        ecoli = TaxonomyNode(562, "Escherichia coli", TaxonomicRank.SPECIES, 2)
        
        tree.add_node(root)
        tree.add_node(bacteria)
        tree.add_node(ecoli)
        
        # Add genome information
        genome1 = GenomeInfo(
            genome_id="GCF_000005825.2",
            tax_id=562,
            assembly_accession="GCF_000005825.2",
            file_path="/path/to/genome1.fna",
            sequence_type="genome"
        )
        tree.add_genome(genome1)
        
        return tree
    
    def test_all_exporters_run_without_error(self, tmp_path, tree_with_genomes):
        """Test that all CreateTaxDB exporters can run without errors."""
        exporters = [
            (Accession2TaxidExporter(), "accession2taxid.txt"),
            (Nucl2TaxidExporter(), "nucl2taxid.txt"),
            (Prot2TaxidExporter(), "prot2taxid.txt"),
            (GenomeSizesExporter(), "genome_sizes.txt"),
            (MALTMapDBExporter(), "taxonomy.db"),
        ]
        
        for exporter, filename in exporters:
            output_file = tmp_path / filename
            
            # Should not raise any exceptions
            exporter.export(tree_with_genomes, output_file, include_genomes=True)
            
            # Should create output file
            assert output_file.exists()
            
            # File should have content
            if filename.endswith('.db'):
                # SQLite database
                with sqlite3.connect(output_file) as conn:
                    tables = conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                    assert len(tables) > 0
            else:
                # Text file
                content = output_file.read_text()
                assert len(content.strip()) > 0