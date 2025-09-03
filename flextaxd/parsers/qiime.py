"""QIIME/GTDB taxonomy format parser."""

import re
from typing import Optional, Dict, Any, List
from pathlib import Path

from .base import FileBasedParser
from ..core.models import TaxonomyTree, TaxonomyNode, TaxonomicRank
from ..core.exceptions import ParseError


class QIIMETaxonomyParser(FileBasedParser):
    """Parser for QIIME/GTDB taxonomy format files."""

    @property
    def parser_name(self) -> str:
        return "qiime"

    @property
    def supported_extensions(self) -> list[str]:
        return [".tsv", ".txt", ".taxonomy"]

    def can_parse(self, file_path: Path) -> bool:
        """Check if this appears to be QIIME/GTDB taxonomy format."""
        try:
            self._validate_file(file_path)

            # Read first few lines to check format
            with open(file_path, "r", encoding="utf-8") as f:
                lines = [f.readline().strip() for _ in range(5) if f.readable()]

            if not lines:
                return False

            # Look for semicolon-separated hierarchical taxonomy
            for line in lines:
                if not line or line.startswith("#"):
                    continue

                # Check for QIIME/GTDB format patterns
                if ";" in line and any(
                    prefix in line
                    for prefix in ["d__", "p__", "c__", "o__", "f__", "g__", "s__"]
                ):
                    return True

                # Also check for simpler semicolon-separated format
                if line.count(";") >= 2 and "\t" in line:
                    parts = line.split("\t")
                    if len(parts) >= 2 and ";" in parts[-1]:
                        return True

            return False

        except Exception:
            return False

    def parse(self, file_path: Path, **kwargs: Any) -> TaxonomyTree:
        """Parse QIIME/GTDB taxonomy file."""
        self._validate_file(file_path)

        tree = TaxonomyTree()
        next_tax_id = kwargs.get("taxid_base", 1)

        # Track name to tax_id mapping to avoid duplicates
        name_to_id: Dict[str, int] = {}

        lines = list(self._read_lines(file_path))
        if not lines:
            raise ParseError(f"File is empty: {file_path}")

        # Process each line
        for line_num, line in enumerate(lines, 1):
            if not line.strip() or line.startswith("#"):
                continue

            try:
                # Parse line - could be "ID\ttaxonomy" or just "taxonomy"
                parts = line.split("\t")
                if len(parts) >= 2:
                    taxonomy_string = parts[1]  # Second column is taxonomy
                else:
                    taxonomy_string = parts[0]  # Single column

                # Parse hierarchical taxonomy
                taxonomy_levels = self._parse_taxonomy_string(taxonomy_string)

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
                            parent_id=parent_id,
                        )
                        tree.add_node(node)

                    parent_id = current_id

            except Exception as e:
                raise ParseError(f"Error parsing line {line_num}: {e}")

        return tree

    def _parse_taxonomy_string(
        self, taxonomy_string: str
    ) -> List[tuple[str, TaxonomicRank]]:
        """Parse semicolon-separated taxonomy string."""
        taxonomy_string = taxonomy_string.strip()

        # Split by semicolon and clean up
        levels = [
            level.strip() for level in taxonomy_string.split(";") if level.strip()
        ]

        result = []
        for i, level in enumerate(levels):
            # Parse GTDB-style prefixes (d__, p__, c__, etc.)
            rank, name = self._parse_gtdb_level(level, i)

            if name:  # Skip empty levels
                result.append((name, rank))

        return result

    def _parse_gtdb_level(self, level: str, position: int) -> tuple[TaxonomicRank, str]:
        """Parse GTDB-style taxonomy level."""
        level = level.strip()

        # GTDB format uses prefixes like d__, p__, c__, o__, f__, g__, s__
        gtdb_prefixes = {
            "d__": TaxonomicRank.SUPERKINGDOM,  # Domain
            "p__": TaxonomicRank.PHYLUM,
            "c__": TaxonomicRank.CLASS,
            "o__": TaxonomicRank.ORDER,
            "f__": TaxonomicRank.FAMILY,
            "g__": TaxonomicRank.GENUS,
            "s__": TaxonomicRank.SPECIES,
        }

        # Check for GTDB prefix
        for prefix, rank in gtdb_prefixes.items():
            if level.startswith(prefix):
                name = level[len(prefix) :].strip()
                return rank, name

        # Fallback: guess rank based on position
        position_ranks = [
            TaxonomicRank.SUPERKINGDOM,  # 0
            TaxonomicRank.PHYLUM,  # 1
            TaxonomicRank.CLASS,  # 2
            TaxonomicRank.ORDER,  # 3
            TaxonomicRank.FAMILY,  # 4
            TaxonomicRank.GENUS,  # 5
            TaxonomicRank.SPECIES,  # 6
        ]

        rank = (
            position_ranks[position]
            if position < len(position_ranks)
            else TaxonomicRank.CUSTOM
        )

        return rank, level
