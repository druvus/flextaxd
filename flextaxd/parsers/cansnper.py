"""CanSNPer taxonomy format parser."""

import re
from typing import Optional, Dict, Any, List, Set
from pathlib import Path

from .base import FileBasedParser
from ..core.models import TaxonomyTree, TaxonomyNode, TaxonomicRank
from ..core.exceptions import ParseError


class CanSNPerTaxonomyParser(FileBasedParser):
    """Parser for CanSNPer taxonomy format files."""
    
    @property
    def parser_name(self) -> str:
        return "cansnper"
    
    @property
    def supported_extensions(self) -> list[str]:
        return [".txt", ".tsv", ".tree"]
    
    def can_parse(self, file_path: Path) -> bool:
        """Check if this appears to be CanSNPer format."""
        try:
            self._validate_file(file_path)
            
            # Read first few lines to check format
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = [f.readline().strip() for _ in range(10) if f.readable()]
            
            if not lines:
                return False
            
            # Look for CanSNPer-specific patterns
            cansnper_indicators = 0
            for line in lines:
                if not line or line.startswith('#'):
                    continue
                
                # CanSNPer often uses specific formatting with dots for hierarchy
                if '.' in line and any(char.isdigit() for char in line):
                    cansnper_indicators += 1
                
                # Look for CanSNPer-style node names (often numerical or coded)
                if re.search(r'^\d+\.', line) or re.search(r'[A-Z]+\.\d+', line):
                    cansnper_indicators += 1
                
                # Tab-separated with specific patterns
                if '\t' in line:
                    parts = line.split('\t')
                    if len(parts) >= 2 and any('.' in part for part in parts):
                        cansnper_indicators += 1
            
            return cansnper_indicators >= 2
            
        except Exception:
            return False
    
    def parse(self, file_path: Path, **kwargs: Any) -> TaxonomyTree:
        """Parse CanSNPer taxonomy file."""
        self._validate_file(file_path)
        
        tree = TaxonomyTree()
        next_tax_id = kwargs.get('taxid_base', 1)
        
        # Track name to tax_id mapping
        name_to_id: Dict[str, int] = {}
        
        # Configuration
        has_header = kwargs.get('has_header', True)
        parent_col = kwargs.get('parent_column', 0)
        child_col = kwargs.get('child_column', 1)
        
        lines = list(self._read_lines(file_path))
        if not lines:
            raise ParseError(f"File is empty: {file_path}")
        
        start_line = 1 if has_header else 0
        
        # First pass: collect all unique names
        for line in lines[start_line:]:
            if not line.strip() or line.startswith('#'):
                continue
            
            parts = line.split('\t')
            if len(parts) < 2:
                continue
            
            parent_name = parts[parent_col].strip()
            child_name = parts[child_col].strip()
            
            for name in [parent_name, child_name]:
                if name and name not in name_to_id:
                    name_to_id[name] = next_tax_id
                    next_tax_id += 1
        
        # Second pass: build tree
        root_candidates: Set[str] = set()
        child_names: Set[str] = set()
        
        for line_num, line in enumerate(lines[start_line:], start=start_line + 1):
            if not line.strip() or line.startswith('#'):
                continue
            
            parts = line.split('\t')
            if len(parts) < 2:
                continue
            
            parent_name = parts[parent_col].strip()
            child_name = parts[child_col].strip()
            
            if not parent_name or not child_name:
                continue
            
            parent_id = name_to_id[parent_name]
            child_id = name_to_id[child_name]
            
            # Determine ranks based on CanSNPer patterns
            parent_rank = self._guess_cansnper_rank(parent_name)
            child_rank = self._guess_cansnper_rank(child_name)
            
            # Create parent node if not exists
            if parent_id not in tree:
                parent_node = TaxonomyNode(
                    tax_id=parent_id,
                    name=parent_name,
                    rank=parent_rank,
                    parent_id=None
                )
                tree.add_node(parent_node)
                root_candidates.add(parent_name)
            
            # Create child node
            if child_id not in tree:
                child_node = TaxonomyNode(
                    tax_id=child_id,
                    name=child_name,
                    rank=child_rank,
                    parent_id=parent_id
                )
                tree.add_node(child_node)
                child_names.add(child_name)
        
        # Handle root nodes
        self._handle_cansnper_roots(tree, root_candidates, child_names, name_to_id)
        
        return tree
    
    def _guess_cansnper_rank(self, name: str) -> TaxonomicRank:
        """Guess taxonomic rank from CanSNPer node name patterns."""
        name_lower = name.lower()
        
        # CanSNPer-specific patterns
        if re.match(r'^\d+$', name):
            # Pure numbers are often higher level groups
            return TaxonomicRank.GENUS
        elif re.match(r'^\d+\.\d+$', name):
            # Decimal notation often indicates species/subspecies
            return TaxonomicRank.SPECIES
        elif re.match(r'^\d+\.\d+\.\d+', name):
            # More specific decimal notation
            return TaxonomicRank.SUBSPECIES
        elif re.match(r'^[A-Z]+\.\d+', name):
            # Letter-number combinations
            return TaxonomicRank.STRAIN
        elif any(term in name_lower for term in ['subsp', 'strain', 'isolate']):
            return TaxonomicRank.STRAIN
        elif any(term in name_lower for term in ['species', 'sp.']):
            return TaxonomicRank.SPECIES
        elif len(name.split('.')) > 1:
            # Hierarchical notation
            levels = len(name.split('.'))
            if levels >= 3:
                return TaxonomicRank.STRAIN
            elif levels == 2:
                return TaxonomicRank.SPECIES
            else:
                return TaxonomicRank.GENUS
        
        return TaxonomicRank.CUSTOM
    
    def _handle_cansnper_roots(
        self, 
        tree: TaxonomyTree, 
        root_candidates: Set[str], 
        child_names: Set[str],
        name_to_id: Dict[str, int]
    ) -> None:
        """Handle root node detection for CanSNPer trees."""
        actual_roots = root_candidates - child_names
        
        if not actual_roots:
            raise ParseError("No root node found in CanSNPer taxonomy")
        
        if len(actual_roots) > 1:
            # Create synthetic root
            root_id = max(name_to_id.values()) + 1
            synthetic_root = TaxonomyNode(
                tax_id=root_id,
                name="root",
                rank=TaxonomicRank.ROOT,
                parent_id=None
            )
            tree.add_node(synthetic_root)
            
            # Make all actual roots children of synthetic root
            for root_name in actual_roots:
                root_node_id = name_to_id[root_name]
                old_node = tree.get_node(root_node_id)
                if old_node:
                    tree.remove_node(root_node_id, reassign_children=False)
                    new_root = TaxonomyNode(
                        tax_id=old_node.tax_id,
                        name=old_node.name,
                        rank=old_node.rank,
                        parent_id=root_id
                    )
                    tree.add_node(new_root)