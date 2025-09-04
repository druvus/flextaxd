"""Metabuli format exporter for taxonomic classification."""

from typing import Optional, Dict, Any, Set, List
from pathlib import Path

from .base import DirectoryBasedExporter
from .validation import require_export_validation
from ..core.models import TaxonomyTree
from ..core.exceptions import ExportError
from ..utils.logging_config import get_logger

logger = get_logger(__name__)


class MetabuliExporter(DirectoryBasedExporter):
    """Exporter for Metabuli taxonomy format.

    Metabuli requires NCBI-style taxonomy dump files (names.dmp, nodes.dmp, merged.dmp)
    and accession2taxid mapping files for sequence-to-taxonomy assignment.

    Reference genome filenames must include assembly accession for proper mapping.
    Supports both GTDB and NCBI taxonomy frameworks.
    """

    @property
    def exporter_name(self) -> str:
        return "metabuli"

    @property
    def file_extensions(self) -> list[str]:
        return [".dmp", ".tsv", ".txt"]

    @require_export_validation("metabuli")
    def export(self, tree: TaxonomyTree, output_path: Path, **kwargs: Any) -> None:
        """Export taxonomy tree in Metabuli format.

        Creates:
        - names.dmp: Taxonomic names file (NCBI format)
        - nodes.dmp: Taxonomic nodes file (NCBI format)
        - merged.dmp: Historical taxonomy changes (optional)
        - accession2taxid.txt: Sequence ID to taxonomy ID mapping

        Args:
            tree: Taxonomy tree to export
            output_path: Output directory path
            **kwargs: Additional options
                - include_merged: Include merged.dmp file (default: False)
                - compress: Compress output files (default: False)
                - include_genomes: Include genome mappings (default: True)
        """
        self._validate_tree(tree)
        self._ensure_output_path(output_path)

        logger.info(
            f"Exporting {tree.node_count} nodes to Metabuli format: {output_path}"
        )

        # Configuration options
        include_merged = kwargs.get("include_merged", False)
        compress = kwargs.get("compress", False)
        include_genomes = kwargs.get("include_genomes", True)

        # Create required taxonomy files
        names_path = output_path / "names.dmp"
        nodes_path = output_path / "nodes.dmp"

        self._write_names_file(tree, names_path, compress)
        self._write_nodes_file(tree, nodes_path, compress)

        # Create optional merged.dmp file
        if include_merged:
            merged_path = output_path / "merged.dmp"
            self._write_merged_file(tree, merged_path, compress)
            logger.info(f"Created merged.dmp file: {merged_path}")

        # Create accession2taxid mapping if genomes are present
        if include_genomes and tree.genome_count > 0:
            accession_path = output_path / "accession2taxid.txt"
            self._write_accession_mapping(tree, accession_path, compress)
            logger.info(
                f"Created accession2taxid mapping with {tree.genome_count} genome entries"
            )

        logger.info(f"Metabuli export completed: {names_path}, {nodes_path}")

    def _write_names_file(
        self, tree: TaxonomyTree, output_path: Path, compress: bool
    ) -> None:
        """Write NCBI names.dmp format file."""
        # Track names for unique name generation
        name_counts: Dict[str, int] = {}
        name_entries = []

        # First pass: collect all names and count duplicates
        for node in tree:
            escaped_name = self._escape_name(node.name)
            name_counts[escaped_name] = name_counts.get(escaped_name, 0) + 1
            name_entries.append((node.tax_id, escaped_name))

        # Second pass: write with proper unique names
        with open(output_path, "w", encoding="utf-8", newline="\n") as f:
            used_unique_names: Set[str] = set()
            for tax_id, escaped_name in name_entries:
                # Generate unique name if duplicates exist
                unique_name = self._generate_unique_name(
                    escaped_name, tax_id, name_counts, used_unique_names
                )

                # NCBI names.dmp format: tax_id | name | unique name | name class |
                f.write(
                    f"{tax_id}\t|\t{escaped_name}\t|\t{unique_name}\t|\tscientific name\t|\n"
                )

        if compress:
            from ..utils.subprocess_utils import compress_file

            compress_file(output_path)

    def _escape_name(self, name: str) -> str:
        """Escape special characters in taxonomic names for NCBI format."""
        if not name:
            return "unnamed"

        # Replace tabs with spaces (critical for format integrity)
        escaped = name.replace("\t", " ")

        # Replace pipes with semicolons (pipes are field separators)
        escaped = escaped.replace("|", ";")

        # Replace newlines with spaces
        escaped = escaped.replace("\n", " ").replace("\r", " ")

        # Trim whitespace and collapse multiple spaces
        escaped = " ".join(escaped.split())

        # Ensure name is not empty after cleaning
        return escaped if escaped else "unnamed"

    def _generate_unique_name(
        self,
        name: str,
        tax_id: int,
        name_counts: Dict[str, int],
        used_unique_names: Set[str],
    ) -> str:
        """Generate unique name for taxa when duplicates exist."""
        # If name is unique, no unique name needed (empty field)
        if name_counts.get(name, 0) <= 1:
            return ""

        # Generate unique name: name + tax_id
        unique_name = f"{name} <{tax_id}>"

        # Ensure this unique name hasn't been used
        counter = 1
        original_unique = unique_name
        while unique_name in used_unique_names:
            unique_name = f"{original_unique}_{counter}"
            counter += 1

        used_unique_names.add(unique_name)
        return unique_name

    def _write_nodes_file(
        self, tree: TaxonomyTree, output_path: Path, compress: bool
    ) -> None:
        """Write NCBI nodes.dmp format file."""
        with open(output_path, "w", encoding="utf-8", newline="\n") as f:
            for node in tree:
                # Parent ID validation and handling
                parent_id = self._validate_parent_id(node, tree)

                # Rank validation - ensure valid NCBI rank
                rank = self._validate_rank(node.rank)

                # NCBI nodes.dmp format (12 fields):
                # tax_id | parent_tax_id | rank | embl_code | division_id | inherited_div_flag |
                # genetic_code_id | inherited_gc_flag | mitochondrial_genetic_code_id |
                # inherited_mgc_flag | genbank_hidden_flag | hidden_subtree_root_flag | comments
                fields = [
                    str(node.tax_id),  # tax_id
                    str(parent_id),  # parent_tax_id
                    rank,  # rank
                    "",  # embl_code (empty)
                    "0",  # division_id (0 = unassigned)
                    "1",  # inherited_div_flag
                    "1",  # genetic_code_id (1 = standard genetic code)
                    "1",  # inherited_gc_flag
                    "1",  # mitochondrial_genetic_code_id (1 = standard)
                    "1",  # inherited_mgc_flag
                    "0",  # genbank_hidden_flag (0 = visible)
                    "0",  # hidden_subtree_root_flag (0 = not hidden)
                    "",  # comments (empty)
                ]

                # Write with proper NCBI format: field | field | field |
                f.write("\t|\t".join(fields) + "\t|\n")

        if compress:
            from ..utils.subprocess_utils import compress_file

            compress_file(output_path)

    def _validate_parent_id(self, node: Any, tree: TaxonomyTree) -> int:
        """Validate and return proper parent ID for node."""
        # Root nodes (tax_id=1) should have themselves as parent
        if node.tax_id == 1:
            return 1

        # If no parent specified, this is a root node - use itself as parent
        if node.parent_id is None:
            return int(node.tax_id)

        # Validate parent exists in tree
        if tree.get_node(node.parent_id) is None:
            logger.warning(
                f"Node {node.tax_id} references non-existent parent {node.parent_id}, using self as parent"
            )
            return int(node.tax_id)

        return int(node.parent_id)

    def _validate_rank(self, rank: Any) -> str:
        """Validate taxonomic rank for NCBI format."""
        if rank is None:
            return "no rank"

        # Convert rank to string and normalize
        rank_str = str(rank).lower()
        if hasattr(rank, "value"):
            rank_str = rank.value.lower()

        # Map common rank variations to NCBI standard ranks
        rank_mapping = {
            "custom": "no rank",
            "root": "no rank",
            "domain": "superkingdom",
            "kingdom": "kingdom",
            "phylum": "phylum",
            "class": "class",
            "order": "order",
            "family": "family",
            "genus": "genus",
            "species": "species",
            "strain": "no rank",
            "subspecies": "subspecies",
            "varietas": "varietas",
            "forma": "forma",
        }

        return rank_mapping.get(rank_str, rank_str)

    def _write_merged_file(
        self, tree: TaxonomyTree, output_path: Path, compress: bool
    ) -> None:
        """Write merged.dmp file for historical taxonomy changes.

        This creates an empty merged.dmp file since FlexTaxD doesn't track
        historical taxonomy changes. Real merged.dmp files would contain:
        old_tax_id | new_tax_id |
        """
        with open(output_path, "w", encoding="utf-8", newline="\n") as f:
            # Write header comment
            f.write("# merged.dmp - historical taxonomy ID changes\n")
            f.write("# Format: old_tax_id | new_tax_id |\n")
            # Empty file for now - no historical changes tracked

        if compress:
            from ..utils.subprocess_utils import compress_file

            compress_file(output_path)

    def _write_accession_mapping(
        self, tree: TaxonomyTree, output_path: Path, compress: bool
    ) -> None:
        """Write accession2taxid mapping file for Metabuli.

        Metabuli requires sequence accessions to be mapped to taxonomy IDs.
        Reference genome filenames must include assembly accession.
        """
        sequences_mapped = 0

        with open(output_path, "w", encoding="utf-8", newline="\n") as f:
            # Write header
            f.write("accession\taccession.version\ttaxid\tgi\n")

            for node in tree:
                genomes = tree.get_genomes_for_node(node.tax_id)
                for genome in genomes:
                    # Map genome ID directly
                    accession = genome.genome_id
                    f.write(f"{accession}\t{accession}\t{node.tax_id}\t0\n")
                    sequences_mapped += 1

                    # If assembly accession is available and different, also map that
                    if (
                        genome.assembly_accession
                        and genome.assembly_accession != genome.genome_id
                    ):
                        acc = genome.assembly_accession
                        f.write(f"{acc}\t{acc}\t{node.tax_id}\t0\n")
                        sequences_mapped += 1

                    # Extract additional accessions from genome ID if it contains multiple identifiers
                    additional_accessions = self._extract_additional_accessions(
                        genome.genome_id
                    )
                    for acc in additional_accessions:
                        f.write(f"{acc}\t{acc}\t{node.tax_id}\t0\n")
                        sequences_mapped += 1

        logger.info(
            f"Created accession2taxid mapping with {sequences_mapped} accession entries"
        )

        if compress:
            from ..utils.subprocess_utils import compress_file

            compress_file(output_path)

    def _extract_additional_accessions(self, genome_id: str) -> List[str]:
        """Extract additional accessions from genome ID.

        Some genome IDs may contain multiple accessions separated by delimiters.
        This method extracts them for comprehensive mapping.
        """
        accessions: List[str] = []

        # Handle common separators in genome IDs
        separators = ["|", ";", ",", " "]
        parts = [genome_id]

        for sep in separators:
            new_parts: List[str] = []
            for part in parts:
                new_parts.extend(part.split(sep))
            parts = new_parts

        # Filter for valid accession-like strings
        for part in parts:
            part = part.strip()
            if part and part != genome_id and len(part) > 3:
                # Basic validation for accession format (letters + numbers)
                if any(c.isalpha() for c in part) and any(c.isdigit() for c in part):
                    accessions.append(part)

        return accessions

    def validate_export(self, output_path: Path) -> Dict[str, Any]:
        """Validate the created Metabuli taxonomy files."""
        try:
            validation_results: Dict[str, Any] = {
                "valid": True,
                "files_created": [],
                "errors": [],
                "format": "Metabuli taxonomy",
            }

            # Check required files
            required_files = ["names.dmp", "nodes.dmp"]
            optional_files = ["merged.dmp", "accession2taxid.txt"]

            for filename in required_files:
                file_path = output_path / filename
                if file_path.exists():
                    validation_results["files_created"].append(filename)
                else:
                    validation_results["valid"] = False
                    validation_results["errors"].append(
                        f"Required file missing: {filename}"
                    )

            for filename in optional_files:
                file_path = output_path / filename
                if file_path.exists():
                    validation_results["files_created"].append(filename)

            # Basic format validation for names.dmp
            names_file = output_path / "names.dmp"
            if names_file.exists():
                try:
                    with open(names_file, "r") as f:
                        first_line = f.readline().strip()
                        if not first_line or first_line.count("\t|\t") < 3:
                            validation_results["errors"].append(
                                "names.dmp: Invalid format"
                            )
                except Exception as e:
                    validation_results["errors"].append(f"names.dmp: Read error - {e}")

            # Basic format validation for nodes.dmp
            nodes_file = output_path / "nodes.dmp"
            if nodes_file.exists():
                try:
                    with open(nodes_file, "r") as f:
                        first_line = f.readline().strip()
                        if not first_line or first_line.count("\t|\t") < 11:
                            validation_results["errors"].append(
                                "nodes.dmp: Invalid format"
                            )
                except Exception as e:
                    validation_results["errors"].append(f"nodes.dmp: Read error - {e}")

            if validation_results["errors"]:
                validation_results["valid"] = False

            return validation_results

        except Exception as e:
            return {"valid": False, "error": str(e)}
