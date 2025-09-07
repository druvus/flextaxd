"""Comprehensive unit tests for AddGenomeCommand."""

import pytest
import argparse
from unittest.mock import Mock, patch
from pathlib import Path

from flextaxd.cli.commands.add_genome import AddGenomeCommand
from flextaxd.core.exceptions import ValidationError, DatabaseError
from flextaxd.core.models import TaxonomyTree, TaxonomyNode, TaxonomicRank, GenomeInfo

from ....fixtures.cli.conftest import *
from ....fixtures.cli.mock_data import MockData, CLITestHelper


def create_add_genome_mock_args(**overrides):
    """Create complete mock args for AddGenomeCommand with all required attributes."""
    defaults = {
        'database': '/test/db.ftd',
        'genome_id': 'test_genome',
        'tax_id': None,
        'tax_name': None,
        'file_path': None,
        'assembly_accession': None,
        'nucleotide_accession': None,
        'protein_accession': None,
        'biosample_accession': None,
        'sequence_type': 'genome',
        'source': 'custom',
        'strain': None,
        'description': None,
        'validate_file': True,
        'skip_file_validation': False,
        'dry_run': False,
        'force': False,
        'verbose': False,
        'quiet': False,
        'skip_validation': True,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


class TestAddGenomeCommand:
    """Test AddGenomeCommand basic functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = AddGenomeCommand()
    
    def test_initialization(self):
        """Test command initialization."""
        assert isinstance(self.command, AddGenomeCommand)
        assert hasattr(self.command, 'logger')
    
    def test_register_parser(self):
        """Test parser registration."""
        mock_subparsers = Mock()
        mock_parser = Mock()
        mock_subparsers.add_parser.return_value = mock_parser
        
        parser = AddGenomeCommand.register_parser(mock_subparsers)
        
        # Verify parser was created
        mock_subparsers.add_parser.assert_called_once()
        call_args = mock_subparsers.add_parser.call_args
        assert call_args[0][0] == "add-genome"
        
        # Should be the actual parser returned
        assert parser == mock_parser
    
    @patch('flextaxd.cli.commands.add_genome.SQLiteTaxonomyRepository')
    def test_execute_add_genome_by_tax_id(self, mock_repo_class, sample_taxonomy_tree):
        """Test adding a genome by taxonomy ID."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        
        # Mock target node lookup
        target_node = sample_taxonomy_tree.get_node(4)
        mock_repo.get_node.return_value = target_node
        
        # Mock no existing genome
        mock_repo.get_genome.return_value = None
        
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_add_genome_mock_args(
            genome_id="ecoli_genome",
            tax_id=4,
            sequence_type="genome",
            source="NCBI",
            skip_file_validation=True
        )
        
        with patch.object(self.command, '_validate_database_path'):
            result = self.command.execute(args)
            
            assert result == 0
            mock_repo.add_genome.assert_called_once()
            
            # Verify the genome that was added
            added_genome = mock_repo.add_genome.call_args[0][0]
            assert added_genome.genome_id == "ecoli_genome"
            assert added_genome.tax_id == 4
            assert added_genome.sequence_type == "genome"
            assert added_genome.source == "NCBI"
    
    @patch('flextaxd.cli.commands.add_genome.SQLiteTaxonomyRepository')
    def test_execute_add_genome_by_tax_name(self, mock_repo_class, sample_taxonomy_tree):
        """Test adding a genome by taxonomy name."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        
        # Mock target node lookup by name
        target_node = sample_taxonomy_tree.get_node(4)
        mock_repo.get_node_by_name.return_value = target_node
        
        # Mock no existing genome
        mock_repo.get_genome.return_value = None
        
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_add_genome_mock_args(
            genome_id="ecoli_genome",
            tax_name="Escherichia",
            sequence_type="genome",
            source="NCBI",
            skip_file_validation=True
        )
        
        with patch.object(self.command, '_validate_database_path'):
            result = self.command.execute(args)
            
            assert result == 0
            mock_repo.add_genome.assert_called_once()
    
    @patch('flextaxd.cli.commands.add_genome.SQLiteTaxonomyRepository')
    def test_execute_add_genome_with_file_path(self, mock_repo_class, sample_taxonomy_tree):
        """Test adding a genome with file path validation."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        
        # Mock target node lookup
        target_node = sample_taxonomy_tree.get_node(4)
        mock_repo.get_node.return_value = target_node
        
        # Mock no existing genome
        mock_repo.get_genome.return_value = None
        
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_add_genome_mock_args(
            genome_id="ecoli_genome",
            tax_id=4,
            file_path="/data/ecoli.fna",
            sequence_type="genome",
            source="NCBI",
            skip_file_validation=True
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('flextaxd.cli.commands.add_genome.Path') as mock_path, \
             patch('pathlib.Path') as mock_pathlib_path:
            
            # Mock file exists and is accessible
            mock_path_obj = Mock()
            mock_path_obj.exists.return_value = True
            mock_path_obj.is_file.return_value = True
            mock_path_obj.stat.return_value.st_size = 1024000  # 1MB
            mock_path.return_value = mock_path_obj
            mock_pathlib_path.return_value = mock_path_obj
            
            result = self.command.execute(args)
            
            assert result == 0
            mock_repo.add_genome.assert_called_once()
            
            # Verify file path was included
            added_genome = mock_repo.add_genome.call_args[0][0]
            assert added_genome.file_path == "/data/ecoli.fna"
    
    @patch('flextaxd.cli.commands.add_genome.SQLiteTaxonomyRepository')
    def test_execute_update_existing_genome(self, mock_repo_class, sample_taxonomy_tree):
        """Test updating an existing genome with force flag."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        
        # Mock target node lookup
        target_node = sample_taxonomy_tree.get_node(4)
        mock_repo.get_node.return_value = target_node
        
        # Mock existing genome
        existing_genome = GenomeInfo(
            genome_id="ecoli_genome",
            tax_id=4,
            sequence_type="genome",
            source="old_source"
        )
        mock_repo.get_genome.return_value = existing_genome
        
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_add_genome_mock_args(
            genome_id="ecoli_genome",
            tax_id=4,
            sequence_type="genome",
            source="new_source",
            force=True,
            skip_file_validation=True
        )
        
        with patch.object(self.command, '_validate_database_path'):
            result = self.command.execute(args)
            
            assert result == 0
            mock_repo.update_genome.assert_called_once()
            mock_repo.add_genome.assert_not_called()
    
    @patch('flextaxd.cli.commands.add_genome.SQLiteTaxonomyRepository')
    def test_execute_dry_run(self, mock_repo_class, sample_taxonomy_tree):
        """Test dry-run mode."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        
        # Mock target node lookup
        target_node = sample_taxonomy_tree.get_node(4)
        mock_repo.get_node.return_value = target_node
        
        # Mock no existing genome
        mock_repo.get_genome.return_value = None
        
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_add_genome_mock_args(
            genome_id="dry_run_genome",
            tax_id=4,
            sequence_type="genome",
            source="test",
            dry_run=True,
            skip_file_validation=True
        )
        
        with patch.object(self.command, '_validate_database_path'):
            result = self.command.execute(args)
            
            assert result == 0
            # Should not add genome in dry-run mode
            mock_repo.add_genome.assert_not_called()
            mock_repo.update_genome.assert_not_called()


class TestAddGenomeCommandValidation:
    """Test AddGenomeCommand validation logic."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = AddGenomeCommand()
    
    @patch('flextaxd.cli.commands.add_genome.SQLiteTaxonomyRepository')
    def test_missing_target_validation(self, mock_repo_class):
        """Test validation when target taxonomy node doesn't exist."""
        mock_repo = Mock()
        mock_repo.get_node.return_value = None  # Target doesn't exist
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_add_genome_mock_args(
            genome_id="orphan_genome",
            tax_id=999,  # Non-existent target
            skip_file_validation=True
        )
        
        with patch.object(self.command, '_validate_database_path'):
            result = self.command.execute(args)
            
            assert result == 1  # Should fail
            mock_repo.add_genome.assert_not_called()
    
    @patch('flextaxd.cli.commands.add_genome.SQLiteTaxonomyRepository')
    def test_existing_genome_validation(self, mock_repo_class, sample_taxonomy_tree):
        """Test validation when genome ID already exists."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        
        # Mock target node exists
        target_node = sample_taxonomy_tree.get_node(4)
        mock_repo.get_node.return_value = target_node
        
        # Mock existing genome
        existing_genome = GenomeInfo(
            genome_id="existing_genome",
            tax_id=4,
            sequence_type="genome"
        )
        mock_repo.get_genome.return_value = existing_genome
        
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_add_genome_mock_args(
            genome_id="existing_genome",
            tax_id=4,
            force=False,  # Don't force overwrite
            skip_file_validation=True
        )
        
        with patch.object(self.command, '_validate_database_path'):
            result = self.command.execute(args)
            
            assert result == 1  # Should fail without force
            mock_repo.add_genome.assert_not_called()
    
    @patch('flextaxd.cli.commands.add_genome.SQLiteTaxonomyRepository')
    def test_file_validation_missing_file(self, mock_repo_class, sample_taxonomy_tree):
        """Test file validation when file doesn't exist."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        
        # Mock target node exists
        target_node = sample_taxonomy_tree.get_node(4)
        mock_repo.get_node.return_value = target_node
        
        # Mock no existing genome
        mock_repo.get_genome.return_value = None
        
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_add_genome_mock_args(
            genome_id="missing_file_genome",
            tax_id=4,
            file_path="/nonexistent/file.fna",
            validate_file=True
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('flextaxd.cli.commands.add_genome.Path') as mock_path:
            
            # Mock file doesn't exist
            mock_path_obj = Mock()
            mock_path_obj.exists.return_value = False
            mock_path.return_value = mock_path_obj
            
            result = self.command.execute(args)
            
            assert result == 1  # Should fail
            mock_repo.add_genome.assert_not_called()
    
    @patch('flextaxd.cli.commands.add_genome.SQLiteTaxonomyRepository')
    def test_genome_info_validation(self, mock_repo_class, sample_taxonomy_tree):
        """Test GenomeInfo model validation."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        
        # Mock target node exists
        target_node = sample_taxonomy_tree.get_node(4)
        mock_repo.get_node.return_value = target_node
        
        # Mock no existing genome
        mock_repo.get_genome.return_value = None
        
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_add_genome_mock_args(
            genome_id="",  # Invalid empty genome ID
            tax_id=4,
            skip_file_validation=True
        )
        
        with patch.object(self.command, '_validate_database_path'):
            result = self.command.execute(args)
            
            assert result == 1  # Should fail due to validation
            mock_repo.add_genome.assert_not_called()


class TestAddGenomeCommandErrorHandling:
    """Test AddGenomeCommand error handling."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = AddGenomeCommand()
    
    @patch('flextaxd.cli.commands.add_genome.SQLiteTaxonomyRepository')
    def test_database_error_handling(self, mock_repo_class, sample_taxonomy_tree):
        """Test handling of database errors."""
        mock_repo = Mock()
        mock_repo.load_tree.return_value = sample_taxonomy_tree
        
        # Mock successful lookups up to the point of error
        target_node = sample_taxonomy_tree.get_node(4)
        mock_repo.get_node.return_value = target_node
        mock_repo.get_genome.return_value = None
        
        # Mock database error on add
        mock_repo.add_genome.side_effect = DatabaseError("Database write failed")
        
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_add_genome_mock_args(
            genome_id="error_genome",
            tax_id=4,
            skip_file_validation=True
        )
        
        with patch.object(self.command, '_validate_database_path'):
            result = self.command.execute(args)
            
            assert result == 1  # Should fail gracefully
    
    @patch('flextaxd.cli.commands.add_genome.SQLiteTaxonomyRepository')
    def test_validation_error_handling(self, mock_repo_class):
        """Test handling of validation errors."""
        mock_repo = Mock()
        mock_repo.get_node.side_effect = ValidationError("Invalid target node")
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_add_genome_mock_args(
            genome_id="validation_error_genome",
            tax_id=4,
            skip_file_validation=True
        )
        
        with patch.object(self.command, '_validate_database_path'):
            result = self.command.execute(args)
            
            assert result == 1  # Should fail gracefully
    
    @patch('flextaxd.cli.commands.add_genome.SQLiteTaxonomyRepository')
    def test_unexpected_error_handling(self, mock_repo_class):
        """Test handling of unexpected errors."""
        mock_repo = Mock()
        mock_repo.get_node.side_effect = Exception("Unexpected error")
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_add_genome_mock_args(
            genome_id="exception_genome",
            tax_id=4,
            skip_file_validation=True
        )
        
        with patch.object(self.command, '_validate_database_path'):
            result = self.command.execute(args)
            
            assert result == 1  # Should fail gracefully


class TestAddGenomeCommandIntegration:
    """Integration tests for AddGenomeCommand."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.command = AddGenomeCommand()
    
    @patch('flextaxd.cli.commands.add_genome.SQLiteTaxonomyRepository')
    def test_comprehensive_genome_addition(self, mock_repo_class):
        """Test adding a genome with comprehensive metadata."""
        tree = MockData.create_complex_taxonomy_tree()
        
        mock_repo = Mock()
        mock_repo.load_tree.return_value = tree
        
        # Mock target node lookup (E. coli)
        ecoli_node = tree.get_node(8)
        mock_repo.get_node.return_value = ecoli_node
        
        # Mock no existing genome
        mock_repo.get_genome.return_value = None
        
        mock_repo_class.return_value.__enter__.return_value = mock_repo
        
        args = create_add_genome_mock_args(
            genome_id="GCF_000005825.2",
            tax_id=8,
            file_path="/data/ecoli_k12.fna",
            assembly_accession="GCF_000005825.2",
            nucleotide_accession="NC_000913.3",
            biosample_accession="SAMN02604091",
            sequence_type="genome",
            source="NCBI",
            strain="K-12 substr. MG1655",
            description="Escherichia coli str. K-12 substr. MG1655",
            skip_file_validation=True
        )
        
        with patch.object(self.command, '_validate_database_path'), \
             patch('flextaxd.cli.commands.add_genome.Path') as mock_path, \
             patch('pathlib.Path') as mock_pathlib_path:
            
            # Mock file exists and is accessible
            mock_path_obj = Mock()
            mock_path_obj.exists.return_value = True
            mock_path_obj.is_file.return_value = True
            mock_path_obj.stat.return_value.st_size = 5000000  # 5MB
            mock_path.return_value = mock_path_obj
            mock_pathlib_path.return_value = mock_path_obj
            
            result = self.command.execute(args)
            
            assert result == 0
            mock_repo.add_genome.assert_called_once()
            
            # Verify comprehensive genome data
            added_genome = mock_repo.add_genome.call_args[0][0]
            assert added_genome.genome_id == "GCF_000005825.2"
            assert added_genome.tax_id == 8
            assert added_genome.assembly_accession == "GCF_000005825.2"
            assert added_genome.nucleotide_accession == "NC_000913.3"
            assert added_genome.biosample_accession == "SAMN02604091"
            assert added_genome.strain == "K-12 substr. MG1655"
            assert added_genome.source == "NCBI"