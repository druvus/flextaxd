"""Download command for accession-based genome and protein downloads."""

import argparse
from pathlib import Path
from typing import Optional, List, Dict, Any
import logging

from .base import BaseCommand
from ...database.sqlite import SQLiteTaxonomyRepository
from ...core.exceptions import ValidationError, DatabaseError
from ...utils.ncbi_datasets import NCBIDatasetsManager, NCBIDatasetsError, check_ncbi_datasets_installation


class DownloadCommand(BaseCommand):
    """Download genomes and proteins based on specific accession lists only."""
    
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
    
    @classmethod
    def register_parser(cls, subparsers) -> argparse.ArgumentParser:
        """Register download command parser."""
        parser = subparsers.add_parser(
            'download',
            help='Download genomes and proteins by accession lists',
            description='Download sequence data from NCBI based on specific accession lists for precise control. '
                       'By default, genome files are moved to the output directory root for easier access. '
                       'Use --keep-structure to preserve the original NCBI nested directory layout.',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  # Download genomes with flat structure (default)
  flextaxd download --accession-file genome_accessions.txt --database my_db.ftd --output-dir ./genomes
  
  # Download specific genomes by accession
  flextaxd download --accessions GCF_000005825.2,GCF_000009605.1 --type genome --database my_db.ftd --output-dir ./data
  
  # Download missing genomes from database (based on imported accessions)
  flextaxd download --missing --type genome --database my_db.ftd --output-dir ./missing
  
  # Keep NCBI nested directory structure
  flextaxd download --missing --type genome --database my_db.ftd --output-dir ./genomes --keep-structure
  
  # Clean file paths for missing files (makes them downloadable again)
  flextaxd download --clean-missing-paths --database my_db.ftd
  
  # Download with assembly level filtering
  flextaxd download --accession-file accessions.txt --type genome --assembly-level complete --database my_db.ftd
  
  # Dry run to see what would be downloaded
  flextaxd download --accessions GCF_000005825.2 --type genome --dry-run --database test.ftd

Accession File Format:
  One accession per line, supporting:
  - Assembly accessions: GCF_000005825.2, GCA_000005825.2
  - Nucleotide accessions: NC_000913.3, NZ_CP009273.1
  - Protein accessions: WP_000001234.1, YP_000001234.1

Note: This command uses accession-based downloads for precise genome control.
For initial taxonomy setup, use 'flextaxd create' with taxonomy files.
            """,
        )
        
        # Download target - mutually exclusive (not required if using --clean-missing-paths)
        target_group = parser.add_argument_group("Download target")
        target_source = target_group.add_mutually_exclusive_group(required=False)
        
        target_source.add_argument(
            '--accessions',
            type=str,
            help='Comma-separated list of accessions to download (e.g., "GCF_000005825.2,GCF_000009605.1")'
        )
        
        target_source.add_argument(
            '--accession-file',
            type=Path,
            help='File containing accessions to download (one per line)'
        )
        
        target_source.add_argument(
            '--missing',
            action='store_true',
            help='Download missing files from database based on stored accession mappings'
        )
        
        target_source.add_argument(
            '--missing-genomes',
            action='store_true',
            help='Download genomes missing from database (deprecated: use --missing --type genome)'
        )
        
        # Required arguments
        parser.add_argument(
            '--database', '-d',
            type=Path,
            required=True,
            help='Path to FlexTaxD database file (.ftd)'
        )
        
        parser.add_argument(
            '--output-dir',
            type=Path,
            default=Path('./genomes'),
            help='Directory for downloaded files (default: ./genomes)'
        )
        
        # Download options
        download_group = parser.add_argument_group("Download options")
        
        download_group.add_argument(
            '--type', '-t',
            choices=['genome', 'protein', 'nucleotide', 'all'],
            default='genome',
            help='Type of sequences to download (default: genome)'
        )
        
        download_group.add_argument(
            '--assembly-level',
            choices=['complete', 'chromosome', 'scaffold', 'contig', 'all'],
            default='complete',
            help='Assembly level filter for genomes (default: complete)'
        )
        
        download_group.add_argument(
            '--max-genomes',
            type=int,
            help='Maximum number of genomes to download (no limit if not specified)'
        )
        
        download_group.add_argument(
            '--include-proteins',
            action='store_true',
            help='Extract proteins from downloaded genomes'
        )
        
        download_group.add_argument(
            '--batch-size',
            type=int,
            default=50,
            help='Number of genomes to download per batch (default: 50)'
        )
        
        download_group.add_argument(
            '--retry',
            type=int,
            default=3,
            help='Number of retry attempts for failed downloads (default: 3)'
        )
        
        # Processing options
        parser.add_argument(
            '--update-database',
            action='store_true',
            help='Update database with downloaded genome information (default: True unless --no-update-database is specified)'
        )
        
        parser.add_argument(
            '--no-update-database',
            action='store_true',
            help='Do not update database with downloaded genome information'
        )
        
        parser.add_argument(
            '--clean-missing-paths',
            action='store_true',
            help='Clean file paths for genomes where files are missing (makes them downloadable again)'
        )
        
        parser.add_argument(
            '--validate-downloads',
            action='store_true',
            help='Validate downloaded files after download'
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be downloaded without downloading'
        )
        
        # Cache options
        cache_group = parser.add_argument_group("Cache options")
        
        cache_group.add_argument(
            '--cache-dir',
            type=Path,
            help='Directory to cache downloads (default: ~/.flextaxd/cache)'
        )
        
        cache_group.add_argument(
            '--no-cache',
            action='store_true',
            help='Disable download caching'
        )
        
        # File organization options
        file_org_group = parser.add_argument_group("File organization")
        
        file_structure = file_org_group.add_mutually_exclusive_group()
        
        file_structure.add_argument(
            '--flatten-files',
            action='store_true',
            default=True,
            help='Move genome files to output directory root (default behavior)'
        )
        
        file_structure.add_argument(
            '--keep-structure',
            action='store_true',
            help='Preserve NCBI nested directory structure'
        )
        
        file_org_group.add_argument(
            '--remove-ncbi-dirs',
            action='store_true',
            default=True,
            help='Remove empty NCBI directories after flattening (default: True)'
        )
        
        file_org_group.add_argument(
            '--keep-metadata',
            action='store_true',
            help='Keep NCBI metadata files (md5sum.txt, README.md, ncbi_dataset/) after download'
        )

        return parser
    
    def execute(self, args: argparse.Namespace) -> int:
        """Execute download command."""
        try:
            # Check NCBI Datasets installation
            install_check = check_ncbi_datasets_installation()
            if not install_check.get("installed", False):
                self.logger.error(
                    f"NCBI Datasets CLI not found: {install_check.get('error', 'Unknown error')}\n"
                    f"Please install it first:\n"
                    f"curl -o datasets 'https://ftp.ncbi.nlm.nih.gov/pub/datasets/command-line/v2/linux-amd64/datasets'\n"
                    f"chmod +x datasets && sudo mv datasets /usr/local/bin/"
                )
                return 1
            
            # Initialize repository and manager
            repository = SQLiteTaxonomyRepository(args.database)
            
            # Set default update_database behavior: True unless --no-update-database is specified
            if not hasattr(args, 'update_database'):
                args.update_database = True
            if args.no_update_database:
                args.update_database = False
            elif not args.update_database:  # If neither flag was set
                args.update_database = True
            
            # Initialize NCBI datasets manager (only accepts cache_dir)
            cache_dir = args.cache_dir if not args.no_cache else None
            datasets_manager = NCBIDatasetsManager(cache_dir=cache_dir)
            
            # Validate database file exists
            if not args.database.exists():
                self.logger.error(f"Database file not found: {args.database}")
                return 1
            
            # Handle clean missing paths option
            if args.clean_missing_paths:
                return self._handle_clean_missing_paths(args, repository)
            
            # Ensure we have a download target if not cleaning paths
            if not any([args.accessions, args.accession_file, args.missing, args.missing_genomes]):
                self.logger.error("Must specify one of: --accessions, --accession-file, --missing, --missing-genomes, or --clean-missing-paths")
                return 1
            
            # Collect accessions to download
            accessions = self._collect_accessions(args, repository)
            if not accessions:
                self.logger.info("No accessions found to download")
                if args.missing:
                    self.logger.info("This means all required files are already present or no accession mappings exist.")
                    self.logger.info("Use 'flextaxd stats --database <db>' to check genome file status.")
                return 0
            
            self.logger.info(f"Found {len(accessions)} accessions to download")
            
            # Apply max_genomes limit if specified
            if args.max_genomes and len(accessions) > args.max_genomes:
                accessions = accessions[:args.max_genomes]
                self.logger.info(f"Limited to first {args.max_genomes} accessions due to --max-genomes setting")
            
            # Validate accessions
            valid_accessions = self._validate_accessions(accessions)
            invalid_count = len(accessions) - len(valid_accessions)
            
            if invalid_count > 0:
                self.logger.warning(f"Found {invalid_count} invalid accessions (will be skipped)")
            
            if not valid_accessions:
                self.logger.error("No valid accessions found after validation")
                self.logger.error("Supported formats: GCF_000000000.0 (assembly), NC_000000.0 (nucleotide), WP_000000000.0 (protein)")
                return 1
            
            self.logger.info(f"Proceeding with {len(valid_accessions)} valid accessions")
            self.logger.info(f"First few valid accessions: {valid_accessions[:3] if len(valid_accessions) >= 3 else valid_accessions}")
            
            # Create output directory with validation
            try:
                args.output_dir.mkdir(parents=True, exist_ok=True)
                
                # Test write permissions
                test_file = args.output_dir / ".write_test"
                test_file.touch()
                test_file.unlink()
                
            except PermissionError:
                self.logger.error(f"No write permission to output directory: {args.output_dir}")
                return 1
            except Exception as e:
                self.logger.error(f"Cannot create output directory {args.output_dir}: {e}")
                return 1
            
            # Download genomes by accession
            total_downloaded = 0
            total_failed = 0
            
            # Process accessions in batches
            batch_size = args.batch_size
            for i in range(0, len(valid_accessions), batch_size):
                batch_accessions = valid_accessions[i:i+batch_size]
                
                try:
                    self.logger.info(f"Processing batch {i//batch_size + 1}: {len(batch_accessions)} accessions")
                    
                    if args.dry_run:
                        # Just show what would be downloaded
                        result = self._simulate_accession_download(batch_accessions, args)
                        self.logger.info(f"Would download {result['count']} genomes from batch")
                        total_downloaded += result['count']
                    else:
                        # Actually download
                        result = self._download_accessions(
                            batch_accessions, datasets_manager, repository, args
                        )
                        total_downloaded += result['downloaded']
                        total_failed += result['failed']
                        
                        self.logger.info(
                            f"Batch {i//batch_size + 1}: {result['downloaded']} downloaded, "
                            f"{result['failed']} failed"
                        )
                        
                except Exception as e:
                    self.logger.error(f"Failed to process batch {i//batch_size + 1}: {e}")
                    total_failed += len(batch_accessions)
            
            # Print summary
            if args.dry_run:
                print(f"\nDry Run Summary:")
                print(f"  Would download {total_downloaded} genomes")
            else:
                print(f"\nDownload Summary:")
                print(f"  Total genomes downloaded: {total_downloaded}")
                print(f"  Total failures: {total_failed}")
            
            return 0 if total_failed == 0 else 1
            
        except KeyboardInterrupt:
            self.logger.info("Download cancelled by user")
            return 130
        except Exception as e:
            self.logger.error(f"Download failed: {e}")
            self.logger.debug("Full error details:", exc_info=True)
            return 1
    
    def _collect_accessions(self, args: argparse.Namespace, repository: SQLiteTaxonomyRepository) -> List[str]:
        """Collect accessions from command line arguments."""
        accessions = []
        
        try:
            if args.accessions:
                # Parse comma-separated accessions
                raw_accessions = [acc.strip() for acc in args.accessions.split(',')]
                accessions = [acc for acc in raw_accessions if acc]  # Remove empty strings
                self.logger.info(f"Loaded {len(accessions)} accessions from command line")
                
            elif args.accession_file:
                # Read accessions from file
                if not args.accession_file.exists():
                    raise ValidationError(f"Accession file not found: {args.accession_file}")
                
                try:
                    with open(args.accession_file, 'r') as f:
                        line_count = 0
                        for line in f:
                            line_count += 1
                            line = line.strip()
                            if line and not line.startswith('#'):  # Skip comments and empty lines
                                accessions.append(line)
                    
                    self.logger.info(f"Loaded {len(accessions)} accessions from {line_count} lines in {args.accession_file}")
                    
                except Exception as e:
                    raise ValidationError(f"Error reading accession file {args.accession_file}: {e}")
                    
            elif args.missing_genomes:
                # Get accessions for missing genomes from database (deprecated path)
                self.logger.warning("--missing-genomes is deprecated, use --missing --type genome instead")
                accessions = self._get_missing_accessions_by_type(repository, 'genome')
            
            elif args.missing:
                # Get comprehensive status and provide detailed reporting
                self.logger.info(f"Analyzing {args.type} file status in database...")
                status = repository.get_comprehensive_genome_status()
                
                # Print comprehensive report
                self._print_genome_status_report(status)
                
                # Get accessions for missing files
                accessions = self._get_missing_accessions_by_type(repository, args.type)
                
                if not accessions:
                    summary = status.get('summary', {})
                    self.logger.info(f"\n✅ All genomes with accession mappings have been downloaded")
                    self.logger.info(f"   - Total genomes in database: {summary.get('total_genomes', 0)}")
                    self.logger.info(f"   - Genomes with valid files: {summary.get('valid_files_total', 0)}")
                    self.logger.info(f"   - Downloadable accessions available: {status.get('downloadable_count', 0)}")
                    
                    # Check if there are paths that need cleaning
                    missing_with_paths = status.get('missing_with_paths', [])
                    if missing_with_paths:
                        self.logger.info(f"\n💡 Tip: Found {len(missing_with_paths)} genomes with file paths to missing files.")
                        self.logger.info(f"     Use 'flextaxd download --clean-missing-paths --database {args.database}' to clean these paths.")
            
            # Remove duplicates while preserving order
            if accessions:
                seen = set()
                unique_accessions = []
                for acc in accessions:
                    if acc not in seen:
                        seen.add(acc)
                        unique_accessions.append(acc)
                accessions = unique_accessions
                
                if len(unique_accessions) < len(accessions):
                    self.logger.info(f"Removed {len(accessions) - len(unique_accessions)} duplicate accessions")
        
        except Exception as e:
            self.logger.error(f"Error collecting accessions: {e}")
            raise
        
        return accessions
    
    def _get_missing_accessions_by_type(self, repository: SQLiteTaxonomyRepository, accession_type: str) -> List[str]:
        """Get accessions for missing files by type."""
        try:
            # Get missing files analysis from database
            analysis = repository.get_missing_files_analysis()
            missing_files = analysis.get("missing_files", {})
            
            accessions = []
            
            if accession_type == 'genome':
                # Get missing genome accessions
                genome_missing = missing_files.get('genome', [])
                accessions = [item['accession'] for item in genome_missing if item.get('accession')]
                
            elif accession_type == 'protein':
                # Get missing protein accessions
                protein_missing = missing_files.get('protein', [])
                accessions = [item['accession'] for item in protein_missing if item.get('accession')]
                
            elif accession_type == 'nucleotide':
                # Get missing nucleotide accessions
                nucleotide_missing = missing_files.get('nucleotide', [])
                accessions = [item['accession'] for item in nucleotide_missing if item.get('accession')]
                
            elif accession_type == 'all':
                # Get all missing accessions regardless of type
                for file_type, missing_items in missing_files.items():
                    for item in missing_items:
                        if item.get('accession'):
                            accessions.append(item['accession'])
                            
            # Remove duplicates while preserving order
            seen = set()
            unique_accessions = []
            for acc in accessions:
                if acc not in seen:
                    seen.add(acc)
                    unique_accessions.append(acc)
            
            self.logger.info(f"Found {len(unique_accessions)} missing {accession_type} accessions")
            return unique_accessions
            
        except Exception as e:
            self.logger.error(f"Error finding missing {accession_type} accessions: {e}")
            return []
    
    def _get_missing_genome_accessions(self, repository: SQLiteTaxonomyRepository) -> List[str]:
        """Get accessions for genomes missing from database."""
        try:
            conn = repository._get_connection()
            
            # Find accessions in accession_mappings that don't have corresponding genome files
            cursor = conn.execute("""
                SELECT DISTINCT am.accession
                FROM accession_mappings am
                WHERE am.accession_type IN ('assembly', 'nucleotide')
                AND am.tax_id NOT IN (
                    SELECT DISTINCT tax_id 
                    FROM genomes_v2 
                    WHERE file_exists = TRUE
                )
                ORDER BY am.accession
                LIMIT 500
            """)
            
            missing_accessions = [row[0] for row in cursor.fetchall()]
            self.logger.info(f"Found {len(missing_accessions)} missing genome accessions")
            
            return missing_accessions
            
        except Exception as e:
            self.logger.error(f"Error finding missing genome accessions: {e}")
            return []
    
    def _validate_accessions(self, accessions: List[str]) -> List[str]:
        """Validate and filter accessions."""
        valid_accessions = []
        
        for accession in accessions:
            if self._is_valid_accession(accession):
                valid_accessions.append(accession)
            else:
                self.logger.warning(f"Invalid accession format: {accession}")
        
        return valid_accessions
    
    def _is_valid_accession(self, accession: str) -> bool:
        """Check if accession has valid format."""
        import re
        
        # Assembly accessions
        if re.match(r'^GC[FA]_\d{9}\.\d+$', accession):
            return True
        
        # Nucleotide accessions  
        if re.match(r'^(NC|NZ|CP|AP|AE|AL|AM|BA|BX|CM|FO|FP|FQ|FR)_\d+\.\d+$', accession):
            return True
        
        # Protein accessions
        if re.match(r'^(WP|YP|NP|XP|AP)_\d+\.\d+$', accession):
            return True
        
        return False
    
    def _simulate_accession_download(
        self,
        accessions: List[str],
        args: argparse.Namespace
    ) -> Dict[str, Any]:
        """Simulate download to show what would be downloaded."""
        try:
            # Count accessions by type
            assembly_count = sum(1 for acc in accessions if acc.startswith(('GCF_', 'GCA_')))
            nucleotide_count = sum(1 for acc in accessions if acc.startswith(('NC_', 'NZ_', 'CP_')))
            protein_count = sum(1 for acc in accessions if acc.startswith(('WP_', 'YP_', 'NP_')))
            
            return {
                'count': len(accessions),
                'assembly_count': assembly_count,
                'nucleotide_count': nucleotide_count,
                'protein_count': protein_count
            }
            
        except Exception as e:
            self.logger.error(f"Error simulating download: {e}")
            return {'count': 0}
    
    def _download_accessions(
        self,
        accessions: List[str],
        datasets_manager: NCBIDatasetsManager,
        repository: SQLiteTaxonomyRepository,
        args: argparse.Namespace
    ) -> Dict[str, int]:
        """Download genomes for specific accessions."""
        downloaded = 0
        failed = 0
        
        try:
            self.logger.info(f"Starting download for {len(accessions)} accessions")
            
            # Group accessions by type
            assembly_accessions = [acc for acc in accessions if acc.startswith(('GCF_', 'GCA_'))]
            nucleotide_accessions = [acc for acc in accessions if acc.startswith(('NC_', 'NZ_', 'CP_'))]
            protein_accessions = [acc for acc in accessions if acc.startswith(('WP_', 'YP_', 'NP_'))]
            
            self.logger.info(f"Accession breakdown: assembly={len(assembly_accessions)}, nucleotide={len(nucleotide_accessions)}, protein={len(protein_accessions)}")
            if assembly_accessions:
                self.logger.info(f"First few assembly accessions: {assembly_accessions[:3]}")
            
            # Download assemblies (priority for genomes)
            if assembly_accessions:
                result = self._download_assemblies(assembly_accessions, datasets_manager, args)
                downloaded += result['downloaded']
                failed += result['failed']
                
                # Update database if requested
                self.logger.info(f"Checking database update: update_database={args.update_database}, genomes_count={len(result.get('genomes', []))}")
                if args.update_database and result.get('genomes'):
                    self.logger.info("Starting database update...")
                    self._update_database_with_downloads(result['genomes'], repository, args)
            
            # Download nucleotide sequences
            if nucleotide_accessions:
                result = self._download_nucleotides(nucleotide_accessions, datasets_manager, args)
                downloaded += result['downloaded']
                failed += result['failed']
            
            # Download proteins if requested
            if protein_accessions and args.include_proteins:
                result = self._download_proteins(protein_accessions, datasets_manager, args)
                # Note: proteins don't count toward genome download total
                
        except Exception as e:
            self.logger.error(f"Error downloading accessions: {e}")
            failed += len(accessions)
        
        return {'downloaded': downloaded, 'failed': failed}
    
    def _download_assemblies(
        self,
        assembly_accessions: List[str],
        datasets_manager: NCBIDatasetsManager,
        args: argparse.Namespace
    ) -> Dict[str, Any]:
        """Download genome assemblies by accession."""
        try:
            self.logger.info(f"Downloading {len(assembly_accessions)} genome assemblies")
            
            # Use datasets manager to download by accession
            result = datasets_manager.download_genomes_by_accession(
                accessions=assembly_accessions,
                output_dir=args.output_dir,
                include_proteins=args.include_proteins,
                flatten_files=not args.keep_structure,  # Flatten by default, unless keep_structure is True
                remove_ncbi_dirs=args.remove_ncbi_dirs,
                keep_metadata=args.keep_metadata
            )
            
            # Convert genome files to GenomeInfo objects for database storage
            genomes = []
            checksums = result.get('checksums', {})
            
            for accession, file_path in result.get('genome_files', {}).items():
                # Get MD5 checksum for this file
                file_checksum = checksums.get(str(file_path))
                
                # We need to get tax_id for this accession from database or NCBI
                genome_info = {
                    'genome_id': accession,
                    'assembly_accession': accession,
                    'file_path': str(file_path),
                    'source': 'NCBI',
                    'sequence_type': 'genome',
                    'file_checksum': file_checksum
                }
                genomes.append(genome_info)
            
            return {
                'downloaded': len(result.get('downloaded', [])),
                'failed': len(result.get('failed', [])),
                'genomes': genomes
            }
            
        except Exception as e:
            self.logger.error(f"Assembly download failed: {e}")
            return {'downloaded': 0, 'failed': len(assembly_accessions), 'genomes': []}
    
    def _download_nucleotides(
        self,
        nucleotide_accessions: List[str],
        datasets_manager: NCBIDatasetsManager,
        args: argparse.Namespace
    ) -> Dict[str, Any]:
        """Download nucleotide sequences by accession."""
        try:
            self.logger.info(f"Downloading {len(nucleotide_accessions)} nucleotide sequences")
            
            # Note: NCBI datasets CLI primarily supports genome/assembly downloads
            # Nucleotide sequences would need Entrez/EFetch integration
            # For now, skip nucleotide-only downloads
            self.logger.warning("Nucleotide-only downloads not yet supported. Use assembly accessions (GCF_/GCA_) instead.")
            
            return {
                'downloaded': 0,
                'failed': len(nucleotide_accessions)
            }
            
        except Exception as e:
            self.logger.error(f"Nucleotide download failed: {e}")
            return {'downloaded': 0, 'failed': len(nucleotide_accessions)}
    
    def _download_proteins(
        self,
        protein_accessions: List[str],
        datasets_manager: NCBIDatasetsManager,
        args: argparse.Namespace
    ) -> Dict[str, Any]:
        """Download protein sequences by accession."""
        try:
            self.logger.info(f"Downloading {len(protein_accessions)} protein sequences")
            
            # Note: NCBI datasets CLI supports protein downloads with --include-protein
            # But individual protein accession downloads would need Entrez integration
            # For now, skip protein-only downloads
            self.logger.warning("Protein-only downloads not yet supported. Use --include-proteins with genome downloads instead.")
            
            return {
                'downloaded': 0,
                'failed': len(protein_accessions)
            }
            
        except Exception as e:
            self.logger.error(f"Protein download failed: {e}")
            return {'downloaded': 0, 'failed': len(protein_accessions)}
    
    def _update_database_with_downloads(
        self,
        genomes: List[Dict[str, Any]],
        repository: SQLiteTaxonomyRepository,
        args: argparse.Namespace
    ) -> None:
        """Update database with information about downloaded genomes."""
        try:
            self.logger.info(f"Updating database with {len(genomes)} genomes")
            
            for genome_info in genomes:
                self.logger.info(f"Processing genome: {genome_info.get('assembly_accession', 'unknown')}")
                try:
                    # Get taxonomy ID for this accession
                    accession = genome_info['assembly_accession']
                    tax_id = self._get_tax_id_for_accession(repository, accession)
                    
                    self.logger.info(f"Found tax_id {tax_id} for accession {accession}")
                    if tax_id:
                        # Update or create genome entry
                        genome_info['tax_id'] = tax_id
                        
                        # Use repository to add/update genome
                        from ...core.models import GenomeInfo
                        
                        genome_obj = GenomeInfo(
                            genome_id=genome_info['genome_id'],
                            tax_id=tax_id,
                            file_path=genome_info['file_path'],
                            sequence_type=genome_info.get('sequence_type', 'genome'),
                            assembly_accession=genome_info['assembly_accession'],
                            source=genome_info.get('source', 'NCBI'),
                            file_checksum=genome_info.get('file_checksum')
                        )
                        
                        # Add to database (this will update the genomes table)
                        try:
                            repository.add_genome(genome_obj)
                            self.logger.info(f"Added genome {accession} to database for tax_id {tax_id}")
                        except Exception as db_error:
                            if "already exists" in str(db_error):
                                self.logger.info(f"Genome {accession} already exists in database, updating file path")
                                # Could add update logic here if needed
                            else:
                                raise db_error
                    else:
                        self.logger.warning(f"Could not find taxonomy ID for accession {accession}")
                        
                except Exception as e:
                    self.logger.error(f"Error processing genome {genome_info.get('genome_id', 'unknown')}: {e}")
                    continue
                
        except Exception as e:
            self.logger.error(f"Error updating database: {e}")
    
    def _get_tax_id_for_accession(self, repository: SQLiteTaxonomyRepository, accession: str) -> Optional[int]:
        """Get taxonomy ID for an accession from the database."""
        try:
            conn = repository._get_connection()
            cursor = conn.execute(
                "SELECT tax_id FROM accession_mappings WHERE accession = ? OR accession_version = ?",
                (accession, accession)
            )
            result = cursor.fetchone()
            return result[0] if result else None
        except Exception as e:
            self.logger.debug(f"Could not find tax_id for {accession}: {e}")
            return None
    
    def _extract_proteins(
        self,
        genomes: List[Dict[str, Any]],
        args: argparse.Namespace
    ) -> None:
        """Extract proteins from downloaded genomes."""
        try:
            self.logger.info(f"Extracting proteins from {len(genomes)} genomes")
            
            # This would implement protein extraction functionality
            # Could use external tools like Prodigal or parse existing annotations
            
        except Exception as e:
            self.logger.error(f"Error extracting proteins: {e}")
    
    def _print_genome_status_report(self, status: Dict[str, Any]) -> None:
        """Print comprehensive genome status report."""
        summary = status.get('summary', {})
        missing_with_paths = status.get('missing_with_paths', [])
        truly_missing = status.get('truly_missing', [])
        
        print(f"\n📊 Genome File Status Report")
        print(f"=============================")
        print(f"Total genomes in database: {summary.get('total_genomes', 0)}")
        print(f"├── With file paths: {summary.get('with_file_paths', 0)}")
        print(f"├── Without file paths: {summary.get('without_file_paths', 0)}")
        print(f"└── Valid files present: {summary.get('valid_files_total', 0)}")
        
        if missing_with_paths:
            print(f"\n⚠️  Genomes with missing files: {len(missing_with_paths)}")
            print(f"   (Have file paths but files don't exist)")
            # Show a few examples
            for i, item in enumerate(missing_with_paths[:3]):
                exists_status = "✓" if item.get('file_actually_exists') else "✗"
                print(f"   {exists_status} {item['assembly_accession']} -> {item['file_path']}")
            if len(missing_with_paths) > 3:
                print(f"   ... and {len(missing_with_paths) - 3} more")
        
        if truly_missing:
            print(f"\n📥 Downloadable genomes: {len(truly_missing)}")
            print(f"   (Have accession mappings but no genome files)")
            # Show a few examples
            for i, item in enumerate(truly_missing[:5]):
                print(f"   • {item['accession']} ({item['tax_name'] or 'Unknown'})") 
            if len(truly_missing) > 5:
                print(f"   ... and {len(truly_missing) - 5} more")
        
        print()  # Empty line for spacing
    
    def _handle_clean_missing_paths(self, args: argparse.Namespace, repository: SQLiteTaxonomyRepository) -> int:
        """Handle the --clean-missing-paths option."""
        try:
            print(f"\n🧹 Cleaning file paths for missing genome files...")
            
            # Get status before cleaning
            status_before = repository.get_comprehensive_genome_status()
            missing_with_paths_before = status_before.get('missing_with_paths', [])
            
            if not missing_with_paths_before:
                print(f"✅ No genome file paths need cleaning")
                return 0
            
            print(f"Found {len(missing_with_paths_before)} genomes with paths to missing files")
            
            # Show what will be cleaned
            print(f"\nGenomes to be cleaned:")
            for i, item in enumerate(missing_with_paths_before[:10]):
                exists_status = "✓" if item.get('file_actually_exists') else "✗"
                print(f"  {exists_status} {item['assembly_accession']} -> {item['file_path']}")
            
            if len(missing_with_paths_before) > 10:
                print(f"  ... and {len(missing_with_paths_before) - 10} more")
            
            # Confirm with user (unless in automated context)
            import sys
            if sys.stdin.isatty():  # Interactive session
                response = input(f"\nContinue cleaning {len(missing_with_paths_before)} file paths? [y/N]: ")
                if response.lower() not in ['y', 'yes']:
                    print("Operation cancelled")
                    return 0
            
            # Perform cleaning
            result = repository.clean_missing_file_paths(verify_files=True)
            
            print(f"\n✅ Cleaning completed:")
            print(f"   - Genomes checked: {result['genomes_checked']}")
            print(f"   - Paths cleaned: {result['paths_cleaned']}")
            
            if result['paths_cleaned'] > 0:
                print(f"\n💡 These genomes are now available for download using:")
                print(f"   flextaxd download --missing --type genome --database {args.database} --output-dir <dir>")
            
            return 0
            
        except Exception as e:
            self.logger.error(f"Error cleaning missing paths: {e}")
            return 1