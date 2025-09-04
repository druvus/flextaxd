"""Tests for purge CLI command functionality."""

import pytest
import tempfile
import os
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, call
from argparse import Namespace

from flextaxd.cli.commands.purge import PurgeCommand
from flextaxd.core.exceptions import ValidationError, DatabaseError
from flextaxd.core.models import TaxonomyTree, TaxonomyNode, GenomeInfo, TaxonomicRank


class TestPurgeCommand:
    """Test purge CLI command functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.command = PurgeCommand()
        self.temp_dir = Path(tempfile.mkdtemp())
        
    def teardown_method(self):
        """Clean up test fixtures."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def _create_test_database(self, filename="test.ftd"):
        """Create a test database file."""
        db_path = self.temp_dir / filename
        db_path.touch()
        return str(db_path)

    def _create_test_args(self, **kwargs):
        """Create test arguments with defaults."""
        defaults = {
            "database": self._create_test_database(),
            "dry_run": False,
            "force": False,
            "allow_metadata_only": False,
            "backup": None,
            "stats_only": False,
        }
        defaults.update(kwargs)
        return Namespace(**defaults)

    def test_execute_validation_error_missing_database(self):
        """Test execute with missing database file."""
        args = self._create_test_args(database="/nonexistent/database.ftd")
        
        result = self.command.execute(args)
        assert result == 1  # Error exit code

    def test_execute_validation_error_invalid_backup_path(self):
        """Test execute with invalid backup path."""
        with patch('os.access', return_value=False):
            args = self._create_test_args(backup="/readonly/backup.ftd")
            
            result = self.command.execute(args)
            assert result == 1

    def test_execute_dry_run_mode(self):
        """Test execute in dry run mode."""
        mock_tree = Mock()
        mock_tree.get_tree_statistics.return_value = {"node_count": 100, "genome_count": 10}
        mock_tree.purge_nodes_without_genomes.return_value = {
            "nodes_before": 100,
            "nodes_after": 50,
            "nodes_removed": 50,
            "genomes_retained": 10,
            "lineages_preserved": 5,
            "nodes_with_genomes": 5,
            "essential_nodes_kept": 50
        }
        
        with patch('flextaxd.database.sqlite.SQLiteTaxonomyRepository') as mock_repo:
            mock_repo.return_value.__enter__.return_value.load_tree.return_value = mock_tree
            
            args = self._create_test_args(dry_run=True)
            result = self.command.execute(args)
            
            assert result == 0
            # Should not call save_tree in dry run mode
            mock_repo.return_value.__enter__.return_value.save_tree.assert_not_called()

    def test_execute_stats_only_mode(self):
        """Test execute in stats only mode."""
        mock_tree = Mock()
        mock_tree.get_tree_statistics.return_value = {"node_count": 100, "genome_count": 10}
        mock_tree.purge_nodes_without_genomes.return_value = {
            "nodes_before": 100,
            "nodes_after": 60,
            "nodes_removed": 40,
            "genomes_retained": 8,
            "lineages_preserved": 4,
            "nodes_with_genomes": 4,
            "essential_nodes_kept": 60
        }
        
        with patch('flextaxd.database.sqlite.SQLiteTaxonomyRepository') as mock_repo:
            mock_repo.return_value.__enter__.return_value.load_tree.return_value = mock_tree
            
            args = self._create_test_args(stats_only=True)
            result = self.command.execute(args)
            
            assert result == 0
            # Should not call save_tree in stats only mode
            mock_repo.return_value.__enter__.return_value.save_tree.assert_not_called()

    def test_execute_with_backup_creation(self):
        """Test execute with backup creation."""
        backup_path = str(self.temp_dir / "backup.ftd")
        mock_tree = Mock()
        mock_tree.get_tree_statistics.return_value = {"node_count": 100, "genome_count": 10}
        mock_tree.purge_nodes_without_genomes.return_value = {
            "nodes_before": 100,
            "nodes_after": 80,
            "nodes_removed": 20,
            "genomes_retained": 10,
            "lineages_preserved": 3,
            "nodes_with_genomes": 3,
            "essential_nodes_kept": 80
        }
        
        with patch('flextaxd.database.sqlite.SQLiteTaxonomyRepository') as mock_repo:
            mock_repo.return_value.__enter__.return_value.load_tree.return_value = mock_tree
            
            args = self._create_test_args(backup=backup_path, force=True)
            result = self.command.execute(args)
            
            assert result == 0
            # Verify backup was created
            assert Path(backup_path).exists()

    def test_execute_with_user_confirmation_yes(self):
        """Test execute with user confirmation (yes)."""
        mock_tree = Mock()
        mock_tree.get_tree_statistics.return_value = {"node_count": 100, "genome_count": 10}
        mock_tree.purge_nodes_without_genomes.return_value = {
            "nodes_before": 100,
            "nodes_after": 75,
            "nodes_removed": 25,
            "genomes_retained": 8,
            "lineages_preserved": 4,
            "nodes_with_genomes": 4,
            "essential_nodes_kept": 75
        }
        
        with patch('flextaxd.database.sqlite.SQLiteTaxonomyRepository') as mock_repo, \
             patch('builtins.input', return_value='y'):
            
            mock_repo.return_value.__enter__.return_value.load_tree.return_value = mock_tree
            
            args = self._create_test_args()
            result = self.command.execute(args)
            
            assert result == 0
            mock_repo.return_value.__enter__.return_value.save_tree.assert_called_once()

    def test_execute_with_user_confirmation_no(self):
        """Test execute with user confirmation (no)."""
        mock_tree = Mock()
        mock_tree.get_tree_statistics.return_value = {"node_count": 100, "genome_count": 10}
        mock_tree.purge_nodes_without_genomes.return_value = {
            "nodes_before": 100,
            "nodes_after": 75,
            "nodes_removed": 25,
            "genomes_retained": 8,
            "lineages_preserved": 4,
            "nodes_with_genomes": 4,
            "essential_nodes_kept": 75
        }
        
        with patch('flextaxd.database.sqlite.SQLiteTaxonomyRepository') as mock_repo, \
             patch('builtins.input', return_value='n'):
            
            mock_repo.return_value.__enter__.return_value.load_tree.return_value = mock_tree
            
            args = self._create_test_args()
            result = self.command.execute(args)
            
            assert result == 0
            # Should not save when user says no
            mock_repo.return_value.__enter__.return_value.save_tree.assert_not_called()

    def test_execute_with_warning_result(self):
        """Test execute when purge returns warning."""
        mock_tree = Mock()
        mock_tree.get_tree_statistics.return_value = {"node_count": 100, "genome_count": 0}
        mock_tree.purge_nodes_without_genomes.return_value = {
            "nodes_before": 100,
            "nodes_after": 100,
            "nodes_removed": 0,
            "genomes_retained": 0,
            "lineages_preserved": 0,
            "warning": "No nodes with eligible genomes found - no changes made"
        }
        
        with patch('flextaxd.database.sqlite.SQLiteTaxonomyRepository') as mock_repo:
            mock_repo.return_value.__enter__.return_value.load_tree.return_value = mock_tree
            
            args = self._create_test_args(force=True)
            result = self.command.execute(args)
            
            assert result == 0
            # Should not save when warning occurs
            mock_repo.return_value.__enter__.return_value.save_tree.assert_not_called()

    def test_execute_force_mode(self):
        """Test execute in force mode (skips confirmations)."""
        mock_tree = Mock()
        mock_tree.get_tree_statistics.return_value = {"node_count": 100, "genome_count": 5}
        mock_tree.purge_nodes_without_genomes.return_value = {
            "nodes_before": 100,
            "nodes_after": 20,
            "nodes_removed": 80,
            "genomes_retained": 5,
            "lineages_preserved": 2,
            "nodes_with_genomes": 2,
            "essential_nodes_kept": 20
        }
        
        with patch('flextaxd.database.sqlite.SQLiteTaxonomyRepository') as mock_repo:
            mock_repo.return_value.__enter__.return_value.load_tree.return_value = mock_tree
            
            args = self._create_test_args(force=True)
            result = self.command.execute(args)
            
            assert result == 0
            # Force mode should call purge with force=True
            mock_tree.purge_nodes_without_genomes.assert_called_with(require_fasta_files=True, force=True)
            mock_repo.return_value.__enter__.return_value.save_tree.assert_called_once()

    def test_execute_allow_metadata_only(self):
        """Test execute with allow metadata only flag."""
        mock_tree = Mock()
        mock_tree.get_tree_statistics.return_value = {"node_count": 100, "genome_count": 10}
        mock_tree.purge_nodes_without_genomes.return_value = {
            "nodes_before": 100,
            "nodes_after": 90,
            "nodes_removed": 10,
            "genomes_retained": 15,  # More genomes retained when allowing metadata
            "lineages_preserved": 8,
            "nodes_with_genomes": 8,
            "essential_nodes_kept": 90
        }
        
        with patch('flextaxd.database.sqlite.SQLiteTaxonomyRepository') as mock_repo:
            mock_repo.return_value.__enter__.return_value.load_tree.return_value = mock_tree
            
            args = self._create_test_args(allow_metadata_only=True, force=True)
            result = self.command.execute(args)
            
            assert result == 0
            # Should call purge with require_fasta_files=False
            mock_tree.purge_nodes_without_genomes.assert_called_with(require_fasta_files=False, force=True)

    def test_execute_database_error(self):
        """Test execute with database error."""
        with patch('flextaxd.database.sqlite.SQLiteTaxonomyRepository') as mock_repo:
            mock_repo.side_effect = DatabaseError("Database connection failed")
            
            args = self._create_test_args()
            result = self.command.execute(args)
            
            assert result == 1

    def test_execute_unexpected_error(self):
        """Test execute with unexpected error."""
        with patch('flextaxd.database.sqlite.SQLiteTaxonomyRepository') as mock_repo:
            mock_repo.side_effect = Exception("Unexpected error")
            
            args = self._create_test_args()
            result = self.command.execute(args)
            
            assert result == 2

    def test_create_backup_success(self):
        """Test successful backup creation."""
        source_db = self._create_test_database("source.ftd")
        backup_path = str(self.temp_dir / "backup.ftd")
        
        # Write some content to source
        with open(source_db, 'w') as f:
            f.write("test database content")
        
        self.command._create_backup(source_db, backup_path)
        
        # Verify backup was created and has same content
        assert Path(backup_path).exists()
        with open(backup_path, 'r') as f:
            assert f.read() == "test database content"

    def test_create_backup_failure(self):
        """Test backup creation failure."""
        source_db = self._create_test_database("source.ftd")
        backup_path = "/readonly/cannot_write_here/backup.ftd"
        
        with pytest.raises(ValidationError, match="Failed to create backup"):
            self.command._create_backup(source_db, backup_path)

    def test_analyze_purge_impact(self):
        """Test purge impact analysis."""
        mock_tree = Mock()
        mock_tree.purge_nodes_without_genomes.return_value = {
            "nodes_before": 100,
            "nodes_after": 60,
            "nodes_removed": 40,
            "genomes_retained": 8,
            "lineages_preserved": 4,
            "nodes_with_genomes": 4,
            "essential_nodes_kept": 60
        }
        
        result = self.command._analyze_purge_impact(mock_tree, require_fasta=True, force=False)
        
        assert result["nodes_removed"] == 40
        assert result["nodes_after"] == 60
        mock_tree.purge_nodes_without_genomes.assert_called_with(require_fasta_files=True, force=False)

    def test_confirm_purge_yes(self):
        """Test purge confirmation with yes response."""
        stats = {
            "nodes_before": 100,
            "nodes_after": 60,
            "nodes_removed": 40,
            "genomes_retained": 8,
        }
        
        with patch('builtins.input', return_value='y'):
            result = self.command._confirm_purge(stats)
            assert result is True

    def test_confirm_purge_no(self):
        """Test purge confirmation with no response."""
        stats = {
            "nodes_before": 100,
            "nodes_after": 60, 
            "nodes_removed": 40,
            "genomes_retained": 8,
        }
        
        with patch('builtins.input', return_value='n'):
            result = self.command._confirm_purge(stats)
            assert result is False

    def test_confirm_purge_with_warning(self):
        """Test purge confirmation with warning stats."""
        stats = {
            "warning": "No eligible genomes found"
        }
        
        result = self.command._confirm_purge(stats)
        assert result is False

    def test_validate_purge_safety_no_backup_interactive(self):
        """Test safety validation with no backup in interactive mode."""
        args = self._create_test_args(force=False)
        
        with patch('builtins.input', return_value='y'):
            # Should not raise exception
            self.command._validate_purge_safety(args)

    def test_validate_purge_safety_no_backup_cancelled(self):
        """Test safety validation with no backup cancelled by user."""
        args = self._create_test_args(force=False)
        
        with patch('builtins.input', return_value='n'):
            with pytest.raises(ValidationError, match="Operation cancelled by user"):
                self.command._validate_purge_safety(args)

    def test_validate_purge_safety_backup_exists_overwrite(self):
        """Test safety validation with existing backup file."""
        backup_path = str(self.temp_dir / "existing_backup.ftd")
        Path(backup_path).touch()  # Create existing file
        
        args = self._create_test_args(backup=backup_path, force=False)
        
        with patch('builtins.input', return_value='y'):
            # Should not raise exception
            self.command._validate_purge_safety(args)

    def test_validate_purge_safety_backup_exists_cancelled(self):
        """Test safety validation with existing backup file cancelled."""
        backup_path = str(self.temp_dir / "existing_backup.ftd")
        Path(backup_path).touch()  # Create existing file
        
        args = self._create_test_args(backup=backup_path, force=False)
        
        with patch('builtins.input', return_value='n'):
            with pytest.raises(ValidationError, match="cancelled to prevent overwriting"):
                self.command._validate_purge_safety(args)

    def test_validate_purge_safety_dry_run_skips_checks(self):
        """Test that dry run skips most safety checks."""
        args = self._create_test_args(dry_run=True, database="/nonexistent.ftd")
        
        # Should not raise exception for non-existent database in dry run
        self.command._validate_purge_safety(args)

    def test_validate_purge_safety_stats_only_skips_checks(self):
        """Test that stats only skips most safety checks."""
        args = self._create_test_args(stats_only=True, database="/nonexistent.ftd")
        
        # Should not raise exception for non-existent database in stats only
        self.command._validate_purge_safety(args)

    def test_validate_purge_safety_force_skips_interactive(self):
        """Test that force mode skips interactive prompts.""" 
        args = self._create_test_args(force=True)  # No backup specified
        
        # Should not prompt for backup confirmation in force mode
        with patch('builtins.input') as mock_input:
            self.command._validate_purge_safety(args)
            mock_input.assert_not_called()

    def test_display_purge_analysis_dry_run(self):
        """Test display of purge analysis in dry run mode."""
        stats = {
            "nodes_before": 100,
            "nodes_after": 60,
            "nodes_removed": 40,
            "genomes_retained": 8,
            "lineages_preserved": 4,
            "nodes_with_genomes": 4,
            "essential_nodes_kept": 60
        }
        
        # Should not raise exception
        self.command._display_purge_analysis(stats, is_dry_run=True)

    def test_display_purge_analysis_with_warning(self):
        """Test display of purge analysis with warning."""
        stats = {
            "warning": "No eligible genomes found"
        }
        
        # Should not raise exception
        self.command._display_purge_analysis(stats, is_dry_run=False)

    def test_display_purge_results(self):
        """Test display of final purge results."""
        stats = {
            "nodes_before": 100,
            "nodes_after": 60,
            "nodes_removed": 40,
            "genomes_retained": 8,
        }
        
        # Should not raise exception
        self.command._display_purge_results(stats)

    def test_display_purge_results_with_warning(self):
        """Test display of purge results with warning."""
        stats = {
            "warning": "Some warning message"
        }
        
        # Should not raise exception
        self.command._display_purge_results(stats)