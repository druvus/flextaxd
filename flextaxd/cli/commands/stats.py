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
            "--format",
            choices=["text", "json", "csv"],
            default="text",
            help="Output format (default: text)",
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
        from ..core.models import TaxonomicRank
        
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
