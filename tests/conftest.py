"""Test configuration and shared fixtures for FlexTaxD tests."""

import tempfile
import os
import sqlite3
from pathlib import Path
from typing import Generator

import pytest


@pytest.fixture
def temp_database() -> Generator[str, None, None]:
    """Create a temporary SQLite database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".ftd", delete=False) as tmp_file:
        db_path = tmp_file.name
    
    try:
        # Use our modernized database schema through SQLiteTaxonomyRepository
        from flextaxd.database.sqlite import SQLiteTaxonomyRepository
        from flextaxd.core.models import TaxonomyNode, TaxonomicRank
        
        # Initialize with modern schema
        with SQLiteTaxonomyRepository(db_path) as repo:
            # Add some test data with the modern schema
            root_node = TaxonomyNode(
                tax_id=1,
                name='root',
                rank=TaxonomicRank.ROOT,
                parent_id=None
            )
            bacteria_node = TaxonomyNode(
                tax_id=2,
                name='Bacteria',
                rank=TaxonomicRank.SUPERKINGDOM,
                parent_id=1
            )
            archaea_node = TaxonomyNode(
                tax_id=3,
                name='Archaea',
                rank=TaxonomicRank.SUPERKINGDOM,
                parent_id=1
            )
            
            repo.add_node(root_node)
            repo.add_node(bacteria_node)
            repo.add_node(archaea_node)
        
        yield db_path
    finally:
        # Clean up
        if os.path.exists(db_path):
            os.unlink(db_path)


@pytest.fixture
def sample_taxonomy_file() -> Generator[str, None, None]:
    """Create a sample taxonomy file for testing."""
    content = """parent	child
root	Bacteria
root	Archaea
Bacteria	Escherichia coli
Archaea	Methanocaldococcus
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.tsv', delete=False) as tmp_file:
        tmp_file.write(content)
        tmp_file.flush()
        
        yield tmp_file.name
    
    # Clean up
    if os.path.exists(tmp_file.name):
        os.unlink(tmp_file.name)


@pytest.fixture
def test_data_dir() -> Path:
    """Return path to test data directory."""
    return Path(__file__).parent / "fixtures"