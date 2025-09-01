"""Database abstraction layer for FlexTaxD."""

from .repository import TaxonomyRepository
from .sqlite import SQLiteTaxonomyRepository

__all__ = ["TaxonomyRepository", "SQLiteTaxonomyRepository"]