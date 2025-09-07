"""List missing command for identifying missing files based on accessions."""

import argparse
from pathlib import Path
from typing import Optional, Dict, Any
import logging

from .base import BaseCommand
from ...database.sqlite import SQLiteTaxonomyRepository
from ...core.exceptions import ValidationError, DatabaseError


class ListMissingCommand(BaseCommand):
    """Command to list missing files for specific accession types."""

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)

    @classmethod
    def register_parser(cls, subparsers) -> argparse.ArgumentParser:
        """Register list-missing command parser."""
        parser = subparsers.add_parser(
            'list-missing',
            help='List missing files based on imported accessions',
            description='Generate lists of missing accessions for targeted downloads',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  # List missing genome files to stdout
  flextaxd list-missing --database my_db.ftd --type genome
  
  # Save missing genome accessions to file
  flextaxd list-missing --database my_db.ftd --type genome --output missing_genomes.txt
  
  # List all missing files with details
  flextaxd list-missing --database my_db.ftd --type all --detailed
  
  # List missing proteins
  flextaxd list-missing --database my_db.ftd --type protein --output missing_proteins.txt

Output Format:
  Default: One accession per line
  --detailed: accession,accession_version,tax_id,type
  --json: JSON format with full metadata

Usage with download command:
  flextaxd list-missing --database my_db.ftd --type genome --output missing.txt
  flextaxd download --accession-file missing.txt --database my_db.ftd --output-dir ./genomes
            """,
        )

        parser.add_argument(
            '--database', '-d',
            type=Path,
            required=True,
            help='Path to FlexTaxD database file (.ftd)'
        )

        parser.add_argument(
            '--type', '-t',
            choices=['genome', 'protein', 'nucleotide', 'all'],
            default='genome',
            help='Type of missing files to list (default: genome)'
        )

        parser.add_argument(
            '--output', '-o',
            type=Path,
            help='Output file (default: stdout)'
        )

        parser.add_argument(
            '--format',
            choices=['simple', 'detailed', 'json'],
            default='simple',
            help='Output format (default: simple)'
        )

        parser.add_argument(
            '--include-tax-id',
            action='store_true',
            help='Include taxonomy ID in simple format output'
        )

        return parser

    def execute(self, args: argparse.Namespace) -> Optional[int]:
        """Execute list-missing command."""
        try:
            # Validate database exists
            self._validate_database_path(args.database, must_exist=True)

            # Load database
            with SQLiteTaxonomyRepository(args.database) as repository:
                # Get missing files analysis
                missing_analysis = repository.get_missing_files_analysis()
                
                # Extract missing files of requested type
                missing_files = self._extract_missing_by_type(missing_analysis, args.type)
                
                if not missing_files:
                    self.logger.info(f"No missing {args.type} files found")
                    if args.output:
                        # Create empty file
                        with open(args.output, 'w') as f:
                            pass
                    return 0
                
                # Output results
                self._output_missing_files(missing_files, args)
                
                return 0

        except ValidationError as e:
            self.logger.error(f"Validation error: {e.message}")
            print(f"Error: {e.message}")
            return 1

        except DatabaseError as e:
            self.logger.error(f"Database error: {e.message}")
            print(f"Database error: {e.message}")
            return 1

        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
            print(f"Error: {e}")
            return 1

    def _extract_missing_by_type(self, analysis: Dict[str, Any], file_type: str) -> Dict[str, Any]:
        """Extract missing files of specified type from analysis."""
        missing = analysis.get("missing_files", {})
        
        if file_type == "all":
            # Combine all types
            all_missing = []
            for type_name, files in missing.items():
                for file_info in files:
                    file_info['missing_type'] = type_name  # Add type info
                    all_missing.append(file_info)
            return {'all': all_missing}
        else:
            # Return specific type
            return {file_type: missing.get(file_type, [])}

    def _output_missing_files(self, missing_files: Dict[str, Any], args: argparse.Namespace) -> None:
        """Output missing files in requested format."""
        # Prepare output stream
        if args.output:
            output_file = open(args.output, 'w')
            self.logger.info(f"Writing missing files to {args.output}")
        else:
            import sys
            output_file = sys.stdout

        try:
            if args.format == 'json':
                self._output_json_format(missing_files, output_file)
            elif args.format == 'detailed':
                self._output_detailed_format(missing_files, output_file)
            else:
                self._output_simple_format(missing_files, output_file, args.include_tax_id)
                
        finally:
            if args.output:
                output_file.close()

    def _output_simple_format(self, missing_files: Dict[str, Any], output_file, include_tax_id: bool) -> None:
        """Output in simple format - one accession per line."""
        count = 0
        for file_type, files in missing_files.items():
            for file_info in files:
                accession = file_info.get('accession', '')
                if include_tax_id:
                    tax_id = file_info.get('tax_id', '')
                    output_file.write(f"{accession}\t{tax_id}\n")
                else:
                    output_file.write(f"{accession}\n")
                count += 1
        
        # Log summary to stderr if outputting to stdout
        if hasattr(output_file, 'name') and output_file.name == '<stdout>':
            import sys
            print(f"# Found {count} missing files", file=sys.stderr)

    def _output_detailed_format(self, missing_files: Dict[str, Any], output_file) -> None:
        """Output in detailed CSV format."""
        # Header
        output_file.write("accession,accession_version,tax_id,type\n")
        
        count = 0
        for file_type, files in missing_files.items():
            for file_info in files:
                accession = file_info.get('accession', '')
                accession_version = file_info.get('accession_version', '')
                tax_id = file_info.get('tax_id', '')
                missing_type = file_info.get('missing_type', file_type)
                
                output_file.write(f"{accession},{accession_version},{tax_id},{missing_type}\n")
                count += 1
        
        # Log summary to stderr if outputting to stdout
        if hasattr(output_file, 'name') and output_file.name == '<stdout>':
            import sys
            print(f"# Found {count} missing files", file=sys.stderr)

    def _output_json_format(self, missing_files: Dict[str, Any], output_file) -> None:
        """Output in JSON format."""
        import json
        
        # Restructure for cleaner JSON
        output_data = {
            "missing_files": missing_files,
            "summary": {}
        }
        
        # Add summary counts
        for file_type, files in missing_files.items():
            output_data["summary"][f"{file_type}_count"] = len(files)
        
        json.dump(output_data, output_file, indent=2, default=str)
        output_file.write('\n')  # Add newline for clean terminal output