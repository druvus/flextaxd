"""Tests for export validation framework."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from flextaxd.exporters.validation import (
    ExportValidator,
    ExportRequirement,
    ValidationResult,
    RequirementType,
    RequirementLevel,
    validate_export_requirements,
    require_export_validation
)
from flextaxd.core.models import TaxonomyTree, TaxonomyNode, GenomeInfo, TaxonomicRank
from flextaxd.core.exceptions import ExportError


class TestExportRequirement:
    """Test ExportRequirement dataclass."""

    def test_requirement_validation_genome_count(self):
        """Test that GENOME_COUNT requirement requires min_count."""
        with pytest.raises(ValueError, match="must specify min_count"):
            ExportRequirement(
                RequirementType.GENOME_COUNT,
                RequirementLevel.REQUIRED,
                "Test requirement"
            )

    def test_requirement_validation_sequence_types(self):
        """Test that SEQUENCE_TYPES requirement requires required_values."""
        with pytest.raises(ValueError, match="must specify required_values"):
            ExportRequirement(
                RequirementType.SEQUENCE_TYPES,
                RequirementLevel.REQUIRED,
                "Test requirement"
            )

    def test_valid_requirement_creation(self):
        """Test successful requirement creation."""
        req = ExportRequirement(
            RequirementType.GENOME_COUNT,
            RequirementLevel.REQUIRED,
            "Test requirement",
            min_count=5
        )
        assert req.requirement_type == RequirementType.GENOME_COUNT
        assert req.level == RequirementLevel.REQUIRED
        assert req.min_count == 5


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
            requirements_met=["req1"],
            requirements_failed=["req2"],
            warnings=["warn1"],
            statistics={"count": 5}
        )
        assert result.passed is False
        assert result.requirements_met == ["req1"]
        assert result.requirements_failed == ["req2"]
        assert result.warnings == ["warn1"]
        assert result.statistics == {"count": 5}


class TestExportValidator:
    """Test ExportValidator class."""

    def test_validator_initialization(self):
        """Test validator initializes with builtin requirements."""
        validator = ExportValidator()
        
        # Check that builtin formats are registered
        assert "diamond" in validator._format_requirements
        assert "kraken2" in validator._format_requirements
        assert "accession2taxid" in validator._format_requirements
        
        # Check Diamond requirements
        diamond_reqs = validator._format_requirements["diamond"]
        assert len(diamond_reqs) == 1
        assert diamond_reqs[0].requirement_type == RequirementType.GENOME_FILES
        assert diamond_reqs[0].level == RequirementLevel.REQUIRED

    def test_register_custom_requirements(self):
        """Test registering custom format requirements."""
        validator = ExportValidator()
        
        custom_reqs = [
            ExportRequirement(
                RequirementType.GENOME_COUNT,
                RequirementLevel.REQUIRED,
                "Custom requirement",
                min_count=10
            )
        ]
        
        validator.register_format_requirements("custom_format", custom_reqs)
        assert "custom_format" in validator._format_requirements
        assert len(validator._format_requirements["custom_format"]) == 1

    def test_validate_unknown_format(self):
        """Test validation with unknown format."""
        validator = ExportValidator()
        tree = self._create_test_tree()
        
        result = validator.validate_export("unknown_format", tree)
        assert result.passed is True
        assert len(result.warnings) == 1
        assert "No validation rules defined" in result.warnings[0]

    def test_validate_genome_count_requirement_success(self):
        """Test genome count requirement validation - success."""
        validator = ExportValidator()
        tree = self._create_test_tree_with_genomes(5)
        
        validator.register_format_requirements("test_format", [
            ExportRequirement(
                RequirementType.GENOME_COUNT,
                RequirementLevel.REQUIRED,
                "Test requirement",
                min_count=3
            )
        ])
        
        result = validator.validate_export("test_format", tree)
        assert result.passed is True
        assert len(result.requirements_met) == 1
        assert "Genome count requirement met: 5 ≥ 3" in result.requirements_met[0]

    def test_validate_genome_count_requirement_failure(self):
        """Test genome count requirement validation - failure."""
        validator = ExportValidator()
        tree = self._create_test_tree_with_genomes(2)
        
        validator.register_format_requirements("test_format", [
            ExportRequirement(
                RequirementType.GENOME_COUNT,
                RequirementLevel.REQUIRED,
                "Test requirement",
                min_count=5
            )
        ])
        
        result = validator.validate_export("test_format", tree)
        assert result.passed is False
        assert len(result.requirements_failed) == 1
        assert "Insufficient genomes: found 2, need at least 5" in result.requirements_failed[0]

    def test_validate_genome_files_requirement_success(self):
        """Test genome files requirement validation - success."""
        validator = ExportValidator()
        
        # Create test files
        test_files = []
        for i in range(3):
            temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.fasta', delete=False)
            temp_file.write(f">seq{i}\nATCG\n")
            temp_file.close()
            test_files.append(Path(temp_file.name))
        
        try:
            tree = self._create_test_tree_with_genome_files(test_files[:2])
            
            validator.register_format_requirements("test_format", [
                ExportRequirement(
                    RequirementType.GENOME_FILES,
                    RequirementLevel.REQUIRED,
                    "Test requirement",
                    min_count=1,
                    validate_files=True
                )
            ])
            
            result = validator.validate_export("test_format", tree, validate_files=True)
            assert result.passed is True
            assert len(result.requirements_met) == 1
            assert "accessible files" in result.requirements_met[0]
            
        finally:
            # Cleanup test files
            for temp_file in test_files:
                if temp_file.exists():
                    temp_file.unlink()

    def test_validate_sequence_types_requirement_success(self):
        """Test sequence types requirement validation - success."""
        validator = ExportValidator()
        tree = self._create_test_tree_with_sequence_types(["genome", "16S", "plasmid"])
        
        validator.register_format_requirements("test_format", [
            ExportRequirement(
                RequirementType.SEQUENCE_TYPES,
                RequirementLevel.REQUIRED,
                "Test requirement",
                required_values={"genome", "16S"}
            )
        ])
        
        result = validator.validate_export("test_format", tree)
        assert result.passed is True
        assert len(result.requirements_met) == 1

    def test_validate_sequence_types_requirement_failure(self):
        """Test sequence types requirement validation - failure."""
        validator = ExportValidator()
        tree = self._create_test_tree_with_sequence_types(["genome"])
        
        validator.register_format_requirements("test_format", [
            ExportRequirement(
                RequirementType.SEQUENCE_TYPES,
                RequirementLevel.REQUIRED,
                "Test requirement",
                required_values={"genome", "16S", "plasmid"}
            )
        ])
        
        result = validator.validate_export("test_format", tree)
        assert result.passed is False
        assert len(result.requirements_failed) == 1
        assert "Missing required sequence types: 16S, plasmid" in result.requirements_failed[0]

    def test_validate_recommended_requirement_warning(self):
        """Test recommended requirement creates warning when failed."""
        validator = ExportValidator()
        tree = self._create_test_tree_with_genomes(1)
        
        validator.register_format_requirements("test_format", [
            ExportRequirement(
                RequirementType.GENOME_COUNT,
                RequirementLevel.RECOMMENDED,
                "Test requirement",
                min_count=5
            )
        ])
        
        result = validator.validate_export("test_format", tree)
        assert result.passed is True  # Still passes despite failed recommended requirement
        assert len(result.warnings) == 1
        assert "Recommended:" in result.warnings[0]

    def test_validate_optional_requirement_ignored(self):
        """Test optional requirement doesn't affect result when failed."""
        validator = ExportValidator()
        tree = self._create_test_tree_with_genomes(1)
        
        validator.register_format_requirements("test_format", [
            ExportRequirement(
                RequirementType.GENOME_COUNT,
                RequirementLevel.OPTIONAL,
                "Test requirement",
                min_count=5
            )
        ])
        
        result = validator.validate_export("test_format", tree)
        assert result.passed is True
        assert len(result.warnings) == 0
        assert len(result.requirements_failed) == 0

    def test_collect_genome_statistics(self):
        """Test genome statistics collection."""
        validator = ExportValidator()
        tree = self._create_test_tree_with_mixed_genomes()
        
        stats = validator._collect_genome_statistics(tree, validate_files=False)
        
        assert stats["total_genomes"] == 3
        assert stats["genomes_with_files"] == 2
        assert stats["genomes_with_accessions"] == 2
        assert stats["genomes_with_lengths"] == 2
        assert stats["sequence_types"]["genome"] == 2
        assert stats["sequence_types"]["16S"] == 1
        assert stats["sources"]["NCBI"] == 2
        assert stats["sources"]["GTDB"] == 1

    # Helper methods

    def _create_test_tree(self):
        """Create a basic test taxonomy tree."""
        tree = TaxonomyTree()
        
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT)
        bacteria = TaxonomyNode(tax_id=2, name="Bacteria", rank=TaxonomicRank.SUPERKINGDOM, parent_id=1)
        
        tree.add_node(root)
        tree.add_node(bacteria)
        
        return tree

    def _create_test_tree_with_genomes(self, count):
        """Create test tree with specified number of genomes."""
        tree = self._create_test_tree()
        
        for i in range(count):
            genome = GenomeInfo(
                genome_id=f"genome_{i}",
                tax_id=2,
                sequence_length=1000000,
                sequence_type="genome",
                source="TEST"
            )
            tree.add_genome(genome)
        
        return tree

    def _create_test_tree_with_genome_files(self, file_paths):
        """Create test tree with genomes having file paths."""
        tree = self._create_test_tree()
        
        for i, file_path in enumerate(file_paths):
            genome = GenomeInfo(
                genome_id=f"genome_{i}",
                tax_id=2,
                file_path=str(file_path),
                sequence_length=1000000,
                sequence_type="genome",
                source="TEST"
            )
            tree.add_genome(genome)
        
        return tree

    def _create_test_tree_with_sequence_types(self, seq_types):
        """Create test tree with genomes of different sequence types."""
        tree = self._create_test_tree()
        
        for i, seq_type in enumerate(seq_types):
            genome = GenomeInfo(
                genome_id=f"genome_{i}",
                tax_id=2,
                sequence_type=seq_type,
                source="TEST"
            )
            tree.add_genome(genome)
        
        return tree

    def _create_test_tree_with_mixed_genomes(self):
        """Create test tree with mixed genome scenarios."""
        tree = self._create_test_tree()
        
        genomes = [
            GenomeInfo(
                genome_id="genome_1",
                tax_id=2,
                file_path="/test/file1.fasta",
                sequence_length=2000000,
                sequence_type="genome",
                assembly_accession="GCF_000001.1",
                source="NCBI"
            ),
            GenomeInfo(
                genome_id="genome_2",
                tax_id=2,
                file_path="/test/file2.fasta",
                sequence_length=3000000,
                sequence_type="genome",
                assembly_accession="GCF_000002.1",
                source="NCBI"
            ),
            GenomeInfo(
                genome_id="16S_seq",
                tax_id=2,
                sequence_type="16S",
                source="GTDB"
            )
        ]
        
        for genome in genomes:
            tree.add_genome(genome)
        
        return tree


class TestValidationFunctions:
    """Test module-level validation functions."""

    def test_validate_export_requirements_function(self):
        """Test convenience validation function."""
        tree = TaxonomyTree()
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT)
        tree.add_node(root)
        
        result = validate_export_requirements("diamond", tree)
        # Diamond requires genome files, so this should fail
        assert result.passed is False

    def test_require_export_validation_decorator_success(self):
        """Test validation decorator with successful validation."""
        
        @require_export_validation("tsv")  # TSV has optional requirements
        def mock_export(self, tree, output_path, **kwargs):
            return "export_success"
        
        tree = TaxonomyTree()
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT)
        tree.add_node(root)
        
        # Should succeed since TSV has optional requirements
        result = mock_export(None, tree, Path("/test/output.tsv"))
        assert result == "export_success"

    def test_require_export_validation_decorator_failure(self):
        """Test validation decorator with failed validation."""
        
        @require_export_validation("diamond", validate_files=True)
        def mock_export(self, tree, output_path, **kwargs):
            return "export_success"
        
        tree = TaxonomyTree()
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT)
        tree.add_node(root)
        
        # Should fail since Diamond requires genome files
        with pytest.raises(ExportError, match="Export validation failed for diamond"):
            mock_export(None, tree, Path("/test/output"))


class TestBuiltinFormatRequirements:
    """Test builtin format requirements are correctly configured."""

    def test_fasta_file_formats(self):
        """Test formats requiring FASTA files."""
        validator = ExportValidator()
        fasta_formats = ["sylph", "diamond", "malt", "melon"]
        
        for format_name in fasta_formats:
            requirements = validator._format_requirements[format_name]
            assert len(requirements) == 1
            assert requirements[0].requirement_type == RequirementType.GENOME_FILES
            assert requirements[0].level == RequirementLevel.REQUIRED
            assert requirements[0].validate_files is True

    def test_accession_formats(self):
        """Test formats requiring assembly accessions."""
        validator = ExportValidator()
        accession_formats = ["metabuli", "metacache", "mmseqs2"]
        
        for format_name in accession_formats:
            requirements = validator._format_requirements[format_name]
            # Should have both assembly accession and genome count requirements
            req_types = [req.requirement_type for req in requirements]
            assert RequirementType.ASSEMBLY_ACCESSIONS in req_types
            assert RequirementType.GENOME_COUNT in req_types

    def test_mapping_formats(self):
        """Test formats requiring sequence mappings."""
        validator = ExportValidator()
        mapping_formats = ["kraken2", "centrifuge", "ganon", "ganon2"]
        
        for format_name in mapping_formats:
            requirements = validator._format_requirements[format_name]
            req_types = [req.requirement_type for req in requirements]
            assert RequirementType.GENOME_IDS in req_types
            # Should also have recommended file paths
            file_path_reqs = [req for req in requirements if req.requirement_type == RequirementType.FILE_PATHS]
            assert len(file_path_reqs) == 1
            assert file_path_reqs[0].level == RequirementLevel.RECOMMENDED

    def test_metadata_formats(self):
        """Test metadata-only formats."""
        validator = ExportValidator()
        metadata_formats = ["accession2taxid", "nucl2taxid", "prot2taxid", "genome_sizes"]
        
        for format_name in metadata_formats:
            requirements = validator._format_requirements[format_name]
            assert len(requirements) == 1
            assert requirements[0].requirement_type == RequirementType.GENOME_COUNT
            assert requirements[0].level == RequirementLevel.REQUIRED
            assert requirements[0].min_count == 1

    def test_taxonomy_only_formats(self):
        """Test taxonomy-only formats."""
        validator = ExportValidator()
        taxonomy_formats = ["tsv", "json", "newick", "ncbi"]
        
        for format_name in taxonomy_formats:
            requirements = validator._format_requirements[format_name]
            assert len(requirements) == 1
            assert requirements[0].requirement_type == RequirementType.GENOME_COUNT
            assert requirements[0].level == RequirementLevel.OPTIONAL


if __name__ == "__main__":
    pytest.main([__file__])