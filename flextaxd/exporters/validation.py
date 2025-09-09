"""Export format dependency validation framework.

This module provides standardized validation for export format requirements,
ensuring consistent behavior and clear user feedback across all exporters.
"""

from __future__ import annotations
from typing import Dict, List, Set, Optional, Any, Union, Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ..core.models import TaxonomyTree, GenomeInfo
from ..core.exceptions import ExportError
from ..utils.logging_config import get_logger

logger = get_logger(__name__)


class RequirementLevel(Enum):
    """Level of requirement for export validation."""
    REQUIRED = "required"      # Export fails without this
    RECOMMENDED = "recommended"  # Export proceeds with warning
    OPTIONAL = "optional"      # Silent fallback


class RequirementType(Enum):
    """Types of export format requirements."""
    GENOME_COUNT = "genome_count"                    # Minimum number of genomes
    GENOME_FILES = "genome_files"                    # Accessible FASTA files
    ASSEMBLY_ACCESSIONS = "assembly_accessions"      # Assembly accession fields
    SEQUENCE_TYPES = "sequence_types"                # Specific sequence types
    SEQUENCE_LENGTHS = "sequence_lengths"            # Sequence length data
    SOURCES = "sources"                              # Data source requirements
    FILE_PATHS = "file_paths"                        # Non-null file_path fields
    GENOME_IDS = "genome_ids"                        # Valid genome identifiers


@dataclass
class ExportRequirements:
    """Container for export format requirements."""
    format_name: str
    requirements: List['ExportRequirement']
    
    def __iter__(self):
        """Allow iteration over requirements."""
        return iter(self.requirements)


@dataclass
class ExportRequirement:
    """Specification for a single export format requirement."""
    
    requirement_type: RequirementType
    level: RequirementLevel
    description: str
    min_count: Optional[int] = None
    required_values: Optional[Set[str]] = None
    validate_files: bool = False  # Whether to check file existence
    
    def __post_init__(self):
        """Validate requirement specification."""
        if self.requirement_type == RequirementType.GENOME_COUNT and self.min_count is None:
            raise ValueError("GENOME_COUNT requirement must specify min_count")
        if self.requirement_type in [RequirementType.SEQUENCE_TYPES, RequirementType.SOURCES] and self.required_values is None:
            raise ValueError(f"{self.requirement_type.value} requirement must specify required_values")


@dataclass 
class ValidationResult:
    """Result of export format validation."""
    
    passed: bool
    requirements_met: List[str] = None
    requirements_failed: List[str] = None
    warnings: List[str] = None
    statistics: Dict[str, Any] = None
    
    def __post_init__(self):
        """Initialize empty lists if None."""
        if self.requirements_met is None:
            self.requirements_met = []
        if self.requirements_failed is None:
            self.requirements_failed = []
        if self.warnings is None:
            self.warnings = []
        if self.statistics is None:
            self.statistics = {}


class ExportValidator:
    """Validator for export format dependencies."""
    
    def __init__(self):
        """Initialize export validator."""
        self._format_requirements: Dict[str, List[ExportRequirement]] = {}
        self._register_builtin_requirements()
    
    def register_format_requirements(self, format_name: str, requirements: List[ExportRequirement]) -> None:
        """Register requirements for an export format.
        
        Args:
            format_name: Name of the export format
            requirements: List of requirements for this format
        """
        self._format_requirements[format_name] = requirements
        logger.debug(f"Registered {len(requirements)} requirements for format '{format_name}'")
    
    def validate_export(self, format_name: str, tree: TaxonomyTree, **kwargs) -> ValidationResult:
        """Validate taxonomy tree against export format requirements.
        
        Args:
            format_name: Name of the export format to validate against
            tree: TaxonomyTree to validate
            **kwargs: Additional validation options (e.g., validate_files=True)
            
        Returns:
            ValidationResult with detailed validation information
        """
        if format_name not in self._format_requirements:
            logger.warning(f"No requirements registered for format '{format_name}'")
            return ValidationResult(passed=True, warnings=[f"No validation rules defined for format '{format_name}'"])
        
        requirements = self._format_requirements[format_name]
        result = ValidationResult(passed=True)
        validate_files = kwargs.get("validate_files", False)
        
        # Collect genome statistics for validation
        genome_stats = self._collect_genome_statistics(tree, validate_files)
        result.statistics = genome_stats
        
        # Validate each requirement
        for requirement in requirements:
            validation_passed, message = self._validate_requirement(requirement, tree, genome_stats)
            
            if validation_passed:
                result.requirements_met.append(message)
            else:
                if requirement.level == RequirementLevel.REQUIRED:
                    result.requirements_failed.append(message)
                    result.passed = False
                elif requirement.level == RequirementLevel.RECOMMENDED:
                    result.warnings.append(f"Recommended: {message}")
                # Optional requirements don't affect result
        
        return result
    
    def _validate_requirement(self, requirement: ExportRequirement, tree: TaxonomyTree, 
                            stats: Dict[str, Any]) -> tuple[bool, str]:
        """Validate a single requirement against the tree.
        
        Returns:
            Tuple of (validation_passed, descriptive_message)
        """
        req_type = requirement.requirement_type
        
        if req_type == RequirementType.GENOME_COUNT:
            actual_count = stats["total_genomes"]
            min_required = requirement.min_count
            if actual_count >= min_required:
                return True, f"Genome count requirement met: {actual_count} ≥ {min_required}"
            else:
                return False, f"Insufficient genomes: found {actual_count}, need at least {min_required}"
        
        elif req_type == RequirementType.GENOME_FILES:
            files_available = stats["genomes_with_files"]
            accessible_files = stats.get("accessible_files", files_available)  # Default if not validated
            min_required = requirement.min_count or 1
            
            if requirement.validate_files and accessible_files >= min_required:
                return True, f"Genome files requirement met: {accessible_files} accessible files"
            elif not requirement.validate_files and files_available >= min_required:
                return True, f"Genome files requirement met: {files_available} files specified"
            else:
                target_count = accessible_files if requirement.validate_files else files_available
                return False, f"Insufficient genome files: found {target_count}, need at least {min_required}"
        
        elif req_type == RequirementType.ASSEMBLY_ACCESSIONS:
            accessions_available = stats["genomes_with_accessions"]
            min_required = requirement.min_count or 1
            if accessions_available >= min_required:
                return True, f"Assembly accessions requirement met: {accessions_available} accessions available"
            else:
                return False, f"Insufficient assembly accessions: found {accessions_available}, need at least {min_required}"
        
        elif req_type == RequirementType.SEQUENCE_TYPES:
            available_types = set(stats["sequence_types"].keys())
            required_types = requirement.required_values
            missing_types = required_types - available_types
            
            if not missing_types:
                return True, f"Sequence types requirement met: {', '.join(sorted(available_types))}"
            else:
                return False, f"Missing required sequence types: {', '.join(sorted(missing_types))}"
        
        elif req_type == RequirementType.SEQUENCE_LENGTHS:
            genomes_with_lengths = stats["genomes_with_lengths"]
            min_required = requirement.min_count or 1
            if genomes_with_lengths >= min_required:
                return True, f"Sequence lengths requirement met: {genomes_with_lengths} genomes with length data"
            else:
                return False, f"Insufficient sequence length data: found {genomes_with_lengths}, need at least {min_required}"
        
        elif req_type == RequirementType.SOURCES:
            available_sources = set(stats["sources"].keys())
            required_sources = requirement.required_values
            missing_sources = required_sources - available_sources
            
            if not missing_sources:
                return True, f"Data sources requirement met: {', '.join(sorted(available_sources))}"
            else:
                return False, f"Missing required data sources: {', '.join(sorted(missing_sources))}"
        
        elif req_type == RequirementType.FILE_PATHS:
            genomes_with_paths = stats["genomes_with_files"]
            min_required = requirement.min_count or 1
            if genomes_with_paths >= min_required:
                return True, f"File paths requirement met: {genomes_with_paths} genomes with file paths"
            else:
                return False, f"Insufficient file paths: found {genomes_with_paths}, need at least {min_required}"
        
        elif req_type == RequirementType.GENOME_IDS:
            total_genomes = stats["total_genomes"]
            min_required = requirement.min_count or 1
            if total_genomes >= min_required:
                return True, f"Genome IDs requirement met: {total_genomes} valid genome IDs"
            else:
                return False, f"Insufficient genome IDs: found {total_genomes}, need at least {min_required}"
        
        # Unknown requirement type
        return False, f"Unknown requirement type: {req_type.value}"
    
    def _collect_genome_statistics(self, tree: TaxonomyTree, validate_files: bool = False) -> Dict[str, Any]:
        """Collect comprehensive genome statistics for validation."""
        stats = {
            "total_genomes": tree.genome_count,
            "genomes_with_files": 0,
            "genomes_with_accessions": 0,
            "genomes_with_lengths": 0,
            "accessible_files": 0,
            "missing_files": 0,
            "invalid_files": 0,
            "sequence_types": {},
            "sources": {},
        }
        
        if tree.genome_count == 0:
            return stats
        
        # Analyze each genome
        for node in tree:
            genomes = tree.get_genomes_for_node(node.tax_id)
            for genome in genomes:
                # File path analysis
                if genome.file_path:
                    stats["genomes_with_files"] += 1
                    
                    # File validation if requested
                    if validate_files:
                        try:
                            path = Path(genome.file_path)
                            if path.exists() and path.is_file() and path.stat().st_size > 0:
                                stats["accessible_files"] += 1
                            elif path.exists():
                                stats["invalid_files"] += 1
                            else:
                                stats["missing_files"] += 1
                        except (OSError, PermissionError):
                            stats["invalid_files"] += 1
                
                # Assembly accession analysis
                if genome.assembly_accession:
                    stats["genomes_with_accessions"] += 1
                
                # Sequence length analysis  
                if genome.sequence_length is not None and genome.sequence_length > 0:
                    stats["genomes_with_lengths"] += 1
                
                # Sequence type breakdown
                seq_type = genome.sequence_type or "unknown"
                stats["sequence_types"][seq_type] = stats["sequence_types"].get(seq_type, 0) + 1
                
                # Source breakdown
                source = genome.source or "unknown"
                stats["sources"][source] = stats["sources"].get(source, 0) + 1
        
        return stats
    
    def _register_builtin_requirements(self) -> None:
        """Register requirements for built-in export formats."""
        
        # Formats requiring FASTA files
        fasta_file_formats = ["sylph", "diamond", "malt", "melon"]
        for format_name in fasta_file_formats:
            self.register_format_requirements(format_name, [
                ExportRequirement(
                    RequirementType.GENOME_FILES,
                    RequirementLevel.REQUIRED,
                    f"Requires accessible FASTA files for {format_name} database creation",
                    min_count=1,
                    validate_files=True
                )
            ])
        
        # Formats requiring assembly accessions
        accession_formats = ["metabuli", "metacache", "mmseqs2"]
        for format_name in accession_formats:
            self.register_format_requirements(format_name, [
                ExportRequirement(
                    RequirementType.ASSEMBLY_ACCESSIONS,
                    RequirementLevel.REQUIRED,
                    f"Requires assembly accessions for {format_name} mappings",
                    min_count=1
                ),
                ExportRequirement(
                    RequirementType.GENOME_COUNT,
                    RequirementLevel.REQUIRED,
                    f"Requires at least one genome for {format_name} export",
                    min_count=1
                )
            ])
        
        # Formats requiring sequence mappings
        mapping_formats = ["kraken2", "centrifuge", "ganon", "ganon2"]
        for format_name in mapping_formats:
            self.register_format_requirements(format_name, [
                ExportRequirement(
                    RequirementType.GENOME_IDS,
                    RequirementLevel.REQUIRED,
                    f"Requires genome identifiers for {format_name} sequence mappings",
                    min_count=1
                ),
                ExportRequirement(
                    RequirementType.FILE_PATHS,
                    RequirementLevel.RECOMMENDED,
                    f"File paths recommended for complete {format_name} database",
                    min_count=1
                )
            ])
        
        # Metadata-only formats
        metadata_formats = ["accession2taxid", "nucl2taxid", "prot2taxid", "genome_sizes"]
        for format_name in metadata_formats:
            self.register_format_requirements(format_name, [
                ExportRequirement(
                    RequirementType.GENOME_COUNT,
                    RequirementLevel.REQUIRED,
                    f"Requires genome metadata for {format_name} export",
                    min_count=1
                )
            ])
        
        # TSV and JSON formats (taxonomy only)
        taxonomy_formats = ["tsv", "json", "newick"]
        for format_name in taxonomy_formats:
            self.register_format_requirements(format_name, [
                # These formats work with taxonomy only, genomes are optional
                ExportRequirement(
                    RequirementType.GENOME_COUNT,
                    RequirementLevel.OPTIONAL,
                    f"Genomes are optional for {format_name} export",
                    min_count=0
                )
            ])
        
        # NCBI format (taxonomy only)
        self.register_format_requirements("ncbi", [
            ExportRequirement(
                RequirementType.GENOME_COUNT,
                RequirementLevel.OPTIONAL,
                "Genomes are optional for NCBI taxonomy export",
                min_count=0
            )
        ])


# Global validator instance
export_validator = ExportValidator()


def get_format_requirements(format_name: str) -> Optional[ExportRequirements]:
    """Get export requirements for a specific format.
    
    Args:
        format_name: Name of the export format
        
    Returns:
        ExportRequirements container for the format, or None if unknown format
    """
    requirements_list = export_validator._format_requirements.get(format_name)
    if requirements_list is None:
        return None
    return ExportRequirements(format_name=format_name, requirements=requirements_list)


def validate_export_requirements(format_name: str, tree: TaxonomyTree, **kwargs) -> ValidationResult:
    """Convenience function to validate export requirements.
    
    Args:
        format_name: Name of the export format
        tree: TaxonomyTree to validate
        **kwargs: Additional validation options
        
    Returns:
        ValidationResult with validation details
    """
    return export_validator.validate_export(format_name, tree, **kwargs)


def require_export_validation(format_name: str, **validation_kwargs):
    """Decorator to add export validation to exporter methods.
    
    Args:
        format_name: Name of the export format
        **validation_kwargs: Additional validation options
        
    Usage:
        @require_export_validation("diamond", validate_files=True)
        def export(self, tree, output_path, **kwargs):
            # Export logic here
    """
    def decorator(export_method: Callable) -> Callable:
        def wrapper(self, tree: TaxonomyTree, output_path: Path, **kwargs):
            # Check if validation is skipped
            if kwargs.get("skip_validation", False):
                logger.debug(f"Skipping export validation for {format_name}")
                return export_method(self, tree, output_path, **kwargs)
            
            # Merge validation kwargs with method kwargs
            merged_kwargs = {**validation_kwargs, **kwargs}
            
            # Perform validation
            validation_result = validate_export_requirements(format_name, tree, **merged_kwargs)
            
            # Handle validation results
            if not validation_result.passed:
                error_messages = "; ".join(validation_result.requirements_failed)
                raise ExportError(f"Export validation failed for {format_name}: {error_messages}")
            
            # Log warnings
            for warning in validation_result.warnings:
                logger.warning(f"Export validation warning for {format_name}: {warning}")
            
            # Log success
            if validation_result.requirements_met:
                logger.info(f"Export validation passed for {format_name}: {len(validation_result.requirements_met)} requirements met")
            
            # Call original export method
            return export_method(self, tree, output_path, **kwargs)
        
        return wrapper
    return decorator