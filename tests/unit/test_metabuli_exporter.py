"""Unit tests for Metabuli exporter."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from flextaxd.core.models import TaxonomyTree, TaxonomyNode, TaxonomicRank, GenomeInfo
from flextaxd.core.exceptions import ExportError
from flextaxd.exporters.metabuli import MetabuliExporter


class TestMetabuliExporter:
    """Test Metabuli format exporter."""

    def test_exporter_properties(self):
        """Test exporter basic properties."""
        exporter = MetabuliExporter()
        assert exporter.exporter_name == "metabuli"
        assert ".dmp" in exporter.file_extensions
        assert ".tsv" in exporter.file_extensions
        assert ".txt" in exporter.file_extensions
        assert exporter.requires_directory is True

    def test_export_basic_functionality(self):
        """Test basic export functionality."""
        exporter = MetabuliExporter()
        tree = self._create_test_tree()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(tree, output_path)

            # Should create required files
            names_file = output_path / "names.dmp"
            nodes_file = output_path / "nodes.dmp"
            accession_file = output_path / "accession2taxid.txt"

            assert names_file.exists()
            assert nodes_file.exists()
            assert accession_file.exists()

            # Check basic file content
            names_content = names_file.read_text()
            nodes_content = nodes_file.read_text()
            accession_content = accession_file.read_text()

            # Names.dmp should contain taxa
            assert "1\t|\troot\t|\t\t|\tscientific name\t|\n" in names_content
            assert (
                "562\t|\tEscherichia coli\t|\t\t|\tscientific name\t|\n"
                in names_content
            )

            # Nodes.dmp should contain taxonomic relationships
            assert "1\t|\t1\t|\tno rank\t|" in nodes_content
            assert "562\t|\t2\t|\tspecies\t|" in nodes_content

            # Accession2taxid should contain genome mappings
            assert "accession\taccession.version\ttaxid\tgi\n" in accession_content
            assert "NC_000913\tNC_000913\t562\t0\n" in accession_content

    def test_export_with_merged_file(self):
        """Test export with merged.dmp file creation."""
        exporter = MetabuliExporter()
        tree = self._create_test_tree()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(tree, output_path, include_merged=True)

            merged_file = output_path / "merged.dmp"
            assert merged_file.exists()

            content = merged_file.read_text()
            assert "# merged.dmp - historical taxonomy ID changes" in content
            assert "# Format: old_tax_id | new_tax_id |" in content

    def test_export_without_genomes(self):
        """Test export when no genomes are present."""
        exporter = MetabuliExporter()
        tree = self._create_tree_without_genomes()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(tree, output_path)

            # Should still create names.dmp and nodes.dmp
            names_file = output_path / "names.dmp"
            nodes_file = output_path / "nodes.dmp"
            accession_file = output_path / "accession2taxid.txt"

            assert names_file.exists()
            assert nodes_file.exists()
            # Should not create accession file when no genomes
            assert not accession_file.exists()

    def test_export_with_compression(self):
        """Test export with file compression."""
        exporter = MetabuliExporter()
        tree = self._create_test_tree()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)

            with patch(
                "flextaxd.utils.subprocess_utils.compress_file"
            ) as mock_compress:
                exporter.export(tree, output_path, compress=True)

                # Should call compression for each file
                assert (
                    mock_compress.call_count >= 3
                )  # names.dmp, nodes.dmp, accession2taxid.txt

    def test_name_escaping(self):
        """Test proper escaping of taxonomic names."""
        exporter = MetabuliExporter()
        tree = self._create_tree_with_special_names()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(tree, output_path)

            names_file = output_path / "names.dmp"
            content = names_file.read_text()

            # Should escape special characters
            assert "Special;Name" in content  # Pipe replaced with semicolon
            assert "Tab Name" in content  # Tab replaced with space

    def test_duplicate_name_handling(self):
        """Test handling of duplicate taxonomic names."""
        exporter = MetabuliExporter()
        tree = self._create_tree_with_duplicate_names()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(tree, output_path)

            names_file = output_path / "names.dmp"
            content = names_file.read_text()

            # Should have unique names for duplicates
            assert "Duplicate <100>" in content
            assert "Duplicate <200>" in content

    def test_parent_validation(self):
        """Test parent ID validation and correction."""
        exporter = MetabuliExporter()
        tree = self._create_tree_with_invalid_parents()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(tree, output_path)

            nodes_file = output_path / "nodes.dmp"
            content = nodes_file.read_text()

            # Should correct invalid parent references
            assert "999\t|\t999\t|\t" in content  # Self-parent for orphan

    def test_rank_mapping(self):
        """Test taxonomic rank mapping to NCBI standards."""
        exporter = MetabuliExporter()
        tree = self._create_tree_with_various_ranks()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(tree, output_path)

            nodes_file = output_path / "nodes.dmp"
            content = nodes_file.read_text()

            # Should map ranks correctly
            assert "superkingdom" in content  # Domain -> superkingdom
            assert "no rank" in content  # Custom -> no rank

    def test_accession_extraction(self):
        """Test extraction of additional accessions from genome IDs."""
        exporter = MetabuliExporter()
        tree = self._create_tree_with_complex_accessions()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(tree, output_path)

            accession_file = output_path / "accession2taxid.txt"
            content = accession_file.read_text()

            # Should extract multiple accessions
            assert "NC_000913\tNC_000913\t562\t0\n" in content
            assert "GCF_000005825\tGCF_000005825\t562\t0\n" in content

    def test_validation_method(self):
        """Test export validation method."""
        exporter = MetabuliExporter()
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
            assert results["format"] == "Metabuli taxonomy"

    def test_empty_tree_error(self):
        """Test error handling with empty tree."""
        exporter = MetabuliExporter()
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
        genome = GenomeInfo(
            genome_id="NC_000913",
            tax_id=562,
            sequence_type="genome",
            assembly_accession="GCF_000005825.2",
        )
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

    def _create_tree_with_special_names(self):
        """Create tree with names containing special characters."""
        tree = TaxonomyTree()

        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        tree.add_node(root)

        # Name with pipe character
        special1 = TaxonomyNode(
            tax_id=100, name="Special|Name", rank=TaxonomicRank.GENUS, parent_id=1
        )
        tree.add_node(special1)

        # Name with tab character
        special2 = TaxonomyNode(
            tax_id=200, name="Tab\tName", rank=TaxonomicRank.SPECIES, parent_id=100
        )
        tree.add_node(special2)

        return tree

    def _create_tree_with_duplicate_names(self):
        """Create tree with duplicate taxonomic names."""
        tree = TaxonomyTree()

        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        tree.add_node(root)

        # Two nodes with same name
        dup1 = TaxonomyNode(
            tax_id=100, name="Duplicate", rank=TaxonomicRank.GENUS, parent_id=1
        )
        tree.add_node(dup1)

        dup2 = TaxonomyNode(
            tax_id=200, name="Duplicate", rank=TaxonomicRank.SPECIES, parent_id=1
        )
        tree.add_node(dup2)

        return tree

    def _create_tree_with_invalid_parents(self):
        """Create tree with invalid parent references."""
        tree = TaxonomyTree()

        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        tree.add_node(root)

        # Node with non-existent parent
        orphan = TaxonomyNode(
            tax_id=999, name="Orphan", rank=TaxonomicRank.GENUS, parent_id=888
        )
        tree.add_node(orphan)

        return tree

    def _create_tree_with_various_ranks(self):
        """Create tree with various taxonomic ranks."""
        tree = TaxonomyTree()

        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        tree.add_node(root)

        # Domain rank (should map to superkingdom)
        domain = TaxonomyNode(
            tax_id=2, name="Bacteria", rank=TaxonomicRank.DOMAIN, parent_id=1
        )
        tree.add_node(domain)

        return tree

    def _create_tree_with_complex_accessions(self):
        """Create tree with genomes having complex accession formats."""
        tree = TaxonomyTree()

        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        tree.add_node(root)

        ecoli = TaxonomyNode(
            tax_id=562, name="Escherichia coli", rank=TaxonomicRank.SPECIES, parent_id=1
        )
        tree.add_node(ecoli)

        # Genome with complex ID containing multiple accessions
        genome = GenomeInfo(
            genome_id="NC_000913|GCF_000005825.2", tax_id=562, sequence_type="genome"
        )
        tree.add_genome(genome)

        return tree
