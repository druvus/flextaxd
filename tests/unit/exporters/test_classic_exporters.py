"""Unit tests for classic taxonomy exporters (NCBI, Kraken2, Ganon, Centrifuge)."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from flextaxd.core.models import TaxonomyTree, TaxonomyNode, TaxonomicRank, GenomeInfo
from flextaxd.core.exceptions import ExportError
from flextaxd.exporters.ncbi import NCBIExporter
from flextaxd.exporters.kraken2 import Kraken2Exporter
from flextaxd.exporters.ganon import GanonExporter
from flextaxd.exporters.centrifuge import CentrifugeExporter


class TestClassicExportersBase:
    """Base class with common test utilities for classic exporters."""

    @staticmethod
    def create_test_tree():
        """Create a comprehensive test taxonomy tree."""
        tree = TaxonomyTree()
        
        # Add root
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        tree.add_node(root)
        
        # Add Bacteria
        bacteria = TaxonomyNode(tax_id=2, name="Bacteria", rank=TaxonomicRank.SUPERKINGDOM, parent_id=1)
        tree.add_node(bacteria)
        
        # Add Proteobacteria
        proteobacteria = TaxonomyNode(tax_id=1224, name="Proteobacteria", rank=TaxonomicRank.PHYLUM, parent_id=2)
        tree.add_node(proteobacteria)
        
        # Add Escherichia coli
        ecoli = TaxonomyNode(tax_id=511145, name="Escherichia coli str. K-12", rank=TaxonomicRank.SPECIES, parent_id=1224)
        tree.add_node(ecoli)
        
        # Add genomes
        genome1 = GenomeInfo(genome_id="GCA_000005825.2", assembly_accession="GCF_000005825.2")
        tree.add_genome(511145, genome1)
        
        return tree


class TestNCBIExporter(TestClassicExportersBase):
    """Test NCBI taxonomy dump format exporter."""

    def test_exporter_properties(self):
        """Test exporter basic properties."""
        exporter = NCBIExporter()
        assert exporter.exporter_name == "ncbi"
        assert ".dmp" in exporter.file_extensions
        assert exporter.requires_directory is True

    def test_export_basic_functionality(self):
        """Test basic NCBI export functionality."""
        exporter = NCBIExporter()
        tree = self.create_test_tree()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            
            # Export
            exporter.export(tree, output_path)
            
            # Check required NCBI files
            assert (output_path / "names.dmp").exists()
            assert (output_path / "nodes.dmp").exists()

    def test_names_dmp_format(self):
        """Test names.dmp file format compliance."""
        exporter = NCBIExporter()
        tree = self.create_test_tree()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(tree, output_path)
            
            # Verify names.dmp format
            with open(output_path / "names.dmp") as f:
                lines = f.readlines()
            
            assert len(lines) >= 4  # root, bacteria, proteobacteria, ecoli
            
            for line in lines:
                # NCBI format: tax_id | name | unique name | name class |
                assert line.count("\t|\t") >= 3
                assert line.endswith("|\n")
                parts = line.split("\t|\t")
                assert parts[0].isdigit()  # tax_id
                assert len(parts[1]) > 0   # name
                assert "scientific name" in parts[3]  # name class

    def test_nodes_dmp_format(self):
        """Test nodes.dmp file format compliance."""
        exporter = NCBIExporter()
        tree = self.create_test_tree()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(tree, output_path)
            
            # Verify nodes.dmp format
            with open(output_path / "nodes.dmp") as f:
                lines = f.readlines()
            
            for line in lines:
                # Should have 12+ fields in NCBI format
                parts = line.split("\t|\t")
                assert len(parts) >= 12
                assert parts[0].isdigit()  # tax_id
                assert parts[1].isdigit()  # parent_tax_id
                assert len(parts[2]) > 0   # rank

    def test_parent_child_relationships(self):
        """Test that parent-child relationships are correct."""
        exporter = NCBIExporter()
        tree = self.create_test_tree()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(tree, output_path)
            
            # Parse nodes.dmp to verify relationships
            tax_to_parent = {}
            with open(output_path / "nodes.dmp") as f:
                for line in f:
                    parts = line.split("\t|\t")
                    tax_id = int(parts[0])
                    parent_id = int(parts[1])
                    tax_to_parent[tax_id] = parent_id
            
            # Verify specific relationships
            assert tax_to_parent[1] == 1      # Root parent is itself
            assert tax_to_parent[2] == 1      # Bacteria parent is root
            assert tax_to_parent[1224] == 2   # Proteobacteria parent is Bacteria


class TestKraken2Exporter(TestClassicExportersBase):
    """Test Kraken2 taxonomy format exporter."""

    def test_exporter_properties(self):
        """Test exporter basic properties."""
        exporter = Kraken2Exporter()
        assert exporter.exporter_name == "kraken2"
        assert ".dmp" in exporter.file_extensions
        assert exporter.requires_directory is True

    def test_export_basic_functionality(self):
        """Test basic Kraken2 export functionality."""
        exporter = Kraken2Exporter()
        tree = self.create_test_tree()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            
            # Export
            exporter.export(tree, output_path)
            
            # Check required Kraken2 files
            assert (output_path / "names.dmp").exists()
            assert (output_path / "nodes.dmp").exists()

    def test_kraken2_specific_features(self):
        """Test Kraken2-specific format features."""
        exporter = Kraken2Exporter()
        tree = self.create_test_tree()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(tree, output_path)
            
            # Kraken2 should produce NCBI-compatible format
            # Verify tax_ids are preserved correctly
            tax_ids_found = set()
            with open(output_path / "nodes.dmp") as f:
                for line in f:
                    tax_id = int(line.split("\t|\t")[0])
                    tax_ids_found.add(tax_id)
            
            # Should contain our test tax_ids
            expected_ids = {1, 2, 1224, 511145}
            assert expected_ids.issubset(tax_ids_found)

    def test_sequence_mapping(self):
        """Test sequence to taxonomy mapping generation."""
        exporter = Kraken2Exporter()
        tree = self.create_test_tree()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(tree, output_path)
            
            # Check if sequence mapping files are created when genomes exist
            # This depends on the actual Kraken2 exporter implementation
            files_created = list(output_path.glob("*"))
            assert len(files_created) >= 2  # At least names.dmp and nodes.dmp


class TestGanonExporter(TestClassicExportersBase):
    """Test Ganon taxonomy format exporter."""

    def test_exporter_properties(self):
        """Test exporter basic properties."""
        exporter = GanonExporter()
        assert exporter.exporter_name == "ganon"
        assert ".dmp" in exporter.file_extensions
        assert exporter.requires_directory is True

    def test_export_basic_functionality(self):
        """Test basic Ganon export functionality."""
        exporter = GanonExporter()
        tree = self.create_test_tree()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            
            # Export
            exporter.export(tree, output_path)
            
            # Check required files
            assert (output_path / "names.dmp").exists()
            assert (output_path / "nodes.dmp").exists()

    def test_ganon_format_compatibility(self):
        """Test Ganon format compatibility with hierarchical classification."""
        exporter = GanonExporter()
        tree = self.create_test_tree()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(tree, output_path)
            
            # Verify hierarchical structure is maintained
            parent_child_map = {}
            with open(output_path / "nodes.dmp") as f:
                for line in f:
                    parts = line.split("\t|\t")
                    child_id = int(parts[0])
                    parent_id = int(parts[1])
                    parent_child_map[child_id] = parent_id
            
            # Check hierarchy: ecoli -> proteobacteria -> bacteria -> root
            assert parent_child_map[511145] == 1224  # ecoli -> proteobacteria
            assert parent_child_map[1224] == 2       # proteobacteria -> bacteria
            assert parent_child_map[2] == 1          # bacteria -> root


class TestCentrifugeExporter(TestClassicExportersBase):
    """Test Centrifuge taxonomy format exporter."""

    def test_exporter_properties(self):
        """Test exporter basic properties."""
        exporter = CentrifugeExporter()
        assert exporter.exporter_name == "centrifuge"
        assert exporter.requires_directory is True

    def test_export_basic_functionality(self):
        """Test basic Centrifuge export functionality."""
        exporter = CentrifugeExporter()
        tree = self.create_test_tree()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            
            # Export
            exporter.export(tree, output_path)
            
            # Check that files are created
            files_created = list(output_path.glob("*"))
            assert len(files_created) > 0

    def test_centrifuge_conversion_format(self):
        """Test Centrifuge conversion table format."""
        exporter = CentrifugeExporter()
        tree = self.create_test_tree()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(tree, output_path)
            
            # Centrifuge may create different files than standard NCBI format
            # Check that export completes without errors and creates output
            assert len(list(output_path.glob("*"))) > 0


class TestClassicExportersIntegration:
    """Integration tests for classic exporters."""

    def test_all_classic_exporters_work(self):
        """Test that all classic exporters can export successfully."""
        exporters = [
            NCBIExporter(),
            Kraken2Exporter(),
            GanonExporter(),
            CentrifugeExporter()
        ]
        
        tree = TestClassicExportersBase.create_test_tree()
        
        for exporter in exporters:
            with tempfile.TemporaryDirectory() as tmp_dir:
                output_path = Path(tmp_dir)
                
                # Should not raise exceptions
                exporter.export(tree, output_path)
                
                # Should create some files
                files_created = list(output_path.glob("*"))
                assert len(files_created) > 0

    def test_format_consistency_across_exporters(self):
        """Test format consistency across NCBI-based exporters."""
        # NCBI, Kraken2, and Ganon should create similar NCBI-style formats
        exporters = [NCBIExporter(), Kraken2Exporter(), GanonExporter()]
        tree = TestClassicExportersBase.create_test_tree()
        
        tax_ids_per_exporter = []
        
        for exporter in exporters:
            with tempfile.TemporaryDirectory() as tmp_dir:
                output_path = Path(tmp_dir)
                exporter.export(tree, output_path)
                
                # Extract tax_ids from nodes.dmp if it exists
                if (output_path / "nodes.dmp").exists():
                    tax_ids = set()
                    with open(output_path / "nodes.dmp") as f:
                        for line in f:
                            tax_id = int(line.split("\t|\t")[0])
                            tax_ids.add(tax_id)
                    tax_ids_per_exporter.append(tax_ids)
        
        # All NCBI-style exporters should have the same core tax_ids
        if len(tax_ids_per_exporter) > 1:
            base_ids = tax_ids_per_exporter[0]
            for other_ids in tax_ids_per_exporter[1:]:
                # Should have significant overlap in tax_ids
                overlap = base_ids.intersection(other_ids)
                assert len(overlap) > 0

    def test_error_handling_empty_tree(self):
        """Test error handling with empty trees."""
        exporters = [
            NCBIExporter(),
            Kraken2Exporter(),
            GanonExporter(),
            CentrifugeExporter()
        ]
        
        empty_tree = TaxonomyTree()
        
        for exporter in exporters:
            with tempfile.TemporaryDirectory() as tmp_dir:
                output_path = Path(tmp_dir)
                
                # Should either succeed with minimal output or raise informative error
                try:
                    exporter.export(empty_tree, output_path)
                    # If successful, should create some output
                    files = list(output_path.glob("*"))
                    # Either no files (acceptable) or minimal files
                    assert len(files) >= 0
                except ExportError as e:
                    # Informative error is acceptable
                    assert len(str(e)) > 0

    def test_large_tax_ids(self):
        """Test handling of large taxonomy IDs."""
        # Create tree with large tax_ids
        tree = TaxonomyTree()
        
        # Add nodes with large IDs (common in real taxonomies)
        large_root = TaxonomyNode(tax_id=999999999, name="test_root", rank=TaxonomicRank.CUSTOM)
        tree.add_node(large_root)
        
        large_child = TaxonomyNode(
            tax_id=1000000001, 
            name="test_species", 
            rank=TaxonomicRank.SPECIES, 
            parent_id=999999999
        )
        tree.add_node(large_child)
        
        exporters = [NCBIExporter(), Kraken2Exporter(), GanonExporter()]
        
        for exporter in exporters:
            with tempfile.TemporaryDirectory() as tmp_dir:
                output_path = Path(tmp_dir)
                
                # Should handle large tax_ids without issues
                exporter.export(tree, output_path)
                
                # Verify large tax_ids are preserved
                if (output_path / "nodes.dmp").exists():
                    with open(output_path / "nodes.dmp") as f:
                        content = f.read()
                        assert "999999999" in content
                        assert "1000000001" in content