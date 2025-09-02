"""GTDB (Genome Taxonomy Database) format parser.

GTDB files come in several formats:
1. Standard taxonomy files (ar122_taxonomy_r*.tsv, bac120_taxonomy_r*.tsv):
   - 2 columns: genome_id, taxonomy_string
   - Example: GB_GCA_000005825.2    d__Bacteria;p__Firmicutes;c__Bacilli;...
   
2. GTDB-Tk summary files (*.bac120.summary.tsv, *.ar53.summary.tsv):
   - Multiple columns with 'classification' column containing taxonomy
   - Additional metadata like ANI, AF, closest genome, etc.
   
3. Tree mapping files (tree.mapping.tsv from GTDB-Tk):
   - Genome mappings for phylogenetic analysis
"""

import re
from typing import Optional, Dict, Any, List, Set
from pathlib import Path

from .base import FileBasedParser
from ..core.models import TaxonomyTree, TaxonomyNode, TaxonomicRank
from ..core.exceptions import ParseError, ValidationError
from ..utils.logging_config import get_logger

logger = get_logger(__name__)


class GTDBTaxonomyParser(FileBasedParser):
    """Parser for GTDB (Genome Taxonomy Database) taxonomy formats."""
    
    @property
    def parser_name(self) -> str:
        return "gtdb"
    
    @property
    def supported_extensions(self) -> list[str]:
        return [".tsv", ".txt", ".tsv.gz", ".txt.gz"]
    
    def can_parse(self, file_path: Path) -> bool:
        """Check if this appears to be GTDB taxonomy format."""
        try:
            self._validate_file(file_path)
            
            # Check filename patterns first - strong indicators
            filename = file_path.name.lower()
            
            # GTDB standard filenames
            gtdb_patterns = [
                r'^ar\d+_taxonomy_r\d+\.tsv$',      # ar122_taxonomy_r202.tsv
                r'^bac\d+_taxonomy_r\d+\.tsv$',     # bac120_taxonomy_r202.tsv  
                r'^.*\.ar\d+\.summary\.tsv$',       # *.ar53.summary.tsv
                r'^.*\.bac\d+\.summary\.tsv$',      # *.bac120.summary.tsv
                r'^tree\.mapping\.tsv$',            # tree.mapping.tsv
            ]
            
            for pattern in gtdb_patterns:
                if re.match(pattern, filename):
                    logger.debug(f"GTDB filename pattern matched: {pattern}")
                    return True
            
            # Content-based detection for non-standard filenames
            return self._check_content_format(file_path)
            
        except Exception as e:
            logger.debug(f"GTDB parser check failed for {file_path}: {e}")
            return False
    
    def _check_content_format(self, file_path: Path) -> bool:
        """Check file content for GTDB format patterns."""
        try:
            # Read first few lines to analyze format
            lines = []
            with open(file_path, 'r', encoding='utf-8') as f:
                for _ in range(10):
                    line = f.readline()
                    if not line:
                        break
                    lines.append(line.strip())
            
            if not lines:
                return False
            
            # Skip comments and empty lines
            content_lines = [line for line in lines if line and not line.startswith('#')]
            if not content_lines:
                return False
            
            header_line = content_lines[0]
            
            # Check for GTDB-Tk summary format (multi-column with specific headers)
            if self._is_gtdb_tk_summary(header_line, content_lines[1:]):
                return True
            
            # Check for standard GTDB taxonomy format (2-column)
            if self._is_standard_gtdb_taxonomy(content_lines):
                return True
            
            return False
            
        except Exception:
            return False
    
    def _is_gtdb_tk_summary(self, header_line: str, data_lines: List[str]) -> bool:
        """Check if this is GTDB-Tk summary format."""
        # GTDB-Tk summary files have specific column headers
        expected_headers = ['user_genome', 'classification', 'closest_genome_reference']
        header_lower = header_line.lower()
        
        # Must have at least 2 of the expected headers
        header_matches = sum(1 for h in expected_headers if h in header_lower)
        if header_matches < 2:
            return False
        
        # Check data lines for GTDB taxonomy strings in classification column
        for line in data_lines[:3]:  # Check first few data lines
            if not line or line.startswith('#'):
                continue
            
            parts = line.split('\t')
            if len(parts) < 2:
                continue
            
            # Look for GTDB taxonomy format in any column
            for part in parts:
                if self._has_gtdb_taxonomy_string(part):
                    return True
        
        return False
    
    def _is_standard_gtdb_taxonomy(self, lines: List[str]) -> bool:
        """Check if this is standard 2-column GTDB taxonomy format."""
        for line in lines[:5]:  # Check first few lines
            if not line or line.startswith('#'):
                continue
            
            parts = line.split('\t')
            if len(parts) != 2:
                continue  # Standard format should be exactly 2 columns
            
            genome_id, taxonomy = parts
            
            # Check genome ID format (GTDB uses specific patterns)
            if self._is_gtdb_genome_id(genome_id) and self._has_gtdb_taxonomy_string(taxonomy):
                return True
        
        return False
    
    def _is_gtdb_genome_id(self, genome_id: str) -> bool:
        """Check if this looks like a GTDB genome identifier."""
        # GTDB genome IDs follow patterns like:
        # GB_GCA_000005825.2, RS_GCF_000005825.2, UBA1234, etc.
        patterns = [
            r'^GB_GC[AF]_\d+\.\d+$',  # GenBank assemblies
            r'^RS_GC[AF]_\d+\.\d+$',  # RefSeq assemblies  
            r'^UBA\d+$',              # Uncultivated Bacterial/Archaeal genomes
        ]
        
        for pattern in patterns:
            if re.match(pattern, genome_id):
                return True
        
        # Also accept other reasonable genome ID formats
        if len(genome_id) >= 3 and not ' ' in genome_id and ('_' in genome_id or '.' in genome_id):
            return True
        
        return False
    
    def _has_gtdb_taxonomy_string(self, taxonomy: str) -> bool:
        """Check if string contains GTDB taxonomy format."""
        # GTDB uses specific prefixes: d__, p__, c__, o__, f__, g__, s__
        gtdb_prefixes = ['d__', 'p__', 'c__', 'o__', 'f__', 'g__', 's__']
        
        # Must have semicolons and at least one GTDB prefix
        if ';' not in taxonomy:
            return False
        
        # Check for GTDB prefixes
        prefix_count = sum(1 for prefix in gtdb_prefixes if prefix in taxonomy)
        return prefix_count >= 2  # At least domain + one other level
    
    def parse(self, file_path: Path, **kwargs: Any) -> TaxonomyTree:
        """Parse GTDB taxonomy file."""
        self._validate_file(file_path)
        
        tree = TaxonomyTree()
        next_tax_id = kwargs.get('taxid_base', 1)
        
        # Track name to tax_id mapping to avoid duplicates
        name_to_id: Dict[str, int] = {}
        processed_genomes: Set[str] = set()
        
        # Determine file format
        file_format = self._detect_file_format(file_path)
        logger.info(f"Detected GTDB format: {file_format}")
        
        lines = list(self._read_lines(file_path))
        if not lines:
            raise ParseError(f"File is empty: {file_path}")
        
        # Parse based on detected format
        if file_format == "gtdb_tk_summary":
            next_tax_id = self._parse_gtdb_tk_summary(tree, lines, name_to_id, processed_genomes, next_tax_id)
        elif file_format == "standard_taxonomy":
            next_tax_id = self._parse_standard_taxonomy(tree, lines, name_to_id, processed_genomes, next_tax_id)
        else:
            raise ParseError(f"Unsupported GTDB format in file: {file_path}")
        
        logger.info(f"Parsed GTDB file: {tree.node_count} nodes, {len(processed_genomes)} genomes")
        return tree
    
    def _detect_file_format(self, file_path: Path) -> str:
        """Detect specific GTDB file format."""
        filename = file_path.name.lower()
        
        # Check filename patterns
        if re.match(r'^.*\.ar\d+\.summary\.tsv$', filename) or re.match(r'^.*\.bac\d+\.summary\.tsv$', filename):
            return "gtdb_tk_summary"
        
        if re.match(r'^ar\d+_taxonomy_r\d+\.tsv$', filename) or re.match(r'^bac\d+_taxonomy_r\d+\.tsv$', filename):
            return "standard_taxonomy"
        
        # Content-based detection
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()
                if not first_line or first_line.startswith('#'):
                    first_line = f.readline().strip()
            
            if 'user_genome' in first_line.lower() and 'classification' in first_line.lower():
                return "gtdb_tk_summary"
            
            # Check if it's 2-column format
            parts = first_line.split('\t')
            if len(parts) == 2 and self._has_gtdb_taxonomy_string(parts[1]):
                return "standard_taxonomy"
            
        except Exception:
            pass
        
        return "unknown"
    
    def _parse_gtdb_tk_summary(self, tree: TaxonomyTree, lines: List[str], 
                              name_to_id: Dict[str, int], processed_genomes: Set[str], 
                              next_tax_id: int) -> int:
        """Parse GTDB-Tk summary file format."""
        # Find header line
        header_line = None
        data_start_idx = 0
        
        for i, line in enumerate(lines):
            if line and not line.startswith('#'):
                if 'user_genome' in line.lower() or 'classification' in line.lower():
                    header_line = line
                    data_start_idx = i + 1
                    break
                else:
                    # First non-comment line without headers - assume no header
                    data_start_idx = i
                    break
        
        if header_line:
            headers = [h.strip().lower() for h in header_line.split('\t')]
            try:
                classification_col = headers.index('classification')
            except ValueError:
                raise ParseError("GTDB-Tk summary file missing 'classification' column")
            
            try:
                genome_col = headers.index('user_genome')
            except ValueError:
                genome_col = 0  # Assume first column
        else:
            # No headers - assume classification in column 1, genome in column 0
            classification_col = 1
            genome_col = 0
        
        # Process data lines
        for line_num, line in enumerate(lines[data_start_idx:], data_start_idx + 1):
            if not line.strip() or line.startswith('#'):
                continue
            
            try:
                parts = line.split('\t')
                if len(parts) <= max(classification_col, genome_col):
                    continue
                
                genome_id = parts[genome_col] if genome_col < len(parts) else f"genome_{line_num}"
                taxonomy_string = parts[classification_col]
                
                if genome_id in processed_genomes:
                    continue
                processed_genomes.add(genome_id)
                
                # Parse taxonomy and add to tree
                next_tax_id = self._add_taxonomy_to_tree(
                    tree, taxonomy_string, name_to_id, next_tax_id, genome_id
                )
                
            except Exception as e:
                logger.warning(f"Error parsing GTDB-Tk summary line {line_num}: {e}")
        
        return next_tax_id
    
    def _parse_standard_taxonomy(self, tree: TaxonomyTree, lines: List[str],
                                name_to_id: Dict[str, int], processed_genomes: Set[str],
                                next_tax_id: int) -> int:
        """Parse standard 2-column GTDB taxonomy format."""
        for line_num, line in enumerate(lines, 1):
            if not line.strip() or line.startswith('#'):
                continue
            
            try:
                parts = line.split('\t')
                if len(parts) != 2:
                    continue
                
                genome_id, taxonomy_string = parts
                
                if genome_id in processed_genomes:
                    continue
                processed_genomes.add(genome_id)
                
                # Parse taxonomy and add to tree
                next_tax_id = self._add_taxonomy_to_tree(
                    tree, taxonomy_string, name_to_id, next_tax_id, genome_id
                )
                
            except Exception as e:
                logger.warning(f"Error parsing standard GTDB line {line_num}: {e}")
        
        return next_tax_id
    
    def _add_taxonomy_to_tree(self, tree: TaxonomyTree, taxonomy_string: str,
                             name_to_id: Dict[str, int], next_tax_id: int, 
                             genome_id: Optional[str] = None) -> int:
        """Parse taxonomy string and add nodes to tree."""
        # Parse GTDB hierarchical taxonomy
        taxonomy_levels = self._parse_gtdb_taxonomy_string(taxonomy_string)
        
        # Add nodes to tree hierarchically
        parent_id = None
        for level_name, rank in taxonomy_levels:
            if level_name in name_to_id:
                # Node already exists
                current_id = name_to_id[level_name]
            else:
                # Create new node
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
        
        return next_tax_id
    
    def _parse_gtdb_taxonomy_string(self, taxonomy_string: str) -> List[tuple[str, TaxonomicRank]]:
        """Parse GTDB semicolon-separated taxonomy string."""
        taxonomy_string = taxonomy_string.strip()
        
        # Split by semicolon and clean up
        levels = [level.strip() for level in taxonomy_string.split(';') if level.strip()]
        
        result = []
        for level in levels:
            rank, name = self._parse_gtdb_level(level)
            
            if name and name != "":  # Skip empty levels
                result.append((name, rank))
        
        return result
    
    def _parse_gtdb_level(self, level: str) -> tuple[TaxonomicRank, str]:
        """Parse GTDB-style taxonomy level."""
        level = level.strip()
        
        # GTDB format uses prefixes like d__, p__, c__, o__, f__, g__, s__
        gtdb_prefixes = {
            'd__': TaxonomicRank.SUPERKINGDOM,  # Domain
            'p__': TaxonomicRank.PHYLUM,
            'c__': TaxonomicRank.CLASS,
            'o__': TaxonomicRank.ORDER,
            'f__': TaxonomicRank.FAMILY,
            'g__': TaxonomicRank.GENUS,
            's__': TaxonomicRank.SPECIES,
        }
        
        # Check for GTDB prefix
        for prefix, rank in gtdb_prefixes.items():
            if level.startswith(prefix):
                name = level[len(prefix):].strip()
                # Handle empty species designations (s__)
                if not name:
                    return rank, ""
                return rank, name
        
        # If no prefix found, treat as custom rank
        return TaxonomicRank.CUSTOM, level