"""TSV format taxonomy parser."""

import re
from typing import Optional, Dict, Any, Set
from pathlib import Path

from .base import FileBasedParser
from ..core.models import TaxonomyTree, TaxonomyNode, TaxonomicRank
from ..core.exceptions import ParseError


class TSVTaxonomyParser(FileBasedParser):
    """Parser for Tab-Separated Values taxonomy files."""

    @property
    def parser_name(self) -> str:
        return "tsv"

    @property
    def supported_extensions(self) -> list[str]:
        return [".tsv", ".txt", ".tab"]

    def can_parse(self, file_path: Path) -> bool:
        """Check if this file appears to be a TSV taxonomy file."""
        if file_path.suffix.lower() not in self.supported_extensions:
            return False

        try:
            self._validate_file(file_path)

            # Read first few lines to check format
            with open(file_path, "r", encoding="utf-8") as f:
                lines = [f.readline().strip() for _ in range(3) if f.readable()]

            if not lines:
                return False

            # Check for tab-separated structure
            first_line = lines[0]
            if "\t" not in first_line:
                return False

            # Check for common parent/child headers
            columns = [col.strip().lower() for col in first_line.split("\t")]

            # Look for parent/child or similar column patterns
            has_parent_child = (
                ("parent" in columns and "child" in columns)
                or ("parent_name" in columns and "child_name" in columns)
                or ("parent_id" in columns and "child_id" in columns)
            )

            # If we have explicit parent/child headers, this is likely TSV format
            if has_parent_child:
                return True

            # For files without headers, check if it looks like simple parent-child data
            # But exclude GTDB format (which has genome IDs and semicolon taxonomy strings)
            if len(columns) >= 2 and len(lines) > 1:
                # Check second line (first data line) to see if it looks like GTDB
                second_line = lines[1] if len(lines) > 1 else first_line
                parts = second_line.split("\t")

                if len(parts) >= 2:
                    # If second column contains GTDB-style taxonomy (with d__, p__, etc.), skip it
                    if ";" in parts[1] and any(
                        prefix in parts[1]
                        for prefix in ["d__", "p__", "c__", "o__", "f__", "g__", "s__"]
                    ):
                        return False

                    # If first column looks like a GTDB genome ID, skip it
                    genome_id = parts[0]
                    if (
                        genome_id.startswith("GB_GC")
                        or genome_id.startswith("RS_GC")
                        or genome_id.startswith("UBA")
                        or "." in genome_id
                    ):
                        return False

                    # Otherwise, assume it's a simple TSV parent-child format
                    return True

            return False

        except Exception:
            return False

    def parse(self, file_path: Path, **kwargs: Any) -> TaxonomyTree:
        """Parse a TSV taxonomy file."""
        self._validate_file(file_path)

        tree = TaxonomyTree()
        node_name_to_id: Dict[str, int] = {}
        next_id = 1

        # Configuration options
        has_header = kwargs.get("has_header", True)
        parent_col = kwargs.get("parent_column", 0)
        child_col = kwargs.get("child_column", 1)
        id_col = kwargs.get("id_column", None)
        rank_col = kwargs.get("rank_column", None)

        lines = list(self._read_lines(file_path))
        if not lines:
            raise ParseError(f"File is empty: {file_path}")

        start_line = 1 if has_header else 0

        # Auto-detect column structure from header if present
        if has_header and lines:
            header_info = self._parse_header(lines[0])
            if header_info:
                parent_col = header_info.get(
                    "parent", header_info.get("parent_name", parent_col)
                )
                child_col = header_info.get(
                    "child", header_info.get("child_name", child_col)
                )
                if "id" in header_info or "tax_id" in header_info:
                    id_col = header_info.get("id", header_info.get("tax_id"))
                if "rank" in header_info:
                    rank_col = header_info.get("rank")

        # First pass: collect all unique names and assign IDs
        for line_num, line in enumerate(lines[start_line:], start=start_line + 1):
            if not line.strip() or line.startswith("#"):
                continue

            fields = line.split("\t")
            if len(fields) < 2:
                raise ParseError(
                    f"Line {line_num}: Expected at least 2 columns, got {len(fields)}"
                )

            try:
                parent_name = fields[parent_col].strip()
                child_name = fields[child_col].strip()

                # Assign IDs if not already assigned
                for name in [parent_name, child_name]:
                    if name and name not in node_name_to_id:
                        node_name_to_id[name] = next_id
                        next_id += 1

            except IndexError as e:
                raise ParseError(f"Line {line_num}: Column index error - {e}")

        # Second pass: create nodes, ensuring parents exist before children
        root_candidates: Set[str] = set()
        child_names: Set[str] = set()
        relationships = []

        # Collect all relationships
        for line_num, line in enumerate(lines[start_line:], start=start_line + 1):
            if not line.strip() or line.startswith("#"):
                continue

            fields = line.split("\t")
            parent_name = fields[parent_col].strip()
            child_name = fields[child_col].strip()

            if not parent_name or not child_name:
                continue

            parent_id = node_name_to_id[parent_name]
            child_id = node_name_to_id[child_name]

            # Determine rank if rank column is specified
            rank = TaxonomicRank.CUSTOM
            if rank_col is not None and rank_col < len(fields):
                rank_str = fields[rank_col].strip().lower()
                rank = self._parse_rank(rank_str)

            relationships.append(
                (parent_name, child_name, parent_id, child_id, rank, line_num)
            )
            child_names.add(child_name)

        # Create nodes in dependency order
        created_nodes = set()
        remaining_relationships = relationships[:]

        while remaining_relationships:
            progress_made = False

            for i, (
                parent_name,
                child_name,
                parent_id,
                child_id,
                rank,
                line_num,
            ) in enumerate(remaining_relationships):
                # Create parent node if it doesn't exist and isn't in relationships (it's a root)
                if parent_id not in tree and parent_name not in child_names:
                    parent_node = TaxonomyNode(
                        tax_id=parent_id,
                        name=parent_name,
                        rank=TaxonomicRank.CUSTOM,
                        parent_id=None,
                    )
                    tree.add_node(parent_node)
                    root_candidates.add(parent_name)
                    created_nodes.add(parent_id)

                # Try to create child node if parent exists
                if parent_id in tree and child_id not in tree:
                    child_node = TaxonomyNode(
                        tax_id=child_id, name=child_name, rank=rank, parent_id=parent_id
                    )
                    try:
                        tree.add_node(child_node)
                        created_nodes.add(child_id)
                        remaining_relationships.pop(i)
                        progress_made = True
                        break
                    except ValueError as e:
                        raise ParseError(
                            f"Line {line_num}: Error creating child node - {e}"
                        )

            if not progress_made:
                if remaining_relationships:
                    # Find missing parents
                    missing_parents = []
                    for (
                        parent_name,
                        child_name,
                        parent_id,
                        child_id,
                        rank,
                        line_num,
                    ) in remaining_relationships:
                        if parent_id not in tree:
                            missing_parents.append(f"{parent_name} (line {line_num})")
                    raise ParseError(
                        f"Cannot resolve dependencies. Missing parent nodes: {', '.join(missing_parents)}"
                    )
                break

        # Handle root node detection
        self._handle_root_nodes(tree, root_candidates, child_names, node_name_to_id)

        # Validate the resulting tree
        issues = tree.validate_tree()
        if issues:
            raise ParseError(f"Tree validation failed: {'; '.join(issues)}")

        return tree

    def _parse_rank(self, rank_str: str) -> TaxonomicRank:
        """Parse rank string to TaxonomicRank enum."""
        rank_str = rank_str.lower().strip()

        # Handle common variations
        rank_mapping = {
            "root": TaxonomicRank.ROOT,
            "superkingdom": TaxonomicRank.SUPERKINGDOM,
            "kingdom": TaxonomicRank.KINGDOM,
            "phylum": TaxonomicRank.PHYLUM,
            "class": TaxonomicRank.CLASS,
            "order": TaxonomicRank.ORDER,
            "family": TaxonomicRank.FAMILY,
            "genus": TaxonomicRank.GENUS,
            "species": TaxonomicRank.SPECIES,
            "subspecies": TaxonomicRank.SUBSPECIES,
            "strain": TaxonomicRank.STRAIN,
            # Handle variations
            "domain": TaxonomicRank.SUPERKINGDOM,
            "sub-species": TaxonomicRank.SUBSPECIES,
            "sub_species": TaxonomicRank.SUBSPECIES,
        }

        return rank_mapping.get(rank_str, TaxonomicRank.CUSTOM)

    def _handle_root_nodes(
        self,
        tree: TaxonomyTree,
        root_candidates: Set[str],
        child_names: Set[str],
        name_to_id: Dict[str, int],
    ) -> None:
        """Handle root node detection and creation."""
        # Find nodes that are parents but not children (potential roots)
        actual_roots = root_candidates - child_names

        if not actual_roots:
            raise ParseError("No root node found in taxonomy")

        if len(actual_roots) > 1:
            # Multiple roots - create a synthetic root
            synthetic_root = TaxonomyNode(
                tax_id=max(name_to_id.values()) + 1,
                name="root",
                rank=TaxonomicRank.ROOT,
                parent_id=None,
            )
            tree.add_node(synthetic_root)

            # Make all actual roots children of synthetic root
            for root_name in actual_roots:
                root_id = name_to_id[root_name]
                old_node = tree.get_node(root_id)
                if old_node:
                    # Remove and re-add with new parent
                    tree.remove_node(root_id, reassign_children=False)
                    new_root = TaxonomyNode(
                        tax_id=old_node.tax_id,
                        name=old_node.name,
                        rank=old_node.rank,
                        parent_id=synthetic_root.tax_id,
                    )
                    tree.add_node(new_root)
