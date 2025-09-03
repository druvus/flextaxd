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

            # Load database
            with SQLiteTaxonomyRepository(args.database) as repository:
                stats = repository.get_statistics()

                if args.format == "json":
                    self._output_json(stats)
                elif args.format == "csv":
                    self._output_csv(stats)
                else:
                    self._output_text(stats, detailed=args.detailed)

            return 0

        except ValidationError as e:
            self.logger.error(f"Validation error: {e.message}")
            print(f"Error: {e.message}")
            return 1

        except DatabaseError as e:
            self.logger.error(f"Database error: {e.message}")
            print(f"Database error: {e.message}")
            return 1

    def _output_text(self, stats: Dict[str, Any], detailed: bool = False) -> None:
        """Output statistics in human-readable text format."""
        print("Taxonomy Database Statistics")
        print("=" * 40)
        print(f"Total nodes: {stats['node_count']:,}")
        print(f"Total genomes: {stats['genome_count']:,}")
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
                print(f"  {rank:15}: {count:6,} ({percentage:5.1f}%)")

        if detailed and stats["node_count"] > 0:
            print(f"\nDatabase Metrics:")
            print("-" * 20)
            # Calculate some derived metrics
            if "leaf_count" in stats and stats["node_count"] > stats["leaf_count"]:
                internal_nodes = stats["node_count"] - stats["leaf_count"]
                avg_children = (
                    stats["leaf_count"] / internal_nodes if internal_nodes > 0 else 0
                )
                print(f"Internal nodes: {internal_nodes:,}")
                print(f"Average children per internal node: {avg_children:.2f}")

            if stats["genome_count"] > 0:
                avg_genomes_per_node = stats["genome_count"] / stats["node_count"]
                print(f"Average genomes per node: {avg_genomes_per_node:.2f}")

    def _output_json(self, stats: Dict[str, Any]) -> None:
        """Output statistics in JSON format."""
        import json

        print(json.dumps(stats, indent=2))

    def _output_csv(self, stats: Dict[str, Any]) -> None:
        """Output statistics in CSV format."""
        import csv
        import sys

        writer = csv.writer(sys.stdout)

        # Basic stats
        writer.writerow(["metric", "value"])
        writer.writerow(["node_count", stats["node_count"]])
        writer.writerow(["genome_count", stats["genome_count"]])
        if "root_count" in stats:
            writer.writerow(["root_count", stats["root_count"]])
        if "leaf_count" in stats:
            writer.writerow(["leaf_count", stats["leaf_count"]])

        # Rank distribution
        if stats["rank_distribution"]:
            writer.writerow([])
            writer.writerow(["rank", "count"])
            for rank, count in stats["rank_distribution"].items():
                writer.writerow([rank, count])
