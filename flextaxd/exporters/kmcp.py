"""KMCP format exporter for nf-core createtaxdb compatibility."""

from typing import Optional, Dict, Any, Callable, Union, IO
from pathlib import Path

from .base import FileBasedExporter
from ..core.models import TaxonomyTree
from ..core.exceptions import ExportError
from ..utils.logging_config import get_logger

logger = get_logger(__name__)


class KMCPExporter(FileBasedExporter):
    """Exporter for KMCP taxonomy mapping format.

    Creates tab-separated files mapping reference identifiers to taxonomy IDs.
    Format: reference_id<TAB>taxid

    KMCP (K-mer-based Metagenomic Classification and Profiling) requires:
    1. Reference-to-TaxID mapping file (this exporter)
    2. NCBI taxonomy dump files (names.dmp, nodes.dmp) - use NCBIExporter
    3. Reference genome files (FASTA format)
    """

    @property
    def exporter_name(self) -> str:
        return "kmcp"

    @property
    def file_extensions(self) -> list[str]:
        return [".txt", ".tsv", ".map", ".gz"]

    def export(self, tree: TaxonomyTree, output_path: Path, **kwargs: Any) -> None:
        """Export taxonomy tree in KMCP mapping format.

        Creates a simple two-column tab-separated file:
        reference_id	taxid

        Args:
            tree: Taxonomy tree to export
            output_path: Output file path
            **kwargs: Additional options:
                - compress: Whether to gzip compress output
                - include_genomes: Whether to include genome mappings
                - sequence_type: Filter by sequence type (genome, protein, rna)
                - header: Whether to include header row (default: False for KMCP compatibility)
        """
        self._validate_tree(tree)
        self._ensure_output_path(output_path)

        logger.info(
            f"Exporting {tree.node_count} nodes to KMCP mapping format: {output_path}"
        )

        # Configuration options
        compress = kwargs.get("compress", False)
        include_genomes = kwargs.get("include_genomes", True)
        sequence_type = kwargs.get("sequence_type", None)
        include_header = kwargs.get(
            "header", False
        )  # KMCP typically doesn't use headers

        if not include_genomes or tree.genome_count == 0:
            logger.warning("No genome information available for KMCP mapping export")
            # Create empty file (with header if requested)
            self._write_empty_file(output_path, compress, include_header)
            return

        # Write KMCP mapping file
        self._write_kmcp_mapping_file(
            tree, output_path, compress, sequence_type, include_header
        )

        logger.info(f"KMCP mapping export completed: {output_path}")

    def _write_empty_file(
        self, output_path: Path, compress: bool, include_header: bool
    ) -> None:
        """Write empty file with optional header."""
        header = "reference_id\ttaxid\n" if include_header else ""

        open_func = self._get_open_function(compress)
        actual_path = self._get_output_path(output_path, compress)

        with open_func(actual_path, "wt", encoding="utf-8") as f:
            if header:
                f.write(header)

    def _write_kmcp_mapping_file(
        self,
        tree: TaxonomyTree,
        output_path: Path,
        compress: bool,
        sequence_type: Optional[str] = None,
        include_header: bool = False,
    ) -> None:
        """Write KMCP reference-to-taxid mapping file."""
        open_func = self._get_open_function(compress)
        actual_path = self._get_output_path(output_path, compress)

        with open_func(actual_path, "wt", encoding="utf-8") as f:
            # Write header if requested
            if include_header:
                f.write("reference_id\ttaxid\n")

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

                    # Extract reference identifier from genome
                    reference_id = self._extract_reference_id(genome)

                    # Write mapping: reference_id<TAB>taxid
                    f.write(f"{reference_id}\t{node.tax_id}\n")
                    entries_written += 1

            logger.info(f"Wrote {entries_written} reference-to-taxid mappings")

    def _extract_reference_id(self, genome: Any) -> str:
        """Extract reference identifier from genome info.

        KMCP expects reference identifiers that match the genome file names.
        Priority:
        1. Assembly accession (GCF_/GCA_ format)
        2. Genome ID
        3. Any available identifier

        Args:
            genome: GenomeInfo object

        Returns:
            Reference identifier string
        """
        # Priority 1: Assembly accession (RefSeq/GenBank format)
        if hasattr(genome, "assembly_accession") and genome.assembly_accession:
            return str(genome.assembly_accession)

        # Priority 2: Genome ID
        if hasattr(genome, "genome_id") and genome.genome_id:
            return str(genome.genome_id)

        # Priority 3: Fallback to any available ID
        if hasattr(genome, "sequence_id") and genome.sequence_id:
            return str(genome.sequence_id)

        # Last resort: use tax_id as reference (not ideal but functional)
        if hasattr(genome, "tax_id"):
            logger.warning(
                f"No suitable reference ID found for genome in taxid {genome.tax_id}, using tax_id as reference"
            )
            return str(genome.tax_id)

        # Absolute fallback
        return "unknown"

    def _get_open_function(self, compress: bool) -> Callable[..., Any]:
        """Get appropriate file opening function."""
        if compress:
            import gzip

            return gzip.open
        else:
            return open

    def _get_output_path(self, output_path: Path, compress: bool) -> Path:
        """Get actual output path with compression extension if needed."""
        if compress and not str(output_path).endswith(".gz"):
            return Path(str(output_path) + ".gz")
        return output_path
