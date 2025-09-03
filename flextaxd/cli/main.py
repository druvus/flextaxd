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
    ModifyCommand,
    ExportCommand,
    StatsCommand,
    VisualizeCommand,
)
from .commands.base import BaseCommand


def create_parser() -> argparse.ArgumentParser:
    """Create the main argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="flextaxd",
        description="Flexible modification of taxonomy databases",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  flextaxd create --input taxonomy.tsv --database my_db.ftd
  flextaxd export --database my_db.ftd --format ncbi --output ./output/
  flextaxd stats --database my_db.ftd
  flextaxd visualize --database my_db.ftd --type tree --max-depth 3
  flextaxd modify --database my_db.ftd --add-node "New Species" --parent-id 12345

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

    # Register subcommands
    CreateCommand.register_parser(subparsers)
    ModifyCommand.register_parser(subparsers)
    ExportCommand.register_parser(subparsers)
    StatsCommand.register_parser(subparsers)
    VisualizeCommand.register_parser(subparsers)

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
            "modify": ModifyCommand,
            "export": ExportCommand,
            "stats": StatsCommand,
            "visualize": VisualizeCommand,
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
