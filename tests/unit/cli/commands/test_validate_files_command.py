"""Test cases for ValidateFilesCommand."""

import pytest
import argparse
from pathlib import Path
from unittest.mock import Mock, patch, mock_open
import tempfile
import json

from flextaxd.cli.commands.validate_files import ValidateFilesCommand
from flextaxd.core.exceptions import ValidationError, DatabaseError


def create_validate_files_mock_args(**overrides):
    """Create complete mock args for ValidateFilesCommand."""
    defaults = {
        'database': Path('/test/db.ftd'),
        'level': 'standard',
        'file_type': 'all',
        'max_files': None,
        'output': None,
        'output_dir': None,
        'format': 'text',
        'summary_only': False,
        'auto_repair': False,
        'search_dirs': None,
        'update_checksums': False,
        'parallel': 4,
        'skip_large_files': None,
        'dry_run': False,
        'verbose': False,
        'quiet': False
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def create_mock_file_data():
    """Create mock file data for testing."""
    return [
        {
            'file_id': 1,
            'file_path': '/test/genome1.fna',
            'file_type': 'genome',
            'scope': 'single_taxa',
            'taxa_count': 1,
            'file_exists': True,
            'file_checksum': 'abc123',
            'file_size': 1024,
            'last_validated': None,
            'entity_id': 'genome1',
            'tax_id': 562,
            'expected_path': '/test/genome1.fna',
            'actual_path': '/test/genome1.fna',
            'registry_exists': True,
            'registry_accessible': True,
            'registry_valid_format': True,
            'registry_size_bytes': 1024,
            'registry_checksum': 'abc123',
            'registry_last_checked': None,
            'registry_issue_type': None
        },
        {
            'file_id': 2,
            'file_path': '/test/genome2.fna',
            'file_type': 'genome',
            'scope': 'single_taxa',
            'taxa_count': 1,
            'file_exists': False,  # Missing file
            'file_checksum': None,
            'file_size': None,
            'last_validated': None,
            'entity_id': 'genome2',
            'tax_id': 511145,
            'expected_path': '/test/genome2.fna',
            'actual_path': '/test/genome2.fna',
            'registry_exists': False,
            'registry_accessible': False,
            'registry_valid_format': False,
            'registry_size_bytes': None,
            'registry_checksum': None,
            'registry_last_checked': None,
            'registry_issue_type': 'missing'
        }
    ]


class TestValidateFilesCommand:
    """Test ValidateFilesCommand functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = ValidateFilesCommand()
    
    def test_initialization(self):
        """Test command initialization."""
        assert self.command is not None
        assert hasattr(self.command, 'logger')
    
    def test_register_parser(self):
        """Test parser registration."""
        mock_subparsers = Mock()
        mock_parser = Mock()
        mock_subparsers.add_parser.return_value = mock_parser
        
        parser = ValidateFilesCommand.register_parser(mock_subparsers)
        
        # Verify parser was created
        mock_subparsers.add_parser.assert_called_once()
        call_args = mock_subparsers.add_parser.call_args
        assert call_args[0][0] == "validate-files"
        
        # Verify arguments were added
        assert mock_parser.add_argument.called
    
    @patch('flextaxd.cli.commands.validate_files.SQLiteTaxonomyRepository')
    def test_execute_basic_validation(self, mock_repo_class):
        """Test basic file validation execution."""
        mock_repo = Mock()
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_validate_files_mock_args()
        
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_collect_files_to_validate', return_value=create_mock_file_data()), \
             patch.object(self.command, '_validate_files', return_value={
                 'files_validated': 2,
                 'files_passed': 1,
                 'files_failed': 1,
                 'issues': [{'file_path': '/test/genome2.fna', 'issue_type': 'missing_file', 'severity': 'critical'}],
                 'summary': {'total_files': 2, 'critical_issues': 1, 'warning_issues': 0, 'info_issues': 0}
             }), \
             patch.object(self.command, '_output_results'):
            
            result = self.command.execute(args)
            
            assert result == 1  # Should return 1 due to critical issues
    
    @patch('flextaxd.cli.commands.validate_files.SQLiteTaxonomyRepository')
    def test_execute_no_files_found(self, mock_repo_class):
        """Test execution when no files are found."""
        mock_repo = Mock()
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_validate_files_mock_args()
        
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_collect_files_to_validate', return_value=[]):
            
            result = self.command.execute(args)
            
            assert result == 0
    
    @patch('flextaxd.cli.commands.validate_files.SQLiteTaxonomyRepository')
    def test_execute_dry_run(self, mock_repo_class):
        """Test dry run execution."""
        mock_repo = Mock()
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_validate_files_mock_args(dry_run=True)
        
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_collect_files_to_validate', return_value=create_mock_file_data()), \
             patch.object(self.command, '_show_dry_run_summary', return_value=0):
            
            result = self.command.execute(args)
            
            assert result == 0
    
    def test_collect_files_to_validate(self):
        """Test file collection from database."""
        mock_repo = Mock()
        mock_conn = Mock()
        mock_cursor = Mock()
        
        # Mock the database query result
        mock_rows = [
            (1, '/test/genome1.fna', 'genome', 'single_taxa', 1, True, 'abc123', 1024, None,
             'genome1', 562, '/test/genome1.fna', '/test/genome1.fna', True, True, True, 1024,
             'abc123', None, None)
        ]
        mock_cursor.fetchall.return_value = mock_rows
        mock_conn.execute.return_value = mock_cursor
        mock_repo._get_connection.return_value = mock_conn
        
        args = create_validate_files_mock_args()
        files = self.command._collect_files_to_validate(mock_repo, args)
        
        assert len(files) == 1
        assert files[0]['file_path'] == '/test/genome1.fna'
        assert files[0]['file_type'] == 'genome'
    
    def test_validate_single_file_exists(self):
        """Test validation of a file that exists."""
        file_info = {
            'file_path': '/test/genome1.fna',
            'file_size': 1024,
            'file_checksum': 'abc123'
        }
        
        args = create_validate_files_mock_args(level='basic')
        
        with patch('pathlib.Path.exists', return_value=True), \
             patch('pathlib.Path.is_file', return_value=True), \
             patch('pathlib.Path.stat') as mock_stat:
            
            mock_stat.return_value.st_size = 1024
            
            result = self.command._validate_single_file(file_info, args)
            
            assert result['issues'] == []
    
    def test_validate_single_file_missing(self):
        """Test validation of a missing file."""
        file_info = {
            'file_path': '/test/missing.fna',
            'file_size': 1024,
            'file_checksum': 'abc123'
        }
        
        args = create_validate_files_mock_args()
        
        with patch('pathlib.Path.exists', return_value=False):
            
            result = self.command._validate_single_file(file_info, args)
            
            assert len(result['issues']) == 1
            assert result['issues'][0]['issue_type'] == 'missing_file'
            assert result['issues'][0]['severity'] == 'critical'
    
    def test_validate_single_file_size_mismatch(self):
        """Test validation with file size mismatch."""
        file_info = {
            'file_path': '/test/genome.fna',
            'file_size': 1024,  # Expected size from database
            'file_checksum': 'abc123',
            'file_type': 'genome'
        }
        
        args = create_validate_files_mock_args(level='basic')  # Basic level to skip format validation
        
        # Mock file existence and size
        mock_stat = Mock()
        mock_stat.st_size = 2048  # Actual size differs by 1024 bytes (exactly at tolerance threshold)
        
        with patch('pathlib.Path.exists', return_value=True), \
             patch('pathlib.Path.is_file', return_value=True), \
             patch('pathlib.Path.stat', return_value=mock_stat):
            
            result = self.command._validate_single_file(file_info, args)
            
            # Should detect size mismatch (difference > 1024 tolerance)
            # Wait, 2048 - 1024 = 1024, which is exactly at the tolerance, let me make it exceed
            
        # Test with size difference that exceeds tolerance
        mock_stat.st_size = 2050  # Difference of 1026 bytes > 1024 tolerance
        
        with patch('pathlib.Path.exists', return_value=True), \
             patch('pathlib.Path.is_file', return_value=True), \
             patch('pathlib.Path.stat', return_value=mock_stat):
            
            result = self.command._validate_single_file(file_info, args)
            
            assert len(result['issues']) == 1
            assert result['issues'][0]['issue_type'] == 'size_mismatch'
            assert result['issues'][0]['severity'] == 'warning'
            assert 'expected 1024, got 2050' in result['issues'][0]['description']
    
    def test_validate_fasta_format_valid(self):
        """Test FASTA format validation with valid file."""
        with patch('builtins.open', mock_open(read_data='>sequence1\nACGT\n>sequence2\nGGCC\n')):
            issues = self.command._validate_fasta_format(Path('/test/genome.fna'), 'genome')
            
            assert issues == []
    
    def test_validate_fasta_format_invalid_characters(self):
        """Test FASTA format validation with invalid nucleotides."""
        with patch('builtins.open', mock_open(read_data='>sequence1\nACGTXYZ\n')):
            issues = self.command._validate_fasta_format(Path('/test/genome.fna'), 'genome')
            
            # Should have invalid character warning
            char_issues = [issue for issue in issues if issue['issue_type'] == 'invalid_nucleotide_characters']
            assert len(char_issues) == 1
            assert char_issues[0]['severity'] == 'warning'
    
    def test_validate_fasta_format_no_sequences(self):
        """Test FASTA format validation with no sequences."""
        with patch('builtins.open', mock_open(read_data='# This is just a comment\n')):
            issues = self.command._validate_fasta_format(Path('/test/empty.fna'), 'genome')
            
            # Should have no sequences error
            no_seq_issues = [issue for issue in issues if issue['issue_type'] == 'no_sequences']
            assert len(no_seq_issues) == 1
            assert no_seq_issues[0]['severity'] == 'critical'
    
    def test_validate_file_checksum_match(self):
        """Test checksum validation with matching checksum."""
        with patch.object(self.command, '_compute_file_checksum', return_value='abc123'):
            issues = self.command._validate_file_checksum(Path('/test/genome.fna'), 'abc123')
            
            assert issues == []
    
    def test_validate_file_checksum_mismatch(self):
        """Test checksum validation with mismatched checksum."""
        with patch.object(self.command, '_compute_file_checksum', return_value='def456'):
            issues = self.command._validate_file_checksum(Path('/test/genome.fna'), 'abc123')
            
            assert len(issues) == 1
            assert issues[0]['issue_type'] == 'checksum_mismatch'
            assert issues[0]['severity'] == 'critical'
    
    def test_extract_accessions_from_fasta(self):
        """Test accession extraction from FASTA headers."""
        fasta_content = '>GCF_000005825.2 Escherichia coli\nACGT\n>WP_000001234.1 protein\nMKLV\n'
        
        with patch('builtins.open', mock_open(read_data=fasta_content)):
            accessions = self.command._extract_accessions_from_fasta(Path('/test/genome.fna'))
            
            assert len(accessions) == 2
            assert 'GCF_000005825.2' in accessions
            assert 'WP_000001234.1' in accessions
    
    
    def test_output_text_results(self):
        """Test text output formatting."""
        results = {
            'files_validated': 10,
            'files_passed': 8,
            'files_failed': 2,
            'issues': [
                {
                    'file_path': '/test/genome1.fna',
                    'issue_type': 'missing_file',
                    'severity': 'critical',
                    'description': 'File does not exist',
                    'suggestion': 'Check file path'
                }
            ],
            'summary': {
                'total_files': 10,
                'critical_issues': 1,
                'warning_issues': 1,
                'info_issues': 0
            }
        }
        
        args = create_validate_files_mock_args()
        
        with patch('builtins.print') as mock_print:
            self.command._output_text_results(results, args)
            
            # Should print summary information
            assert mock_print.called
            print_calls = [str(call) for call in mock_print.call_args_list]
            summary_printed = any('Total files: 10' in call for call in print_calls)
            assert summary_printed
    
    def test_output_json_results(self):
        """Test JSON output."""
        results = {
            'files_validated': 5,
            'files_passed': 5,
            'files_failed': 0,
            'issues': [],
            'summary': {'total_files': 5, 'critical_issues': 0, 'warning_issues': 0, 'info_issues': 0}
        }
        
        args = create_validate_files_mock_args(format='json')
        
        with patch('builtins.print') as mock_print:
            self.command._output_json_results(results, args)
            
            # Should print JSON
            assert mock_print.called
            json_call = mock_print.call_args_list[0][0][0]
            parsed = json.loads(json_call)
            assert parsed['files_validated'] == 5
    
    def test_attempt_repairs_missing_file(self):
        """Test repair attempt for missing file."""
        issues = [
            {
                'file_path': '/test/missing.fna',
                'issue_type': 'missing_file',
                'severity': 'critical',
                'description': 'File does not exist',
                'suggestion': 'Check file path'
            }
        ]
        
        mock_repo = Mock()
        args = create_validate_files_mock_args(
            auto_repair=True,
            search_dirs='/backup,/archive'
        )
        
        with patch.object(self.command, '_repair_missing_file', return_value={
            'issue': issues[0],
            'action': 'search_missing_file',
            'success': True,
            'description': 'Found file at /backup/missing.fna'
        }):
            
            results = self.command._attempt_repairs(issues, mock_repo, args)
            
            assert results['attempted'] == 1
            assert results['successful'] == 1
            assert results['failed'] == 0
    
    def test_attempt_repairs_checksum_update(self):
        """Test repair attempt for checksum mismatch."""
        issues = [
            {
                'file_path': '/test/genome.fna',
                'issue_type': 'checksum_mismatch',
                'severity': 'critical',
                'description': 'Checksum mismatch',
                'suggestion': 'Update checksum'
            }
        ]
        
        mock_repo = Mock()
        args = create_validate_files_mock_args(
            auto_repair=True,
            update_checksums=True
        )
        
        with patch.object(self.command, '_repair_checksum_mismatch', return_value={
            'issue': issues[0],
            'action': 'update_checksum',
            'success': True,
            'description': 'Updated checksum to def456...'
        }):
            
            results = self.command._attempt_repairs(issues, mock_repo, args)
            
            assert results['attempted'] == 1
            assert results['successful'] == 1


class TestValidateFilesCommandErrorHandling:
    """Test error handling in ValidateFilesCommand."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = ValidateFilesCommand()
    
    @patch('flextaxd.cli.commands.validate_files.SQLiteTaxonomyRepository')
    def test_execute_database_error(self, mock_repo_class):
        """Test handling of database errors."""
        mock_repo_class.side_effect = DatabaseError("Database connection failed")
        
        args = create_validate_files_mock_args()
        
        result = self.command.execute(args)
        
        assert result == 1
    
    @patch('flextaxd.cli.commands.validate_files.SQLiteTaxonomyRepository')
    def test_execute_validation_error(self, mock_repo_class):
        """Test handling of validation errors."""
        args = create_validate_files_mock_args()
        
        # Simulate a validation error in database path validation
        with patch.object(self.command, '_validate_database_path', side_effect=ValidationError("Test error")):
            result = self.command.execute(args)
            
            assert result == 1
    
    def test_validate_single_file_permission_error(self):
        """Test handling of file permission errors."""
        file_info = {
            'file_path': '/test/restricted.fna',
            'file_size': 1024,
            'file_checksum': 'abc123',
            'file_type': 'genome'  # Required by _validate_fasta_format
        }
        
        args = create_validate_files_mock_args()
        
        with patch('pathlib.Path.exists', return_value=True), \
             patch('pathlib.Path.is_file', return_value=True), \
             patch('pathlib.Path.stat', side_effect=PermissionError("Access denied")):
            
            result = self.command._validate_single_file(file_info, args)
            
            # Should have size check error
            permission_issues = [issue for issue in result['issues'] if 'size_check_failed' in issue['issue_type']]
            assert len(permission_issues) == 1
    
    def test_validate_fasta_format_file_not_found(self):
        """Test FASTA validation with file not found."""
        with patch('builtins.open', side_effect=FileNotFoundError("File not found")):
            issues = self.command._validate_fasta_format(Path('/test/missing.fna'), 'genome')
            
            # Should have format validation error
            format_issues = [issue for issue in issues if issue['issue_type'] == 'format_validation_error']
            assert len(format_issues) == 1
            assert format_issues[0]['severity'] == 'warning'


class TestValidateFilesCommandIntegration:
    """Integration tests for ValidateFilesCommand."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = ValidateFilesCommand()
    
    @patch('flextaxd.cli.commands.validate_files.SQLiteTaxonomyRepository')
    def test_complete_validation_workflow(self, mock_repo_class):
        """Test complete validation workflow."""
        mock_repo = Mock()
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        # Mock file data with mix of valid and invalid files
        file_data = create_mock_file_data()
        
        args = create_validate_files_mock_args(level='comprehensive')
        
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_collect_files_to_validate', return_value=file_data), \
             patch('pathlib.Path.exists', side_effect=lambda path: str(path) != '/test/genome2.fna'), \
             patch('pathlib.Path.is_file', return_value=True), \
             patch('pathlib.Path.stat') as mock_stat, \
             patch('builtins.print'):
            
            mock_stat.return_value.st_size = 1024
            
            result = self.command.execute(args)
            
            # Should return 1 due to missing file
            assert result == 1
    
    @patch('flextaxd.cli.commands.validate_files.SQLiteTaxonomyRepository')
    def test_validation_with_auto_repair(self, mock_repo_class):
        """Test validation workflow with auto-repair enabled."""
        mock_repo = Mock()
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        file_data = create_mock_file_data()
        
        args = create_validate_files_mock_args(
            auto_repair=True,
            search_dirs='/backup',
            update_checksums=True
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_collect_files_to_validate', return_value=file_data), \
             patch('pathlib.Path.exists', return_value=False), \
             patch.object(self.command, '_repair_missing_file', return_value={
                 'issue': {}, 'action': 'search_missing_file', 'success': False,
                 'description': 'File not found in search directories'
             }), \
             patch('builtins.print'):
            
            result = self.command.execute(args)
            
            # Should still return 1 if repair failed
            assert result == 1