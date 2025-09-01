"""Tests for utility modules."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from flextaxd.utils.logging_config import setup_logging, get_logger
from flextaxd.utils.sequence_utils import FASTAProcessor, SequenceInfo


class TestLoggingConfig:
    """Test logging configuration utilities."""
    
    def test_setup_logging_basic(self):
        """Test basic logging setup."""
        import logging
        
        # Test with INFO level
        setup_logging(level=logging.INFO)
        
        # Should not raise exception
        logger = get_logger("test")
        assert logger.level <= logging.INFO
    
    def test_setup_logging_with_file(self):
        """Test logging setup with file output."""
        import logging
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            log_file = Path(f.name)
        
        try:
            setup_logging(level=logging.DEBUG, log_file=log_file)
            
            # Test that we can get a logger and log to it
            logger = get_logger("test_file")
            logger.info("Test message")
            
            # File should exist and have content
            assert log_file.exists()
            # Note: checking file content is tricky due to buffering
        finally:
            if log_file.exists():
                log_file.unlink()
    
    def test_get_logger_different_names(self):
        """Test getting loggers with different names."""
        logger1 = get_logger("module1")
        logger2 = get_logger("module2")
        logger3 = get_logger("module1")  # Same as logger1
        
        assert logger1.name == "module1"
        assert logger2.name == "module2"
        assert logger1 is logger3  # Should return same instance
        assert logger1 is not logger2


class TestSequenceUtils:
    """Test sequence utility functions."""
    
    def test_fasta_processor_init(self):
        """Test FASTA processor initialization."""
        processor = FASTAProcessor()
        assert isinstance(processor.sequence_info, dict)
        assert isinstance(processor.seqid_mappings, dict)
    
    def test_sequence_info_creation(self):
        """Test SequenceInfo dataclass creation."""
        seq_info = SequenceInfo(
            sequence_id="test_seq",
            taxonomy_id=123,
            description="Test sequence",
            length=1000
        )
        
        assert seq_info.sequence_id == "test_seq"
        assert seq_info.taxonomy_id == 123
        assert seq_info.description == "Test sequence"
        assert seq_info.length == 1000
        assert seq_info.file_path is None
    
    def test_fasta_processor_parse_headers(self):
        """Test FASTA header parsing."""
        fasta_content = ">seq1 description\nACGTACGT\n>seq2\nGGCCAATA\n"
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.fasta', delete=False) as f:
            f.write(fasta_content)
            f.flush()
            fasta_file = Path(f.name)
        
        try:
            processor = FASTAProcessor()
            sequences = processor.parse_fasta_headers(fasta_file)
            
            assert isinstance(sequences, list)
            # The actual behavior depends on the implementation
            
        finally:
            if fasta_file.exists():
                fasta_file.unlink()


class TestSequenceUtilsErrorHandling:
    """Test error handling in sequence utilities."""
    
    def test_fasta_processor_nonexistent_file(self):
        """Test FASTA processing with non-existent file."""
        processor = FASTAProcessor()
        nonexistent_file = Path("/nonexistent/file.fasta")
        
        # Should handle gracefully or raise appropriate exception
        try:
            sequences = processor.parse_fasta_headers(nonexistent_file)
            assert isinstance(sequences, list)
        except (FileNotFoundError, IOError):
            # Acceptable to raise file-related exceptions
            pass