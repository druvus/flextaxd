"""Unit tests for modern taxonomy exporters (Metabuli, MetaCache, MMseqs2)."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from flextaxd.core.models import TaxonomyTree, TaxonomyNode, TaxonomicRank, GenomeInfo
from flextaxd.core.exceptions import ExportError
from flextaxd.exporters.metabuli import MetabuliExporter
from flextaxd.exporters.metacache import MetaCacheExporter
from flextaxd.exporters.mmseqs2 import MMseqs2Exporter


class TestModernExportersBase:
    """Base class with common test utilities for modern exporters."""

    @staticmethod
    def create_test_tree():
        """Create a test taxonomy tree with genomes."""
        tree = TaxonomyTree()
        
        # Add root
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        tree.add_node(root)
        
        # Add Bacteria
        bacteria = TaxonomyNode(tax_id=2, name="Bacteria", rank=TaxonomicRank.SUPERKINGDOM, parent_id=1)
        tree.add_node(bacteria)
        
        # Add Escherichia
        escherichia = TaxonomyNode(tax_id=511145, name="Escherichia coli", rank=TaxonomicRank.SPECIES, parent_id=2)
        tree.add_node(escherichia)
        
        # Add genome
        genome = GenomeInfo(genome_id="GCA_000005825.2", tax_id=511145, assembly_accession="GCF_000005825.2")
        tree.add_genome(genome)
        
        return tree


class TestMetabuliExporter(TestModernExportersBase):
    """Test Metabuli format exporter."""

    def test_exporter_properties(self):
        """Test exporter basic properties."""
        exporter = MetabuliExporter()
        assert exporter.exporter_name == "metabuli"
        assert ".dmp" in exporter.file_extensions
        assert ".tsv" in exporter.file_extensions
        assert ".txt" in exporter.file_extensions
        assert exporter.requires_directory is True

    def test_export_basic_functionality(self):
        """Test basic export functionality."""
        exporter = MetabuliExporter()
        tree = self.create_test_tree()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            
            # Test export
            exporter.export(tree, output_path)
            
            # Check that required files were created
            assert (output_path / "names.dmp").exists()
            assert (output_path / "nodes.dmp").exists()

    def test_export_with_merged_file(self):
        """Test export with merged.dmp file."""
        exporter = MetabuliExporter()
        tree = self.create_test_tree()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            
            # Export with merged file
            exporter.export(tree, output_path, include_merged=True)
            
            # Check files
            assert (output_path / "names.dmp").exists()
            assert (output_path / "nodes.dmp").exists()
            assert (output_path / "merged.dmp").exists()

    def test_export_with_accession_mapping(self):
        """Test export with accession2taxid mapping."""
        exporter = MetabuliExporter()
        tree = self.create_test_tree()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            
            # Export with genome mapping
            exporter.export(tree, output_path, include_genomes=True)
            
            # Check files
            assert (output_path / "accession2taxid.txt").exists()
            
            # Verify mapping content
            with open(output_path / "accession2taxid.txt") as f:
                content = f.read()
                assert "GCA_000005825.2" in content
                assert "511145" in content

    def test_names_file_format(self):
        """Test names.dmp file format."""
        exporter = MetabuliExporter()
        tree = self.create_test_tree()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(tree, output_path)
            
            # Read and verify names.dmp format
            with open(output_path / "names.dmp") as f:
                lines = f.readlines()
                
            # Check NCBI format: tax_id | name | unique name | name class |
            assert len(lines) >= 2  # At least root and bacteria
            for line in lines:
                parts = line.strip().split("\t|\t")
                assert len(parts) >= 4
                assert parts[-1].endswith("|")

    def test_nodes_file_format(self):
        """Test nodes.dmp file format."""
        exporter = MetabuliExporter()
        tree = self.create_test_tree()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(tree, output_path)
            
            # Read and verify nodes.dmp format
            with open(output_path / "nodes.dmp") as f:
                lines = f.readlines()
                
            # Check NCBI format with 12 fields
            assert len(lines) >= 2
            for line in lines:
                parts = line.strip().split("\t|\t")
                assert len(parts) >= 12

    def test_validation_method(self):
        """Test export validation."""
        exporter = MetabuliExporter()
        tree = self.create_test_tree()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(tree, output_path)
            
            # Validate export
            validation_result = exporter.validate_export(output_path)
            
            assert validation_result["valid"] is True
            assert "names.dmp" in validation_result["files_created"]
            assert "nodes.dmp" in validation_result["files_created"]


class TestMetaCacheExporter(TestModernExportersBase):
    """Test MetaCache format exporter."""

    def test_exporter_properties(self):
        """Test exporter basic properties."""
        exporter = MetaCacheExporter()
        assert exporter.exporter_name == "metacache"
        assert ".dmp" in exporter.file_extensions
        assert ".txt" in exporter.file_extensions
        assert exporter.requires_directory is True

    def test_export_ncbi_taxonomy_format(self):
        """Test export in NCBI taxonomy format (default)."""
        exporter = MetaCacheExporter()
        tree = self.create_test_tree()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            
            # Export in NCBI format (default)
            exporter.export(tree, output_path)
            
            # Check files
            assert (output_path / "names.dmp").exists()
            assert (output_path / "nodes.dmp").exists()

    def test_export_assembly_summary_format(self):
        """Test export in assembly summary format."""
        exporter = MetaCacheExporter()
        tree = self.create_test_tree()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            
            # Export in assembly summary format
            exporter.export(tree, output_path, format_type="assembly_summary")
            
            # Check file
            assert (output_path / "assembly_summary.txt").exists()
            
            # Verify content structure
            with open(output_path / "assembly_summary.txt") as f:
                lines = f.readlines()
                assert len(lines) >= 2  # Header + data
                assert lines[0].startswith("#")

    def test_export_accession2taxid_format(self):
        """Test export in accession2taxid format."""
        exporter = MetaCacheExporter()
        tree = self.create_test_tree()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            
            # Export in accession2taxid format
            exporter.export(tree, output_path, format_type="accession2taxid")
            
            # Check file
            assert (output_path / "accession2taxid.txt").exists()
            
            # Verify standard format
            with open(output_path / "accession2taxid.txt") as f:
                lines = f.readlines()
                assert len(lines) >= 1
                assert lines[0].startswith("accession\taccession.version")

    def test_validation_different_formats(self):
        """Test validation for different export formats."""
        exporter = MetaCacheExporter()
        tree = self.create_test_tree()

        formats = ["ncbi_taxonomy", "assembly_summary", "accession2taxid"]
        
        for format_type in formats:
            with tempfile.TemporaryDirectory() as tmp_dir:
                output_path = Path(tmp_dir)
                exporter.export(tree, output_path, format_type=format_type)
                
                # Validate
                validation_result = exporter.validate_export(output_path, format_type)
                assert validation_result["valid"] is True
                assert len(validation_result["files_created"]) > 0


class TestMMseqs2Exporter(TestModernExportersBase):
    """Test MMseqs2 format exporter."""

    def test_exporter_properties(self):
        """Test exporter basic properties."""
        exporter = MMseqs2Exporter()
        assert exporter.exporter_name == "mmseqs2"
        assert ".dmp" in exporter.file_extensions
        assert ".tsv" in exporter.file_extensions
        assert exporter.requires_directory is True

    def test_export_basic_functionality(self):
        """Test basic export functionality."""
        exporter = MMseqs2Exporter()
        tree = self.create_test_tree()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            
            # Test export
            exporter.export(tree, output_path)
            
            # Check required files
            assert (output_path / "names.dmp").exists()
            assert (output_path / "nodes.dmp").exists()
            assert (output_path / "taxonomy_mapping.tsv").exists()

    def test_export_with_sequence_types(self):
        """Test export with different sequence types."""
        exporter = MMseqs2Exporter()
        tree = self.create_test_tree()

        sequence_types = ["protein", "nucleotide"]
        
        for seq_type in sequence_types:
            with tempfile.TemporaryDirectory() as tmp_dir:
                output_path = Path(tmp_dir)
                
                # Export with specific sequence type
                exporter.export(tree, output_path, sequence_type=seq_type)
                
                # Check files exist
                assert (output_path / "taxonomy_mapping.tsv").exists()
                
                # Verify sequence type in config if generated
                if (output_path / "mmseqs2_config.txt").exists():
                    with open(output_path / "mmseqs2_config.txt") as f:
                        content = f.read()
                        assert seq_type in content.lower()

    def test_lca_support(self):
        """Test LCA (Lowest Common Ancestor) support features."""
        exporter = MMseqs2Exporter()
        tree = self.create_test_tree()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            
            # Export with LCA support
            exporter.export(tree, output_path, enable_lca=True)
            
            # Check taxonomy mapping includes LCA hints
            with open(output_path / "taxonomy_mapping.tsv") as f:
                content = f.read()
                # Should have taxonomy mappings
                assert len(content.strip()) > 0

    def test_genetic_code_assignments(self):
        """Test genetic code assignments in export."""
        exporter = MMseqs2Exporter()
        tree = self.create_test_tree()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(tree, output_path)
            
            # Read nodes.dmp to check genetic code assignments
            with open(output_path / "nodes.dmp") as f:
                lines = f.readlines()
                
            # Verify genetic codes are assigned (position 6 in NCBI format)
            for line in lines:
                parts = line.strip().split("\t|\t")
                if len(parts) >= 7:
                    genetic_code = parts[6]
                    assert genetic_code.isdigit()
                    assert int(genetic_code) >= 1

    def test_validation_method(self):
        """Test export validation."""
        exporter = MMseqs2Exporter()
        tree = self.create_test_tree()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(tree, output_path)
            
            # Validate export
            validation_result = exporter.validate_export(output_path)
            
            assert validation_result["valid"] is True
            assert "names.dmp" in validation_result["files_created"]
            assert "nodes.dmp" in validation_result["files_created"]
            assert "taxonomy_mapping.tsv" in validation_result["files_created"]


class TestModernExportersIntegration:
    """Integration tests for modern exporters."""

    def test_all_exporters_create_compatible_formats(self):
        """Test that all modern exporters create compatible NCBI-style formats."""
        exporters = [
            MetabuliExporter(),
            MetaCacheExporter(),
            MMseqs2Exporter()
        ]
        
        tree = TestModernExportersBase.create_test_tree()
        
        for exporter in exporters:
            with tempfile.TemporaryDirectory() as tmp_dir:
                output_path = Path(tmp_dir)
                
                # Export with default settings
                exporter.export(tree, output_path)
                
                # All should create names.dmp and nodes.dmp
                assert (output_path / "names.dmp").exists()
                assert (output_path / "nodes.dmp").exists()
                
                # Verify NCBI format compatibility
                self._verify_ncbi_format_compatibility(output_path)

    def _verify_ncbi_format_compatibility(self, output_path: Path):
        """Verify that files follow NCBI format standards."""
        # Check names.dmp format
        with open(output_path / "names.dmp") as f:
            for line in f:
                line = line.strip()
                if line:
                    assert "\t|\t" in line
                    assert line.endswith("|")
        
        # Check nodes.dmp format
        with open(output_path / "nodes.dmp") as f:
            for line in f:
                line = line.strip()
                if line:
                    assert "\t|\t" in line
                    assert line.endswith("|")
                    # Should have at least tax_id, parent_id, rank
                    parts = line.split("\t|\t")
                    assert len(parts) >= 3

    def test_compression_support(self):
        """Test that modern exporters support compression."""
        exporters = [
            MetabuliExporter(),
            MetaCacheExporter(),
            MMseqs2Exporter()
        ]
        
        tree = TestModernExportersBase.create_test_tree()
        
        for exporter in exporters:
            with tempfile.TemporaryDirectory() as tmp_dir:
                output_path = Path(tmp_dir)
                
                # Export with compression
                exporter.export(tree, output_path, compress=True)
                
                # Should still create base files (compression happens after)
                assert (output_path / "names.dmp").exists()
                assert (output_path / "nodes.dmp").exists()

    def test_error_handling(self):
        """Test error handling in modern exporters."""
        exporters = [
            MetabuliExporter(),
            MetaCacheExporter(),
            MMseqs2Exporter()
        ]
        
        # Empty tree should be handled gracefully
        empty_tree = TaxonomyTree()
        
        for exporter in exporters:
            with tempfile.TemporaryDirectory() as tmp_dir:
                output_path = Path(tmp_dir)
                
                # Should either succeed with empty output or raise informative error
                try:
                    exporter.export(empty_tree, output_path)
                    # If it succeeds, files should exist but be minimal
                    assert (output_path / "names.dmp").exists()
                    assert (output_path / "nodes.dmp").exists()
                except ExportError as e:
                    # Informative error is acceptable
                    assert len(str(e)) > 0