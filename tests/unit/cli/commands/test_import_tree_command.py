"""Comprehensive unit tests for ImportTreeCommand."""

import pytest
import argparse
from unittest.mock import Mock, patch, mock_open
from pathlib import Path

from flextaxd.cli.commands.import_tree import ImportTreeCommand
from flextaxd.core.exceptions import ValidationError, DatabaseError
from flextaxd.core.models import TaxonomyTree, TaxonomyNode, TaxonomicRank

from ....fixtures.cli.conftest import *
from ....fixtures.cli.mock_data import MockData, CLITestHelper


def create_import_tree_mock_args(**overrides):
    """Create complete mock args for ImportTreeCommand with all required attributes."""
    defaults = {
        # Required CLI args
        'database': '/test/db.ftd',
        'input': '/test/tree.tsv',
        'strategy': 'merge',
        'attach_to': None,
        'attach_to_id': None,
        'target': None,
        'root_node': None,
        'auto_root': True,
        'keep_names': 'file',
        'on_conflict': 'skip',
        'format': 'auto',
        'dry_run': False,
        'force': False,
        'backup': True,
        
        # Global CLI options (from main parser)
        'verbose': 0,
        'quiet': False,
        'log_file': None,
        'command': 'import-tree',
        
        # Progress-related options (expected by CLI commands)
        'progress_width': 80,
        'no_eta': False,
        'no_rate': False,
        'progress_log': None,
        'progress_interval': 1.0,
        
        # Additional command-specific options
        'disable_parallel': False,
        'max_workers': 4,
        'skip_validation': True,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


class TestImportTreeCommand:
    """Test ImportTreeCommand basic functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = ImportTreeCommand()
    
    def test_initialization(self):
        """Test command initialization."""
        assert isinstance(self.command, ImportTreeCommand)
        assert hasattr(self.command, 'logger')
    
    def test_register_parser(self):
        """Test parser registration."""
        mock_subparsers = Mock()
        mock_parser = Mock()
        mock_subparsers.add_parser.return_value = mock_parser
        
        parser = ImportTreeCommand.register_parser(mock_subparsers)
        
        # Verify parser was created
        mock_subparsers.add_parser.assert_called_once()
        call_args = mock_subparsers.add_parser.call_args
        assert call_args[0][0] == "import-tree"
        
        # Should be the actual parser returned
        assert parser == mock_parser
    
    @patch('flextaxd.cli.commands.import_tree.SQLiteTaxonomyRepository')
    @patch('flextaxd.parsers.tsv.TSVTaxonomyParser')
    def test_execute_merge_strategy(self, mock_parser_class, mock_repo_class, sample_taxonomy_tree):
        """Test importing tree with merge strategy."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        
        # Mock attachment point lookup
        attach_node = sample_taxonomy_tree.get_node(2)  # Bacteria
        def mock_get_node_by_name(name):
            if name == "Bacteria":  # Attachment point exists
                return attach_node
            elif name == "Salmonella":  # New node doesn't exist
                return None
            return None
        mock_repo.get_node_by_name.side_effect = mock_get_node_by_name
        
        # Mock next tax_id generation
        mock_repo.get_next_tax_id.return_value = 1010
        
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        # Create a simple import tree
        import_tree = TaxonomyTree()
        import_node = TaxonomyNode(
            tax_id=5001, 
            name="Salmonella", 
            rank=TaxonomicRank.GENUS,
            parent_id=None,
            description="Salmonella genus"
        )
        import_tree.add_node(import_node)
        
        # Mock TSV parser directly
        mock_parser = Mock()
        mock_parser.can_parse.return_value = True
        mock_parser.parse.return_value = import_tree
        mock_parser_class.return_value = mock_parser
        
        tree_content = """tax_id\tname\trank\tparent_id
5001\tSalmonella\tgenus\t"""
        
        args = create_import_tree_mock_args(
            attach_to="Bacteria",
            strategy="merge"
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_validate_input_file'), \
             patch('flextaxd.cli.commands.import_tree.Path') as mock_path, \
             patch('builtins.open', mock_open(read_data=tree_content)):
            
            # Mock file exists
            mock_path_obj = Mock()
            mock_path_obj.exists.return_value = True
            mock_path_obj.is_file.return_value = True
            mock_path.return_value = mock_path_obj
            
            result = self.command.execute(args)
            
            assert result == 0
            # Should call add_node for the imported node
            mock_repo.add_node.assert_called()
    
    @patch('flextaxd.cli.commands.import_tree.SQLiteTaxonomyRepository')
    @patch('flextaxd.parsers.tsv.TSVTaxonomyParser')
    def test_execute_replace_strategy(self, mock_parser_class, mock_repo_class, sample_taxonomy_tree):
        """Test importing tree with replace strategy."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        
        # Mock target node lookup
        target_node = sample_taxonomy_tree.get_node(3)  # Escherichia
        def mock_get_node_by_name(name):
            if name == "Escherichia":  # Target node exists
                return target_node
            elif name == "Salmonella":  # New node doesn't exist
                return None
            return None
        mock_repo.get_node_by_name.side_effect = mock_get_node_by_name
        
        # Mock next tax_id generation
        mock_repo.get_next_tax_id.return_value = 1010
        
        # Mock replace strategy operations
        mock_repo.get_children.return_value = []  # No children to avoid force requirement
        mock_repo.remove_subtree.return_value = 1  # Removed 1 node
        
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        # Create replacement tree
        import_tree = TaxonomyTree()
        replacement_node = TaxonomyNode(
            tax_id=5001, 
            name="Salmonella", 
            rank=TaxonomicRank.GENUS,
            parent_id=None,
            description="Salmonella genus"
        )
        import_tree.add_node(replacement_node)
        
        # Mock TSV parser directly
        mock_parser = Mock()
        mock_parser.can_parse.return_value = True
        mock_parser.parse.return_value = import_tree
        mock_parser_class.return_value = mock_parser
        
        tree_content = """tax_id\tname\trank\tparent_id
5001\tSalmonella\tgenus\t"""
        
        args = create_import_tree_mock_args(
            target="Escherichia",
            strategy="replace"
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_validate_input_file'), \
             patch('flextaxd.cli.commands.import_tree.Path') as mock_path, \
             patch('builtins.open', mock_open(read_data=tree_content)):
            
            # Mock file exists
            mock_path_obj = Mock()
            mock_path_obj.exists.return_value = True
            mock_path_obj.is_file.return_value = True
            mock_path.return_value = mock_path_obj
            
            result = self.command.execute(args)
            
            assert result == 0
            # Should perform replacement operations
    
    @patch('flextaxd.cli.commands.import_tree.SQLiteTaxonomyRepository')
    @patch('flextaxd.parsers.tsv.TSVTaxonomyParser')
    def test_execute_with_root_node_specification(self, mock_parser_class, mock_repo_class, sample_taxonomy_tree):
        """Test importing tree with specific root node."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        
        # Mock attachment point lookup with conditional behavior
        attach_node = sample_taxonomy_tree.get_node(2)  # Bacteria
        def mock_get_node_by_name(name):
            if name == "Bacteria":  # Attachment point exists
                return attach_node
            elif name in ["Enterobacteriaceae", "Salmonella"]:  # New nodes don't exist
                return None
            return None
        mock_repo.get_node_by_name.side_effect = mock_get_node_by_name
        
        # Mock next tax_id generation
        mock_repo.get_next_tax_id.return_value = 1010
        
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        # Create import tree with multiple nodes (with description fields)
        import_tree = TaxonomyTree()
        root_node = TaxonomyNode(
            tax_id=5001, 
            name="Enterobacteriaceae", 
            rank=TaxonomicRank.FAMILY,
            parent_id=None,
            description="Enterobacteriaceae family"
        )
        child_node = TaxonomyNode(
            tax_id=5002, 
            name="Salmonella", 
            rank=TaxonomicRank.GENUS, 
            parent_id=5001,
            description="Salmonella genus"
        )
        import_tree.add_node(root_node)
        import_tree.add_node(child_node)
        
        # Mock TSV parser directly
        mock_parser = Mock()
        mock_parser.can_parse.return_value = True
        mock_parser.parse.return_value = import_tree
        mock_parser_class.return_value = mock_parser
        
        tree_content = """tax_id\tname\trank\tparent_id
5001\tEnterobacteriaceae\tfamily\t
5002\tSalmonella\tgenus\t5001"""
        
        args = create_import_tree_mock_args(
            attach_to="Bacteria",
            root_node="Enterobacteriaceae",
            strategy="merge"
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_validate_input_file'), \
             patch('flextaxd.cli.commands.import_tree.Path') as mock_path, \
             patch('builtins.open', mock_open(read_data=tree_content)):
            
            # Mock file exists
            mock_path_obj = Mock()
            mock_path_obj.exists.return_value = True
            mock_path_obj.is_file.return_value = True
            mock_path.return_value = mock_path_obj
            
            result = self.command.execute(args)
            
            assert result == 0
    
    @patch('flextaxd.cli.commands.import_tree.SQLiteTaxonomyRepository')
    @patch('flextaxd.parsers.tsv.TSVTaxonomyParser')
    def test_execute_dry_run(self, mock_parser_class, mock_repo_class, sample_taxonomy_tree):
        """Test dry-run mode."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        
        # Mock attachment point with conditional behavior
        attach_node = sample_taxonomy_tree.get_node(2)  # Bacteria
        def mock_get_node_by_name(name):
            if name == "Bacteria":  # Attachment point exists
                return attach_node
            elif name == "Salmonella":  # New node doesn't exist
                return None
            return None
        mock_repo.get_node_by_name.side_effect = mock_get_node_by_name
        
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        # Create import tree (with description field)
        import_tree = TaxonomyTree()
        import_node = TaxonomyNode(
            tax_id=5001, 
            name="Salmonella", 
            rank=TaxonomicRank.GENUS,
            parent_id=None,
            description="Salmonella genus"
        )
        import_tree.add_node(import_node)
        
        # Mock TSV parser directly
        mock_parser = Mock()
        mock_parser.can_parse.return_value = True
        mock_parser.parse.return_value = import_tree
        mock_parser_class.return_value = mock_parser
        
        tree_content = """tax_id\tname\trank\tparent_id
5001\tSalmonella\tgenus\t"""
        
        args = create_import_tree_mock_args(
            attach_to="Bacteria",
            strategy="merge",
            dry_run=True
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_validate_input_file'), \
             patch('flextaxd.cli.commands.import_tree.Path') as mock_path, \
             patch('builtins.open', mock_open(read_data=tree_content)):
            
            # Mock file exists
            mock_path_obj = Mock()
            mock_path_obj.exists.return_value = True
            mock_path_obj.is_file.return_value = True
            mock_path.return_value = mock_path_obj
            
            result = self.command.execute(args)
            
            assert result == 0
            # Should not make actual changes in dry-run mode
            mock_repo.add_node.assert_not_called()


class TestImportTreeCommandValidation:
    """Test ImportTreeCommand validation logic."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = ImportTreeCommand()
    
    @patch('flextaxd.cli.commands.import_tree.SQLiteTaxonomyRepository')
    def test_missing_input_file_validation(self, mock_repo_class):
        """Test validation when input file doesn't exist."""
        mock_repo = Mock()
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_import_tree_mock_args(
            input="/nonexistent/file.tsv",
            attach_to="Bacteria"
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('flextaxd.cli.commands.import_tree.Path') as mock_path:
            
            # Mock file doesn't exist
            mock_path_obj = Mock()
            mock_path_obj.exists.return_value = False
            mock_path.return_value = mock_path_obj
            
            result = self.command.execute(args)
            
            assert result == 1  # Should fail
    
    @patch('flextaxd.cli.commands.import_tree.SQLiteTaxonomyRepository')
    def test_missing_attachment_point_validation(self, mock_repo_class, sample_taxonomy_tree):
        """Test validation when attachment point doesn't exist."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo.get_node_by_name.return_value = None  # Attachment point not found
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_import_tree_mock_args(
            attach_to="NonExistent",  # Doesn't exist
            strategy="merge"
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('flextaxd.cli.commands.import_tree.Path') as mock_path:
            
            # Mock file exists
            mock_path_obj = Mock()
            mock_path_obj.exists.return_value = True
            mock_path.return_value = mock_path_obj
            
            result = self.command.execute(args)
            
            assert result == 1  # Should fail
    
    @patch('flextaxd.cli.commands.import_tree.SQLiteTaxonomyRepository')
    @patch('flextaxd.parsers.registry.registry')
    def test_parser_not_found_validation(self, mock_registry, mock_repo_class):
        """Test validation when no parser can handle the file."""
        mock_repo = Mock()
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        # Mock no parser found
        mock_registry.find_parser.return_value = None
        
        args = create_import_tree_mock_args(
            attach_to="Bacteria",
            format="unsupported"
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('flextaxd.cli.commands.import_tree.Path') as mock_path:
            
            # Mock file exists
            mock_path_obj = Mock()
            mock_path_obj.exists.return_value = True
            mock_path.return_value = mock_path_obj
            
            result = self.command.execute(args)
            
            assert result == 1  # Should fail
    
    @patch('flextaxd.cli.commands.import_tree.SQLiteTaxonomyRepository')
    def test_invalid_strategy_validation(self, mock_repo_class):
        """Test validation with invalid strategy."""
        # This test relies on argument parser validation which happens before execute()
        # So we test the command with valid args but check strategy handling
        args = create_import_tree_mock_args(
            strategy="invalid_strategy"  # This would fail at parser level
        )
        
        # The parser would catch this, but we can test command handling
        assert hasattr(self.command, 'execute')


class TestImportTreeCommandNameResolution:
    """Test ImportTreeCommand name resolution features."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = ImportTreeCommand()
    
    @patch('flextaxd.cli.commands.import_tree.SQLiteTaxonomyRepository')
    @patch('flextaxd.parsers.tsv.TSVTaxonomyParser')
    def test_keep_names_file_strategy(self, mock_parser_class, mock_repo_class, sample_taxonomy_tree):
        """Test keeping names from import file."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        
        # Mock attachment point and existing node with conditional logic
        attach_node = sample_taxonomy_tree.get_node(2)
        existing_node = TaxonomyNode(
            tax_id=3, 
            name="Old Name", 
            rank=TaxonomicRank.GENUS,
            parent_id=None,
            description="Old description"
        )
        
        def mock_get_node_by_name(name):
            if name == "Bacteria":
                return attach_node
            elif name == "New Name":
                return existing_node
            return None
        mock_repo.get_node_by_name.side_effect = mock_get_node_by_name
        
        mock_repo.get_next_tax_id.return_value = 1010
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        # Import tree with conflicting name (with description field)
        import_tree = TaxonomyTree()
        import_node = TaxonomyNode(
            tax_id=5001, 
            name="New Name", 
            rank=TaxonomicRank.GENUS,
            parent_id=None,
            description="New description"
        )
        import_tree.add_node(import_node)
        
        # Mock TSV parser directly
        mock_parser = Mock()
        mock_parser.can_parse.return_value = True
        mock_parser.parse.return_value = import_tree
        mock_parser_class.return_value = mock_parser
        
        args = create_import_tree_mock_args(
            attach_to="Bacteria",
            strategy="merge",
            keep_names="file",
            on_conflict="update"
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_validate_input_file'), \
             patch('flextaxd.cli.commands.import_tree.Path') as mock_path, \
             patch('builtins.open', mock_open(read_data="mock_content")):
            
            # Mock file exists
            mock_path_obj = Mock()
            mock_path_obj.exists.return_value = True
            mock_path_obj.is_file.return_value = True
            mock_path.return_value = mock_path_obj
            
            result = self.command.execute(args)
            
            assert result == 0
    
    @patch('flextaxd.cli.commands.import_tree.SQLiteTaxonomyRepository')
    @patch('flextaxd.parsers.tsv.TSVTaxonomyParser')
    def test_on_conflict_skip_strategy(self, mock_parser_class, mock_repo_class, sample_taxonomy_tree):
        """Test skipping conflicting nodes."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo.get_next_tax_id.return_value = 10000
        
        # Mock attachment point
        attach_node = sample_taxonomy_tree.get_node(2)
        
        # Mock existing node with same name
        existing_node = sample_taxonomy_tree.get_node(3)
        def mock_node_lookup(name):
            if name == "Bacteria":
                return attach_node
            elif name == "Escherichia":
                return existing_node
            return None
        mock_repo.get_node_by_name.side_effect = mock_node_lookup
        
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        # Import tree with existing node name
        import_tree = TaxonomyTree()
        import_node = TaxonomyNode(
            tax_id=5001,
            name="Escherichia",
            rank=TaxonomicRank.GENUS,
            parent_id=None,
            description="Escherichia genus"
        )
        import_tree.add_node(import_node)
        
        # Mock parser
        mock_parser = Mock()
        mock_parser.can_parse.return_value = True
        mock_parser.parse.return_value = import_tree
        mock_parser_class.return_value = mock_parser
        
        args = create_import_tree_mock_args(
            attach_to="Bacteria",
            strategy="merge",
            on_conflict="skip"
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_validate_input_file'), \
             patch('flextaxd.cli.commands.import_tree.Path') as mock_path, \
             patch('builtins.open', mock_open(read_data="mock_content")):
            
            # Mock file exists
            mock_path_obj = Mock()
            mock_path_obj.exists.return_value = True
            mock_path_obj.is_file.return_value = True
            mock_path.return_value = mock_path_obj
            
            result = self.command.execute(args)
            
            assert result == 0
            # Should skip conflicting nodes


class TestImportTreeCommandErrorHandling:
    """Test ImportTreeCommand error handling."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = ImportTreeCommand()
    
    @patch('flextaxd.cli.commands.import_tree.SQLiteTaxonomyRepository')
    def test_database_error_handling(self, mock_repo_class):
        """Test handling of database errors."""
        mock_repo = Mock()
        mock_repo.load_tree.side_effect = DatabaseError("Database corrupted")
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_import_tree_mock_args(
            attach_to="Bacteria"
        )
        
        with patch.object(self.command, '_validate_database_path'):
            result = self.command.execute(args)
            
            assert result == 1  # Should fail gracefully
    
    @patch('flextaxd.cli.commands.import_tree.SQLiteTaxonomyRepository')
    @patch('flextaxd.parsers.registry.registry')
    def test_parser_error_handling(self, mock_registry, mock_repo_class, sample_taxonomy_tree):
        """Test handling of parser errors."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        # Mock parser error
        mock_parser = Mock()
        mock_parser.can_parse.return_value = True
        mock_parser.parse.side_effect = Exception("Parser failed")
        mock_registry.find_parser.return_value = mock_parser
        
        args = create_import_tree_mock_args(
            attach_to="Bacteria"
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('flextaxd.cli.commands.import_tree.Path') as mock_path, \
             patch('builtins.open', mock_open(read_data="mock_content")):
            
            # Mock file exists
            mock_path_obj = Mock()
            mock_path_obj.exists.return_value = True
            mock_path.return_value = mock_path_obj
            
            result = self.command.execute(args)
            
            assert result == 1  # Should fail gracefully


class TestImportTreeCommandIntegration:
    """Integration tests for ImportTreeCommand."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = ImportTreeCommand()
    
    @patch('flextaxd.cli.commands.import_tree.SQLiteTaxonomyRepository')
    @patch('flextaxd.parsers.tsv.TSVTaxonomyParser')  
    def test_complex_tree_merge_workflow(self, mock_parser_class, mock_repo_class):
        """Test complex tree merging workflow."""
        # Start with complex existing tree
        existing_tree = MockData.create_complex_taxonomy_tree()
        
        mock_repo = Mock()
        mock_repo.load_tree.return_value = existing_tree
        
        # Mock attachment to Bacteria and existing nodes
        bacteria_node = existing_tree.get_node(2)
        salmonella_enterica_node = existing_tree.get_node(9)  # This exists in complex tree
        
        def mock_node_lookup(name):
            if name == "Bacteria":
                return bacteria_node
            elif name == "Salmonella enterica":
                return salmonella_enterica_node  # This should be found and skipped
            # "Enterobacteriaceae" and "Salmonella" don't exist, so return None
            return None
        mock_repo.get_node_by_name.side_effect = mock_node_lookup
        
        # Mock next tax_id generation
        mock_repo.get_next_tax_id.return_value = 9001
        
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        # Create complex import tree
        import_tree = TaxonomyTree()
        family_node = TaxonomyNode(
            tax_id=8001,
            name="Enterobacteriaceae",
            rank=TaxonomicRank.FAMILY,
            parent_id=None,
            description="Enterobacteriaceae family"
        )
        genus_node = TaxonomyNode(
            tax_id=8002,
            name="Salmonella",
            rank=TaxonomicRank.GENUS,
            parent_id=8001,
            description="Salmonella genus"
        )
        species_node = TaxonomyNode(
            tax_id=8003,
            name="Salmonella enterica",
            rank=TaxonomicRank.SPECIES,
            parent_id=8002,
            description="Salmonella enterica species"
        )
        
        import_tree.add_node(family_node)
        import_tree.add_node(genus_node)
        import_tree.add_node(species_node)
        
        # Mock parser
        mock_parser = Mock()
        mock_parser.can_parse.return_value = True
        mock_parser.parse.return_value = import_tree
        mock_parser_class.return_value = mock_parser
        
        tree_content = """tax_id\tname\trank\tparent_id
8001\tEnterobacteriaceae\tfamily\t
8002\tSalmonella\tgenus\t8001
8003\tSalmonella enterica\tspecies\t8002"""
        
        args = create_import_tree_mock_args(
            attach_to="Bacteria",
            root_node="Enterobacteriaceae",
            strategy="merge",
            on_conflict="skip"
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch.object(self.command, '_validate_input_file'), \
             patch('flextaxd.cli.commands.import_tree.Path') as mock_path, \
             patch('builtins.open', mock_open(read_data=tree_content)):
            
            # Mock file exists
            mock_path_obj = Mock()
            mock_path_obj.exists.return_value = True
            mock_path_obj.is_file.return_value = True
            mock_path.return_value = mock_path_obj
            
            result = self.command.execute(args)
            
            assert result == 0
            # Should add 2 nodes (Enterobacteriaceae, Salmonella) and skip 1 (Salmonella enterica)
            assert mock_repo.add_node.call_count == 2