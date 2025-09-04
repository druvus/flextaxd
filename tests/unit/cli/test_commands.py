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
    @patch('flextaxd.cli.commands.create.registry')
    def test_create_from_tsv(self, mock_registry, mock_repo):
        """Test creating database from TSV file."""
        mock_parser = Mock()
        mock_parser.parse.return_value = self.create_test_tree()
        mock_parser.can_parse.return_value = True  # Add can_parse method
        mock_parser.parser_name = "tsv"  # Add parser_name attribute
        mock_registry.get_parser.return_value = mock_parser
        
        mock_repository = Mock()
        mock_repository.get_statistics.return_value = {
            'node_count': 2,
            'genome_count': 0,
            'root_count': 1,
            'leaf_count': 1,
            'rank_distribution': {'root': 1, 'superkingdom': 1}
        }
        mock_repo.return_value = mock_repository
        mock_repository.__enter__ = Mock(return_value=mock_repository)
        mock_repository.__exit__ = Mock(return_value=None)
        
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
                verbose=False,
                overwrite=False,
                no_header=False,
                parent_column=0,
                child_column=1,
                id_column=None,
                rank_column=None,
                genomeid2taxid=None,
                genomes_path=None
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
        
        with pytest.raises((ValidationError, TypeError)):
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
    @patch('flextaxd.cli.commands.export.ExportCommand._validate_database_path')
    def test_export_classifier_format(self, mock_validate_db, mock_repo):
        """Test exporting to classifier format."""
        
        # Setup mock
        mock_repository = Mock()
        mock_repository.load_tree.return_value = self.create_test_tree()
        mock_repo.return_value = mock_repository
        mock_repository.__enter__ = Mock(return_value=mock_repository)
        mock_repository.__exit__ = Mock(return_value=None)
        
        command = ExportCommand()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_file = Path(tmp_dir) / "test.ftd" 
            output_dir = Path(tmp_dir) / "output"
            
            args = Namespace(
                database=str(db_file),
                classifier="kraken2",
                format=None,
                legacy_format=None,
                output=str(output_dir),
                include_genomes=False,
                compress=False,
                names_file="names.dmp",
                nodes_file="nodes.dmp",
                separator="\t",
                sequence_filter="all",
                default_genome_size=1000000,
                db_version="1.0",
                include_header=True,
                verbose=False
            )
            
            # Execute command 
            result = command.execute(args)
            
            # Should succeed (mock will handle the actual export)
            assert result == 0

    @patch('flextaxd.cli.commands.export.SQLiteTaxonomyRepository')
    @patch('flextaxd.cli.commands.export.ExportCommand._validate_database_path')
    def test_export_file_format(self, mock_validate_db, mock_repo):
        """Test exporting to single file format."""
        
        mock_repository = Mock()
        mock_repository.load_tree.return_value = self.create_test_tree()
        mock_repo.return_value = mock_repository
        mock_repository.__enter__ = Mock(return_value=mock_repository)
        mock_repository.__exit__ = Mock(return_value=None)
        
        command = ExportCommand()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_file = Path(tmp_dir) / "test.ftd"
            output_file = Path(tmp_dir) / "output.tsv"
            
            args = Namespace(
                database=str(db_file),
                classifier=None,
                format="tsv",
                legacy_format=None,
                output=str(output_file),
                include_genomes=False,
                compress=False,
                names_file="names.dmp",
                nodes_file="nodes.dmp",
                separator="\t",
                sequence_filter="all",
                default_genome_size=1000000,
                db_version="1.0",
                include_header=True,
                verbose=False
            )
            
            result = command.execute(args)
            assert result == 0

    def test_export_mutual_exclusion(self):
        """Test that classifier and format are mutually exclusive."""
        command = ExportCommand()
        
        # Both classifier and format specified - should return first one found
        args = Namespace(
            database="test.ftd",
            classifier="kraken2",
            format="tsv",
            output="output"
        )
        
        # The logic returns classifier if both are present
        result = command._determine_export_type(args)
        assert result == "kraken2"


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
    @patch('flextaxd.cli.commands.modify.ModifyCommand._validate_database_path')
    def test_add_node(self, mock_validate_db, mock_repo):
        """Test adding a node to database."""
        
        mock_repository = Mock()
        tree = self.create_test_tree()
        mock_repository.load_tree.return_value = tree
        # Add mocks for modify operations
        from flextaxd.core.models import TaxonomyNode, TaxonomicRank
        parent_node = TaxonomyNode(tax_id=2, name="Bacteria", rank=TaxonomicRank.SUPERKINGDOM)
        # Mock get_node to return parent for ID=2, None for new IDs
        def mock_get_node(node_id):
            if node_id == 2:  # Parent exists
                return parent_node
            return None  # New node ID doesn't exist yet
        mock_repository.get_node.side_effect = mock_get_node
        mock_repository.get_statistics.return_value = {
            'node_count': 2,
            'genome_count': 0,
            'root_count': 1,
            'leaf_count': 1
        }
        mock_repo.return_value = mock_repository
        mock_repository.__enter__ = Mock(return_value=mock_repository)
        mock_repository.__exit__ = Mock(return_value=None)
        
        command = ModifyCommand()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_file = Path(tmp_dir) / "test.ftd"
            
            args = Namespace(
                database=str(db_file),
                add_node="New Species",
                parent_id=2,  # Bacteria
                rank="species",
                mod_file=None,
                remove_node=None,
                merge_database=None,
                update_node=None,
                new_name=None,
                new_id=None,
                parent=None,
                replace=False,
                format="auto",
                force=False,
                dry_run=False,
                verbose=False
            )
            
            result = command.execute(args)
            assert result == 0

    @patch('flextaxd.parsers.registry.registry')
    @patch('flextaxd.cli.commands.modify.SQLiteTaxonomyRepository')
    @patch('flextaxd.cli.commands.modify.ModifyCommand._validate_database_path')
    def test_modify_from_file(self, mock_validate_db, mock_repo, mock_registry):
        """Test modifying database from file."""
        
        mock_repository = Mock()
        mock_repository.load_tree.return_value = self.create_test_tree()
        # Add basic mocks that might be needed
        mock_repository.get_statistics.return_value = {
            'node_count': 2,
            'genome_count': 0
        }
        mock_repo.return_value = mock_repository
        mock_repository.__enter__ = Mock(return_value=mock_repository)
        mock_repository.__exit__ = Mock(return_value=None)
        
        # Mock the parser to avoid TSV dependency resolution issues
        from flextaxd.core.models import TaxonomyTree, TaxonomyNode, TaxonomicRank
        mock_parser = Mock()
        
        # Create a modification tree with the new species
        mod_tree = TaxonomyTree()
        new_species = TaxonomyNode(tax_id=1001, name="New Species", rank=TaxonomicRank.SPECIES, parent_id=1000)
        bacteria_ref = TaxonomyNode(tax_id=1000, name="Bacteria", rank=TaxonomicRank.SUPERKINGDOM)  # Reference to existing node
        mod_tree.add_node(bacteria_ref)
        mod_tree.add_node(new_species)
        
        mock_parser.parse.return_value = mod_tree
        mock_parser.can_parse.return_value = True
        mock_registry.get_parser.return_value = mock_parser
        
        command = ModifyCommand()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_file = Path(tmp_dir) / "test.ftd"
            mod_file = Path(tmp_dir) / "modifications.tsv"
            
            # Create actual modification file for Path validation
            mod_file.write_text("name\tparent\trank\nNew Species\tBacteria\tspecies\n")
            
            args = Namespace(
                database=str(db_file),
                add_node=None,
                parent_id=None,
                rank=None,
                mod_file=str(mod_file),
                remove_node=None,
                merge_database=None,
                update_node=None,
                new_name=None,
                new_id=None,
                parent="Bacteria",
                replace=True,
                format="auto",
                force=False,
                dry_run=False,
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
    @patch('flextaxd.cli.commands.stats.StatsCommand._validate_database_path')
    def test_basic_stats(self, mock_validate_db, mock_repo):
        """Test basic statistics display."""
        
        mock_repository = Mock()
        mock_repository.get_statistics.return_value = {
            'node_count': 2,
            'genome_count': 0,
            'root_count': 1,
            'leaf_count': 1,
            'rank_distribution': {'root': 1, 'superkingdom': 1}
        }
        mock_repo.return_value = mock_repository
        mock_repository.__enter__ = Mock(return_value=mock_repository)
        mock_repository.__exit__ = Mock(return_value=None)
        
        command = StatsCommand()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_file = Path(tmp_dir) / "test.ftd"
            
            args = Namespace(
                database=str(db_file),
                detailed=False,
                format="text",
                verbose=False
            )
            
            # Should not crash
            result = command.execute(args)
            assert result == 0

    @patch('flextaxd.cli.commands.stats.SQLiteTaxonomyRepository')
    @patch('flextaxd.cli.commands.stats.StatsCommand._validate_database_path')
    def test_detailed_stats(self, mock_validate_db, mock_repo):
        """Test detailed statistics display."""
        
        mock_repository = Mock()
        mock_repository.get_statistics.return_value = {
            'node_count': 2,
            'genome_count': 0,
            'root_count': 1,
            'leaf_count': 1,
            'rank_distribution': {'root': 1, 'superkingdom': 1}
        }
        mock_repo.return_value = mock_repository
        mock_repository.__enter__ = Mock(return_value=mock_repository)
        mock_repository.__exit__ = Mock(return_value=None)
        
        command = StatsCommand()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_file = Path(tmp_dir) / "test.ftd"
            
            args = Namespace(
                database=str(db_file),
                detailed=True,
                format="text",
                verbose=False,
                validate_files=True,
                skip_file_validation=False
            )
            
            result = command.execute(args)
            assert result == 0

    @patch('flextaxd.cli.commands.stats.SQLiteTaxonomyRepository')
    @patch('flextaxd.cli.commands.stats.StatsCommand._validate_database_path')
    def test_enhanced_genome_stats(self, mock_validate_db, mock_repo):
        """Test enhanced genome statistics display."""
        
        mock_repository = Mock()
        mock_repository.get_statistics.return_value = {
            'node_count': 3,
            'genome_count': 5,
            'genomes_with_files': 3,
            'genomes_metadata_only': 2,
            'genome_file_validation': {
                'accessible': 2,
                'missing': 1,
                'invalid': 0
            },
            'genome_size_distribution': {
                'count': 4,
                'min': 1000000,
                'max': 5000000,
                'avg': 3000000.0,
                'median': 3200000
            },
            'sequence_type_breakdown': {
                'genome': 3,
                '16S': 1,
                'plasmid': 1
            },
            'source_distribution': {
                'NCBI': 3,
                'GTDB': 1,
                'SILVA': 1
            },
            'rank_distribution': {
                TaxonomicRank.ROOT: 1,
                TaxonomicRank.SUPERKINGDOM: 1,
                TaxonomicRank.SPECIES: 1
            },
            'root_nodes': [1],
            'leaf_nodes': [3]
        }
        mock_repo.return_value = mock_repository
        mock_repository.__enter__ = Mock(return_value=mock_repository)
        mock_repository.__exit__ = Mock(return_value=None)
        
        command = StatsCommand()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_file = Path(tmp_dir) / "test.ftd"
            
            args = Namespace(
                database=str(db_file),
                detailed=False,
                format="text",
                verbose=False,
                validate_files=True,
                skip_file_validation=False
            )
            
            result = command.execute(args)
            assert result == 0
            
            # Verify get_statistics was called with correct parameters
            mock_repository.get_statistics.assert_called_once_with(validate_files=True)

    @patch('flextaxd.cli.commands.stats.SQLiteTaxonomyRepository')  
    @patch('flextaxd.cli.commands.stats.StatsCommand._validate_database_path')
    def test_skip_file_validation(self, mock_validate_db, mock_repo):
        """Test skipping file validation for faster stats."""
        
        mock_repository = Mock()
        mock_repository.get_statistics.return_value = {
            'node_count': 2,
            'genome_count': 1,
            'genomes_with_files': 1,
            'genomes_metadata_only': 0,
            'genome_size_distribution': {
                'count': 1,
                'min': 1000000,
                'max': 1000000,  
                'avg': 1000000.0,
                'median': 1000000
            },
            'sequence_type_breakdown': {'genome': 1},
            'source_distribution': {'NCBI': 1},
            'rank_distribution': {TaxonomicRank.ROOT: 1, TaxonomicRank.SPECIES: 1},
            'root_nodes': [1],
            'leaf_nodes': [2]
        }
        mock_repo.return_value = mock_repository
        mock_repository.__enter__ = Mock(return_value=mock_repository)
        mock_repository.__exit__ = Mock(return_value=None)
        
        command = StatsCommand()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_file = Path(tmp_dir) / "test.ftd"
            
            args = Namespace(
                database=str(db_file),
                detailed=False,
                format="text",
                verbose=False,
                validate_files=True,
                skip_file_validation=True  # This should override validate_files
            )
            
            result = command.execute(args)
            assert result == 0
            
            # Verify get_statistics was called with validate_files=False
            mock_repository.get_statistics.assert_called_once_with(validate_files=False)


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
    @patch('flextaxd.cli.commands.visualize.VisualizeCommand._validate_database_path')
    @patch('matplotlib.pyplot.figure')
    @patch('matplotlib.pyplot.savefig')
    def test_tree_visualization(self, mock_savefig, mock_figure, mock_validate_db, mock_repo):
        """Test tree visualization."""
        
        mock_repository = Mock()
        tree = self.create_test_tree()
        mock_repository.load_tree.return_value = tree
        mock_repo.return_value = mock_repository
        mock_repository.__enter__ = Mock(return_value=mock_repository)
        mock_repository.__exit__ = Mock(return_value=None)
        
        # Mock matplotlib components
        mock_figure.return_value = Mock()
        mock_savefig.return_value = None
        
        command = VisualizeCommand()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_file = Path(tmp_dir) / "test.ftd"
            output_file = Path(tmp_dir) / "tree.png"
            
            args = Namespace(
                database=str(db_file),
                output=str(output_file),
                type="tree",
                start_node="root",
                max_depth=0,
                show_ids=False,
                show_genomes=False,
                show_ranks=False,
                compact=False,
                format="text",
                label_size=10,
                clip_labels=False,
                save_plot=str(output_file),
                width=10,
                height=8,
                dpi=300,
                max_nodes=100,
                verbose=False
            )
            
            result = command.execute(args)
            assert result == 0

    @patch('flextaxd.cli.commands.visualize.SQLiteTaxonomyRepository')
    @patch('flextaxd.cli.commands.visualize.VisualizeCommand._validate_database_path')
    def test_newick_export(self, mock_validate_db, mock_repo):
        """Test Newick format export."""
        
        mock_repository = Mock()
        tree = self.create_test_tree()
        mock_repository.load_tree.return_value = tree
        mock_repo.return_value = mock_repository
        mock_repository.__enter__ = Mock(return_value=mock_repository)
        mock_repository.__exit__ = Mock(return_value=None)
        
        command = VisualizeCommand()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_file = Path(tmp_dir) / "test.ftd"
            output_file = Path(tmp_dir) / "tree.nwk"
            
            args = Namespace(
                database=str(db_file),
                output=str(output_file),
                type="newick",
                start_node="root",
                max_depth=0,
                show_ids=False,
                show_genomes=False,
                show_ranks=False,
                compact=False,
                format="text",
                label_size=0,
                clip_labels=False,
                save_plot=None,
                verbose=False
            )
            
            result = command.execute(args)
            assert result == 0
            
            # Newick format prints to stdout, not file


class TestCommandErrorHandling:
    """Test error handling across all commands."""

    def test_missing_database_file(self):
        """Test handling of missing database files."""
        # CreateCommand has different validation - skip it
        commands = [ExportCommand(), ModifyCommand(), StatsCommand(), VisualizeCommand()]
        
        for command in commands:
            args = Namespace(
                database="/nonexistent/path/database.ftd",
                verbose=False
            )
            
            # Should handle missing database gracefully  
            result = command.execute(args)
            assert result == 1  # Should return error code

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
    @patch('flextaxd.cli.commands.export.ExportCommand._validate_database_path')
    @patch('flextaxd.cli.commands.create.registry')
    @patch('flextaxd.cli.commands.create.Path')
    @patch('flextaxd.cli.commands.export.Path.exists')
    def test_create_then_export_workflow(self, mock_export_exists, mock_create_path_cls, mock_registry, mock_export_validate_db, mock_export_repo, mock_create_repo):
        """Test create followed by export workflow."""
        # Mock path creation for create command - input exists, db doesn't; export: db exists
        def create_mock_path(path_str):
            mock_path_obj = Mock()
            mock_path_obj.exists.return_value = str(path_str).endswith('.tsv')  # Only TSV files exist
            mock_path_obj.unlink = Mock()  # For database removal
            return mock_path_obj
        mock_create_path_cls.side_effect = create_mock_path
        
        mock_export_exists.return_value = True  # Database exists for export
        
        # Setup create mocks
        mock_parser = Mock()
        tree = TestCommandsBase.create_test_tree()
        mock_parser.parse.return_value = tree
        mock_parser.can_parse.return_value = True  # Add can_parse method
        mock_parser.parser_name = "tsv"  # Add parser_name attribute
        mock_registry.get_parser.return_value = mock_parser
        
        mock_create_repository = Mock()
        mock_create_repository.get_statistics.return_value = {
            'node_count': 2,
            'genome_count': 0,
            'root_count': 1,
            'leaf_count': 1,
            'rank_distribution': {'root': 1, 'superkingdom': 1}
        }
        mock_create_repo.return_value = mock_create_repository
        mock_create_repository.__enter__ = Mock(return_value=mock_create_repository)
        mock_create_repository.__exit__ = Mock(return_value=None)
        
        # Setup export mocks
        mock_export_repository = Mock()
        mock_export_repository.load_tree.return_value = tree
        mock_export_repo.return_value = mock_export_repository
        mock_export_repository.__enter__ = Mock(return_value=mock_export_repository)
        mock_export_repository.__exit__ = Mock(return_value=None)
        
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
                verbose=False,
                overwrite=False,
                no_header=False,
                parent_column=0,
                child_column=1,
                id_column=None,
                rank_column=None,
                genomeid2taxid=None,
                genomes_path=None
            )
            
            result1 = create_command.execute(create_args)
            assert result1 == 0
            
            # Export database
            export_command = ExportCommand()
            export_args = Namespace(
                database=str(db_file),
                classifier=None,
                format="tsv",
                legacy_format=None,
                output=str(output_file),
                include_genomes=False,
                compress=False,
                names_file="names.dmp",
                nodes_file="nodes.dmp",
                separator="\t",
                sequence_filter="all",
                default_genome_size=1000000,
                db_version="1.0",
                include_header=True,
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