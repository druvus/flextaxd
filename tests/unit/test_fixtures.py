"""Centralized test fixtures for FlexTaxD unit tests."""

import pytest
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import Mock

from flextaxd.core.models import (
    TaxonomyTree, TaxonomyNode, TaxonomicRank, GenomeInfo
)


@pytest.fixture
def simple_taxonomy_tree():
    """Create a simple taxonomy tree for testing."""
    tree = TaxonomyTree()
    
    # Add root with ROOT rank (NCBI standard)
    root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT)
    tree.add_node(root)
    
    # Add bacteria superkingdom
    bacteria = TaxonomyNode(
        tax_id=2, name="Bacteria", rank=TaxonomicRank.SUPERKINGDOM, parent_id=1
    )
    tree.add_node(bacteria)
    
    # Add E. coli species
    ecoli = TaxonomyNode(
        tax_id=562, name="Escherichia coli", rank=TaxonomicRank.SPECIES, parent_id=2
    )
    tree.add_node(ecoli)
    
    return tree


@pytest.fixture
def complex_taxonomy_tree():
    """Create a more complex taxonomy tree for testing."""
    tree = TaxonomyTree()
    
    # Build a more complete taxonomy: Root -> Bacteria -> Proteobacteria -> Gammaproteobacteria -> Enterobacteriales -> Enterobacteriaceae -> Escherichia -> E. coli
    
    # Root
    root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT)
    tree.add_node(root)
    
    # Bacteria (superkingdom)
    bacteria = TaxonomyNode(
        tax_id=2, name="Bacteria", rank=TaxonomicRank.SUPERKINGDOM, parent_id=1
    )
    tree.add_node(bacteria)
    
    # Proteobacteria (phylum)
    proteobacteria = TaxonomyNode(
        tax_id=1224, name="Proteobacteria", rank=TaxonomicRank.PHYLUM, parent_id=2
    )
    tree.add_node(proteobacteria)
    
    # Gammaproteobacteria (class)
    gammaproteobacteria = TaxonomyNode(
        tax_id=1236, name="Gammaproteobacteria", rank=TaxonomicRank.CLASS, parent_id=1224
    )
    tree.add_node(gammaproteobacteria)
    
    # Enterobacteriales (order)
    enterobacteriales = TaxonomyNode(
        tax_id=91347, name="Enterobacteriales", rank=TaxonomicRank.ORDER, parent_id=1236
    )
    tree.add_node(enterobacteriales)
    
    # Enterobacteriaceae (family)
    enterobacteriaceae = TaxonomyNode(
        tax_id=543, name="Enterobacteriaceae", rank=TaxonomicRank.FAMILY, parent_id=91347
    )
    tree.add_node(enterobacteriaceae)
    
    # Escherichia (genus)
    escherichia = TaxonomyNode(
        tax_id=561, name="Escherichia", rank=TaxonomicRank.GENUS, parent_id=543
    )
    tree.add_node(escherichia)
    
    # E. coli (species)
    ecoli = TaxonomyNode(
        tax_id=562, name="Escherichia coli", rank=TaxonomicRank.SPECIES, parent_id=561
    )
    tree.add_node(ecoli)
    
    return tree


@pytest.fixture
def tree_with_genomes():
    """Create taxonomy tree with genome information."""
    tree = TaxonomyTree()
    
    # Simple tree structure
    root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT)
    tree.add_node(root)
    
    bacteria = TaxonomyNode(
        tax_id=2, name="Bacteria", rank=TaxonomicRank.SUPERKINGDOM, parent_id=1
    )
    tree.add_node(bacteria)
    
    ecoli = TaxonomyNode(
        tax_id=562, name="Escherichia coli", rank=TaxonomicRank.SPECIES, parent_id=2
    )
    tree.add_node(ecoli)
    
    # Add genomes with different sequence types
    genomes = [
        GenomeInfo(
            genome_id="NC_000913",
            tax_id=562,
            assembly_accession="GCF_000005825.2",
            file_path="/test/genomes/NC_000913.fna",
            source="NCBI"
        ),
        GenomeInfo(
            genome_id="NP_414542",
            tax_id=562,
            assembly_accession="GCF_000005825.2",
            file_path="/test/proteins/NP_414542.faa",
            source="NCBI"
        ),
        GenomeInfo(
            genome_id="CP000819",
            tax_id=562,
            assembly_accession="GCF_000006945.2",
            file_path="/test/genomes/CP000819.fna",
            source="NCBI"
        )
    ]
    
    for genome in genomes:
        tree.add_genome(genome)
    
    return tree


@pytest.fixture
def mock_sequence_files():
    """Create mock sequence files for testing."""
    files = {}
    
    # Create temporary FASTA files
    with NamedTemporaryFile(mode='w', suffix='.fna', delete=False) as f:
        f.write(">NC_000913 Escherichia coli str. K-12 substr. MG1655, complete genome\n")
        f.write("ATCGATCGATCG" * 100 + "\n")
        files['genome'] = Path(f.name)
    
    with NamedTemporaryFile(mode='w', suffix='.faa', delete=False) as f:
        f.write(">NP_414542.1 thrL; thr operon leader peptide\n")
        f.write("MKRISTTITTTITITTGNGAG\n")
        files['protein'] = Path(f.name)
    
    yield files
    
    # Cleanup
    for file_path in files.values():
        if file_path.exists():
            file_path.unlink()


@pytest.fixture
def mock_genome_directory(tmp_path):
    """Create a mock genome directory structure."""
    genome_dir = tmp_path / "genomes"
    genome_dir.mkdir()
    
    # Create genome files
    (genome_dir / "NC_000913.fna").write_text(
        ">NC_000913 Escherichia coli str. K-12 substr. MG1655, complete genome\n" +
        "ATCGATCGATCGATCG" * 100 + "\n"
    )
    
    (genome_dir / "NP_414542.faa").write_text(
        ">NP_414542.1 thrL; thr operon leader peptide\n" +
        "MKRISTTITTTITITTGNGAG\n"
    )
    
    return genome_dir


@pytest.fixture  
def expected_ncbi_formats():
    """Expected output formats for NCBI exporter."""
    return {
        'nodes_root': "1\t|\t1\t|\tno rank\t|\t\t|\t0\t|\t1\t|\t1\t|\t1\t|\t1\t|\t1\t|\t0\t|\t0\t|\t\t|\n",
        'nodes_bacteria': "2\t|\t1\t|\tsuperkingdom\t|\t\t|\t0\t|\t1\t|\t1\t|\t1\t|\t1\t|\t1\t|\t0\t|\t0\t|\t\t|\n",
        'nodes_ecoli': "562\t|\t2\t|\tspecies\t|\t\t|\t0\t|\t1\t|\t1\t|\t1\t|\t1\t|\t1\t|\t0\t|\t0\t|\t\t|\n",
        'names_root': "1\t|\troot\t|\t\t|\tscientific name\t|\n",
        'names_bacteria': "2\t|\tBacteria\t|\t\t|\tscientific name\t|\n",
        'names_ecoli': "562\t|\tEscherichia coli\t|\t\t|\tscientific name\t|\n"
    }


# Mock data generators
def create_mock_taxonomy_parser(tree_data=None):
    """Create a mock taxonomy parser."""
    mock_parser = Mock()
    mock_parser.parse.return_value = tree_data or simple_taxonomy_tree()
    mock_parser.parser_name = "mock_parser"
    mock_parser.supported_formats = [".txt", ".tsv"]
    return mock_parser


def create_mock_exporter(name="mock_exporter", extensions=None):
    """Create a mock taxonomy exporter."""
    mock_exporter = Mock()
    mock_exporter.exporter_name = name
    mock_exporter.file_extensions = extensions or [".txt"]
    mock_exporter.requires_directory = False
    return mock_exporter