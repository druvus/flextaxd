"""Parser registry for dynamic parser discovery and loading."""

from typing import Dict, Type, List, Optional, Any
from pathlib import Path

from .base import TaxonomyParser
from ..core.exceptions import ConfigurationError


class ParserRegistry:
    """Registry for managing taxonomy parsers."""

    def __init__(self) -> None:
        self._parsers: Dict[str, Type[TaxonomyParser]] = {}

    def register(self, parser_class: Type[TaxonomyParser]) -> None:
        """Register a parser class."""
        if not issubclass(parser_class, TaxonomyParser):
            raise ConfigurationError(
                f"Parser {parser_class.__name__} must inherit from TaxonomyParser"
            )

        # Instantiate to get parser name (since it's an instance property)
        try:
            parser_instance = parser_class()
            parser_name = parser_instance.parser_name
        except Exception as e:
            raise ConfigurationError(
                f"Cannot instantiate parser {parser_class.__name__}: {e}"
            )

        if parser_name in self._parsers:
            raise ConfigurationError(f"Parser '{parser_name}' is already registered")

        self._parsers[parser_name] = parser_class

    def get_parser(self, parser_name: str, **kwargs: Any) -> TaxonomyParser:
        """Get a parser instance by name."""
        if parser_name not in self._parsers:
            raise ConfigurationError(f"Unknown parser: {parser_name}")

        parser_class = self._parsers[parser_name]
        return parser_class(**kwargs)

    def find_parser(self, file_path: Path, **kwargs: Any) -> Optional[TaxonomyParser]:
        """Find the best parser for a given file."""
        for parser_class in self._parsers.values():
            parser = parser_class(**kwargs)
            if parser.can_parse(file_path):
                return parser
        return None

    def list_parsers(self) -> List[str]:
        """List all registered parser names."""
        return list(self._parsers.keys())

    def get_supported_extensions(self) -> Dict[str, List[str]]:
        """Get supported file extensions for each parser."""
        extensions = {}
        for name, parser_class in self._parsers.items():
            # We need to instantiate to get extensions (not ideal, but works)
            try:
                parser = parser_class()
                extensions[name] = parser.supported_extensions
            except Exception:
                # Skip parsers that can't be instantiated without parameters
                extensions[name] = []
        return extensions


# Global registry instance
registry = ParserRegistry()
