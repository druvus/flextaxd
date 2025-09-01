"""Tests for genome file processing integration."""

import tempfile
from pathlib import Path

import pytest

from flextaxd.utils.sequence_utils import (
    FASTAProcessor, SeqIDMappingManager, GenomeDirectoryManager, 
    SequenceInfo, SeqIDMapping
)
from flextaxd.core.models import GenomeInfo
from flextaxd.cli.commands.create import CreateCommand


class TestGenomeIntegration:
    """Test genome integration functionality."""
    
    def test_fasta_processor_parse_headers(self, tmp_path: Path):
        """Test FASTA header parsing."""
        # Create test FASTA file
        fasta_content = """>seq1 description for sequence 1
ATCGATCGATCG
>seq2 description for sequence 2  
GCTAGCTAGCTA
>seq3
AAAAAAAAAA"""
        
        fasta_file = tmp_path / "test.fasta"
        fasta_file.write_text(fasta_content)
        
        processor = FASTAProcessor()
        sequences = processor.parse_fasta_headers(fasta_file)
        
        assert len(sequences) == 3
        
        assert sequences[0].sequence_id == "seq1"
        assert sequences[0].description == "description for sequence 1"
        
        assert sequences[1].sequence_id == "seq2"
        assert sequences[1].description == "description for sequence 2"
        
        assert sequences[2].sequence_id == "seq3"
        assert sequences[2].description == ""
    
    def test_fasta_processor_gtdb_taxonomy_extraction(self):
        """Test GTDB taxonomy extraction from headers."""
        processor = FASTAProcessor()
        
        header1 = ">GB_GCA_000001405.38 d__Bacteria;p__Proteobacteria;c__Gammaproteobacteria"
        taxonomy1 = processor.extract_gtdb_taxonomy_from_header(header1)
        assert taxonomy1 == "d__Bacteria;p__Proteobacteria;c__Gammaproteobacteria"
        
        header2 = ">RS_GCF_000005825.2 d__Bacteria;p__Firmicutes;c__Bacilli"
        taxonomy2 = processor.extract_gtdb_taxonomy_from_header(header2)
        assert taxonomy2 == "d__Bacteria;p__Firmicutes;c__Bacilli"
        
        header3 = ">normal_header without taxonomy"
        taxonomy3 = processor.extract_gtdb_taxonomy_from_header(header3)
        assert taxonomy3 is None
    
    def test_fasta_processor_silva_taxonomy_extraction(self):
        """Test SILVA taxonomy extraction from headers."""
        processor = FASTAProcessor()
        
        header1 = ">AACY020068177.1.1441.1464 Bacteria;Actinobacteria;Actinobacteria;Acidimicrobiia"
        result1 = processor.extract_silva_taxonomy_from_header(header1)
        assert result1 == ("AACY020068177.1.1441.1464", "Bacteria;Actinobacteria;Actinobacteria;Acidimicrobiia")
        
        header2 = ">AB000001 Bacteria;Proteobacteria some other info"
        result2 = processor.extract_silva_taxonomy_from_header(header2)
        assert result2 == ("AB000001", "Bacteria;Proteobacteria")
        
        header3 = ">no_taxonomy"
        result3 = processor.extract_silva_taxonomy_from_header(header3)
        assert result3 is None
    
    def test_fasta_processor_split_sequences(self, tmp_path: Path):
        """Test FASTA file splitting."""
        # Create test multi-sequence FASTA
        fasta_content = """>seq1
ATCGATCGATCG
GCTAGCTAGCTA
>seq2
AAAAAAAAAA
TTTTTTTTTT
>seq3
CCCCCCCCCC"""
        
        input_file = tmp_path / "multi.fasta"
        input_file.write_text(fasta_content)
        
        output_dir = tmp_path / "split"
        
        processor = FASTAProcessor()
        created_files = processor.split_fasta_by_sequence(input_file, output_dir, max_sequences_per_file=1)
        
        assert len(created_files) == 3
        
        # Verify individual files exist and have correct content
        seq1_file = output_dir / "seq1.fasta"
        assert seq1_file.exists()
        seq1_content = seq1_file.read_text()
        assert ">seq1" in seq1_content
        assert "ATCGATCGATCG" in seq1_content
        
        seq2_file = output_dir / "seq2.fasta"
        assert seq2_file.exists()
        seq2_content = seq2_file.read_text()
        assert ">seq2" in seq2_content
        assert "AAAAAAAAAA" in seq2_content
    
    def test_fasta_processor_rna_to_dna_conversion(self, tmp_path: Path):
        """Test RNA to DNA conversion."""
        # Create RNA FASTA file
        rna_content = """>seq1
AUCGAUCGAUCG
GCUAGCUAGCUA
>seq2
UUUUUUUUUU"""
        
        rna_file = tmp_path / "rna.fasta"
        rna_file.write_text(rna_content)
        
        processor = FASTAProcessor()
        processor.convert_rna_to_dna(rna_file)
        
        # Verify conversion
        dna_content = rna_file.read_text()
        assert "U" not in dna_content
        assert "u" not in dna_content
        assert "ATCGATCGATCG" in dna_content
        assert "GCTAGCTAGCTA" in dna_content
        assert "TTTTTTTTTT" in dna_content
    
    def test_seqid_mapping_manager(self, tmp_path: Path):
        """Test sequence ID mapping management."""
        # Create mapping file
        mapping_content = """seq1\t123
seq2\t456
seq3\t789"""
        
        mapping_file = tmp_path / "mapping.txt"
        mapping_file.write_text(mapping_content)
        
        manager = SeqIDMappingManager()
        manager.load_seqid_mapping_file(mapping_file)
        
        assert len(manager.mappings) == 3
        assert manager.get_mapping("seq1") == 123
        assert manager.get_mapping("seq2") == 456
        assert manager.get_mapping("seq3") == 789
        assert manager.get_mapping("nonexistent") is None
        
        # Test statistics
        stats = manager.get_statistics()
        assert stats["total_mappings"] == 3
        assert stats["unique_taxonomy_ids"] == 3
    
    def test_seqid_mapping_manager_ncbi_format(self, tmp_path: Path):
        """Test NCBI accession2taxid format parsing."""
        # Create NCBI format mapping file
        mapping_content = """accession\taccession.version\ttaxid\tgi
AB000001\tAB000001.1\t123\t456
AB000002\tAB000002.1\t789\t101112"""
        
        mapping_file = tmp_path / "ncbi_mapping.txt"
        mapping_file.write_text(mapping_content)
        
        manager = SeqIDMappingManager()
        manager.load_seqid_mapping_file(mapping_file)
        
        assert len(manager.mappings) == 2
        assert manager.get_mapping("AB000001") == 123
        assert manager.get_mapping("AB000002") == 789
    
    def test_seqid_mapping_export(self, tmp_path: Path):
        """Test seqid2taxid mapping export."""
        manager = SeqIDMappingManager()
        
        # Add some mappings manually
        manager.mappings["seq1"] = SeqIDMapping("seq1", 123, "test")
        manager.mappings["seq2"] = SeqIDMapping("seq2", 456, "test")
        manager.mappings["seq3"] = SeqIDMapping("seq3", 789, "test")
        
        output_file = tmp_path / "exported_mapping.txt"
        manager.export_seqid2taxid_map(output_file)
        
        # Verify export
        content = output_file.read_text()
        lines = [line for line in content.split('\n') if line.strip()]
        
        assert len(lines) == 3
        assert "seq1\t123" in content
        assert "seq2\t456" in content
        assert "seq3\t789" in content
    
    def test_genome_directory_manager(self, tmp_path: Path):
        """Test genome directory management."""
        # Create mock genome directory structure
        genomes_dir = tmp_path / "genomes"
        genomes_dir.mkdir()
        
        # Create some genome files
        (genomes_dir / "genome1.fasta").write_text(">seq1\nATCG")
        (genomes_dir / "genome2.fa").write_text(">seq2\nGCTA")
        (genomes_dir / "genome3.fna").write_text(">seq3\nAAAA")
        (genomes_dir / "genome4.txt").write_text("not a genome file")  # Should be ignored
        
        # Create subdirectory with more genomes
        subdir = genomes_dir / "subdir"
        subdir.mkdir()
        (subdir / "genome5.fasta.gz").write_text(">seq5\nTTTT")
        
        manager = GenomeDirectoryManager(genomes_dir)
        
        # Test file discovery
        genome_ids = manager.list_genome_ids()
        assert "genome1" in genome_ids
        assert "genome2" in genome_ids
        assert "genome3" in genome_ids
        assert "genome5.fasta" in genome_ids  # .gz extension stripped
        assert "genome4" not in genome_ids  # .txt files ignored
        
        # Test file retrieval
        genome1_path = manager.get_genome_file("genome1")
        assert genome1_path is not None
        assert genome1_path.name == "genome1.fasta"
        
        nonexistent_path = manager.get_genome_file("nonexistent")
        assert nonexistent_path is None
        
        # Test statistics
        stats = manager.get_statistics()
        assert stats["total_files"] == 4  # 4 valid genome files
        assert stats["total_size_bytes"] > 0
    
    def test_genome_directory_coverage_validation(self, tmp_path: Path):
        """Test genome coverage validation."""
        # Create genome directory
        genomes_dir = tmp_path / "genomes"
        genomes_dir.mkdir()
        
        (genomes_dir / "seq1.fasta").write_text(">seq1\nATCG")
        (genomes_dir / "seq2.fasta").write_text(">seq2\nGCTA")
        
        manager = GenomeDirectoryManager(genomes_dir)
        
        # Test coverage validation
        sequence_ids = {"seq1", "seq2", "seq3", "seq4"}
        coverage = manager.validate_genome_coverage(sequence_ids)
        
        assert "seq1" in coverage["found"]
        assert "seq2" in coverage["found"]
        assert "seq3" in coverage["missing"]
        assert "seq4" in coverage["missing"]
        
        assert len(coverage["found"]) == 2
        assert len(coverage["missing"]) == 2
    
    def test_enhanced_genome_info_model(self):
        """Test the enhanced GenomeInfo model."""
        # Test basic genome info
        genome1 = GenomeInfo(
            genome_id="test_genome",
            tax_id=123,
            sequence_type="16S",
            source="SILVA"
        )
        
        assert genome1.genome_id == "test_genome"
        assert genome1.tax_id == 123
        assert genome1.sequence_type == "16S"
        assert genome1.source == "SILVA"
        assert not genome1.has_sequence_file  # No file path provided
        assert genome1.file_size is None
        
        # Test validation
        issues = genome1.validate()
        assert len(issues) == 0  # Should be valid
        
        # Test invalid genome info
        with pytest.raises(ValueError):
            GenomeInfo(genome_id="", tax_id=123)  # Empty ID should fail
        
        with pytest.raises(ValueError):
            GenomeInfo(genome_id="test", tax_id=-1)  # Negative tax_id should fail
    
    def test_genome_info_with_file(self, tmp_path: Path):
        """Test GenomeInfo with actual sequence files."""
        # Create test sequence file
        seq_file = tmp_path / "test_sequence.fasta"
        seq_content = ">seq1\nATCGATCGATCG\n>seq2\nGCTAGCTAGCTA"
        seq_file.write_text(seq_content)
        
        genome = GenomeInfo(
            genome_id="test_genome",
            tax_id=123,
            file_path=str(seq_file),
            sequence_type="genome"
        )
        
        assert genome.has_sequence_file
        assert genome.file_size == len(seq_content)
        
        # Test validation with existing file
        issues = genome.validate()
        assert len(issues) == 0
        
        # Test with non-existent file
        genome_bad = GenomeInfo(
            genome_id="bad_genome",
            tax_id=123,
            file_path="/nonexistent/path/file.fasta"
        )
        
        assert not genome_bad.has_sequence_file
        issues = genome_bad.validate()
        assert len(issues) == 1
        assert "does not exist" in issues[0]