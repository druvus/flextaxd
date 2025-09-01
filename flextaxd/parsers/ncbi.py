"""NCBI taxonomy dump format parser."""

import re
from typing import Optional, Dict, Any, Iterator, List, TypedDict
from pathlib import Path

from .base import DirectoryBasedParser
from ..core.models import TaxonomyTree, TaxonomyNode, TaxonomicRank
from ..core.exceptions import ParseError


class NodeData(TypedDict):
    tax_id: int
    name: str
    rank: TaxonomicRank
    parent_id: Optional[int]


class NCBITaxonomyParser(DirectoryBasedParser):
    """Parser for NCBI taxonomy dump files (names.dmp, nodes.dmp)."""
    
    @property
    def parser_name(self) -> str:
        return "ncbi"
    
    @property
    def supported_extensions(self) -> list[str]:
        return [".dmp"]
    
    def can_parse(self, file_path: Path) -> bool:
        """Check if this appears to be NCBI taxonomy dump format."""
        try:
            if not file_path.exists():
                return False
                
            if file_path.is_file():
                # Single file - check if it looks like a dump file
                return self._is_dump_file(file_path)
            elif file_path.is_dir():
                # Directory - look for names.dmp and nodes.dmp
                names_file = file_path / "names.dmp"
                nodes_file = file_path / "nodes.dmp"
                
                return (names_file.exists() and nodes_file.exists() and
                        self._is_dump_file(names_file) and self._is_dump_file(nodes_file))
            
            return False
            
        except Exception:
            return False
    
    def parse(self, file_path: Path, **kwargs: Any) -> TaxonomyTree:
        """Parse NCBI taxonomy dump files."""
        if file_path.is_file():
            # Single file - assume it's nodes.dmp and look for names.dmp
            if file_path.name == "names.dmp":
                names_file = file_path
                nodes_file = file_path.parent / "nodes.dmp"
            else:
                nodes_file = file_path
                names_file = file_path.parent / "names.dmp"
        else:
            # Directory containing dump files
            names_file = file_path / "names.dmp"
            nodes_file = file_path / "nodes.dmp"
        
        if not nodes_file.exists():
            raise ParseError(f"Required nodes.dmp file not found: {nodes_file}")
        
        # Names file is optional for basic tree structure
        names_dict = {}
        if names_file.exists():
            names_dict = self._parse_names_file(names_file)
        
        return self._parse_nodes_file(nodes_file, names_dict)
    
    def _is_dump_file(self, file_path: Path) -> bool:
        """Check if file looks like NCBI dump format."""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                # Check first few lines for dump format patterns
                for _ in range(5):
                    line = f.readline()
                    if not line:
                        break
                    
                    # NCBI dump format uses \t|\t as separator
                    if '\t|\t' in line and line.strip().endswith('\t|'):
                        return True
            
            return False
        except Exception:
            return False
    
    def _parse_names_file(self, names_file: Path) -> Dict[int, str]:
        """Parse names.dmp file and return tax_id -> name mapping."""
        names = {}
        
        try:
            with open(names_file, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    if not line.strip() or line.startswith('#'):
                        continue
                    
                    try:
                        # NCBI names format: tax_id | name | unique_name | name_class |
                        parts = line.split('\t|\t')
                        if len(parts) < 4:
                            continue
                        
                        tax_id = int(parts[0].strip())
                        name = parts[1].strip()
                        name_class = parts[3].strip().rstrip('\t|')
                        
                        # Prefer scientific names, but accept others if not available
                        if name_class == "scientific name" or tax_id not in names:
                            names[tax_id] = name
                            
                    except (ValueError, IndexError) as e:
                        raise ParseError(f"Error parsing names file line {line_num}: {e}")
        except (IOError, OSError) as e:
            raise ParseError(f"Cannot read names file {names_file}: {e}")
        
        return names
    
    def _parse_nodes_file(self, nodes_file: Path, names_dict: Dict[int, str]) -> TaxonomyTree:
        """Parse nodes.dmp file and build taxonomy tree."""
        tree = TaxonomyTree()
        
        # First pass: collect all nodes
        nodes_data: List[NodeData] = []
        with open(nodes_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                if not line.strip() or line.startswith('#'):
                    continue
                
                try:
                    # NCBI nodes format: tax_id | parent_tax_id | rank | embl_code | division_id | ...
                    parts = line.split('\t|\t')
                    if len(parts) < 3:
                        continue
                    
                    tax_id = int(parts[0].strip())
                    parent_tax_id = int(parts[1].strip())
                    rank_str = parts[2].strip()
                    
                    # Handle root nodes (parent == self)
                    parent_id = None if parent_tax_id == tax_id else parent_tax_id
                    
                    # Get name from names dict or use tax_id as fallback
                    name = names_dict.get(tax_id, f"taxid_{tax_id}")
                    
                    # Parse rank
                    rank = self._parse_rank(rank_str)
                    
                    nodes_data.append({
                        'tax_id': tax_id,
                        'name': name,
                        'rank': rank,
                        'parent_id': parent_id
                    })
                    
                except (ValueError, IndexError) as e:
                    raise ParseError(f"Error parsing nodes file line {line_num}: {e}")
        
        # Sort nodes to ensure parents are added before children
        nodes_data.sort(key=lambda x: (x['parent_id'] is None, x['tax_id']))
        
        # Second pass: add nodes to tree
        for node_data in nodes_data:
            try:
                node = TaxonomyNode(
                    tax_id=node_data['tax_id'],
                    name=node_data['name'],
                    rank=node_data['rank'],
                    parent_id=node_data['parent_id']
                )
                tree.add_node(node)
            except ValueError as e:
                # Skip problematic nodes but log the issue
                self.logger.warning(f"Skipping node {node_data['tax_id']}: {e}")
        
        return tree
    
    def _parse_rank(self, rank_str: str) -> TaxonomicRank:
        """Parse NCBI rank string to TaxonomicRank enum."""
        rank_str = rank_str.lower().strip()
        
        # NCBI rank mappings
        rank_mapping = {
            'superkingdom': TaxonomicRank.SUPERKINGDOM,
            'kingdom': TaxonomicRank.KINGDOM,
            'phylum': TaxonomicRank.PHYLUM,
            'class': TaxonomicRank.CLASS,
            'order': TaxonomicRank.ORDER,
            'family': TaxonomicRank.FAMILY,
            'genus': TaxonomicRank.GENUS,
            'species': TaxonomicRank.SPECIES,
            'subspecies': TaxonomicRank.SUBSPECIES,
            'strain': TaxonomicRank.STRAIN,
            # Handle NCBI-specific ranks
            'no rank': TaxonomicRank.CUSTOM,
            'varietas': TaxonomicRank.SUBSPECIES,
            'forma': TaxonomicRank.SUBSPECIES,
        }
        
        return rank_mapping.get(rank_str, TaxonomicRank.CUSTOM)