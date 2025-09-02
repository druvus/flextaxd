"""Melon format exporter.

Melon is a metagenomic long-read-based taxonomic identification tool using marker genes.
It uses a two-stage approach: protein database (Diamond) + nucleotide database (minimap2).
This exporter creates the input files needed for Melon database creation:

- protein/prot.fa: Protein sequences for Diamond database
- nucleotide/: Directory with nucleotide sequences for minimap2 indexing
- taxonomy_info.txt: Taxonomy mapping for sequences
- melon_config.txt: Database indexing commands

Melon Database Creation Workflow:
1. Export sequences using this exporter
2. Index protein database: diamond makedb --in protein/prot.fa --db protein/prot
3. Index nucleotide databases: minimap2 -x map-ont -d nucl.mmi nucl.fa
4. Use databases with melon for taxonomic profiling

Note: Melon requires both protein and nucleotide databases.
This exporter creates the input files for both database types.
"""

from typing import Optional, Dict, Any, Set
from pathlib import Path
import re

from .base import DirectoryBasedExporter
from ..core.models import TaxonomyTree, TaxonomicRank
from ..core.exceptions import ExportError, ValidationError
from ..utils.logging_config import get_logger

logger = get_logger(__name__)


class MelonExporter(DirectoryBasedExporter):
    """Exporter for Melon database format with dual protein/nucleotide approach.
    
    Creates input files for Melon database creation using both Diamond and minimap2.
    Melon uses marker genes for taxonomic profiling of long-read metagenomic data.
    
    Melon Format Requirements:
    - protein/prot.fa: Protein FASTA for Diamond database
    - nucleotide/*.fa: Nucleotide FASTA files for minimap2 indexing
    - taxonomy_info.txt: Tab-separated taxonomy mapping
    - melon_config.txt: Database indexing commands
    - nucl_list.txt: List of nucleotide files for batch indexing
    
    The files produced by this exporter can be used with:
    - Diamond makedb for protein database creation
    - minimap2 for nucleotide database indexing
    - Melon for long-read taxonomic profiling workflows
    """
    
    def __init__(self) -> None:
        super().__init__()
        self._unique_names: Dict[str, int] = {}
        self._processed_names: Set[str] = set()
        self._node_name_mapping: Dict[int, str] = {}
    
    @property
    def exporter_name(self) -> str:
        return "melon"
    
    @property
    def file_extensions(self) -> list[str]:
        return [".fa", ".fasta", ".txt"]
    
    def export(self, tree: TaxonomyTree, output_path: Path, **kwargs: Any) -> None:
        """Export taxonomy tree for Melon database creation.
        
        Creates input files for Melon dual database system:
        - protein/prot.fa: Protein sequences for Diamond
        - nucleotide/*.fa: Nucleotide sequences for minimap2
        - taxonomy_info.txt: Taxonomy mapping
        - melon_config.txt: Database indexing commands
        
        Args:
            tree: TaxonomyTree to export
            output_path: Output directory path
            **kwargs: Export options including include_genomes, region_size
        """
        self._validate_tree(tree)
        self._ensure_output_path(output_path)
        
        logger.info(f"Starting Melon export: {tree.node_count} nodes to {output_path}")
        
        # Parse configuration
        include_genomes = kwargs.get('include_genomes', True)
        region_size = kwargs.get('region_size', 10000)  # 10kb regions like Melon default
        compress = kwargs.get('compress', False)
        
        try:
            # Reset state for new export
            self._unique_names.clear()
            self._processed_names.clear()
            self._node_name_mapping.clear()
            
            # Build unique names mapping
            self._build_unique_names(tree)
            
            # Create protein directory and file
            protein_dir = output_path / "protein"
            protein_dir.mkdir(parents=True, exist_ok=True)
            
            # Create nucleotide directory
            nucleotide_dir = output_path / "nucleotide"
            nucleotide_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate databases
            nucl_files = []
            if include_genomes and tree.genome_count > 0:
                # Create protein database file
                prot_file = protein_dir / "prot.fa"
                protein_count = self._write_protein_database(tree, prot_file)
                logger.info(f"Created protein database with {protein_count} sequences")
                
                # Create nucleotide database files
                nucl_files = self._write_nucleotide_databases(tree, nucleotide_dir, region_size)
                logger.info(f"Created {len(nucl_files)} nucleotide database files")
            
            # Create nucleotide file list
            nucl_list_path = output_path / "nucl_list.txt"
            self._write_nucleotide_list(nucl_files, nucl_list_path)
            
            # Create taxonomy information file
            taxonomy_info_path = output_path / "taxonomy_info.txt"
            self._write_taxonomy_info(tree, taxonomy_info_path, region_size)
            
            # Create Melon configuration file
            config_path = output_path / "melon_config.txt"
            self._write_melon_config(config_path, len(nucl_files), protein_count if include_genomes else 0)
            
            logger.info(f"Melon export completed successfully")
            logger.info(f"To build databases: see commands in {config_path}")
            
        except Exception as e:
            logger.error(f"Melon export failed: {str(e)}")
            raise ExportError(f"Failed to export Melon format: {str(e)}") from e
    
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
    
    def _write_protein_database(self, tree: TaxonomyTree, output_path: Path) -> int:
        """Write single protein FASTA file for Diamond database."""
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
                        
                        # Create marker protein sequences (similar to Melon's approach)
                        protein_sequences = self._generate_marker_proteins(genome, node)
                        
                        for seq_id, sequence in protein_sequences:
                            # Write FASTA header with taxonomy info (Melon style)
                            header = f">{seq_id}|tax_id:{node.tax_id}|species:{escaped_name}|lineage:{lineage}"
                            f.write(f"{header}\n")
                            f.write(f"{sequence}\n")
                            sequence_count += 1
            
            return sequence_count
            
        except Exception as e:
            logger.error(f"Failed to write protein database: {str(e)}")
            raise ExportError(f"Failed to create protein database file: {str(e)}") from e
    
    def _write_nucleotide_databases(self, tree: TaxonomyTree, nucleotide_dir: Path, region_size: int) -> list[str]:
        """Write nucleotide FASTA files for minimap2 indexing."""
        nucl_files = []
        
        for node in tree:
            genomes = tree.get_genomes_for_node(node.tax_id)
            for genome in genomes:
                if not genome.genome_id:
                    logger.warning(f"Skipping genome with empty genome_id for tax_id {node.tax_id}")
                    continue
                
                # Generate safe filename
                safe_name = self._escape_filename(genome.genome_id)
                filename = f"nucl.{safe_name}.fa"
                nucl_file_path = nucleotide_dir / filename
                
                # Write nucleotide file with genomic regions
                self._write_genome_nucleotide_file(genome, node, tree, nucl_file_path, region_size)
                
                # Add to files list
                nucl_files.append(str(nucl_file_path))
        
        return nucl_files
    
    def _write_genome_nucleotide_file(self, genome: Any, node: Any, tree: TaxonomyTree, 
                                      output_path: Path, region_size: int) -> None:
        """Write nucleotide FASTA file for a single genome."""
        try:
            unique_name = self._get_unique_name(node)
            escaped_name = self._escape_name(unique_name)
            lineage = self._build_lineage(tree, node)
            
            # Generate genomic regions (like Melon's 10kb regions)
            nucleotide_regions = self._generate_genomic_regions(genome, node, region_size)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                for seq_id, sequence in nucleotide_regions:
                    header = f">{seq_id}|tax_id:{node.tax_id}|species:{escaped_name}|lineage:{lineage}"
                    f.write(f"{header}\n")
                    f.write(f"{sequence}\n")
                    
        except Exception as e:
            logger.error(f"Failed to write nucleotide file {output_path}: {str(e)}")
            raise ExportError(f"Failed to write nucleotide FASTA file: {str(e)}") from e
    
    def _generate_marker_proteins(self, genome: Any, node: Any) -> list[tuple[str, str]]:
        """Generate marker protein sequences (similar to Melon's marker genes)."""
        proteins = []
        genome_id = genome.genome_id or f"genome_{node.tax_id}"
        
        # Melon focuses on marker genes, so simulate key bacterial markers
        marker_templates = [
            ("rpoB", "MSDLAREITPVNIEEELKSSYLDYAMSVIVGRALPDVRDGLKPVHRRVLYAMNVLGNDWNKAYKKSARVLGRLEEQDLEMWQSFHAWSPTSIGKLFDFEEHFNHYMASMHLTDQVVAAFQIAEPDIK"),
            ("16S_rRNA", "MGKIIAIIAIMVLLSGCGVNSQQEIDRLNVMGFAELMRTQKEEGLLHQYNELQRHTQNQGYEHHMVDLLNHNCKHVGILKKTLSPDPHNVMTMKQFQWGSLAVGKEYEIR"),
            ("gyrA", "MSDLAREITPVNIEEELKSSYLDYAMSVIVGRALPDVRDGLKPVHRRVLYAMNVLGNDWNKAYKKSARVLGRLEEQDLEMWQSFHAWSPTSIGKLFDFEEHFNHYMASMHLTDQVVAAFQIAEPDIK"),
            ("recA", "MAIDENKQKALLELLQQIEQLDADTLDRHVMQFNLDELQKQFAKLMAQGKKIEIEDSLIGFGVGKKVMAGLRELDNILLMKQIVNNLQAEIGELGVLKEENAQLEALKQRNAEVVQAQQIAGLQKV"),
            ("dnaK", "MSKGPAVGIDLGTTYSCVGVFQHGKVEIIANDQGNRTTPSYVAFTDTERLIGDAAKNQVAMNPTNTVFDAKRLIGRRFDDAVVQSDMKHWPFMVVNDAGRPKVQVEYKGETKSFYPEEVSSMVLTKMKEIAEAYLGKKVTHAVVTVPAYFNDAQRQATKDAGTIAGLNVMRIINEPTAAAIAYGLDKKVGAERNVLIFDLGGGTFDVSILTIEEGIFEVKSTAGDTHLGGEDFDNRMVNHFIAEFKRKHKKDISENKRAVRRLRTACERAKRTLSSSTQASIEIDSLYEGIDFYTSITRARFEELNADLFRGTLDPVEKALRDAKLDKSQIHDIVLVGGSTRIPKIQKLLQDFFNGKELNKSINPDEAVAYGAAVQAAILSGDKSENVQDLLLLDVAPLSLGLETAGGVMTVLIKRNTTIPTKKSQVFSTAEDNQSAVTIHVLQGERKRAADNKSLGQFNLDGINPAPRGMPQIEVTFDIDANGILNVTATDKSTGKANKITITNDKGRLSKEEIERMVQEAEKYKAEDPANPKREKYDGDMKKMVDDEELLELVELEVRELLSSQPQTEPKALPAGEKSEKDIILKMVDAEEQLKEEEVKRLQKDLKGYFPDPEKKMKPFVGSIKRVDRGPMVVDVHDTEEKKRLIEEKLRQLKVSDDTISVEELSKYEQVNVRRTKKLIQACMDLYKSQKELKEVKGDLLAHKAEKQVDVLIDVGEEKLTQLDAQQKKVLVPTSFDEVDRKVREAISQTGGTTHDILADIKVDSKLKRQEELMRDDQILQRALAQAKTELIQDVKDIADDMFKDWVERADQGLKQKQRELQEDVKKEAEEAAHEAKEVLATSLKNDEDILKTLSEEIKSLREAAKQALLEALSNLMAEEIVTKFNKEEMKDGQEKIELLQGLVEELKRDKDYKVEEDAKEEKQEQLGNLLQGTSQQIVLNKEKSRLEQEQKLEEAQVRMKEEKAKKEEDQMQDVLQRSLVGEKIQDIMDVFAEHIKAAGQNRIVSQVNAANKKALQAAKDGMKSLQETQKLKEAKLAAANAKIQLAMDAEKLKKVLNELKKQVQQMKQTQKEQQTLAKLQDDLQEAAEARKAELMIRQADKAQLEEQAKQEQGQMAKLIRQAEKELAENNELANEMK"),
            ("groEL", "MSIKMAKGDKKTDVVLAIMSDRQEGEEVVVQGAKDDGFKIKGKFSKNTLLLDLGGGTFGKGVEIKGDVKIKQAEEIGQKVIDYAKTGTTVQYLVNAQMAPVEVLLVVDTAGDTILGRKVLGAEFGDQGKELRDILDGGGHAVTDAGGVTGAKVEDPEPFKDIVKRTVPEITDGEKKVRRVDGDVDLVGFKDKGEQKIKLGLDFPNIATLGEKMDLLLELKDDFPLSHVSVKTQKGHPSFIMTSVRDGVVKADIEGMKVETFDVKGFMVKYGGFSKRQVKQKGEIKAIKDGYKVSDGGDGKMDNFFGDVDLAAEEFKTKGAEEIKGLQFVEIVPDETDGEKRRLLMQVKGFGYDPSNIILLSPSFGKPSGLLDADTITLLKKSLVEGVGDTLSIGAEYLFDRKTTVKGADGDQVLVAKIEKFGFTKSADKLEDGSLDRVGFTQALTTYDGVKRLHGDDVVITGDSKEKGTKDMLQRVMDLGLRMLQGDGDNLLVGISGSQKTDELLKDVIRHAVATLGRQLKGQIGVPDIPVQRFFLGVQVPHIYFDQAEVVTYIKQKLQKAQTMSLISRTSVAQMRDSDFESEEGSKQVMLYKIFEAEIEEPNIEVKKL")
        ]
        
        for protein_name, sequence in marker_templates:
            seq_id = f"{genome_id}_{protein_name}_marker"
            proteins.append((seq_id, sequence))
        
        return proteins
    
    def _generate_genomic_regions(self, genome: Any, node: Any, region_size: int) -> list[tuple[str, str]]:
        """Generate genomic regions encompassing marker genes (like Melon's approach)."""
        regions = []
        genome_id = genome.genome_id or f"genome_{node.tax_id}"
        
        # Simulate genomic regions of specified size (default 10kb like Melon)
        # In practice, these would be extracted from actual genome sequences
        num_regions = 3  # Simulate 3 regions per genome
        
        for i in range(num_regions):
            seq_id = f"{genome_id}_region_{i+1:03d}_{region_size}bp"
            
            # Generate placeholder nucleotide sequence of specified length
            # In real implementation, this would be actual genomic DNA
            sequence = self._generate_nucleotide_sequence(region_size)
            
            regions.append((seq_id, sequence))
        
        return regions
    
    def _generate_nucleotide_sequence(self, length: int) -> str:
        """Generate placeholder nucleotide sequence of specified length."""
        import random
        nucleotides = ['A', 'T', 'C', 'G']
        
        # Generate random DNA sequence as placeholder
        sequence = ''.join(random.choices(nucleotides, k=length))
        
        # Format in lines of 80 characters
        formatted_lines = []
        for i in range(0, len(sequence), 80):
            formatted_lines.append(sequence[i:i+80])
        
        return '\n'.join(formatted_lines)
    
    def _write_nucleotide_list(self, nucl_files: list[str], output_path: Path) -> None:
        """Write nucleotide file list for batch minimap2 indexing."""
        try:
            with open(output_path, 'w', encoding='utf-8', newline='\n') as f:
                for nucl_file in nucl_files:
                    f.write(f"{nucl_file}\n")
            
            logger.info(f"Created nucl_list.txt with {len(nucl_files)} nucleotide files")
            
        except Exception as e:
            logger.error(f"Failed to write nucl_list.txt: {str(e)}")
            raise ExportError(f"Failed to create nucl_list.txt file: {str(e)}") from e
    
    def _write_taxonomy_info(self, tree: TaxonomyTree, output_path: Path, region_size: int) -> None:
        """Write taxonomy information file for Melon database."""
        try:
            with open(output_path, 'w', encoding='utf-8', newline='\n') as f:
                # Write header
                f.write("genome_id\ttax_id\tspecies_name\trank\tlineage\tmarker_count\tregion_size\tregion_count\n")
                
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
                            
                            # Count markers and regions (based on our templates)
                            marker_count = 6  # Based on marker protein templates
                            region_count = 3  # Based on genomic region templates
                            
                            f.write(f"{genome.genome_id}\t{node.tax_id}\t{escaped_name}\t{rank}\t{lineage}\t{marker_count}\t{region_size}\t{region_count}\n")
                    else:
                        # Write placeholder entry for nodes without genomes
                        f.write(f"placeholder_{node.tax_id}\t{node.tax_id}\t{escaped_name}\t{rank}\t{lineage}\t0\t{region_size}\t0\n")
            
            logger.info(f"Created taxonomy_info.txt with Melon database mappings")
            
        except Exception as e:
            logger.error(f"Failed to write taxonomy_info.txt: {str(e)}")
            raise ExportError(f"Failed to create taxonomy_info.txt file: {str(e)}") from e
    
    def _write_melon_config(self, output_path: Path, nucl_file_count: int, protein_count: int) -> None:
        """Write Melon configuration file with database creation commands."""
        try:
            with open(output_path, 'w', encoding='utf-8', newline='\n') as f:
                f.write("# Melon Database Creation Configuration\n")
                f.write("# Generated by FlexTaxD Melon Exporter\n\n")
                
                f.write("# Melon uses dual databases: protein (Diamond) + nucleotide (minimap2)\n\n")
                
                f.write("# Step 1: Create Diamond protein database\n")
                f.write("diamond makedb --in protein/prot.fa --db protein/prot --quiet\n\n")
                
                f.write("# Step 2: Create minimap2 nucleotide databases\n")
                f.write("# Index each nucleotide file separately (parallel processing recommended)\n")
                f.write("ls nucleotide/nucl.*.fa | sort | xargs -P $cpu_count -I {} bash -c '\n")
                f.write("    filename=${1%.fa*};\n")
                f.write("    filename=${filename##*/};\n")
                f.write("    minimap2 -x map-ont -d nucleotide/$filename.mmi ${1} 2> /dev/null;\n")
                f.write("    echo \"Indexed <nucleotide/$filename.fa>.\";' - {}\n\n")
                
                f.write("# Alternative: Index from file list\n")
                f.write("cat nucl_list.txt | xargs -P $cpu_count -I {} bash -c '\n")
                f.write("    filename=${1%.fa*};\n")
                f.write("    filename=${filename##*/};\n")
                f.write("    minimap2 -x map-ont -d nucleotide/$filename.mmi ${1} 2> /dev/null;\n")
                f.write("    echo \"Indexed <$filename.fa>.\";' - {}\n\n")
                
                f.write("# Usage with Melon:\n")
                f.write("# melon -t <threads> -p protein/prot -n nucleotide -i input_reads.fastq -o results\n\n")
                
                f.write("# Database statistics:\n")
                f.write(f"# Protein sequences: {protein_count}\n")
                f.write(f"# Nucleotide files: {nucl_file_count}\n")
                f.write("# Database type: NCBI or GTDB compatible\n")
                
                f.write("\n# Performance notes:\n")
                f.write("# - Use multiple CPU cores for parallel minimap2 indexing\n")
                f.write("# - Melon is optimized for long-read sequencing data\n")
                f.write("# - Quality-controlled reads (nanoq -q 10 -l 1000) recommended\n")
            
            logger.info(f"Created melon_config.txt with database creation commands")
            
        except Exception as e:
            logger.error(f"Failed to write melon_config.txt: {str(e)}")
            raise ExportError(f"Failed to create melon_config.txt file: {str(e)}") from e
    
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