"""Ganon2 format exporter.

Ganon2 is the next generation metagenomics classifier with Hierarchical Interleaved Bloom Filters.
This exporter creates the custom database input files needed for Ganon2:

- input_files.txt: Tab-separated input file mapping for ganon build-custom
- taxonomy.tax: Taxonomy tree file (compatible with ganon2 --taxonomy format)
- seq-info.txt: Optional sequence information file

Note: Ganon2 creates its own index files (.hibf/.ibf and .tax) during database build.
This exporter only creates the input files needed for ganon build-custom command.
"""

from typing import Optional, Dict, Any, Set
from pathlib import Path
import re

from .base import DirectoryBasedExporter
from ..core.models import TaxonomyTree, TaxonomicRank
from ..core.exceptions import ExportError, ValidationError
from ..utils.logging_config import get_logger

logger = get_logger(__name__)


class Ganon2Exporter(DirectoryBasedExporter):
    """Exporter for Ganon2 custom database format with nf-core/createtaxdb compatibility.

    Creates Ganon2-compatible input files for custom database building.
    Includes robust validation, special character escaping, and unique name generation.

    Ganon2 Format Requirements:
    - input_files.txt: Tab-separated with file, target, node, [specialization, specialization_name]
    - taxonomy.tax: Taxonomy tree with target/node, parent, rank, name, genome_size
    - seq-info.txt: Optional sequence information (seqid, length, taxid, assembly_id)
    - All files must use tabs as separators
    - Compatible with ganon build-custom command

    The files produced by this exporter can be used with:
    - ganon build-custom for building custom databases
    - nf-core/createtaxdb pipeline for automated database construction
    - Direct use with Ganon2 classification workflows
    """

    def __init__(self) -> None:
        super().__init__()
        self._unique_names: Dict[str, int] = {}
        self._processed_names: Set[str] = set()
        self._node_name_mapping: Dict[int, str] = {}

    @property
    def exporter_name(self) -> str:
        return "ganon2"

    @property
    def file_extensions(self) -> list[str]:
        return [".txt", ".tax"]

    def export(self, tree: TaxonomyTree, output_path: Path, **kwargs: Any) -> None:
        """Export taxonomy tree in Ganon2 format.

        Creates Ganon2-compatible input files for custom database building:
        - input_files.txt: Input file mapping for ganon build-custom
        - taxonomy.tax: Taxonomy tree file
        - seq-info.txt: Optional sequence information (if genomes present)

        Args:
            tree: TaxonomyTree to export
            output_path: Output directory path
            **kwargs: Export options including compress, include_genomes, level
        """
        self._validate_tree(tree)
        self._ensure_output_path(output_path)

        logger.info(f"Starting Ganon2 export: {tree.node_count} nodes to {output_path}")

        # Parse configuration
        compress = kwargs.get("compress", False)
        include_genomes = kwargs.get("include_genomes", True)
        level = kwargs.get("level", "file")  # file, sequence, assembly, species, etc.

        try:
            # Reset state for new export
            self._unique_names.clear()
            self._processed_names.clear()
            self._node_name_mapping.clear()

            # Build unique names mapping for validation
            self._build_unique_names(tree)

            # Create Ganon2 input files
            input_files_path = output_path / "input_files.txt"
            taxonomy_tax_path = output_path / "taxonomy.tax"

            self._write_input_files(
                tree, input_files_path, compress, level, include_genomes
            )
            self._write_taxonomy_tax(tree, taxonomy_tax_path, compress)

            # Create seq-info file if genomes are present
            if include_genomes and tree.genome_count > 0:
                seq_info_path = output_path / "seq-info.txt"
                self._write_seq_info_file(tree, seq_info_path, compress)
                logger.info(f"Created seq-info file with {tree.genome_count} entries")

            logger.info(f"Ganon2 export completed successfully")
            logger.info(
                f"To build Ganon2 database, run: ganon build-custom --input-file {input_files_path}"
            )

        except Exception as e:
            logger.error(f"Ganon2 export failed: {str(e)}")
            raise ExportError(f"Failed to export Ganon2 format: {str(e)}") from e

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

            self._node_name_mapping[node.tax_id] = unique_name
            self._processed_names.add(unique_name)

    def _get_unique_name(self, node: Any) -> str:
        """Get unique name for a node, handling duplicates."""
        # Use the pre-computed unique name mapping
        default_name = (
            str(node.name).strip() if hasattr(node, "name") and node.name else "unnamed"
        )
        return self._node_name_mapping.get(node.tax_id, default_name)

    def _escape_name(self, name: str) -> str:
        """Escape special characters in taxonomy names for Ganon2 format compliance."""
        if not name:
            return ""

        # Remove or replace characters that cause issues in taxonomy formats
        escaped = name.strip()

        # Replace problematic characters for tab-separated format
        escaped = re.sub(r"[|]", "_", escaped)  # Pipes interfere with taxonomy formats
        escaped = re.sub(r"[\t\n\r]", " ", escaped)  # Tab/newline to space
        escaped = re.sub(r"\s+", " ", escaped)  # Multiple spaces to single space

        # Handle quotes and special characters
        escaped = escaped.replace('"', "'")
        escaped = escaped.replace("\x00", "")  # Remove null bytes

        return escaped.strip() or "unnamed"

    def _write_input_files(
        self,
        tree: TaxonomyTree,
        output_path: Path,
        compress: bool,
        level: str,
        include_genomes: bool,
    ) -> None:
        """Write Ganon2 input_files.txt format file.

        Format: file <tab> target <tab> node [<tab> specialization <tab> specialization_name]

        For Ganon2 custom database building with ganon build-custom.
        """
        try:
            entry_count = 0

            with open(output_path, "w", encoding="utf-8", newline="\n") as f:
                # Write header for clarity
                f.write("file\ttarget\tnode\tspecialization\tspecialization_name\n")

                for node in tree:
                    # Get escaped name
                    unique_name = self._get_unique_name(node)
                    escaped_name = self._escape_name(unique_name)

                    if not escaped_name:
                        escaped_name = "unnamed"

                    # Handle genomes if present and requested
                    if include_genomes and tree.genome_count > 0:
                        genomes = tree.get_genomes_for_node(node.tax_id)
                        for genome in genomes:
                            if not genome.genome_id:
                                logger.warning(
                                    f"Skipping genome with empty genome_id for tax_id {node.tax_id}"
                                )
                                continue

                            # Create file entry
                            file_path = self._get_genome_file_path(genome)
                            target = self._get_target_name(genome, node)
                            specialization = self._get_specialization(genome, level)
                            specialization_name = self._get_specialization_name(
                                genome, escaped_name
                            )

                            # Write entry
                            f.write(
                                f"{file_path}\t{target}\t{node.tax_id}\t{specialization}\t{specialization_name}\n"
                            )
                            entry_count += 1
                    else:
                        # Create placeholder entry for nodes without genomes
                        file_path = f"sequences/{node.tax_id}.fna"
                        target = f"target_{node.tax_id}"
                        specialization = f"spec_{node.tax_id}"
                        specialization_name = escaped_name

                        f.write(
                            f"{file_path}\t{target}\t{node.tax_id}\t{specialization}\t{specialization_name}\n"
                        )
                        entry_count += 1

            logger.info(
                f"Created input_files.txt with {entry_count} entries for Ganon2"
            )

            if compress:
                from ..utils.subprocess_utils import compress_file

                compress_file(output_path)
                logger.info(f"Compressed input_files.txt to {output_path}.gz")

        except Exception as e:
            logger.error(f"Failed to write input_files.txt: {str(e)}")
            raise ExportError(f"Failed to create input_files.txt file: {str(e)}") from e

    def _write_taxonomy_tax(
        self, tree: TaxonomyTree, output_path: Path, compress: bool
    ) -> None:
        """Write Ganon2 taxonomy.tax format file.

        Format: target/node <tab> parent <tab> rank <tab> name <tab> genome_size
        """
        try:
            with open(output_path, "w", encoding="utf-8", newline="\n") as f:
                # Write header for clarity
                f.write("target\tparent\trank\tname\tgenome_size\n")

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

                    # Estimate genome size
                    genome_size = self._estimate_genome_size(node, tree)

                    # Write entry (using tax_id as both target and node)
                    f.write(
                        f"{node.tax_id}\t{parent_id}\t{rank}\t{escaped_name}\t{genome_size}\n"
                    )

            logger.info(
                f"Created taxonomy.tax with {tree.node_count} entries for Ganon2"
            )

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
        """Write Ganon2 seq-info.txt file (optional sequence information).

        Format: seqid <tab> length <tab> taxid <tab> assembly_id
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

            logger.info(
                f"Created seq-info.txt with {genome_count} genome entries for Ganon2"
            )

            if compress:
                from ..utils.subprocess_utils import compress_file

                compress_file(output_path)
                logger.info(f"Compressed seq-info.txt to {output_path}.gz")

        except Exception as e:
            logger.error(f"Failed to write seq-info.txt: {str(e)}")
            raise ExportError(f"Failed to create seq-info.txt file: {str(e)}") from e

    def _get_genome_file_path(self, genome: Any) -> str:
        """Get file path for a genome."""
        if hasattr(genome, "file_path") and genome.file_path:
            return str(genome.file_path)

        # Generate default path
        if hasattr(genome, "genome_id") and genome.genome_id:
            return f"sequences/{genome.genome_id}.fna"

        return f"sequences/genome_{id(genome)}.fna"

    def _get_target_name(self, genome: Any, node: Any) -> str:
        """Get target name for a genome."""
        if hasattr(genome, "genome_id") and genome.genome_id:
            return f"target_{genome.genome_id}"

        return f"target_{node.tax_id}_{id(genome)}"

    def _get_specialization(self, genome: Any, level: str) -> str:
        """Get specialization for a genome based on level."""
        if hasattr(genome, "assembly_accession") and genome.assembly_accession:
            return f"spec_{genome.assembly_accession}"

        if hasattr(genome, "genome_id") and genome.genome_id:
            return f"spec_{genome.genome_id}"

        return f"spec_{level}_{id(genome)}"

    def _get_specialization_name(self, genome: Any, escaped_name: str) -> str:
        """Get specialization name for a genome."""
        if hasattr(genome, "description") and genome.description:
            return self._escape_name(genome.description)

        return escaped_name

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
                    file_size = file_path.stat().st_size
                    # Assume ~2 bytes per nucleotide (including headers, formatting)
                    estimated_length = file_size // 2
                    return max(estimated_length, 1000)  # At least 1kb
            except Exception:
                pass

        # Default bacterial genome size
        return 3_000_000

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

    def _estimate_genome_size(self, node: Any, tree: TaxonomyTree) -> int:
        """Estimate genome size for a taxonomic node."""
        # Try to get from genomes first
        if tree.genome_count > 0:
            genomes = tree.get_genomes_for_node(node.tax_id)
            if genomes:
                total_size = 0
                count = 0
                for genome in genomes:
                    size = self._get_sequence_length(genome)
                    total_size += size
                    count += 1
                if count > 0:
                    return total_size // count

        # Estimate based on taxonomic rank
        if hasattr(node, "rank") and node.rank:
            rank = node.rank.value.lower() if node.rank else "species"

            # Rough estimates by taxonomic level
            size_estimates = {
                "species": 3_000_000,  # 3 Mb (bacterial)
                "genus": 4_000_000,  # 4 Mb
                "family": 5_000_000,  # 5 Mb
                "order": 6_000_000,  # 6 Mb
                "class": 7_000_000,  # 7 Mb
                "phylum": 8_000_000,  # 8 Mb
                "superkingdom": 10_000_000,  # 10 Mb
                "kingdom": 10_000_000,  # 10 Mb
                "no rank": 3_000_000,  # Default
                "custom": 3_000_000,  # Default
            }

            return size_estimates.get(rank, 3_000_000)

        # Default estimate
        return int(3_000_000)
