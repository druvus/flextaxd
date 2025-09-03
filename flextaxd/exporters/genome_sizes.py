"""Genome Sizes format exporter for createtaxdb compatibility."""

from typing import Optional, Dict, Any, Union, IO, Callable
from pathlib import Path

from .base import FileBasedExporter
from ..core.models import TaxonomyTree
from ..core.exceptions import ExportError
from ..utils.logging_config import get_logger

logger = get_logger(__name__)


class GenomeSizesExporter(FileBasedExporter):
    """Exporter for Genome Sizes format used by createtaxdb pipeline.

    Creates tab-separated files with genome size information mapped to taxonomy IDs.
    Format: taxid<TAB>assembly_accession<TAB>species_taxid<TAB>organism_name<TAB>assembly_level<TAB>genome_size
    """

    @property
    def exporter_name(self) -> str:
        return "genome_sizes"

    @property
    def file_extensions(self) -> list[str]:
        return [".txt", ".tsv", ".gz"]

    def export(self, tree: TaxonomyTree, output_path: Path, **kwargs: Any) -> None:
        """Export taxonomy tree in Genome Sizes format.

        Creates a tab-separated file with header:
        taxid	assembly_accession	species_taxid	organism_name	assembly_level	genome_size
        """
        self._validate_tree(tree)
        self._ensure_output_path(output_path)

        logger.info(
            f"Exporting {tree.node_count} nodes to Genome Sizes format: {output_path}"
        )

        # Configuration options
        compress = kwargs.get("compress", False)
        include_genomes = kwargs.get("include_genomes", True)
        default_size = kwargs.get(
            "default_genome_size", 0
        )  # Default genome size if not available

        if not include_genomes or tree.genome_count == 0:
            logger.warning("No genome information available for Genome Sizes export")
            # Create empty file with header only
            self._write_empty_file(output_path, compress)
            return

        # Write genome sizes file
        self._write_genome_sizes_file(tree, output_path, compress, default_size)

        logger.info(f"Genome Sizes export completed: {output_path}")

    def _write_empty_file(self, output_path: Path, compress: bool) -> None:
        """Write empty file with header only."""
        header = "taxid\tassembly_accession\tspecies_taxid\torganism_name\tassembly_level\tgenome_size\n"
        open_func = self._get_open_function(output_path, compress)

        with open_func(output_path, "wt", encoding="utf-8") as f:
            f.write(header)

    def _write_genome_sizes_file(
        self, tree: TaxonomyTree, output_path: Path, compress: bool, default_size: int
    ) -> None:
        """Write genome sizes mapping file."""
        open_func = self._get_open_function(output_path, compress)

        with open_func(output_path, "wt", encoding="utf-8") as f:
            # Write header
            f.write(
                "taxid\tassembly_accession\tspecies_taxid\torganism_name\tassembly_level\tgenome_size\n"
            )

            entries_written = 0

            for node in tree:
                genomes = tree.get_genomes_for_node(node.tax_id)
                for genome in genomes:
                    # Extract information for each column
                    taxid = node.tax_id
                    assembly_accession = genome.assembly_accession or genome.genome_id
                    species_taxid = self._get_species_taxid(node, tree)
                    organism_name = self._get_organism_name(node, tree)
                    assembly_level = self._get_assembly_level(genome)
                    genome_size = self._get_genome_size(genome, default_size)

                    f.write(
                        f"{taxid}\t{assembly_accession}\t{species_taxid}\t{organism_name}\t{assembly_level}\t{genome_size}\n"
                    )
                    entries_written += 1

            logger.info(f"Wrote {entries_written} genome size entries")

    def _get_species_taxid(self, node: Any, tree: TaxonomyTree) -> int:
        """Get the species-level taxonomy ID for a node."""
        # Walk up the tree to find species-level node
        current = node
        while current:
            if current.rank.value.lower() == "species":
                return int(current.tax_id)
            # Get parent
            if current.parent_id:
                current = tree.get_node(current.parent_id)
            else:
                break

        # If no species found, return the node's own tax_id
        return int(node.tax_id)

    def _get_organism_name(self, node: Any, tree: TaxonomyTree) -> str:
        """Get the organism name (preferably species name)."""
        # Try to get species-level name
        species_taxid = self._get_species_taxid(node, tree)
        if species_taxid != node.tax_id:
            species_node = tree.get_node(species_taxid)
            if species_node:
                return species_node.name

        # Fall back to current node name
        return str(node.name).replace(
            "\t", " "
        )  # Clean any tabs that might break format

    def _get_assembly_level(self, genome: Any) -> str:
        """Get assembly level information."""
        # Check if genome has assembly level info
        if hasattr(genome, "assembly_level"):
            return str(genome.assembly_level)

        # Infer from genome ID or assembly accession
        genome_id = genome.assembly_accession or genome.genome_id

        if genome_id.startswith("GCF_"):
            return "Complete Genome"  # RefSeq complete genomes
        elif genome_id.startswith("GCA_"):
            return "Scaffold"  # GenBank assemblies are often scaffolds
        else:
            return "Contig"  # Default for unknown

    def _get_genome_size(self, genome: Any, default_size: int) -> int:
        """Get genome size in base pairs."""
        # Check if genome has size info
        if hasattr(genome, "genome_size") and genome.genome_size:
            return int(genome.genome_size)

        # Check for sequence length
        if hasattr(genome, "sequence_length") and genome.sequence_length:
            return int(genome.sequence_length)

        # Check file path and try to estimate from file size (very rough approximation)
        if hasattr(genome, "file_path") and genome.file_path:
            try:
                file_path = Path(genome.file_path)
                if file_path.exists():
                    file_size = file_path.stat().st_size
                    # Very rough estimate: FASTA files are ~50% overhead (headers, newlines)
                    # So actual sequence is roughly half the file size
                    estimated_size = max(file_size // 2, default_size)
                    return estimated_size
            except:
                pass

        # Return default size
        return default_size

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
