"""High-level sequence tracking interface for FlexTaxD."""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass

from .unified_manager import UnifiedSequenceManager, ExtractionResult
from .mapping_generator import MappingFileGenerator
from ..database.sqlite import SQLiteTaxonomyRepository
from ..core.exceptions import ValidationError, DatabaseError

logger = logging.getLogger(__name__)


@dataclass
class SequenceStats:
    """Statistics about tracked sequences."""
    total_files: int = 0
    genome_files: int = 0
    protein_files: int = 0
    taxa_with_genomes: int = 0
    taxa_with_proteins: int = 0
    total_sequences: int = 0
    total_proteins: int = 0
    file_validation_errors: List[str] = None


class SequenceTracker:
    """High-level interface for sequence tracking and export."""
    
    def __init__(self, repository: SQLiteTaxonomyRepository):
        """Initialize with database repository."""
        self.repository = repository
        self.manager = UnifiedSequenceManager(repository)
        self.generator = MappingFileGenerator(repository)
    
    def register_genomes(self, genome_dir: Path, pattern: str = "*.fna") -> Dict[str, int]:
        """Register genome files from directory.
        
        Args:
            genome_dir: Directory containing genome files
            pattern: Glob pattern for genome files
            
        Returns:
            Dictionary of {filename: file_id}
        """
        return self.manager.register_genome_files(genome_dir, pattern)
    
    def register_proteins(self, protein_dir: Path, pattern: str = "*.faa") -> Dict[str, int]:
        """Register protein files from directory.
        
        Args:
            protein_dir: Directory containing protein files  
            pattern: Glob pattern for protein files
            
        Returns:
            Dictionary of {filename: file_id}
        """
        return self.manager.register_protein_files(protein_dir, pattern)
    
    def extract_proteins(self, strategy: str, output_path: Path, **kwargs) -> ExtractionResult:
        """Extract proteins with specified strategy.
        
        Args:
            strategy: 'one_per_taxa', 'global', 'by_genome', 'by_genus'
            output_path: Base path for output
            **kwargs: Strategy-specific parameters
            
        Returns:
            ExtractionResult with files created and statistics
        """
        return self.manager.extract_proteins_flexible(strategy, output_path, **kwargs)
    
    def generate_mapping_files(self, output_dir: Path, 
                              formats: Optional[List[str]] = None,
                              prefix: str = '') -> Dict[str, int]:
        """Generate standard mapping files.
        
        Args:
            output_dir: Directory for output files
            formats: List of formats to generate, None for all
            prefix: Optional prefix for filenames
            
        Returns:
            Dictionary of {filename: count} for generated files
        """
        if formats is None:
            return self.generator.generate_all_mappings(output_dir, prefix)
        
        results = {}
        for fmt in formats:
            if fmt == 'accession2taxid':
                path = output_dir / f"{prefix}accession2taxid.txt"
                results[fmt] = self.generator.generate_accession2taxid(path)
            elif fmt == 'nucl2taxid':
                path = output_dir / f"{prefix}nucl2taxid.txt"
                results[fmt] = self.generator.generate_nucl2taxid(path)
            elif fmt == 'prot2taxid':
                path = output_dir / f"{prefix}prot2taxid.txt"
                results[fmt] = self.generator.generate_prot2taxid(path)
            elif fmt == 'genome_sizes':
                path = output_dir / f"{prefix}genome_sizes.txt"
                results[fmt] = self.generator.generate_genome_sizes(path)
            else:
                logger.warning(f"Unknown mapping format: {fmt}")
        
        return results
    
    def generate_for_tool(self, tool: str, output_dir: Path) -> Dict[str, int]:
        """Generate tool-specific mapping files.
        
        Args:
            tool: Tool name ('diamond', 'kraken2', 'mmseqs2', etc.)
            output_dir: Directory for output files
            
        Returns:
            Dictionary of generated files and counts
        """
        return self.generator.generate_for_tool(tool, output_dir)
    
    def get_sequence_statistics(self) -> SequenceStats:
        """Get comprehensive sequence tracking statistics."""
        conn = self.repository._get_connection()
        stats = SequenceStats()
        
        try:
            # File counts by type
            cursor = conn.execute("""
                SELECT file_type, COUNT(*) as count 
                FROM sequence_files 
                GROUP BY file_type
            """)
            file_counts = dict(cursor.fetchall())
            
            stats.genome_files = file_counts.get('genome', 0)
            stats.protein_files = file_counts.get('protein_taxa', 0) + file_counts.get('protein_global', 0)
            stats.total_files = sum(file_counts.values())
            
            # Taxa counts
            cursor = conn.execute("""
                SELECT COUNT(DISTINCT tax_id) FROM taxa_file_mapping tfm
                JOIN sequence_files sf ON tfm.file_id = sf.file_id
                WHERE sf.file_type = 'genome'
            """)
            stats.taxa_with_genomes = cursor.fetchone()[0]
            
            cursor = conn.execute("""
                SELECT COUNT(DISTINCT tax_id) FROM taxa_file_mapping tfm
                JOIN sequence_files sf ON tfm.file_id = sf.file_id
                WHERE sf.file_type IN ('protein_taxa', 'protein_global')
            """)
            stats.taxa_with_proteins = cursor.fetchone()[0]
            
            # Sequence counts
            cursor = conn.execute("""
                SELECT SUM(sequence_count) FROM sequence_files 
                WHERE sequence_count IS NOT NULL
            """)
            result = cursor.fetchone()[0]
            stats.total_sequences = result if result else 0
            
            # Protein counts
            cursor = conn.execute("SELECT COUNT(*) FROM proteins")
            stats.total_proteins = cursor.fetchone()[0]
            
            # File validation errors
            cursor = conn.execute("""
                SELECT file_path FROM sequence_files 
                WHERE file_exists = FALSE
            """)
            missing_files = [row[0] for row in cursor.fetchall()]
            
            stats.file_validation_errors = []
            for file_path in missing_files:
                stats.file_validation_errors.append(f"Missing file: {file_path}")
                
        except Exception as e:
            logger.error(f"Failed to get sequence statistics: {e}")
            
        return stats
    
    def validate_sequences(self) -> Dict[str, Any]:
        """Validate sequence tracking integrity.
        
        Returns:
            Dictionary with validation results and issues
        """
        return self.generator.validate_mappings()
    
    def cleanup_missing_files(self, dry_run: bool = True) -> Dict[str, Any]:
        """Clean up tracking entries for missing files.
        
        Args:
            dry_run: If True, only report what would be cleaned up
            
        Returns:
            Dictionary with cleanup results
        """
        conn = self.repository._get_connection()
        results = {
            'files_to_remove': [],
            'taxa_mappings_to_remove': [],
            'proteins_to_remove': [],
            'dry_run': dry_run
        }
        
        try:
            # Find files that don't exist
            cursor = conn.execute("""
                SELECT file_id, file_path FROM sequence_files 
                WHERE file_exists = FALSE
            """)
            missing_files = cursor.fetchall()
            
            for file_id, file_path in missing_files:
                results['files_to_remove'].append(file_path)
                
                if not dry_run:
                    with self.repository.transaction():
                        # Remove taxa mappings
                        cursor = conn.execute("""
                            DELETE FROM taxa_file_mapping WHERE file_id = ?
                        """, (file_id,))
                        results['taxa_mappings_to_remove'].append(cursor.rowcount)
                        
                        # Remove file record
                        conn.execute("DELETE FROM sequence_files WHERE file_id = ?", (file_id,))
            
            # Find orphaned proteins (proteins without valid genomes)
            cursor = conn.execute("""
                SELECT protein_id FROM proteins p
                WHERE p.genome_id IS NOT NULL 
                AND p.genome_id NOT IN (SELECT genome_id FROM genomes)
            """)
            orphaned_proteins = [row[0] for row in cursor.fetchall()]
            results['proteins_to_remove'] = orphaned_proteins
            
            if not dry_run and orphaned_proteins:
                with self.repository.transaction():
                    placeholders = ','.join('?' * len(orphaned_proteins))
                    conn.execute(f"""
                        DELETE FROM proteins WHERE protein_id IN ({placeholders})
                    """, orphaned_proteins)
                    
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
            results['error'] = str(e)
            
        return results
    
    def sync_with_genomes(self) -> Dict[str, Any]:
        """Synchronize sequence tracking with existing genomes table.
        
        Returns:
            Dictionary with sync results
        """
        conn = self.repository._get_connection()
        results = {
            'genomes_registered': 0,
            'files_registered': 0,
            'errors': []
        }
        
        try:
            with self.repository.transaction():
                # Get genomes that aren't tracked yet
                cursor = conn.execute("""
                    SELECT g.genome_id, g.tax_id, g.file_path, g.sequence_length
                    FROM genomes g
                    LEFT JOIN taxa_file_mapping tfm ON g.tax_id = tfm.tax_id
                    LEFT JOIN sequence_files sf ON tfm.file_id = sf.file_id 
                        AND sf.file_type = 'genome'
                    WHERE sf.file_id IS NULL AND g.file_path IS NOT NULL
                """)
                
                untracked_genomes = cursor.fetchall()
                
                for genome_id, tax_id, file_path, seq_length in untracked_genomes:
                    if file_path and Path(file_path).exists():
                        try:
                            file_id = self.manager.register_sequence_file(
                                Path(file_path), 'genome', 'single_taxa', [tax_id]
                            )
                            results['files_registered'] += 1
                            results['genomes_registered'] += 1
                        except Exception as e:
                            results['errors'].append(f"Failed to register {file_path}: {e}")
                            
        except Exception as e:
            logger.error(f"Sync with genomes failed: {e}")
            results['error'] = str(e)
            
        return results