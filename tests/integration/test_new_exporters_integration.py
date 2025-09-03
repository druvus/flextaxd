"""Integration tests for new exporters via CLI."""

import pytest
import tempfile
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

from flextaxd.core.models import TaxonomyTree, TaxonomyNode, TaxonomicRank, GenomeInfo
from flextaxd.database.sqlite import SQLiteTaxonomyRepository
from flextaxd.cli.commands.export import ExportCommand


class TestNewExportersIntegration:
    """Integration tests for new exporters via CLI."""

    def test_metabuli_cli_export(self):
        """Test Metabuli export via CLI command."""
        # Create test database
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.ftd"
            output_path = Path(tmp_dir) / "metabuli_output"

            # Create test data in database
            tree = self._create_comprehensive_test_tree()
            with SQLiteTaxonomyRepository(str(db_path)) as repo:
                repo.save_tree(tree)

            # Test CLI export
            cmd = ExportCommand()
            args = Mock()
            args.database = str(db_path)
            args.format = "metabuli"
            args.output = str(output_path)
            args.compress = False
            args.include_genomes = True
            args.include_merged = True
            args.names_file = "names.dmp"
            args.nodes_file = "nodes.dmp"

            result = cmd.execute(args)

            assert result == 0
            assert output_path.exists()
            assert (output_path / "names.dmp").exists()
            assert (output_path / "nodes.dmp").exists()
            assert (output_path / "merged.dmp").exists()
            assert (output_path / "accession2taxid.txt").exists()

    def test_metacache_cli_export_ncbi_format(self):
        """Test MetaCache NCBI format export via CLI."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.ftd"
            output_path = Path(tmp_dir) / "metacache_output"

            tree = self._create_comprehensive_test_tree()
            with SQLiteTaxonomyRepository(str(db_path)) as repo:
                repo.save_tree(tree)

            cmd = ExportCommand()
            args = Mock()
            args.database = str(db_path)
            args.format = "metacache"
            args.output = str(output_path)
            args.compress = False
            args.include_genomes = True
            args.format_type = "ncbi_taxonomy"
            args.names_file = "names.dmp"
            args.nodes_file = "nodes.dmp"

            result = cmd.execute(args)

            assert result == 0
            assert output_path.exists()
            assert (output_path / "names.dmp").exists()
            assert (output_path / "nodes.dmp").exists()

    def test_metacache_cli_export_assembly_summary(self):
        """Test MetaCache assembly summary format export via CLI."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.ftd"
            output_path = Path(tmp_dir) / "metacache_output"

            tree = self._create_comprehensive_test_tree()
            with SQLiteTaxonomyRepository(str(db_path)) as repo:
                repo.save_tree(tree)

            cmd = ExportCommand()
            args = Mock()
            args.database = str(db_path)
            args.format = "metacache"
            args.output = str(output_path)
            args.compress = False
            args.include_genomes = True
            args.format_type = "assembly_summary"
            args.names_file = "names.dmp"
            args.nodes_file = "nodes.dmp"

            result = cmd.execute(args)

            assert result == 0
            assert output_path.exists()
            assert (output_path / "assembly_summary.txt").exists()

            # Check assembly summary content
            content = (output_path / "assembly_summary.txt").read_text()
            assert "# assembly_accession\tbioproject\tbiosample\ttaxid" in content
            assert "GCF_000005825.2" in content

    def test_mmseqs2_cli_export(self):
        """Test MMseqs2 export via CLI command."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.ftd"
            output_path = Path(tmp_dir) / "mmseqs2_output"

            tree = self._create_comprehensive_test_tree()
            with SQLiteTaxonomyRepository(str(db_path)) as repo:
                repo.save_tree(tree)

            cmd = ExportCommand()
            args = Mock()
            args.database = str(db_path)
            args.format = "mmseqs2"
            args.output = str(output_path)
            args.compress = False
            args.include_genomes = True
            args.sequence_type = "all"
            args.create_lca_mapping = True
            args.names_file = "names.dmp"
            args.nodes_file = "nodes.dmp"

            result = cmd.execute(args)

            assert result == 0
            assert output_path.exists()
            assert (output_path / "names.dmp").exists()
            assert (output_path / "nodes.dmp").exists()
            assert (output_path / "accession2taxid.txt").exists()
            assert (output_path / "taxonomy_mapping.tsv").exists()
            assert (output_path / "mmseqs2_config.txt").exists()

    def test_mmseqs2_protein_filter_cli(self):
        """Test MMseqs2 export with protein sequence filter via CLI."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.ftd"
            output_path = Path(tmp_dir) / "mmseqs2_output"

            tree = self._create_tree_with_mixed_sequences()
            with SQLiteTaxonomyRepository(str(db_path)) as repo:
                repo.save_tree(tree)

            cmd = ExportCommand()
            args = Mock()
            args.database = str(db_path)
            args.format = "mmseqs2"
            args.output = str(output_path)
            args.compress = False
            args.include_genomes = True
            args.sequence_type = "protein"
            args.create_lca_mapping = True
            args.names_file = "names.dmp"
            args.nodes_file = "nodes.dmp"

            result = cmd.execute(args)

            assert result == 0

            # Check that only protein sequences were exported
            accession_content = (output_path / "accession2taxid.txt").read_text()
            assert "NP_414542" in accession_content  # Protein sequence
            assert "NC_000913" not in accession_content  # Nucleotide sequence

    def test_export_format_consistency(self):
        """Test that same taxonomy produces consistent results across exporters."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.ftd"

            tree = self._create_comprehensive_test_tree()
            with SQLiteTaxonomyRepository(str(db_path)) as repo:
                repo.save_tree(tree)

            # Export to different formats
            formats_outputs = {}
            for format_name in ["ncbi", "metabuli", "metacache", "mmseqs2"]:
                output_path = Path(tmp_dir) / f"{format_name}_output"

                cmd = ExportCommand()
                args = Mock()
                args.database = str(db_path)
                args.format = format_name
                args.output = str(output_path)
                args.compress = False
                args.include_genomes = True
                args.names_file = "names.dmp"
                args.nodes_file = "nodes.dmp"
                # Format-specific options
                args.include_merged = False
                args.format_type = "ncbi_taxonomy"
                args.sequence_type = "all"
                args.create_lca_mapping = True

                result = cmd.execute(args)
                assert result == 0

                formats_outputs[format_name] = output_path

            # Validate taxonomic consistency across formats
            self._validate_taxonomic_consistency(formats_outputs)

    def test_cli_error_handling(self):
        """Test CLI error handling for new exporters."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Test with non-existent database
            cmd = ExportCommand()
            args = Mock()
            args.database = str(Path(tmp_dir) / "nonexistent.ftd")
            args.format = "metabuli"
            args.output = str(Path(tmp_dir) / "output")
            args.compress = False
            args.include_genomes = True
            args.include_merged = False
            args.names_file = "names.dmp"
            args.nodes_file = "nodes.dmp"

            result = cmd.execute(args)
            assert result == 1  # Should return error code

    def test_compression_integration(self):
        """Test compression functionality integration."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test.ftd"
            output_path = Path(tmp_dir) / "compressed_output"

            tree = self._create_comprehensive_test_tree()
            with SQLiteTaxonomyRepository(str(db_path)) as repo:
                repo.save_tree(tree)

            cmd = ExportCommand()
            args = Mock()
            args.database = str(db_path)
            args.format = "metabuli"
            args.output = str(output_path)
            args.compress = True  # Enable compression
            args.include_genomes = True
            args.include_merged = False
            args.names_file = "names.dmp"
            args.nodes_file = "nodes.dmp"

            with patch(
                "flextaxd.utils.subprocess_utils.compress_file"
            ) as mock_compress:
                result = cmd.execute(args)
                assert result == 0
                # Should have called compression
                assert mock_compress.call_count > 0

    def test_large_taxonomy_performance(self):
        """Test performance with large taxonomy trees."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "large_test.ftd"
            output_path = Path(tmp_dir) / "large_output"

            # Create large test tree
            tree = self._create_large_test_tree(1000)  # 1000 nodes
            with SQLiteTaxonomyRepository(str(db_path)) as repo:
                repo.save_tree(tree)

            cmd = ExportCommand()
            args = Mock()
            args.database = str(db_path)
            args.format = "mmseqs2"
            args.output = str(output_path)
            args.compress = False
            args.include_genomes = True
            args.sequence_type = "all"
            args.create_lca_mapping = True
            args.names_file = "names.dmp"
            args.nodes_file = "nodes.dmp"

            import time

            start_time = time.time()
            result = cmd.execute(args)
            export_time = time.time() - start_time

            assert result == 0
            # Should complete within reasonable time (less than 30 seconds)
            assert export_time < 30.0

            # Validate output files exist and have content
            assert (output_path / "names.dmp").exists()
            assert (output_path / "nodes.dmp").stat().st_size > 0

    def _create_comprehensive_test_tree(self):
        """Create comprehensive test tree for integration tests."""
        tree = TaxonomyTree()

        # Create hierarchical taxonomy
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        tree.add_node(root)

        bacteria = TaxonomyNode(
            tax_id=2, name="Bacteria", rank=TaxonomicRank.SUPERKINGDOM, parent_id=1
        )
        tree.add_node(bacteria)

        proteobacteria = TaxonomyNode(
            tax_id=1224, name="Proteobacteria", rank=TaxonomicRank.PHYLUM, parent_id=2
        )
        tree.add_node(proteobacteria)

        enterobacteriaceae = TaxonomyNode(
            tax_id=543,
            name="Enterobacteriaceae",
            rank=TaxonomicRank.FAMILY,
            parent_id=1224,
        )
        tree.add_node(enterobacteriaceae)

        escherichia = TaxonomyNode(
            tax_id=561, name="Escherichia", rank=TaxonomicRank.GENUS, parent_id=543
        )
        tree.add_node(escherichia)

        ecoli = TaxonomyNode(
            tax_id=562,
            name="Escherichia coli",
            rank=TaxonomicRank.SPECIES,
            parent_id=561,
        )
        tree.add_node(ecoli)

        # Add genomes with different formats
        genome1 = GenomeInfo(
            genome_id="NC_000913",
            tax_id=562,
            sequence_type="genome",
            assembly_accession="GCF_000005825.2",
        )
        tree.add_genome(genome1)

        genome2 = GenomeInfo(
            genome_id="NZ_CP009273",
            tax_id=562,
            sequence_type="genome",
            assembly_accession="GCF_000759855.1",
        )
        tree.add_genome(genome2)

        return tree

    def _create_tree_with_mixed_sequences(self):
        """Create tree with mixed sequence types for filter testing."""
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

        rna = GenomeInfo("NR_074233", 562, sequence_type="rna")
        tree.add_genome(rna)

        return tree

    def _create_large_test_tree(self, num_nodes: int):
        """Create large test tree for performance testing."""
        tree = TaxonomyTree()

        # Add root
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        tree.add_node(root)

        # Add nodes in batches
        current_parent = 1
        for i in range(2, num_nodes + 1):
            # Create some hierarchy by occasionally switching parent
            if i % 10 == 0 and i > 10:
                current_parent = max(1, i - 5)

            node = TaxonomyNode(
                tax_id=i,
                name=f"Taxon_{i}",
                rank=TaxonomicRank.SPECIES if i % 5 == 0 else TaxonomicRank.GENUS,
                parent_id=current_parent,
            )
            tree.add_node(node)

            # Add genome for some nodes
            if i % 20 == 0:
                genome = GenomeInfo(f"NC_{i:06d}", i, sequence_type="genome")
                tree.add_genome(genome)

        return tree

    def _validate_taxonomic_consistency(self, formats_outputs: dict):
        """Validate taxonomic consistency across different export formats."""
        # Extract taxonomy information from each format
        taxonomies = {}

        for format_name, output_path in formats_outputs.items():
            if format_name in ["ncbi", "metabuli", "metacache", "mmseqs2"]:
                names_file = output_path / "names.dmp"
                nodes_file = output_path / "nodes.dmp"

                if names_file.exists() and nodes_file.exists():
                    # Parse basic taxonomy information
                    names_content = names_file.read_text()
                    nodes_content = nodes_file.read_text()

                    # Extract tax_ids from both files
                    name_tax_ids = set()
                    for line in names_content.split("\n"):
                        if line.strip() and "\t|\t" in line:
                            tax_id = line.split("\t|\t")[0]
                            name_tax_ids.add(tax_id)

                    node_tax_ids = set()
                    for line in nodes_content.split("\n"):
                        if line.strip() and "\t|\t" in line:
                            tax_id = line.split("\t|\t")[0]
                            node_tax_ids.add(tax_id)

                    taxonomies[format_name] = {
                        "name_tax_ids": name_tax_ids,
                        "node_tax_ids": node_tax_ids,
                    }

        # Validate consistency
        if len(taxonomies) > 1:
            # All formats should have same tax_ids
            reference_format = list(taxonomies.keys())[0]
            reference_tax_ids = taxonomies[reference_format]["name_tax_ids"]

            for format_name, taxonomy in taxonomies.items():
                if format_name != reference_format:
                    # Tax IDs should be consistent
                    assert (
                        taxonomy["name_tax_ids"] == reference_tax_ids
                    ), f"Tax IDs inconsistent between {reference_format} and {format_name}"
                    assert (
                        taxonomy["node_tax_ids"] == reference_tax_ids
                    ), f"Node tax IDs inconsistent in {format_name}"


@pytest.mark.slow
class TestNewExportersPerformance:
    """Performance tests for new exporters."""

    @pytest.mark.parametrize("format_name", ["metabuli", "metacache", "mmseqs2"])
    def test_export_performance_benchmarks(self, format_name):
        """Benchmark export performance for new formats."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "benchmark.ftd"
            output_path = Path(tmp_dir) / f"{format_name}_benchmark"

            # Create moderately large tree (500 nodes)
            tree = self._create_benchmark_tree(500)
            with SQLiteTaxonomyRepository(str(db_path)) as repo:
                repo.save_tree(tree)

            cmd = ExportCommand()
            args = Mock()
            args.database = str(db_path)
            args.format = format_name
            args.output = str(output_path)
            args.compress = False
            args.include_genomes = True
            args.names_file = "names.dmp"
            args.nodes_file = "nodes.dmp"
            # Format-specific options
            args.include_merged = False
            args.format_type = "ncbi_taxonomy"
            args.sequence_type = "all"
            args.create_lca_mapping = True

            import time

            start_time = time.time()
            result = cmd.execute(args)
            export_time = time.time() - start_time

            assert result == 0
            # Should complete within reasonable time
            assert export_time < 15.0  # 15 seconds max for 500 nodes

            # Log performance for monitoring
            print(f"{format_name} export time for 500 nodes: {export_time:.2f} seconds")

    def _create_benchmark_tree(self, num_nodes: int):
        """Create tree for performance benchmarking."""
        tree = TaxonomyTree()

        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        tree.add_node(root)

        # Create realistic hierarchy
        current_parent = 1
        for i in range(2, num_nodes + 1):
            # Create branching hierarchy
            if i % 50 == 0:  # New high-level group
                current_parent = 1
            elif i % 10 == 0:  # New mid-level group
                current_parent = max(2, i - 25)

            rank = TaxonomicRank.SPECIES if i % 3 == 0 else TaxonomicRank.GENUS

            node = TaxonomyNode(
                tax_id=i,
                name=f"Benchmark_taxon_{i}",
                rank=rank,
                parent_id=current_parent,
            )
            tree.add_node(node)

            # Add genomes for species-level nodes
            if rank == TaxonomicRank.SPECIES:
                genome = GenomeInfo(f"NC_{i:06d}", i, sequence_type="genome")
                tree.add_genome(genome)

        return tree
