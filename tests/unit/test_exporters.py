"""Comprehensive unit tests for taxonomy exporters."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from flextaxd.core.models import (
    TaxonomyTree, TaxonomyNode, TaxonomicRank, GenomeInfo
)
from flextaxd.core.exceptions import ExportError
from flextaxd.exporters import (
    NCBIExporter, Kraken2Exporter, GanonExporter, CentrifugeExporter,
    Accession2TaxidExporter, Nucl2TaxidExporter, Prot2TaxidExporter,
    GenomeSizesExporter, MALTMapDBExporter
)
from flextaxd.exporters.base import TaxonomyExporter, FileBasedExporter, DirectoryBasedExporter


class TestTaxonomyExporterBase:
    """Test base exporter functionality."""
    
    def test_abstract_exporter_cannot_be_instantiated(self):
        """Test that abstract base class cannot be instantiated."""
        with pytest.raises(TypeError):
            TaxonomyExporter()
    
    def test_file_based_exporter_requires_directory_false(self):
        """Test FileBasedExporter returns False for requires_directory."""
        
        class TestFileExporter(FileBasedExporter):
            def export(self, tree, output_path, **kwargs):
                pass
            
            @property
            def exporter_name(self):
                return "test_file"
            
            @property  
            def file_extensions(self):
                return [".test"]
        
        exporter = TestFileExporter()
        assert exporter.requires_directory is False
    
    def test_directory_based_exporter_requires_directory_true(self):
        """Test DirectoryBasedExporter returns True for requires_directory."""
        
        class TestDirExporter(DirectoryBasedExporter):
            def export(self, tree, output_path, **kwargs):
                pass
            
            @property
            def exporter_name(self):
                return "test_dir"
            
            @property
            def file_extensions(self):
                return [".test"]
        
        exporter = TestDirExporter()
        assert exporter.requires_directory is True

    def test_validate_tree_empty(self):
        """Test tree validation fails on empty tree."""
        
        class TestExporter(FileBasedExporter):
            def export(self, tree, output_path, **kwargs):
                self._validate_tree(tree)
            
            @property
            def exporter_name(self):
                return "test"
            
            @property
            def file_extensions(self):
                return [".test"]
        
        exporter = TestExporter()
        empty_tree = TaxonomyTree()
        
        with pytest.raises(ExportError, match="Cannot export empty taxonomy tree"):
            exporter.export(empty_tree, Path("/tmp/test"))

    def test_ensure_output_path_file(self):
        """Test output path creation for files."""
        
        class TestExporter(FileBasedExporter):
            def export(self, tree, output_path, **kwargs):
                self._ensure_output_path(output_path)
            
            @property
            def exporter_name(self):
                return "test"
            
            @property
            def file_extensions(self):
                return [".test"]
        
        exporter = TestExporter()
        tree = self._create_simple_tree()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_file = Path(tmp_dir) / "test.txt"
            exporter.export(tree, test_file)
            # Should not raise error

    def test_ensure_output_path_directory(self):
        """Test output path creation for directories."""
        
        class TestExporter(DirectoryBasedExporter):
            def export(self, tree, output_path, **kwargs):
                self._ensure_output_path(output_path)
            
            @property
            def exporter_name(self):
                return "test"
            
            @property
            def file_extensions(self):
                return [".test"]
        
        exporter = TestExporter()
        tree = self._create_simple_tree()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_dir = Path(tmp_dir) / "test_export"
            exporter.export(tree, test_dir)
            assert test_dir.exists()
            assert test_dir.is_dir()

    def _create_simple_tree(self):
        """Create a simple test tree."""
        tree = TaxonomyTree()
        
        root = TaxonomyNode(
            tax_id=1,
            name="root",
            rank=TaxonomicRank.CUSTOM,
            parent_id=None
        )
        tree.add_node(root)
        
        bacteria = TaxonomyNode(
            tax_id=2,
            name="Bacteria", 
            rank=TaxonomicRank.SUPERKINGDOM,
            parent_id=1
        )
        tree.add_node(bacteria)
        
        ecoli = TaxonomyNode(
            tax_id=562,
            name="Escherichia coli",
            rank=TaxonomicRank.SPECIES,
            parent_id=2
        )
        tree.add_node(ecoli)
        
        # Add genome info
        genome = GenomeInfo(
            genome_id="NC_000913",
            tax_id=562,
            sequence_type="genome"
        )
        tree.add_genome(genome)
        
        return tree


class TestNCBIExporter:
    """Test NCBI dump format exporter."""
    
    def test_exporter_properties(self):
        """Test exporter basic properties."""
        exporter = NCBIExporter()
        assert exporter.exporter_name == "ncbi"
        assert ".dmp" in exporter.file_extensions
        assert exporter.requires_directory is True
    
    def test_export_basic_functionality(self):
        """Test basic export functionality."""
        exporter = NCBIExporter()
        tree = self._create_test_tree()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(tree, output_path)
            
            # Should create nodes.dmp and names.dmp files
            nodes_file = output_path / "nodes.dmp"
            names_file = output_path / "names.dmp"
            
            assert nodes_file.exists()
            assert names_file.exists()
            
            # Check basic file content
            nodes_content = nodes_file.read_text()
            names_content = names_file.read_text()
            
            assert "1\t|\t1\t|\tno rank" in nodes_content  # Root node
            assert "562\t|\t2\t|\tspecies" in nodes_content  # E. coli
            
            assert "1\t|\troot\t|\t\t|\tscientific name" in names_content
            assert "562\t|\tEscherichia coli\t|\t\t|\tscientific name" in names_content

    def _create_test_tree(self):
        """Create test taxonomy tree."""
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
        
        return tree


class TestKraken2Exporter:
    """Test Kraken2 format exporter."""
    
    def test_exporter_properties(self):
        """Test exporter basic properties."""
        exporter = Kraken2Exporter()
        assert exporter.exporter_name == "kraken2"
        assert ".dmp" in exporter.file_extensions
        assert ".map" in exporter.file_extensions
        assert exporter.requires_directory is True
    
    def test_export_functionality(self):
        """Test export creates required files."""
        exporter = Kraken2Exporter()
        tree = self._create_test_tree()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(tree, output_path)
            
            # Check for expected Kraken2 files
            taxonomy_file = output_path / "taxonomy.tab"
            assert taxonomy_file.exists()
            
            content = taxonomy_file.read_text()
            assert "562\tEscherichia coli" in content

    def _create_test_tree(self):
        """Create test tree with genomes."""
        tree = TaxonomyTree()
        
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        tree.add_node(root)
        
        bacteria = TaxonomyNode(
            tax_id=2, name="Bacteria", rank=TaxonomicRank.SUPERKINGDOM, parent_id=1
        )
        tree.add_node(bacteria)
        
        ecoli = TaxonomyNode(
            tax_id=562, name="Escherichia coli", rank=TaxonomicRank.SPECIES, parent_id=2
        )
        tree.add_node(ecoli)
        
        # Add genome for testing
        genome = GenomeInfo(
            genome_id="NC_000913",
            tax_id=562,
            sequence_type="genome"
        )
        tree.add_genome(genome)
        
        return tree


class TestGanonExporter:
    """Test Ganon format exporter."""
    
    def test_exporter_properties(self):
        """Test exporter properties."""
        exporter = GanonExporter()
        assert exporter.exporter_name == "ganon"
        assert ".dmp" in exporter.file_extensions
        assert ".info" in exporter.file_extensions
        assert exporter.requires_directory is True
    
    def test_export_creates_files(self):
        """Test export creates required files."""
        exporter = GanonExporter()
        tree = self._create_test_tree()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            exporter.export(tree, output_path)
            
            # Check for Ganon taxonomy file
            tax_file = output_path / "taxonomy.tax" 
            assert tax_file.exists()
            
            content = tax_file.read_text()
            assert "562" in content  # Should contain tax IDs

    def _create_test_tree(self):
        """Create minimal test tree.""" 
        tree = TaxonomyTree()
        
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        tree.add_node(root)
        
        ecoli = TaxonomyNode(
            tax_id=562, name="Escherichia coli", rank=TaxonomicRank.SPECIES, parent_id=1
        )
        tree.add_node(ecoli)
        
        return tree


class TestCentrifugeExporter:
    """Test Centrifuge format exporter."""
    
    def test_exporter_properties(self):
        """Test exporter properties."""
        exporter = CentrifugeExporter()
        assert exporter.exporter_name == "centrifuge"
        assert ".dmp" in exporter.file_extensions
        assert ".tab" in exporter.file_extensions
        assert exporter.requires_directory is True
    
    def test_export_functionality(self):
        """Test basic export functionality."""
        exporter = CentrifugeExporter()
        tree = self._create_test_tree()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) 
            exporter.export(tree, output_path)
            
            # Check for Centrifuge files
            name_table = output_path / "names.txt"
            nodes_table = output_path / "nodes.txt"
            
            assert name_table.exists()
            assert nodes_table.exists()

    def _create_test_tree(self):
        """Create test tree."""
        tree = TaxonomyTree()
        
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        tree.add_node(root)
        
        bacteria = TaxonomyNode(
            tax_id=2, name="Bacteria", rank=TaxonomicRank.SUPERKINGDOM, parent_id=1
        )
        tree.add_node(bacteria)
        
        return tree


class TestAccession2TaxidExporter:
    """Test accession2taxid format exporter (CreateTaxDB compatible)."""
    
    def test_exporter_properties(self):
        """Test exporter properties."""
        exporter = Accession2TaxidExporter()
        assert exporter.exporter_name == "accession2taxid"
        assert ".txt" in exporter.file_extensions
        assert exporter.requires_directory is False
        
    def test_export_basic_format(self):
        """Test export produces correct format."""
        exporter = Accession2TaxidExporter()
        tree = self._create_test_tree_with_genomes()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_file = Path(tmp_dir) / "accession2taxid.txt"
            exporter.export(tree, output_file)
            
            assert output_file.exists()
            content = output_file.read_text()
            
            # Should have header
            assert "accession\taccession.version\ttaxid\tgi" in content
            # Should have genome entries  
            assert "NC_000913" in content
            assert "562" in content
    
    def test_export_with_sequence_type_filter(self):
        """Test export with sequence type filtering."""
        exporter = Accession2TaxidExporter()
        tree = self._create_test_tree_with_genomes()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_file = Path(tmp_dir) / "accession2taxid.txt"
            exporter.export(tree, output_file, sequence_type="protein")
            
            content = output_file.read_text()
            # Should only include proteins (one in our test tree)
            lines = content.strip().split('\n')
            assert len(lines) == 2  # Header + 1 protein entry
            assert "NP_414542" in content  # Protein genome should be included

    def _create_test_tree_with_genomes(self):
        """Create test tree with genome entries."""
        tree = TaxonomyTree()
        
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        tree.add_node(root)
        
        ecoli = TaxonomyNode(
            tax_id=562, name="Escherichia coli", rank=TaxonomicRank.SPECIES, parent_id=1
        )
        tree.add_node(ecoli)
        
        # Add genomes
        genome1 = GenomeInfo(
            genome_id="NC_000913", 
            tax_id=562, 
            sequence_type="genome"
        )
        genome2 = GenomeInfo(
            genome_id="NP_414542",
            tax_id=562, 
            sequence_type="protein"
        )
        tree.add_genome(genome1)
        tree.add_genome(genome2)
        
        return tree


class TestNucl2TaxidExporter:
    """Test nucl2taxid exporter (CreateTaxDB compatible)."""
    
    def test_exporter_properties(self):
        """Test basic properties."""
        exporter = Nucl2TaxidExporter()
        assert exporter.exporter_name == "nucl2taxid" 
        assert ".txt" in exporter.file_extensions
        assert exporter.requires_directory is False
    
    def test_export_nucleotide_sequences(self):
        """Test export includes only nucleotide sequences."""
        exporter = Nucl2TaxidExporter()
        tree = self._create_mixed_tree()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_file = Path(tmp_dir) / "nucl2taxid.txt"
            exporter.export(tree, output_file)
            
            content = output_file.read_text()
            # Should include nucleotide sequences
            assert "NC_000913" in content  # Genome
            assert "NR_074233" in content  # RNA
            # Should not include proteins
            assert "NP_414542" not in content

    def _create_mixed_tree(self):
        """Create tree with mixed sequence types."""
        tree = TaxonomyTree()
        
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        tree.add_node(root)
        
        ecoli = TaxonomyNode(
            tax_id=562, name="Escherichia coli", rank=TaxonomicRank.SPECIES, parent_id=1
        )
        tree.add_node(ecoli)
        
        # Add different sequence types
        tree.add_genome(GenomeInfo("NC_000913", 562, sequence_type="genome"))
        tree.add_genome(GenomeInfo("NR_074233", 562, sequence_type="rna")) 
        tree.add_genome(GenomeInfo("NP_414542", 562, sequence_type="protein"))
        
        return tree


class TestProt2TaxidExporter:
    """Test prot2taxid exporter (CreateTaxDB compatible)."""
    
    def test_exporter_properties(self):
        """Test basic properties."""
        exporter = Prot2TaxidExporter()
        assert exporter.exporter_name == "prot2taxid"
        assert ".txt" in exporter.file_extensions
        assert exporter.requires_directory is False
        
    def test_export_protein_sequences(self):
        """Test export includes only protein sequences."""
        exporter = Prot2TaxidExporter()
        tree = self._create_mixed_tree()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_file = Path(tmp_dir) / "prot2taxid.txt"
            exporter.export(tree, output_file)
            
            content = output_file.read_text()
            # Should include protein sequences only
            assert "NP_414542" in content
            # Should not include nucleotides
            assert "NC_000913" not in content
            assert "NR_074233" not in content

    def _create_mixed_tree(self):
        """Create tree with mixed sequence types."""
        tree = TaxonomyTree()
        
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        tree.add_node(root)
        
        ecoli = TaxonomyNode(
            tax_id=562, name="Escherichia coli", rank=TaxonomicRank.SPECIES, parent_id=1
        )
        tree.add_node(ecoli)
        
        # Add sequences
        tree.add_genome(GenomeInfo("NC_000913", 562, sequence_type="genome"))
        tree.add_genome(GenomeInfo("NR_074233", 562, sequence_type="rna"))
        tree.add_genome(GenomeInfo("NP_414542", 562, sequence_type="protein"))
        
        return tree


class TestGenomeSizesExporter:
    """Test genome_sizes exporter (CreateTaxDB compatible)."""
    
    def test_exporter_properties(self):
        """Test basic properties."""
        exporter = GenomeSizesExporter()
        assert exporter.exporter_name == "genome_sizes"
        assert ".txt" in exporter.file_extensions
        assert exporter.requires_directory is False
    
    def test_export_with_mock_sizes(self):
        """Test export with sequence lengths."""
        exporter = GenomeSizesExporter()
        tree = self._create_genome_tree_with_sizes()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_file = Path(tmp_dir) / "genome_sizes.txt"
            exporter.export(tree, output_file)
            
            content = output_file.read_text()
            assert "562\tNC_000913\t562\tEscherichia coli\tContig\t4641652" in content
    
    def test_export_without_sequence_files(self):
        """Test export when sequence files don't exist."""
        exporter = GenomeSizesExporter()
        tree = self._create_genome_tree()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_file = Path(tmp_dir) / "genome_sizes.txt"
            # This should not crash even if sequence files don't exist
            exporter.export(tree, output_file)
            
            content = output_file.read_text()
            # Should have header at minimum
            assert "taxid\tassembly_accession\tspecies_taxid\torganism_name\tassembly_level\tgenome_size" in content

    def _create_genome_tree(self):
        """Create tree with genome sequences."""
        tree = TaxonomyTree()
        
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        tree.add_node(root)
        
        ecoli = TaxonomyNode(
            tax_id=562, name="Escherichia coli", rank=TaxonomicRank.SPECIES, parent_id=1
        )
        tree.add_node(ecoli)
        
        tree.add_genome(GenomeInfo("NC_000913", 562, sequence_type="genome"))
        
        return tree

    def _create_genome_tree_with_sizes(self):
        """Create tree with genome sequences that have size information."""
        tree = TaxonomyTree()
        
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        tree.add_node(root)
        
        ecoli = TaxonomyNode(
            tax_id=562, name="Escherichia coli", rank=TaxonomicRank.SPECIES, parent_id=1
        )
        tree.add_node(ecoli)
        
        tree.add_genome(GenomeInfo("NC_000913", 562, sequence_type="genome", sequence_length=4641652))
        
        return tree


class TestMALTMapDBExporter:
    """Test MALT taxonomy database exporter (CreateTaxDB compatible)."""
    
    def test_exporter_properties(self):
        """Test basic properties."""
        exporter = MALTMapDBExporter()
        assert exporter.exporter_name == "malt_mapdb"
        assert ".db" in exporter.file_extensions
        assert exporter.requires_directory is False
    
    def test_export_creates_sqlite_file(self):
        """Test export creates SQLite database file."""
        exporter = MALTMapDBExporter()
        tree = self._create_test_tree()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_file = Path(tmp_dir) / "taxonomy.db"
            exporter.export(tree, output_file)
            
            assert output_file.exists()
            # File should be non-empty
            assert output_file.stat().st_size > 0

    def _create_test_tree(self):
        """Create simple test tree."""
        tree = TaxonomyTree()
        
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        tree.add_node(root)
        
        bacteria = TaxonomyNode(
            tax_id=2, name="Bacteria", rank=TaxonomicRank.SUPERKINGDOM, parent_id=1
        )
        tree.add_node(bacteria)
        
        return tree


class TestExporterErrorHandling:
    """Test error handling across exporters."""
    
    def test_exporters_handle_empty_trees(self):
        """Test all exporters handle empty trees gracefully."""
        exporters = [
            NCBIExporter(),
            Kraken2Exporter(),
            GanonExporter(), 
            CentrifugeExporter(),
            Accession2TaxidExporter(),
            Nucl2TaxidExporter(),
            Prot2TaxidExporter(),
            GenomeSizesExporter(),
            MALTMapDBExporter()
        ]
        
        empty_tree = TaxonomyTree()
        
        for exporter in exporters:
            with tempfile.TemporaryDirectory() as tmp_dir:
                if exporter.requires_directory:
                    output_path = Path(tmp_dir) / "output_dir"
                else:
                    output_path = Path(tmp_dir) / "output.txt"
                
                with pytest.raises(ExportError, match="Cannot export empty taxonomy tree"):
                    exporter.export(empty_tree, output_path)
    
    def test_exporters_handle_invalid_paths(self):
        """Test exporters handle invalid output paths."""
        exporter = Accession2TaxidExporter()  # File-based exporter
        tree = self._create_simple_tree()
        
        # Try to write to a directory when expecting a file
        with tempfile.TemporaryDirectory() as tmp_dir:
            existing_dir = Path(tmp_dir) / "existing"
            existing_dir.mkdir()
            
            with pytest.raises(ExportError):
                exporter.export(tree, existing_dir)

    def _create_simple_tree(self):
        """Create minimal valid tree."""
        tree = TaxonomyTree()
        
        root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
        tree.add_node(root)
        
        return tree