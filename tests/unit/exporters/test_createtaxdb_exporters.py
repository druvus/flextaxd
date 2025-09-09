"""Unit tests for CreateTaxDB format exporters (accession2taxid, nucl2taxid, etc.)."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from flextaxd.core.models import TaxonomyTree, TaxonomyNode, TaxonomicRank, GenomeInfo
from flextaxd.core.exceptions import ExportError
from flextaxd.exporters.accession2taxid import Accession2TaxidExporter
from flextaxd.exporters.nucl2taxid import Nucl2TaxidExporter
from flextaxd.exporters.prot2taxid import Prot2TaxidExporter
from flextaxd.exporters.genome_sizes import GenomeSizesExporter
from flextaxd.exporters.malt_mapdb import MALTMapDBExporter


class TestCreateTaxDBExportersBase:
    """Base class with common test utilities for CreateTaxDB exporters."""

    @staticmethod
    def create_test_tree_with_genomes():
        """Create a test taxonomy tree with comprehensive genome information."""
        tree = TaxonomyTree()
        
        # Add root
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        tree.add_node(root)
        
        # Add Bacteria
        bacteria = TaxonomyNode(tax_id=2, name="Bacteria", rank=TaxonomicRank.SUPERKINGDOM, parent_id=1)
        tree.add_node(bacteria)
        
        # Add E. coli
        ecoli = TaxonomyNode(tax_id=511145, name="Escherichia coli str. K-12", rank=TaxonomicRank.SPECIES, parent_id=2)
        tree.add_node(ecoli)
        
        # Add genomes with various accession formats
        genomes = [
            GenomeInfo(
                genome_id="GCA_000005825.2", 
                tax_id=511145,
                assembly_accession="GCF_000005825.2",
                sequence_length=4641652,
                sequence_type="genome"  # Nucleotide/genome sequence
            ),
            GenomeInfo(
                genome_id="NC_000913.3",
                tax_id=511145,
                assembly_accession="GCF_000005825.2", 
                sequence_length=4641652,
                sequence_type="nucleotide"  # Nucleotide sequence
            ),
            GenomeInfo(
                genome_id="WP_000001.1|protein_id",
                tax_id=511145,
                sequence_type="protein"  # Protein entry
            )
        ]
        
        for genome in genomes:
            tree.add_genome(genome)
        
        # Add another species for variety
        salmonella = TaxonomyNode(tax_id=28901, name="Salmonella enterica", rank=TaxonomicRank.SPECIES, parent_id=2)
        tree.add_node(salmonella)
        
        salm_genome = GenomeInfo(
            genome_id="GCA_000006945.2",
            tax_id=28901,
            assembly_accession="GCF_000006945.2",
            sequence_length=4857432,
            sequence_type="genome"  # Nucleotide/genome sequence
        )
        tree.add_genome(salm_genome)
        
        return tree


class TestAccession2TaxidExporter(TestCreateTaxDBExportersBase):
    """Test accession2taxid format exporter."""

    def test_exporter_properties(self):
        """Test exporter basic properties."""
        exporter = Accession2TaxidExporter()
        assert exporter.exporter_name == "accession2taxid"
        assert ".txt" in exporter.file_extensions
        assert exporter.requires_directory is False

    def test_export_basic_functionality(self):
        """Test basic accession2taxid export."""
        exporter = Accession2TaxidExporter()
        tree = self.create_test_tree_with_genomes()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_file = Path(tmp_dir) / "accession2taxid.txt"
            
            # Export
            exporter.export(tree, output_file)
            
            # Check file was created
            assert output_file.exists()
            
            # Verify content
            with open(output_file) as f:
                lines = f.readlines()
            
            # Should have header + data lines
            assert len(lines) >= 2
            
            # Check header format
            header = lines[0].strip()
            assert "accession" in header
            assert "taxid" in header

    def test_accession_mapping_format(self):
        """Test accession2taxid mapping format."""
        exporter = Accession2TaxidExporter()
        tree = self.create_test_tree_with_genomes()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_file = Path(tmp_dir) / "accession2taxid.txt"
            exporter.export(tree, output_file)
            
            # Parse and verify format
            mappings = {}
            with open(output_file) as f:
                header = f.readline()  # Skip header
                for line in f:
                    parts = line.strip().split('\t')
                    if len(parts) >= 3:  # Need at least accession, accession.version, taxid
                        accession = parts[0]
                        taxid = int(parts[2])  # taxid is in column 2 (0-indexed)
                        mappings[accession] = taxid
            
            # Should have mappings for our genomes
            assert len(mappings) > 0
            
            # Check specific mappings
            expected_accessions = ["GCA_000005825.2", "NC_000913.3", "GCA_000006945.2"]
            for acc in expected_accessions:
                if acc in mappings:
                    assert mappings[acc] in [511145, 28901]  # Our test tax_ids

    def test_duplicate_accession_handling(self):
        """Test handling of duplicate accessions."""
        exporter = Accession2TaxidExporter()
        tree = self.create_test_tree_with_genomes()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_file = Path(tmp_dir) / "accession2taxid.txt"
            exporter.export(tree, output_file)
            
            # Count occurrences of each accession
            accession_counts = {}
            with open(output_file) as f:
                f.readline()  # Skip header
                for line in f:
                    parts = line.strip().split('\t')
                    if len(parts) >= 1:
                        acc = parts[0]
                        accession_counts[acc] = accession_counts.get(acc, 0) + 1
            
            # Each accession should appear only once
            for acc, count in accession_counts.items():
                assert count == 1, f"Accession {acc} appears {count} times"


class TestNucl2TaxidExporter(TestCreateTaxDBExportersBase):
    """Test nucl2taxid format exporter."""

    def test_exporter_properties(self):
        """Test exporter basic properties."""
        exporter = Nucl2TaxidExporter()
        assert exporter.exporter_name == "nucl2taxid"
        assert ".txt" in exporter.file_extensions
        assert exporter.requires_directory is False

    def test_export_nucleotide_sequences(self):
        """Test nucleotide sequence mapping export."""
        exporter = Nucl2TaxidExporter()
        tree = self.create_test_tree_with_genomes()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_file = Path(tmp_dir) / "nucl2taxid.txt"
            
            # Export
            exporter.export(tree, output_file)
            
            # Check file
            assert output_file.exists()
            
            # Verify nucleotide-specific format
            with open(output_file) as f:
                lines = f.readlines()
            
            assert len(lines) >= 1  # At least header
            
            # Check for nucleotide accessions (GCA_, NC_, etc.)
            content = "".join(lines)
            nucleotide_prefixes = ["GCA_", "NC_", "NZ_"]
            has_nucleotide = any(prefix in content for prefix in nucleotide_prefixes)
            assert has_nucleotide or len(lines) == 1  # Either has nucleotide data or just header

    def test_filter_nucleotide_only(self):
        """Test that only nucleotide accessions are included."""
        exporter = Nucl2TaxidExporter()
        tree = self.create_test_tree_with_genomes()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_file = Path(tmp_dir) / "nucl2taxid.txt"
            exporter.export(tree, output_file)
            
            # Parse file and check accessions
            with open(output_file) as f:
                f.readline()  # Skip header
                for line in f:
                    parts = line.strip().split('\t')
                    if len(parts) >= 1:
                        accession = parts[0]
                        # Should not contain protein accessions
                        assert not accession.startswith("WP_")
                        assert not accession.startswith("XP_")


class TestProt2TaxidExporter(TestCreateTaxDBExportersBase):
    """Test prot2taxid format exporter."""

    def test_exporter_properties(self):
        """Test exporter basic properties."""
        exporter = Prot2TaxidExporter()
        assert exporter.exporter_name == "prot2taxid"
        assert ".txt" in exporter.file_extensions
        assert exporter.requires_directory is False

    def test_export_protein_sequences(self):
        """Test protein sequence mapping export."""
        exporter = Prot2TaxidExporter()
        tree = self.create_test_tree_with_genomes()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_file = Path(tmp_dir) / "prot2taxid.txt"
            
            # Export
            exporter.export(tree, output_file)
            
            # Check file
            assert output_file.exists()
            
            # Verify format
            with open(output_file) as f:
                lines = f.readlines()
            
            assert len(lines) >= 1  # At least header

    def test_filter_protein_only(self):
        """Test that only protein accessions are included."""
        exporter = Prot2TaxidExporter()
        tree = self.create_test_tree_with_genomes()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_file = Path(tmp_dir) / "prot2taxid.txt"
            exporter.export(tree, output_file)
            
            # Parse file and check accessions
            with open(output_file) as f:
                f.readline()  # Skip header
                for line in f:
                    parts = line.strip().split('\t')
                    if len(parts) >= 1:
                        accession = parts[0]
                        # Check for protein-like patterns
                        if accession:
                            # Should not be nucleotide accessions
                            assert not accession.startswith("GCA_")
                            assert not accession.startswith("NC_")


class TestGenomeSizesExporter(TestCreateTaxDBExportersBase):
    """Test genome_sizes format exporter."""

    def test_exporter_properties(self):
        """Test exporter basic properties."""
        exporter = GenomeSizesExporter()
        assert exporter.exporter_name == "genome_sizes"
        assert ".txt" in exporter.file_extensions
        assert exporter.requires_directory is False

    def test_export_genome_sizes(self):
        """Test genome sizes export."""
        exporter = GenomeSizesExporter()
        tree = self.create_test_tree_with_genomes()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_file = Path(tmp_dir) / "genome_sizes.txt"
            
            # Export
            exporter.export(tree, output_file)
            
            # Check file
            assert output_file.exists()
            
            # Verify content
            with open(output_file) as f:
                lines = f.readlines()
            
            # Should have data for genomes with sizes
            assert len(lines) >= 1

    def test_genome_size_format(self):
        """Test genome size file format."""
        exporter = GenomeSizesExporter()
        tree = self.create_test_tree_with_genomes()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_file = Path(tmp_dir) / "genome_sizes.txt"
            exporter.export(tree, output_file)
            
            # Parse and verify format
            with open(output_file) as f:
                header = f.readline().strip()  # Skip header line
                assert 'genome_size' in header  # Verify header format
                
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        parts = line.split('\t')
                        assert len(parts) >= 6  # Expect full format: taxid, assembly_accession, species_taxid, organism_name, assembly_level, genome_size
                        
                        # First column should be taxid
                        taxid = parts[0]
                        assert taxid.isdigit()
                        
                        # Last column should be genome_size (integer)
                        size = parts[5]  # genome_size is column 5 (0-indexed)
                        assert size.isdigit()
                        assert int(size) >= 0  # Allow 0 size for protein entries

    def test_missing_genome_sizes_handling(self):
        """Test handling of genomes without size information."""
        exporter = GenomeSizesExporter()
        
        # Create tree with genome without size
        tree = TaxonomyTree()
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        tree.add_node(root)
        
        species = TaxonomyNode(tax_id=123, name="Test species", rank=TaxonomicRank.SPECIES, parent_id=1)
        tree.add_node(species)
        
        # Add genome without size
        genome = GenomeInfo(genome_id="TEST_001", tax_id=123, sequence_length=None)
        tree.add_genome(genome)

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_file = Path(tmp_dir) / "genome_sizes.txt"
            
            # Should not crash
            exporter.export(tree, output_file)
            assert output_file.exists()


class TestMALTMapDBExporter(TestCreateTaxDBExportersBase):
    """Test MALT mapping database exporter."""

    def test_exporter_properties(self):
        """Test exporter basic properties."""
        exporter = MALTMapDBExporter()
        assert exporter.exporter_name == "malt_mapdb"
        assert ".db" in exporter.file_extensions
        assert exporter.requires_directory is False

    def test_export_basic_functionality(self):
        """Test basic MALT mapping export."""
        exporter = MALTMapDBExporter()
        tree = self.create_test_tree_with_genomes()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_file = Path(tmp_dir) / "taxonomy.db"
            
            # Export
            exporter.export(tree, output_file)
            
            # Check file
            assert output_file.exists()
            assert output_file.stat().st_size > 0

    def test_malt_mapping_format(self):
        """Test MALT mapping format."""
        exporter = MALTMapDBExporter()
        tree = self.create_test_tree_with_genomes()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_file = Path(tmp_dir) / "taxonomy.db"
            exporter.export(tree, output_file)
            
            # MALT format creates SQLite database - validate using the exporter's method
            validation_result = exporter.validate_database(output_file)
            
            # Should be valid database
            assert validation_result["valid"] is True
            
            # Should have required tables
            assert "info" in validation_result["tables"]
            assert "mappings" in validation_result["tables"]
            
            # Should have some mappings for our genomes
            assert validation_result["mappings_count"] > 0
            
            # Should have info records
            assert validation_result["info_records"] > 0


class TestCreateTaxDBExportersIntegration:
    """Integration tests for CreateTaxDB exporters."""

    def test_all_exporters_handle_empty_tree(self):
        """Test all CreateTaxDB exporters with empty tree."""
        exporters = [
            Accession2TaxidExporter(),
            Nucl2TaxidExporter(),
            Prot2TaxidExporter(),
            GenomeSizesExporter(),
            MALTMapDBExporter()
        ]
        
        empty_tree = TaxonomyTree()
        
        for exporter in exporters:
            with tempfile.TemporaryDirectory() as tmp_dir:
                output_file = Path(tmp_dir) / f"test.{exporter.file_extensions[0][1:]}"
                
                # CreateTaxDB exporters should raise ExportError for empty trees
                # This is the expected behavior as they need genome data to function
                with pytest.raises(ExportError) as exc_info:
                    exporter.export(empty_tree, output_file)
                
                # Error message should mention insufficient genomes or empty tree
                error_message = str(exc_info.value).lower()
                assert "insufficient genomes" in error_message or "empty" in error_message

    def test_all_exporters_create_valid_files(self):
        """Test all CreateTaxDB exporters create valid output files."""
        exporters = [
            Accession2TaxidExporter(),
            Nucl2TaxidExporter(), 
            Prot2TaxidExporter(),
            GenomeSizesExporter(),
            MALTMapDBExporter()
        ]
        
        tree = TestCreateTaxDBExportersBase.create_test_tree_with_genomes()
        
        for exporter in exporters:
            with tempfile.TemporaryDirectory() as tmp_dir:
                output_file = Path(tmp_dir) / f"test.{exporter.file_extensions[0][1:]}"
                
                # Export should succeed
                exporter.export(tree, output_file)
                
                # File should exist and have content
                assert output_file.exists()
                assert output_file.stat().st_size > 0
                
                # Should be readable (handle binary files like MALT MapDB)
                if exporter.exporter_name == "malt_mapdb":
                    # MALT MapDB creates binary SQLite files, validate using exporter method
                    validation_result = exporter.validate_database(output_file)
                    assert validation_result["valid"] is True
                else:
                    # Text-based formats can be read normally
                    with open(output_file) as f:
                        content = f.read()
                        assert len(content) > 0

    def test_consistent_taxid_usage(self):
        """Test consistent tax_id usage across CreateTaxDB formats."""
        tree = TestCreateTaxDBExportersBase.create_test_tree_with_genomes()
        
        # Export with different formats and collect tax_ids used
        formats_and_taxids = {}
        
        text_exporters = [
            ("accession2taxid", Accession2TaxidExporter()),
            ("nucl2taxid", Nucl2TaxidExporter()),
            ("prot2taxid", Prot2TaxidExporter())
        ]
        
        for format_name, exporter in text_exporters:
            with tempfile.TemporaryDirectory() as tmp_dir:
                output_file = Path(tmp_dir) / f"test.txt"
                exporter.export(tree, output_file)
                
                # Extract tax_ids from file
                tax_ids = set()
                with open(output_file) as f:
                    f.readline()  # Skip header
                    for line in f:
                        parts = line.strip().split('\t')
                        if len(parts) >= 2:
                            try:
                                tax_id = int(parts[1])
                                tax_ids.add(tax_id)
                            except ValueError:
                                pass
                
                formats_and_taxids[format_name] = tax_ids
        
        # All formats should use valid tax_ids from our tree
        expected_tax_ids = {511145, 28901}
        for format_name, found_tax_ids in formats_and_taxids.items():
            if found_tax_ids:  # If any tax_ids found
                # Should be subset of expected tax_ids
                assert found_tax_ids.issubset(expected_tax_ids), \
                    f"Format {format_name} has unexpected tax_ids: {found_tax_ids - expected_tax_ids}"

    def test_file_extensions_consistency(self):
        """Test that file extensions are correctly defined."""
        exporters = [
            Accession2TaxidExporter(),
            Nucl2TaxidExporter(),
            Prot2TaxidExporter(),
            GenomeSizesExporter(),
            MALTMapDBExporter()
        ]
        
        for exporter in exporters:
            # Should have defined file extensions
            assert len(exporter.file_extensions) > 0
            
            # Extensions should start with dot
            for ext in exporter.file_extensions:
                assert ext.startswith(".")
                assert len(ext) > 1
            
            # Should not require directory (these are single-file exports)
            assert exporter.requires_directory is False