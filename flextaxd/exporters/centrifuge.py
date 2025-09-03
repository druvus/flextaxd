"""Centrifuge format exporter."""

from typing import Optional, Dict, Any
from pathlib import Path

from .base import DirectoryBasedExporter
from ..core.models import TaxonomyTree
from ..core.exceptions import ExportError
from ..utils.logging_config import get_logger

logger = get_logger(__name__)


class CentrifugeExporter(DirectoryBasedExporter):
    """Exporter for Centrifuge taxonomy format."""

    @property
    def exporter_name(self) -> str:
        return "centrifuge"

    @property
    def file_extensions(self) -> list[str]:
        return [".dmp", ".tab"]

    def export(self, tree: TaxonomyTree, output_path: Path, **kwargs: Any) -> None:
        """Export taxonomy tree in Centrifuge format.

        Creates:
        - taxonomy/names.dmp: Taxonomic names file
        - taxonomy/nodes.dmp: Taxonomic nodes file
        - conversion_table.tab: Sequence ID to taxonomy ID mapping
        """
        self._validate_tree(tree)
        self._ensure_output_path(output_path)

        logger.info(
            f"Exporting {tree.node_count} nodes to Centrifuge format: {output_path}"
        )

        # Configuration options
        compress = kwargs.get("compress", False)
        include_genomes = kwargs.get("include_genomes", True)

        # Create taxonomy directory
        taxonomy_dir = output_path / "taxonomy"
        taxonomy_dir.mkdir(exist_ok=True)

        # Create taxonomy files
        names_path = taxonomy_dir / "names.dmp"
        nodes_path = taxonomy_dir / "nodes.dmp"

        self._write_names_file(tree, names_path, compress)
        self._write_nodes_file(tree, nodes_path, compress)

        # Create names.txt and nodes.txt files at root level for compatibility
        names_txt_path = output_path / "names.txt"
        nodes_txt_path = output_path / "nodes.txt"
        self._write_names_txt(tree, names_txt_path, compress)
        self._write_nodes_txt(tree, nodes_txt_path, compress)

        # Create conversion table if genomes are present
        if include_genomes and tree.genome_count > 0:
            conversion_path = output_path / "conversion_table.tab"
            self._write_conversion_table(tree, conversion_path, compress)
            logger.info(f"Created conversion table with {tree.genome_count} entries")

        logger.info(
            f"Centrifuge export completed: {taxonomy_dir}, {names_txt_path}, {nodes_txt_path}"
        )

    def _write_names_file(
        self, tree: TaxonomyTree, output_path: Path, compress: bool
    ) -> None:
        """Write NCBI names.dmp format file."""
        with open(output_path, "w") as f:
            for node in tree:
                f.write(f"{node.tax_id}\t|\t{node.name}\t|\t\t|\tscientific name\t|\n")

        if compress:
            from ..utils.subprocess_utils import compress_file

            compress_file(output_path)

    def _write_nodes_file(
        self, tree: TaxonomyTree, output_path: Path, compress: bool
    ) -> None:
        """Write NCBI nodes.dmp format file."""
        with open(output_path, "w") as f:
            for node in tree:
                parent_id = (
                    node.parent_id if node.parent_id is not None else node.tax_id
                )
                f.write(
                    f"{node.tax_id}\t|\t{parent_id}\t|\t{node.rank.value}\t|\t\t|\t0\t|\t1\t|\t1\t|\t1\t|\t1\t|\t1\t|\t1\t|\t1\t|\t\t|\n"
                )

        if compress:
            from ..utils.subprocess_utils import compress_file

            compress_file(output_path)

    def _write_names_txt(
        self, tree: TaxonomyTree, output_path: Path, compress: bool
    ) -> None:
        """Write simplified names.txt format file."""
        with open(output_path, "w") as f:
            for node in tree:
                # Simple tab-separated format: tax_id\tname
                f.write(f"{node.tax_id}\t{node.name}\n")

        if compress:
            from ..utils.subprocess_utils import compress_file

            compress_file(output_path)

    def _write_nodes_txt(
        self, tree: TaxonomyTree, output_path: Path, compress: bool
    ) -> None:
        """Write simplified nodes.txt format file."""
        with open(output_path, "w") as f:
            for node in tree:
                parent_id = (
                    node.parent_id if node.parent_id is not None else node.tax_id
                )
                f.write(f"{node.tax_id}\t{parent_id}\t{node.rank.value}\n")

        if compress:
            from ..utils.subprocess_utils import compress_file

            compress_file(output_path)

    def _write_conversion_table(
        self, tree: TaxonomyTree, output_path: Path, compress: bool
    ) -> None:
        """Write Centrifuge conversion table.

        Format: sequence_id <tab> taxonomy_id
        """
        with open(output_path, "w") as f:
            for node in tree:
                genomes = tree.get_genomes_for_node(node.tax_id)
                for genome in genomes:
                    # Map genome ID to taxonomy ID
                    f.write(f"{genome.genome_id}\t{node.tax_id}\n")

                    # Also map assembly accession if different
                    if (
                        genome.assembly_accession
                        and genome.assembly_accession != genome.genome_id
                    ):
                        f.write(f"{genome.assembly_accession}\t{node.tax_id}\n")

        if compress:
            from ..utils.subprocess_utils import compress_file

            compress_file(output_path)
