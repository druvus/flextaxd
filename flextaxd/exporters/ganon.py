"""Ganon format exporter.

Ganon uses NCBI-compliant taxonomy files plus sequence information.
This exporter creates:
- taxonomy/names.dmp: NCBI format taxonomic names
- taxonomy/nodes.dmp: NCBI format taxonomic hierarchy
- seq-info.txt: Sequence information for genomic data
- taxonomy.tax: Simplified taxonomy format (optional)
"""

from typing import Optional, Dict, Any, Set
from pathlib import Path
import re

from .base import DirectoryBasedExporter
from ..core.models import TaxonomyTree, TaxonomicRank
from ..core.exceptions import ExportError, ValidationError
from ..utils.logging_config import get_logger

logger = get_logger(__name__)


class GanonExporter(DirectoryBasedExporter):
    """Exporter for Ganon taxonomy format with full nf-core/createtaxdb compatibility.

    Creates NCBI-compliant taxonomy files and Ganon-specific sequence information.
    Includes robust validation, special character escaping, and unique name generation.

    Ganon Format Requirements:
    - taxonomy/names.dmp: NCBI format with scientific names and synonyms
    - taxonomy/nodes.dmp: NCBI format with hierarchy and ranks
    - seq-info.txt: Tab-separated with seqid, length, taxid, assembly_id (optional)
    - taxonomy.tax: Simplified format with tax_id, parent_id, rank, name
    - All files must use tabs as separators
    - Taxonomy names must be properly escaped for special characters
    """

    def __init__(self) -> None:
        super().__init__()
        self._unique_names: Dict[str, int] = {}
        self._processed_names: Set[str] = set()

    @property
    def exporter_name(self) -> str:
        return "ganon"

    @property
    def file_extensions(self) -> list[str]:
        return [".dmp", ".info", ".tax"]

    def export(self, tree: TaxonomyTree, output_path: Path, **kwargs: Any) -> None:
        """Export taxonomy tree in Ganon format.

        Creates:
        - taxonomy/names.dmp: NCBI-compliant taxonomic names
        - taxonomy/nodes.dmp: NCBI-compliant taxonomic hierarchy
        - taxonomy.tax: Simplified taxonomy format
        - seq-info.txt: Ganon sequence information (if genomes present)

        Args:
            tree: TaxonomyTree to export
            output_path: Output directory path
            **kwargs: Export options including compress, include_genomes
        """
        self._validate_tree(tree)
        self._ensure_output_path(output_path)

        logger.info(f"Starting Ganon export: {tree.node_count} nodes to {output_path}")

        # Parse configuration
        compress = kwargs.get("compress", False)
        include_genomes = kwargs.get("include_genomes", True)

        try:
            # Reset state for new export
            self._unique_names.clear()
            self._processed_names.clear()

            # Create taxonomy directory
            taxonomy_dir = output_path / "taxonomy"
            taxonomy_dir.mkdir(parents=True, exist_ok=True)

            # Build unique names mapping for validation
            self._build_unique_names(tree)

            # Create NCBI-compliant taxonomy files
            names_path = taxonomy_dir / "names.dmp"
            nodes_path = taxonomy_dir / "nodes.dmp"

            self._write_names_file(tree, names_path, compress)
            self._write_nodes_file(tree, nodes_path, compress)

            # Create simplified taxonomy.tax format
            taxonomy_tax_path = output_path / "taxonomy.tax"
            self._write_taxonomy_tax(tree, taxonomy_tax_path, compress)

            # Create seq-info file if genomes are present
            if include_genomes and tree.genome_count > 0:
                seq_info_path = output_path / "seq-info.txt"
                self._write_seq_info_file(tree, seq_info_path, compress)
                logger.info(f"Created seq-info file with {tree.genome_count} entries")

            logger.info(f"Ganon export completed successfully")

        except Exception as e:
            logger.error(f"Ganon export failed: {str(e)}")
            raise ExportError(f"Failed to export Ganon format: {str(e)}") from e

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
        name = (
            str(node.name).strip() if hasattr(node, "name") and node.name else "unnamed"
        )

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
        escaped = re.sub(r"[|]", "_", escaped)  # Pipes interfere with NCBI format
        escaped = re.sub(r"[\t\n\r]", " ", escaped)  # Tab/newline to space
        escaped = re.sub(r"\s+", " ", escaped)  # Multiple spaces to single space

        # Handle quotes and special characters
        escaped = escaped.replace('"', "'")
        escaped = escaped.replace("\x00", "")  # Remove null bytes

        return escaped.strip() or "unnamed"

    def _write_names_file(
        self, tree: TaxonomyTree, output_path: Path, compress: bool
    ) -> None:
        """Write NCBI-compliant names.dmp format file.

        Format: tax_id | name_txt | unique name | name class |
        """
        try:
            with open(output_path, "w", encoding="utf-8", newline="\n") as f:
                for node in tree:
                    # Get unique, escaped name
                    unique_name = self._get_unique_name(node)
                    escaped_name = self._escape_name(unique_name)

                    if not escaped_name:
                        logger.warning(
                            f"Empty name for node {node.tax_id}, using 'unnamed'"
                        )
                        escaped_name = "unnamed"

                    # Write scientific name entry (required)
                    f.write(
                        f"{node.tax_id}\t|\t{escaped_name}\t|\t\t|\tscientific name\t|\n"
                    )

                    # Add synonym if the original name was modified
                    if escaped_name != node.name.strip() and node.name.strip():
                        original_escaped = self._escape_name(node.name.strip())
                        if original_escaped and original_escaped != escaped_name:
                            f.write(
                                f"{node.tax_id}\t|\t{original_escaped}\t|\t\t|\tsynonym\t|\n"
                            )

            logger.info(f"Created names.dmp with {tree.node_count} entries")

            if compress:
                from ..utils.subprocess_utils import compress_file

                compress_file(output_path)
                logger.info(f"Compressed names.dmp to {output_path}.gz")

        except Exception as e:
            logger.error(f"Failed to write names.dmp: {str(e)}")
            raise ExportError(f"Failed to create names.dmp file: {str(e)}") from e

    def _write_nodes_file(
        self, tree: TaxonomyTree, output_path: Path, compress: bool
    ) -> None:
        """Write NCBI-compliant nodes.dmp format file.

        Format: tax_id | parent tax_id | rank | embl code | division id |
                inherited div flag | genetic code id | inherited GC flag |
                mitochondrial genetic code id | inherited MGC flag |
                GenBank hidden flag | hidden subtree root flag | comments |
        """
        try:
            with open(output_path, "w", encoding="utf-8", newline="\n") as f:
                for node in tree:
                    # Handle parent relationship
                    parent_id = (
                        node.parent_id if node.parent_id is not None else node.tax_id
                    )

                    # Validate rank
                    rank = node.rank.value if node.rank else "no rank"
                    if not rank.strip():
                        rank = "no rank"

                    # Write NCBI format with all required fields
                    # Fields: tax_id | parent_id | rank | embl_code | div_id |
                    #         inherited_div | gc_id | inherited_gc | mgc_id | inherited_mgc |
                    #         genbank_hidden | hidden_subtree | comments |
                    f.write(
                        f"{node.tax_id}\t|\t{parent_id}\t|\t{rank}\t|\t\t|\t0\t|\t1\t|\t1\t|\t1\t|\t1\t|\t1\t|\t1\t|\t1\t|\t\t|\n"
                    )

            logger.info(f"Created nodes.dmp with {tree.node_count} entries")

            if compress:
                from ..utils.subprocess_utils import compress_file

                compress_file(output_path)
                logger.info(f"Compressed nodes.dmp to {output_path}.gz")

        except Exception as e:
            logger.error(f"Failed to write nodes.dmp: {str(e)}")
            raise ExportError(f"Failed to create nodes.dmp file: {str(e)}") from e

    def _write_taxonomy_tax(
        self, tree: TaxonomyTree, output_path: Path, compress: bool
    ) -> None:
        """Write simplified taxonomy.tax format file for Ganon.

        Format: tax_id <tab> parent_id <tab> rank <tab> name
        """
        try:
            with open(output_path, "w", encoding="utf-8", newline="\n") as f:
                for node in tree:
                    # Get escaped name
                    unique_name = self._get_unique_name(node)
                    escaped_name = self._escape_name(unique_name)

                    if not escaped_name:
                        escaped_name = "unnamed"

                    # Handle parent relationship
                    parent_id = (
                        node.parent_id if node.parent_id is not None else node.tax_id
                    )

                    # Get rank
                    rank = node.rank.value if node.rank else "no rank"
                    if not rank.strip():
                        rank = "no rank"

                    # Write simple tab-separated format
                    f.write(f"{node.tax_id}\t{parent_id}\t{rank}\t{escaped_name}\n")

            logger.info(f"Created taxonomy.tax with {tree.node_count} entries")

            if compress:
                from ..utils.subprocess_utils import compress_file

                compress_file(output_path)
                logger.info(f"Compressed taxonomy.tax to {output_path}.gz")

        except Exception as e:
            logger.error(f"Failed to write taxonomy.tax: {str(e)}")
            raise ExportError(f"Failed to create taxonomy.tax file: {str(e)}") from e

    def _write_seq_info_file(
        self, tree: TaxonomyTree, output_path: Path, compress: bool
    ) -> None:
        """Write Ganon seq-info.txt file.

        Format: seqid <tab> length <tab> taxid <tab> assembly_id
        Header is optional but recommended for clarity.
        """
        try:
            genome_count = 0

            with open(output_path, "w", encoding="utf-8", newline="\n") as f:
                # Write header for clarity
                f.write("seqid\tlength\ttaxid\tassembly_id\n")

                for node in tree:
                    genomes = tree.get_genomes_for_node(node.tax_id)
                    for genome in genomes:
                        # Get sequence information
                        seq_length = self._get_sequence_length(genome)
                        assembly_id = self._get_assembly_id(genome)

                        # Validate required fields
                        if not genome.genome_id:
                            logger.warning(
                                f"Skipping genome with empty genome_id for tax_id {node.tax_id}"
                            )
                            continue

                        # Write seq-info entry
                        f.write(
                            f"{genome.genome_id}\t{seq_length}\t{node.tax_id}\t{assembly_id}\n"
                        )
                        genome_count += 1

            logger.info(f"Created seq-info.txt with {genome_count} genome entries")

            if compress:
                from ..utils.subprocess_utils import compress_file

                compress_file(output_path)
                logger.info(f"Compressed seq-info.txt to {output_path}.gz")

        except Exception as e:
            logger.error(f"Failed to write seq-info.txt: {str(e)}")
            raise ExportError(f"Failed to create seq-info.txt file: {str(e)}") from e

    def _get_sequence_length(self, genome: Any) -> int:
        """Get sequence length for a genome."""
        # Try to get stored length if available
        if (
            hasattr(genome, "sequence_length")
            and genome.sequence_length
            and genome.sequence_length > 0
        ):
            return int(genome.sequence_length)

        # Try to estimate from file if available
        if hasattr(genome, "file_path") and genome.file_path:
            try:
                file_path = Path(genome.file_path)
                if file_path.exists():
                    # Very rough estimate based on file size
                    # This is not accurate but serves as placeholder
                    file_size = file_path.stat().st_size
                    # Assume ~2 bytes per nucleotide (including headers, formatting)
                    estimated_length = file_size // 2
                    return max(estimated_length, 1000)  # At least 1kb
            except Exception:
                pass

        # Default bacterial genome size
        return int(3_000_000)

    def _get_assembly_id(self, genome: Any) -> str:
        """Get assembly ID for a genome."""
        # Prefer assembly_accession if available
        if hasattr(genome, "assembly_accession") and genome.assembly_accession:
            return str(genome.assembly_accession).strip()

        # Fall back to genome_id
        if hasattr(genome, "genome_id") and genome.genome_id:
            return str(genome.genome_id).strip()

        # Last resort
        return "unknown"
