"""Validate command for comprehensive genome and database validation."""

import argparse
from pathlib import Path
from typing import Optional, Dict, Any
import logging

from .base import BaseCommand
from ...database.sqlite import SQLiteTaxonomyRepository
from ...core.exceptions import ValidationError
from ...utils.progress import (
    progress_manager, 
    create_console_reporter, 
    create_logging_reporter,
    create_silent_reporter,
    MultiProgressReporter
)


class ValidateCommand(BaseCommand):
    """Command for comprehensive validation of genome data and database integrity."""

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def register_parser(subparsers) -> argparse.ArgumentParser:
        """Register the validate command parser."""
        parser = subparsers.add_parser(
            "validate",
            help="Validate genome files and database integrity",
            description="Comprehensive validation of genome files, database consistency, and export requirements."
        )

        parser.add_argument(
            "database",
            type=str,
            help="Path to FlexTaxD database file (.ftd)"
        )

        # Validation mode selection
        mode_group = parser.add_mutually_exclusive_group()
        mode_group.add_argument(
            "--files-only",
            action="store_true", 
            help="Validate only genome files (skip database checks)"
        )
        mode_group.add_argument(
            "--consistency-only",
            action="store_true",
            help="Check only database consistency (skip file validation)"
        )
        mode_group.add_argument(
            "--export-format",
            type=str,
            help="Validate requirements for specific export format"
        )

        # Validation level
        parser.add_argument(
            "--level",
            choices=["basic", "standard", "comprehensive"],
            default="standard",
            help="Validation level (default: standard)"
        )

        # Performance options
        parser.add_argument(
            "--max-workers",
            type=int,
            default=4,
            help="Maximum number of parallel workers for file validation (default: 4)"
        )

        parser.add_argument(
            "--sample-size",
            type=int,
            help="Validate only a random sample of files (for large datasets)"
        )

        # Output options
        parser.add_argument(
            "--format",
            choices=["text", "json", "csv"],
            default="text",
            help="Output format (default: text)"
        )

        parser.add_argument(
            "--output-file",
            type=str,
            help="Write validation report to file"
        )

        parser.add_argument(
            "--show-valid",
            action="store_true",
            help="Include valid items in report (default: show only issues)"
        )

        parser.add_argument(
            "--verbose", "-v",
            action="store_true",
            help="Verbose output with detailed progress information"
        )

        # Progress reporting options
        progress_group = parser.add_argument_group("Progress reporting options")
        progress_group.add_argument(
            "--quiet", "-q", action="store_true",
            help="Suppress progress bars and non-essential output"
        )
        
        progress_group.add_argument(
            "--progress-log", type=str, metavar="FILE",
            help="Write progress information to log file"
        )
        
        progress_group.add_argument(
            "--progress-interval", type=int, default=1000, metavar="N",
            help="Progress update interval for large operations (default: 1000)"
        )
        
        progress_group.add_argument(
            "--no-eta", action="store_true",
            help="Don't show estimated time remaining in progress bars"
        )
        
        progress_group.add_argument(
            "--no-rate", action="store_true",
            help="Don't show processing rate in progress bars"
        )
        
        progress_group.add_argument(
            "--progress-width", type=int, default=50, metavar="N",
            help="Width of progress bar (default: 50)"
        )

        return parser

    def _setup_progress_reporting(self, args: argparse.Namespace) -> None:
        """Setup the progress reporting system based on command arguments."""
        reporters = []
        
        # Console reporter (unless quiet)
        if not args.quiet:
            console_reporter = create_console_reporter(
                width=args.progress_width,
                show_eta=not args.no_eta,
                show_rate=not args.no_rate
            )
            reporters.append(console_reporter)
        
        # Logging reporter (if progress log specified)
        if hasattr(args, 'progress_log') and args.progress_log:
            # Setup file logger
            log_handler = logging.FileHandler(args.progress_log)
            log_formatter = logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s'
            )
            log_handler.setFormatter(log_formatter)
            
            progress_logger = logging.getLogger('flextaxd.validation.progress')
            progress_logger.addHandler(log_handler)
            progress_logger.setLevel(logging.INFO)
            
            logging_reporter = create_logging_reporter(
                progress_logger, 
                args.progress_interval
            )
            reporters.append(logging_reporter)
        
        # If no reporters, use silent reporter
        if not reporters:
            reporters.append(create_silent_reporter())
        
        # Set up the progress manager
        if len(reporters) == 1:
            progress_manager.set_default_reporter(reporters[0])
        else:
            multi_reporter = MultiProgressReporter(reporters)
            progress_manager.set_default_reporter(multi_reporter)

    def execute(self, args: argparse.Namespace) -> Optional[int]:
        """Execute the validate command."""
        try:
            # Validate database exists
            self._validate_database_path(args.database, must_exist=True)

            # Setup progress reporting system
            self._setup_progress_reporting(args)

            if args.verbose:
                self.logger.setLevel(logging.DEBUG)
            
            if not args.quiet:
                print("Starting comprehensive validation...")

            # Import validation modules
            from flextaxd.validation import (
                FileValidator, GenomeValidator, ConsistencyChecker, ValidationLevel
            )

            level_map = {
                "basic": ValidationLevel.BASIC,
                "standard": ValidationLevel.STANDARD,
                "comprehensive": ValidationLevel.COMPREHENSIVE
            }
            validation_level = level_map[args.level]

            with SQLiteTaxonomyRepository(args.database) as repository:
                
                if args.export_format:
                    # Validate for specific export format
                    if not args.quiet:
                        print(f"Validating requirements for {args.export_format} export...")
                    
                    validator = GenomeValidator(repository, max_workers=args.max_workers)
                    total_genomes = repository.get_genome_count()
                    
                    with progress_manager.operation(
                        total=total_genomes,
                        description=f"Validating for {args.export_format} export"
                    ) as progress:
                        
                        # Progress simulation for export validation
                        progress.update(total_genomes // 4, "Checking format requirements")
                        progress.update(total_genomes // 2, "Validating genome metadata")
                        progress.update(3 * total_genomes // 4, "Verifying file dependencies")
                        
                        results = validator.validate_genomes_for_export(args.export_format)
                        
                        progress.update(total_genomes, "Export validation complete")
                    
                    self._output_export_validation(results, args)
                    
                elif args.consistency_only:
                    # Database consistency check only
                    if not args.quiet:
                        print("Checking database consistency...")
                    
                    checker = ConsistencyChecker(repository, max_workers=args.max_workers)
                    total_nodes = repository.get_node_count()
                    total_genomes = repository.get_genome_count()
                    
                    with progress_manager.operation(
                        total=total_nodes + total_genomes,
                        description="Checking database consistency"
                    ) as progress:
                        
                        # Simulate progress for different consistency checks
                        progress.update(total_nodes // 4, "Checking taxonomy integrity")
                        progress.update(total_nodes // 2, "Checking genome linkages")  
                        progress.update(3 * total_nodes // 4, "Detecting duplicates")
                        
                        results = checker.check_full_consistency()
                        
                        progress.update(total_nodes + total_genomes, "Consistency check complete")
                    
                    self._output_consistency_results(results, args)
                    
                elif args.files_only:
                    # File validation only
                    if not args.quiet:
                        print("Validating genome files...")
                    
                    validator = GenomeValidator(repository, max_workers=args.max_workers)
                    
                    # Get total genome count for progress tracking
                    total_genomes = repository.get_genome_count()
                    
                    with progress_manager.operation(
                        total=total_genomes,
                        description="Validating genome files"
                    ) as progress:
                        
                        # Create progress callback for validator
                        def progress_callback(completed, total):
                            progress.update(completed, f"Validated {completed}/{total} genomes")
                        
                        results = validator.validate_all_genomes(
                            level=validation_level,
                            progress_callback=progress_callback
                        )
                    
                    validation_report = validator.generate_validation_report(results)
                    self._output_file_validation(validation_report, results, args)
                    
                else:
                    # Full validation (default)
                    if not args.quiet:
                        print("Running comprehensive validation (files + consistency)...")
                    
                    # Get total genome count for progress tracking
                    total_genomes = repository.get_genome_count()
                    
                    # Step 1: File validation with progress
                    with progress_manager.operation(
                        total=total_genomes,
                        description="Validating genome files"
                    ) as progress:
                        
                        validator = GenomeValidator(repository, max_workers=args.max_workers)
                        
                        def file_progress_callback(completed, total):
                            progress.update(completed, f"Validated {completed}/{total} genomes")
                        
                        file_results = validator.validate_all_genomes(
                            level=validation_level,
                            progress_callback=file_progress_callback
                        )
                    
                    # Step 2: Consistency check with progress
                    total_nodes = repository.get_node_count()
                    
                    with progress_manager.operation(
                        total=total_nodes + total_genomes,  # Estimate operations
                        description="Checking database consistency"
                    ) as progress:
                        
                        checker = ConsistencyChecker(repository, max_workers=args.max_workers)
                        
                        # Simulate progress for consistency checking
                        # (In real implementation, ConsistencyChecker would support progress callbacks)
                        progress.update(total_nodes // 4, "Checking taxonomy integrity")
                        progress.update(total_nodes // 2, "Checking genome linkages")
                        progress.update(3 * total_nodes // 4, "Detecting duplicates")
                        
                        consistency_results = checker.check_full_consistency()
                        
                        progress.update(total_nodes + total_genomes, "Consistency check complete")
                    
                    # Combined report
                    file_report = validator.generate_validation_report(file_results)
                    combined_results = {
                        "file_validation": file_report,
                        "consistency_check": consistency_results,
                        "overall_status": self._calculate_overall_status(file_report, consistency_results)
                    }
                    
                    self._output_full_validation(combined_results, args)

            return 0

        except ValidationError as e:
            self.logger.error(f"Validation error: {e.message}")
            print(f"Error: {e.message}")
            return 1

        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
            print(f"Unexpected error: {e}")
            return 1

    def _output_export_validation(self, results: Dict[str, Any], args: argparse.Namespace) -> None:
        """Output export format validation results."""
        if args.format == "json":
            import json
            output = json.dumps(results, indent=2, default=str)
        elif args.format == "csv":
            output = self._format_export_csv(results)
        else:
            output = self._format_export_text(results)
        
        self._write_output(output, args.output_file)

    def _output_consistency_results(self, results: Dict[str, Any], args: argparse.Namespace) -> None:
        """Output consistency check results."""
        if args.format == "json":
            import json
            output = json.dumps(results, indent=2, default=str)
        elif args.format == "csv":
            output = self._format_consistency_csv(results)
        else:
            output = self._format_consistency_text(results)
        
        self._write_output(output, args.output_file)

    def _output_file_validation(self, report: Dict[str, Any], detailed_results: Dict[str, Any], args: argparse.Namespace) -> None:
        """Output file validation results."""
        if args.format == "json":
            import json
            if args.show_valid:
                output = json.dumps({"summary": report, "details": detailed_results}, indent=2, default=str)
            else:
                output = json.dumps(report, indent=2, default=str)
        elif args.format == "csv":
            output = self._format_file_validation_csv(report, detailed_results, args.show_valid)
        else:
            output = self._format_file_validation_text(report, detailed_results, args.show_valid)
        
        self._write_output(output, args.output_file)

    def _output_full_validation(self, results: Dict[str, Any], args: argparse.Namespace) -> None:
        """Output comprehensive validation results."""
        if args.format == "json":
            import json
            output = json.dumps(results, indent=2, default=str)
        elif args.format == "csv":
            output = self._format_full_validation_csv(results)
        else:
            output = self._format_full_validation_text(results)
        
        self._write_output(output, args.output_file)

    def _format_export_text(self, results: Dict[str, Any]) -> str:
        """Format export validation results as text."""
        output = []
        output.append(f"Export Format Validation: {results['export_format']}")
        output.append("=" * 50)
        
        if results["requirements_met"]:
            output.append("✓ All requirements met - export should succeed")
        else:
            output.append("✗ Requirements not met - export may fail")
        
        output.append(f"\nTotal genomes: {results['total_genomes']:,}")
        
        summary = results.get("summary", {})
        output.append(f"Requirements passed: {summary.get('passed', 0)}")
        output.append(f"Requirements failed: {summary.get('failed', 0)}")
        output.append(f"Requirements warned: {summary.get('warnings', 0)}")
        output.append(f"Success rate: {summary.get('success_rate', 0):.1f}%")
        
        output.append("\nRequirement Details:")
        output.append("-" * 20)
        for req_name, req_result in results.get("requirement_results", {}).items():
            status_symbol = "✓" if req_result["status"] == "pass" else ("⚠" if req_result["status"] == "warn" else "✗")
            output.append(f"{status_symbol} {req_name}: {req_result.get('message', 'No details')}")
        
        return "\n".join(output)

    def _format_consistency_text(self, results: Dict[str, Any]) -> str:
        """Format consistency check results as text."""
        output = []
        output.append("Database Consistency Report")
        output.append("=" * 50)
        
        summary = results.get("summary", {})
        score = results.get("consistency_score", 0)
        
        if score >= 95:
            status = "Excellent"
        elif score >= 80:
            status = "Good"
        elif score >= 60:
            status = "Fair"
        else:
            status = "Poor"
        
        output.append(f"Overall consistency: {status} ({score:.1f}/100)")
        output.append(f"Total issues found: {summary.get('total_issues', 0)}")
        output.append(f"  Errors: {summary.get('errors', 0)}")
        output.append(f"  Warnings: {summary.get('warnings', 0)}")
        output.append(f"  Info: {summary.get('info', 0)}")
        
        # Show issues by severity
        issues_by_severity = results.get("issues_by_severity", {})
        
        if issues_by_severity.get("errors"):
            output.append(f"\nErrors ({len(issues_by_severity['errors'])}):")
            output.append("-" * 20)
            for issue in issues_by_severity["errors"][:10]:
                output.append(f"  • {issue['description']}")
            if len(issues_by_severity["errors"]) > 10:
                output.append(f"  ... and {len(issues_by_severity['errors']) - 10} more errors")
        
        return "\n".join(output)

    def _format_file_validation_text(self, report: Dict[str, Any], detailed_results: Dict[str, Any], show_valid: bool) -> str:
        """Format file validation results as text."""
        output = []
        output.append("File Validation Report")
        output.append("=" * 50)
        
        summary = report.get("validation_summary", {})
        output.append(f"Total genomes: {summary.get('total_genomes', 0):,}")
        output.append(f"Valid genomes: {summary.get('valid_genomes', 0):,}")
        output.append(f"Invalid genomes: {summary.get('invalid_genomes', 0):,}")
        output.append(f"Validation rate: {summary.get('validation_rate', 0):.1f}%")
        
        file_validation = report.get("file_validation", {})
        if file_validation:
            output.append(f"\nFile Status:")
            output.append(f"  Genomes with files: {file_validation.get('genomes_with_files', 0):,}")
            output.append(f"  Valid files: {file_validation.get('valid_files', 0):,}")
            output.append(f"  File validation rate: {file_validation.get('file_validation_rate', 0):.1f}%")
        
        consistency = report.get("consistency_issues", {})
        if consistency:
            output.append(f"\nConsistency Issues:")
            output.append(f"  Metadata incomplete: {consistency.get('metadata_incomplete', 0):,}")
            output.append(f"  Taxonomy unlinked: {consistency.get('taxonomy_unlinked', 0):,}")
            output.append(f"  Size mismatches: {consistency.get('size_mismatches', 0):,}")
        
        if not show_valid:
            # Show problematic items only
            invalid_genomes = [
                (genome_id, result) for genome_id, result in detailed_results.items() 
                if not result.is_valid
            ]
            
            if invalid_genomes:
                output.append(f"\nProblematic Genomes ({len(invalid_genomes)}):")
                output.append("-" * 30)
                for genome_id, result in invalid_genomes[:20]:  # Limit display
                    issues = "; ".join(result.issues[:3])  # Show first 3 issues
                    output.append(f"  {genome_id}: {issues}")
                if len(invalid_genomes) > 20:
                    output.append(f"  ... and {len(invalid_genomes) - 20} more problematic genomes")
        
        return "\n".join(output)

    def _format_full_validation_text(self, results: Dict[str, Any]) -> str:
        """Format comprehensive validation results as text."""
        output = []
        output.append("Comprehensive Validation Report")
        output.append("=" * 50)
        
        overall = results.get("overall_status", {})
        output.append(f"Overall Status: {overall.get('status', 'Unknown')}")
        output.append(f"Overall Score: {overall.get('score', 0):.1f}/100")
        
        # File validation summary
        file_val = results.get("file_validation", {})
        file_summary = file_val.get("validation_summary", {})
        output.append(f"\nFile Validation:")
        output.append(f"  Total genomes: {file_summary.get('total_genomes', 0):,}")
        output.append(f"  Valid: {file_summary.get('valid_genomes', 0):,}")
        output.append(f"  Invalid: {file_summary.get('invalid_genomes', 0):,}")
        output.append(f"  Success rate: {file_summary.get('validation_rate', 0):.1f}%")
        
        # Consistency check summary
        consistency = results.get("consistency_check", {})
        consistency_summary = consistency.get("summary", {})
        output.append(f"\nDatabase Consistency:")
        output.append(f"  Total issues: {consistency_summary.get('total_issues', 0)}")
        output.append(f"  Errors: {consistency_summary.get('errors', 0)}")
        output.append(f"  Warnings: {consistency_summary.get('warnings', 0)}")
        output.append(f"  Score: {consistency.get('consistency_score', 0):.1f}/100")
        
        return "\n".join(output)

    def _format_export_csv(self, results: Dict[str, Any]) -> str:
        """Format export validation as CSV."""
        import csv
        import io
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        writer.writerow(["metric", "value"])
        writer.writerow(["export_format", results["export_format"]])
        writer.writerow(["requirements_met", results["requirements_met"]])
        writer.writerow(["total_genomes", results["total_genomes"]])
        
        summary = results.get("summary", {})
        writer.writerow(["requirements_passed", summary.get("passed", 0)])
        writer.writerow(["requirements_failed", summary.get("failed", 0)])
        writer.writerow(["success_rate", summary.get("success_rate", 0)])
        
        return output.getvalue()

    def _format_consistency_csv(self, results: Dict[str, Any]) -> str:
        """Format consistency results as CSV."""
        import csv
        import io
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        writer.writerow(["metric", "value"])
        
        summary = results.get("summary", {})
        writer.writerow(["total_issues", summary.get("total_issues", 0)])
        writer.writerow(["errors", summary.get("errors", 0)])
        writer.writerow(["warnings", summary.get("warnings", 0)])
        writer.writerow(["info", summary.get("info", 0)])
        writer.writerow(["consistency_score", results.get("consistency_score", 0)])
        writer.writerow(["total_nodes", results.get("total_nodes", 0)])
        writer.writerow(["total_genomes", results.get("total_genomes", 0)])
        
        return output.getvalue()

    def _format_file_validation_csv(self, report: Dict[str, Any], detailed_results: Dict[str, Any], show_valid: bool) -> str:
        """Format file validation as CSV."""
        import csv
        import io
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        writer.writerow(["metric", "value"])
        
        summary = report.get("validation_summary", {})
        writer.writerow(["total_genomes", summary.get("total_genomes", 0)])
        writer.writerow(["valid_genomes", summary.get("valid_genomes", 0)])
        writer.writerow(["invalid_genomes", summary.get("invalid_genomes", 0)])
        writer.writerow(["validation_rate", summary.get("validation_rate", 0)])
        
        return output.getvalue()

    def _format_full_validation_csv(self, results: Dict[str, Any]) -> str:
        """Format comprehensive validation as CSV."""
        import csv
        import io
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        writer.writerow(["category", "metric", "value"])
        
        overall = results.get("overall_status", {})
        writer.writerow(["overall", "status", overall.get("status", "Unknown")])
        writer.writerow(["overall", "score", overall.get("score", 0)])
        
        # File validation metrics
        file_val = results.get("file_validation", {})
        file_summary = file_val.get("validation_summary", {})
        writer.writerow(["file_validation", "total_genomes", file_summary.get("total_genomes", 0)])
        writer.writerow(["file_validation", "valid_genomes", file_summary.get("valid_genomes", 0)])
        writer.writerow(["file_validation", "validation_rate", file_summary.get("validation_rate", 0)])
        
        # Consistency metrics
        consistency = results.get("consistency_check", {})
        consistency_summary = consistency.get("summary", {})
        writer.writerow(["consistency", "total_issues", consistency_summary.get("total_issues", 0)])
        writer.writerow(["consistency", "errors", consistency_summary.get("errors", 0)])
        writer.writerow(["consistency", "score", consistency.get("consistency_score", 0)])
        
        return output.getvalue()

    def _calculate_overall_status(self, file_report: Dict[str, Any], consistency_report: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate overall validation status."""
        file_summary = file_report.get("validation_summary", {})
        file_rate = file_summary.get("validation_rate", 0)
        
        consistency_score = consistency_report.get("consistency_score", 0)
        
        # Weighted average (60% file validation, 40% consistency)
        overall_score = (file_rate * 0.6) + (consistency_score * 0.4)
        
        if overall_score >= 95:
            status = "Excellent"
        elif overall_score >= 80:
            status = "Good"
        elif overall_score >= 60:
            status = "Fair"
        else:
            status = "Poor"
        
        return {
            "status": status,
            "score": overall_score,
            "file_validation_rate": file_rate,
            "consistency_score": consistency_score
        }

    def _write_output(self, content: str, output_file: Optional[str]) -> None:
        """Write output to file or stdout."""
        if output_file:
            try:
                Path(output_file).write_text(content)
                print(f"Validation report written to: {output_file}")
            except Exception as e:
                print(f"Error writing to file {output_file}: {e}")
                print(content)
        else:
            print(content)