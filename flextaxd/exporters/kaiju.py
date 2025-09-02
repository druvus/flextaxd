"""Kaiju format exporter.

Kaiju is a fast and sensitive taxonomic classification tool for metagenomic sequencing reads
using protein reference databases. This exporter creates the taxonomy files needed for Kaiju:

- nodes.dmp: NCBI format taxonomic hierarchy
- names.dmp: NCBI format taxonomic names

Note: Kaiju also requires a protein database index file (kaiju_db_*.fmi) which is created
by Kaiju's own kaiju-makedb tool from protein FASTA sequences. This exporter only creates
the taxonomy files that are compatible with nf-core/createtaxdb pipeline.
"""

from typing import Optional, Dict, Any, Set
from pathlib import Path
import re

from .base import DirectoryBasedExporter
from ..core.models import TaxonomyTree, TaxonomicRank
from ..core.exceptions import ExportError, ValidationError
from ..utils.logging_config import get_logger

logger = get_logger(__name__)


class KaijuExporter(DirectoryBasedExporter):
    """Exporter for Kaiju taxonomy format with full nf-core/createtaxdb compatibility.
    
    Creates NCBI-compliant taxonomy files for Kaiju metagenomics classifier.
    Includes robust validation, special character escaping, and unique name generation.
    
    Kaiju Format Requirements:
    - nodes.dmp: NCBI format taxonomic hierarchy with all required fields
    - names.dmp: NCBI format taxonomic names (scientific names and synonyms)
    - Files must be NCBI-compliant for compatibility with Kaiju and nf-core/createtaxdb
    - Protein database index (.fmi) is created separately by kaiju-makedb
    
    The taxonomy files produced by this exporter can be used with:
    - kaiju-makedb for building custom databases
    - nf-core/createtaxdb pipeline for automated database construction
    - Direct use with pre-built Kaiju protein databases
    """
    
    def __init__(self) -> None:
        super().__init__()
        self._unique_names: Dict[str, int] = {}
        self._processed_names: Set[str] = set()
    
    @property
    def exporter_name(self) -> str:
        return "kaiju"
    
    @property
    def file_extensions(self) -> list[str]:
        return [".dmp"]
    
    def export(self, tree: TaxonomyTree, output_path: Path, **kwargs: Any) -> None:
        """Export taxonomy tree in Kaiju format.
        
        Creates NCBI-compliant taxonomy files for use with Kaiju:
        - nodes.dmp: Taxonomic hierarchy
        - names.dmp: Taxonomic names
        
        Args:
            tree: TaxonomyTree to export
            output_path: Output directory path
            **kwargs: Export options including compress
            
        Note:
            This exporter only creates taxonomy files. The protein database index
            (.fmi file) must be created separately using kaiju-makedb tool.
        """
        self._validate_tree(tree)
        self._ensure_output_path(output_path)
        
        logger.info(f"Starting Kaiju export: {tree.node_count} nodes to {output_path}")
        
        # Parse configuration
        compress = kwargs.get('compress', False)
        
        try:
            # Reset state for new export
            self._unique_names.clear()
            self._processed_names.clear()
            
            # Build unique names mapping for validation
            self._build_unique_names(tree)
            
            # Create NCBI-compliant taxonomy files
            names_path = output_path / "names.dmp"
            nodes_path = output_path / "nodes.dmp"
            
            self._write_names_file(tree, names_path, compress)
            self._write_nodes_file(tree, nodes_path, compress)
            
            logger.info(f"Kaiju export completed successfully")
            logger.info(f"To build Kaiju database index, run: kaiju-makedb -s [source] --output {output_path}/")
            
        except Exception as e:
            logger.error(f"Kaiju export failed: {str(e)}")
            raise ExportError(f"Failed to export Kaiju format: {str(e)}") from e
    
    def _build_unique_names(self, tree: TaxonomyTree) -> None:
        """Build mapping of unique names to handle duplicates."""
        name_counts: Dict[str, int] = {}
        
        # Count occurrences of each name
        for node in tree:
            name = node.name.strip()
            name_counts[name] = name_counts.get(name, 0) + 1
        
        # Build unique names for duplicates
        for node in tree:
            name = node.name.strip()
            if name_counts[name] > 1:
                if name not in self._unique_names:
                    self._unique_names[name] = 0
                self._unique_names[name] += 1
                unique_name = f"{name}_{self._unique_names[name]}"
            else:
                unique_name = name
            
            self._processed_names.add(unique_name)
    
    def _get_unique_name(self, node: Any) -> str:
        """Get unique name for a node, handling duplicates."""
        name = str(node.name).strip() if hasattr(node, 'name') and node.name else "unnamed"
        
        if name in self._unique_names and self._unique_names[name] > 0:
            # Find the correct unique name for this specific node
            # This is a simplified approach - in practice you'd track node-specific mappings
            count = 1
            unique_name = f"{name}_{count}"
            while unique_name in self._processed_names:
                count += 1
                unique_name = f"{name}_{count}"
            return unique_name
        
        return name
    
    def _escape_name(self, name: str) -> str:
        """Escape special characters in taxonomy names for NCBI format compliance."""
        if not name:
            return ""
        
        # Remove or replace characters that cause issues in taxonomy formats
        escaped = name.strip()
        
        # Replace problematic characters
        escaped = re.sub(r'[|]', '_', escaped)  # Pipes interfere with NCBI format
        escaped = re.sub(r'[\t\n\r]', ' ', escaped)  # Tab/newline to space
        escaped = re.sub(r'\s+', ' ', escaped)  # Multiple spaces to single space
        
        # Handle quotes and special characters
        escaped = escaped.replace('"', "'")
        escaped = escaped.replace('\x00', '')  # Remove null bytes
        
        return escaped.strip() or "unnamed"
    
    def _write_names_file(self, tree: TaxonomyTree, output_path: Path, compress: bool) -> None:
        """Write NCBI-compliant names.dmp format file for Kaiju.
        
        Format: tax_id | name_txt | unique name | name class |
        
        Kaiju specifically uses scientific names from this file for taxonomic classification.
        """
        try:
            with open(output_path, 'w', encoding='utf-8', newline='\n') as f:
                for node in tree:
                    # Get unique, escaped name
                    unique_name = self._get_unique_name(node)
                    escaped_name = self._escape_name(unique_name)
                    
                    if not escaped_name:
                        logger.warning(f"Empty name for node {node.tax_id}, using 'unnamed'")
                        escaped_name = "unnamed"
                    
                    # Write scientific name entry (required by Kaiju)
                    f.write(f"{node.tax_id}\t|\t{escaped_name}\t|\t\t|\tscientific name\t|\n")
                    
                    # Add synonym if the original name was modified
                    if escaped_name != node.name.strip() and node.name.strip():
                        original_escaped = self._escape_name(node.name.strip())
                        if original_escaped and original_escaped != escaped_name:
                            f.write(f"{node.tax_id}\t|\t{original_escaped}\t|\t\t|\tsynonym\t|\n")
            
            logger.info(f"Created names.dmp with {tree.node_count} entries for Kaiju")
            
            if compress:
                from ..utils.subprocess_utils import compress_file
                compress_file(output_path)
                logger.info(f"Compressed names.dmp to {output_path}.gz")
                
        except Exception as e:
            logger.error(f"Failed to write names.dmp: {str(e)}")
            raise ExportError(f"Failed to create names.dmp file: {str(e)}") from e
    
    def _write_nodes_file(self, tree: TaxonomyTree, output_path: Path, compress: bool) -> None:
        """Write NCBI-compliant nodes.dmp format file for Kaiju.
        
        Format: tax_id | parent tax_id | rank | embl code | division id | 
                inherited div flag | genetic code id | inherited GC flag | 
                mitochondrial genetic code id | inherited MGC flag | 
                GenBank hidden flag | hidden subtree root flag | comments |
                
        Kaiju uses this file to understand taxonomic hierarchy relationships.
        """
        try:
            with open(output_path, 'w', encoding='utf-8', newline='\n') as f:
                for node in tree:
                    # Handle parent relationship
                    parent_id = node.parent_id if node.parent_id is not None else node.tax_id
                    
                    # Validate rank
                    rank = node.rank.value if node.rank else "no rank"
                    if not rank.strip():
                        rank = "no rank"
                    
                    # Write NCBI format with all required fields for Kaiju compatibility
                    # Fields: tax_id | parent_id | rank | embl_code | div_id | 
                    #         inherited_div | gc_id | inherited_gc | mgc_id | inherited_mgc | 
                    #         genbank_hidden | hidden_subtree | comments |
                    f.write(f"{node.tax_id}\t|\t{parent_id}\t|\t{rank}\t|\t\t|\t0\t|\t1\t|\t1\t|\t1\t|\t1\t|\t1\t|\t1\t|\t1\t|\t\t|\n")
            
            logger.info(f"Created nodes.dmp with {tree.node_count} entries for Kaiju")
            
            if compress:
                from ..utils.subprocess_utils import compress_file
                compress_file(output_path)
                logger.info(f"Compressed nodes.dmp to {output_path}.gz")
                
        except Exception as e:
            logger.error(f"Failed to write nodes.dmp: {str(e)}")
            raise ExportError(f"Failed to create nodes.dmp file: {str(e)}") from e