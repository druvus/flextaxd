"""Export mapping files command for FlexTaxD CLI."""

import argparse
from pathlib import Path
from typing import Optional

from .base import BaseCommand
from ...database.sqlite import SQLiteTaxonomyRepository
from ...sequence.sequence_tracker import SequenceTracker
from ...core.exceptions import DatabaseError, ValidationError


class ExportMappingsCommand(BaseCommand):
    """Export standard mapping files command."""
    
    @classmethod
    def register_parser(cls, subparsers) -> argparse.ArgumentParser:
        """Register export-mappings command parser."""
        parser = subparsers.add_parser(
            'export-mappings',
            help='Export standard mapping files (accession2taxid, nucl2taxid, prot2taxid, genome_sizes)',
            description='Generate standard mapping files from sequence tracking database'
        )
        
        # Required arguments
        parser.add_argument(
            '--database', '-d',
            type=Path,
            required=True,
            help='Path to FlexTaxD database file (.ftd)'
        )
        
        parser.add_argument(
            '--output', '-o',
            type=Path,
            required=True,
            help='Output file path or directory (depending on format)'
        )
        
        # Format selection
        format_group = parser.add_mutually_exclusive_group(required=True)
        format_group.add_argument(
            '--format', '-f',
            choices=['accession2taxid', 'nucl2taxid', 'prot2taxid', 'genome_sizes', 'all'],
            help='Mapping file format to generate'
        )
        
        format_group.add_argument(
            '--tool', '-t',
            choices=['diamond', 'kraken2', 'mmseqs2', 'kaiju', 'centrifuge'],
            help='Generate mappings specific to a classification tool'
        )
        
        # Optional arguments
        parser.add_argument(
            '--prefix',
            type=str,
            default='',
            help='Optional prefix for generated filenames'
        )
        
        parser.add_argument(
            '--sequence-types',
            nargs='+',
            choices=['assembly', 'nucleotide', 'protein'],
            help='Sequence types to include (for accession2taxid format only)'
        )
        
        parser.add_argument(
            '--validate-files',
            action='store_true',
            help='Validate that referenced files exist before generating mappings'
        )
        
        parser.add_argument(
            '--stats-only',
            action='store_true',
            help='Show statistics about available sequences without generating files'
        )
        
        return parser
    
    def execute(self, args: argparse.Namespace) -> Optional[int]:
        """Execute the export-mappings command."""
        try:
            # Validate database
            self._validate_database_path(str(args.database))
            
            # Initialize components
            repository = SQLiteTaxonomyRepository(str(args.database))
            tracker = SequenceTracker(repository)
            
            # Show statistics if requested
            if args.stats_only:
                return self._show_sequence_statistics(tracker)
            
            # Validate sequences if requested
            if args.validate_files:
                validation_results = tracker.validate_sequences()
                if validation_results['invalid_mappings'] > 0:
                    self.logger.warning("Found validation issues:")
                    for issue in validation_results['issues'][:5]:  # Show first 5 issues
                        self.logger.warning(f"  - {issue}")
                    if len(validation_results['issues']) > 5:
                        self.logger.warning(f"  ... and {len(validation_results['issues']) - 5} more issues")
            
            # Generate mappings based on format/tool
            if args.tool:
                results = self._generate_tool_mappings(tracker, args)
            elif args.format == 'all':
                results = self._generate_all_mappings(tracker, args)
            else:
                results = self._generate_single_format(tracker, args)
            
            # Report results
            if results:
                self.logger.info("Generated mapping files:")
                total_mappings = 0
                for filename, count in results.items():
                    self.logger.info(f"  {filename}: {count:,} mappings")
                    total_mappings += count
                self.logger.info(f"Total mappings: {total_mappings:,}")
            else:
                self.logger.warning("No mapping files generated (no sequence data available)")
                return 1
                
            return 0
            
        except (DatabaseError, ValidationError) as e:
            self.logger.error(f"Export mappings failed: {e}")
            return 1
        except Exception as e:
            self.logger.exception("Unexpected error during mapping export")
            return 2

    def _show_sequence_statistics(self, tracker: SequenceTracker) -> int:
        """Show sequence tracking statistics."""
        stats = tracker.get_sequence_statistics()
        
        self.logger.info("Sequence Tracking Statistics")
        self.logger.info("=" * 40)
        self.logger.info(f"Total files tracked: {stats.total_files:,}")
        self.logger.info(f"  Genome files: {stats.genome_files:,}")
        self.logger.info(f"  Protein files: {stats.protein_files:,}")
        self.logger.info("")
        self.logger.info(f"Taxa with sequences: {max(stats.taxa_with_genomes, stats.taxa_with_proteins):,}")
        self.logger.info(f"  With genomes: {stats.taxa_with_genomes:,}")
        self.logger.info(f"  With proteins: {stats.taxa_with_proteins:,}")
        self.logger.info("")
        self.logger.info(f"Total sequences: {stats.total_sequences:,}")
        self.logger.info(f"Total proteins: {stats.total_proteins:,}")
        
        if stats.file_validation_errors:
            self.logger.warning(f"File validation issues: {len(stats.file_validation_errors)}")
            for error in stats.file_validation_errors[:3]:  # Show first 3 errors
                self.logger.warning(f"  - {error}")
            if len(stats.file_validation_errors) > 3:
                self.logger.warning(f"  ... and {len(stats.file_validation_errors) - 3} more issues")
        
        return 0

    def _generate_tool_mappings(self, tracker: SequenceTracker, args: argparse.Namespace) -> dict:
        """Generate mappings for a specific tool."""
        if args.output.suffix:
            # Output is a file - use parent directory
            output_dir = args.output.parent
            output_dir.mkdir(parents=True, exist_ok=True)
        else:
            # Output is a directory
            output_dir = args.output
            output_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger.info(f"Generating {args.tool} mappings...")
        return tracker.generate_for_tool(args.tool, output_dir)

    def _generate_all_mappings(self, tracker: SequenceTracker, args: argparse.Namespace) -> dict:
        """Generate all standard mapping formats."""
        if args.output.suffix:
            self.logger.error("When using --format all, output must be a directory")
            return {}
        
        output_dir = args.output
        output_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger.info("Generating all mapping formats...")
        return tracker.generate_mapping_files(output_dir, prefix=args.prefix)

    def _generate_single_format(self, tracker: SequenceTracker, args: argparse.Namespace) -> dict:
        """Generate a single mapping format."""
        if args.format == 'accession2taxid':
            if args.output.is_dir():
                output_path = args.output / f"{args.prefix}accession2taxid.txt"
            else:
                output_path = args.output
                output_path.parent.mkdir(parents=True, exist_ok=True)
            
            self.logger.info("Generating accession2taxid.txt...")
            count = tracker.generator.generate_accession2taxid(
                output_path, args.sequence_types
            )
            return {output_path.name: count}
            
        elif args.format == 'nucl2taxid':
            if args.output.is_dir():
                output_path = args.output / f"{args.prefix}nucl2taxid.txt"
            else:
                output_path = args.output
                output_path.parent.mkdir(parents=True, exist_ok=True)
            
            self.logger.info("Generating nucl2taxid.txt...")
            count = tracker.generator.generate_nucl2taxid(output_path)
            return {output_path.name: count}
            
        elif args.format == 'prot2taxid':
            if args.output.is_dir():
                output_path = args.output / f"{args.prefix}prot2taxid.txt"
            else:
                output_path = args.output
                output_path.parent.mkdir(parents=True, exist_ok=True)
            
            self.logger.info("Generating prot2taxid.txt...")
            count = tracker.generator.generate_prot2taxid(output_path)
            return {output_path.name: count}
            
        elif args.format == 'genome_sizes':
            if args.output.is_dir():
                output_path = args.output / f"{args.prefix}genome_sizes.txt"
            else:
                output_path = args.output
                output_path.parent.mkdir(parents=True, exist_ok=True)
            
            self.logger.info("Generating genome_sizes.txt...")
            count = tracker.generator.generate_genome_sizes(output_path)
            return {output_path.name: count}
        
        return {}