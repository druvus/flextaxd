"""Unit tests for CLI commands."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from argparse import Namespace

from flextaxd.core.models import TaxonomyTree, TaxonomyNode, TaxonomicRank
from flextaxd.core.exceptions import ValidationError, DatabaseError
from flextaxd.cli.commands.create import CreateCommand
from flextaxd.cli.commands.export import ExportCommand  
from flextaxd.cli.commands.modify import ModifyCommand
from flextaxd.cli.commands.stats import StatsCommand
from flextaxd.cli.commands.visualize import VisualizeCommand


class TestCommandsBase:
    """Base class for command tests."""

    @staticmethod
    def create_test_tree():
        """Create a simple test taxonomy tree."""
        tree = TaxonomyTree()
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        tree.add_node(root)
        
        bacteria = TaxonomyNode(tax_id=2, name="Bacteria", rank=TaxonomicRank.SUPERKINGDOM, parent_id=1)
        tree.add_node(bacteria)
        
        return tree


class TestCreateCommand(TestCommandsBase):
    """Test create command functionality."""

    def test_command_registration(self):
        """Test that create command can be registered."""
        # Mock subparsers
        subparsers = Mock()
        mock_parser = Mock()
        subparsers.add_parser.return_value = mock_parser
        
        # Should not raise exception
        parser = CreateCommand.register_parser(subparsers)
        assert parser is not None
        
        # Verify parser setup was called
        subparsers.add_parser.assert_called_once()

    @patch('flextaxd.cli.commands.create.SQLiteTaxonomyRepository')
    @patch('flextaxd.cli.commands.create.ParserRegistry')
    def test_create_from_tsv(self, mock_registry, mock_repo):
        """Test creating database from TSV file."""
        # Setup mocks
        mock_parser = Mock()
        mock_parser.parse.return_value = self.create_test_tree()
        mock_registry.return_value.get_parser.return_value = mock_parser
        
        mock_repository = Mock()
        mock_repo.return_value = mock_repository
        
        # Create command
        command = CreateCommand()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_file = Path(tmp_dir) / "test.tsv"
            input_file.write_text("child\tparent\trank\nBacteria\troot\tsuperkingdom\n")
            
            output_db = Path(tmp_dir) / "test.ftd"
            
            args = Namespace(
                input=str(input_file),
                database=str(output_db), 
                format="tsv",
                verbose=False
            )
            
            # Execute command
            result = command.execute(args)
            
            # Should succeed
            assert result == 0
            
            # Verify interactions
            mock_parser.parse.assert_called_once()
            mock_repository.save_tree.assert_called_once()

    def test_create_validation(self):
        """Test input validation for create command."""
        command = CreateCommand()
        
        # Missing input file
        args = Namespace(input=None, database="test.ftd", format="tsv")
        
        with pytest.raises((ValidationError, AttributeError)):
            command.execute(args)


class TestExportCommand(TestCommandsBase):
    """Test export command functionality."""

    def test_command_registration(self):
        """Test that export command can be registered."""
        subparsers = Mock()
        mock_parser = Mock()
        subparsers.add_parser.return_value = mock_parser
        
        parser = ExportCommand.register_parser(subparsers)
        assert parser is not None

    @patch('flextaxd.cli.commands.export.SQLiteTaxonomyRepository')
    def test_export_classifier_format(self, mock_repo):
        """Test exporting to classifier format."""
        # Setup mock
        mock_repository = Mock()
        mock_repository.load_tree.return_value = self.create_test_tree()
        mock_repo.return_value = mock_repository
        
        command = ExportCommand()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_file = Path(tmp_dir) / "test.ftd" 
            output_dir = Path(tmp_dir) / "output"
            
            args = Namespace(
                database=str(db_file),
                classifier="kraken2",
                format=None,
                output=str(output_dir),
                verbose=False
            )
            
            # Execute command 
            result = command.execute(args)
            
            # Should succeed (mock will handle the actual export)
            assert result == 0

    @patch('flextaxd.cli.commands.export.SQLiteTaxonomyRepository')
    def test_export_file_format(self, mock_repo):
        """Test exporting to single file format."""
        mock_repository = Mock()
        mock_repository.load_tree.return_value = self.create_test_tree()
        mock_repo.return_value = mock_repository
        
        command = ExportCommand()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_file = Path(tmp_dir) / "test.ftd"
            output_file = Path(tmp_dir) / "output.tsv"
            
            args = Namespace(
                database=str(db_file),
                classifier=None,
                format="tsv", 
                output=str(output_file),
                verbose=False
            )
            
            result = command.execute(args)
            assert result == 0

    def test_export_mutual_exclusion(self):
        """Test that classifier and format are mutually exclusive."""
        command = ExportCommand()
        
        # Both classifier and format specified should fail
        args = Namespace(
            database="test.ftd",
            classifier="kraken2",
            format="tsv",
            output="output"
        )
        
        # This would be caught by argument parser in real usage
        # Here we test the command logic
        with pytest.raises((ValidationError, AttributeError)):
            command._determine_export_type(args)


class TestModifyCommand(TestCommandsBase):
    """Test modify command functionality."""

    def test_command_registration(self):
        """Test that modify command can be registered."""
        subparsers = Mock()
        mock_parser = Mock()
        subparsers.add_parser.return_value = mock_parser
        
        parser = ModifyCommand.register_parser(subparsers)
        assert parser is not None

    @patch('flextaxd.cli.commands.modify.SQLiteTaxonomyRepository')
    def test_add_node(self, mock_repo):
        """Test adding a node to database."""
        mock_repository = Mock()
        tree = self.create_test_tree()
        mock_repository.load_tree.return_value = tree
        mock_repo.return_value = mock_repository
        
        command = ModifyCommand()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_file = Path(tmp_dir) / "test.ftd"
            
            args = Namespace(
                database=str(db_file),
                add_node="New Species",
                parent_id=2,  # Bacteria
                rank="species",
                mod_file=None,
                replace=False,
                verbose=False
            )
            
            result = command.execute(args)
            assert result == 0
            
            # Verify tree was modified and saved
            mock_repository.save_tree.assert_called_once()

    @patch('flextaxd.cli.commands.modify.SQLiteTaxonomyRepository')
    def test_modify_from_file(self, mock_repo):
        """Test modifying database from file."""
        mock_repository = Mock()
        mock_repository.load_tree.return_value = self.create_test_tree()
        mock_repo.return_value = mock_repository
        
        command = ModifyCommand()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_file = Path(tmp_dir) / "test.ftd"
            mod_file = Path(tmp_dir) / "modifications.tsv"
            
            # Create modification file
            mod_file.write_text("name\tparent\trank\nNew Species\tBacteria\tspecies\n")
            
            args = Namespace(
                database=str(db_file),
                add_node=None,
                parent_id=None,
                rank=None,
                mod_file=str(mod_file),
                parent="Bacteria",
                replace=True,
                verbose=False
            )
            
            result = command.execute(args)
            assert result == 0


class TestStatsCommand(TestCommandsBase):
    """Test stats command functionality."""

    def test_command_registration(self):
        """Test that stats command can be registered."""
        subparsers = Mock()
        mock_parser = Mock()
        subparsers.add_parser.return_value = mock_parser
        
        parser = StatsCommand.register_parser(subparsers)
        assert parser is not None

    @patch('flextaxd.cli.commands.stats.SQLiteTaxonomyRepository')
    def test_basic_stats(self, mock_repo):
        """Test basic statistics display."""
        mock_repository = Mock()
        tree = self.create_test_tree()
        mock_repository.load_tree.return_value = tree
        mock_repo.return_value = mock_repository
        
        command = StatsCommand()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_file = Path(tmp_dir) / "test.ftd"
            
            args = Namespace(
                database=str(db_file),
                detailed=False,
                verbose=False
            )
            
            # Should not crash
            result = command.execute(args)
            assert result == 0

    @patch('flextaxd.cli.commands.stats.SQLiteTaxonomyRepository')
    def test_detailed_stats(self, mock_repo):
        """Test detailed statistics display."""
        mock_repository = Mock()
        tree = self.create_test_tree()
        mock_repository.load_tree.return_value = tree
        mock_repo.return_value = mock_repository
        
        command = StatsCommand()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_file = Path(tmp_dir) / "test.ftd"
            
            args = Namespace(
                database=str(db_file),
                detailed=True,
                verbose=False
            )
            
            result = command.execute(args)
            assert result == 0


class TestVisualizeCommand(TestCommandsBase):
    """Test visualize command functionality."""

    def test_command_registration(self):
        """Test that visualize command can be registered."""
        subparsers = Mock()
        mock_parser = Mock()
        subparsers.add_parser.return_value = mock_parser
        
        parser = VisualizeCommand.register_parser(subparsers)
        assert parser is not None

    @patch('flextaxd.cli.commands.visualize.SQLiteTaxonomyRepository')
    @patch('flextaxd.cli.commands.visualize.matplotlib')
    @patch('flextaxd.cli.commands.visualize.plt')
    def test_tree_visualization(self, mock_plt, mock_matplotlib, mock_repo):
        """Test tree visualization."""
        mock_repository = Mock()
        tree = self.create_test_tree()
        mock_repository.load_tree.return_value = tree
        mock_repo.return_value = mock_repository
        
        command = VisualizeCommand()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_file = Path(tmp_dir) / "test.ftd"
            output_file = Path(tmp_dir) / "tree.png"
            
            args = Namespace(
                database=str(db_file),
                output=str(output_file),
                type="tree",
                width=10,
                height=8,
                dpi=300,
                label_size=10,
                max_nodes=100,
                verbose=False
            )
            
            # Mock matplotlib components
            mock_plt.figure.return_value = Mock()
            mock_plt.savefig.return_value = None
            
            result = command.execute(args)
            assert result == 0

    @patch('flextaxd.cli.commands.visualize.SQLiteTaxonomyRepository')
    def test_newick_export(self, mock_repo):
        """Test Newick format export."""
        mock_repository = Mock()
        tree = self.create_test_tree()
        mock_repository.load_tree.return_value = tree
        mock_repo.return_value = mock_repository
        
        command = VisualizeCommand()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_file = Path(tmp_dir) / "test.ftd"
            output_file = Path(tmp_dir) / "tree.nwk"
            
            args = Namespace(
                database=str(db_file),
                output=str(output_file),
                type="newick",
                verbose=False
            )
            
            result = command.execute(args)
            assert result == 0
            
            # Should create newick file
            assert output_file.exists()


class TestCommandErrorHandling:
    """Test error handling across all commands."""

    def test_missing_database_file(self):
        """Test handling of missing database files."""
        commands = [CreateCommand(), ExportCommand(), ModifyCommand(), StatsCommand(), VisualizeCommand()]
        
        for command in commands:
            args = Namespace(
                database="/nonexistent/path/database.ftd",
                verbose=False
            )
            
            # Should handle missing database gracefully
            with pytest.raises((DatabaseError, FileNotFoundError)):
                command.execute(args)

    def test_invalid_arguments(self):
        """Test handling of invalid command arguments.""" 
        # Test with None args
        commands = [CreateCommand(), ExportCommand(), ModifyCommand(), StatsCommand(), VisualizeCommand()]
        
        for command in commands:
            with pytest.raises((AttributeError, ValidationError)):
                command.execute(None)

    @patch('flextaxd.cli.commands.create.SQLiteTaxonomyRepository')
    def test_database_corruption_handling(self, mock_repo):
        """Test handling of corrupted database files."""
        # Simulate database corruption
        mock_repo.side_effect = DatabaseError("Database is corrupted")
        
        command = CreateCommand()
        args = Namespace(
            input="input.tsv",
            database="corrupted.ftd", 
            format="tsv",
            verbose=False
        )
        
        result = command.execute(args)
        # Should return error code
        assert result != 0


class TestCommandIntegration:
    """Integration tests for command workflows."""

    @patch('flextaxd.cli.commands.create.SQLiteTaxonomyRepository')
    @patch('flextaxd.cli.commands.export.SQLiteTaxonomyRepository') 
    @patch('flextaxd.cli.commands.create.ParserRegistry')
    def test_create_then_export_workflow(self, mock_registry, mock_export_repo, mock_create_repo):
        """Test create followed by export workflow."""
        # Setup create mocks
        mock_parser = Mock()
        tree = TestCommandsBase.create_test_tree()
        mock_parser.parse.return_value = tree
        mock_registry.return_value.get_parser.return_value = mock_parser
        
        mock_create_repository = Mock()
        mock_create_repo.return_value = mock_create_repository
        
        # Setup export mocks
        mock_export_repository = Mock()
        mock_export_repository.load_tree.return_value = tree
        mock_export_repo.return_value = mock_export_repository
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_file = Path(tmp_dir) / "input.tsv"
            input_file.write_text("child\tparent\trank\nBacteria\troot\tsuperkingdom\n")
            
            db_file = Path(tmp_dir) / "test.ftd"
            output_file = Path(tmp_dir) / "output.tsv"
            
            # Create database
            create_command = CreateCommand()
            create_args = Namespace(
                input=str(input_file),
                database=str(db_file),
                format="tsv", 
                verbose=False
            )
            
            result1 = create_command.execute(create_args)
            assert result1 == 0
            
            # Export database
            export_command = ExportCommand()
            export_args = Namespace(
                database=str(db_file),
                classifier=None,
                format="tsv",
                output=str(output_file),
                verbose=False
            )
            
            result2 = export_command.execute(export_args)
            assert result2 == 0

    def test_command_help_messages(self):
        """Test that all commands provide help messages."""
        commands = [CreateCommand, ExportCommand, ModifyCommand, StatsCommand, VisualizeCommand]
        
        for command_class in commands:
            # Mock subparsers
            subparsers = Mock()
            mock_parser = Mock()
            subparsers.add_parser.return_value = mock_parser
            
            # Should not raise exception
            parser = command_class.register_parser(subparsers)
            assert parser is not None
            
            # Verify help was configured
            subparsers.add_parser.assert_called()
            call_args = subparsers.add_parser.call_args
            assert "help" in call_args[1] or len(call_args[0]) > 1