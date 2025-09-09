"""Stats command for displaying taxonomy database statistics."""

import argparse
from typing import Optional, Dict, Any

from .base import BaseCommand
from ...core.exceptions import ValidationError, DatabaseError
from ...database.sqlite import SQLiteTaxonomyRepository


class StatsCommand(BaseCommand):
    """Command to display database statistics."""

    @classmethod
    def register_parser(
        cls, subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]"
    ) -> argparse.ArgumentParser:
        """Register the stats command parser."""
        parser = subparsers.add_parser(
            "stats",
            help="Display database statistics",
            description="Display detailed statistics about a taxonomy database",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  flextaxd stats --database my_db.ftd
  flextaxd stats --database my_db.ftd --detailed
            """,
        )

        parser.add_argument(
            "--database",
            "-d",
            type=str,
            required=True,
            help="Database file path (.ftd)",
        )

        parser.add_argument(
            "--detailed", action="store_true", help="Show detailed statistics"
        )

        parser.add_argument(
            "--validate-files",
            action="store_true",
            default=True,
            help="Validate genome file paths (default: True, can be slow for large datasets)",
        )

        parser.add_argument(
            "--skip-file-validation",
            action="store_true",
            help="Skip genome file validation for faster statistics (overrides --validate-files)",
        )

        parser.add_argument(
            "--validation-level",
            choices=["basic", "standard", "comprehensive"],
            default="standard",
            help="File validation level (default: standard)",
        )

        parser.add_argument(
            "--consistency-check",
            action="store_true",
            help="Run comprehensive database consistency check",
        )

        parser.add_argument(
            "--format",
            choices=["text", "json", "csv"],
            default="text",
            help="Output format (default: text)",
        )

        parser.add_argument(
            "--missing-files",
            action="store_true",
            help="Analyze and report missing files based on imported accessions",
        )

        return parser

    def execute(self, args: argparse.Namespace) -> Optional[int]:
        """Execute the stats command."""
        try:
            # Validate database exists
            self._validate_database_path(args.database, must_exist=True)

            # Determine file validation setting
            validate_files = args.validate_files and not args.skip_file_validation
            
            if args.skip_file_validation:
                self.logger.info("Skipping genome file validation for faster statistics")

            # Load database
            with SQLiteTaxonomyRepository(args.database) as repository:
                if args.consistency_check:
                    # Run comprehensive consistency check
                    from ...validation import ConsistencyChecker
                    checker = ConsistencyChecker(repository)
                    consistency_report = checker.check_full_consistency()
                    self._output_consistency_report(consistency_report, args.format)
                    return 0

                # Handle missing files analysis
                if args.missing_files:
                    missing_analysis = repository.get_missing_files_analysis()
                    self._output_missing_files_analysis(missing_analysis, args.format)
                    return 0
                
                # Regular statistics with optional enhanced validation
                if validate_files and args.validation_level != "basic":
                    # Use enhanced validation system
                    from ...validation import GenomeValidator, ValidationLevel
                    
                    level_map = {
                        "basic": ValidationLevel.BASIC,
                        "standard": ValidationLevel.STANDARD, 
                        "comprehensive": ValidationLevel.COMPREHENSIVE
                    }
                    validation_level = level_map[args.validation_level]
                    
                    validator = GenomeValidator(repository)
                    
                    # Progress callback for large datasets
                    def progress_callback(completed, total):
                        if total > 100:  # Only show progress for large datasets
                            print(f"Validating files... {completed}/{total} ({completed/total*100:.1f}%)", end='\r')
                    
                    validation_results = validator.validate_all_genomes(
                        level=validation_level, 
                        progress_callback=progress_callback
                    )
                    
                    if len(validation_results) > 100:
                        print()  # Clear progress line
                    
                    # Generate enhanced stats with validation data
                    stats = repository.get_statistics(validate_files=False)  # Skip basic validation
                    validation_report = validator.generate_validation_report(validation_results)
                    stats["enhanced_validation"] = validation_report
                    
                else:
                    # Use basic statistics
                    stats = repository.get_statistics(validate_files=validate_files)

                if args.format == "json":
                    self._output_json(stats)
                elif args.format == "csv":
                    self._output_csv(stats)
                else:
                    self._output_text(stats, detailed=args.detailed, validate_files=validate_files)

            return 0

        except ValidationError as e:
            self.logger.error(f"Validation error: {e.message}")
            print(f"Error: {e.message}")
            return 1

        except DatabaseError as e:
            self.logger.error(f"Database error: {e.message}")
            print(f"Database error: {e.message}")
            return 1
        
        except KeyboardInterrupt:
            self.logger.info("Statistics generation interrupted by user")
            print("\nOperation interrupted by user")
            return 1
            
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
            print(f"Error: {e}")
            return 1

    def _output_text(self, stats: Dict[str, Any], detailed: bool = False, validate_files: bool = True) -> None:
        """Output statistics in human-readable text format."""
        print("Taxonomy Database Statistics")
        print("=" * 40)
        print(f"Total nodes: {stats['node_count']:,}")
        print(f"Total genomes: {stats['genome_count']:,}")
        
        # Enhanced genome statistics
        if stats["genome_count"] > 0:
            self._output_genome_statistics(stats, detailed, validate_files)
        
        if "root_count" in stats:
            print(f"Root nodes: {stats['root_count']:,}")
        if "leaf_count" in stats:
            print(f"Leaf nodes: {stats['leaf_count']:,}")

        if stats["rank_distribution"]:
            print("\nRank Distribution:")
            print("-" * 20)
            total_ranked = sum(stats["rank_distribution"].values())
            for rank, count in sorted(
                stats["rank_distribution"].items(), key=lambda x: x[1], reverse=True
            ):
                percentage = (count / total_ranked) * 100 if total_ranked > 0 else 0
                print(f"  {rank.value:15}: {count:6,} ({percentage:5.1f}%)")

        if detailed and stats["node_count"] > 0:
            print(f"\nDatabase Metrics:")
            print("-" * 20)
            # Calculate some derived metrics
            if "leaf_nodes" in stats:
                leaf_count = len(stats["leaf_nodes"])
                if stats["node_count"] > leaf_count:
                    internal_nodes = stats["node_count"] - leaf_count
                    avg_children = (
                        leaf_count / internal_nodes if internal_nodes > 0 else 0
                    )
                    print(f"Internal nodes: {internal_nodes:,}")
                    print(f"Average children per internal node: {avg_children:.2f}")

            if stats["genome_count"] > 0:
                avg_genomes_per_node = stats["genome_count"] / stats["node_count"]
                print(f"Average genomes per node: {avg_genomes_per_node:.2f}")

    def _output_genome_statistics(self, stats: Dict[str, Any], detailed: bool, validate_files: bool) -> None:
        """Output detailed genome statistics."""
        print("\nGenome Statistics:")
        print("-" * 20)
        
        # File availability
        if "genomes_with_files" in stats:
            print(f"  With file paths: {stats['genomes_with_files']:,}")
            print(f"  Metadata only:   {stats['genomes_metadata_only']:,}")
        
        # File validation (if performed)
        if validate_files and "genome_file_validation" in stats:
            validation = stats["genome_file_validation"]
            total_files = sum(validation.values())
            if total_files > 0:
                print(f"\nFile Validation:")
                print(f"  Accessible: {validation['accessible']:,} ({validation['accessible']/total_files*100:.1f}%)")
                print(f"  Missing:    {validation['missing']:,} ({validation['missing']/total_files*100:.1f}%)")
                print(f"  Invalid:    {validation['invalid']:,} ({validation['invalid']/total_files*100:.1f}%)")
        elif not validate_files:
            print("  File validation: Skipped (use --validate-files to enable)")
        
        # Genome size distribution
        if "genome_size_distribution" in stats:
            size_stats = stats["genome_size_distribution"]
            if size_stats["count"] > 0:
                print(f"\nGenome Size Distribution ({size_stats['count']:,} genomes with size data):")
                print(f"  Min:    {size_stats['min']:,} bp")
                print(f"  Max:    {size_stats['max']:,} bp") 
                print(f"  Mean:   {size_stats['avg']:,.0f} bp")
                print(f"  Median: {size_stats['median']:,} bp")
            else:
                print(f"\nGenome Size Distribution: No size data available")
        
        # Sequence type breakdown
        if "sequence_type_breakdown" in stats and stats["sequence_type_breakdown"]:
            print(f"\nSequence Type Breakdown:")
            for seq_type, count in sorted(
                stats["sequence_type_breakdown"].items(), key=lambda x: x[1], reverse=True
            ):
                percentage = (count / stats["genome_count"]) * 100
                print(f"  {seq_type:15}: {count:6,} ({percentage:5.1f}%)")
        
        # Source distribution  
        if "source_distribution" in stats and stats["source_distribution"]:
            print(f"\nSource Distribution:")
            for source, count in sorted(
                stats["source_distribution"].items(), key=lambda x: x[1], reverse=True
            ):
                percentage = (count / stats["genome_count"]) * 100
                print(f"  {source:15}: {count:6,} ({percentage:5.1f}%)")

    def _output_json(self, stats: Dict[str, Any]) -> None:
        """Output statistics in JSON format."""
        import json

        # Convert TaxonomicRank enum values to strings for JSON serialization
        json_stats = self._prepare_stats_for_json(stats)
        print(json.dumps(json_stats, indent=2))

    def _prepare_stats_for_json(self, stats: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare statistics for JSON output by converting enum values."""
        from ...core.models import TaxonomicRank
        
        json_stats = {}
        for key, value in stats.items():
            if key == "rank_distribution" and isinstance(value, dict):
                # Convert TaxonomicRank enum keys to strings
                json_stats[key] = {
                    rank.value if hasattr(rank, 'value') else str(rank): count
                    for rank, count in value.items()
                }
            else:
                json_stats[key] = value
        
        return json_stats

    def _output_csv(self, stats: Dict[str, Any]) -> None:
        """Output statistics in CSV format."""
        import csv
        import sys

        writer = csv.writer(sys.stdout)

        # Basic stats
        writer.writerow(["metric", "value"])
        writer.writerow(["node_count", stats["node_count"]])
        writer.writerow(["genome_count", stats["genome_count"]])
        
        # Enhanced genome stats
        if "genomes_with_files" in stats:
            writer.writerow(["genomes_with_files", stats["genomes_with_files"]])
            writer.writerow(["genomes_metadata_only", stats["genomes_metadata_only"]])
        
        if "genome_file_validation" in stats:
            validation = stats["genome_file_validation"]
            writer.writerow(["genome_files_accessible", validation.get("accessible", 0)])
            writer.writerow(["genome_files_missing", validation.get("missing", 0)])
            writer.writerow(["genome_files_invalid", validation.get("invalid", 0)])
        
        if "genome_size_distribution" in stats:
            size_stats = stats["genome_size_distribution"]
            writer.writerow(["genomes_with_size_data", size_stats["count"]])
            if size_stats["count"] > 0:
                writer.writerow(["genome_size_min", size_stats["min"]])
                writer.writerow(["genome_size_max", size_stats["max"]])
                writer.writerow(["genome_size_avg", f"{size_stats['avg']:.0f}"])
                writer.writerow(["genome_size_median", size_stats["median"]])
        
        if "root_nodes" in stats:
            writer.writerow(["root_count", len(stats["root_nodes"])])
        if "leaf_nodes" in stats:
            writer.writerow(["leaf_count", len(stats["leaf_nodes"])])

        # Rank distribution
        if stats["rank_distribution"]:
            writer.writerow([])
            writer.writerow(["rank", "count"])
            for rank, count in stats["rank_distribution"].items():
                rank_name = rank.value if hasattr(rank, 'value') else str(rank)
                writer.writerow([rank_name, count])

        # Sequence type breakdown
        if "sequence_type_breakdown" in stats and stats["sequence_type_breakdown"]:
            writer.writerow([])
            writer.writerow(["sequence_type", "count"])
            for seq_type, count in stats["sequence_type_breakdown"].items():
                writer.writerow([seq_type, count])

        # Source distribution
        if "source_distribution" in stats and stats["source_distribution"]:
            writer.writerow([])
            writer.writerow(["source", "count"])
            for source, count in stats["source_distribution"].items():
                writer.writerow([source, count])
    
    def _output_consistency_report(self, report: Dict[str, Any], format_type: str = "text") -> None:
        """Output consistency check results."""
        if format_type == "json":
            import json
            print(json.dumps(report, indent=2, default=str))
        elif format_type == "csv":
            import csv
            import sys
            
            writer = csv.writer(sys.stdout)
            writer.writerow(["metric", "value"])
            
            summary = report.get("summary", {})
            writer.writerow(["total_issues", summary.get("total_issues", 0)])
            writer.writerow(["errors", summary.get("errors", 0)])
            writer.writerow(["warnings", summary.get("warnings", 0)])
            writer.writerow(["info", summary.get("info", 0)])
            writer.writerow(["consistency_score", report.get("consistency_score", 0)])
            writer.writerow(["total_nodes", report.get("total_nodes", 0)])
            writer.writerow(["total_genomes", report.get("total_genomes", 0)])
            
        else:
            # Text format
            print("Database Consistency Report")
            print("=" * 50)
            
            summary = report.get("summary", {})
            print(f"Total issues found: {summary.get('total_issues', 0)}")
            print(f"  Errors: {summary.get('errors', 0)}")
            print(f"  Warnings: {summary.get('warnings', 0)}")
            print(f"  Info: {summary.get('info', 0)}")
            print(f"Consistency score: {report.get('consistency_score', 0):.1f}/100")
            
            print(f"\nDatabase overview:")
            print(f"  Total taxonomy nodes: {report.get('total_nodes', 0):,}")
            print(f"  Total genomes: {report.get('total_genomes', 0):,}")
            
            # Show issues by severity
            issues_by_severity = report.get("issues_by_severity", {})
            
            if issues_by_severity.get("errors"):
                print(f"\nErrors ({len(issues_by_severity['errors'])}):")
                print("-" * 20)
                for issue in issues_by_severity["errors"][:10]:  # Limit display
                    print(f"  • {issue['description']}")
                if len(issues_by_severity["errors"]) > 10:
                    print(f"  ... and {len(issues_by_severity['errors']) - 10} more errors")
            
            if issues_by_severity.get("warnings"):
                print(f"\nWarnings ({len(issues_by_severity['warnings'])}):")
                print("-" * 20)
                for issue in issues_by_severity["warnings"][:5]:  # Limit display
                    print(f"  • {issue['description']}")
                if len(issues_by_severity["warnings"]) > 5:
                    print(f"  ... and {len(issues_by_severity['warnings']) - 5} more warnings")
            
            # Show category breakdown
            categories = report.get("issues_by_category", {})
            if categories:
                print(f"\nIssues by category:")
                print("-" * 20)
                for category, issues in categories.items():
                    print(f"  {category}: {len(issues)} issues")
    
    def _output_missing_files_analysis(self, analysis: Dict[str, Any], format_type: str = "text") -> None:
        """Output missing files analysis results."""
        if format_type == "json":
            import json
            print(json.dumps(analysis, indent=2, default=str))
        elif format_type == "csv":
            import csv
            import sys
            
            writer = csv.writer(sys.stdout)
            writer.writerow(["type", "accession", "tax_id", "issue"])
            
            # Missing files
            missing = analysis.get("missing_files", {})
            for file_type, files in missing.items():
                for file_info in files:
                    writer.writerow([
                        file_type, 
                        file_info.get("accession", ""),
                        file_info.get("tax_id", ""),
                        "missing_file"
                    ])
            
            # File issues
            for issue in analysis.get("file_issues", []):
                writer.writerow([
                    "file_issue",
                    issue.get("accession", ""),
                    issue.get("tax_id", ""),
                    issue.get("issue", "")
                ])
                
        else:
            # Text format
            print("Missing Files Analysis")
            print("=" * 50)
            
            summary = analysis.get("summary", {})
            print(f"Total accessions imported: {summary.get('total_accessions', 0):,}")
            print(f"Genome accessions: {summary.get('genome_accessions', 0):,}")
            print(f"Existing genome files: {summary.get('existing_genome_files', 0):,}")
            print(f"Missing genome files: {summary.get('missing_genome_files', 0):,}")
            print(f"File issues: {summary.get('file_issues', 0):,}")
            
            # Calculate percentages if we have data
            if summary.get('genome_accessions', 0) > 0:
                coverage = (summary.get('existing_genome_files', 0) / summary.get('genome_accessions', 1)) * 100
                print(f"File coverage: {coverage:.1f}%")
            
            # Show missing files breakdown
            missing = analysis.get("missing_files", {})
            if missing.get("genome"):
                print(f"\nMissing genome files ({len(missing['genome'])}):")
                print("-" * 30)
                for i, file_info in enumerate(missing["genome"][:10]):  # Show first 10
                    print(f"  • {file_info['accession']} (tax_id: {file_info['tax_id']})")
                if len(missing["genome"]) > 10:
                    print(f"  ... and {len(missing['genome']) - 10} more missing files")
            
            # Show file issues
            file_issues = analysis.get("file_issues", [])
            if file_issues:
                print(f"\nFile Issues ({len(file_issues)}):")
                print("-" * 20)
                for i, issue in enumerate(file_issues[:5]):  # Show first 5
                    print(f"  • {issue['accession']}: {issue['issue']} ({issue['file_path']})")
                if len(file_issues) > 5:
                    print(f"  ... and {len(file_issues) - 5} more issues")
            
            # Show recommendations
            print(f"\nRecommendations:")
            print("-" * 15)
            if summary.get('missing_genome_files', 0) > 0:
                print(f"  1. Download missing files: flextaxd download --missing --database <db_file>")
                print(f"  2. List missing files: flextaxd list-missing --type genome --database <db_file>")
            
            if summary.get('file_issues', 0) > 0:
                print(f"  3. Validate and repair files: flextaxd validate-files --repair --database <db_file>")
                
            if summary.get('missing_genome_files', 0) == 0 and summary.get('file_issues', 0) == 0:
                print("  ✅ All imported accessions have corresponding files!")
