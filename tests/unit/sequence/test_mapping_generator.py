"""Unit tests for MappingFileGenerator."""

import pytest
import csv
from pathlib import Path
from tempfile import TemporaryDirectory, NamedTemporaryFile
from unittest.mock import Mock, patch, mock_open

from flextaxd.sequence.mapping_generator import MappingFileGenerator
from flextaxd.database.sequence_tracking import UnifiedSequenceTracker
from flextaxd.database.sqlite import SQLiteTaxonomyRepository
from flextaxd.core.exceptions import ValidationError, DatabaseError


class TestMappingFileGenerator:
    """Test MappingFileGenerator class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_repository = Mock(spec=SQLiteTaxonomyRepository)
        self.mock_tracker = Mock(spec=UnifiedSequenceTracker)
        
        # Create generator instance
        self.generator = MappingFileGenerator(self.mock_repository)
        # Replace the tracker with our mock
        self.generator.tracker = self.mock_tracker

    def test_initialization(self):
        """Test generator initialization."""
        repository = Mock(spec=SQLiteTaxonomyRepository)
        generator = MappingFileGenerator(repository)
        
        assert generator.repository == repository
        assert isinstance(generator.tracker, UnifiedSequenceTracker)

    def test_generate_accession2taxid_all_types(self):
        """Test generating accession2taxid file with all sequence types."""
        with TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "accession2taxid.txt"
            
            # Mock _get_taxa_with_sequences
            self.generator._get_taxa_with_sequences = Mock(return_value=[562, 511145, 263])
            
            # Mock get_all_accessions_for_taxa
            self.mock_tracker.get_all_accessions_for_taxa = Mock(side_effect=[
                {  # tax_id 562
                    'assembly': ['GCF_000005825.2'],
                    'nucleotide': ['NC_000913.3', 'NC_000914.1'],
                    'protein': ['WP_000001234.1', 'WP_000002345.1']
                },
                {  # tax_id 511145
                    'assembly': ['GCF_000001405.38'],
                    'nucleotide': ['NC_000001.11'],
                    'protein': ['WP_000003456.1']
                },
                {  # tax_id 263
                    'assembly': ['GCF_000008985.1'],
                    'nucleotide': [],
                    'protein': ['WP_000004567.1']
                }
            ])
            
            result = self.generator.generate_accession2taxid(output_path)
            
            # Should have written 10 mappings total (5 + 3 + 2)
            # tax_id 562: 1 assembly + 2 nucleotide + 2 protein = 5
            # tax_id 511145: 1 assembly + 1 nucleotide + 1 protein = 3  
            # tax_id 263: 1 assembly + 0 nucleotide + 1 protein = 2
            assert result == 10
            assert output_path.exists()
            
            # Check file contents
            with open(output_path, 'r') as f:
                reader = csv.DictReader(f, delimiter='\t')
                rows = list(reader)
            
            assert len(rows) == 10
            
            # Check header
            assert 'accession' in rows[0].keys()
            assert 'accession.version' in rows[0].keys()
            assert 'taxid' in rows[0].keys()
            assert 'gi' in rows[0].keys()
            
            # Check some specific mappings
            assembly_rows = [r for r in rows if r['accession'].startswith('GCF_')]
            assert len(assembly_rows) == 3
            assert any(r['taxid'] == '562' and r['accession'] == 'GCF_000005825' for r in assembly_rows)

    def test_generate_accession2taxid_specific_types(self):
        """Test generating accession2taxid with specific sequence types."""
        with TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "protein_accession2taxid.txt"
            
            self.generator._get_taxa_with_sequences = Mock(return_value=[562])
            self.mock_tracker.get_all_accessions_for_taxa = Mock(return_value={
                'assembly': ['GCF_000005825.2'],
                'nucleotide': ['NC_000913.3'],
                'protein': ['WP_000001234.1', 'WP_000002345.1']
            })
            
            # Only request protein sequences
            result = self.generator.generate_accession2taxid(output_path, ['protein'])
            
            assert result == 2  # Only protein accessions
            
            with open(output_path, 'r') as f:
                reader = csv.DictReader(f, delimiter='\t')
                rows = list(reader)
            
            assert len(rows) == 2
            assert all(r['accession'].startswith('WP_') for r in rows)

    def test_generate_accession2taxid_empty_accessions(self):
        """Test generating accession2taxid with empty accessions."""
        with TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "empty_accession2taxid.txt"
            
            self.generator._get_taxa_with_sequences = Mock(return_value=[562])
            self.mock_tracker.get_all_accessions_for_taxa = Mock(return_value={
                'assembly': ['', None, 'GCF_000005825.2'],  # Include empty/None values
                'nucleotide': [],
                'protein': ['']
            })
            
            result = self.generator.generate_accession2taxid(output_path)
            
            # Should only count valid (non-empty) accessions
            assert result == 1
            
            with open(output_path, 'r') as f:
                reader = csv.DictReader(f, delimiter='\t')
                rows = list(reader)
            
            assert len(rows) == 1
            assert rows[0]['accession'] == 'GCF_000005825'

    def test_generate_accession2taxid_version_handling(self):
        """Test proper handling of accession versions."""
        with TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "versioned_accession2taxid.txt"
            
            self.generator._get_taxa_with_sequences = Mock(return_value=[562])
            self.mock_tracker.get_all_accessions_for_taxa = Mock(return_value={
                'assembly': ['GCF_000005825.2'],  # Has version
                'nucleotide': ['NC_000913'],      # No version
                'protein': []
            })
            
            result = self.generator.generate_accession2taxid(output_path)
            
            assert result == 2
            
            with open(output_path, 'r') as f:
                reader = csv.DictReader(f, delimiter='\t')
                rows = list(reader)
            
            # Check version handling
            gcf_row = next(r for r in rows if r['accession'] == 'GCF_000005825')
            assert gcf_row['accession.version'] == 'GCF_000005825.2'
            
            nc_row = next(r for r in rows if r['accession'] == 'NC_000913')
            assert nc_row['accession.version'] == 'NC_000913.1'  # Default version added

    def test_generate_nucl2taxid(self):
        """Test generating nucl2taxid file."""
        with TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "nucl2taxid.txt"
            
            self.generator._get_taxa_with_sequences = Mock(return_value=[562, 511145])
            self.mock_tracker.get_all_accessions_for_taxa = Mock(side_effect=[
                {'nucleotide': ['NC_000913.3', 'NC_000914.1']},
                {'nucleotide': ['NC_000001.11']}
            ])
            
            result = self.generator.generate_nucl2taxid(output_path)
            
            assert result == 3
            assert output_path.exists()
            
            with open(output_path, 'r') as f:
                reader = csv.DictReader(f, delimiter='\t')
                rows = list(reader)
            
            assert len(rows) == 3
            assert all(r['accession'].startswith('NC_') for r in rows)

    def test_generate_prot2taxid(self):
        """Test generating prot2taxid file."""
        with TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "prot2taxid.txt"
            
            self.generator._get_taxa_with_sequences = Mock(return_value=[562])
            self.mock_tracker.get_all_accessions_for_taxa = Mock(return_value={
                'protein': ['WP_000001234.1', 'WP_000002345.1', 'YP_000003456.1']
            })
            
            result = self.generator.generate_prot2taxid(output_path)
            
            assert result == 3
            assert output_path.exists()
            
            with open(output_path, 'r') as f:
                reader = csv.DictReader(f, delimiter='\t')
                rows = list(reader)
            
            assert len(rows) == 3
            # Check mix of protein accession types
            wp_rows = [r for r in rows if r['accession'].startswith('WP_')]
            yp_rows = [r for r in rows if r['accession'].startswith('YP_')]
            assert len(wp_rows) == 2
            assert len(yp_rows) == 1

    def test_generate_genome_sizes(self):
        """Test generating genome_sizes file."""
        with TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "genome_sizes.txt"
            
            # Mock the correct method that the implementation actually calls
            self.generator._get_taxa_with_genomes = Mock(return_value=[562, 511145])
            self.mock_tracker.get_genome_size_info = Mock(side_effect=[
                {  # tax_id 562
                    'genome_size': 4641652,
                    'assembly_accession': 'GCF_000005825.2',
                    'sequence_count': 1
                },
                {  # tax_id 511145
                    'genome_size': 4686137,
                    'assembly_accession': 'GCF_000001405.38',
                    'sequence_count': 2
                }
            ])
            
            result = self.generator.generate_genome_sizes(output_path)
            
            assert result == 2
            assert output_path.exists()
            
            with open(output_path, 'r') as f:
                reader = csv.DictReader(f, delimiter='\t')
                rows = list(reader)
            
            assert len(rows) == 2
            assert 'taxid' in rows[0].keys()
            assert 'genome_size' in rows[0].keys()
            assert 'assembly_accession' in rows[0].keys()
            
            # Check specific values
            ecoli_row = next(r for r in rows if r['taxid'] == '562')
            assert ecoli_row['genome_size'] == '4641652'
            assert ecoli_row['assembly_accession'] == 'GCF_000005825.2'

    def test_generate_genome_sizes_missing_info(self):
        """Test generating genome_sizes with missing genome info."""
        with TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "genome_sizes.txt"
            
            self.generator._get_taxa_with_genomes = Mock(return_value=[562, 263])
            self.mock_tracker.get_genome_size_info = Mock(side_effect=[
                {  # tax_id 562 - complete info
                    'genome_size': 4641652,
                    'assembly_accession': 'GCF_000005825.2',
                    'sequence_count': 1
                },
                {'genome_size': None}  # tax_id 263 - missing info (return dict with None, not None itself)
            ])
            
            result = self.generator.generate_genome_sizes(output_path)
            
            assert result == 1  # Only one valid entry (the implementation silently skips missing genome_size)
            
            with open(output_path, 'r') as f:
                reader = csv.DictReader(f, delimiter='\t')
                rows = list(reader)
            
            assert len(rows) == 1
            assert rows[0]['taxid'] == '562'

    def test_generate_all_mappings(self):
        """Test generating all standard mapping files."""
        with TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            prefix = "test_"
            
            # Mock _get_taxa_with_sequences for summary generation
            self.generator._get_taxa_with_sequences = Mock(return_value=[562, 511145, 263])
            
            # Mock individual generation methods
            self.generator.generate_accession2taxid = Mock(return_value=1500)
            self.generator.generate_nucl2taxid = Mock(return_value=800)
            self.generator.generate_prot2taxid = Mock(return_value=700)
            self.generator.generate_genome_sizes = Mock(return_value=50)
            
            result = self.generator.generate_all_mappings(output_dir, prefix)
            
            expected_result = {
                "accession2taxid.txt": 1500,
                "nucl2taxid.txt": 800,
                "prot2taxid.txt": 700,
                "genome_sizes.txt": 50
            }
            
            assert result == expected_result
            
            # Check all methods were called with correct paths
            self.generator.generate_accession2taxid.assert_called_once_with(
                output_dir / "test_accession2taxid.txt"
            )
            self.generator.generate_nucl2taxid.assert_called_once_with(
                output_dir / "test_nucl2taxid.txt"
            )
            self.generator.generate_prot2taxid.assert_called_once_with(
                output_dir / "test_prot2taxid.txt"
            )
            self.generator.generate_genome_sizes.assert_called_once_with(
                output_dir / "test_genome_sizes.txt"
            )

    def test_generate_all_mappings_no_prefix(self):
        """Test generating all mappings without prefix."""
        with TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            
            # Mock _get_taxa_with_sequences for summary generation
            self.generator._get_taxa_with_sequences = Mock(return_value=[562, 511145])
            
            # Mock individual generation methods
            self.generator.generate_accession2taxid = Mock(return_value=1000)
            self.generator.generate_nucl2taxid = Mock(return_value=600)
            self.generator.generate_prot2taxid = Mock(return_value=400)
            self.generator.generate_genome_sizes = Mock(return_value=30)
            
            result = self.generator.generate_all_mappings(output_dir)
            
            expected_result = {
                "accession2taxid.txt": 1000,
                "nucl2taxid.txt": 600,
                "prot2taxid.txt": 400,
                "genome_sizes.txt": 30
            }
            
            assert result == expected_result

    def test_generate_for_tool_diamond(self):
        """Test generating tool-specific files for Diamond."""
        with TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            
            # Mock the tool-specific method
            with patch.object(self.generator, '_generate_diamond_mappings') as mock_diamond:
                mock_diamond.return_value = {
                    "prot.accession2taxid": 700,
                    "taxonomy_info.txt": 50
                }
                
                result = self.generator.generate_for_tool("diamond", output_dir)
                
                assert result["prot.accession2taxid"] == 700
                assert result["taxonomy_info.txt"] == 50
                mock_diamond.assert_called_once_with(output_dir)

    def test_generate_for_tool_kraken2(self):
        """Test generating tool-specific files for Kraken2."""
        with TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            
            with patch.object(self.generator, '_generate_kraken2_mappings') as mock_kraken2:
                mock_kraken2.return_value = {
                    "seqid2taxid.map": 1200,
                    "names.dmp": 800,
                    "nodes.dmp": 800
                }
                
                result = self.generator.generate_for_tool("kraken2", output_dir)
                
                assert result["seqid2taxid.map"] == 1200
                mock_kraken2.assert_called_once_with(output_dir)

    def test_generate_for_tool_mmseqs2(self):
        """Test generating tool-specific files for MMseqs2."""
        with TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            
            with patch.object(self.generator, '_generate_mmseqs2_mappings') as mock_mmseqs2:
                mock_mmseqs2.return_value = {
                    "names.dmp": 800,
                    "nodes.dmp": 800,
                    "prot.accession2taxid": 700,
                    "lca_mapping.txt": 350
                }
                
                result = self.generator.generate_for_tool("mmseqs2", output_dir)
                
                assert "lca_mapping.txt" in result
                assert result["lca_mapping.txt"] == 350
                mock_mmseqs2.assert_called_once_with(output_dir)

    def test_generate_for_tool_unknown(self):
        """Test generating files for unknown tool (falls back to all mappings)."""
        with TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            
            # Mock both methods that access database
            self.generator._get_taxa_with_sequences = Mock(return_value=[])
            self.generator._get_taxa_with_genomes = Mock(return_value=[])
            
            # Should not raise error, but generate all mappings with warning
            result = self.generator.generate_for_tool("unknown_tool", output_dir)
            
            # Should return results for all mapping files
            assert isinstance(result, dict)
            assert "accession2taxid.txt" in result

    def test_get_taxa_with_sequences(self):
        """Test getting taxa that have sequence data."""
        # Mock the database connection and cursor
        mock_cursor = Mock()
        mock_cursor.fetchall.side_effect = [
            [{'tax_id': 562}, {'tax_id': 511145}],  # From genomes table
            [{'tax_id': 263}, {'tax_id': 9606}]     # From proteins table  
        ]
        
        mock_conn = Mock()
        mock_conn.execute.return_value = mock_cursor
        
        self.generator.repository._get_connection = Mock(return_value=mock_conn)
        
        result = self.generator._get_taxa_with_sequences()
        
        # Should return unique union of both sets: [562, 511145, 263, 9606]
        expected_taxa = [562, 511145, 263, 9606]
        assert sorted(result) == sorted(expected_taxa)
        
        # Should have executed both queries
        assert mock_conn.execute.call_count == 2

    def test_generate_diamond_files_implementation(self):
        """Test Diamond-specific file generation."""
        with TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            
            # Mock dependencies based on actual implementation
            self.generator.generate_prot2taxid = Mock(return_value=700)
            self.generator.generate_genome_sizes = Mock(return_value=50)
            
            result = self.generator._generate_diamond_mappings(output_dir)
            
            assert "prot.accession2taxid" in result
            assert "genome_sizes.txt" in result
            assert result["prot.accession2taxid"] == 700
            assert result["genome_sizes.txt"] == 50
            
            self.generator.generate_prot2taxid.assert_called_once_with(
                output_dir / "prot.accession2taxid"
            )
            self.generator.generate_genome_sizes.assert_called_once_with(
                output_dir / "genome_sizes.txt"
            )

    def test_generate_kraken2_files_implementation(self):
        """Test Kraken2-specific file generation."""
        with TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            
            # Mock dependencies based on actual implementation
            self.generator.generate_nucl2taxid = Mock(return_value=1200)
            self.generator.generate_accession2taxid = Mock(return_value=800)
            
            result = self.generator._generate_kraken2_mappings(output_dir)
            
            assert "seqid2taxid.map" in result
            assert "accession2taxid.txt" in result
            assert result["seqid2taxid.map"] == 1200
            assert result["accession2taxid.txt"] == 800
            
            self.generator.generate_nucl2taxid.assert_called_once_with(
                output_dir / "seqid2taxid.map"
            )
            self.generator.generate_accession2taxid.assert_called_once_with(
                output_dir / "accession2taxid.txt"
            )

    def test_file_creation_with_parent_directories(self):
        """Test that files are created with necessary parent directories."""
        with TemporaryDirectory() as tmp_dir:
            # Create nested path that doesn't exist
            output_path = Path(tmp_dir) / "nested" / "subdirs" / "accession2taxid.txt"
            
            self.generator._get_taxa_with_sequences = Mock(return_value=[562])
            self.mock_tracker.get_all_accessions_for_taxa = Mock(return_value={
                'assembly': ['GCF_000005825.2']
            })
            
            result = self.generator.generate_accession2taxid(output_path)
            
            assert result == 1
            assert output_path.exists()
            assert output_path.parent.exists()  # Parent directories created

    def test_error_handling_file_write_permission(self):
        """Test error handling when file write permissions are denied."""
        with TemporaryDirectory() as tmp_dir:
            # Use a path in a temp directory to avoid filesystem issues
            readonly_path = Path(tmp_dir) / "readonly" / "accession2taxid.txt"
            
            self.generator._get_taxa_with_sequences = Mock(return_value=[562])
            
            # Mock mkdir to succeed but open to fail with permission error
            with patch('pathlib.Path.mkdir'), \
                 patch('builtins.open', side_effect=PermissionError("Permission denied")):
                with pytest.raises(PermissionError):
                    self.generator.generate_accession2taxid(readonly_path)

    def test_empty_taxa_handling(self):
        """Test handling when no taxa have sequences."""
        with TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "empty_accession2taxid.txt"
            
            self.generator._get_taxa_with_sequences = Mock(return_value=[])
            
            result = self.generator.generate_accession2taxid(output_path)
            
            assert result == 0
            assert output_path.exists()
            
            # Should still have header
            with open(output_path, 'r') as f:
                reader = csv.DictReader(f, delimiter='\t')
                rows = list(reader)
            
            assert len(rows) == 0  # No data rows, only header

    def test_logging_output(self):
        """Test that appropriate logging messages are generated."""
        with TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "accession2taxid.txt"
            
            self.generator._get_taxa_with_sequences = Mock(return_value=[562])
            self.mock_tracker.get_all_accessions_for_taxa = Mock(return_value={
                'assembly': ['GCF_000005825.2']
            })
            
            with patch('flextaxd.sequence.mapping_generator.logger') as mock_logger:
                result = self.generator.generate_accession2taxid(output_path)
                
                assert result == 1
                mock_logger.info.assert_called_with("Generated accession2taxid with 1 mappings")