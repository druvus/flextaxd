"""Unified sequence management for flexible file organization."""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import json

from ..database.sequence_tracking import UnifiedSequenceTracker, SequenceFileInfo
from ..database.sqlite import SQLiteTaxonomyRepository
from ..core.exceptions import DatabaseError, ValidationError

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    """Results from protein extraction operation."""
    files_created: List[Path]
    proteins_extracted: int
    taxa_processed: int
    strategy_used: str
    mapping_files: List[Path] = None


class UnifiedSequenceManager:
    """Manage sequences with unified tracking for easy export generation."""
    
    def __init__(self, repository: SQLiteTaxonomyRepository):
        """Initialize with repository."""
        self.repository = repository
        self.tracker = UnifiedSequenceTracker(repository)
    
    def register_sequence_file(self, file_path: Path, file_type: str, 
                              scope: str, taxa_list: List[int]) -> int:
        """Register any sequence file (genome, protein) with taxa mapping.
        
        Args:
            file_path: Path to sequence file
            file_type: 'genome', 'protein_taxa', 'protein_global'
            scope: 'single_taxa', 'multi_taxa', 'global'
            taxa_list: List of taxa IDs in this file
        
        Returns: file_id for tracking
        """
        if not file_path.exists():
            raise ValidationError(f"Sequence file does not exist: {file_path}")
        
        if file_type not in ['genome', 'protein_taxa', 'protein_global']:
            raise ValidationError(f"Invalid file_type: {file_type}")
            
        if scope not in ['single_taxa', 'multi_taxa', 'global']:
            raise ValidationError(f"Invalid scope: {scope}")
            
        if not taxa_list:
            raise ValidationError("Taxa list cannot be empty")
        
        return self.tracker.register_sequence_file(file_path, file_type, scope, taxa_list)
    
    def register_genome_files(self, genome_dir: Path, pattern: str = "*.fna") -> Dict[str, int]:
        """Register genome files from a directory.
        
        Args:
            genome_dir: Directory containing genome files
            pattern: Glob pattern for genome files
            
        Returns:
            Dictionary of {filename: file_id}
        """
        if not genome_dir.exists():
            raise ValidationError(f"Genome directory does not exist: {genome_dir}")
        
        genome_files = list(genome_dir.glob(pattern))
        if not genome_files:
            logger.warning(f"No genome files found in {genome_dir} with pattern {pattern}")
            return {}
        
        results = {}
        
        for genome_file in genome_files:
            # Try to extract tax_id from filename or lookup in database
            tax_id = self._extract_tax_id_from_genome_file(genome_file)
            if tax_id:
                try:
                    file_id = self.register_sequence_file(
                        genome_file, 'genome', 'single_taxa', [tax_id]
                    )
                    results[genome_file.name] = file_id
                except Exception as e:
                    logger.error(f"Failed to register genome file {genome_file}: {e}")
            else:
                logger.warning(f"Could not determine tax_id for genome file: {genome_file}")
        
        logger.info(f"Registered {len(results)} genome files")
        return results
    
    def register_protein_files(self, protein_dir: Path, pattern: str = "*.faa") -> Dict[str, int]:
        """Register protein files from a directory.
        
        Args:
            protein_dir: Directory containing protein files
            pattern: Glob pattern for protein files
            
        Returns:
            Dictionary of {filename: file_id}
        """
        if not protein_dir.exists():
            raise ValidationError(f"Protein directory does not exist: {protein_dir}")
        
        protein_files = list(protein_dir.glob(pattern))
        if not protein_files:
            logger.warning(f"No protein files found in {protein_dir} with pattern {pattern}")
            return {}
        
        results = {}
        
        for protein_file in protein_files:
            # Determine if this is taxa-specific or global
            tax_ids = self._extract_tax_ids_from_protein_file(protein_file)
            
            if len(tax_ids) == 1:
                file_type = 'protein_taxa'
                scope = 'single_taxa'
            elif len(tax_ids) > 1:
                file_type = 'protein_taxa'
                scope = 'multi_taxa'
            else:
                # Assume global if no tax_ids found in filename
                file_type = 'protein_global'
                scope = 'global'
                tax_ids = self._get_all_tax_ids()  # Get all taxa from database
            
            try:
                file_id = self.register_sequence_file(
                    protein_file, file_type, scope, tax_ids
                )
                results[protein_file.name] = file_id
            except Exception as e:
                logger.error(f"Failed to register protein file {protein_file}: {e}")
        
        logger.info(f"Registered {len(results)} protein files")
        return results
    
    def extract_proteins_flexible(self, output_strategy: str, 
                                  output_path: Path, 
                                  **kwargs) -> ExtractionResult:
        """Extract proteins with flexible output strategy.
        
        Args:
            output_strategy: 'one_per_taxa', 'global', 'by_genome', 'by_genus'
            output_path: Base path for output
            **kwargs: Strategy-specific parameters
            
        Returns:
            Information about created files and mappings
        """
        if output_strategy == 'one_per_taxa':
            return self._extract_one_per_taxa(output_path, **kwargs)
        elif output_strategy == 'global':
            return self._extract_global(output_path, **kwargs)
        elif output_strategy == 'by_genome':
            return self._extract_by_genome(output_path, **kwargs)
        elif output_strategy == 'by_genus':
            return self._extract_by_genus(output_path, **kwargs)
        else:
            raise ValidationError(f"Unknown extraction strategy: {output_strategy}")
    
    def _extract_one_per_taxa(self, output_dir: Path, **kwargs) -> ExtractionResult:
        """Extract proteins with one file per taxonomic node."""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Get all taxa with genomes
        taxa_with_genomes = self._get_taxa_with_genomes()
        
        # Apply taxa_limit if specified
        taxa_limit = kwargs.get('taxa_limit')
        if taxa_limit and isinstance(taxa_limit, int) and taxa_limit > 0:
            taxa_with_genomes = taxa_with_genomes[:taxa_limit]
        
        files_created = []
        proteins_extracted = 0
        taxa_processed = 0
        
        for tax_id in taxa_with_genomes:
            # Extract proteins for this taxonomic node
            proteins = self._extract_proteins_for_taxa(tax_id)
            
            if proteins:
                # Create output file
                output_file = output_dir / f"tax_{tax_id}.faa"
                self._write_proteins_to_fasta(proteins, output_file)
                
                # Register the file
                self.register_sequence_file(
                    output_file, 'protein_taxa', 'single_taxa', [tax_id]
                )
                
                # Track proteins in database
                self.tracker.track_protein_sequences(tax_id, proteins)
                
                files_created.append(output_file)
                proteins_extracted += len(proteins)
                taxa_processed += 1
        
        return ExtractionResult(
            files_created=files_created,
            proteins_extracted=proteins_extracted,
            taxa_processed=taxa_processed,
            strategy_used='one_per_taxa'
        )
    
    def _extract_global(self, output_path: Path, **kwargs) -> ExtractionResult:
        """Extract proteins to a single global file with mapping."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create mapping file path
        mapping_path = output_path.parent / f"{output_path.stem}_accession2taxid.txt"
        
        # Get all taxa with genomes
        taxa_with_genomes = self._get_taxa_with_genomes()
        
        proteins_extracted = 0
        taxa_processed = 0
        
        with open(output_path, 'w') as fasta_out, open(mapping_path, 'w') as map_out:
            # Write mapping header
            map_out.write("accession\taccession.version\ttaxid\tgi\n")
            
            for tax_id in taxa_with_genomes:
                proteins = self._extract_proteins_for_taxa(tax_id)
                
                for protein in proteins:
                    # Write protein to FASTA
                    fasta_out.write(f">{protein['protein_accession']} {protein.get('product', '')}\n")
                    fasta_out.write(f"{protein['sequence']}\n")
                    
                    # Write mapping entry
                    accession = protein['protein_accession']
                    map_out.write(f"{accession}\t{accession}\t{tax_id}\t0\n")
                    
                    proteins_extracted += 1
                
                # Track proteins in database
                if proteins:
                    self.tracker.track_protein_sequences(tax_id, proteins)
                    taxa_processed += 1
        
        # Register the global file
        all_taxa = list(taxa_with_genomes)
        self.register_sequence_file(
            output_path, 'protein_global', 'global', all_taxa
        )
        
        return ExtractionResult(
            files_created=[output_path],
            proteins_extracted=proteins_extracted,
            taxa_processed=taxa_processed,
            strategy_used='global',
            mapping_files=[mapping_path]
        )
    
    def _extract_proteins_for_taxa(self, tax_id: int) -> List[Dict[str, Any]]:
        """Extract proteins for a specific taxonomic node.
        
        This is a placeholder - in real implementation, this would:
        1. Find genome files for this taxa
        2. Parse GenBank/GFF files to extract protein sequences
        3. Return list of protein information
        """
        # For now, return mock data for testing
        return [
            {
                'protein_id': f'protein_{tax_id}_{i}',
                'protein_accession': f'WP_{tax_id:06d}{i:03d}.1',
                'gene_name': f'gene_{i}',
                'sequence': 'MKVLIVLLLAVSLWCSASG',  # Mock sequence
                'sequence_length': 19,
                'product': f'hypothetical protein {i}',
                'ec_number': None,
                'go_terms': None
            }
            for i in range(1, 6)  # Mock 5 proteins per genome
        ]
    
    def _extract_tax_id_from_genome_file(self, genome_file: Path) -> Optional[int]:
        """Extract tax_id from genome filename or database lookup."""
        filename = genome_file.stem
        
        # Try to extract GCF/GCA accession and lookup in database
        if filename.startswith('GCF_') or filename.startswith('GCA_'):
            # Try to find this assembly accession in genomes table
            conn = self.repository._get_connection()
            cursor = conn.execute(
                "SELECT tax_id FROM genomes WHERE assembly_accession = ? OR genome_id = ?", 
                (filename, filename)
            )
            row = cursor.fetchone()
            if row:
                return row['tax_id']
        
        # Try to extract tax_id from filename patterns like "tax_562.fna"
        if 'tax_' in filename:
            try:
                return int(filename.split('tax_')[1].split('_')[0].split('.')[0])
            except (ValueError, IndexError):
                pass
        
        return None
    
    def _extract_tax_ids_from_protein_file(self, protein_file: Path) -> List[int]:
        """Extract tax_ids from protein filename."""
        filename = protein_file.stem
        tax_ids = []
        
        # Pattern like "tax_562.faa"
        if 'tax_' in filename:
            try:
                tax_id = int(filename.split('tax_')[1].split('_')[0].split('.')[0])
                tax_ids.append(tax_id)
            except (ValueError, IndexError):
                pass
        
        return tax_ids
    
    def _get_taxa_with_genomes(self) -> List[int]:
        """Get all taxa that have genome files."""
        conn = self.repository._get_connection()
        cursor = conn.execute("SELECT DISTINCT tax_id FROM genomes")
        return [row['tax_id'] for row in cursor.fetchall()]
    
    def _get_all_tax_ids(self) -> List[int]:
        """Get all taxonomy IDs from the database."""
        conn = self.repository._get_connection()
        cursor = conn.execute("SELECT tax_id FROM nodes")
        return [row['tax_id'] for row in cursor.fetchall()]
    
    def _write_proteins_to_fasta(self, proteins: List[Dict[str, Any]], output_file: Path) -> None:
        """Write proteins to FASTA format."""
        with open(output_file, 'w') as f:
            for protein in proteins:
                accession = protein.get('protein_accession', protein['protein_id'])
                product = protein.get('product', '')
                sequence = protein['sequence']
                
                f.write(f">{accession} {product}\n")
                f.write(f"{sequence}\n")
    
    def _extract_by_genome(self, output_dir: Path, **kwargs) -> ExtractionResult:
        """Extract proteins with one file per genome."""
        # Implementation would create separate files for each genome
        # This is a placeholder
        raise NotImplementedError("by_genome strategy not yet implemented")
    
    def _extract_by_genus(self, output_dir: Path, **kwargs) -> ExtractionResult:
        """Extract proteins grouped by genus."""
        # Implementation would group taxa by genus and create files accordingly
        # This is a placeholder  
        raise NotImplementedError("by_genus strategy not yet implemented")
    
    def get_sequences_for_export(self, export_format: str) -> Dict[str, Any]:
        """Get sequence information needed for specific export format.
        
        Returns all necessary data to generate:
        - accession2taxid.txt
        - nucl2taxid.txt  
        - prot2taxid.txt
        - genome_sizes.txt
        """
        if export_format == 'diamond':
            return self._get_diamond_export_data()
        elif export_format == 'kraken2':
            return self._get_kraken2_export_data()
        elif export_format == 'mmseqs2':
            return self._get_mmseqs2_export_data()
        else:
            # Return general data that works for most formats
            return self._get_general_export_data()
    
    def _get_general_export_data(self) -> Dict[str, Any]:
        """Get general export data suitable for most formats."""
        taxa_with_sequences = self._get_taxa_with_genomes()
        
        all_accessions = []
        genome_sizes = []
        
        for tax_id in taxa_with_sequences:
            accessions = self.tracker.get_all_accessions_for_taxa(tax_id)
            genome_info = self.tracker.get_genome_size_info(tax_id)
            
            # Collect accession mappings
            for acc_type, acc_list in accessions.items():
                for accession in acc_list:
                    all_accessions.append({
                        'accession': accession,
                        'tax_id': tax_id,
                        'type': acc_type
                    })
            
            # Collect genome size info
            if genome_info['genome_size']:
                genome_sizes.append(genome_info)
        
        return {
            'accessions': all_accessions,
            'genome_sizes': genome_sizes,
            'taxa_count': len(taxa_with_sequences)
        }
    
    def _get_diamond_export_data(self) -> Dict[str, Any]:
        """Get export data specific to Diamond."""
        data = self._get_general_export_data()
        
        # Filter for protein accessions only
        protein_accessions = [
            acc for acc in data['accessions'] if acc['type'] == 'protein'
        ]
        
        data['protein_accessions'] = protein_accessions
        return data
    
    def _get_kraken2_export_data(self) -> Dict[str, Any]:
        """Get export data specific to Kraken2.""" 
        data = self._get_general_export_data()
        
        # Filter for nucleotide accessions
        nucleotide_accessions = [
            acc for acc in data['accessions'] 
            if acc['type'] in ['assembly', 'nucleotide']
        ]
        
        data['nucleotide_accessions'] = nucleotide_accessions
        return data
    
    def _get_mmseqs2_export_data(self) -> Dict[str, Any]:
        """Get export data specific to MMseqs2."""
        data = self._get_general_export_data()
        
        # MMseqs2 can use both protein and nucleotide
        data['supports_proteins'] = True
        data['supports_nucleotides'] = True
        
        return data
    
    def validate_all_sequences(self, level: str = "standard") -> Dict[str, Any]:
        """Validate all sequence files with comprehensive checking.
        
        Args:
            level: Validation level - "basic", "standard", or "comprehensive"
            
        Returns:
            Combined validation results from file and integrity checks
        """
        results = {}
        
        # Get file validation results
        try:
            file_results = self.tracker.validate_sequence_files(level=level)
            results.update(file_results)
        except AttributeError:
            # Method doesn't exist, skip
            pass
        
        # Get sequence integrity results for comprehensive validation
        if level == "comprehensive":
            try:
                integrity_results = self.tracker.validate_sequence_integrity()
                results.update(integrity_results)
            except AttributeError:
                # Method doesn't exist, skip
                pass
        
        return results
    
    def get_sequence_file_info(self, file_id: int) -> Any:
        """Get sequence file information by file ID.
        
        Args:
            file_id: The file ID to get info for
            
        Returns:
            SequenceFileInfo object with file details
        """
        return self.tracker.get_sequence_file_info(file_id)
    
    def update_file_validation_status(self, file_id: int, validation_result: Dict[str, Any]) -> None:
        """Update file validation status.
        
        Args:
            file_id: The file ID to update
            validation_result: Dictionary with validation results
        """
        self.tracker.update_file_validation_status(file_id, validation_result)
    
    def cleanup_missing_files(self, **kwargs) -> Dict[str, Any]:
        """Clean up missing sequence files.
        
        Args:
            **kwargs: Parameters to pass to the tracker cleanup method
            
        Returns:
            Dictionary with cleanup results
        """
        return self.tracker.cleanup_missing_files(**kwargs)