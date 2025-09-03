"""MMseqs2 format exporter for taxonomic classification."""

from typing import Optional, Dict, Any, Set, List
from pathlib import Path

from .base import DirectoryBasedExporter
from ..core.models import TaxonomyTree
from ..core.exceptions import ExportError
from ..utils.logging_config import get_logger

logger = get_logger(__name__)


class MMseqs2Exporter(DirectoryBasedExporter):
    """Exporter for MMseqs2 createtaxdb format.
    
    MMseqs2 uses NCBI-style taxonomy files with enhanced support for:
    - Custom taxonomies integrated with NCBI framework
    - Optimized accession2taxid mappings
    - Support for both protein and nucleotide sequences
    - Integration with MMseqs2 createtaxdb workflow
    
    Creates NCBI-compatible files optimized for MMseqs2 taxonomy database creation.
    """
    
    @property
    def exporter_name(self) -> str:
        return "mmseqs2"
    
    @property
    def file_extensions(self) -> list[str]:
        return [".dmp", ".txt", ".tsv"]
    
    def export(self, tree: TaxonomyTree, output_path: Path, **kwargs: Any) -> None:
        """Export taxonomy tree in MMseqs2 createtaxdb format.
        
        Creates:
        - names.dmp: Taxonomic names file (NCBI format)
        - nodes.dmp: Taxonomic nodes file (NCBI format)
        - accession2taxid.txt: Sequence to taxonomy mapping
        - taxonomy_mapping.tsv: Enhanced mapping for MMseqs2
        
        Args:
            tree: Taxonomy tree to export
            output_path: Output directory path
            **kwargs: Additional options
                - compress: Compress output files (default: False)
                - include_genomes: Include genome mappings (default: True)
                - sequence_type: Filter sequences by type ('all', 'protein', 'nucleotide')
                - create_lca_mapping: Create LCA-compatible mappings (default: True)
        """
        self._validate_tree(tree)
        self._ensure_output_path(output_path)
        
        logger.info(f"Exporting {tree.node_count} nodes to MMseqs2 format: {output_path}")
        
        # Configuration options
        compress = kwargs.get('compress', False)
        include_genomes = kwargs.get('include_genomes', True)
        sequence_type = kwargs.get('sequence_type', 'all')
        create_lca_mapping = kwargs.get('create_lca_mapping', True)
        
        # Create core taxonomy files
        names_path = output_path / "names.dmp"
        nodes_path = output_path / "nodes.dmp"
        
        self._write_names_file(tree, names_path, compress)
        self._write_nodes_file(tree, nodes_path, compress)
        
        # Create sequence mappings if genomes are present
        if include_genomes and tree.genome_count > 0:
            accession_path = output_path / "accession2taxid.txt"
            self._write_accession_mapping(tree, accession_path, compress, sequence_type)
            
            # Create enhanced mapping for MMseqs2
            if create_lca_mapping:
                mapping_path = output_path / "taxonomy_mapping.tsv"
                self._write_taxonomy_mapping(tree, mapping_path, compress, sequence_type)
        
        # Create MMseqs2 configuration file
        config_path = output_path / "mmseqs2_config.txt"
        self._write_mmseqs2_config(tree, config_path)
        
        logger.info(f"MMseqs2 export completed: {names_path}, {nodes_path}")
    
    def _write_names_file(self, tree: TaxonomyTree, output_path: Path, compress: bool) -> None:
        """Write NCBI names.dmp format file optimized for MMseqs2."""
        name_counts: Dict[str, int] = {}
        name_entries = []
        
        # First pass: collect all names and count duplicates
        for node in tree:
            escaped_name = self._escape_name(node.name)
            name_counts[escaped_name] = name_counts.get(escaped_name, 0) + 1
            name_entries.append((node.tax_id, escaped_name))
        
        # Second pass: write with MMseqs2 optimizations
        with open(output_path, 'w', encoding='utf-8', newline='\n') as f:
            used_unique_names: Set[str] = set()
            for tax_id, escaped_name in name_entries:
                # Generate unique name if duplicates exist
                unique_name = self._generate_unique_name(
                    escaped_name, tax_id, name_counts, used_unique_names
                )
                
                # NCBI names.dmp format: tax_id | name | unique name | name class |
                f.write(f"{tax_id}\t|\t{escaped_name}\t|\t{unique_name}\t|\tscientific name\t|\n")
                
                # Add common name entry if different from scientific name
                if self._should_add_common_name(escaped_name):
                    common_name = self._generate_common_name(escaped_name)
                    f.write(f"{tax_id}\t|\t{common_name}\t|\t\t|\tcommon name\t|\n")
        
        if compress:
            from ..utils.subprocess_utils import compress_file
            compress_file(output_path)
    
    def _write_nodes_file(self, tree: TaxonomyTree, output_path: Path, compress: bool) -> None:
        """Write NCBI nodes.dmp format file optimized for MMseqs2."""
        with open(output_path, 'w', encoding='utf-8', newline='\n') as f:
            for node in tree:
                # Parent ID validation
                parent_id = self._validate_parent_id(node, tree)
                
                # Rank validation with MMseqs2 optimizations
                rank = self._validate_rank_for_mmseqs2(node.rank)
                
                # NCBI nodes.dmp format with MMseqs2 optimizations
                fields = [
                    str(node.tax_id),           # tax_id
                    str(parent_id),             # parent_tax_id  
                    rank,                       # rank
                    "",                         # embl_code
                    self._get_division_id(node), # division_id (optimized)
                    "1",                        # inherited_div_flag
                    self._get_genetic_code(node), # genetic_code_id
                    "1",                        # inherited_gc_flag
                    self._get_mito_genetic_code(node), # mitochondrial_genetic_code_id
                    "1",                        # inherited_mgc_flag
                    "0",                        # genbank_hidden_flag
                    "0",                        # hidden_subtree_root_flag
                    "",                         # comments
                ]
                
                f.write("\t|\t".join(fields) + "\t|\n")
        
        if compress:
            from ..utils.subprocess_utils import compress_file
            compress_file(output_path)
    
    def _write_accession_mapping(self, tree: TaxonomyTree, output_path: Path, 
                                compress: bool, sequence_type: str) -> None:
        """Write accession2taxid mapping file optimized for MMseqs2."""
        sequences_mapped = 0
        
        with open(output_path, 'w', encoding='utf-8', newline='\n') as f:
            # NCBI accession2taxid format header
            f.write("accession\taccession.version\ttaxid\tgi\n")
            
            for node in tree:
                genomes = tree.get_genomes_for_node(node.tax_id)
                for genome in genomes:
                    # Filter by sequence type if specified
                    if not self._matches_sequence_type(genome, sequence_type):
                        continue
                    
                    # Map primary accession
                    accession = genome.genome_id
                    f.write(f"{accession}\t{accession}\t{node.tax_id}\t0\n")
                    sequences_mapped += 1
                    
                    # Map assembly accession if different
                    if genome.assembly_accession and genome.assembly_accession != genome.genome_id:
                        acc = genome.assembly_accession
                        f.write(f"{acc}\t{acc}\t{node.tax_id}\t0\n")
                        sequences_mapped += 1
                    
                    # Extract and map additional accessions for MMseqs2 compatibility
                    additional_accs = self._extract_mmseqs2_accessions(genome.genome_id)
                    for acc in additional_accs:
                        f.write(f"{acc}\t{acc}\t{node.tax_id}\t0\n")
                        sequences_mapped += 1
        
        logger.info(f"Created MMseqs2 accession mapping with {sequences_mapped} entries")
        
        if compress:
            from ..utils.subprocess_utils import compress_file
            compress_file(output_path)
    
    def _write_taxonomy_mapping(self, tree: TaxonomyTree, output_path: Path,
                               compress: bool, sequence_type: str) -> None:
        """Write enhanced taxonomy mapping for MMseqs2 LCA operations."""
        mappings_created = 0
        
        with open(output_path, 'w', encoding='utf-8', newline='\n') as f:
            # Header for enhanced mapping
            f.write("accession\ttaxid\tlineage\trank\tlca_level\n")
            
            for node in tree:
                genomes = tree.get_genomes_for_node(node.tax_id)
                for genome in genomes:
                    # Filter by sequence type
                    if not self._matches_sequence_type(genome, sequence_type):
                        continue
                    
                    # Get lineage for LCA operations
                    lineage = self._get_taxonomic_lineage(tree, node)
                    rank = self._validate_rank_for_mmseqs2(node.rank)
                    lca_level = self._calculate_lca_level(tree, node)
                    
                    # Write mapping entry
                    f.write(f"{genome.genome_id}\t{node.tax_id}\t{lineage}\t{rank}\t{lca_level}\n")
                    mappings_created += 1
                    
                    # Additional accessions
                    additional_accs = self._extract_mmseqs2_accessions(genome.genome_id)
                    for acc in additional_accs:
                        f.write(f"{acc}\t{node.tax_id}\t{lineage}\t{rank}\t{lca_level}\n")
                        mappings_created += 1
        
        logger.info(f"Created MMseqs2 taxonomy mapping with {mappings_created} entries")
        
        if compress:
            from ..utils.subprocess_utils import compress_file
            compress_file(output_path)
    
    def _write_mmseqs2_config(self, tree: TaxonomyTree, output_path: Path) -> None:
        """Write MMseqs2 configuration file with usage instructions."""
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("# MMseqs2 Taxonomy Database Configuration\n")
            f.write("# Generated by FlexTaxD\n\n")
            
            f.write(f"# Taxonomy Statistics:\n")
            f.write(f"# - Total nodes: {tree.node_count}\n")
            f.write(f"# - Total genomes: {tree.genome_count}\n")
            f.write(f"# - Root taxid: {tree.root_id}\n\n")
            
            f.write("# Usage Instructions:\n")
            f.write("# 1. Create MMseqs2 database from your sequence files:\n")
            f.write("#    mmseqs createdb sequences.fasta seqDB\n\n")
            
            f.write("# 2. Create taxonomy database using exported files:\n")
            f.write("#    mmseqs createtaxdb seqDB taxDB --tax-mapping-file accession2taxid.txt \\\n")
            f.write("#                      --ncbi-tax-dump names.dmp,nodes.dmp\n\n")
            
            f.write("# 3. Run taxonomic assignment:\n")
            f.write("#    mmseqs taxonomy queryDB taxDB resultDB\n\n")
            
            f.write("# 4. Convert results to readable format:\n")
            f.write("#    mmseqs taxonomyreport taxDB resultDB report.tsv\n\n")
            
            f.write("# Advanced Options:\n")
            f.write("# - Use --lca-mode for different LCA strategies (2, 3, 4)\n")
            f.write("# - Adjust --majority for LCA threshold\n")
            f.write("# - Use --tax-lineage for detailed lineage output\n")
        
        logger.info(f"Created MMseqs2 configuration file: {output_path}")
    
    def _generate_unique_name(self, name: str, tax_id: int, name_counts: Dict[str, int],
                             used_unique_names: Set[str]) -> str:
        """Generate unique name for taxa when duplicates exist."""
        if name_counts.get(name, 0) <= 1:
            return ""
        
        unique_name = f"{name} <{tax_id}>"
        counter = 1
        original_unique = unique_name
        while unique_name in used_unique_names:
            unique_name = f"{original_unique}_{counter}"
            counter += 1
        
        used_unique_names.add(unique_name)
        return unique_name
    
    def _should_add_common_name(self, scientific_name: str) -> bool:
        """Determine if a common name should be added for MMseqs2."""
        # Add common names for well-known organisms
        common_indicators = ['escherichia', 'bacillus', 'streptococcus', 'staphylococcus']
        return any(indicator in scientific_name.lower() for indicator in common_indicators)
    
    def _generate_common_name(self, scientific_name: str) -> str:
        """Generate common name from scientific name."""
        # Simple common name generation (genus + "sp." for species)
        parts = scientific_name.split()
        if len(parts) >= 2:
            return f"{parts[0]} sp."
        return scientific_name
    
    def _validate_parent_id(self, node: Any, tree: TaxonomyTree) -> int:
        """Validate and return proper parent ID for node."""
        if node.parent_id is None or node.tax_id == 1:
            return int(node.tax_id)
            
        if tree.get_node(node.parent_id) is None:
            logger.warning(f"Node {node.tax_id} references non-existent parent {node.parent_id}")
            return int(node.tax_id)
            
        return int(node.parent_id)
    
    def _validate_rank_for_mmseqs2(self, rank: Any) -> str:
        """Validate taxonomic rank with MMseqs2 optimizations."""
        if rank is None:
            return "no rank"
            
        rank_str = str(rank).lower()
        if hasattr(rank, 'value'):
            rank_str = rank.value.lower()
            
        # MMseqs2-optimized rank mapping
        rank_mapping = {
            'custom': 'no rank',
            'root': 'no rank', 
            'domain': 'superkingdom',
            'kingdom': 'kingdom',
            'phylum': 'phylum',
            'class': 'class',
            'order': 'order', 
            'family': 'family',
            'genus': 'genus',
            'species': 'species',
            'strain': 'no rank',
            'subspecies': 'subspecies',
            'varietas': 'varietas',
            'forma': 'forma',
        }
        
        return rank_mapping.get(rank_str, rank_str)
    
    def _get_division_id(self, node: Any) -> str:
        """Get division ID optimized for MMseqs2."""
        # Simplified division mapping for MMseqs2
        if hasattr(node.rank, 'value'):
            rank = node.rank.value.lower()
        else:
            rank = str(node.rank).lower()
        
        # Basic division mapping
        if 'bacteria' in node.name.lower() or rank == 'superkingdom':
            return "0"  # Bacteria
        elif 'archaea' in node.name.lower():
            return "2"  # Archaea
        elif 'virus' in node.name.lower():
            return "9"  # Viruses
        else:
            return "0"  # Default
    
    def _get_genetic_code(self, node: Any) -> str:
        """Get genetic code optimized for MMseqs2."""
        # Most bacteria and archaea use standard genetic code
        if 'bacteria' in node.name.lower() or 'archaea' in node.name.lower():
            return "11"  # Bacterial genetic code
        return "1"   # Standard genetic code
    
    def _get_mito_genetic_code(self, node: Any) -> str:
        """Get mitochondrial genetic code for MMseqs2."""
        # Simplified mitochondrial genetic code assignment
        return "1"  # Standard for most cases
    
    def _matches_sequence_type(self, genome: Any, sequence_type: str) -> bool:
        """Check if genome matches the specified sequence type filter."""
        if sequence_type == 'all':
            return True
        
        genome_type = getattr(genome, 'sequence_type', '').lower()
        
        if sequence_type == 'protein':
            return genome_type in ['protein', 'cds']
        elif sequence_type == 'nucleotide':
            return genome_type in ['genome', 'nucleotide', 'dna', 'rna', 'cdna']
        
        return True  # Default to include if uncertain
    
    def _extract_mmseqs2_accessions(self, genome_id: str) -> List[str]:
        """Extract accessions optimized for MMseqs2."""
        accessions: List[str] = []
        
        # MMseqs2-specific accession patterns
        separators = ['|', ';', ',', ' ', '_']
        parts = [genome_id]
        
        for sep in separators:
            new_parts: List[str] = []
            for part in parts:
                new_parts.extend(part.split(sep))
            parts = new_parts
        
        # Filter for MMseqs2-compatible accession formats
        for part in parts:
            part = part.strip()
            if (part and part != genome_id and len(part) > 3 and 
                any(c.isalpha() for c in part) and any(c.isdigit() for c in part)):
                # Additional validation for MMseqs2 compatibility
                if not part.startswith('gi|') and '.' in part:
                    accessions.append(part)
        
        return accessions
    
    def _get_taxonomic_lineage(self, tree: TaxonomyTree, node: Any) -> str:
        """Get full taxonomic lineage for LCA operations."""
        lineage_parts = []
        current = node
        
        while current:
            lineage_parts.append(str(current.tax_id))
            if current.parent_id and current.parent_id != current.tax_id:
                current = tree.get_node(current.parent_id)
            else:
                break
        
        # Reverse to get root-to-leaf order
        lineage_parts.reverse()
        return ";".join(lineage_parts)
    
    def _calculate_lca_level(self, tree: TaxonomyTree, node: Any) -> int:
        """Calculate LCA level for MMseqs2 operations."""
        level = 0
        current = node
        
        while current and current.parent_id and current.parent_id != current.tax_id:
            level += 1
            current = tree.get_node(current.parent_id)
        
        return level
    
    def _escape_name(self, name: str) -> str:
        """Escape special characters in taxonomic names."""
        if not name:
            return "unnamed"
        
        escaped = name.replace('\t', ' ').replace('|', ';')
        escaped = escaped.replace('\n', ' ').replace('\r', ' ')
        escaped = ' '.join(escaped.split())
        
        return escaped if escaped else "unnamed"
    
    def validate_export(self, output_path: Path) -> Dict[str, Any]:
        """Validate the created MMseqs2 taxonomy files."""
        try:
            validation_results: Dict[str, Any] = {
                'valid': True,
                'files_created': [],
                'errors': [],
                'format': 'MMseqs2 createtaxdb'
            }
            
            # Check required files
            required_files = ['names.dmp', 'nodes.dmp']
            optional_files = ['accession2taxid.txt', 'taxonomy_mapping.tsv', 'mmseqs2_config.txt']
            
            for filename in required_files:
                file_path = output_path / filename
                if file_path.exists():
                    validation_results['files_created'].append(filename)
                else:
                    validation_results['valid'] = False
                    validation_results['errors'].append(f"Required file missing: {filename}")
            
            for filename in optional_files:
                file_path = output_path / filename
                if file_path.exists():
                    validation_results['files_created'].append(filename)
            
            # Validate file formats
            names_file = output_path / "names.dmp"
            if names_file.exists():
                try:
                    with open(names_file, 'r') as f:
                        first_line = f.readline().strip()
                        if not first_line or first_line.count('\t|\t') < 3:
                            validation_results['errors'].append("names.dmp: Invalid format")
                except Exception as e:
                    validation_results['errors'].append(f"names.dmp: Read error - {e}")
            
            if validation_results['errors']:
                validation_results['valid'] = False
            
            return validation_results
            
        except Exception as e:
            return {'valid': False, 'error': str(e)}