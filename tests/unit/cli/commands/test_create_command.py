"""Comprehensive unit tests for CreateCommand."""

import pytest
import argparse
from unittest.mock import Mock, patch, MagicMock, mock_open
from pathlib import Path

from flextaxd.cli.commands.create import CreateCommand
from flextaxd.core.exceptions import ValidationError, ParseError
from flextaxd.core.models import TaxonomyTree

from ....fixtures.cli.conftest import *
from ....fixtures.cli.mock_data import MockData, CLITestHelper


class TestCreateCommand:
    """Test CreateCommand basic functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = CreateCommand()
    
    def test_initialization(self):
        """Test command initialization."""
        assert isinstance(self.command, CreateCommand)
        assert hasattr(self.command, 'logger')
    
    def test_register_parser(self):
        """Test parser registration."""
        mock_subparsers = Mock()
        mock_parser = Mock()
        mock_subparsers.add_parser.return_value = mock_parser
        
        parser = CreateCommand.register_parser(mock_subparsers)
        
        # Verify parser was created with correct arguments
        mock_subparsers.add_parser.assert_called_once()
        call_args = mock_subparsers.add_parser.call_args
        assert call_args[0][0] == "create"  # Command name
        assert "help" in call_args[1]
        assert "description" in call_args[1]
        
        # Verify argument groups were added
        assert mock_parser.add_argument_group.called
        assert mock_parser.add_argument.called or mock_parser.add_argument_group().add_argument.called
    
    @patch('flextaxd.cli.commands.create.SQLiteTaxonomyRepository')
    @patch('flextaxd.cli.commands.create.registry')
    def test_execute_basic_success(self, mock_registry, mock_repo_class, sample_taxonomy_tree):
        """Test successful execution with basic arguments."""
        # Setup mocks
        mock_parser = Mock()
        mock_parser.parse_and_build_tree.return_value = sample_taxonomy_tree
        mock_registry.get_parser.return_value = mock_parser
        
        mock_repo = Mock()
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        # Create test arguments
        args = CLITestHelper.create_mock_args(
            input="/test/taxonomy.tsv",
            database="/test/output.ftd", 
            format="tsv",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_input_file'), \
             patch.object(self.command, '_validate_database_path'):
            
            result = self.command.execute(args)
            
            # Verify success
            assert result == 0
            mock_registry.get_parser.assert_called_with("tsv")
            mock_parser.parse_and_build_tree.assert_called_with("/test/taxonomy.tsv")
            mock_repo.save_tree.assert_called_with(sample_taxonomy_tree)
    
    @patch('flextaxd.cli.commands.create.registry')
    def test_execute_invalid_format(self, mock_registry):
        """Test execution with invalid format."""
        mock_registry.get_parser.side_effect = ValueError("Unknown format: invalid")
        
        args = CLITestHelper.create_mock_args(
            input="/test/taxonomy.tsv",
            database="/test/output.ftd",
            format="invalid",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_input_file'), \
             patch.object(self.command, '_validate_database_path'):
            
            result = self.command.execute(args)
            
            # Should fail with error code
            assert result != 0
    
    def test_execute_validation_errors(self):
        """Test execution with validation errors."""
        args = CLITestHelper.create_mock_args(
            input="/nonexistent/file.tsv",
            database="/test/output.ftd",
            format="tsv",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_input_file', 
                         side_effect=ValidationError("Input file does not exist")), \
             patch.object(self.command, '_validate_database_path'):
            
            result = self.command.execute(args)
            assert result != 0
    
    @patch('flextaxd.cli.commands.create.SQLiteTaxonomyRepository')
    @patch('flextaxd.cli.commands.create.registry')
    def test_execute_parse_error(self, mock_registry, mock_repo_class):
        """Test execution with parsing errors."""
        mock_parser = Mock()
        mock_parser.parse_and_build_tree.side_effect = ParseError("Invalid taxonomy format")
        mock_registry.get_parser.return_value = mock_parser
        
        args = CLITestHelper.create_mock_args(
            input="/test/bad_taxonomy.tsv",
            database="/test/output.ftd",
            format="tsv",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_input_file'), \
             patch.object(self.command, '_validate_database_path'):
            
            result = self.command.execute(args)
            assert result != 0


class TestCreateCommandFormats:
    """Test CreateCommand with different input formats."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = CreateCommand()
    
    @pytest.mark.parametrize("format_name", ["tsv", "ncbi", "gtdb", "qiime", "silva", "cansnper"])
    @patch('flextaxd.cli.commands.create.SQLiteTaxonomyRepository')
    @patch('flextaxd.cli.commands.create.registry')
    def test_execute_different_formats(self, mock_registry, mock_repo_class, format_name, sample_taxonomy_tree):
        """Test execution with different input formats."""
        # Setup mocks
        mock_parser = Mock()
        mock_parser.parse_and_build_tree.return_value = sample_taxonomy_tree
        mock_registry.get_parser.return_value = mock_parser
        
        mock_repo = Mock()
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = CLITestHelper.create_mock_args(
            input=f"/test/taxonomy.{format_name}",
            database="/test/output.ftd",
            format=format_name,
            verbose=False
        )
        
        with patch.object(self.command, '_validate_input_file'), \
             patch.object(self.command, '_validate_database_path'):
            
            result = self.command.execute(args)
            
            assert result == 0
            mock_registry.get_parser.assert_called_with(format_name)
    
    @patch('flextaxd.cli.commands.create.SQLiteTaxonomyRepository')
    @patch('flextaxd.cli.commands.create.registry')
    def test_execute_ncbi_directory(self, mock_registry, mock_repo_class, sample_taxonomy_tree):
        """Test execution with NCBI directory input."""
        mock_parser = Mock()
        mock_parser.parse_and_build_tree.return_value = sample_taxonomy_tree
        mock_registry.get_parser.return_value = mock_parser
        
        mock_repo = Mock()
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = CLITestHelper.create_mock_args(
            input="/test/ncbi_dump/",
            database="/test/ncbi.ftd",
            format="ncbi",
            verbose=True
        )
        
        with patch.object(self.command, '_validate_input_file'), \
             patch.object(self.command, '_validate_database_path'):
            
            result = self.command.execute(args)
            
            assert result == 0
            mock_registry.get_parser.assert_called_with("ncbi")
    
    @patch('flextaxd.cli.commands.create.registry')  
    def test_auto_format_detection(self, mock_registry, sample_input_files):
        """Test automatic format detection."""
        # Mock registry to support auto-detection
        mock_registry.detect_format.return_value = "tsv"
        mock_parser = Mock()
        mock_registry.get_parser.return_value = mock_parser
        
        args = CLITestHelper.create_mock_args(
            input=sample_input_files["tsv"],
            database="/test/auto.ftd",
            # No format specified - should auto-detect
            verbose=False
        )
        
        with patch.object(self.command, '_validate_input_file'), \
             patch.object(self.command, '_validate_database_path'), \
             patch('flextaxd.cli.commands.create.SQLiteTaxonomyRepository'):
            
            result = self.command.execute(args)
            
            # Should attempt format detection
            if hasattr(mock_registry, 'detect_format'):
                mock_registry.detect_format.assert_called()


class TestCreateCommandValidation:
    """Test CreateCommand input validation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = CreateCommand()
    
    def test_validation_missing_input(self):
        """Test validation with missing input file."""
        args = CLITestHelper.create_mock_args(
            input="/nonexistent/file.tsv",
            database="/test/output.ftd",
            format="tsv"
        )
        
        with patch('pathlib.Path') as mock_path:
            mock_path_obj = Mock()
            mock_path_obj.exists.return_value = False
            mock_path.return_value = mock_path_obj
            
            result = self.command.execute(args)
            assert result != 0
    
    def test_validation_empty_input(self):
        """Test validation with empty input file."""
        args = CLITestHelper.create_mock_args(
            input="/test/empty.tsv",
            database="/test/output.ftd",
            format="tsv"
        )
        
        with patch('pathlib.Path') as mock_path:
            mock_path_obj = Mock()
            mock_path_obj.exists.return_value = True
            mock_path_obj.is_file.return_value = True
            mock_stat = Mock()
            mock_stat.st_size = 0  # Empty file
            mock_path_obj.stat.return_value = mock_stat
            mock_path.return_value = mock_path_obj
            
            result = self.command.execute(args)
            assert result != 0
    
    def test_validation_database_path_creation(self):
        """Test database path creation for new database."""
        args = CLITestHelper.create_mock_args(
            input="/test/taxonomy.tsv",
            database="/test/new/output.ftd",
            format="tsv"
        )
        
        with patch('pathlib.Path') as mock_path, \
             patch('flextaxd.cli.commands.create.registry') as mock_registry, \
             patch('flextaxd.cli.commands.create.SQLiteTaxonomyRepository'):
            
            # Setup input file validation
            input_path_obj = Mock()
            input_path_obj.exists.return_value = True
            input_path_obj.is_file.return_value = True
            mock_stat = Mock()
            mock_stat.st_size = 1024
            input_path_obj.stat.return_value = mock_stat
            
            # Setup database path validation  
            db_path_obj = Mock()
            db_path_obj.parent.mkdir = Mock()
            
            mock_path.side_effect = lambda p: input_path_obj if "taxonomy" in str(p) else db_path_obj
            
            # Setup parser mock
            mock_parser = Mock()
            mock_parser.parse_and_build_tree.return_value = Mock()
            mock_registry.get_parser.return_value = mock_parser
            
            result = self.command.execute(args)
            
            # Should create parent directories
            db_path_obj.parent.mkdir.assert_called_with(parents=True, exist_ok=True)
    
    def test_validation_invalid_database_extension(self):
        """Test validation with non-standard database extension."""
        args = CLITestHelper.create_mock_args(
            input="/test/taxonomy.tsv",
            database="/test/output.db",  # Non-standard extension
            format="tsv"
        )
        
        # Should still work - extension validation is not enforced
        with patch.object(self.command, '_validate_input_file'), \
             patch.object(self.command, '_validate_database_path'), \
             patch('flextaxd.cli.commands.create.registry') as mock_registry, \
             patch('flextaxd.cli.commands.create.SQLiteTaxonomyRepository'):
            
            mock_parser = Mock()
            mock_parser.parse_and_build_tree.return_value = Mock()
            mock_registry.get_parser.return_value = mock_parser
            
            result = self.command.execute(args)
            assert result == 0


class TestCreateCommandErrorHandling:
    """Test CreateCommand error handling and edge cases."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = CreateCommand()
    
    @patch('flextaxd.cli.commands.create.registry')
    def test_parser_registry_error(self, mock_registry):
        """Test handling of parser registry errors."""
        mock_registry.get_parser.side_effect = KeyError("Unknown format")
        
        args = CLITestHelper.create_mock_args(
            input="/test/taxonomy.tsv",
            database="/test/output.ftd",
            format="unknown",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_input_file'), \
             patch.object(self.command, '_validate_database_path'):
            
            result = self.command.execute(args)
            assert result != 0
    
    @patch('flextaxd.cli.commands.create.SQLiteTaxonomyRepository')
    @patch('flextaxd.cli.commands.create.registry')
    def test_database_save_error(self, mock_registry, mock_repo_class, sample_taxonomy_tree):
        """Test handling of database save errors."""
        # Setup mocks
        mock_parser = Mock()
        mock_parser.parse_and_build_tree.return_value = sample_taxonomy_tree
        mock_registry.get_parser.return_value = mock_parser
        
        mock_repo = Mock()
        mock_repo.save_tree.side_effect = Exception("Database write failed")
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = CLITestHelper.create_mock_args(
            input="/test/taxonomy.tsv",
            database="/test/output.ftd",
            format="tsv",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_input_file'), \
             patch.object(self.command, '_validate_database_path'):
            
            result = self.command.execute(args)
            assert result != 0
    
    @patch('flextaxd.cli.commands.create.SQLiteTaxonomyRepository')
    @patch('flextaxd.cli.commands.create.registry') 
    def test_memory_constraints(self, mock_registry, mock_repo_class):
        """Test handling of memory constraints with large files."""
        mock_parser = Mock()
        mock_parser.parse_and_build_tree.side_effect = MemoryError("Not enough memory")
        mock_registry.get_parser.return_value = mock_parser
        
        args = CLITestHelper.create_mock_args(
            input="/test/huge_taxonomy.tsv",
            database="/test/output.ftd",
            format="tsv",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_input_file'), \
             patch.object(self.command, '_validate_database_path'):
            
            result = self.command.execute(args)
            assert result != 0
    
    @patch('flextaxd.cli.commands.create.SQLiteTaxonomyRepository')
    @patch('flextaxd.cli.commands.create.registry')
    def test_interrupted_execution(self, mock_registry, mock_repo_class):
        """Test handling of interrupted execution."""
        mock_parser = Mock()
        mock_parser.parse_and_build_tree.side_effect = KeyboardInterrupt()
        mock_registry.get_parser.return_value = mock_parser
        
        args = CLITestHelper.create_mock_args(
            input="/test/taxonomy.tsv",
            database="/test/output.ftd",
            format="tsv",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_input_file'), \
             patch.object(self.command, '_validate_database_path'):
            
            result = self.command.execute(args)
            assert result != 0


class TestCreateCommandVerboseMode:
    """Test CreateCommand verbose output and logging."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = CreateCommand()
    
    @patch('flextaxd.cli.commands.create.SQLiteTaxonomyRepository')
    @patch('flextaxd.cli.commands.create.registry')
    def test_verbose_output(self, mock_registry, mock_repo_class, sample_taxonomy_tree):
        """Test verbose mode output."""
        # Setup mocks
        mock_parser = Mock()
        mock_parser.parse_and_build_tree.return_value = sample_taxonomy_tree
        mock_registry.get_parser.return_value = mock_parser
        
        mock_repo = Mock()
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = CLITestHelper.create_mock_args(
            input="/test/taxonomy.tsv",
            database="/test/output.ftd",
            format="tsv",
            verbose=True
        )
        
        with patch.object(self.command, '_validate_input_file'), \
             patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, 'logger') as mock_logger:
            
            result = self.command.execute(args)
            
            assert result == 0
            # Should log verbose information
            assert mock_logger.info.called
    
    @patch('flextaxd.cli.commands.create.SQLiteTaxonomyRepository')
    @patch('flextaxd.cli.commands.create.registry')
    def test_quiet_mode(self, mock_registry, mock_repo_class, sample_taxonomy_tree):
        """Test quiet mode (minimal output)."""
        # Setup mocks
        mock_parser = Mock()
        mock_parser.parse_and_build_tree.return_value = sample_taxonomy_tree
        mock_registry.get_parser.return_value = mock_parser
        
        mock_repo = Mock()
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = CLITestHelper.create_mock_args(
            input="/test/taxonomy.tsv",
            database="/test/output.ftd",
            format="tsv",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_input_file'), \
             patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, 'logger') as mock_logger:
            
            result = self.command.execute(args)
            
            assert result == 0
            # Should have minimal logging in quiet mode
            # Only essential info/error messages


class TestCreateCommandIntegration:
    """Integration-style tests for CreateCommand with realistic scenarios."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = CreateCommand()
    
    @patch('flextaxd.cli.commands.create.SQLiteTaxonomyRepository')
    @patch('flextaxd.cli.commands.create.registry')
    def test_realistic_tsv_workflow(self, mock_registry, mock_repo_class):
        """Test realistic TSV processing workflow."""
        # Create realistic taxonomy tree
        tree = MockData.create_complex_taxonomy_tree()
        
        mock_parser = Mock()
        mock_parser.parse_and_build_tree.return_value = tree
        mock_registry.get_parser.return_value = mock_parser
        
        mock_repo = Mock()
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = CLITestHelper.create_mock_args(
            input="/test/complex_taxonomy.tsv",
            database="/test/complex.ftd",
            format="tsv",
            verbose=True
        )
        
        with patch.object(self.command, '_validate_input_file'), \
             patch.object(self.command, '_validate_database_path'):
            
            result = self.command.execute(args)
            
            assert result == 0
            # Verify complex tree was processed
            mock_repo.save_tree.assert_called_with(tree)
            assert len(tree._nodes) == 11  # Complex tree has 11 nodes
            assert len(tree._genomes) == 5  # Complex tree has 5 genomes
    
    def test_real_file_system_integration(self, temp_dir, sample_input_files):
        """Test with real file system operations."""
        # Use real file paths from fixtures
        real_input = sample_input_files["tsv"]
        real_output = temp_dir / "real_test.ftd"
        
        args = CLITestHelper.create_mock_args(
            input=real_input,
            database=str(real_output),
            format="tsv",
            verbose=False
        )
        
        with patch('flextaxd.cli.commands.create.registry') as mock_registry, \
             patch('flextaxd.cli.commands.create.SQLiteTaxonomyRepository') as mock_repo_class:
            
            # Setup mocks while using real filesystem
            mock_parser = Mock()
            mock_parser.parse_and_build_tree.return_value = MockData.create_complex_taxonomy_tree()
            mock_registry.get_parser.return_value = mock_parser
            
            mock_repo = Mock()
            mock_repo_class.return_value.__enter__.return_value = mock_repo
            
            result = self.command.execute(args)
            
            assert result == 0
            # Real file validation should pass
            assert Path(real_input).exists()  # Input file exists from fixture