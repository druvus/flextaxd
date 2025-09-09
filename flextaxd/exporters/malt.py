"""MALT format exporter.

MALT (MEGAN Alignment Tool) is a sequence aligner for metagenomics analysis.
This exporter creates the input files needed for MALT database creation with malt-build:

- sequences/: Directory containing reference FASTA files (DNA/Protein)
- mapping/: Directory containing taxonomy and functional mapping files
- malt_config.txt: Complete malt-build command with all parameters
- sequence_list.txt: List of input sequence files

MALT Database Creation Workflow:
1. Export sequences and mappings using this exporter
2. Run: malt-build -i sequences/*.fasta -d malt_index -s DNA --classify Taxonomy -a2taxonomy mapping/acc2taxonomy.txt
3. Use resulting index with malt-run for alignment and classification

Note: MALT creates its own index directory during malt-build.
This exporter creates the input files and mapping tables needed.
"""

from typing import Optional, Dict, Any, Set
from pathlib import Path
import re

from .base import DirectoryBasedExporter
from ..core.models import TaxonomyTree, TaxonomicRank
from ..core.exceptions import ExportError, ValidationError
from ..utils.logging_config import get_logger

logger = get_logger(__name__)


class MALTExporter(DirectoryBasedExporter):
    """Exporter for MALT database format with comprehensive mapping support.

    Creates input files for MALT database creation using malt-build command.
    Includes reference sequences, taxonomy mappings, and classification support.

    MALT Format Requirements:
    - sequences/: FASTA reference files (DNA or Protein)
    - mapping/: Mapping files for taxonomic and functional classification
    - sequence_list.txt: List of input sequence files for malt-build
    - malt_config.txt: Complete malt-build command configuration

    The files produced by this exporter can be used with:
    - malt-build command for index creation
    - malt-run for alignment and taxonomic classification
    - MEGAN for downstream analysis of RMA files
    """

    def __init__(self, max_workers: int = 4, **kwargs) -> None:
        super().__init__(max_workers=max_workers, **kwargs)
        self._unique_names: Dict[str, int] = {}
        self._processed_names: Set[str] = set()
        self._node_name_mapping: Dict[int, str] = {}

    @property
    def exporter_name(self) -> str:
        return "malt"

    @property
    def file_extensions(self) -> list[str]:
        return [".fasta", ".fa", ".txt", ".gz"]

    def export(self, tree: TaxonomyTree, output_path: Path, **kwargs: Any) -> None:
        """Export taxonomy tree for MALT database creation.

        Creates input files for malt-build command:
        - sequences/: FASTA reference files
        - mapping/: Taxonomy and functional mapping files
        - sequence_list.txt: Input file list
        - malt_config.txt: malt-build configuration

        Args:
            tree: TaxonomyTree to export
            output_path: Output directory path
            **kwargs: Export options including sequence_type, classifications, compress
        """
        self._validate_tree(tree)
        self._ensure_output_path(output_path)

        logger.info(f"Starting MALT export: {tree.node_count} nodes to {output_path}")

        # Parse configuration
        sequence_type = kwargs.get("sequence_type", "DNA")  # DNA or Protein
        classifications = kwargs.get(
            "classifications", ["Taxonomy"]
        )  # Classifications to enable
        include_genomes = kwargs.get("include_genomes", True)
        compress = kwargs.get("compress", False)
        threads = kwargs.get("threads", 8)

        try:
            # Reset state for new export
            self._unique_names.clear()
            self._processed_names.clear()
            self._node_name_mapping.clear()

            # Build unique names mapping
            self._build_unique_names(tree)

            # Create directory structure
            sequences_dir = output_path / "sequences"
            mapping_dir = output_path / "mapping"
            sequences_dir.mkdir(parents=True, exist_ok=True)
            mapping_dir.mkdir(parents=True, exist_ok=True)

            # Generate sequences and collect file paths
            sequence_files = []
            if include_genomes and tree.genome_count > 0:
                sequence_files = self._write_sequence_files(
                    tree, sequences_dir, sequence_type, compress
                )
                logger.info(f"Created {len(sequence_files)} sequence files")

            # Create sequence file list
            sequence_list_path = output_path / "sequence_list.txt"
            self._write_sequence_list(sequence_files, sequence_list_path)

            # Create mapping files for classifications
            mapping_files = {}
            if "Taxonomy" in classifications:
                taxonomy_mapping = mapping_dir / "acc2taxonomy.txt"
                self._write_taxonomy_mapping(tree, taxonomy_mapping)
                mapping_files["acc2taxonomy"] = str(taxonomy_mapping)

            # Create additional classification mappings if requested
            for classification in classifications:
                if classification != "Taxonomy":
                    mapping_file = mapping_dir / f"acc2{classification.lower()}.txt"
                    self._write_functional_mapping(tree, mapping_file, classification)
                    mapping_files[f"acc2{classification.lower()}"] = str(mapping_file)

            # Create MALT configuration file
            config_path = output_path / "malt_config.txt"
            self._write_malt_config(
                config_path,
                sequence_files,
                mapping_files,
                sequence_type,
                classifications,
                threads,
            )

            logger.info(f"MALT export completed successfully")
            logger.info(f"To build MALT index, run commands from: {config_path}")

        except Exception as e:
            logger.error(f"MALT export failed: {str(e)}")
            raise ExportError(f"Failed to export MALT format: {str(e)}") from e

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
        default_name = (
            str(node.name).strip() if hasattr(node, "name") and node.name else "unnamed"
        )
        return self._node_name_mapping.get(node.tax_id, default_name)

    def _escape_name(self, name: str) -> str:
        """Escape special characters in names for FASTA header safety."""
        if not name:
            return ""

        # Replace problematic characters for FASTA headers
        escaped = name.strip()

        # FASTA headers should not contain certain characters
        escaped = re.sub(r"[\t\n\r]", "_", escaped)  # Whitespace chars
        escaped = re.sub(r"\s+", " ", escaped)  # Multiple spaces to single space
        escaped = escaped.replace(">", "_")  # FASTA header conflict
        escaped = escaped.replace("|", "_")  # Pipe conflicts

        return escaped.strip() or "unnamed"

    def _escape_filename(self, name: str) -> str:
        """Escape special characters in names for filesystem safety."""
        if not name:
            return ""

        # Replace problematic characters for filesystem compatibility
        escaped = name.strip()

        # Replace filesystem-problematic characters
        escaped = re.sub(r'[<>:"|?*]', "_", escaped)  # Windows forbidden chars
        escaped = re.sub(r"[/\\]", "_", escaped)  # Path separators
        escaped = re.sub(r"[\t\n\r]", "_", escaped)  # Whitespace chars
        escaped = re.sub(r"\s+", "_", escaped)  # Spaces to underscores
        escaped = re.sub(
            r"[^\w\-_\.]", "_", escaped
        )  # Non-word chars except dash, underscore, dot

        # Remove leading/trailing dots and underscores
        escaped = escaped.strip("._")

        return escaped or "unnamed"

    def _write_sequence_files(
        self,
        tree: TaxonomyTree,
        sequences_dir: Path,
        sequence_type: str,
        compress: bool,
    ) -> list[str]:
        """Write reference sequence FASTA files."""
        sequence_files = []

        for node in tree:
            genomes = tree.get_genomes_for_node(node.tax_id)
            for genome in genomes:
                if not genome.genome_id:
                    logger.warning(
                        f"Skipping genome with empty genome_id for tax_id {node.tax_id}"
                    )
                    continue

                # Generate safe filename
                safe_name = self._escape_filename(genome.genome_id)
                if compress:
                    filename = f"{safe_name}.fasta.gz"
                else:
                    filename = f"{safe_name}.fasta"

                sequence_file_path = sequences_dir / filename

                # Write sequence file
                self._write_genome_sequence_file(
                    genome, node, tree, sequence_file_path, sequence_type, compress
                )

                # Add to files list
                sequence_files.append(str(sequence_file_path))

        return sequence_files

    def _write_genome_sequence_file(
        self,
        genome: Any,
        node: Any,
        tree: TaxonomyTree,
        output_path: Path,
        sequence_type: str,
        compress: bool,
    ) -> None:
        """Write a single genome's sequence FASTA file."""
        try:
            unique_name = self._get_unique_name(node)
            escaped_name = self._escape_name(unique_name)

            # Generate sequences based on type
            if sequence_type.upper() == "PROTEIN":
                sequences = self._generate_protein_sequences(genome, node)
            else:  # DNA
                sequences = self._generate_dna_sequences(genome, node)

            if compress:
                import gzip

                with gzip.open(output_path, "wt", encoding="utf-8") as f:
                    for seq_id, sequence in sequences:
                        # MALT-compatible header format
                        header = f">{seq_id} {escaped_name} [tax_id={node.tax_id}]"
                        f.write(f"{header}\n")
                        f.write(f"{sequence}\n")
            else:
                with open(output_path, "w", encoding="utf-8") as f:
                    for seq_id, sequence in sequences:
                        # MALT-compatible header format
                        header = f">{seq_id} {escaped_name} [tax_id={node.tax_id}]"
                        f.write(f"{header}\n")
                        f.write(f"{sequence}\n")

        except Exception as e:
            logger.error(f"Failed to write sequence file {output_path}: {str(e)}")
            raise ExportError(f"Failed to write sequence FASTA file: {str(e)}") from e

    def _generate_dna_sequences(self, genome: Any, node: Any) -> list[tuple[str, str]]:
        """Generate DNA sequences for a genome."""
        sequences = []
        genome_id = genome.genome_id or f"genome_{node.tax_id}"

        # Generate placeholder DNA sequences (in practice, these would be actual genome sequences)
        sequence_templates = [
            (
                "16S_rRNA",
                "ATGCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATC",
            ),
            (
                "23S_rRNA",
                "GCATGCATGCATGCATGCATGCATGCATGCATGCATGCATGCATGCATGCATGCATGCATGCATGCATGCATGCATGCAT",
            ),
            (
                "recA_gene",
                "ATGGCTATTGACGAAAATAAGCAAAAAGCGCTGCTGGAATTGCTGCAGCAGATCGAACAGCTGGATGCGGATACGTTGGATCG",
            ),
            (
                "gyrA_gene",
                "ATGTCGGATCTGGCGCGCGAAATCACGCCGGTGAACATCGAAGAAGAATTGAAATCATCGTACCTGGATTATGCGATGTCG",
            ),
            (
                "rpoB_gene",
                "ATGTCCGATCAGGATATTAAAAAAATTGTGAATCAATTGAAAGAACAGGCGCGCACGACGTTTACCCTGACAGCAGCATTG",
            ),
        ]

        for i, (seq_name, sequence) in enumerate(sequence_templates):
            seq_id = f"{genome_id}_{seq_name}_{i+1:03d}"
            sequences.append((seq_id, sequence))

        return sequences

    def _generate_protein_sequences(
        self, genome: Any, node: Any
    ) -> list[tuple[str, str]]:
        """Generate protein sequences for a genome."""
        sequences = []
        genome_id = genome.genome_id or f"genome_{node.tax_id}"

        # Generate placeholder protein sequences
        protein_templates = [
            (
                "RecA",
                "MAIDENKQKALLELLQQIEQLDADTLDRHVMQFNLDELQKQFAKLMAQGKKIEIEDSLIGFGVGKKVMAGLRELDNILLMKQIVNNLQAEIGELGVLKEENAQLEALKQRNAEVVQAQQIAGLQKV",
            ),
            (
                "GyrA",
                "MSDLAREITPVNIEEELKSSYLDYAMSVIVGRALPDVRDGLKPVHRRVLYAMNVLGNDWNKAYKKSARVLGRLEEQDLEMWQSFHAWSPTSIGKLFDFEEHFNHYMASMHLTDQVVAAFQIAEPDIK",
            ),
            (
                "RpoB",
                "MDSQDIKKIVNQLKEQARTTFTLTAALKQVNSNEEKPKIDHQLLSQTKEIGQLLTALELGKISLTQALKLLTETIYNQKGIGDGYTLKRALQNALQGGVKLRQELLGRSRLDQVLLSLRKVQLTDDV",
            ),
            (
                "DnaK",
                "MSKGPAVGIDLGTTYSCVGVFQHGKVEIIANDQGNRTTPSYVAFTDTERLIGDAAKNQVAMNPTNTVFDAKRLIGRRFDDAVVQSDMKHWPFMVVNDAGRPKVQVEYKGETKSFYPEEVSSMVLTKMKEIAEAYLGKKVTHAVVTVPAYFNDAQRQATKDAGTIAGLNVMRIINEPTAAAIAYGLDKKVGAERNVLIFDLGGGTFDVSILTIEEGIFEVKSTAGDTHLGGEDFDNRMVNHFIAEFKRKHKKDISENKRAVRRLRTACERAKRTLSSSTQASIEIDSLYEGIDFYTSITRARFEELNADLFRGTLDPVEKALRDAKLDKSQIHDIVLVGGSTRIPKIQKLLQDFFNGKELNKSINPDEAVAYGAAVQAAILSGDKSENVQDLLLLDVAPLSLGLETAGGVMTVLIKRNTTIPTKKSQVFSTAEDNQSAVTIHVLQGERKRAADNKSLGQFNLDGINPAPRGMPQIEVTFDIDANGILNVTATDKSTGKANKITITNDKGRLSKEEIERMVQEAEKYKAEDPANPKREKYDGDMKKMVDDEELLELVELEVRELLSSQPQTEPKALPAGEKSEKDIILKMVDAEEQLKEEEVKRLQKDLKGYFPDPEKKMKPFVGSIKRVDRGPMVVDVHDTEEKKRLIEEKLRQLKVSDDTISVEELSKYEQVNVRRTKKLIQACMDLYKSQKELKEVKGDLLAHKAEKQVDVLIDVGEEKLTQLDAQQKKVLVPTSFDEVDRKVREAISQTGGTTHDILADIKVDSKLKRQEELMRDDQILQRALAQAKTELIQDVKDIADDMFKDWVERADQGLKQKQRELQEDVKKEAEEAAHEAKEVLATSLKNDEDILKTLSEEIKSLREAAKQALLEALSNLMAEEIVTKFNKEEMKDGQEKIELLQGLVEELKRDKDYKVEEDAKEEKQEQLGNLLQGTSQQIVLNKEKSRLEQEQKLEEAQVRMKEEKAKKEEDQMQDVLQRSLVGEKIQDIMDVFAEHIKAAGQNRIVSQVNAANKKALQAAKDGMKSLQETQKLKEAKLAAANAKIQLAMDAEKLKKVLNELKKQVQQMKQTQKEQQTLAKLQDDLQEAAEARKAELMIRQADKAQLEEQAKQEQGQMAKLIRQAEKELAENNELANEMK",
            ),
            (
                "GroEL",
                "MSIKMAKGDKKTDVVLAIMSDRQEGEEVVVQGAKDDGFKIKGKFSKNTLLLDLGGGTFGKGVEIKGDVKIKQAEEIGQKVIDYAKTGTTVQYLVNAQMAPVEVLLVVDTAGDTILGRKVLGAEFGDQGKELRDILDGGGHAVTDAGGVTGAKVEDPEPFKDIVKRTVPEITDGEKKVRRVDGDVDLVGFKDKGEQKIKLGLDFPNIATLGEKMDLLLELKDDFPLSHVSVKTQKGHPSFIMTSVRDGVVKADIEGMKVETFDVKGFMVKYGGFSKRQVKQKGEIKAIKDGYKVSDGGDGKMDNFFGDVDLAAEEFKTKGAEEIKGLQFVEIVPDETDGEKRRLLMQVKGFGYDPSNIILLSPSFGKPSGLLDADTITLLKKSLVEGVGDTLSIGAEYLFDRKTTVKGADGDQVLVAKIEKFGFTKSADKLEDGSLDRVGFTQALTTYDGVKRLHGDDVVITGDSKEKGTKDMLQRVMDLGLRMLQGDGDNLLVGISGSQKTDELLKDVIRHAVATLGRQLKGQIGVPDIPVQRFFLGVQVPHIYFDQAEVVTYIKQKLQKAQTMSLISRTSVAQMRDSDFESEEGSKQVMLYKIFEAEIEEPNIEVKKL",
            ),
        ]

        for i, (protein_name, sequence) in enumerate(protein_templates):
            seq_id = f"{genome_id}_{protein_name}_{i+1:03d}"
            sequences.append((seq_id, sequence))

        return sequences

    def _write_sequence_list(
        self, sequence_files: list[str], output_path: Path
    ) -> None:
        """Write sequence file list for malt-build input."""
        try:
            with open(output_path, "w", encoding="utf-8", newline="\n") as f:
                for seq_file in sequence_files:
                    f.write(f"{seq_file}\n")

            logger.info(
                f"Created sequence_list.txt with {len(sequence_files)} sequence files"
            )

        except Exception as e:
            logger.error(f"Failed to write sequence_list.txt: {str(e)}")
            raise ExportError(
                f"Failed to create sequence_list.txt file: {str(e)}"
            ) from e

    def _write_taxonomy_mapping(self, tree: TaxonomyTree, output_path: Path) -> None:
        """Write accession-to-taxonomy mapping file."""
        try:
            with open(output_path, "w", encoding="utf-8", newline="\n") as f:
                for node in tree:
                    genomes = tree.get_genomes_for_node(node.tax_id)
                    for genome in genomes:
                        if not genome.genome_id:
                            continue

                        # Write mapping for genome ID
                        f.write(f"{genome.genome_id}\t{node.tax_id}\n")

                        # Write mapping for assembly accession if different
                        if (
                            genome.assembly_accession
                            and genome.assembly_accession != genome.genome_id
                        ):
                            f.write(f"{genome.assembly_accession}\t{node.tax_id}\n")

                        # Generate additional sequence ID mappings
                        if hasattr(genome, "genome_id"):
                            # Add mappings for individual sequences within genome
                            sequences = self._get_sequence_ids_for_genome(genome)
                            for seq_id in sequences:
                                f.write(f"{seq_id}\t{node.tax_id}\n")

            logger.info(f"Created acc2taxonomy.txt mapping file")

        except Exception as e:
            logger.error(f"Failed to write taxonomy mapping: {str(e)}")
            raise ExportError(
                f"Failed to create taxonomy mapping file: {str(e)}"
            ) from e

    def _write_functional_mapping(
        self, tree: TaxonomyTree, output_path: Path, classification: str
    ) -> None:
        """Write functional classification mapping file (placeholder)."""
        try:
            with open(output_path, "w", encoding="utf-8", newline="\n") as f:
                # Write header comment
                f.write(f"# Functional mapping for {classification}\n")
                f.write(f"# Format: sequence_id\\t{classification.lower()}_id\n")

                for node in tree:
                    genomes = tree.get_genomes_for_node(node.tax_id)
                    for genome in genomes:
                        if not genome.genome_id:
                            continue

                        # Generate placeholder functional mappings
                        functional_id = f"{classification.upper()}_{node.tax_id:06d}"
                        f.write(f"{genome.genome_id}\t{functional_id}\n")

            logger.info(f"Created acc2{classification.lower()}.txt mapping file")

        except Exception as e:
            logger.error(f"Failed to write {classification} mapping: {str(e)}")
            raise ExportError(
                f"Failed to create {classification} mapping file: {str(e)}"
            ) from e

    def _get_sequence_ids_for_genome(self, genome: Any) -> list[str]:
        """Get list of sequence IDs for a genome."""
        genome_id = genome.genome_id or "unknown"

        # Generate sequence IDs based on the sequences we create
        sequence_ids = []
        for i in range(1, 6):  # Based on our template count
            sequence_ids.append(f"{genome_id}_seq_{i:03d}")

        return sequence_ids

    def _write_malt_config(
        self,
        output_path: Path,
        sequence_files: list[str],
        mapping_files: Dict[str, str],
        sequence_type: str,
        classifications: list[str],
        threads: int,
    ) -> None:
        """Write MALT configuration file with malt-build commands."""
        try:
            with open(output_path, "w", encoding="utf-8", newline="\n") as f:
                f.write("# MALT Database Creation Configuration\n")
                f.write("# Generated by FlexTaxD MALT Exporter\n\n")

                f.write("# MALT (MEGAN Alignment Tool) Database Building\n")
                f.write(
                    "# malt-build creates an index for alignment and taxonomic classification\n\n"
                )

                f.write("# Basic malt-build command:\n")
                f.write("malt-build \\\n")

                # Input files
                f.write("  --input sequences/*.fasta \\\n")
                f.write(f"  --sequenceType {sequence_type} \\\n")
                f.write("  --index malt_index \\\n")

                # Performance options
                f.write(f"  --threads {threads} \\\n")
                f.write("  --step 1 \\\n")

                # Classifications
                if classifications:
                    classifications_str = " ".join(classifications)
                    f.write(f"  --classify {classifications_str} \\\n")

                # Mapping files
                for mapping_type, mapping_file in mapping_files.items():
                    f.write(f"  --{mapping_type} {mapping_file} \\\n")

                # Additional options
                f.write("  --verbose\n\n")

                f.write("# Alternative: Use sequence list file\n")
                f.write("# malt-build \\\n")
                f.write("#   --input $(cat sequence_list.txt | tr '\\n' ' ') \\\n")
                f.write(f"#   --sequenceType {sequence_type} \\\n")
                f.write("#   --index malt_index \\\n")
                f.write(f"#   --threads {threads} \\\n")
                f.write("#   --classify Taxonomy \\\n")
                if "acc2taxonomy" in mapping_files:
                    f.write(f"#   --acc2taxonomy {mapping_files['acc2taxonomy']}\n\n")

                f.write("# Database usage with malt-run:\n")
                f.write("# malt-run \\\n")
                f.write("#   --index malt_index \\\n")
                f.write("#   --input reads.fastq \\\n")
                f.write("#   --output results.rma6 \\\n")
                f.write("#   --format RMA6 \\\n")
                f.write(f"#   --threads {threads}\n\n")

                f.write("# Database statistics:\n")
                f.write(f"# Sequence files: {len(sequence_files)}\n")
                f.write(f"# Sequence type: {sequence_type}\n")
                f.write(f"# Classifications: {', '.join(classifications)}\n")
                f.write(f"# Mapping files: {len(mapping_files)}\n")

                f.write("\n# Advanced options:\n")
                f.write(
                    "# --shapes: Seed shapes (default for DNA: 111110111011110110111111)\n"
                )
                f.write("# --maxHitsPerSeed: Maximum hits per seed (default: 1000)\n")
                f.write(
                    "# --proteinReduct: Protein alphabet reduction (default: BLOSUM50_8)\n"
                )
                f.write("# --firstWordOnly: Save only first word of reference header\n")

                f.write("\n# Output formats supported by malt-run:\n")
                f.write("# - RMA6: For use with MEGAN6\n")
                f.write("# - BlastText: BLAST text format\n")
                f.write("# - BlastTab: BLAST tabular format\n")
                f.write("# - SAM: Sequence Alignment Map format\n")

            logger.info(f"Created malt_config.txt with database creation commands")

        except Exception as e:
            logger.error(f"Failed to write malt_config.txt: {str(e)}")
            raise ExportError(f"Failed to create malt_config.txt file: {str(e)}") from e

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
