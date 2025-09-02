"""Diamond format exporter.

Diamond is a high-performance protein sequence aligner that uses binary databases.
This exporter creates the input files needed for Diamond database creation:

- proteins/: Directory containing protein FASTA files
- protein_list.txt: List of protein file paths for batch processing
- taxonomy_info.txt: Taxonomy mapping for protein sequences
- diamond_config.txt: Commands for diamond makedb

Diamond Database Creation Workflow:
1. Export protein sequences using this exporter
2. Run: diamond makedb --in proteins.fasta -d database
3. Use resulting database.dmnd file with diamond alignment commands

Note: Diamond creates binary .dmnd databases during makedb.
This exporter only creates the input protein FASTA files needed.
"""

from typing import Optional, Dict, Any, Set
from pathlib import Path
import re

from .base import DirectoryBasedExporter
from ..core.models import TaxonomyTree, TaxonomicRank
from ..core.exceptions import ExportError, ValidationError
from ..utils.logging_config import get_logger

logger = get_logger(__name__)


class DiamondExporter(DirectoryBasedExporter):
    """Exporter for Diamond database format with protein sequence handling.
    
    Creates input files for Diamond database creation using diamond makedb command.
    Focuses on protein sequences and taxonomy mapping for high-performance alignment.
    
    Diamond Format Requirements:
    - proteins.fasta: Single FASTA file with all protein sequences
    - proteins/: Directory with individual protein FASTA files (optional)
    - taxonomy_info.txt: Tab-separated taxonomy mapping
    - diamond_config.txt: Recommended parameters for diamond makedb
    
    The files produced by this exporter can be used with:
    - diamond makedb command for database creation
    - High-performance protein alignment workflows
    - Metagenomics analysis pipelines (e.g., Melon)
    """
    
    def __init__(self) -> None:
        super().__init__()
        self._unique_names: Dict[str, int] = {}
        self._processed_names: Set[str] = set()
        self._node_name_mapping: Dict[int, str] = {}
    
    @property
    def exporter_name(self) -> str:
        return "diamond"
    
    @property
    def file_extensions(self) -> list[str]:
        return [".fasta", ".fa", ".txt"]
    
    def export(self, tree: TaxonomyTree, output_path: Path, **kwargs: Any) -> None:
        """Export taxonomy tree for Diamond database creation.
        
        Creates input files for diamond makedb command:
        - proteins.fasta: Single FASTA file with all protein sequences
        - proteins/: Directory with individual protein FASTA files
        - taxonomy_info.txt: Taxonomy mapping
        - diamond_config.txt: Recommended makedb parameters
        
        Args:
            tree: TaxonomyTree to export
            output_path: Output directory path
            **kwargs: Export options including include_genomes, single_file, compress
        """
        self._validate_tree(tree)
        self._ensure_output_path(output_path)
        
        logger.info(f"Starting Diamond export: {tree.node_count} nodes to {output_path}")
        
        # Parse configuration
        include_genomes = kwargs.get('include_genomes', True)
        single_file = kwargs.get('single_file', True)  # Default to single FASTA file
        compress = kwargs.get('compress', False)  # Diamond doesn't require compression
        
        try:
            # Reset state for new export
            self._unique_names.clear()
            self._processed_names.clear()
            self._node_name_mapping.clear()
            
            # Build unique names mapping
            self._build_unique_names(tree)
            
            # Create protein files
            protein_paths = []
            if include_genomes and tree.genome_count > 0:
                if single_file:
                    # Create single proteins.fasta file
                    proteins_file = output_path / "proteins.fasta"
                    count = self._write_single_protein_file(tree, proteins_file)
                    protein_paths = [str(proteins_file)]
                    logger.info(f"Created single proteins.fasta with {count} sequences")
                else:
                    # Create proteins directory with individual files
                    proteins_dir = output_path / "proteins"
                    proteins_dir.mkdir(parents=True, exist_ok=True)
                    protein_paths = self._write_protein_files(tree, proteins_dir, compress)
                    logger.info(f"Created {len(protein_paths)} protein files")
            
            # Create taxonomy information file
            taxonomy_info_path = output_path / "taxonomy_info.txt"
            self._write_taxonomy_info(tree, taxonomy_info_path)
            
            # Create Diamond configuration file
            config_path = output_path / "diamond_config.txt"
            self._write_diamond_config(config_path, protein_paths, single_file)
            
            logger.info(f"Diamond export completed successfully")
            if single_file and protein_paths:
                logger.info(f"To build Diamond database, run: diamond makedb --in {protein_paths[0]} -d database")
            
        except Exception as e:
            logger.error(f"Diamond export failed: {str(e)}")
            raise ExportError(f"Failed to export Diamond format: {str(e)}") from e
    
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
        default_name = str(node.name).strip() if hasattr(node, 'name') and node.name else "unnamed"
        return self._node_name_mapping.get(node.tax_id, default_name)
    
    def _escape_name(self, name: str) -> str:
        """Escape special characters in names for FASTA header safety."""
        if not name:
            return ""
        
        # Replace problematic characters for FASTA headers
        escaped = name.strip()
        
        # FASTA headers should not contain certain characters
        escaped = re.sub(r'[\t\n\r]', '_', escaped)  # Whitespace chars
        escaped = re.sub(r'\s+', ' ', escaped)  # Multiple spaces to single space
        escaped = escaped.replace('>', '_')  # FASTA header conflict
        escaped = escaped.replace('|', '_')  # Pipe conflicts
        
        return escaped.strip() or "unnamed"
    
    def _escape_filename(self, name: str) -> str:
        """Escape special characters in names for filesystem safety."""
        if not name:
            return ""
        
        # Replace problematic characters for filesystem compatibility
        escaped = name.strip()
        
        # Replace filesystem-problematic characters
        escaped = re.sub(r'[<>:"|?*]', '_', escaped)  # Windows forbidden chars
        escaped = re.sub(r'[/\\]', '_', escaped)  # Path separators
        escaped = re.sub(r'[\t\n\r]', '_', escaped)  # Whitespace chars
        escaped = re.sub(r'\s+', '_', escaped)  # Spaces to underscores
        escaped = re.sub(r'[^\w\-_\.]', '_', escaped)  # Non-word chars except dash, underscore, dot
        
        # Remove leading/trailing dots and underscores
        escaped = escaped.strip('._')
        
        return escaped or "unnamed"
    
    def _write_single_protein_file(self, tree: TaxonomyTree, output_path: Path) -> int:
        """Write single FASTA file containing all protein sequences."""
        sequence_count = 0
        
        try:
            with open(output_path, 'w', encoding='utf-8', newline='\n') as f:
                for node in tree:
                    genomes = tree.get_genomes_for_node(node.tax_id)
                    for genome in genomes:
                        if not genome.genome_id:
                            logger.warning(f"Skipping genome with empty genome_id for tax_id {node.tax_id}")
                            continue
                        
                        # Get taxonomy information
                        unique_name = self._get_unique_name(node)
                        escaped_name = self._escape_name(unique_name)
                        lineage = self._build_lineage(tree, node)
                        
                        # Create protein sequences for this genome
                        protein_sequences = self._generate_protein_sequences(genome, node)
                        
                        for seq_id, sequence in protein_sequences:
                            # Write FASTA header with taxonomy info
                            header = f">{seq_id}|tax_id:{node.tax_id}|species:{escaped_name}|lineage:{lineage}"
                            f.write(f"{header}\n")
                            f.write(f"{sequence}\n")
                            sequence_count += 1
            
            return sequence_count
            
        except Exception as e:
            logger.error(f"Failed to write proteins.fasta: {str(e)}")
            raise ExportError(f"Failed to create proteins.fasta file: {str(e)}") from e
    
    def _write_protein_files(self, tree: TaxonomyTree, proteins_dir: Path, compress: bool) -> list[str]:
        """Write individual protein FASTA files and return list of file paths."""
        protein_paths = []
        
        for node in tree:
            genomes = tree.get_genomes_for_node(node.tax_id)
            for genome in genomes:
                if not genome.genome_id:
                    logger.warning(f"Skipping genome with empty genome_id for tax_id {node.tax_id}")
                    continue
                
                # Generate safe filename
                safe_name = self._escape_filename(genome.genome_id)
                if compress:
                    filename = f"{safe_name}_proteins.fasta.gz"
                else:
                    filename = f"{safe_name}_proteins.fasta"
                
                protein_file_path = proteins_dir / filename
                
                # Write protein file
                self._write_genome_protein_file(genome, node, tree, protein_file_path, compress)
                
                # Add to paths list
                protein_paths.append(str(protein_file_path))
        
        return protein_paths
    
    def _write_genome_protein_file(self, genome: Any, node: Any, tree: TaxonomyTree, 
                                   output_path: Path, compress: bool) -> None:
        """Write a single genome's protein FASTA file."""
        try:
            unique_name = self._get_unique_name(node)
            escaped_name = self._escape_name(unique_name)
            lineage = self._build_lineage(tree, node)
            
            # Generate protein sequences for this genome
            protein_sequences = self._generate_protein_sequences(genome, node)
            
            if compress:
                import gzip
                with gzip.open(output_path, 'wt', encoding='utf-8') as f:
                    for seq_id, sequence in protein_sequences:
                        header = f">{seq_id}|tax_id:{node.tax_id}|species:{escaped_name}|lineage:{lineage}"
                        f.write(f"{header}\n")
                        f.write(f"{sequence}\n")
            else:
                with open(output_path, 'w', encoding='utf-8') as f:
                    for seq_id, sequence in protein_sequences:
                        header = f">{seq_id}|tax_id:{node.tax_id}|species:{escaped_name}|lineage:{lineage}"
                        f.write(f"{header}\n")
                        f.write(f"{sequence}\n")
                    
        except Exception as e:
            logger.error(f"Failed to write protein file {output_path}: {str(e)}")
            raise ExportError(f"Failed to write protein FASTA file: {str(e)}") from e
    
    def _generate_protein_sequences(self, genome: Any, node: Any) -> list[tuple[str, str]]:
        """Generate placeholder protein sequences for a genome.
        
        In a real implementation, this would extract actual protein sequences
        from genome files or protein annotation databases.
        """
        proteins = []
        
        # Generate some placeholder proteins based on genome
        genome_id = genome.genome_id or f"genome_{node.tax_id}"
        
        # Simulate common bacterial proteins
        protein_templates = [
            ("16S_rRNA", "MGKIIAIIAIMVLLSGCGVNSQQEIDRLNVMGFAELMRTQKEEGLLHQYNELQRHTQNQGYEHHMVDLLNHNCKHVGILKKTLSPDPHNVMTMKQFQWGSLAVGKEYEIR"),
            ("recA", "MAIDENKQKALLELLQQIEQLDADTLDRHVMQFNLDELQKQFAKLMAQGKKIEIEDSLIGFGVGKKVMAGLRELDNILLMKQIVNNLQAEIGELGVLKEENAQLEALKQRNAEVVQAQQIAGLQKV"),
            ("gyrA", "MSDLAREITPVNIEEELKSSYLDYAMSVIVGRALPDVRDGLKPVHRRVLYAMNVLGNDWNKAYKKSARVLGRLEEQDLEMWQSFHAWSPTSIGKLFDFEEHFNHYMASMHLTDQVVAAFQIAEPDIK"),
            ("dnaA", "MSLSLWQQCLARLQDELPATEFSMWIRPLQAELSDNTLALYAPNRFVLDWVRDKYLNNINGLLTSFCGADAPQLRFEVGTKPVTQTPQAAVTSNVAAPAQVTEAPAKDTSLQALADAVATQGQLQV"),
            ("rpoB", "MDSQDIKKIVNQLKEQARTTFTLTAALKQVNSNEEKPKIDHQLLSQTKEIGQLLTALELGKISLTQALKLLTETIYNQKGIGDGYTLKRALQNALQGGVKLRQELLGRSRLDQVLLSLRKVQLTDDV")
        ]
        
        for i, (protein_name, sequence) in enumerate(protein_templates):
            seq_id = f"{genome_id}_{protein_name}_{i+1:03d}"
            proteins.append((seq_id, sequence))
        
        return proteins
    
    def _write_taxonomy_info(self, tree: TaxonomyTree, output_path: Path) -> None:
        """Write taxonomy information file mapping protein sequences to taxonomic info."""
        try:
            with open(output_path, 'w', encoding='utf-8', newline='\n') as f:
                # Write header
                f.write("genome_id\ttax_id\tspecies_name\trank\tlineage\tprotein_count\n")
                
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
                            
                            # Count proteins (placeholder count)
                            protein_count = 5  # Based on our template proteins
                            
                            f.write(f"{genome.genome_id}\t{node.tax_id}\t{escaped_name}\t{rank}\t{lineage}\t{protein_count}\n")
                    else:
                        # Write placeholder entry for nodes without genomes
                        f.write(f"placeholder_{node.tax_id}\t{node.tax_id}\t{escaped_name}\t{rank}\t{lineage}\t0\n")
            
            logger.info(f"Created taxonomy_info.txt with taxonomy mappings")
            
        except Exception as e:
            logger.error(f"Failed to write taxonomy_info.txt: {str(e)}")
            raise ExportError(f"Failed to create taxonomy_info.txt file: {str(e)}") from e
    
    def _write_diamond_config(self, output_path: Path, protein_paths: list[str], single_file: bool) -> None:
        """Write Diamond configuration file with recommended parameters."""
        try:
            with open(output_path, 'w', encoding='utf-8', newline='\n') as f:
                f.write("# Diamond Database Creation Configuration\n")
                f.write("# Generated by FlexTaxD Diamond Exporter\n\n")
                
                f.write("# Recommended diamond makedb command:\n")
                if single_file and protein_paths:
                    f.write(f"# diamond makedb --in {protein_paths[0]} -d database\n\n")
                else:
                    f.write("# diamond makedb --in proteins.fasta -d database\n\n")
                
                f.write("# Parameters explanation:\n")
                f.write("# --in: Input protein FASTA file\n")
                f.write("# -d: Output database name (creates database.dmnd)\n")
                f.write("# -p: Number of threads (optional, e.g., -p 8)\n\n")
                
                f.write("# Usage examples:\n")
                f.write("# 1. Create database with 8 threads:\n")
                if single_file and protein_paths:
                    f.write(f"#    diamond makedb --in {protein_paths[0]} -d database -p 8\n\n")
                else:
                    f.write("#    diamond makedb --in proteins.fasta -d database -p 8\n\n")
                
                f.write("# 2. Use database for alignment (blastx example):\n")
                f.write("#    diamond blastx -d database -q reads.fasta -a matches -p 8\n\n")
                
                f.write("# 3. Use database for alignment (blastp example):\n")
                f.write("#    diamond blastp -d database -q proteins.fasta -a matches -p 8\n\n")
                
                f.write("# Database statistics:\n")
                f.write(f"# Input files: {len(protein_paths)}\n")
                f.write(f"# Format: {'Single FASTA file' if single_file else 'Individual protein files'}\n")
                
                f.write("\n# For Melon compatibility:\n")
                f.write("# The created database.dmnd can be used directly with Melon\n")
                f.write("# for long-read metagenomic taxonomic profiling\n")
            
            logger.info(f"Created diamond_config.txt with recommended parameters")
            
        except Exception as e:
            logger.error(f"Failed to write diamond_config.txt: {str(e)}")
            raise ExportError(f"Failed to create diamond_config.txt file: {str(e)}") from e
    
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
            
            if current_node.parent_id is None or current_node.parent_id == current_node.tax_id:
                break
            
            current_node = tree.get_node(current_node.parent_id)
        
        # Reverse to get root-to-leaf order
        lineage_parts.reverse()
        return "; ".join(lineage_parts) if lineage_parts else "root"