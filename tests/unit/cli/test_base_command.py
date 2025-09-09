"""Tests for BaseCommand functionality."""

import pytest
import argparse
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from flextaxd.cli.commands.base import BaseCommand
from flextaxd.core.exceptions import ValidationError


class TestBaseCommand:
    """Test BaseCommand abstract base class functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Create a concrete implementation for testing
        class ConcreteCommand(BaseCommand):
            @classmethod
            def register_parser(cls, subparsers):
                return subparsers.add_parser("test")
            
            def execute(self, args):
                return 0
        
        self.command_class = ConcreteCommand
        self.command = ConcreteCommand()
    
    def test_initialization(self):
        """Test command initialization."""
        assert hasattr(self.command, 'logger')
        assert self.command.logger.name.endswith('concretecommand')
    
    def test_abstract_methods_required(self):
        """Test that abstract methods must be implemented."""
        with pytest.raises(TypeError):
            BaseCommand()
    
    def test_register_parser_abstract(self):
        """Test that register_parser is abstract."""
        # Should work with concrete implementation
        mock_subparsers = Mock()
        result = self.command_class.register_parser(mock_subparsers)
        assert result is not None
    
    def test_execute_abstract(self):
        """Test that execute is abstract.""" 
        # Should work with concrete implementation
        args = argparse.Namespace()
        result = self.command.execute(args)
        assert result == 0


class TestBaseCommandValidation:
    """Test BaseCommand validation methods."""
    
    def setup_method(self):
        """Set up test fixtures."""
        class TestCommand(BaseCommand):
            @classmethod  
            def register_parser(cls, subparsers):
                return subparsers.add_parser("test")
            
            def execute(self, args):
                return 0
        
        self.command = TestCommand()
    
    @patch('pathlib.Path')
    def test_validate_database_path_exists(self, mock_path):
        """Test database path validation when file exists."""
        # Setup mocks
        mock_path_obj = Mock()
        mock_path_obj.exists.return_value = True
        mock_path_obj.is_file.return_value = True
        mock_path.return_value = mock_path_obj
        
        # Should not raise exception
        self.command._validate_database_path("/test/db.ftd", must_exist=True)
        
        mock_path.assert_called_with("/test/db.ftd")
        mock_path_obj.exists.assert_called_once()
        mock_path_obj.is_file.assert_called_once()
    
    @patch('pathlib.Path')  
    def test_validate_database_path_missing(self, mock_path):
        """Test database path validation when file missing."""
        # Setup mocks
        mock_path_obj = Mock()
        mock_path_obj.exists.return_value = False
        mock_path.return_value = mock_path_obj
        
        # Should raise ValidationError
        with pytest.raises(ValidationError, match="Database file does not exist"):
            self.command._validate_database_path("/test/missing.ftd", must_exist=True)
    
    @patch('pathlib.Path')
    def test_validate_database_path_not_file(self, mock_path):
        """Test database path validation when path is not a file."""
        # Setup mocks  
        mock_path_obj = Mock()
        mock_path_obj.exists.return_value = True
        mock_path_obj.is_file.return_value = False
        mock_path.return_value = mock_path_obj
        
        # Should raise ValidationError
        with pytest.raises(ValidationError, match="Database path is not a file"):
            self.command._validate_database_path("/test/directory", must_exist=True)
    
    @patch('pathlib.Path')
    def test_validate_database_path_new_file(self, mock_path):
        """Test database path validation for new file creation."""
        # Setup mocks
        mock_path_obj = Mock()
        mock_path_obj.parent.mkdir = Mock()
        mock_path.return_value = mock_path_obj
        
        # Should create parent directories
        self.command._validate_database_path("/test/new.ftd", must_exist=False)
        
        mock_path_obj.parent.mkdir.assert_called_with(parents=True, exist_ok=True)
    
    @patch('pathlib.Path')
    def test_validate_input_file_exists(self, mock_path):
        """Test input file validation when file exists."""
        # Setup mocks
        mock_path_obj = Mock()
        mock_path_obj.exists.return_value = True
        mock_path_obj.is_file.return_value = True
        mock_stat = Mock()
        mock_stat.st_size = 1024
        mock_path_obj.stat.return_value = mock_stat
        mock_path.return_value = mock_path_obj
        
        # Should not raise exception
        self.command._validate_input_file("/test/input.tsv")
        
        mock_path_obj.exists.assert_called_once()
        mock_path_obj.is_file.assert_called_once()
        mock_path_obj.stat.assert_called_once()
    
    @patch('pathlib.Path')
    def test_validate_input_file_missing(self, mock_path):
        """Test input file validation when file missing."""
        # Setup mocks
        mock_path_obj = Mock()
        mock_path_obj.exists.return_value = False
        mock_path.return_value = mock_path_obj
        
        # Should raise ValidationError
        with pytest.raises(ValidationError, match="Input file does not exist"):
            self.command._validate_input_file("/test/missing.tsv")
    
    @patch('pathlib.Path')
    def test_validate_input_file_empty(self, mock_path):
        """Test input file validation when file is empty."""
        # Setup mocks
        mock_path_obj = Mock()
        mock_path_obj.exists.return_value = True
        mock_path_obj.is_file.return_value = True
        mock_stat = Mock()
        mock_stat.st_size = 0  # Empty file
        mock_path_obj.stat.return_value = mock_stat
        mock_path.return_value = mock_path_obj
        
        # Should raise ValidationError
        with pytest.raises(ValidationError, match="Input file is empty"):
            self.command._validate_input_file("/test/empty.tsv")
    
    @patch('pathlib.Path')
    def test_validate_input_file_not_file(self, mock_path):
        """Test input file validation when path is directory.""" 
        # Setup mocks
        mock_path_obj = Mock()
        mock_path_obj.exists.return_value = True
        mock_path_obj.is_file.return_value = False
        mock_path.return_value = mock_path_obj
        
        # Should raise ValidationError
        with pytest.raises(ValidationError, match="Input path is not a file"):
            self.command._validate_input_file("/test/directory")
    
    @patch('pathlib.Path')
    def test_validate_output_directory_exists(self, mock_path):
        """Test output directory validation when directory exists."""
        # Setup mocks
        mock_path_obj = Mock()
        mock_path_obj.exists.return_value = True
        mock_path_obj.is_dir.return_value = True
        mock_path.return_value = mock_path_obj
        
        # Should not raise exception
        self.command._validate_output_directory("/test/output")
        
        # exists() is called twice: once in the first condition, once in the create condition
        assert mock_path_obj.exists.call_count == 2
        mock_path_obj.is_dir.assert_called_once()
    
    @patch('pathlib.Path')
    def test_validate_output_directory_create_new(self, mock_path):
        """Test output directory validation when creating new directory."""
        # Setup mocks
        mock_path_obj = Mock()
        mock_path_obj.exists.return_value = False
        mock_path_obj.mkdir = Mock()
        mock_path.return_value = mock_path_obj
        
        # Should create directory
        self.command._validate_output_directory("/test/new_output", create=True)
        
        mock_path_obj.mkdir.assert_called_with(parents=True, exist_ok=True)
    
    @patch('pathlib.Path')
    def test_validate_output_directory_not_directory(self, mock_path):
        """Test output directory validation when path is not directory."""
        # Setup mocks
        mock_path_obj = Mock()
        mock_path_obj.exists.return_value = True
        mock_path_obj.is_dir.return_value = False
        mock_path.return_value = mock_path_obj
        
        # Should raise ValidationError
        with pytest.raises(ValidationError, match="Output path exists but is not a directory"):
            self.command._validate_output_directory("/test/file.txt")
    
    @patch('pathlib.Path')
    def test_validate_output_directory_creation_error(self, mock_path):
        """Test output directory validation when creation fails."""
        # Setup mocks
        mock_path_obj = Mock()
        mock_path_obj.exists.return_value = False
        mock_path_obj.mkdir.side_effect = OSError("Permission denied")
        mock_path.return_value = mock_path_obj
        
        # Should raise ValidationError
        with pytest.raises(ValidationError, match="Cannot create output directory"):
            self.command._validate_output_directory("/test/forbidden", create=True)
    
    @patch('pathlib.Path')
    def test_validate_output_directory_no_create(self, mock_path):
        """Test output directory validation without creation."""
        # Setup mocks
        mock_path_obj = Mock()
        mock_path_obj.exists.return_value = False
        mock_path_obj.mkdir = Mock()
        mock_path.return_value = mock_path_obj
        
        # Should not create directory
        self.command._validate_output_directory("/test/new_output", create=False)
        
        # mkdir should not be called
        mock_path_obj.mkdir.assert_not_called()


class TestBaseCommandEdgeCases:
    """Test edge cases and error conditions for BaseCommand."""
    
    def setup_method(self):
        """Set up test fixtures."""
        class EdgeCaseCommand(BaseCommand):
            @classmethod
            def register_parser(cls, subparsers):
                return subparsers.add_parser("edge")
            
            def execute(self, args):
                # Test various validation scenarios
                if hasattr(args, 'database'):
                    self._validate_database_path(args.database, args.must_exist)
                if hasattr(args, 'input'):
                    self._validate_input_file(args.input)
                if hasattr(args, 'output'):
                    self._validate_output_directory(args.output, args.create)
                return 0
        
        self.command = EdgeCaseCommand()
    
    def test_empty_paths(self):
        """Test validation with empty paths."""
        with pytest.raises(ValidationError):
            self.command._validate_database_path("")
        
        with pytest.raises(ValidationError):
            self.command._validate_input_file("")
        
        with pytest.raises(ValidationError):
            self.command._validate_output_directory("")
    
    def test_whitespace_paths(self):
        """Test validation with whitespace-only paths."""
        with pytest.raises(ValidationError):
            self.command._validate_database_path("   ")
        
        with pytest.raises(ValidationError):
            self.command._validate_input_file("   ")
        
        with pytest.raises(ValidationError):
            self.command._validate_output_directory("   ")
    
    @patch('pathlib.Path')
    def test_special_characters_in_paths(self, mock_path):
        """Test validation with special characters in paths."""
        # Setup mocks for success case
        mock_path_obj = Mock()
        mock_path_obj.exists.return_value = True
        mock_path_obj.is_file.return_value = True
        mock_path_obj.is_dir.return_value = True
        mock_stat = Mock()
        mock_stat.st_size = 1024
        mock_path_obj.stat.return_value = mock_stat
        mock_path.return_value = mock_path_obj
        
        # Test paths with special characters
        special_paths = [
            "/test/file with spaces.ftd",
            "/test/file-with-dashes.ftd", 
            "/test/file_with_underscores.ftd",
            "/test/файл.ftd",  # Unicode characters
            "/test/file@domain.ftd"
        ]
        
        for path in special_paths:
            # Should handle special characters without error
            self.command._validate_database_path(path, must_exist=True)
            self.command._validate_input_file(path)
            mock_path_obj.is_dir.return_value = True  # Set for directory validation
            self.command._validate_output_directory(path, create=False)
            mock_path_obj.is_file.return_value = True  # Reset for next iteration
    
    @patch('pathlib.Path')
    def test_nested_directory_creation(self, mock_path):
        """Test creation of deeply nested directories."""
        # Setup mocks
        mock_path_obj = Mock()
        mock_path_obj.exists.return_value = False
        mock_path_obj.mkdir = Mock()
        mock_path_obj.parent.mkdir = Mock()
        mock_path.return_value = mock_path_obj
        
        # Test deeply nested path
        deep_path = "/test/very/deep/nested/directory/structure/db.ftd"
        
        self.command._validate_database_path(deep_path, must_exist=False)
        mock_path_obj.parent.mkdir.assert_called_with(parents=True, exist_ok=True)
        
        # Test output directory
        deep_output = "/test/very/deep/output/directory"
        self.command._validate_output_directory(deep_output, create=True)
        mock_path_obj.mkdir.assert_called_with(parents=True, exist_ok=True)
    
    @patch('pathlib.Path')
    def test_concurrent_file_operations(self, mock_path):
        """Test handling of concurrent file operations."""
        # Setup mocks that simulate race conditions
        mock_path_obj = Mock()
        
        # First call returns False (file doesn't exist)
        # Second call returns True (file was created by another process)
        mock_path_obj.exists.side_effect = [False, True]
        mock_path_obj.mkdir.side_effect = FileExistsError("Directory already exists")
        mock_path.return_value = mock_path_obj
        
        # Should handle race condition gracefully
        try:
            self.command._validate_output_directory("/test/concurrent", create=True)
        except ValidationError:
            pytest.fail("Should handle concurrent directory creation gracefully")
    
    @patch('pathlib.Path') 
    def test_permission_edge_cases(self, mock_path):
        """Test various permission-related edge cases."""
        mock_path_obj = Mock()
        mock_path.return_value = mock_path_obj
        
        # Test read-only filesystem
        mock_path_obj.exists.return_value = False
        mock_path_obj.mkdir.side_effect = OSError("Read-only file system")
        
        with pytest.raises(ValidationError, match="Cannot create output directory"):
            self.command._validate_output_directory("/readonly/path", create=True)
        
        # Test permission denied
        mock_path_obj.mkdir.side_effect = PermissionError("Permission denied")
        
        with pytest.raises(ValidationError, match="Cannot create output directory"):
            self.command._validate_output_directory("/forbidden/path", create=True)
    
    def test_logger_configuration(self):
        """Test logger is properly configured for each command."""
        class TestCommand1(BaseCommand):
            @classmethod
            def register_parser(cls, subparsers):
                return subparsers.add_parser("test1")
            def execute(self, args):
                return 0
        
        class TestCommand2(BaseCommand):
            @classmethod
            def register_parser(cls, subparsers):
                return subparsers.add_parser("test2") 
            def execute(self, args):
                return 0
        
        cmd1 = TestCommand1()
        cmd2 = TestCommand2()
        
        # Each command should have its own logger instance
        assert cmd1.logger.name.endswith("testcommand1")
        assert cmd2.logger.name.endswith("testcommand2") 
        assert cmd1.logger != cmd2.logger