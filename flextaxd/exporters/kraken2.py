"""Kraken2/KrakenUniq format exporter."""

from typing import Optional, Dict, Any, Set
from pathlib import Path

from .base import DirectoryBasedExporter
from .validation import require_export_validation
from ..core.models import TaxonomyTree
from ..core.exceptions import ExportError
from ..utils.logging_config import get_logger

logger = get_logger(__name__)


class Kraken2Exporter(DirectoryBasedExporter):
    """Exporter for Kraken2/KrakenUniq taxonomy format."""

    @property
    def exporter_name(self) -> str:
        return "kraken2"

    @property
    def file_extensions(self) -> list[str]:
        return [".dmp", ".map"]

    @require_export_validation("kraken2")
    def export(self, tree: TaxonomyTree, output_path: Path, **kwargs: Any) -> None:
        """Export taxonomy tree in Kraken2 format.

        Creates:
        - names.dmp: Taxonomic names file
        - nodes.dmp: Taxonomic nodes file
        - seqid2taxid.map: Optional sequence ID to taxonomy ID mapping (if genomes present)
        """
        self._validate_tree(tree)
        self._ensure_output_path(output_path)

        logger.info(
            f"Exporting {tree.node_count} nodes to Kraken2 format: {output_path}"
        )

        # Configuration options
        compress = kwargs.get("compress", False)
        include_genomes = kwargs.get("include_genomes", True)
        use_parallel = kwargs.get("use_parallel", True) and tree.node_count > 10000

        # Define file paths
        names_path = output_path / "names.dmp"
        nodes_path = output_path / "nodes.dmp"
        taxonomy_tab_path = output_path / "taxonomy.tab"
        seqid_path = output_path / "seqid2taxid.map"

        if use_parallel and self.max_workers > 1:
            logger.info(f"Using parallel processing with {self.max_workers} workers for large tree")
            self._export_parallel(tree, output_path, compress, include_genomes)
        else:
            logger.info("Using sequential processing")
            self._export_sequential(tree, output_path, compress, include_genomes)

        logger.info(
            f"Kraken2 export completed: {names_path}, {nodes_path}, {taxonomy_tab_path}"
        )

    def _export_sequential(self, tree: TaxonomyTree, output_path: Path, compress: bool, include_genomes: bool) -> None:
        """Sequential export (original method)."""
        names_path = output_path / "names.dmp"
        nodes_path = output_path / "nodes.dmp"
        taxonomy_tab_path = output_path / "taxonomy.tab"

        self._write_names_file(tree, names_path, compress)
        self._write_nodes_file(tree, nodes_path, compress)
        self._write_taxonomy_tab(tree, taxonomy_tab_path, compress)

        # Create sequence mapping if genomes are present
        if include_genomes and tree.genome_count > 0:
            seqid_path = output_path / "seqid2taxid.map"
            self._write_seqid_mapping(tree, seqid_path, compress)
            logger.info(f"Created seqid2taxid mapping with {tree.genome_count} entries")

    def _export_parallel(self, tree: TaxonomyTree, output_path: Path, compress: bool, include_genomes: bool) -> None:
        """Parallel export using multiple workers."""
        names_path = output_path / "names.dmp"
        nodes_path = output_path / "nodes.dmp"
        taxonomy_tab_path = output_path / "taxonomy.tab"

        # Define file writing tasks
        file_writers = {
            names_path: lambda: self._write_names_file(tree, names_path, compress),
            nodes_path: lambda: self._write_nodes_file(tree, nodes_path, compress),
            taxonomy_tab_path: lambda: self._write_taxonomy_tab(tree, taxonomy_tab_path, compress)
        }

        # Add sequence mapping task if needed
        if include_genomes and tree.genome_count > 0:
            seqid_path = output_path / "seqid2taxid.map"
            file_writers[seqid_path] = lambda: self._write_seqid_mapping(tree, seqid_path, compress)

        # Write all files in parallel
        self._write_files_parallel(file_writers)

    def _write_names_file(
        self, tree: TaxonomyTree, output_path: Path, compress: bool
    ) -> None:
        """Write NCBI names.dmp format file with proper escaping and validation."""
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
        """Write NCBI nodes.dmp format file with proper validation."""
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

    def _write_taxonomy_tab(
        self, tree: TaxonomyTree, output_path: Path, compress: bool
    ) -> None:
        """Write simplified taxonomy.tab format file."""
        with open(output_path, "w") as f:
            for node in tree:
                # Simple tab-separated format: tax_id\tname
                f.write(f"{node.tax_id}\t{node.name}\n")

        if compress:
            from ..utils.subprocess_utils import compress_file

            compress_file(output_path)

    def _write_seqid_mapping(
        self, tree: TaxonomyTree, output_path: Path, compress: bool
    ) -> None:
        """Write seqid2taxid.map file for Kraken2."""
        from ..utils.sequence_utils import FASTAProcessor

        processor = FASTAProcessor()
        sequences_mapped = 0

        with open(output_path, "w") as f:
            for node in tree:
                genomes = tree.get_genomes_for_node(node.tax_id)
                for genome in genomes:
                    # Map genome ID directly
                    f.write(f"{genome.genome_id}\t{node.tax_id}\n")
                    sequences_mapped += 1

                    # If assembly accession is available, also map that
                    if (
                        genome.assembly_accession
                        and genome.assembly_accession != genome.genome_id
                    ):
                        f.write(f"{genome.assembly_accession}\t{node.tax_id}\n")
                        sequences_mapped += 1

                    # If genome has a sequence file, extract sequence IDs from FASTA headers
                    if genome.has_sequence_file and genome.file_path:
                        try:
                            sequence_infos = processor.parse_fasta_headers(
                                Path(genome.file_path)
                            )
                            for seq_info in sequence_infos:
                                # Map each sequence ID to taxonomy ID
                                f.write(f"{seq_info.sequence_id}\t{node.tax_id}\n")
                                sequences_mapped += 1

                        except Exception as e:
                            logger.warning(
                                f"Could not process FASTA file {genome.file_path}: {e}"
                            )

        logger.info(
            f"Created seqid2taxid mapping with {sequences_mapped} sequence entries"
        )

        if compress:
            from ..utils.subprocess_utils import compress_file

            compress_file(output_path)
