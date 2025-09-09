"""Unit tests for download command."""

import pytest
import argparse
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from flextaxd.cli.commands.download import DownloadCommand
from flextaxd.core.exceptions import ValidationError


@pytest.fixture
def download_command():
    """Create DownloadCommand instance."""
    return DownloadCommand()


@pytest.fixture
def mock_args():
    """Create mock arguments for download command."""
    return argparse.Namespace(
        database=Path('/test/db.ftd'),
        output_dir=Path('/test/output'),
        accessions=None,
        accession_file=None,
        missing=False,
        missing_genomes=False,
        type='genome',
        assembly_level='complete',
        max_genomes=None,
        include_proteins=False,
        batch_size=50,
        retry=3,
        update_database=True,
        no_update_database=False,
        clean_missing_paths=False,
        validate_downloads=False,
        dry_run=False,
        cache_dir=None,
        no_cache=False,
        flatten_files=True,
        keep_structure=False,
        remove_ncbi_dirs=True,
        keep_metadata=False,
        verbose=0,
        quiet=False
    )


@pytest.fixture
def mock_repository():
    """Create mock SQLiteTaxonomyRepository."""
    repo = Mock()
    repo.get_comprehensive_genome_status.return_value = {
        'summary': {
            'total_genomes': 100,
            'with_file_paths': 80,
            'without_file_paths': 20,
            'valid_files_total': 70
        },
        'missing_with_paths': [],
        'truly_missing': [],
        'downloadable_count': 30
    }
    repo.get_missing_files_analysis.return_value = {
        'missing_files': {
            'genome': [
                {'accession': 'GCF_000000001.1', 'tax_id': 1, 'tax_name': 'Test organism'}
            ]
        }
    }
    repo.clean_missing_file_paths.return_value = {
        'genomes_checked': 10,
        'paths_cleaned': 5
    }
    return repo


@pytest.fixture
def mock_datasets_manager():
    """Create mock NCBIDatasetsManager."""
    manager = Mock()
    manager.download_genomes_by_accession.return_value = {
        'downloaded': ['GCF_000000001.1'],
        'failed': [],
        'genome_files': {'GCF_000000001.1': '/test/output/genome.fna'},
        'checksums': {'/test/output/genome.fna': 'abc123'}
    }
    return manager


class TestDownloadCommand:
    """Test download command functionality."""
    
    def test_register_parser(self):
        """Test parser registration."""
        import argparse
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        
        download_parser = DownloadCommand.register_parser(subparsers)
        
        assert download_parser is not None
        # Check that the parser has the expected arguments
        assert any(action.dest == 'accessions' for action in download_parser._actions)
        assert any(action.dest == 'database' for action in download_parser._actions)
        
    def test_collect_accessions_from_command_line(self, download_command, mock_args, mock_repository):
        """Test collecting accessions from command line."""
        mock_args.accessions = "GCF_000000001.1,GCF_000000002.1"
        
        accessions = download_command._collect_accessions(mock_args, mock_repository)
        
        assert accessions == ['GCF_000000001.1', 'GCF_000000002.1']
    
    def test_collect_accessions_from_file(self, download_command, mock_args, mock_repository, tmp_path):
        """Test collecting accessions from file."""
        # Create test accession file
        accession_file = tmp_path / "accessions.txt"
        accession_file.write_text("GCF_000000001.1\nGCF_000000002.1\n# Comment\n\n")
        
        mock_args.accession_file = accession_file
        
        accessions = download_command._collect_accessions(mock_args, mock_repository)
        
        assert accessions == ['GCF_000000001.1', 'GCF_000000002.1']
    
    def test_collect_accessions_missing(self, download_command, mock_args, mock_repository):
        """Test collecting missing accessions."""
        mock_args.missing = True
        mock_args.type = 'genome'
        
        accessions = download_command._collect_accessions(mock_args, mock_repository)
        
        assert accessions == ['GCF_000000001.1']
    
    def test_collect_accessions_file_not_found(self, download_command, mock_args, mock_repository):
        """Test error when accession file doesn't exist."""
        mock_args.accession_file = Path('/nonexistent/file.txt')
        
        with pytest.raises(ValidationError, match="Accession file not found"):
            download_command._collect_accessions(mock_args, mock_repository)
    
    def test_validate_accessions(self, download_command):
        """Test accession validation."""
        accessions = [
            'GCF_000000001.1',  # Valid assembly (9 digits)
            'NC_000001.1',      # Valid nucleotide
            'WP_000001.1',      # Valid protein
            'invalid_acc'       # Invalid
        ]
        
        valid = download_command._validate_accessions(accessions)
        
        assert valid == ['GCF_000000001.1', 'NC_000001.1', 'WP_000001.1']
    
    def test_is_valid_accession(self, download_command):
        """Test individual accession validation."""
        # Assembly accessions (need 9 digits)
        assert download_command._is_valid_accession('GCF_000001405.38')
        assert download_command._is_valid_accession('GCA_000001405.38')
        
        # Nucleotide accessions
        assert download_command._is_valid_accession('NC_000913.3')
        assert download_command._is_valid_accession('NZ_CP009273.1')
        
        # Protein accessions
        assert download_command._is_valid_accession('WP_000001234.1')
        assert download_command._is_valid_accession('YP_000001234.1')
        
        # Invalid accessions
        assert not download_command._is_valid_accession('invalid')
        assert not download_command._is_valid_accession('GCF_000001.1')  # Wrong number of digits (need 9)
        assert not download_command._is_valid_accession('GCF_000001')  # Missing version
    
    def test_simulate_accession_download(self, download_command, mock_args):
        """Test download simulation."""
        accessions = ['GCF_000000001.1', 'NC_000002.1', 'WP_000003.1']
        
        result = download_command._simulate_accession_download(accessions, mock_args)
        
        assert result['count'] == 3
        assert result['assembly_count'] == 1
        assert result['nucleotide_count'] == 1
        assert result['protein_count'] == 1
    
    def test_get_tax_id_for_accession(self, download_command, mock_repository):
        """Test getting taxonomy ID for accession."""
        # Mock database connection and cursor
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = (12345,)
        mock_conn.execute.return_value = mock_cursor
        mock_repository._get_connection.return_value = mock_conn
        
        tax_id = download_command._get_tax_id_for_accession(mock_repository, 'GCF_000000001.1')
        
        assert tax_id == 12345
        mock_conn.execute.assert_called_once()
    
    def test_get_tax_id_for_accession_not_found(self, download_command, mock_repository):
        """Test getting taxonomy ID when accession not found."""
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = None
        mock_conn.execute.return_value = mock_cursor
        mock_repository._get_connection.return_value = mock_conn
        
        tax_id = download_command._get_tax_id_for_accession(mock_repository, 'GCF_999999999.1')
        
        assert tax_id is None
    
    @patch('flextaxd.cli.commands.download.check_ncbi_datasets_installation')
    @patch('flextaxd.cli.commands.download.NCBIDatasetsManager')  
    @patch('flextaxd.cli.commands.download.SQLiteTaxonomyRepository')
    def test_execute_dry_run(self, mock_repo_class, mock_manager_class, mock_install_check, 
                           download_command, mock_args):
        """Test execute with dry run."""
        # Setup mocks
        mock_install_check.return_value = {'installed': True}
        mock_repo = Mock()
        mock_repo_class.return_value = mock_repo
        mock_manager = Mock()
        mock_manager_class.return_value = mock_manager
        
        # Set arguments for dry run
        mock_args.dry_run = True
        mock_args.accessions = "GCF_000000001.1"  # Use proper 9-digit format
        mock_args.database = Mock()
        mock_args.database.exists.return_value = True
        mock_args.clean_missing_paths = False
        mock_args.missing = False
        mock_args.missing_genomes = False
        mock_args.accession_file = None
        
        # Mock path operations
        with patch.object(Path, 'mkdir'), patch.object(Path, 'touch'), patch.object(Path, 'unlink'):
            result = download_command.execute(mock_args)
        
        assert result == 0
        mock_install_check.assert_called_once()
    
    @patch('flextaxd.cli.commands.download.check_ncbi_datasets_installation')
    def test_execute_missing_ncbi_datasets(self, mock_install_check, download_command, mock_args):
        """Test execute when NCBI Datasets is not installed."""
        mock_install_check.return_value = {'installed': False, 'error': 'Command not found'}
        
        result = download_command.execute(mock_args)
        
        assert result == 1
    
    @patch('flextaxd.cli.commands.download.check_ncbi_datasets_installation')
    @patch('flextaxd.cli.commands.download.SQLiteTaxonomyRepository')
    def test_execute_database_not_found(self, mock_repo_class, mock_install_check, 
                                       download_command, mock_args):
        """Test execute when database doesn't exist."""
        mock_install_check.return_value = {'installed': True}
        mock_args.database = Mock()
        mock_args.database.exists.return_value = False
        
        result = download_command.execute(mock_args)
        
        assert result == 1
    
    @patch('flextaxd.cli.commands.download.check_ncbi_datasets_installation')
    @patch('flextaxd.cli.commands.download.SQLiteTaxonomyRepository')
    def test_execute_no_download_target(self, mock_repo_class, mock_install_check, 
                                       download_command, mock_args):
        """Test execute when no download target is specified."""
        mock_install_check.return_value = {'installed': True}
        mock_args.database = Mock()
        mock_args.database.exists.return_value = True
        
        # No download target specified
        mock_args.accessions = None
        mock_args.accession_file = None
        mock_args.missing = False
        mock_args.missing_genomes = False
        mock_args.clean_missing_paths = False
        
        result = download_command.execute(mock_args)
        
        assert result == 1
    
    def test_handle_clean_missing_paths(self, download_command, mock_args, mock_repository):
        """Test handling clean missing paths option."""
        mock_repository.get_comprehensive_genome_status.return_value = {
            'missing_with_paths': [
                {
                    'assembly_accession': 'GCF_000000001.1',
                    'file_path': '/missing/file.fna',
                    'file_actually_exists': False
                }
            ]
        }
        
        # Mock user input
        with patch('builtins.input', return_value='y'), patch('sys.stdin.isatty', return_value=True):
            result = download_command._handle_clean_missing_paths(mock_args, mock_repository)
        
        assert result == 0
        mock_repository.clean_missing_file_paths.assert_called_once_with(verify_files=True)
    
    def test_handle_clean_missing_paths_no_paths_to_clean(self, download_command, mock_args, mock_repository):
        """Test clean missing paths when no paths need cleaning."""
        mock_repository.get_comprehensive_genome_status.return_value = {
            'missing_with_paths': []
        }
        
        result = download_command._handle_clean_missing_paths(mock_args, mock_repository)
        
        assert result == 0
        mock_repository.clean_missing_file_paths.assert_not_called()
    
    def test_download_assemblies(self, download_command, mock_datasets_manager, mock_args):
        """Test downloading genome assemblies."""
        accessions = ['GCF_000000001.1', 'GCF_000000002.1']
        
        result = download_command._download_assemblies(accessions, mock_datasets_manager, mock_args)
        
        assert result['downloaded'] == 1
        assert result['failed'] == 0
        assert len(result['genomes']) == 1
        mock_datasets_manager.download_genomes_by_accession.assert_called_once()
    
    def test_update_database_with_downloads(self, download_command, mock_repository, mock_args):
        """Test updating database with downloaded genomes."""
        genomes = [{
            'genome_id': 'GCF_000000001.1',
            'assembly_accession': 'GCF_000000001.1',
            'file_path': '/test/genome.fna',
            'source': 'NCBI',
            'sequence_type': 'genome'
        }]
        
        # Mock _get_tax_id_for_accession
        with patch.object(download_command, '_get_tax_id_for_accession', return_value=12345):
            download_command._update_database_with_downloads(genomes, mock_repository, mock_args)
        
        mock_repository.add_genome.assert_called_once()
    
    def test_get_missing_accessions_by_type(self, download_command, mock_repository):
        """Test getting missing accessions by type."""
        accessions = download_command._get_missing_accessions_by_type(mock_repository, 'genome')
        
        assert accessions == ['GCF_000000001.1']
        mock_repository.get_missing_files_analysis.assert_called_once()
    
    def test_print_genome_status_report(self, download_command, capsys):
        """Test printing genome status report."""
        status = {
            'summary': {
                'total_genomes': 100,
                'with_file_paths': 80,
                'without_file_paths': 20,
                'valid_files_total': 70
            },
            'missing_with_paths': [
                {
                    'assembly_accession': 'GCF_000000001.1',
                    'file_path': '/missing/file.fna',
                    'file_actually_exists': False
                }
            ],
            'truly_missing': [
                {
                    'accession': 'GCF_000000002.1',
                    'tax_name': 'Test organism'
                }
            ]
        }
        
        download_command._print_genome_status_report(status)
        
        captured = capsys.readouterr()
        assert "Genome File Status Report" in captured.out
        assert "Total genomes in database: 100" in captured.out
        assert "Genomes with missing files: 1" in captured.out
        assert "Downloadable genomes: 1" in captured.out


class TestDownloadCommandEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_collect_accessions_empty_list(self, download_command, mock_args, mock_repository):
        """Test collecting empty accession list."""
        mock_args.accessions = ""
        
        accessions = download_command._collect_accessions(mock_args, mock_repository)
        
        assert accessions == []
    
    def test_collect_accessions_with_duplicates(self, download_command, mock_args, mock_repository):
        """Test collecting accessions with duplicates."""
        mock_args.accessions = "GCF_000000001.1,GCF_000000002.1,GCF_000000001.1"
        
        accessions = download_command._collect_accessions(mock_args, mock_repository)
        
        assert accessions == ['GCF_000000001.1', 'GCF_000000002.1']
    
    def test_download_assemblies_failure(self, download_command, mock_args):
        """Test assembly download failure."""
        mock_manager = Mock()
        mock_manager.download_genomes_by_accession.side_effect = Exception("Download failed")
        
        result = download_command._download_assemblies(['GCF_000000001.1'], mock_manager, mock_args)
        
        assert result['downloaded'] == 0
        assert result['failed'] == 1
        assert result['genomes'] == []
    
    def test_validate_accessions_all_invalid(self, download_command):
        """Test validation with all invalid accessions."""
        accessions = ['invalid1', 'invalid2', 'invalid3']
        
        valid = download_command._validate_accessions(accessions)
        
        assert valid == []
    
    @patch('flextaxd.cli.commands.download.check_ncbi_datasets_installation')  
    @patch('flextaxd.cli.commands.download.SQLiteTaxonomyRepository')
    @patch('flextaxd.cli.commands.download.NCBIDatasetsManager')
    def test_execute_keyboard_interrupt(self, mock_manager_class, mock_repo_class, mock_install_check, download_command, mock_args):
        """Test graceful handling of keyboard interrupt."""
        mock_install_check.return_value = {'installed': True}
        mock_args.database = Mock()
        mock_args.database.exists.return_value = True
        mock_args.clean_missing_paths = False
        
        # Set missing=True to pass validation and get to _collect_accessions
        mock_args.missing = True
        
        # Mock the repository and manager classes
        mock_repo = Mock()
        mock_repo_class.return_value = mock_repo
        mock_manager = Mock()
        mock_manager_class.return_value = mock_manager
        
        # Patch the collect_accessions method to raise KeyboardInterrupt
        with patch.object(download_command, '_collect_accessions', side_effect=KeyboardInterrupt):
            result = download_command.execute(mock_args)
        
        assert result == 130  # Standard SIGINT exit code
    
    @patch('flextaxd.cli.commands.download.check_ncbi_datasets_installation')
    def test_execute_unexpected_error(self, mock_install_check, download_command, mock_args):
        """Test handling of unexpected errors."""
        mock_install_check.side_effect = Exception("Unexpected error")
        
        result = download_command.execute(mock_args)
        
        assert result == 1