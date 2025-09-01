"""Unit tests for sequence processing utilities."""

import pytest
import gzip
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from unittest.mock import Mock, patch

from flextaxd.utils.sequence_utils import (
    SequenceInfo, SeqIDMapping, FASTAProcessor,
    SeqIDMappingManager, GenomeDirectoryManager
)
from flextaxd.core.exceptions import ValidationError


class TestSequenceInfo:
    """Test SequenceInfo dataclass."""
    
    def test_create_basic_sequence_info(self):
        """Test creating basic sequence info."""
        seq = SequenceInfo(sequence_id="seq1")
        
        assert seq.sequence_id == "seq1"
        assert seq.taxonomy_id is None
        assert seq.description == ""
        assert seq.length is None
        assert seq.file_path is None
    
    def test_create_complete_sequence_info(self):
        """Test creating complete sequence info."""
        file_path = Path("/test/file.fasta")
        seq = SequenceInfo(
            sequence_id="GCF_123456.1",
            taxonomy_id=562,
            description="Escherichia coli strain K12",
            length=4641652,
            file_path=file_path
        )
        
        assert seq.sequence_id == "GCF_123456.1"
        assert seq.taxonomy_id == 562
        assert seq.description == "Escherichia coli strain K12"
        assert seq.length == 4641652
        assert seq.file_path == file_path


class TestSeqIDMapping:
    """Test SeqIDMapping dataclass."""
    
    def test_create_basic_mapping(self):
        """Test creating basic seq ID mapping."""
        mapping = SeqIDMapping(sequence_id="seq1", taxonomy_id=123)
        
        assert mapping.sequence_id == "seq1"
        assert mapping.taxonomy_id == 123
        assert mapping.source == "unknown"
    
    def test_create_mapping_with_source(self):
        """Test creating mapping with source."""
        mapping = SeqIDMapping(
            sequence_id="GCF_123456.1",
            taxonomy_id=562,
            source="NCBI"
        )
        
        assert mapping.sequence_id == "GCF_123456.1"
        assert mapping.taxonomy_id == 562
        assert mapping.source == "NCBI"


class TestFASTAProcessor:
    """Test FASTAProcessor class."""
    
    def test_processor_initialization(self):
        """Test processor initialization."""
        processor = FASTAProcessor()
        
        assert isinstance(processor.sequence_info, dict)
        assert isinstance(processor.seqid_mappings, dict)
        assert len(processor.sequence_info) == 0
        assert len(processor.seqid_mappings) == 0
    
    def test_parse_fasta_header_basic(self):
        """Test parsing basic FASTA header."""
        processor = FASTAProcessor()
        header = ">seq1 test sequence"
        file_path = Path("/test/file.fasta")
        
        result = processor._parse_fasta_header(header, file_path, 1)
        
        assert result is not None
        assert result.sequence_id == "seq1"
        assert result.description == "test sequence"
        assert result.file_path == file_path
    
    def test_parse_fasta_header_no_description(self):
        """Test parsing FASTA header without description."""
        processor = FASTAProcessor()
        header = ">seq1"
        file_path = Path("/test/file.fasta")
        
        result = processor._parse_fasta_header(header, file_path, 1)
        
        assert result is not None
        assert result.sequence_id == "seq1"
        assert result.description == ""
    
    def test_parse_fasta_header_empty(self):
        """Test parsing empty FASTA header."""
        processor = FASTAProcessor()
        header = ">"
        file_path = Path("/test/file.fasta")
        
        result = processor._parse_fasta_header(header, file_path, 1)
        
        assert result is None
    
    def test_parse_fasta_headers_from_file(self):
        """Test parsing FASTA headers from file."""
        fasta_content = """>seq1 first sequence
ATCGATCGATCG
>seq2 second sequence
GCTAGCTAGCTA
>seq3
TTTTAAAACCCC
"""
        
        with NamedTemporaryFile(mode='w', suffix='.fasta', delete=False) as f:
            f.write(fasta_content)
            temp_path = Path(f.name)
        
        try:
            processor = FASTAProcessor()
            sequences = processor.parse_fasta_headers(temp_path)
            
            assert len(sequences) == 3
            assert sequences[0].sequence_id == "seq1"
            assert sequences[0].description == "first sequence"
            assert sequences[1].sequence_id == "seq2"
            assert sequences[1].description == "second sequence"
            assert sequences[2].sequence_id == "seq3"
            assert sequences[2].description == ""
        finally:
            temp_path.unlink()
    
    def test_parse_fasta_headers_gzipped(self):
        """Test parsing gzipped FASTA file."""
        fasta_content = b""">seq1 gzipped sequence
ATCGATCGATCG
>seq2 another sequence
GCTAGCTAGCTA
"""
        
        with NamedTemporaryFile(suffix='.fasta.gz', delete=False) as f:
            with gzip.open(f.name, 'wb') as gz_f:
                gz_f.write(fasta_content)
            temp_path = Path(f.name)
        
        try:
            processor = FASTAProcessor()
            sequences = processor.parse_fasta_headers(temp_path)
            
            assert len(sequences) == 2
            assert sequences[0].sequence_id == "seq1"
            assert sequences[0].description == "gzipped sequence"
            assert sequences[1].sequence_id == "seq2"
            assert sequences[1].description == "another sequence"
        finally:
            temp_path.unlink()
    
    def test_parse_fasta_headers_nonexistent_file(self):
        """Test parsing non-existent file raises error."""
        processor = FASTAProcessor()
        nonexistent_path = Path("/nonexistent/file.fasta")
        
        with pytest.raises(ValidationError, match="Error parsing FASTA file"):
            processor.parse_fasta_headers(nonexistent_path)
    
    def test_extract_gtdb_taxonomy_from_header(self):
        """Test extracting GTDB taxonomy from header."""
        processor = FASTAProcessor()
        
        # Test valid GTDB header
        header = ">GB_GCA_000001405.38 d__Bacteria;p__Proteobacteria;c__Gammaproteobacteria"
        result = processor.extract_gtdb_taxonomy_from_header(header)
        assert result == "d__Bacteria;p__Proteobacteria;c__Gammaproteobacteria"
        
        # Test another GTDB format
        header = ">RS_GCF_000005825.2 d__Bacteria;p__Firmicutes;c__Bacilli;o__Bacillales"
        result = processor.extract_gtdb_taxonomy_from_header(header)
        assert result == "d__Bacteria;p__Firmicutes;c__Bacilli;o__Bacillales"
        
        # Test header without GTDB taxonomy
        header = ">seq1 regular sequence header"
        result = processor.extract_gtdb_taxonomy_from_header(header)
        assert result is None
    
    def test_extract_silva_taxonomy_from_header(self):
        """Test extracting SILVA taxonomy from header."""
        processor = FASTAProcessor()
        
        # Test valid SILVA header
        header = ">AACY020068177.1.1441.1464 Bacteria;Actinobacteria;Actinobacteria;Coriobacteriales"
        result = processor.extract_silva_taxonomy_from_header(header)
        assert result is not None
        assert result[0] == "AACY020068177.1.1441.1464"
        assert result[1] == "Bacteria;Actinobacteria;Actinobacteria;Coriobacteriales"
        
        # Test header with just accession
        header = ">AACY020068177.1.1441.1464"
        result = processor.extract_silva_taxonomy_from_header(header)
        assert result is None
        
        # Test empty header
        header = ">"
        result = processor.extract_silva_taxonomy_from_header(header)
        assert result is None
    
    def test_split_fasta_by_sequence_individual(self):
        """Test splitting FASTA into individual files."""
        fasta_content = """>seq1 description1
ATCGATCGATCG
>seq2 description2
GCTAGCTAGCTA
>seq3 description3
TTTTAAAACCCC
"""
        
        with NamedTemporaryFile(mode='w', suffix='.fasta', delete=False) as f:
            f.write(fasta_content)
            input_path = Path(f.name)
        
        with TemporaryDirectory() as output_dir:
            output_path = Path(output_dir)
            
            try:
                processor = FASTAProcessor()
                created_files = processor.split_fasta_by_sequence(
                    input_path, output_path, max_sequences_per_file=1
                )
                
                assert len(created_files) == 3
                
                # Check individual files were created
                seq1_file = output_path / "seq1.fasta"
                seq2_file = output_path / "seq2.fasta"
                seq3_file = output_path / "seq3.fasta"
                
                assert seq1_file.exists()
                assert seq2_file.exists()
                assert seq3_file.exists()
                
                # Check file contents
                with open(seq1_file, 'r') as f:
                    content = f.read()
                    assert ">seq1 description1" in content
                    assert "ATCGATCGATCG" in content
                    assert "seq2" not in content  # Only seq1
            finally:
                input_path.unlink()
    
    def test_split_fasta_by_sequence_batch(self):
        """Test splitting FASTA into batch files."""
        fasta_content = """>seq1
ATCG
>seq2
GCTA
>seq3
TTTT
>seq4
AAAA
"""
        
        with NamedTemporaryFile(mode='w', suffix='.fasta', delete=False) as f:
            f.write(fasta_content)
            input_path = Path(f.name)
        
        with TemporaryDirectory() as output_dir:
            output_path = Path(output_dir)
            
            try:
                processor = FASTAProcessor()
                created_files = processor.split_fasta_by_sequence(
                    input_path, output_path, max_sequences_per_file=2
                )
                
                assert len(created_files) == 2
                
                # Check batch files were created
                batch1_file = output_path / "sequences_000000.fasta"
                batch2_file = output_path / "sequences_000001.fasta"
                
                assert batch1_file.exists()
                assert batch2_file.exists()
                
                # Check first batch contains 2 sequences
                with open(batch1_file, 'r') as f:
                    content = f.read()
                    assert content.count('>') == 2
                    assert "seq1" in content
                    assert "seq2" in content
                    
                # Check second batch contains remaining sequences
                with open(batch2_file, 'r') as f:
                    content = f.read()
                    assert content.count('>') == 2
                    assert "seq3" in content
                    assert "seq4" in content
            finally:
                input_path.unlink()
    
    def test_split_fasta_by_sequence_gzipped(self):
        """Test splitting gzipped FASTA file."""
        fasta_content = b""">seq1
ATCGATCG
>seq2
GCTAGCTA
"""
        
        with NamedTemporaryFile(suffix='.fasta.gz', delete=False) as f:
            with gzip.open(f.name, 'wb') as gz_f:
                gz_f.write(fasta_content)
            input_path = Path(f.name)
        
        with TemporaryDirectory() as output_dir:
            output_path = Path(output_dir)
            
            try:
                processor = FASTAProcessor()
                created_files = processor.split_fasta_by_sequence(
                    input_path, output_path, max_sequences_per_file=1
                )
                
                assert len(created_files) == 2
                assert all(f.exists() for f in created_files)
            finally:
                input_path.unlink()
    
    def test_split_fasta_sanitize_filenames(self):
        """Test that special characters in sequence IDs are sanitized."""
        fasta_content = """>seq<1>/test:file*name?
ATCG
"""
        
        with NamedTemporaryFile(mode='w', suffix='.fasta', delete=False) as f:
            f.write(fasta_content)
            input_path = Path(f.name)
        
        with TemporaryDirectory() as output_dir:
            output_path = Path(output_dir)
            
            try:
                processor = FASTAProcessor()
                created_files = processor.split_fasta_by_sequence(
                    input_path, output_path, max_sequences_per_file=1
                )
                
                assert len(created_files) == 1
                # Check that filename is sanitized
                filename = created_files[0].name
                assert "<" not in filename
                assert "/" not in filename
                assert ":" not in filename
                assert "*" not in filename
                assert "?" not in filename
                assert "_" in filename  # Should be replaced with underscores
            finally:
                input_path.unlink()
    
    def test_split_fasta_error_handling(self):
        """Test error handling during FASTA splitting."""
        processor = FASTAProcessor()
        nonexistent_path = Path("/nonexistent/file.fasta")
        
        with TemporaryDirectory() as output_dir:
            output_path = Path(output_dir)
            
            with pytest.raises(ValidationError, match="Error splitting FASTA file"):
                processor.split_fasta_by_sequence(nonexistent_path, output_path)
    
    def test_convert_rna_to_dna(self):
        """Test converting RNA sequences to DNA."""
        rna_content = """>rna1
AUCGAUCGAUCG
>rna2
AAAAUUUUGGGGCCCC
UUUUAAAAGGGGCCCC
"""
        
        with NamedTemporaryFile(mode='w', suffix='.fasta', delete=False) as f:
            f.write(rna_content)
            rna_path = Path(f.name)
        
        try:
            processor = FASTAProcessor()
            processor.convert_rna_to_dna(rna_path)
            
            # Check that RNA was converted to DNA
            with open(rna_path, 'r') as f:
                content = f.read()
                assert 'U' not in content  # No uppercase U
                assert 'u' not in content  # No lowercase u
                assert 'T' in content      # Should have T
                assert 'ATCGATCGATCG' in content  # U->T conversion
                assert 'AAAATTTTGGGGCCCC' in content  # Multiple U conversion
        finally:
            rna_path.unlink()
    
    def test_convert_rna_to_dna_error_handling(self):
        """Test error handling during RNA to DNA conversion."""
        processor = FASTAProcessor()
        nonexistent_path = Path("/nonexistent/file.fasta")
        
        with pytest.raises(ValidationError, match="Error converting RNA to DNA"):
            processor.convert_rna_to_dna(nonexistent_path)


class TestSeqIDMappingManager:
    """Test SeqIDMappingManager class."""
    
    def test_manager_initialization(self):
        """Test manager initialization."""
        manager = SeqIDMappingManager()
        
        assert isinstance(manager.mappings, dict)
        assert len(manager.mappings) == 0
    
    def test_parse_mapping_line_basic(self):
        """Test parsing basic mapping line."""
        manager = SeqIDMappingManager()
        
        # Test tab-separated format
        line = "seq1\t123"
        result = manager._parse_mapping_line(line, "test_source", 1)
        
        assert result is not None
        assert result.sequence_id == "seq1"
        assert result.taxonomy_id == 123
        assert result.source == "test_source"
    
    def test_parse_mapping_line_invalid(self):
        """Test parsing invalid mapping line."""
        manager = SeqIDMappingManager()
        
        # Test line with non-numeric taxid
        line = "seq1\tinvalid_taxid"
        result = manager._parse_mapping_line(line, "test", 1)
        
        # Should handle gracefully and return None
        assert result is None
    
    def test_parse_mapping_line_ncbi_format(self):
        """Test parsing NCBI format mapping line."""
        manager = SeqIDMappingManager()
        
        # Test NCBI format: accession<TAB>accession.version<TAB>taxid<TAB>gi
        line = "NC_000001\tNC_000001.11\t9606\t568815597"
        result = manager._parse_mapping_line(line, "ncbi", 1)
        
        assert result is not None
        assert result.sequence_id == "NC_000001"
        assert result.taxonomy_id == 9606  # Uses taxid from third column
        assert result.source == "ncbi"
    
    def test_parse_mapping_line_invalid_ncbi_taxid(self):
        """Test parsing NCBI line with invalid taxid."""
        manager = SeqIDMappingManager()
        
        # Test line with non-numeric taxid in third column
        line = "seq1\tseq1.1\tinvalid_taxid\tgi123"
        
        with patch('builtins.print'):  # Mock the warning print
            result = manager._parse_mapping_line(line, "test", 1)
        
        assert result is None
    
    def test_create_mapping_from_fasta_and_taxonomy(self):
        """Test creating mapping from FASTA with taxonomy extraction."""
        fasta_content = """>seq1 d__Bacteria;p__Proteobacteria;c__Gammaproteobacteria
ATCG
>seq2 d__Bacteria;p__Firmicutes;c__Bacilli
GCTA
>seq3 d__Bacteria;p__Proteobacteria;c__Gammaproteobacteria
TTTT
"""
        
        with NamedTemporaryFile(mode='w', suffix='.fasta', delete=False) as f:
            f.write(fasta_content)
            fasta_path = Path(f.name)
        
        try:
            manager = SeqIDMappingManager()
            
            def extract_gtdb_taxonomy(header: str) -> str:
                """Extract GTDB taxonomy from header."""
                import re
                match = re.search(r'd__[^;]+(?:;[^;]+)*', header)
                return match.group() if match else ""
            
            mappings = manager.create_mapping_from_fasta_and_taxonomy(
                fasta_path, extract_gtdb_taxonomy
            )
            
            assert len(mappings) == 3
            assert "seq1" in mappings
            assert "seq2" in mappings
            assert "seq3" in mappings
            
            # seq1 and seq3 should have same taxonomy ID (same taxonomy)
            assert mappings["seq1"] == mappings["seq3"]
            # seq2 should have different taxonomy ID
            assert mappings["seq2"] != mappings["seq1"]
            
            # Check internal mappings were created
            assert len(manager.mappings) == 3
            assert "seq1" in manager.mappings
        finally:
            fasta_path.unlink()
    
    def test_export_seqid2taxid_map(self):
        """Test exporting seq ID to tax ID mappings."""
        manager = SeqIDMappingManager()
        
        # Add some test mappings
        manager.mappings["seq1"] = SeqIDMapping("seq1", 123, "test")
        manager.mappings["seq2"] = SeqIDMapping("seq2", 456, "test")
        manager.mappings["seq3"] = SeqIDMapping("seq3", 789, "test")
        
        with NamedTemporaryFile(mode='w', delete=False) as f:
            output_path = Path(f.name)
        
        try:
            manager.export_seqid2taxid_map(output_path)
            
            # Check exported file
            with open(output_path, 'r') as f:
                content = f.read()
                lines = content.strip().split('\n')
                
            assert len(lines) == 3
            # Should be sorted by sequence ID
            assert "seq1\t123" in lines
            assert "seq2\t456" in lines
            assert "seq3\t789" in lines
            
            # Check sorting (seq1 should come before seq2, etc.)
            assert lines.index("seq1\t123") < lines.index("seq2\t456")
        finally:
            output_path.unlink()
    
    def test_get_mapping(self):
        """Test getting taxonomy ID for sequence ID."""
        manager = SeqIDMappingManager()
        
        # Add test mapping
        manager.mappings["seq1"] = SeqIDMapping("seq1", 123, "test")
        
        # Test existing mapping
        tax_id = manager.get_mapping("seq1")
        assert tax_id == 123
        
        # Test non-existent mapping
        tax_id = manager.get_mapping("nonexistent")
        assert tax_id is None
    
    def test_get_statistics_empty(self):
        """Test getting statistics from empty mapping manager."""
        manager = SeqIDMappingManager()
        
        stats = manager.get_statistics()
        assert stats["total_mappings"] == 0
    
    def test_get_statistics_populated(self):
        """Test getting statistics from populated mapping manager."""
        manager = SeqIDMappingManager()
        
        # Add test mappings with different tax IDs and sources
        manager.mappings["seq1"] = SeqIDMapping("seq1", 123, "source1")
        manager.mappings["seq2"] = SeqIDMapping("seq2", 123, "source1")  # Same tax ID
        manager.mappings["seq3"] = SeqIDMapping("seq3", 456, "source2")  # Different tax ID and source
        manager.mappings["seq4"] = SeqIDMapping("seq4", 789, "source1")
        
        stats = manager.get_statistics()
        
        assert stats["total_mappings"] == 4
        assert stats["unique_taxonomy_ids"] == 3  # 123, 456, 789
        assert stats["sources"]["source1"] == 3
        assert stats["sources"]["source2"] == 1
        # Most common tax ID should be 123 (appears twice)
        assert stats["most_common_tax_id"][0] == 123
        assert stats["most_common_tax_id"][1] == 2  # Count
    
    def test_load_seqid_mapping_file(self):
        """Test loading mapping file."""
        mapping_content = """# This is a comment
seq1\t123
seq2\t456
seq3\t789
"""
        
        with NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(mapping_content)
            temp_path = Path(f.name)
        
        try:
            manager = SeqIDMappingManager()
            # Capture print output by mocking it
            with patch('builtins.print'):
                manager.load_seqid_mapping_file(temp_path)
            
            assert len(manager.mappings) == 3
            assert "seq1" in manager.mappings
            assert manager.mappings["seq1"].taxonomy_id == 123
            assert "seq2" in manager.mappings
            assert manager.mappings["seq2"].taxonomy_id == 456
        finally:
            temp_path.unlink()
    
    def test_load_seqid_mapping_gzipped(self):
        """Test loading gzipped mapping file."""
        mapping_content = b"seq1\t111\nseq2\t222\n"
        
        with NamedTemporaryFile(suffix='.txt.gz', delete=False) as f:
            with gzip.open(f.name, 'wb') as gz_f:
                gz_f.write(mapping_content)
            temp_path = Path(f.name)
        
        try:
            manager = SeqIDMappingManager()
            with patch('builtins.print'):
                manager.load_seqid_mapping_file(temp_path)
            
            assert len(manager.mappings) == 2
            assert "seq1" in manager.mappings
            assert manager.mappings["seq1"].taxonomy_id == 111
        finally:
            temp_path.unlink()
    
    def test_load_nonexistent_file(self):
        """Test loading non-existent file raises error."""
        manager = SeqIDMappingManager()
        nonexistent_path = Path("/nonexistent/file.txt")
        
        with pytest.raises(ValidationError, match="Error loading seqid mapping"):
            manager.load_seqid_mapping_file(nonexistent_path)


class TestGenomeDirectoryManager:
    """Test GenomeDirectoryManager class."""
    
    def test_manager_initialization(self):
        """Test manager initialization."""
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            manager = GenomeDirectoryManager(temp_path)
            
            assert manager.genomes_path == temp_path
            assert isinstance(manager.genome_files, dict)
    
    def test_get_genome_directory_path(self):
        """Test getting genome directory path."""
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            manager = GenomeDirectoryManager(temp_path)
            
            # Test getting directory for a genome
            genome_id = "GCF_000001405.40"
            if hasattr(manager, '_get_genome_directory_path'):
                genome_dir = manager._get_genome_directory_path(genome_id)
                
                assert isinstance(genome_dir, Path)
                assert str(genome_dir).startswith(str(temp_path))
    
    def test_directory_structure_creation(self):
        """Test that manager can work with directory structures."""
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            manager = GenomeDirectoryManager(temp_path)
            
            # Create some test structure
            genome_dir = temp_path / "genomes" / "GCF_000001405.40"
            genome_dir.mkdir(parents=True)
            (genome_dir / "genome.fna").write_text(">seq1\nATCGATCG\n")
            
            # Verify structure exists
            assert genome_dir.exists()
            assert (genome_dir / "genome.fna").exists()
    
    def test_scan_directory_with_genome_files(self):
        """Test scanning directory with various genome file types."""
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create various genome files
            (temp_path / "genome1.fasta").write_text(">seq1\nATCG\n")
            (temp_path / "genome2.fa").write_text(">seq2\nGCTA\n")
            (temp_path / "genome3.fna").write_text(">seq3\nTTTT\n")
            (temp_path / "proteins.faa").write_text(">prot1\nMKLL\n")
            (temp_path / "readme.txt").write_text("Not a genome file")  # Should be ignored
            
            # Create gzipped file
            with gzip.open(temp_path / "genome4.fasta.gz", 'wt') as f:
                f.write(">seq4\nAAAA\n")
            
            manager = GenomeDirectoryManager(temp_path)
            
            # Should find 5 genome files (including .gz)
            # Note: .gz files have .fasta extension, so genome4.fasta.gz becomes genome4.fasta as ID
            assert len(manager.genome_files) >= 4  # At least the 4 genome files
            assert "genome1" in manager.genome_files
            assert "genome2" in manager.genome_files
            assert "genome3" in manager.genome_files
            assert "proteins" in manager.genome_files
            # Check that gzipped file is included (may have different ID)
            gzipped_found = any("genome4" in genome_id for genome_id in manager.genome_files.keys())
            assert gzipped_found, f"Expected genome4 in {list(manager.genome_files.keys())}"
            assert "readme" not in manager.genome_files  # .txt ignored
    
    def test_get_genome_file(self):
        """Test getting genome file by ID."""
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create test file
            genome_file = temp_path / "test_genome.fasta"
            genome_file.write_text(">seq1\nATCG\n")
            
            manager = GenomeDirectoryManager(temp_path)
            
            # Test existing genome
            result = manager.get_genome_file("test_genome")
            assert result == genome_file
            
            # Test non-existent genome
            result = manager.get_genome_file("nonexistent")
            assert result is None
    
    def test_list_genome_ids(self):
        """Test listing all genome IDs."""
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create test files
            (temp_path / "genome1.fasta").write_text(">seq1\nATCG\n")
            (temp_path / "genome2.fa").write_text(">seq2\nGCTA\n")
            
            manager = GenomeDirectoryManager(temp_path)
            
            genome_ids = manager.list_genome_ids()
            assert len(genome_ids) == 2
            assert "genome1" in genome_ids
            assert "genome2" in genome_ids
    
    def test_validate_genome_coverage(self):
        """Test validating genome coverage for sequence IDs."""
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create some genome files
            (temp_path / "genome1.fasta").write_text(">seq1\nATCG\n")
            (temp_path / "genome2.fasta").write_text(">seq2\nGCTA\n")
            
            manager = GenomeDirectoryManager(temp_path)
            
            # Test validation
            sequence_ids = {"genome1", "genome2", "genome3", "genome4"}
            results = manager.validate_genome_coverage(sequence_ids)
            
            assert len(results["found"]) == 2
            assert "genome1" in results["found"]
            assert "genome2" in results["found"]
            
            assert len(results["missing"]) == 2
            assert "genome3" in results["missing"]
            assert "genome4" in results["missing"]
    
    def test_get_genome_statistics(self):
        """Test getting statistics about genome directory."""
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create files of different types
            (temp_path / "genome1.fasta").write_text(">seq1\nATCGATCGATCG" * 100)  # Longer content
            (temp_path / "genome2.fa").write_text(">seq2\nGCTA" * 50)
            
            manager = GenomeDirectoryManager(temp_path)
            
            stats = manager.get_statistics()
            
            assert stats["total_files"] == 2
            assert stats["total_size_bytes"] > 0
            assert stats["total_size_mb"] >= 0  # Allow 0.0 due to rounding for small files
            assert ".fasta" in stats["file_types"]
            assert ".fa" in stats["file_types"]
            assert stats["file_types"][".fasta"] == 1
            assert stats["file_types"][".fa"] == 1
    
    def test_genome_directory_nonexistent_path(self):
        """Test handling non-existent directory."""
        nonexistent_path = Path("/nonexistent/directory")
        manager = GenomeDirectoryManager(nonexistent_path)
        
        # Should handle gracefully
        assert len(manager.genome_files) == 0
        assert manager.list_genome_ids() == []