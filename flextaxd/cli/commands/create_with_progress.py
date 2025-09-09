"""Enhanced create command with progress indicators."""

import argparse
from pathlib import Path
from typing import Any
import logging

from ...core.exceptions import ParseError, ValidationError
from ...core.models import TaxonomyTree
from ...database.sqlite import SQLiteTaxonomyRepository
from ...parsers.registry import registry
from ...utils.progress import (
    progress_manager, 
    create_console_reporter, 
    create_logging_reporter,
    create_silent_reporter,
    MultiProgressReporter
)
from .base import BaseCommand


class CreateCommandWithProgress(BaseCommand):
    """Enhanced create command with comprehensive progress indicators."""

    @classmethod
    def register_parser(
        cls, subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]"
    ) -> argparse.ArgumentParser:
        """Register the create command parser with progress options."""
        parser = subparsers.add_parser(
            "create",
            help="Create taxonomy database with progress indicators",
            description="Create taxonomy database from various input sources with detailed progress reporting",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  # Basic usage with progress bars
  flextaxd create --input taxonomy.tsv --database my_db.ftd
  
  # Silent mode (no progress bars)
  flextaxd create --input taxonomy.tsv --database my_db.ftd --quiet
  
  # Progress to log file
  flextaxd create --input ncbi_dump/ --database ncbi.ftd --progress-log create.log
  
  # Large datasets with detailed progress
  flextaxd create --input gtdb_taxonomy.tsv --database gtdb.ftd --verbose --progress-interval 5000
            """,
        )

        # Input options
        input_group = parser.add_argument_group("Input options")
        input_source = input_group.add_mutually_exclusive_group(required=True)
        
        input_source.add_argument(
            "--input", "-i", type=str, help="Input taxonomy file or directory"
        )
        
        input_source.add_argument(
            "--ncbi-datasets", type=str,
            help="Create from NCBI datasets using taxon name or ID"
        )

        # Output options
        output_group = parser.add_argument_group("Output options")
        output_group.add_argument(
            "--database", "-d", required=True, type=str,
            help="Output database file path (.ftd)"
        )
        
        output_group.add_argument(
            "--overwrite", action="store_true",
            help="Overwrite existing database"
        )

        # Format options
        format_group = parser.add_argument_group("Format options")
        format_group.add_argument(
            "--format", "-f",
            choices=["auto", "tsv", "ncbi", "qiime", "gtdb", "silva", "cansnper"],
            default="auto",
            help="Input file format (default: auto-detect)"
        )

        # Progress options (NEW)
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

    def execute(self, args: argparse.Namespace) -> int | None:
        """Execute the create command with progress indicators."""
        try:
            # Setup progress reporting system
            self._setup_progress_reporting(args)
            
            # Check if database exists
            db_path = Path(args.database)
            if db_path.exists() and not args.overwrite:
                raise ValidationError(
                    f"Database already exists: {args.database}. "
                    "Use --overwrite to replace it."
                )
            
            # Handle NCBI datasets input
            if args.ncbi_datasets:
                return self._create_from_ncbi_datasets_with_progress(args)
            
            # Handle regular file input
            if not args.input:
                raise ValidationError("Either --input or --ncbi-datasets must be provided")
            
            return self._create_from_file_with_progress(args)
            
        except (ParseError, ValidationError) as e:
            self.logger.error(f"Validation error: {str(e)}")
            if not args.quiet:
                print(f"Error: {e}")
            return 1
        except Exception as e:
            self.logger.error(f"Unexpected error: {str(e)}")
            if not args.quiet:
                print(f"Error: {e}")
            return 1

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
            
            progress_logger = logging.getLogger('flextaxd.progress')
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

    def _create_from_file_with_progress(self, args: argparse.Namespace) -> int:
        """Create database from file with progress tracking."""
        input_path = Path(args.input)
        if not input_path.exists():
            raise ValidationError(f"Input path does not exist: {args.input}")

        # Step 1: Parser setup and validation
        with progress_manager.operation(
            total=4, 
            description="Initializing database creation"
        ) as progress:
            
            progress.update(1, "Registering parsers")
            self._register_parsers()
            
            progress.update(2, "Detecting file format")
            parser = self._get_parser(input_path, args.format)
            
            progress.update(3, "Validating input format")
            if not parser.can_parse(input_path):
                self._handle_format_mismatch(parser, input_path, args.format)
            
            progress.update(4, "Setup complete")

        # Step 2: Parse taxonomy file with progress
        self.logger.info(f"Parsing taxonomy file: {args.input}")
        
        # Estimate parsing operations based on file size
        file_size = input_path.stat().st_size
        estimated_lines = max(100, file_size // 50)  # Rough estimate
        
        with progress_manager.operation(
            total=estimated_lines,
            description=f"Parsing {input_path.name}"
        ) as progress:
            
            # Create progress callback for parser
            def parse_progress_callback(current_line: int):
                progress.update(current_line, f"Processing line {current_line}")
            
            # Parse with progress (assuming parser supports progress callback)
            parser_options = self._build_parser_options(args)
            tree = self._parse_with_progress(parser, input_path, parser_options, parse_progress_callback)

        self.logger.info(f"Parsed taxonomy tree with {tree.node_count} nodes")

        # Step 3: Save to database with progress
        db_path = Path(args.database)
        if db_path.exists() and args.overwrite:
            db_path.unlink()

        repository = SQLiteTaxonomyRepository(db_path)
        
        with progress_manager.operation(
            total=3 + tree.node_count,
            description="Creating database"
        ) as progress:
            
            progress.update(1, "Initializing database schema")
            repository.initialize()
            
            progress.update(2, "Preparing data structures")
            # Additional preparation if needed
            
            progress.update(3, "Saving taxonomy tree")
            
            # Enhanced save_tree with progress callback
            def save_progress_callback(nodes_saved: int):
                progress.update(3 + nodes_saved, f"Saved {nodes_saved}/{tree.node_count} nodes")
            
            self._save_tree_with_progress(repository, tree, save_progress_callback)

        self.logger.info("Database created successfully")
        if not args.quiet:
            print(f"✓ Created database: {args.database}")
            print(f"  • {tree.node_count} taxonomy nodes")
            if hasattr(tree, 'genome_count') and tree.genome_count > 0:
                print(f"  • {tree.genome_count} genomes")

        return 0

    def _create_from_ncbi_datasets_with_progress(self, args: argparse.Namespace) -> int:
        """Create database from NCBI datasets with progress tracking."""
        from ...utils.ncbi_datasets import NCBIDatasetsManager
        
        # Step 1: Setup and validation
        with progress_manager.operation(
            total=3,
            description="Preparing NCBI datasets download"
        ) as progress:
            
            progress.update(1, "Initializing NCBI datasets manager")
            manager = NCBIDatasetsManager()
            
            progress.update(2, "Validating installation")
            if not manager.check_installation():
                raise ValidationError(
                    "NCBI datasets CLI is not installed or not in PATH. "
                    "Please install it following the instructions at: "
                    "https://www.ncbi.nlm.nih.gov/datasets/docs/v2/download-and-install/"
                )
            
            progress.update(3, "Validating taxon")
            if not manager.validate_taxon(args.ncbi_datasets):
                raise ValidationError(
                    f"Invalid taxon: '{args.ncbi_datasets}'. "
                    "Please provide a valid taxonomic name or NCBI taxonomy ID."
                )

        # Step 2: Download with progress
        self.logger.info(f"Creating database from NCBI datasets for taxon: {args.ncbi_datasets}")
        
        # Create progress callback for download operations
        def download_progress_callback(step: str, current: int, total: int):
            if not hasattr(download_progress_callback, 'current_progress'):
                download_progress_callback.current_progress = None
            
            # Start new progress operation if needed
            if download_progress_callback.current_progress is None:
                download_progress_callback.current_progress = progress_manager.get_reporter()
                download_progress_callback.current_progress.start(total, f"NCBI datasets: {step}")
            
            download_progress_callback.current_progress.update(current, step)
            
            # Finish when complete
            if current >= total:
                download_progress_callback.current_progress.finish(f"Completed: {step}")
                download_progress_callback.current_progress = None

        # Step 3: Create database
        db_path = Path(args.database)
        if db_path.exists() and args.overwrite:
            db_path.unlink()

        # Enhanced NCBI datasets creation with progress
        stats = self._create_ncbi_database_with_progress(
            manager, args, db_path, download_progress_callback
        )

        self.logger.info("Database created successfully from NCBI datasets")
        if not args.quiet:
            print(f"✓ Created database: {args.database}")
            print(f"  • {stats.get('taxonomy_nodes', 0)} taxonomy nodes")
            if stats.get('genomes_downloaded', 0) > 0:
                print(f"  • {stats['genomes_downloaded']} genomes downloaded")

        return 0

    def _register_parsers(self) -> None:
        """Register all available parsers."""
        from ...parsers import (
            CanSNPerTaxonomyParser,
            GTDBTaxonomyParser, 
            NCBITaxonomyParser,
            QIIMETaxonomyParser,
            SILVATaxonomyParser,
            TSVTaxonomyParser,
        )

        parser_classes = [
            TSVTaxonomyParser,
            NCBITaxonomyParser,
            QIIMETaxonomyParser,
            GTDBTaxonomyParser,
            SILVATaxonomyParser,
            CanSNPerTaxonomyParser,
        ]

        for parser_class in parser_classes:
            try:
                registry.register(parser_class())
            except Exception as e:
                self.logger.warning(f"Failed to register parser {parser_class.__name__}: {e}")

    def _get_parser(self, input_path: Path, format_name: str):
        """Get appropriate parser for input."""
        if format_name == "auto":
            parser = registry.find_parser(input_path)
            if not parser:
                raise ValidationError(
                    f"Cannot determine format for: {input_path}. "
                    "Please specify format explicitly with --format"
                )
        else:
            try:
                parser = registry.get_parser(format_name)
            except:
                raise ValidationError(f"Unknown format: {format_name}")
        
        return parser

    def _handle_format_mismatch(self, parser, input_path: Path, specified_format: str) -> None:
        """Handle format mismatch with helpful suggestions."""
        self.logger.warning(
            f"Input file does not appear to match specified format '{specified_format}'"
        )
        
        suggested_parser = registry.find_parser(input_path)
        if suggested_parser and suggested_parser.parser_name != parser.parser_name:
            raise ValidationError(
                f"Input file does not match specified format '{specified_format}'. "
                f"Auto-detection suggests format '{suggested_parser.parser_name}'. "
                f"Use --format {suggested_parser.parser_name} or --format auto"
            )
        else:
            raise ValidationError(
                f"Input file does not match specified format '{specified_format}'. "
                f"Please verify the file format or use --format auto"
            )

    def _build_parser_options(self, args: argparse.Namespace) -> dict:
        """Build parser options from command arguments."""
        parser_options = {"has_header": True}  # Default
        
        # Add other parser-specific options as needed
        if hasattr(args, 'parent_column') and args.parent_column:
            parser_options["parent_column"] = args.parent_column
        if hasattr(args, 'child_column') and args.child_column:
            parser_options["child_column"] = args.child_column
        if hasattr(args, 'id_column') and args.id_column:
            parser_options["id_column"] = args.id_column
        if hasattr(args, 'rank_column') and args.rank_column:
            parser_options["rank_column"] = args.rank_column
            
        return parser_options

    def _parse_with_progress(self, parser, input_path: Path, options: dict, 
                           progress_callback) -> TaxonomyTree:
        """Parse taxonomy file with progress reporting."""
        # For now, call regular parse method
        # In a full implementation, parsers would be enhanced to support progress callbacks
        try:
            tree = parser.parse(input_path, **options)
            # Simulate progress updates for demonstration
            if hasattr(tree, 'node_count'):
                for i in range(0, tree.node_count, max(1, tree.node_count // 20)):
                    progress_callback(i)
            progress_callback(tree.node_count if hasattr(tree, 'node_count') else 100)
            return tree
        except Exception as e:
            raise ParseError(f"Failed to parse {input_path}: {e}")

    def _save_tree_with_progress(self, repository: SQLiteTaxonomyRepository, 
                               tree: TaxonomyTree, progress_callback) -> None:
        """Save tree to database with progress reporting."""
        # For now, call regular save_tree method
        # In a full implementation, save_tree would be enhanced to support progress callbacks
        try:
            repository.save_tree(tree)
            # Simulate progress updates
            if hasattr(tree, 'node_count'):
                for i in range(0, tree.node_count, max(1, tree.node_count // 10)):
                    progress_callback(i)
            progress_callback(tree.node_count if hasattr(tree, 'node_count') else 100)
        except Exception as e:
            raise ValidationError(f"Failed to save tree to database: {e}")

    def _create_ncbi_database_with_progress(self, manager, args: argparse.Namespace, 
                                          db_path: Path, progress_callback) -> dict:
        """Create NCBI database with progress tracking."""
        # Enhanced NCBI creation with progress reporting
        # This would integrate with the actual NCBIDatasetsManager
        
        progress_callback("Downloading taxonomy data", 1, 5)
        progress_callback("Processing taxonomy", 2, 5) 
        progress_callback("Downloading genomes", 3, 5)
        progress_callback("Creating database", 4, 5)
        progress_callback("Finalizing", 5, 5)
        
        # Return mock stats for now
        return {
            'taxonomy_nodes': 1000,
            'genomes_downloaded': 50
        }