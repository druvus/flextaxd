"""Integration tests for purge functionality with real database operations."""

import pytest
import tempfile
import shutil
from pathlib import Path
import sqlite3

from flextaxd.database.sqlite import SQLiteTaxonomyRepository
from flextaxd.core.models import TaxonomyTree, TaxonomyNode, GenomeInfo, TaxonomicRank
from flextaxd.cli.commands.purge import PurgeCommand
from argparse import Namespace


class TestPurgeIntegration:
    """Integration tests for purge functionality with real database."""

    def setup_method(self):
        """Set up test fixtures with real database."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.db_path = self.temp_dir / "test_purge.ftd"
        
        # Create a real database with test data
        self._create_test_database()
        
    def teardown_method(self):
        """Clean up test fixtures."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def _create_test_database(self):
        """Create a real test database with complex taxonomy."""
        tree = TaxonomyTree()
        
        # Create complex taxonomy structure
        #         root(1)
        #        /   |   \
        #   bact(2) arch(3) euk(4)
        #      |      |      |
        #   prot(5)  meth(6) anim(7)
        #   /    \     |      |
        # ecoli(8) sal(9) meta(10) homo(11)
        
        nodes = [
            (1, "root", TaxonomicRank.ROOT, None),
            (2, "Bacteria", TaxonomicRank.SUPERKINGDOM, 1),
            (3, "Archaea", TaxonomicRank.SUPERKINGDOM, 1),
            (4, "Eukaryota", TaxonomicRank.SUPERKINGDOM, 1),
            (5, "Proteobacteria", TaxonomicRank.PHYLUM, 2),
            (6, "Methanobrevibacter", TaxonomicRank.GENUS, 3),
            (7, "Animalia", TaxonomicRank.KINGDOM, 4),
            (8, "Escherichia coli", TaxonomicRank.SPECIES, 5),
            (9, "Salmonella enterica", TaxonomicRank.SPECIES, 5),
            (10, "Methanobrevibacter smithii", TaxonomicRank.SPECIES, 6),
            (11, "Homo sapiens", TaxonomicRank.SPECIES, 7),
        ]
        
        for tax_id, name, rank, parent_id in nodes:
            node = TaxonomyNode(tax_id=tax_id, name=name, rank=rank, parent_id=parent_id)
            tree.add_node(node)
        
        # Create diverse genomes
        genomes = [
            # E. coli - multiple genomes with files
            GenomeInfo(genome_id="ecoli_k12", tax_id=8, file_path="/genomes/ecoli_k12.fasta", 
                      sequence_length=4641652, sequence_type="genome", assembly_accession="GCF_000005825.2", source="NCBI"),
            GenomeInfo(genome_id="ecoli_o157", tax_id=8, file_path="/genomes/ecoli_o157.fasta",
                      sequence_length=5528445, sequence_type="genome", assembly_accession="GCF_000008865.2", source="NCBI"),
            GenomeInfo(genome_id="ecoli_16s", tax_id=8, file_path="/rrna/ecoli_16s.fasta",
                      sequence_length=1542, sequence_type="16S", source="SILVA"),
            
            # Salmonella - genome without file
            GenomeInfo(genome_id="salmonella_meta", tax_id=9, assembly_accession="GCF_000006945.2",
                      sequence_length=4857450, sequence_type="genome", source="NCBI"),
            
            # Methanobrevibacter - with file
            GenomeInfo(genome_id="msmith_genome", tax_id=10, file_path="/archaea/msmith.fasta",
                      sequence_length=1853160, sequence_type="genome", assembly_accession="GCF_000016525.1", source="NCBI"),
            
            # Homo sapiens - metadata only
            GenomeInfo(genome_id="human_chr1", tax_id=11, assembly_accession="GCF_000001405.40",
                      sequence_length=248956422, sequence_type="chromosome", source="NCBI"),
        ]
        
        for genome in genomes:
            tree.add_genome(genome)
        
        # Save to database
        with SQLiteTaxonomyRepository(str(self.db_path)) as repo:
            repo.save_tree(tree)

    def test_purge_with_fasta_files_required(self):
        """Test purge requiring FASTA files."""
        with SQLiteTaxonomyRepository(str(self.db_path)) as repo:
            tree = repo.load_tree()
            
            result = tree.purge_nodes_without_genomes(require_fasta_files=True)
            
            # Should keep lineages with FASTA files:
            # - E. coli lineage: root(1) -> Bacteria(2) -> Proteobacteria(5) -> E.coli(8)
            # - M. smithii lineage: root(1) -> Archaea(3) -> Methanobrevibacter(6) -> M.smithii(10)
            # Should remove: Eukaryota branch, Salmonella
            
            expected_kept = {1, 2, 3, 5, 6, 8, 10}
            remaining_ids = set(tree._nodes.keys())
            assert remaining_ids == expected_kept
            
            assert result["nodes_removed"] == 4  # Eukaryota(4), Animalia(7), Homo(11), Salmonella(9)
            assert result["nodes_after"] == 7
            assert result["genomes_retained"] == 4  # 3 E.coli genomes + 1 M.smithii genome
            
            # Save back to database
            repo.save_tree(tree)
        
        # Verify database integrity after purge
        with SQLiteTaxonomyRepository(str(self.db_path)) as repo:
            reloaded_tree = repo.load_tree()
            assert len(reloaded_tree._nodes) == 7
            assert len(reloaded_tree._genomes) == 4

    def test_purge_allow_metadata_only(self):
        """Test purge allowing metadata-only genomes."""
        with SQLiteTaxonomyRepository(str(self.db_path)) as repo:
            tree = repo.load_tree()
            
            result = tree.purge_nodes_without_genomes(require_fasta_files=False)
            
            # Should keep all nodes with genomes (including metadata-only)
            # All lineages to genome nodes must be preserved, so no nodes removed
            assert result["nodes_removed"] == 0  # All lineages to genome nodes preserved
            assert result["nodes_after"] == 11   # All original nodes kept
            assert result["genomes_retained"] == 6  # All genomes
            
            # All nodes should remain because they're either:
            # 1. Have genomes themselves: 8(E.coli), 9(Salmonella), 10(M.smithii), 11(Homo)
            # 2. Are in lineage paths to genome nodes: 1,2,3,4,5,6,7
            assert 7 in tree._nodes   # Animalia kept (in path to Homo sapiens)
            assert 11 in tree._nodes  # Homo sapiens kept (has metadata genome)

    def test_purge_cli_integration_dry_run(self):
        """Test purge CLI command in dry run mode."""
        command = PurgeCommand()
        args = Namespace(
            database=str(self.db_path),
            dry_run=True,
            force=False,
            allow_metadata_only=False,
            backup=None,
            stats_only=False
        )
        
        result = command.execute(args)
        assert result == 0
        
        # Verify database unchanged after dry run
        with SQLiteTaxonomyRepository(str(self.db_path)) as repo:
            tree = repo.load_tree()
            assert len(tree._nodes) == 11  # Original count
            assert len(tree._genomes) == 6  # Original count

    def test_purge_cli_integration_with_backup(self):
        """Test purge CLI command with backup creation."""
        backup_path = str(self.temp_dir / "backup.ftd")
        command = PurgeCommand()
        args = Namespace(
            database=str(self.db_path),
            dry_run=False,
            force=True,  # Skip confirmation
            allow_metadata_only=False,
            backup=backup_path,
            stats_only=False
        )
        
        result = command.execute(args)
        assert result == 0
        
        # Verify backup was created
        assert Path(backup_path).exists()
        
        # Verify backup contains original data
        with SQLiteTaxonomyRepository(backup_path) as repo:
            backup_tree = repo.load_tree()
            assert len(backup_tree._nodes) == 11
            assert len(backup_tree._genomes) == 6
        
        # Verify main database was purged
        with SQLiteTaxonomyRepository(str(self.db_path)) as repo:
            purged_tree = repo.load_tree()
            assert len(purged_tree._nodes) < 11
            assert len(purged_tree._genomes) <= 6

    def test_purge_database_consistency_checks(self):
        """Test that purged database maintains referential integrity."""
        with SQLiteTaxonomyRepository(str(self.db_path)) as repo:
            tree = repo.load_tree()
            tree.purge_nodes_without_genomes(require_fasta_files=True)
            repo.save_tree(tree)
        
        # Check database schema and constraints
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        # Check that all genomes reference existing nodes
        cursor.execute("""
            SELECT g.genome_id, g.tax_id, n.tax_id 
            FROM genomes g 
            LEFT JOIN nodes n ON g.tax_id = n.tax_id 
            WHERE n.tax_id IS NULL
        """)
        orphaned_genomes = cursor.fetchall()
        assert len(orphaned_genomes) == 0, f"Found orphaned genomes: {orphaned_genomes}"
        
        # Check that all nodes (except root) have existing parents
        cursor.execute("""
            SELECT n1.tax_id, n1.parent_id, n2.tax_id
            FROM nodes n1
            LEFT JOIN nodes n2 ON n1.parent_id = n2.tax_id
            WHERE n1.parent_id IS NOT NULL AND n2.tax_id IS NULL
        """)
        orphaned_nodes = cursor.fetchall()
        assert len(orphaned_nodes) == 0, f"Found orphaned nodes: {orphaned_nodes}"
        
        # Check that tree has exactly one root
        cursor.execute("SELECT COUNT(*) FROM nodes WHERE parent_id IS NULL")
        root_count = cursor.fetchone()[0]
        assert root_count == 1, f"Expected 1 root, found {root_count}"
        
        conn.close()

    def test_purge_preserves_genome_metadata(self):
        """Test that purge preserves all genome metadata for kept genomes."""
        original_genomes = {}
        
        # Capture original genome data
        with SQLiteTaxonomyRepository(str(self.db_path)) as repo:
            tree = repo.load_tree()
            for genome_id, genome in tree._genomes.items():
                original_genomes[genome_id] = {
                    'tax_id': genome.tax_id,
                    'file_path': genome.file_path,
                    'sequence_length': genome.sequence_length,
                    'sequence_type': genome.sequence_type,
                    'assembly_accession': genome.assembly_accession,
                    'source': genome.source
                }
            
            tree.purge_nodes_without_genomes(require_fasta_files=True)
            repo.save_tree(tree)
        
        # Verify preserved genomes have identical metadata
        with SQLiteTaxonomyRepository(str(self.db_path)) as repo:
            purged_tree = repo.load_tree()
            
            for genome_id, genome in purged_tree._genomes.items():
                assert genome_id in original_genomes
                original = original_genomes[genome_id]
                
                assert genome.tax_id == original['tax_id']
                assert genome.file_path == original['file_path']
                assert genome.sequence_length == original['sequence_length']
                assert genome.sequence_type == original['sequence_type']
                assert genome.assembly_accession == original['assembly_accession']
                assert genome.source == original['source']

    def test_purge_with_complex_branching(self):
        """Test purge behavior with complex branching patterns.""" 
        # Add more complex branching to existing database
        with SQLiteTaxonomyRepository(str(self.db_path)) as repo:
            tree = repo.load_tree()
            
            # Add multiple species under Proteobacteria
            additional_nodes = [
                (12, "Enterobacteriaceae", TaxonomicRank.FAMILY, 5),  # Under Proteobacteria
                (13, "Shigella flexneri", TaxonomicRank.SPECIES, 12),
                (14, "Klebsiella pneumoniae", TaxonomicRank.SPECIES, 12),
                (15, "Pseudomonadaceae", TaxonomicRank.FAMILY, 5),  # Another family under Proteobacteria
                (16, "Pseudomonas aeruginosa", TaxonomicRank.SPECIES, 15),
            ]
            
            for tax_id, name, rank, parent_id in additional_nodes:
                node = TaxonomyNode(tax_id=tax_id, name=name, rank=rank, parent_id=parent_id)
                tree.add_node(node)
            
            # Add genome only to Klebsiella
            genome = GenomeInfo(
                genome_id="klebsiella_genome",
                tax_id=14,
                file_path="/genomes/klebsiella.fasta",
                sequence_length=5333942,
                sequence_type="genome",
                assembly_accession="GCF_000240185.1",
                source="NCBI"
            )
            tree.add_genome(genome)
            
            repo.save_tree(tree)
        
        # Perform purge
        with SQLiteTaxonomyRepository(str(self.db_path)) as repo:
            tree = repo.load_tree()
            result = tree.purge_nodes_without_genomes(require_fasta_files=True)
            
            # Should preserve both E. coli and Klebsiella lineages
            # E. coli: root(1) -> Bacteria(2) -> Proteobacteria(5) -> E.coli(8)
            # Klebsiella: root(1) -> Bacteria(2) -> Proteobacteria(5) -> Enterobacteriaceae(12) -> Klebsiella(14)
            # Plus Archaea lineage: root(1) -> Archaea(3) -> Methanobrevibacter(6) -> M.smithii(10)
            
            expected_kept = {1, 2, 3, 5, 6, 8, 10, 12, 14}
            remaining_ids = set(tree._nodes.keys())
            assert remaining_ids == expected_kept
            
            # Should remove: Eukaryota branch, Salmonella, Shigella, Pseudomonadaceae branch
            removed_count = 16 - len(expected_kept)  # 16 total nodes - 9 kept
            assert result["nodes_removed"] == removed_count

    def test_purge_performance_with_realistic_database(self):
        """Test purge performance with realistic database size."""
        # Create larger database with realistic taxonomy structure
        large_db_path = self.temp_dir / "large_test.ftd"
        tree = TaxonomyTree()
        
        # Create root
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT)
        tree.add_node(root)
        
        # Create realistic bacterial taxonomy (500 nodes)
        current_id = 2
        
        # Superkingdom
        bacteria = TaxonomyNode(tax_id=current_id, name="Bacteria", rank=TaxonomicRank.SUPERKINGDOM, parent_id=1)
        tree.add_node(bacteria)
        current_id += 1
        
        # Create 5 phyla with 10 classes each, 2 orders per class, 5 genera per order, 2 species per genus
        phyla_ids = []
        for p in range(5):  # 5 phyla
            phylum_id = current_id
            phylum = TaxonomyNode(tax_id=phylum_id, name=f"Phylum{p}", rank=TaxonomicRank.PHYLUM, parent_id=2)
            tree.add_node(phylum)
            phyla_ids.append(phylum_id)
            current_id += 1
            
            for c in range(2):  # 2 classes per phylum
                class_id = current_id
                class_node = TaxonomyNode(tax_id=class_id, name=f"Class{p}_{c}", rank=TaxonomicRank.CLASS, parent_id=phylum_id)
                tree.add_node(class_node)
                current_id += 1
                
                for o in range(2):  # 2 orders per class
                    order_id = current_id
                    order_node = TaxonomyNode(tax_id=order_id, name=f"Order{p}_{c}_{o}", rank=TaxonomicRank.ORDER, parent_id=class_id)
                    tree.add_node(order_node)
                    current_id += 1
                    
                    for g in range(3):  # 3 genera per order
                        genus_id = current_id
                        genus_node = TaxonomyNode(tax_id=genus_id, name=f"Genus{p}_{c}_{o}_{g}", rank=TaxonomicRank.GENUS, parent_id=order_id)
                        tree.add_node(genus_node)
                        current_id += 1
                        
                        for s in range(3):  # 3 species per genus
                            species_id = current_id
                            species_node = TaxonomyNode(tax_id=species_id, name=f"Species{p}_{c}_{o}_{g}_{s}", rank=TaxonomicRank.SPECIES, parent_id=genus_id)
                            tree.add_node(species_node)
                            current_id += 1
                            
                            # Add genome to every 5th species
                            if species_id % 5 == 0:
                                genome = GenomeInfo(
                                    genome_id=f"genome_{species_id}",
                                    tax_id=species_id,
                                    file_path=f"/genomes/species_{species_id}.fasta",
                                    sequence_length=4000000 + (species_id * 1000),
                                    sequence_type="genome",
                                    source="TEST"
                                )
                                tree.add_genome(genome)
        
        # Save large database
        with SQLiteTaxonomyRepository(str(large_db_path)) as repo:
            repo.save_tree(tree)
        
        initial_nodes = len(tree._nodes)
        initial_genomes = len(tree._genomes)
        
        # Test purge performance
        import time
        start_time = time.time()
        
        with SQLiteTaxonomyRepository(str(large_db_path)) as repo:
            tree = repo.load_tree()
            result = tree.purge_nodes_without_genomes(require_fasta_files=True)
            repo.save_tree(tree)
        
        end_time = time.time()
        
        # Performance should be reasonable (< 2 seconds for ~500 nodes)
        assert end_time - start_time < 2.0
        
        # Verify results
        assert result["nodes_before"] == initial_nodes
        assert result["genomes_retained"] == initial_genomes
        assert result["nodes_after"] < initial_nodes  # Should have removed some nodes
        
        print(f"Large database purge: {initial_nodes} -> {result['nodes_after']} nodes in {end_time - start_time:.3f}s")