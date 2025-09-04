"""Accession2Taxid format exporter for createtaxdb compatibility."""

from typing import Optional, Dict, Any, Callable, IO
from pathlib import Path

from .base import FileBasedExporter
from .validation import require_export_validation
from ..core.models import TaxonomyTree
from ..core.exceptions import ExportError
from ..utils.logging_config import get_logger

logger = get_logger(__name__)


class Accession2TaxidExporter(FileBasedExporter):
    """Exporter for Accession2Taxid format used by createtaxdb pipeline.

    Creates tab-separated files mapping sequence accessions to taxonomy IDs.
    Format: accession<TAB>accession.version<TAB>taxid<TAB>gi
    """

    @property
    def exporter_name(self) -> str:
        return "accession2taxid"

    @property
    def file_extensions(self) -> list[str]:
        return [".txt", ".tsv", ".gz"]

    @require_export_validation("accession2taxid")
    def export(self, tree: TaxonomyTree, output_path: Path, **kwargs: Any) -> None:
        """Export taxonomy tree in Accession2Taxid format.

        Creates a tab-separated file with header:
        accession	accession.version	taxid	gi
        """
        self._validate_tree(tree)
        self._ensure_output_path(output_path)

        logger.info(
            f"Exporting {tree.node_count} nodes to Accession2Taxid format: {output_path}"
        )

        # Configuration options
        compress = kwargs.get("compress", False)
        include_genomes = kwargs.get("include_genomes", True)
        sequence_type = kwargs.get("sequence_type", None)

        if not include_genomes or tree.genome_count == 0:
            logger.warning("No genome information available for Accession2Taxid export")
            # Create empty file with header only
            self._write_empty_file(output_path, compress)
            return

        # Write accession2taxid file
        self._write_accession2taxid_file(tree, output_path, compress, sequence_type)

        logger.info(f"Accession2Taxid export completed: {output_path}")

    def _write_empty_file(self, output_path: Path, compress: bool) -> None:
        """Write empty file with header only."""
        header = "accession\taccession.version\ttaxid\tgi\n"

        if compress:
            import gzip

            with gzip.open(f"{output_path}.gz", "wt", encoding="utf-8") as f:
                f.write(header)
        else:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(header)

    def _write_accession2taxid_file(
        self,
        tree: TaxonomyTree,
        output_path: Path,
        compress: bool,
        sequence_type: Optional[str] = None,
    ) -> None:
        """Write accession2taxid mapping file."""
        open_func = self._get_open_function(output_path, compress)

        with open_func(output_path, "wt", encoding="utf-8") as f:
            # Write header
            f.write("accession\taccession.version\ttaxid\tgi\n")

            entries_written = 0

            for node in tree:
                genomes = tree.get_genomes_for_node(node.tax_id)
                for genome in genomes:
                    # Apply sequence type filter if specified
                    if (
                        sequence_type is not None
                        and genome.sequence_type != sequence_type
                    ):
                        continue

                    # Extract accession from genome ID
                    accession = self._extract_accession(genome.genome_id)
                    accession_version = genome.assembly_accession or genome.genome_id

                    # Use 0 as placeholder for GI (GenInfo Identifier) as it's legacy
                    gi = "0"

                    f.write(f"{accession}\t{accession_version}\t{node.tax_id}\t{gi}\n")
                    entries_written += 1

            logger.info(f"Wrote {entries_written} accession mappings")

    def _extract_accession(self, genome_id: str) -> str:
        """Extract base accession from genome ID.

        Examples:
        GCF_000005825.2 -> GCF_000005825
        GCA_000001405.38 -> GCA_000001405
        """
        # Handle common NCBI accession patterns
        if "." in genome_id and (
            genome_id.startswith("GCF_") or genome_id.startswith("GCA_")
        ):
            return genome_id.split(".")[0]

        # For other IDs, use as-is
        return genome_id

    def _get_open_function(
        self, output_path: Path, compress: bool
    ) -> Callable[..., Any]:
        """Get appropriate file opening function."""
        if compress:
            import gzip

            # Modify output path to add .gz extension
            output_path = Path(str(output_path) + ".gz")
            return lambda path, mode, **kwargs: gzip.open(path, mode, **kwargs)
        else:
            return open
