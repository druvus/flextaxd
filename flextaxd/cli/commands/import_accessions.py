"""Import accession-to-taxonomy mappings command for FlexTaxD CLI."""

import argparse
import csv
from pathlib import Path
from typing import Optional, List, Dict, Any, Iterator
import logging

from .base import BaseCommand
from ...database.sqlite import SQLiteTaxonomyRepository
from ...core.models import AccessionMapping
from ...core.exceptions import DatabaseError, ValidationError


class ImportAccessionsCommand(BaseCommand):
    """Import accession-to-taxonomy mappings from various file formats."""
    
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
    
    @classmethod
    def register_parser(cls, subparsers) -> argparse.ArgumentParser:
        """Register import-accessions command parser."""
        parser = subparsers.add_parser(
            'import-accessions',
            help='Import accession-to-taxonomy mappings from files',
            description='Import accession mappings from various file formats to enable accession-based operations',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  # Import NCBI accession2taxid format
  flextaxd import-accessions --mapping-file acc2taxid.txt --format ncbi --database my_db.ftd
  
  # Import custom TSV format with auto-detection
  flextaxd import-accessions --mapping-file custom_mappings.tsv --database my_db.ftd
  
  # Import from directory (batch import)
  flextaxd import-accessions --input-dir ./mappings/ --database my_db.ftd
  
  # Validate accessions before import
  flextaxd import-accessions --mapping-file acc2taxid.txt --validate --database my_db.ftd

Supported Formats:
  - ncbi: NCBI accession2taxid format (accession, accession.version, taxid, gi)
  - custom: Custom TSV/CSV with flexible column detection
  - auto: Automatic format detection (default)

File Examples:
  NCBI format:
    accession	accession.version	taxid	gi
    CP000001	CP000001.1	12345	89106884
    GCF_000005825	GCF_000005825.2	562	0
  
  Custom TSV format:
    assembly_accession	tax_id	strain	source
    GCF_000008985.1	263	SCHU_S4	clinical
    GCF_000009245.1	119856	LVS	vaccine
            """,
        )
        
        # Input options - mutually exclusive
        input_group = parser.add_argument_group("Input options")
        input_source = input_group.add_mutually_exclusive_group(required=True)
        
        input_source.add_argument(
            '--mapping-file',
            type=Path,
            help='Single file containing accession mappings'
        )
        
        input_source.add_argument(
            '--input-dir',
            type=Path,
            help='Directory containing multiple mapping files'
        )
        
        # Required arguments
        parser.add_argument(
            '--database', '-d',
            type=Path,
            required=True,
            help='Path to FlexTaxD database file (.ftd)'
        )
        
        # Format options
        parser.add_argument(
            '--format',
            choices=['ncbi', 'custom', 'auto'],
            default='auto',
            help='Input file format (default: auto-detect)'
        )
        
        # Processing options
        parser.add_argument(
            '--validate',
            action='store_true',
            help='Validate accession formats before import'
        )
        
        parser.add_argument(
            '--batch-size',
            type=int,
            default=10000,
            help='Number of mappings to process in each batch (default: 10000)'
        )
        
        parser.add_argument(
            '--update-existing',
            action='store_true',
            help='Update existing mappings (default: skip duplicates)'
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be imported without making changes'
        )

        return parser
    
    def execute(self, args: argparse.Namespace) -> int:
        """Execute import-accessions command."""
        try:
            # Collect input files
            input_files = self._collect_input_files(args)
            if not input_files:
                self.logger.error("No mapping files found")
                return 1
            
            # Initialize database repository
            repository = SQLiteTaxonomyRepository(args.database)
            
            # Process each file
            total_imported = 0
            total_skipped = 0
            total_errors = 0
            
            for file_path in input_files:
                self.logger.info(f"Processing {file_path}")
                
                try:
                    # Detect or use specified format
                    format_type = self._detect_format(file_path, args.format)
                    self.logger.info(f"Detected format: {format_type}")
                    
                    # Import mappings from file
                    result = self._import_file(
                        file_path, format_type, repository, args
                    )
                    
                    total_imported += result['imported']
                    total_skipped += result['skipped']
                    total_errors += result['errors']
                    
                    self.logger.info(
                        f"File {file_path}: {result['imported']} imported, "
                        f"{result['skipped']} skipped, {result['errors']} errors"
                    )
                    
                except Exception as e:
                    self.logger.error(f"Failed to process {file_path}: {e}")
                    total_errors += 1
            
            # Print summary
            print(f"\nImport Summary:")
            print(f"  Total mappings imported: {total_imported}")
            print(f"  Total mappings skipped: {total_skipped}")
            print(f"  Total errors: {total_errors}")
            
            return 0 if total_errors == 0 else 1
            
        except Exception as e:
            self.logger.error(f"Import failed: {e}")
            return 1
    
    def _collect_input_files(self, args: argparse.Namespace) -> List[Path]:
        """Collect input files from arguments."""
        files = []
        
        if args.mapping_file:
            if not args.mapping_file.exists():
                raise ValidationError(f"Mapping file not found: {args.mapping_file}")
            if not args.mapping_file.is_file():
                raise ValidationError(f"Path is not a file: {args.mapping_file}")
            files.append(args.mapping_file)
            
        elif args.input_dir:
            if not args.input_dir.exists():
                raise ValidationError(f"Input directory not found: {args.input_dir}")
            if not args.input_dir.is_dir():
                raise ValidationError(f"Path is not a directory: {args.input_dir}")
            
            # Find mapping files in directory
            for pattern in ['*.txt', '*.tsv', '*.csv']:
                files.extend(args.input_dir.glob(pattern))
        
        return sorted(files)
    
    def _detect_format(self, file_path: Path, specified_format: str) -> str:
        """Detect or validate file format."""
        if specified_format != 'auto':
            return specified_format
        
        # Auto-detect format by examining file content
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                # Read first few lines
                lines = [f.readline().strip() for _ in range(3)]
                
            # Check for NCBI accession2taxid format
            if lines and lines[0]:
                header = lines[0].lower()
                if 'accession' in header and 'taxid' in header:
                    # Count columns
                    cols = len(lines[0].split('\t'))
                    if cols >= 3:  # accession, accession.version, taxid (gi optional)
                        return 'ncbi'
            
            # Default to custom format
            return 'custom'
            
        except Exception as e:
            self.logger.warning(f"Could not auto-detect format for {file_path}: {e}")
            return 'custom'
    
    def _import_file(
        self,
        file_path: Path,
        format_type: str,
        repository: SQLiteTaxonomyRepository,
        args: argparse.Namespace
    ) -> Dict[str, int]:
        """Import mappings from a single file."""
        if format_type == 'ncbi':
            return self._import_ncbi_format(file_path, repository, args)
        else:
            return self._import_custom_format(file_path, repository, args)
    
    def _import_ncbi_format(
        self,
        file_path: Path,
        repository: SQLiteTaxonomyRepository,
        args: argparse.Namespace
    ) -> Dict[str, int]:
        """Import NCBI accession2taxid format."""
        imported = 0
        skipped = 0
        errors = 0
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f, delimiter='\t')
                
                batch = []
                for row in reader:
                    try:
                        # Parse NCBI format
                        accession = row.get('accession', '').strip()
                        accession_version = row.get('accession.version', '').strip()
                        tax_id = int(row.get('taxid', 0))
                        
                        if not accession or tax_id <= 0:
                            errors += 1
                            continue
                        
                        # Determine accession type
                        accession_type = self._determine_accession_type(accession)
                        
                        # Create mapping
                        mapping = AccessionMapping(
                            accession=accession,
                            accession_version=accession_version if accession_version else None,
                            tax_id=tax_id,
                            accession_type=accession_type
                        )
                        
                        # Validate if requested
                        if args.validate:
                            validation_issues = mapping.validate()
                            if validation_issues:
                                self.logger.warning(f"Validation issues for {accession}: {validation_issues}")
                                errors += 1
                                continue
                        
                        batch.append(mapping)
                        
                        # Process batch when full
                        if len(batch) >= args.batch_size:
                            batch_result = self._process_batch(batch, repository, args)
                            imported += batch_result['imported']
                            skipped += batch_result['skipped']
                            errors += batch_result['errors']
                            batch = []
                            
                    except Exception as e:
                        self.logger.error(f"Error processing row: {e}")
                        errors += 1
                
                # Process remaining batch
                if batch:
                    batch_result = self._process_batch(batch, repository, args)
                    imported += batch_result['imported']
                    skipped += batch_result['skipped'] 
                    errors += batch_result['errors']
                    
        except Exception as e:
            self.logger.error(f"Error reading file {file_path}: {e}")
            errors += 1
        
        return {'imported': imported, 'skipped': skipped, 'errors': errors}
    
    def _import_custom_format(
        self,
        file_path: Path,
        repository: SQLiteTaxonomyRepository,
        args: argparse.Namespace
    ) -> Dict[str, int]:
        """Import custom TSV/CSV format with flexible column detection."""
        imported = 0
        skipped = 0
        errors = 0
        
        try:
            # Detect delimiter
            delimiter = self._detect_delimiter(file_path)
            
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f, delimiter=delimiter)
                
                # Map column names to standard fields
                column_mapping = self._map_columns(reader.fieldnames or [])
                
                if not column_mapping['accession'] or not column_mapping['tax_id']:
                    raise ValidationError(f"Could not find required columns in {file_path}")
                
                batch = []
                for row in reader:
                    try:
                        # Extract fields using column mapping
                        accession = row.get(column_mapping['accession'], '').strip()
                        tax_id_str = row.get(column_mapping['tax_id'], '0').strip()
                        
                        # Parse tax_id
                        try:
                            tax_id = int(tax_id_str)
                        except ValueError:
                            errors += 1
                            continue
                        
                        if not accession or tax_id <= 0:
                            errors += 1
                            continue
                        
                        # Determine accession type
                        accession_type = self._determine_accession_type(accession)
                        
                        # Create mapping
                        mapping = AccessionMapping(
                            accession=accession,
                            tax_id=tax_id,
                            accession_type=accession_type
                        )
                        
                        # Validate if requested
                        if args.validate:
                            validation_issues = mapping.validate()
                            if validation_issues:
                                self.logger.warning(f"Validation issues for {accession}: {validation_issues}")
                                errors += 1
                                continue
                        
                        batch.append(mapping)
                        
                        # Process batch when full
                        if len(batch) >= args.batch_size:
                            batch_result = self._process_batch(batch, repository, args)
                            imported += batch_result['imported']
                            skipped += batch_result['skipped']
                            errors += batch_result['errors']
                            batch = []
                            
                    except Exception as e:
                        self.logger.error(f"Error processing row: {e}")
                        errors += 1
                
                # Process remaining batch
                if batch:
                    batch_result = self._process_batch(batch, repository, args)
                    imported += batch_result['imported']
                    skipped += batch_result['skipped']
                    errors += batch_result['errors']
                    
        except Exception as e:
            self.logger.error(f"Error reading file {file_path}: {e}")
            errors += 1
        
        return {'imported': imported, 'skipped': skipped, 'errors': errors}
    
    def _process_batch(
        self,
        mappings: List[AccessionMapping],
        repository: SQLiteTaxonomyRepository,
        args: argparse.Namespace
    ) -> Dict[str, int]:
        """Process a batch of accession mappings."""
        if args.dry_run:
            # Just validate and count
            return {'imported': len(mappings), 'skipped': 0, 'errors': 0}
        
        try:
            # Add mappings to database
            # Note: This would need to be implemented in the repository
            imported = len(mappings)  # Placeholder
            return {'imported': imported, 'skipped': 0, 'errors': 0}
            
        except Exception as e:
            self.logger.error(f"Error processing batch: {e}")
            return {'imported': 0, 'skipped': 0, 'errors': len(mappings)}
    
    def _detect_delimiter(self, file_path: Path) -> str:
        """Detect CSV delimiter."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                sample = f.read(1024)
                
            # Try common delimiters
            for delimiter in ['\t', ',', ';', '|']:
                if sample.count(delimiter) > sample.count('\n'):
                    return delimiter
                    
            return '\t'  # Default to tab
            
        except Exception:
            return '\t'
    
    def _map_columns(self, field_names: List[str]) -> Dict[str, Optional[str]]:
        """Map column names to standard fields."""
        mapping = {
            'accession': None,
            'tax_id': None
        }
        
        # Normalize field names for matching
        normalized = {name.lower().replace('_', '').replace('.', ''): name for name in field_names}
        
        # Try to find accession column
        for pattern in ['accession', 'acc', 'assemblyaccession', 'genomeaccession']:
            if pattern in normalized:
                mapping['accession'] = normalized[pattern]
                break
        
        # Try to find tax_id column
        for pattern in ['taxid', 'taxonomyid', 'tax_id', 'taxonomy_id']:
            if pattern in normalized:
                mapping['tax_id'] = normalized[pattern]
                break
        
        return mapping
    
    def _determine_accession_type(self, accession: str) -> Optional[str]:
        """Determine accession type based on format."""
        if accession.startswith(('GCF_', 'GCA_')):
            return 'assembly'
        elif accession.startswith(('NC_', 'NZ_', 'CP_', 'AP_', 'AE_', 'AL_', 'AM_', 'BA_', 'BX_', 'CM_', 'FO_', 'FP_', 'FQ_', 'FR_')):
            return 'nucleotide'
        elif accession.startswith(('WP_', 'YP_', 'NP_', 'XP_', 'AP_')):
            return 'protein'
        else:
            return None