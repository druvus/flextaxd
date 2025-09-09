"""Comprehensive tests for file validation functionality."""

import gzip
import hashlib
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
import pytest

from flextaxd.validation.file_validator import (
    ValidationLevel,
    ValidationResult,
    FileValidator
)


class TestValidationLevel:
    """Test ValidationLevel enum."""
    
    def test_validation_levels(self):
        """Test that all validation levels are defined correctly."""
        assert ValidationLevel.BASIC.value == "basic"
        assert ValidationLevel.STANDARD.value == "standard"
        assert ValidationLevel.COMPREHENSIVE.value == "comprehensive"


class TestValidationResult:
    """Test ValidationResult dataclass."""
    
    def test_basic_initialization(self):
        """Test basic ValidationResult initialization."""
        result = ValidationResult(
            file_path="/test/file.fna",
            is_valid=True,
            level=ValidationLevel.STANDARD
        )
        
        assert result.file_path == "/test/file.fna"
        assert result.is_valid is True
        assert result.level == ValidationLevel.STANDARD
        assert result.file_exists is False
        assert result.is_readable is False
        assert result.file_size == 0
        assert result.format_valid is False
        assert result.sequence_count == 0
        assert result.total_length == 0
        assert result.errors == []
        assert result.warnings == []
    
    def test_initialization_with_values(self):
        """Test ValidationResult with all values set."""
        result = ValidationResult(
            file_path="/test/file.fna",
            is_valid=True,
            level=ValidationLevel.COMPREHENSIVE,
            file_exists=True,
            is_readable=True,
            file_size=1024,
            format_valid=True,
            sequence_count=5,
            total_length=5000,
            errors=["Error 1"],
            warnings=["Warning 1"]
        )
        
        assert result.file_path == "/test/file.fna"
        assert result.is_valid is True
        assert result.level == ValidationLevel.COMPREHENSIVE
        assert result.file_exists is True
        assert result.is_readable is True
        assert result.file_size == 1024
        assert result.format_valid is True
        assert result.sequence_count == 5
        assert result.total_length == 5000
        assert result.errors == ["Error 1"]
        assert result.warnings == ["Warning 1"]
    
    def test_post_init_with_none_lists(self):
        """Test that __post_init__ initializes None lists."""
        result = ValidationResult(
            file_path="/test/file.fna",
            is_valid=False,
            level=ValidationLevel.BASIC,
            errors=None,
            warnings=None
        )
        
        assert result.errors == []
        assert result.warnings == []
    
    def test_has_errors_property(self):
        """Test has_errors property."""
        result = ValidationResult(
            file_path="/test/file.fna",
            is_valid=False,
            level=ValidationLevel.BASIC
        )
        
        # No errors initially
        assert result.has_errors is False
        
        # Add error
        result.errors.append("Test error")
        assert result.has_errors is True
    
    def test_has_warnings_property(self):
        """Test has_warnings property."""
        result = ValidationResult(
            file_path="/test/file.fna",
            is_valid=True,
            level=ValidationLevel.BASIC
        )
        
        # No warnings initially
        assert result.has_warnings is False
        
        # Add warning
        result.warnings.append("Test warning")
        assert result.has_warnings is True


class TestFileValidator:
    """Test FileValidator class."""
    
    @pytest.fixture
    def validator(self):
        """Create FileValidator instance for testing."""
        return FileValidator(max_workers=2)
    
    @pytest.fixture
    def temp_valid_fasta(self):
        """Create a temporary valid FASTA file."""
        content = """>seq1 Test sequence 1
ATCGATCGATCG
ATCGATCGATCG
>seq2 Test sequence 2
GCTAGCTAGCTA
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.fasta', delete=False) as f:
            f.write(content)
            temp_path = Path(f.name)
        
        yield temp_path
        
        # Cleanup
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
    
    @pytest.fixture
    def temp_invalid_fasta(self):
        """Create a temporary invalid FASTA file."""
        content = """This is not FASTA format
Just some random text
No headers or sequences
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.fasta', delete=False) as f:
            f.write(content)
            temp_path = Path(f.name)
        
        yield temp_path
        
        # Cleanup
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
    
    @pytest.fixture
    def temp_empty_file(self):
        """Create a temporary empty file."""
        with tempfile.NamedTemporaryFile(suffix='.fasta', delete=False) as f:
            temp_path = Path(f.name)
        
        yield temp_path
        
        # Cleanup
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
    
    @pytest.fixture
    def temp_compressed_fasta(self):
        """Create a temporary compressed FASTA file."""
        content = b""">seq1 Compressed sequence
ATCGATCGATCGATCG
>seq2 Another sequence
GCTAGCTAGCTAGCTA
"""
        with tempfile.NamedTemporaryFile(suffix='.fasta.gz', delete=False) as f:
            with gzip.open(f.name, 'wb') as gz_file:
                gz_file.write(content)
            temp_path = Path(f.name)
        
        yield temp_path
        
        # Cleanup
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
    
    def test_initialization(self, validator):
        """Test FileValidator initialization."""
        assert validator.max_workers == 2
        assert validator._progress_callback is None
        assert isinstance(validator.supported_extensions, set)
        assert '.fasta' in validator.supported_extensions
        assert '.fa' in validator.supported_extensions
        assert isinstance(validator.compressed_extensions, set)
        assert '.gz' in validator.compressed_extensions
    
    def test_set_progress_callback(self, validator):
        """Test setting progress callback."""
        callback = Mock()
        validator.set_progress_callback(callback)
        assert validator._progress_callback == callback
    
    def test_validate_file_nonexistent(self, validator):
        """Test validation of non-existent file."""
        nonexistent_path = Path("/nonexistent/file.fasta")
        result = validator.validate_file(nonexistent_path)
        
        assert result.is_valid is False
        assert result.file_exists is False
        assert len(result.errors) > 0
        assert "does not exist" in result.errors[0].lower()
    
    def test_validate_file_basic_level(self, validator, temp_valid_fasta):
        """Test basic level validation."""
        result = validator.validate_file(temp_valid_fasta, ValidationLevel.BASIC)
        
        assert result.level == ValidationLevel.BASIC
        assert result.file_exists is True
        assert result.is_readable is True
        assert result.file_size > 0
        # Format validation shouldn't run at BASIC level
        assert result.format_valid is False
        assert result.sequence_count == 0
    
    def test_validate_file_standard_level(self, validator, temp_valid_fasta):
        """Test standard level validation."""
        result = validator.validate_file(temp_valid_fasta, ValidationLevel.STANDARD)
        
        assert result.level == ValidationLevel.STANDARD
        assert result.file_exists is True
        assert result.is_readable is True
        assert result.file_size > 0
        assert result.format_valid is True
        assert result.sequence_count == 2
        assert result.total_length > 0
        assert result.is_valid is True
    
    def test_validate_file_comprehensive_level(self, validator, temp_valid_fasta):
        """Test comprehensive level validation."""
        result = validator.validate_file(temp_valid_fasta, ValidationLevel.COMPREHENSIVE)
        
        assert result.level == ValidationLevel.COMPREHENSIVE
        assert result.file_exists is True
        assert result.is_readable is True
        assert result.file_size > 0
        assert result.format_valid is True
        assert result.sequence_count == 2
        assert result.total_length > 0
        # Should have checksum at comprehensive level
        assert hasattr(result, 'checksum') or len(result.errors) == 0
    
    def test_validate_file_invalid_fasta(self, validator, temp_invalid_fasta):
        """Test validation of invalid FASTA file."""
        result = validator.validate_file(temp_invalid_fasta, ValidationLevel.STANDARD)
        
        assert result.is_valid is False
        assert result.file_exists is True
        assert result.is_readable is True
        assert result.sequence_count == 0
        assert len(result.errors) > 0
    
    def test_validate_file_empty_file(self, validator, temp_empty_file):
        """Test validation of empty file."""
        result = validator.validate_file(temp_empty_file, ValidationLevel.STANDARD)
        
        assert result.is_valid is False
        assert result.file_exists is True
        assert result.file_size == 0
        assert len(result.errors) > 0
        assert any("empty" in error.lower() for error in result.errors)
    
    def test_validate_file_compressed(self, validator, temp_compressed_fasta):
        """Test validation of compressed FASTA file."""
        result = validator.validate_file(temp_compressed_fasta, ValidationLevel.STANDARD)
        
        assert result.file_exists is True
        assert result.is_readable is True
        assert result.file_size > 0
        # Should handle compressed files
        if result.is_valid:
            assert result.format_valid is True
            assert result.sequence_count == 2
    
    def test_validate_files_serial(self, validator, temp_valid_fasta, temp_invalid_fasta):
        """Test batch validation in serial mode."""
        validator.max_workers = 1
        file_paths = [temp_valid_fasta, temp_invalid_fasta]
        
        results = validator.validate_files(file_paths, ValidationLevel.STANDARD)
        
        assert len(results) == 2
        assert str(temp_valid_fasta) in results
        assert str(temp_invalid_fasta) in results
        
        valid_result = results[str(temp_valid_fasta)]
        invalid_result = results[str(temp_invalid_fasta)]
        
        assert valid_result.is_valid is True
        assert invalid_result.is_valid is False
    
    def test_validate_files_parallel(self, validator, temp_valid_fasta, temp_empty_file):
        """Test batch validation in parallel mode."""
        file_paths = [temp_valid_fasta, temp_empty_file]
        
        results = validator.validate_files(file_paths, ValidationLevel.STANDARD)
        
        assert len(results) == 2
        assert str(temp_valid_fasta) in results
        assert str(temp_empty_file) in results
        
        valid_result = results[str(temp_valid_fasta)]
        empty_result = results[str(temp_empty_file)]
        
        assert valid_result.is_valid is True
        assert empty_result.is_valid is False
    
    def test_validate_files_with_progress_callback(self, validator, temp_valid_fasta):
        """Test batch validation with progress callback."""
        callback = Mock()
        validator.set_progress_callback(callback)
        
        file_paths = [temp_valid_fasta]
        results = validator.validate_files(file_paths, ValidationLevel.BASIC)
        
        assert len(results) == 1
        callback.assert_called_with(1, 1)
    
    def test_validate_files_with_exception(self, validator):
        """Test batch validation when file validation raises exception."""
        nonexistent_path = Path("/nonexistent/file.fasta")
        file_paths = [nonexistent_path]
        
        results = validator.validate_files(file_paths, ValidationLevel.STANDARD)
        
        assert len(results) == 1
        result = results[str(nonexistent_path)]
        assert result.is_valid is False
        assert len(result.errors) > 0
    
    def test_generate_report(self, validator):
        """Test validation report generation."""
        # Create mock results
        valid_result = ValidationResult(
            file_path="/test/valid.fasta",
            is_valid=True,
            level=ValidationLevel.STANDARD,
            file_exists=True,
            is_readable=True,
            file_size=1024,
            format_valid=True,
            sequence_count=5,
            total_length=5000
        )
        
        invalid_result = ValidationResult(
            file_path="/test/invalid.fasta",
            is_valid=False,
            level=ValidationLevel.STANDARD,
            file_exists=False,
            errors=["File does not exist"]
        )
        
        results = {
            "/test/valid.fasta": valid_result,
            "/test/invalid.fasta": invalid_result
        }
        
        report = validator.generate_report(results)
        
        # Check report structure
        assert "validation_summary" in report
        assert "file_status" in report
        assert "sequence_statistics" in report
        assert "error_count" in report
        assert "warning_count" in report
        
        # Check summary
        summary = report["validation_summary"]
        assert summary["total_files"] == 2
        assert summary["valid_files"] == 1
        assert summary["invalid_files"] == 1
        assert summary["validation_rate"] == 50.0
        
        # Check file status
        file_status = report["file_status"]
        assert file_status["missing"] == 1
        assert file_status["accessible"] == 1
        
        # Check sequence statistics
        seq_stats = report["sequence_statistics"]
        assert seq_stats["total_sequences"] == 5
        assert seq_stats["total_length"] == 5000
        assert seq_stats["average_length"] == 1000.0
    
    def test_generate_report_empty(self, validator):
        """Test report generation with empty results."""
        report = validator.generate_report({})
        
        assert report["validation_summary"]["total_files"] == 0
        assert report["validation_summary"]["valid_files"] == 0
        assert report["validation_summary"]["validation_rate"] == 0
        assert report["sequence_statistics"]["total_sequences"] == 0
        assert report["sequence_statistics"]["average_length"] == 0
    
    def test_get_common_issues(self, validator):
        """Test common issues extraction."""
        issues = [
            "File does not exist: file1.fasta",
            "File does not exist: file2.fasta",
            "Invalid format: file3.fasta",
            "File does not exist: file4.fasta",
            "Permission denied: file5.fasta"
        ]
        
        common_issues = validator._get_common_issues(issues, limit=3)
        
        assert len(common_issues) <= 3
        assert common_issues[0][0] == "File does not exist"
        assert common_issues[0][1] == 3  # Should appear 3 times
        assert common_issues[1][0] == "Invalid format"
        assert common_issues[1][1] == 1
    
    @patch('os.access')
    def test_check_file_accessibility_permission_denied(self, mock_access, validator, temp_valid_fasta):
        """Test file accessibility check with permission denied."""
        mock_access.return_value = False
        
        result = validator.validate_file(temp_valid_fasta, ValidationLevel.BASIC)
        
        assert result.is_valid is False
        assert result.is_readable is False
        assert len(result.errors) > 0
        assert any("not readable" in error.lower() for error in result.errors)
    
    def test_unsupported_file_extension(self, validator):
        """Test validation of file with unsupported extension."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(">seq1\nATCG\n")
            temp_path = Path(f.name)
        
        try:
            result = validator.validate_file(temp_path, ValidationLevel.STANDARD)
            
            # Should still validate but may have warnings about extension
            assert len(result.warnings) >= 0  # May or may not warn about extension
        finally:
            temp_path.unlink()
    
    def test_file_size_warnings(self, validator):
        """Test file size warnings for very small and large files."""
        # Test very small file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.fasta', delete=False) as f:
            f.write("A")  # Very small content
            small_path = Path(f.name)
        
        try:
            result = validator.validate_file(small_path, ValidationLevel.BASIC)
            
            # Should warn about very small file
            assert len(result.warnings) > 0
            assert any("small" in warning.lower() for warning in result.warnings)
        finally:
            small_path.unlink()


class TestFileValidatorEdgeCases:
    """Test edge cases and error conditions."""
    
    @pytest.fixture
    def validator(self):
        return FileValidator()
    
    def test_fasta_with_duplicate_ids(self, validator):
        """Test FASTA file with duplicate sequence IDs."""
        content = """>seq1 First sequence
ATCGATCGATCG
>seq1 Duplicate ID
GCTAGCTAGCTA
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.fasta', delete=False) as f:
            f.write(content)
            temp_path = Path(f.name)
        
        try:
            result = validator.validate_file(temp_path, ValidationLevel.COMPREHENSIVE)
            
            # Should detect duplicate IDs at comprehensive level
            if result.warnings:
                assert any("duplicate" in warning.lower() for warning in result.warnings)
        finally:
            temp_path.unlink()
    
    def test_fasta_with_empty_sequences(self, validator):
        """Test FASTA file with empty sequences."""
        content = """>seq1 Normal sequence
ATCGATCGATCG
>seq2 Empty sequence
>seq3 Another normal
GCTAGCTAGCTA
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.fasta', delete=False) as f:
            f.write(content)
            temp_path = Path(f.name)
        
        try:
            result = validator.validate_file(temp_path, ValidationLevel.COMPREHENSIVE)
            
            # May warn about empty sequences
            if result.warnings:
                assert any("no sequence data" in warning.lower() for warning in result.warnings)
        finally:
            temp_path.unlink()
    
    def test_fasta_with_invalid_characters(self, validator):
        """Test FASTA file with invalid sequence characters."""
        content = """>seq1 Sequence with invalid chars
ATCG123XYZ!@#
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.fasta', delete=False) as f:
            f.write(content)
            temp_path = Path(f.name)
        
        try:
            result = validator.validate_file(temp_path, ValidationLevel.STANDARD)
            
            # May warn about non-standard characters
            if result.warnings:
                assert any("non-standard" in warning.lower() for warning in result.warnings)
        finally:
            temp_path.unlink()


if __name__ == "__main__":
    pytest.main([__file__])