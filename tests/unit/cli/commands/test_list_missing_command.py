"""Test cases for ListMissingCommand."""

import pytest
import argparse
from pathlib import Path
from unittest.mock import Mock, patch, mock_open
import json
import csv
import io

from flextaxd.cli.commands.list_missing import ListMissingCommand
from flextaxd.core.exceptions import ValidationError, DatabaseError


def create_list_missing_mock_args(**overrides):
    """Create complete mock args for ListMissingCommand."""
    defaults = {
        'database': Path('/test/db.ftd'),
        'type': 'genome',
        'output': None,
        'format': 'simple',
        'include_tax_id': False,
        'verbose': False,
        'quiet': False
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def create_mock_missing_analysis():
    """Create mock missing files analysis data."""
    return {
        'missing_files': {
            'genome': [
                {
                    'accession': 'GCF_000001405.38',
                    'accession_version': 'GCF_000001405.38',
                    'tax_id': 9606,
                    'type': 'genome',
                    'description': 'Homo sapiens reference genome'
                },
                {
                    'accession': 'GCF_000005825.2',
                    'accession_version': 'GCF_000005825.2',
                    'tax_id': 562,
                    'type': 'genome',
                    'description': 'Escherichia coli K-12 MG1655'
                }
            ],
            'protein': [
                {
                    'accession': 'WP_000001234.1',
                    'accession_version': 'WP_000001234.1',
                    'tax_id': 562,
                    'type': 'protein',
                    'description': 'hypothetical protein'
                }
            ],
            'nucleotide': []
        },
        'summary': {
            'total_accessions': 100,
            'missing_genome_files': 2,
            'missing_protein_files': 1,
            'missing_nucleotide_files': 0
        }
    }


class TestListMissingCommand:
    """Test ListMissingCommand functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = ListMissingCommand()
    
    def test_initialization(self):
        """Test command initialization."""
        assert self.command is not None
        assert hasattr(self.command, 'logger')
    
    def test_register_parser(self):
        """Test parser registration."""
        mock_subparsers = Mock()
        mock_parser = Mock()
        mock_subparsers.add_parser.return_value = mock_parser
        
        parser = ListMissingCommand.register_parser(mock_subparsers)
        
        # Verify parser was created
        mock_subparsers.add_parser.assert_called_once()
        call_args = mock_subparsers.add_parser.call_args
        assert call_args[0][0] == "list-missing"
        
        # Verify arguments were added
        assert mock_parser.add_argument.called
        
        # Check for key arguments
        arg_calls = [str(call) for call in mock_parser.add_argument.call_args_list]
        database_arg = any('--database' in call for call in arg_calls)
        type_arg = any('--type' in call for call in arg_calls)
        output_arg = any('--output' in call for call in arg_calls)
        format_arg = any('--format' in call for call in arg_calls)
        
        assert database_arg
        assert type_arg
        assert output_arg
        assert format_arg
    
    @patch('flextaxd.cli.commands.list_missing.SQLiteTaxonomyRepository')
    def test_execute_basic_list_genome(self, mock_repo_class):
        """Test basic execution for listing missing genomes."""
        mock_repo = Mock()
        mock_repo.get_missing_files_analysis.return_value = create_mock_missing_analysis()
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_list_missing_mock_args(type='genome')
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('sys.stdout', new_callable=io.StringIO) as mock_stdout, \
             patch('sys.stderr', new_callable=io.StringIO):
            
            result = self.command.execute(args)
            
            assert result == 0
            output = mock_stdout.getvalue()
            assert 'GCF_000001405.38' in output
            assert 'GCF_000005825.2' in output
    
    @patch('flextaxd.cli.commands.list_missing.SQLiteTaxonomyRepository')
    def test_execute_list_protein(self, mock_repo_class):
        """Test execution for listing missing proteins."""
        mock_repo = Mock()
        mock_repo.get_missing_files_analysis.return_value = create_mock_missing_analysis()
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_list_missing_mock_args(type='protein')
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('sys.stdout', new_callable=io.StringIO) as mock_stdout, \
             patch('sys.stderr', new_callable=io.StringIO):
            
            result = self.command.execute(args)
            
            assert result == 0
            output = mock_stdout.getvalue()
            assert 'WP_000001234.1' in output
    
    @patch('flextaxd.cli.commands.list_missing.SQLiteTaxonomyRepository')
    def test_execute_list_all(self, mock_repo_class):
        """Test execution for listing all missing files."""
        mock_repo = Mock()
        mock_repo.get_missing_files_analysis.return_value = create_mock_missing_analysis()
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_list_missing_mock_args(type='all')
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('sys.stdout', new_callable=io.StringIO) as mock_stdout, \
             patch('sys.stderr', new_callable=io.StringIO):
            
            result = self.command.execute(args)
            
            assert result == 0
            output = mock_stdout.getvalue()
            assert 'GCF_000001405.38' in output  # Genome
            assert 'WP_000001234.1' in output    # Protein
    
    @patch('flextaxd.cli.commands.list_missing.SQLiteTaxonomyRepository')
    def test_execute_no_missing_files(self, mock_repo_class):
        """Test execution when no missing files found."""
        mock_repo = Mock()
        empty_analysis = {
            'missing_files': {'genome': [], 'protein': [], 'nucleotide': []},
            'summary': {'total_accessions': 10, 'missing_genome_files': 0}
        }
        mock_repo.get_missing_files_analysis.return_value = empty_analysis
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_list_missing_mock_args(type='genome')
        
        with patch.object(self.command, '_validate_database_path'):
            result = self.command.execute(args)
            
            assert result == 0
    
    @patch('flextaxd.cli.commands.list_missing.SQLiteTaxonomyRepository')
    def test_execute_with_output_file(self, mock_repo_class):
        """Test execution with output to file."""
        mock_repo = Mock()
        mock_repo.get_missing_files_analysis.return_value = create_mock_missing_analysis()
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        output_file = Path('/test/missing.txt')
        args = create_list_missing_mock_args(type='genome', output=output_file)
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('builtins.open', mock_open()) as mock_file:
            
            result = self.command.execute(args)
            
            assert result == 0
            mock_file.assert_called_once_with(output_file, 'w')
    
    @patch('flextaxd.cli.commands.list_missing.SQLiteTaxonomyRepository')
    def test_execute_detailed_format(self, mock_repo_class):
        """Test execution with detailed output format."""
        mock_repo = Mock()
        mock_repo.get_missing_files_analysis.return_value = create_mock_missing_analysis()
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_list_missing_mock_args(type='genome', format='detailed')
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('sys.stdout', new_callable=io.StringIO) as mock_stdout, \
             patch('sys.stderr', new_callable=io.StringIO):
            
            result = self.command.execute(args)
            
            assert result == 0
            output = mock_stdout.getvalue()
            # Should contain CSV header
            assert 'accession,accession_version,tax_id,type' in output
            assert 'GCF_000001405.38,GCF_000001405.38,9606,genome' in output
    
    @patch('flextaxd.cli.commands.list_missing.SQLiteTaxonomyRepository')
    def test_execute_json_format(self, mock_repo_class):
        """Test execution with JSON output format."""
        mock_repo = Mock()
        mock_repo.get_missing_files_analysis.return_value = create_mock_missing_analysis()
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_list_missing_mock_args(type='genome', format='json')
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('sys.stdout', new_callable=io.StringIO) as mock_stdout, \
             patch('sys.stderr', new_callable=io.StringIO):
            
            result = self.command.execute(args)
            
            assert result == 0
            output = mock_stdout.getvalue()
            # Should be valid JSON
            parsed = json.loads(output)
            assert 'missing_files' in parsed
            assert 'summary' in parsed
    
    @patch('flextaxd.cli.commands.list_missing.SQLiteTaxonomyRepository')
    def test_execute_with_tax_id(self, mock_repo_class):
        """Test execution with taxonomy ID inclusion."""
        mock_repo = Mock()
        mock_repo.get_missing_files_analysis.return_value = create_mock_missing_analysis()
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_list_missing_mock_args(type='genome', include_tax_id=True)
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('sys.stdout', new_callable=io.StringIO) as mock_stdout, \
             patch('sys.stderr', new_callable=io.StringIO):
            
            result = self.command.execute(args)
            
            assert result == 0
            output = mock_stdout.getvalue()
            # Should include tab-separated tax_ids
            assert 'GCF_000001405.38\t9606' in output
            assert 'GCF_000005825.2\t562' in output
    
    def test_extract_missing_by_type_genome(self):
        """Test extraction of missing files by type (genome)."""
        analysis = create_mock_missing_analysis()
        
        result = self.command._extract_missing_by_type(analysis, 'genome')
        
        assert 'genome' in result
        assert len(result['genome']) == 2
        assert result['genome'][0]['accession'] == 'GCF_000001405.38'
        assert result['genome'][1]['accession'] == 'GCF_000005825.2'
    
    def test_extract_missing_by_type_protein(self):
        """Test extraction of missing files by type (protein)."""
        analysis = create_mock_missing_analysis()
        
        result = self.command._extract_missing_by_type(analysis, 'protein')
        
        assert 'protein' in result
        assert len(result['protein']) == 1
        assert result['protein'][0]['accession'] == 'WP_000001234.1'
    
    def test_extract_missing_by_type_all(self):
        """Test extraction of missing files by type (all)."""
        analysis = create_mock_missing_analysis()
        
        result = self.command._extract_missing_by_type(analysis, 'all')
        
        assert 'all' in result
        assert len(result['all']) == 3  # 2 genomes + 1 protein
        
        # Should add missing_type to entries
        accessions = [item['accession'] for item in result['all']]
        assert 'GCF_000001405.38' in accessions
        assert 'GCF_000005825.2' in accessions
        assert 'WP_000001234.1' in accessions
    
    def test_extract_missing_by_type_nucleotide(self):
        """Test extraction of missing files by type (nucleotide)."""
        analysis = create_mock_missing_analysis()
        
        result = self.command._extract_missing_by_type(analysis, 'nucleotide')
        
        assert 'nucleotide' in result
        assert len(result['nucleotide']) == 0  # No missing nucleotides in test data
    
    def test_output_simple_format(self):
        """Test simple format output."""
        missing_files = {
            'genome': [
                {'accession': 'GCF_000001405.38', 'tax_id': 9606},
                {'accession': 'GCF_000005825.2', 'tax_id': 562}
            ]
        }
        
        output_buffer = io.StringIO()
        
        self.command._output_simple_format(missing_files, output_buffer, include_tax_id=False)
        
        output = output_buffer.getvalue()
        lines = output.strip().split('\n')
        assert len(lines) == 2
        assert 'GCF_000001405.38' in lines[0]
        assert 'GCF_000005825.2' in lines[1]
    
    def test_output_simple_format_with_tax_id(self):
        """Test simple format output with taxonomy IDs."""
        missing_files = {
            'genome': [
                {'accession': 'GCF_000001405.38', 'tax_id': 9606},
                {'accession': 'GCF_000005825.2', 'tax_id': 562}
            ]
        }
        
        output_buffer = io.StringIO()
        
        self.command._output_simple_format(missing_files, output_buffer, include_tax_id=True)
        
        output = output_buffer.getvalue()
        assert 'GCF_000001405.38\t9606' in output
        assert 'GCF_000005825.2\t562' in output
    
    def test_output_detailed_format(self):
        """Test detailed CSV format output."""
        missing_files = {
            'genome': [
                {
                    'accession': 'GCF_000001405.38',
                    'accession_version': 'GCF_000001405.38',
                    'tax_id': 9606,
                    'missing_type': 'genome'
                }
            ]
        }
        
        output_buffer = io.StringIO()
        
        self.command._output_detailed_format(missing_files, output_buffer)
        
        output = output_buffer.getvalue()
        lines = output.strip().split('\n')
        assert len(lines) == 2  # Header + 1 data line
        assert lines[0] == 'accession,accession_version,tax_id,type'
        assert 'GCF_000001405.38,GCF_000001405.38,9606,genome' in lines[1]
    
    def test_output_json_format(self):
        """Test JSON format output."""
        missing_files = {
            'genome': [
                {'accession': 'GCF_000001405.38', 'tax_id': 9606}
            ]
        }
        
        output_buffer = io.StringIO()
        
        self.command._output_json_format(missing_files, output_buffer)
        
        output = output_buffer.getvalue()
        parsed = json.loads(output)
        
        assert 'missing_files' in parsed
        assert 'summary' in parsed
        assert parsed['summary']['genome_count'] == 1


class TestListMissingCommandErrorHandling:
    """Test error handling in ListMissingCommand."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = ListMissingCommand()
    
    def test_execute_missing_database(self):
        """Test handling of missing database."""
        args = create_list_missing_mock_args(database=Path('/nonexistent/db.ftd'))
        
        result = self.command.execute(args)
        
        assert result == 1
    
    @patch('flextaxd.cli.commands.list_missing.SQLiteTaxonomyRepository')
    def test_execute_database_error(self, mock_repo_class):
        """Test handling of database errors."""
        mock_repo_class.side_effect = DatabaseError("Database connection failed")
        
        args = create_list_missing_mock_args()
        
        with patch.object(self.command, '_validate_database_path'):
            result = self.command.execute(args)
            
            assert result == 1
    
    @patch('flextaxd.cli.commands.list_missing.SQLiteTaxonomyRepository')
    def test_execute_validation_error(self, mock_repo_class):
        """Test handling of validation errors."""
        mock_repo = Mock()
        mock_repo.get_missing_files_analysis.side_effect = ValidationError("Validation failed")
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_list_missing_mock_args()
        
        with patch.object(self.command, '_validate_database_path'):
            result = self.command.execute(args)
            
            assert result == 1
    
    @patch('flextaxd.cli.commands.list_missing.SQLiteTaxonomyRepository')
    def test_execute_unexpected_error(self, mock_repo_class):
        """Test handling of unexpected errors."""
        mock_repo = Mock()
        mock_repo.get_missing_files_analysis.side_effect = Exception("Unexpected error")
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_list_missing_mock_args()
        
        with patch.object(self.command, '_validate_database_path'):
            result = self.command.execute(args)
            
            assert result == 1
    
    @patch('flextaxd.cli.commands.list_missing.SQLiteTaxonomyRepository')
    def test_output_file_permission_error(self, mock_repo_class):
        """Test handling of output file permission errors."""
        mock_repo = Mock()
        mock_repo.get_missing_files_analysis.return_value = create_mock_missing_analysis()
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_list_missing_mock_args(output=Path('/test/readonly.txt'))
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('builtins.open', side_effect=PermissionError("Permission denied")):
            
            result = self.command.execute(args)
            
            assert result == 1


class TestListMissingCommandIntegration:
    """Integration tests for ListMissingCommand."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = ListMissingCommand()
    
    @patch('flextaxd.cli.commands.list_missing.SQLiteTaxonomyRepository')
    def test_complete_workflow_simple_format(self, mock_repo_class):
        """Test complete workflow with simple format output."""
        mock_repo = Mock()
        mock_repo.get_missing_files_analysis.return_value = create_mock_missing_analysis()
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_list_missing_mock_args(
            type='genome',
            format='simple',
            include_tax_id=True
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('sys.stdout', new_callable=io.StringIO) as mock_stdout, \
             patch('sys.stderr', new_callable=io.StringIO) as mock_stderr:
            
            # Set the name attribute for stdout mock to trigger stderr logging
            mock_stdout.name = '<stdout>'
            
            result = self.command.execute(args)
            
            assert result == 0
            
            stdout_output = mock_stdout.getvalue()
            stderr_output = mock_stderr.getvalue()
            
            # Check stdout contains accessions with tax_ids
            assert 'GCF_000001405.38\t9606' in stdout_output
            assert 'GCF_000005825.2\t562' in stdout_output
            
            # Check stderr contains summary
            assert '# Found 2 missing files' in stderr_output
    
    @patch('flextaxd.cli.commands.list_missing.SQLiteTaxonomyRepository')
    def test_complete_workflow_detailed_format(self, mock_repo_class):
        """Test complete workflow with detailed format output."""
        mock_repo = Mock()
        mock_repo.get_missing_files_analysis.return_value = create_mock_missing_analysis()
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        output_file = Path('/test/detailed.csv')
        args = create_list_missing_mock_args(
            type='all',
            format='detailed',
            output=output_file
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('builtins.open', mock_open()) as mock_file, \
             patch('sys.stderr', new_callable=io.StringIO):
            
            result = self.command.execute(args)
            
            assert result == 0
            mock_file.assert_called_once_with(output_file, 'w')
            
            # Check that CSV content was written
            handle = mock_file.return_value.__enter__.return_value
            write_calls = [call[0][0] for call in handle.write.call_args_list]
            csv_content = ''.join(write_calls)
            
            assert 'accession,accession_version,tax_id,type' in csv_content
            assert 'GCF_000001405.38' in csv_content
            assert 'WP_000001234.1' in csv_content
    
    @patch('flextaxd.cli.commands.list_missing.SQLiteTaxonomyRepository')
    def test_complete_workflow_json_format(self, mock_repo_class):
        """Test complete workflow with JSON format output."""
        mock_repo = Mock()
        mock_repo.get_missing_files_analysis.return_value = create_mock_missing_analysis()
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        output_file = Path('/test/missing.json')
        args = create_list_missing_mock_args(
            type='genome',
            format='json',
            output=output_file
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('builtins.open', mock_open()) as mock_file, \
             patch('sys.stderr', new_callable=io.StringIO):
            
            result = self.command.execute(args)
            
            assert result == 0
            
            # Verify JSON content structure
            handle = mock_file.return_value.__enter__.return_value
            write_calls = handle.write.call_args_list
            
            # Should have written JSON content
            assert len(write_calls) >= 1