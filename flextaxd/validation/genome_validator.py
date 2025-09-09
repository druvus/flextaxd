"""Genome-specific validation that integrates with the database."""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Any, Tuple
import logging

from .file_validator import FileValidator, ValidationResult, ValidationLevel
from ..core.models import GenomeInfo, TaxonomyTree
from ..database.repository import TaxonomyRepository
from ..core.exceptions import ValidationError


@dataclass
class GenomeValidationResult:
    """Result of genome validation including database consistency."""
    genome_id: str
    file_validation: Optional[ValidationResult] = None
    database_consistent: bool = True
    metadata_complete: bool = True
    size_matches: bool = True
    taxonomy_linked: bool = True
    issues: List[str] = None
    
    def __post_init__(self):
        if self.issues is None:
            self.issues = []
    
    @property
    def is_valid(self) -> bool:
        """Overall validity check."""
        file_valid = self.file_validation.is_valid if self.file_validation else True
        return (file_valid and self.database_consistent and 
                self.metadata_complete and self.taxonomy_linked)


class GenomeValidator:
    """Validate genome data consistency between database and filesystem."""
    
    def __init__(self, repository: TaxonomyRepository, max_workers: int = 4):
        self.repository = repository
        self.file_validator = FileValidator(max_workers=max_workers)
        self.logger = logging.getLogger(__name__)
    
    def validate_genome(self, genome: GenomeInfo, level: ValidationLevel = ValidationLevel.STANDARD) -> GenomeValidationResult:
        """Validate a single genome's data consistency."""
        result = GenomeValidationResult(genome_id=genome.genome_id)
        
        # File validation
        if genome.file_path:
            file_path = Path(genome.file_path)
            result.file_validation = self.file_validator.validate_file(file_path, level)
            
            # Check size consistency
            if (result.file_validation.is_valid and 
                genome.sequence_length and 
                result.file_validation.total_length > 0):
                
                length_diff = abs(genome.sequence_length - result.file_validation.total_length)
                tolerance = max(1000, genome.sequence_length * 0.01)  # 1% or 1kb
                
                if length_diff > tolerance:
                    result.size_matches = False
                    result.issues.append(
                        f"Size mismatch: database={genome.sequence_length}, "
                        f"file={result.file_validation.total_length}, "
                        f"difference={length_diff}"
                    )
        else:
            # No file path - metadata only genome
            if level == ValidationLevel.COMPREHENSIVE:
                result.issues.append("Genome has no associated file")
        
        # Check database metadata completeness
        result.metadata_complete = self._check_metadata_completeness(genome, result)
        
        # Check taxonomy linkage
        result.taxonomy_linked = self._check_taxonomy_linkage(genome, result)
        
        return result
    
    def validate_all_genomes(self, level: ValidationLevel = ValidationLevel.STANDARD, 
                           progress_callback: Optional[callable] = None) -> Dict[str, GenomeValidationResult]:
        """Validate all genomes in the database."""
        genomes = self.repository.get_all_genomes()
        results = {}
        
        if progress_callback:
            self.file_validator.set_progress_callback(progress_callback)
        
        total_genomes = len(genomes)
        
        # Group genomes by whether they have files
        genomes_with_files = [g for g in genomes if g.file_path]
        genomes_metadata_only = [g for g in genomes if not g.file_path]
        
        # Batch validate files for efficiency
        if genomes_with_files:
            file_paths = [Path(g.file_path) for g in genomes_with_files]
            file_results = self.file_validator.validate_files(file_paths, level)
            
            # Match results with genomes
            for genome in genomes_with_files:
                genome_result = GenomeValidationResult(genome_id=genome.genome_id)
                genome_result.file_validation = file_results.get(genome.file_path)
                
                # Database consistency checks
                self._check_metadata_completeness(genome, genome_result)
                self._check_taxonomy_linkage(genome, genome_result)
                
                # Size consistency check
                if (genome_result.file_validation and 
                    genome_result.file_validation.is_valid and
                    genome.sequence_length and
                    genome_result.file_validation.total_length > 0):
                    
                    length_diff = abs(genome.sequence_length - genome_result.file_validation.total_length)
                    tolerance = max(1000, genome.sequence_length * 0.01)
                    
                    if length_diff > tolerance:
                        genome_result.size_matches = False
                        genome_result.issues.append(
                            f"Size mismatch: database={genome.sequence_length}, "
                            f"file={genome_result.file_validation.total_length}"
                        )
                
                results[genome.genome_id] = genome_result
        
        # Process metadata-only genomes
        for genome in genomes_metadata_only:
            genome_result = GenomeValidationResult(genome_id=genome.genome_id)
            
            # Database consistency checks
            self._check_metadata_completeness(genome, genome_result)
            self._check_taxonomy_linkage(genome, genome_result)
            
            if level == ValidationLevel.COMPREHENSIVE:
                genome_result.issues.append("Genome has no associated file")
            
            results[genome.genome_id] = genome_result
        
        return results
    
    def validate_genomes_for_export(self, export_format: str) -> Dict[str, Any]:
        """Validate genomes for specific export format requirements."""
        from ..exporters.validation import ExportRequirements, get_format_requirements
        
        # Get requirements for the export format
        requirements = get_format_requirements(export_format)
        if not requirements:
            raise ValidationError(f"Unknown export format: {export_format}")
        
        genomes = self.repository.get_all_genomes()
        validation_results = {}
        
        # Check each requirement
        for req in requirements.requirements:
            validation_results[req.name] = self._validate_export_requirement(genomes, req)
        
        # Summary
        all_requirements_met = all(
            result["status"] == "pass" 
            for result in validation_results.values()
        )
        
        return {
            "export_format": export_format,
            "requirements_met": all_requirements_met,
            "requirement_results": validation_results,
            "total_genomes": len(genomes),
            "summary": self._generate_export_validation_summary(validation_results)
        }
    
    def _check_metadata_completeness(self, genome: GenomeInfo, result: GenomeValidationResult) -> bool:
        """Check if genome metadata is complete."""
        required_fields = ['genome_id', 'tax_id']
        optional_important_fields = ['sequence_type', 'source']
        
        complete = True
        
        for field in required_fields:
            if not getattr(genome, field):
                complete = False
                result.issues.append(f"Missing required field: {field}")
        
        for field in optional_important_fields:
            if not getattr(genome, field):
                result.issues.append(f"Missing recommended field: {field}")
        
        return complete
    
    def _check_taxonomy_linkage(self, genome: GenomeInfo, result: GenomeValidationResult) -> bool:
        """Check if genome is properly linked to taxonomy."""
        try:
            # Verify tax_id exists in taxonomy tree
            tree = self.repository.load_tree()
            node = tree.get_node(genome.tax_id)
            
            if not node:
                result.issues.append(f"Taxonomy ID {genome.tax_id} not found in tree")
                return False
            
            return True
            
        except Exception as e:
            result.issues.append(f"Error checking taxonomy linkage: {e}")
            return False
    
    def _validate_export_requirement(self, genomes: List[GenomeInfo], requirement) -> Dict[str, Any]:
        """Validate a specific export requirement."""
        from ..exporters.validation import RequirementLevel
        
        if requirement.requirement_type == "genome_count":
            count = len(genomes)
            threshold = requirement.threshold
            
            # Handle both enum and mock objects
            is_required = (requirement.level == RequirementLevel.REQUIRED or 
                          (hasattr(requirement.level, 'value') and requirement.level.value == "required"))
            
            if is_required:
                status = "pass" if count >= threshold else "fail"
            else:
                status = "pass" if count >= threshold else "warn"
            
            return {
                "status": status,
                "actual": count,
                "required": threshold,
                "message": f"Found {count} genomes, need {threshold}"
            }
        
        elif requirement.requirement_type == "file_paths":
            genomes_with_files = [g for g in genomes if g.file_path]
            count = len(genomes_with_files)
            threshold = requirement.threshold
            
            # Handle both enum and mock objects
            is_required = (requirement.level == RequirementLevel.REQUIRED or 
                          (hasattr(requirement.level, 'value') and requirement.level.value == "required"))
            
            if is_required:
                status = "pass" if count >= threshold else "fail"
            else:
                status = "pass" if count >= threshold else "warn"
            
            return {
                "status": status,
                "actual": count,
                "required": threshold,
                "message": f"Found {count} genomes with files, need {threshold}"
            }
        
        elif requirement.requirement_type == "assembly_accessions":
            genomes_with_accessions = [g for g in genomes if g.assembly_accession]
            count = len(genomes_with_accessions)
            threshold = requirement.threshold
            
            if requirement.level == RequirementLevel.REQUIRED:
                status = "pass" if count >= threshold else "fail"
            else:
                status = "pass" if count >= threshold else "warn"
            
            return {
                "status": status,
                "actual": count,
                "required": threshold,
                "message": f"Found {count} genomes with assembly accessions, need {threshold}"
            }
        
        else:
            return {
                "status": "unknown",
                "message": f"Unknown requirement type: {requirement.requirement_type}"
            }
    
    def _generate_export_validation_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate summary of export validation results."""
        passed = sum(1 for r in results.values() if r["status"] == "pass")
        failed = sum(1 for r in results.values() if r["status"] == "fail")
        warnings = sum(1 for r in results.values() if r["status"] == "warn")
        
        return {
            "total_requirements": len(results),
            "passed": passed,
            "failed": failed,
            "warnings": warnings,
            "success_rate": passed / len(results) * 100 if results else 0
        }
    
    def generate_validation_report(self, results: Dict[str, GenomeValidationResult]) -> Dict[str, Any]:
        """Generate comprehensive validation report."""
        total_genomes = len(results)
        valid_genomes = sum(1 for r in results.values() if r.is_valid)
        
        # File statistics
        genomes_with_files = sum(1 for r in results.values() if r.file_validation)
        valid_files = sum(1 for r in results.values() 
                         if r.file_validation and r.file_validation.is_valid)
        
        # Issue categorization
        metadata_issues = sum(1 for r in results.values() if not r.metadata_complete)
        taxonomy_issues = sum(1 for r in results.values() if not r.taxonomy_linked)
        size_mismatches = sum(1 for r in results.values() if not r.size_matches)
        
        # Common issues
        all_issues = []
        for result in results.values():
            all_issues.extend(result.issues)
        
        report = {
            "validation_summary": {
                "total_genomes": total_genomes,
                "valid_genomes": valid_genomes,
                "invalid_genomes": total_genomes - valid_genomes,
                "validation_rate": valid_genomes / total_genomes * 100 if total_genomes > 0 else 0
            },
            "file_validation": {
                "genomes_with_files": genomes_with_files,
                "valid_files": valid_files,
                "file_validation_rate": valid_files / genomes_with_files * 100 if genomes_with_files > 0 else 0
            },
            "consistency_issues": {
                "metadata_incomplete": metadata_issues,
                "taxonomy_unlinked": taxonomy_issues,
                "size_mismatches": size_mismatches
            },
            "common_issues": self._get_common_issues(all_issues)
        }
        
        return report
    
    def _get_common_issues(self, issues: List[str], limit: int = 10) -> List[Tuple[str, int]]:
        """Get most common issues from validation results."""
        from collections import Counter
        
        issue_counts = Counter()
        for issue in issues:
            # Extract the key part of the issue
            if ":" in issue:
                key = issue.split(':')[0]
            else:
                key = issue
            issue_counts[key] += 1
        
        return issue_counts.most_common(limit)