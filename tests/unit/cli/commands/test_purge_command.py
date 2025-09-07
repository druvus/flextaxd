"""Comprehensive unit tests for PurgeCommand."""

import pytest
import argparse
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from flextaxd.cli.commands.purge import PurgeCommand
from flextaxd.core.exceptions import ValidationError, DatabaseError
from flextaxd.core.models import TaxonomyTree

from ....fixtures.cli.conftest import *
from ....fixtures.cli.mock_data import MockData, CLITestHelper


def create_purge_mock_args(**overrides):
    """Create complete mock args for PurgeCommand with all required attributes."""
    defaults = {
        'database': '/test/db.ftd',
        'backup': None,
        'dry_run': False,
        'allow_metadata_only': False,
        'force': False,
        'stats_only': False,
        'verbose': False,
        'quiet': False,
        'skip_validation': True  # For test isolation
    }
    defaults.update(overrides)
    return CLITestHelper.create_mock_args(**defaults)


class TestPurgeCommand:
    """Test PurgeCommand functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = PurgeCommand()
    
    def test_register_parser(self):
        """Test parser registration."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        
        result_parser = PurgeCommand.register_parser(subparsers)
        
        assert result_parser is not None
        assert result_parser.prog.endswith('purge')
    
    @patch('flextaxd.cli.commands.purge.SQLiteTaxonomyRepository')
    def test_execute_dry_run(self, mock_repo_class):
        """Test dry run execution."""
        mock_repo = Mock()
        mock_repo_class.return_value.__enter__ = Mock(return_value=mock_repo)
        mock_repo_class.return_value.__exit__ = Mock(return_value=None)
        
        # Mock tree with some nodes
        mock_tree = Mock()
        mock_tree.get_tree_statistics.return_value = {'node_count': 100, 'genome_count': 50}
        mock_repo.load_tree.return_value = mock_tree
        
        # Mock command methods
        self.command._validate_database_path = Mock()
        self.command._validate_purge_safety = Mock()
        self.command._analyze_purge_impact = Mock(return_value={
            'nodes_before': 100,
            'nodes_after': 75,
            'nodes_removed': 25,
            'genomes_retained': 50
        })
        self.command._display_purge_analysis = Mock()
        
        args = create_purge_mock_args(dry_run=True)
        
        result = self.command.execute(args)
        
        assert result == 0
        self.command._analyze_purge_impact.assert_called_once()
        self.command._display_purge_analysis.assert_called_once()
    
    @patch('flextaxd.cli.commands.purge.SQLiteTaxonomyRepository')
    def test_execute_with_backup(self, mock_repo_class):
        """Test execution with backup creation."""
        mock_repo = Mock()
        mock_repo_class.return_value.__enter__ = Mock(return_value=mock_repo)
        mock_repo_class.return_value.__exit__ = Mock(return_value=None)
        
        # Mock tree
        mock_tree = Mock()
        mock_tree.get_tree_statistics.return_value = {'node_count': 100, 'genome_count': 50}
        mock_tree.purge_nodes_without_genomes.return_value = {
            'nodes_before': 100,
            'nodes_after': 75,
            'nodes_removed': 25
        }
        mock_repo.load_tree.return_value = mock_tree
        
        # Mock command methods
        self.command._validate_database_path = Mock()
        self.command._validate_purge_safety = Mock()
        self.command._create_backup = Mock()
        self.command._display_purge_results = Mock()
        
        args = create_purge_mock_args(backup='/test/backup.ftd', force=True)
        
        result = self.command.execute(args)
        
        assert result == 0
        self.command._create_backup.assert_called_once_with(args.database, args.backup)
        mock_repo.save_tree.assert_called_once_with(mock_tree)
    
    @patch('flextaxd.cli.commands.purge.SQLiteTaxonomyRepository')
    def test_execute_stats_only(self, mock_repo_class):
        """Test stats-only execution."""
        mock_repo = Mock()
        mock_repo_class.return_value.__enter__ = Mock(return_value=mock_repo)
        mock_repo_class.return_value.__exit__ = Mock(return_value=None)
        
        # Mock tree
        mock_tree = Mock()
        mock_tree.get_tree_statistics.return_value = {'node_count': 100, 'genome_count': 50}
        mock_repo.load_tree.return_value = mock_tree
        
        # Mock command methods  
        self.command._validate_database_path = Mock()
        self.command._validate_purge_safety = Mock()
        self.command._analyze_purge_impact = Mock(return_value={
            'nodes_before': 100,
            'nodes_after': 75,
            'nodes_removed': 25
        })
        self.command._display_purge_analysis = Mock()
        
        args = create_purge_mock_args(stats_only=True)
        
        result = self.command.execute(args)
        
        assert result == 0
        self.command._analyze_purge_impact.assert_called_once()
        self.command._display_purge_analysis.assert_called_once()
    
    @patch('flextaxd.cli.commands.purge.SQLiteTaxonomyRepository')
    def test_execute_allow_metadata_only(self, mock_repo_class):
        """Test execution with metadata-only genomes allowed."""
        mock_repo = Mock()
        mock_repo_class.return_value.__enter__ = Mock(return_value=mock_repo)
        mock_repo_class.return_value.__exit__ = Mock(return_value=None)
        
        # Mock tree
        mock_tree = Mock()
        mock_tree.get_tree_statistics.return_value = {'node_count': 100, 'genome_count': 50}
        mock_tree.purge_nodes_without_genomes.return_value = {
            'nodes_before': 100,
            'nodes_after': 80,
            'nodes_removed': 20
        }
        mock_repo.load_tree.return_value = mock_tree
        
        # Mock command methods
        self.command._validate_database_path = Mock()
        self.command._validate_purge_safety = Mock()
        self.command._display_purge_results = Mock()
        
        args = create_purge_mock_args(allow_metadata_only=True, force=True)
        
        result = self.command.execute(args)
        
        assert result == 0
        mock_tree.purge_nodes_without_genomes.assert_called_once_with(
            require_fasta_files=False,
            force=True
        )
    
    @patch('flextaxd.cli.commands.purge.SQLiteTaxonomyRepository')
    def test_execute_database_error(self, mock_repo_class):
        """Test handling of database errors."""
        mock_repo = Mock()
        mock_repo_class.return_value = mock_repo
        mock_repo.load_tree.side_effect = DatabaseError("Database connection failed")
        
        args = create_purge_mock_args()
        
        result = self.command.execute(args)
        
        assert result == 1
    
    @patch('flextaxd.cli.commands.purge.SQLiteTaxonomyRepository')
    @patch('flextaxd.cli.commands.purge.Path')
    def test_execute_missing_database(self, mock_path, mock_repo_class):
        """Test handling of missing database file."""
        mock_db_path = Mock()
        mock_path.return_value = mock_db_path
        mock_db_path.exists.return_value = False
        
        args = create_purge_mock_args()
        
        result = self.command.execute(args)
        
        assert result == 1
    
    @patch('flextaxd.cli.commands.purge.SQLiteTaxonomyRepository')
    @patch('flextaxd.cli.commands.purge.Path')
    def test_execute_backup_exists_no_force(self, mock_path, mock_repo_class):
        """Test handling of existing backup without force flag."""
        mock_db_path = Mock()
        mock_backup_path = Mock()
        mock_path.side_effect = lambda x: mock_db_path if 'db.ftd' in str(x) else mock_backup_path
        
        mock_db_path.exists.return_value = True
        mock_backup_path.exists.return_value = True
        
        args = create_purge_mock_args(backup='/test/backup.ftd')
        
        result = self.command.execute(args)
        
        assert result == 1
    
    @patch('flextaxd.cli.commands.purge.SQLiteTaxonomyRepository')
    def test_execute_safety_check_too_many_removals(self, mock_repo_class):
        """Test safety check preventing excessive node removal."""
        mock_repo = Mock()
        mock_repo_class.return_value = mock_repo
        
        mock_tree = Mock()
        mock_tree.node_count = 100
        mock_tree.genome_count = 2  # Very few genomes
        mock_repo.load_tree.return_value = mock_tree
        
        # Simulate removing 98% of nodes (unsafe)
        purge_result = {
            'nodes_before': 100,
            'nodes_after': 2,
            'nodes_removed': 98,
            'genomes_retained': 2,
            'lineages_preserved': 2,
            'nodes_with_genomes': 2,
            'essential_nodes_kept': 2
        }
        mock_tree.purge_nodes_without_genomes.return_value = purge_result
        
        args = create_purge_mock_args()  # No force flag
        
        result = self.command.execute(args)
        
        assert result == 1  # Should fail safety check
    
    @patch('flextaxd.cli.commands.purge.SQLiteTaxonomyRepository')
    def test_execute_safety_check_with_force(self, mock_repo_class):
        """Test safety check bypass with force flag."""
        mock_repo = Mock()
        mock_repo_class.return_value.__enter__ = Mock(return_value=mock_repo)
        mock_repo_class.return_value.__exit__ = Mock(return_value=None)
        
        # Mock tree
        mock_tree = Mock()
        mock_tree.get_tree_statistics.return_value = {'node_count': 100, 'genome_count': 2}
        mock_tree.purge_nodes_without_genomes.return_value = {
            'nodes_before': 100,
            'nodes_after': 2,
            'nodes_removed': 98
        }
        mock_repo.load_tree.return_value = mock_tree
        
        # Mock command methods
        self.command._validate_database_path = Mock()
        self.command._validate_purge_safety = Mock()
        self.command._display_purge_results = Mock()
        
        args = create_purge_mock_args(force=True)
        
        result = self.command.execute(args)
        
        assert result == 0  # Should succeed with force
        mock_repo.save_tree.assert_called_once()


class TestPurgeCommandEdgeCases:
    """Test edge cases and error conditions for PurgeCommand."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = PurgeCommand()
    
    @patch('flextaxd.cli.commands.purge.SQLiteTaxonomyRepository')
    def test_execute_empty_tree(self, mock_repo_class):
        """Test purging an empty tree."""
        mock_repo = Mock()
        mock_repo_class.return_value.__enter__ = Mock(return_value=mock_repo)
        mock_repo_class.return_value.__exit__ = Mock(return_value=None)
        
        # Mock tree
        mock_tree = Mock()
        mock_tree.get_tree_statistics.return_value = {'node_count': 0, 'genome_count': 0}
        mock_tree.purge_nodes_without_genomes.return_value = {
            'nodes_before': 0,
            'nodes_after': 0,
            'nodes_removed': 0
        }
        mock_repo.load_tree.return_value = mock_tree
        
        # Mock command methods
        self.command._validate_database_path = Mock()
        self.command._validate_purge_safety = Mock()
        self.command._display_purge_results = Mock()
        
        args = create_purge_mock_args(force=True)
        
        result = self.command.execute(args)
        
        assert result == 0
    
    @patch('flextaxd.cli.commands.purge.SQLiteTaxonomyRepository')
    def test_execute_no_nodes_to_remove(self, mock_repo_class):
        """Test when no nodes need to be removed."""
        mock_repo = Mock()
        mock_repo_class.return_value.__enter__ = Mock(return_value=mock_repo)
        mock_repo_class.return_value.__exit__ = Mock(return_value=None)
        
        # Mock tree
        mock_tree = Mock()
        mock_tree.get_tree_statistics.return_value = {'node_count': 50, 'genome_count': 50}
        mock_tree.purge_nodes_without_genomes.return_value = {
            'nodes_before': 50,
            'nodes_after': 50,
            'nodes_removed': 0
        }
        mock_repo.load_tree.return_value = mock_tree
        
        # Mock command methods
        self.command._validate_database_path = Mock()
        self.command._validate_purge_safety = Mock()
        self.command._display_purge_results = Mock()
        
        args = create_purge_mock_args(force=True)
        
        result = self.command.execute(args)
        
        assert result == 0
        mock_repo.save_tree.assert_called_once()  # Still saves even with no changes