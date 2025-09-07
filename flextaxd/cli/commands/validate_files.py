"""Validate-files command for comprehensive file integrity checking."""

import argparse
from pathlib import Path
from typing import Optional, List, Dict, Any
import logging
import hashlib
import json
import csv
from datetime import datetime

from .base import BaseCommand
from ...database.sqlite import SQLiteTaxonomyRepository
from ...core.exceptions import ValidationError, DatabaseError


class ValidateFilesCommand(BaseCommand):
    """Command for comprehensive file integrity checking and validation."""
    
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
    
    @classmethod
    def register_parser(cls, subparsers) -> argparse.ArgumentParser:
        """Register validate-files command parser."""
        parser = subparsers.add_parser(
            'validate-files',
            help='Validate integrity of registered sequence files',
            description='Comprehensive file integrity checking and validation system',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  # Basic validation of all registered files
  flextaxd validate-files --database my_db.ftd
  
  # Comprehensive validation with checksum verification
  flextaxd validate-files --database my_db.ftd --level comprehensive
  
  # Validate only genome files
  flextaxd validate-files --database my_db.ftd --file-type genome
  
  # Output detailed report to JSON
  flextaxd validate-files --database my_db.ftd --output report.json --format json
  
  # Validate and attempt repairs
  flextaxd validate-files --database my_db.ftd --auto-repair --search-dirs /data,/backup
  
  # Quick check of file existence only
  flextaxd validate-files --database my_db.ftd --level basic --quiet

Validation Levels:
  basic: File existence and accessibility
  standard: Format validation and basic content checks  
  comprehensive: Full validation including checksums and accession consistency

Output Formats:
  text: Human-readable summary (default)
  json: Structured data for programmatic use
  csv: Tabular format for spreadsheet analysis
            """,
        )
        
        parser.add_argument(
            '--database', '-d',
            type=Path,
            required=True,
            help='Path to FlexTaxD database file (.ftd)'
        )
        
        # Validation scope options
        scope_group = parser.add_argument_group("Validation scope")
        
        scope_group.add_argument(
            '--level',
            choices=['basic', 'standard', 'comprehensive'],
            default='standard',
            help='Validation level (default: standard)'
        )
        
        scope_group.add_argument(
            '--file-type',
            choices=['genome', 'protein', 'all'],
            default='all',
            help='Type of files to validate (default: all)'
        )
        
        scope_group.add_argument(
            '--max-files',
            type=int,
            help='Maximum number of files to validate (for testing/sampling)'
        )
        
        # Output options
        output_group = parser.add_argument_group("Output options")
        
        output_group.add_argument(
            '--output', '-o',
            type=Path,
            help='Output file for detailed report'
        )
        
        output_group.add_argument(
            '--format',
            choices=['text', 'json', 'csv'],
            default='text',
            help='Output format (default: text)'
        )
        
        output_group.add_argument(
            '--summary-only',
            action='store_true',
            help='Show only summary, not individual file details'
        )
        
        # Repair options
        repair_group = parser.add_argument_group("Repair options")
        
        repair_group.add_argument(
            '--auto-repair',
            action='store_true',
            help='Attempt automatic repair of issues where possible'
        )
        
        repair_group.add_argument(
            '--search-dirs',
            type=str,
            help='Comma-separated directories to search for missing files'
        )
        
        repair_group.add_argument(
            '--update-checksums',
            action='store_true',
            help='Update checksums for files that have changed'
        )
        
        # Processing options
        process_group = parser.add_argument_group("Processing options")
        
        process_group.add_argument(
            '--parallel',
            type=int,
            default=4,
            help='Number of parallel validation processes (default: 4)'
        )
        
        process_group.add_argument(
            '--skip-large-files',
            type=int,
            help='Skip files larger than N MB for content validation'
        )
        
        process_group.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be validated without performing validation'
        )

        return parser
    
    def execute(self, args: argparse.Namespace) -> int:
        """Execute validate-files command."""
        try:
            # Validate database exists
            self._validate_database_path(args.database, must_exist=True)
            
            # Load database
            with SQLiteTaxonomyRepository(args.database) as repository:
                # Get files to validate
                files_to_validate = self._collect_files_to_validate(repository, args)
                
                if not files_to_validate:
                    self.logger.info("No files found to validate")
                    return 0
                
                self.logger.info(f"Found {len(files_to_validate)} files to validate")
                
                if args.dry_run:
                    return self._show_dry_run_summary(files_to_validate, args)
                
                # Perform validation
                validation_results = self._validate_files(files_to_validate, repository, args)
                
                # Attempt repairs if requested
                if args.auto_repair and validation_results['issues']:
                    repair_results = self._attempt_repairs(validation_results['issues'], repository, args)
                    validation_results['repairs'] = repair_results
                
                # Output results
                self._output_results(validation_results, args)
                
                # Return success if no critical issues found
                return 0 if validation_results['summary']['critical_issues'] == 0 else 1
                
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
    
    def _collect_files_to_validate(self, repository: SQLiteTaxonomyRepository, args: argparse.Namespace) -> List[Dict[str, Any]]:
        """Collect files that need validation."""
        try:
            conn = repository._get_connection()
            
            # Build query based on file type filter
            query = """
                SELECT sf.file_id, sf.file_path, sf.file_type, sf.scope, sf.taxa_count,
                       sf.file_exists, sf.file_checksum, sf.file_size, sf.last_validated,
                       fr.entity_id, fr.tax_id, fr.expected_path, fr.actual_path,
                       fr.exists, fr.accessible, fr.valid_format, fr.size_bytes,
                       fr.checksum, fr.last_checked, fr.issue_type
                FROM sequence_files sf
                LEFT JOIN file_registry fr ON sf.file_id = fr.file_id
            """
            
            params = []
            conditions = []
            
            # Filter by file type
            if args.file_type != 'all':
                if args.file_type == 'genome':
                    conditions.append("sf.file_type = ?")
                    params.append('genome')
                elif args.file_type == 'protein':
                    conditions.append("sf.file_type LIKE 'protein%'")
            
            # Add conditions to query
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            
            # Add limit if specified
            if args.max_files:
                query += f" LIMIT {args.max_files}"
            
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            
            files = []
            for row in rows:
                files.append({
                    'file_id': row[0],
                    'file_path': row[1],
                    'file_type': row[2],
                    'scope': row[3],
                    'taxa_count': row[4],
                    'file_exists': row[5],
                    'file_checksum': row[6],
                    'file_size': row[7],
                    'last_validated': row[8],
                    'entity_id': row[9],
                    'tax_id': row[10],
                    'expected_path': row[11],
                    'actual_path': row[12],
                    'registry_exists': row[13],
                    'registry_accessible': row[14],
                    'registry_valid_format': row[15],
                    'registry_size_bytes': row[16],
                    'registry_checksum': row[17],
                    'registry_last_checked': row[18],
                    'registry_issue_type': row[19]
                })
            
            return files
            
        except Exception as e:
            raise DatabaseError(f"Failed to collect files for validation: {e}")
    
    def _validate_files(self, files: List[Dict[str, Any]], repository: SQLiteTaxonomyRepository, args: argparse.Namespace) -> Dict[str, Any]:
        """Perform validation on collected files."""
        results = {
            'files_validated': 0,
            'files_passed': 0,
            'files_failed': 0,
            'issues': [],
            'summary': {
                'total_files': len(files),
                'critical_issues': 0,
                'warning_issues': 0,
                'info_issues': 0
            }
        }
        
        self.logger.info(f"Starting {args.level} validation of {len(files)} files")
        
        for file_info in files:
            try:
                file_path = Path(file_info['file_path'])
                file_results = self._validate_single_file(file_info, args)
                
                results['files_validated'] += 1
                
                if file_results['issues']:
                    results['files_failed'] += 1
                    results['issues'].extend(file_results['issues'])
                    
                    # Count issue severity
                    for issue in file_results['issues']:
                        if issue['severity'] == 'critical':
                            results['summary']['critical_issues'] += 1
                        elif issue['severity'] == 'warning':
                            results['summary']['warning_issues'] += 1
                        else:
                            results['summary']['info_issues'] += 1
                else:
                    results['files_passed'] += 1
                
                # Update validation timestamp in database
                if not args.dry_run:
                    self._update_validation_timestamp(file_info['file_id'], repository)
                    
            except Exception as e:
                self.logger.error(f"Failed to validate file {file_info['file_path']}: {e}")
                results['issues'].append({
                    'file_path': file_info['file_path'],
                    'issue_type': 'validation_error',
                    'severity': 'critical',
                    'description': f"Validation failed: {e}",
                    'suggestion': 'Check file accessibility and format'
                })
                results['files_failed'] += 1
                results['summary']['critical_issues'] += 1
        
        return results
    
    def _validate_single_file(self, file_info: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
        """Validate a single file comprehensively."""
        issues = []
        file_path = Path(file_info['file_path'])
        
        # Basic validation - file existence
        if not file_path.exists():
            issues.append({
                'file_path': str(file_path),
                'issue_type': 'missing_file',
                'severity': 'critical',
                'description': f"File does not exist: {file_path}",
                'suggestion': 'Check file path or search for file in alternative locations'
            })
            return {'issues': issues}
        
        # Accessibility check
        if not file_path.is_file():
            issues.append({
                'file_path': str(file_path),
                'issue_type': 'not_a_file',
                'severity': 'critical', 
                'description': f"Path exists but is not a file: {file_path}",
                'suggestion': 'Verify path points to a file, not a directory'
            })
            return {'issues': issues}
        
        # File size validation
        try:
            actual_size = file_path.stat().st_size
            if file_info['file_size'] and abs(actual_size - file_info['file_size']) > 1024:  # 1KB tolerance
                issues.append({
                    'file_path': str(file_path),
                    'issue_type': 'size_mismatch',
                    'severity': 'warning',
                    'description': f"File size mismatch: expected {file_info['file_size']}, got {actual_size}",
                    'suggestion': 'Update file size in database or check for file corruption'
                })
        except Exception as e:
            issues.append({
                'file_path': str(file_path),
                'issue_type': 'size_check_failed',
                'severity': 'warning',
                'description': f"Could not check file size: {e}",
                'suggestion': 'Check file permissions'
            })
        
        # Skip further validation for basic level
        if args.level == 'basic':
            return {'issues': issues}
        
        # Format validation for standard and comprehensive
        format_issues = self._validate_fasta_format(file_path, file_info['file_type'])
        issues.extend(format_issues)
        
        # Skip content validation for large files if requested
        if args.skip_large_files:
            try:
                size_mb = file_path.stat().st_size / (1024 * 1024)
                if size_mb > args.skip_large_files:
                    self.logger.debug(f"Skipping content validation for large file: {file_path} ({size_mb:.1f} MB)")
                    return {'issues': issues}
            except Exception:
                pass
        
        # Comprehensive validation
        if args.level == 'comprehensive':
            # Checksum validation
            if file_info['file_checksum']:
                checksum_issues = self._validate_file_checksum(file_path, file_info['file_checksum'])
                issues.extend(checksum_issues)
            
            # Accession consistency validation
            accession_issues = self._validate_accession_consistency(file_path, file_info)
            issues.extend(accession_issues)
        
        return {'issues': issues}
    
    def _validate_fasta_format(self, file_path: Path, file_type: str) -> List[Dict[str, Any]]:
        """Validate FASTA file format."""
        issues = []
        
        try:
            with open(file_path, 'r') as f:
                line_num = 0
                sequence_count = 0
                in_sequence = False
                
                for line in f:
                    line_num += 1
                    line = line.rstrip()
                    
                    if not line:
                        continue
                    
                    if line.startswith('>'):
                        # Header line
                        sequence_count += 1
                        in_sequence = True
                        
                        if len(line) < 2:
                            issues.append({
                                'file_path': str(file_path),
                                'issue_type': 'empty_header',
                                'severity': 'warning',
                                'description': f"Empty FASTA header at line {line_num}",
                                'suggestion': 'Check FASTA format integrity'
                            })
                    else:
                        # Sequence line
                        if not in_sequence:
                            issues.append({
                                'file_path': str(file_path),
                                'issue_type': 'sequence_before_header',
                                'severity': 'critical',
                                'description': f"Sequence data before header at line {line_num}",
                                'suggestion': 'Fix FASTA format - sequences must follow headers'
                            })
                            break
                        
                        # Basic sequence character validation
                        if file_type == 'genome':
                            # DNA/RNA sequences
                            valid_chars = set('ACGTUNacgtun-')
                            invalid_chars = set(line) - valid_chars
                            if invalid_chars:
                                issues.append({
                                    'file_path': str(file_path),
                                    'issue_type': 'invalid_nucleotide_characters',
                                    'severity': 'warning', 
                                    'description': f"Invalid nucleotide characters at line {line_num}: {sorted(invalid_chars)}",
                                    'suggestion': 'Check sequence data integrity'
                                })
                        elif 'protein' in file_type:
                            # Protein sequences
                            valid_chars = set('ABCDEFGHIKLMNPQRSTUVWYZX*-abcdefghiklmnpqrstuvwyzx')
                            invalid_chars = set(line) - valid_chars
                            if invalid_chars:
                                issues.append({
                                    'file_path': str(file_path),
                                    'issue_type': 'invalid_amino_acid_characters',
                                    'severity': 'warning',
                                    'description': f"Invalid amino acid characters at line {line_num}: {sorted(invalid_chars)}",
                                    'suggestion': 'Check protein sequence data integrity'
                                })
                    
                    # Stop after checking first few sequences for large files
                    if sequence_count > 100:
                        break
                
                if sequence_count == 0:
                    issues.append({
                        'file_path': str(file_path),
                        'issue_type': 'no_sequences',
                        'severity': 'critical',
                        'description': "No sequences found in FASTA file",
                        'suggestion': 'Check if file is empty or corrupted'
                    })
                    
        except UnicodeDecodeError:
            issues.append({
                'file_path': str(file_path),
                'issue_type': 'encoding_error',
                'severity': 'critical',
                'description': "File encoding error - not readable as text",
                'suggestion': 'Check file format and encoding'
            })
        except Exception as e:
            issues.append({
                'file_path': str(file_path),
                'issue_type': 'format_validation_error',
                'severity': 'warning',
                'description': f"Could not validate format: {e}",
                'suggestion': 'Check file accessibility and format'
            })
        
        return issues
    
    def _validate_file_checksum(self, file_path: Path, expected_checksum: str) -> List[Dict[str, Any]]:
        """Validate file checksum for integrity."""
        issues = []
        
        try:
            actual_checksum = self._compute_file_checksum(file_path)
            
            if actual_checksum != expected_checksum:
                issues.append({
                    'file_path': str(file_path),
                    'issue_type': 'checksum_mismatch',
                    'severity': 'critical',
                    'description': f"Checksum mismatch - file may be corrupted or modified",
                    'suggestion': 'Re-download file or update checksum if intentionally modified'
                })
                
        except Exception as e:
            issues.append({
                'file_path': str(file_path),
                'issue_type': 'checksum_validation_error', 
                'severity': 'warning',
                'description': f"Could not validate checksum: {e}",
                'suggestion': 'Check file accessibility'
            })
        
        return issues
    
    def _validate_accession_consistency(self, file_path: Path, file_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Validate accession consistency between file headers and database."""
        issues = []
        
        try:
            # Extract accessions from file headers
            accessions = self._extract_accessions_from_fasta(file_path)
            
            if not accessions:
                issues.append({
                    'file_path': str(file_path),
                    'issue_type': 'no_accessions_found',
                    'severity': 'warning',
                    'description': "No biological accessions found in FASTA headers",
                    'suggestion': 'Check if file headers contain proper accession identifiers'
                })
            
            # TODO: Add database consistency checking when accession mappings are available
            # This would require querying the database for expected accessions for this file
            
        except Exception as e:
            issues.append({
                'file_path': str(file_path),
                'issue_type': 'accession_validation_error',
                'severity': 'warning',
                'description': f"Could not validate accessions: {e}",
                'suggestion': 'Check file format and accessibility'
            })
        
        return issues
    
    def _extract_accessions_from_fasta(self, file_path: Path) -> List[str]:
        """Extract accessions from FASTA headers (reused from register command)."""
        accessions = []
        import re
        
        try:
            with open(file_path, 'r') as f:
                for line in f:
                    if line.startswith('>'):
                        header = line[1:].strip()
                        
                        # Extract various accession types
                        patterns = [
                            r'\b(GC[FA]_\d{9}\.\d+)\b',  # Assembly
                            r'\b((NC|NZ|CP|AP|AE|AL|AM|BA|BX|CM|FO|FP|FQ|FR)_\d+\.\d+)\b',  # Nucleotide
                            r'\b((WP|YP|NP|XP|AP)_\d+\.\d+)\b'  # Protein
                        ]
                        
                        for pattern in patterns:
                            matches = re.findall(pattern, header)
                            for match in matches:
                                if isinstance(match, tuple):
                                    accessions.append(match[0])
                                else:
                                    accessions.append(match)
                        
        except Exception as e:
            self.logger.error(f"Error extracting accessions from {file_path}: {e}")
        
        return list(set(accessions))  # Remove duplicates
    
    def _compute_file_checksum(self, file_path: Path) -> str:
        """Compute SHA256 checksum for file."""
        hash_sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()
    
    def _update_validation_timestamp(self, file_id: int, repository: SQLiteTaxonomyRepository) -> None:
        """Update validation timestamp in database."""
        try:
            conn = repository._get_connection()
            now = datetime.now().isoformat()
            
            conn.execute("""
                UPDATE sequence_files 
                SET last_validated = ? 
                WHERE file_id = ?
            """, (now, file_id))
            
            conn.execute("""
                UPDATE file_registry 
                SET last_checked = ? 
                WHERE file_id = ?
            """, (now, file_id))
            
        except Exception as e:
            self.logger.warning(f"Could not update validation timestamp: {e}")
    
    def _attempt_repairs(self, issues: List[Dict[str, Any]], repository: SQLiteTaxonomyRepository, args: argparse.Namespace) -> Dict[str, Any]:
        """Attempt automatic repairs of issues where possible."""
        repair_results = {
            'attempted': 0,
            'successful': 0,
            'failed': 0,
            'actions': []
        }
        
        search_dirs = []
        if args.search_dirs:
            search_dirs = [Path(d.strip()) for d in args.search_dirs.split(',')]
        
        for issue in issues:
            if issue['issue_type'] == 'missing_file' and search_dirs:
                # Try to find missing files
                repair_result = self._repair_missing_file(issue, search_dirs)
                repair_results['attempted'] += 1
                if repair_result['success']:
                    repair_results['successful'] += 1
                else:
                    repair_results['failed'] += 1
                repair_results['actions'].append(repair_result)
            
            elif issue['issue_type'] == 'checksum_mismatch' and args.update_checksums:
                # Update checksums for modified files
                repair_result = self._repair_checksum_mismatch(issue, repository)
                repair_results['attempted'] += 1
                if repair_result['success']:
                    repair_results['successful'] += 1
                else:
                    repair_results['failed'] += 1
                repair_results['actions'].append(repair_result)
        
        return repair_results
    
    def _repair_missing_file(self, issue: Dict[str, Any], search_dirs: List[Path]) -> Dict[str, Any]:
        """Try to find a missing file in search directories."""
        result = {
            'issue': issue,
            'action': 'search_missing_file',
            'success': False,
            'description': ''
        }
        
        file_path = Path(issue['file_path'])
        filename = file_path.name
        
        for search_dir in search_dirs:
            if not search_dir.exists():
                continue
                
            # Search for file with same name
            for candidate in search_dir.rglob(filename):
                if candidate.is_file():
                    result['success'] = True
                    result['description'] = f"Found file at {candidate}"
                    result['new_path'] = str(candidate)
                    return result
        
        result['description'] = f"File {filename} not found in search directories"
        return result
    
    def _repair_checksum_mismatch(self, issue: Dict[str, Any], repository: SQLiteTaxonomyRepository) -> Dict[str, Any]:
        """Update checksum for a file that has changed."""
        result = {
            'issue': issue,
            'action': 'update_checksum',
            'success': False,
            'description': ''
        }
        
        try:
            file_path = Path(issue['file_path'])
            new_checksum = self._compute_file_checksum(file_path)
            
            # Update in database
            conn = repository._get_connection()
            conn.execute("""
                UPDATE sequence_files 
                SET file_checksum = ? 
                WHERE file_path = ?
            """, (new_checksum, str(file_path)))
            
            conn.execute("""
                UPDATE file_registry 
                SET checksum = ? 
                WHERE file_path = ?
            """, (new_checksum, str(file_path)))
            
            result['success'] = True
            result['description'] = f"Updated checksum to {new_checksum[:16]}..."
            
        except Exception as e:
            result['description'] = f"Failed to update checksum: {e}"
        
        return result
    
    def _show_dry_run_summary(self, files: List[Dict[str, Any]], args: argparse.Namespace) -> int:
        """Show what would be validated without performing validation."""
        print(f"\nDry Run Summary:")
        print(f"  Would validate {len(files)} files")
        print(f"  Validation level: {args.level}")
        print(f"  File type filter: {args.file_type}")
        
        if args.parallel > 1:
            print(f"  Parallel processes: {args.parallel}")
        
        if args.skip_large_files:
            print(f"  Skip files larger than: {args.skip_large_files} MB")
        
        # File type breakdown
        type_counts = {}
        for file_info in files:
            file_type = file_info['file_type']
            type_counts[file_type] = type_counts.get(file_type, 0) + 1
        
        print("\n  File type breakdown:")
        for file_type, count in sorted(type_counts.items()):
            print(f"    {file_type}: {count}")
        
        return 0
    
    def _output_results(self, results: Dict[str, Any], args: argparse.Namespace) -> None:
        """Output validation results in requested format."""
        if args.format == 'json':
            self._output_json_results(results, args)
        elif args.format == 'csv':
            self._output_csv_results(results, args)
        else:
            self._output_text_results(results, args)
    
    def _output_text_results(self, results: Dict[str, Any], args: argparse.Namespace) -> None:
        """Output results in human-readable text format."""
        summary = results['summary']
        
        # Print summary
        print(f"\nFile Validation Results:")
        print(f"{'='*50}")
        print(f"Total files: {summary['total_files']}")
        print(f"Files validated: {results['files_validated']}")
        print(f"Files passed: {results['files_passed']}")
        print(f"Files with issues: {results['files_failed']}")
        print()
        print(f"Issue Summary:")
        print(f"  Critical issues: {summary['critical_issues']}")
        print(f"  Warning issues: {summary['warning_issues']}")  
        print(f"  Info issues: {summary['info_issues']}")
        
        # Print repair results if available
        if 'repairs' in results:
            repairs = results['repairs']
            print(f"\nRepair Results:")
            print(f"  Attempted: {repairs['attempted']}")
            print(f"  Successful: {repairs['successful']}")
            print(f"  Failed: {repairs['failed']}")
        
        # Print individual issues if not summary-only
        if not args.summary_only and results['issues']:
            print(f"\nDetailed Issues:")
            print(f"{'-'*50}")
            
            for issue in results['issues'][:20]:  # Limit to first 20 issues
                print(f"File: {Path(issue['file_path']).name}")
                print(f"  Type: {issue['issue_type']} ({issue['severity']})")
                print(f"  Description: {issue['description']}")
                print(f"  Suggestion: {issue['suggestion']}")
                print()
            
            if len(results['issues']) > 20:
                print(f"... and {len(results['issues']) - 20} more issues")
                print("Use --output to save full report to file")
        
        # Write detailed report to file if requested
        if args.output:
            self._write_detailed_report(results, args)
            print(f"\nDetailed report written to: {args.output}")
    
    def _output_json_results(self, results: Dict[str, Any], args: argparse.Namespace) -> None:
        """Output results in JSON format."""
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(results, f, indent=2, default=str)
            print(f"JSON report written to: {args.output}")
        else:
            print(json.dumps(results, indent=2, default=str))
    
    def _output_csv_results(self, results: Dict[str, Any], args: argparse.Namespace) -> None:
        """Output results in CSV format."""
        if not args.output:
            print("CSV format requires --output file")
            return
        
        with open(args.output, 'w', newline='') as f:
            writer = csv.writer(f)
            
            # Write header
            writer.writerow(['file_path', 'issue_type', 'severity', 'description', 'suggestion'])
            
            # Write issues
            for issue in results['issues']:
                writer.writerow([
                    issue['file_path'],
                    issue['issue_type'],
                    issue['severity'],
                    issue['description'],
                    issue['suggestion']
                ])
        
        print(f"CSV report written to: {args.output}")
    
    def _write_detailed_report(self, results: Dict[str, Any], args: argparse.Namespace) -> None:
        """Write detailed validation report to file."""
        with open(args.output, 'w') as f:
            f.write("FlexTaxD File Validation Report\n")
            f.write("="*50 + "\n")
            f.write(f"Generated: {datetime.now().isoformat()}\n")
            f.write(f"Database: {args.database}\n")
            f.write(f"Validation level: {args.level}\n")
            f.write(f"File type filter: {args.file_type}\n")
            f.write("\n")
            
            # Summary
            summary = results['summary']
            f.write("Summary:\n")
            f.write("-"*20 + "\n")
            f.write(f"Total files: {summary['total_files']}\n")
            f.write(f"Files validated: {results['files_validated']}\n")
            f.write(f"Files passed: {results['files_passed']}\n")
            f.write(f"Files with issues: {results['files_failed']}\n")
            f.write(f"Critical issues: {summary['critical_issues']}\n")
            f.write(f"Warning issues: {summary['warning_issues']}\n")
            f.write(f"Info issues: {summary['info_issues']}\n")
            f.write("\n")
            
            # Detailed issues
            if results['issues']:
                f.write("Detailed Issues:\n")
                f.write("-"*50 + "\n")
                
                for i, issue in enumerate(results['issues'], 1):
                    f.write(f"{i}. {Path(issue['file_path']).name}\n")
                    f.write(f"   Type: {issue['issue_type']} ({issue['severity']})\n")
                    f.write(f"   Description: {issue['description']}\n")
                    f.write(f"   Suggestion: {issue['suggestion']}\n")
                    f.write(f"   Full path: {issue['file_path']}\n")
                    f.write("\n")
            
            # Repair results
            if 'repairs' in results:
                repairs = results['repairs']
                f.write("Repair Results:\n")
                f.write("-"*30 + "\n")
                f.write(f"Attempted: {repairs['attempted']}\n")
                f.write(f"Successful: {repairs['successful']}\n")
                f.write(f"Failed: {repairs['failed']}\n")
                f.write("\n")
                
                for action in repairs['actions']:
                    f.write(f"Action: {action['action']}\n")
                    f.write(f"Success: {action['success']}\n") 
                    f.write(f"Description: {action['description']}\n")
                    f.write("\n")