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


def create_export_mock_args(**overrides):
    """Create complete mock args for ExportCommand with all required attributes."""
    defaults = {
        # Required CLI args
        'database': '/test/db.ftd',
        'classifier': None,
        'format': None,
        'legacy_format': None,
        'output': '/test/output',
        
        # Export options
        'include_genomes': False,
        'compress': False,
        'validate_files': True,
        'skip_validation': False,
        
        # NCBI options
        'names_file': 'names.dmp',
        'nodes_file': 'nodes.dmp',
        
        # TSV options
        'separator': '\t',
        'include_header': True,
        
        # CreateTaxDB options
        'sequence_filter': 'all',
        'default_genome_size': 1000000,
        'db_version': '1.0',
        
        # Classifier-specific options
        'include_merged': False,
        'format_type': 'ncbi_taxonomy',
        'sequence_type': 'all',
        'create_lca_mapping': True,
        'disable_parallel': False,  # Missing attribute causing failures
        'max_workers': 4,  # Missing attribute for parallel processing
        
        # Global CLI options (from main parser)
        'verbose': 0,
        'quiet': False,
        'log_file': None,
        'command': 'export',
        
        # Progress-related options (expected by export command)
        'progress_width': 80,
        'no_eta': False,
        'no_rate': False,
        'progress_log': None,
        'progress_interval': 1.0,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


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
        
        args = create_export_mock_args(
            database="/test/db.ftd",
            classifier="kraken2", 
            output="/test/kraken2_db/",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_validate_output_directory'), \
             patch.object(self.command, '_export_classifier_format') as mock_export:
            
            result = self.command.execute(args)
            
            assert result == 0
            mock_export.assert_called_once()
    
    @patch('flextaxd.cli.commands.export.SQLiteTaxonomyRepository')
    def test_execute_format_export(self, mock_repo_class, sample_taxonomy_tree):
        """Test successful format export (single file output)."""
        # Setup repository mock
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_export_mock_args(
            database="/test/db.ftd",
            format="tsv",
            output="/test/taxonomy.tsv",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('flextaxd.cli.commands.export.Path') as mock_path, \
             patch.object(self.command, '_export_tsv_with_progress') as mock_export:
            
            # Setup path mock for output file
            mock_path_obj = Mock()
            mock_path_obj.exists.return_value = False
            mock_path_obj.is_dir.return_value = False
            # Mock the parent and mkdir method
            mock_parent = Mock()
            mock_parent.mkdir = Mock()
            mock_path_obj.parent = mock_parent
            # Make the mock path object behave like a string when needed
            mock_path_obj.__str__ = Mock(return_value="/test/taxonomy.tsv")
            mock_path_obj.__fspath__ = Mock(return_value="/test/taxonomy.tsv")
            mock_path.return_value = mock_path_obj
            
            result = self.command.execute(args)
            
            assert result == 0
            mock_export.assert_called_once()
            # Should create parent directory for output file
            mock_parent.mkdir.assert_called_with(parents=True, exist_ok=True)
    
    @patch('flextaxd.cli.commands.export.SQLiteTaxonomyRepository')
    def test_execute_legacy_format(self, mock_repo_class, sample_taxonomy_tree):
        """Test legacy format export (backward compatibility)."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_export_mock_args(
            database="/test/db.ftd",
            legacy_format="ncbi",
            output="/test/ncbi_dump/",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_validate_output_directory'), \
             patch.object(self.command, '_export_classifier_format') as mock_export:
            
            result = self.command.execute(args)
            
            assert result == 0
            # Legacy format should be treated as classifier
            mock_export.assert_called_once()
    
    def test_execute_no_export_option(self):
        """Test execution with no export option specified."""
        args = create_export_mock_args(
            database="/test/db.ftd",
            output="/test/output/",
            verbose=False
            # No classifier, format, or legacy_format specified
        )
        
        result = self.command.execute(args)
        
        # Should fail with validation error
        assert result != 0
    
    def test_execute_multiple_export_options(self, sample_taxonomy_tree):
        """Test execution with multiple export options (should be prevented by argparse)."""
        # This test verifies the mutually exclusive group setup
        # In practice, argparse would prevent this, but we test the logic
        args = create_export_mock_args(
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
             patch.object(self.command, '_export_classifier_format') as mock_export:
            
            mock_repo = Mock()
            mock_repo.load_tree.return_value = sample_taxonomy_tree
            mock_repo_class.return_value.__enter__.return_value = mock_repo
            
            result = self.command.execute(args)
            
            # Should prefer classifier over format
            assert result == 0
            mock_export.assert_called_once()


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
    def test_classifier_export_variants(self, mock_repo_class, classifier, sample_taxonomy_tree):
        """Test export with different classifiers."""
        # Setup mocks
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        # Some classifiers like sourmash may expect file output rather than directory
        output_path = f"/test/{classifier}_db/" if classifier != "sourmash" else f"/test/{classifier}_db.zip"
        
        args = create_export_mock_args(
            database="/test/db.ftd",
            classifier=classifier,
            output=output_path,
            verbose=False,
            skip_validation=True
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_validate_output_directory'), \
             patch.object(self.command, '_export_classifier_format') as mock_export, \
             patch('flextaxd.cli.commands.export.Path') as mock_path:
            
            # Configure mock path to behave like a file, not directory
            mock_path_instance = Mock()
            mock_path_instance.exists.return_value = False
            mock_path_instance.is_dir.return_value = False
            mock_path_instance.parent.mkdir = Mock()
            mock_path.return_value = mock_path_instance
            
            result = self.command.execute(args)
            
            assert result == 0
            mock_export.assert_called_once()
    
    def test_invalid_classifier(self):
        """Test export with invalid classifier."""
        
        args = create_export_mock_args(
            database="/test/db.ftd", 
            classifier="invalid",
            output="/test/output/",
            verbose=False,
            skip_validation=True
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_validate_output_directory'), \
             patch('flextaxd.cli.commands.export.SQLiteTaxonomyRepository'), \
             patch('flextaxd.cli.commands.export.Path') as mock_path, \
             patch.object(self.command, '_export_classifier_format') as mock_export:
            
            # Configure mock path to behave like a file, not directory
            mock_path_instance = Mock()
            mock_path_instance.exists.return_value = False
            mock_path_instance.is_dir.return_value = False
            mock_path_instance.parent.mkdir = Mock()
            mock_path.return_value = mock_path_instance
            
            # Make the export method raise a KeyError for invalid classifier
            mock_export.side_effect = KeyError("invalid")
            
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
    def test_format_export_variants(self, mock_repo_class, format_name, extension, sample_taxonomy_tree):
        """Test export with different single-file formats."""
        # Setup mocks
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        output_file = f"/test/output{extension}"
        args = create_export_mock_args(
            database="/test/db.ftd",
            format=format_name,
            output=output_file,
            verbose=False,
            skip_validation=True
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_validate_output_directory'), \
             patch('flextaxd.cli.commands.export.Path') as mock_path:
            
            # Configure mock path
            mock_path_instance = Mock()
            mock_path_instance.exists.return_value = False
            mock_path_instance.is_dir.return_value = False
            mock_parent = Mock()
            mock_parent.mkdir = Mock()
            mock_path_instance.parent = mock_parent
            # Make the mock path object behave like a string when needed
            mock_path_instance.__str__ = Mock(return_value=output_file)
            mock_path_instance.__fspath__ = Mock(return_value=output_file)
            mock_path.return_value = mock_path_instance
            
            # Mock the specific export methods based on format
            if format_name == "tsv":
                with patch.object(self.command, '_export_tsv_with_progress') as mock_export:
                    result = self.command.execute(args)
                    assert result == 0
                    mock_export.assert_called_once()
            elif format_name == "json":
                with patch.object(self.command, '_export_json_with_progress') as mock_export:
                    result = self.command.execute(args)
                    assert result == 0
                    mock_export.assert_called_once()
            elif format_name == "newick":
                with patch.object(self.command, '_export_newick_with_progress') as mock_export:
                    result = self.command.execute(args)
                    assert result == 0
                    mock_export.assert_called_once()
            else:
                # Other formats go through _export_classifier_format
                with patch.object(self.command, '_export_classifier_format') as mock_export:
                    result = self.command.execute(args)
                    assert result == 0
                    mock_export.assert_called_once()
    
    def test_invalid_format(self):
        """Test export with invalid format."""
        
        args = create_export_mock_args(
            database="/test/db.ftd",
            format="invalid", 
            output="/test/output.txt",
            skip_validation=True,
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_validate_output_directory'), \
             patch('flextaxd.cli.commands.export.Path') as mock_path, \
             patch('flextaxd.cli.commands.export.SQLiteTaxonomyRepository'):
            
            # Configure mock path
            mock_path_instance = Mock()
            mock_path_instance.exists.return_value = False
            mock_path_instance.is_dir.return_value = False
            mock_path_instance.parent.mkdir = Mock()
            mock_path.return_value = mock_path_instance
            
            result = self.command.execute(args)
            assert result != 0


class TestExportCommandValidation:
    """Test ExportCommand input validation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = ExportCommand()
    
    def test_validate_missing_database(self):
        """Test validation with missing database."""
        args = create_export_mock_args(
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
        args = create_export_mock_args(
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
    
    def test_validate_output_path_creation(self, sample_taxonomy_tree):
        """Test output path validation and creation."""
        args = create_export_mock_args(
            database="/test/db.ftd",
            classifier="kraken2",
            output="/test/new/output/",
            verbose=False,
            skip_validation=True
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('flextaxd.cli.commands.export.Path') as mock_path, \
             patch('flextaxd.cli.commands.export.SQLiteTaxonomyRepository') as mock_repo_class, \
             patch.object(self.command, '_export_classifier_format') as mock_export:
            
            # Setup for directory creation
            mock_path_obj = Mock()
            mock_path_obj.exists.return_value = False
            mock_path_obj.mkdir = Mock()
            mock_path.return_value = mock_path_obj
            
            mock_repo = Mock()
            mock_repo.load_tree.return_value = sample_taxonomy_tree
            mock_repo_class.return_value.__enter__.return_value = mock_repo
            
            result = self.command.execute(args)
            
            # Should complete successfully
            assert result == 0
    
    def test_validate_output_permission_error(self):
        """Test handling of output permission errors."""
        args = create_export_mock_args(
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
        
        args = create_export_mock_args(
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
    def test_exporter_error(self, mock_repo_class, sample_taxonomy_tree):
        """Test handling of exporter errors."""
        # Setup mocks
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_export_mock_args(
            database="/test/db.ftd",
            classifier="kraken2",
            output="/test/output/",
            verbose=False
        )
        
        # Mock the kraken2 exporter to simulate export failure
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_validate_output_directory'), \
             patch('flextaxd.exporters.kraken2.Kraken2Exporter') as mock_exporter_class:
            
            mock_exporter = Mock()
            mock_exporter.export.side_effect = Exception("Export failed")
            mock_exporter_class.return_value = mock_exporter
            
            result = self.command.execute(args)
            assert result == 1  # Should return error code due to exception handling
    
    @patch('flextaxd.cli.commands.export.SQLiteTaxonomyRepository')
    def test_empty_database(self, mock_repo_class):
        """Test handling of empty databases."""
        # Create empty tree
        empty_tree = TaxonomyTree()
        
        mock_repo = Mock()
        mock_repo.load_tree.return_value = empty_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_export_mock_args(
            database="/test/empty.ftd",
            classifier="kraken2",
            output="/test/output/",
            verbose=False
        )
        
        # Mock the kraken2 exporter for empty database export
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_validate_output_directory'), \
             patch('flextaxd.exporters.kraken2.Kraken2Exporter') as mock_exporter_class:
            
            mock_exporter = Mock()
            mock_exporter_class.return_value = mock_exporter
            
            result = self.command.execute(args)
            
            # Should handle empty database gracefully by failing validation
            assert result == 1  # Export should fail for empty tree due to validation
            # Exporter should not be called due to failed validation
            mock_exporter.export.assert_not_called()
    
    @patch('flextaxd.cli.commands.export.SQLiteTaxonomyRepository')
    def test_interrupted_export(self, mock_repo_class, sample_taxonomy_tree):
        """Test handling of interrupted export."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_export_mock_args(
            database="/test/db.ftd",
            classifier="kraken2",
            output="/test/output/",
            verbose=False
        )
        
        # Mock the kraken2 exporter to simulate KeyboardInterrupt
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_validate_output_directory'), \
             patch('flextaxd.exporters.kraken2.Kraken2Exporter') as mock_exporter_class:
            
            mock_exporter = Mock()
            mock_exporter.export.side_effect = KeyboardInterrupt()
            mock_exporter_class.return_value = mock_exporter
            
            result = self.command.execute(args)
            assert result == 1  # Should return error code due to exception handling


class TestExportCommandAdvancedFeatures:
    """Test ExportCommand advanced features."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = ExportCommand()
    
    @patch('flextaxd.cli.commands.export.SQLiteTaxonomyRepository')
    @patch('flextaxd.exporters.kraken2.Kraken2Exporter')
    def test_export_with_validation(self, mock_exporter_class, mock_repo_class, sample_taxonomy_tree):
        """Test export with validation enabled."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo.get_statistics.return_value = {
            'node_count': 5,
            'genome_count': 3,
            'genomes_with_files': 2,
            'genomes_metadata_only': 1,
            'rank_distribution': {'species': 2, 'genus': 1}
        }
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        mock_exporter = Mock()
        mock_exporter_class.return_value = mock_exporter
        
        args = create_export_mock_args(
            database="/test/db.ftd",
            classifier="kraken2",
            output="/test/output/",
            validate_files=True,
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_validate_output_directory'), \
             patch('flextaxd.cli.commands.export.validate_export_requirements') as mock_validate:
            
            # Mock validation to return success
            from flextaxd.exporters.validation import ValidationResult
            mock_validate.return_value = ValidationResult(
                passed=True,
                requirements_met=['has_genomes'],
                requirements_failed=[],
                warnings=[]
            )
            
            result = self.command.execute(args)
            
            assert result == 0
            # Should call validation when validate_files is True
            mock_validate.assert_called_once()
    
    @patch('flextaxd.cli.commands.export.SQLiteTaxonomyRepository')
    def test_export_with_compression(self, mock_repo_class, sample_taxonomy_tree):
        """Test export with compression."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo.get_statistics.return_value = {
            'node_count': 5,
            'genome_count': 3
        }
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        # Use temp directory for paths
        import tempfile
        with tempfile.TemporaryDirectory() as temp_dir:
            args = create_export_mock_args(
                database=f"{temp_dir}/db.ftd",
                format="json",
                output=f"{temp_dir}/taxonomy.json.gz",
                compress=True,
                verbose=False
            )
            
            with patch.object(self.command, '_validate_database_path'), \
                 patch.object(self.command, '_export_json_with_progress') as mock_export_json:
                
                result = self.command.execute(args)
                
                assert result == 0
                # JSON export method should be called
                mock_export_json.assert_called_once()
    
    @patch('flextaxd.cli.commands.export.SQLiteTaxonomyRepository')
    @patch('flextaxd.exporters.kraken2.Kraken2Exporter')
    def test_verbose_export_logging(self, mock_exporter_class, mock_repo_class, sample_taxonomy_tree):
        """Test verbose logging during export."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        mock_exporter = Mock()
        mock_exporter_class.return_value = mock_exporter
        
        args = create_export_mock_args(
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
        
        args = create_export_mock_args(
            database=str(db_path),
            classifier="kraken2", 
            output=str(output_dir),
            verbose=True
        )
        
        with patch('flextaxd.cli.commands.export.SQLiteTaxonomyRepository') as mock_repo_class, \
             patch('flextaxd.exporters.kraken2.Kraken2Exporter') as mock_exporter_class, \
             patch.object(self.command, '_validate_database_path'):
            
            # Setup mocks
            mock_repo = Mock()
            mock_repo.load_tree.return_value = complex_tree
            mock_repo.get_statistics.return_value = {'node_count': 11, 'genome_count': 5}
            mock_repo_class.return_value.__enter__.return_value = mock_repo
            
            mock_exporter = Mock()
            mock_exporter_class.return_value = mock_exporter
            
            result = self.command.execute(args)
            
            assert result == 0
            # Verify complex tree was exported
            mock_exporter.export.assert_called_once()
            # Check first argument is the tree
            call_args = mock_exporter.export.call_args
            assert call_args[0][0] == complex_tree
            assert len(complex_tree._nodes) == 11
            assert len(complex_tree._genomes) == 5
    
    def test_format_export_workflow(self, temp_dir):
        """Test complete format export workflow."""
        tree = MockData.create_complex_taxonomy_tree()
        db_path = temp_dir / "test.ftd"
        output_file = temp_dir / "taxonomy.tsv"
        
        args = create_export_mock_args(
            database=str(db_path),
            format="tsv",
            output=str(output_file),
            verbose=False
        )
        
        with patch('flextaxd.cli.commands.export.SQLiteTaxonomyRepository') as mock_repo_class, \
             patch.object(self.command, '_export_tsv_with_progress') as mock_export_tsv, \
             patch.object(self.command, '_validate_database_path'):
            
            mock_repo = Mock()
            mock_repo.load_tree.return_value = tree
            mock_repo.get_statistics.return_value = {'node_count': 5, 'genome_count': 3}
            mock_repo_class.return_value.__enter__.return_value = mock_repo
            
            result = self.command.execute(args)
            
            assert result == 0
            # TSV export method should be called
            mock_export_tsv.assert_called_once()
    
    def test_backward_compatibility(self):
        """Test backward compatibility with legacy format option."""
        args = create_export_mock_args(
            database="/test/db.ftd",
            legacy_format="ncbi",  # Old-style format specification
            output="/test/ncbi_output/",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_validate_output_directory'), \
             patch('flextaxd.cli.commands.export.SQLiteTaxonomyRepository') as mock_repo_class, \
             patch('flextaxd.exporters.ncbi.NCBIExporter') as mock_exporter_class:
            
            mock_repo = Mock()
            mock_repo.load_tree.return_value = MockData.create_complex_taxonomy_tree()
            mock_repo_class.return_value.__enter__.return_value = mock_repo
            
            mock_exporter = Mock()
            mock_exporter_class.return_value = mock_exporter
            
            result = self.command.execute(args)
            
            assert result == 0
            # Legacy format should work as classifier
            mock_exporter_class.assert_called_once()