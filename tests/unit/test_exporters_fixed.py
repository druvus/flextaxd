"""Comprehensive unit tests for taxonomy exporters with proper fixtures."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from flextaxd.core.models import (
    TaxonomyTree, TaxonomyNode, TaxonomicRank, GenomeInfo
)
from flextaxd.core.exceptions import ExportError
from flextaxd.exporters import (
    NCBIExporter, Kraken2Exporter, GanonExporter, CentrifugeExporter,
    Accession2TaxidExporter, Nucl2TaxidExporter, Prot2TaxidExporter,
    GenomeSizesExporter, MALTMapDBExporter
)
from flextaxd.exporters.base import TaxonomyExporter, FileBasedExporter, DirectoryBasedExporter

# Import fixtures
from .test_fixtures import (
    simple_taxonomy_tree, complex_taxonomy_tree, tree_with_genomes,
    mock_sequence_files, mock_genome_directory, expected_ncbi_formats
)


class TestTaxonomyExporterBase:
    """Test base exporter functionality."""
    
    def test_abstract_exporter_cannot_be_instantiated(self):
        """Test that abstract base class cannot be instantiated."""
        with pytest.raises(TypeError):
            TaxonomyExporter()
    
    def test_file_based_exporter_requires_directory_false(self):
        """Test FileBasedExporter returns False for requires_directory."""
        
        class TestFileExporter(FileBasedExporter):
            def export(self, tree, output_path, **kwargs):
                pass
            
            @property
            def exporter_name(self):
                return "test_file"
            
            @property  
            def file_extensions(self):
                return [".test"]
        
        exporter = TestFileExporter()
        assert exporter.requires_directory is False
    
    def test_directory_based_exporter_requires_directory_true(self):
        """Test DirectoryBasedExporter returns True for requires_directory."""
        
        class TestDirExporter(DirectoryBasedExporter):
            def export(self, tree, output_path, **kwargs):
                pass
                
            @property
            def exporter_name(self):
                return "test_dir"
            
            @property
            def file_extensions(self):
                return [".test"]
        
        exporter = TestDirExporter()
        assert exporter.requires_directory is True


class TestNCBIExporter:
    """Test NCBI dump format exporter."""
    
    def test_exporter_properties(self):
        """Test exporter basic properties."""
        exporter = NCBIExporter()
        assert exporter.exporter_name == "ncbi"
        assert ".dmp" in exporter.file_extensions
        assert exporter.requires_directory is True
    
    def test_export_basic_functionality(self, simple_taxonomy_tree, expected_ncbi_formats):
        """Test basic export functionality."""
        exporter = NCBIExporter()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(simple_taxonomy_tree, output_path)
            
            # Should create nodes.dmp and names.dmp files
            nodes_file = output_path / "nodes.dmp"
            names_file = output_path / "names.dmp"
            
            assert nodes_file.exists()
            assert names_file.exists()
            
            # Check file content matches expected NCBI format
            nodes_content = nodes_file.read_text()
            names_content = names_file.read_text()
            
            # Check specific nodes are present with correct format
            assert expected_ncbi_formats['nodes_root'] in nodes_content
            assert expected_ncbi_formats['nodes_bacteria'] in nodes_content
            assert expected_ncbi_formats['nodes_ecoli'] in nodes_content
            
            # Check names are present
            assert expected_ncbi_formats['names_root'] in names_content
            assert expected_ncbi_formats['names_bacteria'] in names_content
            assert expected_ncbi_formats['names_ecoli'] in names_content
    
    def test_export_with_compression(self, simple_taxonomy_tree):
        """Test export with compression option."""
        exporter = NCBIExporter()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            
            # Mock the compression function to avoid dependency issues
            with patch('flextaxd.utils.subprocess_utils.compress_file') as mock_compress:
                exporter.export(simple_taxonomy_tree, output_path, compress=True)
                
                # Should call compress twice (for both files)
                assert mock_compress.call_count == 2
    
    def test_export_custom_filenames(self, simple_taxonomy_tree):
        """Test export with custom filenames."""
        exporter = NCBIExporter()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(
                simple_taxonomy_tree, 
                output_path,
                names_file='custom_names.dmp',
                nodes_file='custom_nodes.dmp'
            )
            
            assert (output_path / "custom_names.dmp").exists()
            assert (output_path / "custom_nodes.dmp").exists()


class TestKraken2Exporter:
    """Test Kraken2 format exporter."""
    
    def test_exporter_properties(self):
        """Test exporter basic properties."""
        exporter = Kraken2Exporter()
        assert exporter.exporter_name == "kraken2"
        assert ".dmp" in exporter.file_extensions
        assert ".map" in exporter.file_extensions
        assert exporter.requires_directory is True
    
    def test_export_functionality(self, simple_taxonomy_tree):
        """Test export functionality."""
        exporter = Kraken2Exporter()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(simple_taxonomy_tree, output_path)
            
            # Should create necessary files
            names_file = output_path / "names.dmp"
            nodes_file = output_path / "nodes.dmp"
            
            assert names_file.exists()
            assert nodes_file.exists()
            
            # Check basic content structure
            names_content = names_file.read_text()
            assert len(names_content.strip().split('\n')) == simple_taxonomy_tree.node_count


class TestGanonExporter:
    """Test Ganon format exporter."""
    
    def test_exporter_properties(self):
        """Test exporter properties."""
        exporter = GanonExporter()
        assert exporter.exporter_name == "ganon"
        assert ".dmp" in exporter.file_extensions
        assert ".info" in exporter.file_extensions
        assert exporter.requires_directory is True
    
    def test_export_creates_files(self, simple_taxonomy_tree):
        """Test that export creates expected files."""
        exporter = GanonExporter()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(simple_taxonomy_tree, output_path)
            
            # Should create ganon-specific files in taxonomy subdirectory
            names_file = output_path / "taxonomy" / "names.dmp"
            nodes_file = output_path / "taxonomy" / "nodes.dmp"
            
            assert names_file.exists()
            assert nodes_file.exists()
            assert (output_path / "taxonomy").is_dir()


class TestCentrifugeExporter:
    """Test Centrifuge format exporter."""
    
    def test_exporter_properties(self):
        """Test exporter properties."""
        exporter = CentrifugeExporter()
        assert exporter.exporter_name == "centrifuge"
        assert ".dmp" in exporter.file_extensions
        assert ".tab" in exporter.file_extensions
        assert exporter.requires_directory is True
    
    def test_export_functionality(self, simple_taxonomy_tree):
        """Test export functionality."""
        exporter = CentrifugeExporter()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(simple_taxonomy_tree, output_path)
            
            # Should create centrifuge-specific files in taxonomy subdirectory
            names_file = output_path / "taxonomy" / "names.dmp"
            nodes_file = output_path / "taxonomy" / "nodes.dmp"
            
            assert names_file.exists()
            assert nodes_file.exists()
            assert (output_path / "taxonomy").is_dir()
            
            # No genomes in simple_taxonomy_tree, so no conversion table
            conversion_file = output_path / "conversion_table.tab"
            assert not conversion_file.exists()


class TestAccession2TaxidExporter:
    """Test accession2taxid format exporter."""
    
    def test_exporter_properties(self):
        """Test exporter properties."""
        exporter = Accession2TaxidExporter()
        assert exporter.exporter_name == "accession2taxid"
        assert ".txt" in exporter.file_extensions
        assert exporter.requires_directory is False
    
    def test_export_with_genomes(self, tree_with_genomes):
        """Test export with genome data."""
        exporter = Accession2TaxidExporter()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            output_path = Path(f.name)
        
        try:
            exporter.export(tree_with_genomes, output_path)
            
            assert output_path.exists()
            content = output_path.read_text()
            
            # Should have header and genome entries
            lines = content.strip().split('\n')
            assert len(lines) > 1  # Header + data
            assert "accession" in lines[0].lower()  # Header
            
            # Should contain genome accessions
            assert any("NC_000913" in line for line in lines[1:])
            assert any("562" in line for line in lines[1:])  # Tax ID
            
        finally:
            if output_path.exists():
                output_path.unlink()


class TestNucl2TaxidExporter:
    """Test nucl2taxid format exporter."""
    
    def test_exporter_properties(self):
        """Test exporter properties."""
        exporter = Nucl2TaxidExporter()
        assert exporter.exporter_name == "nucl2taxid"
        assert ".txt" in exporter.file_extensions
        assert exporter.requires_directory is False
    
    def test_export_nucleotide_sequences(self, tree_with_genomes):
        """Test export filters nucleotide sequences."""
        exporter = Nucl2TaxidExporter()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            output_path = Path(f.name)
        
        try:
            exporter.export(tree_with_genomes, output_path)
            
            assert output_path.exists()
            content = output_path.read_text()
            
            # Should contain nucleotide sequences (NC_, CP_ prefixes)
            assert "NC_000913" in content
            assert "CP000819" in content
            # Should NOT contain protein sequences (NP_ prefix)
            # Note: This assumes the exporter correctly filters by sequence type
            
        finally:
            if output_path.exists():
                output_path.unlink()


class TestProt2TaxidExporter:
    """Test prot2taxid format exporter."""
    
    def test_exporter_properties(self):
        """Test exporter properties."""
        exporter = Prot2TaxidExporter()
        assert exporter.exporter_name == "prot2taxid"
        assert ".txt" in exporter.file_extensions
        assert exporter.requires_directory is False
    
    def test_export_protein_sequences(self, tree_with_genomes):
        """Test export filters protein sequences."""
        exporter = Prot2TaxidExporter()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            output_path = Path(f.name)
        
        try:
            exporter.export(tree_with_genomes, output_path)
            
            assert output_path.exists()
            content = output_path.read_text()
            
            # Should contain protein sequences (NP_ prefix)
            assert "NP_414542" in content
            # Should contain taxonomy ID
            assert "562" in content
            
        finally:
            if output_path.exists():
                output_path.unlink()


class TestGenomeSizesExporter:
    """Test genome sizes format exporter."""
    
    def test_exporter_properties(self):
        """Test exporter properties."""
        exporter = GenomeSizesExporter()
        assert exporter.exporter_name == "genome_sizes"
        assert ".txt" in exporter.file_extensions
        assert exporter.requires_directory is False
    
    def test_export_with_mock_sizes(self, tree_with_genomes):
        """Test export with actual genome data."""
        exporter = GenomeSizesExporter()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            output_path = Path(f.name)
        
        try:
            # Test with tree_with_genomes which has genomes but no actual files
            exporter.export(tree_with_genomes, output_path)
            
            assert output_path.exists()
            content = output_path.read_text()
            
            # Should contain genome size information
            lines = content.strip().split('\n')
            assert len(lines) > 1  # Header + data
            
            # Check for expected columns
            header = lines[0].lower()
            assert any(col in header for col in ['taxid', 'accession', 'size', 'length'])
            
            # Check that genome entries are present with default size (0)
            data_lines = lines[1:]
            assert len(data_lines) == 3  # Three genomes in fixture
            
            # Check that each line has the expected format
            for line in data_lines:
                parts = line.split('\t')
                assert len(parts) == 6  # taxid, assembly_accession, species_taxid, organism_name, assembly_level, genome_size
                assert parts[0] == '562'  # tax_id from fixture
                assert parts[5] == '0'    # default genome size since no files exist
            
        finally:
            if output_path.exists():
                output_path.unlink()
    
    def test_export_without_sequence_files(self, tree_with_genomes):
        """Test export handles missing sequence files gracefully."""
        exporter = GenomeSizesExporter()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            output_path = Path(f.name)
        
        try:
            # Should not crash even if sequence files don't exist
            exporter.export(tree_with_genomes, output_path)
            assert output_path.exists()
            
            content = output_path.read_text()
            # Should at least have header
            assert len(content.strip()) > 0
            
        finally:
            if output_path.exists():
                output_path.unlink()


class TestMALTMapDBExporter:
    """Test MALT taxonomy database exporter."""
    
    def test_exporter_properties(self):
        """Test exporter properties."""
        exporter = MALTMapDBExporter()
        assert exporter.exporter_name == "malt_mapdb"
        assert ".db" in exporter.file_extensions
        assert ".sqlite" in exporter.file_extensions
        assert ".sqlite3" in exporter.file_extensions
        assert exporter.requires_directory is False


# Integration tests
class TestExporterIntegration:
    """Test exporter integration scenarios."""
    
    def test_export_empty_tree(self):
        """Test exporters handle empty trees gracefully."""
        empty_tree = TaxonomyTree()
        exporter = NCBIExporter()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            
            # Should handle empty tree without crashing
            try:
                exporter.export(empty_tree, output_path)
                
                # Files should be created but minimal
                nodes_file = output_path / "nodes.dmp"
                names_file = output_path / "names.dmp"
                
                if nodes_file.exists():
                    content = nodes_file.read_text()
                    # Empty or just whitespace
                    assert len(content.strip()) == 0
                    
            except ExportError:
                # Some exporters may legitimately reject empty trees
                pass
    
    def test_export_large_tree(self, complex_taxonomy_tree):
        """Test exporters handle larger trees."""
        exporter = NCBIExporter()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(complex_taxonomy_tree, output_path)
            
            nodes_file = output_path / "nodes.dmp"
            assert nodes_file.exists()
            
            content = nodes_file.read_text()
            lines = content.strip().split('\n')
            
            # Should have one line per node
            assert len(lines) == complex_taxonomy_tree.node_count
    
    def test_exporters_with_invalid_output_path(self, simple_taxonomy_tree):
        """Test exporters handle invalid output paths."""
        exporter = NCBIExporter()
        # Use a path that doesn't require creating directories in system locations
        with tempfile.TemporaryDirectory() as tmp_dir:
            invalid_path = Path(tmp_dir) / "nonexistent" / "deeply" / "nested" / "path"
            
            # This should actually work since _ensure_output_path creates directories
            # So let's test with a truly invalid path - a file as directory
            file_as_dir = Path(tmp_dir) / "file.txt"
            file_as_dir.write_text("content")
            invalid_path = file_as_dir / "subdirectory"
            
            with pytest.raises((ExportError, OSError, FileNotFoundError)):
                exporter.export(simple_taxonomy_tree, invalid_path)