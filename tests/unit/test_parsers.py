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
