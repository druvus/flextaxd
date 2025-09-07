"""Comprehensive unit tests for AddNodeCommand."""

import pytest
import argparse
from unittest.mock import Mock, patch
from pathlib import Path

from flextaxd.cli.commands.add_node import AddNodeCommand
from flextaxd.core.exceptions import ValidationError, DatabaseError
from flextaxd.core.models import TaxonomyTree, TaxonomyNode, TaxonomicRank

from ....fixtures.cli.conftest import *
from ....fixtures.cli.mock_data import MockData, CLITestHelper


def create_add_node_mock_args(**overrides):
    """Create complete mock args for AddNodeCommand with all required attributes."""
    defaults = {
        'database': '/test/db.ftd',
        'name': 'Test Species',
        'parent_id': None,
        'parent_name': None,
        'rank': 'species',
        'tax_id': None,
        'dry_run': False,
        'force': False,
        'verbose': False,
        'quiet': False,
        'skip_validation': True,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


class TestAddNodeCommand:
    """Test AddNodeCommand basic functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = AddNodeCommand()
    
    def test_initialization(self):
        """Test command initialization."""
        assert isinstance(self.command, AddNodeCommand)
        assert hasattr(self.command, 'logger')
    
    def test_register_parser(self):
        """Test parser registration."""
        mock_subparsers = Mock()
        mock_parser = Mock()
        mock_subparsers.add_parser.return_value = mock_parser
        
        parser = AddNodeCommand.register_parser(mock_subparsers)
        
        # Verify parser was created
        mock_subparsers.add_parser.assert_called_once()
        call_args = mock_subparsers.add_parser.call_args
        assert call_args[0][0] == "add-node"
        
        # Should be the actual parser returned
        assert parser == mock_parser
    
    @patch('flextaxd.cli.commands.add_node.SQLiteTaxonomyRepository')
    def test_execute_add_node_by_parent_id(self, mock_repo_class, sample_taxonomy_tree):
        """Test adding a new node by parent ID."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        
        # Mock parent node lookup
        parent_node = sample_taxonomy_tree.get_node(4)
        mock_repo.get_node.return_value = parent_node
        
        # Mock that new node name doesn't exist yet
        mock_repo.get_node_by_name.return_value = None
        
        # Mock next tax_id generation
        mock_repo.get_next_tax_id.return_value = 1010
        
        # Mock ancestors for validation
        mock_repo.get_ancestors.return_value = []
        
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_add_node_mock_args(
            name="New Species",
            parent_id=4,
            rank="species"
        )
        
        with patch.object(self.command, '_validate_database_path'):
            result = self.command.execute(args)
            
            assert result == 0
            mock_repo.add_node.assert_called_once()
            
            # Verify the node that was added
            added_node = mock_repo.add_node.call_args[0][0]
            assert added_node.name == "New Species"
            assert added_node.tax_id == 1010
            assert added_node.rank == TaxonomicRank.SPECIES
            assert added_node.parent_id == 4
    
    @patch('flextaxd.cli.commands.add_node.SQLiteTaxonomyRepository')
    def test_execute_add_node_by_parent_name(self, mock_repo_class, sample_taxonomy_tree):
        """Test adding a new node by parent name."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        
        # Mock parent node lookup by name
        parent_node = sample_taxonomy_tree.get_node(4)
        
        # Mock get_node_by_name to return parent for parent name, None for new node name
        def mock_get_node_by_name(name):
            if name == "Escherichia":  # Parent name
                return parent_node
            elif name == "New Species":  # New node name - should not exist
                return None
            return None
        mock_repo.get_node_by_name.side_effect = mock_get_node_by_name
        
        # Mock next tax_id generation
        mock_repo.get_next_tax_id.return_value = 1010
        
        # Mock ancestors for validation
        mock_repo.get_ancestors.return_value = []
        
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_add_node_mock_args(
            name="New Species",
            parent_name="Escherichia",
            rank="species"
        )
        
        with patch.object(self.command, '_validate_database_path'):
            result = self.command.execute(args)
            
            assert result == 0
            mock_repo.add_node.assert_called_once()
    
    @patch('flextaxd.cli.commands.add_node.SQLiteTaxonomyRepository')
    def test_execute_add_node_with_custom_tax_id(self, mock_repo_class, sample_taxonomy_tree):
        """Test adding a new node with custom taxonomy ID."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        
        # Mock parent node lookup
        parent_node = sample_taxonomy_tree.get_node(4)
        mock_repo.get_node.return_value = parent_node
        
        # Mock that custom tax_id doesn't exist
        def mock_get_node(tax_id):
            if tax_id == 4:  # Parent exists
                return parent_node
            elif tax_id == 9999:  # Custom tax_id doesn't exist
                return None
            return None
        mock_repo.get_node.side_effect = mock_get_node
        
        # Mock that new node name doesn't exist yet
        mock_repo.get_node_by_name.return_value = None
        
        # Mock ancestors for validation
        mock_repo.get_ancestors.return_value = []
        
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_add_node_mock_args(
            name="Custom Species",
            parent_id=4,
            rank="species",
            tax_id=9999
        )
        
        with patch.object(self.command, '_validate_database_path'):
            result = self.command.execute(args)
            
            assert result == 0
            mock_repo.add_node.assert_called_once()
            
            # Verify the custom tax_id was used
            added_node = mock_repo.add_node.call_args[0][0]
            assert added_node.tax_id == 9999
    
    @patch('flextaxd.cli.commands.add_node.SQLiteTaxonomyRepository')
    def test_execute_dry_run(self, mock_repo_class, sample_taxonomy_tree):
        """Test dry-run mode."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        
        # Mock parent node lookup
        parent_node = sample_taxonomy_tree.get_node(4)
        mock_repo.get_node.return_value = parent_node
        
        # Mock that new node name doesn't exist yet
        mock_repo.get_node_by_name.return_value = None
        
        # Mock next tax_id generation
        mock_repo.get_next_tax_id.return_value = 1010
        
        # Mock ancestors for validation
        mock_repo.get_ancestors.return_value = []
        
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_add_node_mock_args(
            name="Dry Run Species",
            parent_id=4,
            rank="species",
            dry_run=True
        )
        
        with patch.object(self.command, '_validate_database_path'):
            result = self.command.execute(args)
            
            assert result == 0
            # Should not add node in dry-run mode
            mock_repo.add_node.assert_not_called()


class TestAddNodeCommandValidation:
    """Test AddNodeCommand validation logic."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = AddNodeCommand()
    
    @patch('flextaxd.cli.commands.add_node.SQLiteTaxonomyRepository')
    def test_missing_parent_validation(self, mock_repo_class):
        """Test validation when parent doesn't exist."""
        mock_repo = Mock()
        mock_repo.get_node.return_value = None  # Parent doesn't exist
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_add_node_mock_args(
            name="Orphan Species",
            parent_id=999,  # Non-existent parent
            rank="species"
        )
        
        with patch.object(self.command, '_validate_database_path'):
            result = self.command.execute(args)
            
            assert result == 1  # Should fail
            mock_repo.add_node.assert_not_called()
    
    @patch('flextaxd.cli.commands.add_node.SQLiteTaxonomyRepository')
    def test_existing_tax_id_validation(self, mock_repo_class, sample_taxonomy_tree):
        """Test validation when custom tax_id already exists."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        
        # Mock that custom tax_id already exists
        existing_node = sample_taxonomy_tree.get_node(4)
        def mock_get_node(tax_id):
            if tax_id == 4:  # Both parent and custom tax_id exist
                return existing_node
            return None
        mock_repo.get_node.side_effect = mock_get_node
        
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_add_node_mock_args(
            name="Duplicate ID Species",
            parent_id=4,
            rank="species",
            tax_id=4,  # Already exists
            force=False
        )
        
        with patch.object(self.command, '_validate_database_path'):
            result = self.command.execute(args)
            
            assert result == 1  # Should fail without force
            mock_repo.add_node.assert_not_called()
    
    @patch('flextaxd.cli.commands.add_node.SQLiteTaxonomyRepository')
    def test_existing_name_validation(self, mock_repo_class, sample_taxonomy_tree):
        """Test validation when node name already exists."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        
        # Mock parent lookup
        parent_node = sample_taxonomy_tree.get_node(4)
        mock_repo.get_node.return_value = parent_node
        
        # Mock existing name lookup
        existing_node = sample_taxonomy_tree.get_node(4)
        mock_repo.get_node_by_name.return_value = existing_node
        
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_add_node_mock_args(
            name="Escherichia",  # Already exists
            parent_id=4,
            rank="species",
            force=False
        )
        
        with patch.object(self.command, '_validate_database_path'):
            result = self.command.execute(args)
            
            assert result == 1  # Should fail without force
            mock_repo.add_node.assert_not_called()
    
    def test_invalid_rank_validation(self):
        """Test validation with invalid taxonomic rank."""
        args = create_add_node_mock_args(
            name="Invalid Rank Node",
            parent_id=4,
            rank="invalid_rank"
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('flextaxd.cli.commands.add_node.SQLiteTaxonomyRepository'):
            
            result = self.command.execute(args)
            
            assert result == 1  # Should fail due to invalid rank


class TestAddNodeCommandErrorHandling:
    """Test AddNodeCommand error handling."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = AddNodeCommand()
    
    @patch('flextaxd.cli.commands.add_node.SQLiteTaxonomyRepository')
    def test_database_error_handling(self, mock_repo_class):
        """Test handling of database errors."""
        mock_repo = Mock()
        mock_repo.add_node.side_effect = DatabaseError("Database write failed")
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        # Mock successful lookups up to the point of error
        mock_repo.get_node.return_value = Mock(tax_id=4, name="Parent")
        mock_repo.get_next_tax_id.return_value = 1010
        mock_repo.get_ancestors.return_value = []
        
        args = create_add_node_mock_args(
            name="Error Species",
            parent_id=4,
            rank="species"
        )
        
        with patch.object(self.command, '_validate_database_path'):
            result = self.command.execute(args)
            
            assert result == 1  # Should fail gracefully
    
    @patch('flextaxd.cli.commands.add_node.SQLiteTaxonomyRepository')
    def test_validation_error_handling(self, mock_repo_class):
        """Test handling of validation errors."""
        mock_repo = Mock()
        mock_repo.get_node.side_effect = ValidationError("Invalid parent node")
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_add_node_mock_args(
            name="Validation Error Species",
            parent_id=4,
            rank="species"
        )
        
        with patch.object(self.command, '_validate_database_path'):
            result = self.command.execute(args)
            
            assert result == 1  # Should fail gracefully
    
    @patch('flextaxd.cli.commands.add_node.SQLiteTaxonomyRepository')
    def test_unexpected_error_handling(self, mock_repo_class):
        """Test handling of unexpected errors."""
        mock_repo = Mock()
        mock_repo.get_node.side_effect = Exception("Unexpected error")
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_add_node_mock_args(
            name="Exception Species",
            parent_id=4,
            rank="species"
        )
        
        with patch.object(self.command, '_validate_database_path'):
            result = self.command.execute(args)
            
            assert result == 1  # Should fail gracefully


class TestAddNodeCommandIntegration:
    """Integration tests for AddNodeCommand."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = AddNodeCommand()
    
    @patch('flextaxd.cli.commands.add_node.SQLiteTaxonomyRepository')
    def test_complex_taxonomy_extension(self, mock_repo_class):
        """Test extending a complex taxonomy tree."""
        tree = MockData.create_complex_taxonomy_tree()
        
        mock_repo = Mock()
        mock_repo.load_tree.return_value = tree
        
        # Mock parent lookup (Bacteria)
        bacteria_node = tree.get_node(2)
        mock_repo.get_node.return_value = bacteria_node
        
        # Mock that new node name doesn't exist yet
        mock_repo.get_node_by_name.return_value = None
        
        # Mock next tax_id generation
        mock_repo.get_next_tax_id.return_value = 8001
        
        # Mock ancestors for validation
        mock_repo.get_ancestors.return_value = [tree.get_node(1)]  # Root
        
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_add_node_mock_args(
            name="Salmonella",
            parent_id=2,  # Under Bacteria
            rank="genus"
        )
        
        with patch.object(self.command, '_validate_database_path'):
            result = self.command.execute(args)
            
            assert result == 0
            mock_repo.add_node.assert_called_once()
            
            # Verify the added node
            added_node = mock_repo.add_node.call_args[0][0]
            assert added_node.name == "Salmonella"
            assert added_node.rank == TaxonomicRank.GENUS
            assert added_node.parent_id == 2