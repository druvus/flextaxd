"""Comprehensive unit tests for ModifyCommand."""

import pytest
import argparse
from unittest.mock import Mock, patch, mock_open
from pathlib import Path

from flextaxd.cli.commands.modify import ModifyCommand
from flextaxd.core.exceptions import ValidationError
from flextaxd.core.models import TaxonomyTree, TaxonomyNode, TaxonomicRank

from ....fixtures.cli.conftest import *
from ....fixtures.cli.mock_data import MockData, CLITestHelper


class TestModifyCommand:
    """Test ModifyCommand basic functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = ModifyCommand()
    
    def test_initialization(self):
        """Test command initialization."""
        assert isinstance(self.command, ModifyCommand)
        assert hasattr(self.command, 'logger')
    
    def test_register_parser(self):
        """Test parser registration."""
        mock_subparsers = Mock()
        mock_parser = Mock()
        mock_subparsers.add_parser.return_value = mock_parser
        
        parser = ModifyCommand.register_parser(mock_subparsers)
        
        # Verify parser was created
        mock_subparsers.add_parser.assert_called_once()
        call_args = mock_subparsers.add_parser.call_args
        assert call_args[0][0] == "modify"
        
        # Verify argument groups were added
        assert mock_parser.add_argument_group.called
        assert mock_parser.add_argument.called
    
    @patch('flextaxd.cli.commands.modify.SQLiteTaxonomyRepository')
    def test_execute_add_node(self, mock_repo_class, sample_taxonomy_tree):
        """Test adding a new node."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            add_node="New Species",
            parent_id=4,  # E. coli parent
            rank="species",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'):
            result = self.command.execute(args)
            
            assert result == 0
            mock_repo.save_tree.assert_called_once()
    
    @patch('flextaxd.cli.commands.modify.SQLiteTaxonomyRepository')
    def test_execute_update_node(self, mock_repo_class, sample_taxonomy_tree):
        """Test updating an existing node."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            update_node=4,  # E. coli tax_id
            name="Escherichia coli K-12",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'):
            result = self.command.execute(args)
            
            assert result == 0
            mock_repo.save_tree.assert_called_once()
    
    @patch('flextaxd.cli.commands.modify.SQLiteTaxonomyRepository')
    def test_execute_delete_node(self, mock_repo_class, sample_taxonomy_tree):
        """Test deleting a node."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            delete_node=4,  # E. coli tax_id
            force=True,
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'):
            result = self.command.execute(args)
            
            assert result == 0
            mock_repo.save_tree.assert_called_once()
    
    @patch('flextaxd.cli.commands.modify.SQLiteTaxonomyRepository')
    def test_execute_mod_file(self, mock_repo_class, sample_taxonomy_tree):
        """Test batch modifications from file."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        # Mock file content
        mod_content = """action\ttax_id\tname\tparent_id\trank
add\t\tNew Species 1\t4\tspecies
update\t4\tUpdated E. coli\t\t
delete\t3\t\t\t
"""
        
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            mod_file="/test/modifications.tsv",
            replace=False,
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_validate_input_file'), \
             patch('builtins.open', mock_open(read_data=mod_content)):
            
            result = self.command.execute(args)
            
            assert result == 0
            mock_repo.save_tree.assert_called_once()
    
    def test_execute_no_action(self):
        """Test execution with no modification action."""
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            verbose=False
            # No modification action specified
        )
        
        result = self.command.execute(args)
        
        # Should fail with validation error
        assert result != 0


class TestModifyCommandValidation:
    """Test ModifyCommand validation logic."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = ModifyCommand()
    
    @patch('flextaxd.cli.commands.modify.SQLiteTaxonomyRepository')
    def test_add_node_validation(self, mock_repo_class, sample_taxonomy_tree):
        """Test add node validation."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        # Test missing parent
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            add_node="Orphan Species",
            parent_id=999,  # Non-existent parent
            rank="species",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'):
            result = self.command.execute(args)
            
            # Should fail due to missing parent
            assert result != 0
    
    @patch('flextaxd.cli.commands.modify.SQLiteTaxonomyRepository')
    def test_update_node_validation(self, mock_repo_class, sample_taxonomy_tree):
        """Test update node validation."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        # Test updating non-existent node
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            update_node=999,  # Non-existent node
            name="Ghost Species",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'):
            result = self.command.execute(args)
            
            # Should fail due to non-existent node
            assert result != 0
    
    @patch('flextaxd.cli.commands.modify.SQLiteTaxonomyRepository')
    def test_delete_node_validation(self, mock_repo_class, sample_taxonomy_tree):
        """Test delete node validation.""" 
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        # Test deleting root node without force
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            delete_node=1,  # Root node
            force=False,
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'):
            result = self.command.execute(args)
            
            # Should fail due to safety check
            assert result != 0
    
    @patch('flextaxd.cli.commands.modify.SQLiteTaxonomyRepository') 
    def test_delete_node_with_children(self, mock_repo_class, sample_taxonomy_tree):
        """Test deleting node with children."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        # Test deleting node with children without force
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            delete_node=2,  # Bacteria (has children)
            force=False,
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'):
            result = self.command.execute(args)
            
            # Should fail due to children
            assert result != 0
    
    def test_invalid_rank(self):
        """Test validation with invalid taxonomic rank."""
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            add_node="Invalid Rank Node",
            parent_id=4,
            rank="invalid_rank",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('flextaxd.cli.commands.modify.SQLiteTaxonomyRepository'):
            
            result = self.command.execute(args)
            
            # Should fail due to invalid rank
            assert result != 0
    
    def test_circular_dependency_prevention(self):
        """Test prevention of circular dependencies."""
        tree = MockData.create_complex_taxonomy_tree()
        
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            update_node=2,  # Bacteria
            parent_id=8,   # E. coli (child of bacteria)
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('flextaxd.cli.commands.modify.SQLiteTaxonomyRepository') as mock_repo_class:
            
            mock_repo = Mock()
            mock_repo.load_tree.return_value = tree
            mock_repo_class.return_value.__enter__.return_value = mock_repo
            
            result = self.command.execute(args)
            
            # Should fail due to circular dependency
            assert result != 0


class TestModifyCommandFileOperations:
    """Test ModifyCommand file-based operations."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = ModifyCommand()
    
    @patch('flextaxd.cli.commands.modify.SQLiteTaxonomyRepository')
    def test_mod_file_parsing(self, mock_repo_class, sample_taxonomy_tree):
        """Test modification file parsing."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        # Valid modification file content
        mod_content = """action\ttax_id\tname\tparent_id\trank
add\t\tNew Species\t4\tspecies
update\t4\tEscherichia coli K-12\t\t
delete\t3\t\t\t
"""
        
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            mod_file="/test/mods.tsv",
            replace=False,
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_validate_input_file'), \
             patch('builtins.open', mock_open(read_data=mod_content)):
            
            result = self.command.execute(args)
            
            assert result == 0
            mock_repo.save_tree.assert_called_once()
    
    @patch('flextaxd.cli.commands.modify.SQLiteTaxonomyRepository')
    def test_mod_file_invalid_format(self, mock_repo_class, sample_taxonomy_tree):
        """Test handling of invalid modification file format."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        # Invalid file content (missing columns)
        mod_content = """action\ttax_id
add\t5
update
"""
        
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            mod_file="/test/invalid.tsv",
            replace=False,
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_validate_input_file'), \
             patch('builtins.open', mock_open(read_data=mod_content)):
            
            result = self.command.execute(args)
            
            # Should handle parsing errors gracefully
            assert result != 0
    
    @patch('flextaxd.cli.commands.modify.SQLiteTaxonomyRepository')
    def test_mod_file_replace_mode(self, mock_repo_class):
        """Test replace mode with modification file."""
        # Create empty tree for replacement
        empty_tree = TaxonomyTree()
        
        mock_repo = Mock()
        mock_repo.load_tree.return_value = empty_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        # Replacement content (complete new taxonomy)
        mod_content = """action\ttax_id\tname\tparent_id\trank
add\t1\troot\t\troot
add\t2\tNew Domain\t1\tsuperkingdom
add\t3\tNew Species\t2\tspecies
"""
        
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            mod_file="/test/replace.tsv",
            replace=True,
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_validate_input_file'), \
             patch('builtins.open', mock_open(read_data=mod_content)):
            
            result = self.command.execute(args)
            
            assert result == 0
            # In replace mode, should rebuild tree from scratch
    
    def test_mod_file_validation(self):
        """Test modification file validation."""
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            mod_file="/nonexistent/file.tsv",
            replace=False,
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('pathlib.Path') as mock_path:
            
            mock_path_obj = Mock()
            mock_path_obj.exists.return_value = False
            mock_path.return_value = mock_path_obj
            
            result = self.command.execute(args)
            assert result != 0


class TestModifyCommandBackup:
    """Test ModifyCommand backup functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = ModifyCommand()
    
    @patch('flextaxd.cli.commands.modify.SQLiteTaxonomyRepository')
    def test_automatic_backup_creation(self, mock_repo_class, sample_taxonomy_tree):
        """Test automatic backup creation before modification."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            add_node="New Species",
            parent_id=4,
            rank="species",
            backup="/test/backup.ftd",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('shutil.copy2') as mock_copy:
            
            result = self.command.execute(args)
            
            assert result == 0
            # Should create backup before modification
            mock_copy.assert_called_with("/test/db.ftd", "/test/backup.ftd")
    
    @patch('flextaxd.cli.commands.modify.SQLiteTaxonomyRepository')
    def test_backup_failure_handling(self, mock_repo_class, sample_taxonomy_tree):
        """Test handling of backup creation failure."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            add_node="New Species",
            parent_id=4,
            rank="species",
            backup="/readonly/backup.ftd",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('shutil.copy2', side_effect=PermissionError("Permission denied")):
            
            result = self.command.execute(args)
            
            # Should fail if backup cannot be created
            assert result != 0


class TestModifyCommandErrorHandling:
    """Test ModifyCommand error handling."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = ModifyCommand()
    
    @patch('flextaxd.cli.commands.modify.SQLiteTaxonomyRepository')
    def test_database_load_error(self, mock_repo_class):
        """Test handling of database load errors."""
        mock_repo = Mock()
        mock_repo.load_tree.side_effect = Exception("Database corrupted")
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = CLITestHelper.create_mock_args(
            database="/test/corrupted.ftd",
            add_node="New Species",
            parent_id=4,
            rank="species",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'):
            result = self.command.execute(args)
            assert result != 0
    
    @patch('flextaxd.cli.commands.modify.SQLiteTaxonomyRepository')
    def test_database_save_error(self, mock_repo_class, sample_taxonomy_tree):
        """Test handling of database save errors."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo.save_tree.side_effect = Exception("Save failed")
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            add_node="New Species",
            parent_id=4,
            rank="species",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'):
            result = self.command.execute(args)
            assert result != 0
    
    @patch('flextaxd.cli.commands.modify.SQLiteTaxonomyRepository')
    def test_interrupted_modification(self, mock_repo_class, sample_taxonomy_tree):
        """Test handling of interrupted modifications."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            add_node="New Species",
            parent_id=4,
            rank="species",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(sample_taxonomy_tree, 'add_node', side_effect=KeyboardInterrupt()):
            
            result = self.command.execute(args)
            assert result != 0


class TestModifyCommandAdvancedFeatures:
    """Test ModifyCommand advanced features."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = ModifyCommand()
    
    @patch('flextaxd.cli.commands.modify.SQLiteTaxonomyRepository')
    def test_batch_modifications_transaction(self, mock_repo_class, sample_taxonomy_tree):
        """Test batch modifications as atomic transaction."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        # Mixed operations in one file
        mod_content = """action\ttax_id\tname\tparent_id\trank
add\t\tSpecies A\t4\tspecies  
add\t\tSpecies B\t4\tspecies
update\t4\tUpdated E. coli\t\t
delete\t3\t\t\t
"""
        
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            mod_file="/test/batch.tsv",
            replace=False,
            verbose=True
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_validate_input_file'), \
             patch('builtins.open', mock_open(read_data=mod_content)):
            
            result = self.command.execute(args)
            
            assert result == 0
            # Should apply all modifications or none (atomic)
            mock_repo.save_tree.assert_called_once()
    
    @patch('flextaxd.cli.commands.modify.SQLiteTaxonomyRepository')
    def test_modification_with_genomes(self, mock_repo_class):
        """Test modifications on nodes with genomes."""
        tree = MockData.create_complex_taxonomy_tree()
        
        mock_repo = Mock()
        mock_repo.load_tree.return_value = tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        # Try to delete node with genomes
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            delete_node=8,  # E. coli (has genomes)
            force=False,
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'):
            result = self.command.execute(args)
            
            # Should warn about genomes or require force
            # Implementation dependent on business logic
    
    @patch('flextaxd.cli.commands.modify.SQLiteTaxonomyRepository')
    def test_verbose_modification_logging(self, mock_repo_class, sample_taxonomy_tree):
        """Test verbose logging during modifications."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            add_node="Verbose Species",
            parent_id=4,
            rank="species",
            verbose=True
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, 'logger') as mock_logger:
            
            result = self.command.execute(args)
            
            assert result == 0
            # Should have detailed logging
            assert mock_logger.info.called
            assert mock_logger.debug.called or mock_logger.info.call_count > 1


class TestModifyCommandIntegration:
    """Integration tests for ModifyCommand."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = ModifyCommand()
    
    def test_realistic_taxonomy_extension(self, temp_dir):
        """Test realistic taxonomy extension scenario."""
        # Start with complex tree and add new branches
        tree = MockData.create_complex_taxonomy_tree()
        db_path = temp_dir / "modify_test.ftd"
        
        # Add multiple species under existing genus
        mod_content = """action\ttax_id\tname\tparent_id\trank
add\t\tEscherichia albertii\t5\tspecies
add\t\tEscherichia fergusonii\t5\tspecies
add\t\tSalmonella bongori\t5\tspecies
update\t5\tEnterobacteriaceae\t\tfamily
"""
        
        args = CLITestHelper.create_mock_args(
            database=str(db_path),
            mod_file=str(temp_dir / "extend.tsv"),
            replace=False,
            verbose=True
        )
        
        # Write mod file
        mod_file_path = temp_dir / "extend.tsv"
        mod_file_path.write_text(mod_content)
        
        with patch('flextaxd.cli.commands.modify.SQLiteTaxonomyRepository') as mock_repo_class, \
             patch.object(self.command, '_validate_database_path'):
            
            mock_repo = Mock()
            mock_repo.load_tree.return_value = tree
            mock_repo_class.return_value.__enter__.return_value = mock_repo
            
            result = self.command.execute(args)
            
            assert result == 0
            # Should successfully extend taxonomy
            mock_repo.save_tree.assert_called_once()
    
    def test_taxonomy_cleanup_workflow(self):
        """Test taxonomy cleanup workflow."""
        tree = MockData.create_complex_taxonomy_tree()
        
        # Remove empty intermediate nodes
        args = CLITestHelper.create_mock_args(
            database="/test/cleanup.ftd",
            delete_node=7,  # Animalia (remove empty kingdom)
            force=True,
            backup="/test/cleanup_backup.ftd",
            verbose=True
        )
        
        with patch('flextaxd.cli.commands.modify.SQLiteTaxonomyRepository') as mock_repo_class, \
             patch.object(self.command, '_validate_database_path'), \
             patch('shutil.copy2') as mock_backup:
            
            mock_repo = Mock()
            mock_repo.load_tree.return_value = tree
            mock_repo_class.return_value.__enter__.return_value = mock_repo
            
            result = self.command.execute(args)
            
            assert result == 0
            # Should create backup and clean up taxonomy
            mock_backup.assert_called_once()
            mock_repo.save_tree.assert_called_once()