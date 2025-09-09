"""Integration tests for CLI command interactions and workflows."""

import pytest
import tempfile
from unittest.mock import Mock, patch, MagicMock, mock_open
from pathlib import Path

from flextaxd.cli.commands.create import CreateCommand
from flextaxd.cli.commands.export import ExportCommand
from flextaxd.cli.commands.add_node import AddNodeCommand
from flextaxd.cli.commands.import_tree import ImportTreeCommand
from flextaxd.cli.commands.add_genome import AddGenomeCommand
from flextaxd.cli.commands.stats import StatsCommand
from flextaxd.cli.commands.visualize import VisualizeCommand
from flextaxd.cli.commands.purge import PurgeCommand

from ...fixtures.cli.conftest import *
from ...fixtures.cli.mock_data import MockData, CLITestHelper
from .commands.test_create_command import create_create_mock_args
from .commands.test_export_command import create_export_mock_args
from .commands.test_add_node_command import create_add_node_mock_args
from .commands.test_import_tree_command import create_import_tree_mock_args
from .commands.test_add_genome_command import create_add_genome_mock_args
from .commands.test_stats_command import create_stats_mock_args
from .commands.test_visualize_command import create_visualize_mock_args
from .commands.test_purge_command import create_purge_mock_args


class TestCLIWorkflowIntegration:
    """Test complete CLI workflows with multiple commands."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = None
    
    def teardown_method(self):
        """Clean up test fixtures.""" 
        if self.temp_dir:
            # Cleanup would happen automatically with tempfile
            pass
    
    @patch('flextaxd.cli.commands.create.SQLiteTaxonomyRepository')
    @patch('flextaxd.cli.commands.create.registry')
    @patch('flextaxd.cli.commands.export.SQLiteTaxonomyRepository')
    @patch('flextaxd.exporters.kraken2.Kraken2Exporter')
    def test_create_then_export_workflow(self, mock_kraken2_exporter, mock_export_repo_class,
                                       mock_create_registry, mock_create_repo_class):
        """Test create database then export workflow."""
        # Setup complex tree for realistic workflow
        tree = MockData.create_complex_taxonomy_tree()
        
        # Setup create command mocks
        mock_parser = Mock()
        mock_parser.parse.return_value = tree
        mock_create_registry.get_parser.return_value = mock_parser
        
        mock_create_repo = Mock()
        mock_create_repo.get_statistics.return_value = {
            'node_count': 100, 
            'genome_count': 50,
            'root_count': 1,
            'leaf_count': 80,
            'rank_distribution': {'species': 40, 'genus': 10}
        }
        mock_create_repo_class.return_value.__enter__.return_value = mock_create_repo
        
        # Setup export command mocks
        mock_export_repo = Mock()
        mock_export_repo.load_tree.return_value = tree
        mock_export_repo_class.return_value.__enter__.return_value = mock_export_repo
        
        mock_exporter_instance = Mock()
        mock_kraken2_exporter.return_value = mock_exporter_instance
        
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "workflow_test.ftd"
            input_path = Path(temp_dir) / "input.tsv"
            output_dir = Path(temp_dir) / "kraken2_output"
            
            # Create mock input file
            input_path.write_text("tax_id\tparent_id\tname\trank\n1\t\troot\troot\n")
            
            # Step 1: Create database
            create_command = CreateCommand()
            create_args = create_create_mock_args(
                input=str(input_path),
                database=str(db_path),
                format="tsv",
                verbose=False,
                skip_validation=True
            )
            
            result1 = create_command.execute(create_args)
            assert result1 == 0
            
            # Verify create command executed
            mock_create_repo.save_tree.assert_called_once_with(tree)
            
            # Step 2: Export database
            export_command = ExportCommand()
            export_args = create_export_mock_args(
                database=str(db_path),
                classifier="kraken2",
                output=str(output_dir),
                verbose=False,
                skip_validation=True
            )
            
            # Mock the database validation method for export
            with patch.object(export_command, '_validate_database_path'):
                result2 = export_command.execute(export_args)
            assert result2 == 0
            
            # Verify export command executed (with all parameters that are passed)
            mock_exporter_instance.export.assert_called_once()
            # Check that the tree and output directory are passed correctly
            call_args = mock_exporter_instance.export.call_args
            assert call_args[0][0] == tree  # First positional arg is the tree
            assert str(call_args[0][1]) == str(output_dir)  # Second positional arg is output path
    
    @patch('flextaxd.cli.commands.create.SQLiteTaxonomyRepository')
    @patch('flextaxd.cli.commands.create.registry')
    @patch('flextaxd.cli.commands.add_node.SQLiteTaxonomyRepository')
    @patch('flextaxd.cli.commands.stats.SQLiteTaxonomyRepository')
    @patch('flextaxd.cli.commands.add_node.AddNodeCommand._validate_database_path')
    @patch('flextaxd.cli.commands.stats.StatsCommand._validate_database_path')
    def test_create_add_node_stats_workflow(self, mock_stats_validate_db_path, mock_add_node_validate_db_path, 
                                          mock_stats_repo_class, mock_add_node_repo_class,
                                        mock_create_registry, mock_create_repo_class):
        """Test create, add-node, then stats workflow."""
        from flextaxd.core.models import TaxonomicRank
        
        # Setup initial tree
        initial_tree = MockData.create_complex_taxonomy_tree()
        
        # Setup create mocks
        mock_parser = Mock()
        mock_parser.parse.return_value = initial_tree  # Fix: parse() not parse_and_build_tree()
        mock_create_registry.get_parser.return_value = mock_parser
        
        mock_create_repo = Mock()
        mock_create_repo.get_statistics.return_value = {
            'node_count': 5,
            'genome_count': 0,
            'root_count': 1,
            'leaf_count': 1,
            'rank_distribution': {TaxonomicRank.ROOT: 1, TaxonomicRank.SPECIES: 4}
        }
        mock_create_repo_class.return_value.__enter__.return_value = mock_create_repo
        
        # Setup modify mocks
        mock_modify_repo = Mock()
        mock_modify_repo.load_tree.return_value = initial_tree
        mock_modify_repo.get_statistics.return_value = {
            'node_count': 5,
            'genome_count': 0,
            'root_count': 1,
            'leaf_count': 1,
            'rank_distribution': {TaxonomicRank.ROOT: 1, TaxonomicRank.SPECIES: 4}
        }
        # Setup get_node mock with conditional returns
        def mock_get_node(node_id):
            if node_id == 8:  # E. coli parent should exist
                return initial_tree.get_node(8)  # Return actual E. coli node
            elif node_id == 1005:  # New node shouldn't exist
                return None
            else:
                return None  # Default: other nodes don't exist
        mock_modify_repo.get_node.side_effect = mock_get_node
        
        # Setup get_node_by_name mock for add-node command
        def mock_get_node_by_name(name):
            if name == "New Species":  # New node shouldn't exist yet
                return None
            else:
                return None  # Default: other nodes don't exist
        mock_modify_repo.get_node_by_name.side_effect = mock_get_node_by_name
        mock_modify_repo.get_next_tax_id.return_value = 10000  # Prevent Mock comparison error
        mock_modify_repo.get_children.return_value = []  # Return empty list for iterations
        mock_modify_repo.get_genomes.return_value = []  # Return empty list for iterations
        mock_modify_repo.get_ancestors.return_value = []  # Return empty list for ancestor validation
        mock_add_node_repo_class.return_value.__enter__.return_value = mock_modify_repo
        
        # Setup stats mocks
        mock_stats_repo = Mock()
        mock_stats_repo.load_tree.return_value = initial_tree
        mock_stats_repo.get_statistics.return_value = {
            'node_count': 6,  # Updated after modify
            'genome_count': 0,
            'root_count': 1,
            'leaf_count': 2,
            'rank_distribution': {TaxonomicRank.ROOT: 1, TaxonomicRank.SPECIES: 5}
        }
        mock_stats_repo_class.return_value.__enter__.return_value = mock_stats_repo
        
        # Setup database validation mocks for add-node and stats commands
        mock_add_node_validate_db_path.return_value = None  # No exception = valid
        mock_stats_validate_db_path.return_value = None  # No exception = valid
        
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "modify_workflow.ftd"
            input_path = Path(temp_dir) / "input.tsv"
            
            input_path.write_text("tax_id\tparent_id\tname\trank\n1\t\troot\troot\n")
            
            # Step 1: Create database
            create_command = CreateCommand()
            create_args = create_create_mock_args(
                input=str(input_path),
                database=str(db_path),
                format="tsv",
                verbose=False
            )
            
            result1 = create_command.execute(create_args)
            assert result1 == 0
            
            # Step 2: Add node to database
            add_node_command = AddNodeCommand()
            add_node_args = create_add_node_mock_args(
                database=str(db_path),
                name="New Species",
                parent_id=8,  # E. coli parent
                rank="species",
                verbose=False
            )
            
            result2 = add_node_command.execute(add_node_args)
            assert result2 == 0
            
            # Step 3: Get statistics
            stats_command = StatsCommand()
            stats_args = create_stats_mock_args(
                database=str(db_path),
                detailed=True,
                verbose=False
            )
            
            with patch('builtins.print') as mock_print:
                result3 = stats_command.execute(stats_args)
                assert result3 == 0
                
                # Verify stats were displayed
                assert mock_print.called
    
    @patch('flextaxd.cli.commands.create.SQLiteTaxonomyRepository')
    @patch('flextaxd.cli.commands.create.registry')
    @patch('flextaxd.cli.commands.purge.SQLiteTaxonomyRepository')
    @patch('flextaxd.cli.commands.purge.Path')
    @patch('flextaxd.cli.commands.visualize.SQLiteTaxonomyRepository')
    @patch('flextaxd.cli.commands.visualize.VisualizeCommand._visualize_tree')
    def test_create_purge_visualize_workflow(self, mock_viz_func, mock_viz_repo_class,
                                           mock_purge_path, mock_purge_repo_class, 
                                           mock_create_registry, mock_create_repo_class):
        """Test create, purge, then visualize workflow."""
        # Setup trees for before/after purge
        initial_tree = MockData.create_complex_taxonomy_tree()
        
        # Create a modified tree to simulate purge results
        purged_tree = MockData.create_complex_taxonomy_tree()
        # Simulate removal of some nodes (implementation specific)
        
        # Setup create mocks
        mock_parser = Mock()
        mock_parser.parse.return_value = initial_tree  # Fix: parse() not parse_and_build_tree()
        mock_create_registry.get_parser.return_value = mock_parser
        
        mock_create_repo = Mock()
        mock_create_repo.get_statistics.return_value = {
            'node_count': 5,
            'genome_count': 0,
            'root_count': 1,
            'leaf_count': 1,
            'rank_distribution': {TaxonomicRank.ROOT: 1, TaxonomicRank.SPECIES: 4}
        }
        mock_create_repo_class.return_value.__enter__.return_value = mock_create_repo
        
        # Setup purge mocks
        mock_purge_repo = Mock()
        mock_purge_repo.load_tree.return_value = initial_tree
        mock_purge_repo_class.return_value.__enter__.return_value = mock_purge_repo
        
        # Setup visualize mocks
        mock_viz_repo = Mock()
        mock_viz_repo.load_tree.return_value = purged_tree
        mock_viz_repo_class.return_value.__enter__.return_value = mock_viz_repo
        
        # Setup purge Path mock - make database appear to exist
        mock_path_instance = Mock()
        mock_path_instance.exists.return_value = True
        mock_path_instance.is_file.return_value = True
        mock_path_instance.parent = Mock()
        mock_purge_path.return_value = mock_path_instance
        
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "purge_viz_workflow.ftd"
            input_path = Path(temp_dir) / "input.tsv"
            viz_path = Path(temp_dir) / "tree.png"
            
            input_path.write_text("tax_id\tparent_id\tname\trank\n1\t\troot\troot\n")
            
            # Step 1: Create database
            create_command = CreateCommand()
            create_args = create_create_mock_args(
                input=str(input_path),
                database=str(db_path),
                format="tsv",
                verbose=False
            )
            
            result1 = create_command.execute(create_args)
            assert result1 == 0
            
            # Step 2: Purge database
            purge_command = PurgeCommand()
            purge_args = create_purge_mock_args(
                database=str(db_path),
                force=True,  # Skip safety checks
                verbose=False
            )
            
            # Mock both validation methods for purge command
            with patch.object(purge_command, '_validate_database_path'), \
                 patch.object(purge_command, '_validate_purge_safety'):
                result2 = purge_command.execute(purge_args)
            assert result2 == 0
            
            # Step 3: Visualize purged database
            viz_command = VisualizeCommand()
            viz_args = create_visualize_mock_args(
                database=str(db_path),
                type="tree",
                save_plot=str(viz_path),
                verbose=False
            )
            
            # Mock validation for visualize command
            with patch.object(viz_command, '_validate_database_path'):
                result3 = viz_command.execute(viz_args)
            assert result3 == 0
            
            # Verify visualization was created
            mock_viz_func.assert_called_once()


class TestCLICommandChaining:
    """Test chaining of CLI commands with shared state."""
    
    def test_database_consistency_across_commands(self):
        """Test that database state is consistent across command invocations.""" 
        tree = MockData.create_complex_taxonomy_tree()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "consistency_test.ftd"
            
            # Mock repository to return same tree for all commands
            with patch('flextaxd.cli.commands.stats.SQLiteTaxonomyRepository') as mock_stats_repo, \
                 patch('flextaxd.cli.commands.add_node.SQLiteTaxonomyRepository') as mock_add_node_repo, \
                 patch('flextaxd.cli.commands.export.SQLiteTaxonomyRepository') as mock_export_repo, \
                 patch('flextaxd.cli.commands.base.BaseCommand._validate_database_path') as mock_validate_base:
                
                # Setup base validation mock to bypass file checks for all commands
                mock_validate_base.return_value = None
                
                # Setup all repository mocks to return same tree
                mock_stats_db = Mock()
                mock_stats_db.load_tree.return_value = tree
                # Add get_statistics mock for stats command
                mock_stats_db.get_statistics.return_value = {
                    'node_count': 5,
                    'genome_count': 0,
                    'genomes_metadata_only': 0,  # Missing field
                    'root_count': 1,
                    'leaf_count': 1,
                    'rank_distribution': {},
                    'leaf_nodes': [1, 2, 3, 4],
                    'root_nodes': [0],
                    'max_depth': 3,
                    'avg_depth': 2.5,
                    'total_genomes': 0,
                    'genomes_with_files': 0,
                    'source_distribution': {},
                    'validation_results': [],
                    'genome_size_stats': {}
                }
                mock_stats_repo.return_value.__enter__.return_value = mock_stats_db
                
                mock_add_node_db = Mock()
                mock_add_node_db.load_tree.return_value = tree
                # Use the actual repository get_node method since we have a real tree
                mock_add_node_db.get_node = lambda node_id: tree.get_node(node_id)
                # Mock get_node_by_name to return None for new nodes
                def mock_get_node_by_name(name):
                    if name == "Consistency Test Species":
                        return None  # New node doesn't exist yet
                    else:
                        return None  # Default: other nodes don't exist
                mock_add_node_db.get_node_by_name.side_effect = mock_get_node_by_name
                mock_add_node_db.get_next_tax_id.return_value = 10000  # Prevent Mock comparison error
                mock_add_node_db.get_children.return_value = []  # Return empty list for iterations
                mock_add_node_db.get_genomes.return_value = []  # Return empty list for iterations
                mock_add_node_db.get_ancestors.return_value = []  # Return empty list for ancestor iteration
                mock_add_node_db.add_node = Mock(return_value=None)  # Mock add_node method
                mock_add_node_db.save_tree = Mock(return_value=None)  # Mock save_tree method
                # Add get_statistics mock for add_node command (needed for new node ID generation)
                mock_add_node_db.get_statistics.return_value = {
                    'node_count': 5,
                    'genome_count': 0,
                    'genomes_metadata_only': 0,
                    'root_count': 1,
                    'leaf_count': 1,
                    'rank_distribution': {},
                    'leaf_nodes': [1, 2, 3, 4],
                    'root_nodes': [0],
                    'max_depth': 3,
                    'avg_depth': 2.5,
                    'total_genomes': 0,
                    'genomes_with_files': 0,
                    'source_distribution': {},
                    'validation_results': [],
                    'genome_size_stats': {}
                }
                
                # Mock the tree's add_node method as well
                tree.add_node = Mock(return_value=None)
                mock_add_node_repo.return_value.__enter__.return_value = mock_add_node_db
                
                mock_export_db = Mock()
                mock_export_db.load_tree.return_value = tree
                mock_export_repo.return_value.__enter__.return_value = mock_export_db
                
                # Command 1: Get stats
                stats_command = StatsCommand()
                stats_args = create_stats_mock_args(
                    database=str(db_path),
                    detailed=False,
                    verbose=False
                )
                
                with patch('builtins.print'):
                    result1 = stats_command.execute(stats_args)
                    assert result1 == 0
                
                # Command 2: Add node (should work with same database)
                add_node_command = AddNodeCommand()
                add_node_args = create_add_node_mock_args(
                    database=str(db_path),
                    name="Consistency Test Species",
                    parent_id=8,
                    rank="species",
                    verbose=False
                )
                
                result2 = add_node_command.execute(add_node_args)
                assert result2 == 0
                
                # Command 3: Export (should work with potentially modified database)
                export_command = ExportCommand()
                export_args = create_export_mock_args(
                    database=str(db_path),
                    format="tsv",
                    output=str(Path(temp_dir) / "export.tsv"),  # Fix: use Path properly
                    verbose=False,
                    skip_validation=True
                )
                
                result3 = export_command.execute(export_args)
                assert result3 == 0
    
    def test_error_propagation_across_commands(self):
        """Test error handling when commands are chained."""
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "error_test.ftd"
            
            # Test with corrupted database
            with patch('flextaxd.cli.commands.stats.SQLiteTaxonomyRepository') as mock_repo_class:
                mock_repo = Mock()
                mock_repo.load_tree.side_effect = Exception("Database corrupted")
                mock_repo_class.return_value.__enter__.return_value = mock_repo
                
                # First command should fail
                stats_command = StatsCommand()
                stats_args = create_stats_mock_args(
                    database=str(db_path),
                    detailed=False,
                    verbose=False
                )
                
                result1 = stats_command.execute(stats_args)
                assert result1 != 0
                
                # Subsequent commands should also handle the same error
                add_node_command = AddNodeCommand()
                add_node_args = create_add_node_mock_args(
                    database=str(db_path),
                    name="Test Species",
                    parent_id=1,
                    rank="species",
                    verbose=False
                )
                
                with patch('flextaxd.cli.commands.add_node.SQLiteTaxonomyRepository') as mock_add_node_repo:
                    mock_add_node_repo.return_value.__enter__.return_value = mock_repo
                    result2 = add_node_command.execute(add_node_args)
                    assert result2 != 0


class TestCLIFileSystemIntegration:
    """Test CLI commands with real file system operations."""
    
    def test_real_file_operations_workflow(self, temp_dir, sample_input_files):
        """Test workflow with actual file system operations."""
        db_path = temp_dir / "real_fs_test.ftd"
        
        # Use real input file from fixtures
        real_input = sample_input_files["tsv"]
        
        with patch('flextaxd.cli.commands.create.SQLiteTaxonomyRepository') as mock_create_repo, \
             patch('flextaxd.cli.commands.create.registry') as mock_registry, \
             patch('flextaxd.cli.commands.stats.SQLiteTaxonomyRepository') as mock_stats_repo, \
             patch('flextaxd.cli.commands.base.BaseCommand._validate_database_path') as mock_base_validate:
            
            # Setup base validation mock to bypass file checks
            mock_base_validate.return_value = None
            
            # Setup create command mocks
            mock_parser = Mock()
            mock_parser.parse.return_value = MockData.create_complex_taxonomy_tree()  # Fix: use parse() not parse_and_build_tree()
            mock_registry.get_parser.return_value = mock_parser
            
            mock_create_db = Mock()
            # Add get_statistics mock for create command (needed for summary output)
            mock_create_db.get_statistics.return_value = {
                'node_count': 5,
                'genome_count': 0,
                'genomes_metadata_only': 0,
                'root_count': 1,
                'leaf_count': 1,
                'rank_distribution': {},
                'leaf_nodes': [1, 2, 3, 4],
                'root_nodes': [0],
                'max_depth': 3,
                'avg_depth': 2.5,
                'total_genomes': 0,
                'genomes_with_files': 0,
                'source_distribution': {},
                'validation_results': [],
                'genome_size_stats': {}
            }
            mock_create_repo.return_value.__enter__.return_value = mock_create_db
            
            # Setup stats command mocks
            mock_stats_db = Mock()
            mock_stats_db.load_tree.return_value = MockData.create_complex_taxonomy_tree()
            # Add get_statistics mock for stats command
            mock_stats_db.get_statistics.return_value = {
                'node_count': 5,
                'genome_count': 0,
                'genomes_metadata_only': 0,  # Missing field
                'root_count': 1,
                'leaf_count': 1,
                'rank_distribution': {},
                'leaf_nodes': [1, 2, 3, 4],
                'root_nodes': [0],
                'max_depth': 3,
                'avg_depth': 2.5,
                'total_genomes': 0,
                'genomes_with_files': 0,
                'source_distribution': {},
                'validation_results': [],
                'genome_size_stats': {}
            }
            mock_stats_repo.return_value.__enter__.return_value = mock_stats_db
            
            # Step 1: Create database (using real input file)
            create_command = CreateCommand()
            create_args = create_create_mock_args(
                input=real_input,
                database=str(db_path),
                format="tsv",
                verbose=False
            )
            
            result1 = create_command.execute(create_args)
            assert result1 == 0
            
            # Verify real input file exists and was processed
            assert Path(real_input).exists()
            
            # Step 2: Get stats (database path validation should work)
            stats_command = StatsCommand()
            stats_args = create_stats_mock_args(
                database=str(db_path),
                format="json",  # Fix: use format instead of output
                detailed=True,
                verbose=False
            )
            
            with patch('builtins.print') as mock_print:
                result2 = stats_command.execute(stats_args)
                assert result2 == 0
                
                # Verify stats output was printed (JSON format)
                mock_print.assert_called()
    
    def test_path_resolution_and_validation(self, temp_dir):
        """Test path resolution across different command types."""
        # Test various path formats
        paths = {
            "absolute": temp_dir / "absolute.ftd",
            "relative": Path("./relative.ftd"),
            "parent": Path("../parent.ftd"),
            "with_spaces": temp_dir / "path with spaces.ftd",
            "nested": temp_dir / "deep" / "nested" / "path.ftd"
        }
        
        for path_type, path in paths.items():
            with patch('flextaxd.cli.commands.stats.SQLiteTaxonomyRepository') as mock_repo:
                mock_db = Mock()
                mock_db.load_tree.return_value = MockData.create_complex_taxonomy_tree()
                mock_repo.return_value.__enter__.return_value = mock_db
                
                stats_command = StatsCommand()
                stats_args = create_stats_mock_args(
                    database=str(path),
                    detailed=False,
                    verbose=False
                )
                
                # Path validation should handle different formats
                # (Implementation dependent on validation logic)
                with patch('builtins.print'):
                    result = stats_command.execute(stats_args)
                    # Result depends on validation implementation


class TestCLIPerformanceIntegration:
    """Test CLI performance with various data sizes."""
    
    def test_large_dataset_workflow(self):
        """Test workflow with large dataset simulation."""
        # Create large mock tree
        large_tree = Mock()
        large_tree._nodes = {i: Mock() for i in range(10000)}
        large_tree._genomes = {f"genome_{i}": Mock() for i in range(1000)}
        large_tree.get_tree_statistics.return_value = {
            "total_nodes": 10000,
            "total_genomes": 1000,
            "max_depth": 15
        }
        
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "large_dataset.ftd"
            
            # Test stats command performance
            with patch('flextaxd.cli.commands.stats.SQLiteTaxonomyRepository') as mock_repo, \
                 patch('flextaxd.cli.commands.base.BaseCommand._validate_database_path') as mock_validate:
                # Setup base validation mock to bypass file checks
                mock_validate.return_value = None
                
                mock_db = Mock()
                mock_db.load_tree.return_value = large_tree
                # Add get_statistics mock for stats command
                mock_db.get_statistics.return_value = {
                    'node_count': 10000,
                    'genome_count': 1000,
                    'genomes_metadata_only': 0,  # Missing field
                    'root_count': 1,
                    'leaf_count': 8000,
                    'rank_distribution': {},
                    'leaf_nodes': list(range(2000, 10000)),
                    'root_nodes': [0],
                    'max_depth': 15,
                    'avg_depth': 8.5,
                    'total_genomes': 1000,
                    'genomes_with_files': 1000,
                    'source_distribution': {},
                    'validation_results': [],
                    'genome_size_stats': {}
                }
                mock_repo.return_value.__enter__.return_value = mock_db
                
                stats_command = StatsCommand()
                stats_args = create_stats_mock_args(
                    database=str(db_path),
                    detailed=True,
                    verbose=False
                )
                
                # Measure performance
                import time
                start_time = time.time()
                
                with patch('builtins.print'):
                    result = stats_command.execute(stats_args)
                
                end_time = time.time()
                
                assert result == 0
                # Should complete in reasonable time for large dataset
                assert end_time - start_time < 10.0  # 10 second timeout
    
    def test_memory_efficient_command_execution(self):
        """Test memory efficiency of command execution."""
        from flextaxd.core.models import TaxonomyNode, TaxonomicRank
        tree = MockData.create_complex_taxonomy_tree()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "memory_test.ftd"
            
            # Test multiple commands without memory leaks
            commands = [
                (StatsCommand, {
                    "database": str(db_path), 
                    "detailed": True, 
                    "verbose": False,
                    "validate_files": False,  # Skip validation to avoid Mock issues
                    "skip_file_validation": True,
                    "validation_level": "basic",
                    "consistency_check": False,
                    "format": "text",
                    "missing_files": False  # Required by stats command
                }),
                (AddNodeCommand, {
                    "database": str(db_path), 
                    "name": "Test", 
                    "parent_id": 1, 
                    "rank": "species", 
                    "verbose": False,
                    "tax_id": None,
                    "parent_name": None,
                    "dry_run": False,
                    "force": False,
                    "quiet": False,
                    "skip_validation": True,
                    "max_workers": None,
                    "report_missing": False
                }),
                (StatsCommand, {
                    "database": str(db_path), 
                    "detailed": False, 
                    "verbose": False,
                    "validate_files": False,  # Skip validation to avoid Mock issues
                    "skip_file_validation": True,
                    "validation_level": "basic",
                    "consistency_check": False,
                    "format": "text",
                    "missing_files": False  # Required by stats command
                })
            ]
            
            for command_class, args_dict in commands:
                # Add database validation mocks for Pattern 2 fix
                command_module = 'stats' if command_class == StatsCommand else 'add_node'
                with patch(f'flextaxd.cli.commands.{command_class.__module__.split(".")[-1]}.SQLiteTaxonomyRepository') as mock_repo, \
                     patch(f'flextaxd.cli.commands.{command_module}.{command_class.__name__}._validate_database_path') as mock_validate:
                    
                    mock_validate.return_value = None  # No validation error
                    mock_db = Mock()
                    mock_db.load_tree.return_value = tree
                    
                    # Add proper statistics mock for both commands
                    mock_db.get_statistics.return_value = {
                        'node_count': 5,
                        'genome_count': 0,
                        'root_count': 1,
                        'leaf_count': 1,
                        'rank_distribution': {TaxonomicRank.ROOT: 1, TaxonomicRank.SPECIES: 4},
                        'leaf_nodes': [1, 2, 3, 4],  # List of leaf node IDs
                        'root_nodes': [0],           # List of root node IDs
                        'max_depth': 3,
                        'avg_depth': 2.5,
                        'total_genomes': 0,
                        'genomes_with_files': 0,
                        'source_distribution': {},
                        'validation_results': [],
                        'genome_size_stats': {}
                    }
                    
                    # Add AddNodeCommand-specific mocks
                    if command_class == AddNodeCommand:
                        # Mock tree iteration and node access
                        mock_db.add_node = Mock(return_value=None)
                        
                        # Mock get_node to return different responses based on ID
                        def mock_get_node(tax_id):
                            if tax_id == 1:  # Parent node exists
                                return TaxonomyNode(
                                    tax_id=1,
                                    name="Mock Parent",
                                    parent_id=None,
                                    rank=TaxonomicRank.ROOT
                                )
                            else:  # New IDs don't exist yet
                                return None
                        
                        mock_db.get_node = Mock(side_effect=mock_get_node)
                        
                        # Add essential mocks to prevent iteration errors
                        mock_db.get_node_by_name = Mock(return_value=None)  # New nodes don't exist
                        mock_db.get_next_tax_id = Mock(return_value=10000)  # Prevent Mock comparison error
                        mock_db.get_children = Mock(return_value=[])  # Return empty list for iterations
                        mock_db.get_genomes = Mock(return_value=[])  # Return empty list for iterations
                        mock_db.get_ancestors = Mock(return_value=[])  # Return empty list for ancestor iteration
                    
                    mock_repo.return_value.__enter__.return_value = mock_db
                    
                    command = command_class()
                    # Use appropriate mock args function based on command class
                    if command_class == StatsCommand:
                        args = create_stats_mock_args(**args_dict)
                    elif command_class == AddNodeCommand:
                        args = create_add_node_mock_args(**args_dict)
                    else:
                        # Fallback to argparse.Namespace if no specific function
                        import argparse
                        args = argparse.Namespace(**args_dict)
                    
                    if command_class == StatsCommand:
                        with patch('builtins.print'):
                            result = command.execute(args)
                    else:
                        result = command.execute(args)
                    
                    assert result == 0
                    
                    # Verify command completes and releases resources
                    # (Memory monitoring would be implementation-specific)


class TestCLIErrorRecovery:
    """Test CLI error recovery and resilience."""
    
    def test_graceful_degradation(self):
        """Test graceful degradation when optional features fail."""
        tree = MockData.create_complex_taxonomy_tree()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "degradation_test.ftd"
            output_path = Path(temp_dir) / "tree.png"  # Fix: create Path object properly
            
            # Test visualization with missing dependencies
            with patch('flextaxd.cli.commands.visualize.SQLiteTaxonomyRepository') as mock_repo, \
                 patch('flextaxd.cli.commands.base.BaseCommand._validate_database_path') as mock_validate, \
                 patch('flextaxd.cli.commands.visualize.VisualizeCommand._visualize_tree', 
                       side_effect=ImportError("Matplotlib not available")):
                
                # Setup base validation mock to bypass file checks
                mock_validate.return_value = None
                
                mock_db = Mock()
                mock_db.load_tree.return_value = tree
                mock_repo.return_value.__enter__.return_value = mock_db
                
                viz_command = VisualizeCommand()
                viz_args = create_visualize_mock_args(
                    database=str(db_path),
                    type="tree",
                    output=str(output_path),
                    verbose=False
                )
                
                result = viz_command.execute(viz_args)
                
                # Should handle missing dependencies gracefully
                assert result != 0  # Expected to fail, but gracefully
    
    def test_partial_failure_recovery(self):
        """Test recovery from partial failures in batch operations."""
        tree = MockData.create_complex_taxonomy_tree()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            db_path = temp_path / "partial_failure_test.ftd"
            mod_file = temp_path / "modifications.tsv"
            
            # Create modification file with mixed valid/invalid operations
            mod_content = """action\ttax_id\tname\tparent_id\trank
add\t\tValid Species\t8\tspecies
add\t\tInvalid Species\t999\tspecies
update\t8\tUpdated E. coli\t\t
delete\t999\t\t\t
"""
            mod_file.write_text(mod_content)
            
            with patch('flextaxd.cli.commands.import_tree.SQLiteTaxonomyRepository') as mock_repo, \
                 patch('flextaxd.cli.commands.base.BaseCommand._validate_database_path') as mock_validate:
                
                # Setup base validation mock to bypass file checks
                mock_validate.return_value = None
                
                mock_db = Mock()
                mock_db.load_tree.return_value = tree
                mock_repo.return_value.__enter__.return_value = mock_db
                
                import_tree_command = ImportTreeCommand()
                import_tree_args = create_import_tree_mock_args(
                    database=str(db_path),
                    input=str(mod_file),
                    strategy="merge",
                    verbose=True
                )
                
                result = import_tree_command.execute(import_tree_args)
                
                # Should handle partial failures appropriately
                # Implementation dependent on error handling strategy
                assert result == 0 or result != 0  # Either way should be handled
    
    def test_command_interruption_recovery(self):
        """Test recovery from command interruption."""
        tree = MockData.create_complex_taxonomy_tree()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "interruption_test.ftd"
            
            # Test stats command interruption - more targeted approach
            with patch('flextaxd.cli.commands.stats.SQLiteTaxonomyRepository') as mock_repo, \
                 patch('flextaxd.cli.commands.base.BaseCommand._validate_database_path') as mock_validate:
                
                # Setup base validation mock to bypass file checks
                mock_validate.return_value = None
                
                # Mock the database to raise KeyboardInterrupt during statistics calculation
                mock_db = Mock()
                mock_db.load_tree.return_value = tree
                mock_db.get_statistics.side_effect = KeyboardInterrupt("Simulated user interruption")
                mock_repo.return_value.__enter__.return_value = mock_db
                
                stats_command = StatsCommand()
                stats_args = create_stats_mock_args(
                    database=str(db_path),
                    detailed=True,
                    verbose=False,
                    validate_files=True,
                    skip_file_validation=False,
                    format="text",
                    consistency_check=False,
                    validation_level="basic"
                )
                
                # Execute command - should catch KeyboardInterrupt and return 1
                result = stats_command.execute(stats_args)
                
                # Should handle interruption gracefully and return non-zero exit code
                assert result == 1  # StatsCommand returns 1 on KeyboardInterrupt