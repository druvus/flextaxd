"""Comprehensive unit tests for ExportCommand."""

import pytest
import argparse
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from flextaxd.cli.commands.export import ExportCommand
from flextaxd.core.exceptions import ValidationError
from flextaxd.core.models import TaxonomyTree

from ....fixtures.cli.conftest import *
from ....fixtures.cli.mock_data import MockData, CLITestHelper


class TestExportCommand:
    """Test ExportCommand basic functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = ExportCommand()
    
    def test_initialization(self):
        """Test command initialization."""
        assert isinstance(self.command, ExportCommand)
        assert hasattr(self.command, 'logger')
    
    def test_register_parser(self):
        """Test parser registration."""
        mock_subparsers = Mock()
        mock_parser = Mock()
        mock_subparsers.add_parser.return_value = mock_parser
        
        parser = ExportCommand.register_parser(mock_subparsers)
        
        # Verify parser was created
        mock_subparsers.add_parser.assert_called_once()
        call_args = mock_subparsers.add_parser.call_args
        assert call_args[0][0] == "export"
        
        # Verify mutually exclusive groups for --classifier vs --format
        assert mock_parser.add_mutually_exclusive_group.called
        assert mock_parser.add_argument_group.called
    
    @patch('flextaxd.cli.commands.export.SQLiteTaxonomyRepository')
    def test_execute_classifier_export(self, mock_repo_class, sample_taxonomy_tree):
        """Test successful classifier export (directory output)."""
        # Setup repository mock
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            classifier="kraken2", 
            output="/test/kraken2_db/",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_validate_output_directory'), \
             patch('flextaxd.cli.commands.export.get_exporter') as mock_get_exporter:
            
            # Setup exporter mock
            mock_exporter = Mock()
            mock_get_exporter.return_value = mock_exporter
            
            result = self.command.execute(args)
            
            assert result == 0
            mock_get_exporter.assert_called_with("kraken2")
            mock_exporter.export.assert_called_once()
    
    @patch('flextaxd.cli.commands.export.SQLiteTaxonomyRepository')
    def test_execute_format_export(self, mock_repo_class, sample_taxonomy_tree):
        """Test successful format export (single file output)."""
        # Setup repository mock
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            format="tsv",
            output="/test/taxonomy.tsv",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('pathlib.Path') as mock_path, \
             patch('flextaxd.cli.commands.export.get_exporter') as mock_get_exporter:
            
            # Setup path mock for output file
            mock_path_obj = Mock()
            mock_path_obj.parent.mkdir = Mock()
            mock_path.return_value = mock_path_obj
            
            # Setup exporter mock  
            mock_exporter = Mock()
            mock_get_exporter.return_value = mock_exporter
            
            result = self.command.execute(args)
            
            assert result == 0
            mock_get_exporter.assert_called_with("tsv")
            mock_exporter.export.assert_called_once()
            # Should create parent directory for output file
            mock_path_obj.parent.mkdir.assert_called_with(parents=True, exist_ok=True)
    
    @patch('flextaxd.cli.commands.export.SQLiteTaxonomyRepository')
    def test_execute_legacy_format(self, mock_repo_class, sample_taxonomy_tree):
        """Test legacy format export (backward compatibility)."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            legacy_format="ncbi",
            output="/test/ncbi_dump/",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_validate_output_directory'), \
             patch('flextaxd.cli.commands.export.get_exporter') as mock_get_exporter:
            
            mock_exporter = Mock()
            mock_get_exporter.return_value = mock_exporter
            
            result = self.command.execute(args)
            
            assert result == 0
            # Legacy format should be treated as classifier
            mock_get_exporter.assert_called_with("ncbi")
    
    def test_execute_no_export_option(self):
        """Test execution with no export option specified."""
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            output="/test/output/",
            verbose=False
            # No classifier, format, or legacy_format specified
        )
        
        result = self.command.execute(args)
        
        # Should fail with validation error
        assert result != 0
    
    def test_execute_multiple_export_options(self):
        """Test execution with multiple export options (should be prevented by argparse)."""
        # This test verifies the mutually exclusive group setup
        # In practice, argparse would prevent this, but we test the logic
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            classifier="kraken2",
            format="tsv",  # Both classifier and format specified
            output="/test/output/",
            verbose=False
        )
        
        # Command should handle this gracefully (prefer classifier over format)
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_validate_output_directory'), \
             patch('flextaxd.cli.commands.export.SQLiteTaxonomyRepository') as mock_repo_class, \
             patch('flextaxd.cli.commands.export.get_exporter') as mock_get_exporter:
            
            mock_repo = Mock()
            mock_repo_class.return_value.__enter__.return_value = mock_repo
            mock_exporter = Mock()
            mock_get_exporter.return_value = mock_exporter
            
            result = self.command.execute(args)
            
            # Should prefer classifier over format
            assert result == 0
            mock_get_exporter.assert_called_with("kraken2")


class TestExportCommandClassifiers:
    """Test ExportCommand with different classifier options."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = ExportCommand()
    
    @pytest.mark.parametrize("classifier", [
        "ncbi", "kraken2", "diamond", "ganon", "ganon2", "kaiju", "malt", 
        "melon", "sourmash", "sylph", "metabuli", "metacache", "mmseqs2", "centrifuge"
    ])
    @patch('flextaxd.cli.commands.export.SQLiteTaxonomyRepository')
    @patch('flextaxd.cli.commands.export.get_exporter')
    def test_classifier_export_variants(self, mock_get_exporter, mock_repo_class, classifier, sample_taxonomy_tree):
        """Test export with different classifiers."""
        # Setup mocks
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        mock_exporter = Mock()
        mock_get_exporter.return_value = mock_exporter
        
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            classifier=classifier,
            output=f"/test/{classifier}_db/",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_validate_output_directory'):
            
            result = self.command.execute(args)
            
            assert result == 0
            mock_get_exporter.assert_called_with(classifier)
            mock_exporter.export.assert_called_once()
    
    @patch('flextaxd.cli.commands.export.get_exporter')
    def test_invalid_classifier(self, mock_get_exporter):
        """Test export with invalid classifier."""
        mock_get_exporter.side_effect = ValueError("Unknown classifier: invalid")
        
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd", 
            classifier="invalid",
            output="/test/output/",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_validate_output_directory'), \
             patch('flextaxd.cli.commands.export.SQLiteTaxonomyRepository'):
            
            result = self.command.execute(args)
            assert result != 0


class TestExportCommandFormats:
    """Test ExportCommand with different format options."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = ExportCommand()
    
    @pytest.mark.parametrize("format_name,extension", [
        ("tsv", ".tsv"),
        ("json", ".json"), 
        ("newick", ".nwk"),
        ("accession2taxid", ".txt"),
        ("nucl2taxid", ".txt"),
        ("prot2taxid", ".txt"),
        ("genome_sizes", ".txt"),
        ("malt_mapdb", ".db"),
        ("kmcp", ".txt")
    ])
    @patch('flextaxd.cli.commands.export.SQLiteTaxonomyRepository')
    @patch('flextaxd.cli.commands.export.get_exporter')
    def test_format_export_variants(self, mock_get_exporter, mock_repo_class, format_name, extension, sample_taxonomy_tree):
        """Test export with different single-file formats."""
        # Setup mocks
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        mock_exporter = Mock()
        mock_get_exporter.return_value = mock_exporter
        
        output_file = f"/test/output{extension}"
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            format=format_name,
            output=output_file,
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('pathlib.Path') as mock_path:
            
            mock_path_obj = Mock()
            mock_path_obj.parent.mkdir = Mock()
            mock_path.return_value = mock_path_obj
            
            result = self.command.execute(args)
            
            assert result == 0
            mock_get_exporter.assert_called_with(format_name)
            mock_exporter.export.assert_called_once()
    
    @patch('flextaxd.cli.commands.export.get_exporter')
    def test_invalid_format(self, mock_get_exporter):
        """Test export with invalid format."""
        mock_get_exporter.side_effect = ValueError("Unknown format: invalid")
        
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            format="invalid", 
            output="/test/output.txt",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('pathlib.Path'), \
             patch('flextaxd.cli.commands.export.SQLiteTaxonomyRepository'):
            
            result = self.command.execute(args)
            assert result != 0


class TestExportCommandValidation:
    """Test ExportCommand input validation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = ExportCommand()
    
    def test_validate_missing_database(self):
        """Test validation with missing database."""
        args = CLITestHelper.create_mock_args(
            database="/nonexistent/db.ftd",
            classifier="kraken2",
            output="/test/output/",
            verbose=False
        )
        
        with patch('pathlib.Path') as mock_path:
            mock_path_obj = Mock()
            mock_path_obj.exists.return_value = False
            mock_path.return_value = mock_path_obj
            
            result = self.command.execute(args)
            assert result != 0
    
    def test_validate_invalid_database(self):
        """Test validation with invalid database file."""
        args = CLITestHelper.create_mock_args(
            database="/test/directory",  # Directory instead of file
            classifier="kraken2", 
            output="/test/output/",
            verbose=False
        )
        
        with patch('pathlib.Path') as mock_path:
            mock_path_obj = Mock()
            mock_path_obj.exists.return_value = True
            mock_path_obj.is_file.return_value = False
            mock_path.return_value = mock_path_obj
            
            result = self.command.execute(args)
            assert result != 0
    
    def test_validate_output_path_creation(self):
        """Test output path validation and creation."""
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            classifier="kraken2",
            output="/test/new/output/",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('pathlib.Path') as mock_path, \
             patch('flextaxd.cli.commands.export.SQLiteTaxonomyRepository') as mock_repo_class, \
             patch('flextaxd.cli.commands.export.get_exporter'):
            
            # Setup for directory creation
            mock_path_obj = Mock()
            mock_path_obj.exists.return_value = False
            mock_path_obj.mkdir = Mock()
            mock_path.return_value = mock_path_obj
            
            mock_repo = Mock()
            mock_repo_class.return_value.__enter__.return_value = mock_repo
            
            result = self.command.execute(args)
            
            # Should create output directory
            mock_path_obj.mkdir.assert_called_with(parents=True, exist_ok=True)
    
    def test_validate_output_permission_error(self):
        """Test handling of output permission errors."""
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            classifier="kraken2",
            output="/root/forbidden/",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('pathlib.Path') as mock_path:
            
            mock_path_obj = Mock()
            mock_path_obj.exists.return_value = False
            mock_path_obj.mkdir.side_effect = PermissionError("Permission denied")
            mock_path.return_value = mock_path_obj
            
            result = self.command.execute(args)
            assert result != 0


class TestExportCommandErrorHandling:
    """Test ExportCommand error handling."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = ExportCommand()
    
    @patch('flextaxd.cli.commands.export.SQLiteTaxonomyRepository')
    def test_database_load_error(self, mock_repo_class):
        """Test handling of database load errors."""
        mock_repo = Mock()
        mock_repo.load_tree.side_effect = Exception("Database corrupted")
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = CLITestHelper.create_mock_args(
            database="/test/corrupted.ftd",
            classifier="kraken2",
            output="/test/output/",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_validate_output_directory'):
            
            result = self.command.execute(args)
            assert result != 0
    
    @patch('flextaxd.cli.commands.export.SQLiteTaxonomyRepository') 
    @patch('flextaxd.cli.commands.export.get_exporter')
    def test_exporter_error(self, mock_get_exporter, mock_repo_class, sample_taxonomy_tree):
        """Test handling of exporter errors."""
        # Setup mocks
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        mock_exporter = Mock()
        mock_exporter.export.side_effect = Exception("Export failed")
        mock_get_exporter.return_value = mock_exporter
        
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            classifier="kraken2",
            output="/test/output/",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_validate_output_directory'):
            
            result = self.command.execute(args)
            assert result != 0
    
    @patch('flextaxd.cli.commands.export.SQLiteTaxonomyRepository')
    @patch('flextaxd.cli.commands.export.get_exporter')
    def test_empty_database(self, mock_get_exporter, mock_repo_class):
        """Test handling of empty databases."""
        # Create empty tree
        empty_tree = TaxonomyTree()
        
        mock_repo = Mock()
        mock_repo.load_tree.return_value = empty_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        mock_exporter = Mock()
        mock_get_exporter.return_value = mock_exporter
        
        args = CLITestHelper.create_mock_args(
            database="/test/empty.ftd",
            classifier="kraken2",
            output="/test/output/",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_validate_output_directory'):
            
            result = self.command.execute(args)
            
            # Should handle empty database gracefully
            assert result == 0  # or != 0 depending on desired behavior
            mock_exporter.export.assert_called_with(empty_tree, "/test/output/")
    
    @patch('flextaxd.cli.commands.export.SQLiteTaxonomyRepository')
    def test_interrupted_export(self, mock_repo_class, sample_taxonomy_tree):
        """Test handling of interrupted export."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            classifier="kraken2",
            output="/test/output/",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_validate_output_directory'), \
             patch('flextaxd.cli.commands.export.get_exporter') as mock_get_exporter:
            
            mock_exporter = Mock()
            mock_exporter.export.side_effect = KeyboardInterrupt()
            mock_get_exporter.return_value = mock_exporter
            
            result = self.command.execute(args)
            assert result != 0


class TestExportCommandAdvancedFeatures:
    """Test ExportCommand advanced features."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = ExportCommand()
    
    @patch('flextaxd.cli.commands.export.SQLiteTaxonomyRepository')
    @patch('flextaxd.cli.commands.export.get_exporter')
    def test_export_with_validation(self, mock_get_exporter, mock_repo_class, sample_taxonomy_tree):
        """Test export with validation enabled."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        mock_exporter = Mock()
        mock_get_exporter.return_value = mock_exporter
        
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            classifier="kraken2",
            output="/test/output/",
            validate=True,
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_validate_output_directory'):
            
            result = self.command.execute(args)
            
            assert result == 0
            # Should call validation if supported by exporter
            if hasattr(mock_exporter, 'validate'):
                mock_exporter.validate.assert_called_once()
    
    @patch('flextaxd.cli.commands.export.SQLiteTaxonomyRepository')
    @patch('flextaxd.cli.commands.export.get_exporter') 
    def test_export_with_compression(self, mock_get_exporter, mock_repo_class, sample_taxonomy_tree):
        """Test export with compression."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        mock_exporter = Mock()
        mock_get_exporter.return_value = mock_exporter
        
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            format="json",
            output="/test/taxonomy.json.gz",
            compress=True,
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('pathlib.Path') as mock_path:
            
            mock_path_obj = Mock()
            mock_path_obj.parent.mkdir = Mock()
            mock_path.return_value = mock_path_obj
            
            result = self.command.execute(args)
            
            assert result == 0
            # Compression should be handled by exporter or post-processing
    
    @patch('flextaxd.cli.commands.export.SQLiteTaxonomyRepository')
    @patch('flextaxd.cli.commands.export.get_exporter')
    def test_verbose_export_logging(self, mock_get_exporter, mock_repo_class, sample_taxonomy_tree):
        """Test verbose logging during export."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        mock_exporter = Mock()
        mock_get_exporter.return_value = mock_exporter
        
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            classifier="kraken2",
            output="/test/output/", 
            verbose=True
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_validate_output_directory'), \
             patch.object(self.command, 'logger') as mock_logger:
            
            result = self.command.execute(args)
            
            assert result == 0
            # Should have verbose logging
            assert mock_logger.info.called
            assert mock_logger.debug.called or mock_logger.info.call_count > 1


class TestExportCommandIntegration:
    """Integration tests for ExportCommand."""
    
    def setup_method(self):
        """Set up test fixtures.""" 
        self.command = ExportCommand()
    
    def test_realistic_kraken2_export(self, temp_dir):
        """Test realistic Kraken2 export workflow."""
        # Create realistic test scenario
        complex_tree = MockData.create_complex_taxonomy_tree()
        db_path = temp_dir / "complex.ftd"
        output_dir = temp_dir / "kraken2_output"
        
        args = CLITestHelper.create_mock_args(
            database=str(db_path),
            classifier="kraken2", 
            output=str(output_dir),
            verbose=True
        )
        
        with patch('flextaxd.cli.commands.export.SQLiteTaxonomyRepository') as mock_repo_class, \
             patch('flextaxd.cli.commands.export.get_exporter') as mock_get_exporter, \
             patch.object(self.command, '_validate_database_path'):
            
            # Setup mocks
            mock_repo = Mock()
            mock_repo.load_tree.return_value = complex_tree
            mock_repo_class.return_value.__enter__.return_value = mock_repo
            
            mock_exporter = Mock()
            mock_get_exporter.return_value = mock_exporter
            
            result = self.command.execute(args)
            
            assert result == 0
            # Verify complex tree was exported
            mock_exporter.export.assert_called_with(complex_tree, str(output_dir))
            assert len(complex_tree._nodes) == 11
            assert len(complex_tree._genomes) == 5
    
    def test_format_export_workflow(self, temp_dir):
        """Test complete format export workflow."""
        tree = MockData.create_complex_taxonomy_tree()
        db_path = temp_dir / "test.ftd"
        output_file = temp_dir / "taxonomy.tsv"
        
        args = CLITestHelper.create_mock_args(
            database=str(db_path),
            format="tsv",
            output=str(output_file),
            verbose=False
        )
        
        with patch('flextaxd.cli.commands.export.SQLiteTaxonomyRepository') as mock_repo_class, \
             patch('flextaxd.cli.commands.export.get_exporter') as mock_get_exporter, \
             patch.object(self.command, '_validate_database_path'):
            
            mock_repo = Mock()
            mock_repo.load_tree.return_value = tree
            mock_repo_class.return_value.__enter__.return_value = mock_repo
            
            mock_exporter = Mock()
            mock_get_exporter.return_value = mock_exporter
            
            result = self.command.execute(args)
            
            assert result == 0
            # Output should be a single file, not directory
            mock_exporter.export.assert_called_with(tree, str(output_file))
    
    def test_backward_compatibility(self):
        """Test backward compatibility with legacy format option."""
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            legacy_format="ncbi",  # Old-style format specification
            output="/test/ncbi_output/",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_validate_output_directory'), \
             patch('flextaxd.cli.commands.export.SQLiteTaxonomyRepository') as mock_repo_class, \
             patch('flextaxd.cli.commands.export.get_exporter') as mock_get_exporter:
            
            mock_repo = Mock()
            mock_repo_class.return_value.__enter__.return_value = mock_repo
            
            mock_exporter = Mock()
            mock_get_exporter.return_value = mock_exporter
            
            result = self.command.execute(args)
            
            assert result == 0
            # Legacy format should work as classifier
            mock_get_exporter.assert_called_with("ncbi")