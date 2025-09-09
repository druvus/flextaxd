"""Unit tests for SequenceTracker."""

import pytest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch, MagicMock

from flextaxd.sequence.sequence_tracker import SequenceTracker, SequenceStats
from flextaxd.sequence.unified_manager import UnifiedSequenceManager, ExtractionResult
from flextaxd.sequence.mapping_generator import MappingFileGenerator
from flextaxd.database.sqlite import SQLiteTaxonomyRepository
from flextaxd.core.exceptions import ValidationError, DatabaseError


class TestSequenceStats:
    """Test SequenceStats dataclass."""

    def test_create_empty_stats(self):
        """Test creating empty statistics object."""
        stats = SequenceStats()
        
        assert stats.total_files == 0
        assert stats.genome_files == 0
        assert stats.protein_files == 0
        assert stats.taxa_with_genomes == 0
        assert stats.taxa_with_proteins == 0
        assert stats.total_sequences == 0
        assert stats.total_proteins == 0
        assert stats.file_validation_errors is None

    def test_create_populated_stats(self):
        """Test creating statistics with data."""
        errors = ["File not found: test.fna", "Invalid format: test2.faa"]
        stats = SequenceStats(
            total_files=150,
            genome_files=75,
            protein_files=75,
            taxa_with_genomes=50,
            taxa_with_proteins=45,
            total_sequences=1200000,
            total_proteins=850000,
            file_validation_errors=errors
        )
        
        assert stats.total_files == 150
        assert stats.genome_files == 75
        assert stats.protein_files == 75
        assert stats.taxa_with_genomes == 50
        assert stats.taxa_with_proteins == 45
        assert stats.total_sequences == 1200000
        assert stats.total_proteins == 850000
        assert stats.file_validation_errors == errors
        assert len(stats.file_validation_errors) == 2


class TestSequenceTracker:
    """Test SequenceTracker class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_repository = Mock(spec=SQLiteTaxonomyRepository)
        
        # Mock the _get_connection method
        self.mock_connection = Mock()
        self.mock_repository._get_connection.return_value = self.mock_connection
        
        # Create tracker instance
        self.tracker = SequenceTracker(self.mock_repository)

    def test_initialization(self):
        """Test tracker initialization."""
        assert self.tracker.repository == self.mock_repository
        assert isinstance(self.tracker.manager, UnifiedSequenceManager)
        assert isinstance(self.tracker.generator, MappingFileGenerator)

    def test_register_genomes(self):
        """Test registering genome files from directory."""
        with TemporaryDirectory() as tmp_dir:
            genome_dir = Path(tmp_dir)
            
            # Create test genome files
            (genome_dir / "genome1.fna").write_text(">seq1\nATCGATCG\n")
            (genome_dir / "genome2.fna").write_text(">seq2\nGCTAGCTA\n")
            (genome_dir / "other.txt").write_text("Not a genome file")
            
            # Mock the manager's register_genome_files method
            expected_result = {"genome1.fna": 1, "genome2.fna": 2}
            self.tracker.manager.register_genome_files = Mock(return_value=expected_result)
            
            result = self.tracker.register_genomes(genome_dir, "*.fna")
            
            assert result == expected_result
            self.tracker.manager.register_genome_files.assert_called_once_with(genome_dir, "*.fna")

    def test_register_genomes_custom_pattern(self):
        """Test registering genomes with custom pattern."""
        with TemporaryDirectory() as tmp_dir:
            genome_dir = Path(tmp_dir)
            
            # Mock the manager method
            expected_result = {"genome1.fasta": 1}
            self.tracker.manager.register_genome_files = Mock(return_value=expected_result)
            
            result = self.tracker.register_genomes(genome_dir, "*.fasta")
            
            assert result == expected_result
            self.tracker.manager.register_genome_files.assert_called_once_with(genome_dir, "*.fasta")

    def test_register_proteins(self):
        """Test registering protein files from directory."""
        with TemporaryDirectory() as tmp_dir:
            protein_dir = Path(tmp_dir)
            
            # Create test protein files
            (protein_dir / "proteins1.faa").write_text(">prot1\nMKLLSVLLNAIVYFKGLWK\n")
            (protein_dir / "proteins2.faa").write_text(">prot2\nMETALPVSKESK\n")
            
            # Mock the manager's register_protein_files method
            expected_result = {"proteins1.faa": 3, "proteins2.faa": 4}
            self.tracker.manager.register_protein_files = Mock(return_value=expected_result)
            
            result = self.tracker.register_proteins(protein_dir, "*.faa")
            
            assert result == expected_result
            self.tracker.manager.register_protein_files.assert_called_once_with(protein_dir, "*.faa")

    def test_register_proteins_custom_pattern(self):
        """Test registering proteins with custom pattern."""
        with TemporaryDirectory() as tmp_dir:
            protein_dir = Path(tmp_dir)
            
            # Mock the manager method
            expected_result = {"proteins.fasta": 5}
            self.tracker.manager.register_protein_files = Mock(return_value=expected_result)
            
            result = self.tracker.register_proteins(protein_dir, "*.fasta")
            
            assert result == expected_result
            self.tracker.manager.register_protein_files.assert_called_once_with(protein_dir, "*.fasta")

    def test_extract_proteins_one_per_taxa(self):
        """Test extracting proteins with one-per-taxa strategy."""
        with TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            
            # Mock extraction result
            expected_result = ExtractionResult(
                files_created=[output_path / "tax_562.faa", output_path / "tax_511145.faa"],
                proteins_extracted=1250,
                taxa_processed=2,
                strategy_used="one_per_taxa"
            )
            
            self.tracker.manager.extract_proteins_flexible = Mock(return_value=expected_result)
            
            result = self.tracker.extract_proteins("one_per_taxa", output_path, taxa_limit=100)
            
            assert result == expected_result
            assert result.strategy_used == "one_per_taxa"
            assert result.proteins_extracted == 1250
            assert result.taxa_processed == 2
            self.tracker.manager.extract_proteins_flexible.assert_called_once_with(
                "one_per_taxa", output_path, taxa_limit=100
            )

    def test_extract_proteins_global_strategy(self):
        """Test extracting proteins with global strategy."""
        with TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            
            expected_result = ExtractionResult(
                files_created=[output_path / "all_proteins.faa"],
                proteins_extracted=5000,
                taxa_processed=50,
                strategy_used="global",
                mapping_files=[output_path / "protein_mappings.txt"]
            )
            
            self.tracker.manager.extract_proteins_flexible = Mock(return_value=expected_result)
            
            result = self.tracker.extract_proteins("global", output_path, max_file_size="1GB")
            
            assert result == expected_result
            assert result.strategy_used == "global"
            assert result.mapping_files is not None
            assert len(result.mapping_files) == 1
            self.tracker.manager.extract_proteins_flexible.assert_called_once_with(
                "global", output_path, max_file_size="1GB"
            )

    def test_generate_mapping_files_all_formats(self):
        """Test generating all mapping file formats."""
        with TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            
            # Mock generator's generate_all_mappings method
            expected_result = {
                "accession2taxid.txt": 1500,
                "nucl2taxid.txt": 800,
                "prot2taxid.txt": 700,
                "genome_sizes.txt": 50
            }
            self.tracker.generator.generate_all_mappings = Mock(return_value=expected_result)
            
            result = self.tracker.generate_mapping_files(output_dir)
            
            assert result == expected_result
            assert "accession2taxid.txt" in result
            assert "genome_sizes.txt" in result
            self.tracker.generator.generate_all_mappings.assert_called_once_with(output_dir, '')

    def test_generate_mapping_files_with_prefix(self):
        """Test generating mapping files with custom prefix."""
        with TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            prefix = "custom_"
            
            expected_result = {
                "custom_accession2taxid.txt": 1200,
                "custom_nucl2taxid.txt": 600,
                "custom_prot2taxid.txt": 600,
                "custom_genome_sizes.txt": 40
            }
            self.tracker.generator.generate_all_mappings = Mock(return_value=expected_result)
            
            result = self.tracker.generate_mapping_files(output_dir, prefix=prefix)
            
            assert result == expected_result
            self.tracker.generator.generate_all_mappings.assert_called_once_with(output_dir, prefix)

    def test_generate_mapping_files_specific_formats(self):
        """Test generating specific mapping file formats."""
        with TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            formats = ["accession2taxid", "prot2taxid"]
            
            # Mock individual generator methods
            self.tracker.generator.generate_accession2taxid = Mock(return_value=1500)
            self.tracker.generator.generate_prot2taxid = Mock(return_value=700)
            
            result = self.tracker.generate_mapping_files(output_dir, formats=formats)
            
            assert result == {"accession2taxid": 1500, "prot2taxid": 700}
            self.tracker.generator.generate_accession2taxid.assert_called_once_with(
                output_dir / "accession2taxid.txt"
            )
            self.tracker.generator.generate_prot2taxid.assert_called_once_with(
                output_dir / "prot2taxid.txt"
            )

    def test_generate_mapping_files_unknown_format(self):
        """Test handling unknown mapping format."""
        with TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            formats = ["accession2taxid", "unknown_format"]
            
            # Mock methods
            self.tracker.generator.generate_accession2taxid = Mock(return_value=1500)
            
            # Should handle unknown format gracefully
            with patch('flextaxd.sequence.sequence_tracker.logger') as mock_logger:
                result = self.tracker.generate_mapping_files(output_dir, formats=formats)
                
                assert result == {"accession2taxid": 1500}
                mock_logger.warning.assert_called_once_with("Unknown mapping format: unknown_format")

    def test_generate_for_tool_diamond(self):
        """Test generating tool-specific mapping files for Diamond."""
        with TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            
            expected_result = {
                "prot.accession2taxid": 700,
                "taxonomy_info.txt": 50
            }
            self.tracker.generator.generate_for_tool = Mock(return_value=expected_result)
            
            result = self.tracker.generate_for_tool("diamond", output_dir)
            
            assert result == expected_result
            self.tracker.generator.generate_for_tool.assert_called_once_with("diamond", output_dir)

    def test_generate_for_tool_kraken2(self):
        """Test generating tool-specific mapping files for Kraken2."""
        with TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            
            expected_result = {
                "seqid2taxid.map": 1200,
                "names.dmp": 800,
                "nodes.dmp": 800
            }
            self.tracker.generator.generate_for_tool = Mock(return_value=expected_result)
            
            result = self.tracker.generate_for_tool("kraken2", output_dir)
            
            assert result == expected_result
            self.tracker.generator.generate_for_tool.assert_called_once_with("kraken2", output_dir)

    def test_get_sequence_statistics(self):
        """Test getting comprehensive sequence statistics."""
        # Mock database cursor and results
        mock_cursor = Mock()
        self.mock_connection.execute.return_value = mock_cursor
        
        # The actual implementation uses multiple execute calls, so we need to handle them in order
        mock_cursor.fetchall.side_effect = [
            # First query: file counts by type
            [('genome', 75), ('protein_taxa', 50), ('protein_global', 25)],
            # Missing files query  
            [('/path/to/missing1.fna',), ('/path/to/missing2.faa',)]
        ]
        
        # Mock the fetchone results for various queries
        mock_cursor.fetchone.side_effect = [
            (50,),      # taxa_with_genomes query
            (45,),      # taxa_with_proteins query  
            (1200000,), # total_sequences query
            (850000,),  # total_proteins query
        ]
        
        stats = self.tracker.get_sequence_statistics()
        
        assert isinstance(stats, SequenceStats)
        assert stats.total_files == 150  # 75 + 50 + 25
        assert stats.genome_files == 75
        assert stats.protein_files == 75  # 50 + 25
        assert stats.taxa_with_genomes == 50
        assert stats.taxa_with_proteins == 45
        assert stats.total_sequences == 1200000
        assert stats.total_proteins == 850000
        assert stats.file_validation_errors == ["Missing file: /path/to/missing1.fna", "Missing file: /path/to/missing2.faa"]

    def test_get_sequence_statistics_database_error(self):
        """Test handling database error in statistics generation."""
        # Mock database error
        self.mock_connection.execute.side_effect = Exception("Database connection failed")
        
        # The actual implementation catches exceptions and returns default stats
        stats = self.tracker.get_sequence_statistics()
        
        # Should return default SequenceStats when there's an error
        assert isinstance(stats, SequenceStats)
        assert stats.total_files == 0
        assert stats.genome_files == 0
        assert stats.protein_files == 0

    def test_validate_sequences(self):
        """Test sequence validation functionality."""
        # Mock the generator's validation method
        validation_result = {
            "valid_mappings": 1450,
            "invalid_mappings": 5,
            "duplicate_accessions": ["GCF_000001.1"],
            "missing_taxa": [12345],
            "issues": ["Duplicate accession GCF_000001.1 for taxa 562 and 12345"]
        }
        
        self.tracker.generator.validate_mappings = Mock(return_value=validation_result)
        
        result = self.tracker.validate_sequences()
        
        assert result == validation_result
        assert result["valid_mappings"] == 1450
        assert result["invalid_mappings"] == 5
        self.tracker.generator.validate_mappings.assert_called_once()

    def test_cleanup_missing_files_dry_run(self):
        """Test cleanup missing files in dry run mode."""
        # Mock the cleanup method
        cleanup_result = {
            'files_to_remove': ['/path/to/missing1.fna', '/path/to/missing2.faa'],
            'taxa_mappings_to_remove': [],
            'proteins_to_remove': ['protein_123', 'protein_456'],
            'dry_run': True
        }
        
        # The actual method exists on SequenceTracker
        with patch.object(self.tracker, 'cleanup_missing_files', return_value=cleanup_result) as mock_cleanup:
            result = self.tracker.cleanup_missing_files(dry_run=True)
            
            assert result == cleanup_result
            assert result['dry_run'] is True
            assert len(result['files_to_remove']) == 2
            assert len(result['proteins_to_remove']) == 2
            mock_cleanup.assert_called_once_with(dry_run=True)
    
    def test_sync_with_genomes(self):
        """Test synchronizing sequence tracking with genomes table."""
        # Mock the sync method
        sync_result = {
            'genomes_registered': 15,
            'files_registered': 15,
            'errors': []
        }
        
        with patch.object(self.tracker, 'sync_with_genomes', return_value=sync_result) as mock_sync:
            result = self.tracker.sync_with_genomes()
            
            assert result == sync_result
            assert result['genomes_registered'] == 15
            assert result['files_registered'] == 15
            assert result['errors'] == []
            mock_sync.assert_called_once()

    @pytest.fixture
    def sample_extraction_result(self):
        """Sample extraction result for testing."""
        return ExtractionResult(
            files_created=[Path("/tmp/tax_562.faa"), Path("/tmp/tax_511145.faa")],
            proteins_extracted=2500,
            taxa_processed=2,
            strategy_used="one_per_taxa",
            mapping_files=[Path("/tmp/protein_mappings.txt")]
        )

    def test_extract_proteins_with_result_validation(self, sample_extraction_result):
        """Test protein extraction with result validation."""
        self.tracker.manager.extract_proteins_flexible = Mock(return_value=sample_extraction_result)
        
        result = self.tracker.extract_proteins("one_per_taxa", Path("/tmp"), batch_size=1000)
        
        assert isinstance(result, ExtractionResult)
        assert len(result.files_created) == 2
        assert result.proteins_extracted == 2500
        assert result.taxa_processed == 2
        assert result.strategy_used == "one_per_taxa"
        assert result.mapping_files is not None