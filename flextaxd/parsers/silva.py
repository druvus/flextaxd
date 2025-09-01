"""SILVA taxonomy format parser."""

import re
from typing import Optional, Dict, Any, List
from pathlib import Path

from .base import FileBasedParser
from ..core.models import TaxonomyTree, TaxonomyNode, TaxonomicRank
from ..core.exceptions import ParseError


class SILVATaxonomyParser(FileBasedParser):
    """Parser for SILVA taxonomy format files."""
    
    @property
    def parser_name(self) -> str:
        return "silva"
    
    @property
    def supported_extensions(self) -> list[str]:
        return [".txt", ".tsv", ".silva"]
    
    def can_parse(self, file_path: Path) -> bool:
        """Check if this appears to be SILVA taxonomy format."""
        try:
            self._validate_file(file_path)
            
            # Read first few lines to check format
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = [f.readline().strip() for _ in range(10) if f.readable()]
            
            if not lines:
                return False
            
            # Look for SILVA-specific patterns
            silva_indicators = 0
            for line in lines:
                if not line or line.startswith('#'):
                    continue
                
                # SILVA often uses specific formatting
                if any(indicator in line.lower() for indicator in [
                    'bacteria;', 'archaea;', 'eukaryota;',
                    'domain:', 'phylum:', 'class:',
                ]):
                    silva_indicators += 1
                
                # Check for tab-separated ID and taxonomy
                if '\t' in line:
                    parts = line.split('\t')
                    if len(parts) >= 2 and ';' in parts[1]:
                        silva_indicators += 1
            
            return silva_indicators >= 2
            
        except Exception:
            return False
    
    def parse(self, file_path: Path, **kwargs: Any) -> TaxonomyTree:
        """Parse SILVA taxonomy file."""
        self._validate_file(file_path)
        
        tree = TaxonomyTree()
        next_tax_id = kwargs.get('taxid_base', 1)
        
        # Track name to tax_id mapping
        name_to_id: Dict[str, int] = {}
        
        lines = list(self._read_lines(file_path))
        if not lines:
            raise ParseError(f"File is empty: {file_path}")
        
        # Process each line
        for line_num, line in enumerate(lines, 1):
            if not line.strip() or line.startswith('#'):
                continue
            
            try:
                # Parse line format (usually ID\ttaxonomy or just taxonomy)
                parts = line.split('\t')
                if len(parts) >= 2:
                    taxonomy_string = parts[1]  # Second column
                else:
                    taxonomy_string = parts[0]  # Single column
                
                # Parse SILVA taxonomy
                taxonomy_levels = self._parse_silva_taxonomy(taxonomy_string)
                
                # Add nodes to tree hierarchically
                parent_id = None
                for level_name, rank in taxonomy_levels:
                    if level_name in name_to_id:
                        current_id = name_to_id[level_name]
                    else:
                        current_id = next_tax_id
                        next_tax_id += 1
                        name_to_id[level_name] = current_id
                        
                        node = TaxonomyNode(
                            tax_id=current_id,
                            name=level_name,
                            rank=rank,
                            parent_id=parent_id
                        )
                        tree.add_node(node)
                    
                    parent_id = current_id
                    
            except Exception as e:
                raise ParseError(f"Error parsing line {line_num}: {e}")
        
        return tree
    
    def _parse_silva_taxonomy(self, taxonomy_string: str) -> List[tuple[str, TaxonomicRank]]:
        """Parse SILVA taxonomy string."""
        taxonomy_string = taxonomy_string.strip()
        
        # SILVA format can vary, but often uses semicolons
        if ';' in taxonomy_string:
            levels = [level.strip() for level in taxonomy_string.split(';') if level.strip()]
        else:
            # Sometimes uses other separators
            levels = [taxonomy_string]
        
        result = []
        for i, level in enumerate(levels):
            rank, name = self._parse_silva_level(level, i)
            if name:
                result.append((name, rank))
        
        return result
    
    def _parse_silva_level(self, level: str, position: int) -> tuple[TaxonomicRank, str]:
        """Parse SILVA taxonomy level."""
        level = level.strip()
        
        # Remove common SILVA annotations
        level = re.sub(r'\s+\([^)]+\)$', '', level)  # Remove trailing parentheses
        level = re.sub(r'^[A-Z][a-z]*:', '', level)  # Remove rank prefixes like "Domain:"
        
        # SILVA rank detection based on common patterns
        level_lower = level.lower()
        
        if any(domain in level_lower for domain in ['bacteria', 'archaea', 'eukaryota']):
            rank = TaxonomicRank.SUPERKINGDOM
        elif position == 0:
            rank = TaxonomicRank.SUPERKINGDOM
        elif position == 1:
            rank = TaxonomicRank.PHYLUM
        elif position == 2:
            rank = TaxonomicRank.CLASS
        elif position == 3:
            rank = TaxonomicRank.ORDER
        elif position == 4:
            rank = TaxonomicRank.FAMILY
        elif position == 5:
            rank = TaxonomicRank.GENUS
        elif position == 6:
            rank = TaxonomicRank.SPECIES
        else:
            rank = TaxonomicRank.CUSTOM
        
        return rank, level