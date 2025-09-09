"""Create command for building taxonomy databases."""

import argparse
from pathlib import Path
from typing import Any, cast

from ...core.exceptions import ParseError, ValidationError
from ...core.models import TaxonomyTree
from ...database.sqlite import SQLiteTaxonomyRepository
from ...parsers.registry import registry
from .base import BaseCommand


class CreateCommand(BaseCommand):
    """Command to create a new taxonomy database."""

    @classmethod
    def register_parser(
        cls, subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]"
    ) -> argparse.ArgumentParser:
        """Register the create command parser."""
        parser = subparsers.add_parser(
            "create",
            help="Create taxonomy database from various sources",
            description="Create taxonomy database from various input sources",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  # From local files
  flextaxd create --input taxonomy.tsv --database my_db.ftd
  flextaxd create --input ncbi_dump/ --format ncbi --database ncbi_db.ftd
  flextaxd create --input gtdb_taxonomy.tsv --format gtdb --database gtdb_db.ftd
  
  # From NCBI datasets (requires NCBI datasets CLI)
  flextaxd create --ncbi-datasets "Escherichia coli" --database ecoli.ftd
  flextaxd create --ncbi-datasets "562" --assembly-level complete --max-genomes 10 --database ecoli_genomes.ftd
  flextaxd create --ncbi-datasets "Bacteria" --taxonomy-only --database bacteria_taxonomy.ftd
            """,
        )

        # Input options - mutually exclusive input sources
        input_group = parser.add_argument_group("Input options")
        input_source = input_group.add_mutually_exclusive_group(required=True)
        
        input_source.add_argument(
            "--input",
            "-i",
            type=str,
            help="Input taxonomy file or directory",
        )
        
        input_source.add_argument(
            "--ncbi-datasets",
            type=str,
            help="Download data from NCBI datasets for specified taxon (e.g., 'Escherichia coli', '562')",
        )

        input_group.add_argument(
            "--format",
            "-f",
            type=str,
            choices=["auto", "tsv", "ncbi", "qiime", "gtdb", "silva", "cansnper"],
            default="auto",
            help="Input format (default: auto-detect, ignored with --ncbi-datasets)",
        )
        
        # NCBI datasets specific options
        ncbi_group = parser.add_argument_group("NCBI datasets options (used with --ncbi-datasets)")
        ncbi_group.add_argument(
            "--assembly-level",
            choices=["complete", "chromosome", "scaffold", "contig", "all"],
            default="complete",
            help="Assembly level filter for genomes (default: complete)",
        )
        
        ncbi_group.add_argument(
            "--max-genomes",
            type=int,
            help="Maximum number of genomes to download",
        )
        
        ncbi_group.add_argument(
            "--taxonomy-only",
            action="store_true",
            help="Download taxonomy data only (no genomes)",
        )
        
        ncbi_group.add_argument(
            "--ncbi-cache-dir",
            type=str,
            help="Directory to cache NCBI downloads (default: ~/.flextaxd/ncbi_cache)",
        )

        # Database options
        db_group = parser.add_argument_group("Database options")
        db_group.add_argument(
            "--database",
            "-d",
            type=str,
            required=True,
            help="Output database file path (.ftd)",
        )

        db_group.add_argument(
            "--overwrite", action="store_true", help="Overwrite existing database"
        )

        # Parser-specific options
        parser_group = parser.add_argument_group("Parser options")
        parser_group.add_argument(
            "--no-header", action="store_true", help="Input file has no header row"
        )

        parser_group.add_argument(
            "--parent-column",
            type=int,
            default=0,
            help="Column index for parent names (0-based, default: 0)",
        )

        parser_group.add_argument(
            "--child-column",
            type=int,
            default=1,
            help="Column index for child names (0-based, default: 1)",
        )

        parser_group.add_argument(
            "--id-column", type=int, help="Column index for taxonomic IDs"
        )

        parser_group.add_argument(
            "--rank-column", type=int, help="Column index for taxonomic ranks"
        )

        # Genome integration options
        genome_group = parser.add_argument_group("Genome integration options")
        genome_group.add_argument(
            "--genomeid2taxid",
            type=str,
            help="File mapping genome/sequence IDs to taxonomy IDs",
        )

        genome_group.add_argument(
            "--genomes-path",
            type=str,
            help="Directory containing genome sequence files",
        )

        genome_group.add_argument(
            "--auto-detect-sequences",
            action="store_true",
            help="Automatically detect sequences from FASTA headers",
        )

        genome_group.add_argument(
            "--sequence-type",
            choices=["genome", "16S", "plasmid", "other"],
            default="genome",
            help="Type of sequences being processed (default: genome)",
        )

        return parser

    def execute(self, args: argparse.Namespace) -> int | None:
        """Execute the create command."""
        try:
            # Check if database exists
            db_path = Path(args.database)
            if db_path.exists() and not args.overwrite:
                raise ValidationError(
                    f"Database already exists: {args.database}. "
                    "Use --overwrite to replace it."
                )
            
            # Handle NCBI datasets input
            if args.ncbi_datasets:
                return self._create_from_ncbi_datasets(args)
            
            # Handle regular file input
            if not args.input:
                raise ValidationError("Either --input or --ncbi-datasets must be provided")
            
            # Validate input path exists (but don't enforce file vs directory yet)
            input_path = Path(args.input)
            if not input_path.exists():
                raise ValidationError(f"Input path does not exist: {args.input}")

            # Register all parsers
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
                    registry.register(cast(Any, parser_class))
                except Exception:
                    # Parser already registered, skip
                    pass

            # Find appropriate parser
            input_path = Path(args.input)
            parser = None

            if args.format == "auto":
                parser = registry.find_parser(input_path)
                if parser is None:
                    raise ValidationError(
                        f"Cannot auto-detect format for: {args.input}"
                    )
                self.logger.info(f"Auto-detected format: {parser.parser_name}")
            else:
                # Use format directly - no more aliases needed with proper GTDB parser
                actual_format = args.format

                try:
                    parser = registry.get_parser(actual_format)
                except:
                    raise ValidationError(f"Unknown format: {args.format}")

                # Validate that the input file actually matches the specified format
                if not parser.can_parse(input_path):
                    self.logger.warning(
                        f"Input file does not appear to match specified format '{args.format}'. "
                        f"The parser for '{args.format}' cannot validate this file."
                    )

                    # Try auto-detection to suggest the correct format
                    suggested_parser = registry.find_parser(input_path)
                    if (
                        suggested_parser
                        and suggested_parser.parser_name != parser.parser_name
                    ):
                        raise ValidationError(
                            f"Input file does not match specified format '{args.format}'. "
                            f"Auto-detection suggests format '{suggested_parser.parser_name}'. "
                            f"Use --format {suggested_parser.parser_name} or --format auto"
                        )
                    else:
                        raise ValidationError(
                            f"Input file does not match specified format '{args.format}'. "
                            f"Please verify the file format or use --format auto for automatic detection."
                        )

            # Prepare parser options
            parser_options = {
                "has_header": not args.no_header,
                "parent_column": args.parent_column,
                "child_column": args.child_column,
            }

            if args.id_column is not None:
                parser_options["id_column"] = args.id_column

            if args.rank_column is not None:
                parser_options["rank_column"] = args.rank_column

            # Parse taxonomy file
            self.logger.info(f"Parsing taxonomy file: {args.input}")
            tree = parser.parse(input_path, **parser_options)

            self.logger.info(f"Parsed taxonomy tree with {tree.node_count} nodes")

            # Process genome integration if provided
            if args.genomeid2taxid or args.genomes_path:
                self._process_genome_integration(tree, args)

            # Create database repository
            if db_path.exists():
                db_path.unlink()  # Remove existing database if overwrite

            with SQLiteTaxonomyRepository(db_path) as repository:
                self.logger.info(f"Saving taxonomy to database: {args.database}")
                repository.save_tree(tree)

                # Print statistics
                stats = repository.get_statistics()
                self.logger.info("Database created successfully")
                print(f"Created database: {args.database}")
                print(f"  Nodes: {stats['node_count']}")
                print(f"  Genomes: {stats['genome_count']}")
                if "root_count" in stats:
                    print(f"  Root nodes: {stats['root_count']}")
                if "leaf_count" in stats:
                    print(f"  Leaf nodes: {stats['leaf_count']}")

                if stats["rank_distribution"]:
                    print("  Rank distribution:")
                    for rank, count in stats["rank_distribution"].items():
                        print(f"    {rank}: {count}")

            return 0

        except ValidationError as e:
            self.logger.error(f"Validation error: {e.message}")
            print(f"Error: {e.message}")
            return 1

        except ParseError as e:
            self.logger.error(f"Parse error: {e.message}")
            print(f"Parse error: {e.message}")
            return 1
        
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
            print(f"Error: {e}")
            return 1

    def _process_genome_integration(
        self, tree: TaxonomyTree, args: argparse.Namespace
    ) -> None:
        """Process genome integration with sequence ID mapping."""
        from ...core.models import GenomeInfo
        from ...utils.sequence_utils import GenomeDirectoryManager, SeqIDMappingManager

        self.logger.info("Processing genome integration...")

        # Initialize managers
        seqid_manager = SeqIDMappingManager()
        genome_manager = None

        # Load genome directory if provided
        if args.genomes_path:
            genome_manager = GenomeDirectoryManager(Path(args.genomes_path))
            genome_stats = genome_manager.get_statistics()
            self.logger.info(
                f"Found {genome_stats['total_files']} genome files "
                f"({genome_stats['total_size_mb']} MB total)"
            )

        # Load seqid2taxid mapping if provided
        if args.genomeid2taxid:
            mapping_file = Path(args.genomeid2taxid)
            if not mapping_file.exists():
                raise ValidationError(
                    f"Genome mapping file not found: {args.genomeid2taxid}"
                )

            self.logger.info(
                f"Loading sequence ID mappings from: {args.genomeid2taxid}"
            )
            seqid_manager.load_seqid_mapping_file(mapping_file)

            mapping_stats = seqid_manager.get_statistics()
            self.logger.info(
                f"Loaded {mapping_stats['total_mappings']} sequence mappings"
            )

        # Process auto-detection of sequences from FASTA files
        if args.auto_detect_sequences and genome_manager:
            self._auto_detect_sequences_from_genomes(
                tree, genome_manager, seqid_manager, args
            )

        # Add genome information to taxonomy tree
        genomes_added = 0
        for seq_id, mapping in seqid_manager.mappings.items():
            # Find corresponding taxonomy node
            tax_node = tree.get_node(mapping.taxonomy_id)
            if not tax_node:
                self.logger.warning(
                    f"Taxonomy node {mapping.taxonomy_id} not found for sequence {seq_id}"
                )
                continue

            # Get genome file path if available
            file_path: str | None = None
            if genome_manager:
                genome_path = genome_manager.get_genome_file(seq_id)
                if genome_path:
                    file_path = str(genome_path)

            # Create genome info
            genome_info = GenomeInfo(
                genome_id=seq_id,
                tax_id=mapping.taxonomy_id,
                file_path=file_path,
                sequence_type=args.sequence_type,
                source=mapping.source,
            )

            # Add to tree
            tree.add_genome(genome_info)
            genomes_added += 1

        self.logger.info(f"Added {genomes_added} genome associations to taxonomy tree")

    def _auto_detect_sequences_from_genomes(
        self,
        tree: TaxonomyTree,
        genome_manager: Any,
        seqid_manager: Any,
        args: argparse.Namespace,
    ) -> None:
        """Auto-detect sequence IDs from genome FASTA files."""
        from ...utils.sequence_utils import FASTAProcessor

        self.logger.info("Auto-detecting sequences from genome files...")
        processor = FASTAProcessor()
        sequences_detected = 0

        # Process each genome file
        for genome_id, file_path in genome_manager.genome_files.items():
            try:
                # Only process FASTA files
                if not any(
                    str(file_path).lower().endswith(ext)
                    for ext in [".fasta", ".fa", ".fna", ".ffn", ".faa"]
                ):
                    continue

                # Parse FASTA headers
                sequence_infos = processor.parse_fasta_headers(file_path)

                # Try to match sequences to taxonomy based on filename or content
                # This is a heuristic approach - could be improved
                for seq_info in sequence_infos:
                    # For now, assume the genome file name corresponds to a taxonomy node
                    # In a real implementation, you might have more sophisticated matching

                    # Try to find taxonomy node by name matching
                    matching_nodes = []
                    for node in tree:
                        if (
                            genome_id.lower() in node.name.lower()
                            or node.name.lower() in genome_id.lower()
                        ):
                            matching_nodes.append(node)

                    if matching_nodes:
                        # Use the most specific matching node (highest tax_id as heuristic)
                        best_match = max(matching_nodes, key=lambda n: n.tax_id)

                        # Add to seqid manager
                        from ...utils.sequence_utils import SeqIDMapping

                        mapping = SeqIDMapping(
                            seq_info.sequence_id,
                            best_match.tax_id,
                            f"auto-detected from {file_path}",
                        )
                        seqid_manager.mappings[seq_info.sequence_id] = mapping
                        sequences_detected += 1

            except Exception as e:
                self.logger.warning(f"Could not process genome file {file_path}: {e}")

        self.logger.info(f"Auto-detected {sequences_detected} sequence associations")

    def _create_from_ncbi_datasets(self, args: argparse.Namespace) -> int:
        """Create database from NCBI datasets."""
        from ...utils.ncbi_datasets import NCBIDatasetsManager, NCBIDatasetsError
        import tempfile
        
        self.logger.info(f"Creating database from NCBI datasets for taxon: {args.ncbi_datasets}")
        
        try:
            # Initialize NCBI datasets manager
            cache_dir = Path(args.ncbi_cache_dir) if args.ncbi_cache_dir else None
            manager = NCBIDatasetsManager(cache_dir=cache_dir)
            
            # Create temporary directory for downloads
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                
                self.logger.info(f"Downloading NCBI data to: {temp_path}")
                
                # Download data based on options
                if args.taxonomy_only:
                    dataset_info = manager.download_taxonomy(
                        taxon=args.ncbi_datasets,
                        output_dir=temp_path,
                        include_children=True
                    )
                else:
                    download_kwargs = {}
                    dataset_info = manager.download_genomes(
                        taxon=args.ncbi_datasets,
                        output_dir=temp_path,
                        assembly_level=args.assembly_level,
                        max_genomes=args.max_genomes,
                        **download_kwargs
                    )
                
                self.logger.info(f"Downloaded {dataset_info.genome_count} genomes")
                
                # Create database
                db_path = Path(args.database)
                if db_path.exists():
                    db_path.unlink()  # Remove existing database if overwrite
                
                include_genomes = not args.taxonomy_only and dataset_info.genomes_directory is not None
                
                stats = manager.create_flextaxd_database(
                    dataset_info=dataset_info,
                    database_path=db_path,
                    include_genomes=include_genomes
                )
                
                # Print statistics  
                self.logger.info("Database created successfully from NCBI datasets")
                print(f"Created database: {args.database}")
                print(f"  Taxon: {args.ncbi_datasets}")
                print(f"  Nodes: {stats['node_count']}")
                print(f"  Genomes: {stats['genome_count']}")
                
                if "root_count" in stats:
                    print(f"  Root nodes: {stats['root_count']}")
                if "leaf_count" in stats:
                    print(f"  Leaf nodes: {stats['leaf_count']}")

                if stats["rank_distribution"]:
                    print("  Rank distribution:")
                    for rank, count in stats["rank_distribution"].items():
                        rank_name = rank.value if hasattr(rank, 'value') else str(rank)
                        print(f"    {rank_name}: {count}")
                
                return 0
                
        except NCBIDatasetsError as e:
            self.logger.error(f"NCBI datasets error: {e}")
            print(f"NCBI datasets error: {e}")
            return 1
