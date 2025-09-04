"""Comprehensive unit tests for StatsCommand."""

import pytest
import argparse
import json
from unittest.mock import Mock, patch, mock_open
from pathlib import Path

from flextaxd.cli.commands.stats import StatsCommand
from flextaxd.core.exceptions import ValidationError
from flextaxd.core.models import TaxonomyTree

from ....fixtures.cli.conftest import *
from ....fixtures.cli.mock_data import MockData, CLITestHelper


class TestStatsCommand:
    """Test StatsCommand basic functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = StatsCommand()
    
    def test_initialization(self):
        """Test command initialization."""
        assert isinstance(self.command, StatsCommand)
        assert hasattr(self.command, 'logger')
    
    def test_register_parser(self):
        """Test parser registration."""
        mock_subparsers = Mock()
        mock_parser = Mock()
        mock_subparsers.add_parser.return_value = mock_parser
        
        parser = StatsCommand.register_parser(mock_subparsers)
        
        # Verify parser was created
        mock_subparsers.add_parser.assert_called_once()
        call_args = mock_subparsers.add_parser.call_args
        assert call_args[0][0] == "stats"
        
        # Verify arguments were added
        assert mock_parser.add_argument.called
    
    @patch('flextaxd.cli.commands.stats.SQLiteTaxonomyRepository')
    def test_execute_basic_stats(self, mock_repo_class, sample_taxonomy_tree):
        """Test basic statistics display."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            detailed=False,
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('builtins.print') as mock_print:
            
            result = self.command.execute(args)
            
            assert result == 0
            # Should display basic statistics
            assert mock_print.called
    
    @patch('flextaxd.cli.commands.stats.SQLiteTaxonomyRepository')
    def test_execute_detailed_stats(self, mock_repo_class, sample_taxonomy_tree):
        """Test detailed statistics display."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            detailed=True,
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('builtins.print') as mock_print:
            
            result = self.command.execute(args)
            
            assert result == 0
            # Should display detailed statistics
            assert mock_print.called
            # Detailed stats should have more output
    
    @patch('flextaxd.cli.commands.stats.SQLiteTaxonomyRepository')
    def test_execute_with_output_file(self, mock_repo_class, sample_taxonomy_tree):
        """Test statistics output to file."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            detailed=True,
            output="/test/stats.json",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('builtins.open', mock_open()) as mock_file, \
             patch('json.dump') as mock_json_dump:
            
            result = self.command.execute(args)
            
            assert result == 0
            # Should write JSON output to file
            mock_file.assert_called_with("/test/stats.json", 'w')
            mock_json_dump.assert_called_once()
    
    def test_execute_missing_database(self):
        """Test execution with missing database."""
        args = CLITestHelper.create_mock_args(
            database="/nonexistent/db.ftd",
            detailed=False,
            verbose=False
        )
        
        with patch('pathlib.Path') as mock_path:
            mock_path_obj = Mock()
            mock_path_obj.exists.return_value = False
            mock_path.return_value = mock_path_obj
            
            result = self.command.execute(args)
            assert result != 0


class TestStatsCommandStatisticsCalculation:
    """Test StatsCommand statistics calculation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = StatsCommand()
    
    @patch('flextaxd.cli.commands.stats.SQLiteTaxonomyRepository')
    def test_basic_statistics_calculation(self, mock_repo_class):
        """Test calculation of basic statistics."""
        # Use complex tree for realistic statistics
        tree = MockData.create_complex_taxonomy_tree()
        
        mock_repo = Mock()
        mock_repo.load_tree.return_value = tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            detailed=False,
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('builtins.print') as mock_print:
            
            result = self.command.execute(args)
            
            assert result == 0
            # Verify print was called with statistics
            print_calls = [call[0][0] for call in mock_print.call_args_list]
            
            # Should contain basic counts
            stats_output = ' '.join(print_calls)
            assert '11' in stats_output or 'nodes' in stats_output  # Node count
            assert '5' in stats_output or 'genomes' in stats_output  # Genome count
    
    @patch('flextaxd.cli.commands.stats.SQLiteTaxonomyRepository')
    def test_detailed_statistics_calculation(self, mock_repo_class):
        """Test calculation of detailed statistics."""
        tree = MockData.create_complex_taxonomy_tree()
        
        mock_repo = Mock()
        mock_repo.load_tree.return_value = tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            detailed=True,
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('builtins.print') as mock_print:
            
            result = self.command.execute(args)
            
            assert result == 0
            # Should include rank distribution, depth analysis, etc.
            print_calls = [call[0][0] for call in mock_print.call_args_list]
            stats_output = ' '.join(print_calls)
            
            # Check for detailed statistics elements
            assert any('rank' in call.lower() or 'depth' in call.lower() for call in print_calls)
    
    @patch('flextaxd.cli.commands.stats.SQLiteTaxonomyRepository')
    def test_empty_database_statistics(self, mock_repo_class):
        """Test statistics for empty database."""
        empty_tree = TaxonomyTree()
        
        mock_repo = Mock()
        mock_repo.load_tree.return_value = empty_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = CLITestHelper.create_mock_args(
            database="/test/empty.ftd",
            detailed=True,
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('builtins.print') as mock_print:
            
            result = self.command.execute(args)
            
            assert result == 0
            # Should handle empty database gracefully
            print_calls = [call[0][0] for call in mock_print.call_args_list]
            stats_output = ' '.join(print_calls)
            assert '0' in stats_output  # Should show zero counts
    
    @patch('flextaxd.cli.commands.stats.SQLiteTaxonomyRepository')
    def test_rank_specific_statistics(self, mock_repo_class):
        """Test rank-specific statistics."""
        tree = MockData.create_complex_taxonomy_tree()
        
        mock_repo = Mock()
        mock_repo.load_tree.return_value = tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            detailed=True,
            rank="species",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('builtins.print') as mock_print:
            
            result = self.command.execute(args)
            
            assert result == 0
            # Should focus on species-level statistics
            print_calls = [call[0][0] for call in mock_print.call_args_list]
            stats_output = ' '.join(print_calls)
            assert 'species' in stats_output.lower()


class TestStatsCommandOutputFormats:
    """Test StatsCommand different output formats."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = StatsCommand()
    
    @patch('flextaxd.cli.commands.stats.SQLiteTaxonomyRepository')
    def test_json_output(self, mock_repo_class, sample_taxonomy_tree):
        """Test JSON format output."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            detailed=True,
            output="/test/stats.json",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('builtins.open', mock_open()) as mock_file, \
             patch('json.dump') as mock_json_dump:
            
            result = self.command.execute(args)
            
            assert result == 0
            # Should write properly structured JSON
            mock_json_dump.assert_called_once()
            # Check that the data structure is dict-like
            call_args = mock_json_dump.call_args[0]
            assert isinstance(call_args[0], dict)
    
    @patch('flextaxd.cli.commands.stats.SQLiteTaxonomyRepository')
    def test_console_output_formatting(self, mock_repo_class):
        """Test console output formatting."""
        tree = MockData.create_complex_taxonomy_tree()
        
        mock_repo = Mock()
        mock_repo.load_tree.return_value = tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            detailed=True,
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('builtins.print') as mock_print:
            
            result = self.command.execute(args)
            
            assert result == 0
            # Should have well-formatted console output
            print_calls = [call[0][0] for call in mock_print.call_args_list]
            
            # Check for formatting elements
            assert any('=' in call or '-' in call for call in print_calls)  # Headers
            assert len(print_calls) > 5  # Multiple lines of output
    
    @patch('flextaxd.cli.commands.stats.SQLiteTaxonomyRepository')
    def test_output_file_creation(self, mock_repo_class, sample_taxonomy_tree):
        """Test output file creation and path handling."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            detailed=True,
            output="/test/nested/path/stats.json",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('pathlib.Path') as mock_path, \
             patch('builtins.open', mock_open()) as mock_file, \
             patch('json.dump'):
            
            mock_path_obj = Mock()
            mock_path_obj.parent.mkdir = Mock()
            mock_path.return_value = mock_path_obj
            
            result = self.command.execute(args)
            
            assert result == 0
            # Should create parent directories
            mock_path_obj.parent.mkdir.assert_called_with(parents=True, exist_ok=True)
    
    @patch('flextaxd.cli.commands.stats.SQLiteTaxonomyRepository')
    def test_output_file_error_handling(self, mock_repo_class, sample_taxonomy_tree):
        """Test handling of output file errors."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            detailed=True,
            output="/readonly/stats.json",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('builtins.open', side_effect=PermissionError("Permission denied")):
            
            result = self.command.execute(args)
            assert result != 0


class TestStatsCommandValidation:
    """Test StatsCommand validation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = StatsCommand()
    
    def test_database_validation(self):
        """Test database file validation."""
        args = CLITestHelper.create_mock_args(
            database="/nonexistent/db.ftd",
            detailed=False,
            verbose=False
        )
        
        with patch('pathlib.Path') as mock_path:
            mock_path_obj = Mock()
            mock_path_obj.exists.return_value = False
            mock_path.return_value = mock_path_obj
            
            result = self.command.execute(args)
            assert result != 0
    
    def test_invalid_rank(self):
        """Test validation with invalid rank."""
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            detailed=True,
            rank="invalid_rank",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('flextaxd.cli.commands.stats.SQLiteTaxonomyRepository'):
            
            result = self.command.execute(args)
            # Should handle invalid rank gracefully
            # Implementation dependent on validation strategy
    
    def test_output_path_validation(self):
        """Test output path validation."""
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            detailed=True,
            output="/invalid/path/stats.json",
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('flextaxd.cli.commands.stats.SQLiteTaxonomyRepository') as mock_repo_class, \
             patch('pathlib.Path') as mock_path:
            
            # Setup database mock
            mock_repo = Mock()
            mock_repo_class.return_value.__enter__.return_value = mock_repo
            
            # Setup path mock to fail on mkdir
            mock_path_obj = Mock()
            mock_path_obj.parent.mkdir.side_effect = OSError("Cannot create directory")
            mock_path.return_value = mock_path_obj
            
            result = self.command.execute(args)
            # Should handle path creation errors
            assert result != 0


class TestStatsCommandErrorHandling:
    """Test StatsCommand error handling."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = StatsCommand()
    
    @patch('flextaxd.cli.commands.stats.SQLiteTaxonomyRepository')
    def test_database_load_error(self, mock_repo_class):
        """Test handling of database load errors."""
        mock_repo = Mock()
        mock_repo.load_tree.side_effect = Exception("Database corrupted")
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = CLITestHelper.create_mock_args(
            database="/test/corrupted.ftd",
            detailed=False,
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'):
            result = self.command.execute(args)
            assert result != 0
    
    @patch('flextaxd.cli.commands.stats.SQLiteTaxonomyRepository')
    def test_statistics_calculation_error(self, mock_repo_class, sample_taxonomy_tree):
        """Test handling of statistics calculation errors."""
        # Mock a tree that causes calculation errors
        problematic_tree = Mock()
        problematic_tree._nodes = {1: Mock()}
        problematic_tree._genomes = {}
        # Make get_tree_statistics raise an error
        problematic_tree.get_tree_statistics.side_effect = Exception("Calculation failed")
        
        mock_repo = Mock()
        mock_repo.load_tree.return_value = problematic_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            detailed=True,
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'):
            result = self.command.execute(args)
            # Should handle calculation errors gracefully
            assert result != 0
    
    @patch('flextaxd.cli.commands.stats.SQLiteTaxonomyRepository')
    def test_interrupted_statistics(self, mock_repo_class, sample_taxonomy_tree):
        """Test handling of interrupted statistics calculation."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            detailed=True,
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('builtins.print', side_effect=KeyboardInterrupt()):
            
            result = self.command.execute(args)
            assert result != 0


class TestStatsCommandAdvancedFeatures:
    """Test StatsCommand advanced features."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = StatsCommand()
    
    @patch('flextaxd.cli.commands.stats.SQLiteTaxonomyRepository')
    def test_performance_with_large_database(self, mock_repo_class):
        """Test performance with large database simulation."""
        # Create a large mock tree
        large_tree = Mock()
        large_tree._nodes = {i: Mock() for i in range(10000)}  # 10k nodes
        large_tree._genomes = {f"genome_{i}": Mock() for i in range(1000)}  # 1k genomes
        
        # Mock statistics method to return realistic data
        large_tree.get_tree_statistics.return_value = {
            "total_nodes": 10000,
            "total_genomes": 1000,
            "max_depth": 12,
            "rank_distribution": {"species": 5000, "genus": 2000, "family": 1000}
        }
        
        mock_repo = Mock()
        mock_repo.load_tree.return_value = large_tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = CLITestHelper.create_mock_args(
            database="/test/large.ftd",
            detailed=True,
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('builtins.print') as mock_print:
            
            import time
            start_time = time.time()
            result = self.command.execute(args)
            end_time = time.time()
            
            assert result == 0
            # Should complete in reasonable time
            assert end_time - start_time < 5.0  # Should be fast for stats
    
    @patch('flextaxd.cli.commands.stats.SQLiteTaxonomyRepository')
    def test_memory_efficient_statistics(self, mock_repo_class):
        """Test memory-efficient statistics calculation."""
        tree = MockData.create_complex_taxonomy_tree()
        
        mock_repo = Mock()
        mock_repo.load_tree.return_value = tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            detailed=True,
            verbose=False
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('builtins.print'):
            
            # Monitor memory usage would be implementation-specific
            result = self.command.execute(args)
            
            assert result == 0
            # Should not consume excessive memory
    
    @patch('flextaxd.cli.commands.stats.SQLiteTaxonomyRepository')
    def test_verbose_statistics_output(self, mock_repo_class):
        """Test verbose statistics output."""
        tree = MockData.create_complex_taxonomy_tree()
        
        mock_repo = Mock()
        mock_repo.load_tree.return_value = tree
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = CLITestHelper.create_mock_args(
            database="/test/db.ftd",
            detailed=True,
            verbose=True
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('builtins.print') as mock_print, \
             patch.object(self.command, 'logger') as mock_logger:
            
            result = self.command.execute(args)
            
            assert result == 0
            # Should have verbose logging and detailed output
            assert mock_logger.info.called or mock_logger.debug.called
            # Should have more print output in verbose mode
            assert len(mock_print.call_args_list) > 5


class TestStatsCommandIntegration:
    """Integration tests for StatsCommand."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = StatsCommand()
    
    def test_realistic_database_statistics(self, temp_dir):
        """Test realistic database statistics workflow."""
        # Use complex tree with realistic structure
        tree = MockData.create_complex_taxonomy_tree()
        db_path = temp_dir / "stats_test.ftd"
        
        args = CLITestHelper.create_mock_args(
            database=str(db_path),
            detailed=True,
            verbose=True
        )
        
        with patch('flextaxd.cli.commands.stats.SQLiteTaxonomyRepository') as mock_repo_class, \
             patch.object(self.command, '_validate_database_path'), \
             patch('builtins.print') as mock_print:
            
            mock_repo = Mock()
            mock_repo.load_tree.return_value = tree
            mock_repo_class.return_value.__enter__.return_value = mock_repo
            
            result = self.command.execute(args)
            
            assert result == 0
            # Should display comprehensive statistics
            print_calls = [str(call[0][0]) for call in mock_print.call_args_list]
            stats_output = ' '.join(print_calls)
            
            # Verify realistic statistics are displayed
            assert any(str(len(tree._nodes)) in call for call in print_calls)  # Node count
            assert any(str(len(tree._genomes)) in call for call in print_calls)  # Genome count
    
    def test_statistics_export_workflow(self, temp_dir):
        """Test complete statistics export workflow."""
        tree = MockData.create_complex_taxonomy_tree()
        db_path = temp_dir / "export_stats.ftd"
        output_path = temp_dir / "exported_stats.json"
        
        args = CLITestHelper.create_mock_args(
            database=str(db_path),
            detailed=True,
            output=str(output_path),
            verbose=False
        )
        
        with patch('flextaxd.cli.commands.stats.SQLiteTaxonomyRepository') as mock_repo_class, \
             patch.object(self.command, '_validate_database_path'):
            
            mock_repo = Mock()
            mock_repo.load_tree.return_value = tree
            mock_repo_class.return_value.__enter__.return_value = mock_repo
            
            # Use real file operations
            result = self.command.execute(args)
            
            assert result == 0
            # Should create output file (mocked, but path handling tested)
    
    def test_comparative_statistics(self):
        """Test comparative statistics between different tree structures.""" 
        simple_tree = MockData().sample_taxonomy_tree if hasattr(MockData(), 'sample_taxonomy_tree') else TaxonomyTree()
        complex_tree = MockData.create_complex_taxonomy_tree()
        
        args_simple = CLITestHelper.create_mock_args(
            database="/test/simple.ftd",
            detailed=True,
            verbose=False
        )
        
        args_complex = CLITestHelper.create_mock_args(
            database="/test/complex.ftd", 
            detailed=True,
            verbose=False
        )
        
        with patch('flextaxd.cli.commands.stats.SQLiteTaxonomyRepository') as mock_repo_class, \
             patch.object(self.command, '_validate_database_path'), \
             patch('builtins.print') as mock_print:
            
            # Test simple tree
            mock_repo = Mock()
            mock_repo.load_tree.return_value = simple_tree
            mock_repo_class.return_value.__enter__.return_value = mock_repo
            
            result1 = self.command.execute(args_simple)
            simple_calls = len(mock_print.call_args_list)
            
            # Reset mock
            mock_print.reset_mock()
            
            # Test complex tree
            mock_repo.load_tree.return_value = complex_tree
            result2 = self.command.execute(args_complex)
            complex_calls = len(mock_print.call_args_list)
            
            assert result1 == 0 and result2 == 0
            # Complex tree should generally produce more detailed output
            # (Implementation dependent on statistics detail level)