"""Unit tests for export validation framework."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from dataclasses import dataclass
from typing import Dict, Any

from flextaxd.exporters.validation import (
    ExportValidator, 
    ExportRequirement, 
    ValidationResult, 
    RequirementLevel, 
    RequirementType,
    validate_export_requirements,
    require_export_validation,
    export_validator
)
from flextaxd.core.models import TaxonomyTree, TaxonomyNode, GenomeInfo
from flextaxd.core.exceptions import ExportError


@pytest.fixture
def sample_tree():
    """Create a sample taxonomy tree for testing."""
    tree = TaxonomyTree()
    
    # Add nodes
    root = TaxonomyNode(tax_id=1, name="Root", parent_id=None, rank="no rank")
    bacteria = TaxonomyNode(tax_id=2, name="Bacteria", parent_id=1, rank="superkingdom")
    ecoli = TaxonomyNode(tax_id=511145, name="Escherichia coli", parent_id=2, rank="species")
    
    tree.add_node(root)
    tree.add_node(bacteria)
    tree.add_node(ecoli)
    
    # Add genomes
    genome1 = GenomeInfo(
        genome_id="GCF_000001.1",
        tax_id=511145,
        file_path="/test/genome1.fna",
        sequence_length=4641652,
        sequence_type="genome",
        assembly_accession="GCF_000001.1",
        source="NCBI"
    )
    
    genome2 = GenomeInfo(
        genome_id="GCF_000002.1", 
        tax_id=511145,
        file_path="/test/genome2.fna",
        sequence_length=3500000,
        sequence_type="genome",
        assembly_accession="GCF_000002.1",
        source="GTDB"
    )
    
    tree.add_genome(genome1)
    tree.add_genome(genome2)
    
    return tree


@pytest.fixture
def empty_tree():
    """Create an empty taxonomy tree."""
    tree = TaxonomyTree()
    root = TaxonomyNode(tax_id=1, name="Root", parent_id=None, rank="no rank")
    tree.add_node(root)
    return tree


@pytest.fixture
def validator():
    """Create a fresh ExportValidator instance."""
    return ExportValidator()


class TestExportRequirement:
    """Test ExportRequirement dataclass."""
    
    def test_valid_requirement_creation(self):
        """Test creating valid requirements."""
        req = ExportRequirement(
            RequirementType.GENOME_COUNT,
            RequirementLevel.REQUIRED,
            "Test requirement",
            min_count=5
        )
        
        assert req.requirement_type == RequirementType.GENOME_COUNT
        assert req.level == RequirementLevel.REQUIRED
        assert req.min_count == 5
        assert req.validate_files is False
    
    def test_genome_count_requires_min_count(self):
        """Test that GENOME_COUNT requirement must specify min_count."""
        with pytest.raises(ValueError, match="GENOME_COUNT requirement must specify min_count"):
            ExportRequirement(
                RequirementType.GENOME_COUNT,
                RequirementLevel.REQUIRED,
                "Invalid requirement"
                # Missing min_count
            )
    
    def test_sequence_types_requires_values(self):
        """Test that SEQUENCE_TYPES requirement must specify required_values."""
        with pytest.raises(ValueError, match="sequence_types requirement must specify required_values"):
            ExportRequirement(
                RequirementType.SEQUENCE_TYPES,
                RequirementLevel.REQUIRED,
                "Invalid requirement"
                # Missing required_values
            )
    
    def test_sources_requires_values(self):
        """Test that SOURCES requirement must specify required_values."""
        with pytest.raises(ValueError, match="sources requirement must specify required_values"):
            ExportRequirement(
                RequirementType.SOURCES,
                RequirementLevel.REQUIRED,
                "Invalid requirement"
                # Missing required_values
            )


class TestValidationResult:
    """Test ValidationResult dataclass."""
    
    def test_default_initialization(self):
        """Test ValidationResult with default values."""
        result = ValidationResult(passed=True)
        
        assert result.passed is True
        assert result.requirements_met == []
        assert result.requirements_failed == []
        assert result.warnings == []
        assert result.statistics == {}
    
    def test_explicit_initialization(self):
        """Test ValidationResult with explicit values."""
        result = ValidationResult(
            passed=False,
            requirements_met=["req1", "req2"],
            requirements_failed=["req3"],
            warnings=["warning1"],
            statistics={"count": 5}
        )
        
        assert result.passed is False
        assert result.requirements_met == ["req1", "req2"]
        assert result.requirements_failed == ["req3"]
        assert result.warnings == ["warning1"]
        assert result.statistics == {"count": 5}


class TestExportValidator:
    """Test ExportValidator functionality."""
    
    def test_initialization(self, validator):
        """Test validator initialization."""
        assert validator._format_requirements is not None
        
        # Check that builtin formats are registered
        assert "diamond" in validator._format_requirements
        assert "kraken2" in validator._format_requirements
        assert "accession2taxid" in validator._format_requirements
    
    def test_register_format_requirements(self, validator):
        """Test registering custom format requirements."""
        requirements = [
            ExportRequirement(
                RequirementType.GENOME_COUNT,
                RequirementLevel.REQUIRED,
                "Custom format requirement",
                min_count=1
            )
        ]
        
        validator.register_format_requirements("custom_format", requirements)
        
        assert "custom_format" in validator._format_requirements
        assert len(validator._format_requirements["custom_format"]) == 1
    
    def test_validate_unknown_format(self, validator, sample_tree):
        """Test validation of unknown format."""
        result = validator.validate_export("unknown_format", sample_tree)
        
        assert result.passed is True
        assert len(result.warnings) == 1
        assert "No validation rules defined" in result.warnings[0]
    
    def test_validate_diamond_format_success(self, validator, sample_tree):
        """Test successful validation of diamond format."""
        # Mock file existence
        with patch('pathlib.Path.exists', return_value=True), \
             patch('pathlib.Path.is_file', return_value=True), \
             patch('pathlib.Path.stat') as mock_stat:
            
            mock_stat.return_value.st_size = 1000
            
            result = validator.validate_export("diamond", sample_tree, validate_files=True)
            
            assert result.passed is True
            assert len(result.requirements_met) > 0
            assert "Genome files requirement met" in result.requirements_met[0]
    
    def test_validate_diamond_format_failure(self, validator, empty_tree):
        """Test failed validation of diamond format."""
        result = validator.validate_export("diamond", empty_tree, validate_files=True)
        
        assert result.passed is False
        assert len(result.requirements_failed) > 0
        assert "Insufficient genome files" in result.requirements_failed[0]
    
    def test_validate_with_warnings(self, validator, sample_tree):
        """Test validation with recommended requirements."""
        # Create custom format with recommended requirement
        requirements = [
            ExportRequirement(
                RequirementType.GENOME_COUNT,
                RequirementLevel.RECOMMENDED,
                "Recommended genome count",
                min_count=10  # More than our sample tree has
            )
        ]
        validator.register_format_requirements("custom_format", requirements)
        
        result = validator.validate_export("custom_format", sample_tree)
        
        assert result.passed is True  # Should pass despite unmet recommended requirement
        assert len(result.warnings) == 1
        assert "Recommended" in result.warnings[0]
    
    def test_collect_genome_statistics(self, validator, sample_tree):
        """Test genome statistics collection."""
        stats = validator._collect_genome_statistics(sample_tree)
        
        assert stats["total_genomes"] == 2
        assert stats["genomes_with_files"] == 2
        assert stats["genomes_with_accessions"] == 2
        assert stats["genomes_with_lengths"] == 2
        assert stats["sequence_types"]["genome"] == 2
        assert stats["sources"]["NCBI"] == 1
        assert stats["sources"]["GTDB"] == 1
    
    def test_collect_statistics_with_file_validation(self, validator, sample_tree):
        """Test statistics collection with file validation."""
        with patch('pathlib.Path.exists', return_value=True), \
             patch('pathlib.Path.is_file', return_value=True), \
             patch('pathlib.Path.stat') as mock_stat:
            
            mock_stat.return_value.st_size = 1000
            
            stats = validator._collect_genome_statistics(sample_tree, validate_files=True)
            
            assert stats["accessible_files"] == 2
            assert stats["missing_files"] == 0
            assert stats["invalid_files"] == 0
    
    def test_collect_statistics_missing_files(self, validator, sample_tree):
        """Test statistics collection with missing files."""
        with patch('pathlib.Path.exists', return_value=False):
            stats = validator._collect_genome_statistics(sample_tree, validate_files=True)
            
            assert stats["accessible_files"] == 0
            assert stats["missing_files"] == 2
            assert stats["invalid_files"] == 0
    
    def test_collect_statistics_invalid_files(self, validator, sample_tree):
        """Test statistics collection with invalid files."""
        with patch('pathlib.Path.exists', return_value=True), \
             patch('pathlib.Path.is_file', return_value=True), \
             patch('pathlib.Path.stat') as mock_stat:
            
            # Mock zero-size files (invalid)
            mock_stat.return_value.st_size = 0
            
            stats = validator._collect_genome_statistics(sample_tree, validate_files=True)
            
            assert stats["accessible_files"] == 0
            assert stats["missing_files"] == 0
            assert stats["invalid_files"] == 2


class TestRequirementValidation:
    """Test individual requirement validation methods."""
    
    def test_validate_genome_count_success(self, validator, sample_tree):
        """Test successful genome count validation."""
        requirement = ExportRequirement(
            RequirementType.GENOME_COUNT,
            RequirementLevel.REQUIRED,
            "Test requirement",
            min_count=1
        )
        
        stats = validator._collect_genome_statistics(sample_tree)
        passed, message = validator._validate_requirement(requirement, sample_tree, stats)
        
        assert passed is True
        assert "Genome count requirement met" in message
        assert "2 ≥ 1" in message
    
    def test_validate_genome_count_failure(self, validator, empty_tree):
        """Test failed genome count validation."""
        requirement = ExportRequirement(
            RequirementType.GENOME_COUNT,
            RequirementLevel.REQUIRED,
            "Test requirement",
            min_count=5
        )
        
        stats = validator._collect_genome_statistics(empty_tree)
        passed, message = validator._validate_requirement(requirement, empty_tree, stats)
        
        assert passed is False
        assert "Insufficient genomes" in message
        assert "found 0, need at least 5" in message
    
    def test_validate_genome_files_success(self, validator, sample_tree):
        """Test successful genome files validation."""
        requirement = ExportRequirement(
            RequirementType.GENOME_FILES,
            RequirementLevel.REQUIRED,
            "Test requirement",
            min_count=1
        )
        
        stats = validator._collect_genome_statistics(sample_tree)
        passed, message = validator._validate_requirement(requirement, sample_tree, stats)
        
        assert passed is True
        assert "Genome files requirement met" in message
    
    def test_validate_assembly_accessions_success(self, validator, sample_tree):
        """Test successful assembly accessions validation."""
        requirement = ExportRequirement(
            RequirementType.ASSEMBLY_ACCESSIONS,
            RequirementLevel.REQUIRED,
            "Test requirement",
            min_count=1
        )
        
        stats = validator._collect_genome_statistics(sample_tree)
        passed, message = validator._validate_requirement(requirement, sample_tree, stats)
        
        assert passed is True
        assert "Assembly accessions requirement met" in message
    
    def test_validate_sequence_types_success(self, validator, sample_tree):
        """Test successful sequence types validation."""
        requirement = ExportRequirement(
            RequirementType.SEQUENCE_TYPES,
            RequirementLevel.REQUIRED,
            "Test requirement",
            required_values={"genome"}
        )
        
        stats = validator._collect_genome_statistics(sample_tree)
        passed, message = validator._validate_requirement(requirement, sample_tree, stats)
        
        assert passed is True
        assert "Sequence types requirement met" in message
    
    def test_validate_sequence_types_failure(self, validator, sample_tree):
        """Test failed sequence types validation."""
        requirement = ExportRequirement(
            RequirementType.SEQUENCE_TYPES,
            RequirementLevel.REQUIRED,
            "Test requirement",
            required_values={"plasmid", "chromosome"}
        )
        
        stats = validator._collect_genome_statistics(sample_tree)
        passed, message = validator._validate_requirement(requirement, sample_tree, stats)
        
        assert passed is False
        assert "Missing required sequence types" in message
        assert "plasmid" in message and "chromosome" in message
    
    def test_validate_sources_success(self, validator, sample_tree):
        """Test successful data sources validation."""
        requirement = ExportRequirement(
            RequirementType.SOURCES,
            RequirementLevel.REQUIRED,
            "Test requirement",
            required_values={"NCBI"}
        )
        
        stats = validator._collect_genome_statistics(sample_tree)
        passed, message = validator._validate_requirement(requirement, sample_tree, stats)
        
        assert passed is True
        assert "Data sources requirement met" in message
    
    def test_validate_sequence_lengths_success(self, validator, sample_tree):
        """Test successful sequence lengths validation."""
        requirement = ExportRequirement(
            RequirementType.SEQUENCE_LENGTHS,
            RequirementLevel.REQUIRED,
            "Test requirement",
            min_count=1
        )
        
        stats = validator._collect_genome_statistics(sample_tree)
        passed, message = validator._validate_requirement(requirement, sample_tree, stats)
        
        assert passed is True
        assert "Sequence lengths requirement met" in message
    
    def test_validate_file_paths_success(self, validator, sample_tree):
        """Test successful file paths validation."""
        requirement = ExportRequirement(
            RequirementType.FILE_PATHS,
            RequirementLevel.REQUIRED,
            "Test requirement",
            min_count=1
        )
        
        stats = validator._collect_genome_statistics(sample_tree)
        passed, message = validator._validate_requirement(requirement, sample_tree, stats)
        
        assert passed is True
        assert "File paths requirement met" in message
    
    def test_validate_genome_ids_success(self, validator, sample_tree):
        """Test successful genome IDs validation."""
        requirement = ExportRequirement(
            RequirementType.GENOME_IDS,
            RequirementLevel.REQUIRED,
            "Test requirement",
            min_count=1
        )
        
        stats = validator._collect_genome_statistics(sample_tree)
        passed, message = validator._validate_requirement(requirement, sample_tree, stats)
        
        assert passed is True
        assert "Genome IDs requirement met" in message
    
    def test_validate_unknown_requirement_type(self, validator, sample_tree):
        """Test validation of unknown requirement type."""
        # Create a mock requirement with unknown type
        requirement = Mock()
        requirement.requirement_type = Mock()
        requirement.requirement_type.value = "unknown_type"
        
        stats = validator._collect_genome_statistics(sample_tree)
        passed, message = validator._validate_requirement(requirement, sample_tree, stats)
        
        assert passed is False
        assert "Unknown requirement type: unknown_type" in message


class TestBuiltinFormats:
    """Test builtin format requirements."""
    
    def test_fasta_file_formats(self, validator):
        """Test that FASTA file formats have correct requirements."""
        fasta_formats = ["sylph", "diamond", "malt", "melon"]
        
        for format_name in fasta_formats:
            requirements = validator._format_requirements[format_name]
            assert len(requirements) == 1
            
            req = requirements[0]
            assert req.requirement_type == RequirementType.GENOME_FILES
            assert req.level == RequirementLevel.REQUIRED
            assert req.min_count == 1
            assert req.validate_files is True
    
    def test_accession_formats(self, validator):
        """Test that accession formats have correct requirements."""
        accession_formats = ["metabuli", "metacache", "mmseqs2"]
        
        for format_name in accession_formats:
            requirements = validator._format_requirements[format_name]
            assert len(requirements) == 2
            
            # Check for assembly accessions requirement
            accession_req = next(req for req in requirements 
                               if req.requirement_type == RequirementType.ASSEMBLY_ACCESSIONS)
            assert accession_req.level == RequirementLevel.REQUIRED
            assert accession_req.min_count == 1
            
            # Check for genome count requirement
            count_req = next(req for req in requirements 
                           if req.requirement_type == RequirementType.GENOME_COUNT)
            assert count_req.level == RequirementLevel.REQUIRED
            assert count_req.min_count == 1
    
    def test_mapping_formats(self, validator):
        """Test that mapping formats have correct requirements."""
        mapping_formats = ["kraken2", "centrifuge", "ganon", "ganon2"]
        
        for format_name in mapping_formats:
            requirements = validator._format_requirements[format_name]
            assert len(requirements) == 2
            
            # Check for genome IDs requirement (required)
            ids_req = next(req for req in requirements 
                          if req.requirement_type == RequirementType.GENOME_IDS)
            assert ids_req.level == RequirementLevel.REQUIRED
            assert ids_req.min_count == 1
            
            # Check for file paths requirement (recommended)
            paths_req = next(req for req in requirements 
                           if req.requirement_type == RequirementType.FILE_PATHS)
            assert paths_req.level == RequirementLevel.RECOMMENDED
            assert paths_req.min_count == 1
    
    def test_metadata_formats(self, validator):
        """Test that metadata formats have correct requirements."""
        metadata_formats = ["accession2taxid", "nucl2taxid", "prot2taxid", "genome_sizes"]
        
        for format_name in metadata_formats:
            requirements = validator._format_requirements[format_name]
            assert len(requirements) == 1
            
            req = requirements[0]
            assert req.requirement_type == RequirementType.GENOME_COUNT
            assert req.level == RequirementLevel.REQUIRED
            assert req.min_count == 1
    
    def test_taxonomy_only_formats(self, validator):
        """Test that taxonomy-only formats have correct requirements."""
        taxonomy_formats = ["tsv", "json", "newick", "ncbi"]
        
        for format_name in taxonomy_formats:
            requirements = validator._format_requirements[format_name]
            assert len(requirements) == 1
            
            req = requirements[0]
            assert req.requirement_type == RequirementType.GENOME_COUNT
            assert req.level == RequirementLevel.OPTIONAL
            assert req.min_count == 0


class TestConvenienceFunctions:
    """Test convenience functions and decorators."""
    
    def test_validate_export_requirements_function(self, sample_tree):
        """Test standalone validation function."""
        # Mock file existence for diamond format which requires accessible files
        with patch('pathlib.Path.exists', return_value=True), \
             patch('pathlib.Path.is_file', return_value=True), \
             patch('pathlib.Path.stat') as mock_stat:
            
            mock_stat.return_value.st_size = 1000
            
            result = validate_export_requirements("diamond", sample_tree, validate_files=True)
            
            assert isinstance(result, ValidationResult)
            assert result.passed is True
    
    def test_require_export_validation_decorator_success(self, sample_tree):
        """Test export validation decorator with successful validation."""
        @require_export_validation("tsv")
        def mock_export(self, tree, output_path, **kwargs):
            return "export_success"
        
        # Mock self object
        mock_self = Mock()
        
        result = mock_export(mock_self, sample_tree, Path("/test/output.tsv"))
        assert result == "export_success"
    
    def test_require_export_validation_decorator_failure(self, empty_tree):
        """Test export validation decorator with failed validation."""
        @require_export_validation("diamond", validate_files=True)
        def mock_export(self, tree, output_path, **kwargs):
            return "export_success"
        
        mock_self = Mock()
        
        with pytest.raises(ExportError, match="Export validation failed"):
            mock_export(mock_self, empty_tree, Path("/test/output"))
    
    def test_require_export_validation_decorator_skip(self, empty_tree):
        """Test export validation decorator with validation skipped."""
        @require_export_validation("diamond", validate_files=True)
        def mock_export(self, tree, output_path, **kwargs):
            return "export_success"
        
        mock_self = Mock()
        
        # Should succeed when validation is skipped
        result = mock_export(mock_self, empty_tree, Path("/test/output"), skip_validation=True)
        assert result == "export_success"
    
    def test_require_export_validation_decorator_warnings(self, sample_tree):
        """Test export validation decorator with warnings."""
        # Create a custom format with recommended requirements that won't be met
        export_validator.register_format_requirements("test_warning_format", [
            ExportRequirement(
                RequirementType.SEQUENCE_TYPES,
                RequirementLevel.RECOMMENDED,
                "Recommended sequence types",
                required_values={"plasmid"}  # Not present in sample tree
            )
        ])
        
        @require_export_validation("test_warning_format")
        def mock_export(self, tree, output_path, **kwargs):
            return "export_success"
        
        mock_self = Mock()
        
        with patch('flextaxd.exporters.validation.logger') as mock_logger:
            result = mock_export(mock_self, sample_tree, Path("/test/output"))
            
            assert result == "export_success"
            # Should have logged a warning
            mock_logger.warning.assert_called()


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_empty_statistics(self, validator, empty_tree):
        """Test statistics collection with empty tree."""
        stats = validator._collect_genome_statistics(empty_tree)
        
        assert stats["total_genomes"] == 0
        assert stats["genomes_with_files"] == 0
        assert stats["accessible_files"] == 0
        assert len(stats["sequence_types"]) == 0
        assert len(stats["sources"]) == 0
    
    def test_validation_with_permission_error(self, validator, sample_tree):
        """Test file validation with permission errors."""
        with patch('pathlib.Path.exists', side_effect=PermissionError):
            stats = validator._collect_genome_statistics(sample_tree, validate_files=True)
            
            assert stats["invalid_files"] == 2
            assert stats["accessible_files"] == 0
    
    def test_genome_without_optional_fields(self, validator):
        """Test statistics with genomes missing optional fields."""
        tree = TaxonomyTree()
        root = TaxonomyNode(tax_id=1, name="Root", parent_id=None, rank="no rank")
        tree.add_node(root)
        
        # Genome with minimal fields
        genome = GenomeInfo(
            genome_id="minimal_genome",
            tax_id=1
            # Missing file_path, assembly_accession, sequence_length, etc.
        )
        tree.add_genome(genome)
        
        stats = validator._collect_genome_statistics(tree)
        
        assert stats["total_genomes"] == 1
        assert stats["genomes_with_files"] == 0
        assert stats["genomes_with_accessions"] == 0
        assert stats["genomes_with_lengths"] == 0
        assert stats["sequence_types"]["unknown"] == 1
        assert stats["sources"]["unknown"] == 1
    
    def test_requirement_with_zero_min_count(self, validator, empty_tree):
        """Test requirement validation with zero minimum count."""
        requirement = ExportRequirement(
            RequirementType.GENOME_COUNT,
            RequirementLevel.REQUIRED,
            "Zero minimum requirement",
            min_count=0
        )
        
        stats = validator._collect_genome_statistics(empty_tree)
        passed, message = validator._validate_requirement(requirement, empty_tree, stats)
        
        assert passed is True
        assert "0 ≥ 0" in message