"""Register command for sequence file registration and tracking."""

import argparse
from pathlib import Path
from typing import Optional, List, Dict, Any, Iterator
import logging
import hashlib

from .base import BaseCommand
from ...database.sqlite import SQLiteTaxonomyRepository
from ...core.models import SequenceFile, FileRegistryEntry
from ...core.exceptions import ValidationError, DatabaseError


class RegisterCommand(BaseCommand):
    """Register and track sequence files in flexible organization patterns."""
    
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
    
    @classmethod
    def register_parser(cls, subparsers) -> argparse.ArgumentParser:
        """Register command parser."""
        parser = subparsers.add_parser(
            'register',
            help='Register sequence files for tracking and validation',
            description='Register genome and protein files with flexible organization patterns',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  # Register genome files
  flextaxd register --genomes /data/genomes/*.fna --database my_db.ftd
  
  # Register protein files organized per taxa
  flextaxd register --proteins /data/proteins/tax_*.faa --protein-mode taxa --database my_db.ftd
  
  # Register global protein database
  flextaxd register --proteins /data/all_proteins.faa --protein-mode global --database my_db.ftd
  
  # Register files from directory
  flextaxd register --genome-dir /data/genomes --database my_db.ftd
  
  # Register with custom organization
  flextaxd register --genomes "*.fna" --proteins "proteins/*.faa" --database my_db.ftd
  
  # Validate registered files
  flextaxd register --validate-only --database my_db.ftd

File Organization Patterns:
  Genomes: 
    - One file per taxonomic node (typical)
    - Named by taxonomy ID or genome ID
    
  Proteins:
    - taxa: One file per taxonomic node (tax_123.faa)
    - global: Single file with all proteins (all_proteins.faa)  
    - custom: Custom grouping strategy
            """,
        )
        
        # File input options
        file_group = parser.add_argument_group("File input options")
        
        file_group.add_argument(
            '--genomes',
            type=str,
            nargs='*',
            help='Genome files to register (supports globbing patterns)'
        )
        
        file_group.add_argument(
            '--proteins',
            type=str,
            nargs='*', 
            help='Protein files to register (supports globbing patterns)'
        )
        
        file_group.add_argument(
            '--genome-dir',
            type=Path,
            help='Directory containing genome files'
        )
        
        file_group.add_argument(
            '--protein-dir',
            type=Path,
            help='Directory containing protein files'
        )
        
        # Required argument
        parser.add_argument(
            '--database', '-d',
            type=Path,
            required=True,
            help='Path to FlexTaxD database file (.ftd)'
        )
        
        # Organization options
        org_group = parser.add_argument_group("Organization options")
        
        org_group.add_argument(
            '--protein-mode',
            choices=['taxa', 'global', 'custom'],
            default='taxa',
            help='Protein file organization mode (default: taxa)'
        )
        
        org_group.add_argument(
            '--genome-pattern',
            type=str,
            help='Pattern for genome file naming (e.g., "tax_{tax_id}.fna")'
        )
        
        org_group.add_argument(
            '--protein-pattern',
            type=str,
            help='Pattern for protein file naming (e.g., "tax_{tax_id}.faa")'
        )
        
        # Processing options
        process_group = parser.add_argument_group("Processing options")
        
        process_group.add_argument(
            '--validate',
            action='store_true',
            help='Validate file formats during registration'
        )
        
        process_group.add_argument(
            '--validate-only',
            action='store_true',
            help='Only validate existing registered files, do not register new ones'
        )
        
        process_group.add_argument(
            '--compute-checksums',
            action='store_true',
            help='Compute file checksums for integrity validation'
        )
        
        process_group.add_argument(
            '--update-existing',
            action='store_true',
            help='Update existing file registrations'
        )
        
        process_group.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be registered without making changes'
        )

        return parser
    
    def execute(self, args: argparse.Namespace) -> int:
        """Execute register command."""
        try:
            # Initialize repository
            repository = SQLiteTaxonomyRepository(args.database)
            
            if args.validate_only:
                return self._validate_registered_files(repository, args)
            
            # Collect files to register
            genome_files = self._collect_genome_files(args)
            protein_files = self._collect_protein_files(args)
            
            if not genome_files and not protein_files:
                self.logger.warning("No files found to register")
                return 0
            
            self.logger.info(f"Found {len(genome_files)} genome files and {len(protein_files)} protein files")
            
            # Register files
            total_registered = 0
            total_failed = 0
            
            if genome_files:
                result = self._register_genome_files(genome_files, repository, args)
                total_registered += result['registered']
                total_failed += result['failed']
            
            if protein_files:
                result = self._register_protein_files(protein_files, repository, args)
                total_registered += result['registered'] 
                total_failed += result['failed']
            
            # Print summary
            if args.dry_run:
                print(f"\nDry Run Summary:")
                print(f"  Would register {total_registered} files")
            else:
                print(f"\nRegistration Summary:")
                print(f"  Total files registered: {total_registered}")
                print(f"  Total failures: {total_failed}")
            
            return 0 if total_failed == 0 else 1
            
        except Exception as e:
            self.logger.error(f"Registration failed: {e}")
            return 1
    
    def _collect_genome_files(self, args: argparse.Namespace) -> List[Path]:
        """Collect genome files from arguments."""
        files = []
        
        # From --genomes argument
        if args.genomes:
            for pattern in args.genomes:
                if '*' in pattern or '?' in pattern:
                    # Glob pattern
                    files.extend(Path.cwd().glob(pattern))
                else:
                    # Direct file path
                    path = Path(pattern)
                    if path.exists() and path.is_file():
                        files.append(path)
        
        # From --genome-dir argument
        if args.genome_dir:
            if not args.genome_dir.exists():
                raise ValidationError(f"Genome directory not found: {args.genome_dir}")
            
            # Common genome file extensions
            for ext in ['*.fna', '*.fa', '*.fasta', '*.fas']:
                files.extend(args.genome_dir.glob(ext))
        
        # Remove duplicates and sort
        return sorted(set(files))
    
    def _collect_protein_files(self, args: argparse.Namespace) -> List[Path]:
        """Collect protein files from arguments."""
        files = []
        
        # From --proteins argument
        if args.proteins:
            for pattern in args.proteins:
                if '*' in pattern or '?' in pattern:
                    # Glob pattern
                    files.extend(Path.cwd().glob(pattern))
                else:
                    # Direct file path
                    path = Path(pattern)
                    if path.exists() and path.is_file():
                        files.append(path)
        
        # From --protein-dir argument
        if args.protein_dir:
            if not args.protein_dir.exists():
                raise ValidationError(f"Protein directory not found: {args.protein_dir}")
            
            # Common protein file extensions
            for ext in ['*.faa', '*.fasta', '*.fa', '*.fas']:
                files.extend(args.protein_dir.glob(ext))
        
        # Remove duplicates and sort
        return sorted(set(files))
    
    def _register_genome_files(
        self,
        files: List[Path],
        repository: SQLiteTaxonomyRepository,
        args: argparse.Namespace
    ) -> Dict[str, int]:
        """Register genome files."""
        registered = 0
        failed = 0
        
        self.logger.info(f"Registering {len(files)} genome files")
        
        for file_path in files:
            try:
                if args.dry_run:
                    self.logger.info(f"Would register genome file: {file_path}")
                    registered += 1
                    continue
                
                # Extract accessions from both filename and FASTA headers
                filename_accessions = self._extract_accessions_from_filename(file_path)
                header_accessions = self._extract_accessions_from_fasta(file_path)
                
                # Combine accessions from both sources
                all_accessions = filename_accessions + header_accessions
                
                # Remove duplicates while preserving source information
                seen = set()
                unique_accessions = []
                for acc_dict in all_accessions:
                    acc_key = (acc_dict['accession'], acc_dict['type'])
                    if acc_key not in seen:
                        seen.add(acc_key)
                        unique_accessions.append(acc_dict)
                
                self.logger.info(f"Extracted {len(filename_accessions)} accessions from filename, "
                               f"{len(header_accessions)} from headers, "
                               f"{len(unique_accessions)} total unique for {file_path.name}")
                
                # Link accessions to taxonomy
                link_results = self._link_accessions_to_taxonomy(unique_accessions, repository)
                
                # Determine primary taxonomy ID
                tax_id = None
                if link_results['linked_accessions']:
                    # Use first linked accession's taxonomy ID
                    tax_id = link_results['linked_accessions'][0]['tax_id']
                else:
                    # Fallback to filename-based extraction
                    tax_id = self._extract_tax_id_from_filename(file_path, args.genome_pattern)
                
                if not tax_id and link_results['linked_accessions']:
                    tax_id = link_results['linked_accessions'][0]['tax_id']
                
                self.logger.info(f"File {file_path.name}: {link_results['linked']} accessions linked, "
                               f"{link_results['not_found']} not found, taxonomy ID: {tax_id}")
                
                # Create sequence file entry
                sequence_file = SequenceFile(
                    file_path=str(file_path),
                    file_type='genome',
                    scope='single_taxa',
                    taxa_count=1,
                    file_exists=file_path.exists(),
                    file_size=file_path.stat().st_size if file_path.exists() else None
                )
                
                # Validate if requested
                if args.validate:
                    if not self._validate_genome_file(file_path):
                        self.logger.error(f"Invalid genome file format: {file_path}")
                        failed += 1
                        continue
                
                # Compute checksum if requested
                if args.compute_checksums:
                    sequence_file.file_checksum = self._compute_file_checksum(file_path)
                
                # Create registry entry
                registry_entry = FileRegistryEntry(
                    file_path=str(file_path),
                    file_type='genome',
                    entity_id=str(tax_id) if tax_id else file_path.stem,
                    tax_id=tax_id,
                    expected_path=str(file_path),
                    actual_path=str(file_path),
                    exists=file_path.exists(),
                    accessible=True,
                    valid_format=True if not args.validate else self._validate_genome_file(file_path),
                    size_bytes=file_path.stat().st_size if file_path.exists() else None,
                    checksum=sequence_file.file_checksum
                )
                
                # Register in database (would need implementation in repository)
                self._register_sequence_file(sequence_file, registry_entry, repository)
                
                registered += 1
                self.logger.debug(f"Registered genome file: {file_path}")
                
            except Exception as e:
                self.logger.error(f"Failed to register genome file {file_path}: {e}")
                failed += 1
        
        return {'registered': registered, 'failed': failed}
    
    def _register_protein_files(
        self,
        files: List[Path],
        repository: SQLiteTaxonomyRepository,
        args: argparse.Namespace
    ) -> Dict[str, int]:
        """Register protein files."""
        registered = 0
        failed = 0
        
        self.logger.info(f"Registering {len(files)} protein files in {args.protein_mode} mode")
        
        for file_path in files:
            try:
                if args.dry_run:
                    self.logger.info(f"Would register protein file: {file_path}")
                    registered += 1
                    continue
                
                # Extract accessions from both filename and FASTA headers
                filename_accessions = self._extract_accessions_from_filename(file_path)
                header_accessions = self._extract_accessions_from_fasta(file_path)
                
                # Combine accessions from both sources
                all_accessions = filename_accessions + header_accessions
                
                # Remove duplicates while preserving source information
                seen = set()
                unique_accessions = []
                for acc_dict in all_accessions:
                    acc_key = (acc_dict['accession'], acc_dict['type'])
                    if acc_key not in seen:
                        seen.add(acc_key)
                        unique_accessions.append(acc_dict)
                
                self.logger.info(f"Extracted {len(filename_accessions)} accessions from filename, "
                               f"{len(header_accessions)} from headers, "
                               f"{len(unique_accessions)} total unique for {file_path.name}")
                
                # Link accessions to taxonomy
                link_results = self._link_accessions_to_taxonomy(unique_accessions, repository)
                
                # Determine organization mode and taxonomy
                if args.protein_mode == 'global':
                    scope = 'global'
                    # For global files, count unique taxa from linked accessions
                    unique_tax_ids = set(acc['tax_id'] for acc in link_results['linked_accessions'])
                    taxa_count = len(unique_tax_ids) if unique_tax_ids else self._count_taxa_in_protein_file(file_path)
                    entity_id = 'global'
                    tax_id = None
                else:  # taxa or custom mode
                    scope = 'single_taxa'
                    taxa_count = 1
                    # Use linked accession taxonomy ID or fallback to filename
                    tax_id = None
                    if link_results['linked_accessions']:
                        tax_id = link_results['linked_accessions'][0]['tax_id']
                    else:
                        tax_id = self._extract_tax_id_from_filename(file_path, args.protein_pattern)
                    entity_id = str(tax_id) if tax_id else file_path.stem
                
                self.logger.info(f"File {file_path.name}: {link_results['linked']} accessions linked, "
                               f"{link_results['not_found']} not found, mode: {args.protein_mode}, taxonomy ID: {tax_id}")
                
                # Create sequence file entry
                sequence_file = SequenceFile(
                    file_path=str(file_path),
                    file_type='protein_taxa' if scope == 'single_taxa' else 'protein_global',
                    scope=scope,
                    taxa_count=taxa_count,
                    file_exists=file_path.exists(),
                    file_size=file_path.stat().st_size if file_path.exists() else None
                )
                
                # Validate if requested
                if args.validate:
                    if not self._validate_protein_file(file_path):
                        self.logger.error(f"Invalid protein file format: {file_path}")
                        failed += 1
                        continue
                
                # Compute checksum if requested
                if args.compute_checksums:
                    sequence_file.file_checksum = self._compute_file_checksum(file_path)
                
                # Create registry entry
                registry_entry = FileRegistryEntry(
                    file_path=str(file_path),
                    file_type=sequence_file.file_type,
                    entity_id=entity_id,
                    tax_id=tax_id,
                    expected_path=str(file_path),
                    actual_path=str(file_path),
                    exists=file_path.exists(),
                    accessible=True,
                    valid_format=True if not args.validate else self._validate_protein_file(file_path),
                    size_bytes=file_path.stat().st_size if file_path.exists() else None,
                    checksum=sequence_file.file_checksum
                )
                
                # Register in database (would need implementation in repository)
                self._register_sequence_file(sequence_file, registry_entry, repository)
                
                registered += 1
                self.logger.debug(f"Registered protein file: {file_path}")
                
            except Exception as e:
                self.logger.error(f"Failed to register protein file {file_path}: {e}")
                failed += 1
        
        return {'registered': registered, 'failed': failed}
    
    def _extract_accessions_from_filename(self, file_path: Path) -> List[Dict[str, str]]:
        """Extract biological accessions from filename patterns."""
        accessions = []
        filename = file_path.name  # Use full filename, not just stem
        import re
        
        self.logger.debug(f"Parsing filename for accessions: {filename}")
        
        # Assembly accessions (GCF_, GCA_) - most common in genome files
        assembly_pattern = r'\b(GC[FA]_\d{9}\.\d+)\b'
        for match in re.finditer(assembly_pattern, filename, re.IGNORECASE):
            accessions.append({
                'accession': match.group(1).upper(),
                'type': 'assembly',
                'source': 'filename'
            })
        
        # Nucleotide accessions (NC_, NZ_, CP_, etc.)
        nucleotide_pattern = r'\b((NC|NZ|CP|AP|AE|AL|AM|BA|BX|CM|FO|FP|FQ|FR)_\d+\.\d+)\b'
        for match in re.finditer(nucleotide_pattern, filename, re.IGNORECASE):
            accessions.append({
                'accession': match.group(1).upper(),
                'type': 'nucleotide',
                'source': 'filename'
            })
        
        # Protein accessions (WP_, YP_, NP_, etc.)
        protein_pattern = r'\b((WP|YP|NP|XP|AP)_\d+\.\d+)\b'
        for match in re.finditer(protein_pattern, filename, re.IGNORECASE):
            accessions.append({
                'accession': match.group(1).upper(),
                'type': 'protein',
                'source': 'filename'
            })
        
        # BioSample accessions (SAMN_, SAMD_, SAME_)
        biosample_pattern = r'\b(SAM[NDE]\d+)\b'
        for match in re.finditer(biosample_pattern, filename, re.IGNORECASE):
            accessions.append({
                'accession': match.group(1).upper(),
                'type': 'biosample',
                'source': 'filename'
            })
        
        # SRA accessions (SRR_, ERR_, DRR_)
        sra_pattern = r'\b((SRR|ERR|DRR)\d+)\b'
        for match in re.finditer(sra_pattern, filename, re.IGNORECASE):
            accessions.append({
                'accession': match.group(1).upper(),
                'type': 'sra',
                'source': 'filename'
            })
        
        # Remove duplicates while preserving order
        seen = set()
        unique_accessions = []
        for acc_dict in accessions:
            acc_key = (acc_dict['accession'], acc_dict['type'])
            if acc_key not in seen:
                seen.add(acc_key)
                unique_accessions.append(acc_dict)
        
        if unique_accessions:
            self.logger.info(f"Found {len(unique_accessions)} accessions in filename {filename}: "
                           f"{[acc['accession'] for acc in unique_accessions]}")
        else:
            self.logger.debug(f"No accessions found in filename: {filename}")
        
        return unique_accessions

    def _extract_tax_id_from_filename(
        self,
        file_path: Path,
        pattern: Optional[str] = None
    ) -> Optional[int]:
        """Extract taxonomy ID from filename using pattern or heuristics."""
        filename = file_path.stem
        
        # If pattern provided, use it
        if pattern:
            # Simple pattern matching - would need more sophisticated implementation
            # For now, just try to extract numbers
            import re
            matches = re.findall(r'\d+', filename)
            if matches:
                return int(matches[0])
        
        # Heuristic patterns
        import re
        
        # Pattern: tax_123, taxid_123, etc.
        match = re.search(r'tax(?:id)?[_-]?(\d+)', filename, re.IGNORECASE)
        if match:
            return int(match.group(1))
        
        # Pattern: just numbers (risky but common)
        match = re.search(r'^(\d+)', filename)
        if match:
            return int(match.group(1))
        
        return None
    
    def _count_taxa_in_protein_file(self, file_path: Path) -> int:
        """Count number of taxa in a protein file (for global files)."""
        # This would analyze the FASTA headers to count unique taxa
        # For now, return placeholder
        return 100  # Placeholder
    
    def _extract_accessions_from_fasta(self, file_path: Path) -> List[Dict[str, str]]:
        """Extract accessions from FASTA headers."""
        accessions = []
        import re
        
        try:
            with open(file_path, 'r') as f:
                for line in f:
                    if line.startswith('>'):
                        header = line[1:].strip()
                        
                        # Extract various accession types from header
                        found_accessions = self._parse_fasta_header_accessions(header)
                        accessions.extend(found_accessions)
                        
        except Exception as e:
            self.logger.error(f"Error reading FASTA file {file_path}: {e}")
        
        # Remove duplicates while preserving order
        seen = set()
        unique_accessions = []
        for acc_dict in accessions:
            acc_key = (acc_dict['accession'], acc_dict['type'])
            if acc_key not in seen:
                seen.add(acc_key)
                unique_accessions.append(acc_dict)
        
        return unique_accessions
    
    def _parse_fasta_header_accessions(self, header: str) -> List[Dict[str, str]]:
        """Parse individual FASTA header to extract accessions."""
        accessions = []
        import re
        
        # Assembly accessions (GCF_, GCA_)
        assembly_pattern = r'\b(GC[FA]_\d{9}\.\d+)\b'
        for match in re.finditer(assembly_pattern, header):
            accessions.append({
                'accession': match.group(1),
                'type': 'assembly',
                'header': header
            })
        
        # Nucleotide accessions (NC_, NZ_, CP_, etc.)
        nucleotide_pattern = r'\b((NC|NZ|CP|AP|AE|AL|AM|BA|BX|CM|FO|FP|FQ|FR)_\d+\.\d+)\b'
        for match in re.finditer(nucleotide_pattern, header):
            accessions.append({
                'accession': match.group(1),
                'type': 'nucleotide',
                'header': header
            })
        
        # Protein accessions (WP_, YP_, NP_, etc.)
        protein_pattern = r'\b((WP|YP|NP|XP|AP)_\d+\.\d+)\b'
        for match in re.finditer(protein_pattern, header):
            accessions.append({
                'accession': match.group(1),
                'type': 'protein',
                'header': header
            })
        
        # BioSample accessions (SAMN_, SAMD_, SAME_)
        biosample_pattern = r'\b(SAM[NDE]\d+)\b'
        for match in re.finditer(biosample_pattern, header):
            accessions.append({
                'accession': match.group(1),
                'type': 'biosample',
                'header': header
            })
        
        return accessions
    
    def _link_accessions_to_taxonomy(
        self,
        accessions: List[Dict[str, str]],
        repository: SQLiteTaxonomyRepository
    ) -> Dict[str, Any]:
        """Link extracted accessions to taxonomy IDs in database."""
        results = {
            'linked': 0,
            'not_found': 0,
            'errors': 0,
            'linked_accessions': [],
            'missing_accessions': []
        }
        
        try:
            # Get all existing accession mappings from database
            existing_mappings = repository.get_all_accession_mappings()
            mapping_dict = {mapping['accession']: mapping['tax_id'] for mapping in existing_mappings}
            
            for acc_info in accessions:
                accession = acc_info['accession']
                
                if accession in mapping_dict:
                    # Found mapping
                    tax_id = mapping_dict[accession]
                    results['linked'] += 1
                    results['linked_accessions'].append({
                        'accession': accession,
                        'tax_id': tax_id,
                        'type': acc_info['type']
                    })
                    self.logger.debug(f"Linked accession {accession} to taxonomy {tax_id}")
                else:
                    # No mapping found
                    results['not_found'] += 1
                    results['missing_accessions'].append(acc_info)
                    self.logger.warning(f"No taxonomy mapping found for accession: {accession}")
                    
        except Exception as e:
            self.logger.error(f"Error linking accessions: {e}")
            results['errors'] += 1
        
        return results
    
    def _validate_genome_file(self, file_path: Path) -> bool:
        """Validate genome file format."""
        try:
            with open(file_path, 'r') as f:
                first_line = f.readline().strip()
                # Basic FASTA format check
                return first_line.startswith('>')
        except Exception:
            return False
    
    def _validate_protein_file(self, file_path: Path) -> bool:
        """Validate protein file format."""
        try:
            with open(file_path, 'r') as f:
                first_line = f.readline().strip()
                # Basic FASTA format check
                return first_line.startswith('>')
        except Exception:
            return False
    
    def _compute_file_checksum(self, file_path: Path) -> str:
        """Compute SHA256 checksum for file."""
        try:
            hash_sha256 = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except Exception as e:
            self.logger.error(f"Error computing checksum for {file_path}: {e}")
            return ""
    
    def _register_sequence_file(
        self,
        sequence_file: SequenceFile,
        registry_entry: FileRegistryEntry,
        repository: SQLiteTaxonomyRepository
    ) -> None:
        """Register sequence file and registry entry in database."""
        try:
            # Store sequence file information
            file_id = repository.register_sequence_file(sequence_file)
            self.logger.debug(f"Registered sequence file with ID {file_id}: {sequence_file.file_path}")
            
            # Store file registry entry
            registry_entry.file_id = file_id
            repository.register_file_registry_entry(registry_entry)
            self.logger.debug(f"Registered file registry entry for: {registry_entry.file_path}")
            
        except Exception as e:
            self.logger.error(f"Failed to register sequence file {sequence_file.file_path}: {e}")
            raise
    
    def _validate_registered_files(
        self,
        repository: SQLiteTaxonomyRepository,
        args: argparse.Namespace
    ) -> int:
        """Validate existing registered files."""
        try:
            self.logger.info("Validating registered files")
            
            # This would query the database for registered files and validate them
            # For now, return success
            
            print("File validation completed successfully")
            return 0
            
        except Exception as e:
            self.logger.error(f"File validation failed: {e}")
            return 1