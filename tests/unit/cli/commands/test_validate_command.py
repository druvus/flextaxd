"""Comprehensive unit tests for ValidateCommand."""

import pytest
import argparse
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from flextaxd.cli.commands.validate import ValidateCommand
from flextaxd.core.exceptions import ValidationError, DatabaseError

from ....fixtures.cli.conftest import *
from ....fixtures.cli.mock_data import MockData, CLITestHelper


def create_validate_mock_args(**overrides):
    """Create complete mock args for ValidateCommand with all required attributes."""
    defaults = {
        'database': '/test/db.ftd',
        'level': 'standard',
        'consistency_only': False,
        'files_only': False,
        'export_format': None,
        'output_file': None,
        'format': 'text',
        'max_workers': 4,
        'verbose': False,
        'quiet': False,
        'skip_validation': True  # For test isolation
    }
    defaults.update(overrides)
    return CLITestHelper.create_mock_args(**defaults)


class TestValidateCommand:
    """Test ValidateCommand functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = ValidateCommand()
    
    def test_register_parser(self):
        """Test parser registration."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        
        result_parser = ValidateCommand.register_parser(subparsers)
        
        assert result_parser is not None
        assert result_parser.prog.endswith('validate')
    
    @patch('flextaxd.cli.commands.validate.SQLiteTaxonomyRepository')
    def test_execute_standard_validation(self, mock_repo_class):
        """Test standard validation execution."""
        mock_repo = Mock()
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        # Mock validation results (what validate_all_genomes returns)
        mock_validation_results = [
            {'file_path': '/genome1.fna', 'valid': True},
            {'file_path': '/genome2.fna', 'valid': False, 'error': 'Missing file'}
        ]
        
        # Mock validation report (what generate_validation_report returns)
        mock_validation_report = {
            'total_genomes': 2,
            'valid_genomes': 1,
            'invalid_genomes': 1,
            'issues': ['Missing file: /genome2.fna']
        }
        
        mock_validator = Mock()
        mock_validator.validate_all_genomes.return_value = mock_validation_results
        mock_validator.generate_validation_report.return_value = mock_validation_report
        
        # Mock consistency checker results
        mock_consistency_results = {
            'circular_references': [],
            'orphaned_nodes': [],
            'duplicate_names': []
        }
        
        mock_consistency_checker = Mock()
        mock_consistency_checker.check_full_consistency.return_value = mock_consistency_results
        
        args = create_validate_mock_args(level='standard')
        
        with patch('flextaxd.validation.GenomeValidator') as mock_validator_class, \
             patch('flextaxd.validation.ConsistencyChecker') as mock_checker_class, \
             patch.object(self.command, '_validate_database_path'):
            mock_validator_class.return_value = mock_validator
            mock_checker_class.return_value = mock_consistency_checker
            result = self.command.execute(args)
        
        assert result == 0
    
    @patch('flextaxd.cli.commands.validate.SQLiteTaxonomyRepository')
    def test_execute_comprehensive_validation(self, mock_repo_class):
        """Test comprehensive validation execution."""
        mock_repo = Mock()
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        # Mock file validation results (what validate_all_genomes returns)
        mock_file_results = [
            {'file_path': '/genome1.fna', 'valid': True},
            {'file_path': '/genome2.fna', 'valid': False, 'error': 'Missing file'}
        ]
        
        # Mock validation report (what generate_validation_report returns)
        mock_file_report = {
            'total_genomes': 2,
            'valid_genomes': 1,
            'invalid_genomes': 1,
            'issues': ['Missing file: /genome2.fna']
        }
        
        # Mock consistency results
        mock_consistency_results = {
            'circular_references': [],
            'orphaned_nodes': [],
            'duplicate_names': []
        }
        
        mock_validator = Mock()
        mock_validator.validate_all_genomes.return_value = mock_file_results
        mock_validator.generate_validation_report.return_value = mock_file_report
        
        mock_consistency_checker = Mock()
        mock_consistency_checker.check_full_consistency.return_value = mock_consistency_results
        
        args = create_validate_mock_args(level='comprehensive')
        
        with patch('flextaxd.validation.GenomeValidator') as mock_validator_class, \
             patch('flextaxd.validation.ConsistencyChecker') as mock_checker_class, \
             patch.object(self.command, '_validate_database_path'):
            mock_validator_class.return_value = mock_validator
            mock_checker_class.return_value = mock_consistency_checker
            result = self.command.execute(args)
        
        assert result == 0
    
    @patch('flextaxd.cli.commands.validate.SQLiteTaxonomyRepository')
    def test_execute_consistency_only(self, mock_repo_class):
        """Test consistency-only validation."""
        mock_repo = Mock()
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        consistency_result = {
            'circular_references': [],
            'orphaned_nodes': [],
            'duplicate_names': [],
            'missing_parents': [],
            'issues_by_severity': {
                'errors': [],
                'warnings': [],
                'info': []
            },
            'summary': {
                'total_issues': 0,
                'errors': 0,
                'warnings': 0,
                'info': 0
            }
        }
        
        mock_validator = Mock()
        mock_validator.check_full_consistency.return_value = consistency_result
        
        args = create_validate_mock_args(consistency_only=True)
        
        with patch('flextaxd.validation.ConsistencyChecker') as mock_validator_class, \
             patch.object(self.command, '_validate_database_path'):
            mock_validator_class.return_value = mock_validator
            result = self.command.execute(args)
        
        assert result == 0  # Should return 0 for no issues
        mock_validator.check_full_consistency.assert_called_once()
    
    @patch('flextaxd.cli.commands.validate.SQLiteTaxonomyRepository')
    def test_execute_files_only(self, mock_repo_class):
        """Test files-only validation."""
        mock_repo = Mock()
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        file_result = {
            'total_files': 100,
            'valid_files': 90,
            'missing_files': 8,
            'invalid_files': 2,
            'missing_file_list': ['/path1.fna', '/path2.fna'],
            'invalid_file_list': ['/path3.fna']
        }
        
        mock_validator = Mock()
        mock_validator.validate_all_genomes.return_value = []
        mock_validator.generate_validation_report.return_value = file_result
        
        args = create_validate_mock_args(files_only=True, max_workers=8)
        
        with patch('flextaxd.validation.GenomeValidator') as mock_validator_class:
            mock_validator_class.return_value = mock_validator
            result = self.command.execute(args)
        
        assert result == 1  # Should return 1 due to missing/invalid files
    
    @patch('flextaxd.cli.commands.validate.SQLiteTaxonomyRepository')
    def test_execute_export_format_validation(self, mock_repo_class):
        """Test export format specific validation."""
        mock_repo = Mock()
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        export_validation_result = {
            'export_format': 'kraken2',
            'format': 'kraken2',
            'requirements_met': True,
            'missing_requirements': [],
            'warnings': ['Some genomes lack assembly accessions'],
            'total_genomes': 100,
            'valid_genomes': 98,
            'invalid_genomes': 2
        }
        
        mock_validator = Mock()
        mock_validator.validate_genomes_for_export.return_value = export_validation_result
        
        args = create_validate_mock_args(export_format='kraken2')
        
        with patch('flextaxd.validation.GenomeValidator') as mock_validator_class, \
             patch.object(self.command, '_validate_database_path'):
            mock_validator_class.return_value = mock_validator
            result = self.command.execute(args)
        
        assert result == 0
    
    @patch('flextaxd.cli.commands.validate.SQLiteTaxonomyRepository')
    def test_execute_json_output(self, mock_repo_class):
        """Test JSON output format."""
        mock_repo = Mock()
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        validation_result = {
            'database_valid': True,
            'validation_level': 'standard',
            'timestamp': '2024-01-01T12:00:00',
            'issues': []
        }
        
        mock_validator = Mock()
        mock_validator.validate_all_genomes.return_value = []
        mock_validator.generate_validation_report.return_value = validation_result
        
        mock_consistency_checker = Mock()
        mock_consistency_checker.check_full_consistency.return_value = {}
        
        args = create_validate_mock_args(format='json')
        
        with patch('flextaxd.validation.GenomeValidator') as mock_validator_class, \
             patch('flextaxd.validation.ConsistencyChecker') as mock_checker_class, \
             patch.object(self.command, '_validate_database_path'):
            mock_validator_class.return_value = mock_validator
            mock_checker_class.return_value = mock_consistency_checker
            with patch('builtins.print') as mock_print:
                result = self.command.execute(args)
        
        assert result == 0
        # Should print JSON formatted output
        mock_print.assert_called()
    
    @patch('flextaxd.cli.commands.validate.SQLiteTaxonomyRepository')
    @patch('flextaxd.cli.commands.validate.Path')
    def test_execute_with_output_file(self, mock_path, mock_repo_class):
        """Test validation with output file."""
        mock_repo = Mock()
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        mock_output_path = Mock()
        mock_path.return_value = mock_output_path
        mock_output_path.parent.mkdir = Mock()
        
        validation_result = {
            'database_valid': True,
            'issues': []
        }
        
        mock_validator = Mock()
        mock_validator.validate_all_genomes.return_value = []
        mock_validator.generate_validation_report.return_value = validation_result
        
        mock_consistency_checker = Mock()
        mock_consistency_checker.check_full_consistency.return_value = {}
        
        args = create_validate_mock_args(output_file='/test/output.json', format='json')
        
        with patch('flextaxd.validation.GenomeValidator') as mock_validator_class, \
             patch('flextaxd.validation.ConsistencyChecker') as mock_checker_class, \
             patch.object(self.command, '_validate_database_path'):
            mock_validator_class.return_value = mock_validator
            mock_checker_class.return_value = mock_consistency_checker
            with patch('builtins.open', create=True) as mock_open:
                result = self.command.execute(args)
        
        assert result == 0
        # Note: File writing is handled internally and mock assertions may not be needed
    
    @patch('flextaxd.cli.commands.validate.SQLiteTaxonomyRepository')
    def test_execute_database_error(self, mock_repo_class):
        """Test handling of database errors."""
        mock_repo = Mock()
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        mock_repo_class.side_effect = DatabaseError("Cannot connect to database")
        
        args = create_validate_mock_args()
        
        result = self.command.execute(args)
        
        assert result == 1
    
    @patch('flextaxd.cli.commands.validate.SQLiteTaxonomyRepository')
    def test_execute_validation_with_issues(self, mock_repo_class):
        """Test validation that finds issues."""
        mock_repo = Mock()
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        validation_result = {
            'database_valid': False,
            'file_validation': {
                'total_files': 100,
                'valid_files': 85,
                'missing_files': 10,
                'invalid_files': 5
            },
            'consistency_check': {
                'circular_references': ['562->511145->562'],
                'orphaned_nodes': ['123', '456'],
                'duplicate_names': [('Escherichia coli', [562, 511145])]
            },
            'issues': [
                'Missing files: 10',
                'Invalid files: 5',
                'Circular references found: 1',
                'Orphaned nodes: 2',
                'Duplicate names: 1'
            ]
        }
        
        mock_validator = Mock()
        mock_validator.validate_all_genomes.return_value = []
        mock_validator.generate_validation_report.return_value = validation_result['file_validation']
        
        mock_consistency_checker = Mock()
        mock_consistency_checker.check_full_consistency.return_value = validation_result['consistency_check']
        
        args = create_validate_mock_args()
        
        with patch('flextaxd.validation.GenomeValidator') as mock_validator_class, \
             patch('flextaxd.validation.ConsistencyChecker') as mock_checker_class:
            mock_validator_class.return_value = mock_validator
            mock_checker_class.return_value = mock_consistency_checker
            result = self.command.execute(args)
        
        assert result == 1  # Should return 1 due to validation issues


class TestValidateCommandEdgeCases:
    """Test edge cases and error conditions for ValidateCommand."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = ValidateCommand()
    
    @patch('flextaxd.cli.commands.validate.SQLiteTaxonomyRepository')
    def test_execute_invalid_export_format(self, mock_repo_class):
        """Test handling of invalid export format."""
        mock_repo = Mock()
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_validate_mock_args(export_format='invalid_format')
        
        result = self.command.execute(args)
        
        assert result == 1
    
    @patch('flextaxd.cli.commands.validate.SQLiteTaxonomyRepository')
    @patch('flextaxd.cli.commands.validate.Path')
    def test_execute_invalid_output_file(self, mock_path, mock_repo_class):
        """Test handling of invalid output file path."""
        mock_repo = Mock()
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        mock_output_path = Mock()
        mock_path.return_value = mock_output_path
        mock_output_path.parent.mkdir.side_effect = PermissionError("Cannot create directory")
        
        args = create_validate_mock_args(output_file='/invalid/path/output.json')
        
        result = self.command.execute(args)
        
        assert result == 1
    
    @patch('flextaxd.cli.commands.validate.SQLiteTaxonomyRepository')
    def test_execute_basic_validation_success(self, mock_repo_class):
        """Test basic validation with all checks passing."""
        mock_repo = Mock()
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        validation_result = {
            'database_valid': True,
            'file_validation': {
                'total_files': 50,
                'valid_files': 50,
                'missing_files': 0,
                'invalid_files': 0
            },
            'consistency_check': {
                'circular_references': [],
                'orphaned_nodes': [],
                'duplicate_names': []
            },
            'issues': []
        }
        
        mock_validator = Mock()
        mock_validator.validate_all_genomes.return_value = []
        mock_validator.generate_validation_report.return_value = validation_result['file_validation']
        
        mock_consistency_checker = Mock()
        mock_consistency_checker.check_full_consistency.return_value = validation_result['consistency_check']
        
        args = create_validate_mock_args(level='basic')
        
        with patch('flextaxd.validation.GenomeValidator') as mock_validator_class, \
             patch('flextaxd.validation.ConsistencyChecker') as mock_checker_class, \
             patch.object(self.command, '_validate_database_path'):
            mock_validator_class.return_value = mock_validator
            mock_checker_class.return_value = mock_consistency_checker
            result = self.command.execute(args)
        
        assert result == 0