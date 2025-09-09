"""Integration tests for complete FlexTaxD workflows."""

import tempfile
import sqlite3
from pathlib import Path
from typing import Dict, Any

import pytest

from flextaxd.parsers.registry import registry
from flextaxd.parsers import (
    TSVTaxonomyParser,
    NCBITaxonomyParser,
    QIIMETaxonomyParser,
    SILVATaxonomyParser,
    CanSNPerTaxonomyParser,
)
from flextaxd.exporters import Kraken2Exporter, GanonExporter, CentrifugeExporter
from flextaxd.database.sqlite import SQLiteTaxonomyRepository
from flextaxd.cli.commands.create import CreateCommand
from flextaxd.core.models import TaxonomicRank
from flextaxd.cli.commands.export import ExportCommand


class TestCompleteWorkflows:
    """Test complete workflows from input parsing to classification export."""

    @pytest.fixture(autouse=True)
    def setup_registry(self):
        """Register all parsers before each test."""
        # Check if parsers are already registered to avoid duplicates
        parser_classes = [
            TSVTaxonomyParser,
            NCBITaxonomyParser,
            QIIMETaxonomyParser,
            SILVATaxonomyParser,
            CanSNPerTaxonomyParser,
        ]

        for parser_class in parser_classes:
            try:
                registry.register(parser_class)
            except Exception:
                # Parser already registered, skip
                pass

    def test_tsv_to_kraken2_workflow(self, tmp_path: Path):
        """Test complete workflow: TSV input -> database -> Kraken2 export."""
        # Create test TSV file
        tsv_content = """Parent	Child	TaxID	Rank
Bacteria	Proteobacteria	2	phylum
Proteobacteria	Gammaproteobacteria	1236	class
Gammaproteobacteria	Enterobacterales	91347	order
Enterobacterales	Enterobacteriaceae	543	family
Enterobacteriaceae	Escherichia	561	genus
Escherichia	Escherichia coli	562	species"""

        input_file = tmp_path / "test_taxonomy.tsv"
        input_file.write_text(tsv_content)

        database_file = tmp_path / "test.ftd"

        # Step 1: Create database from TSV
        create_cmd = CreateCommand()

        class MockArgs:
            def __init__(self):
                self.input = str(input_file)
                self.database = str(database_file)
                self.format = "tsv"
                self.overwrite = True
                self.no_header = False
                self.parent_column = 0
                self.child_column = 1
                self.id_column = 2
                self.rank_column = 3
                self.genomeid2taxid = None
                self.genomes_path = None
                self.auto_detect_sequences = False
                self.sequence_type = "genome"
                # NCBI datasets args (Phase 3 enhancement)
                self.ncbi_datasets = None
                self.taxonomy_only = False
                self.assembly_level = None
                self.max_genomes = None
                
                # Global CLI options (from main parser) - required by all commands
                self.verbose = 0
                self.quiet = False
                self.log_file = None
                self.command = 'create'
                
                # Progress-related options (expected by CLI commands with progress indicators)
                self.progress_width = 80
                self.no_eta = False
                self.no_rate = False
                self.progress_log = None
                self.progress_interval = 1.0
                
                # Additional command-specific options
                self.dry_run = False
                self.force = False
                self.disable_parallel = False
                self.max_workers = 4

        result = create_cmd.execute(MockArgs())
        assert result == 0
        assert database_file.exists()

        # Verify database contents
        with SQLiteTaxonomyRepository(database_file) as repo:
            stats = repo.get_statistics()
            assert stats["node_count"] == 7  # 7 nodes including implicit root

        # Step 2: Export to Kraken2 format
        export_cmd = ExportCommand()
        kraken2_dir = tmp_path / "kraken2_export"

        class MockExportArgs:
            def __init__(self):
                self.database = str(database_file)
                self.format = "kraken2"
                self.output = str(kraken2_dir)
                self.include_unclassified = True
                self.compress = False
                self.include_genomes = False
                self.names_file = None
                self.nodes_file = None
                self.skip_validation = True
                self.validate_files = False
                self.include_header = True
                self.separator = "\t"
                self.legacy_format = None
                self.classifier = None
                
                # Global CLI options (from main parser) - required by all commands
                self.verbose = 0
                self.quiet = False
                self.log_file = None
                self.command = 'export'
                
                # Progress-related options (expected by CLI commands with progress indicators)
                self.progress_width = 80
                self.no_eta = False
                self.no_rate = False
                self.progress_log = None
                self.progress_interval = 1.0
                
                # Additional command-specific options
                self.dry_run = False
                self.force = False
                self.disable_parallel = False
                self.max_workers = 4

        result = export_cmd.execute(MockExportArgs())
        assert result == 0
        assert kraken2_dir.exists()
        assert kraken2_dir.is_dir()

        # Verify Kraken2 export files exist
        names_file = kraken2_dir / "names.dmp"
        nodes_file = kraken2_dir / "nodes.dmp"
        assert names_file.exists()
        assert nodes_file.exists()

        # Verify names.dmp format
        names_content = names_file.read_text()
        lines = [line for line in names_content.split("\n") if line.strip()]

        # Should have entries for each taxonomic level (using auto-generated IDs)
        assert any(
            "Escherichia coli" in line and "scientific name" in line for line in lines
        )
        assert any(
            "Escherichia" in line and "scientific name" in line for line in lines
        )
        assert any(
            "Proteobacteria" in line and "scientific name" in line for line in lines
        )

        # Check that we have the right number of entries
        assert len(lines) == 7  # All 7 nodes should be present

    def test_gtdb_to_ganon_workflow(self, tmp_path: Path):
        """Test complete workflow: GTDB/QIIME input -> database -> Ganon export."""
        # Create test GTDB format file
        gtdb_content = """GCF_000001405.38\td__Bacteria;p__Proteobacteria;c__Gammaproteobacteria;o__Enterobacterales;f__Enterobacteriaceae;g__Escherichia;s__Escherichia coli
GCF_000002305.1\td__Bacteria;p__Proteobacteria;c__Gammaproteobacteria;o__Enterobacterales;f__Enterobacteriaceae;g__Salmonella;s__Salmonella enterica"""

        input_file = tmp_path / "gtdb_taxonomy.tsv"
        input_file.write_text(gtdb_content)

        database_file = tmp_path / "gtdb.ftd"

        # Create database from GTDB format
        create_cmd = CreateCommand()

        class MockArgs:
            def __init__(self):
                self.input = str(input_file)
                self.database = str(database_file)
                self.format = "gtdb"  # Should map to qiime format
                self.overwrite = True
                self.no_header = True
                self.parent_column = 0
                self.child_column = 1
                self.id_column = None
                self.rank_column = None
                self.genomeid2taxid = None
                self.genomes_path = None
                self.auto_detect_sequences = False
                self.sequence_type = "genome"
                # NCBI datasets args (Phase 3 enhancement)
                self.ncbi_datasets = None
                self.taxonomy_only = False
                self.assembly_level = None
                self.max_genomes = None
                
                # Global CLI options (from main parser) - required by all commands
                self.verbose = 0
                self.quiet = False
                self.log_file = None
                self.command = 'create'
                
                # Progress-related options (expected by CLI commands with progress indicators)
                self.progress_width = 80
                self.no_eta = False
                self.no_rate = False
                self.progress_log = None
                self.progress_interval = 1.0
                
                # Additional command-specific options
                self.dry_run = False
                self.force = False
                self.disable_parallel = False
                self.max_workers = 4

        result = create_cmd.execute(MockArgs())
        assert result == 0

        # Export to Ganon format
        export_cmd = ExportCommand()
        ganon_file = tmp_path / "ganon.txt"

        class MockExportArgs:
            def __init__(self):
                self.database = str(database_file)
                self.format = "ganon"
                self.output = str(ganon_file)
                self.include_unclassified = False
                self.compress = False
                self.include_genomes = False
                self.names_file = None
                self.nodes_file = None
                self.skip_validation = True
                self.validate_files = False
                self.include_header = True
                self.separator = "\t"
                self.legacy_format = None
                self.classifier = None
                
                # Global CLI options (from main parser) - required by all commands
                self.verbose = 0
                self.quiet = False
                self.log_file = None
                self.command = 'export'
                
                # Progress-related options (expected by CLI commands with progress indicators)
                self.progress_width = 80
                self.no_eta = False
                self.no_rate = False
                self.progress_log = None
                self.progress_interval = 1.0
                
                # Additional command-specific options
                self.dry_run = False
                self.force = False
                self.disable_parallel = False
                self.max_workers = 4

        result = export_cmd.execute(MockExportArgs())
        assert result == 0
        assert ganon_file.exists()

        # Verify Ganon export format (creates directory structure)
        assert ganon_file.is_dir()  # Ganon creates directory
        taxonomy_dir = ganon_file / "taxonomy"
        assert taxonomy_dir.exists()

        # Check for required Ganon files
        names_file = taxonomy_dir / "names.dmp"
        nodes_file = taxonomy_dir / "nodes.dmp"
        assert names_file.exists()
        assert nodes_file.exists()

        # Verify content in names file
        names_content = names_file.read_text()
        assert "Bacteria" in names_content
        assert "Escherichia" in names_content

    def test_silva_to_centrifuge_workflow(self, tmp_path: Path):
        """Test complete workflow: SILVA input -> database -> Centrifuge export."""
        # Create test SILVA format file
        silva_content = """AB000001\tBacteria;Proteobacteria;Gammaproteobacteria;Enterobacterales;Enterobacteriaceae;Escherichia
AB000002\tBacteria;Proteobacteria;Gammaproteobacteria;Enterobacterales;Enterobacteriaceae;Salmonella"""

        input_file = tmp_path / "silva_taxonomy.txt"
        input_file.write_text(silva_content)

        database_file = tmp_path / "silva.ftd"

        # Create database from SILVA format
        create_cmd = CreateCommand()

        class MockArgs:
            def __init__(self):
                self.input = str(input_file)
                self.database = str(database_file)
                self.format = "silva"
                self.overwrite = True
                self.no_header = True
                self.parent_column = 0
                self.child_column = 1
                self.id_column = None
                self.rank_column = None
                self.genomeid2taxid = None
                self.genomes_path = None
                self.auto_detect_sequences = False
                self.sequence_type = "genome"
                # NCBI datasets args (Phase 3 enhancement)
                self.ncbi_datasets = None
                self.taxonomy_only = False
                self.assembly_level = None
                self.max_genomes = None
                
                # Global CLI options (from main parser) - required by all commands
                self.verbose = 0
                self.quiet = False
                self.log_file = None
                self.command = 'create'
                
                # Progress-related options (expected by CLI commands with progress indicators)
                self.progress_width = 80
                self.no_eta = False
                self.no_rate = False
                self.progress_log = None
                self.progress_interval = 1.0
                
                # Additional command-specific options
                self.dry_run = False
                self.force = False
                self.disable_parallel = False
                self.max_workers = 4

        result = create_cmd.execute(MockArgs())
        assert result == 0

        # Export to Centrifuge format
        export_cmd = ExportCommand()
        centrifuge_file = tmp_path / "centrifuge.txt"

        class MockExportArgs:
            def __init__(self):
                self.database = str(database_file)
                self.format = "centrifuge"
                self.output = str(centrifuge_file)
                self.include_unclassified = True
                self.compress = False
                self.include_genomes = False
                self.names_file = None
                self.nodes_file = None
                self.skip_validation = True
                self.validate_files = False
                self.include_header = True
                self.separator = "\t"
                self.legacy_format = None
                self.classifier = None
                
                # Global CLI options (from main parser) - required by all commands
                self.verbose = 0
                self.quiet = False
                self.log_file = None
                self.command = 'export'
                
                # Progress-related options (expected by CLI commands with progress indicators)
                self.progress_width = 80
                self.no_eta = False
                self.no_rate = False
                self.progress_log = None
                self.progress_interval = 1.0
                
                # Additional command-specific options
                self.dry_run = False
                self.force = False
                self.disable_parallel = False
                self.max_workers = 4

        result = export_cmd.execute(MockExportArgs())
        assert result == 0
        assert centrifuge_file.exists()

        # Verify Centrifuge export format (creates directory structure)
        assert centrifuge_file.is_dir()  # Centrifuge creates directory
        taxonomy_dir = centrifuge_file / "taxonomy"
        assert taxonomy_dir.exists()

        # Check for required Centrifuge files
        names_file = taxonomy_dir / "names.dmp"
        nodes_file = taxonomy_dir / "nodes.dmp"
        assert names_file.exists()
        assert nodes_file.exists()

        # Verify content in names file
        names_content = names_file.read_text()
        assert "Bacteria" in names_content
        assert "Escherichia" in names_content

    def test_ncbi_format_detection_and_parsing(self, tmp_path: Path):
        """Test NCBI format auto-detection and parsing."""
        # Create mock NCBI nodes.dmp file
        nodes_content = """1\t|\t1\t|\tno rank\t|\t\t|\t8\t|\t0\t|\t1\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|\t\t|
2\t|\t131567\t|\tsuperkingdom\t|\t\t|\t0\t|\t0\t|\t11\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|\t\t|
562\t|\t561\t|\tspecies\t|\tEC\t|\t11\t|\t1\t|\t1\t|\t1\t|\t0\t|\t1\t|\t1\t|\t0\t|\t\t|"""

        names_content = """1\t|\tall\t|\t\t|\tsynonym\t|
1\t|\troot\t|\t\t|\tscientific name\t|
2\t|\tBacteria\t|\tBacteria <prokaryotes>\t|\tscientific name\t|
562\t|\tEscherichia coli\t|\t\t|\tscientific name\t|"""

        # Create NCBI directory structure
        ncbi_dir = tmp_path / "ncbi_dump"
        ncbi_dir.mkdir()

        (ncbi_dir / "nodes.dmp").write_text(nodes_content)
        (ncbi_dir / "names.dmp").write_text(names_content)

        database_file = tmp_path / "ncbi.ftd"

        # Test auto-detection
        create_cmd = CreateCommand()

        class MockArgs:
            def __init__(self):
                self.input = str(ncbi_dir)
                self.database = str(database_file)
                self.format = "auto"  # Should auto-detect as NCBI
                self.overwrite = True
                self.no_header = True
                self.parent_column = 0
                self.child_column = 1
                self.id_column = None
                self.rank_column = None
                self.genomeid2taxid = None
                self.genomes_path = None
                self.auto_detect_sequences = False
                self.sequence_type = "genome"
                # NCBI datasets args (Phase 3 enhancement)
                self.ncbi_datasets = None
                self.taxonomy_only = False
                self.assembly_level = None
                self.max_genomes = None
                
                # Global CLI options (from main parser) - required by all commands
                self.verbose = 0
                self.quiet = False
                self.log_file = None
                self.command = 'create'
                
                # Progress-related options (expected by CLI commands with progress indicators)
                self.progress_width = 80
                self.no_eta = False
                self.no_rate = False
                self.progress_log = None
                self.progress_interval = 1.0
                
                # Additional command-specific options
                self.dry_run = False
                self.force = False
                self.disable_parallel = False
                self.max_workers = 4

        result = create_cmd.execute(MockArgs())
        assert result == 0

        # Verify database was created successfully
        with SQLiteTaxonomyRepository(database_file) as repo:
            stats = repo.get_statistics()
            assert stats["node_count"] > 0

            # Verify that root node exists (tax_id = 1)
            root_node = repo.get_node(1)
            assert root_node is not None
            assert root_node.tax_id == 1

    def test_cansnper_format_workflow(self, tmp_path: Path):
        """Test CanSNPer format parsing and export workflow."""
        # Create test CanSNPer format file
        cansnper_content = """Francisella	1.1
1.1	1.1.1
1.1.1	1.1.1.1
1.1	1.2
1.2	1.2.1"""

        input_file = tmp_path / "cansnper.tree"
        input_file.write_text(cansnper_content)

        database_file = tmp_path / "cansnper.ftd"

        # Create database from CanSNPer format
        create_cmd = CreateCommand()

        class MockArgs:
            def __init__(self):
                self.input = str(input_file)
                self.database = str(database_file)
                self.format = "cansnper"
                self.overwrite = True
                self.no_header = True
                self.parent_column = 0
                self.child_column = 1
                self.id_column = None
                self.rank_column = None
                self.genomeid2taxid = None
                self.genomes_path = None
                self.auto_detect_sequences = False
                self.sequence_type = "genome"
                # NCBI datasets args (Phase 3 enhancement)
                self.ncbi_datasets = None
                self.taxonomy_only = False
                self.assembly_level = None
                self.max_genomes = None
                
                # Global CLI options (from main parser) - required by all commands
                self.verbose = 0
                self.quiet = False
                self.log_file = None
                self.command = 'create'
                
                # Progress-related options (expected by CLI commands with progress indicators)
                self.progress_width = 80
                self.no_eta = False
                self.no_rate = False
                self.progress_log = None
                self.progress_interval = 1.0
                
                # Additional command-specific options
                self.dry_run = False
                self.force = False
                self.disable_parallel = False
                self.max_workers = 4

        result = create_cmd.execute(MockArgs())
        assert result == 0

        # Verify database structure
        with SQLiteTaxonomyRepository(database_file) as repo:
            stats = repo.get_statistics()
            assert stats["node_count"] >= 5  # Should have at least 5 unique nodes
            assert len(stats["root_nodes"]) == 1  # Should have one root node
            assert (
                TaxonomicRank.SUBSPECIES in stats["rank_distribution"]
            )  # Should have subspecies ranks

    def test_format_conversion_chain(self, tmp_path: Path):
        """Test converting between different formats through the database."""
        # Create initial TSV data
        tsv_content = """Parent	Child	TaxID	Rank
root	Bacteria	2	superkingdom
Bacteria	Proteobacteria	1224	phylum
Proteobacteria	Escherichia	561	genus
Escherichia	Escherichia coli	562	species"""

        tsv_file = tmp_path / "input.tsv"
        tsv_file.write_text(tsv_content)

        database_file = tmp_path / "conversion.ftd"

        # Step 1: Import TSV
        create_cmd = CreateCommand()

        class MockCreateArgs:
            def __init__(self):
                self.input = str(tsv_file)
                self.database = str(database_file)
                self.format = "tsv"
                self.overwrite = True
                self.no_header = False
                self.parent_column = 0
                self.child_column = 1
                self.id_column = 2
                self.rank_column = 3
                self.genomeid2taxid = None
                self.genomes_path = None
                self.auto_detect_sequences = False
                self.sequence_type = "genome"
                # NCBI datasets args (Phase 3 enhancement)
                self.ncbi_datasets = None
                self.taxonomy_only = False
                self.assembly_level = None
                self.max_genomes = None
                
                # Global CLI options (from main parser) - required by all commands
                self.verbose = 0
                self.quiet = False
                self.log_file = None
                self.command = 'create'
                
                # Progress-related options (expected by CLI commands with progress indicators)
                self.progress_width = 80
                self.no_eta = False
                self.no_rate = False
                self.progress_log = None
                self.progress_interval = 1.0
                
                # Additional command-specific options
                self.dry_run = False
                self.force = False
                self.disable_parallel = False
                self.max_workers = 4

        result = create_cmd.execute(MockCreateArgs())
        assert result == 0

        # Step 2: Export to all supported formats
        export_cmd = ExportCommand()

        formats_to_test = ["kraken2", "ganon", "centrifuge"]

        for fmt in formats_to_test:
            output_file = tmp_path / f"output.{fmt}"

            class MockExportArgs:
                def __init__(self, format_name, output_path):
                    self.database = str(database_file)
                    self.format = format_name
                    self.output = str(output_path)
                    self.include_unclassified = True
                    self.compress = False
                    self.include_genomes = False
                    self.names_file = None
                    self.nodes_file = None
                    self.skip_validation = True
                    self.validate_files = False
                    self.include_header = True
                    self.separator = "\t"
                    self.legacy_format = None
                    self.classifier = None
                    
                    # Global CLI options (from main parser) - required by all commands
                    self.verbose = 0
                    self.quiet = False
                    self.log_file = None
                    self.command = 'export'
                    
                    # Progress-related options (expected by CLI commands with progress indicators)
                    self.progress_width = 80
                    self.no_eta = False
                    self.no_rate = False
                    self.progress_log = None
                    self.progress_interval = 1.0
                    
                    # Additional command-specific options
                    self.dry_run = False
                    self.force = False
                    self.disable_parallel = False
                    self.max_workers = 4

            result = export_cmd.execute(MockExportArgs(fmt, output_file))
            assert result == 0, f"Failed to export to {fmt} format"
            assert output_file.exists(), f"Output file not created for {fmt}"

            # Handle directory-based export formats
            if output_file.is_dir():
                # For directory-based exporters (ganon, centrifuge, kraken2)
                taxonomy_dir = output_file / "taxonomy"
                if taxonomy_dir.exists():
                    # Check for common taxonomy files
                    names_file = taxonomy_dir / "names.dmp"
                    nodes_file = taxonomy_dir / "nodes.dmp"
                    assert (
                        names_file.exists() or nodes_file.exists()
                    ), f"No taxonomy files found in {fmt} output"
                else:
                    # Check for any content files in the directory
                    content_files = list(output_file.rglob("*"))
                    content_files = [f for f in content_files if f.is_file()]
                    assert (
                        len(content_files) > 0
                    ), f"No content files found in {fmt} directory"
            else:
                # For single-file exports
                content = output_file.read_text().strip()
                assert len(content) > 0, f"Empty output file for {fmt}"

    def test_database_statistics_accuracy(self, tmp_path: Path):
        """Test that database statistics are accurate after import."""
        # Create comprehensive test data
        test_data = """Parent	Child	TaxID	Rank
root	Bacteria	2	superkingdom
root	Archaea	2157	superkingdom
Bacteria	Proteobacteria	1224	phylum
Bacteria	Firmicutes	1239	phylum
Proteobacteria	Gammaproteobacteria	1236	class
Gammaproteobacteria	Enterobacterales	91347	order
Enterobacterales	Enterobacteriaceae	543	family
Enterobacteriaceae	Escherichia	561	genus
Enterobacteriaceae	Salmonella	590	genus
Escherichia	Escherichia coli	562	species
Salmonella	Salmonella enterica	28901	species"""

        input_file = tmp_path / "comprehensive.tsv"
        input_file.write_text(test_data)

        database_file = tmp_path / "comprehensive.ftd"

        # Import data
        create_cmd = CreateCommand()

        class MockArgs:
            def __init__(self):
                self.input = str(input_file)
                self.database = str(database_file)
                self.format = "tsv"
                self.overwrite = True
                self.no_header = False
                self.parent_column = 0
                self.child_column = 1
                self.id_column = 2
                self.rank_column = 3
                self.genomeid2taxid = None
                self.genomes_path = None
                self.auto_detect_sequences = False
                self.sequence_type = "genome"
                # NCBI datasets args (Phase 3 enhancement)
                self.ncbi_datasets = None
                self.taxonomy_only = False
                self.assembly_level = None
                self.max_genomes = None
                
                # Global CLI options (from main parser) - required by all commands
                self.verbose = 0
                self.quiet = False
                self.log_file = None
                self.command = 'create'
                
                # Progress-related options (expected by CLI commands with progress indicators)
                self.progress_width = 80
                self.no_eta = False
                self.no_rate = False
                self.progress_log = None
                self.progress_interval = 1.0
                
                # Additional command-specific options
                self.dry_run = False
                self.force = False
                self.disable_parallel = False
                self.max_workers = 4

        result = create_cmd.execute(MockArgs())
        assert result == 0

        # Verify statistics
        with SQLiteTaxonomyRepository(database_file) as repo:
            stats = repo.get_statistics()

            # Count nodes by rank (root gets 'custom' rank from TSV parser)
            expected_ranks = {
                TaxonomicRank.CUSTOM: 1,  # Root node gets custom rank
                TaxonomicRank.SUPERKINGDOM: 2,
                TaxonomicRank.PHYLUM: 2,
                TaxonomicRank.CLASS: 1,
                TaxonomicRank.ORDER: 1,
                TaxonomicRank.FAMILY: 1,
                TaxonomicRank.GENUS: 2,
                TaxonomicRank.SPECIES: 2,
            }

            total_expected = sum(expected_ranks.values())
            assert stats["node_count"] == total_expected

            # Check rank distribution
            if stats["rank_distribution"]:
                for rank, expected_count in expected_ranks.items():
                    actual_count = stats["rank_distribution"].get(rank, 0)
                    assert (
                        actual_count == expected_count
                    ), f"Expected {expected_count} {rank.value} nodes, got {actual_count}"
