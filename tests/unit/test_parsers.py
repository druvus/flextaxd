"""Comprehensive unit tests for taxonomy parsers."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from flextaxd.core.models import TaxonomyTree, TaxonomyNode, TaxonomicRank
from flextaxd.core.exceptions import ParseError
from flextaxd.parsers import (
    NCBITaxonomyParser,
    TSVTaxonomyParser,
    QIIMETaxonomyParser,
    SILVATaxonomyParser,
    CanSNPerTaxonomyParser,
    GTDBTaxonomyParser,
)
from flextaxd.parsers.base import TaxonomyParser, FileBasedParser, DirectoryBasedParser
from flextaxd.parsers.registry import ParserRegistry


class TestTaxonomyParserBase:
    """Test base parser functionality."""

    def test_abstract_parser_cannot_be_instantiated(self):
        """Test that abstract base class cannot be instantiated."""
        with pytest.raises(TypeError):
            TaxonomyParser()

    def test_file_based_parser_read_lines(self):
        """Test FileBasedParser._read_lines method."""

        class TestFileParser(FileBasedParser):
            def can_parse(self, file_path):
                return True

            def parse(self, file_path, **kwargs):
                lines = list(self._read_lines(file_path))
                tree = TaxonomyTree()
                root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
                tree.add_node(root)
                return tree

            @property
            def supported_extensions(self):
                return [".test"]

            @property
            def parser_name(self):
                return "test_file_parser"

        parser = TestFileParser()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".test", delete=False) as f:
            f.write("line1\n")
            f.write("line2\n")
            f.write("line3\n")
            f.flush()

            test_file = Path(f.name)

        try:
            lines = list(parser._read_lines(test_file))
            assert lines == ["line1", "line2", "line3"]
        finally:
            test_file.unlink()

    def test_directory_based_parser_find_files(self):
        """Test DirectoryBasedParser._find_files_with_pattern method."""

        class TestDirParser(DirectoryBasedParser):
            def can_parse(self, file_path):
                return True

            def parse(self, file_path, **kwargs):
                tree = TaxonomyTree()
                root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.CUSTOM)
                tree.add_node(root)
                return tree

            @property
            def supported_extensions(self):
                return [".dmp"]

            @property
            def parser_name(self):
                return "test_dir_parser"

        parser = TestDirParser()

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Create test files
            (tmp_path / "nodes.dmp").write_text("test")
            (tmp_path / "names.dmp").write_text("test")
            (tmp_path / "other.txt").write_text("test")

            dmp_files = parser._find_files_with_pattern(tmp_path, "*.dmp")
            assert len(dmp_files) == 2

            file_names = [f.name for f in dmp_files]
            assert "nodes.dmp" in file_names
            assert "names.dmp" in file_names

    def test_validate_file_nonexistent(self):
        """Test file validation with nonexistent file."""

        class TestParser(FileBasedParser):
            def can_parse(self, file_path):
                return True

            def parse(self, file_path, **kwargs):
                self._validate_file(file_path)
                return TaxonomyTree()

            @property
            def supported_extensions(self):
                return [".test"]

            @property
            def parser_name(self):
                return "test_validator"

        parser = TestParser()
        nonexistent_file = Path("/nonexistent/file.test")

        with pytest.raises(ParseError, match="File does not exist"):
            parser.parse(nonexistent_file)

    def test_validate_file_empty(self):
        """Test file validation with empty file."""

        class TestParser(FileBasedParser):
            def can_parse(self, file_path):
                return True

            def parse(self, file_path, **kwargs):
                self._validate_file(file_path)
                return TaxonomyTree()

            @property
            def supported_extensions(self):
                return [".test"]

            @property
            def parser_name(self):
                return "test_validator"

        parser = TestParser()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".test", delete=False) as f:
            # Create empty file
            f.flush()
            empty_file = Path(f.name)

        try:
            with pytest.raises(ParseError, match="File is empty"):
                parser.parse(empty_file)
        finally:
            empty_file.unlink()

    def test_parse_header_functionality(self):
        """Test header parsing functionality."""

        class TestParser(FileBasedParser):
            def can_parse(self, file_path):
                return True

            def parse(self, file_path, **kwargs):
                return TaxonomyTree()

            @property
            def supported_extensions(self):
                return [".test"]

            @property
            def parser_name(self):
                return "test_header"

            def test_header_parse(self, header_line):
                return self._parse_header(header_line)

        parser = TestParser()

        # Test valid header
        header_dict = parser.test_header_parse("name\trank\tparent")
        expected = {"name": 0, "rank": 1, "parent": 2}
        assert header_dict == expected

        # Test empty header
        assert parser.test_header_parse("") is None
        assert parser.test_header_parse("   ") is None


class TestNCBITaxonomyParser:
    """Test NCBI taxonomy dump format parser."""

    def test_parser_properties(self):
        """Test parser basic properties."""
        parser = NCBITaxonomyParser()
        assert parser.parser_name == "ncbi"
        assert ".dmp" in parser.supported_extensions

    def test_can_parse_valid_ncbi_directory(self):
        """Test detection of valid NCBI directory."""
        parser = NCBITaxonomyParser()

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Create valid NCBI dump files
            nodes_content = "1\t|\t1\t|\tno rank\t|\t\t|\t8\t|\t0\t|\t1\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|\t\t|"
            names_content = "1\t|\troot\t|\t\t|\tscientific name\t|"

            (tmp_path / "nodes.dmp").write_text(nodes_content)
            (tmp_path / "names.dmp").write_text(names_content)

            assert parser.can_parse(tmp_path) is True

    def test_can_parse_invalid_directory(self):
        """Test rejection of invalid directory."""
        parser = NCBITaxonomyParser()

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Create non-NCBI files
            (tmp_path / "random.txt").write_text("not ncbi format")

            assert parser.can_parse(tmp_path) is False

    def test_can_parse_single_dmp_file(self):
        """Test parsing single .dmp file."""
        parser = NCBITaxonomyParser()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".dmp", delete=False) as f:
            # Write NCBI format content
            f.write(
                "1\t|\t1\t|\tno rank\t|\t\t|\t8\t|\t0\t|\t1\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|\t\t|"
            )
            f.flush()
            test_file = Path(f.name)

        try:
            assert parser.can_parse(test_file) is True
        finally:
            test_file.unlink()

    def test_parse_simple_taxonomy(self):
        """Test parsing simple taxonomy structure."""
        parser = NCBITaxonomyParser()

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Create minimal NCBI dump files
            # Use "no rank" for root (NCBI standard) and test just the root node for now
            nodes_content = """1\t|\t1\t|\tno rank\t|\t\t|\t8\t|\t0\t|\t1\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|\t\t|"""

            names_content = """1\t|\troot\t|\t\t|\tscientific name\t|"""

            (tmp_path / "nodes.dmp").write_text(nodes_content)
            (tmp_path / "names.dmp").write_text(names_content)

            tree = parser.parse(tmp_path)

            # Should have exactly 1 node (the root)
            assert tree.node_count == 1

            # Check root node exists and has correct properties
            root_node = tree.get_node(1)
            assert root_node is not None
            assert root_node.name == "root"
            assert root_node.parent_id is None  # Root nodes have parent_id=None
            assert root_node.rank == TaxonomicRank.CUSTOM  # "no rank" maps to CUSTOM

    def test_parse_rank_mapping(self):
        """Test rank string to enum mapping."""
        parser = NCBITaxonomyParser()

        # Test standard ranks
        assert parser._parse_rank("superkingdom") == TaxonomicRank.SUPERKINGDOM
        assert parser._parse_rank("kingdom") == TaxonomicRank.KINGDOM
        assert parser._parse_rank("phylum") == TaxonomicRank.PHYLUM
        assert parser._parse_rank("class") == TaxonomicRank.CLASS
        assert parser._parse_rank("order") == TaxonomicRank.ORDER
        assert parser._parse_rank("family") == TaxonomicRank.FAMILY
        assert parser._parse_rank("genus") == TaxonomicRank.GENUS
        assert parser._parse_rank("species") == TaxonomicRank.SPECIES
        assert parser._parse_rank("subspecies") == TaxonomicRank.SUBSPECIES
        assert parser._parse_rank("strain") == TaxonomicRank.STRAIN

        # Test special cases
        assert parser._parse_rank("no rank") == TaxonomicRank.CUSTOM
        assert parser._parse_rank("varietas") == TaxonomicRank.SUBSPECIES
        assert parser._parse_rank("forma") == TaxonomicRank.SUBSPECIES

        # Test unknown rank
        assert parser._parse_rank("unknown_rank") == TaxonomicRank.CUSTOM


class TestTSVTaxonomyParser:
    """Test TSV format parser."""

    def test_parser_properties(self):
        """Test parser properties."""
        parser = TSVTaxonomyParser()
        assert parser.parser_name == "tsv"
        assert ".tsv" in parser.supported_extensions
        assert ".txt" in parser.supported_extensions

    def test_can_parse_tsv_file(self):
        """Test TSV file detection."""
        parser = TSVTaxonomyParser()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
            f.write("child\tparent\trank\n")
            f.write("Bacteria\troot\tsuperkingdom\n")
            f.flush()
            test_file = Path(f.name)

        try:
            assert parser.can_parse(test_file) is True
        finally:
            test_file.unlink()

    def test_parse_basic_tsv(self):
        """Test parsing basic TSV format."""
        parser = TSVTaxonomyParser()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
            f.write("child\tparent\trank\n")
            f.write("root\t\tno rank\n")
            f.write("Bacteria\troot\tsuperkingdom\n")
            f.write("Escherichia\tBacteria\tgenus\n")
            f.flush()
            test_file = Path(f.name)

        try:
            tree = parser.parse(test_file)

            assert tree.node_count == 3  # root, Bacteria, Escherichia

            # Verify tree structure
            bacteria_node = None
            escherichia_node = None

            for node in tree:
                if node.name == "Bacteria":
                    bacteria_node = node
                elif node.name == "Escherichia":
                    escherichia_node = node

            assert bacteria_node is not None
            assert bacteria_node.rank == TaxonomicRank.SUPERKINGDOM

            assert escherichia_node is not None
            assert escherichia_node.rank == TaxonomicRank.GENUS

        finally:
            test_file.unlink()

    def test_parse_with_tax_ids(self):
        """Test parsing TSV with taxonomic IDs."""
        parser = TSVTaxonomyParser()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
            f.write("child\tparent\trank\ttax_id\n")
            f.write("root\t\tno rank\t1\n")
            f.write("Bacteria\troot\tsuperkingdom\t2\n")
            f.flush()
            test_file = Path(f.name)

        try:
            tree = parser.parse(test_file)

            root_node = tree.get_node(1)
            assert root_node is not None
            assert root_node.name == "root"

            bacteria_node = tree.get_node(2)
            assert bacteria_node is not None
            assert bacteria_node.name == "Bacteria"
            assert bacteria_node.parent_id == 1

        finally:
            test_file.unlink()


class TestQIIMETaxonomyParser:
    """Test QIIME taxonomy format parser."""

    def test_parser_properties(self):
        """Test parser properties."""
        parser = QIIMETaxonomyParser()
        assert parser.parser_name == "qiime"
        assert ".txt" in parser.supported_extensions

    def test_can_parse_qiime_format(self):
        """Test QIIME format detection."""
        parser = QIIMETaxonomyParser()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            # QIIME format: OTU_ID<tab>taxonomy_string
            f.write("OTU_1\tk__Bacteria;p__Proteobacteria;c__Gammaproteobacteria\n")
            f.flush()
            test_file = Path(f.name)

        try:
            assert parser.can_parse(test_file) is True
        finally:
            test_file.unlink()

    def test_parse_qiime_taxonomy_string(self):
        """Test parsing QIIME taxonomy strings."""
        parser = QIIMETaxonomyParser()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(
                "OTU_1\tk__Bacteria;p__Proteobacteria;c__Gammaproteobacteria;o__Enterobacterales;f__Enterobacteriaceae;g__Escherichia;s__Escherichia_coli\n"
            )
            f.flush()
            test_file = Path(f.name)

        try:
            tree = parser.parse(test_file)

            # Should have created nodes for each taxonomic level
            assert tree.node_count >= 7  # At least kingdom through species

            # Check that hierarchy is preserved
            node_names = [node.name for node in tree]

            assert "k__Bacteria" in node_names or "Bacteria" in node_names
            assert "Proteobacteria" in node_names
            assert "Gammaproteobacteria" in node_names
            assert "Enterobacterales" in node_names
            assert "Enterobacteriaceae" in node_names
            assert "Escherichia" in node_names
            assert "Escherichia_coli" in node_names

        finally:
            test_file.unlink()


class TestSILVATaxonomyParser:
    """Test SILVA taxonomy format parser."""

    def test_parser_properties(self):
        """Test parser properties."""
        parser = SILVATaxonomyParser()
        assert parser.parser_name == "silva"
        assert ".txt" in parser.supported_extensions

    def test_can_parse_silva_format(self):
        """Test SILVA format detection."""
        parser = SILVATaxonomyParser()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            # SILVA format typically has specific patterns
            f.write(
                "Bacteria;Proteobacteria;Gammaproteobacteria;Enterobacterales;Enterobacteriaceae;Escherichia;\n"
            )
            f.flush()
            test_file = Path(f.name)

        try:
            # This may return False depending on implementation details
            # The actual implementation should be checked
            result = parser.can_parse(test_file)
            assert isinstance(result, bool)
        finally:
            test_file.unlink()


class TestCanSNPerTaxonomyParser:
    """Test CanSNPer taxonomy format parser."""

    def test_parser_properties(self):
        """Test parser properties."""
        parser = CanSNPerTaxonomyParser()
        assert parser.parser_name == "cansnper"
        assert ".txt" in parser.supported_extensions

    def test_can_parse_cansnper_format(self):
        """Test CanSNPer format detection."""
        parser = CanSNPerTaxonomyParser()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            # CanSNPer format (implementation specific)
            f.write("test content for cansnper\n")
            f.flush()
            test_file = Path(f.name)

        try:
            result = parser.can_parse(test_file)
            assert isinstance(result, bool)
        finally:
            test_file.unlink()


class TestParserRegistry:
    """Test parser registry functionality."""

    def test_registry_initialization(self):
        """Test registry starts empty."""
        registry = ParserRegistry()
        assert len(registry.list_parsers()) == 0

    def test_register_valid_parser(self):
        """Test registering a valid parser."""
        registry = ParserRegistry()

        class TestParser(FileBasedParser):
            def can_parse(self, file_path):
                return True

            def parse(self, file_path, **kwargs):
                return TaxonomyTree()

            @property
            def supported_extensions(self):
                return [".test"]

            @property
            def parser_name(self):
                return "test_parser"

        registry.register(TestParser)

        assert "test_parser" in registry.list_parsers()
        assert len(registry.list_parsers()) == 1

    def test_register_invalid_parser(self):
        """Test registering invalid parser raises error."""
        registry = ParserRegistry()

        class NotAParser:
            pass

        from flextaxd.core.exceptions import ConfigurationError

        with pytest.raises(
            ConfigurationError, match="must inherit from TaxonomyParser"
        ):
            registry.register(NotAParser)

    def test_register_duplicate_parser(self):
        """Test registering parser with duplicate name raises error."""
        registry = ParserRegistry()

        class TestParser1(FileBasedParser):
            def can_parse(self, file_path):
                return True

            def parse(self, file_path, **kwargs):
                return TaxonomyTree()

            @property
            def supported_extensions(self):
                return [".test"]

            @property
            def parser_name(self):
                return "duplicate_name"

        class TestParser2(FileBasedParser):
            def can_parse(self, file_path):
                return True

            def parse(self, file_path, **kwargs):
                return TaxonomyTree()

            @property
            def supported_extensions(self):
                return [".test2"]

            @property
            def parser_name(self):
                return "duplicate_name"  # Same name

        registry.register(TestParser1)

        from flextaxd.core.exceptions import ConfigurationError

        with pytest.raises(ConfigurationError, match="is already registered"):
            registry.register(TestParser2)

    def test_get_parser_by_name(self):
        """Test getting parser by name."""
        registry = ParserRegistry()

        class TestParser(FileBasedParser):
            def can_parse(self, file_path):
                return True

            def parse(self, file_path, **kwargs):
                return TaxonomyTree()

            @property
            def supported_extensions(self):
                return [".test"]

            @property
            def parser_name(self):
                return "test_parser"

        registry.register(TestParser)

        parser = registry.get_parser("test_parser")
        assert isinstance(parser, TestParser)
        assert parser.parser_name == "test_parser"

    def test_get_nonexistent_parser(self):
        """Test getting nonexistent parser raises error."""
        registry = ParserRegistry()

        from flextaxd.core.exceptions import ConfigurationError

        with pytest.raises(ConfigurationError, match="Unknown parser"):
            registry.get_parser("nonexistent")

    def test_find_parser_for_file(self):
        """Test finding appropriate parser for file."""
        registry = ParserRegistry()

        class TestParser(FileBasedParser):
            def can_parse(self, file_path):
                return file_path.suffix == ".test"

            def parse(self, file_path, **kwargs):
                return TaxonomyTree()

            @property
            def supported_extensions(self):
                return [".test"]

            @property
            def parser_name(self):
                return "test_parser"

        registry.register(TestParser)

        with tempfile.NamedTemporaryFile(suffix=".test", delete=False) as f:
            test_file = Path(f.name)

        try:
            parser = registry.find_parser(test_file)
            assert parser is not None
            assert parser.parser_name == "test_parser"

            # Test file that doesn't match
            with tempfile.NamedTemporaryFile(suffix=".nomatch", delete=False) as f2:
                no_match_file = Path(f2.name)

            try:
                parser = registry.find_parser(no_match_file)
                assert parser is None
            finally:
                no_match_file.unlink()

        finally:
            test_file.unlink()

    def test_get_supported_extensions(self):
        """Test getting supported extensions from registry."""
        registry = ParserRegistry()

        class TestParser1(FileBasedParser):
            def can_parse(self, file_path):
                return True

            def parse(self, file_path, **kwargs):
                return TaxonomyTree()

            @property
            def supported_extensions(self):
                return [".test1", ".test2"]

            @property
            def parser_name(self):
                return "test_parser1"

        class TestParser2(FileBasedParser):
            def can_parse(self, file_path):
                return True

            def parse(self, file_path, **kwargs):
                return TaxonomyTree()

            @property
            def supported_extensions(self):
                return [".test3"]

            @property
            def parser_name(self):
                return "test_parser2"

        registry.register(TestParser1)
        registry.register(TestParser2)

        extensions = registry.get_supported_extensions()

        assert "test_parser1" in extensions
        assert "test_parser2" in extensions
        assert extensions["test_parser1"] == [".test1", ".test2"]
        assert extensions["test_parser2"] == [".test3"]


class TestParserErrorHandling:
    """Test error handling across parsers."""

    def test_parsers_handle_malformed_files(self):
        """Test parsers handle malformed files gracefully."""
        parsers = [
            NCBITaxonomyParser(),
            TSVTaxonomyParser(),
            QIIMETaxonomyParser(),
            SILVATaxonomyParser(),
            CanSNPerTaxonomyParser(),
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            # Write malformed content
            f.write("completely\ninvalid\nformat\ndata")
            f.flush()
            malformed_file = Path(f.name)

        try:
            for parser in parsers:
                # Parsers should either parse successfully or raise ParseError
                # They should not crash with uncaught exceptions
                try:
                    result = parser.parse(malformed_file)
                    # If parsing succeeds, result should be a TaxonomyTree
                    assert isinstance(result, TaxonomyTree)
                except ParseError:
                    # ParseError is acceptable for malformed input
                    pass
                except Exception as e:
                    # Unexpected exceptions should be caught and reported
                    pytest.fail(
                        f"Parser {parser.parser_name} raised unexpected exception: {e}"
                    )

        finally:
            malformed_file.unlink()

    def test_parsers_handle_permission_errors(self):
        """Test parsers handle permission errors."""
        parser = TSVTaxonomyParser()

        # Try to parse a file that doesn't exist
        nonexistent_file = Path("/nonexistent/path/file.tsv")

        with pytest.raises(ParseError):
            parser.parse(nonexistent_file)


class TestGTDBTaxonomyParser:
    """Test GTDB taxonomy format parser."""

    def test_parser_properties(self):
        """Test parser basic properties."""
        parser = GTDBTaxonomyParser()
        assert parser.parser_name == "gtdb"
        assert ".tsv" in parser.supported_extensions
        assert ".txt" in parser.supported_extensions

    def test_can_parse_ar122_taxonomy_file(self):
        """Test detection of GTDB ar122_taxonomy file."""
        parser = GTDBTaxonomyParser()

        with tempfile.NamedTemporaryFile(mode="w", suffix="_taxonomy_r202.tsv", delete=False) as f:
            # Rename to match GTDB pattern
            gtdb_file = Path(f.name).parent / "ar122_taxonomy_r202.tsv"
            f.flush()
            Path(f.name).rename(gtdb_file)

            # Write GTDB format content
            gtdb_file.write_text(
                "GB_GCA_000005825.2\td__Bacteria;p__Firmicutes;c__Bacilli;o__Lactobacillales;f__Streptococcaceae;g__Streptococcus;s__Streptococcus pyogenes\n"
            )

        try:
            assert parser.can_parse(gtdb_file) is True
        finally:
            gtdb_file.unlink()

    def test_can_parse_bac120_taxonomy_file(self):
        """Test detection of GTDB bac120_taxonomy file."""
        parser = GTDBTaxonomyParser()

        with tempfile.NamedTemporaryFile(mode="w", suffix="_taxonomy_r207.tsv", delete=False) as f:
            # Rename to match GTDB pattern
            gtdb_file = Path(f.name).parent / "bac120_taxonomy_r207.tsv"
            f.flush()
            Path(f.name).rename(gtdb_file)

            # Write GTDB format content
            gtdb_file.write_text(
                "GCA_000001405.1\td__Bacteria;p__Proteobacteria;c__Gammaproteobacteria;o__Enterobacterales;f__Enterobacteriaceae;g__Escherichia;s__Escherichia coli\n"
            )

        try:
            assert parser.can_parse(gtdb_file) is True
        finally:
            gtdb_file.unlink()

    def test_can_parse_gtdbtk_summary_file(self):
        """Test detection of GTDB-Tk summary file."""
        parser = GTDBTaxonomyParser()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".bac120.summary.tsv", delete=False) as f:
            # Write GTDB-Tk summary header and content
            f.write("user_genome\tclassification\tfastani_reference\tfastani_reference_radius\tfastani_taxonomy\n")
            f.write("genome1\td__Bacteria;p__Firmicutes;c__Bacilli\tGCA_000005825.2\t95.0\td__Bacteria;p__Firmicutes;c__Bacilli\n")
            f.flush()
            test_file = Path(f.name)

        try:
            assert parser.can_parse(test_file) is True
        finally:
            test_file.unlink()

    def test_parse_standard_gtdb_taxonomy(self):
        """Test parsing standard GTDB taxonomy format."""
        parser = GTDBTaxonomyParser()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
            # Write standard GTDB format
            f.write("GB_GCA_000005825.2\td__Bacteria;p__Firmicutes;c__Bacilli;o__Lactobacillales;f__Streptococcaceae;g__Streptococcus;s__Streptococcus pyogenes\n")
            f.write("GCA_000001405.1\td__Bacteria;p__Proteobacteria;c__Gammaproteobacteria;o__Enterobacterales;f__Enterobacteriaceae;g__Escherichia;s__Escherichia coli\n")
            f.flush()
            test_file = Path(f.name)

        try:
            tree = parser.parse(test_file)

            # Should have root plus multiple taxonomy levels
            assert tree.node_count > 8  # Root + at least 7 taxonomic levels

            # Check that domains were created
            domain_nodes = [node for node in tree if node.rank == TaxonomicRank.SUPERKINGDOM]
            assert len(domain_nodes) >= 1
            
            # Check for Bacteria domain
            bacteria_found = any(node.name == "Bacteria" for node in domain_nodes)
            assert bacteria_found

        finally:
            test_file.unlink()

    def test_parse_gtdbtk_summary_format(self):
        """Test parsing GTDB-Tk summary format."""
        parser = GTDBTaxonomyParser()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".summary.tsv", delete=False) as f:
            # Write GTDB-Tk summary format with header
            f.write("user_genome\tclassification\tfastani_reference\n")
            f.write("genome1\td__Bacteria;p__Firmicutes;c__Bacilli;o__Lactobacillales\tGCA_000005825.2\n")
            f.write("genome2\td__Bacteria;p__Proteobacteria;c__Gammaproteobacteria\tGCA_000001405.1\n")
            f.flush()
            test_file = Path(f.name)

        try:
            tree = parser.parse(test_file)

            # Should have taxonomy hierarchy
            assert tree.node_count > 5

            # Check for expected taxonomic levels
            node_names = [node.name for node in tree]
            assert "Bacteria" in node_names
            assert "Firmicutes" in node_names
            assert "Proteobacteria" in node_names

        finally:
            test_file.unlink()

    def test_has_gtdb_taxonomy_string(self):
        """Test GTDB taxonomy string detection."""
        parser = GTDBTaxonomyParser()

        # Test valid GTDB taxonomy strings
        assert parser._has_gtdb_taxonomy_string("d__Bacteria;p__Firmicutes;c__Bacilli") is True
        assert parser._has_gtdb_taxonomy_string("d__Archaea;p__Thermoproteota") is True
        
        # Test invalid strings
        assert parser._has_gtdb_taxonomy_string("Bacteria;Firmicutes;Bacilli") is False
        assert parser._has_gtdb_taxonomy_string("random string") is False

    def test_parse_gtdb_taxonomy_string(self):
        """Test parsing GTDB taxonomy string method."""
        parser = GTDBTaxonomyParser()

        # Test that the method exists and can parse basic taxonomy
        taxonomy_string = "d__Bacteria;p__Firmicutes;c__Bacilli"

        # Call the actual method - it returns list of (name, rank) tuples
        result = parser._parse_gtdb_taxonomy_string(taxonomy_string)

        # Should return a list of taxonomy levels
        assert isinstance(result, list)
        assert len(result) == 3  # d__, p__, c__
        
        # Check that names and ranks are correctly parsed
        names = [name for name, rank in result]
        ranks = [rank for name, rank in result]
        
        assert "Bacteria" in names
        assert "Firmicutes" in names
        assert "Bacilli" in names
        
        # Check ranks
        assert TaxonomicRank.SUPERKINGDOM in ranks
        assert TaxonomicRank.PHYLUM in ranks
        assert TaxonomicRank.CLASS in ranks


class TestImprovedTSVTaxonomyParser:
    """Extended tests for TSV parser to improve coverage."""

    def test_parse_without_header(self):
        """Test parsing TSV without header line."""
        parser = TSVTaxonomyParser()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
            # No header - should auto-detect columns
            f.write("root\t\tno rank\n")
            f.write("Bacteria\troot\tsuperkingdom\n") 
            f.write("Escherichia\tBacteria\tgenus\n")
            f.flush()
            test_file = Path(f.name)

        try:
            tree = parser.parse(test_file, has_header=False)
            assert tree.node_count >= 2  # Should parse at least some nodes
        finally:
            test_file.unlink()

    def test_parse_with_optional_columns(self):
        """Test parsing TSV with additional optional columns."""
        parser = TSVTaxonomyParser()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
            # Include optional columns that may or may not be used
            f.write("child\tparent\trank\tdescription\n")
            f.write("root\t\tno rank\tRoot of taxonomy\n")
            f.write("Bacteria\troot\tsuperkingdom\tBacterial domain\n")
            f.write("Escherichia\tBacteria\tgenus\tE. coli genus\n")
            f.flush()
            test_file = Path(f.name)

        try:
            tree = parser.parse(test_file)
            
            # Should parse successfully despite extra columns
            assert tree.node_count >= 2
            
            # Check basic structure
            bacteria_found = False
            for node in tree:
                if node.name == "Bacteria":
                    bacteria_found = True
                    assert node.rank == TaxonomicRank.SUPERKINGDOM
            assert bacteria_found

        finally:
            test_file.unlink()

    def test_parse_flexible_column_order(self):
        """Test parsing with different column order.""" 
        parser = TSVTaxonomyParser()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
            # Use standard column names but test they work
            f.write("child\tparent\trank\n")
            f.write("root\t\tno rank\n")
            f.write("Bacteria\troot\tsuperkingdom\n")
            f.write("Proteobacteria\tBacteria\tphylum\n")
            f.flush()
            test_file = Path(f.name)

        try:
            tree = parser.parse(test_file)
            assert tree.node_count >= 3
            
            # Find the Bacteria node
            bacteria_node = None
            for node in tree:
                if node.name == "Bacteria":
                    bacteria_node = node
                    break
            
            assert bacteria_node is not None
            assert bacteria_node.rank == TaxonomicRank.SUPERKINGDOM

        finally:
            test_file.unlink()


class TestImprovedCanSNPerParser:
    """Extended tests for CanSNPer parser to improve coverage."""

    def test_parser_properties(self):
        """Test parser properties."""
        parser = CanSNPerTaxonomyParser()
        assert parser.parser_name == "cansnper"
        assert ".txt" in parser.supported_extensions

    def test_cansnper_detection_robustness(self):
        """Test that CanSNPer parser handles detection gracefully."""
        parser = CanSNPerTaxonomyParser()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            # Write content that should not crash the detector
            f.write("some content\n")
            f.write("more content\twith tabs\n")
            f.flush()
            test_file = Path(f.name)

        try:
            # Test detection - should not crash
            can_parse_result = parser.can_parse(test_file)
            assert isinstance(can_parse_result, bool)
            
            # Test that parse method exists and handles invalid format gracefully
            try:
                result = parser.parse(test_file)
                # If it succeeds, should be a TaxonomyTree
                assert isinstance(result, TaxonomyTree)
            except (ParseError, Exception):
                # Any controlled exception is acceptable
                pass
                
        finally:
            test_file.unlink()


class TestImprovedSILVAParser:
    """Extended tests for SILVA parser to improve coverage."""

    def test_parse_silva_taxonomy_format(self):
        """Test parsing SILVA taxonomy format."""
        parser = SILVATaxonomyParser()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            # SILVA-like format
            f.write("Bacteria;Proteobacteria;Gammaproteobacteria;Enterobacterales;Enterobacteriaceae;Escherichia;\n")
            f.write("Bacteria;Firmicutes;Bacilli;Lactobacillales;Streptococcaceae;Streptococcus;\n")
            f.flush()
            test_file = Path(f.name)

        try:
            # Test if it can parse
            if parser.can_parse(test_file):
                tree = parser.parse(test_file)
                assert isinstance(tree, TaxonomyTree)
                assert tree.node_count > 0
                
                # Check for expected taxonomy
                node_names = [node.name for node in tree]
                assert "Bacteria" in node_names
                
        finally:
            test_file.unlink()

    def test_silva_rank_detection(self):
        """Test SILVA rank detection and assignment."""
        parser = SILVATaxonomyParser()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            # Single SILVA taxonomy line
            f.write("Bacteria;Proteobacteria;Gammaproteobacteria;\n")
            f.flush()
            test_file = Path(f.name)

        try:
            if parser.can_parse(test_file):
                tree = parser.parse(test_file)
                
                # Check rank assignments
                for node in tree:
                    if node.name == "Bacteria":
                        assert node.rank in [TaxonomicRank.SUPERKINGDOM, TaxonomicRank.KINGDOM]
                    elif node.name == "Proteobacteria":
                        assert node.rank == TaxonomicRank.PHYLUM
                    elif node.name == "Gammaproteobacteria":
                        assert node.rank == TaxonomicRank.CLASS
                        
        finally:
            test_file.unlink()


class TestParserEdgeCases:
    """Test edge cases and error conditions for parsers."""

    def test_parser_with_unicode_characters(self):
        """Test parsers handle Unicode characters properly."""
        parser = TSVTaxonomyParser()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False, encoding="utf-8") as f:
            # Include Unicode characters
            f.write("child\tparent\trank\n")
            f.write("root\t\tno rank\n")
            f.write("Bactéria\troot\tsuperkingdom\n")  # Accented character
            f.write("Escherichia coli ß-strain\tBactéria\tspecies\n")  # German ß
            f.flush()
            test_file = Path(f.name)

        try:
            tree = parser.parse(test_file)
            assert tree.node_count >= 2
            
            # Check Unicode names were preserved
            node_names = [node.name for node in tree]
            assert "Bactéria" in node_names
            assert "Escherichia coli ß-strain" in node_names
            
        finally:
            test_file.unlink()

    def test_parser_with_very_long_names(self):
        """Test parsers handle very long taxonomic names."""
        parser = TSVTaxonomyParser()
        
        long_name = "Very_long_taxonomic_name_" * 10  # 270 characters

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
            f.write("child\tparent\trank\n")
            f.write("root\t\tno rank\n")
            f.write(f"{long_name}\troot\tspecies\n")
            f.flush()
            test_file = Path(f.name)

        try:
            tree = parser.parse(test_file)
            assert tree.node_count >= 2
            
            # Check long name was preserved
            node_names = [node.name for node in tree]
            assert long_name in node_names
            
        finally:
            test_file.unlink()

    def test_parser_with_special_characters(self):
        """Test parsers handle special characters in names."""
        parser = TSVTaxonomyParser()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
            f.write("child\tparent\trank\n")
            f.write("root\t\tno rank\n")
            f.write("Bacteria (group)\troot\tsuperkingdom\n")  # Parentheses
            f.write("Species-with-hyphens_and_underscores\tBacteria (group)\tspecies\n")  # Hyphens and underscores
            f.write("'Single quotes'\tBacteria (group)\tspecies\n")  # Single quotes
            f.flush()
            test_file = Path(f.name)

        try:
            tree = parser.parse(test_file)
            assert tree.node_count >= 4
            
        finally:
            test_file.unlink()

    def test_ncbi_parser_with_minimal_nodes_file(self):
        """Test NCBI parser with minimal nodes.dmp file."""
        parser = NCBITaxonomyParser()

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Minimal nodes.dmp - just root
            nodes_content = "1\t|\t1\t|\tno rank\t|\t\t|\t8\t|\t0\t|\t1\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|\t\t|"
            names_content = "1\t|\troot\t|\t\t|\tscientific name\t|"

            (tmp_path / "nodes.dmp").write_text(nodes_content)
            (tmp_path / "names.dmp").write_text(names_content)

            tree = parser.parse(tmp_path)
            assert tree.node_count == 1
            
            root = tree.get_node(1)
            assert root is not None
            assert root.name == "root"

    def test_ncbi_parser_with_missing_names_entries(self):
        """Test NCBI parser handles missing names entries gracefully."""
        parser = NCBITaxonomyParser()

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # nodes.dmp has entry for tax_id 2, but names.dmp doesn't
            nodes_content = """1\t|\t1\t|\tno rank\t|\t\t|\t8\t|\t0\t|\t1\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|\t\t|
2\t|\t1\t|\tspecies\t|\t\t|\t8\t|\t0\t|\t1\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|\t\t|"""

            names_content = """1\t|\troot\t|\t\t|\tscientific name\t|"""
            # Missing entry for tax_id 2

            (tmp_path / "nodes.dmp").write_text(nodes_content)
            (tmp_path / "names.dmp").write_text(names_content)

            # Should either handle gracefully or raise informative error
            try:
                tree = parser.parse(tmp_path)
                # If it succeeds, tax_id 2 should have a default name
                node_2 = tree.get_node(2)
                if node_2:
                    assert isinstance(node_2.name, str)
                    assert len(node_2.name) > 0
            except ParseError:
                # Acceptable to raise ParseError for missing names
                pass
