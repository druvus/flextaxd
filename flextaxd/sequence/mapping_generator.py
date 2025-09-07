"""Generate standard mapping files from unified tracking system."""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
import csv

from ..database.sequence_tracking import UnifiedSequenceTracker
from ..database.sqlite import SQLiteTaxonomyRepository
from ..core.exceptions import DatabaseError, ValidationError

logger = logging.getLogger(__name__)


class MappingFileGenerator:
    """Generate standard mapping files from unified tracking system."""
    
    def __init__(self, repository: SQLiteTaxonomyRepository):
        """Initialize with repository."""
        self.repository = repository
        self.tracker = UnifiedSequenceTracker(repository)
    
    def generate_accession2taxid(self, output_path: Path, 
                                sequence_types: Optional[List[str]] = None) -> int:
        """Generate accession2taxid.txt from tracked sequences.
        
        Args:
            output_path: Output file path
            sequence_types: ['assembly', 'nucleotide', 'protein'] or None for all
            
        Format:
        accession    accession.version    taxid    gi
        GCF_000005825    GCF_000005825.2    562    0
        WP_000001234    WP_000001234.1    562    0
        
        Returns:
            Number of mappings written
        """
        if sequence_types is None:
            sequence_types = ['assembly', 'nucleotide', 'protein']
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        count = 0
        taxa_with_sequences = self._get_taxa_with_sequences()
        
        with open(output_path, 'w', newline='') as f:
            writer = csv.writer(f, delimiter='\t')
            
            # Write header
            writer.writerow(['accession', 'accession.version', 'taxid', 'gi'])
            
            for tax_id in taxa_with_sequences:
                accessions = self.tracker.get_all_accessions_for_taxa(tax_id)
                
                for acc_type in sequence_types:
                    if acc_type in accessions:
                        for accession in accessions[acc_type]:
                            if accession:
                                # Split version if present
                                if '.' in accession:
                                    base_acc, version = accession.rsplit('.', 1)
                                    full_acc = accession
                                else:
                                    base_acc = accession
                                    full_acc = f"{accession}.1"  # Default version
                                
                                writer.writerow([base_acc, full_acc, tax_id, 0])
                                count += 1
        
        logger.info(f"Generated accession2taxid with {count} mappings")
        return count
    
    def generate_nucl2taxid(self, output_path: Path) -> int:
        """Generate nucl2taxid.txt from nucleotide sequences.
        
        Format:
        accession    accession.version    taxid    gi
        NC_000913    NC_000913.3    562    0
        """
        return self.generate_accession2taxid(output_path, ['assembly', 'nucleotide'])
    
    def generate_prot2taxid(self, output_path: Path) -> int:
        """Generate prot2taxid.txt from protein sequences.
        
        Format:
        accession    accession.version    taxid    gi
        WP_000001234    WP_000001234.1    562    0
        """
        return self.generate_accession2taxid(output_path, ['protein'])
    
    def generate_genome_sizes(self, output_path: Path) -> int:
        """Generate genome_sizes.txt with sequence length information.
        
        Format:
        taxid    genome_size    assembly_accession
        562    4641652    GCF_000005825.2
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        count = 0
        taxa_with_genomes = self._get_taxa_with_genomes()
        
        with open(output_path, 'w', newline='') as f:
            writer = csv.writer(f, delimiter='\t')
            
            # Write header
            writer.writerow(['taxid', 'genome_size', 'assembly_accession'])
            
            for tax_id in taxa_with_genomes:
                genome_info = self.tracker.get_genome_size_info(tax_id)
                
                if genome_info['genome_size'] is not None:
                    writer.writerow([
                        tax_id,
                        genome_info['genome_size'],
                        genome_info['assembly_accession'] or ''
                    ])
                    count += 1
        
        logger.info(f"Generated genome_sizes with {count} entries")
        return count
    
    def generate_all_mappings(self, output_dir: Path, 
                             prefix: str = '') -> Dict[str, int]:
        """Generate all standard mapping files.
        
        Args:
            output_dir: Directory for output files
            prefix: Optional prefix for filenames
            
        Returns:
            Dictionary of {filename: count} for each generated file
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        
        results = {}
        
        # Generate accession2taxid (all accessions)
        acc2taxid_path = output_dir / f"{prefix}accession2taxid.txt"
        results['accession2taxid.txt'] = self.generate_accession2taxid(acc2taxid_path)
        
        # Generate nucl2taxid (nucleotide accessions only)
        nucl2taxid_path = output_dir / f"{prefix}nucl2taxid.txt"
        results['nucl2taxid.txt'] = self.generate_nucl2taxid(nucl2taxid_path)
        
        # Generate prot2taxid (protein accessions only)
        prot2taxid_path = output_dir / f"{prefix}prot2taxid.txt"
        results['prot2taxid.txt'] = self.generate_prot2taxid(prot2taxid_path)
        
        # Generate genome_sizes
        genome_sizes_path = output_dir / f"{prefix}genome_sizes.txt"
        results['genome_sizes.txt'] = self.generate_genome_sizes(genome_sizes_path)
        
        # Generate summary
        summary_path = output_dir / f"{prefix}mapping_summary.json"
        self._generate_summary(summary_path, results)
        
        total_mappings = sum(results.values())
        logger.info(f"Generated all mapping files with {total_mappings} total entries")
        
        return results
    
    def generate_for_tool(self, tool: str, output_dir: Path) -> Dict[str, int]:
        """Generate mapping files specific to a classification tool.
        
        Args:
            tool: 'diamond', 'kraken2', 'mmseqs2', 'kaiju', etc.
            output_dir: Directory for output files
            
        Returns:
            Dictionary of generated files and their counts
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        
        if tool.lower() == 'diamond':
            return self._generate_diamond_mappings(output_dir)
        elif tool.lower() == 'kraken2':
            return self._generate_kraken2_mappings(output_dir)
        elif tool.lower() == 'mmseqs2':
            return self._generate_mmseqs2_mappings(output_dir)
        elif tool.lower() == 'kaiju':
            return self._generate_kaiju_mappings(output_dir)
        else:
            # Default: generate all mappings
            logger.warning(f"Unknown tool '{tool}', generating all mappings")
            return self.generate_all_mappings(output_dir)
    
    def _generate_diamond_mappings(self, output_dir: Path) -> Dict[str, int]:
        """Generate mappings specific to Diamond."""
        results = {}
        
        # Diamond primarily needs protein mappings
        prot2taxid_path = output_dir / "prot.accession2taxid"
        results['prot.accession2taxid'] = self.generate_prot2taxid(prot2taxid_path)
        
        # Also useful for Diamond
        genome_sizes_path = output_dir / "genome_sizes.txt"
        results['genome_sizes.txt'] = self.generate_genome_sizes(genome_sizes_path)
        
        return results
    
    def _generate_kraken2_mappings(self, output_dir: Path) -> Dict[str, int]:
        """Generate mappings specific to Kraken2."""
        results = {}
        
        # Kraken2 needs nucleotide mappings (renamed for Kraken2)
        seqid2taxid_path = output_dir / "seqid2taxid.map"
        results['seqid2taxid.map'] = self.generate_nucl2taxid(seqid2taxid_path)
        
        # Also generate standard accession2taxid
        acc2taxid_path = output_dir / "accession2taxid.txt"
        results['accession2taxid.txt'] = self.generate_accession2taxid(acc2taxid_path)
        
        return results
    
    def _generate_mmseqs2_mappings(self, output_dir: Path) -> Dict[str, int]:
        """Generate mappings specific to MMseqs2."""
        results = {}
        
        # MMseqs2 can use both protein and nucleotide
        acc2taxid_path = output_dir / "accession2taxid.txt"
        results['accession2taxid.txt'] = self.generate_accession2taxid(acc2taxid_path)
        
        # Generate enhanced mapping with LCA information
        lca_mapping_path = output_dir / "taxonomy_mapping.tsv"
        results['taxonomy_mapping.tsv'] = self._generate_lca_mapping(lca_mapping_path)
        
        return results
    
    def _generate_kaiju_mappings(self, output_dir: Path) -> Dict[str, int]:
        """Generate mappings specific to Kaiju."""
        results = {}
        
        # Kaiju primarily uses protein sequences
        prot2taxid_path = output_dir / "prot.accession2taxid"
        results['prot.accession2taxid'] = self.generate_prot2taxid(prot2taxid_path)
        
        return results
    
    def _generate_lca_mapping(self, output_path: Path) -> int:
        """Generate enhanced LCA mapping for MMseqs2.
        
        Format:
        accession    taxid    lca_taxid    lineage
        """
        count = 0
        taxa_with_sequences = self._get_taxa_with_sequences()
        
        with open(output_path, 'w', newline='') as f:
            writer = csv.writer(f, delimiter='\t')
            
            # Write header
            writer.writerow(['accession', 'taxid', 'lca_taxid', 'lineage'])
            
            for tax_id in taxa_with_sequences:
                accessions = self.tracker.get_all_accessions_for_taxa(tax_id)
                lineage = self._get_lineage_string(tax_id)
                
                # Use tax_id as LCA for now (could be enhanced)
                lca_taxid = tax_id
                
                for acc_type, acc_list in accessions.items():
                    for accession in acc_list:
                        if accession:
                            writer.writerow([accession, tax_id, lca_taxid, lineage])
                            count += 1
        
        logger.info(f"Generated LCA mapping with {count} entries")
        return count
    
    def _generate_summary(self, output_path: Path, results: Dict[str, int]) -> None:
        """Generate a summary file with mapping statistics."""
        import json
        from datetime import datetime
        
        summary = {
            'generated_at': datetime.now().isoformat(),
            'total_taxa': len(self._get_taxa_with_sequences()),
            'files_generated': results,
            'total_mappings': sum(results.values())
        }
        
        with open(output_path, 'w') as f:
            json.dump(summary, f, indent=2)
        
        logger.info(f"Generated mapping summary: {summary}")
    
    def _get_taxa_with_sequences(self) -> List[int]:
        """Get all taxa that have sequences (genomes or proteins)."""
        conn = self.repository._get_connection()
        
        # Get taxa with genomes
        cursor = conn.execute("SELECT DISTINCT tax_id FROM genomes")
        taxa_with_genomes = set(row['tax_id'] for row in cursor.fetchall())
        
        # Get taxa with proteins (if proteins table exists)
        try:
            cursor = conn.execute("SELECT DISTINCT tax_id FROM proteins")
            taxa_with_proteins = set(row['tax_id'] for row in cursor.fetchall())
        except:
            taxa_with_proteins = set()
        
        return list(taxa_with_genomes | taxa_with_proteins)
    
    def _get_taxa_with_genomes(self) -> List[int]:
        """Get all taxa that have genome files."""
        conn = self.repository._get_connection()
        cursor = conn.execute("SELECT DISTINCT tax_id FROM genomes")
        return [row['tax_id'] for row in cursor.fetchall()]
    
    def _get_lineage_string(self, tax_id: int) -> str:
        """Get lineage string for a taxonomic node."""
        try:
            # Get the complete taxonomy tree
            tree = self.repository.load_tree()
            
            # Get lineage from root to this node
            lineage = []
            current_id = tax_id
            
            while current_id is not None:
                node = tree.get_node(current_id)
                if node:
                    lineage.append(node.name)
                    current_id = node.parent_id
                else:
                    break
            
            # Reverse to get root -> leaf order
            lineage.reverse()
            
            return ';'.join(lineage)
            
        except Exception as e:
            logger.warning(f"Failed to get lineage for tax_id {tax_id}: {e}")
            return ''
    
    def validate_mappings(self) -> Dict[str, Any]:
        """Validate consistency of accession mappings.
        
        Returns:
            Dictionary with validation results
        """
        results = {
            'valid_mappings': 0,
            'invalid_mappings': 0,
            'duplicate_accessions': [],
            'missing_taxa': [],
            'issues': []
        }
        
        try:
            taxa_with_sequences = self._get_taxa_with_sequences()
            accession_counts = {}
            
            for tax_id in taxa_with_sequences:
                # Check if tax_id exists in taxonomy
                conn = self.repository._get_connection()
                cursor = conn.execute("SELECT 1 FROM nodes WHERE tax_id = ?", (tax_id,))
                if not cursor.fetchone():
                    results['missing_taxa'].append(tax_id)
                    results['issues'].append(f"Tax ID {tax_id} not found in taxonomy")
                    continue
                
                # Get accessions for this taxa
                accessions = self.tracker.get_all_accessions_for_taxa(tax_id)
                
                for acc_type, acc_list in accessions.items():
                    for accession in acc_list:
                        if accession:
                            if accession in accession_counts:
                                # Duplicate accession
                                results['duplicate_accessions'].append(accession)
                                results['issues'].append(
                                    f"Duplicate accession {accession} for taxa "
                                    f"{accession_counts[accession]} and {tax_id}"
                                )
                                results['invalid_mappings'] += 1
                            else:
                                accession_counts[accession] = tax_id
                                results['valid_mappings'] += 1
        
        except Exception as e:
            results['issues'].append(f"Validation error: {e}")
            logger.error(f"Mapping validation failed: {e}")
        
        logger.info(f"Mapping validation: {results['valid_mappings']} valid, "
                   f"{results['invalid_mappings']} invalid, "
                   f"{len(results['issues'])} issues")
        
        return results