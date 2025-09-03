"""Sylph format exporter.

Sylph uses custom sketched databases built from genome FASTA files.
This exporter creates the input files needed for Sylph database creation:

- genomes/: Directory containing FASTA files for each genome
- genome_list.txt: List of genome file paths for sylph sketch command
- taxonomy_info.txt: Taxonomy information mapping genomes to taxa

Sylph Database Creation Workflow:
1. Export genomes and metadata using this exporter
2. Run: sylph sketch genomes/*.fa.gz -o database -t 50 -c 200
3. Use resulting database.syldb file with sylph profile

Note: Sylph creates binary .syldb databases during sketching.
This exporter only creates the input files needed for sylph sketch command.
"""

from typing import Optional, Dict, Any, Set
from pathlib import Path
import re

from .base import DirectoryBasedExporter
from ..core.models import TaxonomyTree, TaxonomicRank, TaxonomyNode
from ..core.exceptions import ExportError, ValidationError
from ..utils.logging_config import get_logger

logger = get_logger(__name__)


class SylphExporter(DirectoryBasedExporter):
    """Exporter for Sylph database format with genome-based sketching.

    Creates input files for Sylph database creation using sylph sketch command.
    Includes genome files, taxonomy mapping, and configuration for optimal database building.

    Sylph Format Requirements:
    - genomes/: FASTA files for each genome (.fa, .fa.gz, .fasta, .fasta.gz)
    - genome_list.txt: File paths for sylph sketch -l command
    - taxonomy_info.txt: Tab-separated taxonomy mapping
    - sylph_config.txt: Recommended parameters for sylph sketch

    The files produced by this exporter can be used with:
    - sylph sketch command for database creation
    - Custom database building workflows
    - Metagenomics profiling pipelines
    """

    def __init__(self) -> None:
        super().__init__()
        self._unique_names: Dict[str, int] = {}
        self._processed_names: Set[str] = set()
        self._node_name_mapping: Dict[int, str] = {}

    @property
    def exporter_name(self) -> str:
        return "sylph"

    @property
    def file_extensions(self) -> list[str]:
        return [".fa", ".txt", ".gz"]

    def export(self, tree: TaxonomyTree, output_path: Path, **kwargs: Any) -> None:
        """Export taxonomy tree for Sylph database creation.

        Creates input files for sylph sketch command:
        - genomes/: FASTA files for each genome
        - genome_list.txt: File paths for sylph sketch
        - taxonomy_info.txt: Taxonomy mapping
        - sylph_config.txt: Recommended sketch parameters

        Args:
            tree: TaxonomyTree to export
            output_path: Output directory path
            **kwargs: Export options including compress, compression_level, include_genomes
        """
        self._validate_tree(tree)
        self._ensure_output_path(output_path)

        logger.info(f"Starting Sylph export: {tree.node_count} nodes to {output_path}")

        # Parse configuration
        compress = kwargs.get("compress", True)  # Default to compressed for Sylph
        compression_level = kwargs.get("compression_level", 200)  # Default -c 200
        include_genomes = kwargs.get("include_genomes", True)

        try:
            # Reset state for new export
            self._unique_names.clear()
            self._processed_names.clear()
            self._node_name_mapping.clear()

            # Create genomes directory
            genomes_dir = output_path / "genomes"
            genomes_dir.mkdir(parents=True, exist_ok=True)

            # Build unique names mapping
            self._build_unique_names(tree)

            # Create genome files and collect paths
            genome_paths = []
            if include_genomes and tree.genome_count > 0:
                genome_paths = self._write_genome_files(tree, genomes_dir, compress)
                logger.info(f"Created {len(genome_paths)} genome files")

            # Create genome list file for sylph sketch -l command
            genome_list_path = output_path / "genome_list.txt"
            self._write_genome_list(genome_paths, genome_list_path)

            # Create taxonomy information file
            taxonomy_info_path = output_path / "taxonomy_info.txt"
            self._write_taxonomy_info(tree, taxonomy_info_path)

            # Create Sylph configuration file
            config_path = output_path / "sylph_config.txt"
            self._write_sylph_config(config_path, compression_level, len(genome_paths))

            logger.info(f"Sylph export completed successfully")
            logger.info(
                f"To build Sylph database, run: sylph sketch -l {genome_list_path} -o database -t 50 -c {compression_level}"
            )

        except Exception as e:
            logger.error(f"Sylph export failed: {str(e)}")
            raise ExportError(f"Failed to export Sylph format: {str(e)}") from e

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

    def _get_unique_name(self, node: TaxonomyNode) -> str:
        """Get unique name for a node, handling duplicates."""
        # Use the pre-computed unique name mapping
        return self._node_name_mapping.get(node.tax_id, node.name.strip())

    def _escape_name(self, name: str) -> str:
        """Escape special characters in names for filename safety."""
        if not name:
            return ""

        # Replace problematic characters for filesystem compatibility
        escaped = name.strip()

        # Replace filesystem-problematic characters
        escaped = re.sub(r'[<>:"|?*]', "_", escaped)  # Windows forbidden chars
        escaped = re.sub(r"[/\\]", "_", escaped)  # Path separators
        escaped = re.sub(r"[\t\n\r]", "_", escaped)  # Whitespace chars
        escaped = re.sub(r"\s+", "_", escaped)  # Multiple spaces to single underscore
        escaped = re.sub(
            r"[^\w\-_\.]", "_", escaped
        )  # Non-word chars except dash, underscore, dot

        # Remove leading/trailing dots and underscores
        escaped = escaped.strip("._")

        return escaped or "unnamed"

    def _write_genome_files(
        self, tree: TaxonomyTree, genomes_dir: Path, compress: bool
    ) -> list[str]:
        """Write genome FASTA files and return list of file paths."""
        genome_paths = []

        for node in tree:
            genomes = tree.get_genomes_for_node(node.tax_id)
            for genome in genomes:
                if not genome.genome_id:
                    logger.warning(
                        f"Skipping genome with empty genome_id for tax_id {node.tax_id}"
                    )
                    continue

                # Generate safe filename
                safe_name = self._escape_name(genome.genome_id)
                if compress:
                    filename = f"{safe_name}.fa.gz"
                else:
                    filename = f"{safe_name}.fa"

                genome_file_path = genomes_dir / filename

                # Write genome file (placeholder - actual sequence data would be needed)
                self._write_genome_fasta(genome, genome_file_path, compress)

                # Add to paths list
                genome_paths.append(str(genome_file_path))

        return genome_paths

    def _write_genome_fasta(
        self, genome: Any, output_path: Path, compress: bool
    ) -> None:
        """Write a single genome FASTA file."""
        try:
            # This is a placeholder implementation
            # In practice, you'd read actual sequence data from genome.file_path

            if compress:
                import gzip

                with gzip.open(output_path, "wt", encoding="utf-8") as f:
                    f.write(f">{genome.genome_id}\n")
                    if hasattr(genome, "description") and genome.description:
                        f.write(f"# {genome.description}\n")
                    # Placeholder sequence - would be actual genome sequence
                    f.write("ATCGATCGATCGATCG\n")
            else:
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(f">{genome.genome_id}\n")
                    if hasattr(genome, "description") and genome.description:
                        f.write(f"# {genome.description}\n")
                    # Placeholder sequence - would be actual genome sequence
                    f.write("ATCGATCGATCGATCG\n")

        except Exception as e:
            logger.error(f"Failed to write genome file {output_path}: {str(e)}")
            raise ExportError(f"Failed to write genome FASTA file: {str(e)}") from e

    def _write_genome_list(self, genome_paths: list[str], output_path: Path) -> None:
        """Write genome list file for sylph sketch -l command."""
        try:
            with open(output_path, "w", encoding="utf-8", newline="\n") as f:
                for path in genome_paths:
                    f.write(f"{path}\n")

            logger.info(f"Created genome_list.txt with {len(genome_paths)} entries")

        except Exception as e:
            logger.error(f"Failed to write genome_list.txt: {str(e)}")
            raise ExportError(f"Failed to create genome_list.txt file: {str(e)}") from e

    def _write_taxonomy_info(self, tree: TaxonomyTree, output_path: Path) -> None:
        """Write taxonomy information file mapping genomes to taxonomic info."""
        try:
            with open(output_path, "w", encoding="utf-8", newline="\n") as f:
                # Write header
                f.write("genome_id\ttax_id\tspecies_name\trank\tlineage\n")

                for node in tree:
                    # Get escaped name
                    unique_name = self._get_unique_name(node)
                    escaped_name = self._escape_name(unique_name)

                    if not escaped_name:
                        escaped_name = "unnamed"

                    # Get rank
                    rank = node.rank.value if node.rank else "no rank"

                    # Build lineage
                    lineage = self._build_lineage(tree, node)

                    # Write entries for genomes
                    if tree.genome_count > 0:
                        genomes = tree.get_genomes_for_node(node.tax_id)
                        for genome in genomes:
                            if not genome.genome_id:
                                continue

                            f.write(
                                f"{genome.genome_id}\t{node.tax_id}\t{escaped_name}\t{rank}\t{lineage}\n"
                            )
                    else:
                        # Write placeholder entry for nodes without genomes
                        f.write(
                            f"placeholder_{node.tax_id}\t{node.tax_id}\t{escaped_name}\t{rank}\t{lineage}\n"
                        )

            logger.info(f"Created taxonomy_info.txt with taxonomy mappings")

        except Exception as e:
            logger.error(f"Failed to write taxonomy_info.txt: {str(e)}")
            raise ExportError(
                f"Failed to create taxonomy_info.txt file: {str(e)}"
            ) from e

    def _write_sylph_config(
        self, output_path: Path, compression_level: int, genome_count: int
    ) -> None:
        """Write Sylph configuration file with recommended parameters."""
        try:
            with open(output_path, "w", encoding="utf-8", newline="\n") as f:
                f.write("# Sylph Database Creation Configuration\n")
                f.write("# Generated by FlexTaxD Sylph Exporter\n\n")

                f.write("# Recommended sylph sketch command:\n")
                f.write(
                    f"# sylph sketch -l genome_list.txt -o database -t 50 -c {compression_level}\n\n"
                )

                f.write("# Parameters explanation:\n")
                f.write(
                    f"# -c {compression_level}: Compression parameter (higher = faster but less sensitive)\n"
                )
                f.write("# -t 50: Number of threads\n")
                f.write(
                    "# -o database: Output database prefix (creates database.syldb)\n\n"
                )

                f.write("# Database statistics:\n")
                f.write(f"# Total genomes: {genome_count}\n")
                f.write(f"# Recommended compression: {compression_level}\n")

                # Compression recommendations based on genome size/type
                if genome_count > 10000:
                    f.write("# Note: Large database - consider c=200 for speed\n")
                elif genome_count < 1000:
                    f.write("# Note: Small database - consider c=100 for sensitivity\n")

                f.write("\n# For viral genomes, consider lower compression (c=100)\n")
                f.write(
                    "# For dereplicated genomes, can use higher compression (c=300)\n"
                )

            logger.info(f"Created sylph_config.txt with recommended parameters")

        except Exception as e:
            logger.error(f"Failed to write sylph_config.txt: {str(e)}")
            raise ExportError(
                f"Failed to create sylph_config.txt file: {str(e)}"
            ) from e

    def _build_lineage(self, tree: TaxonomyTree, node: Any) -> str:
        """Build taxonomic lineage string for a node."""
        lineage_parts = []
        current_node = node

        # Traverse up the tree to build lineage
        while current_node is not None:
            unique_name = self._get_unique_name(current_node)
            escaped_name = self._escape_name(unique_name)
            if escaped_name and escaped_name != "root":
                lineage_parts.append(escaped_name)

            if (
                current_node.parent_id is None
                or current_node.parent_id == current_node.tax_id
            ):
                break

            current_node = tree.get_node(current_node.parent_id)

        # Reverse to get root-to-leaf order
        lineage_parts.reverse()
        return "; ".join(lineage_parts) if lineage_parts else "root"
