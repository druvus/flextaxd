"""NCBI Datasets integration for automated taxonomy and genome data download."""

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Union, Tuple
import logging

from .subprocess_utils import run_command_safely, validate_command_exists, SubprocessError
from ..core.exceptions import ValidationError, FlexTaxDError


logger = logging.getLogger(__name__)


class NCBIDatasetsError(FlexTaxDError):
    """Exception raised when NCBI Datasets operations fail."""
    pass


@dataclass
class NCBIDatasetInfo:
    """Information about an NCBI dataset download."""
    taxon: str
    assembly_level: str
    genome_count: int
    download_path: Path
    metadata_file: Path
    taxonomy_file: Optional[Path] = None
    genomes_directory: Optional[Path] = None


@dataclass
class AssemblyInfo:
    """Information about a genome assembly from NCBI."""
    accession: str
    organism_name: str
    tax_id: int
    assembly_level: str
    genome_size: Optional[int] = None
    ftp_path: Optional[str] = None
    local_path: Optional[Path] = None


class NCBIDatasetsManager:
    """Manager for NCBI Datasets API integration."""
    
    def __init__(self, cache_dir: Optional[Path] = None):
        """
        Initialize NCBI Datasets manager.
        
        Args:
            cache_dir: Directory to cache downloaded datasets
        """
        self.cache_dir = cache_dir or Path.home() / ".flextaxd" / "ncbi_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(__name__)
        
        # Verify datasets command is available
        if not validate_command_exists("datasets"):
            raise NCBIDatasetsError(
                "NCBI Datasets command not found. Please install NCBI Datasets CLI:\n"
                "  curl -o datasets 'https://ftp.ncbi.nlm.nih.gov/pub/datasets/command-line/v2/linux-amd64/datasets'\n"
                "  chmod +x datasets\n"
                "  # Add to PATH or use full path"
            )
    
    def download_taxonomy(self, taxon: str, output_dir: Path, **kwargs) -> NCBIDatasetInfo:
        """
        Download taxonomy data for a specific taxon using NCBI Datasets.
        
        Args:
            taxon: Taxonomic name or taxid (e.g., "Bacteria", "562", "Escherichia coli")
            output_dir: Directory to store downloaded data
            **kwargs: Additional options for datasets command
        
        Returns:
            NCBIDatasetInfo with download details
        """
        self.logger.info(f"Downloading NCBI taxonomy data for: {taxon}")
        
        # Prepare output directory
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Build datasets taxonomy command
        cmd_parts = [
            "datasets", "download", "taxonomy",
            "taxon", taxon,
            "--filename", str(output_dir / "ncbi_dataset.zip")
        ]
        
        # Add optional parameters
        if kwargs.get("include_children", True):
            cmd_parts.append("--children")
        
        try:
            # Execute download command
            result = run_command_safely(" ".join(cmd_parts), cwd=output_dir)
            
            if result.returncode != 0:
                raise NCBIDatasetsError(f"Taxonomy download failed: {result.stderr}")
            
            # Extract the dataset
            self._extract_dataset(output_dir / "ncbi_dataset.zip", output_dir)
            
            # Parse metadata
            metadata_file = output_dir / "ncbi_dataset" / "data" / "taxonomy.jsonl"
            if not metadata_file.exists():
                # Try alternative locations
                for alt_path in [
                    output_dir / "data" / "taxonomy.jsonl",
                    output_dir / "taxonomy.jsonl"
                ]:
                    if alt_path.exists():
                        metadata_file = alt_path
                        break
            
            if not metadata_file.exists():
                raise NCBIDatasetsError(f"Taxonomy metadata file not found in {output_dir}")
            
            # Create taxonomy dump files compatible with existing NCBI parser
            taxonomy_dir = self._convert_jsonl_to_dumps(metadata_file, output_dir)
            
            return NCBIDatasetInfo(
                taxon=taxon,
                assembly_level="taxonomy_only",
                genome_count=0,
                download_path=output_dir,
                metadata_file=metadata_file,
                taxonomy_file=taxonomy_dir / "names.dmp"
            )
            
        except SubprocessError as e:
            raise NCBIDatasetsError(f"Failed to download taxonomy for {taxon}: {e}")
    
    def download_genomes(self, 
                        taxon: str, 
                        output_dir: Path,
                        assembly_level: str = "complete",
                        max_genomes: Optional[int] = None,
                        **kwargs) -> NCBIDatasetInfo:
        """
        Download genome assemblies for a specific taxon.
        
        Args:
            taxon: Taxonomic name or taxid
            output_dir: Directory to store downloaded data  
            assembly_level: Assembly level filter ("complete", "chromosome", "scaffold", "contig", "all")
            max_genomes: Maximum number of genomes to download
            **kwargs: Additional options
        
        Returns:
            NCBIDatasetInfo with download details
        """
        self.logger.info(f"Downloading NCBI genome data for: {taxon} (level: {assembly_level})")
        
        # Prepare output directory
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Build datasets genome command
        cmd_parts = [
            "datasets", "download", "genome",
            "taxon", taxon
        ]
        
        # Add assembly level filter
        if assembly_level != "all":
            cmd_parts.extend(["--assembly-level", assembly_level])
        
        # Add limit if specified
        if max_genomes:
            cmd_parts.extend(["--limit", str(max_genomes)])
        
        # Add output filename
        cmd_parts.extend(["--filename", str(output_dir / "genomes_dataset.zip")])
        
        # Add optional parameters
        if kwargs.get("include_gbff", False):
            cmd_parts.append("--include-gbff")
        if kwargs.get("include_protein", False):
            cmd_parts.append("--include-protein")
        
        try:
            # Execute download command
            result = run_command_safely(" ".join(cmd_parts), cwd=output_dir)
            
            if result.returncode != 0:
                raise NCBIDatasetsError(f"Genome download failed: {result.stderr}")
            
            # Extract the dataset
            self._extract_dataset(output_dir / "genomes_dataset.zip", output_dir)
            
            # Parse metadata
            metadata_file = output_dir / "ncbi_dataset" / "data" / "assembly_data_report.jsonl"
            if not metadata_file.exists():
                # Try alternative locations
                for alt_path in [
                    output_dir / "data" / "assembly_data_report.jsonl",
                    output_dir / "assembly_data_report.jsonl"
                ]:
                    if alt_path.exists():
                        metadata_file = alt_path
                        break
            
            if not metadata_file.exists():
                raise NCBIDatasetsError(f"Assembly metadata file not found in {output_dir}")
            
            # Count genomes and find genome directory
            genome_count = self._count_assemblies(metadata_file)
            genomes_dir = output_dir / "ncbi_dataset" / "data"
            if not genomes_dir.exists():
                genomes_dir = output_dir / "data"
            
            # Create taxonomy dump files from assembly metadata
            taxonomy_dir = self._extract_taxonomy_from_assemblies(metadata_file, output_dir)
            
            return NCBIDatasetInfo(
                taxon=taxon,
                assembly_level=assembly_level,
                genome_count=genome_count,
                download_path=output_dir,
                metadata_file=metadata_file,
                taxonomy_file=taxonomy_dir / "names.dmp" if taxonomy_dir else None,
                genomes_directory=genomes_dir
            )
            
        except SubprocessError as e:
            raise NCBIDatasetsError(f"Failed to download genomes for {taxon}: {e}")
    
    def create_flextaxd_database(self, 
                               dataset_info: NCBIDatasetInfo,
                               database_path: Path,
                               include_genomes: bool = True) -> Dict[str, Any]:
        """
        Create a FlexTaxD database from downloaded NCBI dataset.
        
        Args:
            dataset_info: Information about downloaded dataset
            database_path: Path for output FlexTaxD database
            include_genomes: Whether to include genome information
        
        Returns:
            Statistics about created database
        """
        from ..database.sqlite import SQLiteTaxonomyRepository
        from ..parsers.ncbi import NCBITaxonomyParser
        from ..core.models import GenomeInfo, TaxonomyTree
        
        self.logger.info(f"Creating FlexTaxD database: {database_path}")
        
        # Parse taxonomy using existing NCBI parser
        if not dataset_info.taxonomy_file:
            raise NCBIDatasetsError("No taxonomy file available in dataset")
        
        parser = NCBITaxonomyParser()
        taxonomy_dir = dataset_info.taxonomy_file.parent
        tree = parser.parse(taxonomy_dir)
        
        self.logger.info(f"Parsed taxonomy tree with {tree.node_count} nodes")
        
        # Add genome information if requested and available
        if include_genomes and dataset_info.genomes_directory:
            genomes_added = self._add_genome_info_to_tree(
                tree, dataset_info.metadata_file, dataset_info.genomes_directory
            )
            self.logger.info(f"Added {genomes_added} genome associations")
        
        # Create database
        database_path.parent.mkdir(parents=True, exist_ok=True)
        if database_path.exists():
            database_path.unlink()
        
        with SQLiteTaxonomyRepository(database_path) as repository:
            repository.save_tree(tree)
            stats = repository.get_statistics()
        
        self.logger.info("Database created successfully")
        return stats
    
    def _extract_dataset(self, zip_path: Path, output_dir: Path) -> None:
        """Extract NCBI dataset zip file."""
        import zipfile
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(output_dir)
            
            # Remove zip file after extraction
            zip_path.unlink()
            
        except zipfile.BadZipFile as e:
            raise NCBIDatasetsError(f"Invalid zip file: {e}")
    
    def _convert_jsonl_to_dumps(self, jsonl_file: Path, output_dir: Path) -> Path:
        """Convert NCBI taxonomy JSONL to names.dmp/nodes.dmp format."""
        taxonomy_dir = output_dir / "taxonomy_dumps"
        taxonomy_dir.mkdir(exist_ok=True)
        
        names_file = taxonomy_dir / "names.dmp"
        nodes_file = taxonomy_dir / "nodes.dmp"
        
        # Parse JSONL and create dump files
        taxonomy_data = {}
        
        try:
            with open(jsonl_file, 'r') as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        tax_id = data.get('tax_id')
                        if tax_id:
                            taxonomy_data[tax_id] = data
        except (json.JSONDecodeError, IOError) as e:
            raise NCBIDatasetsError(f"Failed to parse taxonomy JSONL: {e}")
        
        # Write names.dmp
        with open(names_file, 'w') as names_f:
            for tax_id, data in taxonomy_data.items():
                sci_name = data.get('sci_name', f'taxid_{tax_id}')
                names_f.write(f"{tax_id}\t|\t{sci_name}\t|\t\t|\tscientific name\t|\n")
        
        # Write nodes.dmp
        with open(nodes_file, 'w') as nodes_f:
            for tax_id, data in taxonomy_data.items():
                parent_tax_id = data.get('parent_tax_id', tax_id)
                rank = data.get('rank', 'no rank')
                nodes_f.write(f"{tax_id}\t|\t{parent_tax_id}\t|\t{rank}\t|\t\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|\n")
        
        return taxonomy_dir
    
    def _extract_taxonomy_from_assemblies(self, metadata_file: Path, output_dir: Path) -> Optional[Path]:
        """Extract taxonomy information from assembly metadata."""
        taxonomy_dir = output_dir / "taxonomy_from_assemblies"
        taxonomy_dir.mkdir(exist_ok=True)
        
        names_file = taxonomy_dir / "names.dmp"
        nodes_file = taxonomy_dir / "nodes.dmp"
        
        taxonomy_data = {}
        
        try:
            with open(metadata_file, 'r') as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        
                        # Extract taxonomy info from assembly
                        organism = data.get('organism', {})
                        tax_id = organism.get('tax_id')
                        sci_name = organism.get('organism_name')
                        
                        if tax_id and sci_name:
                            taxonomy_data[tax_id] = {
                                'tax_id': tax_id,
                                'sci_name': sci_name,
                                'parent_tax_id': tax_id,  # Simplified - would need full lineage
                                'rank': 'species'  # Simplified assumption
                            }
        
        except (json.JSONDecodeError, IOError) as e:
            self.logger.warning(f"Could not extract taxonomy from assemblies: {e}")
            return None
        
        if not taxonomy_data:
            return None
        
        # Write simplified taxonomy files
        with open(names_file, 'w') as names_f:
            for tax_id, data in taxonomy_data.items():
                names_f.write(f"{tax_id}\t|\t{data['sci_name']}\t|\t\t|\tscientific name\t|\n")
        
        with open(nodes_file, 'w') as nodes_f:
            for tax_id, data in taxonomy_data.items():
                parent_id = data['parent_tax_id']
                rank = data['rank']
                nodes_f.write(f"{tax_id}\t|\t{parent_id}\t|\t{rank}\t|\t\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|\n")
        
        return taxonomy_dir
    
    def _count_assemblies(self, metadata_file: Path) -> int:
        """Count the number of assemblies in metadata file."""
        count = 0
        try:
            with open(metadata_file, 'r') as f:
                for line in f:
                    if line.strip():
                        count += 1
        except IOError:
            self.logger.warning(f"Could not read metadata file: {metadata_file}")
        
        return count
    
    def _add_genome_info_to_tree(self, 
                                tree, 
                                metadata_file: Path, 
                                genomes_dir: Path) -> int:
        """Add genome information to taxonomy tree from assembly metadata."""
        from ..core.models import GenomeInfo
        
        genomes_added = 0
        
        try:
            with open(metadata_file, 'r') as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        
                        # Extract assembly information
                        accession = data.get('accession')
                        organism = data.get('organism', {})
                        tax_id = organism.get('tax_id')
                        organism_name = organism.get('organism_name')
                        assembly_info = data.get('assembly_info', {})
                        assembly_level = assembly_info.get('assembly_level')
                        
                        if not (accession and tax_id):
                            continue
                        
                        # Look for genome files
                        assembly_dir = genomes_dir / accession
                        genome_file = None
                        
                        # Look for FASTA files in assembly directory
                        if assembly_dir.exists():
                            for fasta_file in assembly_dir.glob("*.fna"):
                                genome_file = str(fasta_file)
                                break
                        
                        # Create genome info
                        genome_info = GenomeInfo(
                            genome_id=accession,
                            tax_id=tax_id,
                            file_path=genome_file,
                            sequence_type="genome",
                            assembly_accession=accession,
                            description=organism_name,
                            source="NCBI"
                        )
                        
                        # Add to tree
                        tree.add_genome(genome_info)
                        genomes_added += 1
        
        except (json.JSONDecodeError, IOError) as e:
            self.logger.warning(f"Could not process assembly metadata: {e}")
        
        return genomes_added
    
    def download_genomes_by_accession(self, 
                                     accessions: List[str], 
                                     output_dir: Path,
                                     include_proteins: bool = False,
                                     flatten_files: bool = True,
                                     remove_ncbi_dirs: bool = True,
                                     keep_metadata: bool = False) -> Dict[str, Any]:
        """
        Download genome assemblies by specific accession numbers.
        
        Args:
            accessions: List of assembly accessions (GCF_/GCA_)
            output_dir: Directory to store downloaded genomes
            include_proteins: Whether to include protein sequences
            flatten_files: If True, move files to output_dir root (default: True)
            remove_ncbi_dirs: If True, remove empty NCBI directories after flattening (default: True)
            keep_metadata: If True, keep md5sum.txt, README.md, and ncbi_dataset/ (default: False)
        
        Returns:
            Dictionary with download results and file paths
        """
        self.logger.info(f"Downloading {len(accessions)} genomes by accession")
        
        # Prepare output directory
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Filter assembly accessions
        assembly_accessions = [acc for acc in accessions if acc.startswith(('GCF_', 'GCA_'))]
        
        if not assembly_accessions:
            self.logger.warning("No valid assembly accessions found")
            return {'downloaded': [], 'failed': accessions, 'genome_files': {}}
        
        # Write accessions to temporary file for batch download
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as tmp_file:
            for acc in assembly_accessions:
                tmp_file.write(f"{acc}\n")
            accession_file = tmp_file.name
        
        try:
            # Use absolute paths to avoid relative path issues
            output_dir = output_dir.resolve()
            zip_file = output_dir / "dataset.zip"  # Use simple filename
            
            # Build datasets command with absolute paths
            cmd_parts = [
                "datasets", "download", "genome", "accession",
                "--inputfile", accession_file,
                "--filename", str(zip_file)
            ]
            
            if include_proteins:
                cmd_parts.append("--include-protein")
            
            # Execute download in the output directory
            self.logger.debug(f"Running command: {' '.join(cmd_parts)}")
            result = run_command_safely(" ".join(cmd_parts), cwd=output_dir)
            
            if result.returncode != 0:
                raise NCBIDatasetsError(f"Genome download by accession failed: {result.stderr}")
            
            # Extract dataset
            if zip_file.exists():
                self._extract_dataset(zip_file, output_dir)
            else:
                raise NCBIDatasetsError(f"Download zip file not created: {zip_file}")
            
            # Find and optionally flatten downloaded genome files
            genome_files = self._catalog_downloaded_genomes(
                output_dir, 
                assembly_accessions,
                flatten_files=flatten_files,
                remove_ncbi_dirs=remove_ncbi_dirs
            )
            
            # Process MD5 checksums and cleanup metadata files
            checksums = self._process_metadata_and_cleanup(
                output_dir,
                genome_files,
                keep_metadata=keep_metadata
            )
            
            return {
                'downloaded': list(genome_files.keys()),
                'failed': [acc for acc in assembly_accessions if acc not in genome_files],
                'genome_files': genome_files,
                'checksums': checksums,
                'output_dir': output_dir
            }
            
        except SubprocessError as e:
            raise NCBIDatasetsError(f"Failed to download genomes by accession: {e}")
        finally:
            # Clean up temporary file
            Path(accession_file).unlink(missing_ok=True)
    
    def _catalog_downloaded_genomes(self, 
                                   output_dir: Path, 
                                   expected_accessions: List[str],
                                   flatten_files: bool = True,
                                   remove_ncbi_dirs: bool = True) -> Dict[str, Path]:
        """
        Catalog downloaded genome files and optionally flatten directory structure.
        
        Args:
            output_dir: Directory containing downloaded data
            expected_accessions: List of accessions that were requested
            flatten_files: If True, move files to output_dir root
            remove_ncbi_dirs: If True, remove empty NCBI directories after flattening
        
        Returns:
            Dict mapping accession to final genome file path
        """
        genome_files = {}
        
        # Look for data directory
        data_dir = output_dir / "ncbi_dataset" / "data"
        if not data_dir.exists():
            data_dir = output_dir / "data"
        
        if not data_dir.exists():
            self.logger.warning(f"No data directory found in {output_dir}")
            return genome_files
        
        # Find genome files for each accession
        files_to_flatten = []  # Track files for flattening
        
        for accession in expected_accessions:
            # Look for accession directory
            accession_dir = data_dir / accession
            if accession_dir.exists():
                # Find FASTA file
                for fasta_file in accession_dir.glob("*.fna"):
                    if flatten_files:
                        # Plan to flatten: move to output directory root
                        flat_filename = fasta_file.name
                        flat_path = output_dir / flat_filename
                        
                        # Handle filename conflicts
                        counter = 1
                        while flat_path.exists():
                            name_parts = flat_filename.rsplit('.', 1)
                            if len(name_parts) == 2:
                                flat_filename = f"{name_parts[0]}_{counter}.{name_parts[1]}"
                            else:
                                flat_filename = f"{flat_filename}_{counter}"
                            flat_path = output_dir / flat_filename
                            counter += 1
                        
                        files_to_flatten.append((fasta_file, flat_path))
                        genome_files[accession] = flat_path
                        self.logger.debug(f"Will flatten {fasta_file} -> {flat_path}")
                    else:
                        # Keep original nested structure
                        genome_files[accession] = fasta_file
                        self.logger.debug(f"Keeping nested structure for {accession}: {fasta_file}")
                    break
                else:
                    self.logger.warning(f"No FASTA file found for {accession} in {accession_dir}")
            else:
                self.logger.warning(f"No directory found for {accession}")
        
        # Execute file flattening if requested
        if flatten_files and files_to_flatten:
            self.logger.info(f"Flattening {len(files_to_flatten)} genome files to output directory root")
            
            for source_file, target_file in files_to_flatten:
                try:
                    import shutil
                    shutil.move(str(source_file), str(target_file))
                    self.logger.debug(f"Moved {source_file.name} to {target_file}")
                except Exception as e:
                    self.logger.error(f"Failed to move {source_file} to {target_file}: {e}")
                    # Keep original path in case of failure
                    for acc, path in genome_files.items():
                        if path == target_file:
                            genome_files[acc] = source_file
                            break
            
            # Clean up empty NCBI directory structure if requested
            if remove_ncbi_dirs:
                self._cleanup_empty_directories(output_dir / "ncbi_dataset")
        
        return genome_files
    
    def _process_metadata_and_cleanup(self, 
                                     output_dir: Path,
                                     genome_files: Dict[str, Path],
                                     keep_metadata: bool = False) -> Dict[str, str]:
        """
        Process MD5 checksums and cleanup metadata files.
        
        Args:
            output_dir: Directory containing downloaded data
            genome_files: Dictionary mapping accessions to genome file paths
            keep_metadata: If True, keep metadata files
        
        Returns:
            Dictionary mapping file paths to MD5 checksums
        """
        checksums = {}
        
        try:
            # Parse MD5 checksums from md5sum.txt
            md5_file = output_dir / "md5sum.txt"
            if md5_file.exists():
                checksums = self._parse_md5sum_file(md5_file, genome_files)
                self.logger.info(f"Parsed MD5 checksums for {len(checksums)} files")
            
            # Cleanup metadata files unless user wants to keep them
            if not keep_metadata:
                files_to_remove = []
                dirs_to_remove = []
                
                # Files to remove
                for filename in ["md5sum.txt", "README.md"]:
                    file_path = output_dir / filename
                    if file_path.exists():
                        files_to_remove.append(file_path)
                
                # Directory to remove
                ncbi_dir = output_dir / "ncbi_dataset"
                if ncbi_dir.exists():
                    dirs_to_remove.append(ncbi_dir)
                
                # Remove files
                for file_path in files_to_remove:
                    try:
                        file_path.unlink()
                        self.logger.debug(f"Removed metadata file: {file_path.name}")
                    except Exception as e:
                        self.logger.warning(f"Could not remove {file_path}: {e}")
                
                # Remove directories
                for dir_path in dirs_to_remove:
                    try:
                        import shutil
                        shutil.rmtree(dir_path)
                        self.logger.debug(f"Removed metadata directory: {dir_path.name}")
                    except Exception as e:
                        self.logger.warning(f"Could not remove {dir_path}: {e}")
                
                if files_to_remove or dirs_to_remove:
                    self.logger.info(f"Cleaned up {len(files_to_remove)} files and {len(dirs_to_remove)} directories")
            else:
                self.logger.info("Keeping metadata files as requested")
        
        except Exception as e:
            self.logger.error(f"Error processing metadata: {e}")
        
        return checksums
    
    def _parse_md5sum_file(self, md5_file: Path, genome_files: Dict[str, Path]) -> Dict[str, str]:
        """
        Parse MD5 checksums from NCBI md5sum.txt file.
        
        Args:
            md5_file: Path to md5sum.txt file
            genome_files: Dictionary mapping accessions to genome file paths
        
        Returns:
            Dictionary mapping file paths to MD5 checksums
        """
        checksums = {}
        
        try:
            with open(md5_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    
                    # MD5 format: "checksum  filename"
                    parts = line.split('  ', 1)
                    if len(parts) == 2:
                        checksum, filename = parts
                        
                        # Match against our genome files
                        filename_only = Path(filename).name
                        for accession, genome_path in genome_files.items():
                            if genome_path.name == filename_only:
                                checksums[str(genome_path)] = checksum
                                self.logger.debug(f"MD5 for {genome_path.name}: {checksum[:8]}...")
                                break
        
        except Exception as e:
            self.logger.error(f"Error parsing MD5 file {md5_file}: {e}")
        
        return checksums
    
    def _cleanup_empty_directories(self, root_dir: Path) -> None:
        """
        Recursively remove empty directories starting from root_dir.
        
        Args:
            root_dir: Root directory to start cleanup from
        """
        if not root_dir.exists():
            return
        
        try:
            # Remove empty subdirectories first (bottom-up)
            for item in root_dir.iterdir():
                if item.is_dir():
                    self._cleanup_empty_directories(item)
            
            # Try to remove this directory if it's empty
            try:
                root_dir.rmdir()  # Only removes if empty
                self.logger.debug(f"Removed empty directory: {root_dir}")
            except OSError:
                # Directory not empty, that's fine
                self.logger.debug(f"Directory not empty (keeping): {root_dir}")
                
        except Exception as e:
            self.logger.warning(f"Error during directory cleanup {root_dir}: {e}")
    
    def get_available_assembly_levels(self) -> List[str]:
        """Get list of available assembly levels for filtering."""
        return ["complete", "chromosome", "scaffold", "contig", "all"]
    
    def validate_taxon(self, taxon: str) -> Dict[str, Any]:
        """
        Validate a taxon name or ID using NCBI Datasets API.
        
        Args:
            taxon: Taxonomic name or taxid to validate
        
        Returns:
            Dictionary with validation results and metadata
        """
        try:
            # Use datasets summary to validate taxon
            cmd = f"datasets summary taxonomy taxon '{taxon}'"
            result = run_command_safely(cmd)
            
            if result.returncode == 0:
                # Parse the JSON response
                try:
                    summary_data = json.loads(result.stdout)
                    return {
                        "valid": True,
                        "taxon": taxon,
                        "summary": summary_data
                    }
                except json.JSONDecodeError:
                    return {
                        "valid": True,  # Command succeeded but couldn't parse JSON
                        "taxon": taxon,
                        "summary": None
                    }
            else:
                return {
                    "valid": False,
                    "taxon": taxon,
                    "error": result.stderr
                }
        
        except SubprocessError as e:
            return {
                "valid": False,
                "taxon": taxon,
                "error": str(e)
            }


def check_ncbi_datasets_installation() -> Dict[str, Any]:
    """
    Check if NCBI Datasets is properly installed and accessible.
    
    Returns:
        Dictionary with installation status and version info
    """
    try:
        if not validate_command_exists("datasets"):
            return {
                "installed": False,
                "error": "datasets command not found in PATH",
                "install_instructions": [
                    "Download NCBI Datasets CLI:",
                    "curl -o datasets 'https://ftp.ncbi.nlm.nih.gov/pub/datasets/command-line/v2/linux-amd64/datasets'",
                    "chmod +x datasets",
                    "mv datasets /usr/local/bin/ (or add to PATH)"
                ]
            }
        
        # Try to get version
        result = run_command_safely("datasets version", timeout=10)
        
        if result.returncode == 0:
            return {
                "installed": True,
                "version": result.stdout.strip(),
                "command_path": result.stdout
            }
        else:
            return {
                "installed": True,
                "version": "unknown",
                "warning": "datasets command found but version check failed"
            }
    
    except Exception as e:
        return {
            "installed": False,
            "error": f"Error checking installation: {e}"
        }