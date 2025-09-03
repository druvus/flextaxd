"""Unit tests for MMseqs2 exporter."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from flextaxd.core.models import TaxonomyTree, TaxonomyNode, TaxonomicRank, GenomeInfo
from flextaxd.core.exceptions import ExportError
from flextaxd.exporters.mmseqs2 import MMseqs2Exporter


class TestMMseqs2Exporter:
    """Test MMseqs2 format exporter."""

    def test_exporter_properties(self):
        """Test exporter basic properties."""
        exporter = MMseqs2Exporter()
        assert exporter.exporter_name == "mmseqs2"
        assert ".dmp" in exporter.file_extensions
        assert ".txt" in exporter.file_extensions
        assert ".tsv" in exporter.file_extensions
        assert exporter.requires_directory is True

    def test_export_basic_functionality(self):
        """Test basic export functionality."""
        exporter = MMseqs2Exporter()
        tree = self._create_test_tree()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(tree, output_path)

            # Should create required files
            names_file = output_path / "names.dmp"
            nodes_file = output_path / "nodes.dmp"
            accession_file = output_path / "accession2taxid.txt"
            mapping_file = output_path / "taxonomy_mapping.tsv"
            config_file = output_path / "mmseqs2_config.txt"

            assert names_file.exists()
            assert nodes_file.exists()
            assert accession_file.exists()
            assert mapping_file.exists()
            assert config_file.exists()

            # Check basic file content
            names_content = names_file.read_text()
            nodes_content = nodes_file.read_text()
            accession_content = accession_file.read_text()
            mapping_content = mapping_file.read_text()
            config_content = config_file.read_text()

            # Names.dmp should contain taxa
            assert "1\t|\troot\t|\t\t|\tscientific name\t|\n" in names_content
            assert (
                "562\t|\tEscherichia coli\t|\t\t|\tscientific name\t|\n"
                in names_content
            )

            # Should include common names for known bacteria
            assert "common name" in names_content

            # Nodes.dmp should contain taxonomic relationships
            assert "1\t|\t1\t|\tno rank\t|" in nodes_content
            assert "562\t|\t2\t|\tspecies\t|" in nodes_content

            # Accession2taxid should contain genome mappings
            assert "accession\taccession.version\ttaxid\tgi\n" in accession_content
            assert "NC_000913\tNC_000913\t562\t0\n" in accession_content

            # Taxonomy mapping should contain enhanced information
            assert "accession\ttaxid\tlineage\trank\tlca_level\n" in mapping_content
            assert "NC_000913\t562\t" in mapping_content

            # Config file should contain usage instructions
            assert "# MMseqs2 Taxonomy Database Configuration" in config_content
            assert "mmseqs createtaxdb" in config_content
            assert "mmseqs taxonomy" in config_content

    def test_export_without_genomes(self):
        """Test export when no genomes are present."""
        exporter = MMseqs2Exporter()
        tree = self._create_tree_without_genomes()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(tree, output_path)

            # Should create names.dmp and nodes.dmp
            names_file = output_path / "names.dmp"
            nodes_file = output_path / "nodes.dmp"
            config_file = output_path / "mmseqs2_config.txt"

            assert names_file.exists()
            assert nodes_file.exists()
            assert config_file.exists()

            # Should not create sequence mapping files
            accession_file = output_path / "accession2taxid.txt"
            mapping_file = output_path / "taxonomy_mapping.tsv"
            assert not accession_file.exists()
            assert not mapping_file.exists()

    def test_export_with_protein_filter(self):
        """Test export with protein sequence type filter."""
        exporter = MMseqs2Exporter()
        tree = self._create_tree_with_mixed_sequences()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(tree, output_path, sequence_type="protein")

            accession_file = output_path / "accession2taxid.txt"
            content = accession_file.read_text()

            # Should include protein sequences only
            assert "NP_414542\tNP_414542\t562\t0\n" in content
            # Should not include nucleotide sequences
            assert "NC_000913" not in content

    def test_export_with_nucleotide_filter(self):
        """Test export with nucleotide sequence type filter."""
        exporter = MMseqs2Exporter()
        tree = self._create_tree_with_mixed_sequences()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(tree, output_path, sequence_type="nucleotide")

            accession_file = output_path / "accession2taxid.txt"
            content = accession_file.read_text()

            # Should include nucleotide sequences only
            assert "NC_000913\tNC_000913\t562\t0\n" in content
            # Should not include protein sequences
            assert "NP_414542" not in content

    def test_export_without_lca_mapping(self):
        """Test export without LCA mapping creation."""
        exporter = MMseqs2Exporter()
        tree = self._create_test_tree()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(tree, output_path, create_lca_mapping=False)

            # Should not create taxonomy mapping file
            mapping_file = output_path / "taxonomy_mapping.tsv"
            assert not mapping_file.exists()

            # Should still create other files
            names_file = output_path / "names.dmp"
            nodes_file = output_path / "nodes.dmp"
            assert names_file.exists()
            assert nodes_file.exists()

    def test_export_with_compression(self):
        """Test export with file compression."""
        exporter = MMseqs2Exporter()
        tree = self._create_test_tree()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)

            with patch(
                "flextaxd.utils.subprocess_utils.compress_file"
            ) as mock_compress:
                exporter.export(tree, output_path, compress=True)

                # Should call compression for multiple files
                assert mock_compress.call_count >= 3

    def test_common_name_generation(self):
        """Test generation of common names for well-known organisms."""
        exporter = MMseqs2Exporter()
        tree = self._create_tree_with_known_bacteria()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(tree, output_path)

            names_file = output_path / "names.dmp"
            content = names_file.read_text()

            # Should add common names for Escherichia
            assert "Escherichia sp.\t|\t\t|\tcommon name\t|" in content

    def test_genetic_code_assignment(self):
        """Test genetic code assignment in nodes.dmp."""
        exporter = MMseqs2Exporter()
        tree = self._create_tree_with_bacteria_archaea()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(tree, output_path)

            nodes_file = output_path / "nodes.dmp"
            content = nodes_file.read_text()

            # Bacteria should use genetic code 11
            bacteria_line = [
                line
                for line in content.split("\n")
                if "Bacteria" in line and "2\t|" in line
            ][0]
            assert "\t|\t11\t|" in bacteria_line

    def test_division_id_assignment(self):
        """Test division ID assignment for different taxa."""
        exporter = MMseqs2Exporter()
        tree = self._create_tree_with_various_taxa()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(tree, output_path)

            nodes_file = output_path / "nodes.dmp"
            content = nodes_file.read_text()

            # Different taxa should get appropriate division IDs
            assert "\t|\t0\t|" in content  # Default division

    def test_taxonomic_lineage_generation(self):
        """Test taxonomic lineage generation for LCA operations."""
        exporter = MMseqs2Exporter()
        tree = self._create_hierarchical_tree()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(tree, output_path)

            mapping_file = output_path / "taxonomy_mapping.tsv"
            content = mapping_file.read_text()

            # Should contain lineage information
            assert "1;2;561;562" in content  # Full lineage from root to species

    def test_lca_level_calculation(self):
        """Test LCA level calculation."""
        exporter = MMseqs2Exporter()
        tree = self._create_hierarchical_tree()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(tree, output_path)

            mapping_file = output_path / "taxonomy_mapping.tsv"
            content = mapping_file.read_text()

            # Species level should have higher LCA level than genus
            lines = [line for line in content.split("\n") if "NC_000913" in line]
            assert len(lines) > 0
            # LCA level should be present in the mapping
            assert "\t3\n" in content or "\t2\n" in content  # Some LCA level

    def test_mmseqs2_accession_extraction(self):
        """Test MMseqs2-specific accession extraction."""
        exporter = MMseqs2Exporter()
        tree = self._create_tree_with_complex_accessions()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(tree, output_path)

            accession_file = output_path / "accession2taxid.txt"
            content = accession_file.read_text()

            # Should extract MMseqs2-compatible accessions
            lines = content.strip().split("\n")
            accession_lines = [
                line for line in lines if not line.startswith("accession")
            ]

            # Should have multiple mappings from complex accession
            assert len(accession_lines) >= 2

    def test_config_file_generation(self):
        """Test MMseqs2 configuration file generation."""
        exporter = MMseqs2Exporter()
        tree = self._create_test_tree()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(tree, output_path)

            config_file = output_path / "mmseqs2_config.txt"
            content = config_file.read_text()

            # Should contain usage instructions
            assert "mmseqs createdb" in content
            assert "mmseqs createtaxdb" in content
            assert "mmseqs taxonomy" in content
            assert "mmseqs taxonomyreport" in content

            # Should contain statistics
            assert f"Total nodes: {tree.node_count}" in content
            assert f"Total genomes: {tree.genome_count}" in content

    def test_rank_mapping_for_mmseqs2(self):
        """Test rank mapping optimized for MMseqs2."""
        exporter = MMseqs2Exporter()
        tree = self._create_tree_with_various_ranks()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(tree, output_path)

            nodes_file = output_path / "nodes.dmp"
            content = nodes_file.read_text()

            # Should map ranks correctly for MMseqs2
            assert "superkingdom" in content  # Domain -> superkingdom
            assert "no rank" in content  # Custom -> no rank

    def test_validation_method(self):
        """Test export validation method."""
        exporter = MMseqs2Exporter()
        tree = self._create_test_tree()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(tree, output_path)

            # Validate export
            results = exporter.validate_export(output_path)

            assert results["valid"] is True
            assert "names.dmp" in results["files_created"]
            assert "nodes.dmp" in results["files_created"]
            assert "accession2taxid.txt" in results["files_created"]
            assert "taxonomy_mapping.tsv" in results["files_created"]
            assert "mmseqs2_config.txt" in results["files_created"]
            assert results["format"] == "MMseqs2 createtaxdb"

    def test_empty_tree_error(self):
        """Test error handling with empty tree."""
        exporter = MMseqs2Exporter()
        empty_tree = TaxonomyTree()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)

            with pytest.raises(ExportError, match="Cannot export empty taxonomy tree"):
                exporter.export(empty_tree, output_path)

    def _create_test_tree(self):
        """Create test taxonomy tree with genomes."""
        tree = TaxonomyTree()

        # Add root
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        tree.add_node(root)

        # Add bacteria
        bacteria = TaxonomyNode(
            tax_id=2, name="Bacteria", rank=TaxonomicRank.SUPERKINGDOM, parent_id=1
        )
        tree.add_node(bacteria)

        # Add E. coli
        ecoli = TaxonomyNode(
            tax_id=562, name="Escherichia coli", rank=TaxonomicRank.SPECIES, parent_id=2
        )
        tree.add_node(ecoli)

        # Add genome
        genome = GenomeInfo(genome_id="NC_000913", tax_id=562, sequence_type="genome")
        tree.add_genome(genome)

        return tree

    def _create_tree_without_genomes(self):
        """Create tree without genomes."""
        tree = TaxonomyTree()

        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        tree.add_node(root)

        bacteria = TaxonomyNode(
            tax_id=2, name="Bacteria", rank=TaxonomicRank.SUPERKINGDOM, parent_id=1
        )
        tree.add_node(bacteria)

        return tree

    def _create_tree_with_mixed_sequences(self):
        """Create tree with mixed sequence types."""
        tree = TaxonomyTree()

        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        tree.add_node(root)

        ecoli = TaxonomyNode(
            tax_id=562, name="Escherichia coli", rank=TaxonomicRank.SPECIES, parent_id=1
        )
        tree.add_node(ecoli)

        # Add different sequence types
        genome = GenomeInfo("NC_000913", 562, sequence_type="genome")
        tree.add_genome(genome)

        protein = GenomeInfo("NP_414542", 562, sequence_type="protein")
        tree.add_genome(protein)

        return tree

    def _create_tree_with_known_bacteria(self):
        """Create tree with well-known bacterial species."""
        tree = TaxonomyTree()

        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        tree.add_node(root)

        # Escherichia (should get common name)
        ecoli = TaxonomyNode(
            tax_id=562, name="Escherichia coli", rank=TaxonomicRank.SPECIES, parent_id=1
        )
        tree.add_node(ecoli)

        return tree

    def _create_tree_with_bacteria_archaea(self):
        """Create tree with both Bacteria and Archaea."""
        tree = TaxonomyTree()

        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        tree.add_node(root)

        bacteria = TaxonomyNode(
            tax_id=2, name="Bacteria", rank=TaxonomicRank.SUPERKINGDOM, parent_id=1
        )
        tree.add_node(bacteria)

        archaea = TaxonomyNode(
            tax_id=3, name="Archaea", rank=TaxonomicRank.SUPERKINGDOM, parent_id=1
        )
        tree.add_node(archaea)

        return tree

    def _create_tree_with_various_taxa(self):
        """Create tree with various taxonomic groups."""
        tree = TaxonomyTree()

        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        tree.add_node(root)

        bacteria = TaxonomyNode(
            tax_id=2, name="Bacteria", rank=TaxonomicRank.SUPERKINGDOM, parent_id=1
        )
        tree.add_node(bacteria)

        virus = TaxonomyNode(
            tax_id=10239, name="Viruses", rank=TaxonomicRank.SUPERKINGDOM, parent_id=1
        )
        tree.add_node(virus)

        return tree

    def _create_hierarchical_tree(self):
        """Create hierarchical tree for lineage testing."""
        tree = TaxonomyTree()

        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        tree.add_node(root)

        bacteria = TaxonomyNode(
            tax_id=2, name="Bacteria", rank=TaxonomicRank.SUPERKINGDOM, parent_id=1
        )
        tree.add_node(bacteria)

        genus = TaxonomyNode(
            tax_id=561, name="Escherichia", rank=TaxonomicRank.GENUS, parent_id=2
        )
        tree.add_node(genus)

        species = TaxonomyNode(
            tax_id=562,
            name="Escherichia coli",
            rank=TaxonomicRank.SPECIES,
            parent_id=561,
        )
        tree.add_node(species)

        # Add genome
        genome = GenomeInfo("NC_000913", 562, sequence_type="genome")
        tree.add_genome(genome)

        return tree

    def _create_tree_with_complex_accessions(self):
        """Create tree with complex genome accessions."""
        tree = TaxonomyTree()

        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        tree.add_node(root)

        ecoli = TaxonomyNode(
            tax_id=562, name="Escherichia coli", rank=TaxonomicRank.SPECIES, parent_id=1
        )
        tree.add_node(ecoli)

        # Complex accession with multiple identifiers
        genome = GenomeInfo(
            genome_id="NC_000913.3|GCF_000005825.2", tax_id=562, sequence_type="genome"
        )
        tree.add_genome(genome)

        return tree

    def _create_tree_with_various_ranks(self):
        """Create tree with various taxonomic ranks."""
        tree = TaxonomyTree()

        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        tree.add_node(root)

        domain = TaxonomyNode(
            tax_id=2, name="Bacteria", rank=TaxonomicRank.DOMAIN, parent_id=1
        )
        tree.add_node(domain)

        return tree
