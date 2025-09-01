"""Sourmash taxonomy format exporter for taxonomic classification."""

import csv
from typing import Optional, Dict, Any
from pathlib import Path

from .base import FileBasedExporter
from ..core.models import TaxonomyTree, TaxonomyNode
from ..core.exceptions import ExportError
from ..utils.logging_config import get_logger

logger = get_logger(__name__)


class SourmashExporter(FileBasedExporter):
    """Exporter for Sourmash taxonomy CSV format.
    
    Creates CSV files compatible with sourmash tax commands for taxonomic
    classification and profiling. Supports both standard NCBI taxonomy ranks
    and optional strain-level information.
    
    Format requirements:
    - CSV file with 'ident' column containing genome identifiers
    - Standard taxonomic rank columns: superkingdom, phylum, class, order, family, genus, species
    - Optional strain column for strain-level classification
    - Compatible with sourmash v4.8+ and LCA/tax commands
    """
    
    @property
    def exporter_name(self) -> str:
        return "sourmash"
    
    @property
    def file_extensions(self) -> list[str]:
        return [".csv", ".tsv", ".csv.gz", ".tsv.gz"]
    
    def export(self, tree: TaxonomyTree, output_path: Path, **kwargs: Any) -> None:
        """Export taxonomy tree in Sourmash CSV format.
        
        Creates a CSV file with columns:
        - ident: Genome identifier (required)
        - superkingdom through species: Standard taxonomic ranks
        - strain: Optional strain-level information
        
        Args:
            tree: Taxonomy tree to export
            output_path: Output CSV file path
            **kwargs: Additional options
                - include_strain: Include strain column (default: True)
                - delimiter: CSV delimiter (default: ',')
                - include_genomes: Include genome data (default: True)
        """
        self._validate_tree(tree)
        self._ensure_output_path(output_path)
        
        logger.info(f"Exporting {tree.node_count} nodes to Sourmash format: {output_path}")
        
        # Configuration options
        include_strain = kwargs.get('include_strain', True)
        include_genomes = kwargs.get('include_genomes', True)
        delimiter = kwargs.get('delimiter', ',')
        
        if not include_genomes or tree.genome_count == 0:
            logger.warning("No genome information available for Sourmash export")
            self._create_empty_taxonomy_file(output_path, include_strain, delimiter)
            return
        
        # Create Sourmash taxonomy CSV
        self._create_taxonomy_csv(tree, output_path, include_strain, delimiter)
        
        logger.info(f"Sourmash export completed: {output_path}")
    
    def _create_empty_taxonomy_file(self, output_path: Path, include_strain: bool, 
                                   delimiter: str) -> None:
        """Create empty Sourmash taxonomy CSV with headers only."""
        try:
            headers = self._get_csv_headers(include_strain)
            
            with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile, delimiter=delimiter)
                writer.writerow(headers)
                
        except Exception as e:
            raise ExportError(f"Failed to create empty Sourmash taxonomy file: {e}")
    
    def _create_taxonomy_csv(self, tree: TaxonomyTree, output_path: Path,
                            include_strain: bool, delimiter: str) -> None:
        """Create Sourmash taxonomy CSV with genome mappings."""
        try:
            headers = self._get_csv_headers(include_strain)
            
            with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile, delimiter=delimiter)
                writer.writerow(headers)
                
                # Track exported genomes to avoid duplicates
                exported_genomes = set()
                
                for node in tree:
                    genomes = tree.get_genomes_for_node(node.tax_id)
                    for genome in genomes:
                        # Use primary identifier (assembly accession or genome ID)
                        ident = genome.assembly_accession or genome.genome_id
                        
                        if ident in exported_genomes:
                            continue
                        exported_genomes.add(ident)
                        
                        # Build taxonomic lineage
                        lineage = self._build_lineage(tree, node)
                        
                        # Create row data
                        row_data = self._create_row_data(ident, lineage, genome, include_strain)
                        writer.writerow(row_data)
                
                logger.info(f"Exported {len(exported_genomes)} genome taxonomies")
                
        except Exception as e:
            raise ExportError(f"Failed to create Sourmash taxonomy CSV: {e}")
    
    def _get_csv_headers(self, include_strain: bool) -> list[str]:
        """Get CSV headers for Sourmash taxonomy format."""
        headers = [
            'ident',           # Genome identifier
            'superkingdom',    # Domain/superkingdom
            'phylum',          # Phylum
            'class',           # Class
            'order',           # Order
            'family',          # Family
            'genus',           # Genus
            'species'          # Species
        ]
        
        if include_strain:
            headers.append('strain')
        
        return headers
    
    def _build_lineage(self, tree: TaxonomyTree, node: TaxonomyNode) -> Dict[str, str]:
        """Build taxonomic lineage for a node."""
        lineage = {
            'superkingdom': '',
            'phylum': '',
            'class': '',
            'order': '',
            'family': '',
            'genus': '',
            'species': '',
            'strain': ''
        }
        
        # Get full lineage path
        lineage_nodes = []
        current = node
        while current:
            lineage_nodes.append(current)
            parent_id = tree.get_parent_id(current.tax_id)
            current = tree.get_node(parent_id) if parent_id else None
        
        # Reverse to get root-to-leaf order
        lineage_nodes.reverse()
        
        # Map nodes to taxonomic ranks based on rank information
        for lineage_node in lineage_nodes:
            rank = lineage_node.rank.lower() if lineage_node.rank else ''
            name = lineage_node.name
            
            if rank in lineage:
                lineage[rank] = name
            elif rank == 'domain':
                lineage['superkingdom'] = name
            elif rank == 'kingdom' and not lineage['superkingdom']:
                lineage['superkingdom'] = name
            elif rank in ['subspecies', 'forma', 'varietas']:
                lineage['strain'] = name
        
        return lineage
    
    def _create_row_data(self, ident: str, lineage: Dict[str, str], 
                        genome, include_strain: bool) -> list[str]:
        """Create CSV row data for a genome."""
        row = [
            ident,
            lineage['superkingdom'],
            lineage['phylum'],
            lineage['class'],
            lineage['order'],
            lineage['family'],
            lineage['genus'],
            lineage['species']
        ]
        
        if include_strain:
            # Use strain from lineage or genome strain information
            strain = lineage['strain']
            if not strain and hasattr(genome, 'strain') and genome.strain:
                strain = genome.strain
            row.append(strain)
        
        return row
    
    def validate_export(self, output_path: Path) -> Dict[str, Any]:
        """Validate the created Sourmash taxonomy CSV."""
        try:
            with open(output_path, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                
                # Check required headers
                required_headers = ['ident', 'superkingdom', 'phylum', 'class', 
                                  'order', 'family', 'genus', 'species']
                
                if not reader.fieldnames:
                    return {'valid': False, 'error': 'No headers found'}
                
                missing_headers = [h for h in required_headers if h not in reader.fieldnames]
                if missing_headers:
                    return {'valid': False, 'error': f'Missing headers: {missing_headers}'}
                
                # Count rows and check for required data
                row_count = 0
                ident_count = 0
                
                for row in reader:
                    row_count += 1
                    if row.get('ident'):
                        ident_count += 1
                
                return {
                    'valid': True,
                    'headers': list(reader.fieldnames),
                    'total_rows': row_count,
                    'genomes_with_ident': ident_count,
                    'format': 'Sourmash taxonomy CSV'
                }
                
        except Exception as e:
            return {'valid': False, 'error': str(e)}