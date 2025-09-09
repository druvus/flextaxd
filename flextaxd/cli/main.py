"""Main CLI entry point for FlexTaxD."""

import sys
import argparse
import logging
from typing import Optional, List, Dict
from pathlib import Path

from ..core.exceptions import FlexTaxDError
from ..utils.logging_config import setup_logging
from .commands import (
    CreateCommand,
    ExportCommand,
    StatsCommand,
    VisualizeCommand,
    PurgeCommand,
    ValidateCommand,
    ImportAccessionsCommand,
    DownloadCommand,
    RegisterCommand,
    ListMissingCommand,
    ValidateFilesCommand,
    AssignAccessionsCommand,
)
from .commands.export_mappings import ExportMappingsCommand
from .commands.add_node import AddNodeCommand
from .commands.import_tree import ImportTreeCommand
from .commands.add_genome import AddGenomeCommand
from .commands.base import BaseCommand


def create_parser() -> argparse.ArgumentParser:
    """Create the main argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="flextaxd",
        description="Flexible modification of taxonomy databases",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Command Categories:
  DATABASE OPERATIONS:
    create              Create taxonomy database from various sources
    stats               Display database statistics and analysis  
    validate            Validate database integrity and files
    purge               Remove nodes without data
    
  DATA MANAGEMENT:
    download            Download genomes by accession
    import-accessions   Import accession mappings
    register            Register sequence files
    assign-accessions   Auto-assign accessions
    
  NODE OPERATIONS:
    add-node            Add single taxonomy node
    add-genome          Add genome to node
    import-tree         Import taxonomy tree
    
  EXPORT & ANALYSIS:
    export              Export to classification tools
    export-mappings     Export mapping files
    visualize           Generate visualizations
    
  FILE OPERATIONS:
    validate-files      Validate file integrity
    list-missing        List missing files

Examples:
  # Database creation and management
  flextaxd create --input taxonomy.tsv --database my_db.ftd
  flextaxd stats --database my_db.ftd --detailed
  flextaxd validate --database my_db.ftd --level comprehensive
  
  # Data management
  flextaxd download --database my_db.ftd --missing --type genome --output-dir genomes/
  flextaxd import-accessions --mapping-file acc2taxid.txt --database my_db.ftd
  
  # Export operations  
  flextaxd export --database my_db.ftd --classifier kraken2 --output kraken2_db/
  flextaxd export-mappings --database my_db.ftd --format accession2taxid --output acc2taxid.txt
  flextaxd download --accession-file genomes.txt --database my_db.ftd --output-dir ./genomes
  flextaxd register --genomes /data/*.fna --proteins /data/proteins/*.faa --database my_db.ftd
  
  # Export and validation
  flextaxd export --database my_db.ftd --classifier kraken2 --output ./kraken2_db/
  flextaxd export-mappings --database my_db.ftd --format accession2taxid --output acc2taxid.txt
  flextaxd validate --database my_db.ftd --level comprehensive
  flextaxd visualize --database my_db.ftd --type tree --max-depth 3

For more help on a specific command, use:
  flextaxd COMMAND --help
        """,
    )

    # Global options
    parser.add_argument("--version", action="version", version="%(prog)s 0.5.0")

    parser.add_argument(
        "--verbose",
        "-v",
        action="count",
        default=0,
        help="Increase verbosity (can be used multiple times)",
    )

    parser.add_argument(
        "--quiet", "-q", action="store_true", help="Suppress all output except errors"
    )

    parser.add_argument("--log-file", type=Path, help="Log output to file")

    # Create subparsers
    subparsers = parser.add_subparsers(
        dest="command", help="Available commands", metavar="COMMAND"
    )

    # Register subcommands in logical order
    
    # Database Operations
    CreateCommand.register_parser(subparsers)
    StatsCommand.register_parser(subparsers)
    ValidateCommand.register_parser(subparsers)
    PurgeCommand.register_parser(subparsers)
    
    # Data Management
    DownloadCommand.register_parser(subparsers)
    ImportAccessionsCommand.register_parser(subparsers)
    RegisterCommand.register_parser(subparsers)
    AssignAccessionsCommand.register_parser(subparsers)
    
    # Node Operations  
    AddNodeCommand.register_parser(subparsers)
    AddGenomeCommand.register_parser(subparsers)
    ImportTreeCommand.register_parser(subparsers)
    
    # Export & Analysis
    ExportCommand.register_parser(subparsers)
    ExportMappingsCommand.register_parser(subparsers)
    VisualizeCommand.register_parser(subparsers)
    
    # File Operations
    ValidateFilesCommand.register_parser(subparsers)
    ListMissingCommand.register_parser(subparsers)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Main entry point for the CLI."""
    parser = create_parser()
    args = parser.parse_args(argv)

    # Setup logging based on verbosity
    log_level = logging.WARNING
    if args.verbose >= 2:
        log_level = logging.DEBUG
    elif args.verbose == 1:
        log_level = logging.INFO
    elif args.quiet:
        log_level = logging.ERROR

    setup_logging(level=log_level, log_file=args.log_file)
    logger = logging.getLogger(__name__)

    try:
        # Dispatch to appropriate command
        if not args.command:
            parser.print_help()
            return 1

        # Import and run the appropriate command
        command_classes: Dict[str, type[BaseCommand]] = {
            "create": CreateCommand,
            "export": ExportCommand,
            "export-mappings": ExportMappingsCommand,
            "stats": StatsCommand,
            "visualize": VisualizeCommand,
            "purge": PurgeCommand,
            "validate": ValidateCommand,
            "import-accessions": ImportAccessionsCommand,
            "download": DownloadCommand,
            "register": RegisterCommand,
            "list-missing": ListMissingCommand,
            "validate-files": ValidateFilesCommand,
            "assign-accessions": AssignAccessionsCommand,
            # New focused commands
            "add-node": AddNodeCommand,
            "import-tree": ImportTreeCommand,
            "add-genome": AddGenomeCommand,
        }

        command_class = command_classes[args.command]
        command = command_class()

        logger.info(f"Running command: {args.command}")
        result = command.execute(args)

        if result is None:
            return 0
        return int(result)

    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        print("\nOperation cancelled by user", file=sys.stderr)
        return 130  # Standard exit code for SIGINT

    except FlexTaxDError as e:
        logger.error(f"FlexTaxD error: {e.message}")
        print(f"Error: {e.message}", file=sys.stderr)

        if e.context and logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Error context: {e.context}")

        return 1

    except Exception as e:
        logger.exception("Unexpected error occurred")
        print(f"Unexpected error: {e}", file=sys.stderr)
        print("Run with --verbose for more details", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
