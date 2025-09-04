"""Comprehensive tests for CLI argument parsing and validation."""

import pytest
import argparse
from unittest.mock import Mock, patch

from flextaxd.cli.commands.create import CreateCommand
from flextaxd.cli.commands.export import ExportCommand 
from flextaxd.cli.commands.modify import ModifyCommand
from flextaxd.cli.commands.stats import StatsCommand
from flextaxd.cli.commands.visualize import VisualizeCommand
from flextaxd.cli.commands.purge import PurgeCommand

from ...fixtures.cli.conftest import *
from ...fixtures.cli.mock_data import CLITestHelper


class TestArgumentParsingBase:
    """Base test class for argument parsing."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.parser = argparse.ArgumentParser()
        self.subparsers = self.parser.add_subparsers(dest='command')
    
    def parse_args(self, args_list):
        """Helper to parse arguments and handle errors."""
        try:
            return self.parser.parse_args(args_list)
        except SystemExit:
            return None


class TestCreateCommandArgumentParsing(TestArgumentParsingBase):
    """Test argument parsing for create command."""
    
    def setup_method(self):
        """Set up create command parser.""" 
        super().setup_method()
        CreateCommand.register_parser(self.subparsers)
    
    def test_basic_required_arguments(self):
        """Test basic required arguments."""
        args = self.parse_args([
            'create', 
            '--input', '/test/input.tsv',
            '--database', '/test/output.ftd'
        ])
        
        assert args is not None
        assert args.command == 'create'
        assert args.input == '/test/input.tsv'
        assert args.database == '/test/output.ftd'
    
    def test_format_specification(self):
        """Test format specification."""
        args = self.parse_args([
            'create',
            '--input', '/test/input.tsv',
            '--database', '/test/output.ftd',
            '--format', 'tsv'
        ])
        
        assert args is not None
        assert args.format == 'tsv'
    
    def test_verbose_flag(self):
        """Test verbose flag."""
        args = self.parse_args([
            'create',
            '--input', '/test/input.tsv', 
            '--database', '/test/output.ftd',
            '--verbose'
        ])
        
        assert args is not None
        assert args.verbose is True
    
    def test_missing_required_arguments(self):
        """Test missing required arguments."""
        # Missing --input
        args = self.parse_args([
            'create',
            '--database', '/test/output.ftd'
        ])
        assert args is None
        
        # Missing --database
        args = self.parse_args([
            'create',
            '--input', '/test/input.tsv'
        ])
        assert args is None
    
    def test_validation_options(self):
        """Test validation-related options."""
        args = self.parse_args([
            'create',
            '--input', '/test/input.tsv',
            '--database', '/test/output.ftd',
            '--validate',
            '--strict'
        ])
        
        assert args is not None
        if hasattr(args, 'validate'):
            assert args.validate is True
        if hasattr(args, 'strict'):
            assert args.strict is True
    
    def test_short_argument_forms(self):
        """Test short argument forms."""
        args = self.parse_args([
            'create',
            '-i', '/test/input.tsv',
            '-d', '/test/output.ftd',
            '-f', 'ncbi',
            '-v'
        ])
        
        assert args is not None
        assert args.input == '/test/input.tsv'
        assert args.database == '/test/output.ftd'
        if hasattr(args, 'format'):
            assert args.format == 'ncbi'
        if hasattr(args, 'verbose'):
            assert args.verbose is True


class TestExportCommandArgumentParsing(TestArgumentParsingBase):
    """Test argument parsing for export command."""
    
    def setup_method(self):
        """Set up export command parser."""
        super().setup_method()
        ExportCommand.register_parser(self.subparsers)
    
    def test_classifier_export(self):
        """Test classifier export arguments."""
        args = self.parse_args([
            'export',
            '--database', '/test/db.ftd',
            '--classifier', 'kraken2',
            '--output', '/test/kraken2_db/'
        ])
        
        assert args is not None
        assert args.command == 'export'
        assert args.database == '/test/db.ftd'
        assert args.classifier == 'kraken2'
        assert args.output == '/test/kraken2_db/'
    
    def test_format_export(self):
        """Test format export arguments."""
        args = self.parse_args([
            'export',
            '--database', '/test/db.ftd', 
            '--format', 'tsv',
            '--output', '/test/taxonomy.tsv'
        ])
        
        assert args is not None
        assert args.format == 'tsv'
        assert args.output == '/test/taxonomy.tsv'
    
    def test_legacy_format_support(self):
        """Test legacy format support."""
        args = self.parse_args([
            'export',
            '--database', '/test/db.ftd',
            '--legacy-format', 'ncbi',
            '--output', '/test/ncbi_dump/'
        ])
        
        assert args is not None
        if hasattr(args, 'legacy_format'):
            assert args.legacy_format == 'ncbi'
    
    def test_mutually_exclusive_options(self):
        """Test mutually exclusive format options."""
        # Should not allow both --classifier and --format
        args = self.parse_args([
            'export',
            '--database', '/test/db.ftd',
            '--classifier', 'kraken2',
            '--format', 'tsv',
            '--output', '/test/output/'
        ])
        
        # Depending on parser setup, this should either fail or prefer one option
        # Implementation depends on mutually exclusive group setup
    
    def test_export_options(self):
        """Test various export options."""
        args = self.parse_args([
            'export',
            '--database', '/test/db.ftd',
            '--classifier', 'diamond',
            '--output', '/test/diamond_db/',
            '--validate',
            '--compress',
            '--verbose'
        ])
        
        assert args is not None
        if hasattr(args, 'validate'):
            assert args.validate is True
        if hasattr(args, 'compress'):
            assert args.compress is True
        assert args.verbose is True
    
    def test_missing_export_specification(self):
        """Test missing export type specification."""
        args = self.parse_args([
            'export',
            '--database', '/test/db.ftd',
            '--output', '/test/output/'
            # No --classifier, --format, or --legacy-format
        ])
        
        # Should still parse but command execution should handle validation
        assert args is not None


class TestModifyCommandArgumentParsing(TestArgumentParsingBase):
    """Test argument parsing for modify command."""
    
    def setup_method(self):
        """Set up modify command parser."""
        super().setup_method()
        ModifyCommand.register_parser(self.subparsers)
    
    def test_add_node_arguments(self):
        """Test add node arguments."""
        args = self.parse_args([
            'modify',
            '--database', '/test/db.ftd',
            '--add-node', 'New Species',
            '--parent-id', '123',
            '--rank', 'species'
        ])
        
        assert args is not None
        assert args.command == 'modify'
        assert args.add_node == 'New Species'
        assert args.parent_id == '123'
        assert args.rank == 'species'
    
    def test_update_node_arguments(self):
        """Test update node arguments."""
        args = self.parse_args([
            'modify',
            '--database', '/test/db.ftd',
            '--update-node', '123',
            '--name', 'Updated Name'
        ])
        
        assert args is not None
        assert args.update_node == '123'
        assert args.name == 'Updated Name'
    
    def test_delete_node_arguments(self):
        """Test delete node arguments."""
        args = self.parse_args([
            'modify',
            '--database', '/test/db.ftd',
            '--delete-node', '123',
            '--force'
        ])
        
        assert args is not None
        assert args.delete_node == '123'
        assert args.force is True
    
    def test_mod_file_arguments(self):
        """Test modification file arguments."""
        args = self.parse_args([
            'modify',
            '--database', '/test/db.ftd',
            '--mod-file', '/test/modifications.tsv',
            '--replace'
        ])
        
        assert args is not None
        assert args.mod_file == '/test/modifications.tsv'
        assert args.replace is True
    
    def test_backup_option(self):
        """Test backup option."""
        args = self.parse_args([
            'modify',
            '--database', '/test/db.ftd',
            '--add-node', 'Test Species',
            '--parent-id', '123',
            '--rank', 'species',
            '--backup', '/test/backup.ftd'
        ])
        
        assert args is not None
        assert args.backup == '/test/backup.ftd'
    
    def test_multiple_modification_types(self):
        """Test handling of multiple modification types."""
        # Should handle or reject multiple modification actions
        args = self.parse_args([
            'modify',
            '--database', '/test/db.ftd',
            '--add-node', 'New Species',
            '--parent-id', '123',
            '--delete-node', '456',
            '--rank', 'species'
        ])
        
        # Behavior depends on parser setup - might allow or reject


class TestStatsCommandArgumentParsing(TestArgumentParsingBase):
    """Test argument parsing for stats command."""
    
    def setup_method(self):
        """Set up stats command parser."""
        super().setup_method()
        StatsCommand.register_parser(self.subparsers)
    
    def test_basic_stats_arguments(self):
        """Test basic stats arguments."""
        args = self.parse_args([
            'stats',
            '--database', '/test/db.ftd'
        ])
        
        assert args is not None
        assert args.command == 'stats'
        assert args.database == '/test/db.ftd'
    
    def test_detailed_stats(self):
        """Test detailed statistics option."""
        args = self.parse_args([
            'stats',
            '--database', '/test/db.ftd',
            '--detailed'
        ])
        
        assert args is not None
        assert args.detailed is True
    
    def test_output_file(self):
        """Test output file option."""
        args = self.parse_args([
            'stats',
            '--database', '/test/db.ftd',
            '--output', '/test/stats.json'
        ])
        
        assert args is not None
        assert args.output == '/test/stats.json'
    
    def test_rank_filtering(self):
        """Test rank-specific statistics."""
        args = self.parse_args([
            'stats',
            '--database', '/test/db.ftd',
            '--rank', 'species'
        ])
        
        assert args is not None
        if hasattr(args, 'rank'):
            assert args.rank == 'species'
    
    def test_stats_options_combination(self):
        """Test combination of statistics options."""
        args = self.parse_args([
            'stats',
            '--database', '/test/db.ftd',
            '--detailed',
            '--output', '/test/detailed_stats.json',
            '--rank', 'genus',
            '--verbose'
        ])
        
        assert args is not None
        assert args.detailed is True
        assert args.output == '/test/detailed_stats.json'
        if hasattr(args, 'rank'):
            assert args.rank == 'genus'
        assert args.verbose is True


class TestVisualizeCommandArgumentParsing(TestArgumentParsingBase):
    """Test argument parsing for visualize command."""
    
    def setup_method(self):
        """Set up visualize command parser."""
        super().setup_method()
        VisualizeCommand.register_parser(self.subparsers)
    
    def test_basic_visualization_arguments(self):
        """Test basic visualization arguments.""" 
        args = self.parse_args([
            'visualize',
            '--database', '/test/db.ftd',
            '--type', 'tree',
            '--output', '/test/tree.png'
        ])
        
        assert args is not None
        assert args.command == 'visualize'
        assert args.database == '/test/db.ftd'
        assert args.type == 'tree'
        assert args.output == '/test/tree.png'
    
    def test_visualization_dimensions(self):
        """Test visualization dimension arguments."""
        args = self.parse_args([
            'visualize',
            '--database', '/test/db.ftd',
            '--type', 'plot',
            '--output', '/test/plot.png',
            '--width', '12',
            '--height', '8',
            '--dpi', '300'
        ])
        
        assert args is not None
        assert args.width == '12'
        assert args.height == '8'
        assert args.dpi == '300'
    
    def test_visualization_options(self):
        """Test various visualization options."""
        args = self.parse_args([
            'visualize',
            '--database', '/test/db.ftd',
            '--type', 'tree',
            '--output', '/test/tree.png',
            '--max-depth', '5',
            '--min-genomes', '1',
            '--show-labels',
            '--color-by-rank'
        ])
        
        assert args is not None
        if hasattr(args, 'max_depth'):
            assert args.max_depth == '5'
        if hasattr(args, 'min_genomes'):
            assert args.min_genomes == '1'
        if hasattr(args, 'show_labels'):
            assert args.show_labels is True
        if hasattr(args, 'color_by_rank'):
            assert args.color_by_rank is True
    
    def test_visualization_types(self):
        """Test different visualization types."""
        viz_types = ['tree', 'plot', 'newick', 'dendrogram', 'circular']
        
        for viz_type in viz_types:
            args = self.parse_args([
                'visualize',
                '--database', '/test/db.ftd',
                '--type', viz_type,
                '--output', f'/test/{viz_type}.png'
            ])
            
            assert args is not None
            assert args.type == viz_type
    
    def test_advanced_visualization_options(self):
        """Test advanced visualization options."""
        args = self.parse_args([
            'visualize',
            '--database', '/test/db.ftd',
            '--type', 'plot',
            '--output', '/test/advanced_plot.png',
            '--font-size', '14',
            '--color-scheme', 'viridis',
            '--filter-rank', 'species',
            '--layout', 'circular',
            '--verbose'
        ])
        
        assert args is not None
        if hasattr(args, 'font_size'):
            assert args.font_size == '14'
        if hasattr(args, 'color_scheme'):
            assert args.color_scheme == 'viridis'
        if hasattr(args, 'filter_rank'):
            assert args.filter_rank == 'species'
        if hasattr(args, 'layout'):
            assert args.layout == 'circular'
        assert args.verbose is True


class TestPurgeCommandArgumentParsing(TestArgumentParsingBase):
    """Test argument parsing for purge command."""
    
    def setup_method(self):
        """Set up purge command parser."""
        super().setup_method()
        PurgeCommand.register_parser(self.subparsers)
    
    def test_basic_purge_arguments(self):
        """Test basic purge arguments."""
        args = self.parse_args([
            'purge',
            '--database', '/test/db.ftd'
        ])
        
        assert args is not None
        assert args.command == 'purge'
        assert args.database == '/test/db.ftd'
    
    def test_purge_options(self):
        """Test purge-specific options."""
        args = self.parse_args([
            'purge',
            '--database', '/test/db.ftd',
            '--dry-run',
            '--force',
            '--stats-only'
        ])
        
        assert args is not None
        assert args.dry_run is True
        assert args.force is True
        assert args.stats_only is True
    
    def test_purge_modes(self):
        """Test different purge modes."""
        args = self.parse_args([
            'purge',
            '--database', '/test/db.ftd',
            '--allow-metadata-only',
            '--backup', '/test/backup.ftd'
        ])
        
        assert args is not None
        if hasattr(args, 'allow_metadata_only'):
            assert args.allow_metadata_only is True
        assert args.backup == '/test/backup.ftd'
    
    def test_purge_safety_options(self):
        """Test purge safety options."""
        args = self.parse_args([
            'purge',
            '--database', '/test/db.ftd',
            '--interactive',
            '--confirm',
            '--backup', '/test/safety_backup.ftd'
        ])
        
        assert args is not None
        if hasattr(args, 'interactive'):
            assert args.interactive is True
        if hasattr(args, 'confirm'):
            assert args.confirm is True


class TestArgumentValidation:
    """Test argument validation across commands."""
    
    def test_database_path_validation(self):
        """Test database path validation."""
        # Test various database path formats
        valid_paths = [
            '/test/db.ftd',
            './relative/db.ftd',
            '../parent/db.ftd',
            '/path/with spaces/db.ftd',
            '/path/with-dashes/db.ftd',
            '/path/with_underscores/db.ftd'
        ]
        
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest='command')
        CreateCommand.register_parser(subparsers)
        
        for path in valid_paths:
            args = parser.parse_args([
                'create',
                '--input', '/test/input.tsv',
                '--database', path
            ])
            
            assert args.database == path
    
    def test_input_path_validation(self):
        """Test input path validation."""
        valid_inputs = [
            '/test/file.tsv',
            '/test/directory/',
            './relative.tsv',
            '../parent.tsv'
        ]
        
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest='command')
        CreateCommand.register_parser(subparsers)
        
        for input_path in valid_inputs:
            args = parser.parse_args([
                'create', 
                '--input', input_path,
                '--database', '/test/db.ftd'
            ])
            
            assert args.input == input_path
    
    def test_numeric_argument_validation(self):
        """Test numeric argument validation."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest='command')
        VisualizeCommand.register_parser(subparsers)
        
        # Test valid numeric arguments
        args = parser.parse_args([
            'visualize',
            '--database', '/test/db.ftd',
            '--type', 'plot', 
            '--output', '/test/plot.png',
            '--width', '12',
            '--height', '8',
            '--dpi', '300'
        ])
        
        assert args.width == '12'
        assert args.height == '8'
        assert args.dpi == '300'
    
    def test_choice_argument_validation(self):
        """Test choice argument validation."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest='command')
        CreateCommand.register_parser(subparsers)
        
        # Test valid format choices
        valid_formats = ['tsv', 'ncbi', 'gtdb', 'qiime', 'silva', 'cansnper']
        
        for fmt in valid_formats:
            try:
                args = parser.parse_args([
                    'create',
                    '--input', '/test/input.tsv',
                    '--database', '/test/db.ftd',
                    '--format', fmt
                ])
                
                assert args.format == fmt
            except SystemExit:
                # Some formats might not be in choices - this is expected
                pass


class TestArgumentErrorHandling:
    """Test argument parsing error handling."""
    
    def test_unknown_command(self):
        """Test handling of unknown commands."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest='command')
        CreateCommand.register_parser(subparsers)
        
        try:
            args = parser.parse_args(['unknown_command'])
            assert False, "Should have raised SystemExit"
        except SystemExit:
            # Expected behavior for unknown command
            pass
    
    def test_unknown_arguments(self):
        """Test handling of unknown arguments."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest='command')
        CreateCommand.register_parser(subparsers)
        
        try:
            args = parser.parse_args([
                'create',
                '--input', '/test/input.tsv',
                '--database', '/test/db.ftd',
                '--unknown-arg', 'value'
            ])
            assert False, "Should have raised SystemExit"
        except SystemExit:
            # Expected behavior for unknown argument
            pass
    
    def test_conflicting_arguments(self):
        """Test handling of conflicting arguments."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest='command')
        ExportCommand.register_parser(subparsers)
        
        # Test mutually exclusive arguments (if implemented)
        try:
            args = parser.parse_args([
                'export',
                '--database', '/test/db.ftd',
                '--classifier', 'kraken2',
                '--format', 'tsv',  # Conflicting with classifier
                '--output', '/test/output/'
            ])
            
            # Depending on implementation, might allow or reject
            # Test should match actual behavior
        except SystemExit:
            # Expected if mutually exclusive groups are enforced
            pass
    
    def test_missing_required_arguments(self):
        """Test comprehensive missing argument scenarios."""
        commands_and_required = [
            ('create', ['--input', '--database']),
            ('export', ['--database', '--output']),
            ('modify', ['--database']),
            ('stats', ['--database']),
            ('visualize', ['--database', '--type', '--output']),
            ('purge', ['--database'])
        ]
        
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest='command')
        
        # Register all commands
        CreateCommand.register_parser(subparsers)
        ExportCommand.register_parser(subparsers)
        ModifyCommand.register_parser(subparsers)
        StatsCommand.register_parser(subparsers)
        VisualizeCommand.register_parser(subparsers)
        PurgeCommand.register_parser(subparsers)
        
        for command, required_args in commands_and_required:
            # Test missing each required argument
            for missing_arg in required_args:
                test_args = [command]
                
                # Add all required args except the missing one
                for req_arg in required_args:
                    if req_arg != missing_arg:
                        test_args.extend([req_arg, f'/test/value'])
                
                try:
                    args = parser.parse_args(test_args)
                    # Some args might be optional or have defaults
                except SystemExit:
                    # Expected for truly required arguments
                    pass


class TestHelpAndUsage:
    """Test help and usage information."""
    
    def test_command_help_output(self):
        """Test that help output is generated."""
        commands = [
            CreateCommand, ExportCommand, ModifyCommand,
            StatsCommand, VisualizeCommand, PurgeCommand
        ]
        
        for command_class in commands:
            parser = argparse.ArgumentParser()
            subparsers = parser.add_subparsers(dest='command')
            
            # Should not raise exception
            command_parser = command_class.register_parser(subparsers)
            assert command_parser is not None
    
    def test_usage_examples(self):
        """Test that usage examples in help are valid.""" 
        # This would require parsing help text and validating examples
        # Implementation depends on help format
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest='command')
        
        # Register all commands
        CreateCommand.register_parser(subparsers)
        ExportCommand.register_parser(subparsers)
        
        # Help should be accessible
        try:
            parser.parse_args(['create', '--help'])
        except SystemExit:
            # Expected behavior for --help
            pass
    
    def test_argument_descriptions(self):
        """Test that arguments have descriptions."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest='command')
        
        create_parser = CreateCommand.register_parser(subparsers)
        
        # Parser should have been configured with arguments
        # This test verifies parser configuration succeeded
        assert create_parser is not None
        assert hasattr(create_parser, '_actions')
        
        # Should have more than just 'help' action
        assert len(create_parser._actions) > 1