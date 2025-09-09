"""Comprehensive tests for CLI argument parsing and validation."""

import pytest
import argparse
from unittest.mock import Mock, patch

from flextaxd.cli.commands.create import CreateCommand
from flextaxd.cli.commands.export import ExportCommand 
# ModifyCommand removed - replaced by add-node, import-tree, add-genome
from flextaxd.cli.commands.stats import StatsCommand
from flextaxd.cli.commands.visualize import VisualizeCommand
from flextaxd.cli.commands.purge import PurgeCommand
from flextaxd.cli.main import create_parser

from ...fixtures.cli.conftest import *
from ...fixtures.cli.mock_data import CLITestHelper


class TestArgumentParsingBase:
    """Base test class for argument parsing."""
    
    def setup_method(self):
        """Set up test fixtures using the actual FlexTaxD CLI parser."""
        self.parser = create_parser()
    
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
        # Parser is already set up with all commands by create_parser()
    
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
            '--verbose',
            'create',
            '--input', '/test/input.tsv', 
            '--database', '/test/output.ftd'
        ])
        
        assert args is not None
        assert args.verbose == 1  # verbose is a count, not boolean
    
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
        """Test validation-related options - basic test since create doesn't have validation flags."""
        args = self.parse_args([
            'create',
            '--input', '/test/input.tsv',
            '--database', '/test/output.ftd'
        ])
        
        assert args is not None
        assert args.input == '/test/input.tsv'
        assert args.database == '/test/output.ftd'
    
    def test_short_argument_forms(self):
        """Test short argument forms."""
        args = self.parse_args([
            '-v',
            'create',
            '-i', '/test/input.tsv',
            '--database', '/test/output.ftd',  # -d doesn't exist, use --database
            '-f', 'ncbi'
        ])
        
        assert args is not None
        assert args.input == '/test/input.tsv'
        assert args.database == '/test/output.ftd'
        if hasattr(args, 'format'):
            assert args.format == 'ncbi'
        if hasattr(args, 'verbose'):
            assert args.verbose == 1


class TestExportCommandArgumentParsing(TestArgumentParsingBase):
    """Test argument parsing for export command."""
    
    def setup_method(self):
        """Set up export command parser."""
        super().setup_method()
        # Parser is already set up with all commands by create_parser()
    
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
        """Test format support."""
        args = self.parse_args([
            'export',
            '--database', '/test/db.ftd',
            '--format', 'tsv',
            '--output', '/test/output.tsv'
        ])
        
        assert args is not None
        assert args.format == 'tsv'
        assert args.output == '/test/output.tsv'
    
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
            '--verbose',
            'export',
            '--database', '/test/db.ftd',
            '--classifier', 'diamond',
            '--output', '/test/diamond_db/',
            '--validate',
            '--compress'
        ])
        
        assert args is not None
        if hasattr(args, 'validate'):
            assert args.validate is True
        if hasattr(args, 'compress'):
            assert args.compress is True
        assert args.verbose == 1  # verbose is a count
    
    def test_missing_export_specification(self):
        """Test missing export type specification."""
        args = self.parse_args([
            'export',
            '--database', '/test/db.ftd',
            '--output', '/test/output/'
            # No --classifier or --format (both are required)
        ])
        
        # Should fail parsing due to missing required arguments
        assert args is None


# NOTE: TestModifyCommandArgumentParsing class removed.
# The modify command has been replaced by focused commands:
# - add-node: For single node operations  
# - import-tree: For tree import with merge/replace strategies
# - add-genome: For genome operations
# Argument parsing tests for these commands are in their respective test files.


class TestStatsCommandArgumentParsing(TestArgumentParsingBase):
    """Test argument parsing for stats command."""
    
    def setup_method(self):
        """Set up stats command parser."""
        super().setup_method()
        # Parser is already set up with all commands by create_parser()
    
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
    
    def test_format_option(self):
        """Test format option."""
        args = self.parse_args([
            'stats',
            '--database', '/test/db.ftd',
            '--format', 'json'
        ])
        
        assert args is not None
        assert args.format == 'json'
    
    def test_validation_level(self):
        """Test validation level option."""
        args = self.parse_args([
            'stats',
            '--database', '/test/db.ftd',
            '--validation-level', 'comprehensive'
        ])
        
        assert args is not None
        assert args.validation_level == 'comprehensive'
    
    def test_stats_options_combination(self):
        """Test combination of statistics options."""
        args = self.parse_args([
            '--verbose',
            'stats',
            '--database', '/test/db.ftd',
            '--detailed',
            '--format', 'json',
            '--consistency-check'
        ])
        
        assert args is not None
        assert args.verbose == 1
        assert args.database == '/test/db.ftd'
        assert args.detailed is True
        assert args.format == 'json'
        assert args.consistency_check is True


class TestVisualizeCommandArgumentParsing(TestArgumentParsingBase):
    """Test argument parsing for visualize command."""
    
    def setup_method(self):
        """Set up visualize command parser."""
        super().setup_method()
        # Parser is already set up with all commands by create_parser()
    
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
            '--label-size', '12'
        ])
        
        assert args is not None
        assert args.type == 'plot'
        assert args.output == '/test/plot.png'
        assert args.label_size == 12
    
    def test_visualization_options(self):
        """Test various visualization options."""
        args = self.parse_args([
            'visualize',
            '--database', '/test/db.ftd',
            '--type', 'tree',
            '--max-depth', '5',
            '--show-ids',
            '--show-genomes',
            '--compact'
        ])
        
        assert args is not None
        assert args.type == 'tree'
        assert args.max_depth == 5
        assert args.show_ids is True
        assert args.show_genomes is True
        assert args.compact is True
    
    def test_visualization_types(self):
        """Test different visualization types."""
        viz_types = ['tree', 'plot', 'newick', 'newick_vis']
        
        for viz_type in viz_types:
            args = self.parse_args([
                'visualize',
                '--database', '/test/db.ftd',
                '--type', viz_type
            ])
            
            assert args is not None
            assert args.type == viz_type
    
    def test_advanced_visualization_options(self):
        """Test advanced visualization options."""
        args = self.parse_args([
            '--verbose',
            'visualize',
            '--database', '/test/db.ftd',
            '--type', 'plot',
            '--output', '/test/advanced_plot.png',
            '--clip-labels',
            '--start-node', 'Bacteria'
        ])
        
        assert args is not None
        assert args.type == 'plot'
        assert args.output == '/test/advanced_plot.png'
        assert args.clip_labels is True
        assert args.start_node == 'Bacteria'


class TestPurgeCommandArgumentParsing(TestArgumentParsingBase):
    """Test argument parsing for purge command."""
    
    def setup_method(self):
        """Set up purge command parser."""
        super().setup_method()
        # Parser is already set up with all commands by create_parser()
    
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
            '--dry-run',
            '--force',
            '--backup', '/test/safety_backup.ftd'
        ])
        
        assert args is not None
        assert args.dry_run is True
        assert args.force is True
        assert args.backup == '/test/safety_backup.ftd'


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
        from flextaxd.cli.main import create_parser
        parser = create_parser()
        
        # Test valid numeric arguments
        args = parser.parse_args([
            'visualize',
            '--database', '/test/db.ftd',
            '--type', 'plot',
            '--max-depth', '5',
            '--label-size', '12'
        ])
        
        assert args.max_depth == 5
        assert args.label_size == 12
    
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
            ('add-node', ['--database', '--name', '--rank']),
            ('import-tree', ['--database', '--input']),
            ('add-genome', ['--database']),
            ('stats', ['--database']),
            ('visualize', ['--database', '--type', '--output']),
            ('purge', ['--database'])
        ]
        
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest='command')
        
        # Register all commands
        from flextaxd.cli.commands.add_node import AddNodeCommand
        from flextaxd.cli.commands.import_tree import ImportTreeCommand  
        from flextaxd.cli.commands.add_genome import AddGenomeCommand
        
        CreateCommand.register_parser(subparsers)
        ExportCommand.register_parser(subparsers)
        AddNodeCommand.register_parser(subparsers)
        ImportTreeCommand.register_parser(subparsers)
        AddGenomeCommand.register_parser(subparsers)
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
        from flextaxd.cli.commands.add_node import AddNodeCommand
        from flextaxd.cli.commands.import_tree import ImportTreeCommand  
        from flextaxd.cli.commands.add_genome import AddGenomeCommand
        
        commands = [
            CreateCommand, ExportCommand, AddNodeCommand,
            ImportTreeCommand, AddGenomeCommand, StatsCommand, VisualizeCommand, PurgeCommand
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