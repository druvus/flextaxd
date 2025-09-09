"""Simplified integration tests for core FlexTaxD workflows."""

import tempfile
from pathlib import Path

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
from flextaxd.cli.commands.export import ExportCommand
from flextaxd.core.models import TaxonomicRank


class TestSimplifiedWorkflows:
    """Simplified integration tests for core functionality."""

    @pytest.fixture(autouse=True)
    def setup_registry(self):
        """Register all parsers before each test."""
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

    def create_mock_args(self, **kwargs):
        """Helper to create mock args with all required attributes."""

        class MockArgs:
            def __init__(self, **attrs):
                # Default args for create command
                self.input = attrs.get("input")
                self.database = attrs.get("database")
                self.format = attrs.get("format", "tsv")
                self.overwrite = attrs.get("overwrite", True)
                self.no_header = attrs.get("no_header", False)
                self.parent_column = attrs.get("parent_column", 0)
                self.child_column = attrs.get("child_column", 1)
                self.id_column = attrs.get("id_column", 2)
                self.rank_column = attrs.get("rank_column", 3)

                # Genome integration args
                self.genomeid2taxid = attrs.get("genomeid2taxid", None)
                self.genomes_path = attrs.get("genomes_path", None)
                self.auto_detect_sequences = attrs.get("auto_detect_sequences", False)
                self.sequence_type = attrs.get("sequence_type", "genome")
                
                # NCBI datasets args (Phase 3 enhancement)
                self.ncbi_datasets = attrs.get("ncbi_datasets", None)
                self.taxonomy_only = attrs.get("taxonomy_only", False)
                self.assembly_level = attrs.get("assembly_level", None)
                self.max_genomes = attrs.get("max_genomes", None)

                # Export command args
                self.output = attrs.get("output")
                self.include_unclassified = attrs.get("include_unclassified", True)
                self.compress = attrs.get("compress", False)
                self.include_genomes = attrs.get("include_genomes", False)
                self.names_file = attrs.get("names_file", None)
                self.nodes_file = attrs.get("nodes_file", None)
                self.skip_validation = attrs.get("skip_validation", False)
                self.validate_files = attrs.get("validate_files", False)
                
                # Additional export format args
                self.include_header = attrs.get("include_header", True)
                self.separator = attrs.get("separator", "\t")
                self.legacy_format = attrs.get("legacy_format", None)
                self.classifier = attrs.get("classifier", None)
                # Format already handled above, don't override
                
                # Global CLI options (from main parser) - required by all commands
                self.verbose = attrs.get("verbose", 0)
                self.quiet = attrs.get("quiet", False)
                self.log_file = attrs.get("log_file", None)
                self.command = attrs.get("command", 'create')
                
                # Progress-related options (expected by CLI commands with progress indicators)
                self.progress_width = attrs.get("progress_width", 80)
                self.no_eta = attrs.get("no_eta", False)
                self.no_rate = attrs.get("no_rate", False)
                self.progress_log = attrs.get("progress_log", None)
                self.progress_interval = attrs.get("progress_interval", 1.0)
                
                # Additional command-specific options
                self.dry_run = attrs.get("dry_run", False)
                self.force = attrs.get("force", False)
                self.disable_parallel = attrs.get("disable_parallel", False)
                self.max_workers = attrs.get("max_workers", 4)

        return MockArgs(**kwargs)

    def test_tsv_parsing_and_database_creation(self, tmp_path: Path):
        """Test basic TSV parsing and database creation."""
        # Create test TSV file
        tsv_content = """Parent\tChild\tTaxID\tRank
Bacteria\tProteobacteria\t2\tphylum
Proteobacteria\tEscherichia\t561\tgenus
Escherichia\tEscherichia coli\t562\tspecies"""

        input_file = tmp_path / "test.tsv"
        input_file.write_text(tsv_content)

        database_file = tmp_path / "test.ftd"

        # Create database
        create_cmd = CreateCommand()
        args = self.create_mock_args(
            input=str(input_file), database=str(database_file), format="tsv"
        )

        result = create_cmd.execute(args)
        assert result == 0
        assert database_file.exists()

        # Verify database contents
        with SQLiteTaxonomyRepository(database_file) as repo:
            stats = repo.get_statistics()
            assert stats["node_count"] == 4  # 3 explicit + 1 implicit root
            assert TaxonomicRank.PHYLUM in stats["rank_distribution"]
            assert TaxonomicRank.GENUS in stats["rank_distribution"]
            assert TaxonomicRank.SPECIES in stats["rank_distribution"]

    def test_qiime_gtdb_parsing(self, tmp_path: Path):
        """Test GTDB/QIIME format parsing."""
        # Create test GTDB format file
        gtdb_content = """GCF_000001405.38\td__Bacteria;p__Proteobacteria;c__Gammaproteobacteria;o__Enterobacterales;f__Enterobacteriaceae;g__Escherichia;s__Escherichia coli"""

        input_file = tmp_path / "gtdb.tsv"
        input_file.write_text(gtdb_content)

        database_file = tmp_path / "gtdb.ftd"

        # Create database
        create_cmd = CreateCommand()
        args = self.create_mock_args(
            input=str(input_file),
            database=str(database_file),
            format="gtdb",  # Maps to qiime
            no_header=True,
        )

        result = create_cmd.execute(args)
        assert result == 0

        # Verify database contents
        with SQLiteTaxonomyRepository(database_file) as repo:
            stats = repo.get_statistics()
            assert stats["node_count"] >= 7  # Should have domain through species
            assert TaxonomicRank.SUPERKINGDOM in stats["rank_distribution"]
            assert TaxonomicRank.PHYLUM in stats["rank_distribution"]
            assert TaxonomicRank.SPECIES in stats["rank_distribution"]

    def test_export_to_kraken2(self, tmp_path: Path):
        """Test export to Kraken2 format."""
        # Create simple database first
        tsv_content = """Parent\tChild\tTaxID\tRank
root\tBacteria\t2\tsuperkingdom
Bacteria\tEscherichia\t561\tgenus
Escherichia\tEscherichia coli\t562\tspecies"""

        input_file = tmp_path / "test.tsv"
        input_file.write_text(tsv_content)

        database_file = tmp_path / "test.ftd"

        # Create database
        create_cmd = CreateCommand()
        create_args = self.create_mock_args(
            input=str(input_file), database=str(database_file), format="tsv"
        )

        result = create_cmd.execute(create_args)
        assert result == 0

        # Export to Kraken2
        kraken2_dir = tmp_path / "kraken2_export"

        export_cmd = ExportCommand()
        export_args = self.create_mock_args(
            database=str(database_file), format="kraken2", output=str(kraken2_dir), skip_validation=True
        )

        result = export_cmd.execute(export_args)
        assert result == 0
        assert kraken2_dir.exists()
        assert kraken2_dir.is_dir()

        # Verify expected files exist
        names_file = kraken2_dir / "names.dmp"
        nodes_file = kraken2_dir / "nodes.dmp"
        assert names_file.exists()
        assert nodes_file.exists()

        # Basic content validation
        names_content = names_file.read_text()
        assert "Bacteria" in names_content
        assert "Escherichia" in names_content
        assert "scientific name" in names_content

    def test_export_to_ganon(self, tmp_path: Path):
        """Test export to Ganon format."""
        # Create simple database first
        tsv_content = """Parent\tChild\tTaxID\tRank
root\tBacteria\t2\tsuperkingdom
Bacteria\tEscherichia\t561\tgenus"""

        input_file = tmp_path / "test.tsv"
        input_file.write_text(tsv_content)

        database_file = tmp_path / "test.ftd"

        # Create database
        create_cmd = CreateCommand()
        create_args = self.create_mock_args(
            input=str(input_file), database=str(database_file), format="tsv"
        )

        result = create_cmd.execute(create_args)
        assert result == 0

        # Export to Ganon
        ganon_dir = tmp_path / "ganon_export"

        export_cmd = ExportCommand()
        export_args = self.create_mock_args(
            database=str(database_file), format="ganon", output=str(ganon_dir), skip_validation=True
        )

        result = export_cmd.execute(export_args)
        assert result == 0
        assert ganon_dir.exists()
        assert ganon_dir.is_dir()

        # Verify some files were created
        created_files = list(ganon_dir.glob("*"))
        assert len(created_files) > 0

    def test_format_auto_detection(self, tmp_path: Path):
        """Test automatic format detection."""
        # Create TSV file with .tsv extension
        tsv_content = """Parent\tChild\tTaxID\tRank
Bacteria\tProteobacteria\t2\tphylum"""

        input_file = tmp_path / "test_data.tsv"
        input_file.write_text(tsv_content)

        database_file = tmp_path / "auto.ftd"

        # Create database using auto-detection
        create_cmd = CreateCommand()
        args = self.create_mock_args(
            input=str(input_file),
            database=str(database_file),
            format="auto",  # Should auto-detect as TSV
        )

        result = create_cmd.execute(args)
        assert result == 0
        assert database_file.exists()

        # Verify database was created
        with SQLiteTaxonomyRepository(database_file) as repo:
            stats = repo.get_statistics()
            assert stats["node_count"] >= 2

    def test_silva_format_parsing(self, tmp_path: Path):
        """Test SILVA format parsing."""
        # Create test SILVA format file
        silva_content = """AB000001\tBacteria;Proteobacteria;Gammaproteobacteria
AB000002\tBacteria;Firmicutes;Bacilli"""

        input_file = tmp_path / "silva.txt"
        input_file.write_text(silva_content)

        database_file = tmp_path / "silva.ftd"

        # Create database
        create_cmd = CreateCommand()
        args = self.create_mock_args(
            input=str(input_file),
            database=str(database_file),
            format="silva",
            no_header=True,
        )

        result = create_cmd.execute(args)
        assert result == 0

        # Verify database contents
        with SQLiteTaxonomyRepository(database_file) as repo:
            stats = repo.get_statistics()
            assert stats["node_count"] >= 4  # Should have several taxonomic levels
            assert TaxonomicRank.SUPERKINGDOM in stats["rank_distribution"]

    def test_complete_workflow_chain(self, tmp_path: Path):
        """Test a complete workflow from TSV to multiple export formats."""
        # Create comprehensive test data
        tsv_content = """Parent\tChild\tTaxID\tRank
root\tBacteria\t2\tsuperkingdom
Bacteria\tProteobacteria\t1224\tphylum
Proteobacteria\tGammaproteobacteria\t1236\tclass
Gammaproteobacteria\tEscherichia\t561\tgenus
Escherichia\tEscherichia coli\t562\tspecies"""

        input_file = tmp_path / "comprehensive.tsv"
        input_file.write_text(tsv_content)

        database_file = tmp_path / "comprehensive.ftd"

        # Step 1: Create database
        create_cmd = CreateCommand()
        create_args = self.create_mock_args(
            input=str(input_file), database=str(database_file), format="tsv"
        )

        result = create_cmd.execute(create_args)
        assert result == 0
        assert database_file.exists()

        # Step 2: Export to multiple formats
        export_cmd = ExportCommand()
        formats_to_test = ["kraken2", "ganon"]

        for fmt in formats_to_test:
            export_dir = tmp_path / f"{fmt}_export"

            export_args = self.create_mock_args(
                database=str(database_file), format=fmt, output=str(export_dir), skip_validation=True
            )

            result = export_cmd.execute(export_args)
            assert result == 0, f"Failed to export to {fmt}"
            assert export_dir.exists(), f"Export directory not created for {fmt}"

            # Verify some files were created
            created_files = list(export_dir.glob("*"))
            assert len(created_files) > 0, f"No files created for {fmt} export"

    def test_database_statistics(self, tmp_path: Path):
        """Test that database statistics are calculated correctly."""
        # Create test data with known structure
        tsv_content = """Parent\tChild\tTaxID\tRank
root\tBacteria\t2\tsuperkingdom
root\tArchaea\t2157\tsuperkingdom
Bacteria\tProteobacteria\t1224\tphylum
Bacteria\tFirmicutes\t1239\tphylum
Proteobacteria\tEscherichia\t561\tgenus
Escherichia\tEscherichia coli\t562\tspecies"""

        input_file = tmp_path / "stats_test.tsv"
        input_file.write_text(tsv_content)

        database_file = tmp_path / "stats_test.ftd"

        # Create database
        create_cmd = CreateCommand()
        args = self.create_mock_args(
            input=str(input_file), database=str(database_file), format="tsv"
        )

        result = create_cmd.execute(args)
        assert result == 0

        # Verify statistics
        with SQLiteTaxonomyRepository(database_file) as repo:
            stats = repo.get_statistics()

            # Should have all nodes plus implicit root
            assert stats["node_count"] == 7  # 6 explicit + 1 implicit root

            # Check rank distribution
            expected_ranks = {
                TaxonomicRank.SUPERKINGDOM: 2,  # Bacteria, Archaea
                TaxonomicRank.PHYLUM: 2,  # Proteobacteria, Firmicutes
                TaxonomicRank.GENUS: 1,  # Escherichia
                TaxonomicRank.SPECIES: 1,  # E. coli
                TaxonomicRank.CUSTOM: 1,  # Implicit root
            }

            for rank, expected_count in expected_ranks.items():
                actual_count = stats["rank_distribution"].get(rank, 0)
                assert (
                    actual_count == expected_count
                ), f"Expected {expected_count} {rank.value} nodes, got {actual_count}"
