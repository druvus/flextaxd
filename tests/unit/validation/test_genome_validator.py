"""Comprehensive tests for genome validation functionality."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
import pytest

from flextaxd.validation.genome_validator import (
    GenomeValidationResult,
    GenomeValidator
)
from flextaxd.validation.file_validator import ValidationResult, ValidationLevel
from flextaxd.core.models import GenomeInfo, TaxonomyTree, TaxonomyNode
from flextaxd.database.repository import TaxonomyRepository
from flextaxd.core.exceptions import ValidationError


class TestGenomeValidationResult:
    """Test GenomeValidationResult dataclass."""
    
    def test_basic_initialization(self):
        """Test basic GenomeValidationResult initialization."""
        result = GenomeValidationResult(genome_id="test_genome")
        
        assert result.genome_id == "test_genome"
        assert result.file_validation is None
        assert result.database_consistent is True
        assert result.metadata_complete is True
        assert result.size_matches is True
        assert result.taxonomy_linked is True
        assert result.issues == []
    
    def test_initialization_with_values(self):
        """Test initialization with explicit values."""
        file_validation = ValidationResult(
            file_path="/test/genome.fna",
            is_valid=True,
            level=ValidationLevel.STANDARD
        )
        
        result = GenomeValidationResult(
            genome_id="test_genome",
            file_validation=file_validation,
            database_consistent=False,
            metadata_complete=False,
            size_matches=False,
            taxonomy_linked=False,
            issues=["Test issue"]
        )
        
        assert result.genome_id == "test_genome"
        assert result.file_validation == file_validation
        assert result.database_consistent is False
        assert result.metadata_complete is False
        assert result.size_matches is False
        assert result.taxonomy_linked is False
        assert result.issues == ["Test issue"]
    
    def test_post_init_none_issues(self):
        """Test __post_init__ handles None issues."""
        result = GenomeValidationResult(genome_id="test", issues=None)
        assert result.issues == []
    
    def test_is_valid_all_good(self):
        """Test is_valid property when everything is valid."""
        file_validation = ValidationResult(
            file_path="/test/genome.fna",
            is_valid=True,
            level=ValidationLevel.STANDARD
        )
        
        result = GenomeValidationResult(
            genome_id="test_genome",
            file_validation=file_validation,
            database_consistent=True,
            metadata_complete=True,
            taxonomy_linked=True
        )
        
        assert result.is_valid is True
    
    def test_is_valid_file_invalid(self):
        """Test is_valid when file validation fails."""
        file_validation = ValidationResult(
            file_path="/test/genome.fna",
            is_valid=False,
            level=ValidationLevel.STANDARD
        )
        
        result = GenomeValidationResult(
            genome_id="test_genome",
            file_validation=file_validation
        )
        
        assert result.is_valid is False
    
    def test_is_valid_database_inconsistent(self):
        """Test is_valid when database is inconsistent."""
        result = GenomeValidationResult(
            genome_id="test_genome",
            database_consistent=False
        )
        
        assert result.is_valid is False
    
    def test_is_valid_no_file_validation(self):
        """Test is_valid with no file validation (metadata only)."""
        result = GenomeValidationResult(
            genome_id="test_genome",
            file_validation=None,
            database_consistent=True,
            metadata_complete=True,
            taxonomy_linked=True
        )
        
        assert result.is_valid is True


class TestGenomeValidator:
    """Test GenomeValidator class."""
    
    @pytest.fixture
    def mock_repository(self):
        """Create mock repository."""
        repo = Mock(spec=TaxonomyRepository)
        # Add methods that may not be in the spec but are needed for testing
        repo.get_all_genomes = Mock(return_value=[])
        return repo
    
    @pytest.fixture
    def validator(self, mock_repository):
        """Create GenomeValidator with mock repository."""
        return GenomeValidator(mock_repository, max_workers=2)
    
    @pytest.fixture
    def sample_tree(self):
        """Create sample taxonomy tree."""
        tree = TaxonomyTree()
        root = TaxonomyNode(1, "root", "root", None)
        bacteria = TaxonomyNode(2, "Bacteria", "superkingdom", 1)
        ecoli = TaxonomyNode(562, "Escherichia coli", "species", 2)
        
        tree.add_node(root)
        tree.add_node(bacteria)
        tree.add_node(ecoli)
        
        return tree
    
    @pytest.fixture
    def temp_valid_fasta(self):
        """Create temporary valid FASTA file."""
        content = """>contig1
ATCGATCGATCGATCGATCGATCGATCGATCGATCGATCG
>contig2
GCTAGCTAGCTAGCTAGCTAGCTAGCTAGCTAGCTAGCTA
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
    
    def test_initialization(self, validator, mock_repository):
        """Test GenomeValidator initialization."""
        assert validator.repository == mock_repository
        assert validator.file_validator is not None
        assert validator.file_validator.max_workers == 2
        assert validator.logger is not None
    
    def test_validate_genome_with_file(self, validator, mock_repository, sample_tree, temp_valid_fasta):
        """Test genome validation with file path."""
        mock_repository.load_tree.return_value = sample_tree
        
        genome = GenomeInfo(
            genome_id="test_genome",
            tax_id=562,
            file_path=str(temp_valid_fasta),
            sequence_length=80  # Should match FASTA content
        )
        
        result = validator.validate_genome(genome, ValidationLevel.STANDARD)
        
        assert result.genome_id == "test_genome"
        assert result.file_validation is not None
        assert result.file_validation.is_valid is True
        assert result.taxonomy_linked is True
        assert result.size_matches is True
        assert result.metadata_complete is True
        assert result.is_valid is True
    
    def test_validate_genome_without_file(self, validator, mock_repository, sample_tree):
        """Test genome validation without file path."""
        mock_repository.load_tree.return_value = sample_tree
        
        genome = GenomeInfo(
            genome_id="test_genome",
            tax_id=562,
            file_path=None  # No file
        )
        
        result = validator.validate_genome(genome, ValidationLevel.STANDARD)
        
        assert result.genome_id == "test_genome"
        assert result.file_validation is None
        assert result.taxonomy_linked is True
        assert result.metadata_complete is True
        assert result.is_valid is True
    
    def test_validate_genome_size_mismatch(self, validator, mock_repository, sample_tree, temp_valid_fasta):
        """Test genome validation with size mismatch."""
        mock_repository.load_tree.return_value = sample_tree
        
        genome = GenomeInfo(
            genome_id="test_genome",
            tax_id=562,
            file_path=str(temp_valid_fasta),
            sequence_length=10000  # Much larger than actual file (80 chars) to exceed tolerance
        )
        
        result = validator.validate_genome(genome, ValidationLevel.STANDARD)
        
        assert result.genome_id == "test_genome"
        assert result.size_matches is False
        assert len(result.issues) > 0
        assert any("size mismatch" in issue.lower() for issue in result.issues)
        # Note: size mismatches don't make genome invalid overall in current implementation
    
    def test_validate_genome_missing_taxonomy(self, validator, mock_repository, sample_tree):
        """Test genome validation with missing taxonomy link."""
        mock_repository.load_tree.return_value = sample_tree
        
        genome = GenomeInfo(
            genome_id="test_genome",
            tax_id=999,  # Non-existent tax_id
            file_path=None
        )
        
        result = validator.validate_genome(genome, ValidationLevel.STANDARD)
        
        assert result.genome_id == "test_genome"
        assert result.taxonomy_linked is False
        assert len(result.issues) > 0
        assert any("not found in tree" in issue for issue in result.issues)
        assert result.is_valid is False
    
    def test_validate_genome_comprehensive_without_file(self, validator, mock_repository, sample_tree):
        """Test comprehensive validation without file path."""
        mock_repository.load_tree.return_value = sample_tree
        
        genome = GenomeInfo(
            genome_id="test_genome",
            tax_id=562,
            file_path=None
        )
        
        result = validator.validate_genome(genome, ValidationLevel.COMPREHENSIVE)
        
        assert result.genome_id == "test_genome"
        assert len(result.issues) > 0
        assert any("no associated file" in issue.lower() for issue in result.issues)
    
    def test_validate_genome_incomplete_metadata(self, validator, mock_repository, sample_tree):
        """Test genome validation with incomplete metadata."""
        mock_repository.load_tree.return_value = sample_tree
        
        genome = GenomeInfo(
            genome_id="test_genome",  # Valid genome_id
            tax_id=None,  # Missing required tax_id  
            file_path=None,
            sequence_type=None,  # Missing recommended sequence_type
            source=None  # Missing recommended source
        )
        
        result = validator.validate_genome(genome, ValidationLevel.STANDARD)
        
        assert result.metadata_complete is False
        assert len(result.issues) > 0
        assert any("missing required field" in issue.lower() for issue in result.issues)
        assert any("missing recommended field" in issue.lower() for issue in result.issues)
        assert result.is_valid is False
    
    def test_validate_all_genomes(self, validator, mock_repository, sample_tree, temp_valid_fasta):
        """Test validation of all genomes."""
        mock_repository.load_tree.return_value = sample_tree
        
        genomes = [
            GenomeInfo(
                genome_id="genome1",
                tax_id=562,
                file_path=str(temp_valid_fasta),
                sequence_length=80
            ),
            GenomeInfo(
                genome_id="genome2",
                tax_id=562,
                file_path=None  # Metadata only
            )
        ]
        
        mock_repository.get_all_genomes.return_value = genomes
        
        results = validator.validate_all_genomes(ValidationLevel.STANDARD)
        
        assert len(results) == 2
        assert "genome1" in results
        assert "genome2" in results
        
        # First genome should be valid
        assert results["genome1"].is_valid is True
        assert results["genome1"].file_validation is not None
        
        # Second genome should be valid (metadata only)
        assert results["genome2"].is_valid is True
        assert results["genome2"].file_validation is None
    
    def test_validate_all_genomes_with_progress(self, validator, mock_repository, sample_tree):
        """Test validation with progress callback."""
        mock_repository.load_tree.return_value = sample_tree
        mock_repository.get_all_genomes.return_value = []
        
        progress_callback = Mock()
        
        results = validator.validate_all_genomes(
            ValidationLevel.BASIC,
            progress_callback=progress_callback
        )
        
        assert len(results) == 0
        # Progress callback should have been set on file validator
        assert validator.file_validator._progress_callback == progress_callback
    
    @patch('flextaxd.exporters.validation.get_format_requirements')
    def test_validate_genomes_for_export(self, mock_get_requirements, validator, mock_repository):
        """Test genome validation for specific export format."""
        # Mock requirements
        mock_requirement = Mock()
        mock_requirement.name = "genome_count"
        mock_requirement.requirement_type = "genome_count"
        mock_requirement.threshold = 1
        mock_requirement.level = Mock()
        mock_requirement.level.value = "required"
        
        mock_requirements = Mock()
        mock_requirements.requirements = [mock_requirement]
        
        mock_get_requirements.return_value = mock_requirements
        
        # Mock genomes
        genomes = [
            GenomeInfo(genome_id="genome1", tax_id=562, file_path="/test.fna")
        ]
        mock_repository.get_all_genomes.return_value = genomes
        
        result = validator.validate_genomes_for_export("test_format")
        
        assert result["export_format"] == "test_format"
        assert result["total_genomes"] == 1
        assert "requirement_results" in result
        assert "summary" in result
    
    @patch('flextaxd.exporters.validation.get_format_requirements')
    def test_validate_genomes_for_export_unknown_format(self, mock_get_requirements, validator, mock_repository):
        """Test export validation with unknown format."""
        mock_get_requirements.return_value = None
        
        with pytest.raises(ValidationError) as exc_info:
            validator.validate_genomes_for_export("unknown_format")
        
        assert "unknown export format" in str(exc_info.value).lower()
    
    def test_validate_export_requirement_genome_count(self, validator):
        """Test validation of genome count requirement."""
        genomes = [
            GenomeInfo(genome_id="g1", tax_id=1),
            GenomeInfo(genome_id="g2", tax_id=2)
        ]
        
        requirement = Mock()
        requirement.requirement_type = "genome_count"
        requirement.threshold = 1
        requirement.level = Mock()
        requirement.level.value = "required"
        
        result = validator._validate_export_requirement(genomes, requirement)
        
        assert result["status"] == "pass"
        assert result["actual"] == 2
        assert result["required"] == 1
    
    def test_validate_export_requirement_file_paths(self, validator):
        """Test validation of file paths requirement."""
        genomes = [
            GenomeInfo(genome_id="g1", tax_id=1, file_path="/test1.fna"),
            GenomeInfo(genome_id="g2", tax_id=2, file_path=None)  # No file
        ]
        
        requirement = Mock()
        requirement.requirement_type = "file_paths"
        requirement.threshold = 2
        requirement.level = Mock()
        requirement.level.value = "required"
        
        result = validator._validate_export_requirement(genomes, requirement)
        
        assert result["status"] == "fail"
        assert result["actual"] == 1  # Only one has file path
        assert result["required"] == 2
    
    def test_validate_export_requirement_assembly_accessions(self, validator):
        """Test validation of assembly accessions requirement."""
        genomes = [
            GenomeInfo(genome_id="g1", tax_id=1, assembly_accession="GCF_000001"),
            GenomeInfo(genome_id="g2", tax_id=2, assembly_accession=None)
        ]
        
        requirement = Mock()
        requirement.requirement_type = "assembly_accessions"
        requirement.threshold = 1
        requirement.level = Mock()
        requirement.level.value = "recommended"
        
        result = validator._validate_export_requirement(genomes, requirement)
        
        assert result["status"] == "pass"
        assert result["actual"] == 1
        assert result["required"] == 1
    
    def test_validate_export_requirement_unknown(self, validator):
        """Test validation of unknown requirement type."""
        genomes = []
        
        requirement = Mock()
        requirement.requirement_type = "unknown_type"
        
        result = validator._validate_export_requirement(genomes, requirement)
        
        assert result["status"] == "unknown"
        assert "unknown requirement type" in result["message"].lower()
    
    def test_generate_export_validation_summary(self, validator):
        """Test export validation summary generation."""
        results = {
            "req1": {"status": "pass"},
            "req2": {"status": "fail"},
            "req3": {"status": "warn"},
            "req4": {"status": "pass"}
        }
        
        summary = validator._generate_export_validation_summary(results)
        
        assert summary["total_requirements"] == 4
        assert summary["passed"] == 2
        assert summary["failed"] == 1
        assert summary["warnings"] == 1
        assert summary["success_rate"] == 50.0
    
    def test_generate_validation_report(self, validator):
        """Test comprehensive validation report generation."""
        # Create mock validation results
        valid_result = GenomeValidationResult(
            genome_id="valid",
            file_validation=Mock(is_valid=True),
            database_consistent=True,
            metadata_complete=True,
            size_matches=True,
            taxonomy_linked=True,
            issues=[]
        )
        
        invalid_result = GenomeValidationResult(
            genome_id="invalid",
            file_validation=Mock(is_valid=False),
            database_consistent=False,
            metadata_complete=False,
            size_matches=False,
            taxonomy_linked=False,
            issues=["Error 1", "Error 2"]
        )
        
        results = {
            "valid": valid_result,
            "invalid": invalid_result
        }
        
        report = validator.generate_validation_report(results)
        
        # Check report structure
        assert "validation_summary" in report
        assert "file_validation" in report
        assert "consistency_issues" in report
        assert "common_issues" in report
        
        # Check validation summary
        summary = report["validation_summary"]
        assert summary["total_genomes"] == 2
        assert summary["valid_genomes"] == 1
        assert summary["invalid_genomes"] == 1
        assert summary["validation_rate"] == 50.0
        
        # Check file validation
        file_val = report["file_validation"]
        assert file_val["genomes_with_files"] == 2
        assert file_val["valid_files"] == 1
        assert file_val["file_validation_rate"] == 50.0
        
        # Check consistency issues
        consistency = report["consistency_issues"]
        assert consistency["metadata_incomplete"] == 1
        assert consistency["taxonomy_unlinked"] == 1
        assert consistency["size_mismatches"] == 1
    
    def test_generate_validation_report_empty(self, validator):
        """Test validation report with empty results."""
        report = validator.generate_validation_report({})
        
        summary = report["validation_summary"]
        assert summary["total_genomes"] == 0
        assert summary["valid_genomes"] == 0
        assert summary["validation_rate"] == 0
        
        file_val = report["file_validation"]
        assert file_val["file_validation_rate"] == 0
    
    def test_get_common_issues(self, validator):
        """Test common issues extraction."""
        issues = [
            "Missing required field: genome_id",
            "Missing required field: tax_id", 
            "Size mismatch: database=1000, file=800",
            "Missing required field: genome_id",
            "Taxonomy ID 999 not found"
        ]
        
        common_issues = validator._get_common_issues(issues, limit=3)
        
        assert len(common_issues) <= 3
        assert common_issues[0][0] == "Missing required field"
        assert common_issues[0][1] == 3
    
    def test_check_metadata_completeness_complete(self, validator, sample_tree):
        """Test metadata completeness check with complete data."""
        genome = GenomeInfo(
            genome_id="complete_genome",
            tax_id=562,
            sequence_type="genome",
            source="NCBI"
        )
        
        result = GenomeValidationResult(genome_id="test")
        
        is_complete = validator._check_metadata_completeness(genome, result)
        
        assert is_complete is True
        assert len(result.issues) == 0
    
    def test_check_metadata_completeness_incomplete(self, validator, sample_tree):
        """Test metadata completeness check with incomplete data."""
        genome = GenomeInfo(
            genome_id="test_genome",  # Valid genome_id (required by __post_init__)
            tax_id=None,  # Missing required field 
            sequence_type=None,  # Missing recommended field
            source=None  # Missing recommended field
        )
        
        result = GenomeValidationResult(genome_id="test")
        
        is_complete = validator._check_metadata_completeness(genome, result)
        
        assert is_complete is False
        assert len(result.issues) >= 3  # 1 required + 2 recommended
        assert any("missing required field" in issue.lower() for issue in result.issues)
        assert any("missing recommended field" in issue.lower() for issue in result.issues)
    
    def test_check_taxonomy_linkage_valid(self, validator, mock_repository, sample_tree):
        """Test taxonomy linkage check with valid link."""
        mock_repository.load_tree.return_value = sample_tree
        
        genome = GenomeInfo(genome_id="test", tax_id=562)
        result = GenomeValidationResult(genome_id="test")
        
        is_linked = validator._check_taxonomy_linkage(genome, result)
        
        assert is_linked is True
        assert len(result.issues) == 0
    
    def test_check_taxonomy_linkage_invalid(self, validator, mock_repository, sample_tree):
        """Test taxonomy linkage check with invalid link."""
        mock_repository.load_tree.return_value = sample_tree
        
        genome = GenomeInfo(genome_id="test", tax_id=999)  # Non-existent
        result = GenomeValidationResult(genome_id="test")
        
        is_linked = validator._check_taxonomy_linkage(genome, result)
        
        assert is_linked is False
        assert len(result.issues) > 0
        assert any("not found in tree" in issue for issue in result.issues)
    
    def test_check_taxonomy_linkage_exception(self, validator, mock_repository):
        """Test taxonomy linkage check with exception."""
        mock_repository.load_tree.side_effect = Exception("Test error")
        
        genome = GenomeInfo(genome_id="test", tax_id=562)
        result = GenomeValidationResult(genome_id="test")
        
        is_linked = validator._check_taxonomy_linkage(genome, result)
        
        assert is_linked is False
        assert len(result.issues) > 0
        assert any("error checking taxonomy linkage" in issue.lower() for issue in result.issues)


class TestGenomeValidatorEdgeCases:
    """Test edge cases and error conditions."""
    
    @pytest.fixture
    def validator(self):
        """Create validator with mock repository."""
        mock_repo = Mock(spec=TaxonomyRepository)
        return GenomeValidator(mock_repo)
    
    def test_validation_with_missing_file(self, validator):
        """Test validation when file path points to missing file."""
        genome = GenomeInfo(
            genome_id="test",
            tax_id=562,
            file_path="/nonexistent/file.fasta"
        )
        
        result = validator.validate_genome(genome, ValidationLevel.STANDARD)
        
        assert result.file_validation is not None
        assert result.file_validation.is_valid is False
    
    def test_validation_with_very_large_size_difference(self, validator):
        """Test validation with very large size difference (outside tolerance)."""
        # Create a small temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.fasta', delete=False) as f:
            f.write(">seq\nATCG\n")  # Very small file
            temp_path = Path(f.name)
        
        try:
            genome = GenomeInfo(
                genome_id="test",
                tax_id=562,
                file_path=str(temp_path),
                sequence_length=1000000  # Much larger than file
            )
            
            result = validator.validate_genome(genome, ValidationLevel.STANDARD)
            
            assert result.size_matches is False
            assert any("size mismatch" in issue.lower() for issue in result.issues)
        finally:
            temp_path.unlink()
    
    def test_validation_with_zero_sequence_length(self, validator):
        """Test validation when genome has zero sequence length."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.fasta', delete=False) as f:
            f.write(">seq\nATCG\n")
            temp_path = Path(f.name)
        
        try:
            genome = GenomeInfo(
                genome_id="test",
                tax_id=562,
                file_path=str(temp_path),
                sequence_length=0  # Zero length in database
            )
            
            result = validator.validate_genome(genome, ValidationLevel.STANDARD)
            
            # Should not crash and handle gracefully
            assert result.genome_id == "test"
        finally:
            temp_path.unlink()


if __name__ == "__main__":
    pytest.main([__file__])