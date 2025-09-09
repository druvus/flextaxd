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


def create_create_mock_args(**overrides):
    """Create complete mock args for CreateCommand with all required attributes."""
    defaults = {
        'input': '/test/taxonomy.tsv',
        'database': '/test/output.ftd',
        'format': 'auto',
        'overwrite': False,
        'no_header': False,
        'parent_column': 0,
        'child_column': 1,
        'id_column': None,
        'rank_column': None,
        'genomeid2taxid': None,
        'genomes_path': None,
        'auto_detect_sequences': False,
        'sequence_type': 'genome',
        'verbose': False,
        # NCBI datasets attributes (added in Phase 3)
        'ncbi_datasets': None,
        'assembly_level': 'complete',
        'max_genomes': None,
        'taxonomy_only': False,
        'ncbi_cache_dir': None
    }
    defaults.update(overrides)
    return CLITestHelper.create_mock_args(**defaults)


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
    @patch('flextaxd.cli.commands.create.Path')
    def test_execute_basic_success(self, mock_path, mock_registry, mock_repo_class, sample_taxonomy_tree):
        """Test successful execution with basic arguments."""
        # Setup Path mocks - input exists, database doesn't 
        mock_input_path = Mock()
        mock_input_path.exists.return_value = True
        
        mock_db_path = Mock()
        mock_db_path.exists.return_value = False  # DB doesn't exist
        mock_db_path.unlink = Mock()
        
        def path_side_effect(path):
            if "taxonomy.tsv" in str(path):
                return mock_input_path
            elif "output.ftd" in str(path):
                return mock_db_path
            return Mock()
        
        mock_path.side_effect = path_side_effect
        
        # Setup parser mocks
        mock_parser = Mock()
        mock_parser.parse.return_value = sample_taxonomy_tree
        mock_registry.get_parser.return_value = mock_parser
        
        # Setup repository mocks
        mock_repo = Mock()
        mock_repo.get_statistics.return_value = {
            'node_count': 5,
            'genome_count': 0,
            'rank_distribution': {}
        }
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        # Create test arguments
        args = create_create_mock_args(
            input="/test/taxonomy.tsv",
            database="/test/output.ftd", 
            format="tsv",
            verbose=False,
            overwrite=False,
            no_header=False,
            parent_column=0,
            child_column=1,
            id_column=None,
            rank_column=None,
            genomeid2taxid=None,
            genomes_path=None,
            # NCBI datasets attributes (added in Phase 3)
            ncbi_datasets=None,
            assembly_level='complete',
            max_genomes=None,
            taxonomy_only=False,
            ncbi_cache_dir=None,
            auto_detect_sequences=False,
            sequence_type='genome'
        )
        
        result = self.command.execute(args)
        
        # Verify success
        assert result == 0
        mock_registry.get_parser.assert_called_with("tsv")
        mock_repo.save_tree.assert_called_with(sample_taxonomy_tree)
    
    @patch('flextaxd.cli.commands.create.registry')
    @patch('flextaxd.cli.commands.create.Path')
    def test_execute_invalid_format(self, mock_path, mock_registry):
        """Test execution with invalid format."""
        # Setup Path mocks
        mock_path_obj = Mock()
        mock_path_obj.exists.return_value = True
        mock_path.return_value = mock_path_obj
        
        mock_registry.get_parser.side_effect = Exception("Unknown format")
        
        args = create_create_mock_args(
            input="/test/taxonomy.tsv",
            database="/test/output.ftd",
            format="invalid",
            verbose=False,
            overwrite=False
        )
        
        result = self.command.execute(args)
        
        # Should fail with error code
        assert result == 1
    
    @patch('flextaxd.cli.commands.create.Path')
    def test_execute_validation_errors(self, mock_path):
        """Test execution with validation errors."""
        # Setup Path mock to simulate file not existing
        mock_path_obj = Mock()
        mock_path_obj.exists.return_value = False
        mock_path.return_value = mock_path_obj
        
        args = create_create_mock_args(
            input="/nonexistent/file.tsv",
            database="/test/output.ftd",
            format="tsv",
            verbose=False
        )
        
        result = self.command.execute(args)
        
        # Should fail with error code
        assert result == 1
    
    @patch('flextaxd.cli.commands.create.SQLiteTaxonomyRepository')
    @patch('flextaxd.cli.commands.create.registry')
    @patch('flextaxd.cli.commands.create.Path')
    def test_execute_parse_error(self, mock_path, mock_registry, mock_repo_class):
        """Test execution with parsing errors."""
        # Setup Path mocks
        mock_path_obj = Mock()
        mock_path_obj.exists.return_value = True
        mock_path.return_value = mock_path_obj
        
        mock_parser = Mock()
        mock_parser.parse.side_effect = ParseError("Invalid taxonomy format")
        mock_registry.get_parser.return_value = mock_parser
        
        args = create_create_mock_args(
            input="/test/bad_taxonomy.tsv",
            database="/test/output.ftd",
            format="tsv",
            verbose=False,
            overwrite=False,
            no_header=False,
            parent_column=0,
            child_column=1
        )
        
        result = self.command.execute(args)
        assert result == 1


class TestCreateCommandFormats:
    """Test CreateCommand with different input formats."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = CreateCommand()
    
    @pytest.mark.parametrize("format_name", ["tsv", "ncbi", "gtdb", "qiime", "silva", "cansnper"])
    @patch('flextaxd.cli.commands.create.SQLiteTaxonomyRepository')
    @patch('flextaxd.cli.commands.create.registry')
    @patch('flextaxd.cli.commands.create.Path')
    def test_execute_different_formats(self, mock_path, mock_registry, mock_repo_class, format_name, sample_taxonomy_tree):
        """Test execution with different input formats."""
        # Setup Path mocks - input exists, database doesn't 
        mock_input_path = Mock()
        mock_input_path.exists.return_value = True
        
        mock_db_path = Mock()
        mock_db_path.exists.return_value = False  # DB doesn't exist
        mock_db_path.unlink = Mock()
        
        def path_side_effect(path):
            if f"taxonomy.{format_name}" in str(path):
                return mock_input_path
            elif "output.ftd" in str(path):
                return mock_db_path
            return Mock()
        
        mock_path.side_effect = path_side_effect
        
        # Setup mocks
        mock_parser = Mock()
        mock_parser.parse.return_value = sample_taxonomy_tree
        mock_registry.get_parser.return_value = mock_parser
        
        mock_repo = Mock()
        mock_repo.get_statistics.return_value = {
            'node_count': 5,
            'genome_count': 0,
            'rank_distribution': {}
        }
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_create_mock_args(
            input=f"/test/taxonomy.{format_name}",
            database="/test/output.ftd",
            format=format_name,
            verbose=False,
            overwrite=False,
            no_header=False,
            parent_column=0,
            child_column=1,
            id_column=None,
            rank_column=None,
            genomeid2taxid=None,
            genomes_path=None
        )
        
        result = self.command.execute(args)
        
        assert result == 0
        mock_registry.get_parser.assert_called_with(format_name)
    
    @patch('flextaxd.cli.commands.create.SQLiteTaxonomyRepository')
    @patch('flextaxd.cli.commands.create.registry')
    def test_execute_ncbi_directory(self, mock_registry, mock_repo_class, sample_taxonomy_tree):
        """Test execution with NCBI directory input."""
        mock_parser = Mock()
        mock_parser.parse.return_value = sample_taxonomy_tree
        mock_parser.can_parse.return_value = True
        mock_parser.parser_name = "ncbi"
        mock_registry.get_parser.return_value = mock_parser
        mock_registry.find_parser.return_value = None  # Force explicit format path
        mock_registry.register = Mock()  # Mock registration
        
        mock_repo = Mock()
        mock_repo.get_statistics.return_value = {
            'node_count': 10,
            'genome_count': 0,
            'root_count': 1,
            'leaf_count': 5,
            'rank_distribution': {}
        }
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_create_mock_args(
            input="/test/ncbi_dump/",
            database="/test/ncbi.ftd",
            format="ncbi",
            verbose=True
        )
        
        with patch.object(self.command, '_validate_input_file'), \
             patch.object(self.command, '_validate_database_path'), \
             patch('flextaxd.cli.commands.create.Path') as mock_path:
            
            # Mock Path objects for input and database paths
            mock_input_path = Mock()
            mock_input_path.exists.return_value = True
            mock_db_path = Mock()
            mock_db_path.exists.return_value = False
            
            def path_side_effect(path):
                if "ncbi_dump" in str(path):
                    return mock_input_path
                elif "ncbi.ftd" in str(path):
                    return mock_db_path
                return Mock()
            
            mock_path.side_effect = path_side_effect
            
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
        
        args = create_create_mock_args(
            input=sample_input_files["tsv"],
            database="/test/auto.ftd",
            format="auto",  # Auto-detect format
            verbose=False
        )
        
        with patch.object(self.command, '_validate_input_file'), \
             patch.object(self.command, '_validate_database_path'), \
             patch('flextaxd.cli.commands.create.SQLiteTaxonomyRepository'):
            
            result = self.command.execute(args)
            
            # Should attempt format detection
            mock_registry.find_parser.assert_called()
            
            assert result == 0


class TestCreateCommandValidation:
    """Test CreateCommand input validation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = CreateCommand()
    
    def test_validation_missing_input(self):
        """Test validation with missing input file."""
        args = create_create_mock_args(
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
        args = create_create_mock_args(
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
        args = create_create_mock_args(
            input="/test/taxonomy.tsv",
            database="/test/new/output.ftd",
            format="tsv"
        )
        
        with patch('flextaxd.cli.commands.create.Path') as mock_path, \
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
            db_path_obj.exists.return_value = False  # Database doesn't exist yet
            db_path_obj.parent.mkdir = Mock()
            
            mock_path.side_effect = lambda p: input_path_obj if "taxonomy" in str(p) else db_path_obj
            
            # Setup parser mock
            mock_parser = Mock()
            mock_parser.parse.return_value = Mock()
            mock_parser.can_parse.return_value = True
            mock_registry.get_parser.return_value = mock_parser
            mock_registry.register = Mock()  # Mock registration
            
            result = self.command.execute(args)
            
            # Command should succeed
            assert result == 0
    
    def test_validation_invalid_database_extension(self):
        """Test validation with non-standard database extension."""
        args = create_create_mock_args(
            input="/test/taxonomy.tsv",
            database="/test/output.db",  # Non-standard extension
            format="tsv"
        )
        
        # Should still work - extension validation is not enforced
        with patch('flextaxd.cli.commands.create.Path') as mock_path, \
             patch('flextaxd.cli.commands.create.registry') as mock_registry, \
             patch('flextaxd.cli.commands.create.SQLiteTaxonomyRepository') as mock_repo_class:
            
            # Mock Path objects
            mock_input_path = Mock()
            mock_input_path.exists.return_value = True
            mock_db_path = Mock()
            mock_db_path.exists.return_value = False
            
            def path_side_effect(path):
                if "taxonomy.tsv" in str(path):
                    return mock_input_path
                elif "output.db" in str(path):
                    return mock_db_path
                return Mock()
            
            mock_path.side_effect = path_side_effect
            
            # Mock parser and repository
            mock_parser = Mock()
            mock_parser.parse.return_value = MockData.create_complex_taxonomy_tree()
            mock_parser.can_parse.return_value = True
            mock_registry.get_parser.return_value = mock_parser
            mock_registry.register = Mock()
            
            mock_repo = Mock()
            mock_repo.get_statistics.return_value = {
                'node_count': 5,
                'genome_count': 0,
                'root_count': 1,
                'leaf_count': 2,
                'rank_distribution': {}
            }
            mock_repo_class.return_value.__enter__.return_value = mock_repo
            
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
        
        args = create_create_mock_args(
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
        
        args = create_create_mock_args(
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
        
        args = create_create_mock_args(
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
        
        args = create_create_mock_args(
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
        mock_parser.parse.return_value = sample_taxonomy_tree
        mock_parser.can_parse.return_value = True
        mock_registry.get_parser.return_value = mock_parser
        mock_registry.register = Mock()
        
        mock_repo = Mock()
        mock_repo.get_statistics.return_value = {
            'node_count': 10,
            'genome_count': 0,
            'root_count': 1,
            'leaf_count': 5,
            'rank_distribution': {}
        }
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_create_mock_args(
            input="/test/taxonomy.tsv",
            database="/test/output.ftd",
            format="tsv",
            verbose=True
        )
        
        with patch('flextaxd.cli.commands.create.Path') as mock_path, \
             patch.object(self.command, 'logger') as mock_logger:
            
            # Mock Path objects
            mock_input_path = Mock()
            mock_input_path.exists.return_value = True
            mock_db_path = Mock()
            mock_db_path.exists.return_value = False
            
            def path_side_effect(path):
                if "taxonomy.tsv" in str(path):
                    return mock_input_path
                elif "output.ftd" in str(path):
                    return mock_db_path
                return Mock()
            
            mock_path.side_effect = path_side_effect
            
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
        mock_parser.parse.return_value = sample_taxonomy_tree
        mock_parser.can_parse.return_value = True
        mock_registry.get_parser.return_value = mock_parser
        mock_registry.register = Mock()
        
        mock_repo = Mock()
        mock_repo.get_statistics.return_value = {
            'node_count': 10,
            'genome_count': 0,
            'root_count': 1,
            'leaf_count': 5,
            'rank_distribution': {}
        }
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_create_mock_args(
            input="/test/taxonomy.tsv",
            database="/test/output.ftd",
            format="tsv",
            verbose=False
        )
        
        with patch('flextaxd.cli.commands.create.Path') as mock_path, \
             patch.object(self.command, 'logger') as mock_logger:
            
            # Mock Path objects
            mock_input_path = Mock()
            mock_input_path.exists.return_value = True
            mock_db_path = Mock()
            mock_db_path.exists.return_value = False
            
            def path_side_effect(path):
                if "taxonomy.tsv" in str(path):
                    return mock_input_path
                elif "output.ftd" in str(path):
                    return mock_db_path
                return Mock()
            
            mock_path.side_effect = path_side_effect
            
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
        mock_parser.parse.return_value = tree
        mock_parser.can_parse.return_value = True
        mock_registry.get_parser.return_value = mock_parser
        mock_registry.register = Mock()
        
        mock_repo = Mock()
        mock_repo.get_statistics.return_value = {
            'node_count': 11,
            'genome_count': 5,
            'root_count': 1,
            'leaf_count': 5,
            'rank_distribution': {}
        }
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_create_mock_args(
            input="/test/complex_taxonomy.tsv",
            database="/test/complex.ftd",
            format="tsv",
            verbose=True
        )
        
        with patch('flextaxd.cli.commands.create.Path') as mock_path:
            
            # Mock Path objects
            mock_input_path = Mock()
            mock_input_path.exists.return_value = True
            mock_db_path = Mock()
            mock_db_path.exists.return_value = False
            mock_db_path.unlink = Mock()
            
            def path_side_effect(path):
                if "complex_taxonomy.tsv" in str(path):
                    return mock_input_path
                elif "complex.ftd" in str(path):
                    return mock_db_path
                return Mock()
            
            mock_path.side_effect = path_side_effect
            
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
        
        args = create_create_mock_args(
            input=str(real_input),
            database=str(real_output),
            format="tsv",
            verbose=False
        )
        
        with patch('flextaxd.cli.commands.create.registry') as mock_registry, \
             patch('flextaxd.cli.commands.create.SQLiteTaxonomyRepository') as mock_repo_class:
            
            # Setup mocks while using real filesystem
            mock_parser = Mock()
            mock_parser.parse.return_value = MockData.create_complex_taxonomy_tree()
            mock_parser.can_parse.return_value = True
            mock_registry.get_parser.return_value = mock_parser
            mock_registry.register = Mock()
            
            mock_repo = Mock()
            mock_repo.get_statistics.return_value = {
                'node_count': 11,
                'genome_count': 5,
                'root_count': 1,
                'leaf_count': 5,
                'rank_distribution': {}
            }
            mock_repo_class.return_value.__enter__.return_value = mock_repo
            
            result = self.command.execute(args)
            
            assert result == 0
            # Real file validation should pass
            assert Path(real_input).exists()  # Input file exists from fixture