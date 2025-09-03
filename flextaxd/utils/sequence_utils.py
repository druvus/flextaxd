"""Utilities for processing genome sequences and FASTA files."""

import gzip
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Iterator, Any, Callable
from dataclasses import dataclass
from collections import defaultdict

from ..core.exceptions import ValidationError


@dataclass
class SequenceInfo:
    """Information about a genome sequence."""

    sequence_id: str
    taxonomy_id: Optional[int] = None
    description: str = ""
    length: Optional[int] = None
    file_path: Optional[Path] = None


@dataclass
class SeqIDMapping:
    """Mapping between sequence IDs and taxonomy IDs."""

    sequence_id: str
    taxonomy_id: int
    source: str = "unknown"


class FASTAProcessor:
    """Utilities for processing FASTA files and extracting sequence information."""

    def __init__(self) -> None:
        self.sequence_info: Dict[str, SequenceInfo] = {}
        self.seqid_mappings: Dict[str, int] = {}

    def parse_fasta_headers(self, fasta_path: Path) -> List[SequenceInfo]:
        """Parse FASTA file and extract sequence information from headers."""
        sequences = []

        try:
            open_func = gzip.open if fasta_path.suffix.lower() == ".gz" else open
            with open_func(fasta_path, "rt", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if line.startswith(">"):
                        # Parse FASTA header
                        seq_info = self._parse_fasta_header(line, fasta_path, line_num)
                        if seq_info:
                            sequences.append(seq_info)

        except Exception as e:
            raise ValidationError(f"Error parsing FASTA file {fasta_path}: {e}")

        return sequences

    def _parse_fasta_header(
        self, header: str, file_path: Path, line_num: int
    ) -> Optional[SequenceInfo]:
        """Parse a FASTA header line and extract sequence information."""
        # Remove leading '>'
        header = header[1:].strip()

        if not header:
            return None

        # Extract sequence ID (first space-delimited field)
        parts = header.split(None, 1)
        seq_id = parts[0]
        description = parts[1] if len(parts) > 1 else ""

        return SequenceInfo(
            sequence_id=seq_id, description=description, file_path=file_path
        )

    def extract_gtdb_taxonomy_from_header(self, header: str) -> Optional[str]:
        """Extract GTDB taxonomy string from FASTA header."""
        # GTDB headers often have format: >GB_GCA_000001405.38 d__Bacteria;p__Proteobacteria;...
        # Or: >RS_GCF_000005825.2 d__Bacteria;p__Firmicutes;...

        if "d__" in header:
            # Find the taxonomy part
            taxonomy_match = re.search(r"d__[^;]+(?:;[^;]+)*", header)
            if taxonomy_match:
                return taxonomy_match.group()

        return None

    def extract_silva_taxonomy_from_header(
        self, header: str
    ) -> Optional[Tuple[str, str]]:
        """Extract SILVA taxonomy and accession from header."""
        # SILVA headers: >AACY020068177.1.1441.1464 Bacteria;Actinobacteria;Actinobacteria;...

        parts = header[1:].split(None, 1)
        if len(parts) < 2:
            return None

        accession = parts[0]

        # Look for semicolon-separated taxonomy
        if ";" in parts[1]:
            taxonomy = parts[1].split()[0] if " " in parts[1] else parts[1]
            return accession, taxonomy

        return None

    def split_fasta_by_sequence(
        self,
        input_fasta: Path,
        output_dir: Path,
        max_sequences_per_file: Optional[int] = 1,
    ) -> List[Path]:
        """Split FASTA file into individual files, one per sequence (or grouped)."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        created_files = []
        current_file_handle = None
        current_file_path = None
        sequences_in_current_file = 0
        file_counter = 0

        try:
            open_func = gzip.open if input_fasta.suffix.lower() == ".gz" else open
            with open_func(input_fasta, "rt", encoding="utf-8") as input_f:

                for line in input_f:
                    if line.startswith(">"):
                        # New sequence
                        if (
                            max_sequences_per_file
                            and sequences_in_current_file >= max_sequences_per_file
                        ):
                            # Close current file and start new one
                            if current_file_handle:
                                current_file_handle.close()
                                current_file_handle = None
                                sequences_in_current_file = 0

                        if current_file_handle is None:
                            # Create new file
                            if max_sequences_per_file == 1:
                                # Individual files named by sequence ID
                                seq_id = line[1:].split()[0]
                                # Sanitize filename
                                safe_seq_id = re.sub(r'[<>:"/\\|?*]', "_", seq_id)
                                current_file_path = output_dir / f"{safe_seq_id}.fasta"
                            else:
                                # Batch files
                                current_file_path = (
                                    output_dir / f"sequences_{file_counter:06d}.fasta"
                                )
                                file_counter += 1

                            current_file_handle = open(
                                current_file_path, "w", encoding="utf-8"
                            )
                            created_files.append(current_file_path)

                        sequences_in_current_file += 1

                    if current_file_handle:
                        current_file_handle.write(line)

            if current_file_handle:
                current_file_handle.close()

        except Exception as e:
            # Clean up on error
            if current_file_handle:
                current_file_handle.close()
            raise ValidationError(f"Error splitting FASTA file {input_fasta}: {e}")

        return created_files

    def convert_rna_to_dna(self, fasta_path: Path) -> None:
        """Convert RNA sequences (U) to DNA sequences (T) in-place."""
        try:
            # Read file content
            with open(fasta_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Convert U to T
            content = content.replace("U", "T").replace("u", "t")

            # Write back
            with open(fasta_path, "w", encoding="utf-8") as f:
                f.write(content)

        except Exception as e:
            raise ValidationError(f"Error converting RNA to DNA in {fasta_path}: {e}")


class SeqIDMappingManager:
    """Manager for sequence ID to taxonomy ID mappings."""

    def __init__(self) -> None:
        self.mappings: Dict[str, SeqIDMapping] = {}

    def load_seqid_mapping_file(self, mapping_file: Path) -> None:
        """Load seqid2taxid mapping from file."""
        mappings_loaded = 0

        try:
            open_func = gzip.open if mapping_file.suffix.lower() == ".gz" else open
            with open_func(mapping_file, "rt", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue

                    # Parse different formats
                    mapping = self._parse_mapping_line(
                        line, str(mapping_file), line_num
                    )
                    if mapping:
                        self.mappings[mapping.sequence_id] = mapping
                        mappings_loaded += 1

        except Exception as e:
            raise ValidationError(
                f"Error loading seqid mapping from {mapping_file}: {e}"
            )

        print(f"Loaded {mappings_loaded} sequence ID mappings")

    def _parse_mapping_line(
        self, line: str, source: str, line_num: int
    ) -> Optional[SeqIDMapping]:
        """Parse a single mapping line."""
        # Handle different formats:
        # Format 1: sequence_id<TAB>taxonomy_id
        # Format 2: accession<TAB>accession.version<TAB>taxid<TAB>gi (NCBI format)

        parts = line.split("\t")

        if len(parts) >= 2:
            seq_id = parts[0].strip()

            # Try to parse taxonomy ID from second column
            try:
                tax_id = int(parts[1].strip())
                return SeqIDMapping(seq_id, tax_id, source)
            except ValueError:
                pass

            # Try NCBI format (taxid is third column)
            if len(parts) >= 3:
                try:
                    tax_id = int(parts[2].strip())
                    return SeqIDMapping(seq_id, tax_id, source)
                except ValueError:
                    pass

        # Could not parse
        print(f"Warning: Could not parse mapping line {line_num} in {source}: {line}")
        return None

    def create_mapping_from_fasta_and_taxonomy(
        self, fasta_path: Path, taxonomy_string_extractor: Callable[[str], str]
    ) -> Dict[str, int]:
        """Create seqid2taxid mapping by extracting taxonomy from FASTA headers."""
        mappings = {}
        taxonomy_to_id = {}
        next_tax_id = 1

        processor = FASTAProcessor()
        sequences = processor.parse_fasta_headers(fasta_path)

        for seq_info in sequences:
            # Extract taxonomy from header
            taxonomy = taxonomy_string_extractor(
                f">{seq_info.sequence_id} {seq_info.description}"
            )

            if taxonomy:
                # Get or create taxonomy ID
                if taxonomy not in taxonomy_to_id:
                    taxonomy_to_id[taxonomy] = next_tax_id
                    next_tax_id += 1

                tax_id = taxonomy_to_id[taxonomy]
                mappings[seq_info.sequence_id] = tax_id

                self.mappings[seq_info.sequence_id] = SeqIDMapping(
                    seq_info.sequence_id, tax_id, str(fasta_path)
                )

        return mappings

    def export_seqid2taxid_map(self, output_path: Path) -> None:
        """Export sequence ID to taxonomy ID mappings to file."""
        with open(output_path, "w", encoding="utf-8") as f:
            for mapping in sorted(self.mappings.values(), key=lambda x: x.sequence_id):
                f.write(f"{mapping.sequence_id}\t{mapping.taxonomy_id}\n")

    def get_mapping(self, sequence_id: str) -> Optional[int]:
        """Get taxonomy ID for a sequence ID."""
        mapping = self.mappings.get(sequence_id)
        return mapping.taxonomy_id if mapping else None

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about the mappings."""
        if not self.mappings:
            return {"total_mappings": 0}

        tax_id_counts: Dict[int, int] = defaultdict(int)
        sources: Dict[str, int] = defaultdict(int)

        for mapping in self.mappings.values():
            tax_id_counts[mapping.taxonomy_id] += 1
            sources[mapping.source] += 1

        return {
            "total_mappings": len(self.mappings),
            "unique_taxonomy_ids": len(tax_id_counts),
            "sources": dict(sources),
            "most_common_tax_id": (
                max(tax_id_counts.items(), key=lambda x: x[1])
                if tax_id_counts
                else None
            ),
        }


class GenomeDirectoryManager:
    """Manager for organizing and validating genome directories."""

    def __init__(self, genomes_path: Path):
        self.genomes_path = Path(genomes_path)
        self.genome_files: Dict[str, Path] = {}
        self._scan_directory()

    def _scan_directory(self) -> None:
        """Scan genomes directory and catalog files."""
        if not self.genomes_path.exists():
            return

        # Common genome file extensions
        extensions = {".fasta", ".fa", ".fna", ".ffn", ".faa", ".gz"}

        for file_path in self.genomes_path.rglob("*"):
            if file_path.is_file():
                # Check if it's a genome file
                if any(str(file_path).endswith(ext) for ext in extensions):
                    # Use stem as genome ID (without extensions)
                    genome_id = file_path.stem
                    if genome_id.endswith(".gz"):
                        genome_id = Path(genome_id).stem

                    self.genome_files[genome_id] = file_path

    def get_genome_file(self, genome_id: str) -> Optional[Path]:
        """Get path to genome file by ID."""
        return self.genome_files.get(genome_id)

    def list_genome_ids(self) -> List[str]:
        """List all available genome IDs."""
        return list(self.genome_files.keys())

    def validate_genome_coverage(self, sequence_ids: Set[str]) -> Dict[str, List[str]]:
        """Validate which sequence IDs have corresponding genome files."""
        results: Dict[str, List[str]] = {"found": [], "missing": []}

        for seq_id in sequence_ids:
            if self.get_genome_file(seq_id):
                results["found"].append(seq_id)
            else:
                results["missing"].append(seq_id)

        return results

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about the genome directory."""
        total_size = 0
        file_types: Dict[str, int] = defaultdict(int)

        for file_path in self.genome_files.values():
            try:
                total_size += file_path.stat().st_size
                suffix = file_path.suffix.lower()
                file_types[suffix] += 1
            except OSError:
                pass

        return {
            "total_files": len(self.genome_files),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "file_types": dict(file_types),
        }
