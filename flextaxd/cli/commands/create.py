"""Create command for building taxonomy databases."""

import argparse
from typing import Optional, Any, cast
from pathlib import Path

from .base import BaseCommand
from ...core.exceptions import ValidationError, ParseError, DatabaseError
from ...core.models import TaxonomyTree
from ...parsers.registry import registry
from ...parsers.tsv import TSVTaxonomyParser
from ...database.sqlite import SQLiteTaxonomyRepository


class CreateCommand(BaseCommand):
    """Command to create a new taxonomy database."""
    
    @classmethod
    def register_parser(cls, subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> argparse.ArgumentParser:
        """Register the create command parser."""
        parser = subparsers.add_parser(
            'create',
            help='Create a new taxonomy database',
            description='Create a new taxonomy database from input files',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  flextaxd create --input taxonomy.tsv --database my_db.ftd
  flextaxd create --input ncbi_dump/ --format ncbi --database ncbi_db.ftd
  flextaxd create --input gtdb_taxonomy.tsv --format gtdb --database gtdb_db.ftd
  flextaxd create --input silva_taxonomy.txt --format silva --database silva_db.ftd
  flextaxd create --input cansnper.tree --format cansnper --database cansnper_db.ftd
            """
        )
        
        # Input options
        input_group = parser.add_argument_group('Input options')
        input_group.add_argument(
            '--input', '-i',
            type=str,
            required=True,
            help='Input taxonomy file or directory'
        )
        
        input_group.add_argument(
            '--format', '-f',
            type=str,
            choices=['auto', 'tsv', 'ncbi', 'qiime', 'gtdb', 'silva', 'cansnper'],
            default='auto',
            help='Input format (default: auto-detect)'
        )
        
        # Database options
        db_group = parser.add_argument_group('Database options')
        db_group.add_argument(
            '--database', '-d',
            type=str,
            required=True,
            help='Output database file path (.ftd)'
        )
        
        db_group.add_argument(
            '--overwrite',
            action='store_true',
            help='Overwrite existing database'
        )
        
        # Parser-specific options
        parser_group = parser.add_argument_group('Parser options')
        parser_group.add_argument(
            '--no-header',
            action='store_true',
            help='Input file has no header row'
        )
        
        parser_group.add_argument(
            '--parent-column',
            type=int,
            default=0,
            help='Column index for parent names (0-based, default: 0)'
        )
        
        parser_group.add_argument(
            '--child-column',
            type=int,
            default=1,
            help='Column index for child names (0-based, default: 1)'
        )
        
        parser_group.add_argument(
            '--id-column',
            type=int,
            help='Column index for taxonomic IDs'
        )
        
        parser_group.add_argument(
            '--rank-column',
            type=int,
            help='Column index for taxonomic ranks'
        )
        
        # Genome integration options
        genome_group = parser.add_argument_group('Genome integration options')
        genome_group.add_argument(
            '--genomeid2taxid',
            type=str,
            help='File mapping genome/sequence IDs to taxonomy IDs'
        )
        
        genome_group.add_argument(
            '--genomes-path',
            type=str,
            help='Directory containing genome sequence files'
        )
        
        genome_group.add_argument(
            '--auto-detect-sequences',
            action='store_true',
            help='Automatically detect sequences from FASTA headers'
        )
        
        genome_group.add_argument(
            '--sequence-type',
            choices=['genome', '16S', 'plasmid', 'other'],
            default='genome',
            help='Type of sequences being processed (default: genome)'
        )
        
        return parser
    
    def execute(self, args: argparse.Namespace) -> Optional[int]:
        """Execute the create command."""
        try:
            # Validate input path exists (but don't enforce file vs directory yet)
            input_path = Path(args.input)
            if not input_path.exists():
                raise ValidationError(f"Input path does not exist: {args.input}")
            
            # Check if database exists
            db_path = Path(args.database)
            if db_path.exists() and not args.overwrite:
                raise ValidationError(
                    f"Database already exists: {args.database}. "
                    "Use --overwrite to replace it."
                )
            
            # Register all parsers
            from ...parsers import (
                TSVTaxonomyParser, NCBITaxonomyParser, QIIMETaxonomyParser, 
                SILVATaxonomyParser, CanSNPerTaxonomyParser
            )
            
            parser_classes = [
                TSVTaxonomyParser, NCBITaxonomyParser, QIIMETaxonomyParser,
                SILVATaxonomyParser, CanSNPerTaxonomyParser
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
            
            if args.format == 'auto':
                parser = registry.find_parser(input_path)
                if parser is None:
                    raise ValidationError(f"Cannot auto-detect format for: {args.input}")
                self.logger.info(f"Auto-detected format: {parser.parser_name}")
            else:
                # Handle format aliases
                format_map = {
                    'gtdb': 'qiime',  # GTDB uses QIIME format
                }
                actual_format = format_map.get(args.format, args.format)
                
                try:
                    parser = registry.get_parser(actual_format)
                except:
                    raise ValidationError(f"Unknown format: {args.format}")
            
            # Prepare parser options
            parser_options = {
                'has_header': not args.no_header,
                'parent_column': args.parent_column,
                'child_column': args.child_column,
            }
            
            if args.id_column is not None:
                parser_options['id_column'] = args.id_column
            
            if args.rank_column is not None:
                parser_options['rank_column'] = args.rank_column
            
            # Parse taxonomy file
            self.logger.info(f"Parsing taxonomy file: {args.input}")
            tree = parser.parse(input_path, **parser_options)
            
            self.logger.info(
                f"Parsed taxonomy tree with {tree.node_count} nodes"
            )
            
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
                self.logger.info(f"Database created successfully")
                print(f"Created database: {args.database}")
                print(f"  Nodes: {stats['node_count']}")
                print(f"  Genomes: {stats['genome_count']}")
                print(f"  Root nodes: {stats['root_count']}")
                print(f"  Leaf nodes: {stats['leaf_count']}")
                
                if stats['rank_distribution']:
                    print("  Rank distribution:")
                    for rank, count in stats['rank_distribution'].items():
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
    
    def _process_genome_integration(self, tree: TaxonomyTree, args: argparse.Namespace) -> None:
        """Process genome integration with sequence ID mapping."""
        from ...utils.sequence_utils import SeqIDMappingManager, GenomeDirectoryManager
        from ...core.models import GenomeInfo
        
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
                raise ValidationError(f"Genome mapping file not found: {args.genomeid2taxid}")
            
            self.logger.info(f"Loading sequence ID mappings from: {args.genomeid2taxid}")
            seqid_manager.load_seqid_mapping_file(mapping_file)
            
            mapping_stats = seqid_manager.get_statistics()
            self.logger.info(f"Loaded {mapping_stats['total_mappings']} sequence mappings")
        
        # Process auto-detection of sequences from FASTA files
        if args.auto_detect_sequences and genome_manager:
            self._auto_detect_sequences_from_genomes(tree, genome_manager, seqid_manager, args)
        
        # Add genome information to taxonomy tree
        genomes_added = 0
        for seq_id, mapping in seqid_manager.mappings.items():
            # Find corresponding taxonomy node
            tax_node = tree.get_node(mapping.taxonomy_id)
            if not tax_node:
                self.logger.warning(f"Taxonomy node {mapping.taxonomy_id} not found for sequence {seq_id}")
                continue
            
            # Get genome file path if available
            file_path: Optional[str] = None
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
                source=mapping.source
            )
            
            # Add to tree
            tree.add_genome(genome_info)
            genomes_added += 1
        
        self.logger.info(f"Added {genomes_added} genome associations to taxonomy tree")
    
    def _auto_detect_sequences_from_genomes(self, tree: TaxonomyTree, genome_manager: Any, seqid_manager: Any, args: argparse.Namespace) -> None:
        """Auto-detect sequence IDs from genome FASTA files."""
        from ...utils.sequence_utils import FASTAProcessor
        
        self.logger.info("Auto-detecting sequences from genome files...")
        processor = FASTAProcessor()
        sequences_detected = 0
        
        # Process each genome file
        for genome_id, file_path in genome_manager.genome_files.items():
            try:
                # Only process FASTA files
                if not any(str(file_path).lower().endswith(ext) 
                          for ext in ['.fasta', '.fa', '.fna', '.ffn', '.faa']):
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
                        if genome_id.lower() in node.name.lower() or node.name.lower() in genome_id.lower():
                            matching_nodes.append(node)
                    
                    if matching_nodes:
                        # Use the most specific matching node (highest tax_id as heuristic)
                        best_match = max(matching_nodes, key=lambda n: n.tax_id)
                        
                        # Add to seqid manager
                        from ...utils.sequence_utils import SeqIDMapping
                        mapping = SeqIDMapping(
                            seq_info.sequence_id,
                            best_match.tax_id,
                            f"auto-detected from {file_path}"
                        )
                        seqid_manager.mappings[seq_info.sequence_id] = mapping
                        sequences_detected += 1
                        
            except Exception as e:
                self.logger.warning(f"Could not process genome file {file_path}: {e}")
        
        self.logger.info(f"Auto-detected {sequences_detected} sequence associations")