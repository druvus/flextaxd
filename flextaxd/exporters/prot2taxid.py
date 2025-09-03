"""Prot2Taxid format exporter for createtaxdb compatibility."""

from typing import Optional, Dict, Any, Union, IO, Callable
from pathlib import Path

from .base import FileBasedExporter
from ..core.models import TaxonomyTree
from ..core.exceptions import ExportError
from ..utils.logging_config import get_logger

logger = get_logger(__name__)


class Prot2TaxidExporter(FileBasedExporter):
    """Exporter for Prot2Taxid format used by createtaxdb pipeline.

    Creates tab-separated files mapping protein sequence IDs to taxonomy IDs.
    Format: sequence_id<TAB>taxid (with header)
    """

    @property
    def exporter_name(self) -> str:
        return "prot2taxid"

    @property
    def file_extensions(self) -> list[str]:
        return [".txt", ".tsv", ".gz"]

    def export(self, tree: TaxonomyTree, output_path: Path, **kwargs: Any) -> None:
        """Export taxonomy tree in Prot2Taxid format.

        Creates a tab-separated file with header:
        sequence_id	taxid
        """
        self._validate_tree(tree)
        self._ensure_output_path(output_path)

        logger.info(
            f"Exporting {tree.node_count} nodes to Prot2Taxid format: {output_path}"
        )

        # Configuration options
        compress = kwargs.get("compress", False)
        include_genomes = kwargs.get("include_genomes", True)
        sequence_filter = kwargs.get(
            "sequence_filter", "protein"
        )  # protein, nucleotide, or all

        if not include_genomes or tree.genome_count == 0:
            logger.warning("No genome information available for Prot2Taxid export")
            # Create empty file with header only
            self._write_empty_file(output_path, compress)
            return

        # Write prot2taxid file
        self._write_prot2taxid_file(tree, output_path, compress, sequence_filter)

        logger.info(f"Prot2Taxid export completed: {output_path}")

    def _write_empty_file(self, output_path: Path, compress: bool) -> None:
        """Write empty file with header only."""
        header = "sequence_id\ttaxid\n"
        open_func = self._get_open_function(output_path, compress)

        with open_func(output_path, "wt", encoding="utf-8") as f:
            f.write(header)

    def _write_prot2taxid_file(
        self,
        tree: TaxonomyTree,
        output_path: Path,
        compress: bool,
        sequence_filter: str,
    ) -> None:
        """Write prot2taxid mapping file."""
        open_func = self._get_open_function(output_path, compress)

        with open_func(output_path, "wt", encoding="utf-8") as f:
            # Write header
            f.write("sequence_id\ttaxid\n")

            entries_written = 0

            for node in tree:
                genomes = tree.get_genomes_for_node(node.tax_id)
                for genome in genomes:
                    # Filter by sequence type if specified
                    if self._should_include_sequence(genome, sequence_filter):
                        sequence_id = genome.genome_id
                        f.write(f"{sequence_id}\t{node.tax_id}\n")
                        entries_written += 1

                        # Also include assembly accession if different
                        if (
                            genome.assembly_accession
                            and genome.assembly_accession != genome.genome_id
                        ):
                            # Don't re-check filter since we already know this genome passes
                            f.write(f"{genome.assembly_accession}\t{node.tax_id}\n")
                            entries_written += 1

            logger.info(f"Wrote {entries_written} protein sequence mappings")

    def _should_include_sequence(self, genome: Any, sequence_filter: str) -> bool:
        """Determine if sequence should be included based on filter."""
        if sequence_filter == "all":
            return True

        # Get sequence type from genome
        seq_type = getattr(genome, "sequence_type", None)
        if seq_type is None:
            seq_type = "protein"  # Default for protein exporter
        seq_type = seq_type.lower()

        if sequence_filter == "protein":
            # Include only protein sequences
            return seq_type in ["protein", "proteome"]
        elif sequence_filter == "nucleotide":
            # Include only nucleotide sequences
            return seq_type in [
                "genome",
                "16s",
                "nucleotide",
                "dna",
                "rna",
            ] and seq_type not in ["protein", "proteome"]
        else:
            return True

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
