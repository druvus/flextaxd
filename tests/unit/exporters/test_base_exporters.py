"""Unit tests for base exporter classes and common functionality."""

import pytest
import tempfile
from pathlib import Path
from abc import ABC, abstractmethod
from unittest.mock import Mock, patch

from flextaxd.core.models import TaxonomyTree, TaxonomyNode, TaxonomicRank, GenomeInfo
from flextaxd.core.exceptions import ExportError, ValidationError
from flextaxd.exporters.base import TaxonomyExporter, FileBasedExporter, DirectoryBasedExporter


class TestTaxonomyExporterBase:
    """Test base TaxonomyExporter abstract class."""

    def test_abstract_exporter_cannot_be_instantiated(self):
        """Test that abstract base class cannot be instantiated."""
        with pytest.raises(TypeError):
            TaxonomyExporter()

    def test_abstract_methods_exist(self):
        """Test that required abstract methods are defined."""
        abstract_methods = TaxonomyExporter.__abstractmethods__
        
        expected_methods = {"export", "exporter_name", "file_extensions"}
        assert expected_methods.issubset(abstract_methods)

    def test_subclass_requires_abstract_methods(self):
        """Test that subclass must implement abstract methods."""
        
        # Incomplete subclass should fail
        with pytest.raises(TypeError):
            class IncompleteExporter(TaxonomyExporter):
                pass
            
            IncompleteExporter()

    def test_concrete_subclass_works(self):
        """Test that complete concrete subclass can be instantiated."""
        
        class ConcreteExporter(TaxonomyExporter):
            @property
            def exporter_name(self):
                return "test"
            
            @property
            def file_extensions(self):
                return [".test"]
            
            @property
            def requires_directory(self):
                return False
            
            def export(self, tree, output_path, **kwargs):
                pass
        
        # Should not raise exception
        exporter = ConcreteExporter()
        assert exporter.exporter_name == "test"
        assert exporter.file_extensions == [".test"]


class TestFileBasedExporter:
    """Test FileBasedExporter base class."""

    def create_test_file_exporter(self):
        """Create a concrete file-based exporter for testing."""
        
        class TestFileExporter(FileBasedExporter):
            @property
            def exporter_name(self):
                return "test_file"
            
            @property
            def file_extensions(self):
                return [".txt"]
            
            def export(self, tree, output_path, **kwargs):
                # Simple test export - write tree info to file
                with open(output_path, 'w') as f:
                    f.write(f"Tree with {tree.node_count} nodes\n")
        
        return TestFileExporter()

    def test_file_exporter_properties(self):
        """Test file-based exporter properties."""
        exporter = self.create_test_file_exporter()
        
        assert exporter.requires_directory is False
        assert exporter.exporter_name == "test_file"
        assert ".txt" in exporter.file_extensions

    def test_file_export_basic_functionality(self):
        """Test basic file export functionality."""
        exporter = self.create_test_file_exporter()
        
        # Create test tree
        tree = TaxonomyTree()
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        tree.add_node(root)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            output_file = Path(f.name)

        try:
            # Export to file
            exporter.export(tree, output_file)
            
            # Check file was created and has content
            assert output_file.exists()
            with open(output_file) as f:
                content = f.read()
                assert "Tree with 1 nodes" in content
                
        finally:
            output_file.unlink()

    def test_file_validation_methods(self):
        """Test file validation utility methods."""
        exporter = self.create_test_file_exporter()
        
        # Test with existing file
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("test content")
            f.flush()
            test_file = Path(f.name)

        try:
            # Should not raise exception for valid file
            exporter._validate_file(test_file)
            
        finally:
            test_file.unlink()
        
        # Test with non-existent file
        nonexistent = Path("/nonexistent/path/file.txt")
        with pytest.raises((ValidationError, FileNotFoundError)):
            exporter._validate_file(nonexistent)

    def test_ensure_output_file(self):
        """Test output file path validation."""
        exporter = self.create_test_file_exporter()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Valid file path
            valid_path = Path(tmp_dir) / "output.txt"
            exporter._ensure_output_path(valid_path)  # Should not raise
            
            # Directory as file path should raise error
            with pytest.raises((ValidationError, ExportError, IsADirectoryError)):
                exporter._ensure_output_path(Path(tmp_dir))


class TestDirectoryBasedExporter:
    """Test DirectoryBasedExporter base class."""

    def create_test_directory_exporter(self):
        """Create a concrete directory-based exporter for testing."""
        
        class TestDirExporter(DirectoryBasedExporter):
            @property
            def exporter_name(self):
                return "test_dir"
            
            @property
            def file_extensions(self):
                return [".dmp", ".txt"]
            
            def export(self, tree, output_path, **kwargs):
                # Simple test export - create multiple files
                self._ensure_output_path(output_path)
                (output_path / "names.dmp").write_text("names data")
                (output_path / "nodes.dmp").write_text("nodes data")
                (output_path / "info.txt").write_text(f"Tree: {tree.node_count} nodes")
        
        return TestDirExporter()

    def test_directory_exporter_properties(self):
        """Test directory-based exporter properties."""
        exporter = self.create_test_directory_exporter()
        
        assert exporter.requires_directory is True
        assert exporter.exporter_name == "test_dir"
        assert ".dmp" in exporter.file_extensions
        assert ".txt" in exporter.file_extensions

    def test_directory_export_basic_functionality(self):
        """Test basic directory export functionality."""
        exporter = self.create_test_directory_exporter()
        
        # Create test tree
        tree = TaxonomyTree()
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        tree.add_node(root)

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "output"
            
            # Export to directory
            exporter.export(tree, output_dir)
            
            # Check directory and files were created
            assert output_dir.exists()
            assert output_dir.is_dir()
            
            assert (output_dir / "names.dmp").exists()
            assert (output_dir / "nodes.dmp").exists()
            assert (output_dir / "info.txt").exists()
            
            # Check content
            with open(output_dir / "info.txt") as f:
                content = f.read()
                assert "Tree: 1 nodes" in content

    def test_directory_creation(self):
        """Test automatic directory creation."""
        exporter = self.create_test_directory_exporter()
        tree = TaxonomyTree()
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        tree.add_node(root)

        with tempfile.TemporaryDirectory() as tmp_dir:
            # Non-existent nested directory
            output_dir = Path(tmp_dir) / "nested" / "output"
            assert not output_dir.exists()
            
            # Export should create directory
            exporter.export(tree, output_dir)
            
            # Directory should now exist
            assert output_dir.exists()
            assert output_dir.is_dir()

    def test_ensure_output_directory(self):
        """Test output directory validation and creation."""
        exporter = self.create_test_directory_exporter()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Valid directory path (non-existent)
            valid_path = Path(tmp_dir) / "new_dir"
            exporter._ensure_output_path(valid_path)
            assert valid_path.exists()
            assert valid_path.is_dir()
            
            # Existing directory should work
            exporter._ensure_output_path(valid_path)  # Should not raise
            
            # File as directory path should raise error
            file_path = Path(tmp_dir) / "file.txt"
            file_path.write_text("test")
            
            with pytest.raises((ValidationError, ExportError, NotADirectoryError, FileExistsError)):
                exporter._ensure_output_path(file_path)


class TestExporterCommonFunctionality:
    """Test common functionality across all exporters."""

    def create_comprehensive_test_tree(self):
        """Create a comprehensive tree for testing common functionality."""
        tree = TaxonomyTree()
        
        # Root
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        tree.add_node(root)
        
        # Domain
        bacteria = TaxonomyNode(
            tax_id=2, 
            name="Bacteria", 
            rank=TaxonomicRank.SUPERKINGDOM, 
            parent_id=1
        )
        tree.add_node(bacteria)
        
        # Species with special characters
        special_species = TaxonomyNode(
            tax_id=12345,
            name="Species with | pipe & ampersand",
            rank=TaxonomicRank.SPECIES,
            parent_id=2
        )
        tree.add_node(special_species)
        
        # Add genome with special characters
        genome = GenomeInfo(
            genome_id="GCA_123456.1|special",
            tax_id=12345,
            assembly_accession="GCF_123456.1",
            sequence_length=1000000
        )
        tree.add_genome(genome)
        
        return tree

    def test_tree_validation(self):
        """Test tree validation functionality."""
        
        class TestExporter(FileBasedExporter):
            @property
            def exporter_name(self):
                return "test"
            
            @property  
            def file_extensions(self):
                return [".txt"]
            
            def export(self, tree, output_path, **kwargs):
                self._validate_tree(tree)
                output_path.write_text("validated")
        
        exporter = TestExporter()
        
        # Valid tree should pass
        valid_tree = self.create_comprehensive_test_tree()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            output_file = Path(f.name)
        
        try:
            # Should not raise exception
            exporter.export(valid_tree, output_file)
            assert output_file.read_text() == "validated"
            
        finally:
            output_file.unlink()
        
        # Invalid tree (None) should fail
        with pytest.raises((ValidationError, AttributeError)):
            exporter.export(None, output_file)

    def test_special_character_handling(self):
        """Test handling of special characters in names and IDs."""
        
        class TestExporter(FileBasedExporter):
            @property
            def exporter_name(self):
                return "test"
            
            @property
            def file_extensions(self):
                return [".txt"]
            
            def export(self, tree, output_path, **kwargs):
                # Write names to file to test character handling
                with open(output_path, 'w') as f:
                    for node in tree:
                        f.write(f"{node.tax_id}: {node.name}\n")
        
        exporter = TestExporter()
        tree = self.create_comprehensive_test_tree()

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            output_file = Path(f.name)

        try:
            # Should handle special characters without crashing
            exporter.export(tree, output_file)
            
            # Check content
            content = output_file.read_text()
            assert "Species with | pipe & ampersand" in content
            
        finally:
            output_file.unlink()

    def test_empty_tree_handling(self):
        """Test handling of empty taxonomy trees."""
        
        class TestExporter(FileBasedExporter):
            @property
            def exporter_name(self):
                return "test"
            
            @property
            def file_extensions(self):
                return [".txt"]
            
            def export(self, tree, output_path, **kwargs):
                with open(output_path, 'w') as f:
                    f.write(f"Nodes: {tree.node_count}\n")
                    f.write(f"Genomes: {tree.genome_count}\n")
        
        exporter = TestExporter()
        empty_tree = TaxonomyTree()

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            output_file = Path(f.name)

        try:
            # Should handle empty tree gracefully
            exporter.export(empty_tree, output_file)
            
            content = output_file.read_text()
            assert "Nodes: 0" in content
            assert "Genomes: 0" in content
            
        finally:
            output_file.unlink()

    def test_large_tree_handling(self):
        """Test handling of trees with many nodes."""
        
        class TestExporter(FileBasedExporter):
            @property
            def exporter_name(self):
                return "test"
            
            @property
            def file_extensions(self):
                return [".txt"]
            
            def export(self, tree, output_path, **kwargs):
                with open(output_path, 'w') as f:
                    f.write(f"Tree size: {tree.node_count}\n")
        
        exporter = TestExporter()
        
        # Create large tree
        large_tree = TaxonomyTree()
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        large_tree.add_node(root)
        
        # Add many nodes
        for i in range(2, 1002):  # 1000 additional nodes
            node = TaxonomyNode(
                tax_id=i,
                name=f"node_{i}",
                rank=TaxonomicRank.SPECIES,
                parent_id=1
            )
            large_tree.add_node(node)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            output_file = Path(f.name)

        try:
            # Should handle large tree without issues
            exporter.export(large_tree, output_file)
            
            content = output_file.read_text()
            assert "Tree size: 1001" in content
            
        finally:
            output_file.unlink()


class TestExporterErrorHandling:
    """Test error handling in exporters."""

    def test_invalid_output_path_handling(self):
        """Test handling of invalid output paths."""
        
        class TestExporter(FileBasedExporter):
            @property
            def exporter_name(self):
                return "test"
            
            @property
            def file_extensions(self):
                return [".txt"]
            
            def export(self, tree, output_path, **kwargs):
                self._ensure_output_path(output_path)
        
        exporter = TestExporter()
        tree = TaxonomyTree()
        
        # Invalid paths should raise appropriate errors
        invalid_paths = [
            Path("/nonexistent/deeply/nested/path/file.txt"),
            Path("/root/restricted.txt"),  # Permission denied on most systems
        ]
        
        for invalid_path in invalid_paths:
            with pytest.raises((ValidationError, ExportError, PermissionError, FileNotFoundError, OSError)):
                exporter.export(tree, invalid_path)

    def test_export_interruption_handling(self):
        """Test handling of export interruption/cancellation."""
        
        class TestExporter(FileBasedExporter):
            @property
            def exporter_name(self):
                return "test"
            
            @property
            def file_extensions(self):
                return [".txt"]
            
            def export(self, tree, output_path, **kwargs):
                # Simulate interruption during export
                with open(output_path, 'w') as f:
                    f.write("Starting export...\n")
                    # Simulate interruption
                    raise KeyboardInterrupt("Export interrupted")
        
        exporter = TestExporter()
        tree = TaxonomyTree()

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            output_file = Path(f.name)

        try:
            # Should propagate interruption
            with pytest.raises(KeyboardInterrupt):
                exporter.export(tree, output_file)
                
        finally:
            if output_file.exists():
                output_file.unlink()

    def test_disk_space_error_simulation(self):
        """Test handling of disk space errors."""
        
        class TestExporter(FileBasedExporter):
            @property
            def exporter_name(self):
                return "test"
            
            @property
            def file_extensions(self):
                return [".txt"]
            
            def export(self, tree, output_path, **kwargs):
                # Simulate disk space error
                raise OSError("No space left on device")
        
        exporter = TestExporter()
        tree = TaxonomyTree()

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            output_file = Path(f.name)

        try:
            # Should propagate OS errors
            with pytest.raises(OSError):
                exporter.export(tree, output_file)
                
        finally:
            if output_file.exists():
                output_file.unlink()